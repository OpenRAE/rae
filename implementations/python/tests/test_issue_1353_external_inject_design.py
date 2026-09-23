"""Finite EI-01--EI-06 design relation; not a production trigger implementation.

Trusted resolution, authentication, clocks, evidence validation and atomic store
transactions are inputs/assumptions. Tests falsify the projected claim/lifecycle
rules, not real HTTP, backend, persistence, delivery or security behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import permutations, product

import pytest
from raes.parser import parse_sdl
from raes_processor.compiler import compile_runtime_model


@dataclass(frozen=True)
class Request:
    key: str = "k1"
    occurrence: str = "o1"
    actor: str = "researcher"
    run: str = "r1"
    plan: str = "p1"
    inject: str = "release"
    source: str = "artifact:resolved-1"
    input_ref: str = "input:1"
    targets: tuple[str, ...] = ("host:1",)
    expected_head: int = 0
    order: int = 10
    slot: str | None = None


@dataclass(frozen=True)
class Cut:
    """Already resolved live facts, not caller assertions or security checks."""

    authorized: bool = True
    supported: bool = True
    assertion: bool | None = True
    clock_valid: bool = True
    input_valid: bool = True
    ordered: bool = True
    willing: bool = True
    targets: tuple[str, ...] = ("host:1", "host:2")
    capacity: int = 3


@dataclass(frozen=True)
class Record:
    request: Request
    phase: str = "admitted"
    dispatches: int = 0
    outcomes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class State:
    records: tuple[Record, ...] = ()
    history: tuple[tuple[str, str], ...] = ()
    head: int = 0
    last_order: int = 0
    deliveries: tuple[tuple[str, str, str | None], ...] = ()
    delivery_receipts: frozenset[tuple[str, str, str | None]] = frozenset()
    observations: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Evidence:
    request: Request = Request()
    generation: int = 1
    results: tuple[tuple[str, str, str], ...] = (("host:1", "applied", "readback"),)


DEFAULT_CUT = Cut()
DEFAULT_REQUEST = Request()
EMPTY_STATE = State()


def dispatch(state: State, cut: Cut = DEFAULT_CUT, *, commit: bool = True) -> tuple[State, int]:
    if not state.records or state.records[-1].phase != "admitted" or not commit:
        return state, 0
    record = state.records[-1]
    eligible = (
        cut.authorized
        and cut.supported
        and cut.assertion is True
        and cut.clock_valid
        and cut.input_valid
        and cut.willing
        and set(record.request.targets) <= set(cut.targets)
        and len(state.records) <= cut.capacity
    )
    phase = "running" if eligible else "withdrawn"
    return update_record(state, replace(record, phase=phase, dispatches=int(eligible))), int(eligible)


def settle(state: State, evidence: Evidence | None, *, commit: bool = True) -> State:
    if not state.records or state.records[-1].phase != "running" or not commit:
        return state
    record = state.records[-1]
    outcomes = tuple((target, "unknown") for target in record.request.targets)
    if evidence is not None and evidence.request == record.request and evidence.generation == 1:
        reported = [target for target, _, _ in evidence.results]
        if len(reported) == len(set(reported)) and set(reported) <= set(record.request.targets):
            valid = {("applied", "readback"), ("absent", "cessation"), ("unknown", "unresolved")}
            by_target = {
                target: outcome if (outcome, basis) in valid else "unknown"
                for target, outcome, basis in evidence.results
            }
            outcomes = tuple((target, by_target.get(target, "unknown")) for target in record.request.targets)
    values = {outcome for _, outcome in outcomes}
    if "unknown" in values:
        phase = "indeterminate"
    elif values == {"applied"}:
        phase = "effect-applied"
    elif values == {"absent"}:
        phase = "effect-absent"
    else:
        phase = "known-partial"
    return update_record(state, replace(record, phase=phase, outcomes=outcomes))


def update_record(state: State, record: Record) -> State:
    """Projection of an atomic snapshot/outcome/audit transaction."""
    return replace(
        state,
        records=(*state.records[:-1], record),
        head=state.head + 1,
        history=(*state.history, (record.request.occurrence, record.phase)),
    )


def reserve_delivery(
    state: State,
    *,
    result_occurrence: str = "o1",
    binding: str = "briefing",
    control: str | None = None,
    expected_control: str | None = None,
    authorized: bool = True,
) -> tuple[State, str]:
    if not authorized or control != expected_control or not state.records:
        return state, "denied"
    record = state.records[-1]
    if record.phase != "effect-applied" or result_occurrence != record.request.occurrence:
        return state, "denied"
    claim = (result_occurrence, binding, control)
    for previous in state.deliveries:
        if previous == claim:
            return state, "retry"
        if control is not None and (previous[1], previous[2]) == (binding, control):
            return state, "delivery-conflict"
    return replace(state, deliveries=(*state.deliveries, claim)), "reserved"


def delivery_receipt(state: State, claim: tuple[str, str, str | None], basis: str) -> State:
    if claim not in state.deliveries or basis != "sink-ack":
        return state
    return replace(state, delivery_receipts=state.delivery_receipts | {claim})


def composed_success(state: State, required_delivery: tuple[str, str, str | None] | None = None) -> bool:
    return bool(
        state.records
        and state.records[-1].phase == "effect-applied"
        and (
            required_delivery is None
            or (
                required_delivery[0] == state.records[-1].request.occurrence
                and required_delivery in state.delivery_receipts
            )
        )
    )


def admit(state: State, request: Request, cut: Cut = DEFAULT_CUT, *, commit: bool = True) -> tuple[State, str]:
    """One store/run/operation kind; resolver and ordering authority are inputs."""
    if not cut.authorized:
        return state, "unauthorized"
    if type(request.order) is not int or type(request.expected_head) is not int:
        return state, "invalid-coordinates"
    for record in state.records:
        previous = record.request
        if (previous.actor, previous.key) == (request.actor, request.key):
            return state, "retry" if previous == request else "key-conflict"
        if previous.occurrence == request.occurrence:
            return state, "occurrence-conflict"
        if request.slot is not None and previous.slot == request.slot:
            return state, "slot-conflict"
    if not (cut.supported and cut.assertion is True and cut.clock_valid and cut.input_valid and cut.ordered):
        return state, "ineligible"
    if len(state.records) >= cut.capacity:
        return state, "capacity"
    if (request.run, request.plan, request.inject, request.source) != ("r1", "p1", "release", "artifact:resolved-1"):
        return state, "binding"
    if (
        not request.targets
        or len(set(request.targets)) != len(request.targets)
        or not set(request.targets) <= set(cut.targets)
    ):
        return state, "targets"
    if request.expected_head != state.head or request.order <= state.last_order:
        return state, "stale-or-order"
    if not commit:
        return state, "commit-failed"
    return replace(
        state,
        records=(*state.records, Record(request)),
        history=(*state.history, (request.occurrence, "admitted")),
        head=state.head + 1,
        last_order=request.order,
    ), "admitted"


def admitted(request: Request = DEFAULT_REQUEST, state: State = EMPTY_STATE) -> State:
    state, result = admit(state, request)
    assert result == "admitted"
    return state


def test_researcher_claim_needs_no_participant_or_control_occurrence() -> None:
    state, result = admit(State(), Request())
    assert result == "admitted"
    assert state.records == (Record(Request()),)
    assert state.history == (("o1", "admitted"),)


@pytest.mark.parametrize(
    "change",
    [
        {"authorized": False},
        {"supported": False},
        {"assertion": False},
        {"assertion": None},
        {"clock_valid": False},
        {"input_valid": False},
        {"ordered": False},
        {"capacity": 0},
        {"targets": ()},
    ],
)
def test_unresolved_admission_has_no_claim_or_dispatch(change: dict) -> None:
    state, result = admit(State(), Request(), replace(Cut(), **change))
    assert result != "admitted"
    assert state == State()


@pytest.mark.parametrize(
    "change",
    [
        {"run": "r2"},
        {"plan": "p2"},
        {"inject": "missing"},
        {"source": "artifact:floating"},
        {"targets": ()},
        {"targets": ("host:3",)},
        {"targets": ("host:1", "host:1")},
        {"expected_head": 1},
        {"expected_head": False},
        {"order": 0},
        {"order": True},
    ],
)
def test_stale_ambiguous_or_unbound_request_is_not_admitted(change: dict) -> None:
    state, result = admit(State(), replace(Request(), **change))
    assert result != "admitted"
    assert state == State()


def test_retry_uses_original_claim_without_fresh_admission() -> None:
    state = admitted()
    assert admit(state, Request(), Cut(assertion=False, supported=False)) == (state, "retry")
    assert admit(state, Request(), Cut(authorized=False)) == (state, "unauthorized")
    assert admit(state, replace(Request(), input_ref="input:2")) == (state, "key-conflict")
    assert admit(state, replace(Request(), key="k2")) == (state, "occurrence-conflict")
    assert admit(state, replace(Request(), actor="other")) == (state, "occurrence-conflict")


@pytest.mark.parametrize("change", [{"expected_head": False}, {"order": 10.0}])
def test_retry_cannot_coerce_changed_coordinate_types(change: dict) -> None:
    state = admitted()
    assert admit(state, replace(Request(), **change))[1] != "retry"


def test_fresh_repeat_and_schedule_slot_have_independent_identity() -> None:
    first = Request(slot="schedule:1")
    state = admitted(first)
    second = replace(first, key="k2", occurrence="o2", expected_head=1, order=20)
    assert admit(state, second) == (state, "slot-conflict")
    repeated = admitted(replace(second, slot=None), state)
    assert len(repeated.records) == 2
    assert repeated.last_order == 20


def test_ordered_competitors_revalidate_without_rebasing() -> None:
    first = Request()
    second = replace(first, key="scheduled", occurrence="o2", order=20, slot="schedule:1")
    for arrival in permutations((first, second)):
        state = State()
        results = []
        for candidate in sorted(arrival, key=lambda item: item.order):
            state, result = admit(state, candidate)
            results.append(result)
        assert results == ["admitted", "stale-or-order"]
        assert state.records[0].request == first


def test_failed_claim_commit_has_no_visible_state() -> None:
    assert admit(State(), Request(), commit=False) == (State(), "commit-failed")


def test_existing_authoring_compiles_without_participants_or_schedule() -> None:
    scenario = parse_sdl("""name: external-trigger-design
