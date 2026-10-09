"""Issue #306 (SEM-223): participant budget consumption, exhaustion, and limit effects.

The tests follow the SEM-223 rows of the issue #122 source-to-contract-to-test
matrix in ``specs/formal/participant-episode-model/README.md``. They include
the negative fixtures named on issue #306: global counters leaking into
participant-local budgets, stale or future consumption events, exhaustion that
bypasses the SEM-211 controlled failure classes, hidden quota state exposed
without a view rule, mishandled reset boundaries, and backend-local limits
presented as portable budget limits.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
import yaml
from implementations.python.tests.test_dsl_437_benign_participant_execution import (
    SCENARIO_CLOCK_ADDRESS,
    SCENARIO_CLOCK_STEP_TICKS,
    _activity_control,
    _NativeParticipantRuntime,
)
from implementations.python.tests.test_issue_899_participant_resource_budgets import (
    _budget_policy_yaml,
    _capabilities,
    _governed_manifest,
)
from raes import parse_sdl
from raes._errors import SDLValidationError
from raes.participant_execution import ParticipantAutonomousExecutionPolicyV3
from raes_backend_protocols.capability_admission import participant_autonomous_execution_capability_gaps
from raes_backend_stubs.stubs import create_stub_target
from raes_conformance.conformance import _semantic_diagnostics
from raes_contracts.contracts.participant_resource_budgets import (
    ParticipantResourceBudgetPolicyModel,
    ParticipantResourceBudgetStateModel,
    participant_resource_budget_state_ref,
)
from raes_contracts.participant_resource_exhaustion import (
    PARTICIPANT_RESOURCE_BUDGET_PRECONDITION_ID,
    PARTICIPANT_RESOURCE_EXHAUSTED_CODE,
    iter_participant_resource_budget_event_violations,
    iter_participant_resource_exhaustion_violations,
    participant_resource_admission_state,
    participant_resource_remaining,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, RuntimeSnapshotEnvelope
from raes_processor.compiler import compile_runtime_model
from raes_runtime import participant_scheduler_operations
from raes_runtime.control_plane_api_models import _snapshot_model
from raes_runtime.manager import RuntimeManager
from raes_runtime.participant_activity import resolve_participant_activity_controls
from raes_runtime.participant_resource_accounting import (
    commit_participant_resource_reservation,
    reconcile_participant_resource_budgets,
    release_participant_resource_reservation,
)
from raes_runtime.participant_resource_budgets import (
    initialize_participant_resource_budgets,
    reserve_participant_resources,
)
from raes_runtime.participant_scheduler import ParticipantScheduler
from raes_runtime.result_contracts import (
    participant_runtime_history_transition_diagnostics,
    participant_runtime_state_contract_diagnostics,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_FIXTURE = (
    REPO_ROOT
    / "contracts/fixtures/participant-runtime/participant-resource-budget-policy-v1/valid/complete-resource-vector.json"
)
ACTIONS = "participant-actions"
EPISODE_ACTIONS = {ACTIONS: {"limit": 2, "reset": "episode"}}
STALE_CODE = "runtime.participant-resource-stale-generation"
SETTLED_CODE = "runtime.participant-resource-reservation-settled"
THROTTLED_CODE = "runtime.participant-resource-throttled"


def _budget_payload(
    updates: dict[str, dict[str, object]] | None = None,
    *,
    failure_policy: str = "continue",
) -> dict:
    payload = yaml.safe_load(_budget_policy_yaml())
    policy = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    policy["failure_policy"] = failure_policy
    policy["action_candidates"]["portal_login"]["cooldown_ticks"] = 0
    for budget_id, update in (updates or {}).items():
        policy["resource_budget"]["dimensions"][budget_id].update(update)
    return payload


def _authored_policy(payload: dict) -> dict:
    return payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]


def _runtime_model(payload: dict):
    return compile_runtime_model(parse_sdl(yaml.safe_dump(payload, sort_keys=False)))


def _compiled_policy(runtime_model):
    return next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )


def _policy(payload: dict):
    return _compiled_policy(_runtime_model(payload))


def _initialized(*policies) -> RuntimeSnapshot:
    result = initialize_participant_resource_budgets(
        RuntimeSnapshot(), policies, _capabilities(), execution_generation=0
    )
    assert result.success
    return result.snapshot


def _state(snapshot: RuntimeSnapshot, policy, budget_id: str) -> ParticipantResourceBudgetStateModel:
    return ParticipantResourceBudgetStateModel.model_validate(
        snapshot.participant_resource_budget_states[participant_resource_budget_state_ref(policy.address, budget_id)]
    )


def _only(policy, budget_id: str) -> dict[str, int]:
    """Request one unit of a single dimension and nothing of the rest of the vector."""

    return {demand.budget_id: int(demand.budget_id == budget_id) for demand in policy.resource_demands}


def _reserved_vector(snapshot: RuntimeSnapshot, operation_id: str) -> dict[str, int]:
    return {
        str(event["budget_state_ref"]): int(event["requested"])
        for event in snapshot.participant_resource_budget_events.values()
        if event["operation_id"] == operation_id and event["transition"] == "reserve"
    }


def _commit(snapshot: RuntimeSnapshot, operation_id: str, generation: int) -> ApplyResult:
    return commit_participant_resource_reservation(
        snapshot,
        operation_id=operation_id,
        execution_generation=generation,
        measured_quantities=_reserved_vector(snapshot, operation_id),
        evidence_refs=(f"evidence:{operation_id}:meter",),
    )


def _release(snapshot: RuntimeSnapshot, operation_id: str, generation: int) -> ApplyResult:
    return release_participant_resource_reservation(
        snapshot,
        operation_id=operation_id,
        execution_generation=generation,
        evidence_refs=(f"evidence:{operation_id}:release",),
    )


def _reserve(snapshot: RuntimeSnapshot, policy, operation_id: str, quantities=None) -> ApplyResult:
    return reserve_participant_resources(
        snapshot,
        policy,
        operation_id=operation_id,
        execution_generation=0,
        requested_quantities=quantities,
    )


def _reserved(snapshot: RuntimeSnapshot, policy, operation_id: str, quantities=None) -> RuntimeSnapshot:
    result = _reserve(snapshot, policy, operation_id, quantities)
    assert result.success, [diagnostic.code for diagnostic in result.diagnostics]
    return result.snapshot


def _committed(snapshot: RuntimeSnapshot, policy, operation_id: str, quantities=None) -> RuntimeSnapshot:
    result = _commit(_reserved(snapshot, policy, operation_id, quantities), operation_id, 0)
    assert result.success, [diagnostic.code for diagnostic in result.diagnostics]
    return result.snapshot


def _reconciled(snapshot: RuntimeSnapshot, policy) -> RuntimeSnapshot:
    result = reconcile_participant_resource_budgets(
        snapshot,
        policy_address=policy.address,
        current_generation=0,
        next_generation=1,
        boundary="time_segment",
        evidence_refs=("evidence:reset:generation-1",),
    )
    assert result.success
    return result.snapshot


def _episode_manifest():
    manifest = _governed_manifest()
    budgets = replace(
        _capabilities(),
        supported_reset_modes=_capabilities().supported_reset_modes | {"episode"},
    )
    runtime = replace(manifest.participant_runtime, resource_budgets=budgets)
    return replace(manifest, capabilities=replace(manifest.capabilities, participant_runtime=runtime))


def _manager(payload: dict, participant_runtime: _NativeParticipantRuntime) -> RuntimeManager:
    target = replace(create_stub_target(), manifest=_episode_manifest(), participant_runtime=participant_runtime)
    manager = RuntimeManager(target, stochastic_controls=[_activity_control()])
    applied = manager.apply(manager.plan(parse_sdl(yaml.safe_dump(payload, sort_keys=False))))
    assert applied.success, [diagnostic.code for diagnostic in applied.diagnostics]
    return manager


def _scheduler_state(snapshot: RuntimeSnapshot) -> dict:
    return next(iter(snapshot.participant_autonomous_execution_states.values()))


def _advance_to_next_action(manager: RuntimeManager) -> ApplyResult:
    """Advance the stepped clock one step at a time up to the next due action."""

    target = _scheduler_state(manager.snapshot)["next_tick"]
    while True:
        result = manager.advance_time(SCENARIO_CLOCK_ADDRESS, ticks=SCENARIO_CLOCK_STEP_TICKS)
        if manager.read_time_state().clocks[SCENARIO_CLOCK_ADDRESS].coordinate.tick >= target:
            return result
        assert result.success, [diagnostic.code for diagnostic in result.diagnostics]


def _reject_events(snapshot: RuntimeSnapshot) -> list[dict]:
    return [event for event in snapshot.participant_resource_budget_events.values() if event["transition"] == "reject"]


def _advance_until_rejected(manager: RuntimeManager) -> ApplyResult:
    """Advance the governed clock action by action until a budget rejection is recorded."""

    for _ in range(12):
        assert _scheduler_state(manager.snapshot)["lifecycle_state"] == "running"
        result = _advance_to_next_action(manager)
        if _reject_events(result.snapshot):
            return result
        assert result.success, [diagnostic.code for diagnostic in result.diagnostics]
    raise AssertionError("no participant resource budget rejection was recorded")


def _attempt_events(snapshot: RuntimeSnapshot, action_instance_id: str) -> list[dict]:
    return [
        event
        for history in snapshot.participant_behavior_history.values()
        for event in history
        if event.get("action_instance_id") == action_instance_id
    ]


def _terminal_result(events: list[dict]) -> dict:
    return next(event["action_result"] for event in events if event["event_type"] == "observation_emitted")


@pytest.fixture(scope="module")
def exhausted_run() -> tuple[_NativeParticipantRuntime, ApplyResult]:
    participant_runtime = _NativeParticipantRuntime()
    manager = _manager(_budget_payload(EPISODE_ACTIONS), participant_runtime)
    return participant_runtime, _advance_until_rejected(manager)


def test_exhaustion_is_derived_from_remaining_capacity_across_reserve_commit_cycles() -> None:
    policy = _policy(_budget_payload({ACTIONS: {"limit": 3}}))
    snapshot = _initialized(policy)
    observed = []
    for cycle in range(3):
        snapshot = _committed(snapshot, policy, f"cycle-{cycle}")
        state = _state(snapshot, policy, ACTIONS)
        observed.append((participant_resource_remaining(state), participant_resource_admission_state(state)))

    assert observed == [(2, "open"), (1, "open"), (0, "exhausted")]

    refused = _reserve(snapshot, policy, "cycle-3")
    state = _state(refused.snapshot, policy, ACTIONS)
    assert refused.success is False
    assert [diagnostic.code for diagnostic in refused.diagnostics] == [PARTICIPANT_RESOURCE_EXHAUSTED_CODE]
    assert (state.reserved, state.cumulative_use, state.rejected, state.throttled) == (0, 3, 1, 0)
    assert refused.snapshot.participant_resource_budget_events[f"cycle-3:{state.state_ref}:reject"]["disposition"] == (
        "rejected"
    )
    assert _reserved_vector(refused.snapshot, "cycle-3") == {}


def test_logical_exhaustion_rejects_while_shared_pool_contention_throttles() -> None:
    policy = _policy(_budget_payload({ACTIONS: {"limit": 12}}))
    competing = replace(policy, address=f"{policy.address}.competing")
    snapshot = _initialized(policy, competing)
    for cycle in range(12):
        snapshot = _committed(snapshot, policy, f"own-{cycle}", _only(policy, ACTIONS))
    logical = _reserve(snapshot, policy, "own-12", _only(policy, ACTIONS))
    for cycle in range(11):
        snapshot = _committed(snapshot, competing, f"other-{cycle}", _only(competing, ACTIONS))
    contended = _reserve(snapshot, competing, "other-11", _only(competing, ACTIONS))
    for cycle in range(19):
        snapshot = _committed(snapshot, competing, f"images-{cycle}", _only(competing, "images"))
    # The images pool is now full and is checked before participant-actions in the vector.
    both = _reserve(snapshot, policy, "own-both", _only(policy, ACTIONS) | {"images": 1})

    outcomes = [
        (refusal.diagnostics[0].code, _state(refusal.snapshot, owner, ACTIONS))
        for refusal, owner in ((logical, policy), (contended, competing), (both, policy))
    ]
    assert [(code, state.rejected, state.throttled) for code, state in outcomes] == [
        (PARTICIPANT_RESOURCE_EXHAUSTED_CODE, 1, 0),
        (THROTTLED_CODE, 0, 1),
        (PARTICIPANT_RESOURCE_EXHAUSTED_CODE, 1, 0),
    ]
    assert participant_resource_remaining(outcomes[1][1]) == 1
    assert _state(both.snapshot, policy, "images").throttled == 0


def test_exhaustion_becomes_an_undispatched_resource_exhausted_attempt(exhausted_run) -> None:
    participant_runtime, result = exhausted_run
    snapshot = result.snapshot
    (reject,) = _reject_events(snapshot)
    events = _attempt_events(snapshot, reject["operation_id"])
    action_result = _terminal_result(events)
    (precondition,) = action_result["preconditions"]

    assert result.success is True
    assert reject["operation_id"] not in participant_runtime.native_actions
    assert [event["event_type"] for event in events] == [
        "action_attempted",
        "state_transition_recorded",
        "observation_emitted",
    ]
    assert events[0]["admission_disposition"] == "rejected"
    assert events[1]["state_transition_kind"] == "participant_resource_rejected"
    assert (action_result["status"], action_result["failure_class"]) == ("rejected", "resource_exhausted")
    assert (precondition["precondition_id"], precondition["precondition_class"], precondition["status"]) == (
        PARTICIPANT_RESOURCE_BUDGET_PRECONDITION_ID,
        "resource",
        "unsatisfied",
    )
    episode = snapshot.participant_episode_results[events[0]["participant_address"]]
    assert (episode["status"], episode["terminal_reason"]) == ("running", None)
    assert _scheduler_state(snapshot)["lifecycle_state"] == "running"
    assert participant_runtime_state_contract_diagnostics(snapshot) == []


def test_exhaustion_under_stop_policy_fails_the_scheduler_through_the_attempt() -> None:
    manager = _manager(_budget_payload(EPISODE_ACTIONS, failure_policy="stop"), _NativeParticipantRuntime())

    result = _advance_until_rejected(manager)

    (reject,) = _reject_events(result.snapshot)
    action_result = _terminal_result(_attempt_events(result.snapshot, reject["operation_id"]))
    assert result.success is False
    assert PARTICIPANT_RESOURCE_EXHAUSTED_CODE in [diagnostic.code for diagnostic in result.diagnostics]
    assert action_result["failure_class"] == "resource_exhausted"
    assert _scheduler_state(result.snapshot)["lifecycle_state"] == "failed"
    assert participant_runtime_state_contract_diagnostics(result.snapshot) == []


def test_rejected_attempt_failing_protocol_validation_leaves_no_reject_event(monkeypatch) -> None:
    validate = participant_scheduler_operations.autonomous_action_result_violation

    def refuse_rejections(request, result, *, episode_id, predecessor):
        if result.action_result is not None and result.action_result.failure_class == "resource_exhausted":
            return "forced protocol violation"
        return validate(request, result, episode_id=episode_id, predecessor=predecessor)

    monkeypatch.setattr(participant_scheduler_operations, "autonomous_action_result_violation", refuse_rejections)
    manager = _manager(_budget_payload(EPISODE_ACTIONS), _NativeParticipantRuntime())
    result = _advance_to_next_action(manager)
    for _ in range(12):
        if not result.success:
            break
        result = _advance_to_next_action(manager)

    assert "runtime.participant-autonomous-action-protocol-invalid" in [
        diagnostic.code for diagnostic in result.diagnostics
    ]
    assert _scheduler_state(result.snapshot)["lifecycle_state"] == "failed"
    assert _reject_events(result.snapshot) == []
    assert participant_runtime_state_contract_diagnostics(result.snapshot) == []


def test_participant_visible_attempt_names_no_budget_quantity_or_identity(exhausted_run) -> None:
    _, result = exhausted_run
    (reject,) = _reject_events(result.snapshot)
    visible = json.dumps(_terminal_result(_attempt_events(result.snapshot, reject["operation_id"])))
    state = ParticipantResourceBudgetStateModel.model_validate(
        result.snapshot.participant_resource_budget_states[reject["budget_state_ref"]]
    )

    assert '"support_refs": []' in visible
    assert all(
        hidden not in visible for hidden in (reject["budget_state_ref"], reject["pool_ref"], reject["budget_id"])
    )
    assert (state.limit, state.cumulative_use, participant_resource_remaining(state)) == (2, 2, 0)


def test_coordinated_reset_clears_only_episode_and_segment_owned_use() -> None:
    participant_runtime = _NativeParticipantRuntime()
    manager = _manager(_budget_payload(EPISODE_ACTIONS), participant_runtime)
    exhausted = _advance_until_rejected(manager).snapshot
    before = {key.rsplit(".", 1)[-1]: value for key, value in exhausted.participant_resource_budget_states.items()}

    reset = manager.reset_time(SCENARIO_CLOCK_ADDRESS)

    assert reset.success
    after = {key.rsplit(".", 1)[-1]: value for key, value in reset.snapshot.participant_resource_budget_states.items()}
    cleared = {
        budget_id: before[budget_id]["reset"] for budget_id, state in after.items() if state["cumulative_use"] == 0
    }
    assert cleared == {ACTIONS: "episode", "tokens": "time_segment"}
    assert all(
        after[budget_id]["cumulative_use"] == before[budget_id]["cumulative_use"] > 0
        for budget_id in set(after) - set(cleared)
    )
    assert {state["generation"] for state in after.values()} == {1}
    assert set(exhausted.participant_resource_budget_events) < set(reset.snapshot.participant_resource_budget_events)
    dispatched = len(participant_runtime.native_actions)
    assert _advance_to_next_action(manager).success
    assert len(participant_runtime.native_actions) > dispatched


def test_clock_reset_without_an_episode_reset_keeps_episode_owned_use() -> None:
    payload = _budget_payload(EPISODE_ACTIONS)
    exhausted = _advance_until_rejected(_manager(payload, _NativeParticipantRuntime())).snapshot
    runtime_model = _runtime_model(payload)
    policy = _compiled_policy(runtime_model)

    reset = ParticipantScheduler.reset_clock(
        (policy,),
        runtime_model.time_model,
        _NativeParticipantRuntime(),
        exhausted,
        SCENARIO_CLOCK_ADDRESS,
        reset_participants=False,
        activity_controls=resolve_participant_activity_controls([_activity_control()]),
    )

    assert reset.success, [diagnostic.code for diagnostic in reset.diagnostics]
    assert reset.snapshot.participant_episode_results == exhausted.participant_episode_results
    assert (
        _state(reset.snapshot, policy, ACTIONS).cumulative_use,
        _state(reset.snapshot, policy, "tokens").cumulative_use,
    ) == (
        2,
        0,
    )


@pytest.mark.parametrize("settle", [_commit, _release], ids=["commit", "release"])
def test_pre_reset_reservation_cannot_settle_into_the_next_generation(settle: Callable[..., ApplyResult]) -> None:
    policy = _policy(_budget_payload())
    reconciled = _reconciled(_reserved(_initialized(policy), policy, "before-reset"), policy)

    leaked = settle(reconciled, "before-reset", 1)

    assert leaked.success is False
    assert [diagnostic.code for diagnostic in leaked.diagnostics] == [STALE_CODE]
    assert leaked.snapshot is reconciled
    assert (
        _state(leaked.snapshot, policy, "images").cumulative_use,
        _state(leaked.snapshot, policy, "images").reserved,
    ) == (
        0,
        0,
    )


@pytest.mark.parametrize(
    ("first", "second", "expected_codes"),
    [
        (_commit, _release, [SETTLED_CODE]),
        (_release, _commit, [SETTLED_CODE]),
        (_commit, _commit, []),
        (_release, _release, []),
    ],
    ids=["release-after-commit", "commit-after-release", "repeat-commit", "repeat-release"],
)
def test_each_reservation_settles_exactly_once(
    first: Callable[..., ApplyResult],
    second: Callable[..., ApplyResult],
    expected_codes: list[str],
) -> None:
    policy = _policy(_budget_payload())
    snapshot = _reserved(_reserved(_initialized(policy), policy, "first"), policy, "other", _only(policy, "tokens"))
    settled = first(snapshot, "first", 0)
    assert settled.success

    repeated = second(settled.snapshot, "first", 0)

    assert [diagnostic.code for diagnostic in repeated.diagnostics] == expected_codes
    assert repeated.success is (not expected_codes)
    assert repeated.snapshot.participant_resource_budget_events == settled.snapshot.participant_resource_budget_events
    assert _state(repeated.snapshot, policy, "tokens").reserved == 1


def _settled_stream(policy) -> RuntimeSnapshot:
    snapshot = _committed(_initialized(policy), policy, "committed")
    released = _release(_reserved(snapshot, policy, "released"), "released", 0)
    assert released.success
    return _reconciled(released.snapshot, policy)


def _event_key(policy, operation_id: str, transition: str) -> str:
    return f"{operation_id}:{participant_resource_budget_state_ref(policy.address, 'tokens')}:{transition}"


@dataclass
class _Stream:
    """Mutable copy of one policy's budget states and events."""

    policy: object
    states: dict
    events: dict

    def event(self, operation_id: str, transition: str) -> dict:
        return self.events[_event_key(self.policy, operation_id, transition)]


