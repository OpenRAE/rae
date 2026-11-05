"""Authored trial capacity survives compilation and constrains execution."""

import json

import pytest
from raes import admit_scenario_family, parse_sdl
from raes.validator import SemanticValidator
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import AdmittedTrialPlanModel
from raes_contracts.errors import InvalidInputError
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_scheduler import (
    AllocatorGrant,
    AttemptOutcome,
    build_batch_execution_receipt,
    plan_batch_schedule,
)
from test_sce_002_trial_compiler import _request
from test_sce_006_batch_scheduler import _plan

FORMS = [
    {"posture": "exact", "count": 2},
    {"posture": "constrained", "maximum": 2},
    {"posture": "constrained", "minimum": 2},
    {"posture": "open"},
]


def _limited_plan(intent):
    payload = _plan("two-entry").model_dump(mode="json")
    payload["trial_parallelism"] = intent
    payload["plan_digest"] = canonical_json_digest({k: v for k, v in payload.items() if k != "plan_digest"})
    return AdmittedTrialPlanModel.model_validate(payload)


@pytest.mark.parametrize("intent", FORMS)
def test_parallel_trial_count_forms(intent):
    scenario = parse_sdl(json.dumps({"name": "trial-capacity", "trial_parallelism": intent}))
    assert scenario.model_dump(mode="json")["trial_parallelism"] == intent
    expanded = admit_scenario_family(scenario)
    assert expanded.model_dump(mode="json")["trial_parallelism"] == intent


@pytest.mark.parametrize("intent", FORMS)
def test_parallel_trial_count_realization_postures(intent):
    request = _request()
    payload = request.family.model_dump(mode="json", by_alias=True)
    payload["trial_parallelism"] = intent
    family = type(request.family).model_validate(payload)
    SemanticValidator(family).validate()
    family._set_semantic_validated(True)
    result = compile_admitted_trial_plan(request.with_family(family))
    assert result.plan is not None, result.diagnostics
    assert result.plan.model_dump(mode="json")["trial_parallelism"] == intent


@pytest.mark.parametrize("intent", FORMS)
def test_parallel_trial_limits_at_execution_boundaries(intent):
    plan = _limited_plan(intent)
    schedule = plan_batch_schedule(plan)
    assert schedule.admitted_parallelism_ceiling == 2
    lower = 2 if intent.get("count") == 2 or intent.get("minimum") == 2 else 1
    assert schedule.admitted_parallelism_floor == lower
    for count in (1, 2, 3):
        grant = AllocatorGrant(effective_parallelism=count)
        kwargs = dict(receipt_id="receipt", outcome=AttemptOutcome("attempt", "succeeded", "cleanup"), grant=grant)
        if lower <= count <= 2:
            receipt = build_batch_execution_receipt(schedule, "entry-a", **kwargs)
            assert receipt.effective_parallelism == count
        else:
            with pytest.raises(InvalidInputError, match="parallelism"):
                build_batch_execution_receipt(schedule, "entry-a", **kwargs)


def test_parallel_trial_count_omission_compatibility():
    scenario = parse_sdl('{"name": "legacy"}')
    assert "trial_parallelism" not in scenario.model_dump(mode="json")
    plan = _plan("two-entry")
    assert "trial_parallelism" not in plan.model_dump(mode="json")
    assert plan_batch_schedule(plan).admitted_parallelism_floor == 1


@pytest.mark.parametrize(
    "intent",
    [{"posture": "exact", "count": value} for value in (0, -1, True, 2.0, "2")]
    + [
        {"posture": "open", "count": 2},
        {"posture": "exact"},
        {"posture": "exact", "count": 2, "maximum": 2},
        {"posture": "constrained"},
        {"posture": "constrained", "minimum": 3, "maximum": 2},
        {"posture": "constrained", "maximum": False},
        {"posture": "constrained", "minimum": 0},
        {"posture": "exact", "count": 4097},
        {"posture": "constrained", "maximum": 4097},
    ],
)
def test_invalid_parallelism_rejected_at_sdl_boundary(intent):
    from raes import SDLParseError

    source = json.dumps({"name": "invalid-capacity", "trial_parallelism": intent})
    with pytest.raises(SDLParseError):
        parse_sdl(source)


def test_minimum_above_the_trial_count_fails_before_dispatch():
    plan = _limited_plan({"posture": "constrained", "minimum": 3})
    with pytest.raises(InvalidInputError, match="parallelism"):
        plan_batch_schedule(plan)


@pytest.mark.parametrize(
    "intent, bounds",
    [
        ({"posture": "open"}, (1, 2)),
        ({"posture": "exact", "count": 2}, (2, 2)),
        ({"posture": "exact", "count": 5}, (5, 5)),
        ({"posture": "constrained", "minimum": 2}, (2, 2)),
        ({"posture": "constrained", "maximum": 4}, (1, 4)),
        ({"posture": "constrained", "minimum": 1, "maximum": 3}, (1, 3)),
    ],
)
def test_trial_parallelism_sets_the_limit_without_an_isolation_proof(intent, bounds):
    plan = _limited_plan(intent)
    assert "isolation_proof" not in plan.model_dump(mode="json")
    schedule = plan_batch_schedule(plan)
    assert (schedule.admitted_parallelism_floor, schedule.admitted_parallelism_ceiling) == bounds
    outcome = AttemptOutcome("attempt", "succeeded", "cleanup")
    receipt = build_batch_execution_receipt(
        schedule,
        "entry-a",
        receipt_id="receipt",
        outcome=outcome,
        grant=AllocatorGrant(effective_parallelism=bounds[1]),
    )
    assert receipt.effective_parallelism == bounds[1]


