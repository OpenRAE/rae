"""Bounded design falsification for #1351, not the production control evaluator.

The model assumes trusted policy/target resolution, an admitted total order and
an atomic store. It deliberately does not model providers, transport or clocks.
The specification and worked cases state those assumptions and the claim limits.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import permutations, product

import pytest
from raes.participant_behavior_specification import MixedControlTransitionKind as Kind


@dataclass(frozen=True)
class Edge:
    kind: Kind
    source: str
    destination: str
    targets: tuple[str, ...] = ()


EDGES = {
    "take": Edge(Kind.HANDOFF, "A", "B"),
    "return": Edge(Kind.HANDOFF, "B", "A"),
    "propose": Edge(Kind.PROPOSAL, "A", "A"),
    "approve": Edge(Kind.APPROVAL, "B", "B", ("proposal",)),
    "deny": Edge(Kind.DENIAL, "B", "B", ("proposal",)),
    "direct": Edge(Kind.EXTERNAL_DIRECTION, "B", "B", ("proposal", "action", "control")),
    "intervene": Edge(Kind.INTERVENTION, "B", "B", ("action", "control", "attempt")),
}
CONTROLLERS = {"A": "self", "B": "supervisor"}


@dataclass(frozen=True)
class Target:
    kind: str
    identity: str
    revision: int = 1
    episode: str = "e1"
    available_at: int = 0


@dataclass(frozen=True)
class Request:
    key: str
    edge: str
    actor: str
    expected_state: str
    expected_revision: int
    expected_head: int
    order: int
    episode: str = "e1"
    policy: str = "p1"
    scope: frozenset[str] = frozenset({"node"})
    target: Target | None = None
    proposal: str | None = None
    evidence: tuple[str, ...] = ("evidence",)
    completion: str | None = "handoff-completion"


@dataclass(frozen=True)
class Record:
    request: Request
    principal: str
    disposition: str
    state: str
    revision: int
    position: int
    policy: str


@dataclass(frozen=True)
class State:
    episode: str = "e1"
    policy: str = "p1"
    phase: str = "running"
    current: str = "A"
    revision: int = 0
    last_order: int = -1
    history: tuple[Record, ...] = ()
    targets: tuple[Target, ...] = ()
    incumbent_targets: tuple[Target, ...] = ()
    decided: frozenset[Target] = frozenset()
    script: tuple[str, ...] | None = None
    cursor: int = 0
    grant_active: bool = True
    grant_scope: frozenset[str] = frozenset({"node"})
    order_window: tuple[int, int] = (0, 1000)
    clock: tuple[str, int] = ("clock", 0)
    tick: int = 100
    validity_clock: tuple[str, int] = ("clock", 0)
    clock_window: tuple[int, int] = (90, 110)
    history_limit: int = 100
    revision_limit: int = 1_000_000


def request(state: State, key: str, edge: str, **changes: object) -> Request:
    """A candidate at the trusted cut; order is independent of semantic time."""
    candidate = Request(
        key=key,
        edge=edge,
        actor=CONTROLLERS[state.current],
        expected_state=state.current,
        expected_revision=state.revision,
        expected_head=len(state.history),
        order=state.last_order + 10,
        episode=state.episode,
        policy=state.policy,
    )
    return replace(candidate, **changes)


def apply(
    state: State,
    candidate: Request,
    *,
    principal: str = "operator",
    subjects: frozenset[str] = frozenset({"self", "supervisor"}),
    commit: bool = True,
) -> tuple[State, str]:
    """Abstract relation; one target/run/operation kind is fixed by the model."""
    if candidate.actor not in subjects:
        return state, "unauthorized"
    for record in state.history:
        if (record.principal, record.request.key) == (principal, candidate.key):
            disposition = record.disposition if record.request == candidate else "identity-conflict"
            return state, disposition
    if candidate.episode != state.episode:
        return state, "episode"
    if len(state.history) >= state.history_limit:
        return state, "exhausted"
    reason = rejection(state, candidate)
    current, revision = state.current, state.revision
    targets, decided, cursor = state.targets, state.decided, state.cursor
    if reason is None:
        edge = EDGES[candidate.edge]
        current, revision = edge.destination, revision + 1
        if edge.kind is Kind.PROPOSAL:
            targets += (
                Target("proposal", candidate.proposal, episode=state.episode, available_at=len(state.history) + 1),
            )
        position = len(state.history) + 1
        targets += (Target("control", f"event:{position}", position, state.episode, position),)
        if edge.kind in {Kind.APPROVAL, Kind.DENIAL}:
            decided |= {candidate.target}
        if state.script is not None:
            cursor += 1
    if not commit:
        return state, "commit-failed"
    disposition = reason or "accepted"
    record = Record(candidate, principal, disposition, current, revision, len(state.history) + 1, state.policy)
    result = replace(
        state,
        current=current,
        revision=revision,
        last_order=candidate.order if reason is None else state.last_order,
        history=(*state.history, record),
        targets=targets,
        decided=decided,
        cursor=cursor,
    )
    return result, disposition


def rejection(state: State, candidate: Request) -> str | None:
    """A finite projection of MC-03 through MC-08, not a wire validator."""
    edge = EDGES.get(candidate.edge)
    if edge is None:
        return "edge"
    checks = (
        (state.phase == "running", "episode-state"),
        (candidate.policy == state.policy, "policy"),
        (state.revision < state.revision_limit, "exhausted"),
        (
            candidate.expected_state == state.current == edge.source and candidate.expected_revision == state.revision,
            "stale-state",
        ),
        (candidate.expected_head == len(state.history), "stale-head"),
        (candidate.actor == CONTROLLERS[edge.source], "controller"),
        (bool(candidate.scope) and candidate.scope <= state.grant_scope and candidate.scope <= {"node"}, "scope"),
        (state.grant_active, "revoked"),
        (candidate.order > state.last_order, "order"),
        (state.order_window[0] <= candidate.order <= state.order_window[1], "validity"),
        (state.clock == state.validity_clock, "validity"),
        (state.clock_window[0] <= state.tick <= state.clock_window[1], "validity"),
        (bool(candidate.evidence), "evidence"),
        (edge.kind is not Kind.HANDOFF or bool(candidate.completion), "completion"),
    )
    for valid, reason in checks:
        if not valid:
            return reason
    if state.script is not None:
        if state.cursor >= len(state.script):
            return "script-exhausted"
        if state.script[state.cursor] != candidate.edge:
            return "script-step"
    if edge.kind is Kind.PROPOSAL:
        if not candidate.proposal or any(
            target.kind == "proposal" and target.identity == candidate.proposal for target in state.targets
        ):
            return "proposal-identity"
    if edge.targets:
        target = candidate.target
        if target is None or target.kind not in edge.targets or target.episode != state.episode:
            return "target"
        incumbent = tuple(
            item
            for item in state.incumbent_targets
            if item.kind in {"action", "attempt"} and item.available_at <= len(state.history)
        )
        if target not in (*state.targets, *incumbent):
            return "target"
        if target in state.decided:
            return "decided-proposal"
    return None


def deliver(state: State, control: Record, *, position: int, actor: str, episode: str) -> bool:
    """Project only the exact control-application join, not actual delivery."""
    return (
        control in state.history
        and control.position == position
        and control.request.episode == episode == state.episode
        and control.request.actor == actor
        and control.disposition == "accepted"
        and EDGES[control.request.edge].kind in {Kind.EXTERNAL_DIRECTION, Kind.INTERVENTION}
    )


def apply_batch(state: State, candidates: tuple[Request, ...]) -> tuple[State, dict[str, str]]:
    """Candidate group at one cut, before the admitted order is resolved."""
    if len({candidate.order for candidate in candidates}) != len(candidates):
        return state, {candidate.key: "ambiguous-order" for candidate in candidates}
    outcomes = {}
    for candidate in sorted(candidates, key=lambda item: item.order):
        state, outcomes[candidate.key] = apply(state, candidate)
    return state, outcomes


def replay(records: tuple[Record, ...], *, episode: str, policy: str) -> tuple[str, int]:
    """Reconstruct one pinned episode; no dispatch or current-clock validation."""
    current, revision, order = "A", 0, -1
    for position, record in enumerate(records, start=1):
        if record.position != position:
            raise ValueError("history continuity")
        if record.request.episode != episode:
            continue
        if record.policy != policy:
            raise ValueError("pinned policy mismatch")
        if record.disposition == "accepted":
            candidate = record.request
            edge = EDGES[candidate.edge]
            if (
                candidate.policy != policy
                or candidate.expected_state != current
                or edge.source != current
                or candidate.expected_revision != revision
                or candidate.order <= order
            ):
                raise ValueError("accepted continuity")
            current, revision, order = edge.destination, revision + 1, candidate.order
        if (record.state, record.revision) != (current, revision):
            raise ValueError("result continuity")
    return current, revision


def accepted(state: State, key: str, edge: str, **changes: object) -> State:
    result, disposition = apply(state, request(state, key, edge, **changes))
    assert disposition == "accepted"
    return result


def test_same_edges_complete_two_cycles_with_fresh_revisions() -> None:
    state = State()
    for index, edge in enumerate(("take", "return", "take", "return"), start=1):
        state = accepted(state, f"h{index}", edge)
        assert state.revision == index
    assert state.current == "A"
    assert [record.request.edge for record in state.history] == ["take", "return", "take", "return"]
    assert replay(state.history, episode="e1", policy="p1") == ("A", 4)


def test_returning_to_a_state_does_not_revive_a_stale_request() -> None:
    initial = State()
    stale = request(initial, "late", "take")
    state = accepted(accepted(initial, "h1", "take"), "h2", "return")
    result, disposition = apply(state, stale)
    assert disposition == "stale-state"
    assert (result.current, result.revision) == ("A", 2)
    assert result.history[:2] == state.history
    assert len(result.history) == 3
    assert result.last_order == state.last_order


def test_retry_uses_original_receipt_and_preserves_store_key_scope() -> None:
    initial = State()
    first = request(initial, "key", "take")
    state, _ = apply(initial, first)
    state = accepted(state, "return", "return")
    assert apply(state, first) == (state, "accepted")
    assert apply(state, replace(first, order=99)) == (state, "identity-conflict")
    restarted = replace(state, episode="e2", policy="p2", current="A", revision=0, last_order=-1)
    assert apply(restarted, first) == (restarted, "accepted")
    assert apply(restarted, request(restarted, "key", "take")) == (restarted, "identity-conflict")
    assert apply(state, first, subjects=frozenset()) == (state, "unauthorized")


def test_ordered_concurrency_revalidates_without_rebasing() -> None:
    initial = State()
    contenders = (request(initial, "first", "take", order=10), request(initial, "second", "take", order=20))
    # Arrival permutations do not choose the semantic winner: the admitted order does.
    for arrival in permutations(contenders):
        state, outcomes = apply_batch(initial, arrival)
        assert outcomes == {"first": "accepted", "second": "stale-state"}
        assert state.revision == 1


def test_ambiguous_order_has_no_arrival_selected_winner() -> None:
    initial = State()
    contenders = (request(initial, "first", "take", order=10), request(initial, "second", "take", order=10))
    for arrival in permutations(contenders):
        state, outcomes = apply_batch(initial, arrival)
        assert state == initial
        assert outcomes == {"first": "ambiguous-order", "second": "ambiguous-order"}


def test_selected_consumer_coordinate_limit_cannot_wrap() -> None:
    state = replace(State(), revision=1_000_000)
    result, reason = apply(state, request(state, "overflow", "take"))
    assert reason == "exhausted"
    assert result.revision == state.revision


def test_script_rejection_retains_cursor_and_proposal_identity_is_immutable() -> None:
    state = State(script=("propose", "take"))
    state, reason = apply(state, request(state, "wrong-slot", "take"))
    assert reason == "script-step"
    assert state.cursor == 0
    state = accepted(state, "proposal", "propose", proposal="p")
    assert state.cursor == 1
    reusable = replace(state, script=None)
    result, reason = apply(reusable, request(reusable, "duplicate", "propose", proposal="p"))
    assert reason == "proposal-identity"
    assert result.revision == reusable.revision


@pytest.mark.parametrize("target", [Target("action", "p"), Target("proposal", "p", episode="e2")])
def test_target_kind_and_episode_cannot_be_inferred_from_an_identity(target: Target) -> None:
    state = accepted(State(), "p", "propose", proposal="p")
    state = accepted(state, "h", "take")
    state, reason = apply(state, request(state, "approval", "approve", target=target))
    assert reason == "target"
    assert state.revision == 2


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"actor": "supervisor"}, "controller"),
        ({"scope": frozenset({"other-node"})}, "scope"),
        ({"policy": "p2"}, "policy"),
        ({"episode": "e2"}, "episode"),
        ({"evidence": ()}, "evidence"),
        ({"completion": None}, "completion"),
        ({"expected_revision": 9}, "stale-state"),
        ({"expected_head": 9}, "stale-head"),
        ({"order": 2000}, "validity"),
    ],
)
def test_invalid_occurrence_cannot_change_controller_state(changes: dict, reason: str) -> None:
    state = State()
    result, disposition = apply(state, request(state, "bad", "take", **changes))
    assert disposition == reason
    assert (result.current, result.revision) == (state.current, state.revision)
    assert result.targets == ()


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"phase": "initializing"}, "episode-state"),
        ({"phase": "terminated"}, "episode-state"),
        ({"grant_active": False}, "revoked"),
        ({"tick": 111}, "validity"),
        ({"clock": ("clock", 1)}, "validity"),
        ({"clock": ("other", 0)}, "validity"),
        ({"history_limit": 0}, "exhausted"),
    ],
)
def test_trusted_cut_controls_live_eligibility(changes: dict, reason: str) -> None:
    state = replace(State(), **changes)
    result, disposition = apply(state, request(state, "bad", "take"))
    assert disposition == reason
    assert (result.current, result.revision) == (state.current, state.revision)


def test_time_is_not_control_order_and_windows_are_inclusive() -> None:
    for tick, order in product((90, 110), (0, 1000)):
        state = replace(State(), tick=tick)
        assert apply(state, request(state, "valid", "take", order=order))[1] == "accepted"


def test_same_state_proposal_and_decision_have_independent_revisions() -> None:
    state = accepted(State(), "p1", "propose", proposal="proposal-1")
    assert (state.current, state.revision) == ("A", 1)
    proposal = state.targets[0]
    state = accepted(state, "h1", "take")
    state = accepted(state, "a1", "approve", target=proposal)
    assert (state.current, state.revision) == ("B", 3)
    assert proposal.revision == 1
    state = accepted(state, "h2", "return")
    state = accepted(state, "p2", "propose", proposal="proposal-2")
    state = accepted(state, "h3", "take")
    result, reason = apply(state, request(state, "a2", "approve", target=proposal))
    assert reason == "decided-proposal"
    assert result.revision == state.revision
    assert apply(state, request(state, "future", "approve", target=Target("proposal", "future")))[1] == "target"


def test_finite_script_does_not_acquire_a_second_cycle() -> None:
    state = State(script=("take", "return"))
    state = accepted(accepted(state, "h1", "take"), "h2", "return")
    result, reason = apply(state, request(state, "h3", "take"))
    assert reason == "script-exhausted"
    assert result.revision == 2
    assert result.cursor == 2


def test_failed_atomic_commit_produces_no_occurrence_or_receipt() -> None:
    state = State()
    candidate = request(state, "h1", "take")
    assert apply(state, candidate, commit=False) == (state, "commit-failed")
    committed, disposition = apply(state, candidate)
    assert disposition == "accepted"
    assert len(committed.history) == 1
    assert apply(committed, candidate) == (committed, "accepted")


def test_delivery_joins_exact_control_occurrence_and_source_actor() -> None:
    state = accepted(State(), "p1", "propose", proposal="proposal-1")
    target = state.targets[0]
    state = accepted(state, "h1", "take")
    state = accepted(state, "d1", "direct", target=target)
    first = state.history[-1]
    state = accepted(state, "h2", "return")
    state = accepted(state, "h3", "take")
    state = accepted(state, "d2", "direct", target=target)
    second = state.history[-1]
    assert deliver(state, second, position=second.position, actor="supervisor", episode="e1")
    assert not deliver(state, first, position=second.position, actor="supervisor", episode="e1")
    assert not deliver(state, second, position=second.position, actor="self", episode="e1")
    assert not deliver(state, second, position=second.position, actor="supervisor", episode="e2")
    assert not deliver(state, state.history[1], position=2, actor="self", episode="e1")


def test_replay_uses_pinned_policy_and_rejects_tampered_continuity() -> None:
    state = accepted(accepted(State(), "h1", "take"), "h2", "return")
    with pytest.raises(ValueError, match="policy"):
        replay(state.history, episode="e1", policy="p2")
    altered = replace(state.history[1], revision=99)
    with pytest.raises(ValueError, match="continuity"):
        replay((state.history[0], altered), episode="e1", policy="p1")


def test_bounded_cycles_keep_history_prefix_and_revision_invariants() -> None:
    # Exhaust 64 six-attempt patterns. Stale attempts append rejection facts;
    # accepted visits alone advance the control revision and order.
    for choices in product((False, True), repeat=6):
        state = State()
        for index, valid in enumerate(choices):
            edge = "take" if state.current == "A" else "return"
            candidate = request(state, str(index), edge)
            if not valid:
                candidate = replace(candidate, expected_revision=state.revision + 1)
            previous = state
            state, disposition = apply(state, candidate)
            assert state.history[: len(previous.history)] == previous.history
            assert state.revision == previous.revision + int(valid)
            assert (disposition == "accepted") == valid
            assert replay(state.history, episode="e1", policy="p1") == (state.current, state.revision)


@pytest.mark.parametrize(
    ("edge", "kind"),
    [
        ("direct", "proposal"),
        ("direct", "action"),
        ("direct", "control"),
        ("intervene", "action"),
        ("intervene", "control"),
        ("intervene", "attempt"),
    ],
)
def test_each_direction_intervention_target_kind_at_the_exact_cut(edge: str, kind: str) -> None:
    state = accepted(State(), "proposal", "propose", proposal="p")
    state = accepted(state, "handoff", "take")
    if kind == "proposal":
        target = state.targets[0]
    elif kind == "control":
        target = Target("control", "event:2", revision=2, available_at=2)
    else:
        # Trusted action/attempt owner projection, separate from control history.
        target = Target(kind, "incumbent", available_at=2)
        state = replace(state, incumbent_targets=(target,))
    result, disposition = apply(state, request(state, "valid", edge, target=target))
    assert disposition == "accepted"
    assert result.revision == 3
    assert deliver(result, result.history[-1], position=3, actor="supervisor", episode="e1")
    for invalid in (
        replace(target, revision=99),
        replace(target, episode="e2"),
        replace(target, identity="future"),
        replace(target, kind="decision"),
    ):
        result, disposition = apply(state, request(state, "invalid", edge, target=invalid))
        assert disposition == "target"
        assert result.revision == state.revision


def test_future_incumbent_and_rejected_control_cannot_authorize_a_target() -> None:
    state = accepted(State(), "handoff", "take")
    future = Target("action", "future", available_at=99)
    state = replace(state, incumbent_targets=(future,))
    result, reason = apply(state, request(state, "future-direction", "direct", target=future))
    assert reason == "target"
    assert result.revision == 1
    rejected = Target("control", "event:2", revision=2, available_at=2)
    result, reason = apply(result, request(result, "rejected-target", "intervene", target=rejected))
    assert reason == "target"
    assert result.revision == 1


def test_narrow_request_may_use_a_broader_controller_grant() -> None:
    state = replace(State(), grant_scope=frozenset({"node", "other-node"}))
    assert apply(state, request(state, "narrow", "take"))[1] == "accepted"