def _future_event(stream: _Stream) -> None:
    stream.event("committed", "reserve")["execution_generation"] = 7


def _cross_generation_settlement(stream: _Stream) -> None:
    stream.event("committed", "commit")["execution_generation"] = 1


def _double_settlement(stream: _Stream) -> None:
    release_id = _event_key(stream.policy, "committed", "release")
    stream.events[release_id] = {
        **stream.event("committed", "commit"),
        "event_id": release_id,
        "transition": "release",
        "disposition": "released",
    }


def _over_measured_commit(stream: _Stream) -> None:
    stream.event("committed", "commit")["measured"] = 501


def _orphan_settlement(stream: _Stream) -> None:
    stream.event("committed", "commit")["predecessor_event_ref"] = "missing-reservation"


def _dangling_state_head(stream: _Stream) -> None:
    stream.states[participant_resource_budget_state_ref(stream.policy.address, "tokens")]["last_event_ref"] = (
        "missing-event"
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_future_event, "future generation"),
        (_cross_generation_settlement, "does not settle a same-generation reservation"),
        (_double_settlement, "settled more than once"),
        (_over_measured_commit, "measured more than its reservation"),
        (_orphan_settlement, "does not settle a same-generation reservation"),
        (_dangling_state_head, "does not resolve to its own event stream"),
    ],
    ids=["future", "cross-generation", "double-settlement", "over-measured", "orphan", "dangling-head"],
)
def test_consumption_events_fail_closed_when_stale_future_or_unordered(mutate, message: str) -> None:
    policy = _policy(_budget_payload())
    snapshot = _settled_stream(policy)
    stream = _Stream(
        policy,
        copy.deepcopy(snapshot.participant_resource_budget_states),
        copy.deepcopy(snapshot.participant_resource_budget_events),
    )
    assert list(iter_participant_resource_budget_event_violations(stream.states, stream.events)) == []

    mutate(stream)

    violations = list(iter_participant_resource_budget_event_violations(stream.states, stream.events))
    assert any(message in violation for _, violation in violations), violations