def test_author_maximum_caps_the_ceiling():
    schedule = plan_batch_schedule(_limited_plan({"posture": "constrained", "maximum": 1}))
    assert schedule.admitted_parallelism_ceiling == 1
    outcome = AttemptOutcome("attempt", "succeeded", "cleanup")
    grant = AllocatorGrant(effective_parallelism=2)
    with pytest.raises(InvalidInputError, match="parallelism"):
        build_batch_execution_receipt(
            schedule,
            "entry-a",
            receipt_id="receipt",
            outcome=outcome,
            grant=grant,
        )


def test_realization_rejects_resealed_parallelism_change():
    from raes_processor.trial_realization import instantiate_admitted_trial_entry

    request = _request()
    plan = compile_admitted_trial_plan(request).plan
    payload = plan.model_dump(mode="json")
    payload["trial_parallelism"] = {"posture": "exact", "count": 2}
    payload["plan_digest"] = canonical_json_digest({k: v for k, v in payload.items() if k != "plan_digest"})
    changed = AdmittedTrialPlanModel.model_validate(payload)
    entry_id = next(iter(plan.entries))
    with pytest.raises(InvalidInputError, match="parallelism"):
        instantiate_admitted_trial_entry(
            plan=changed,
            family=request.family,
            plan_entry_id=entry_id,
        )


@pytest.mark.parametrize(
    "intent, count",
    [
        ({"posture": "exact", "count": 2}, 1),
        ({"posture": "constrained", "minimum": 2}, 1),
        ({"posture": "constrained", "maximum": 1}, 2),
    ],
)
def test_receipt_join_enforces_both_author_bounds(intent, count):
    from raes_contracts.contracts import validate_batch_execution_receipt
    from test_sce_006_batch_scheduler import _receipt, _success_cleanup_receipt

    plan = _limited_plan(intent)
    receipt = _receipt(plan, effective_parallelism=count)
    cleanup = _success_cleanup_receipt()
    with pytest.raises(ValueError, match="parallelism"):
        validate_batch_execution_receipt(plan, receipt, cleanup_receipt=cleanup)


def test_assignment_ingress_enforces_both_author_bounds():
    from issue_1629_trial_fixture import TrialServices
    from issue_1870_trial_fixture import parallel_inputs
    from raes_contracts.assigned_trial import TrialAssignmentModel
    from raes_runtime import RuntimeControlPlane

    _, inputs, target = parallel_inputs()
    grant = AllocatorGrant(effective_parallelism=2)
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=TrialServices(target))
        assignment = runtime.assign_trial(experiment, next(iter(inputs.plan.entries)), owner_id="worker", grant=grant)
    for intent, count, allowed in [
        ({"posture": "exact", "count": 2}, 1, False),
        ({"posture": "constrained", "minimum": 2}, 1, False),
        ({"posture": "constrained", "maximum": 1}, 2, False),
        ({"posture": "exact", "count": 2}, 2, True),
        ({"posture": "open"}, 2, True),
        ({"posture": "constrained", "minimum": 2}, 2, True),
        ({"posture": "constrained", "maximum": 4}, 3, True),
        ({"posture": "exact", "count": 4}, 4, True),
    ]:
        payload = assignment.model_dump(mode="json")
        plan = payload["plan"]
        plan["trial_parallelism"] = intent
        plan["plan_digest"] = canonical_json_digest({k: v for k, v in plan.items() if k != "plan_digest"})
        payload["effective_parallelism"] = count
        if allowed:
            assert TrialAssignmentModel.model_validate(payload).effective_parallelism == count
        else:
            with pytest.raises(ValueError, match="parallelism"):
                TrialAssignmentModel.model_validate(payload)


@pytest.mark.parametrize(
    "intent",
    FORMS
    + [
        {"posture": "constrained", "minimum": 1, "maximum": 2},
    ],
)
def test_published_sdl_schema_accepts_each_form(intent):
    from jsonschema import Draft202012Validator
    from paths import REPO_ROOT

    schema = json.loads((REPO_ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json").read_text())
    Draft202012Validator(schema).validate({"name": "capacity", "trial_parallelism": intent})


@pytest.mark.parametrize(
    "intent",
    [
        {"posture": "open", "count": 2},
        {"posture": "exact", "count": True},
        {"posture": "exact", "count": 0},
        {"posture": "constrained"},
        {"posture": "constrained", "minimum": None, "maximum": None},
        {"posture": "exact", "count": 4097},
    ],
)
def test_published_sdl_schema_rejects_malformed_forms(intent):
    from jsonschema import Draft202012Validator
    from paths import REPO_ROOT

    schema = json.loads((REPO_ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json").read_text())
    assert not Draft202012Validator(schema).is_valid({"name": "capacity", "trial_parallelism": intent})


def test_root_parallelism_survives_module_composition(tmp_path):
    from raes.parser import parse_sdl_file
    from test_sdl_module_registry import _local_module, _root_import

    _local_module(tmp_path / "child.yaml")
    root = _root_import(tmp_path / "root.yaml", "path: child.yaml\nnamespace: child")
    root.write_text(root.read_text() + "\ntrial_parallelism: {posture: exact, count: 2}\n")
    assert parse_sdl_file(root).trial_parallelism.count == 2


def test_open_ceiling_never_exceeds_the_assignment_limit():
    from raes_contracts.trial_parallelism import MAX_TRIAL_PARALLELISM, OpenTrialParallelismModel, parallelism_bounds

    assert parallelism_bounds(OpenTrialParallelismModel(posture="open"), 10_000) == (1, MAX_TRIAL_PARALLELISM)
