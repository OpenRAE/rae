"""Validate leaf metadata before it becomes executable recursive authority."""

from collections.abc import Mapping

from pydantic import TypeAdapter

from ._build import RealizationConstraintBuildResult, build_failure
from ._common import validate_realization_value
from ._models import (
    RealizationAllOf,
    RealizationConstraintLimits,
    RealizationDelegatedValue,
    RealizationDomainValue,
    RealizationKnowledgeValue,
    RealizationLiteral,
    RealizationOrigin,
    RealizationPresence,
    RealizationRelationStatus,
    RecursiveRealizationStructure,
)

_LEAF_ADAPTER = TypeAdapter(RecursiveRealizationStructure)


def validated_member_presences(
    values: Mapping[str, RealizationPresence],
) -> tuple[dict[str, RealizationPresence], RealizationConstraintBuildResult | None]:
    try:
        return {path: RealizationPresence(value) for path, value in values.items()}, None
    except (TypeError, ValueError):
        return {}, build_failure(RealizationRelationStatus.INVALID, "", "Normalization presence is invalid.")


def is_scalar_constraint(constraint: RecursiveRealizationStructure) -> bool:
    if isinstance(constraint, RealizationAllOf):
        return len(constraint.constraints) <= 256 and all(
            isinstance(
                item, (RealizationDelegatedValue, RealizationDomainValue, RealizationKnowledgeValue, RealizationLiteral)
            )
            for item in constraint.constraints
        )
    return isinstance(
        constraint, (RealizationDelegatedValue, RealizationDomainValue, RealizationKnowledgeValue, RealizationLiteral)
    )


def validated_leaf_override(
    override: RecursiveRealizationStructure,
    origin: RealizationOrigin,
    limits: RealizationConstraintLimits,
) -> tuple[RecursiveRealizationStructure | None, RealizationConstraintBuildResult | None]:
    """Never trust an instance merely because its original constructor ran."""

    admission = validate_realization_value(override, limits=limits, python_carriers=True)
    if not admission.conformant:
        return None, build_failure(admission.status, "", "Leaf metadata exceeds its admitted value bounds.")
    try:
        value = override.model_dump(mode="python", warnings="none")
        value["origin"] = origin
        selected = _LEAF_ADAPTER.validate_python(value)
    except (AttributeError, TypeError, ValueError):
        return None, build_failure(RealizationRelationStatus.INVALID, "", "Leaf metadata is not a valid constraint.")
    return selected, None
