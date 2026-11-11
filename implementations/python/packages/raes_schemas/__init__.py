"""The composition root of the published RAES contract schemas (ADR-121).

``schema_bundle()`` generates every published schema from the models of its
owner package. ``tools/check_generated_schemas.py`` compares the result with
the normative schemas under ``contracts/schemas/`` (ADR-009). Run-time code reads
the published schemas through ``raes_contracts.published_schemas`` instead.
"""

from .bundle import schema_bundle, validate_raes_semantic_invariant_annotations

__all__ = ["schema_bundle", "validate_raes_semantic_invariant_annotations"]
