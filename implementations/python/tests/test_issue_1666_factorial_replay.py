"""Typed trial source joins, allocation replay and archival claims."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes import canonical_instantiated_sdl_digest
from raes_contracts.canonical import canonical_json_bytes
from raes_contracts.contracts import ExperimentRunModel, validate_admitted_trial_run
from raes_contracts.contracts.experiment_conditions import _run_satisfies_condition_assignment
from raes_contracts.errors import InvalidInputError
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_realization import instantiate_admitted_trial_entry, realize_admitted_trial_entry
from test_exp_719_factorial_allocation import _randomized_spec
from test_issue_1666_factorial_admission import _reseal, _selection_only
from test_issue_1666_factorial_compilation import _treatment_request, _with_design
from test_sce_002_trial_realization import _archival_run_and_receipt, _realization_inputs, _request_with_processor


def test_randomized_treatment_allocation_replays_after_reload_and_reverse_traversal():
    from raes_contracts.contracts.admitted_trial_plan_ingress import parse_admitted_trial_plan_json
    from raes_processor.trial_scheduler import plan_batch_schedule

    request = _treatment_request()
    payload = request.experiment.model_dump(mode="json")
    randomized = _randomized_spec()
    payload["run_plan"]["stochastic_controls"] = randomized.run_plan.model_dump(mode="json")["stochastic_controls"]
    payload["run_plan"]["allocation_policy"] = randomized.run_plan.allocation_policy.model_dump(mode="json")
    request = _with_design(request, payload)
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    plan = parse_admitted_trial_plan_json(result.plan.model_dump_json())
    replay = compile_admitted_trial_plan(request, coordinate_partitions=(tuple(reversed(range(16))),))
    assert replay.plan is not None, replay.diagnostics
    assert canonical_json_bytes(replay.plan.model_dump(mode="json")) == canonical_json_bytes(
        plan.model_dump(mode="json")
    )
    assert [entry.plan_entry_id for entry in plan_batch_schedule(plan).entries] == plan.allocation.entry_order
    assert len(plan.allocation.draws) == 15


@pytest.mark.parametrize("change", ["omit", "source", "extra", "fixed"])
def test_source_aware_one_entry_realization_rejects_resealed_treatment_changes(change):
    request = _treatment_request()
    processor = _request_with_processor()
    request = replace(
        request,
        apparatus_manifests=processor.apparatus_manifests,
        apparatus=processor.apparatus.model_copy(
            update={"participant_manifest_refs": request.apparatus.participant_manifest_refs}
        ),
    )
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    plan = result.plan
    entry = next(
        entry
        for entry in plan.entries.values()
        if any(selection.treatment and selection.outcome.member_id == "offline" for selection in entry.selections)
    )
    selections = deepcopy(entry.selections)
    typed = next(selection for selection in selections if selection.treatment)
    if change == "omit":
        typed.treatment = None
        typed.origin_policy_id = "fixed-disguised"
    elif change == "source":
        typed.treatment.source_factor_level_id = "other-source"
    elif change == "fixed":
        fixed = next(selection for selection in selections if selection.treatment is None)
        fixed.outcome.value = "/opt/b"
    else:
        typed.treatment = typed.treatment.model_copy(
            update={"owner": typed.treatment.owner.model_copy(update={"validator_version": "other-owner-version"})}
        )
    altered = _reseal(plan, entry, selections=selections)
    inputs = _realization_inputs(request, altered, request.task)
    with pytest.raises(InvalidInputError, match="authoring.*selection|selection.*authoring"):
        realize_admitted_trial_entry(inputs=inputs, plan_entry_id=entry.plan_entry_id)


def _archived_treatment(*, replacement=False):
    request = _treatment_request()
    if replacement:
        processor = _request_with_processor()
        request = replace(
            request,
            apparatus_manifests=processor.apparatus_manifests,
            apparatus=processor.apparatus.model_copy(
                update={"participant_manifest_refs": request.apparatus.participant_manifest_refs}
            ),
        )
        payload = request.experiment.model_dump(mode="json")
        payload["run_plan"]["replacement_policy"] = {"max_replacements": 2, "replace_on": ["failed"]}
        request = _with_design(request, payload)
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    plan = result.plan
    entry = next(
        entry
        for entry in plan.entries.values()
        if any(selection.treatment and selection.outcome.member_id == "offline" for selection in entry.selections)
    )
    _, _, baseline, receipt = _archival_run_and_receipt()
    selected = instantiate_admitted_trial_entry(plan=plan, plan_entry_id=entry.plan_entry_id, family=request.family)
    digest = canonical_instantiated_sdl_digest(selected).value
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
    configurations = {
        configuration.participant_address: configuration for configuration in entry.participant_configurations
    }
    payload["realized_bindings"] = [
        {
            "descriptor": binding.descriptor.model_dump(mode="json"),
            "origin": binding.origin,
            "configuration_digest": configurations[binding.descriptor.target.participant_address].configuration_digest,
        }
        for binding in entry.bindings
    ]
    payload["realized_selections"] = [
        selection.treatment.model_dump(mode="json") for selection in entry.selections if selection.treatment
    ]
    configuration = entry.participant_configurations[0]
    payload["participant_implementation_provenance"]["participant_implementations"][0].update(
        participant_address=configuration.participant_address,
        implementation_identity=configuration.configuration.implementation_identity.model_dump(mode="json"),
        manifest_ref=configuration.manifest_ref,
        manifest_digest=configuration.manifest_digest,
        configuration_ref="configuration:admitted",
        configuration_digest=configuration.configuration_digest,
    )
    return request, plan, entry, payload, receipt


@pytest.mark.parametrize("change", [None, "omit", "source", "substitute", "participant"])
def test_archive_matching_requires_both_structural_and_participant_effects(change):
    request, plan, entry, payload, receipt = _archived_treatment()
    assignment = request.experiment.run_plan.allocation.condition_assignments[entry.coordinate.condition_id]
    if change == "omit":
        payload["realized_selections"] = []
    elif change == "source":
        payload["realized_selections"][0]["source_factor_level_id"] = "other-source"
    elif change == "substitute":
        selection = payload["realized_selections"][0]
        selection["outcome"]["member_id"] = (
            "offline" if selection["outcome"]["member_id"] == "instrumented" else "instrumented"
        )
    elif change == "participant":
        payload["realized_bindings"].pop()
    run = ExperimentRunModel.model_validate(payload)
    if change:
        assert _run_satisfies_condition_assignment(run, assignment)
        with pytest.raises(ValueError, match="selection|binding"):
            validate_admitted_trial_run(plan, run, [receipt])
    else:
        assert _run_satisfies_condition_assignment(run, assignment) == []
        validate_admitted_trial_run(plan, run, [receipt])


def test_distinct_descriptor_labels_and_authored_hashes_do_not_hide_equal_structure():
    request = _selection_only(_treatment_request())
    payload = request.family.model_dump(mode="python", by_alias=True)
    alternatives = payload["variation_points"]["deployment-shape"]["alternatives"]
    alternatives["instrumented"] = {"kind": "node-presence", "present": True}
    alternatives["offline"] = {
        "kind": "node-presence",
        "present": True,
        "inventory": {
            "nodes.runtime.scheduled_jobs": [
                "nodes.relay-47.runtime.scheduled_jobs.rotate",
                "nodes.relay-47.runtime.scheduled_jobs.audit",
            ]
        },
    }
    from test_issue_1666_factorial_admission import _with_family

    result = compile_admitted_trial_plan(_with_family(request, payload))
    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.factorial-conditions-indistinguishable"


def test_source_realization_rechecks_supplied_participant_manifest_pins():
    from raes_contracts.contracts import ParticipantImplementationManifestModel

    request = _treatment_request()
    processor = _request_with_processor()
    request = replace(
        request,
        apparatus_manifests=processor.apparatus_manifests,
        apparatus=processor.apparatus.model_copy(
            update={"participant_manifest_refs": request.apparatus.participant_manifest_refs}
        ),
    )
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    plan = result.plan
    entry = next(
        entry
        for entry in plan.entries.values()
        if any(selection.treatment and selection.outcome.member_id == "offline" for selection in entry.selections)
    )
    key, manifest = next(iter(request.participant_manifests.items()))
    payload = manifest.model_dump(mode="json")
    payload["configuration_registry"]["targets"]["policy.model"]["aliases"] = ["new-alias"]
    substituted = ParticipantImplementationManifestModel.model_validate(payload)
    inputs = replace(_realization_inputs(request, plan, request.task), participant_manifests={key: substituted})
    with pytest.raises(InvalidInputError, match="participant.*manifest"):
        realize_admitted_trial_entry(inputs=inputs, plan_entry_id=entry.plan_entry_id)


def test_typed_replacement_keeps_its_condition_and_public_realization():
    from raes_processor.trial_compiler import compile_replacement_trial

    request, root, entry, payload, receipt = _archived_treatment(replacement=True)
    payload.update(run_status="failed", outcome_status="failed")
    run = ExperimentRunModel.model_validate(payload)
    receipt = receipt.model_copy(update={"trial_outcome": "failed"})
    replacement = compile_replacement_trial(
        request,
        original_plan=root,
        root_entry_id=entry.plan_entry_id,
        failed_run=run,
        cleanup_receipts=[receipt],
    )
    assert replacement.plan is not None, replacement.diagnostics
    child = replacement.plan
    new_entry = next(iter(child.entries.values()))
    assert new_entry.coordinate.condition_id == entry.coordinate.condition_id
    assert new_entry.coordinate.replicate_id != entry.coordinate.replicate_id
    realized = realize_admitted_trial_entry(
        inputs=_realization_inputs(request, child, request.task), plan_entry_id=new_entry.plan_entry_id
    )
    assert realized.participant_configurations == tuple(new_entry.participant_configurations)
