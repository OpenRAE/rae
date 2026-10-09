"""Issue #308 (DSL-121): authored participant interaction budgets.

The tests follow the DSL-121 rows of the issue #122 source-to-contract-to-test
matrix in ``specs/formal/participant-episode-model/README.md``:

- interaction budgets project into the ADR-097 canonical demand (EBM-04);
- step, turn, time, token, and tool-use stay distinct governed dimensions, and
  host watchdog time is not a scenario-time quota (EBM-05); and
- a quota becomes participant-visible only through an explicit view rule
  (EBM-07).
"""

from __future__ import annotations

import ast
import copy
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from implementations.python.tests.test_dsl_437_benign_participant_execution import (
    SCENARIO_CLOCK_ADDRESS,
    _activity_control,
    _NativeParticipantRuntime,
)
from implementations.python.tests.test_issue_306_participant_budget_exhaustion import (
    _advance_until_rejected,
    _attempt_events,
    _reject_events,
    _terminal_result,
)
from implementations.python.tests.test_issue_899_participant_resource_budgets import (
    _budget_policy_yaml,
    _capabilities,
    _governed_manifest,
)
from pydantic import ValidationError
from raes import parse_sdl, parse_sdl_file
from raes._errors import SDLParseError, SDLValidationError
from raes.participant_behavior import ParticipantObservationBoundary
from raes.participant_behavior_specification import ParticipantBehaviorSpecification
from raes.participant_execution import ParticipantAutonomousExecutionPolicyV3
from raes.participant_resource_budgets import resource_budget_dimension_reference
from raes_backend_protocols.capability_admission import participant_autonomous_execution_capability_gaps
from raes_backend_protocols.participant_resource_budgets import ParticipantResourcePoolCapacity
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts import schema_bundle
from raes_contracts.contracts.participant_resource_budgets import (
    ParticipantResourceBudgetEventModel,
    ParticipantResourceBudgetPolicyModel,
    ParticipantResourceMeasurementModel,
    ParticipantResourceMeasurementRequirementModel,
    ParticipantResourcePoolCapacityModel,
    participant_resource_budget_state_ref,
)
from raes_contracts.contracts.time_model import (
    ClockTransitionEventModel,
    RuntimeClockStateModel,
    TimeCoordinateModel,
)
from raes_processor.compiler import compile_runtime_model
from raes_runtime.manager import RuntimeManager
from raes_runtime.participant_resource_rejection import disclosed_rejection_quota
from raes_runtime.participant_resource_scenario_time import elapsed_scenario_ticks
from raes_runtime.participant_scheduler_resources import action_resource_quantities, measurement_requirements

REPO_ROOT = Path(__file__).resolve().parents[3]
DESIGN = REPO_ROOT / "specs/formal/participant-episode-model/README.md"
SEMANTICS = REPO_ROOT / "specs/formal/participant-semantics/autonomous-execution.md"
POLICY_FIXTURES = REPO_ROOT / "contracts/fixtures/participant-runtime/participant-resource-budget-policy-v1"
SPEC = "participant-behavior"
ACTION = "probe-customer-portal-login"
AFFORDANCE = "portal-probe"
AFFORDANCE_REF = f"behavior_specifications.{SPEC}.tool_affordances.{AFFORDANCE}"
TOOL_BUDGET = "tool-calls"
TIME_BUDGET = "scenario-time"
POLICY_ADDRESS = f"participant.autonomous-execution.{SPEC}"
WATCHDOG_METER = "host.watchdog-milliseconds/v1"
INTERACTION_KINDS = ("interaction_steps", "interaction_turns", "tool_invocations", "scenario_time")
_COUNTER = {"owner_ref": "green", "pool_ref": "participant-pool", "accounting_mode": "cumulative_counter"}
INTERACTION_DIMENSIONS = {
    "steps": _COUNTER
    | {
        "resource_kind": "interaction_steps",
        "unit": "steps",
        "meter_profile_ref": "raes.participant-step/v1",
        "limit": 40,
        "reservation": 1,
        "reset": "episode",
    },
    "turns": _COUNTER
    | {
        "resource_kind": "interaction_turns",
        "unit": "turns",
        "meter_profile_ref": "raes.participant-turn/v1",
        "limit": 20,
        "reservation": 1,
        "reset": "episode",
    },
    TOOL_BUDGET: _COUNTER
    | {
        "resource_kind": "tool_invocations",
        "unit": "invocations",
        "meter_profile_ref": "raes.tool-invocation/v1",
        "limit": 2,
        "reservation": 1,
        "reset": "episode",
        "tool_affordance_refs": [AFFORDANCE],
    },
    TIME_BUDGET: _COUNTER
    | {
        "resource_kind": "scenario_time",
        "unit": "ticks",
        "meter_profile_ref": "raes.shared-time-ticks/v1",
        "limit": 600,
        "reservation": 1,
        "reset": "time_segment",
    },
}


