"""API-409 ``participant-control-occurrence-v2``: one application of a reusable permission.

The v2 lineage carries ``mixed-control-policy-occurrence/rev1`` meaning (ADR-110,
MC-01 to MC-08). An accepted record binds a fresh occurrence to its exact
permitted-transition ref, prior and resulting states and revisions, the acting
source controller, admitted order and evaluated validity. A rejected record
keeps the attempted coordinates apart from the observed cut and asserts no
valid application. v1 records keep their fixed-coordinate interpretation.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Annotated, Literal, get_args

from pydantic import Discriminator, Field, GetJsonSchemaHandler, Tag, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from raes.participant_behavior_specification import MixedControlTransitionKind
from raes.participant_mixed_control_vocabulary import ParticipantControlTargetKind

from .base import ContractModel, NonEmptyString, PrefixedDigestString
from .participant_control import ParticipantControlOccurrenceModel
from .participant_control_coordinates import ControlCount, ControlPosition, ControlRef
from .participant_envelopes import ParticipantRuntimeBaseEnvelopeModel
from .schema_invariants import _add_raes_invariant

PARTICIPANT_CONTROL_OCCURRENCE_V2_CONTRACT_ID = "participant-control-occurrence-v2"
OccurrenceSchemaName = Literal["participant-control-occurrence"]
PARTICIPANT_CONTROL_OCCURRENCE_SCHEMA_NAME: str = get_args(OccurrenceSchemaName)[0]
PARTICIPANT_CONTROL_OCCURRENCE_V2_VERSION = "2.0.0"
ControlRefList = Annotated[list[ControlRef], Field(min_length=1, max_length=256)]
PolicyRevision = Annotated[NonEmptyString, Field(max_length=256, pattern=r"\S")]
_V2 = [{"contract_id": PARTICIPANT_CONTROL_OCCURRENCE_V2_CONTRACT_ID, "instance_path": "#"}]
_MODEL_VALIDATOR = "raes_contracts.contracts.ParticipantControlOccurrenceV2Model"
_REJECTED = "rejected"


class ParticipantControlOccurrenceV2RejectionCode(str, Enum):
    """Closed rejection reasons; the first six keep the incumbent RUN-310 spellings and meanings."""

    STALE_STATE = "stale-state"
    STALE_POLICY = "stale-policy"
    REVOKED_AUTHORITY = "revoked-authority"
    LATE_AUTHORITY = "late-authority"
    UNSUPPORTED_ORDER_STRATEGY = "unsupported-order-strategy"
    INVALID_TARGET = "invalid-target"
    UNKNOWN_TRANSITION = "unknown-transition"
    TRANSITION_KIND_MISMATCH = "transition-kind-mismatch"
    STALE_HISTORY_HEAD = "stale-history-head"
    NON_INCREASING_ORDER = "non-increasing-order"
    CONTROLLER_NOT_SOURCE = "controller-not-source"
    SCOPE_WIDENED = "scope-widened"
    MISSING_EVIDENCE = "missing-evidence"
    COMPLETION_EVIDENCE_REUSED = "completion-evidence-reused"
    PROPOSAL_IDENTITY_REUSED = "proposal-identity-reused"
    DECISION_IDENTITY_REUSED = "decision-identity-reused"
    STALE_TARGET_REVISION = "stale-target-revision"
    PROPOSAL_ALREADY_DECIDED = "proposal-already-decided"
    TARGET_SUPERSEDED = "target-superseded"
    SCRIPT_STEP_MISMATCH = "script-step-mismatch"
    SCRIPT_EXHAUSTED = "script-exhausted"
    EPISODE_NOT_RUNNING = "episode-not-running"
    COORDINATE_OUT_OF_RANGE = "coordinate-out-of-range"


def _require_unique(values: list[str]) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError("participant control references must be unique")
    return values


class ParticipantControlPolicyPinModel(ContractModel):
    """The episode's pinned rev1 policy: owning specification, policy, revision and form."""

    behavior_specification_ref: ControlRef
    policy_ref: ControlRef
    policy_revision: PolicyRevision
    form: Literal["reusable-policy", "finite-script"]


