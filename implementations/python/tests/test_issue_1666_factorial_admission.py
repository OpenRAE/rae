"""Atomic failures, effective duplicates and trusted-source readmission."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes.canonical import canonical_sdl_digest
from raes_contracts.contracts import AdmittedTrialPlanModel, seal_admitted_trial_entry, seal_admitted_trial_plan
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_realization import instantiate_admitted_trial_entry
from test_issue_1625_structural_variation import _family
from test_issue_1666_factorial_compilation import _treatment_request, _with_design


def _selection_only(request):
    payload = request.experiment.model_dump(mode="json")
    design = payload["factorial_design"]
    design["factor_ids"] = ["terrain-x"]
    design["level_effects"] = {"terrain-x": design["level_effects"]["terrain-x"]}
    payload["factors"] = {"terrain-x": payload["factors"]["terrain-x"]}
    return _with_design(request, payload)


def _with_family(request, family_payload):
    family = _family(family_payload)
    payload = request.experiment.model_dump(mode="json")
    for levels in payload["factorial_design"]["level_effects"].values():
        for effects in levels.values():
            for selection in effects.get("selections", []):
                selection["scenario_family_digest"] = canonical_sdl_digest(family).value
    return _with_design(request.with_family(family), payload)


def _reseal(plan, entry, **changes):
    entry_fields = {key: getattr(entry, key) for key in type(entry).model_fields if key != "entry_digest"}
    altered = seal_admitted_trial_entry(**{**entry_fields, **changes})
    plan_fields = {key: getattr(plan, key) for key in type(plan).model_fields if key != "plan_digest"}
    return seal_admitted_trial_plan(**{**plan_fields, "entries": {**plan.entries, entry.plan_entry_id: altered}})


def test_selection_only_design_keeps_fixed_point_without_dummy_bindings():
    request = _selection_only(_treatment_request())
    assert request.experiment.binding_descriptors is None
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    assert len(result.plan.entries) == 4
    for entry in result.plan.entries.values():
        assert not entry.bindings
        assert len(entry.selections) == 2
        fixed = next(selection for selection in entry.selections if selection.variation_point_id == "payload-path")
        assert fixed.origin_policy_id == "fixed-path"
        assert fixed.treatment is None


@pytest.mark.parametrize("change", ["dangling", "conflict", "equal-effects", "missing-coverage"])
def test_invalid_requested_structural_combination_rejects_every_trial(change):
    request = _selection_only(_treatment_request())
    family = request.family.model_dump(mode="python", by_alias=True)
    if change == "dangling":
        family["content"]["relay-input"] = {"type": "file", "target": "relay-47", "path": "/opt/input"}
    elif change == "conflict":
        family["variation_points"]["separate-jobs"] = {
            "kind": "alternative",
            "target": {"kind": "structural", "owner": "relay-47", "slot": "nodes.runtime.scheduled_jobs"},
            "alternatives": {"empty": {"kind": "runtime-inventory", "references": []}},
        }
    elif change == "equal-effects":
        alternatives = family["variation_points"]["deployment-shape"]["alternatives"]
        alternatives["instrumented"] = {"kind": "node-presence", "present": True}
        alternatives["offline"] = {
            "kind": "node-presence",
            "present": True,
            "inventory": {
                "nodes.runtime.scheduled_jobs": [
                    "nodes.relay-47.runtime.scheduled_jobs.audit",
                    "nodes.relay-47.runtime.scheduled_jobs.rotate",
                ]
            },
        }
    else:
        family["variables"]["untreated"] = {"type": "string", "default": "x"}
        family["variation_points"]["uncovered"] = {
            "kind": "parameter",
            "target": {"kind": "variable", "variable": "untreated"},
            "domain": {"kind": "exact", "value": "x"},
        }
    request = _with_family(request, family)
    if change == "conflict":
        payload = request.experiment.model_dump(mode="json")
        payload["run_plan"]["selection_policies"]["jobs-fixed"] = {
            "kind": "fixed",
            "policy_id": "jobs-fixed",
            "purpose": "fixed-configuration",
            "point_ref": "separate-jobs",
            "outcome": {"kind": "member", "member_id": "empty"},
            "output_bound": 1,
        }
        request = _with_design(request, payload)
    result = compile_admitted_trial_plan(request)
    assert result.plan is None
    expected = {
        "equal-effects": "factorial-conditions-indistinguishable",
        "missing-coverage": "variation-points-uncovered",
    }
    assert result.diagnostics[0].code == "trial-compiler." + expected.get(change, "selected-scenario-rejected")


def test_resealed_changed_target_is_rejected_by_public_family_readmission():
    request = _selection_only(_treatment_request())
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    plan = result.plan
    entry = next(iter(plan.entries.values()))
    selections = deepcopy(entry.selections)
    typed = next(selection for selection in selections if selection.treatment)
    from raes_contracts.contracts.experiment_treatments import ExperimentFactorLevelSelectionModel

    original = typed.treatment
    fields = original.model_dump(
        exclude={"selection_id", "source_factor_id", "source_factor_level_id", "source_condition_id"}
    )
    fields["target"]["target_id"] = "nodes.primary.presence"
    changed = ExperimentFactorLevelSelectionModel.model_validate(fields).descriptor(
        original.source_factor_id, original.source_factor_level_id, original.source_condition_id
    )
    typed.treatment = changed
    altered = _reseal(plan, entry, selections=selections)
    with pytest.raises(ValueError, match="selection treatment"):
        instantiate_admitted_trial_entry(plan=altered, plan_entry_id=entry.plan_entry_id, family=request.family)


def test_source_aware_readmission_rejects_self_consistent_omission():
    from raes_processor.trial_compiler import readmit_admitted_trial_plan

    request = _treatment_request()
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    plan = result.plan
    assert readmit_admitted_trial_plan(plan, request=request).model_dump(mode="json") == plan.model_dump(mode="json")
    entry = next(iter(plan.entries.values()))
    selections = [
        selection.model_copy(update={"treatment": None, "origin_policy_id": "fixed-hidden"})
        for selection in entry.selections
    ]
    altered = _reseal(plan, entry, selections=selections)
    AdmittedTrialPlanModel.model_validate_json(altered.model_dump_json())
    with pytest.raises(ValueError, match="original compilation inputs"):
        readmit_admitted_trial_plan(altered, request=request)


def test_typed_selections_share_the_entry_effect_limit():
    request = _treatment_request()
    request = replace(request, limits=request.limits.model_copy(update={"max_bindings_per_entry": 2}))
    result = compile_admitted_trial_plan(request)
    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.binding-limit-exceeded"


def test_plan_local_reconstruction_rejects_an_omitted_claimed_treatment():
    request = _selection_only(_treatment_request())
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    plan = result.plan
    entry = next(iter(plan.entries.values()))
    selections = [selection.model_copy(update={"treatment": None}) for selection in entry.selections]
    with pytest.raises(ValueError, match="treatment"):
        _reseal(plan, entry, selections=selections)


def test_typed_scalar_and_structural_effects_are_selected_together():
    request = _selection_only(_treatment_request())
    payload = request.experiment.model_dump(mode="json")
    payload["run_plan"]["selection_policies"] = {}
    for level, effects in payload["factorial_design"]["level_effects"]["terrain-x"].items():
        effects["bindings"] = [
            {
                "target": {
                    "plane": "scenario",
                    "scenario_family_id": request.family.name,
                    "variation_point_id": "payload-path",
                    "target_id": "variables.payload_path",
                },
                "owner": effects["selections"][0]["owner"],
                "value_type": "string",
                "value": {"kind": "literal", "value": "/opt/a" if level == "isolated" else "/opt/b"},
            }
        ]
    request = _with_design(request, payload)
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    for entry in result.plan.entries.values():
        selected = instantiate_admitted_trial_entry(
            plan=result.plan, plan_entry_id=entry.plan_entry_id, family=request.family
        )
        assert selected.content["payload"].path == ("/opt/b" if "relay-47" in selected.nodes else "/opt/a")


def test_participant_only_typed_design_has_no_invented_scenario_points():
    request = _treatment_request()
    family_payload = request.family.model_dump(mode="python", by_alias=True)
    family_payload["variation_points"] = {}
    request = _with_family(request, family_payload)
    payload = request.experiment.model_dump(mode="json")
    design = payload["factorial_design"]
    design["factor_ids"].remove("terrain-x")
    design["level_effects"].pop("terrain-x")
    payload["factors"].pop("terrain-x")
    payload["run_plan"]["selection_policies"] = {}
    result = compile_admitted_trial_plan(_with_design(request, payload))
    assert result.plan is not None, result.diagnostics
    assert len(result.plan.entries) == 8
    assert all(not entry.selections and entry.participant_configurations for entry in result.plan.entries.values())


def test_typed_design_checks_intended_family_without_ordinary_policies():
    request = _selection_only(_treatment_request())
    family = request.family.model_dump(mode="python", by_alias=True)
    family["variation_points"].pop("payload-path")
    request = _with_family(request, family)
    payload = request.experiment.model_dump(mode="json")
    payload["run_plan"]["selection_policies"] = {}
    payload["intended_scenario_ref"]["ref_id"] = "different-intended-family"
    result = compile_admitted_trial_plan(_with_design(request, payload))
    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.selection-intent-rejected"
