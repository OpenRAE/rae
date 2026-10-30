"""ADR-117 import-structure helpers that work on plain import data.

`sibling_edge` uses the import-linter `acyclic_siblings` view: an import counts
between the two children of the deepest package that holds both modules.
`cyclic_components` finds the children of each package that reach each other.
`layer_disagreements` compares a `layers` contract with ADR-036 allowances.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from raes_contracts.errors import InvalidInputError

Components = Mapping[str, tuple[tuple[str, ...], ...]]

_INDEPENDENT = "|"
_NON_INDEPENDENT = ":"


@dataclass(frozen=True, order=True)
class SiblingEdge:
    package: str
    importer_child: str
    imported_child: str


@dataclass(frozen=True)
class Layer:
    packages: tuple[str, ...]
    independent: bool


def sibling_edge(importer: str, imported: str) -> SiblingEdge | None:
    """Return the sibling pair of one import, or None when it is not between two siblings."""

    importer_parts = importer.split(".")
    imported_parts = imported.split(".")
    shared = 0
    for left, right in zip(importer_parts, imported_parts, strict=False):
        if left != right:
            break
        shared += 1
    if shared == 0 or shared in (len(importer_parts), len(imported_parts)):
        # Different top-level packages, the same module, or an ancestor and its descendant.
        return None
    package = ".".join(importer_parts[:shared])
    return SiblingEdge(
        package=package,
        importer_child=f"{package}.{importer_parts[shared]}",
        imported_child=f"{package}.{imported_parts[shared]}",
    )


def cyclic_components(imports: Iterable[tuple[str, str]], *, depth: int) -> dict[str, tuple[tuple[str, ...], ...]]:
    """Return, for each package within ``depth``, its components of two or more mutually reachable children."""

    graphs: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for importer, imported in imports:
        edge = sibling_edge(importer, imported)
        if edge is None or edge.package.count(".") > depth:
            continue
        graphs[edge.package][edge.importer_child].add(edge.imported_child)
        graphs[edge.package].setdefault(edge.imported_child, set())
    result: dict[str, tuple[tuple[str, ...], ...]] = {}
    for package in sorted(graphs):
        components = tuple(
            sorted(tuple(sorted(component)) for component in _strong_components(graphs[package]) if len(component) > 1)
        )
        if components:
            result[package] = components
    return result


def is_cyclic_import(imported_pair: tuple[str, str], components: Components) -> bool:
    edge = sibling_edge(*imported_pair)
    if edge is None:
        return False
    return any(
        edge.importer_child in component and edge.imported_child in component
        for component in components.get(edge.package, ())
    )


def parse_layers(entries: Sequence[str]) -> tuple[Layer, ...]:
    """Parse import-linter layer entries; ``|`` marks independent siblings and ``:`` dependent ones."""

    layers: list[Layer] = []
    for entry in entries:
        if _INDEPENDENT in entry and _NON_INDEPENDENT in entry:
            raise InvalidInputError(f"layer {entry!r} mixes independent and non-independent packages")
        delimiter = _NON_INDEPENDENT if _NON_INDEPENDENT in entry else _INDEPENDENT
        packages = tuple(part.strip() for part in entry.split(delimiter))
        if not all(packages):
            raise InvalidInputError(f"layer {entry!r} names an empty package")
        layers.append(Layer(packages, independent=delimiter == _INDEPENDENT))
    return tuple(layers)


def layer_disagreements(layers: Sequence[Layer], allowed: Mapping[str, frozenset[str]]) -> list[str]:
    """Return how the layer order forbids an import that ADR-036 allows without a cycle reason.

    A higher layer may import a lower one. A layer order may forbid an allowed
    import only when ADR-036 also allows the reverse import, because acyclicity
    then requires one direction.
    """

    messages: list[str] = []
    level: dict[str, int] = {}
    layer_of: dict[str, Layer] = {}
    for position, layer in enumerate(layers):
        for package in layer.packages:
            if package in level:
                messages.append(f"layers name {package!r} more than once")
                continue
            if package not in allowed:
                messages.append(f"layers name {package!r}, which is not a package")
            level[package] = position
            layer_of[package] = layer
    messages.extend(f"layers do not name package {package!r}" for package in sorted(allowed) if package not in level)
    if messages:
        return messages
    for importer in sorted(allowed):
        for imported in sorted(allowed[importer]):
            if imported not in level:
                continue
            if level[imported] == level[importer] and layer_of[importer].independent:
                messages.append(
                    f"layers make {importer!r} and {imported!r} independent, "
                    f"but ADR-036 allows {importer!r} to import {imported!r}"
                )
            elif level[imported] < level[importer] and importer not in allowed.get(imported, frozenset()):
                messages.append(
                    f"layers place {imported!r} above {importer!r}, but ADR-036 allows "
                    f"{importer!r} to import {imported!r} and not the reverse"
                )
    return messages


def _strong_components(graph: Mapping[str, set[str]]) -> list[set[str]]:
    """Tarjan's algorithm with an explicit stack, so long chains need no recursion."""

    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[set[str]] = []
    counter = 0
    for root in sorted(graph):
        if root in index:
            continue
        work = [(root, iter(sorted(graph[root])))]
        index[root] = lowlink[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, successors = work[-1]
            advanced = False
            for successor in successors:
                if successor not in index:
                    index[successor] = lowlink[successor] = counter
                    counter += 1
                    stack.append(successor)
                    on_stack.add(successor)
                    work.append((successor, iter(sorted(graph.get(successor, ())))))
                    advanced = True
                    break
                if successor in on_stack:
                    lowlink[node] = min(lowlink[node], index[successor])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
            if lowlink[node] == index[node]:
                component: set[str] = set()
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.add(member)
                    if member == node:
                        break
                components.append(component)
    return components
