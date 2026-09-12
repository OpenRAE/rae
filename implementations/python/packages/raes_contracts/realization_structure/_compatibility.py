"""Lossless conversion between legacy and recursive realization contracts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ..diagnostics import Diagnostic
from ._build import RealizationConstraintBuildResult, build_failure
from ._common import (
    RelationBudget,
    actual_identity,
    pointer,
    recursive_diagnostic,
    validate_bounded_value,
)
from ._compatibility_checks import CompatibilityLimit
from ._compatibility_downgrade_helpers import (
    RecursiveDowngrader,
    collection_projection_baseline,
    downgrade_collection_members,
    downgrade_delegated,
    downgrade_literal,
    downgrade_record_fields,
    downgrade_sequence,
    project_collection_closure,
    project_record_closure,
    record_projection_precondition,
)
from ._compatibility_upgrade_leaf import (
    compatibility_closure,
    legacy_metadata_failure,
    upgrade_exact_node,
    upgrade_open_node,
)
from ._legacy import (
    ExactRealizationValue,
    OpenRealizationValue,
    RealizationCollection,
    RealizationRecord,
    RealizationStructure,
    realization_member_identity,
)
from ._limits import admit_constraint_document
from ._models import (
    DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
    RealizationClosure,
    RealizationCollectionMember,
    RealizationConstraintDocument,
    RealizationConstraintLimits,
    RealizationDelegatedValue,
    RealizationKeyedCollectionConstraint,
    RealizationLiteral,
    RealizationOrigin,
    RealizationPresence,
    RealizationRecordConstraint,
    RealizationRelationStatus,
    RealizationSequenceConstraint,
    RecursiveRealizationStructure,
)


@dataclass(frozen=True)
class RealizationCompatibilityResult:
    """Lossless compatibility conversion for the pre-#1203 structure subset."""

    status: RealizationRelationStatus
    structure: RealizationStructure | None = None
    diagnostics: tuple[Diagnostic, ...] = ()


def upgrade_legacy_realization_structure(
    structure: RealizationStructure,
    expected: object,
    *,
    semantic_profile: str,
    limits: RealizationConstraintLimits = DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
) -> RealizationConstraintBuildResult:
    """Lift the existing value-free plan rule into the recursive authority."""

    value_budget = RelationBudget(limits)
    if invalid := validate_bounded_value(expected, (), 0, value_budget):
        return RealizationConstraintBuildResult(invalid.status, diagnostics=invalid.diagnostics)
    budget = RelationBudget(limits)
    root, failure = _upgrade_legacy_node(structure, expected, (), semantic_profile, budget)
    if failure is not None:
        return failure
    assert root is not None
    return RealizationConstraintBuildResult(
        RealizationRelationStatus.CONFORMANT,
        RealizationConstraintDocument(
            semantic_profile=semantic_profile,
            default_closure=RealizationClosure(
                posture="closed",
                universe="legacy-realization-structure/v1",
                profile=semantic_profile,
            ),
            root=root,
        ),
    )


def _upgrade_legacy_node(
    structure: RealizationStructure,
    expected: object,
    path: tuple[str, ...],
    semantic_profile: str,
    budget: RelationBudget,
) -> tuple[RecursiveRealizationStructure | None, RealizationConstraintBuildResult | None]:
    current_pointer = pointer(path)
    node = None
    failure = None
    if exhausted := budget.spend_node(len(path)):
        failure = build_failure(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            current_pointer,
            f"Legacy structure conversion exceeded {exhausted}.",
        )
    if failure is None:
        node, failure = _LEGACY_UPGRADERS[type(structure)](
            structure,
            expected,
            path,
            semantic_profile,
            budget,
        )
    return node, failure


