"""SDL integrity requirements execute through a supported contract or fail closed."""

import io
from dataclasses import replace

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts import ExperimentRunEvidenceInputs, validate_experiment_run_against_task
from raes_contracts.planning import PlanScope
from raes_processor.capture_admission import capture_admission_diagnostics, compile_capture_spec_demands
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime import RuntimeControlPlane
from test_issue_1112_capture_admission import _capture_scenario, _evidence_bundle, _manifest_with_offers, _offer


@pytest.mark.parametrize("mode", ["chain_of_custody", "signature", "timestamped", "other"])
@pytest.mark.parametrize("advertised", ["exact", "wildcard"])
def test_advertised_mode_without_response_verifier_is_refused_before_effects(mode, advertised):
    scenario = _capture_scenario()
    scenario.evidence_requirements["attacker-action-log"].integrity = mode
    target = create_stub_target()
    manifest = replace(
        target.manifest,
        capabilities=replace(
            target.manifest.capabilities,
            observation=replace(
                target.manifest.observation,
                capture_offers=(_offer(integrity_modes=frozenset({mode if advertised == "exact" else "*"})),),
            ),
        ),
    )
    target = replace(target, manifest=manifest)
    model = compile_runtime_model(scenario)
    assert model.capture_demands[0].integrity_modes == (mode,)
    execution = plan(model, manifest, scope=PlanScope(target_name=target.name))
    assert any(d.code == "capture.integrity-verifier-unavailable" for d in execution.diagnostics)
    assert not execution.is_valid
    with RuntimeControlPlane(target) as runtime:
        receipt = runtime.submit_provisioning(execution.provisioning)
        assert not receipt.accepted
        assert runtime.snapshot.entries == {}


def test_capture_spec_custody_is_not_satisfied_by_an_advertised_string():
    _, _, spec, _, _ = _evidence_bundle()
    spec.capture_requirements["auth-log-evidence"].integrity_requirements = ["checksum", "chain_of_custody"]
    demands = compile_capture_spec_demands((spec,))
    assert demands[0].integrity_modes == ("checksum", "chain_of_custody")
    diagnostics = capture_admission_diagnostics(
        demands, _manifest_with_offers(_offer(integrity_modes=frozenset({"*"}))).observation
    )
    assert any(d.code == "capture.integrity-verifier-unavailable" for d in diagnostics)


@pytest.mark.parametrize("mode", ["chain_of_custody", "signature"])
def test_checksum_and_asserted_provenance_do_not_prove_custody_or_signature(mode):
    task, run, spec, record, _ = _evidence_bundle()
    spec.capture_requirements["auth-log-evidence"].integrity_requirements = [mode]

    class Unreadable(io.BytesIO):
        def read(self, size=-1):
            pytest.fail("unsupported integrity reached artifact I/O")

    evidence = ExperimentRunEvidenceInputs(
        {spec.capture_spec_id: spec},
        {record.evidence_record_id: record},
        {run.evidence_artifacts[0].artifact_id: Unreadable()},
    )
    with pytest.raises(ValueError, match="cannot prove integrity requirement"):
        validate_experiment_run_against_task(task, run, evidence=evidence)


@pytest.mark.parametrize("mode", ["checksum", "sha256-digest"])
def test_supported_integrity_modes_keep_exact_content_proof_without_custody_policy(mode):
    task, run, spec, record, payload = _evidence_bundle()
    spec.capture_requirements["auth-log-evidence"].integrity_requirements = [mode]
    proof = validate_experiment_run_against_task(
        task,
        run,
        evidence=ExperimentRunEvidenceInputs(
            {spec.capture_spec_id: spec},
            {record.evidence_record_id: record},
            {run.evidence_artifacts[0].artifact_id: io.BytesIO(payload)},
        ),
    )
    assert proof.satisfies(run, task.evaluation_protocol.observation_requirements[0])


def test_no_authored_capture_demand_does_not_create_a_custody_requirement():
    scenario = _capture_scenario()
    scenario.evidence_requirements = {}
    compiled = compile_runtime_model(scenario)
    assert compiled.capture_demands == ()
    assert plan(compiled, _manifest_with_offers()).is_valid


def test_sha256_demand_rejects_another_checksum_algorithm_before_io():
    task, run, spec, record, _ = _evidence_bundle()
    spec.capture_requirements["auth-log-evidence"].integrity_requirements = ["sha256-digest"]
    run.evidence_artifacts[0].checksum.algorithm = "blake3"
    record.raw_content.content_checksum.algorithm = "blake3"

    class Unreadable(io.BytesIO):
        def read(self, size=-1):
            pytest.fail("incompatible integrity algorithm reached artifact I/O")

    evidence = ExperimentRunEvidenceInputs(
        {spec.capture_spec_id: spec},
        {record.evidence_record_id: record},
        {run.evidence_artifacts[0].artifact_id: Unreadable()},
    )
    with pytest.raises(ValueError, match="required sha256 integrity mode"):
        validate_experiment_run_against_task(task, run, evidence=evidence)


