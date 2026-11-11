"""Shared graph mechanics give the results of the replaced algorithms (issue #1710, ADR-118).

The reference functions below are verbatim copies of the hand-written algorithms that the
shared module replaces, with the planner's ``canonical_resource_identity`` passed as ``key``.
"""

from __future__ import annotations

import itertools
from collections import defaultdict, deque
from collections.abc import Callable, Iterator, Mapping

import pytest
from raes_contracts.graphs import cyclic_components, has_cycle, stable_topological_order

# --- Reference copies of the replaced algorithms ------------------------------------------------------------


def _reference_validator_sort(graph: dict[str, list[str]]) -> list[str] | None:
    in_degree: dict[str, int] = defaultdict(int)
    for node in graph:
        in_degree.setdefault(node, 0)
    for deps in graph.values():
        for dep in deps:
            in_degree[dep] += 1
    queue = deque(n for n, d in in_degree.items() if d == 0)
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for dep in graph.get(node, []):
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)
    return order if len(order) == len(in_degree) else None


def _reference_recursive_cycle(graph: Mapping[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("cycle")
        if node in visited:
            return
        visiting.add(node)
        for successor in graph.get(node, ()):
            visit(successor)
        visiting.remove(node)
        visited.add(node)

    try:
        for node in graph:
            visit(node)
    except ValueError:
        return True
    return False


def _reference_planner_order(graph: Mapping[str, tuple[str, ...]], key: Callable[[str], object]) -> list[str]:
    dependents: dict[str, list[str]] = {node: [] for node in graph}
    indegree: dict[str, int] = {node: 0 for node in graph}
    for node, dependencies in graph.items():
        for dependency in dependencies:
            dependents[dependency].append(node)
            indegree[node] += 1
    queue = deque(sorted((node for node, degree in indegree.items() if degree == 0), key=key))
    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for dependent in sorted(dependents[current], key=key):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)
    if len(order) != len(graph):
        order.extend(sorted((node for node in graph if node not in order), key=key))
    return order


def _reference_planner_cycles(graph: Mapping[str, tuple[str, ...]], key: Callable[[str], object]) -> list[tuple]:
    if not graph:
        return []
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    cycles: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

    def close_component(node: str) -> None:
        component: list[str] = []
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        component = sorted(component)
        if len(component) > 1 or component[0] in graph[component[0]]:
            cycles.append(tuple(component))

    def strongconnect(root: str) -> None:
        visit(root)
        frames: list[tuple[str, Iterator[str]]] = [(root, iter(graph[root]))]
        while frames:
            node, dependencies = frames[-1]
            descended = False
            for dependency in dependencies:
                if dependency not in indices:
                    visit(dependency)
                    frames.append((dependency, iter(graph[dependency])))
                    descended = True
                    break
                if dependency in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[dependency])
            if descended:
                continue
            frames.pop()
            if frames:
                parent = frames[-1][0]
                lowlinks[parent] = min(lowlinks[parent], lowlinks[node])
            if lowlinks[node] == indices[node]:
                close_component(node)

    for node in sorted(graph, key=key):
        if node not in indices:
            strongconnect(node)
    return sorted(cycles, key=lambda cycle: tuple(key(node) for node in cycle))


# --- Graph enumeration -------------------------------------------------------------------------------------


def _graphs(nodes: tuple[str, ...], *, self_loops: bool) -> Iterator[dict[str, tuple[str, ...]]]:
    edges = [(source, target) for source in nodes for target in nodes if self_loops or source != target]
    for mask in range(1 << len(edges)):
        graph: dict[str, list[str]] = {node: [] for node in nodes}
        for bit, (source, target) in enumerate(edges):
            if mask >> bit & 1:
                graph[source].append(target)
        yield {node: tuple(targets) for node, targets in graph.items()}


def _all_small_graphs() -> Iterator[dict[str, tuple[str, ...]]]:
    yield from _graphs(("a", "b", "c"), self_loops=True)
    yield from _graphs(("a", "b", "c", "d"), self_loops=False)


def _natural(node: str) -> tuple[str]:
    return (node,)


def _reversed(node: str) -> int:
    return -ord(node)


# --- Cycle check ---------------------------------------------------------------------------------------------


