"""Compare only overlapping descriptive assertions, without inferring closure."""

from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from .canonical import canonical_json_digest
from .contracts.realization_descriptions import (
    DescriptionFactModel,
    DescriptionProvenanceModel,
    TypedRealizationDescriptionModel,
)
from .realization_structure import (
    RealizationKeyedCollectionConstraint,
    RealizationLiteral,
    RealizationRecordConstraint,
    RealizationSequenceConstraint,
    RecursiveRealizationStructure,
)
from .realization_structure._common import pointer_tokens
from .realization_structure._models import identity_key

Address = tuple[str, ...]


def _node_markers(value: RecursiveRealizationStructure) -> tuple[str, ...]:
    if isinstance(value, RealizationLiteral):
        markers = (canonical_json_digest({"literal_type": type(value.value).__name__, "literal": value.value}),)
    elif isinstance(value, RealizationKeyedCollectionConstraint):
        markers = (
            value.kind,
            canonical_json_digest({"identity_fields": value.identity_fields, "collection_kind": value.collection_kind}),
        )
    else:
        markers = (value.kind,)
    return markers


def _value_children(value: RecursiveRealizationStructure) -> Iterable[tuple[str, RecursiveRealizationStructure]]:
    children: Iterable[tuple[str, RecursiveRealizationStructure]] = ()
    if isinstance(value, RealizationRecordConstraint):
        children = value.fields.items()
    elif isinstance(value, RealizationKeyedCollectionConstraint):
        children = (("@" + identity_key(member.identity), member.constraint) for member in value.members)
    elif isinstance(value, RealizationSequenceConstraint):
        children = ((str(index), child) for index, child in enumerate(value.items))
    return children


def _value_assertions(path: Address, value: RecursiveRealizationStructure) -> Iterator[tuple[Address, str]]:
    for marker in _node_markers(value):
        yield path, marker
    for name, child in _value_children(value):
        yield from _value_assertions((*path, name), child)


@dataclass
class _WindowAssertions:
    markers: dict[Address, set[frozenset[str]]] = field(default_factory=lambda: defaultdict(set))
    absent: set[Address] = field(default_factory=set)

    def add(self, fact: DescriptionFactModel) -> None:
        path = pointer_tokens(fact.subject)
        if fact.state == "known-absent":
            self.absent.add(path)
        else:
            assert fact.value is not None
            local: dict[Address, set[str]] = defaultdict(set)
            for address, marker in _value_assertions(path, fact.value):
                local[address].add(marker)
            for address, markers in local.items():
                self.markers[address].add(frozenset(markers))

    def conflicts(self) -> bool:
        incompatible = any(len(values) > 1 for values in self.markers.values())
        absent_ancestor = any(path[:length] in self.absent for path in self.markers for length in range(len(path) + 1))
        return incompatible or absent_ancestor


def _window_key(source: DescriptionProvenanceModel) -> str:
    return canonical_json_digest(
        {
            "time": source.recorded_at,
            "window": source.window_ref,
            "operation": source.operation_ref.model_dump(mode="json") if source.operation_ref else None,
            "configuration": source.configuration_ref.model_dump(mode="json") if source.configuration_ref else None,
        }
    )


def assertion_conflict(description: TypedRealizationDescriptionModel) -> str | None:
    """Return a conflict category; separate windows never prove a common state."""
    if any(fact.state == "contradictory" for fact in description.facts):
        return "contradictory"
    windows: dict[str, _WindowAssertions] = {}
    for fact in description.facts:
        if fact.state in {"known", "known-absent"}:
            window = _window_key(fact.provenance or description.provenance)
            windows.setdefault(window, _WindowAssertions()).add(fact)
    if any(window.conflicts() for window in windows.values()):
        return "contradictory"
    return "different-windows" if len(windows) > 1 else None