def _payload(*, disclose: str | None = None) -> dict:
    payload = yaml.safe_load(_budget_policy_yaml())
    spec = payload["behavior_specifications"][SPEC]
    policy = spec["autonomous_execution"]
    policy["action_candidates"]["portal_login"]["cooldown_ticks"] = 0
    policy["resource_budget"]["dimensions"].update(copy.deepcopy(INTERACTION_DIMENSIONS))
    spec["tool_affordances"] = {
        AFFORDANCE: {"action_contract_refs": [ACTION], "observation_boundary_refs": ["participant-view"]}
    }
    boundary = payload["observation_boundaries"]["participant-view"]
    boundary["observable_refs"].append(AFFORDANCE_REF)
    boundary["view_rules"].append(
        {
            "information_ref": AFFORDANCE_REF,
            "boundary_class": "observable_resource",
            "disposition": "observable",
            "visibility_basis": "The participant may use its portal probe tool.",
        }
    )
    if disclose is not None:
        reference = resource_budget_dimension_reference(SPEC, disclose)
        boundary["hidden_refs"].append(reference)
        boundary["view_rules"].append(
            {
                "information_ref": reference,
                "boundary_class": "resource_budget",
                "disposition": "disclosed",
                "visibility_basis": "The participant is told how much of this tool budget remains.",
                "disclosure_rule": "task-brief.tool-budget",
            }
        )
    return payload


def _source(payload: dict) -> str:
    return yaml.safe_dump(payload, sort_keys=False)


def _policy(payload: dict):
    runtime_model = compile_runtime_model(parse_sdl(_source(payload)))
    return runtime_model, next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )


def _dimensions(payload: dict) -> dict:
    return payload["behavior_specifications"][SPEC]["autonomous_execution"]["resource_budget"]["dimensions"]


def _interaction_pool(dimension: dict) -> ParticipantResourcePoolCapacity:
    return replace(
        _capabilities().configured_pools[0],
        resource_kind=dimension["resource_kind"],
        unit=dimension["unit"],
        accounting_mode=dimension["accounting_mode"],
        meter_profile_ref=dimension["meter_profile_ref"],
        # Headroom over the limit keeps the shared pool from throttling first.
        capacity=dimension["limit"] * 2,
    )


def _interaction_capabilities():
    base = _capabilities()
    return replace(
        base,
        supported_resource_kinds=base.supported_resource_kinds | set(INTERACTION_KINDS),
        supported_reset_modes=base.supported_reset_modes | {"episode"},
        configured_pools=base.configured_pools
        + tuple(_interaction_pool(dimension) for dimension in INTERACTION_DIMENSIONS.values()),
    )


def _interaction_manifest(capabilities=None):
    manifest = _governed_manifest()
    runtime = replace(manifest.participant_runtime, resource_budgets=capabilities or _interaction_capabilities())
    return replace(manifest, capabilities=replace(manifest.capabilities, participant_runtime=runtime))


def _manager(payload: dict, participant_runtime: _NativeParticipantRuntime) -> RuntimeManager:
    target = replace(create_stub_target(), manifest=_interaction_manifest(), participant_runtime=participant_runtime)
    manager = RuntimeManager(target, stochastic_controls=[_activity_control()])
    applied = manager.apply(manager.plan(parse_sdl(_source(payload))))
    assert applied.success, [diagnostic.code for diagnostic in applied.diagnostics]
    return manager


