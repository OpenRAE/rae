"""Controlled-vocabulary and pinned external vocabulary-source contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..controlled_vocabularies import ControlledVocabularyTermId
from ..versions import (
    ACTIVITYSTREAMS_ACTIVITY_TYPES_SOURCE_SCHEMA_VERSION,
    ATLAS_TACTICS_SOURCE_SCHEMA_VERSION,
    ATTACK_ENTERPRISE_TACTICS_SOURCE_SCHEMA_VERSION,
    FIPA_COMMUNICATIVE_ACTS_SOURCE_SCHEMA_VERSION,
    NIST_CSF_DEFENSIVE_CATEGORIES_SOURCE_SCHEMA_VERSION,
)
from .base import (
    CalendarDateString,
    ContractModel,
    NonEmptyString,
    PositiveInteger,
    PrefixedDigestString,
)


class AttackEnterpriseTacticSourceTermModel(ContractModel):
    tactic_id: Annotated[str, Field(pattern=r"^TA[0-9]{4}$")]
    shortname: ControlledVocabularyTermId
    name: NonEmptyString
    description: NonEmptyString
    url: NonEmptyString
    stix_id: NonEmptyString


class AttackEnterpriseTacticsSourceModel(ContractModel):
    schema_version: Literal[ATTACK_ENTERPRISE_TACTICS_SOURCE_SCHEMA_VERSION] = (
        ATTACK_ENTERPRISE_TACTICS_SOURCE_SCHEMA_VERSION
    )
    source_authority: Literal["MITRE ATT&CK"]
    source_domain: Literal["enterprise-attack"]
    source_version: NonEmptyString
    source_url: NonEmptyString
    source_digest: PrefixedDigestString
    citation_urls: list[NonEmptyString] = Field(min_length=1)
    retrieved_at: CalendarDateString
    license_url: NonEmptyString
    license_notice: NonEmptyString
    tactics: list[AttackEnterpriseTacticSourceTermModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_attack_tactics_source(self) -> AttackEnterpriseTacticsSourceModel:
        tactic_ids = [tactic.tactic_id for tactic in self.tactics]
        if len(tactic_ids) != len(set(tactic_ids)):
            raise ValueError("ATT&CK Enterprise tactic source must not contain duplicate tactic_id values")

        shortnames = [tactic.shortname for tactic in self.tactics]
        if len(shortnames) != len(set(shortnames)):
            raise ValueError("ATT&CK Enterprise tactic source must not contain duplicate shortname values")
        return self


class AtlasTacticSourceTermModel(ContractModel):
    tactic_id: Annotated[str, Field(pattern=r"^AML\.TA[0-9]{4}$")]
    shortname: ControlledVocabularyTermId
    name: NonEmptyString
    description: NonEmptyString
    url: NonEmptyString
    position: PositiveInteger
    uuid: NonEmptyString
    created_date: CalendarDateString
    modified_date: CalendarDateString
    attack_reference_id: NonEmptyString | None = None
    attack_reference_url: NonEmptyString | None = None


class AtlasTacticsSourceModel(ContractModel):
    schema_version: Literal[ATLAS_TACTICS_SOURCE_SCHEMA_VERSION] = ATLAS_TACTICS_SOURCE_SCHEMA_VERSION
    source_authority: Literal["MITRE ATLAS"]
    source_version: NonEmptyString
    source_format_version: NonEmptyString
    source_url: NonEmptyString
    source_digest: PrefixedDigestString
    citation_urls: list[NonEmptyString] = Field(min_length=1)
    retrieved_at: CalendarDateString
    license_url: NonEmptyString
    license_notice: NonEmptyString
    collection_id: Literal["ATLAS-collection"]
    matrix_id: Literal["ATLAS-matrix"]
    tactics: list[AtlasTacticSourceTermModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_atlas_tactics_source(self) -> AtlasTacticsSourceModel:
        tactic_ids = [tactic.tactic_id for tactic in self.tactics]
        if len(tactic_ids) != len(set(tactic_ids)):
            raise ValueError("ATLAS tactic source must not contain duplicate tactic_id values")

        shortnames = [tactic.shortname for tactic in self.tactics]
        if len(shortnames) != len(set(shortnames)):
            raise ValueError("ATLAS tactic source must not contain duplicate shortname values")

        positions = [tactic.position for tactic in self.tactics]
        if len(positions) != len(set(positions)):
            raise ValueError("ATLAS tactic source must not contain duplicate position values")
        if positions != sorted(positions):
            raise ValueError("ATLAS tactic source tactics must be ordered by matrix position")
        return self


class NistCsfDefensiveCategorySourceTermModel(ContractModel):
    category_id: Annotated[str, Field(pattern=r"^(?:DE|RS|RC)\.[A-Z]{2}$")]
    term_id: ControlledVocabularyTermId
    title: NonEmptyString
    description: NonEmptyString
    function: Literal["Detect", "Respond", "Recover"]


class NistCsfDefensiveCategorySourceModel(ContractModel):
    schema_version: Literal[NIST_CSF_DEFENSIVE_CATEGORIES_SOURCE_SCHEMA_VERSION] = (
        NIST_CSF_DEFENSIVE_CATEGORIES_SOURCE_SCHEMA_VERSION
    )
    source_authority: Literal["NIST Cybersecurity Framework"]
    source_version: Literal["2.0"]
    source_url: NonEmptyString
    source_digest: PrefixedDigestString
    citation_urls: list[NonEmptyString] = Field(min_length=1)
    retrieved_at: CalendarDateString
    license_url: NonEmptyString
    license_notice: NonEmptyString
    categories: list[NistCsfDefensiveCategorySourceTermModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_defensive_categories_source(self) -> NistCsfDefensiveCategorySourceModel:
        category_ids = [category.category_id for category in self.categories]
        if len(category_ids) != len(set(category_ids)):
            raise ValueError("NIST CSF defensive category source must not contain duplicate category_id values")

        term_ids = [category.term_id for category in self.categories]
        if len(term_ids) != len(set(term_ids)):
            raise ValueError("NIST CSF defensive category source must not contain duplicate term_id values")
        return self


class ActivityStreamsActivityTypeSourceTermModel(ContractModel):
    position: PositiveInteger
    type_name: Annotated[str, Field(pattern=r"^[A-Z][A-Za-z]+$")]
    concept_id: NonEmptyString

    @model_validator(mode="after")
    def _validate_concept_iri(self) -> ActivityStreamsActivityTypeSourceTermModel:
        expected = f"https://www.w3.org/ns/activitystreams#{self.type_name}"
        if self.concept_id != expected:
            raise ValueError("ActivityStreams activity type concept_id must be the normative type IRI")
        return self


class ActivityStreamsActivityTypesSourceModel(ContractModel):
    schema_version: Literal[ACTIVITYSTREAMS_ACTIVITY_TYPES_SOURCE_SCHEMA_VERSION] = (
        ACTIVITYSTREAMS_ACTIVITY_TYPES_SOURCE_SCHEMA_VERSION
    )
    source_authority: Literal["World Wide Web Consortium"]
    source_version: Literal["REC-activitystreams-vocabulary-20170523"]
    source_status: Literal["W3C Recommendation"]
    source_url: NonEmptyString
    source_digest: PrefixedDigestString
    citation_urls: list[NonEmptyString] = Field(min_length=1)
    retrieved_at: CalendarDateString
    license_url: NonEmptyString
    license_notice: NonEmptyString
    activity_types: list[ActivityStreamsActivityTypeSourceTermModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_activity_types(self) -> ActivityStreamsActivityTypesSourceModel:
        positions = [term.position for term in self.activity_types]
        if len(positions) != len(set(positions)):
            raise ValueError("ActivityStreams activity type source must not contain duplicate positions")
        if positions != list(range(1, len(positions) + 1)):
            raise ValueError("ActivityStreams activity types must preserve contiguous source order")

        type_names = [term.type_name for term in self.activity_types]
        if len(type_names) != len(set(type_names)):
            raise ValueError("ActivityStreams activity type source must not contain duplicate type_name values")

        concept_ids = [term.concept_id for term in self.activity_types]
        if len(concept_ids) != len(set(concept_ids)):
            raise ValueError("ActivityStreams activity type source must not contain duplicate concept_id values")
        return self


class FipaCommunicativeActSourceTermModel(ContractModel):
    position: PositiveInteger
    concept_id: Annotated[str, Field(pattern=r"^[a-z]+(?:-[a-z]+)*$")]


class FipaCommunicativeActsSourceModel(ContractModel):
    schema_version: Literal[FIPA_COMMUNICATIVE_ACTS_SOURCE_SCHEMA_VERSION] = (
        FIPA_COMMUNICATIVE_ACTS_SOURCE_SCHEMA_VERSION
    )
    source_authority: Literal["Foundation for Intelligent Physical Agents"]
    source_version: Literal["SC00037J-2002-12-03"]
    source_status: Literal["Standard"]
    source_url: NonEmptyString
    source_artifact_url: NonEmptyString
    source_digest: PrefixedDigestString
    citation_urls: list[NonEmptyString] = Field(min_length=1)
    retrieved_at: CalendarDateString
    license_url: NonEmptyString
    license_notice: NonEmptyString
    communicative_acts: list[FipaCommunicativeActSourceTermModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_communicative_acts(self) -> FipaCommunicativeActsSourceModel:
        positions = [act.position for act in self.communicative_acts]
        if len(positions) != len(set(positions)):
            raise ValueError("FIPA communicative act source must not contain duplicate positions")
        if positions != list(range(1, len(positions) + 1)):
            raise ValueError("FIPA communicative acts must preserve contiguous specification order")

        concept_ids = [act.concept_id for act in self.communicative_acts]
        if len(concept_ids) != len(set(concept_ids)):
            raise ValueError("FIPA communicative act source must not contain duplicate concept_id values")
        return self