class ParticipantAcceptedOccurrenceV2Model(ContractModel):
    """Exact coordinates of one accepted application of a permitted transition."""

    disposition: Literal["accepted"]
    permitted_transition_ref: ControlRef
    kind: MixedControlTransitionKind
    prior_state_ref: ControlRef
    expected_state_revision: ControlCount
    resulting_state_ref: ControlRef
    resulting_state_revision: ControlCount
    expected_history_head: ControlCount
    occurrence_revision: ControlPosition
    controller_ref: ControlRef
    authority_basis_refs: ControlRefList
    controlled_scope_refs: ControlRefList
    effective_order: ControlCount
    valid_from_order: ControlCount
    valid_until_order: ControlCount
    script_step_ref: ControlRef | None = None
    limitation_refs: ControlRefList

    @field_validator("authority_basis_refs", "controlled_scope_refs", "limitation_refs")
    @classmethod
    def _unique_refs(cls, values: list[str]) -> list[str]:
        return _require_unique(values)

    @model_validator(mode="after")
    def _validate_accepted_arithmetic(self) -> ParticipantAcceptedOccurrenceV2Model:
        if self.resulting_state_revision != self.expected_state_revision + 1:
            raise ValueError("accepted participant control occurrence must advance state revision by exactly one")
        if self.expected_history_head != self.occurrence_revision - 1:
            raise ValueError("accepted participant control occurrence must append at its expected history head")
        if self.valid_until_order < self.valid_from_order:
            raise ValueError("participant control validity interval must not be inverted")
        if not self.valid_from_order <= self.effective_order <= self.valid_until_order:
            raise ValueError("participant control effective order must fall within its validity interval")
        return self


class ParticipantProposalOccurrenceV2Model(ParticipantAcceptedOccurrenceV2Model):
    """A fresh proposal identity bound once per episode, at its own revision 1."""

    kind: Literal[MixedControlTransitionKind.PROPOSAL]
    proposal_id: ControlRef
    proposal_revision: Literal[1]
    admission_status: Literal["not-admitted"]
    action_contract_ref: ControlRef
    decision_surface_ref: ControlRef | None = None
    proposal_binding_ref: ControlRef | None = None
    payload_ref: ControlRef | None = None
    payload_digest: PrefixedDigestString | None = None
    source_proposal_ref: ControlRef | None = None
    source_proposal_revision: ControlPosition | None = None
    transformation_ref: ControlRef | None = None

    @model_validator(mode="after")
    def _validate_proposal_payload_and_transformation(self) -> ParticipantProposalOccurrenceV2Model:
        if (self.payload_ref is None) == (self.payload_digest is None):
            raise ValueError("proposal requires exactly one payload reference or digest")
        transformation = (self.source_proposal_ref, self.source_proposal_revision, self.transformation_ref)
        if any(value is not None for value in transformation) and None in transformation:
            raise ValueError("transformed proposal source identity and transformation ref must be supplied together")
        if self.source_proposal_ref == self.proposal_id:
            raise ValueError("transformed proposal requires a new proposal identity")
        return self


class ParticipantApprovalOccurrenceV2Model(ParticipantAcceptedOccurrenceV2Model):
    """Approval of one live, unresolved proposal at its exact revision."""

    kind: Literal[MixedControlTransitionKind.APPROVAL]
    proposal_ref: ControlRef
    proposal_revision: ControlPosition
    decision_ref: ControlRef
    decision_revision: Literal[1]


class ParticipantDenialOccurrenceV2Model(ParticipantAcceptedOccurrenceV2Model):
    """Denial of one live, unresolved proposal at its exact revision."""

    kind: Literal[MixedControlTransitionKind.DENIAL]
    proposal_ref: ControlRef
    proposal_revision: ControlPosition
    decision_ref: ControlRef
    decision_revision: Literal[1]


class ParticipantExternalDirectionOccurrenceV2Model(ParticipantAcceptedOccurrenceV2Model):
    """A direction to an existing proposal, action or control occurrence."""

    kind: Literal[MixedControlTransitionKind.EXTERNAL_DIRECTION]
    target_kind: Literal[
        ParticipantControlTargetKind.PROPOSAL,
        ParticipantControlTargetKind.ACTION,
        ParticipantControlTargetKind.CONTROL,
    ]
    target_ref: ControlRef
    target_revision: ControlPosition


class ParticipantInterventionOccurrenceV2Model(ParticipantAcceptedOccurrenceV2Model):
    """An intervention against an existing action, control occurrence or attempt."""

    kind: Literal[MixedControlTransitionKind.INTERVENTION]
    affected_target_kind: Literal[
        ParticipantControlTargetKind.ACTION,
        ParticipantControlTargetKind.CONTROL,
        ParticipantControlTargetKind.ATTEMPT,
    ]
    affected_occurrence_ref: ControlRef
    affected_revision: ControlPosition
    intervention_ref: ControlRef


class ParticipantHandoffOccurrenceV2Model(ParticipantAcceptedOccurrenceV2Model):
    """A controller transfer with this transfer's own completion evidence."""

    kind: Literal[MixedControlTransitionKind.HANDOFF]
    completion_evidence_ref: ControlRef


