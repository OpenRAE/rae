"""Directed-graph mechanics: a cycle check, a stable dependency order and cyclic components (ADR-118).

``graphlib`` gives the cycle check and the dependency order. ``graphlib`` reports
one cycle and no strongly connected components, so :func:`cyclic_components`
keeps an iterative Tarjan traversal. Callers keep graph construction,
normalization, ordering keys and their own refusals.

This module uses only the standard library.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Collection, Hashable, Iterable, Iterator, Mapping
from contextlib import suppress
from graphlib import CycleError, TopologicalSorter
from typing import Any

__all__ = ("cyclic_components", "has_cycle", "stable_topological_order")


def has_cycle[N: Hashable](graph: Mapping[N, Iterable[N]]) -> bool:
    """Report whether a directed graph has a cycle.

    ``graph`` maps each node to its adjacent nodes. Edge direction does not change
    the result, and a node that is only an adjacent node still counts.
    """

    try:
        TopologicalSorter(graph).prepare()
    except CycleError:
        return True
    return False


def stable_topological_order[N: Hashable](graph: Mapping[N, Iterable[N]], *, key: Callable[[N], Any]) -> list[N]:
    """Return every node after its dependencies.

    ``graph`` maps each node to its dependencies, and each dependency must be a
    key. Ready nodes leave in FIFO order: the first ready nodes, and the nodes
    that each departure makes ready, enter the queue in ``key`` order. Nodes that
    a cycle blocks follow in ``key`` order.
    """

    nodes = sorted(graph, key=key)
    sorter: TopologicalSorter[N] = TopologicalSorter()
    for node in nodes:
        sorter.add(node)
    for node in nodes:
        sorter.add(node, *graph[node])
    # A cycle blocks only the nodes that depend on it; get_ready() still releases the others.
    with suppress(CycleError):
        sorter.prepare()
    order: list[N] = []
    ready = deque(sorter.get_ready())
    while ready:
        node = ready.popleft()
        order.append(node)
        sorter.done(node)
        ready.extend(sorter.get_ready())
    if len(order) != len(nodes):
        placed = set(order)
        order.extend(node for node in nodes if node not in placed)
    return order


def cyclic_components[N: Hashable](graph: Mapping[N, Collection[N]], *, key: Callable[[N], Any]) -> list[tuple[N, ...]]:
    """Return each strongly connected component that contains a cycle.

    ``graph`` maps each node to its successors, and each successor must be a key.
    A component counts when it has more than one member or a self-loop. Members
    and components are sorted by ``key``. The traversal uses an explicit stack, so
    a long chain cannot exhaust the interpreter stack.
    """

    index = 0
    indices: dict[N, int] = {}
    lowlinks: dict[N, int] = {}
    stack: list[N] = []
    on_stack: set[N] = set()
    components: list[tuple[N, ...]] = []

    def visit(node: N) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

    def close_component(node: N) -> None:
        component: list[N] = []
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        component = sorted(component, key=key)
        if len(component) > 1 or component[0] in graph[component[0]]:
            components.append(tuple(component))

    def strongconnect(root: N) -> None:
        visit(root)
        frames: list[tuple[N, Iterator[N]]] = [(root, iter(graph[root]))]
        while frames:
            node, successors = frames[-1]
            descended = False
            for successor in successors:
                if successor not in indices:
                    visit(successor)
                    frames.append((successor, iter(graph[successor])))
                    descended = True
                    break
                if successor in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[successor])
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
    return sorted(components, key=lambda component: tuple(key(node) for node in component))
