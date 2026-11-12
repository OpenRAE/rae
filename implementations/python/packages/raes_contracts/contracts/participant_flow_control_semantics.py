"""Closed portable contracts for SEM-233 participant boundary flow control."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from ..canonical import canonical_json_digest
from ..versions import PARTICIPANT_BOUNDARY_FLOW_POLICY_V1_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString, NonNegativeInteger, PrefixedDigestString

FlowProfileRevision = Literal["rev1"]
FlowAuthorityRevision = Literal["sem-233/rev1"]
FlowObligationRef = str

_PROFILE_NONCLAIMS = (
    "backend-realization",
    "covert-channel-control",
    "intentional-subversion-robustness",
    "model-alignment",
    "runtime-enforcement",
    "universal-noninterference",
)
PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_REV1_DIGEST = (
    "sha256:43546386e7c7331fd6ce4b42195b2446d984cf14d1a90aa8f050ef8166d01801"
)


def _require_canonical_refs(values: tuple[str, ...], label: str) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be unique and use canonical sorted order")
    if any(not value for value in values):
        raise ValueError(f"{label} entries must be non-empty")


class ParticipantFlowRuleReferenceModel(ContractModel):
    """Exact identity of one declarative rule used by the flow profile."""

    model_config = ConfigDict(frozen=True)

    rule_ref: NonEmptyString
    rule_revision: NonEmptyString


class ParticipantBoundaryFlowPolicyProfileModel(ContractModel):
    """Immutable, non-executable two-coordinate SEM-233 flow algebra profile."""

    model_config = ConfigDict(frozen=True)
    _published_digest: ClassVar[str] = PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_REV1_DIGEST

    schema_version: Literal[PARTICIPANT_BOUNDARY_FLOW_POLICY_V1_SCHEMA_VERSION] = (
        PARTICIPANT_BOUNDARY_FLOW_POLICY_V1_SCHEMA_VERSION
    )
    profile_id: Literal["participant-boundary-flow-policy-v1"]
    profile_revision: FlowProfileRevision
    authority_revision: FlowAuthorityRevision
    title: NonEmptyString
    description: NonEmptyString
    confidentiality_obligation_refs: tuple[FlowObligationRef, ...] = Field(min_length=1, max_length=128)
    integrity_obligation_refs: tuple[FlowObligationRef, ...] = Field(min_length=1, max_length=128)
    unknown_confidentiality_obligation_ref: NonEmptyString
    unknown_integrity_obligation_ref: NonEmptyString
    normalization: ParticipantFlowRuleReferenceModel
    order: ParticipantFlowRuleReferenceModel
    join: ParticipantFlowRuleReferenceModel
    source_label_resolver: ParticipantFlowRuleReferenceModel
    derivation_rule: ParticipantFlowRuleReferenceModel
    declassification_authority: ParticipantFlowRuleReferenceModel
    endorsement_authority: ParticipantFlowRuleReferenceModel
    sink_policy: ParticipantFlowRuleReferenceModel
    unknown_source_posture: Literal["unsupported-top"]
    nonclaims: tuple[
        Literal[
            "backend-realization",
            "covert-channel-control",
            "intentional-subversion-robustness",
            "model-alignment",
            "runtime-enforcement",
            "universal-noninterference",
        ],
        ...,
    ] = Field(min_length=len(_PROFILE_NONCLAIMS), max_length=len(_PROFILE_NONCLAIMS))

    @model_validator(mode="after")
    def _validate_closed_algebra(self) -> ParticipantBoundaryFlowPolicyProfileModel:
        _require_canonical_refs(self.confidentiality_obligation_refs, "confidentiality obligation refs")
        _require_canonical_refs(self.integrity_obligation_refs, "integrity obligation refs")
        if self.unknown_confidentiality_obligation_ref not in self.confidentiality_obligation_refs:
            raise ValueError("unknown confidentiality obligation must belong to its declared universe")
        if self.unknown_integrity_obligation_ref not in self.integrity_obligation_refs:
            raise ValueError("unknown integrity obligation must belong to its declared universe")
        if self.nonclaims != _PROFILE_NONCLAIMS:
            raise ValueError("nonclaims must exactly match the canonical SEM-233 contract boundary")
        if self.canonical_digest != self._published_digest:
            raise ValueError("participant boundary flow profile must match the exact published rev1 artifact")
        return self

    @property
    def canonical_digest(self) -> str:
        """Return the RFC 8785 digest of this exact profile artifact."""

        return canonical_json_digest(self.model_dump(mode="json"))


class ParticipantFlowLabelResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    UNSUPPORTED = "unsupported"


class ParticipantFlowSubjectKind(str, Enum):
    RUNTIME_FACT_VERSION = "runtime-fact-version"
    ACTION_ARGUMENT = "action-argument"
    PARTICIPANT_CONTROL_OCCURRENCE = "participant-control-occurrence"
    PARTICIPANT_CROSSING_OCCURRENCE = "participant-crossing-occurrence"
    DERIVED_RESULT = "derived-result"


FlowSubjectKey = tuple[ParticipantFlowSubjectKind, str, str, str, str]


class ParticipantFlowReleaseKind(str, Enum):
    DECLASSIFICATION = "declassification"
    ENDORSEMENT = "endorsement"


class ParticipantFlowCoordinateResult(str, Enum):
    SATISFIED = "satisfied"
    DENY = "deny"
    UNSUPPORTED = "unsupported"
    STALE = "stale"
    UNRESOLVED = "unresolved"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"


class ParticipantFlowFinalDisposition(str, Enum):
    PERMIT = "permit"
    DENY = "deny"
    UNSUPPORTED = "unsupported"
    STALE = "stale"
    UNRESOLVED = "unresolved"


class ParticipantFlowSinkKind(str, Enum):
    RUNTIME_FACT_SINK = "runtime-fact-sink"
    ACTION_ARGUMENT = "action-argument"
    PARTICIPANT_CROSSING = "participant-crossing"
    PARTICIPANT_OUTPUT = "participant-output"
    PERSISTENT_WRITE = "persistent-write"
    CALLBACK = "callback"
    ERROR = "error"
    STREAM_CHUNK = "stream-chunk"


class ParticipantFlowBindingKind(str, Enum):
    RUNTIME_FACT = "runtime-fact"
    ACTION_ARGUMENT = "action-argument"
    PARTICIPANT_CONTROL = "participant-control"
    PARTICIPANT_CROSSING = "participant-crossing"


class ParticipantFlowRelationTargetKind(str, Enum):
    LABEL = "label"
    DERIVATION = "derivation"
    RELEASE = "release"
    SINK_DECISION = "sink-decision"


class ParticipantFlowProfileReferenceModel(ContractModel):
    profile_id: Literal["participant-boundary-flow-policy-v1", "participant-owner-flow-policy-v1"]
    profile_revision: FlowProfileRevision
    profile_digest: PrefixedDigestString
    authority_revision: FlowAuthorityRevision


class ParticipantFlowPolicyCutReferenceModel(ContractModel):
    policy_id: NonEmptyString
    policy_revision: NonEmptyString
    policy_digest: PrefixedDigestString
    policy_decision_ref: NonEmptyString
    decision_cut_ref: NonEmptyString
    decision_cut_revision: NonEmptyString
    effective_order: NonNegativeInteger


class ParticipantFlowSubjectReferenceModel(ContractModel):
    subject_kind: ParticipantFlowSubjectKind
    subject_ref: NonEmptyString
    subject_revision: NonEmptyString
    participant_address: NonEmptyString
    episode_id: NonEmptyString


class ParticipantEffectiveFlowLabelModel(ContractModel):
    label_id: NonEmptyString
    subject: ParticipantFlowSubjectReferenceModel
    profile: ParticipantFlowProfileReferenceModel
    policy: ParticipantFlowPolicyCutReferenceModel
    resolution_status: ParticipantFlowLabelResolutionStatus
    confidentiality_obligation_refs: tuple[NonEmptyString, ...]
    integrity_obligation_refs: tuple[NonEmptyString, ...]
    provenance_refs: tuple[NonEmptyString, ...] = Field(min_length=1)
    influence_refs: tuple[NonEmptyString, ...] = Field(min_length=1)
    evidence_refs: tuple[NonEmptyString, ...] = Field(min_length=1)

    @field_validator(
        "confidentiality_obligation_refs",
        "integrity_obligation_refs",
        "provenance_refs",
        "influence_refs",
        "evidence_refs",
    )
    @classmethod
    def _validate_canonical_refs(cls, values: tuple[str, ...], info: object) -> tuple[str, ...]:
        _require_canonical_refs(values, getattr(info, "field_name", "label refs"))
        return values


class ParticipantFlowDerivationInputModel(ContractModel):
    subject: ParticipantFlowSubjectReferenceModel
    label_ref: NonEmptyString


class ParticipantFlowNonInfluenceAssertionModel(ContractModel):
    excluded_input_refs: tuple[NonEmptyString, ...] = Field(min_length=1)
    basis_ref: NonEmptyString
    evidence_refs: tuple[NonEmptyString, ...] = Field(min_length=1)

    @field_validator("excluded_input_refs", "evidence_refs")
    @classmethod
    def _validate_canonical_refs(cls, values: tuple[str, ...], info: object) -> tuple[str, ...]:
        _require_canonical_refs(values, getattr(info, "field_name", "non-influence refs"))
        return values


class ParticipantFlowDerivationModel(ContractModel):
    derivation_id: NonEmptyString
    profile: ParticipantFlowProfileReferenceModel
    policy: ParticipantFlowPolicyCutReferenceModel
    inputs: tuple[ParticipantFlowDerivationInputModel, ...] = Field(min_length=1)
    result_subject: ParticipantFlowSubjectReferenceModel
    result_label_ref: NonEmptyString
    rule_ref: NonEmptyString
    rule_revision: NonEmptyString
    apparatus_ref: NonEmptyString
    apparatus_revision: NonEmptyString
    predecessor_refs: tuple[NonEmptyString, ...] = Field(min_length=1)
    provenance_refs: tuple[NonEmptyString, ...] = Field(min_length=1)
    influence_refs: tuple[NonEmptyString, ...] = Field(min_length=1)
    evidence_refs: tuple[NonEmptyString, ...] = Field(min_length=1)
    non_influence_assertion: ParticipantFlowNonInfluenceAssertionModel | None = None

    @field_validator("predecessor_refs", "provenance_refs", "influence_refs", "evidence_refs")
    @classmethod
    def _validate_canonical_refs(cls, values: tuple[str, ...], info: object) -> tuple[str, ...]:
        _require_canonical_refs(values, getattr(info, "field_name", "derivation refs"))
        return values

    @model_validator(mode="after")
    def _validate_input_order(self) -> ParticipantFlowDerivationModel:
        keys = tuple(
            (item.subject.subject_kind.value, item.subject.subject_ref, item.label_ref) for item in self.inputs
        )
        if keys != tuple(sorted(set(keys))):
            raise ValueError("derivation inputs must be unique and use canonical sorted order")
        if self.non_influence_assertion is not None:
            inputs = {item.subject.subject_ref for item in self.inputs}
            if inputs & set(self.non_influence_assertion.excluded_input_refs):
                raise ValueError("non-influence assertion cannot exclude a declared possible input")
        return self


class ParticipantFlowObligationReplacementModel(ContractModel):
    source_obligation_ref: NonEmptyString
    result_obligation_ref: NonEmptyString


class ParticipantFlowReleaseBaseModel(ContractModel):
    release_id: NonEmptyString
    profile: ParticipantFlowProfileReferenceModel
    policy: ParticipantFlowPolicyCutReferenceModel
    source_subject: ParticipantFlowSubjectReferenceModel
    source_label_ref: NonEmptyString
    result_subject: ParticipantFlowSubjectReferenceModel
    result_label_ref: NonEmptyString
    sink_ref: NonEmptyString
    destination_ref: NonEmptyString
    audience_scope_ref: NonEmptyString
    authority_basis_ref: NonEmptyString
    authority_revision: NonEmptyString
    predecessor_refs: tuple[NonEmptyString, ...] = Field(min_length=1)
    evidence_refs: tuple[NonEmptyString, ...] = Field(min_length=1)
    limitation_refs: tuple[NonEmptyString, ...] = Field(min_length=1)

    @field_validator("predecessor_refs", "evidence_refs", "limitation_refs")
    @classmethod
    def _validate_canonical_refs(cls, values: tuple[str, ...], info: object) -> tuple[str, ...]:
        _require_canonical_refs(values, getattr(info, "field_name", "release refs"))
        return values


class ParticipantFlowDeclassificationModel(ParticipantFlowReleaseBaseModel):
    kind: Literal[ParticipantFlowReleaseKind.DECLASSIFICATION]
    removed_confidentiality_obligation_refs: tuple[NonEmptyString, ...] = Field(min_length=1)

    @field_validator("removed_confidentiality_obligation_refs")
    @classmethod
    def _validate_removed_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        _require_canonical_refs(values, "removed confidentiality obligation refs")
        return values


class ParticipantFlowEndorsementModel(ParticipantFlowReleaseBaseModel):
    kind: Literal[ParticipantFlowReleaseKind.ENDORSEMENT]
    integrity_obligation_replacements: tuple[ParticipantFlowObligationReplacementModel, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_replacement_order(self) -> ParticipantFlowEndorsementModel:
        keys = tuple(
            (item.source_obligation_ref, item.result_obligation_ref) for item in self.integrity_obligation_replacements
        )
        if keys != tuple(sorted(set(keys))):
            raise ValueError("integrity obligation replacements must be unique and canonical")
        if len({item.source_obligation_ref for item in self.integrity_obligation_replacements}) != len(keys):
            raise ValueError("integrity endorsement cannot replace one source obligation more than once")
        return self


ParticipantFlowRelease = Annotated[
    ParticipantFlowDeclassificationModel | ParticipantFlowEndorsementModel,
    Field(discriminator="kind"),
]


class ParticipantFlowSinkReferenceModel(ContractModel):
    sink_kind: ParticipantFlowSinkKind
    sink_ref: NonEmptyString
    destination_ref: NonEmptyString
    audience_scope_ref: NonEmptyString


class ParticipantFlowSinkDecisionModel(ContractModel):
    decision_id: NonEmptyString
    profile: ParticipantFlowProfileReferenceModel
    policy: ParticipantFlowPolicyCutReferenceModel
    subject: ParticipantFlowSubjectReferenceModel
    label_ref: NonEmptyString
    sink: ParticipantFlowSinkReferenceModel
    confidentiality_result: ParticipantFlowCoordinateResult
    integrity_result: ParticipantFlowCoordinateResult
    release_refs: tuple[NonEmptyString, ...]
    api_423_decision_ref: NonEmptyString
    action_admission_ref: NonEmptyString
    capability_resolution_ref: NonEmptyString
    expected_history_head_refs: tuple[NonEmptyString, ...] = Field(min_length=1)
    final_disposition: ParticipantFlowFinalDisposition
    reason_code: NonEmptyString
    evidence_refs: tuple[NonEmptyString, ...] = Field(min_length=1)
    limitation_refs: tuple[NonEmptyString, ...] = Field(min_length=1)

    @field_validator("release_refs", "expected_history_head_refs", "evidence_refs", "limitation_refs")
    @classmethod
    def _validate_canonical_refs(cls, values: tuple[str, ...], info: object) -> tuple[str, ...]:
        _require_canonical_refs(values, getattr(info, "field_name", "sink-decision refs"))
        return values

    @model_validator(mode="after")
    def _validate_disposition(self) -> ParticipantFlowSinkDecisionModel:
        coordinate_disposition = participant_flow_coordinate_disposition(
            self.confidentiality_result,
            self.integrity_result,
        )
        if (
            coordinate_disposition != ParticipantFlowFinalDisposition.PERMIT
            and self.final_disposition == ParticipantFlowFinalDisposition.PERMIT
        ):
            raise ValueError("final disposition cannot permit a non-permitting coordinate result")
        return self


def participant_flow_coordinate_disposition(
    confidentiality: ParticipantFlowCoordinateResult,
    integrity: ParticipantFlowCoordinateResult,
) -> ParticipantFlowFinalDisposition:
    values = {confidentiality, integrity}
    if ParticipantFlowCoordinateResult.DENY in values:
        disposition = ParticipantFlowFinalDisposition.DENY
    elif ParticipantFlowCoordinateResult.UNSUPPORTED in values:
        disposition = ParticipantFlowFinalDisposition.UNSUPPORTED
    elif ParticipantFlowCoordinateResult.STALE in values:
        disposition = ParticipantFlowFinalDisposition.STALE
    elif values & {
        ParticipantFlowCoordinateResult.UNRESOLVED,
        ParticipantFlowCoordinateResult.UNKNOWN,
        ParticipantFlowCoordinateResult.AMBIGUOUS,
    }:
        disposition = ParticipantFlowFinalDisposition.UNRESOLVED
    else:
        disposition = ParticipantFlowFinalDisposition.PERMIT
    return disposition
