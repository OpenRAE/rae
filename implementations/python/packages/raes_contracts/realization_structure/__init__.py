"""Value-free structural authority and recursive realization constraints.

The legacy subset remains import-compatible while the versioned recursive
contract is split into focused implementation modules behind this public owner.
"""

from ._build import RealizationConstraintBuildResult
from ._common import RealizationRelationResult
from ._compatibility import (
    RealizationCompatibilityResult,
    downgrade_recursive_realization_structure,
    upgrade_legacy_realization_structure,
)
from ._composition import compose_realization_constraints, realization_constraint_refines
from ._evaluation import evaluate_realization_constraint
from ._legacy import (
    ExactRealizationValue,
    OpenRealizationValue,
    RealizationCollection,
    RealizationRecord,
    RealizationStructure,
    realization_member_identity,
    structure_matches,
)
from ._models import (
    DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
    DEFAULT_UNDEFINED_REALIZATION_CLOSURE,
    RealizationAllOf,
    RealizationClosure,
    RealizationClosurePosture,
    RealizationCollectionMember,
    RealizationCollectionProfile,
    RealizationConstraintDocument,
    RealizationConstraintLimits,
    RealizationDefinitionReference,
    RealizationDelegatedValue,
    RealizationDomainValue,
    RealizationGraphReference,
    RealizationIdentityAlias,
    RealizationKeyedCollectionConstraint,
    RealizationKnowledgeValue,
    RealizationLiteral,
    RealizationOrigin,
    RealizationPresence,
    RealizationRecordConstraint,
    RealizationRelationStatus,
    RealizationScope,
    RealizationSequenceConstraint,
    RecursiveRealizationStructure,
)
from ._normalization import normalize_realization_literal
from ._semantic_addresses import canonical_semantic_address, semantic_address_contains

__all__ = [
    "DEFAULT_REALIZATION_CONSTRAINT_LIMITS",
    "DEFAULT_UNDEFINED_REALIZATION_CLOSURE",
    "ExactRealizationValue",
    "OpenRealizationValue",
    "RealizationAllOf",
    "RealizationClosure",
    "RealizationClosurePosture",
    "RealizationCollection",
    "RealizationCollectionMember",
    "RealizationCollectionProfile",
    "RealizationCompatibilityResult",
    "RealizationConstraintBuildResult",
    "RealizationConstraintDocument",
    "RealizationConstraintLimits",
    "RealizationDefinitionReference",
    "RealizationDelegatedValue",
    "RealizationDomainValue",
    "RealizationGraphReference",
    "RealizationIdentityAlias",
    "RealizationKeyedCollectionConstraint",
    "RealizationKnowledgeValue",
    "RealizationLiteral",
    "RealizationOrigin",
    "RealizationPresence",
    "RealizationRecord",
    "RealizationRecordConstraint",
    "RealizationRelationResult",
    "RealizationRelationStatus",
    "RealizationScope",
    "RealizationSequenceConstraint",
    "RealizationStructure",
    "RecursiveRealizationStructure",
    "compose_realization_constraints",
    "canonical_semantic_address",
    "downgrade_recursive_realization_structure",
    "evaluate_realization_constraint",
    "normalize_realization_literal",
    "realization_constraint_refines",
    "semantic_address_contains",
    "realization_member_identity",
    "structure_matches",
    "upgrade_legacy_realization_structure",
]