nodes:
  host:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
injects:
  release: {}
events:
  gate:
    injects: [release]
""")
    model = compile_runtime_model(scenario)
    assert not model.diagnostics
    assert not model.agent_specs
    assert not model.participant_behaviors
    assert not model.participant_inject_deliveries
    assert not model.scripts
    assert not model.stories
    assert model.events["orchestration.event.gate"].inject_addresses == ("orchestration.inject.release",)


def running(request: Request = DEFAULT_REQUEST) -> State:
    state, calls = dispatch(admitted(request))
    assert calls == 1
    assert state.records[-1].phase == "running"
    return state


@pytest.mark.parametrize(
    "change",
    [
        {"authorized": False},
        {"assertion": None},
        {"supported": False},
        {"willing": False},
        {"clock_valid": False},
        {"targets": ()},
    ],
)
def test_queued_work_revalidates_and_withdraws_without_dispatch(change: dict) -> None:
    state, calls = dispatch(admitted(), replace(Cut(), **change))
    assert calls == 0
    assert state.records[-1].phase == "withdrawn"
    assert admit(state, Request()) == (state, "retry")


def test_running_intent_must_commit_before_backend_invocation() -> None:
    state = admitted()
    assert dispatch(state, commit=False) == (state, 0)
    active = running()
    assert dispatch(active) == (active, 0)


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    [
        (("applied", "applied"), "effect-applied"),
        (("absent", "absent"), "effect-absent"),
        (("applied", "absent"), "known-partial"),
        (("applied", "unknown"), "indeterminate"),
    ],
)
def test_fanout_retains_per_target_outcomes(outcomes: tuple[str, str], expected: str) -> None:
    request = Request(targets=("host:1", "host:2"))
    basis = {"applied": "readback", "absent": "cessation", "unknown": "unresolved"}
    evidence = Evidence(
        request,
        results=tuple(
            (target, outcome, basis[outcome]) for target, outcome in zip(request.targets, outcomes, strict=True)
        ),
    )
    state = settle(running(request), evidence)
    assert state.records[-1].phase == expected
    assert state.records[-1].outcomes == tuple(zip(request.targets, outcomes, strict=True))


@pytest.mark.parametrize(
    "evidence",
    [
        None,
        Evidence(generation=2),
        Evidence(request=Request(input_ref="changed")),
        Evidence(results=()),
        Evidence(results=(("host:2", "applied", "readback"),)),
        Evidence(results=(("host:1", "applied", "queued"),)),
        Evidence(results=(("host:1", "absent", "cancel-ack"),)),
    ],
)
def test_missing_or_invalid_effect_evidence_stays_indeterminate(evidence: Evidence | None) -> None:
    state = settle(running(), evidence)
    assert state.records[-1].phase == "indeterminate"
    assert state.records[-1].dispatches == 1
    assert dispatch(state) == (state, 0)
    assert admit(state, Request()) == (state, "retry")


def test_crash_after_effect_before_commit_never_replays_and_late_evidence_cannot_rewrite() -> None:
    state = running()
    assert settle(state, Evidence(), commit=False) == state
    uncertain = settle(state, None)
    assert uncertain.records[-1].phase == "indeterminate"
    assert settle(uncertain, Evidence()) == uncertain
    assert dispatch(uncertain) == (uncertain, 0)
    assert admit(uncertain, replace(Request(), key="new")) == (uncertain, "occurrence-conflict")


def test_delivery_reservation_requires_exact_result_and_control_without_refiring() -> None:
    state = settle(running(), Evidence())
    for changes in (
        {"authorized": False},
        {"result_occurrence": "other"},
        {"control": "edge"},
        {"control": "c2", "expected_control": "c1"},
    ):
        rejected, status = reserve_delivery(state, **changes)
        assert rejected == state
        assert status == "denied"
    reserved, status = reserve_delivery(state, control="c1", expected_control="c1")
    assert status == "reserved"
    assert reserved.records == state.records
    assert reserve_delivery(reserved, control="c1", expected_control="c1") == (reserved, "retry")
    # A reservation surviving lost acknowledgment cannot claim actual observation
    # or become available again merely because a client retries it.
    assert reserved.deliveries == (("o1", "briefing", "c1"),)


def test_world_effect_failure_cannot_supply_a_successful_delivery_result() -> None:
    state = settle(running(), None)
    assert reserve_delivery(state) == (state, "denied")


def test_bounded_retry_and_dispatch_sequences_preserve_claims_and_single_invocation() -> None:
    for actions in product(("retry", "changed-key", "dispatch", "lost-result"), repeat=4):
        state = admitted()
        calls = 0
        for action in actions:
            history = state.history
            if action == "retry":
                state, _ = admit(state, Request())
            elif action == "changed-key":
                state, _ = admit(state, Request(key="k2"))
            elif action == "dispatch":
                state, count = dispatch(state)
                calls += count
            else:
                state = settle(state, None)
            assert state.history[: len(history)] == history
            assert len(state.records) == 1
            assert state.records[0].request == Request()
            assert calls <= 1


def test_required_delivery_withholds_composed_success_without_undoing_world_effect() -> None:
    state = settle(running(), Evidence())
    claim = ("o1", "briefing", None)
    assert composed_success(state)
    assert not composed_success(state, claim)
    state, result = reserve_delivery(state)
    assert result == "reserved"
    assert not composed_success(state, claim)
    assert delivery_receipt(state, claim, "queued") == state
    assert delivery_receipt(state, ("o2", "briefing", None), "sink-ack") == state
    delivered = delivery_receipt(state, claim, "sink-ack")
    assert composed_success(delivered, claim)
    assert delivered.records == state.records
    assert not delivered.observations


def test_delivery_pair_cannot_be_reclaimed_by_a_second_world_occurrence() -> None:
    state = settle(running(), Evidence())
    state, _ = reserve_delivery(state, control="c1", expected_control="c1")
    request = Request(key="k2", occurrence="o2", expected_head=state.head, order=20)
    state = admitted(request, state)
    state, _ = dispatch(state)
    state = settle(state, Evidence(request))
    assert reserve_delivery(state, result_occurrence="o2", control="c1", expected_control="c1") == (
        state,
        "delivery-conflict",
    )


def test_old_delivery_receipt_cannot_complete_a_fresh_occurrence() -> None:
    state = settle(running(), Evidence())
    state, _ = reserve_delivery(state)
    claim = ("o1", "briefing", None)
    state = delivery_receipt(state, claim, "sink-ack")
    request = Request(key="k2", occurrence="o2", expected_head=state.head, order=20)
    state, _ = dispatch(admitted(request, state))
    state = settle(state, Evidence(request))
    assert not composed_success(state, claim)