def test_authored_none_capture_accepts_checksum_backend_without_extra_integrity_demand():
    scenario = _capture_scenario()
    scenario.evidence_requirements["attacker-action-log"].integrity = "none"
    model = compile_runtime_model(scenario)
    assert model.capture_demands
    assert model.capture_demands[0].integrity_modes == ()
    assert plan(model, _manifest_with_offers(_offer())).is_valid
    task, run, spec, record, payload = _evidence_bundle()
    spec.capture_requirements["auth-log-evidence"].integrity_requirements = ["none"]
    assert compile_capture_spec_demands((spec,))[0].integrity_modes == ()
    proof = validate_experiment_run_against_task(
        task,
        run,
        evidence=ExperimentRunEvidenceInputs(
            {spec.capture_spec_id: spec},
            {record.evidence_record_id: record},
            {run.evidence_artifacts[0].artifact_id: io.BytesIO(payload)},
        ),
    )
    assert proof.satisfies(run, task.evaluation_protocol.observation_requirements[0])


@pytest.mark.parametrize("failure", [None, "retention", "bytes"])
def test_admitted_capture_policies_reach_installed_owner_and_checked_response(failure):
    from issue_1629_trial_fixture import factorial_inputs
    from issue_1630_record_fixture import ContentServices, metadata_for, readers, record_request
    from raes_contracts.canonical import canonical_contract_digest
    from raes_contracts.errors import ConflictError

    _, inputs, target = factorial_inputs(record_request)
    spec = next(iter(inputs.capture_specs.values()))
    required = spec.capture_requirements["auth-log-evidence"]

    class BoundCaptureOwner(ContentServices):
        def resolve_capture(self, request):
            # The installed owner resolves the exact pinned capture contract.
            # RAE must retain that pin in admission and every capture request.
            refs = request.plan.input_refs.capture_spec_refs
            assert len(refs) == 1
            ref = refs[0]
            assert (ref.ref_id, ref.ref_version, ref.ref_digest) == (
                spec.capture_spec_id,
                spec.spec_version,
                canonical_contract_digest(spec),
            )
            assert required.integrity_requirements == ["sha256-digest"]
            assert required.retention_policy == "Retain raw evidence for the experiment review window."
            if failure == "retention":
                raise ConflictError("installed capture owner cannot execute the retention policy")

        def admit(self, request):
            self.resolve_capture(request)
            return super().admit(request)

        def capture(self, request, snapshot):
            self.resolve_capture(request)
            return super().capture(request, snapshot)

    services = BoundCaptureOwner(target)
    with RuntimeControlPlane(target) as runtime:
        if failure == "retention":
            with pytest.raises(ConflictError, match="retention policy"):
                runtime.admit_experiment(inputs, services=services)
            assert services.events == []
            assert runtime.snapshot.entries == {}
            return
        experiment = runtime.admit_experiment(inputs, services=services)
        first = runtime._experiments[experiment].schedule.entries[0].run_id
        for _ in range(20):
            runtime.advance_experiment(experiment)
            if runtime.get_run("run:" + first)._retired:
                break
        assert (first, "capture") in services.events
        source = next(item for item in runtime.experiment_records(experiment).sources if item.run_id == first)
        metadata = metadata_for(runtime, experiment, source)
        read = readers(inputs, services)

        def response(run):
            evidence = read(run)
            if failure == "bytes":
                evidence = replace(
                    evidence,
                    artifact_readers={
                        "auth-log-evidence": io.BytesIO(b"x" * len(services.content)),
                    },
                )
            return evidence

        result = runtime.experiment_records(experiment, metadata={first: metadata}, evidence_reader=response)
        assert result.validation_by_run[first] == ("failed" if failure == "bytes" else "passed")
        assert (first in result.eligible_run_ids) is (failure is None)


def test_none_does_not_falsely_strengthen_a_scoped_integrity_requirement():
    from raes.authored_scenario_evidence import AuthoredScenarioEvidenceView
    from raes_contracts.contracts import (
        ExperimentEvidenceRequirementRelationModel,
        validate_evidence_requirement_relations,
    )
    from test_exp_731_evidence_requirement_refinement import (
        _authority_ref,
        _capture_spec,
        _fixture,
        _relation,
        _scenario,
    )

    scenario = _scenario()
    scenario.evidence_requirements["event-log"].integrity = "none"
    authority = _authority_ref("task", _fixture("experiment-task-v1"))
    relation = ExperimentEvidenceRequirementRelationModel.model_validate(
        _relation(scenario, authority, dimensions=["integrity-requirements"])
    )
    spec = _capture_spec(authority, integrity=["none"])
    scenario_view = AuthoredScenarioEvidenceView(scenario)
    with pytest.raises(ValueError, match="must strengthen"):
        validate_evidence_requirement_relations(
            (relation,), scenario=scenario_view, capture_specs={spec.capture_spec_id: spec}
        )
