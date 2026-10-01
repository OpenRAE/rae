"""Finite #1352 design projection, not an API-424 parser or RUN-320 runtime.

K stands for a fully resolved exact context. Scope and support are trusted
inputs; immutable replacement models an atomic store, not a durability proof.
Revision-1 typed result satisfaction comes from the incumbent SEM-235 oracle.
"""

from dataclasses import dataclass, replace
from graphlib import TopologicalSorter

from sem235_modular_control_model import Result, Slot, compose


@dataclass(frozen=True)
class Node:
    slot: Slot
    provider: str = "A"
    sinks: frozenset[str] | None = frozenset({"in"})
    loss: int | None = 0
    allowed_loss: int = 0


@dataclass(frozen=True)
class Obligation:
    identity: str
    sinks: frozenset[str] | None
    slots: tuple[str, ...]


@dataclass(frozen=True)
class Evaluation:
    apparatus: tuple[Node, ...]
    applicable: tuple[str, ...] = ()
    inapplicable: tuple[str, ...] = ()
    required: frozenset[str] = frozenset()
    results: tuple[Result, ...] = ()
    blockers: tuple[str, ...] = ()
    lost: tuple[str, ...] = ()


def evaluate(nodes, obligations, resolve, *, sink="in", cut="K0", incumbent=True):
    by_ref = {node.slot.ref: node for node in nodes}
    if len(by_ref) != len(nodes) or len(nodes) > 16:
        raise ValueError("selection")
    graph = {ref: node.slot.dependencies for ref, node in by_ref.items()}
    if any(dep not in graph for deps in graph.values() for dep in deps):
        raise ValueError("unknown dependency")
    order = tuple(TopologicalSorter(graph).static_order())
    applicable = {ref for ref, node in by_ref.items() if node.sinks is not None and sink in node.sinks}
    required = {
        ref for ref, node in by_ref.items() if node.slot.mandatory and (node.sinks is None or ref in applicable)
    }
    blockers, inapplicable = set(), set()
    for obligation in obligations:
        if obligation.sinks is None:
            blockers.add("applicability:" + obligation.identity)
        elif sink not in obligation.sinks:
            inapplicable.add(obligation.identity)
        else:
            if not obligation.slots or not set(obligation.slots) <= applicable:
                blockers.add("coverage:" + obligation.identity)
            required.update(set(obligation.slots) & by_ref.keys())
    # The graph was admitted before invocation. Required input closure does not
    # change a slot's type: required advice is still advice, never a decision.
    for ref in reversed(order):
        if ref in required:
            required.update(graph[ref])
    selected = applicable | required
    # Optional consumers also need explicit failed predecessor records.
    for ref in reversed(order):
        if ref in selected:
            selected.update(graph[ref])
    results = {}
    for ref in order:
        if ref not in selected:
            continue
        node = by_ref[ref]
        predecessors = tuple(results[dep] for dep in graph[ref])
        status = "resolved"
        if ref not in applicable:
            status = "unknown"
        elif node.loss is None or not 0 <= node.loss <= node.allowed_loss:
            status = "unsupported"
        elif any(not _input_satisfied(result) for result in predecessors):
            status = "missing"
        result = (
            _resolve(node, predecessors, cut, resolve)
            if status == "resolved"
            else Result(ref, node.slot.kind, status=status, cut=cut)
        )
        results[ref] = result
    slots = tuple(replace(by_ref[ref].slot, mandatory=ref in required) for ref in sorted(selected))
    canonical = tuple(results[ref] for ref in sorted(results))
    blockers.update(compose(slots, canonical, cut=cut, incumbent=incumbent))
    lost = tuple(ref for ref in sorted(results) if ref not in required and not _input_satisfied(results[ref]))
    return Evaluation(
        nodes,
        tuple(sorted(applicable)),
        tuple(sorted(inapplicable)),
        frozenset(required),
        canonical,
        tuple(sorted(blockers)),
        lost,
    )


def _input_satisfied(result):
    return result.status == "resolved" and (result.kind != "decision" or result.payload == "permit")