def _validation_messages(payload: dict) -> list[str]:
    source = _source(payload)
    with pytest.raises(SDLValidationError) as raised:
        parse_sdl(source)
    return str(raised.value).splitlines()[1:]


def test_interaction_dimensions_compile_into_the_canonical_demand() -> None:
    _, policy = _policy(_payload())
    demands = {demand.budget_id: demand for demand in policy.resource_demands}

    assert {
        budget_id: (demands[budget_id].resource_kind, demands[budget_id].unit) for budget_id in INTERACTION_DIMENSIONS
    } == {
        "steps": ("interaction_steps", "steps"),
        "turns": ("interaction_turns", "turns"),
        TOOL_BUDGET: ("tool_invocations", "invocations"),
        TIME_BUDGET: ("scenario_time", "ticks"),
    }
    assert demands["tokens"].resource_kind == "inference_tokens"
    assert {demand.provenance for demand in demands.values()} == {"authored"}
    assert demands[TOOL_BUDGET].action_contract_addresses == (f"participant.action-contract.{ACTION}",)
    assert all(
        demand.action_contract_addresses == () for budget_id, demand in demands.items() if budget_id != TOOL_BUDGET
    )
    assert {demand.participant_disclosure_ref for demand in demands.values()} == {None}


@pytest.mark.parametrize(
    ("closed_model", "owner", "field_name", "value"),
    [
        (ParticipantAutonomousExecutionPolicyV3, "autonomous_execution", "max_turns", 10),
        (ParticipantAutonomousExecutionPolicyV3, "autonomous_execution", "max_tool_calls", 3),
        (ParticipantBehaviorSpecification, None, "interaction_quota", {"turns": 10}),
    ],
    ids=["max-turns", "max-tool-calls", "quota-map"],
)
def test_parallel_limit_fields_cannot_bypass_the_resource_family(closed_model, owner, field_name, value) -> None:
    spec = _payload()["behavior_specifications"][SPEC]
    target = spec[owner] if owner is not None else spec
    target[field_name] = value

    with pytest.raises(ValidationError, match=rf"{field_name}\n  Extra inputs are not permitted"):
        closed_model.model_validate(target)


def _turns_into_action_parent(dimensions: dict) -> None:
    dimensions["turns"]["parent_budget_ref"] = "participant-actions"


def _turns_counted_as_actions(dimensions: dict) -> None:
    dimensions["turns"]["unit"] = "actions"


def _steps_as_gauge(dimensions: dict) -> None:
    dimensions["steps"]["accounting_mode"] = "reservable_gauge"


def _watchdog_meter(dimensions: dict) -> None:
    dimensions[TIME_BUDGET]["meter_profile_ref"] = WATCHDOG_METER


def _wall_clock_unit(dimensions: dict) -> None:
    dimensions[TIME_BUDGET]["unit"] = "milliseconds"


def _reclaimed_time(dimensions: dict) -> None:
    dimensions[TIME_BUDGET]["reset"] = "reconciled"


def _episode_relative_time(dimensions: dict) -> None:
    dimensions[TIME_BUDGET]["reset"] = "episode"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_turns_into_action_parent, "same resource, unit, mode, and meter"),
        (_turns_counted_as_actions, "interaction_turns resource quantity requires unit 'turns'"),
        (_steps_as_gauge, "does not support accounting mode 'reservable_gauge'"),
        (_watchdog_meter, "host or watchdog time is not scenario time"),
        (_wall_clock_unit, "scenario_time resource quantity requires unit 'ticks'"),
        (_reclaimed_time, "scenario_time resource budget requires a time_segment or run reset"),
        (_episode_relative_time, "scenario_time resource budget requires a time_segment or run reset"),
    ],
    ids=[
        "turns-under-actions",
        "turns-as-actions",
        "steps-as-gauge",
        "watchdog-meter",
        "wall-clock-unit",
        "reclaim",
        "episode-relative-time",
    ],
)
def test_interaction_dimensions_are_distinct_governed_kinds(mutate, message: str) -> None:
    payload = _payload()
    mutate(_dimensions(payload))
    policy = payload["behavior_specifications"][SPEC]["autonomous_execution"]

    with pytest.raises(ValueError, match=message):
        ParticipantAutonomousExecutionPolicyV3.model_validate(policy)


