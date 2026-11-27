"""Deliberate rev2 faults on copies; the baseline transition authorities stay independent."""

from dataclasses import asdict, dataclass, replace

from . import concrete
from .aut import render_aut
from .export import _validate_graph
from .graph import Graph

Edge = tuple[int, str, int]
CASE_IDS = ("hidden-denial", "hidden-observation", "hidden-divergence", "removed-delivery", "later-cut-replay")


def reachable_states(graph: Graph) -> frozenset[int]:
    reached = {graph.initial}
    while True:
        expanded = reached | {target for source, _, target in graph.edges if source in reached}
        if expanded == reached:
            return frozenset(reached)
        reached = expanded


@dataclass(frozen=True)
class Mutation:
    case_id: str
    selector: dict
    location: int
    removed: tuple[Edge, ...]
    added: tuple[Edge, ...]
    graph: Graph

    @property
    def reachable(self) -> frozenset[int]:
        return reachable_states(self.graph)

    def document(self) -> dict:
        return {
            "case_id": self.case_id,
            "mutation_revision": "rev1",
            "mutated_side": "concrete",
            "selector": self.selector,
            "location": self.location,
            "removed_semantic_edges": [list(edge) for edge in self.removed],
            "added_semantic_edges": [list(edge) for edge in self.added],
            "stored_states": len(self.graph.states),
            "reachable_states": len(self.reachable),
            "expected_dpbranching_bisim": False,
        }


def _location(graph: Graph, selector: dict) -> int:
    matches = [
        index
        for index, state in enumerate(graph.states)
        if all(asdict(state)[key] == value for key, value in selector.items())
    ]
    if len(matches) != 1:
        raise ValueError("mutation selector must identify one state")
    return matches[0]


def validate_delta(baseline: Graph, mutation: Mutation) -> None:
    """Check the declared edit independently of mutation construction."""

    before, after = set(baseline.edges), set(mutation.graph.edges)
    removed, added = set(mutation.removed), set(mutation.added)
    valid = (
        bool(removed or added)
        and removed <= before
        and not added & before
        and len(removed) == len(mutation.removed)
        and len(added) == len(mutation.added)
        and before - removed | added == after
        and after - added | removed == before
        and len(after) == len(mutation.graph.edges)
        and mutation.graph.initial == baseline.initial
        and mutation.graph.states[: len(baseline.states)] == baseline.states
        and len(baseline.states) <= len(mutation.graph.states) <= len(baseline.states) + 2
        and mutation.location in reachable_states(baseline)
        and mutation.location in mutation.reachable
        and mutation.location == _location(baseline, mutation.selector)
        and all(source == mutation.location or source >= len(baseline.states) for source, _, _ in removed | added)
    )
    if not valid:
        raise ValueError("invalid mutation delta")
    render_aut(mutation.graph)


def _mutate(baseline: Graph, case_id: str, phase: str, item: str, label: str) -> Mutation:
    replay = case_id == "later-cut-replay"
    selector = {
        "phase": phase,
        "cut": "p1" if replay else "p0",
        "intent": ("request-0", item, "p0", "later-cut" if replay else "fresh"),
    }
    if case_id == "removed-delivery":
        selector["last"] = ("request-0", "p0", "transform")
    location = _location(baseline, selector)
    matched = [edge for edge in baseline.edges if edge[0] == location and edge[1] == label]
    if len(matched) != 1:
        raise ValueError("mutation requires one enabled edge")
    edge = matched[0]
    removed, added, states = (edge,), (), baseline.states
    if case_id in {"hidden-denial", "hidden-observation"}:
        added = ((location, "internal.validate", edge[2]),)
    elif case_id == "hidden-divergence":
        removed, added = (), ((location, "internal.validate", location),)
    elif replay:
        first = len(states)
        origin = states[location]
        states += (
            replace(origin, phase="fault-replay-permitted", decision="permit", delivery="pending"),
            replace(origin, phase="fault-replay-delivered", decision="permit", delivery="pending"),
        )
        added = (
            (location, "crossing.decision.permit", first),
            (first, "crossing.delivery", first + 1),
            (first + 1, "crossing.observation", edge[2]),
        )
    graph = Graph(states, tuple(sorted(set(baseline.edges) - set(removed) | set(added))), baseline.initial)
    mutation = Mutation(case_id, selector, location, removed, added, graph)
    validate_delta(baseline, mutation)
    return mutation


def build_mutations() -> tuple[Mutation, ...]:
    baseline = concrete.build()
    _validate_graph(baseline, concrete)
    declarations = (
        ("hidden-denial", "gating", "forbidden", "crossing.decision.deny"),
        ("hidden-observation", "delivery-pending", "plain", "crossing.observation"),
        ("hidden-divergence", "resolving-cut", "plain", "internal.resolve-policy-cut"),
        ("removed-delivery", "committing", "transform", "crossing.delivery"),
        ("later-cut-replay", "resolving-cut", "plain", "crossing.replay.reject"),
    )
    return tuple(_mutate(baseline, *declaration) for declaration in declarations)
