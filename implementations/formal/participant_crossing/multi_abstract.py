"""Independent SEM-230 authority for the fixed two-operation profile, rev1.

Each ledger entry is (input, body, policy-or-none, decision-head, result-head,
outcome). Its ordinal selects distinct governed key, operation and receipt ids.
"""

from collections import deque
from dataclasses import dataclass, replace

from raes_contracts._participant_crossing_multi_profile import INPUTS

from .graph import Graph


@dataclass(frozen=True)
class State:
    phase: str = "idle"
    cut: str = "p0"
    head: int = 0
    ledger: tuple = ()
    effects: int = 0
    known: int = 0
    intent: tuple[int, str, str, str] | None = None
    decision: str = "none"


INITIAL = State()
_POLICY = {
    "p0": dict(zip(INPUTS, ("permit", "transform", "deny", "unsupported", "deny", "unresolved"), strict=True)),
    "p1": dict(zip(INPUTS, ("permit", "transform", "declassify", "unsupported", "deny", "unresolved"), strict=True)),
}


def _idle(state: State) -> list[tuple[str, State]]:
    choices = [("runtime.restart", state)]
    if state.cut == "p0":
        choices.append(("policy.cut.advance", replace(state, cut="p1")))
    if len(state.ledger) < 2:
        slot = len(state.ledger)
        for item in INPUTS:
            choices.append(
                (
                    f"crossing.request.fresh.{'ab'[slot]}",
                    replace(state, phase="offered", intent=(slot, item, "original", "fresh")),
                )
            )
    for slot, result in enumerate(state.ledger):
        status = "failed" if result[5] in {"deny", "unsupported", "unresolved"} else "completed"
        choices.append((f"crossing.status.{status}.{'ab'[slot]}", state))
        for item in INPUTS:
            for body in ("original", "changed"):
                choices.append(
                    (
                        f"crossing.request.retry.{'ab'[slot]}",
                        replace(state, phase="offered", intent=(slot, item, body, "retry")),
                    )
                )
    return choices


def _record(state: State, *, effect: bool) -> State:
    slot, item, body, _ = state.intent
    head = state.head + (state.decision != "unresolved")
    record = (item, body, None if state.decision == "unresolved" else state.cut, state.head, head, state.decision)
    if slot != len(state.ledger) or slot >= 2:
        raise ValueError("invalid fresh identity")
    return replace(state, phase="responding", head=head, ledger=(*state.ledger, record), effects=state.effects + effect)


def successors(state: State) -> list[tuple[str, State]]:
    if state.phase == "idle":
        return _idle(state)
    slot, item, body, mode = state.intent
    key = "ab"[slot]
    if state.phase == "offered":
        if mode == "retry":
            result = state.ledger[slot]
            exact = (item, body) == result[:2]
            current_policy = result[2] is None or result[2] == state.cut
            same_history = state.head in result[3:5]
            if not (exact and current_policy and same_history):
                return [(f"crossing.replay.reject.{key}", replace(state, phase="idle", intent=None))]
            idle = replace(state, phase="idle", intent=None)
            return [
                (
                    f"crossing.result.{result[5]}.{key}",
                    replace(idle, known=state.known | (1 << slot)),
                ),
                (f"crossing.outcome.unknown.{key}", idle),
                ("runtime.restart", idle),
            ]
        decision = _POLICY[state.cut][item]
        decided = replace(state, decision=decision)
        if decision in {"deny", "unsupported", "unresolved"}:
            return [(f"crossing.decision.{decision}.{key}", _record(decided, effect=False))]
        phase = "delivering" if decision == "permit" else "decided"
        return [(f"crossing.decision.permit.{key}", replace(decided, phase=phase))]
    if state.phase == "decided":
        return [(f"crossing.{state.decision}.{key}", replace(state, phase="delivering"))]
    if state.phase == "delivering":
        return [(f"crossing.delivery.{key}", _record(state, effect=True))]
    if state.phase == "responding":
        idle = replace(state, phase="idle", intent=None, decision="none")
        return [
            (f"crossing.result.{state.decision}.{key}", replace(idle, known=state.known | (1 << slot))),
            (f"crossing.outcome.unknown.{key}", idle),
            ("runtime.restart", idle),
        ]
    raise ValueError("invalid abstract multi-operation phase")


def build(*, max_states: int = 100000) -> Graph:
    """Least reachable fixed point; a resource cap never returns a prefix."""
    states = [INITIAL]
    index = {INITIAL: 0}
    work = deque([INITIAL])
    edges = set()
    while work:
        state = work.popleft()
        for label, target in sorted(successors(state), key=lambda edge: (edge[0], repr(edge[1]))):
            if target not in index:
                if len(states) >= max_states:
                    raise ValueError("abstract resource limit exceeded")
                index[target] = len(states)
                states.append(target)
                work.append(target)
            edges.add((index[state], label, index[target]))
    return Graph(tuple(states), tuple(sorted(edges)))
