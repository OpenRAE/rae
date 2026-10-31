"""Lower mixed authored constraints without copying values into authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError
from raes.explicitness import ExplicitnessClass, ExplicitnessRecord
from raes.scenario import InstantiatedScenario
from raes_contracts.errors import RaesError
from raes_contracts.json_pointer import escape_token
from raes_contracts.realization_structure import (
    ExactRealizationValue,
    OpenRealizationValue,
    RealizationCollection,
    RealizationRecord,
    RealizationStructure,
    realization_member_identity,
)

from ..semantics.realization_concerns import RegisteredRealizationConcern
from .realization_authority_posture import designated_registered_posture
from .realization_concern_explicitness import semantic_explicitness_leaves


class _UnrepresentableAuthority(RaesError):
    """Control signal: an authored value has no supported realization authority form."""


@dataclass
class _StructureCompiler:
    scenario: InstantiatedScenario
    registered: RegisteredRealizationConcern
    records: Mapping[str, ExplicitnessRecord]

    def is_open(self, pointer: str) -> bool:
        return (
            designated_registered_posture(
                self.scenario,
                field_pointer=pointer,
                declaration_name=self.registered.declaration_name,
            ).explicitness
            is ExplicitnessClass.OPEN
        )

    def build(self, value: object, path: str, pointer: str, *, depth: int = 0) -> RealizationStructure:
        if depth > 64:
            raise _UnrepresentableAuthority("realization structure exceeds the supported depth")
        record = self.records.get(path)
        if isinstance(value, dict):
            structure = self.record(value, path, pointer, depth)
        elif isinstance(value, list):
            structure = _sequence_structure(record)
        else:
            structure = _scalar_structure(record)
        return structure

    def record(self, value: dict[str, object], path: str, pointer: str, depth: int) -> RealizationRecord:
        fields = {}
        parent_open = self.is_open(pointer)
        for key, child in value.items():
            source_key = key.removesuffix("_present").removesuffix("_commitment")
            child_path = f"{path}.{source_key}"
            if child_path in self.records:
                fields[key] = self.build(child, child_path, f"{pointer}/{escape_token(source_key)}", depth=depth + 1)
            else:
                child_open = self.is_open(f"{pointer}/{escape_token(source_key)}")
                if parent_open != child_open:
                    fields[key] = (
                        OpenRealizationValue(kind="open") if child_open else ExactRealizationValue(kind="exact")
                    )
        return RealizationRecord(kind="record", fields=fields, additional=parent_open)

    def has_open_descendant(self, pointer: str) -> bool:
        return any(
            designation.field_pointer.startswith(f"{pointer}/") and self.is_open(designation.field_pointer)
            for designation in self.scenario.instantiation_provenance.realization_designations
        )

    def collection(self, source: list[object], pointer: str, root_open: bool) -> RealizationCollection:
        descriptor = self.registered.descriptor
        identity_fields = descriptor.collection_identity_fields
        indices = _authored_member_indices(source, identity_fields)
        try:
            projection = descriptor.project(source)
        except (TypeError, ValueError) as exc:
            # The concern projection refuses a value outside its closed shape (E3).
            raise _UnrepresentableAuthority("keyed concern value violates its projection") from exc
        if not isinstance(projection, list):
            raise _UnrepresentableAuthority("keyed concern must project a collection")
        members = {}
        for item in projection:
            index = indices.get(_member_identity(item, identity_fields))
            if index is None:
                raise _UnrepresentableAuthority("projected member does not resolve to an authored identity")
            digest = realization_member_identity(item, identity_fields)
            if digest is None:
                raise _UnrepresentableAuthority("collection identity is not a concrete scalar tuple")
            members[digest] = self.build(item, f"{self.registered.field_path}[{index}]", f"{pointer}/{index}")
        return RealizationCollection(
            kind="collection", members=members, identity_fields=identity_fields, additional=root_open
        )


def _sequence_structure(record: ExplicitnessRecord | None) -> RealizationStructure:
    # Exact nested sequences retain their projector's comparison semantics.
    if record is not None and record.classification is not ExplicitnessClass.EXACT:
        raise _UnrepresentableAuthority("mixed nested collection has no declared identity policy")
    return ExactRealizationValue(kind="exact")


def _scalar_structure(record: ExplicitnessRecord | None) -> RealizationStructure:
    if record is not None and record.classification is ExplicitnessClass.CONSTRAINED:
        raise _UnrepresentableAuthority("mixed scalar bound has no publication-safe domain")
    if record is not None and record.classification is ExplicitnessClass.OPEN:
        return OpenRealizationValue(kind="open", taxonomy_sentinel=True)
    return ExactRealizationValue(kind="exact")


def _member_identity(record: object, identity_fields: tuple[str, ...]) -> tuple[object, ...]:
    if not isinstance(record, Mapping) or any(key not in record for key in identity_fields):
        raise _UnrepresentableAuthority("keyed concern must contain identified records")
    identity = tuple(record[key] for key in identity_fields)
    if any(isinstance(value, (dict, list)) for value in identity):
        raise _UnrepresentableAuthority("collection identity is not a scalar tuple")
    return identity


def _authored_member_indices(source: list[object], identity_fields: tuple[str, ...]) -> dict[tuple[object, ...], int]:
    indices = {}
    for index, item in enumerate(source):
        raw = item.model_dump(mode="json") if isinstance(item, BaseModel) else item
        identity = _member_identity(raw, identity_fields)
        if identity in indices:
            raise _UnrepresentableAuthority("duplicate authored identity")
        indices[identity] = index
    return indices


def _unkeyed_structure(
    compiler: _StructureCompiler, authored_value: object, root_open: bool
) -> tuple[RealizationStructure | None, bool, bool]:
    leaves = semantic_explicitness_leaves(
        compiler.records,
        field_path=compiler.registered.field_path,
        excluded_fields=compiler.registered.descriptor.explicitness_excluded_fields,
    )
    mixed_open = any(r.classification is ExplicitnessClass.OPEN for r in leaves)
    if mixed_open and not isinstance(authored_value, (list, dict, BaseModel)):
        return OpenRealizationValue(kind="open", taxonomy_sentinel=True), False, root_open
    return None, mixed_open, root_open


def compile_realization_structure(
    scenario: InstantiatedScenario,
    registered: RegisteredRealizationConcern,
    records: Mapping[str, ExplicitnessRecord],
    *,
    authored_value: object,
    field_pointer: str,
) -> tuple[RealizationStructure | None, bool, bool]:
    """Return structural authority, unsupported-demand flag and openness."""

    compiler = _StructureCompiler(scenario, registered, records)
    root_open = compiler.is_open(field_pointer)
    descriptor = registered.descriptor
    identity_fields = descriptor.collection_identity_fields
    record = records.get(registered.field_path)
    nested_open = compiler.has_open_descendant(field_pointer)
    if record is not None and record.classification is ExplicitnessClass.EXACT and not root_open and not nested_open:
        return None, False, False
    if not identity_fields:
        return _unkeyed_structure(compiler, authored_value, root_open)
    return _keyed_structure(compiler, authored_value, field_pointer, root_open=root_open, nested_open=nested_open)


def _keyed_structure(
    compiler: _StructureCompiler,
    authored_value: object,
    field_pointer: str,
    *,
    root_open: bool,
    nested_open: bool,
) -> tuple[RealizationStructure | None, bool, bool]:
    if not (isinstance(authored_value, list) and authored_value):
        return None, False, root_open
    # The structure models refuse a collection beyond their bounds with ValidationError.
    try:
        structure = compiler.collection(authored_value, field_pointer, root_open)
    except _UnrepresentableAuthority, ValidationError:
        return None, True, root_open
    return structure, False, root_open or nested_open