@pytest.mark.parametrize(
    ("budget_id", "scope"),
    [(TOOL_BUDGET, None), ("turns", [AFFORDANCE])],
    ids=["unscoped-tool-budget", "scoped-turn-budget"],
)
def test_only_tool_use_budgets_carry_a_tool_scope(budget_id: str, scope: list[str] | None) -> None:
    payload = _payload()
    dimension = _dimensions(payload)[budget_id]
    dimension.pop("tool_affordance_refs", None)
    if scope is not None:
        dimension["tool_affordance_refs"] = scope
    policy = payload["behavior_specifications"][SPEC]["autonomous_execution"]

    with pytest.raises(ValidationError, match="tool_invocations resource budgets require tool_affordance_refs"):
        ParticipantAutonomousExecutionPolicyV3.model_validate(policy)


def _unknown_affordance(payload: dict) -> None:
    _dimensions(payload)[TOOL_BUDGET]["tool_affordance_refs"] = ["missing-tool"]


def _undispatched_affordance(payload: dict) -> None:
    payload["behavior_specifications"][SPEC]["tool_affordances"][AFFORDANCE]["action_contract_refs"] = ["other-action"]
    payload["action_contracts"]["other-action"] = copy.deepcopy(payload["action_contracts"][ACTION])
    payload["behavior_specifications"][SPEC]["action_contract_refs"].append("other-action")
    payload["agents"]["participant-agent"]["actions"].append("other-action")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_unknown_affordance, "tool_affordance_ref 'missing-tool' does not name a tool affordance"),
        (_undispatched_affordance, "binds no action contract the autonomous policy dispatches"),
    ],
    ids=["unknown-affordance", "undispatched-affordance"],
)
def test_tool_use_budget_binds_exact_tool_affordances(mutate, message: str) -> None:
    payload = _payload()
    mutate(payload)

    assert any(message in line for line in _validation_messages(payload))


def test_tool_scoped_dimension_reserves_only_for_its_tool_actions() -> None:
    _, policy = _policy(_payload())
    tool_action = f"participant.action-contract.{ACTION}"
    other_action = "participant.action-contract.other-action"

    tool_quantities = action_resource_quantities(policy, tool_action)
    other_quantities = action_resource_quantities(policy, other_action)
    other_requirements = {
        item.budget_state_ref.rsplit(".", 1)[-1]: item.reserved
        for item in measurement_requirements(policy, other_action)
    }

    assert (tool_quantities[TOOL_BUDGET], other_quantities[TOOL_BUDGET], other_requirements[TOOL_BUDGET]) == (1, 0, 0)
    assert {key: value for key, value in other_quantities.items() if key != TOOL_BUDGET} == {
        key: value for key, value in tool_quantities.items() if key != TOOL_BUDGET
    }


@pytest.mark.parametrize("disclose", [TOOL_BUDGET, None], ids=["disclosed", "hidden"])
def test_quota_is_participant_visible_only_through_an_explicit_view_rule(disclose: str | None) -> None:
    participant_runtime = _NativeParticipantRuntime()
    manager = _manager(_payload(disclose=disclose), participant_runtime)

    result = _advance_until_rejected(manager)

    (reject,) = _reject_events(result.snapshot)
    action_result = _terminal_result(_attempt_events(result.snapshot, reject["operation_id"]))
    assert (reject["budget_id"], action_result["failure_class"]) == (TOOL_BUDGET, "resource_exhausted")
    assert reject["operation_id"] not in participant_runtime.native_actions
    reference = resource_budget_dimension_reference(SPEC, TOOL_BUDGET)
    expected = [f"{reference}: 2 of 2 invocations used; 0 remaining; 1 requested"] if disclose else []
    assert action_result["observations"] == expected
    assert reject["budget_state_ref"] not in json.dumps(action_result)


def _observable_quota(boundary: dict) -> None:
    boundary["observable_refs"].append(resource_budget_dimension_reference(SPEC, "turns"))


