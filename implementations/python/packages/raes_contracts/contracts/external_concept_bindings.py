"""Closed authored contract for portable external concept-binding assertions."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..uri_safety import validate_safe_absolute_uri
from ..versions import EXTERNAL_CONCEPT_BINDINGS_SCHEMA_VERSION
from ..vocabulary import ExternalKnowledgeBindingEffect
from .base import (
    ClosedUnitIntervalFloat,
    ContractModel,
    NonEmptyString,
    PrefixedDigestString,
    Rfc3339DateTimeString,
)
from .experiment_manifest_references import (
    ExperimentEvidenceRecordReferenceModel,
    ExperimentEvidenceReferenceModel,
)
from .experiment_references import ExperimentReferenceModel
from .schema_invariants import add_raes_invariant

_DOCUMENT_VALIDATOR = "raes_contracts.contracts.ExternalConceptBindingDocumentModel.model_validate"


def _string_branch(schema: JsonSchemaValue) -> JsonSchemaValue:
    """Return the string branch of an optional-string schema."""

    branches = schema.get("anyOf")
    if isinstance(branches, list):
        for branch in branches:
            if isinstance(branch, dict) and branch.get("type") == "string":
                return branch
    return schema


class ExternalConceptRelationshipKind(str, Enum):
    EQUIVALENT_TO = "equivalent-to"
    BROADER_THAN = "broader-than"
    NARROWER_THAN = "narrower-than"
    RELATED_TO = "related-to"
    INSTANCE_OF = "instance-of"


class ExternalConceptConfidencePosture(str, Enum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExternalConceptApproximationPosture(str, Enum):
    EXACT = "exact"
    APPROXIMATE = "approximate"
    LOSSY = "lossy"


class ExternalConceptReviewStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    IN_REVIEW = "in-review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ExternalConceptParticipantAvailabilityKind(str, Enum):
    """Eligibility declaration; never an exposure or delivery record."""

    ELIGIBILITY_ONLY = "eligibility-only"


class ExternalConceptLifecyclePhase(str, Enum):
    NORMALIZED_AUTHORING = "normalized-authoring"
    EXPANDED_AUTHORING = "expanded-authoring"
    INSTANTIATED = "instantiated"
    CANONICAL_SNAPSHOT = "canonical-snapshot"
    COMPILED = "compiled"
    REALIZED = "realized"
    OBSERVED = "observed"
    REPORTED = "reported"


class ExternalConceptSubjectModel(ContractModel):
    """Exact, digest-pinned coordinate for one RAES subject."""

    subject_kind: NonEmptyString
    owning_contract_id: NonEmptyString
    lifecycle_phase: ExternalConceptLifecyclePhase
    canonical_ref: NonEmptyString
    artifact_digest: PrefixedDigestString


class ExternalConceptSchemeCoordinateModel(ContractModel):
    """Versioned and inert coordinate for one concept in an external scheme."""

    scheme_id: NonEmptyString
    authority: NonEmptyString
    revision: NonEmptyString
    source_locator: NonEmptyString | None = None
    source_digest: PrefixedDigestString | None = None
    concept_id: NonEmptyString

    @field_validator("source_locator")
    @classmethod
    def _validate_source_locator(cls, value: str | None) -> str | None:
        if value is not None:
            validate_safe_absolute_uri(
                value,
                field_name="external concept scheme source_locator",
                forbidden_schemes={"file", "data"},
                forbid_fragment=True,
            )
        return value

    @model_validator(mode="after")
    def _validate_pinned_source(self) -> ExternalConceptSchemeCoordinateModel:
        if self.source_locator is None and self.source_digest is None:
            raise ValueError("external concept scheme requires source_locator or source_digest")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        locator_schema = _string_branch(json_schema["properties"]["source_locator"])
        locator_schema.setdefault("allOf", []).extend(
            [
                {"pattern": r"^[A-Za-z][A-Za-z0-9+.-]*:"},
                {"not": {"pattern": r"^[Ff][Ii][Ll][Ee]:"}},
                {"not": {"pattern": r"^[Dd][Aa][Tt][Aa]:"}},
                {"not": {"pattern": r"^[A-Za-z][A-Za-z0-9+.-]*://[^/?#]*@"}},
                {"not": {"pattern": "#"}},
                {
                    "not": {
                        "pattern": (
                            r"[?&][^#&=]*(?:"
                            r"[Aa][Pp][Ii][-_]?[Kk][Ee][Yy]|"
                            r"[Cc][Rr][Ee][Dd][Ee][Nn][Tt][Ii][Aa][Ll]|"
                            r"[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]|"
                            r"[Ss][Ee][Cc][Rr][Ee][Tt]|"
                            r"[Ss][Ii][Gg][Nn][Aa][Tt][Uu][Rr][Ee]|"
                            r"[Tt][Oo][Kk][Ee][Nn]"
                            r")[^#&=]*="
                        )
                    }
                },
                {"not": {"pattern": r"[?&](?:[Aa][Uu][Tt][Hh]|[Kk][Ee][Yy]|[Ss][Ii][Gg])="}},
                {
                    "if": {"pattern": r"^[Hh][Tt][Tt][Pp][Ss]?:"},
                    "then": {"pattern": r"^[Hh][Tt][Tt][Pp][Ss]?://[^/?#]+"},
                },
            ]
        )
        json_schema.setdefault("allOf", []).append(
            {
                "anyOf": [
                    {
                        "required": ["source_locator"],
                        "properties": {"source_locator": {"type": "string"}},
                    },
                    {
                        "required": ["source_digest"],
                        "properties": {"source_digest": {"type": "string"}},
                    },
                ]
            }
        )
        return json_schema


class ExternalConceptAssertionModel(ContractModel):
    relationship_kind: ExternalConceptRelationshipKind
    motivation: NonEmptyString
    motivation_basis_refs: list[ExperimentReferenceModel] = Field(min_length=1)
    semantic_effect: ExternalKnowledgeBindingEffect
    semantic_effect_basis_refs: list[ExperimentReferenceModel] = Field(min_length=1)


class ExternalConceptParticipantAvailabilityModel(ContractModel):
    kind: ExternalConceptParticipantAvailabilityKind
    participant_refs: list[NonEmptyString] = Field(min_length=1)
    basis_refs: list[ExperimentReferenceModel] = Field(min_length=1)

    @field_validator("participant_refs")
    @classmethod
    def _validate_unique_participants(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("external concept participant_refs must be unique")
        return value

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema["properties"]["participant_refs"]["uniqueItems"] = True
        return json_schema


class ExternalConceptPerspectiveModel(ContractModel):
    asserting_party_kind: Literal["author", "reviewer", "publisher", "scheme-authority", "raes-governance"]
    asserting_party_ref: NonEmptyString
    perspective: NonEmptyString
    authority_basis_refs: list[ExperimentReferenceModel] = Field(min_length=1)
    participant_availability: ExternalConceptParticipantAvailabilityModel | None = None


class ExternalConceptProvenanceModel(ContractModel):
    asserted_at: Rfc3339DateTimeString
    source_refs: list[ExperimentReferenceModel] = Field(min_length=1)


class ExternalConceptConfidenceModel(ContractModel):
    posture: ExternalConceptConfidencePosture
    basis: NonEmptyString
    score: ClosedUnitIntervalFloat | None = None
    calibration_profile_ref: ExperimentReferenceModel | None = None

    @model_validator(mode="after")
    def _validate_calibrated_score(self) -> ExternalConceptConfidenceModel:
        if (self.score is None) != (self.calibration_profile_ref is None):
            raise ValueError("numeric external concept confidence requires score and calibration_profile_ref together")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "required": ["score"],
                        "properties": {"score": {"not": {"type": "null"}}},
                    },
                    "then": {
                        "required": ["calibration_profile_ref"],
                        "properties": {"calibration_profile_ref": {"not": {"type": "null"}}},
                    },
                },
                {
                    "if": {
                        "required": ["calibration_profile_ref"],
                        "properties": {"calibration_profile_ref": {"not": {"type": "null"}}},
                    },
                    "then": {
                        "required": ["score"],
                        "properties": {"score": {"not": {"type": "null"}}},
                    },
                },
            ]
        )
        return json_schema


class ExternalConceptApproximationModel(ContractModel):
    posture: ExternalConceptApproximationPosture
    loss_details: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_loss_details(self) -> ExternalConceptApproximationModel:
        if self.posture == ExternalConceptApproximationPosture.EXACT and self.loss_details:
            raise ValueError("exact external concept assertions must not declare loss_details")
        if self.posture != ExternalConceptApproximationPosture.EXACT and not self.loss_details:
            raise ValueError("approximate or lossy external concept assertions require loss_details")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema.setdefault("allOf", []).append(
            {
                "if": {
                    "required": ["posture"],
                    "properties": {"posture": {"const": "exact"}},
                },
                "then": {"properties": {"loss_details": {"maxItems": 0}}},
                "else": {
                    "required": ["loss_details"],
                    "properties": {"loss_details": {"minItems": 1}},
                },
            }
        )
        return json_schema


class ExternalConceptReviewModel(ContractModel):
    status: ExternalConceptReviewStatus
    review_refs: list[ExperimentReferenceModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_review_refs(self) -> ExternalConceptReviewModel:
        reviewed = {
            ExternalConceptReviewStatus.ACCEPTED,
            ExternalConceptReviewStatus.REJECTED,
            ExternalConceptReviewStatus.SUPERSEDED,
        }
        if self.status in reviewed and not self.review_refs:
            raise ValueError("completed external concept review statuses require review_refs")
        if self.status == ExternalConceptReviewStatus.UNREVIEWED and self.review_refs:
            raise ValueError("unreviewed external concept assertions must not declare review_refs")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "required": ["status"],
                        "properties": {"status": {"enum": ["accepted", "rejected", "superseded"]}},
                    },
                    "then": {
                        "required": ["review_refs"],
                        "properties": {"review_refs": {"minItems": 1}},
                    },
                },
                {
                    "if": {
                        "required": ["status"],
                        "properties": {"status": {"const": "unreviewed"}},
                    },
                    "then": {"properties": {"review_refs": {"maxItems": 0}}},
                },
            ]
        )
        return json_schema


class ExternalConceptBindingAssertionModel(ContractModel):
    binding_id: NonEmptyString
    subject: ExternalConceptSubjectModel
    scheme: ExternalConceptSchemeCoordinateModel
    assertion: ExternalConceptAssertionModel
    perspective: ExternalConceptPerspectiveModel
    provenance: ExternalConceptProvenanceModel
    supporting_evidence_refs: list[ExperimentEvidenceReferenceModel | ExperimentEvidenceRecordReferenceModel] = Field(
        default_factory=list
    )
    confidence: ExternalConceptConfidenceModel
    approximation: ExternalConceptApproximationModel
    limitations: list[NonEmptyString] = Field(min_length=1)
    review: ExternalConceptReviewModel


class ExternalConceptBindingDocumentModel(ContractModel):
    """One stable authored set of independently identified binding assertions."""

    schema_version: Literal[EXTERNAL_CONCEPT_BINDINGS_SCHEMA_VERSION] = EXTERNAL_CONCEPT_BINDINGS_SCHEMA_VERSION
    binding_set_id: NonEmptyString
    binding_set_version: NonEmptyString
    bindings: dict[NonEmptyString, ExternalConceptBindingAssertionModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_binding_identities(self) -> ExternalConceptBindingDocumentModel:
        semantic_identities: set[tuple[str, ...]] = set()
        for key, binding in self.bindings.items():
            if key != binding.binding_id:
                raise ValueError("external concept binding map key must equal binding id")
            identity = (
                binding.subject.owning_contract_id,
                binding.subject.lifecycle_phase.value,
                binding.subject.canonical_ref,
                binding.subject.artifact_digest.casefold(),
                binding.scheme.scheme_id,
                binding.scheme.authority,
                binding.scheme.revision,
                binding.scheme.concept_id,
                binding.assertion.relationship_kind.value,
                binding.perspective.asserting_party_ref,
            )
            if identity in semantic_identities:
                raise ValueError("external concept binding set contains duplicate semantic assertions")
            semantic_identities.add(identity)
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        invariants = (
            (
                "external-concept-source-locator-safe",
                "External scheme source locators must be absolute, inert, credential-free, fragment-free URIs.",
            ),
            (
                "external-concept-source-pinned",
                "Every external scheme coordinate must declare a source locator, a content digest, or both.",
            ),
            (
                "external-concept-participants-unique",
                "Participant eligibility references must be unique within one availability assertion.",
            ),
            (
                "external-concept-confidence-calibrated",
                "Numeric confidence scores and calibration profile references must be supplied together.",
            ),
            (
                "external-concept-approximation-loss-consistent",
                "Exact assertions must declare no loss; approximate and lossy assertions must describe loss.",
            ),
            (
                "external-concept-review-evidence-consistent",
                "Completed review statuses require review references, while unreviewed assertions forbid them.",
            ),
            (
                "external-concept-binding-identities",
                "Binding map keys must equal binding ids and semantic assertion identities must be unique.",
            ),
        )
        for invariant_id, description in invariants:
            add_raes_invariant(
                json_schema,
                invariant_id,
                description,
                validator=_DOCUMENT_VALIDATOR,
                inputs=[{"contract_id": "external-concept-bindings-v1", "instance_path": "#"}],
            )
        return json_schema


__all__ = [
    "ExternalConceptApproximationModel",
    "ExternalConceptApproximationPosture",
    "ExternalConceptAssertionModel",
    "ExternalConceptBindingAssertionModel",
    "ExternalConceptBindingDocumentModel",
    "ExternalConceptConfidenceModel",
    "ExternalConceptConfidencePosture",
    "ExternalConceptLifecyclePhase",
    "ExternalConceptParticipantAvailabilityKind",
    "ExternalConceptParticipantAvailabilityModel",
    "ExternalConceptPerspectiveModel",
    "ExternalConceptProvenanceModel",
    "ExternalConceptRelationshipKind",
    "ExternalConceptReviewModel",
    "ExternalConceptReviewStatus",
    "ExternalConceptSchemeCoordinateModel",
    "ExternalConceptSubjectModel",
]
