"""Compare only overlapping descriptive assertions, without inferring closure."""

from collections import defaultdict

from .canonical import canonical_json_digest
from .contracts.realization_descriptions import TypedRealizationDescriptionModel
from .realization_structure import (
    RealizationKeyedCollectionConstraint,
    RealizationLiteral,
    RealizationRecordConstraint,
)
from .realization_structure._common import pointer_tokens
from .realization_structure._models import identity_key


def _value_assertions(path, value):
    if isinstance(value, RealizationLiteral):
        yield path, canonical_json_digest({"literal_type": type(value.value).__name__, "literal": value.value})
        return
    yield path, value.kind
    if isinstance(value, RealizationRecordConstraint):
        children = value.fields.items()
    elif isinstance(value, RealizationKeyedCollectionConstraint):
        yield (
            path,
            canonical_json_digest({"identity_fields": value.identity_fields, "collection_kind": value.collection_kind}),
        )
        children = (("@" + identity_key(member.identity), member.constraint) for member in value.members)
    else:
        children = ((str(index), child) for index, child in enumerate(value.items))
    for name, child in children:
        yield from _value_assertions((*path, name), child)


def assertion_conflict(description: TypedRealizationDescriptionModel) -> str | None:
    """Return a conflict category; separate windows never prove a common state."""
    windows = defaultdict(lambda: defaultdict(set))
    absent = defaultdict(set)
    for fact in description.facts:
        if fact.state == "contradictory":
            return "contradictory"
        if fact.state not in {"known", "known-absent"}:
            continue
        source = fact.provenance or description.provenance
        window = canonical_json_digest(
            {
                "time": source.recorded_at,
                "window": source.window_ref,
                "operation": source.operation_ref.model_dump(mode="json") if source.operation_ref else None,
                "configuration": source.configuration_ref.model_dump(mode="json") if source.configuration_ref else None,
            }
        )
        assertions = windows[window]
        path = pointer_tokens(fact.subject)
        if fact.state == "known-absent":
            absent[window].add(path)
        else:
            # Each fact can assert multiple compatible markers at one node.
            local = defaultdict(set)
            for address, marker in _value_assertions(path, fact.value):
                local[address].add(marker)
            for address, markers in local.items():
                assertions[address].add(frozenset(markers))
    for window, assertions in windows.items():
        if any(len(values) > 1 for values in assertions.values()):
            return "contradictory"
        if any(path[:length] in absent[window] for path in assertions for length in range(len(path) + 1)):
            return "contradictory"
    return "different-windows" if len(windows) > 1 else None