@pytest.mark.parametrize("rewrite", ["remove", "rewrite"])
def test_runtime_refuses_a_transition_that_drops_or_rewrites_budget_history(rewrite: str) -> None:
    policy = _policy(_budget_payload())
    previous = _settled_stream(policy)
    following = copy.deepcopy(previous.participant_resource_budget_events)
    event_id = _event_key(policy, "committed", "commit")
    if rewrite == "remove":
        del following[event_id]
    else:
        following[event_id]["measured"] = 0
    candidate = previous.with_entries(dict(previous.entries), participant_resource_budget_events=following)

    diagnostics = participant_runtime_history_transition_diagnostics(previous, candidate)

    assert [(diagnostic.code, diagnostic.message) for diagnostic in diagnostics] == [
        ("runtime.backend-contract-invalid", "participant resource budget events are append-only")
    ]


Mutation = Callable[[list[dict], dict], None]


def _drop_attempt(history: list[dict], reject: dict) -> None:
    history[:] = [event for event in history if event.get("action_instance_id") != reject["operation_id"]]


def _terminal_observations(history: list[dict], reject: dict) -> list[dict]:
    return [
        event["action_result"]
        for event in history
        if event.get("action_instance_id") == reject["operation_id"] and event["event_type"] == "observation_emitted"
    ]


