"""Regression evidence for the scope review's authorization and lifecycle findings."""

import json
from dataclasses import replace

import pytest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_operations.run_artifacts import RunMaterializationArchive
from raes_runtime.backend_calls import _BackendCallContext, _call_backend_apply, _RealizationApplyContext
from test_issue_1242_scope_admission import scoped_plan
from test_issue_1242_scope_runtime import ScopeReportingProvisioner


@pytest.mark.parametrize("phase", ["provisioning", "evaluation", "orchestration"])
@pytest.mark.parametrize("permission", ["open", "closed"])
def test_stripped_diagnostics_cannot_erase_required_scope_negotiation(tmp_path, phase, permission):
    execution = scoped_plan({"default": permission}, negotiated=False)
    from raes_contracts.planning import PlanScope
    from raes_processor.planner import plan

    manifest = replace(
        execution.manifest,
        supported_contract_versions=execution.manifest.supported_contract_versions
        - {"backend-augmentation-scope-v1", "backend-materialization-attestation-v1"},
    )
    execution = plan(execution.model, manifest, scope=PlanScope(run_id="run-1"))
    request = replace(getattr(execution, phase), diagnostics=[])
    calls = []

    def mutate(plan, previous):
        calls.append(phase)
        return ApplyResult(True, previous)

    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        mutate,
        request,
        previous,
        address="runtime.detached",
        snapshot=previous,
        realization=_RealizationApplyContext(manifest=execution.manifest),
        call=_BackendCallContext(materialization_archive=RunMaterializationArchive(tmp_path)),
    )
    assert not result.success
    assert calls == []


@pytest.mark.parametrize("phase", ["provisioning", "evaluation", "orchestration"])
@pytest.mark.parametrize("planning_support", [True, False])
def test_cleared_scope_flag_cannot_erase_bound_source_policy(tmp_path, phase, planning_support):
    execution = scoped_plan({"default": "closed"}, negotiated=planning_support)
    request = replace(getattr(execution, phase), diagnostics=[], augmentation_scope_required=False)
    manifest = replace(
        execution.manifest,
        supported_contract_versions=execution.manifest.supported_contract_versions - {"backend-augmentation-scope-v1"},
    )
    calls = []

    def mutate(plan, previous):
        calls.append(phase)
        return ApplyResult(True, previous)

    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        mutate,
        request,
        previous,
        address="runtime.detached",
        snapshot=previous,
        realization=_RealizationApplyContext(manifest=manifest),
        call=_BackendCallContext(materialization_archive=RunMaterializationArchive(tmp_path)),
    )
    assert request.materialization_source is not None
    assert not result.success
    assert calls == []


@pytest.mark.parametrize("phase", ["provisioning", "evaluation", "orchestration"])
def test_source_policy_cannot_be_removed_without_invalidating_its_bound_identity(tmp_path, phase):
    execution = scoped_plan({"default": "closed"})
    request = getattr(execution, phase)
    payload = json.loads(request.materialization_source.snapshot)
    payload["scenario"].pop("augmentation_scope")
    request = replace(
        request,
        augmentation_scope_required=False,
        materialization_source=request.materialization_source.model_copy(update={"snapshot": json.dumps(payload)}),
    )
    manifest = replace(
        execution.manifest,
        supported_contract_versions=execution.manifest.supported_contract_versions - {"backend-augmentation-scope-v1"},
    )
    calls = []

    def mutate(plan, previous):
        calls.append(phase)
        return ApplyResult(True, previous)

    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        mutate,
        request,
        previous,
        address="runtime.detached",
        snapshot=previous,
        realization=_RealizationApplyContext(manifest=manifest),
        call=_BackendCallContext(materialization_archive=RunMaterializationArchive(tmp_path)),
    )
    assert not result.success
    assert calls == []


@pytest.mark.parametrize("severity", ["warning", "info"])
def test_advisory_preparation_does_not_fail_whole_run_or_emit_duplicates(tmp_path, severity):
    from raes_backend_protocols.manifest import backend_manifest_v2_model
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.diagnostics import Diagnostic, Severity
    from raes_contracts.realization_preparation import RealizationPreparation, RealizationPreparationAuthority
    from raes_runtime import RuntimeManager
    from raes_runtime.registry import RuntimeTarget

    execution = scoped_plan({"default": "closed"})
    manifest = replace(
        execution.manifest,
        supported_contract_versions=execution.manifest.supported_contract_versions
        | {"backend-realization-preparation-v1"},
    )
    notice = Diagnostic("test.advisory", "runtime", "runtime.prepare", "Advisory.", severity=Severity(severity))

    class AdvisoryProducer(ScopeReportingProvisioner):
        def prepare(self, request, previous):
            return replace(
                RealizationPreparation.for_request(request, previous, operations=tuple(request.operations)),
                diagnostics=(notice,),
            )

    backend = AdvisoryProducer(manifest)
    manager = RuntimeManager(
        RuntimeTarget(name="scope", manifest=manifest, provisioner=backend),
        materialization_archive=RunMaterializationArchive(tmp_path),
    )
    request = replace(
        execution.provisioning,
        preparation=RealizationPreparationAuthority(
            manifest_digest=canonical_json_digest(backend_manifest_v2_model(manifest).model_dump(mode="json"))
        ),
    )
    result = manager.apply(replace(execution, target_name="scope", manifest=manifest, provisioning=request))
    assert result.success, result.diagnostics
    assert backend.calls == 1
    assert result.diagnostics.count(notice) == 1