def _upgrade_record_fields(
    structure: RealizationRecord,
    expected: Mapping[str, object],
    path: tuple[str, ...],
    semantic_profile: str,
    budget: RelationBudget,
) -> tuple[dict[str, RecursiveRealizationStructure], RealizationConstraintBuildResult | None]:
    fields: dict[str, RecursiveRealizationStructure] = {}
    failure = None
    for key, child in structure.fields.items():
        if key not in expected:
            failure = build_failure(
                RealizationRelationStatus.UNSUPPORTED,
                pointer((*path, key)),
                "A legacy record child absent from its baseline has no lossless recursive form.",
            )
        else:
            upgraded, failure = _upgrade_legacy_node(
                child,
                expected[key],
                (*path, key),
                semantic_profile,
                budget,
            )
            if failure is None:
                assert upgraded is not None
                fields[key] = upgraded
        if failure is not None:
            break
    return fields, failure


def _upgrade_record_node(
    structure: RealizationStructure,
    expected: object,
    path: tuple[str, ...],
    semantic_profile: str,
    budget: RelationBudget,
) -> tuple[RecursiveRealizationStructure | None, RealizationConstraintBuildResult | None]:
    assert isinstance(structure, RealizationRecord)
    node = None
    failure = _legacy_record_precondition(structure, expected, path, budget)
    if failure is None:
        assert isinstance(expected, Mapping)
        fields, failure = _upgrade_record_fields(structure, expected, path, semantic_profile, budget)
        if failure is None:
            node = RealizationRecordConstraint(
                kind="recursive-record",
                fields=fields,
                closure=compatibility_closure(structure.additional, semantic_profile),
            )
    return node, failure


def _legacy_record_precondition(
    structure: RealizationRecord,
    expected: object,
    path: tuple[str, ...],
    budget: RelationBudget,
) -> RealizationConstraintBuildResult | None:
    failure = None
    if not isinstance(expected, Mapping):
        failure = build_failure(
            RealizationRelationStatus.INVALID,
            pointer(path),
            "Legacy record conversion requires a record baseline.",
        )
    if failure is None:
        failure = legacy_metadata_failure(
            tuple(structure.fields),
            path,
            budget,
            "Legacy record metadata exceeded its configured work limits.",
        )
    if failure is None and any(key.endswith(("_present", "_commitment")) for key in structure.fields):
        failure = build_failure(
            RealizationRelationStatus.UNSUPPORTED,
            pointer(path),
            "Recursive conversion does not reinterpret legacy suffixed field names.",
        )
    if failure is None:
        assert isinstance(expected, Mapping)
        if not structure.additional and set(expected) != set(structure.fields):
            failure = build_failure(
                RealizationRelationStatus.UNSUPPORTED,
                pointer(path),
                "A closed legacy record with unbound baseline fields has no lossless recursive form.",
            )
    return failure


def _upgrade_collection_members(
    structure: RealizationCollection,
    indexed: Mapping[str, object],
    path: tuple[str, ...],
    semantic_profile: str,
    budget: RelationBudget,
) -> tuple[list[RealizationCollectionMember], RealizationConstraintBuildResult | None]:
    members: list[RealizationCollectionMember] = []
    failure = None
    for digest, child in structure.members.items():
        item = indexed[digest]
        identity = actual_identity(item, structure.identity_fields)
        assert identity is not None
        if exhausted := budget.spend_identity():
            failure = build_failure(
                RealizationRelationStatus.LIMIT_EXCEEDED,
                pointer(path),
                f"Legacy collection conversion exceeded {exhausted}.",
            )
        else:
            upgraded, failure = _upgrade_legacy_node(
                child,
                item,
                (*path, f"@{digest}"),
                semantic_profile,
                budget,
            )
            if failure is None:
                assert upgraded is not None
                members.append(RealizationCollectionMember(identity=identity, constraint=upgraded))
        if failure is not None:
            break
    return members, failure


