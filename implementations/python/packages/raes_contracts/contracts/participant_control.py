"""API-409 portable participant control-occurrence contracts."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from raes.participant_mixed_control_vocabulary import MixedControlTransitionKind, ParticipantControlTargetKind

from .base import (
    ContractModel,
    NonEmptyString,
    NonNegativeInteger,
    PositiveInteger,
    PrefixedDigestString,
)
from .participant_envelopes import ParticipantRuntimeBaseEnvelopeModel
from .schema_invariants import _add_raes_invariant


class ParticipantControlDisposition(str, Enum):
    """Realized disposition of one portable control occurrence."""

    RECORDED = "recorded"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    LIMITED = "limited"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class ParticipantCancellationEffect(str, Enum):
    """What remained cancellable when the occurrence was recorded."""

    PREVENTED = "prevented"
    PARTIAL_LIMITATION = "partial-limitation"
    TOO_LATE = "too-late"


class ParticipantControlOccurrenceBaseModel(ContractModel):
    """Coordinates shared by every API-409 control occurrence."""

    declaration_ref: NonEmptyString
    controller_ref: NonEmptyString
    controller_state_ref: NonEmptyString
    authority_basis_refs: list[NonEmptyString] = Field(min_length=1)
    controlled_scope_refs: list[NonEmptyString] = Field(min_length=1)
    behavior_specification_ref: NonEmptyString
    mixed_control_policy_ref: NonEmptyString
    policy_revision: NonEmptyString
    expected_state_revision: NonNegativeInteger
    effective_order: NonNegativeInteger
    valid_from_order: NonNegativeInteger
    valid_until_order: NonNegativeInteger
    occurrence_revision: PositiveInteger
    disposition: ParticipantControlDisposition
    reason_code: NonEmptyString | None = None
    reason_ref: NonEmptyString | None = None
    limitation_refs: list[NonEmptyString] = Field(min_length=1)

    @field_validator("authority_basis_refs", "controlled_scope_refs", "limitation_refs")
    @classmethod
    def _require_unique_refs(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("participant control references must be unique")
        return values

    @model_validator(mode="after")
    def _validate_effective_interval(self) -> ParticipantControlOccurrenceBaseModel:
        if self.valid_until_order < self.valid_from_order:
            raise ValueError("participant control validity interval must not be inverted")
        if not self.valid_from_order <= self.effective_order <= self.valid_until_order:
            raise ValueError("participant control effective order must fall within its validity interval")
        return self


class ParticipantControlDeclarationModel(ContractModel):
    """Compiled ACT-617 coordinates used to validate an occurrence join."""

    declaration_ref: NonEmptyString
    kind: MixedControlTransitionKind
    participant_address: NonEmptyString
    episode_id: NonEmptyString
    controller_ref: NonEmptyString
    controller_state_ref: NonEmptyString
    authority_basis_refs: list[NonEmptyString] = Field(min_length=1)
    controlled_scope_refs: list[NonEmptyString] = Field(min_length=1)
    behavior_specification_ref: NonEmptyString
    mixed_control_policy_ref: NonEmptyString
    policy_revision: NonEmptyString
    expected_state_revision: NonNegativeInteger
    effective_order: NonNegativeInteger
    valid_from_order: NonNegativeInteger
    valid_until_order: NonNegativeInteger

    @field_validator("authority_basis_refs", "controlled_scope_refs")
    @classmethod
    def _require_unique_refs(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("participant control declaration references must be unique")
        return values

    @model_validator(mode="after")
    def _validate_effective_interval(self) -> ParticipantControlDeclarationModel:
        if self.valid_until_order < self.valid_from_order:
            raise ValueError("participant control declaration validity interval must not be inverted")
        if not self.valid_from_order <= self.effective_order <= self.valid_until_order:
            raise ValueError("participant control declaration order must fall within its validity interval")
        return self


class ParticipantControlTargetContextModel(ContractModel):
    """Typed revision and scope coordinates for one referenced control target."""

    target_kind: ParticipantControlTargetKind
    target_ref: NonEmptyString
    target_revision: PositiveInteger
    participant_address: NonEmptyString
    episode_id: NonEmptyString


class ParticipantProposalOccurrenceModel(ParticipantControlOccurrenceBaseModel):
    """A proposal fact that is neither a decision, admission, nor execution."""

    kind: Literal[MixedControlTransitionKind.PROPOSAL]
    proposal_id: NonEmptyString
    proposal_revision: PositiveInteger
    admission_status: Literal["not-admitted"]
    action_contract_ref: NonEmptyString
    decision_surface_ref: NonEmptyString | None = None
    proposal_binding_ref: NonEmptyString | None = None
    payload_ref: NonEmptyString | None = None
    payload_digest: PrefixedDigestString | None = None
    source_proposal_ref: NonEmptyString | None = None
    source_proposal_revision: PositiveInteger | None = None
    transformation_ref: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_proposal_payload_and_transformation(self) -> ParticipantProposalOccurrenceModel:
        if (self.payload_ref is None) == (self.payload_digest is None):
            raise ValueError("proposal requires exactly one payload reference or digest")
        transformation_values = (
            self.source_proposal_ref,
            self.source_proposal_revision,
            self.transformation_ref,
        )
        if any(value is not None for value in transformation_values) and not all(
            value is not None for value in transformation_values
        ):
            raise ValueError("transformed proposal source identity and transformation ref must be supplied together")
        if self.source_proposal_ref == self.proposal_id:
            raise ValueError("transformed proposal requires a new proposal identity")
        return self


class ParticipantApprovalOccurrenceModel(ParticipantControlOccurrenceBaseModel):
    """Approval of exactly one proposal revision, before action admission."""

    kind: Literal[MixedControlTransitionKind.APPROVAL]
    proposal_ref: NonEmptyString
    proposal_revision: PositiveInteger
    decision_ref: NonEmptyString
    decision_revision: PositiveInteger


class ParticipantDenialOccurrenceModel(ParticipantControlOccurrenceBaseModel):
    """Denial of exactly one proposal revision."""

    kind: Literal[MixedControlTransitionKind.DENIAL]
    proposal_ref: NonEmptyString
    proposal_revision: PositiveInteger
    decision_ref: NonEmptyString
    decision_revision: PositiveInteger


class ParticipantExternalDirectionOccurrenceModel(ParticipantControlOccurrenceBaseModel):
    """A scoped direction that does not bypass proposal validation or admission."""

    kind: Literal[MixedControlTransitionKind.EXTERNAL_DIRECTION]
    target_kind: Literal[
        ParticipantControlTargetKind.PROPOSAL,
        ParticipantControlTargetKind.ACTION,
        ParticipantControlTargetKind.CONTROL,
    ]
    target_ref: NonEmptyString
    target_revision: PositiveInteger


class ParticipantInterventionOccurrenceModel(ParticipantControlOccurrenceBaseModel):
    """An intervention against an existing control or action occurrence."""

    kind: Literal[MixedControlTransitionKind.INTERVENTION]
    affected_target_kind: Literal[
        ParticipantControlTargetKind.ACTION,
        ParticipantControlTargetKind.CONTROL,
        ParticipantControlTargetKind.ATTEMPT,
    ]
    affected_occurrence_ref: NonEmptyString
    affected_revision: PositiveInteger
    intervention_ref: NonEmptyString


class ParticipantHandoffOccurrenceModel(ParticipantControlOccurrenceBaseModel):
    """A controller-state handoff that preserves participant identity."""

    kind: Literal[MixedControlTransitionKind.HANDOFF]
    prior_controller_state_ref: NonEmptyString
    resulting_controller_state_ref: NonEmptyString
    resulting_state_revision: PositiveInteger
    completion_evidence_ref: NonEmptyString

    @model_validator(mode="after")
    def _validate_handoff_revision(self) -> ParticipantHandoffOccurrenceModel:
        if self.resulting_state_revision != self.expected_state_revision + 1:
            raise ValueError("handoff must advance controller-state revision by exactly one")
        return self


class ParticipantOverrideOccurrenceModel(ParticipantControlOccurrenceBaseModel):
    """An override that supersedes rather than rewrites an earlier occurrence."""

    kind: Literal[MixedControlTransitionKind.OVERRIDE]
    superseded_target_kind: Literal[
        ParticipantControlTargetKind.CONTROL,
        ParticipantControlTargetKind.DECISION,
    ]
    superseded_occurrence_ref: NonEmptyString
    superseded_revision: PositiveInteger
    replacement_ref: NonEmptyString


class ParticipantCancellationOccurrenceModel(ParticipantControlOccurrenceBaseModel):
    """A cancellation with an explicit non-retroactive effect."""

    kind: Literal[MixedControlTransitionKind.CANCELLATION]
    target_kind: Literal[
        ParticipantControlTargetKind.PROPOSAL,
        ParticipantControlTargetKind.DECISION,
        ParticipantControlTargetKind.ADMITTED_ACTION,
        ParticipantControlTargetKind.ATTEMPT,
    ]
    target_ref: NonEmptyString
    target_revision: PositiveInteger
    cancellation_effect: ParticipantCancellationEffect


ParticipantControlOccurrenceDetail = Annotated[
    ParticipantProposalOccurrenceModel
    | ParticipantApprovalOccurrenceModel
    | ParticipantDenialOccurrenceModel
    | ParticipantExternalDirectionOccurrenceModel
    | ParticipantInterventionOccurrenceModel
    | ParticipantHandoffOccurrenceModel
    | ParticipantOverrideOccurrenceModel
    | ParticipantCancellationOccurrenceModel,
    Field(discriminator="kind"),
]


class ParticipantControlOccurrenceModel(ParticipantRuntimeBaseEnvelopeModel):
    """Closed participant-runtime carrier for one API-409 control fact."""

    schema_name: Literal["participant-control-occurrence"]
    schema_version: Literal["1.0.0"]
    event_type: Literal["participant-control-occurrence"]
    extension_policy: Literal["closed"]
    participant_address: NonEmptyString
    episode_id: NonEmptyString
    provenance_refs: list[NonEmptyString] = Field(min_length=1)
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    object_marking_refs: list[NonEmptyString] = Field(min_length=1)
    occurrence: ParticipantControlOccurrenceDetail

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
            "participant-control-occurrence-context-agreement",
            "Every occurrence must resolve one matching compiled ACT-617 declaration and preserve participant, "
            "episode, controller, authority, policy revision, order, proposal, target, and semantic identity joins.",
            inputs=[{"contract_id": "participant-control-occurrence-v1", "instance_path": "#"}],
        )
        _add_raes_invariant(
            json_schema,
            "participant-control-occurrence-not-lifecycle-evidence",
            "Proposal, approval, denial, direction, intervention, handoff, override, and cancellation remain "
            "distinct from action admission, execution, delivery, observation, and audit evidence.",
            inputs=[{"contract_id": "participant-control-occurrence-v1", "instance_path": "#"}],
        )
        return json_schema


__all__ = [
    "ParticipantApprovalOccurrenceModel",
    "ParticipantCancellationEffect",
    "ParticipantCancellationOccurrenceModel",
    "ParticipantControlDisposition",
    "ParticipantControlDeclarationModel",
    "ParticipantControlOccurrenceBaseModel",
    "ParticipantControlOccurrenceDetail",
    "ParticipantControlOccurrenceModel",
    "ParticipantControlTargetContextModel",
    "ParticipantControlTargetKind",
    "ParticipantDenialOccurrenceModel",
    "ParticipantExternalDirectionOccurrenceModel",
    "ParticipantHandoffOccurrenceModel",
    "ParticipantInterventionOccurrenceModel",
    "ParticipantOverrideOccurrenceModel",
    "ParticipantProposalOccurrenceModel",
]