@pytest.mark.parametrize("phase", ["evaluation", "orchestration"])
def test_later_phase_preserves_prior_additions_without_claiming_their_effects(tmp_path, phase):
    from raes import admit_instantiated_scenario, parse_sdl
    from raes_contracts.materialization import MaterializationSubmission
    from raes_processor.compiler.materialization_origins import materialization_differences

    execution = scoped_plan({"default": "open"})
    archive = RunMaterializationArchive(tmp_path)
    provisioner = ScopeReportingProvisioner(execution.manifest, addition=True)
    previous = RuntimeSnapshot()
    first = _call_backend_apply(
        provisioner.apply,
        execution.provisioning,
        previous,
        address="runtime.first",
        snapshot=previous,
        realization=_RealizationApplyContext(plan=execution.provisioning, manifest=execution.manifest),
        call=_BackendCallContext(materialization_archive=archive),
    )
    assert first.success, first.diagnostics

    class LaterProducer(ScopeReportingProvisioner):
        def start(self, request, previous):
            self.calls += 1
            self.mutate = self.add_listener
            result = self.report(request, previous, ApplyResult(True, previous))
            document = json.loads(result.materialization_attestation.sdl)
            document["materialization_provenance"]["attestation_id"] = "materialization-later"
            original = admit_instantiated_scenario(json.loads(request.materialization_source.snapshot)["scenario"])
            document["materialization_provenance"]["origins"] = [
                item.model_dump(mode="json")
                for item in materialization_differences(original, parse_sdl(json.dumps(document)))
            ]
            return replace(result, materialization_attestation=MaterializationSubmission(sdl=json.dumps(document)))

    backend = LaterProducer(execution.manifest)
    result = _call_backend_apply(
        backend.start,
        getattr(execution, phase),
        first.snapshot,
        address="runtime.later",
        snapshot=first.snapshot,
        realization=_RealizationApplyContext(manifest=execution.manifest),
        call=_BackendCallContext(materialization_archive=archive),
    )
    assert result.success, result.diagnostics
    assert backend.calls == 1
    assert len(result.snapshot.materialization_attestations) == 2
    assert parse_sdl(result.materialization_attestation.sdl).nodes["host"].services[0].name == "metrics"


@pytest.mark.parametrize("phase", ["provisioning", "evaluation", "orchestration"])
def test_required_scope_fact_survives_wire_roundtrip_and_binds_authorization(phase):
    from raes_contracts import plan_projection
    from raes_contracts.plan_effects import plan_can_mutate
    from raes_runtime import control_plane_api_models

    request = replace(getattr(scoped_plan({"default": "closed"}, negotiated=False), phase), diagnostics=[])
    projected = getattr(plan_projection, f"{phase}_plan_model")(request)
    wire = type(projected).model_validate_json(projected.model_dump_json())
    restored = getattr(control_plane_api_models, f"_{phase}_plan")(wire)
    assert restored.augmentation_scope_required is True
    assert plan_projection.runtime_plan_digest(restored) == plan_projection.runtime_plan_digest(request)
    assert plan_projection.runtime_plan_digest(
        replace(restored, augmentation_scope_required=False)
    ) != plan_projection.runtime_plan_digest(request)
    assert plan_can_mutate(type(restored)(augmentation_scope_required=True))


def test_composition_uses_native_member_identity_and_rejects_overlapping_ownership():
    from raes.prospective_content import admit_prospective_content
    from raes_processor.compiler.materialization_origins import compose_materialization_content

    def content(services):
        return admit_prospective_content(
            {"name": "scope", "nodes": {"host": {"type": "compute", "services": services}}}
        )

    base = content([{"name": "original", "port": 80}])
    prior = content([{"name": "collector", "port": 9000}, {"name": "original", "port": 80}])
    local = content([{"name": "listener", "port": 9090}, {"name": "original", "port": 80}])
    combined = compose_materialization_content(base, prior, local)
    assert {service.name for service in combined.nodes["host"].services} == {"original", "collector", "listener"}
    with pytest.raises(ValueError, match="overlap"):
        compose_materialization_content(base, prior, prior)
    removed = admit_prospective_content({"name": "scope", "nodes": {}})
    with pytest.raises(ValueError, match="overlap"):
        compose_materialization_content(base, prior, removed)