def _upgrade_collection_node(
    structure: RealizationStructure,
    expected: object,
    path: tuple[str, ...],
    semantic_profile: str,
    budget: RelationBudget,
) -> tuple[RecursiveRealizationStructure | None, RealizationConstraintBuildResult | None]:
    assert isinstance(structure, RealizationCollection)
    node = None
    indexed, failure = _legacy_collection_baseline(structure, expected, path, budget)
    if failure is None:
        assert indexed is not None
        members, failure = _upgrade_collection_members(structure, indexed, path, semantic_profile, budget)
        if failure is None:
            node = RealizationKeyedCollectionConstraint(
                kind="keyed-collection",
                collection_kind="legacy-projected-collection",
                identity_fields=structure.identity_fields,
                members=tuple(members),
                closure=compatibility_closure(structure.additional, semantic_profile),
            )
    return node, failure


def _legacy_collection_baseline(
    structure: RealizationCollection,
    expected: object,
    path: tuple[str, ...],
    budget: RelationBudget,
) -> tuple[dict[str, object] | None, RealizationConstraintBuildResult | None]:
    indexed = None
    failure = None
    if not isinstance(expected, list):
        failure = build_failure(
            RealizationRelationStatus.INVALID,
            pointer(path),
            "Legacy collection conversion requires a list baseline.",
        )
    if failure is None:
        failure = legacy_metadata_failure(
            structure.identity_fields,
            path,
            budget,
            "Legacy collection metadata exceeded its configured work limits.",
        )
    if failure is None:
        assert isinstance(expected, list)
        indexed, failure = _budgeted_indexed_collection(expected, structure.identity_fields, path, budget)
    if failure is None and (indexed is None or set(indexed) != set(structure.members)):
        failure = build_failure(
            RealizationRelationStatus.INVALID,
            pointer(path),
            "Legacy collection identities disagree with the baseline.",
        )
    return indexed, failure


LegacyUpgrader = Callable[
    [RealizationStructure, object, tuple[str, ...], str, RelationBudget],
    tuple[RecursiveRealizationStructure | None, RealizationConstraintBuildResult | None],
]

_LEGACY_UPGRADERS: dict[type[object], LegacyUpgrader] = {
    OpenRealizationValue: upgrade_open_node,
    ExactRealizationValue: upgrade_exact_node,
    RealizationRecord: _upgrade_record_node,
    RealizationCollection: _upgrade_collection_node,
}


def downgrade_recursive_realization_structure(
    document: RealizationConstraintDocument,
    expected: object,
    *,
    limits: RealizationConstraintLimits = DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
) -> RealizationCompatibilityResult:
    """Project the recursive authority only when the legacy subset is lossless."""

    budget = RelationBudget(limits)
    result = _downgrade_input_failure(document, expected, limits, budget)
    if result is None:
        result = _attempt_recursive_downgrade(document, expected, budget)
    return result


def _downgrade_input_failure(
    document: RealizationConstraintDocument,
    expected: object,
    limits: RealizationConstraintLimits,
    budget: RelationBudget,
) -> RealizationCompatibilityResult | None:
    failure = None
    if document.scopes or document.definitions:
        diagnostic = recursive_diagnostic(
            "realization.unsupported",
            "",
            "Legacy structure cannot preserve recursive scopes or definitions.",
        )
        failure = RealizationCompatibilityResult(
            RealizationRelationStatus.UNSUPPORTED,
            diagnostics=(diagnostic,),
        )
    if failure is None and (violation := admit_constraint_document(document, budget)):
        failure = _compatibility_failure(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            violation.pointer,
            violation.message,
        )
    value_budget = RelationBudget(limits)
    if failure is None and (invalid := validate_bounded_value(expected, (), 0, value_budget)):
        failure = RealizationCompatibilityResult(invalid.status, diagnostics=invalid.diagnostics)
    return failure


def _attempt_recursive_downgrade(
    document: RealizationConstraintDocument,
    expected: object,
    budget: RelationBudget,
) -> RealizationCompatibilityResult:
    try:
        structure, error = _downgrade_recursive_node(document, document.root, expected, (), budget)
    except CompatibilityLimit as exc:
        result = _compatibility_failure(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            exc.address,
            exc.message,
        )
    else:
        if error is not None:
            diagnostic = recursive_diagnostic("realization.unsupported", pointer(error[0]), error[1])
            result = RealizationCompatibilityResult(
                RealizationRelationStatus.UNSUPPORTED,
                diagnostics=(diagnostic,),
            )
        else:
            result = RealizationCompatibilityResult(RealizationRelationStatus.CONFORMANT, structure)
    return result


