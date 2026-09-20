"""Closed apparatus selection of modular participant-control mechanisms."""

from __future__ import annotations

from graphlib import CycleError, TopologicalSorter
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from .base import ContractModel, PrefixedDigestString
from .participant_control_coordinates import (
    ControlArtifactReferenceModel,
    ControlCount,
    ControlRef,
    ControlRefs,
    Evidence,
    ResultKind,
    require_kind,
    require_unique,
)
from .participant_control_profiles import validate_control_profile_reference
from .participant_crossing_vocab import ParticipantCrossingSubjectKind


class ControlApplicabilityModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    participant_address: ControlRef
    episode_id: ControlRef
    direction: Literal["ingress", "egress"]
    sink_ref: ControlRef
    phase_ref: ControlRef
    subject_kind: ParticipantCrossingSubjectKind


class ControlMechanismBindingModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    instance_id: ControlRef
    profiles: Evidence
    mechanism: ControlArtifactReferenceModel
    protocol_revision: Literal["participant-control-provider/v1"]
    implementation: ControlArtifactReferenceModel
    configuration_digest: PrefixedDigestString
    authority: ControlArtifactReferenceModel
    memory_scope: ControlArtifactReferenceModel
    applicability: Annotated[tuple[ControlApplicabilityModel, ...], Field(min_length=1, max_length=256)]
    evidence: Evidence
    limitations: Evidence

    @model_validator(mode="after")
    def _binding(self):
        for name, kind in (
            ("mechanism", "mechanism"),
            ("implementation", "implementation"),
            ("authority", "authority"),
            ("memory_scope", "memory"),
        ):
            require_kind(getattr(self, name), kind)
        for name, kind in (("profiles", "profile"), ("evidence", "evidence"), ("limitations", "limitation")):
            values = getattr(self, name)
            require_unique(values)
            for value in values:
                require_kind(value, kind)
        require_unique(self.applicability)
        for profile in self.profiles:
            validate_control_profile_reference(profile)
        require_unique(tuple(profile.ref for profile in self.profiles))
        return self


class ControlSlotDependencyModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    slot_id: ControlRef
    kind: ResultKind


class ControlResultSlotModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    slot_id: ControlRef
    instance_id: ControlRef
    kind: ResultKind
    role: Literal["mandatory", "advisory"]
    dependencies: Annotated[tuple[ControlSlotDependencyModel, ...], Field(max_length=256)]


class ControlCausalBoundsModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    max_depth: ControlCount
    max_effects: ControlCount
    max_fanout: ControlCount
    max_firings_per_rule: ControlCount
    max_attempts: ControlCount
    expires_at_order: ControlCount


class ParticipantControlSelectionModel(ContractModel):
    """Exact finite selection; this document cannot install a provider."""

    model_config = ConfigDict(frozen=True)
    schema_version: Literal["participant-control-selection/v1"]
    selection_id: ControlRef
    semantic_revision: Literal["sem-235/rev1"]
    apparatus: ControlArtifactReferenceModel
    required_profiles: ControlRefs
    bindings: Annotated[tuple[ControlMechanismBindingModel, ...], Field(max_length=64)]
    slots: Annotated[tuple[ControlResultSlotModel, ...], Field(max_length=256)]
    bounds: ControlCausalBoundsModel
    evidence: Evidence

    @model_validator(mode="after")
    def _selection_graph(self):
        require_kind(self.apparatus, "apparatus")
        require_unique(self.required_profiles)
        require_unique(tuple(binding.instance_id for binding in self.bindings))
        require_unique(tuple(slot.slot_id for slot in self.slots))
        profiles = {profile.ref for binding in self.bindings for profile in binding.profiles}
        if not set(self.required_profiles) <= profiles:
            raise ValueError("required participant control profile is absent")
        instances = {binding.instance_id for binding in self.bindings}
        slots = {slot.slot_id: slot for slot in self.slots}
        graph = {}
        for slot in self.slots:
            if slot.instance_id not in instances:
                raise ValueError("participant control slot instance is absent")
            require_unique(tuple(dep.slot_id for dep in slot.dependencies))
            for dep in slot.dependencies:
                if dep.slot_id not in slots or slots[dep.slot_id].kind != dep.kind:
                    raise ValueError("participant control dependency is absent or mistyped")
            graph[slot.slot_id] = tuple(dep.slot_id for dep in slot.dependencies)
        try:
            tuple(TopologicalSorter(graph).static_order())
        except CycleError:
            raise ValueError("participant control dependency cycle") from None
        return self