def _foreign_quota(boundary: dict) -> None:
    reference = resource_budget_dimension_reference("other-behavior", "turns")
    boundary["hidden_refs"].append(reference)
    boundary["view_rules"].append(
        {
            "information_ref": reference,
            "boundary_class": "resource_budget",
            "disposition": "disclosed",
            "visibility_basis": "A quota of another behavior specification.",
            "disclosure_rule": "task-brief.turn-budget",
        }
    )


def _misclassified_quota(boundary: dict) -> None:
    reference = resource_budget_dimension_reference(SPEC, "turns")
    boundary["hidden_refs"].append(reference)
    boundary["view_rules"].append(
        {
            "information_ref": reference,
            "boundary_class": "observable_resource",
            "disposition": "hidden",
            "visibility_basis": "A quota classified as an ordinary resource.",
        }
    )


def _evidence_declared_quota(boundary: dict) -> None:
    reference = resource_budget_dimension_reference(SPEC, "turns")
    boundary["evidence_refs"].append(reference)
    boundary["view_rules"].append(
        {
            "information_ref": reference,
            "boundary_class": "resource_budget",
            "disposition": "disclosed",
            "visibility_basis": "A quota declared as evidence rather than hidden state.",
            "disclosure_rule": "task-brief.turn-budget",
        }
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_observable_quota, "a quota is disclosed only through a resource_budget view rule"),
        (_foreign_quota, "does not name a dimension governed through this boundary"),
        (_misclassified_quota, "must pair the resource_budget class with a resource-budget dimension ref"),
        (_evidence_declared_quota, "must declare its dimension in hidden_refs"),
    ],
    ids=["observable-ref", "foreign-dimension", "misclassified", "evidence-declared"],
)
def test_quota_cannot_be_exposed_without_an_explicit_view_rule(mutate, message: str) -> None:
    payload = _payload()
    mutate(payload["observation_boundaries"]["participant-view"])

    assert any(message in line for line in _validation_messages(payload))


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"disposition": "observable"}, "resource_budget must use disposition disclosed, not observable"),
        ({"disclosure_rule": None}, "disclosed view rules require an explicit disclosure_rule"),
    ],
    ids=["observable", "no-disclosure-rule"],
)
def test_quota_disclosure_requires_a_disclosure_rule(update: dict, message: str) -> None:
    boundary = _payload(disclose=TOOL_BUDGET)["observation_boundaries"]["participant-view"]
    boundary["view_rules"][-1].update(update)

    with pytest.raises(ValidationError, match=message):
        ParticipantObservationBoundary.model_validate(boundary)


def test_quota_disclosure_compiles_onto_the_disclosed_dimension_only() -> None:
    _, policy = _policy(_payload(disclose=TOOL_BUDGET))

    disclosed = {
        demand.budget_id: demand.participant_disclosure_ref
        for demand in policy.resource_demands
        if demand.participant_disclosure_ref is not None
    }

    assert disclosed == {TOOL_BUDGET: resource_budget_dimension_reference(SPEC, TOOL_BUDGET)}


def test_tool_scope_and_disclosure_enter_the_policy_identity() -> None:
    from raes_runtime.participant_scheduler_policy import _policy_digest

    hidden_model, hidden = _policy(_payload())
    disclosed_model, disclosed = _policy(_payload(disclose=TOOL_BUDGET))
    unscoped = replace(
        hidden,
        resource_demands=tuple(replace(demand, action_contract_addresses=()) for demand in hidden.resource_demands),
    )

    digests = {
        _policy_digest(hidden, hidden_model.time_model),
        _policy_digest(disclosed, disclosed_model.time_model),
        _policy_digest(unscoped, hidden_model.time_model),
    }
    assert len(digests) == 3


def _module_payload(*, observable: bool) -> dict:
    payload = _payload(disclose=TOOL_BUDGET)
    if observable:
        _observable_quota(payload["observation_boundaries"]["participant-view"])
    payload["module"] = {
        "id": "example/interaction-budgets",
        "version": "1.0.0",
        "exports": {
            "agents": ["participant-agent"],
            "behavior_specifications": [SPEC],
            "deployment_tenants": ["range-a", "range-b"],
            "infrastructure": ["customer-portal"],
            "nodes": ["customer-portal"],
            "observation_boundaries": ["participant-view"],
        },
    }
    return payload


