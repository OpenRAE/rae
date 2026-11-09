"""Integrity binding between safe source projections and recursive authority."""

from ..canonical import canonical_json_digest
from ._common import validate_realization_value
from ._limits import validate_realization_constraint_document
from ._models import (
    DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
    RealizationConstraintDocument,
    RealizationConstraintLimits,
    RealizationRelationStatus,
)


def realization_constraint_binding(
    document: RealizationConstraintDocument,
    source_projection: object,
    *,
    limits: RealizationConstraintLimits = DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
) -> str:
    """Bind both halves of a template; the enclosing plan still requires authentication.

    The source projection can contain delegation markers, not delivered choices.
    This checksum is integrity metadata, never a support or satisfaction claim.
    """

    if not validate_realization_constraint_document(document, limits=limits).conformant:
        raise ValueError("recursive authority exceeds admitted bounds")
    if validate_realization_value(source_projection, limits=limits).status is not RealizationRelationStatus.CONFORMANT:
        raise ValueError("recursive source projection exceeds admitted bounds")
    payload = document.model_dump(mode="json")
    RealizationConstraintDocument.model_validate(payload)
    return canonical_json_digest({"constraint": payload, "source": source_projection})


__all__ = ["realization_constraint_binding"]
