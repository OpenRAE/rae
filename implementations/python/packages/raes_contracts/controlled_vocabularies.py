"""Controlled vocabulary catalog models and the helpers that load and validate declarations."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ._base import ContractModel, NonEmptyString, PrefixedDigestString
from .concept_binding_scopes import BACKEND_CONCEPT_BINDING_SCOPES, PARTICIPANT_IMPLEMENTATION_CONCEPT_BINDING_SCOPES
from .corpus import CONCEPT_AUTHORITY, corpus_family_root
from .runtime_vocabulary_scopes import SDL_IDENTITY_VOCABULARY_SCOPES
from .versions import CONTROLLED_VOCABULARIES_SCHEMA_VERSION

ControlledVocabularyTermId = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")]


_CONTROLLED_VOCABULARY_GOVERNED_SCOPES = frozenset(
    {
        *SDL_IDENTITY_VOCABULARY_SCOPES,
        "behavior_specifications.behavior_mode",
        "agents.interactive_access.channel",
        "sdl.accounts.auth_method",
        "sdl.accounts.credential_bindings.auth_method",
        "sdl.accounts.credential_bindings.purpose",
        "capabilities.supported_features",
        "implementation_kind",
        "capabilities.supported_participant_contracts",
        "capabilities.supported_decision_surface_modes",
        "capabilities.tool_affordance_expectations",
        "capabilities.exposure_policy_kinds",
        "capabilities.orchestrator.supported_workflow_features",
        "capabilities.orchestrator.supported_workflow_state_predicates",
        "workflows.steps.fact_binding_refs",
        "random_streams.draw_purpose",
        "participant-crossing-occurrence.direction",
        "participant-crossing-occurrence.interaction_kind",
        "participant-crossing-occurrence.subject.subject_kind",
        "participant-crossing-occurrence.operation",
        "participant-crossing-occurrence.gates",
        "participant-crossing-occurrence.decision.disposition",
        "participant-crossing-occurrence.backend_posture",
        "participant-crossing-occurrence.losses.kind",
        "participant-crossing-occurrence.stage",
        "participant-flow-control-relation.labels.resolution_status",
        "participant-flow-control-relation.labels.subject.subject_kind",
        "participant-flow-control-relation.releases.kind",
        "participant-flow-control-relation.sink_decisions.coordinate_result",
        "participant-flow-control-relation.sink_decisions.final_disposition",
        "participant-flow-control-relation.sink_decisions.sink.sink_kind",
        "participant-flow-control-relation.bindings.kind",
        "participant-flow-control-relation.bindings.relation_target.target_kind",
        "external_concept_bindings.bindings.*.assertion.relationship_kind",
        "external_concept_bindings.bindings.*.assertion.semantic_effect",
        "external_concept_bindings.bindings.*.confidence.posture",
        "external_concept_bindings.bindings.*.approximation.posture",
        "external_concept_bindings.bindings.*.review.status",
        "external_concept_bindings.bindings.*.perspective.participant_availability.kind",
        "scenario.realization.constraints.compute-substrate",
        "nodes.os_distribution",
        "runtime.snapshot.realization_observations.operating-system.distribution",
        "runtime.snapshot.realization_observations.compute-substrate",
        *BACKEND_CONCEPT_BINDING_SCOPES,
        *PARTICIPANT_IMPLEMENTATION_CONCEPT_BINDING_SCOPES,
    }
)


class ControlledVocabularySourceModel(ContractModel):
    provenance: Literal["adopted", "adapted"]
    authority: NonEmptyString
    authority_version: NonEmptyString
    source_artifact_ref: NonEmptyString
    source_url: NonEmptyString
    source_digest: PrefixedDigestString
    citation_urls: list[NonEmptyString] = Field(min_length=1)
    license_url: NonEmptyString
    license_notice: NonEmptyString


class ControlledVocabularyTermModel(ContractModel):
    title: NonEmptyString
    description: NonEmptyString
    source_id: NonEmptyString | None = None
    source_url: NonEmptyString | None = None


class ControlledVocabularyDefinitionModel(ContractModel):
    title: NonEmptyString
    description: NonEmptyString
    source: ControlledVocabularySourceModel | None = None
    kind: Literal["enumeration", "vocabulary"]
    governed_scopes: list[NonEmptyString] = Field(default_factory=list)
    extension_policy: Literal["closed", "governed-extension"]
    extension_pattern: NonEmptyString | None = None
    terms: dict[ControlledVocabularyTermId, ControlledVocabularyTermModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_vocabulary_definition(self) -> ControlledVocabularyDefinitionModel:
        unknown_scopes = set(self.governed_scopes) - _CONTROLLED_VOCABULARY_GOVERNED_SCOPES
        if unknown_scopes:
            unknown = ", ".join(sorted(unknown_scopes))
            raise ValueError(f"controlled vocabulary includes unknown governed scopes: {unknown}")

        if len(self.governed_scopes) != len(set(self.governed_scopes)):
            raise ValueError("controlled vocabulary governed_scopes must not contain duplicates")

        if self.kind == "enumeration" and self.extension_policy != "closed":
            raise ValueError("enumeration controlled vocabularies must use extension_policy='closed'")

        if self.extension_policy == "closed":
            if self.extension_pattern is not None:
                raise ValueError("closed controlled vocabularies must not declare extension_pattern")
            return self

        if not self.governed_scopes:
            raise ValueError("governed-extension controlled vocabularies must declare governed_scopes")
        if self.extension_pattern is None:
            raise ValueError("governed-extension controlled vocabularies must declare extension_pattern")
        try:
            re.compile(self.extension_pattern)
        except re.error as exc:
            raise ValueError("controlled vocabulary extension_pattern must be a valid regex") from exc
        return self


class ControlledVocabularyCatalogModel(ContractModel):
    schema_version: Literal[CONTROLLED_VOCABULARIES_SCHEMA_VERSION] = CONTROLLED_VOCABULARIES_SCHEMA_VERSION
    vocabularies: dict[NonEmptyString, ControlledVocabularyDefinitionModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_vocabulary_catalog(self) -> ControlledVocabularyCatalogModel:
        scope_to_vocabulary: dict[str, str] = {}
        for vocabulary_id, definition in self.vocabularies.items():
            for scope in definition.governed_scopes:
                previous = scope_to_vocabulary.setdefault(scope, vocabulary_id)
                if previous != vocabulary_id:
                    raise ValueError(
                        f"governed scope '{scope}' is declared by multiple vocabularies: {previous}, {vocabulary_id}"
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
        vocabularies_schema = json_schema.get("properties", {}).get("vocabularies")
        if isinstance(vocabularies_schema, dict):
            vocabularies_schema.setdefault("propertyNames", {"minLength": 1})
        return json_schema


def controlled_vocabulary_catalog_path() -> Path:
    return corpus_family_root(CONCEPT_AUTHORITY) / "controlled-vocabularies-v1.json"


@lru_cache(maxsize=1)
def load_controlled_vocabulary_catalog() -> ControlledVocabularyCatalogModel:
    path = controlled_vocabulary_catalog_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ControlledVocabularyCatalogModel.model_validate(payload)


@lru_cache(maxsize=1)
def _scope_to_vocabulary_id() -> dict[str, str]:
    catalog = load_controlled_vocabulary_catalog()
    return {
        scope: vocabulary_id
        for vocabulary_id, definition in catalog.vocabularies.items()
        for scope in definition.governed_scopes
    }


def controlled_vocabulary_id_for_scope(scope: str) -> str | None:
    """Return the catalog-owned vocabulary for a declared scope, if any."""
    return _scope_to_vocabulary_id().get(scope)


def validate_controlled_vocabulary_value(vocabulary_id: str, value: str) -> None:
    catalog = load_controlled_vocabulary_catalog()
    try:
        definition = catalog.vocabularies[vocabulary_id]
    except KeyError as exc:
        raise ValueError(f"unknown controlled vocabulary '{vocabulary_id}'") from exc

    if value in definition.terms:
        return
    if definition.extension_policy == "closed":
        raise ValueError(
            f"controlled vocabulary '{vocabulary_id}' does not allow extensions; '{value}' is not a permitted term"
        )
    if definition.extension_pattern is None:
        raise ValueError(f"controlled vocabulary '{vocabulary_id}' is missing its extension pattern")
    if re.fullmatch(definition.extension_pattern, value):
        return
    raise ValueError(
        f"controlled vocabulary '{vocabulary_id}' does not permit term '{value}'; "
        "value is not a permitted term and must match the governed extension pattern"
    )


def validate_controlled_vocabulary_scope_values(scope: str, values: Iterable[str]) -> None:
    vocabulary_id = _scope_to_vocabulary_id().get(scope)
    if vocabulary_id is None:
        raise ValueError(f"scope '{scope}' is not governed by controlled-vocabularies-v1")
    for value in values:
        validate_controlled_vocabulary_value(vocabulary_id, value)