def _import_under_namespace(tmp_path: Path, payload: dict):
    (tmp_path / "module.yaml").write_text(_source(payload), encoding="utf-8")
    root = tmp_path / "root.yaml"
    root.write_text(
        _source(
            {
                "name": "imported-interaction-budgets",
                "imports": [{"path": "module.yaml", "namespace": "shared", "version": "1.0.0"}],
            }
        ),
        encoding="utf-8",
    )
    return parse_sdl_file(root)


def test_imported_quota_disclosure_follows_the_namespaced_behavior_specification(tmp_path: Path) -> None:
    expanded = _import_under_namespace(tmp_path, _module_payload(observable=False))

    policy = next(
        specification.autonomous_execution
        for specification in compile_runtime_model(expanded).behavior_specifications.values()
        if specification.autonomous_execution is not None
    )
    demands = {demand.budget_id: demand for demand in policy.resource_demands}
    assert demands[TOOL_BUDGET].participant_disclosure_ref == resource_budget_dimension_reference(
        f"shared.{SPEC}", TOOL_BUDGET
    )
    (tool_action,) = demands[TOOL_BUDGET].action_contract_addresses
    assert tool_action in policy.action_contract_addresses
    assert tool_action.startswith("participant.action-contract.shared.")
    assert tool_action.endswith(f".{ACTION}")


def test_imported_quota_stays_hidden_unless_disclosed(tmp_path: Path) -> None:
    namespaced = resource_budget_dimension_reference(f"shared.{SPEC}", "turns")
    payload = _module_payload(observable=True)

    with pytest.raises(SDLValidationError) as raised:
        _import_under_namespace(tmp_path, payload)

    assert f"exposes resource budget '{namespaced}' as observable" in str(raised.value)


def test_interaction_budget_keys_cannot_come_from_variables() -> None:
    payload = _payload()
    _dimensions(payload)["${budget_name}"] = _dimensions(payload).pop("turns")
    source = _source(payload)

    with pytest.raises(SDLParseError, match="Variable placeholders are not allowed in user-defined mapping keys"):
        parse_sdl(source)


def test_published_policy_contract_carries_the_tool_scope_and_time_basis() -> None:
    scoped = json.loads((POLICY_FIXTURES / "valid/scoped-tool-invocations.json").read_text(encoding="utf-8"))
    unscoped = json.loads((POLICY_FIXTURES / "invalid/unscoped-tool-invocations.json").read_text(encoding="utf-8"))

    assert ParticipantResourceBudgetPolicyModel.model_validate(scoped).demands[-1].action_contract_refs == (
        f"participant.action-contract.{ACTION}",
    )
    with pytest.raises(ValidationError, match="tool_invocations resource budgets require action_contract_refs"):
        ParticipantResourceBudgetPolicyModel.model_validate(unscoped)
    assert set(INTERACTION_KINDS) <= set(
        schema_bundle()["participant-resource-budget-policy-v1"]["$defs"]["ParticipantResourceQuantityModel"][
            "properties"
        ]["resource_kind"]["anyOf"][0]["enum"]
    )


_TIMED_QUANTITY = {"resource_kind": "scenario_time", "unit": "ticks", "meter_profile_ref": WATCHDOG_METER}
_TIME_STATE_REF = participant_resource_budget_state_ref(POLICY_ADDRESS, TIME_BUDGET)


def _watchdog_pool() -> dict:
    pool = next(item for item in _interaction_capabilities().configured_pools if item.resource_kind == "scenario_time")
    payload = ParticipantResourcePoolCapacityModel.model_validate(pool.__dict__).model_dump(mode="json")
    return payload | {"meter_profile_ref": WATCHDOG_METER}


def _watchdog_requirement() -> dict:
    return {"budget_state_ref": _TIME_STATE_REF, "reserved": 1} | _TIMED_QUANTITY


def _watchdog_measurement() -> dict:
    return {
        "budget_state_ref": _TIME_STATE_REF,
        "operation_id": "attempt-1",
        "execution_generation": 0,
        "measured": 1,
        "evidence_refs": ["evidence:attempt-1"],
    } | _TIMED_QUANTITY