def _set_result(**update: object) -> Mutation:
    def mutate(history: list[dict], reject: dict) -> None:
        for action_result in _terminal_observations(history, reject):
            action_result.update(update)

    return mutate


def _disclose(field_name: str) -> Mutation:
    def mutate(history: list[dict], reject: dict) -> None:
        for action_result in _terminal_observations(history, reject):
            target = action_result["preconditions"][0] if field_name == "support_refs" else action_result
            target[field_name] = [f"{reject['budget_state_ref']} has 0 of 2 actions remaining"]

    return mutate


def _mutated_history(snapshot: RuntimeSnapshot, mutate: Mutation) -> dict:
    (reject,) = _reject_events(snapshot)
    histories = copy.deepcopy(snapshot.participant_behavior_history)
    for history in histories.values():
        mutate(history, reject)
    return histories


def _exhaustion_violations(snapshot: RuntimeSnapshot, histories: dict) -> list[str]:
    return [
        message
        for _, message in iter_participant_resource_exhaustion_violations(
            histories, snapshot.participant_resource_budget_events
        )
    ]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_drop_attempt, "has no governed attempt"),
        (_set_result(failure_class="backend_error"), "SEM-211 resource_exhausted failure class"),
        (_set_result(status="succeeded", failure_class=None), "SEM-211 resource_exhausted failure class"),
        (_disclose("support_refs"), "discloses budget identity"),
        (_disclose("diagnostics"), "discloses budget identity"),
    ],
    ids=["silent-terminal", "uncontrolled-failure-class", "dispatched-success", "support-ref", "diagnostic"],
)
def test_exhaustion_cannot_bypass_controlled_failure_or_disclose_hidden_quota(
    exhausted_run, mutate: Mutation, message: str
) -> None:
    _, result = exhausted_run
    snapshot = result.snapshot
    assert _exhaustion_violations(snapshot, snapshot.participant_behavior_history) == []

    violations = _exhaustion_violations(snapshot, _mutated_history(snapshot, mutate))

    assert any(message in violation for violation in violations), violations


