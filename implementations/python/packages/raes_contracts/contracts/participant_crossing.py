"""API-423 portable participant-crossing policy and evidence contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .base import (
    ContractModel,
    NonEmptyString,
    NonNegativeInteger,
    PositiveInteger,
    PrefixedDigestString,
)
from .participant_crossing_vocab import (
    ParticipantCrossingBackendPosture,
    ParticipantCrossingDecisionDisposition,
    ParticipantCrossingDirection,
    ParticipantCrossingGateDisposition,
    ParticipantCrossingInteractionKind,
    ParticipantCrossingLossKind,
    ParticipantCrossingOperation,
    ParticipantCrossingSubjectKind,
)
from .participant_envelopes import ParticipantRuntimeBaseEnvelopeModel
from .participant_opacity import (
    ParticipantOpacityObservationInventoryModel,
    ParticipantOpacityObservationSurfaceModel,
    ParticipantOpacityRuntimeEnforcementBindingModel,
    ParticipantOpacityRuntimeSupportModel,
)
from .participant_runtime import ParticipantRuntimeOrderingBasis
from .schema_invariants import _add_raes_invariant

_TRANSFORMATION_OPERATIONS = frozenset(
    {
        ParticipantCrossingOperation.PROJECTION,
        ParticipantCrossingOperation.MASKING,
        ParticipantCrossingOperation.REDACTION,
        ParticipantCrossingOperation.TRANSFORMATION,
        ParticipantCrossingOperation.DECLASSIFICATION,
    }
)


def _classify_gate_dispositions(
    gates: ParticipantCrossingDecisionGatesModel,
) -> tuple[bool, bool]:
    dispositions = set(gates.dispositions())
    failed = ParticipantCrossingGateDisposition.DENY in dispositions
    unresolved = bool(
        dispositions
        & {
            ParticipantCrossingGateDisposition.UNKNOWN,
            ParticipantCrossingGateDisposition.UNSUPPORTED,
        }
    )
    return failed, unresolved


def _validate_decision_disposition(
    disposition: ParticipantCrossingDecisionDisposition,
    *,
    failed: bool,
    unresolved: bool,
) -> None:
    permitted = {
        ParticipantCrossingDecisionDisposition.PERMIT,
        ParticipantCrossingDecisionDisposition.TRANSFORM,
    }
    if disposition in permitted and (failed or unresolved):
        raise ValueError("permitted participant crossing decisions require every applicable gate to permit")
    if disposition == ParticipantCrossingDecisionDisposition.DENY and not failed:
        raise ValueError("denied participant crossing decisions require a denied gate")
    if disposition == ParticipantCrossingDecisionDisposition.UNSUPPORTED and not unresolved:
        raise ValueError("unsupported participant crossing decisions require an unresolved or unsupported gate")


def _validate_required_operation(
    disposition: ParticipantCrossingDecisionDisposition,
    required_operation: ParticipantCrossingOperation | None,
) -> None:
    if (
        disposition == ParticipantCrossingDecisionDisposition.TRANSFORM
        and required_operation not in _TRANSFORMATION_OPERATIONS
    ):
        raise ValueError("transform decisions require an explicit transformation operation")
    if disposition != ParticipantCrossingDecisionDisposition.TRANSFORM and required_operation is not None:
        raise ValueError("required_operation is reserved for transform decisions")


class ParticipantCrossingSubjectReferenceModel(ContractModel):
    """Typed identity for an existing carrier without copying its payload."""

    subject_kind: ParticipantCrossingSubjectKind
    contract_id: NonEmptyString
    subject_ref: NonEmptyString
    subject_revision: NonEmptyString | None = None
    subject_digest: PrefixedDigestString | None = None
    participant_address: NonEmptyString
    episode_id: NonEmptyString

    @model_validator(mode="after")
    def _require_revision_or_digest(self) -> ParticipantCrossingSubjectReferenceModel:
        if self.subject_revision is None and self.subject_digest is None:
            raise ValueError("participant crossing subject requires a revision or digest")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("anyOf", []).extend(
            [
                {"required": ["subject_revision"], "properties": {"subject_revision": {"type": "string"}}},
                {"required": ["subject_digest"], "properties": {"subject_digest": {"type": "string"}}},
            ]
        )
        return json_schema


class ParticipantCrossingPolicyReferenceModel(ContractModel):
    """Exact revision and order interval for the policy used at a crossing."""

    policy_id: NonEmptyString
    policy_revision: NonEmptyString
    policy_digest: PrefixedDigestString
    policy_decision_ref: NonEmptyString
    decision_cut_ref: NonEmptyString
    effective_order: NonNegativeInteger
    valid_from_order: NonNegativeInteger
    valid_until_order: NonNegativeInteger

    @model_validator(mode="after")
    def _validate_order_interval(self) -> ParticipantCrossingPolicyReferenceModel:
        if self.valid_until_order < self.valid_from_order:
            raise ValueError("participant crossing policy interval must not be inverted")
        if not self.valid_from_order <= self.effective_order <= self.valid_until_order:
            raise ValueError("participant crossing policy effective order must fall within its validity interval")
        return self


class ParticipantCrossingLossModel(ContractModel):
    """One explicit fidelity loss or guarantee weakening."""

    kind: ParticipantCrossingLossKind
    basis_ref: NonEmptyString
    affected_ref: NonEmptyString
    limitation_ref: NonEmptyString


class ParticipantCrossingDecisionGatesModel(ContractModel):
    """Independent deny-first gates for one crossing decision."""

    caller_authorization: ParticipantCrossingGateDisposition
    target_authorization: ParticipantCrossingGateDisposition
    participant_authority: ParticipantCrossingGateDisposition
    action_admission: ParticipantCrossingGateDisposition
    visibility: ParticipantCrossingGateDisposition
    marking_authorization: ParticipantCrossingGateDisposition
    declassification: ParticipantCrossingGateDisposition
    backend_support: ParticipantCrossingGateDisposition
    transformation_validity: ParticipantCrossingGateDisposition

    def dispositions(self) -> tuple[ParticipantCrossingGateDisposition, ...]:
        """Return the complete gate tuple in stable semantic order."""

        return (
            self.caller_authorization,
            self.target_authorization,
            self.participant_authority,
            self.action_admission,
            self.visibility,
            self.marking_authorization,
            self.declassification,
            self.backend_support,
            self.transformation_validity,
        )


class ParticipantCrossingOccurrenceBaseModel(ContractModel):
    """Coordinates shared by every independently addressable crossing fact."""

    direction: ParticipantCrossingDirection
    interaction_kind: ParticipantCrossingInteractionKind
    audience_scope_ref: NonEmptyString
    subject: ParticipantCrossingSubjectReferenceModel
    controller_ref: NonEmptyString
    authority_basis_refs: list[NonEmptyString] = Field(min_length=1)
    policy: ParticipantCrossingPolicyReferenceModel
    effective_order: NonNegativeInteger
    order_model: ParticipantRuntimeOrderingBasis
    backend_posture: ParticipantCrossingBackendPosture
    loss_and_limitations: list[NonEmptyString] = Field(min_length=1)

    @field_validator("authority_basis_refs", "loss_and_limitations")
    @classmethod
    def _require_unique_refs(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("participant crossing references must be unique")
        return values

    @model_validator(mode="after")
    def _validate_policy_order(self) -> ParticipantCrossingOccurrenceBaseModel:
        if not self.policy.valid_from_order <= self.effective_order <= self.policy.valid_until_order:
            raise ValueError("participant crossing order must fall within the policy validity interval")
        if self.policy.effective_order > self.effective_order:
            raise ValueError("participant crossing cannot use a future policy revision")
        return self


class ParticipantCrossingRequestModel(ParticipantCrossingOccurrenceBaseModel):
    """A requested crossing or produced egress candidate, not a decision."""

    stage: Literal["requested"]
    request_id: NonEmptyString
    requested_operation: ParticipantCrossingOperation
    action_or_projection_ref: NonEmptyString
    required_evidence_refs: list[NonEmptyString] = Field(min_length=1)

    @field_validator("required_evidence_refs")
    @classmethod
    def _require_unique_evidence(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("required crossing evidence references must be unique")
        return values


class ParticipantCrossingDecisionModel(ParticipantCrossingOccurrenceBaseModel):
    """The deny-first policy decision for one exact crossing request."""

    stage: Literal["decided"]
    request_ref: NonEmptyString
    decision_id: NonEmptyString
    decision_revision: PositiveInteger
    gates: ParticipantCrossingDecisionGatesModel
    disposition: ParticipantCrossingDecisionDisposition
    reason_code: NonEmptyString
    required_operation: ParticipantCrossingOperation | None = None
    required_evidence_refs: list[NonEmptyString] = Field(min_length=1)
    opacity_enforcement: ParticipantOpacityRuntimeEnforcementBindingModel | None = None

    @model_validator(mode="after")
    def _validate_deny_first_disposition(self) -> ParticipantCrossingDecisionModel:
        failed, unresolved = _classify_gate_dispositions(self.gates)
        _validate_decision_disposition(
            self.disposition,
            failed=failed,
            unresolved=unresolved,
        )
        _validate_required_operation(self.disposition, self.required_operation)
        return self


class ParticipantCrossingTransformationModel(ParticipantCrossingOccurrenceBaseModel):
    """A non-mutating transformation from one typed subject to a new subject."""

    stage: Literal["transformed"]
    decision_ref: NonEmptyString
    transformation_id: NonEmptyString
    operation: Literal[
        ParticipantCrossingOperation.PROJECTION,
        ParticipantCrossingOperation.MASKING,
        ParticipantCrossingOperation.REDACTION,
        ParticipantCrossingOperation.TRANSFORMATION,
        ParticipantCrossingOperation.DECLASSIFICATION,
    ]
    source_subject: ParticipantCrossingSubjectReferenceModel
    result_subject: ParticipantCrossingSubjectReferenceModel
    rule_ref: NonEmptyString
    rule_revision: NonEmptyString
    source_marking_refs: list[NonEmptyString] = Field(min_length=1)
    result_marking_refs: list[NonEmptyString] = Field(min_length=1)
    declassification_basis_ref: NonEmptyString | None = None
    losses: list[ParticipantCrossingLossModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_transformation_shape(self) -> ParticipantCrossingTransformationModel:
        if (self.source_subject.subject_kind, self.source_subject.subject_ref) == (
            self.result_subject.subject_kind,
            self.result_subject.subject_ref,
        ):
            raise ValueError("participant crossing transformation requires a new result identity")
        if self.subject != self.result_subject:
            raise ValueError("participant crossing transformation subject must be its result subject")
        if self.operation == ParticipantCrossingOperation.DECLASSIFICATION and self.declassification_basis_ref is None:
            raise ValueError("declassification requires an explicit authority basis")
        if (
            self.operation != ParticipantCrossingOperation.DECLASSIFICATION
            and self.declassification_basis_ref is not None
        ):
            raise ValueError("declassification_basis_ref is reserved for declassification operations")
        if self.declassification_basis_ref is None and not set(self.source_marking_refs).issubset(
            self.result_marking_refs
        ):
            raise ValueError("transformation results must inherit source markings without declassification")
        return self


class ParticipantCrossingDisclosureModel(ParticipantCrossingOccurrenceBaseModel):
    """An authorized disclosure or declassification decision, not delivery."""

    stage: Literal["disclosed"]
    decision_ref: NonEmptyString
    disclosure_id: NonEmptyString
    operation: Literal[
        ParticipantCrossingOperation.DISCLOSURE,
        ParticipantCrossingOperation.DECLASSIFICATION,
    ]
    transformation_ref: NonEmptyString | None = None
    declassification_basis_ref: NonEmptyString | None = None
    source_marking_refs: list[NonEmptyString] = Field(min_length=1)
    result_marking_refs: list[NonEmptyString] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_disclosure_markings(self) -> ParticipantCrossingDisclosureModel:
        if self.operation == ParticipantCrossingOperation.DECLASSIFICATION and self.declassification_basis_ref is None:
            raise ValueError("declassification disclosure requires an explicit authority basis")
        if (
            self.operation != ParticipantCrossingOperation.DECLASSIFICATION
            and self.declassification_basis_ref is not None
        ):
            raise ValueError("declassification_basis_ref is reserved for declassification operations")
        if self.declassification_basis_ref is None and not set(self.source_marking_refs).issubset(
            self.result_marking_refs
        ):
            raise ValueError("disclosure results must inherit source markings without declassification")
        return self


class ParticipantCrossingDeliveryAttemptModel(ParticipantCrossingOccurrenceBaseModel):
    """An attempted participant delivery, distinct from scheduling and success."""

    stage: Literal["delivery-attempted"]
    decision_ref: NonEmptyString
    transformation_ref: NonEmptyString | None = None
    attempt_id: NonEmptyString
    owning_occurrence_ref: NonEmptyString
    disposition: Literal["attempted", "failed", "withheld", "unsupported"]


class ParticipantCrossingDeliveryModel(ParticipantCrossingOccurrenceBaseModel):
    """A delivered participant-facing occurrence, distinct from observation."""

    stage: Literal["delivered"]
    decision_ref: NonEmptyString
    attempt_ref: NonEmptyString
    delivery_id: NonEmptyString
    owning_occurrence_ref: NonEmptyString
    delivery_order: NonNegativeInteger
    disposition: Literal["delivered", "failed", "unknown", "unsupported"]


class ParticipantCrossingObservationModel(ParticipantCrossingOccurrenceBaseModel):
    """Participant observation of a delivered fact through an incumbent carrier."""

    stage: Literal["observed"]
    decision_ref: NonEmptyString
    delivery_ref: NonEmptyString
    observation_id: NonEmptyString
    owning_observation_ref: NonEmptyString
    observation_order: NonNegativeInteger


class ParticipantCrossingAuditModel(ParticipantCrossingOccurrenceBaseModel):
    """Audit/evidence retention for a prior crossing fact, not participant egress."""

    stage: Literal["audited"]
    audited_event_ref: NonEmptyString
    audit_record_ref: NonEmptyString
    retained_evidence_refs: list[NonEmptyString] = Field(min_length=1)


ParticipantCrossingOccurrenceDetail = Annotated[
    ParticipantCrossingRequestModel
    | ParticipantCrossingDecisionModel
    | ParticipantCrossingTransformationModel
    | ParticipantCrossingDisclosureModel
    | ParticipantCrossingDeliveryAttemptModel
    | ParticipantCrossingDeliveryModel
    | ParticipantCrossingObservationModel
    | ParticipantCrossingAuditModel,
    Field(discriminator="stage"),
]


class ParticipantCrossingOccurrenceModel(ParticipantRuntimeBaseEnvelopeModel):
    """Closed participant-runtime carrier for one API-423 crossing fact."""

    schema_name: Literal["participant-crossing-occurrence"]
    schema_version: Literal["1.0.0"]
    event_type: Literal["participant-crossing-occurrence"]
    extension_policy: Literal["closed"]
    participant_address: NonEmptyString
    episode_id: NonEmptyString
    provenance_refs: list[NonEmptyString] = Field(min_length=1)
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    object_marking_refs: list[NonEmptyString] = Field(min_length=1)
    occurrence: ParticipantCrossingOccurrenceDetail

    @model_validator(mode="after")
    def _validate_subject_scope(self) -> ParticipantCrossingOccurrenceModel:
        subject = self.occurrence.subject
        if (subject.participant_address, subject.episode_id) != (self.participant_address, self.episode_id):
            raise ValueError("participant crossing subject scope must match its occurrence")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        _add_raes_invariant(
            json_schema,
            "participant-crossing-context-agreement",
            "Every crossing fact must resolve typed subjects, exact policy revisions, predecessor stages, "
            "evidence, markings, and order coordinates without retroactive authorization or identity reuse.",
            inputs=[{"contract_id": "participant-crossing-occurrence-v1", "instance_path": "#"}],
        )
        _add_raes_invariant(
            json_schema,
            "participant-crossing-stage-separation",
            "Requested, decided, transformed, disclosed, attempted, delivered, observed, and audited facts "
            "remain independently addressable and do not imply one another.",
            inputs=[{"contract_id": "participant-crossing-occurrence-v1", "instance_path": "#"}],
        )
        return json_schema


__all__ = [
    "ParticipantCrossingAuditModel",
    "ParticipantCrossingBackendPosture",
    "ParticipantCrossingDecisionDisposition",
    "ParticipantCrossingDecisionGatesModel",
    "ParticipantCrossingDecisionModel",
    "ParticipantCrossingDeliveryAttemptModel",
    "ParticipantCrossingDeliveryModel",
    "ParticipantCrossingDirection",
    "ParticipantCrossingDisclosureModel",
    "ParticipantCrossingGateDisposition",
    "ParticipantCrossingInteractionKind",
    "ParticipantCrossingLossKind",
    "ParticipantCrossingLossModel",
    "ParticipantCrossingObservationModel",
    "ParticipantCrossingOccurrenceBaseModel",
    "ParticipantCrossingOccurrenceDetail",
    "ParticipantCrossingOccurrenceModel",
    "ParticipantCrossingOperation",
    "ParticipantOpacityObservationInventoryModel",
    "ParticipantOpacityObservationSurfaceModel",
    "ParticipantOpacityRuntimeEnforcementBindingModel",
    "ParticipantOpacityRuntimeSupportModel",
    "ParticipantCrossingPolicyReferenceModel",
    "ParticipantCrossingRequestModel",
    "ParticipantCrossingSubjectKind",
    "ParticipantCrossingSubjectReferenceModel",
    "ParticipantCrossingTransformationModel",
]