def _compatibility_failure(
    status: RealizationRelationStatus,
    address: str,
    message: str,
) -> RealizationCompatibilityResult:
    return RealizationCompatibilityResult(
        status,
        diagnostics=(recursive_diagnostic(f"realization.{status.value}", address, message),),
    )


def _downgrade_recursive_node(
    document: RealizationConstraintDocument,
    node: RecursiveRealizationStructure,
    expected: object,
    path: tuple[str, ...],
    budget: RelationBudget,
) -> tuple[RealizationStructure | None, tuple[tuple[str, ...], str] | None]:
    if exhausted := budget.spend_node(len(path)):
        raise CompatibilityLimit(pointer(path), f"Legacy projection exceeded {exhausted}.")
    result: tuple[RealizationStructure | None, tuple[tuple[str, ...], str] | None]
    if node.presence is not RealizationPresence.REQUIRED or node.origin is not RealizationOrigin.AUTHOR:
        result = (None, (path, "Legacy structure cannot preserve presence or non-author origin."))
    else:
        handler = _RECURSIVE_DOWNGRADERS.get(type(node))
        result = (
            handler(document, node, expected, path, budget)
            if handler is not None
            else (None, (path, "Recursive node kind has no lossless legacy structure representation."))
        )
    return result


def _downgrade_record(
    document: RealizationConstraintDocument,
    node: RealizationRecordConstraint,
    expected: object,
    path: tuple[str, ...],
    budget: RelationBudget,
) -> tuple[RealizationStructure | None, tuple[tuple[str, ...], str] | None]:
    error = record_projection_precondition(node, expected, path)
    structure = None
    fields: dict[str, RealizationStructure] = {}
    if error is None:
        assert isinstance(expected, Mapping)
        fields, error = downgrade_record_fields(_downgrade_recursive_node, document, node, expected, path, budget)
    if error is None:
        assert isinstance(expected, Mapping)
        structure, error = project_record_closure(document, node, expected, fields, path)
    return structure, error


def _downgrade_collection(
    document: RealizationConstraintDocument,
    node: RealizationKeyedCollectionConstraint,
    expected: object,
    path: tuple[str, ...],
    budget: RelationBudget,
) -> tuple[RealizationStructure | None, tuple[tuple[str, ...], str] | None]:
    indexed, error = collection_projection_baseline(node, expected, path, budget)
    structure = None
    members: dict[str, RealizationStructure] = {}
    if error is None:
        assert indexed is not None
        members, error = downgrade_collection_members(
            _downgrade_recursive_node,
            document,
            node,
            indexed,
            path,
            budget,
        )
    if error is None:
        structure, error = project_collection_closure(document, node, members, path)
    return structure, error


_RECURSIVE_DOWNGRADERS: dict[type[object], RecursiveDowngrader] = {
    RealizationDelegatedValue: downgrade_delegated,
    RealizationLiteral: downgrade_literal,
    RealizationSequenceConstraint: downgrade_sequence,
    RealizationRecordConstraint: _downgrade_record,
    RealizationKeyedCollectionConstraint: _downgrade_collection,
}


def _budgeted_indexed_collection(
    value: list[object],
    fields: tuple[str, ...],
    path: tuple[str, ...],
    budget: RelationBudget,
) -> tuple[dict[str, object] | None, RealizationConstraintBuildResult | None]:
    members: dict[str, object] = {}
    for item in value:
        if exhausted := budget.spend_identity():
            return None, build_failure(
                RealizationRelationStatus.LIMIT_EXCEEDED,
                pointer(path),
                f"Legacy collection conversion exceeded {exhausted}.",
            )
        identity = realization_member_identity(item, fields)
        if identity is None or identity in members:
            return None, None
        members[identity] = item
    return members, None