def _watchdog_event() -> dict:
    return {
        "event_id": f"attempt-1:{_TIME_STATE_REF}:reserve",
        "operation_id": "attempt-1",
        "budget_state_ref": _TIME_STATE_REF,
        "budget_id": TIME_BUDGET,
        "policy_address": POLICY_ADDRESS,
        "owner_ref": "green",
        "pool_ref": "participant-pool",
        "execution_generation": 0,
        "transition": "reserve",
        "disposition": "reserved",
        "requested": 1,
    } | _TIMED_QUANTITY


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (ParticipantResourcePoolCapacityModel, _watchdog_pool),
        (ParticipantResourceMeasurementRequirementModel, _watchdog_requirement),
        (ParticipantResourceMeasurementModel, _watchdog_measurement),
        (ParticipantResourceBudgetEventModel, _watchdog_event),
    ],
    ids=["configured-pool", "measurement-requirement", "measurement", "budget-event"],
)
def test_scenario_time_contracts_must_meter_shared_time(model, payload) -> None:
    data = payload()

    with pytest.raises(ValidationError, match="host or watchdog time is not scenario time"):
        model.model_validate(data)


class _RecordingRuntime(_NativeParticipantRuntime):
    """Native runtime that records which resource kinds each attempt asked it to measure."""

    def __init__(self) -> None:
        super().__init__()
        self.measured_kinds: set[str] = set()

    def _model_action(self, request, snapshot, *, episode_id):
        self.measured_kinds.update(item.resource_kind for item in request.resource_measurement_requirements)
        return super()._model_action(request, snapshot, episode_id=episode_id)


def test_scenario_time_is_metered_from_the_shared_clock() -> None:
    payload = _payload(disclose=TIME_BUDGET)
    _dimensions(payload)[TOOL_BUDGET]["limit"] = 4
    _dimensions(payload)[TIME_BUDGET]["limit"] = 45
    participant_runtime = _RecordingRuntime()
    manager = _manager(payload, participant_runtime)

    result = _advance_until_rejected(manager)

    (reject,) = _reject_events(result.snapshot)
    used = result.snapshot.participant_resource_budget_states[_TIME_STATE_REF]["cumulative_use"]
    commits = [
        event
        for event in result.snapshot.participant_resource_budget_events.values()
        if event["transition"] == "commit" and event["budget_state_ref"] == _TIME_STATE_REF
    ]
    elapsed = manager.read_time_state().clocks[SCENARIO_CLOCK_ADDRESS].coordinate.tick
    assert reject["budget_id"] == TIME_BUDGET
    # Idle ticks are charged: the rejected attempt requests every tick elapsed
    # since the last charge plus its one-tick allowance.
    assert used + reject["requested"] - 1 == elapsed
    assert sum(event["measured"] for event in commits) == used
    assert all(
        f"evidence:{SCENARIO_CLOCK_ADDRESS}:clock-history-" in " ".join(event["evidence_refs"]) for event in commits
    )
    assert "scenario_time" not in participant_runtime.measured_kinds
    assert "tool_invocations" in participant_runtime.measured_kinds
    action_result = _terminal_result(_attempt_events(result.snapshot, reject["operation_id"]))
    reference = resource_budget_dimension_reference(SPEC, TIME_BUDGET)
    assert action_result["observations"] == [
        f"{reference}: {used} of 45 ticks used; {45 - used} remaining; {reject['requested']} requested"
    ]


_CLOCK_TRANSITIONS = (
    ("advance", 0, 10),
    ("pause", 0, 10),
    ("resume", 0, 10),
    ("advance", 0, 25),
    ("jump", 1, 100),
    ("advance", 1, 110),
    ("reset", 2, 0),
    ("advance", 2, 7),
    ("replay", 3, 3),
    ("advance", 3, 8),
)