@pytest.mark.parametrize(
    ("precondition_id", "flagged"),
    [(PARTICIPANT_RESOURCE_BUDGET_PRECONDITION_ID, True), ("provider-quota", False)],
    ids=["claims-portable-budget", "discloses-backend-local-limit"],
)
def test_backend_local_limit_cannot_pose_as_portable_budget_exhaustion(
    exhausted_run, precondition_id: str, flagged: bool
) -> None:
    _, result = exhausted_run
    snapshot = result.snapshot
    histories = copy.deepcopy(snapshot.participant_behavior_history)
    rejected_ids = {event["operation_id"] for event in _reject_events(snapshot)}
    action_result = next(
        event["action_result"]
        for history in histories.values()
        for event in history
        if event["event_type"] == "observation_emitted" and event["action_instance_id"] not in rejected_ids
    )
    action_result.update(
        status="rejected",
        failure_class="resource_exhausted",
        preconditions=[
            {
                "precondition_id": precondition_id,
                "precondition_class": "resource",
                "status": "unsatisfied",
                "participant_address": action_result["participant_address"],
                "episode_id": action_result["episode_id"],
                "action_contract_address": action_result["action_contract_address"],
                "observation_point": action_result["observation_point"],
            }
        ],
    )

    violations = _exhaustion_violations(snapshot, histories)

    assert any("backend-local limit cannot be presented" in message for message in violations) is flagged