class ParticipantOverrideOccurrenceV2Model(ParticipantAcceptedOccurrenceV2Model):
    """A superseding fact appended against an existing control or decision occurrence."""

    kind: Literal[MixedControlTransitionKind.OVERRIDE]
    superseded_target_kind: Literal[ParticipantControlTargetKind.CONTROL, ParticipantControlTargetKind.DECISION]
    superseded_occurrence_ref: ControlRef
    superseded_revision: ControlPosition
    replacement_ref: ControlRef


class ParticipantCancellationOccurrenceV2Model(ParticipantAcceptedOccurrenceV2Model):
    """A cancellation fact; prevented, partial or late outcomes stay with their evidence authority."""

    kind: Literal[MixedControlTransitionKind.CANCELLATION]
    target_kind: Literal[
        ParticipantControlTargetKind.PROPOSAL,
        ParticipantControlTargetKind.DECISION,
        ParticipantControlTargetKind.ADMITTED_ACTION,
        ParticipantControlTargetKind.ATTEMPT,
    ]
    target_ref: ControlRef
    target_revision: ControlPosition


class ParticipantControlAttemptTargetV2Model(ContractModel):
    """The target an attempt named, exactly as supplied."""

    target_kind: ParticipantControlTargetKind
    target_ref: ControlRef
    target_revision: ControlPosition


class ParticipantControlAttemptV2Model(ContractModel):
    """Attempted coordinates, kept apart from the observed cut (MC-06)."""

    permitted_transition_ref: ControlRef
    kind: MixedControlTransitionKind
    state_ref: ControlRef
    expected_state_revision: ControlCount
    effective_order: ControlCount
    expected_history_head: ControlCount
    controller_ref: ControlRef
    authority_basis_refs: ControlRefList
    controlled_scope_refs: ControlRefList
    script_step_ref: ControlRef | None = None
    target: ParticipantControlAttemptTargetV2Model | None = None

    @field_validator("authority_basis_refs", "controlled_scope_refs")
    @classmethod
    def _unique_refs(cls, values: list[str]) -> list[str]:
        return _require_unique(values)


class ParticipantControlObservedCutV2Model(ContractModel):
    """The accepted control state the attempt was evaluated against."""

    state_ref: ControlRef
    state_revision: ControlCount
    last_accepted_order: ControlCount | None = None
    history_head: ControlCount


class ParticipantRejectedOccurrenceV2Model(ContractModel):
    """A durable rejected attempt: no valid application, no state change and no validity bounds."""

    disposition: Literal["rejected"]
    occurrence_revision: ControlPosition
    reason_code: ParticipantControlOccurrenceV2RejectionCode
    reason_ref: ControlRef | None = None
    attempted: ParticipantControlAttemptV2Model
    observed: ParticipantControlObservedCutV2Model
    state_change: Literal["none"]
    limitation_refs: ControlRefList

    @field_validator("limitation_refs")
    @classmethod
    def _unique_refs(cls, values: list[str]) -> list[str]:
        return _require_unique(values)


def _occurrence_tag(value: object) -> str | None:
    """Select by disposition, then by kind for accepted records; anything else matches no member."""

    read = value.get if isinstance(value, dict) else lambda name: getattr(value, name, None)
    disposition = read("disposition")
    if disposition == _REJECTED:
        return _REJECTED
    kind = read("kind")
    kind = getattr(kind, "value", kind)
    return f"accepted:{kind}" if disposition == "accepted" and isinstance(kind, str) else None


ParticipantControlOccurrenceV2Detail = Annotated[
    Annotated[ParticipantProposalOccurrenceV2Model, Tag("accepted:proposal")]
    | Annotated[ParticipantApprovalOccurrenceV2Model, Tag("accepted:approval")]
    | Annotated[ParticipantDenialOccurrenceV2Model, Tag("accepted:denial")]
    | Annotated[ParticipantExternalDirectionOccurrenceV2Model, Tag("accepted:external-direction")]
    | Annotated[ParticipantInterventionOccurrenceV2Model, Tag("accepted:intervention")]
    | Annotated[ParticipantHandoffOccurrenceV2Model, Tag("accepted:handoff")]
    | Annotated[ParticipantOverrideOccurrenceV2Model, Tag("accepted:override")]
    | Annotated[ParticipantCancellationOccurrenceV2Model, Tag("accepted:cancellation")]
    | Annotated[ParticipantRejectedOccurrenceV2Model, Tag(_REJECTED)],
    Discriminator(
        _occurrence_tag,
        custom_error_type="participant_control_occurrence_v2_disposition",
        custom_error_message="v2 occurrence disposition must be accepted (with a known kind) or rejected",
    ),
]

