"""Versioned API-424 apparatus and exact-cut applicability records.

These records describe an admitted evaluation. They do not install a provider
or make an untrusted applicability proof authoritative.
"""

from __future__ import annotations

from graphlib import TopologicalSorter
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from .base import ContractModel, PrefixedDigestString
from .participant_control_composition import control_digest
from .participant_control_coordinates import (
    Artifacts,
    ControlArtifactReferenceModel,
    ControlRef,
    ControlRefs,
    Evidence,
    ParticipantControlContextModel,
    ResultKind,
    require_kind,
    require_unique,
)
from .participant_control_selection import (
    ControlMechanismBindingModel,
    ControlResultSlotModel,
    ParticipantControlSelectionModel,
)


class ControlStateScopeV2Model(ContractModel):
    """Admitted sharing scope, distinct from participant memory and profile."""

    model_config = ConfigDict(frozen=True)
    scope_id: ControlRef
    sharing: Literal["run", "participant", "episode"]
    authority: ControlArtifactReferenceModel
    configuration_digest: PrefixedDigestString

    @model_validator(mode="after")
    def _authority(self) -> Self:
        require_kind(self.authority, "authority")
        return self


class ControlMechanismBindingV2Model(ControlMechanismBindingModel):
    protocol_revision: Literal["participant-control-provider/v2"]
    state_scope: ControlStateScopeV2Model

    @model_validator(mode="after")
    def _scope_binding(self) -> Self:
        if (
            self.state_scope.authority != self.authority
            or self.state_scope.configuration_digest != self.configuration_digest
        ):
            raise ValueError("participant control state scope differs from its binding")
        return self


class ControlProfileObligationV2Model(ContractModel):
    """Profile-owned obligation declared before any provider result exists."""

    model_config = ConfigDict(frozen=True)
    obligation_id: ControlRef
    profile: ControlArtifactReferenceModel
    required_kind: ResultKind
    required_strength: Literal["exact", "bounded", "disclosed_weak"]
    constraints: Artifacts

    @model_validator(mode="after")
    def _owner(self) -> Self:
        require_kind(self.profile, "profile")
        for constraint in self.constraints:
            require_kind(constraint, "constraint")
        if self.required_strength == "bounded" and not self.constraints:
            raise ValueError("bounded obligation requires admitted constraints")
        return self


class ControlResultSlotV2Model(ControlResultSlotModel):
    """Admitted required-input support pin, independent of provider claims."""

    required_strength: Literal["exact", "bounded", "disclosed_weak"] = "exact"
    constraints: Artifacts = ()

    @model_validator(mode="after")
    def _support_pin(self) -> Self:
        for item in self.constraints:
            require_kind(item, "constraint")
        if self.required_strength == "bounded" and not self.constraints:
            raise ValueError("bounded slot support requires admitted constraints")
        return self


class ParticipantControlSelectionV2Model(ParticipantControlSelectionModel):
    """Complete B; no exact-cut filtering changes this identity."""

    schema_version: Literal["participant-control-selection/v2"]
    interpretation: Literal["participant-control-applicability/rev1"]
    bindings: Annotated[tuple[ControlMechanismBindingV2Model, ...], Field(max_length=64)]
    slots: Annotated[tuple[ControlResultSlotV2Model, ...], Field(max_length=256)]
    obligations: Annotated[tuple[ControlProfileObligationV2Model, ...], Field(max_length=256)]

    @model_validator(mode="after")
    def _obligation_owners(self) -> Self:
        require_unique(tuple(item.obligation_id for item in self.obligations))
        selected = {profile for binding in self.bindings for profile in binding.profiles}
        declared = {item.profile for item in self.obligations}
        if not {profile for profile in selected if profile.ref in self.required_profiles} <= declared:
            raise ValueError("required participant control profile has no obligations")
        if any(item.profile not in selected for item in self.obligations):
            raise ValueError("participant control obligation profile is not admitted")
        return self


class ControlObligationCoverageV2Model(ContractModel):
    model_config = ConfigDict(frozen=True)
    obligation_id: ControlRef
    status: Literal["applies", "proven-inapplicable", "unresolved"]
    slot_ids: ControlRefs
    evidence: Evidence

    @model_validator(mode="after")
    def _discharge(self) -> Self:
        require_unique(self.slot_ids)
        if (self.status == "applies") != bool(self.slot_ids):
            raise ValueError("participant control coverage has no valid slot discharge")
        return self


class ControlApplicabilityV2Model(ContractModel):
    model_config = ConfigDict(frozen=True)
    selection_digest: PrefixedDigestString
    context_digest: PrefixedDigestString
    applicable_slot_ids: ControlRefs
    required_slot_ids: ControlRefs
    coverage: Annotated[tuple[ControlObligationCoverageV2Model, ...], Field(max_length=256)]
    derivation_evidence: Evidence


