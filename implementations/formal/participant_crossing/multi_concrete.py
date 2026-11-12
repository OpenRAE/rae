"""Independently derived API-423/RUN-319 two-operation kernel, rev1.

Current candidate preparation precedes scoped claim matching. Only fresh
claims prepare and commit a logical result; response replay performs no effect.
"""

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
    gate: str = "unresolved"
    capability: str = "unresolved"
    changed: bool = False


INITIAL = State()


def _environment(state: State) -> list[tuple[str, State]]:
    edges = [("runtime.restart", state)]
    if state.cut == "p0":
        edges.append(("policy.cut.advance", replace(state, cut="p1")))
    for position in range(len(state.ledger) + (len(state.ledger) < 2)):
        fresh = position == len(state.ledger)
        if not fresh:
            completed = state.ledger[position][5] not in ("deny", "unsupported", "unresolved")
            edges.append((f"crossing.status.{'completed' if completed else 'failed'}.{'ab'[position]}", state))
        for item in INPUTS:
            for body in ("original",) if fresh else ("original", "changed"):
                mode = "fresh" if fresh else "retry"
                candidate = replace(
                    state,
                    phase="validating",
                    intent=(position, item, body, mode),
                    decision="none",
                    gate="unresolved",
                    capability="unresolved",
                    changed=False,
                )
                edges.append((f"crossing.request.{mode}.{'ab'[position]}", candidate))
    return edges


def _gating(state: State) -> list[tuple[str, State]]:
    position, item, body, mode = state.intent
    key = "ab"[position]
    if mode == "retry":
        incumbent = state.ledger[position]
        # Independent candidate-context and scoped-store comparison.
        candidate_policy = None if item == "unresolved" else state.cut
        if (item, body, candidate_policy) != incumbent[:3] or state.head != incumbent[3] and state.head != incumbent[4]:
            return [(f"crossing.replay.reject.{key}", _reset(state))]
        reset = _reset(state)
        return [
            (f"crossing.result.{incumbent[5]}.{key}", replace(reset, known=state.known | (1 << position))),
            (f"crossing.outcome.unknown.{key}", reset),
            ("runtime.restart", reset),
        ]
    if item == "unresolved":
        outcome = "unresolved"
    elif state.gate == "deny":
        outcome = "deny"
    elif state.capability != "supported":
        outcome = "unsupported"
    elif item == "transform" or item == "declassify":
        outcome = item
    else:
        outcome = "permit"
    label = outcome if outcome in ("deny", "unsupported", "unresolved") else "permit"
    return [(f"crossing.decision.{label}.{key}", replace(state, phase="preparing-record", decision=outcome))]


def _reset(state: State) -> State:
    return replace(
        state, phase="idle", intent=None, decision="none", gate="unresolved", capability="unresolved", changed=False
    )


def successors(state: State) -> list[tuple[str, State]]:
    if state.phase == "idle":
        return _environment(state)
    position, item, body, mode = state.intent
    key = "ab"[position]
    if state.phase == "validating":
        return [("internal.validate", replace(state, phase="resolving-cut"))]
    if state.phase == "resolving-cut":
        phase = "gating" if item == "unresolved" else "resolving-capability"
        return [("internal.resolve-policy-cut", replace(state, phase=phase))]
    if state.phase == "resolving-capability":
        capability = "unsupported" if item == "unsupported" else "supported"
        denied = item == "forbidden" or item == "declassify" and state.cut == "p0"
        return [
            (
                "internal.resolve-capability",
                replace(state, phase="gating", capability=capability, gate="deny" if denied else "permit"),
            )
        ]
    if state.phase == "gating":
        return _gating(state)
    if state.phase == "preparing-record":
        if state.decision in ("transform", "declassify") and not state.changed:
            return [(f"crossing.{state.decision}.{key}", replace(state, changed=True))]
        return [("internal.prepare-record", replace(state, phase="committing"))]
    if state.phase == "committing":
        if position != len(state.ledger) or mode != "fresh" or position >= 2:
            raise ValueError("invalid concrete fresh claim")
        next_head = state.head if item == "unresolved" else state.head + 1
        entry = (item, body, None if item == "unresolved" else state.cut, state.head, next_head, state.decision)
        phase = "responding" if state.decision in ("deny", "unsupported", "unresolved") else "delivering"
        return [("internal.atomic-commit", replace(state, phase=phase, head=next_head, ledger=state.ledger + (entry,)))]
    if state.phase == "delivering":
        return [(f"crossing.delivery.{key}", replace(state, phase="responding", effects=state.effects + 1))]
    if state.phase == "responding":
        reset = _reset(state)
        return [
            (f"crossing.result.{state.decision}.{key}", replace(reset, known=state.known | (1 << position))),
            (f"crossing.outcome.unknown.{key}", reset),
            ("runtime.restart", reset),
        ]
    raise ValueError("invalid concrete multi-operation phase")


def internal_rank(state: State) -> int:
    return {
        "validating": 6,
        "resolving-cut": 5,
        "resolving-capability": 4,
        "gating": 3,
        "preparing-record": 2,
        "committing": 1,
    }.get(state.phase, 0)


def build(*, max_states: int = 100000) -> Graph:
    """Independent cursor/worklist closure without schedules or depth bounds."""
    queue = [INITIAL]
    ordinals = {INITIAL: 0}
    arcs = set()
    cursor = 0
    while cursor < len(queue):
        for action, successor in sorted(successors(queue[cursor]), key=lambda edge: (edge[0], repr(edge[1]))):
            if successor not in ordinals:
                if len(queue) >= max_states:
                    raise ValueError("concrete resource limit exceeded")
                ordinals[successor] = len(queue)
                queue.append(successor)
            arcs.add((cursor, action, ordinals[successor]))
        cursor += 1
    return Graph(tuple(queue), tuple(sorted(arcs)))
