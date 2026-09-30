"""SEM-230 transition authority, executable refinement rev2.

Derivation: participant-crossing-models.md, Abstract rules. No concrete-stage
dependency or abstraction map is used to construct this graph.
"""

from collections import deque
from dataclasses import dataclass, replace

from raes_contracts.behavioral_relation_profiles import INPUT_CLASSES

from .graph import Graph


@dataclass(frozen=True)
class State:
    phase: str = "idle"
    cut: str = "p0"
    intent: tuple[str, str, str, str] | None = None
    decision: str = "none"
    delivery: str = "none"
    last: tuple[str, str, str] | None = None


INITIAL = State()
_POLICY = {
    "p0": dict(
        zip(
            INPUT_CLASSES,
            ("permit", "transform", "deny", "unsupported", "deny"),
            strict=True,
        )
    ),
    "p1": dict(
        zip(
            INPUT_CLASSES,
            ("permit", "transform", "declassify", "unsupported", "deny"),
            strict=True,
        )
    ),
}


def successors(state: State) -> list[tuple[str, State]]:
    """Exactly the abstract rules; no silent abstract transitions."""
    if state.phase in {"idle", "terminal"}:
        choices = []
        if state.cut == "p0":
            choices.append(("policy.cut.advance", replace(state, cut="p1")))
        if state.last is None:
            for item in INPUT_CLASSES:
                choices.append(
                    (
                        "crossing.request",
                        State(
                            "offered",
                            state.cut,
                            ("request-0", item, state.cut, "fresh"),
                        ),
                    )
                )
        else:
            mode = "same-cut" if state.last[1] == state.cut else "later-cut"
            intent = ("request-0", state.intent[1], state.last[1], mode)
            choices.append(
                (
                    "crossing.request",
                    State("offered", state.cut, intent, last=state.last),
                )
            )
        return choices
    if state.phase == "offered":
        if state.intent[3] == "later-cut":
            decision = state.last[2]
            delivery = (
                "withheld" if decision in {"deny", "unsupported"} else "delivered"
            )
            return [
                (
                    "crossing.replay.reject",
                    replace(
                        state, phase="terminal", decision=decision, delivery=delivery
                    ),
                )
            ]
        decision = state.last[2] if state.last else _POLICY[state.cut][state.intent[1]]
        if decision in {"deny", "unsupported"}:
            return [
                (
                    f"crossing.decision.{decision}",
                    replace(
                        state,
                        phase="terminal",
                        decision=decision,
                        delivery="withheld",
                        last=state.last or ("request-0", state.cut, decision),
                    ),
                )
            ]
        return [
            (
                "crossing.decision.permit",
                replace(
                    state,
                    phase="decided",
                    decision=decision,
                    delivery="pending" if decision == "permit" else "none",
                ),
            )
        ]
    if state.phase == "decided":
        if state.delivery == "none":
            return [(f"crossing.{state.decision}", replace(state, delivery="pending"))]
        return [("crossing.delivery", replace(state, phase="delivery-pending"))]
    if state.phase == "delivery-pending":
        return [
            (
                "crossing.observation",
                replace(
                    state,
                    phase="terminal",
                    delivery="delivered",
                    last=state.last or ("request-0", state.cut, state.decision),
                ),
            )
        ]
    raise ValueError("invalid abstract phase")


def build(*, max_states: int = 4096) -> Graph:
    """Least reachable fixed point, deterministic breadth-first enumeration."""
    states = [INITIAL]
    ordinals = {INITIAL: 0}
    work = deque([INITIAL])
    edges = set()
    while work:
        state = work.popleft()
        for label, target in sorted(
            successors(state), key=lambda edge: (edge[0], repr(edge[1]))
        ):
            if target not in ordinals:
                if len(states) >= max_states:
                    raise ValueError("abstract resource limit exceeded")
                ordinals[target] = len(states)
                states.append(target)
                work.append(target)
            edges.add((ordinals[state], label, ordinals[target]))
    return Graph(tuple(states), tuple(sorted(edges)))
