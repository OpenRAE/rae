"""EXP-719 cross-plane factorial designs and admitted randomized allocation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from pydantic import ValidationError
from raes_contracts.canonical import canonical_json_bytes, canonical_json_digest
from raes_contracts.contracts import (
    AdmittedTrialPlanModel,
    ExperimentReferenceModel,
    ExperimentSpecModel,
    ParticipantImplementationManifestModel,
)
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_scheduler import dispatch_batch_schedule, plan_batch_schedule
from test_sce_002_trial_compiler import _request, _spec, _with_participant_manifest


def _payload() -> dict:
    payload = _spec().model_dump(mode="json")
    payload["run_plan"].pop("target_run_count")
    payload["run_plan"]["selection_policies"] = {}
    payload["factors"] = {
        "path": {"name": "Payload path", "factor_kind": "treatment", "levels": ["a", "b"]},
        "agent": {"name": "Agent temperature", "factor_kind": "treatment", "levels": ["cold", "warm"]},
    }
    scenario_owner = {
        "contract_id": "sdl-authoring-input-v1",
        "contract_version": "1",
        "validator_id": "raes-selected-scenario",
        "validator_version": "1",
    }
    participant_owner = {
        "contract_id": "participant-configuration-result-v1",
        "contract_version": "1",
        "validator_id": "participant-config",
        "validator_version": "1",
    }
    payload["factorial_design"] = {
        "profile": "factorial-bindings-v1",
        "factor_ids": ["path", "agent"],
        "target_runs_per_condition": 2,
        "condition_bound": 4,
        "level_bindings": {
            "path": {
                level: [
                    {
                        "target": {
                            "plane": "scenario",
                            "scenario_family_id": "compiler-family",
                            "variation_point_id": "payload-path",
                            "target_id": "variables.payload_path",
                        },
                        "value_type": "string",
                        "value": {"kind": "literal", "value": value},
                        "owner": scenario_owner,
                    }
                ]
                for level, value in (("a", "/opt/a"), ("b", "/opt/b"))
            },
            "agent": {
                level: [
                    {
                        "target": {
                            "plane": "participant-implementation",
                            "participant_address": "agents.red",
                            "implementation_name": "reference-agent",
                            "implementation_version": "1.0.0",
                            "manifest_version": "participant-implementation-manifest/v1",
                            "target_id": "policy.temperature",
                        },
                        "value_type": "number",
                        "value": {"kind": "literal", "value": value},
                        "owner": participant_owner,
                    }
                ]
                for level, value in (("cold", 0.0), ("warm", 1.0))
            },
        },
    }
    return payload


def test_factorial_generation_covers_both_planes_and_roundtrips() -> None:
    spec = ExperimentSpecModel.model_validate(_payload())
    allocation = spec.run_plan.allocation
    assert allocation is not None
    assert len(allocation.compared_conditions) == 4
    assert {tuple(sorted(a.factor_levels.items())) for a in allocation.condition_assignments.values()} == {
        (("agent", agent), ("path", path)) for agent in ("cold", "warm") for path in ("a", "b")
    }
    assert len(spec.binding_descriptors.descriptors) == 8
    for assignment in allocation.condition_assignments.values():
        assert {b.target.plane for b in assignment.required_bindings} == {"scenario", "participant-implementation"}
        assert all(b.source_condition_id == assignment.condition_id for b in assignment.required_bindings)
    assert ExperimentSpecModel.model_validate_json(spec.model_dump_json()) == spec
    reordered = deepcopy(_payload())
    reordered["factorial_design"]["factor_ids"].reverse()
    assert ExperimentSpecModel.model_validate(reordered) == spec


def _randomized_spec() -> ExperimentSpecModel:
    payload = _spec(run_count=8, sample=True).model_dump(mode="json")
    payload["run_plan"]["stochastic_controls"][0]["role"] = "randomization"
    payload["run_plan"]["allocation_policy"] = {
        "kind": "randomized",
        "policy_id": "allocation",
        "algorithm_profile": "fisher-yates-allocation-v1",
        "stochastic_control_ref": "sample-control",
    }
    return ExperimentSpecModel.model_validate(payload)


def test_randomized_allocation_is_sealed_replayable_and_drives_dispatch() -> None:
    request = _request(run_count=8, sample=True).with_experiment(_randomized_spec())
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    plan = result.plan
    assert plan.allocation is not None
    assert set(plan.allocation.entry_order) == set(plan.entries)
    assert len(plan.allocation.draws) == 7
    assert all(draw.address.draw_purpose == "condition-assignment" for draw in plan.allocation.draws)
    schedule = plan_batch_schedule(AdmittedTrialPlanModel.model_validate_json(plan.model_dump_json()))
    assert dispatch_batch_schedule(schedule, realize=lambda entry_id: entry_id) == plan.allocation.entry_order
    assert schedule.scheduling_policy_id == "experiment-recorded-allocation-v1"
    replay = compile_admitted_trial_plan(request, coordinate_partitions=((7, 6, 5), (4, 3, 2, 1, 0)))
    assert replay.plan is not None
    assert canonical_json_bytes(replay.plan.model_dump(mode="json")) == canonical_json_bytes(
        plan.model_dump(mode="json")
    )


def _factorial_request():
    request = _with_participant_manifest(_request())
    key, manifest = next(iter(request.participant_manifests.items()))
    payload = _payload()
    for bindings in payload["factorial_design"]["level_bindings"]["agent"].values():
        bindings[0]["target"].update(
            participant_address=key[0],
            implementation_name=key[1],
            implementation_version=key[2],
            manifest_version=key[3],
        )
    manifest_payload = manifest.model_dump(mode="json")
    manifest_payload["supported_contract_versions"] = sorted(
        set(manifest_payload["supported_contract_versions"])
        | {"experiment-binding-descriptors-v1", "participant-configuration-result-v1"}
    )
    manifest_payload["configuration_registry"] = {
        "owner": payload["factorial_design"]["level_bindings"]["agent"]["cold"][0]["owner"],
        "targets": {
            "policy.temperature": {
                "target_id": "policy.temperature",
                "value_type": "number",
                "allowed_value_kinds": ["literal"],
                "sensitivity": "public",
            },
            "policy.mode": {
                "target_id": "policy.mode",
                "value_type": "string",
                "allowed_value_kinds": ["literal"],
                "sensitivity": "public",
                "default": {"kind": "literal", "value": "safe"},
            },
        },
    }
    manifest = ParticipantImplementationManifestModel.model_validate(manifest_payload)
    reference = request.apparatus.participant_manifest_refs[0].model_copy(
        update={"manifest_digest": canonical_json_digest(manifest.model_dump(mode="json"))}
    )
    spec = ExperimentSpecModel.model_validate(payload)
    request = request.with_experiment(spec)
    return replace(
        request,
        participant_manifests={key: manifest},
        apparatus=request.apparatus.model_copy(update={"participant_manifest_refs": [reference]}),
        input_refs=request.input_refs.model_copy(
            update={
                "binding_descriptor_set_ref": ExperimentReferenceModel(
                    ref_kind="other",
                    ref_id="factorial-bindings",
                    ref_digest=canonical_json_digest(spec.binding_descriptors.model_dump(mode="json")),
                )
            }
        ),
    )


def test_factorial_compiler_admits_and_realizes_every_owner_configuration() -> None:
    result = compile_admitted_trial_plan(_factorial_request())
    assert result.plan is not None, result.diagnostics
    assert len(result.plan.entries) == 8
    for entry in result.plan.entries.values():
        assert len(entry.bindings) == 2
        assert len(entry.selections) == 1
        assert len(entry.participant_configurations) == 1
        values = {value.target_id: value for value in entry.participant_configurations[0].configuration.values}
        assert values["policy.mode"].origin == "default"
        assert values["policy.temperature"].origin == "override"


@pytest.mark.parametrize("mutation", ["duplicate-slot", "foreign-entry", "reorder", "draw", "drop-draw"])
def test_resealed_allocation_tampering_is_rejected(mutation: str) -> None:
    result = compile_admitted_trial_plan(_request(run_count=8, sample=True).with_experiment(_randomized_spec()))
    assert result.plan is not None
    payload = result.plan.model_dump(mode="json")
    allocation = payload["allocation"]
    if mutation == "duplicate-slot":
        allocation["entry_order"][0] = allocation["entry_order"][1]
    elif mutation == "foreign-entry":
        allocation["entry_order"][0] = "foreign-entry"
    elif mutation == "reorder":
        allocation["entry_order"].reverse()
    elif mutation == "draw":
        allocation["draws"][0]["value"] = (allocation["draws"][0]["value"] + 1) % 8
    else:
        allocation["draws"].pop()
    payload["plan_digest"] = canonical_json_digest(
        {key: value for key, value in payload.items() if key != "plan_digest"}
    )
    with pytest.raises(ValidationError, match="allocation"):
        AdmittedTrialPlanModel.model_validate(payload)


@pytest.mark.parametrize(
    "mutation",
    ["bound", "duplicate-factor", "unknown-level", "empty-level", "coercion", "identical-levels", "target-collision"],
)
def test_factorial_generation_rejects_ambiguous_or_unbounded_design(mutation: str) -> None:
    payload = _payload()
    design = payload["factorial_design"]
    if mutation == "bound":
        design["condition_bound"] = 3
    elif mutation == "duplicate-factor":
        design["factor_ids"].append("path")
    elif mutation == "unknown-level":
        design["level_bindings"]["path"]["unknown"] = design["level_bindings"]["path"].pop("a")
    elif mutation == "empty-level":
        design["level_bindings"]["path"]["a"] = []
    elif mutation == "coercion":
        design["target_runs_per_condition"] = True
    elif mutation == "identical-levels":
        design["level_bindings"]["path"]["b"] = deepcopy(design["level_bindings"]["path"]["a"])
    else:
        design["level_bindings"]["agent"]["cold"].append(deepcopy(design["level_bindings"]["path"]["a"][0]))
    with pytest.raises(ValidationError):
        ExperimentSpecModel.model_validate(payload)


def test_missing_participant_required_target_refuses_entire_plan() -> None:
    request = _factorial_request()
    key, manifest = next(iter(request.participant_manifests.items()))
    payload = manifest.model_dump(mode="json")
    payload["configuration_registry"]["targets"]["policy.mode"].pop("default")
    manifest = ParticipantImplementationManifestModel.model_validate(payload)
    reference = request.apparatus.participant_manifest_refs[0].model_copy(
        update={"manifest_digest": canonical_json_digest(manifest.model_dump(mode="json"))}
    )
    request = replace(
        request,
        participant_manifests={key: manifest},
        apparatus=request.apparatus.model_copy(update={"participant_manifest_refs": [reference]}),
    )
    result = compile_admitted_trial_plan(request)
    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.participant-configuration-rejected"


def test_allocation_only_controls_are_retained_and_receipts_follow_recorded_order() -> None:
    from raes_contracts.contracts import validate_batch_execution_receipt
    from raes_processor.trial_scheduler import AttemptOutcome, build_batch_execution_receipt
    from test_sce_006_batch_scheduler import _success_cleanup_receipt

    request = _factorial_request()
    payload = request.experiment.model_dump(mode="json")
    randomized = _randomized_spec()
    payload["run_plan"]["stochastic_controls"] = randomized.run_plan.model_dump(mode="json")["stochastic_controls"]
    payload["run_plan"]["allocation_policy"] = randomized.run_plan.allocation_policy.model_dump(mode="json")
    result = compile_admitted_trial_plan(request.with_experiment(ExperimentSpecModel.model_validate(payload)))
    assert result.plan is not None, result.diagnostics
    plan = result.plan
    assert set(plan.stochastic_controls) == {"sample-control"}
    assert all(not entry.stochastic_draws for entry in plan.entries.values())
    schedule = plan_batch_schedule(plan)
    scheduled = schedule.entries[0]
    entry = plan.entries[scheduled.plan_entry_id]
    cleanup = _success_cleanup_receipt(
        cleanup_plan_ref=entry.execution_controls.cleanup_plan_ref,
        plan_entry_id=entry.plan_entry_id,
        run_id=entry.run_id,
        obligation_results={
            "destroy": {"obligation_id": "destroy", "status": "succeeded", "evidence_refs": ["probe:absent"]}
        },
        clean_state_claim={
            "disposition": "verified-clean",
            "boundary_refs": ["range"],
            "evidence_refs": ["evidence:clean"],
        },
    )
    receipt = build_batch_execution_receipt(
        schedule,
        entry.plan_entry_id,
        receipt_id="receipt",
        outcome=AttemptOutcome("attempt-1", "succeeded", cleanup.receipt_id),
    )
    validate_batch_execution_receipt(plan, receipt, cleanup_receipt=cleanup)
    altered_receipt = receipt.model_copy(update={"scheduling_policy_id": "trial-coordinate-canonical-v1"})
    with pytest.raises(ValueError, match="scheduling policy"):
        validate_batch_execution_receipt(plan, altered_receipt, cleanup_receipt=cleanup)


def test_archival_matching_requires_realized_values_from_both_planes() -> None:
    from paths import REPO_ROOT
    from raes_contracts.contracts import ExperimentRunModel, RealizedBindingProvenanceModel
    from raes_contracts.contracts.experiment_conditions import _run_satisfies_condition_assignment

    request = _factorial_request()
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None
    entry = next(iter(result.plan.entries.values()))
    assignment = request.experiment.run_plan.allocation.condition_assignments[entry.coordinate.condition_id]
    run = ExperimentRunModel.model_validate_json(
        (REPO_ROOT / "contracts/fixtures/experiment-core/experiment-run-v1/valid/reference.json").read_text()
    )
    assert len(_run_satisfies_condition_assignment(run, assignment)) == 2
    bindings = [
        RealizedBindingProvenanceModel(
            descriptor=binding.descriptor,
            origin="selection",
            configuration_digest=entry.participant_configurations[0].configuration_digest
            if binding.descriptor.target.plane == "participant-implementation"
            else None,
        )
        for binding in entry.bindings
    ]
    configuration = entry.participant_configurations[0]
    selection = run.participant_implementation_provenance.participant_implementations[0].model_copy(
        update={
            "participant_address": configuration.participant_address,
            "implementation_identity": configuration.configuration.implementation_identity,
            "configuration_digest": configuration.configuration_digest,
            "configuration_ref": "configuration:admitted",
            "manifest_ref": configuration.manifest_ref,
            "manifest_digest": configuration.manifest_digest,
        }
    )
    run = run.model_copy(
        update={
            "participant_implementation_provenance": run.participant_implementation_provenance.model_copy(
                update={"participant_implementations": [selection]}
            )
        }
    )
    assert _run_satisfies_condition_assignment(run.model_copy(update={"realized_bindings": bindings}), assignment) == []
    for omitted in bindings:
        assert _run_satisfies_condition_assignment(
            run.model_copy(update={"realized_bindings": [binding for binding in bindings if binding != omitted]}),
            assignment,
        )


def test_plan_aware_archive_rejects_omitted_realized_bindings() -> None:
    from raes import canonical_instantiated_sdl_digest
    from raes_contracts.contracts import ExperimentRunModel, validate_admitted_trial_run
    from raes_processor.trial_realization import instantiate_admitted_trial_entry
    from test_sce_002_trial_realization import _archival_run_and_receipt

    request = _factorial_request()
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None
    plan = result.plan
    entry = next(iter(plan.entries.values()))
    _, _, baseline, receipt = _archival_run_and_receipt()
    instantiated = instantiate_admitted_trial_entry(plan=plan, plan_entry_id=entry.plan_entry_id, family=request.family)
    digest = canonical_instantiated_sdl_digest(instantiated).value
    payload = baseline.model_dump(mode="json")
    payload["run_id"] = entry.run_id
    payload["participant_implementation_provenance"]["run_id"] = entry.run_id
    payload["scenario_snapshot_ref"]["ref_digest"] = digest
    payload["trial_provenance"].update(
        plan_id=plan.plan_id,
        plan_digest=plan.plan_digest,
        plan_entry_id=entry.plan_entry_id,
        entry_digest=entry.entry_digest,
        admitted_run_id=entry.run_id,
        coordinate=entry.coordinate.model_dump(mode="json"),
        instantiated_scenario_digest=digest,
    )
    receipt = receipt.model_copy(
        update={
            "plan_entry_id": entry.plan_entry_id,
            "run_id": entry.run_id,
            "cleanup_plan_ref": entry.execution_controls.cleanup_plan_ref,
        }
    )
    run = ExperimentRunModel.model_validate(payload)
    with pytest.raises(ValueError, match="binding"):
        validate_admitted_trial_run(plan, run, [receipt])
    configuration = entry.participant_configurations[0]
    payload["realized_bindings"] = [
        dict(
            descriptor=binding.descriptor.model_dump(mode="json"),
            origin=binding.origin,
            configuration_digest=configuration.configuration_digest
            if binding.descriptor.target.plane == "participant-implementation"
            else None,
        )
        for binding in entry.bindings
    ]
    selection = payload["participant_implementation_provenance"]["participant_implementations"][0]
    selection.update(
        participant_address=configuration.participant_address,
        implementation_identity=configuration.configuration.implementation_identity.model_dump(mode="json"),
        manifest_ref=configuration.manifest_ref,
        manifest_digest=configuration.manifest_digest,
        configuration_ref="configuration:admitted",
        configuration_digest=configuration.configuration_digest,
    )
    validate_admitted_trial_run(plan, ExperimentRunModel.model_validate(payload), [receipt])


def test_allocation_procedure_matches_pinned_vector() -> None:
    from raes_contracts.contracts.experiment_allocation import compile_experiment_allocation

    spec = _randomized_spec()
    allocation = compile_experiment_allocation(
        spec.run_plan.allocation_policy,
        ["entry-a", "entry-b", "entry-c", "entry-d"],
        {control.control_id: control for control in spec.run_plan.stochastic_controls},
    )
    assert allocation.entry_order == ["entry-a", "entry-d", "entry-b", "entry-c"]
    assert [draw.value for draw in allocation.draws] == [2, 1, 1]
    assert [draw.address.slot for draw in allocation.draws] == [0, 1, 2]


def test_alias_normalization_cannot_create_operationally_identical_conditions() -> None:
    request = _factorial_request()
    key, manifest = next(iter(request.participant_manifests.items()))
    manifest_payload = manifest.model_dump(mode="json")
    manifest_payload["configuration_registry"]["targets"]["policy.temperature"]["aliases"] = ["temperature"]
    manifest = ParticipantImplementationManifestModel.model_validate(manifest_payload)
    reference = request.apparatus.participant_manifest_refs[0].model_copy(
        update={"manifest_digest": canonical_json_digest(manifest.model_dump(mode="json"))}
    )
    payload = _payload()
    for bindings in payload["factorial_design"]["level_bindings"]["agent"].values():
        bindings[0]["target"].update(
            participant_address=key[0],
            implementation_name=key[1],
            implementation_version=key[2],
            manifest_version=key[3],
        )
    warm = payload["factorial_design"]["level_bindings"]["agent"]["warm"][0]
    warm["value"]["value"] = 0.0
    warm["target"]["target_id"] = "temperature"
    spec = ExperimentSpecModel.model_validate(payload)
    request = request.with_experiment(spec)
    refs = request.input_refs.model_copy(
        update={
            "binding_descriptor_set_ref": request.input_refs.binding_descriptor_set_ref.model_copy(
                update={"ref_digest": canonical_json_digest(spec.binding_descriptors.model_dump(mode="json"))}
            )
        }
    )
    request = replace(
        request,
        participant_manifests={key: manifest},
        apparatus=request.apparatus.model_copy(update={"participant_manifest_refs": [reference]}),
        input_refs=refs,
    )
    result = compile_admitted_trial_plan(request)
    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.factorial-conditions-indistinguishable"