def test_published_snapshot_conformance_rejects_exhaustion_outside_sem211(exhausted_run) -> None:
    _, result = exhausted_run
    envelope = _snapshot_model(RuntimeSnapshotEnvelope(snapshot=result.snapshot)).model_dump(mode="json")
    mutated = copy.deepcopy(envelope)
    mutated["participant_behavior_history"] = _mutated_history(
        result.snapshot, _set_result(failure_class="backend_error")
    )

    def exhaustion_messages(payload: dict) -> list[str]:
        return [
            diagnostic.message
            for diagnostic in _semantic_diagnostics("runtime-snapshot-v1", payload)
            if "participant resource exhaustion" in diagnostic.message
        ]

    assert exhaustion_messages(envelope) == []
    assert len(exhaustion_messages(mutated)) == 1


def test_aggregate_counter_cannot_nest_under_a_participant_local_budget() -> None:
    payload = _budget_payload()
    upward = ParticipantAutonomousExecutionPolicyV3.model_validate(_authored_policy(payload)).resource_budget
    chain = [ACTIONS]
    while (parent := upward.dimensions[chain[-1]].parent_budget_ref) is not None:
        chain.append(str(parent))
    assert [upward.owners[upward.dimensions[budget_id].owner_ref].kind.value for budget_id in chain] == [
        "participant",
        "deployment_tenant",
        "fleet",
    ]

    dimensions = _authored_policy(payload)["resource_budget"]["dimensions"]
    dimensions[ACTIONS].update(limit=240)
    dimensions[ACTIONS].pop("parent_budget_ref")
    dimensions["range-actions"].update(limit=24, parent_budget_ref=ACTIONS)
    inverted = _authored_policy(payload)
    with pytest.raises(ValueError, match="participant-owned parent of another owner"):
        ParticipantAutonomousExecutionPolicyV3.model_validate(inverted)

    contract = json.loads(POLICY_FIXTURE.read_text(encoding="utf-8"))
    actions = next(demand for demand in contract["demands"] if demand["budget_id"] == "actions")
    tenant = next(owner for owner in contract["owners"] if owner["kind"] == "deployment_tenant")
    contract["demands"].append(
        {**actions, "budget_id": "range-actions", "owner": tenant, "pool_ref": "range-pool", "limit": 12}
        | {"parent_budget_ref": "actions"}
    )
    with pytest.raises(ValueError, match="participant-owned parent of another owner"):
        ParticipantResourceBudgetPolicyModel.model_validate(contract)


