"""Immutable API-424 coordinates; references never load executable code."""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, StrictInt, model_validator

from .base import ContractModel, NonEmptyString, PrefixedDigestString
from .participant_crossing import ParticipantCrossingPolicyReferenceModel, ParticipantCrossingSubjectReferenceModel
from .participant_decision_state_cut import (
    ParticipantDecisionSurfaceCausalCutModel,
    ParticipantDecisionSurfaceSequenceCutModel,
)

ControlRef = Annotated[NonEmptyString, Field(max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/@-]*$")]
ControlCount = Annotated[StrictInt, Field(ge=0, le=1_000_000)]
ControlRefs = Annotated[tuple[ControlRef, ...], Field(max_length=256)]
ResultKind = Literal["ifc-fact", "decision", "advisory", "effect-request"]
ResolutionStatus = Literal["resolved", "missing", "unknown", "unsupported", "stale", "failed", "weakened"]


class ControlArtifactReferenceModel(ContractModel):
    """Exact out-of-line artifact coordinate, not an artifact/evidence payload."""

    model_config = ConfigDict(frozen=True)
    kind: Literal[
        "profile",
        "mechanism",
        "implementation",
        "authority",
        "evidence",
        "limitation",
        "memory",
        "apparatus",
        "run",
        "crossing",
        "history",
        "provider-state",
        "input",
        "clock",
        "trigger",
        "rule",
        "inject-delivery",
        "disclosure",
        "manifest",
        "installation",
        "control",
        "transformation",
        "action",
        "lifecycle",
        "audit",
        "receipt",
        "projection",
        "policy",
        "constraint",
        "flow-relation",
    ]
    ref: ControlRef
    revision: ControlRef
    digest: PrefixedDigestString


Artifacts = Annotated[tuple[ControlArtifactReferenceModel, ...], Field(max_length=256)]
Evidence = Annotated[tuple[ControlArtifactReferenceModel, ...], Field(min_length=1, max_length=256)]


def require_kind(reference: ControlArtifactReferenceModel, kind: str) -> None:
    if reference.kind != kind:
        raise ValueError("participant control reference has the wrong owning kind")


def require_unique(values: Sequence[Hashable], label: str = "participant control identities") -> None:
    if len(values) != len(set(values)):
        raise ValueError(label + " must be unique")


class ControlSubjectReferenceModel(ParticipantCrossingSubjectReferenceModel):
    """Frozen specialization of the incumbent crossing subject coordinate."""

    model_config = ConfigDict(frozen=True)
    contract_id: ControlRef
    subject_ref: ControlRef
    subject_revision: ControlRef
    participant_address: ControlRef
    episode_id: ControlRef


class ControlPolicyReferenceModel(ParticipantCrossingPolicyReferenceModel):
    model_config = ConfigDict(frozen=True)
    policy_id: ControlRef
    policy_revision: ControlRef
    policy_decision_ref: ControlRef
    decision_cut_ref: ControlRef
    effective_order: ControlCount
    valid_from_order: ControlCount
    valid_until_order: ControlCount


class ControlSequenceCutModel(ParticipantDecisionSurfaceSequenceCutModel):
    model_config = ConfigDict(frozen=True)
    cut_ref: ControlRef
    anchor_event_ref: ControlRef
    anchor_order: ControlCount
    history_prefix_length: Annotated[StrictInt, Field(ge=1, le=1_000_001)]
    predecessor_event_refs: ControlRefs = ()


class ControlCausalCutModel(ParticipantDecisionSurfaceCausalCutModel):
    model_config = ConfigDict(frozen=True)
    cut_ref: ControlRef
    history_domain: ControlRef
    predecessor_closure_ref: ControlRef
    frontier_event_refs: Annotated[tuple[ControlRef, ...], Field(min_length=1, max_length=256)]


ControlCut = Annotated[ControlSequenceCutModel | ControlCausalCutModel, Field(discriminator="cut_kind")]


class ControlProviderStateModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    instance_id: ControlRef
    state: ControlArtifactReferenceModel

    @model_validator(mode="after")
    def _owner(self) -> Self:
        require_kind(self.state, "provider-state")
        return self


class ControlRuleFiringsModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    rule_id: ControlRef
    rule_revision: ControlRef
    firing_epochs: ControlRefs

    @model_validator(mode="after")
    def _epochs(self) -> Self:
        require_unique(self.firing_epochs)
        return self


class ControlLogicalEffectKeyModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    run_ref: ControlRef
    trigger_root: ControlRef
    rule_id: ControlRef
    rule_revision: ControlRef
    slot: ControlRef
    firing_epoch: ControlRef


class ControlPriorEffectClaimModel(ContractModel):
    """A retained logical claim, authenticated through the admitted context."""

    model_config = ConfigDict(frozen=True)
    effect_id: ControlRef
    key: ControlLogicalEffectKeyModel
    content_digest: PrefixedDigestString


class ParticipantControlContextModel(ContractModel):
    """MPC-03 exact context. No private state, prompt, or native handle."""

    model_config = ConfigDict(frozen=True)
    run: ControlArtifactReferenceModel
    apparatus: ControlArtifactReferenceModel
    participant_address: ControlRef
    episode_id: ControlRef
    subject: ControlSubjectReferenceModel
    crossing: ControlArtifactReferenceModel
    direction: Literal["ingress", "egress"]
    sink_ref: ControlRef
    audience_ref: ControlRef
    destination_ref: ControlRef
    controller_ref: ControlRef
    authority: ControlArtifactReferenceModel
    policy: ControlPolicyReferenceModel
    state_cut: ControlCut
    expected_history_heads: Evidence
    provider_states: Annotated[tuple[ControlProviderStateModel, ...], Field(max_length=64)]
    inputs: Artifacts
    memory_scope: ControlArtifactReferenceModel
    clock: ControlArtifactReferenceModel
    order: ControlCount
    phase_ref: ControlRef
    trigger_root: ControlRef
    trigger: ControlArtifactReferenceModel
    predecessors: Artifacts
    depth: ControlCount
    effects_consumed: ControlCount
    prior_effect_claims: Annotated[tuple[ControlPriorEffectClaimModel, ...], Field(max_length=256)]
    rule_firings: Annotated[tuple[ControlRuleFiringsModel, ...], Field(max_length=256)]
    attempt: Annotated[StrictInt, Field(ge=1, le=1_000_000)]

    @model_validator(mode="after")
    def _coordinates(self) -> Self:
        for name, kind in (
            ("run", "run"),
            ("apparatus", "apparatus"),
            ("crossing", "crossing"),
            ("authority", "authority"),
            ("memory_scope", "memory"),
            ("clock", "clock"),
            ("trigger", "trigger"),
        ):
            require_kind(getattr(self, name), kind)
        if (self.subject.participant_address, self.subject.episode_id) != (self.participant_address, self.episode_id):
            raise ValueError("participant control subject scope differs from context")
        if self.policy.decision_cut_ref != self.state_cut.cut_ref:
            raise ValueError("participant control policy and state cut differ")
        if (
            not self.policy.valid_from_order
            <= self.policy.effective_order
            <= self.order
            <= self.policy.valid_until_order
        ):
            raise ValueError("participant control policy is outside its admitted order")
        require_unique(tuple(state.instance_id for state in self.provider_states))
        self._retained_claims()
        for name in ("expected_history_heads", "inputs", "predecessors"):
            require_unique(getattr(self, name))
        for head in self.expected_history_heads:
            require_kind(head, "history")
        return self

    def _retained_claims(self) -> None:
        require_unique(tuple((state.rule_id, state.rule_revision) for state in self.rule_firings))
        require_unique(tuple(claim.effect_id for claim in self.prior_effect_claims))
        require_unique(tuple(claim.key for claim in self.prior_effect_claims))
        if len(self.prior_effect_claims) > self.effects_consumed:
            raise ValueError("prior effect claims exceed retained consumption")
        epochs = {(state.rule_id, state.rule_revision): set(state.firing_epochs) for state in self.rule_firings}
        for claim in self.prior_effect_claims:
            if (claim.key.run_ref, claim.key.trigger_root) != (self.run.ref, self.trigger_root):
                raise ValueError("prior effect claim has a different causal root")
            if claim.key.firing_epoch not in epochs.get((claim.key.rule_id, claim.key.rule_revision), set()):
                raise ValueError("prior effect claim is missing its retained firing epoch")
