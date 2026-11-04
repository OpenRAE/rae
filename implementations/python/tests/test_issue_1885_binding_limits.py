"""An explicit finite binding budget changes admission, never checksum meaning."""

import pytest
from raes_contracts.realization_structure import (
    RealizationConstraintLimits,
    normalize_realization_literal,
    realization_constraint_binding,
)


def test_binding_uses_explicit_finite_limits():
    limits = RealizationConstraintLimits(max_nodes=8192, max_members=8192, max_operations=100000)
    value = [{"value": index} for index in range(2500)]
    built = normalize_realization_literal(value, semantic_profile="test/v1", limits=limits)
    assert built.document is not None, built.diagnostics
    with pytest.raises(ValueError, match="bounds"):
        realization_constraint_binding(built.document, value)
    assert realization_constraint_binding(built.document, value, limits=limits).startswith("sha256:")


def test_binding_limit_choice_does_not_change_integrity_digest():
    value = {"exact": True}
    document = normalize_realization_literal(value, semantic_profile="test/v1").document
    assert realization_constraint_binding(document, value) == realization_constraint_binding(
        document, value, limits=RealizationConstraintLimits(max_operations=100000)
    )


def test_binding_refuses_document_and_source_outside_explicit_bounds():
    document = normalize_realization_literal({"exact": True}, semantic_profile="test/v1").document
    with pytest.raises(ValueError, match="bounds"):
        realization_constraint_binding(document, {"exact": True}, limits=RealizationConstraintLimits(max_nodes=1))
    with pytest.raises(ValueError, match="bounds"):
        realization_constraint_binding(document, {"exact": [0] * 10}, limits=RealizationConstraintLimits(max_nodes=5))
