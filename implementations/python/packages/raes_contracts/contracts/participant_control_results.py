"""Typed mechanism facts, decisions and advice remain distinct from effects."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StrictFloat, model_validator

from .base import ContractModel, PrefixedDigestString
from .participant_control_coordinates import (
    Artifacts,
    ControlArtifactReferenceModel,
    ControlRef,
    ControlRefs,
    Evidence,
    ResolutionStatus,
    require_kind,
    require_unique,
)
from .participant_control_effects import ControlEffectRequestModel


class ControlTeachingFactModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["ifc-fact"]
    domain: Literal["teaching-influence-domain/rev1"]
    tokens: Annotated[tuple[Literal["coached-hint", "worked-example"], ...], Field(max_length=2)]
    source_refs: Evidence

    @model_validator(mode="after")
    def _canonical_tokens(self):
        if self.tokens != tuple(sorted(set(self.tokens))):
            raise ValueError("teaching influence tokens must be canonical and unique")
        return self


class ControlSecurityFactModel(ContractModel):
    """Reference the exact incumbent SEM-233 label and owning relation."""

    model_config = ConfigDict(frozen=True)
    kind: Literal["ifc-fact"]
    domain: Literal["sem-233/rev1"]
    relation: ControlArtifactReferenceModel
    label_ref: ControlRef

    @model_validator(mode="after")
    def _owner(self):
        require_kind(self.relation, "flow-relation")
        return self


ControlIFCFact = Annotated[ControlTeachingFactModel | ControlSecurityFactModel, Field(discriminator="domain")]


class ControlDecisionModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["decision"]
    disposition: Literal["permit", "deny", "withhold", "abstain"]
    rule: ControlArtifactReferenceModel

    @model_validator(mode="after")
    def _owner(self):
        require_kind(self.rule, "rule")
        return self


class ControlAdvisoryModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["advisory"]
    assessment: Literal["positive", "negative", "abstain"]
    score: Annotated[StrictFloat, Field(ge=0, le=1, allow_inf_nan=False)]
    sample: ControlArtifactReferenceModel


ControlResultPayload = Annotated[
    ControlIFCFact | ControlDecisionModel | ControlAdvisoryModel | ControlEffectRequestModel,
    Field(discriminator="kind"),
]


class ControlMechanismResultModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    result_id: ControlRef
    slot_id: ControlRef
    instance_id: ControlRef
    binding_digest: PrefixedDigestString
    context_digest: PrefixedDigestString
    status: ResolutionStatus
    payload: ControlResultPayload | None
    evidence: Evidence
    next_provider_state: ControlArtifactReferenceModel | None

    @model_validator(mode="after")
    def _resolved_payload(self):
        if (self.status == "resolved") != (self.payload is not None):
            raise ValueError("only a resolved mechanism result carries a typed payload")
        if self.next_provider_state is not None:
            require_kind(self.next_provider_state, "provider-state")
            if self.status != "resolved":
                raise ValueError("unresolved results cannot propose provider state")
        return self


class ControlEffectiveSupportModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    instance_id: ControlRef
    feature: Literal["participant_modular_control"]
    declaration_ref: ControlArtifactReferenceModel
    declared_level: Literal["exact", "bounded", "disclosed_weak", "unsupported"]
    effective_level: Literal["exact", "bounded", "disclosed_weak", "unsupported"]
    status: ResolutionStatus
    context_digest: PrefixedDigestString
    installation: ControlArtifactReferenceModel | None
    constraints: Artifacts
    limitations: Evidence
    evidence: Evidence
    downgrade_authority: ControlArtifactReferenceModel | None

    @model_validator(mode="after")
    def _strength(self):
        levels = ("unsupported", "disclosed_weak", "bounded", "exact")
        require_kind(self.declaration_ref, "manifest")
        if levels.index(self.effective_level) > levels.index(self.declared_level):
            raise ValueError("effective support cannot exceed declared support")
        if self.effective_level != "unsupported" and self.installation is None:
            raise ValueError("positive effective support requires an installed binding")
        if self.installation is not None:
            require_kind(self.installation, "installation")
        for item in self.constraints:
            require_kind(item, "constraint")
        for item in self.limitations:
            require_kind(item, "limitation")
        if self.effective_level == "bounded" and not self.constraints:
            raise ValueError("bounded support requires constraints")
        if self.downgrade_authority is not None:
            require_kind(self.downgrade_authority, "authority")
            if self.effective_level in {"unsupported", "exact"}:
                raise ValueError("unsupported or exact support is not an authorized downgrade")
        return self


class ControlCompositionModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    rule_revision: Literal["sem-235/rev1"]
    disposition: Literal["eligible", "deny", "withhold", "unsupported", "stale", "failed", "weakened", "conflict"]
    blockers: ControlRefs
    contributing_result_ids: ControlRefs
    incumbent_gate_disposition: Literal["permit", "deny", "withhold", "unsupported", "stale", "failed"]
    incumbent_gate_evidence: ControlArtifactReferenceModel

    @model_validator(mode="after")
    def _contributors(self):
        require_unique(self.contributing_result_ids)
        if self.blockers != tuple(sorted(set(self.blockers))):
            raise ValueError("composition blockers must be canonical and unique")
        return self


class ControlRealizationBindingModel(ContractModel):
    """An out-of-line owner outcome, never a provider result or permission."""

    model_config = ConfigDict(frozen=True)
    effect_id: ControlRef
    disposition: Literal["applied", "failed", "indeterminate", "unsupported", "withheld"]
    receipt: ControlArtifactReferenceModel
    evidence: Evidence

    @model_validator(mode="after")
    def _receipt(self):
        require_kind(self.receipt, "receipt")
        return self
