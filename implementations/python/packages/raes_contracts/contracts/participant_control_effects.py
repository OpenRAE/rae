"""MPC-09 typed requests binding existing effect owners; no executor."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from .base import ContractModel
from .participant_control_coordinates import (
    ControlArtifactReferenceModel,
    ControlCount,
    ControlLogicalEffectKeyModel,
    ControlRef,
    ControlRefs,
    ControlSubjectReferenceModel,
    Evidence,
    require_kind,
    require_unique,
)


class ControlCrossingEffectModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["permit", "deny", "withhold"]
    crossing_decision: ControlArtifactReferenceModel
    subject: ControlSubjectReferenceModel

    @model_validator(mode="after")
    def _owner(self) -> Self:
        require_kind(self.crossing_decision, "crossing")
        return self


class ControlTransformationEffectModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["transform", "mask", "route"]
    transformation: ControlArtifactReferenceModel
    source: ControlSubjectReferenceModel
    result: ControlSubjectReferenceModel
    destination_ref: ControlRef
    admission_policy: ControlArtifactReferenceModel

    @model_validator(mode="after")
    def _fresh_subject(self) -> Self:
        require_kind(self.transformation, "transformation")
        require_kind(self.admission_policy, "policy")
        if self.source.subject_ref == self.result.subject_ref:
            raise ValueError("participant control transformation requires fresh subject identity")
        return self


class ControlInjectEffectModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["inject"]
    delivery_ref: ControlArtifactReferenceModel
    inject_ref: ControlRef
    event_ref: ControlRef
    script_ref: ControlRef
    story_ref: ControlRef
    source_item_ref: ControlRef
    result_item_ref: ControlRef
    participant_address: ControlRef
    episode_id: ControlRef
    disclosure_ref: ControlArtifactReferenceModel

    @model_validator(mode="after")
    def _inject(self) -> Self:
        require_kind(self.delivery_ref, "inject-delivery")
        require_kind(self.disclosure_ref, "disclosure")
        if self.source_item_ref == self.result_item_ref:
            raise ValueError("participant control inject requires fresh result identity")
        return self


class ControlDelayEffectModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["delay"]
    subject: ControlSubjectReferenceModel
    clock: ControlArtifactReferenceModel
    earliest_order: ControlCount
    latest_order: ControlCount
    expiry_order: ControlCount
    resumption_policy: ControlArtifactReferenceModel

    @model_validator(mode="after")
    def _window(self) -> Self:
        require_kind(self.clock, "clock")
        require_kind(self.resumption_policy, "policy")
        if not self.earliest_order <= self.latest_order <= self.expiry_order:
            raise ValueError("participant control delay window is inverted or expired")
        return self


class ControlHandoffEffectModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["handoff"]
    transition: ControlArtifactReferenceModel
    participant_address: ControlRef
    episode_id: ControlRef
    prior_controller_ref: ControlRef
    resulting_controller_ref: ControlRef
    expected_state_revision: ControlCount
    completion_obligation: ControlArtifactReferenceModel

    @model_validator(mode="after")
    def _owner(self) -> Self:
        require_kind(self.transition, "control")
        require_kind(self.completion_obligation, "evidence")
        if self.prior_controller_ref == self.resulting_controller_ref:
            raise ValueError("handoff requires a changed controller")
        return self


class ControlReviewEffectModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["request-review"]
    parent: ControlSubjectReferenceModel
    obligation_ref: ControlRef
    supervisor_authority: ControlArtifactReferenceModel
    approval_ref: ControlArtifactReferenceModel
    denial_ref: ControlArtifactReferenceModel
    clock: ControlArtifactReferenceModel
    expiry_order: ControlCount
    resumption_policy: ControlArtifactReferenceModel

    @model_validator(mode="after")
    def _owner(self) -> Self:
        for name, kind in (
            ("supervisor_authority", "authority"),
            ("approval_ref", "control"),
            ("denial_ref", "control"),
            ("clock", "clock"),
            ("resumption_policy", "policy"),
        ):
            require_kind(getattr(self, name), kind)
        if self.approval_ref == self.denial_ref:
            raise ValueError("review approval and denial must be distinct")
        return self


class ControlLifecycleEffectModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["interrupt", "shutdown"]
    target_kind: Literal["participant", "episode", "execution", "workflow", "run"]
    target_ref: ControlRef
    operation: Literal["pause", "cancel", "interrupt", "terminate"]
    lifecycle_authority: ControlArtifactReferenceModel
    expected_revision: ControlRef

    @model_validator(mode="after")
    def _operation(self) -> Self:
        require_kind(self.lifecycle_authority, "authority")
        if (self.kind == "shutdown") != (self.operation == "terminate"):
            raise ValueError("participant control lifecycle kind and operation disagree")
        return self


class ControlAuditEffectModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["audit"]
    subject: ControlSubjectReferenceModel
    audit_record: ControlArtifactReferenceModel
    audience_ref: ControlRef
    retention_policy: ControlArtifactReferenceModel

    @model_validator(mode="after")
    def _owner(self) -> Self:
        require_kind(self.audit_record, "audit")
        require_kind(self.retention_policy, "policy")
        return self


ControlEffectTarget = Annotated[
    ControlCrossingEffectModel
    | ControlTransformationEffectModel
    | ControlInjectEffectModel
    | ControlDelayEffectModel
    | ControlHandoffEffectModel
    | ControlReviewEffectModel
    | ControlLifecycleEffectModel
    | ControlAuditEffectModel,
    Field(discriminator="kind"),
]


class ControlEffectRequestModel(ContractModel):
    """One logical requested effect, independent of retry/cut/transport identity."""

    model_config = ConfigDict(frozen=True)
    kind: Literal["effect-request"]
    effect_id: ControlRef
    key: ControlLogicalEffectKeyModel
    rule: ControlArtifactReferenceModel
    authority: ControlArtifactReferenceModel
    phase: Literal["required-predecessor", "subsequent"]
    predecessor_effect_ids: ControlRefs
    target: ControlEffectTarget
    evidence: Evidence

    @model_validator(mode="after")
    def _identity(self) -> Self:
        require_kind(self.rule, "rule")
        require_kind(self.authority, "authority")
        if (self.key.rule_id, self.key.rule_revision) != (self.rule.ref, self.rule.revision):
            raise ValueError("participant control effect key and rule disagree")
        require_unique(self.predecessor_effect_ids)
        if self.effect_id in self.predecessor_effect_ids:
            raise ValueError("participant control effect cannot precede itself")
        return self
