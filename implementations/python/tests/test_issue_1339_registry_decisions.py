"""Future runtime registrations require their own explicit eligibility decision."""

from __future__ import annotations

import pytest
from raes._declarations import Declaration, DeclarationIndex
from raes._runtime_service_family_registry import RUNTIME_SERVICE_FAMILIES, RuntimeReferenceChild, RuntimeServiceFamily


def test_a_new_runtime_child_requires_an_explicit_reference_policy() -> None:
    with pytest.raises(TypeError, match="reference_policy"):
        RuntimeReferenceChild("future_records", "record_id")


def test_a_new_runtime_family_requires_an_explicit_reference_policy() -> None:
    with pytest.raises(TypeError, match="reference_policy"):
        RuntimeServiceFamily(
            key="future-family",
            module=RUNTIME_SERVICE_FAMILIES[0].module,
            collection_name="future_records",
            id_field="record_id",
        )


def test_every_existing_family_and_nested_registration_records_its_reference_policy() -> None:
    pending = list(RUNTIME_SERVICE_FAMILIES)
    while pending:
        record = pending.pop()
        assert getattr(record, "reference_policy", None) == "world-resource"
        pending.extend(getattr(record, "child_refs", getattr(record, "children", ())))


def test_direct_special_registration_does_not_bypass_the_new_kind_guard() -> None:
    with pytest.raises(RuntimeError, match="no explicit reference-eligibility decision"):
        DeclarationIndex().add(Declaration(kind="future-kind", address="future.record", model_path="future.record"))
