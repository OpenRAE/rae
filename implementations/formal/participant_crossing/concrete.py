"""Independent API-423/RUN-319 formal crossing kernel, rev2.

Derivation: contract predecessor order and runtime gate/prepare/commit stages.
This is a formal kernel; it does not execute or certify the live runtime.
"""

from dataclasses import dataclass, replace

from raes_contracts.behavioral_relation_profiles import INPUT_CLASSES

from .graph import Graph


@dataclass(frozen=True)
class State:
    phase: str = "idle"
    cut: str = "p0"
    intent: tuple[str, str, str, str] | None = None
    gate: str = "unresolved"
    capability: str = "unresolved"
    decision: str = "none"
    delivery: str = "none"
    head: str = "h0"
    last: tuple[str, str, str] | None = None


INITIAL = State()


def _environment(state: State) -> list[tuple[str, State]]:
    edges = []
    if state.cut == "p0":
        edges.append(("policy.cut.advance", replace(state, cut="p1")))
    inputs = INPUT_CLASSES if state.last is None else (state.intent[1],)
    for item in inputs:
        if state.last is None:
            intent = ("request-0", item, state.cut, "fresh")
        else:
            mode = "same-cut" if state.cut == state.last[1] else "later-cut"
            intent = ("request-0", item, state.last[1], mode)
        edges.append(
            (
                "crossing.request",
                State(
                    "validating", state.cut, intent, head=state.head, last=state.last
                ),
            )
        )
    return edges


def _gating(state: State) -> list[tuple[str, State]]:
    # Independent deny-first gate derivation, not the abstract policy table.
    if state.gate == "deny":
        decision = "deny"
    elif state.capability != "supported":
        decision = "unsupported"
    elif state.intent[1] in {"transform", "declassify"}:
        decision = state.intent[1]
    else:
        decision = "permit"
    refused = decision in {"deny", "unsupported"}
    label = f"crossing.decision.{decision}" if refused else "crossing.decision.permit"
    phase = "terminal" if refused and state.last else "preparing-record"
    delivery = (
        "withheld" if refused else ("pending" if decision == "permit" else "none")
    )
    return [(label, replace(state, phase=phase, decision=decision, delivery=delivery))]


def successors(state: State) -> list[tuple[str, State]]:
    if state.phase in {"idle", "terminal"}:
        return _environment(state)
    if state.phase == "validating":
        return [("internal.validate", replace(state, phase="resolving-cut"))]
    if state.phase == "resolving-cut":
        if state.intent[2] != state.cut:
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
        return [
            (
                "internal.resolve-policy-cut",
                replace(state, phase="resolving-capability"),
            )
        ]
    if state.phase == "resolving-capability":
        capability = "unsupported" if state.intent[1] == "unsupported" else "supported"
        allowed = state.intent[1] != "forbidden" and not (
            state.intent[1] == "declassify" and state.cut == "p0"
        )
        return [
            (
                "internal.resolve-capability",
                replace(
                    state,
                    phase="gating",
                    capability=capability,
                    gate="permit" if allowed else "deny",
                ),
            )
        ]
    if state.phase == "gating":
        return _gating(state)
    if state.phase == "preparing-record":
        if state.decision in {"transform", "declassify"} and state.delivery == "none":
            return [(f"crossing.{state.decision}", replace(state, delivery="pending"))]
        return [("internal.prepare-record", replace(state, phase="committing"))]
    if state.phase == "committing":
        if state.last is None:
            phase = (
                "terminal"
                if state.decision in {"deny", "unsupported"}
                else "committing"
            )
            return [
                (
                    "internal.atomic-commit",
                    replace(
                        state,
                        phase=phase,
                        head="h1",
                        last=("request-0", state.cut, state.decision),
                    ),
                )
            ]
        return [("crossing.delivery", replace(state, phase="delivery-pending"))]
    if state.phase == "delivery-pending":
        return [
            (
                "crossing.observation",
                replace(state, phase="terminal", delivery="delivered"),
            )
        ]
    raise ValueError("invalid concrete phase")


def internal_rank(state: State) -> int:
    if state.phase == "committing":
        return 1 if state.last is None else 0
    return {
        "validating": 6,
        "resolving-cut": 5,
        "resolving-capability": 4,
        "gating": 3,
        "preparing-record": 2,
    }.get(state.phase, 0)


def build(*, max_states: int = 4096) -> Graph:
    """Independently enumerate the kernel worklist until no new state exists."""
    queue = [INITIAL]
    ids = {INITIAL: 0}
    arcs = []
    cursor = 0
    while cursor < len(queue):
        for action, successor in sorted(
            successors(queue[cursor]), key=lambda edge: (edge[0], repr(edge[1]))
        ):
            if successor not in ids:
                if len(queue) >= max_states:
                    raise ValueError("concrete resource limit exceeded")
                ids[successor] = len(queue)
                queue.append(successor)
            arcs.append((cursor, action, ids[successor]))
        cursor += 1
    return Graph(tuple(queue), tuple(sorted(set(arcs))))
