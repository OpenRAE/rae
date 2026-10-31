"""Shared JSON-pointer resolution and concept/vocabulary validation helpers."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ..corpus import CONCEPT_AUTHORITY, corpus_family_root
from ..json_pointer import unescape_token
from ..vocabulary import ConceptProvenanceCategory
from .base import ContractModel

if TYPE_CHECKING:
    from .catalogs import ReferenceModelSchemaBindingModel


@lru_cache(maxsize=1)
def _authoritative_concept_family_ids() -> frozenset[str]:
    from .catalogs import ConceptFamilyCatalogModel

    catalog_path = corpus_family_root(CONCEPT_AUTHORITY) / "concept-families-v1.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog = ConceptFamilyCatalogModel.model_validate(payload)
    return frozenset(catalog.families)


@lru_cache(maxsize=1)
def _uco_cyber_concept_family_provenance() -> dict[str, str]:
    """Map each adopted/adapted family whose authority is UCO to its provenance.

    This is the single source of truth for UCO alignment coverage: the
    ``uco-alignment-v1`` catalog must declare exactly these families, so the
    cyber-domain family slice is never hard-coded in a second place.
    """
    from .catalogs import ConceptFamilyCatalogModel

    catalog_path = corpus_family_root(CONCEPT_AUTHORITY) / "concept-families-v1.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog = ConceptFamilyCatalogModel.model_validate(payload)
    return {
        family_id: family.provenance.value
        for family_id, family in catalog.families.items()
        if family.provenance in {ConceptProvenanceCategory.ADOPTED, ConceptProvenanceCategory.ADAPTED}
        and family.authority == "UCO"
    }


@lru_cache(maxsize=1)
def _known_contract_ids() -> frozenset[str]:
    from .bundle import schema_bundle

    return frozenset(schema_bundle())


def _resolve_schema_pointer(schema_root: dict[str, Any], pointer: str) -> dict[str, Any]:
    if not pointer.startswith("#/"):
        raise KeyError(pointer)

    current: object = schema_root
    for raw_segment in pointer[2:].split("/"):
        segment = unescape_token(raw_segment)
        if not isinstance(current, dict) or segment not in current:
            raise KeyError(pointer)
        current = current[segment]

    if not isinstance(current, dict):
        raise KeyError(pointer)
    return current


def _collapse_nullable_optional_schema(schema_node: dict[str, Any]) -> dict[str, Any]:
    """Collapse a nullable-optional ``anyOf`` wrapper to its single non-null branch.

    Pydantic renders an optional reference field (``X | None``) as a two-member
    ``anyOf`` whose branches are the referenced schema and ``{"type": "null"}``.
    Reference-model bindings address the underlying structure, so the resolver
    looks through that wrapper (for example ``nodes.*.runtime``, an optional
    ``RuntimeConfiguration``). Anything that is not exactly this nullable-optional
    shape is returned unchanged, so non-optional and non-reference schemas are
    unaffected.
    """
    any_of = schema_node.get("anyOf")
    if not isinstance(any_of, list) or len(any_of) != 2:
        return schema_node
    non_null = [branch for branch in any_of if not (isinstance(branch, dict) and branch.get("type") == "null")]
    null_branches = [branch for branch in any_of if isinstance(branch, dict) and branch.get("type") == "null"]
    if len(non_null) == 1 and len(null_branches) == 1 and isinstance(non_null[0], dict):
        return non_null[0]
    return schema_node


def _resolve_ref_schema(schema_root: dict[str, Any], schema_node: dict[str, Any]) -> dict[str, Any]:
    current = schema_node
    while True:
        if "$ref" in current:
            ref = current["$ref"]
            if not isinstance(ref, str):
                raise KeyError(ref)
            current = _resolve_schema_pointer(schema_root, ref)
            continue
        collapsed = _collapse_nullable_optional_schema(current)
        if collapsed is not current:
            current = collapsed
            continue
        return current


def _resolve_instance_path_schema(schema_root: dict[str, Any], instance_path: str) -> dict[str, Any]:
    current = schema_root
    for segment in instance_path.split("."):
        current = _resolve_ref_schema(schema_root, current)
        if segment == "*":
            additional_properties = current.get("additionalProperties")
            if not isinstance(additional_properties, dict):
                raise KeyError(instance_path)
            current = additional_properties
            continue

        properties = current.get("properties")
        if not isinstance(properties, dict) or segment not in properties or not isinstance(properties[segment], dict):
            raise KeyError(instance_path)
        current = properties[segment]
    return _resolve_ref_schema(schema_root, current)


def _validate_reference_model_schema_binding(
    *,
    model_id: str,
    binding_label: str,
    binding: ReferenceModelSchemaBindingModel,
    key_fields: list[str],
    schemas: dict[str, dict[str, Any]] | None = None,
) -> None:
    if schemas is None:
        from .bundle import schema_bundle

        schemas = schema_bundle()
    schema_root = schemas[binding.contract_id]
    try:
        pointer_schema = _resolve_ref_schema(schema_root, _resolve_schema_pointer(schema_root, binding.schema_pointer))
    except KeyError as exc:
        raise ValueError(
            f"reference model {model_id} {binding_label} schema_pointer '{binding.schema_pointer}' "
            f"does not resolve within contract '{binding.contract_id}'"
        ) from exc

    try:
        instance_schema = _resolve_instance_path_schema(schema_root, binding.instance_path)
    except KeyError as exc:
        raise ValueError(
            f"reference model {model_id} {binding_label} instance_path '{binding.instance_path}' "
            f"does not resolve within contract '{binding.contract_id}'"
        ) from exc

    if pointer_schema != instance_schema:
        raise ValueError(
            f"reference model {model_id} {binding_label} instance_path '{binding.instance_path}' "
            f"does not resolve to schema_pointer '{binding.schema_pointer}' in contract '{binding.contract_id}'"
        )

    properties = pointer_schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError(
            f"reference model {model_id} {binding_label} schema_pointer '{binding.schema_pointer}' "
            "must resolve to an object schema with properties"
        )

    missing_key_fields = [field for field in key_fields if field not in properties]
    if missing_key_fields:
        missing = ", ".join(sorted(missing_key_fields))
        raise ValueError(
            f"reference model {model_id} key_fields are not declared by schema_pointer "
            f"'{binding.schema_pointer}' in contract '{binding.contract_id}': {missing}"
        )


def _scope_is_present(model: ContractModel, scope: str) -> bool:
    current: object = model
    for segment in scope.split("."):
        if not isinstance(current, BaseModel) or segment not in type(current).model_fields:
            return False
        current = getattr(current, segment)
        if current is None:
            return False
    return True


def _validate_controlled_vocabulary_terms(scope: str, values: list[str]) -> None:
    if not values:
        return
    from ..controlled_vocabularies import validate_controlled_vocabulary_scope_values

    validate_controlled_vocabulary_scope_values(scope, values)


def _validate_unique_string_values(field_name: str, values: list[str]) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        joined = ", ".join(duplicates)
        raise ValueError(f"{field_name} must not contain duplicate values: {joined}")


def _validate_canonical_concept_bindings(model: ContractModel, *, allowed_scopes: frozenset[str]) -> None:
    family_ids = _authoritative_concept_family_ids()
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
