"""Bounded admission of recursive constraint and metadata inputs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from ._common import RelationBudget, pointer
from ._models import (
    RealizationAllOf,
    RealizationCollectionProfile,
    RealizationConstraintDocument,
    RealizationDefinitionReference,
    RealizationDomainValue,
    RealizationGraphReference,
    RealizationKeyedCollectionConstraint,
    RealizationLiteral,
    RealizationRecordConstraint,
    RealizationScope,
    RealizationSequenceConstraint,
    RecursiveRealizationStructure,
)


@dataclass(frozen=True)
class LimitViolation:
    pointer: str
    message: str


def _spend_operation(
    budget: RelationBudget,
    path: tuple[str, ...],
    activity: str,
) -> LimitViolation | None:
    if exhausted := budget.spend_operation():
        return LimitViolation(pointer(path), f"{activity} exceeded {exhausted}.")
    return None


def _admit_metadata(
    value: object,
    path: tuple[str, ...],
    depth: int,
    budget: RelationBudget,
) -> LimitViolation | None:
    violation = None
    if depth > budget.limits.max_depth:
        violation = LimitViolation(pointer(path), "Constraint metadata exceeded max_depth.")
    elif spent := _spend_operation(budget, path, "Constraint metadata admission"):
        violation = spent
    elif exhausted := budget.spend_scalar(value):
        violation = LimitViolation(pointer(path), f"Constraint metadata exceeded {exhausted}.")
    elif isinstance(value, dict):
        violation = _admit_metadata_mapping(value, path, depth, budget)
    elif isinstance(value, (list, tuple)):
        violation = _admit_metadata_sequence(value, path, depth, budget)
    return violation


def _admit_metadata_mapping(
    value: Mapping[object, object],
    path: tuple[str, ...],
    depth: int,
    budget: RelationBudget,
) -> LimitViolation | None:
    violation = None
    if len(value) > budget.limits.max_members:
        violation = LimitViolation(pointer(path), "Constraint metadata exceeded max_members.")
    else:
        for key, child in value.items():
            violation = _admit_metadata(key, (*path, str(key), "$key"), depth + 1, budget)
            if violation is None:
                violation = _admit_metadata(child, (*path, str(key)), depth + 1, budget)
            if violation is not None:
                break
    return violation


def _admit_metadata_sequence(
    value: Sequence[object],
    path: tuple[str, ...],
    depth: int,
    budget: RelationBudget,
) -> LimitViolation | None:
    violation = None
    if len(value) > budget.limits.max_members:
        violation = LimitViolation(pointer(path), "Constraint metadata exceeded max_members.")
    else:
        for index, child in enumerate(value):
            violation = _admit_metadata(child, (*path, str(index)), depth + 1, budget)
            if violation is not None:
                break
    return violation


def _admit_node(
    node: RecursiveRealizationStructure,
    path: tuple[str, ...],
    depth: int,
    budget: RelationBudget,
) -> LimitViolation | None:
    violation = None
    if exhausted := budget.spend_node(depth):
        violation = LimitViolation(pointer(path), f"Constraint admission exceeded {exhausted}.")
    else:
        violation = _admit_metadata(
            {
                "kind": node.kind,
                "presence": getattr(node.presence, "value", node.presence),
                "origin": getattr(node.origin, "value", node.origin),
            },
            (*path, "$header"),
            0,
            budget,
        )
    if violation is None:
        handler = _NODE_ADMITTERS.get(type(node), _admit_empty_node)
        violation = handler(node, path, depth, budget)
    return violation


def _admit_empty_node(
    _node: RecursiveRealizationStructure,
    _path: tuple[str, ...],
    _depth: int,
    _budget: RelationBudget,
) -> LimitViolation | None:
    return None


def _admit_literal_node(
    node: RecursiveRealizationStructure,
    path: tuple[str, ...],
    _depth: int,
    budget: RelationBudget,
) -> LimitViolation | None:
    assert isinstance(node, RealizationLiteral)
    return _admit_metadata(node.value, (*path, "value"), 0, budget)


def _admit_domain_node(
    node: RecursiveRealizationStructure,
    path: tuple[str, ...],
    _depth: int,
    budget: RelationBudget,
) -> LimitViolation | None:
    assert isinstance(node, (RealizationDomainValue, RealizationGraphReference))
    violation = _admit_metadata(node.domain.model_dump(mode="json"), (*path, "domain"), 0, budget)
    if violation is None and isinstance(node, RealizationGraphReference):
        violation = _admit_metadata(node.cycle_policy, (*path, "cycle_policy"), 0, budget)
    return violation


def _admit_definition_node(
    node: RecursiveRealizationStructure,
    path: tuple[str, ...],
    _depth: int,
    budget: RelationBudget,
) -> LimitViolation | None:
    assert isinstance(node, RealizationDefinitionReference)
    return _admit_metadata(node.target, (*path, "target"), 0, budget)


def _admit_record_node(
    node: RecursiveRealizationStructure,
    path: tuple[str, ...],
    depth: int,
    budget: RelationBudget,
) -> LimitViolation | None:
    assert isinstance(node, RealizationRecordConstraint)
    violation = _admit_metadata(node.closure.model_dump(mode="json"), (*path, "closure"), 0, budget)
    if violation is None and len(node.fields) > budget.limits.max_members:
        violation = LimitViolation(pointer(path), "Constraint record exceeded max_members.")
    if violation is None:
        for key, child in node.fields.items():
            violation = _admit_metadata(key, (*path, key, "$key"), 0, budget)
            if violation is None:
                violation = _admit_node(child, (*path, key), depth + 1, budget)
            if violation is not None:
                break
    return violation


def _admit_keyed_node(
    node: RecursiveRealizationStructure,
    path: tuple[str, ...],
    depth: int,
    budget: RelationBudget,
) -> LimitViolation | None:
    assert isinstance(node, RealizationKeyedCollectionConstraint)
    violation = _admit_keyed_metadata(node, path, budget)
    if violation is None:
        for index, member in enumerate(node.members):
            member_path = (*path, str(index))
            exhausted = budget.spend_identity()
            if exhausted is not None:
                violation = LimitViolation(pointer(member_path), f"Constraint admission exceeded {exhausted}.")
            else:
                violation = _admit_metadata(member.identity, (*member_path, "identity"), 0, budget)
            if violation is None:
                violation = _admit_node(member.constraint, member_path, depth + 1, budget)
            if violation is not None:
                break
    return violation


def _admit_children(
    children: Sequence[RecursiveRealizationStructure],
    path: tuple[str, ...],
    depth: int,
    budget: RelationBudget,
) -> LimitViolation | None:
    violation = None
    if len(children) > budget.limits.max_members:
        violation = LimitViolation(pointer(path), "Constraint children exceeded max_members.")
    else:
        for index, child in enumerate(children):
            violation = _admit_node(child, (*path, str(index)), depth + 1, budget)
            if violation is not None:
                break
    return violation


def _admit_sequence_node(
    node: RecursiveRealizationStructure,
    path: tuple[str, ...],
    depth: int,
    budget: RelationBudget,
) -> LimitViolation | None:
    assert isinstance(node, RealizationSequenceConstraint)
    violation = _admit_metadata(node.closure.model_dump(mode="json"), (*path, "closure"), 0, budget)
    if violation is None:
        violation = _admit_metadata(
            {"min_items": node.min_items, "max_items": node.max_items},
            (*path, "cardinality"),
            0,
            budget,
        )
    if violation is None:
        violation = _admit_children(node.items, path, depth, budget)
    return violation


def _admit_all_of_node(
    node: RecursiveRealizationStructure,
    path: tuple[str, ...],
    depth: int,
    budget: RelationBudget,
) -> LimitViolation | None:
    assert isinstance(node, RealizationAllOf)
    return _admit_children(node.constraints, path, depth, budget)


NodeAdmitter = Callable[
    [RecursiveRealizationStructure, tuple[str, ...], int, RelationBudget],
    LimitViolation | None,
]

_NODE_ADMITTERS: dict[type[object], NodeAdmitter] = {
    RealizationLiteral: _admit_literal_node,
    RealizationDomainValue: _admit_domain_node,
    RealizationGraphReference: _admit_domain_node,
    RealizationDefinitionReference: _admit_definition_node,
    RealizationRecordConstraint: _admit_record_node,
    RealizationKeyedCollectionConstraint: _admit_keyed_node,
    RealizationSequenceConstraint: _admit_sequence_node,
    RealizationAllOf: _admit_all_of_node,
}


def _admit_keyed_metadata(
    node: RealizationKeyedCollectionConstraint,
    path: tuple[str, ...],
    budget: RelationBudget,
) -> LimitViolation | None:
    metadata = {
        "collection_kind": node.collection_kind,
        "identity_fields": node.identity_fields,
        "closure": node.closure.model_dump(mode="json"),
        "min_items": node.min_items,
        "max_items": node.max_items,
    }
    violation = _admit_metadata(metadata, (*path, "$collection"), 0, budget)
    if violation is None and len(node.aliases) > budget.limits.max_members:
        violation = LimitViolation(pointer(path), "Constraint aliases exceeded max_members.")
    if violation is None:
        violation = _admit_aliases(node, path, budget)
    return violation


def _admit_aliases(
    node: RealizationKeyedCollectionConstraint,
    path: tuple[str, ...],
    budget: RelationBudget,
) -> LimitViolation | None:
    violation = None
    for index, alias in enumerate(node.aliases):
        alias_path = (*path, "aliases", str(index))
        exhausted = budget.spend_identity()
        if exhausted is not None:
            violation = LimitViolation(pointer(alias_path), f"Constraint admission exceeded {exhausted}.")
        else:
            violation = _admit_metadata(
                {"identity": alias.identity, "target": alias.target},
                alias_path,
                0,
                budget,
            )
        if violation is not None:
            break
    return violation


def _admit_scopes(
    scopes: Sequence[RealizationScope],
    budget: RelationBudget,
) -> LimitViolation | None:
    violation = None
    if len(scopes) > budget.limits.max_members:
        violation = LimitViolation("/scopes", "Constraint scopes exceeded max_members.")
    else:
        for index, scope in enumerate(scopes):
            violation = _admit_metadata(scope.model_dump(mode="json"), ("scopes", str(index)), 0, budget)
            if violation is not None:
                break
    return violation


def _admit_definitions(
    definitions: Mapping[str, RecursiveRealizationStructure],
    budget: RelationBudget,
) -> LimitViolation | None:
    violation = None
    for name, definition in definitions.items():
        violation = _admit_metadata(name, ("definitions", name, "$key"), 0, budget)
        if violation is None:
            violation = _admit_node(definition, ("definitions", name), 0, budget)
        if violation is not None:
            break
    return violation


def admit_constraint_document(
    document: RealizationConstraintDocument,
    budget: RelationBudget,
) -> LimitViolation | None:
    """Bound every structural and metadata input before a recursive relation."""

    header = {
        "contract_id": document.contract_id,
        "semantic_profile": document.semantic_profile,
        "default_closure": document.default_closure.model_dump(mode="json"),
    }
    violation = _admit_metadata(header, ("$document",), 0, budget)
    if violation is None:
        violation = _admit_scopes(document.scopes, budget)
    if violation is None:
        violation = _admit_node(document.root, ("root",), 0, budget)
    if violation is None:
        violation = _admit_definitions(document.definitions, budget)
    return violation


def _admit_normalization_groups(
    groups: Sequence[Sequence[RealizationScope | RealizationCollectionProfile]],
    budget: RelationBudget,
) -> LimitViolation | None:
    violation = None
    for group_index, group in enumerate(groups):
        for index, item in enumerate(group):
            violation = _admit_metadata(
                item.model_dump(mode="json"),
                ("$metadata", str(group_index), str(index)),
                0,
                budget,
            )
            if violation is not None:
                break
        if violation is not None:
            break
    return violation


def _admit_origins(
    origins: Mapping[str, object],
    budget: RelationBudget,
) -> LimitViolation | None:
    violation = None
    for address, origin in origins.items():
        violation = _admit_metadata(
            {"address": address, "origin": str(origin)},
            ("$metadata", "origins", address),
            0,
            budget,
        )
        if violation is not None:
            break
    return violation


def admit_normalization_metadata(
    scopes: tuple[RealizationScope, ...],
    profiles: tuple[RealizationCollectionProfile, ...],
    origins: Mapping[str, object],
    budget: RelationBudget,
) -> LimitViolation | None:
    """Bound address overlays supplied beside an ordinary literal."""

    violation = None
    if max(len(scopes), len(profiles), len(origins)) > budget.limits.max_members:
        violation = LimitViolation("", "Normalization metadata exceeded max_members.")
    if violation is None:
        violation = _admit_normalization_groups((scopes, profiles), budget)
    if violation is None:
        violation = _admit_origins(origins, budget)
    return violation
