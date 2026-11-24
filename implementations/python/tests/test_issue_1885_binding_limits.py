"""An explicit finite binding budget changes admission, never checksum meaning."""

import pytest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.realization_structure import (
    RealizationConstraintLimits,
    RealizationLiteral,
    normalize_realization_literal,
    realization_constraint_binding,
    validate_realization_value,
)
from raes_contracts.runtime_value_limits import PLAN_AUTHORITY_LIMITS


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
    document_limits = RealizationConstraintLimits(max_nodes=1)
    source_limits = RealizationConstraintLimits(max_nodes=5)
    with pytest.raises(ValueError, match="bounds"):
        realization_constraint_binding(document, {"exact": True}, limits=document_limits)
    with pytest.raises(ValueError, match="bounds"):
        realization_constraint_binding(document, {"exact": [0] * 10}, limits=source_limits)


@pytest.mark.parametrize("python_carriers", [False, True])
@pytest.mark.parametrize(
    "leaf, updates, code",
    [
        (float("inf"), {}, "realization.invalid"),
        (object(), {}, "realization.invalid"),
        ("\ud800", {}, "realization.invalid"),
        ("exceeds", {"max_scalar_bytes": 5}, "realization.limit-exceeded"),
        (0, {"max_nodes": 3}, "realization.limit-exceeded"),
    ],
)
def test_value_admission_keeps_escaped_failure_addresses(leaf, updates, code, python_carriers):
    result = validate_realization_value(
        {"a/b": {"~key": [leaf]}},
        limits=PLAN_AUTHORITY_LIMITS.model_copy(update=updates),
        python_carriers=python_carriers,
    )
    assert not result.conformant
    assert result.diagnostics[0].code == code
    assert result.diagnostics[0].address == "/a~1b/~0key/0"


@pytest.mark.parametrize(
    "leaf", [RealizationLiteral(kind="literal", value=0), Diagnostic(code="x", domain="x", address="", message="x")]
)
def test_carrier_member_limits_keep_escaped_failure_addresses(leaf):
    result = validate_realization_value(
        {"a/b": {"~key": [leaf]}},
        limits=PLAN_AUTHORITY_LIMITS.model_copy(update={"max_members": 1}),
        python_carriers=True,
    )
    assert result.diagnostics[0].code == "realization.limit-exceeded"
    assert result.diagnostics[0].address == "/a~1b/~0key/0"