class ParticipantControlRequestV2Model(ContractModel):
    """Exact K plus A(B,K), with B and total profile coverage retained."""

    model_config = ConfigDict(frozen=True)
    selection: ParticipantControlSelectionV2Model
    context: ParticipantControlContextModel
    applicability: ControlApplicabilityV2Model

    @model_validator(mode="after")
    def _exact_cut(self) -> Self:
        _validate_request_identity(self)
        _validate_required_closure(self)
        _validate_coverage(self)
        _validate_context_bindings(self)
        _validate_causal_bounds(self)
        return self


def _validate_request_identity(request: ParticipantControlRequestV2Model) -> None:
    selection, context, applicability = request.selection, request.context, request.applicability
    if selection.apparatus != context.apparatus:
        raise ValueError("participant control apparatus binding differs")
    if applicability.selection_digest != control_digest(selection) or applicability.context_digest != control_digest(
        context
    ):
        raise ValueError("participant control applicability has a different admitted identity or cut")


def _validate_coverage(request: ParticipantControlRequestV2Model) -> None:
    selection, applicability = request.selection, request.applicability
    slots = {slot.slot_id: slot for slot in selection.slots}
    bindings = {binding.instance_id: binding for binding in selection.bindings}
    obligations = {item.obligation_id: item for item in selection.obligations}
    coverage = {item.obligation_id: item for item in applicability.coverage}
    require_unique(tuple(item.obligation_id for item in applicability.coverage))
    if coverage.keys() != obligations.keys():
        raise ValueError("participant control coverage is incomplete")
    applicable = set(applicability.applicable_slot_ids)
    for item in applicability.coverage:
        if item.status == "applies":
            obligation = obligations[item.obligation_id]
            for identity in item.slot_ids:
                if identity not in applicable or slots[identity].kind != obligation.required_kind:
                    raise ValueError("participant control coverage does not map to an applicable typed slot")
                if obligation.profile not in bindings[slots[identity].instance_id].profiles:
                    raise ValueError("participant control coverage slot does not select its owning profile")


def _coverage_roots(request: ParticipantControlRequestV2Model) -> set[str]:
    applicable = set(request.applicability.applicable_slot_ids)
    roots = {
        slot_id for item in request.applicability.coverage if item.status == "applies" for slot_id in item.slot_ids
    }
    roots.update(
        slot.slot_id for slot in request.selection.slots if slot.role == "mandatory" and slot.slot_id in applicable
    )
    return roots


def _validate_required_closure(request: ParticipantControlRequestV2Model) -> None:
    applicability = request.applicability
    slots = {slot.slot_id: slot for slot in request.selection.slots}
    applicable = set(applicability.applicable_slot_ids)
    required = set(applicability.required_slot_ids)
    require_unique(applicability.applicable_slot_ids)
    require_unique(applicability.required_slot_ids)
    if applicable - slots.keys() or required - applicable:
        raise ValueError("participant control applicable slots are not admitted")
    roots = _coverage_roots(request)
    graph = {slot.slot_id: {dep.slot_id for dep in slot.dependencies} for slot in request.selection.slots}
    for identity in reversed(tuple(TopologicalSorter(graph).static_order())):
        if identity in roots:
            roots.update(graph[identity])
    if roots != required or any(not graph[identity] <= applicable for identity in applicable):
        raise ValueError("participant control required input closure or applicable subset is incomplete")


def _validate_context_bindings(request: ParticipantControlRequestV2Model) -> None:
    selection, context, applicability = request.selection, request.context, request.applicability
    slots = {slot.slot_id: slot for slot in selection.slots}
    bindings = {binding.instance_id: binding for binding in selection.bindings}
    matching_instances = {slots[identity].instance_id for identity in applicability.applicable_slot_ids}
    if {state.instance_id for state in context.provider_states} != matching_instances:
        raise ValueError("participant control provider-state coverage is incomplete")
    for instance in matching_instances:
        binding = bindings[instance]
        if binding.memory_scope != context.memory_scope or not any(
            (a.participant_address, a.episode_id, a.direction, a.sink_ref, a.phase_ref, a.subject_kind)
            == (
                context.participant_address,
                context.episode_id,
                context.direction,
                context.sink_ref,
                context.phase_ref,
                context.subject.subject_kind,
            )
            for a in binding.applicability
        ):
            raise ValueError("participant control applicable binding does not match the exact crossing")


def _validate_causal_bounds(request: ParticipantControlRequestV2Model) -> None:
    context, bounds = request.context, request.selection.bounds
    if (
        context.depth > bounds.max_depth
        or context.effects_consumed > bounds.max_effects
        or context.attempt > bounds.max_attempts
        or context.order > bounds.expires_at_order
    ):
        raise ValueError("participant control causal bounds are exhausted")