_INVARIANTS = (
    (
        "participant-control-occurrence-v2-context-agreement",
        "Every v2 occurrence must fold under its episode's exact pinned rev1 policy at its participant-wide "
        "position: exact state, revision and history head, acting source controller and scope, order and windows, "
        "script cursor, target identity, revision, liveness and evaluated validity bounds.",
        "raes_contracts.contracts.validate_participant_control_occurrence_context",
    ),
    (
        "participant-control-occurrence-v2-acting-controller",
        "actor_ref equals the acting controller_ref: the accepted record's, or the rejected attempt's.",
        _MODEL_VALIDATOR,
    ),
    (
        "participant-control-occurrence-v2-revision-advance",
        "An accepted occurrence's resulting_state_revision equals expected_state_revision + 1 for every kind.",
        _MODEL_VALIDATOR,
    ),
    (
        "participant-control-occurrence-v2-history-head",
        "An accepted occurrence's expected_history_head equals occurrence_revision - 1.",
        _MODEL_VALIDATOR,
    ),
    (
        "participant-control-occurrence-v2-validity-bounds",
        "An accepted occurrence satisfies valid_from_order <= effective_order <= valid_until_order (inclusive).",
        _MODEL_VALIDATOR,
    ),
)


class ParticipantControlOccurrenceV2Model(ParticipantRuntimeBaseEnvelopeModel):
    """Closed carrier for one API-409 v2 control fact under a pinned rev1 policy."""

    event_id: ControlRef
    schema_name: OccurrenceSchemaName
    schema_version: Literal["2.0.0"]
    event_type: OccurrenceSchemaName
    extension_policy: Literal["closed"]
    participant_address: ControlRef
    episode_id: ControlRef
    provenance_refs: list[NonEmptyString] = Field(min_length=1)
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    object_marking_refs: list[NonEmptyString] = Field(min_length=1)
    semantics: Literal["mixed-control-policy-occurrence/rev1"]
    policy: ParticipantControlPolicyPinModel
    occurrence: ParticipantControlOccurrenceV2Detail

    @model_validator(mode="after")
    def _validate_actor(self) -> ParticipantControlOccurrenceV2Model:
        occurrence = self.occurrence
        acting = occurrence.attempted if isinstance(occurrence, ParticipantRejectedOccurrenceV2Model) else occurrence
        if self.actor_ref != acting.controller_ref:
            raise ValueError("participant control actor_ref must be the acting controller")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        for invariant_id, description, validator in _INVARIANTS:
            _add_raes_invariant(json_schema, invariant_id, description, validator=validator, inputs=_V2)
        return json_schema


def is_participant_control_occurrence_v2(record: object) -> bool:
    """Return whether ``record`` claims the v2 lineage by its (schema_name, schema_version) pair."""

    return (getattr(record, "schema_name", None), getattr(record, "schema_version", None)) == (
        PARTICIPANT_CONTROL_OCCURRENCE_SCHEMA_NAME,
        PARTICIPANT_CONTROL_OCCURRENCE_V2_VERSION,
    )


def parse_participant_control_occurrence(
    payload: Mapping[str, object],
) -> ParticipantControlOccurrenceModel | ParticipantControlOccurrenceV2Model:
    """Read one stored occurrence with its exact lineage reader; never upgrade v1 or guess a lineage."""

    pair = (payload.get("schema_name"), payload.get("schema_version"))
    if pair == (PARTICIPANT_CONTROL_OCCURRENCE_SCHEMA_NAME, "1.0.0"):
        return ParticipantControlOccurrenceModel.model_validate(payload)
    if pair == (PARTICIPANT_CONTROL_OCCURRENCE_SCHEMA_NAME, PARTICIPANT_CONTROL_OCCURRENCE_V2_VERSION):
        return ParticipantControlOccurrenceV2Model.model_validate(payload)
    raise ValueError("participant control occurrence lineage is unsupported")


__all__ = [
    "PARTICIPANT_CONTROL_OCCURRENCE_V2_CONTRACT_ID",
    "parse_participant_control_occurrence",
    "ParticipantAcceptedOccurrenceV2Model",
    "ParticipantApprovalOccurrenceV2Model",
    "ParticipantCancellationOccurrenceV2Model",
    "ParticipantControlAttemptTargetV2Model",
    "ParticipantControlAttemptV2Model",
    "ParticipantControlObservedCutV2Model",
    "ParticipantControlOccurrenceV2Detail",
    "ParticipantControlOccurrenceV2Model",
    "ParticipantControlOccurrenceV2RejectionCode",
    "ParticipantControlPolicyPinModel",
    "ParticipantDenialOccurrenceV2Model",
    "ParticipantExternalDirectionOccurrenceV2Model",
    "ParticipantHandoffOccurrenceV2Model",
    "ParticipantInterventionOccurrenceV2Model",
    "ParticipantOverrideOccurrenceV2Model",
    "ParticipantProposalOccurrenceV2Model",
    "ParticipantRejectedOccurrenceV2Model",
    "is_participant_control_occurrence_v2",
]