@pytest.mark.parametrize("overlap", [False, True])
def test_manager_composes_all_phases_before_mutation_and_preserves_cumulative_world(tmp_path, overlap):
    from raes import admit_instantiated_scenario, parse_sdl
    from raes_backend_stubs.stubs import create_stub_manifest
    from raes_contracts.materialization import MaterializationSubmission
    from raes_contracts.planning import PlanScope
    from raes_processor.compiler.materialization_origins import materialization_differences
    from raes_processor.planner import plan
    from raes_runtime import RuntimeManager
    from raes_runtime.registry import RuntimeTarget
    from test_runtime_manager import RecordingEvaluator, RecordingOrchestrator, _full_scenario

    source = _full_scenario().model_dump(mode="json", exclude_unset=True)
    source["realization"] = {"default": "open"}
    source["nodes"]["host"] = source["nodes"].pop("vm")
    source["propositions"]["health"]["subjects"] = ["nodes.host"]
    execution = scoped_plan({"default": "open"}, content=source)
    stub = create_stub_manifest()
    manifest = replace(
        execution.manifest,
        capabilities=replace(execution.manifest.capabilities, evaluator=stub.evaluator, orchestrator=stub.orchestrator),
    )
    execution = plan(execution.model, manifest, scope=PlanScope(run_id="run-1", target_name="scope"))
    assert execution.is_valid, execution.diagnostics
    assert execution.evaluation.actionable_operations
    assert execution.orchestration.actionable_operations
    calls = []

    class CumulativeReportingMixin:
        def prepare_augmentation(self, request, previous):
            return ScopeReportingProvisioner(manifest, addition=overlap).prepare_augmentation(request, previous)

        def start(self, request, previous):
            result = super().start(request, previous)
            reporter = ScopeReportingProvisioner(manifest)
            reporter.mutate = reporter.add_listener
            result = reporter.report(request, previous, result)
            document = json.loads(result.materialization_attestation.sdl)
            document["materialization_provenance"]["attestation_id"] = self.name
            original = admit_instantiated_scenario(json.loads(request.materialization_source.snapshot)["scenario"])
            document["materialization_provenance"]["origins"] = [
                item.model_dump(mode="json")
                for item in materialization_differences(original, parse_sdl(json.dumps(document)))
            ]
            return replace(result, materialization_attestation=MaterializationSubmission(sdl=json.dumps(document)))

    class Evaluator(CumulativeReportingMixin, RecordingEvaluator):
        pass

    class Orchestrator(CumulativeReportingMixin, RecordingOrchestrator):
        pass

    provisioner = ScopeReportingProvisioner(manifest, addition=True)
    manager = RuntimeManager(
        RuntimeTarget(
            name="scope",
            manifest=manifest,
            provisioner=provisioner,
            evaluator=Evaluator(calls, "evaluation"),
            orchestrator=Orchestrator(calls, "orchestration"),
        ),
        materialization_archive=RunMaterializationArchive(tmp_path),
    )
    result = manager.apply(execution)
    assert result.success is not overlap, result.diagnostics
    if overlap:
        assert provisioner.calls == 0
        assert calls == []
        assert any(item.code == "augmentation.composition-invalid" for item in result.diagnostics)
    else:
        assert provisioner.calls == 1
        assert calls == ["evaluation-start", "orchestration-start"]
        assert len(result.snapshot.materialization_attestations) == 3
        assert parse_sdl(result.materialization_attestation.sdl).nodes["host"].services[0].name == "metrics"


@pytest.mark.parametrize("damage", ["bytes", "symlink", "foreign-path"])
def test_prior_attestation_read_refuses_corruption_and_unsafe_paths(tmp_path, damage):
    from test_issue_1242_scope_runtime import apply

    result, _ = apply(tmp_path, {"default": "open"}, addition=True)
    assert result.success
    record = result.snapshot.materialization_attestations[-1]
    path = tmp_path / record.reference.ref_path
    if damage == "bytes":
        path.write_text("corrupt")
    elif damage == "symlink":
        moved = path.with_suffix(".retained")
        path.rename(moved)
        path.symlink_to(moved)
    else:
        record = record.model_copy(
            update={"reference": record.reference.model_copy(update={"ref_path": "/tmp/foreign.sdl"})}
        )
    archive = RunMaterializationArchive(tmp_path)
    with pytest.raises((ValueError, OSError)):
        archive.read(record)