def _resolve(node, predecessors, cut, resolve):
    try:
        result = resolve(node, predecessors, cut)
    except Exception:  # Deliberate per-invocation isolation; no exception value enters evidence.
        return Result(node.slot.ref, node.slot.kind, status="failed", cut=cut)
    if result is None:
        return Result(node.slot.ref, node.slot.kind, status="missing", cut=cut)
    if not isinstance(result, Result) or (result.slot, result.kind) != (node.slot.ref, node.slot.kind):
        return Result(node.slot.ref, node.slot.kind, status="failed", cut=cut)
    if result.cut != cut:
        return Result(node.slot.ref, node.slot.kind, status="stale", cut=cut)
    return result


@dataclass(frozen=True)
class Effect:
    identity: str
    kind: str = "audit"
    target: str = "audit"
    phase: str = "independent"
    predecessors: tuple[str, ...] = ()
    authorized: bool = True
    supported: bool = True
    accepts: frozenset[str] = frozenset({"deny", "withhold", "permit"})


def effect_decision(decisions, effects, *, applied=frozenset(), incumbent=True):
    """Each call is a fresh evaluation; applied contains trusted exact receipts.

    Parent-target decisions in the legacy-shaped input are conservatively
    projected before phase handling. This is not a wire-history migration.
    """
    index = {effect.identity: effect for effect in effects}
    if len(index) != len(effects) or "parent" in index:
        raise ValueError("effect identity")
    graph = {key: set(effect.predecessors) for key, effect in index.items()}
    graph["parent"] = set()
    opinions = set(decisions)
    for effect in effects:
        if effect.target == "parent" and effect.kind in {"permit", "deny", "withhold"}:
            opinions.add(effect.kind)
            continue
        if effect.phase == "predecessor":
            graph["parent"].add(effect.identity)
        elif effect.phase == "subsequent":
            graph[effect.identity].add("parent")
        elif effect.phase != "independent":
            raise ValueError("phase")
    if any(dep not in graph for deps in graph.values() for dep in deps):
        raise ValueError("unknown effect predecessor")
    tuple(TopologicalSorter(graph).static_order())
    decision = "deny" if "deny" in opinions or not incumbent else "withhold" if opinions - {"permit"} else "permit"
    root_decision = decision
    if decision == "permit" and not graph["parent"] <= applied:
        decision = "withhold"
    runnable = []
    for effect in effects:
        if effect.target == "parent" and effect.kind in {"permit", "deny", "withhold"}:
            continue
        if effect.identity in applied or not effect.authorized or not effect.supported:
            continue
        if not graph[effect.identity] <= applied:
            continue
        if effect.phase == "predecessor" and root_decision != "permit":
            continue
        if effect.phase == "subsequent" and decision != "permit":
            continue
        if effect.phase == "independent" and decision not in effect.accepts:
            continue
        runnable.append(effect.identity)
    return decision, tuple(sorted(runnable))


@dataclass(frozen=True)
class State:
    head: int = 0
    cells: tuple[tuple[str, int], ...] = ()
    history: tuple[str, ...] = ()
    intents: tuple[str, ...] = ()


@dataclass(frozen=True)
class Write:
    scope: str
    before: int
    after: int
    on: str = "evaluation"


def commit(state, expected, decision, writes=(), intents=(), *, succeeds=True):
    """Intents are already independently admitted; this function executes none.

    This finite projection rejects multiple writes to a cell; it does not
    model the optional declared serial-state transition extension.
    """
    if state.head != expected:
        return state, "stale"
    cells = dict(state.cells)
    selected = tuple(write for write in writes if write.on == "evaluation" or decision == "permit")
    if len({write.scope for write in selected}) != len(selected):
        return state, "state-conflict"
    if any(write.on not in {"evaluation", "release"} or cells.get(write.scope) != write.before for write in writes):
        return state, "state-conflict"
    if not succeeds:
        return state, "commit-failed"
    cells.update((write.scope, write.after) for write in selected)
    return State(
        state.head + 1, tuple(sorted(cells.items())), (*state.history, decision), (*state.intents, *intents)
    ), "committed"