@pytest.mark.parametrize("named_in_participant_refs", [True, False], ids=["participant-ref", "role-selected"])
def test_participant_owned_budget_cannot_count_several_participants(named_in_participant_refs: bool) -> None:
    payload = _budget_payload()
    # A copy shares the affiliation, so the green participant_role_refs entry
    # selects it even when participant_refs does not name it.
    payload["agents"]["participant-agent-b"] = copy.deepcopy(payload["agents"]["participant-agent"])
    specification = payload["behavior_specifications"]["participant-behavior"]
    assert specification["participant_role_refs"] == ["green"]
    if named_in_participant_refs:
        specification["participant_refs"].append("participant-agent-b")
    for window in ("work-window", "pause-window"):
        payload["temporal_constraints"][window]["subject_refs"].append("participant-agent-b")

    source = yaml.safe_dump(payload, sort_keys=False)
    with pytest.raises(SDLValidationError) as raised:
        parse_sdl(source)

    assert str(raised.value).splitlines()[1:] == [
        "  Behavior specification 'participant-behavior' resource-budget owner 'green' participant ref "
        "'participant-agent' would count every governed participant's use (participant-agent, participant-agent-b)"
    ]


def test_incompatible_token_meters_never_aggregate_or_admit() -> None:
    payload = _budget_payload()
    dimensions = _authored_policy(payload)["resource_budget"]["dimensions"]
    dimensions["participant-tokens"] = {
        **dimensions["tokens"],
        "owner_ref": "green",
        "pool_ref": "participant-pool",
        "limit": 5000,
        "parent_budget_ref": "tokens",
        "meter_profile_ref": "tokenizer.other/v1",
    }
    mixed_meters = _authored_policy(payload)
    with pytest.raises(ValueError, match="same resource, unit, mode, and meter"):
        ParticipantAutonomousExecutionPolicyV3.model_validate(mixed_meters)

    remetered = _budget_payload({"tokens": {"meter_profile_ref": "tokenizer.other/v1"}})
    runtime_model = _runtime_model(remetered)
    gaps = participant_autonomous_execution_capability_gaps(
        _governed_manifest(), (_compiled_policy(runtime_model),), runtime_model.time_model
    )
    assert any("tokens (inference_tokens) has no exact configured owner/unit/accounting/meter" in gap for gap in gaps)
