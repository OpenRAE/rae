"""Integrity binding between safe source projections and recursive authority."""

from ..canonical import canonical_json_digest
from ._common import RelationBudget, validate_realization_value
from ._limits import admit_constraint_document
from ._models import DEFAULT_REALIZATION_CONSTRAINT_LIMITS, RealizationConstraintDocument, RealizationRelationStatus


def realization_constraint_binding(document: RealizationConstraintDocument, source_projection: object) -> str:
    """Bind both halves of a template; the enclosing plan still requires authentication.

    The source projection can contain delegation markers, not delivered choices.
    This checksum is integrity metadata, never a support or satisfaction claim.
    """

    if admit_constraint_document(document, RelationBudget(DEFAULT_REALIZATION_CONSTRAINT_LIMITS)) is not None:
        raise ValueError("recursive authority exceeds admitted bounds")
    if validate_realization_value(source_projection).status is not RealizationRelationStatus.CONFORMANT:
        raise ValueError("recursive source projection exceeds admitted bounds")
    payload = document.model_dump(mode="json")
    RealizationConstraintDocument.model_validate(payload)
    return canonical_json_digest({"constraint": payload, "source": source_projection})


__all__ = ["realization_constraint_binding"]
