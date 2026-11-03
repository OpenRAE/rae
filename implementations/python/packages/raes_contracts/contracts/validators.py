"""Shared field validators for contract models: unique values, governed vocabulary terms and concept bindings."""

from __future__ import annotations

from pydantic import BaseModel

from ..controlled_vocabularies import validate_controlled_vocabulary_scope_values
from .base import ContractModel
from .catalogs import authoritative_concept_family_ids


def _scope_is_present(model: ContractModel, scope: str) -> bool:
    current: object = model
    for segment in scope.split("."):
        if not isinstance(current, BaseModel) or segment not in type(current).model_fields:
            return False
        current = getattr(current, segment)
        if current is None:
            return False
    return True


def validate_controlled_vocabulary_terms(scope: str, values: list[str]) -> None:
    if not values:
        return
    validate_controlled_vocabulary_scope_values(scope, values)


def validate_unique_string_values(field_name: str, values: list[str]) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        joined = ", ".join(duplicates)
        raise ValueError(f"{field_name} must not contain duplicate values: {joined}")


def validate_canonical_concept_bindings(model: ContractModel, *, allowed_scopes: frozenset[str]) -> None:
    family_ids = authoritative_concept_family_ids()
    for binding in getattr(model, "concept_bindings", ()):
        if binding.family not in family_ids:
            raise ValueError(f"concept_bindings family '{binding.family}' is not defined in concept-families-v1")
        if binding.scope not in allowed_scopes:
            allowed = ", ".join(sorted(allowed_scopes))
            raise ValueError(
                f"concept_bindings scope '{binding.scope}' is not a governed manifest vocabulary surface; "
                f"allowed scopes: {allowed}"
            )
        if not _scope_is_present(model, binding.scope):
            raise ValueError(
                f"concept_bindings scope '{binding.scope}' does not resolve to a declared field in this manifest"
            )


__all__ = [
    "validate_canonical_concept_bindings",
    "validate_controlled_vocabulary_terms",
    "validate_unique_string_values",
]