def _clock_history(transitions: tuple[tuple[str, int, int], ...]) -> RuntimeClockStateModel:
    events = [
        ClockTransitionEventModel(
            sequence=0,
            kind="initialize",
            previous=None,
            resulting=TimeCoordinateModel(tick=0),
            resulting_state="running",
        )
    ]
    for kind, segment, tick in transitions:
        events.append(
            ClockTransitionEventModel(
                sequence=len(events),
                kind=kind,
                previous=events[-1].resulting,
                resulting=TimeCoordinateModel(segment=segment, tick=tick),
                resulting_state="paused" if kind == "pause" else "running",
            )
        )
    return RuntimeClockStateModel(
        clock_address=SCENARIO_CLOCK_ADDRESS,
        time_domain_address="time.domain.scenario-time",
        authority_kind="runtime",
        authority_ref="raes.reference-time",
        state=events[-1].resulting_state,
        coordinate=events[-1].resulting,
        sequence=events[-1].sequence,
        history=events,
    )


@pytest.mark.parametrize(("reset", "elapsed"), [("time_segment", 12), ("run", 47)])
def test_scenario_time_elapses_only_while_the_shared_clock_advances(reset: str, elapsed: int) -> None:
    # Pause and resume keep the coordinate; jump and replay open a segment
    # without elapsing time; only a reset reopens the time_segment boundary.
    assert elapsed_scenario_ticks(_clock_history(_CLOCK_TRANSITIONS), reset) == elapsed


def test_disclosure_reports_only_this_policys_rejection_against_the_authored_limit() -> None:
    payload = _payload(disclose=TOOL_BUDGET)
    result = _advance_until_rejected(_manager(payload, _NativeParticipantRuntime()))
    (reject,) = _reject_events(result.snapshot)
    states = dict(result.snapshot.participant_resource_budget_states)
    # A shared pool smaller than the authored limit is backend configuration.
    states[reject["budget_state_ref"]] = states[reject["budget_state_ref"]] | {"configured_capacity": 1}
    snapshot = result.snapshot.with_entries(dict(result.snapshot.entries), participant_resource_budget_states=states)
    _, policy = _policy(payload)
    foreign = replace(policy, address="participant.autonomous-execution.other-behavior")

    reference = resource_budget_dimension_reference(SPEC, TOOL_BUDGET)
    assert disclosed_rejection_quota(policy, reject["operation_id"], snapshot) == (
        f"{reference}: 2 of 2 invocations used; 0 remaining; 1 requested",
    )
    assert disclosed_rejection_quota(foreign, reject["operation_id"], snapshot) == ()


def test_backend_must_declare_each_interaction_kind_it_admits() -> None:
    runtime_model, policy = _policy(_payload())
    capabilities = _interaction_capabilities()
    without_turns = replace(
        capabilities,
        supported_resource_kinds=capabilities.supported_resource_kinds - {"interaction_turns"},
        configured_pools=tuple(
            pool for pool in capabilities.configured_pools if pool.resource_kind != "interaction_turns"
        ),
    )

    admitted = participant_autonomous_execution_capability_gaps(
        _interaction_manifest(), (policy,), runtime_model.time_model
    )
    refused = participant_autonomous_execution_capability_gaps(
        _interaction_manifest(without_turns), (policy,), runtime_model.time_model
    )

    assert admitted == ()
    assert refused == ("participant resource budget turns unsupported: resource kind interaction_turns",)


def _table_rows(path: Path, heading: str) -> list[list[str]]:
    rows: list[list[str]] = []
    in_table = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            in_table = line.startswith(heading)
        elif in_table and line.startswith("|") and not line.startswith("| ---"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows[1:]


def test_traceability_table_covers_the_design_routed_invariants() -> None:
    routed = {
        invariant
        for row in _table_rows(DESIGN, "## Source-to-contract-to-test matrix")
        if "#308" in row[-1]
        for invariant in re.findall(r"EBM-\d{2}", row[0])
    }
    rows = _table_rows(SEMANTICS, "### DSL-121 Traceability")
    named = {name for row in rows for cell in row[3:] for name in re.findall(r"`(test_[a-z0-9_]+)`", cell)}
    defined = {
        node.name
        for node in ast.walk(ast.parse(Path(__file__).read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }

    assert routed
    assert routed <= {invariant for row in rows for invariant in re.findall(r"EBM-\d{2}", row[1])}
    assert named
    assert named <= defined
