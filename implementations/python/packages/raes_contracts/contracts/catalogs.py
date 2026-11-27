"""Concept-family, reference-model, and UCO-alignment catalogs."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..corpus import CONCEPT_AUTHORITY, corpus_family_root
from ..published_schemas import published_contract_ids, published_schema
from ..versions import (
    CONCEPT_FAMILIES_SCHEMA_VERSION,
    REFERENCE_MODELS_SCHEMA_VERSION,
    UCO_ALIGNMENT_SCHEMA_VERSION,
)
from ..vocabulary import ConceptFamilyId, ConceptProvenanceCategory
from .base import ContractModel, InstancePath, JsonPointerString, NonEmptyString
from .schema_resolution import resolve_instance_path_schema, resolve_ref_schema, resolve_schema_pointer


class ConceptFamilyDefinitionModel(ContractModel):
    title: NonEmptyString
    description: NonEmptyString
    provenance: ConceptProvenanceCategory
    authority: str | None = Field(default=None, min_length=1)
    authority_reference: str | None = Field(default=None, min_length=1)
    extension_scope: str | None = Field(default=None, min_length=1)
    relation_rules: list[NonEmptyString] = Field(default_factory=list, min_length=1)
    non_ambiguity_constraints: list[NonEmptyString] = Field(default_factory=list, min_length=1)

    def _validate_borrowed_provenance_requires_authority(self) -> None:
        if self.provenance in {ConceptProvenanceCategory.ADOPTED, ConceptProvenanceCategory.ADAPTED}:
            if self.authority is None or self.authority_reference is None:
                raise ValueError("adopted and adapted concept families require both authority and authority_reference")

    def _validate_native_forbids_authority_metadata(self) -> None:
        if self.provenance == ConceptProvenanceCategory.NATIVE and (
            self.authority is not None or self.authority_reference is not None
        ):
            raise ValueError("native concept families must not declare authority metadata")

    def _validate_native_requires_extension_metadata(self) -> None:
        if self.provenance == ConceptProvenanceCategory.NATIVE:
            if self.extension_scope is None:
                raise ValueError("native concept families require extension_scope")
            if not self.relation_rules:
                raise ValueError("native concept families require relation_rules")
            if not self.non_ambiguity_constraints:
                raise ValueError("native concept families require non_ambiguity_constraints")

    @model_validator(mode="after")
    def _validate_provenance_rules(self) -> ConceptFamilyDefinitionModel:
        self._validate_borrowed_provenance_requires_authority()
        self._validate_native_forbids_authority_metadata()
        self._validate_native_requires_extension_metadata()
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {"provenance": {"const": ConceptProvenanceCategory.ADOPTED.value}},
                        "required": ["provenance"],
                    },
                    "then": {
                        "required": ["authority", "authority_reference"],
                        "properties": {
                            "authority": {"type": "string", "minLength": 1},
                            "authority_reference": {"type": "string", "minLength": 1},
                        },
                    },
                },
                {
                    "if": {
                        "properties": {"provenance": {"const": ConceptProvenanceCategory.ADAPTED.value}},
                        "required": ["provenance"],
                    },
                    "then": {
                        "required": ["authority", "authority_reference"],
                        "properties": {
                            "authority": {"type": "string", "minLength": 1},
                            "authority_reference": {"type": "string", "minLength": 1},
                        },
                    },
                },
                {
                    "if": {
                        "properties": {"provenance": {"const": ConceptProvenanceCategory.NATIVE.value}},
                        "required": ["provenance"],
                    },
                    "then": {
                        "required": ["extension_scope", "relation_rules", "non_ambiguity_constraints"],
                        "properties": {
                            "extension_scope": {"type": "string", "minLength": 1},
                            "relation_rules": {"type": "array", "minItems": 1},
                            "non_ambiguity_constraints": {"type": "array", "minItems": 1},
                        },
                        "not": {
                            "anyOf": [
                                {"required": ["authority"]},
                                {"required": ["authority_reference"]},
                            ]
                        },
                    },
                },
            ]
        )
        return json_schema


class ConceptFamilyCatalogModel(ContractModel):
    schema_version: Literal[CONCEPT_FAMILIES_SCHEMA_VERSION] = CONCEPT_FAMILIES_SCHEMA_VERSION
    families: dict[NonEmptyString, ConceptFamilyDefinitionModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_family_keys(self) -> ConceptFamilyCatalogModel:
        if any(not family_id.strip() for family_id in self.families):
            raise ValueError("concept family identifiers must be non-empty")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        families_schema = json_schema.get("properties", {}).get("families")
        if isinstance(families_schema, dict):
            families_schema.setdefault("propertyNames", {"minLength": 1})
        return json_schema


class ReferenceModelSchemaBindingModel(ContractModel):
    contract_id: NonEmptyString
    schema_pointer: JsonPointerString
    instance_path: InstancePath


class ReferenceModelDefinitionModel(ContractModel):
    title: NonEmptyString
    description: NonEmptyString
    concept_family: ConceptFamilyId
    authoritative_schema: ReferenceModelSchemaBindingModel
    reused_schemas: list[ReferenceModelSchemaBindingModel] = Field(default_factory=list)
    key_fields: list[NonEmptyString] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_reference_model_definition(self) -> ReferenceModelDefinitionModel:
        if len(self.key_fields) != len(set(self.key_fields)):
            raise ValueError("reference model key_fields must not contain duplicates")

        authoritative_key = (
            self.authoritative_schema.contract_id,
            self.authoritative_schema.schema_pointer,
            self.authoritative_schema.instance_path,
        )
        reused_keys = [
            (binding.contract_id, binding.schema_pointer, binding.instance_path) for binding in self.reused_schemas
        ]
        if len(reused_keys) != len(set(reused_keys)):
            raise ValueError("reference model reused_schemas must not contain duplicate schema bindings")
        if authoritative_key in set(reused_keys):
            raise ValueError("reference model reused_schemas must not repeat authoritative_schema")
        return self


class ReferenceModelCatalogModel(ContractModel):
    schema_version: Literal[REFERENCE_MODELS_SCHEMA_VERSION] = REFERENCE_MODELS_SCHEMA_VERSION
    models: dict[NonEmptyString, ReferenceModelDefinitionModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_reference_models(self) -> ReferenceModelCatalogModel:
        known_families = authoritative_concept_family_ids()
        unknown_families = {
            model.concept_family for model in self.models.values() if model.concept_family not in known_families
        }
        if unknown_families:
            unknown = ", ".join(sorted(unknown_families))
            raise ValueError(f"reference models include unknown concept families: {unknown}")

        known_contracts = published_contract_ids()
        unknown_contracts = {
            binding.contract_id
            for model in self.models.values()
            for binding in (model.authoritative_schema, *model.reused_schemas)
            if binding.contract_id not in known_contracts
        }
        if unknown_contracts:
            unknown = ", ".join(sorted(unknown_contracts))
            raise ValueError(f"reference models include unknown contract ids: {unknown}")

        for model_id, model in self.models.items():
            validate_reference_model_schema_binding(
                model_id=model_id,
                binding_label="authoritative_schema",
                binding=model.authoritative_schema,
                key_fields=model.key_fields,
            )
            for index, binding in enumerate(model.reused_schemas):
                validate_reference_model_schema_binding(
                    model_id=model_id,
                    binding_label=f"reused_schemas[{index}]",
                    binding=binding,
                    key_fields=model.key_fields,
                )
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        models_schema = json_schema.get("properties", {}).get("models")
        if isinstance(models_schema, dict):
            models_schema.setdefault("propertyNames", {"minLength": 1})
        return json_schema


_UCO_NAMESPACE_BASE = "https://ontology.unifiedcyberontology.org/uco/"


UcoClassName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9]*:[A-Z][A-Za-z0-9]*$")]


class UcoAlignmentTypeModel(ContractModel):
    uco_class: UcoClassName
    iri: NonEmptyString
    note: NonEmptyString

    @model_validator(mode="after")
    def _validate_canonical_iri(self) -> UcoAlignmentTypeModel:
        prefix, _, local = self.uco_class.partition(":")
        expected_iri = f"{_UCO_NAMESPACE_BASE}{prefix}/{local}"
        if self.iri != expected_iri:
            raise ValueError(
                f"uco_type iri must equal the canonical UCO IRI {expected_iri} for class "
                f"{self.uco_class!r}; got {self.iri!r}"
            )
        return self


class UcoFamilyAlignmentModel(ContractModel):
    concept_family: ConceptFamilyId
    provenance: ConceptProvenanceCategory
    uco_types: list[UcoAlignmentTypeModel] = Field(min_length=1)
    divergences: list[NonEmptyString]

    @model_validator(mode="after")
    def _validate_family_alignment(self) -> UcoFamilyAlignmentModel:
        if self.provenance == ConceptProvenanceCategory.NATIVE:
            raise ValueError(f"uco alignment family {self.concept_family!r} must be adopted or adapted, not native")
        if self.provenance == ConceptProvenanceCategory.ADAPTED and not self.divergences:
            raise ValueError(
                f"adapted uco alignment family {self.concept_family!r} must enumerate at least one divergence"
            )
        if self.provenance == ConceptProvenanceCategory.ADOPTED and self.divergences:
            raise ValueError(
                f"adopted uco alignment family {self.concept_family!r} must record an empty divergences list"
            )
        uco_classes = [uco_type.uco_class for uco_type in self.uco_types]
        if len(uco_classes) != len(set(uco_classes)):
            raise ValueError(f"uco alignment family {self.concept_family!r} must not repeat a uco_class")
        return self


class UcoAlignmentCatalogModel(ContractModel):
    schema_version: Literal[UCO_ALIGNMENT_SCHEMA_VERSION] = UCO_ALIGNMENT_SCHEMA_VERSION
    uco_version: NonEmptyString
    uco_reference: NonEmptyString
    review_scope: NonEmptyString
    alignments: dict[NonEmptyString, UcoFamilyAlignmentModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_alignment_catalog(self) -> UcoAlignmentCatalogModel:
        for family_id, alignment in self.alignments.items():
            if not family_id.strip():
                raise ValueError("uco alignment family identifiers must be non-empty")
            if alignment.concept_family != family_id:
                raise ValueError(
                    f"uco alignment entry key {family_id!r} must match its concept_family {alignment.concept_family!r}"
                )

        expected_provenance = uco_cyber_concept_family_provenance()
        actual_ids = set(self.alignments)
        expected_ids = set(expected_provenance)
        missing = expected_ids - actual_ids
        unexpected = actual_ids - expected_ids
        if missing or unexpected:
            raise ValueError(
                "uco alignment must cover exactly the adopted/adapted UCO concept families declared in "
                f"concept-families-v1; missing: {sorted(missing)}; unexpected: {sorted(unexpected)}"
            )

        for family_id, alignment in self.alignments.items():
            declared = expected_provenance[family_id]
            if alignment.provenance.value != declared:
                raise ValueError(
                    f"uco alignment provenance for family {family_id!r} is "
                    f"{alignment.provenance.value!r} but concept-families-v1 declares {declared!r}"
                )
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        alignments_schema = json_schema.get("properties", {}).get("alignments")
        if isinstance(alignments_schema, dict):
            alignments_schema.setdefault("propertyNames", {"minLength": 1})
        return json_schema


@lru_cache(maxsize=1)
def authoritative_concept_family_ids() -> frozenset[str]:
    catalog_path = corpus_family_root(CONCEPT_AUTHORITY) / "concept-families-v1.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog = ConceptFamilyCatalogModel.model_validate(payload)
    return frozenset(catalog.families)


@lru_cache(maxsize=1)
def uco_cyber_concept_family_provenance() -> dict[str, str]:
    """Map each adopted/adapted family whose authority is UCO to its provenance.

    This is the single source of truth for UCO alignment coverage: the
    ``uco-alignment-v1`` catalog must declare exactly these families, so the
    cyber-domain family slice is never hard-coded in a second place.
    """
    catalog_path = corpus_family_root(CONCEPT_AUTHORITY) / "concept-families-v1.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog = ConceptFamilyCatalogModel.model_validate(payload)
    return {
        family_id: family.provenance.value
        for family_id, family in catalog.families.items()
        if family.provenance in {ConceptProvenanceCategory.ADOPTED, ConceptProvenanceCategory.ADAPTED}
        and family.authority == "UCO"
    }


def validate_reference_model_schema_binding(
    *,
    model_id: str,
    binding_label: str,
    binding: ReferenceModelSchemaBindingModel,
    key_fields: list[str],
    schemas: dict[str, dict[str, Any]] | None = None,
) -> None:
    schema_root = published_schema(binding.contract_id) if schemas is None else schemas[binding.contract_id]
    try:
        pointer_schema = resolve_ref_schema(schema_root, resolve_schema_pointer(schema_root, binding.schema_pointer))
    except KeyError as exc:
        raise ValueError(
            f"reference model {model_id} {binding_label} schema_pointer '{binding.schema_pointer}' "
            f"does not resolve within contract '{binding.contract_id}'"
        ) from exc

    try:
        instance_schema = resolve_instance_path_schema(schema_root, binding.instance_path)
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
