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

    traversal = _Tarjan(graph, key)
    for node in sorted(graph, key=key):
        if node not in traversal.indices:
            traversal.strongconnect(node)
    return sorted(traversal.components, key=lambda component: tuple(key(node) for node in component))


class _Tarjan[N: Hashable]:
    """State of one iterative Tarjan traversal (Tarjan 1972)."""

    def __init__(self, graph: Mapping[N, Collection[N]], key: Callable[[N], Any]) -> None:
        self.graph = graph
        self.key = key
        self.index = 0
        self.indices: dict[N, int] = {}
        self.lowlinks: dict[N, int] = {}
        self.stack: list[N] = []
        self.on_stack: set[N] = set()
        self.components: list[tuple[N, ...]] = []

    def visit(self, node: N) -> None:
        self.indices[node] = self.index
        self.lowlinks[node] = self.index
        self.index += 1
        self.stack.append(node)
        self.on_stack.add(node)

    def unvisited_successor(self, node: N, successors: Iterator[N]) -> N | None:
        """Advance ``successors`` to the next unvisited node; lower ``node``'s link for each one on the stack."""

        for successor in successors:
            if successor not in self.indices:
                return successor
            if successor in self.on_stack:
                self.lowlinks[node] = min(self.lowlinks[node], self.indices[successor])
        return None

    def strongconnect(self, root: N) -> None:
        self.visit(root)
        frames: list[tuple[N, Iterator[N]]] = [(root, iter(self.graph[root]))]
        while frames:
            node, successors = frames[-1]
            successor = self.unvisited_successor(node, successors)
            if successor is not None:
                self.visit(successor)
                frames.append((successor, iter(self.graph[successor])))
                continue
            frames.pop()
            if frames:
                parent = frames[-1][0]
                self.lowlinks[parent] = min(self.lowlinks[parent], self.lowlinks[node])
            if self.lowlinks[node] == self.indices[node]:
                self.close_component(node)

    def close_component(self, node: N) -> None:
        component: list[N] = []
        while self.stack:
            member = self.stack.pop()
            self.on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        component = sorted(component, key=self.key)
        if len(component) > 1 or component[0] in self.graph[component[0]]:
            self.components.append(tuple(component))