def test_cycle_check_agrees_with_every_replaced_algorithm_on_every_small_graph():
    checked = 0
    for graph in _all_small_graphs():
        lists = {node: list(targets) for node, targets in graph.items()}
        expected = _reference_validator_sort(lists) is None
        assert _reference_recursive_cycle(lists) is expected
        assert has_cycle(lists) is expected
        # Nodes that only appear as edge targets.
        sparse = {node: targets for node, targets in lists.items() if targets}
        assert has_cycle(sparse) is (_reference_validator_sort(sparse) is None)
        # Repeated edges and sets as edge collections.
        doubled = {node: [*targets, *targets] for node, targets in lists.items()}
        assert has_cycle(doubled) is expected
        assert has_cycle({node: set(targets) for node, targets in lists.items()}) is expected
        checked += 1
    assert checked == 512 + 4096


@pytest.mark.parametrize(
    ("graph", "expected"),
    [
        ({}, False),
        ({"a": []}, False),
        ({"a": ["a"]}, True),
        ({"a": ["b"]}, False),
        ({"a": ["b"], "b": ["a"]}, True),
        ({"a": ["b"], "b": ["c"], "c": ["a"]}, True),
        ({"a": ["b", "c"], "b": ["c"], "c": []}, False),
    ],
)
def test_cycle_check_examples(graph, expected):
    assert has_cycle(graph) is expected


def test_cycle_check_survives_a_long_chain():
    chain = {f"n{index}": [f"n{index + 1}"] for index in range(5000)}
    assert has_cycle(chain) is False
    chain["n5000"] = ["n0"]
    assert has_cycle(chain) is True


# --- Dependency order ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("key", [_natural, _reversed], ids=["natural", "reversed"])
def test_dependency_order_agrees_with_the_planner_on_every_small_graph(key):
    for graph in _all_small_graphs():
        assert stable_topological_order(graph, key=key) == _reference_planner_order(graph, key)
        reordered = {node: tuple(reversed(targets)) for node, targets in reversed(graph.items())}
        assert stable_topological_order(reordered, key=key) == _reference_planner_order(reordered, key)
        doubled = {node: (*targets, *targets) for node, targets in graph.items()}
        assert stable_topological_order(doubled, key=key) == _reference_planner_order(doubled, key)


def test_dependency_order_uses_a_fifo_queue_not_a_globally_sorted_heap():
    graph = {"a": (), "c": (), "b": ("a",)}
    # A heap would give a, b, c; the FIFO queue releases b after c, which was ready first.
    assert stable_topological_order(graph, key=_natural) == ["a", "c", "b"]


def test_dependency_order_appends_nodes_on_or_after_a_cycle_in_key_order():
    graph = {"a": ("b",), "b": ("a",), "c": (), "d": ("a",)}
    assert stable_topological_order(graph, key=_natural) == ["c", "a", "b", "d"]
    assert stable_topological_order({"a": ("a",)}, key=_natural) == ["a"]
    assert stable_topological_order({}, key=_natural) == []


def test_dependency_order_survives_a_long_chain():
    chain = {f"n{index:05d}": (f"n{index + 1:05d}",) for index in range(5000)}
    chain["n05000"] = ()
    order = stable_topological_order(chain, key=_natural)
    assert order[0] == "n05000"
    assert order[-1] == "n00000"


# --- Cyclic components ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("key", [_natural, _reversed], ids=["natural", "reversed"])
def test_cyclic_components_agree_with_the_planner_on_every_small_graph(key):
    for graph in _all_small_graphs():
        expected = _reference_planner_cycles(graph, _natural)
        if key is _reversed:
            expected = sorted(
                (tuple(sorted(component, key=key)) for component in expected),
                key=lambda component: tuple(key(node) for node in component),
            )
        assert cyclic_components(graph, key=key) == expected


def test_cyclic_components_keep_self_loops_and_drop_acyclic_members():
    graph = {"a": ("a",), "b": ("c",), "c": ("b",), "d": ("b",)}
    assert cyclic_components(graph, key=_natural) == [("a",), ("b", "c")]
    assert cyclic_components({}, key=_natural) == []


def test_cyclic_components_survive_a_long_chain():
    chain = {f"n{index:05d}": (f"n{index + 1:05d}",) for index in range(5000)}
    chain["n05000"] = ("n00000",)
    components = cyclic_components(chain, key=_natural)
    assert len(components) == 1
    assert len(components[0]) == 5001


def test_planner_mechanics_match_on_permuted_node_names():
    nodes = ("b", "a", "d", "c")
    for permutation in itertools.permutations(nodes):
        graph = {node: (permutation[(index + 1) % 4],) for index, node in enumerate(permutation)}
        assert stable_topological_order(graph, key=_natural) == _reference_planner_order(graph, _natural)
        assert cyclic_components(graph, key=_natural) == _reference_planner_cycles(graph, _natural)
