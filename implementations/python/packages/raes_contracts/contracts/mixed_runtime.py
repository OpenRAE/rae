"""Closed, value-free facts for one admitted mixed composition at runtime."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonEmptyString, PrefixedDigestString

_EventKind = Literal[
    "phase-activated",
    "phase-transition",
    "decision",
    "attempt",
    "result",
    "lifecycle-decision",
    "lifecycle-attempt",
    "lifecycle-result",
    "delivery",
    "observation",
    "handoff",
    "weakening",
    "failure",
]
_Disposition = Literal["committed", "permitted", "denied", "succeeded", "failed", "indeterminate"]


class MixedCompositionRuntimeEventModel(ContractModel):
    """One append-only phase or coordination fact, never a copied payload."""

    event_id: NonEmptyString
    event_kind: _EventKind
    run_id: NonEmptyString
    plan_id: NonEmptyString
    plan_entry_id: NonEmptyString
    profile_id: NonEmptyString
    profile_digest: PrefixedDigestString
    phase_id: NonEmptyString
    phase_revision: int = Field(ge=0)
    active_component_ids: list[NonEmptyString] = Field(min_length=1, max_length=64)
    active_allocation_ids: list[NonEmptyString] = Field(min_length=1, max_length=1024)
    active_edge_ids: list[NonEmptyString] = Field(default_factory=list, max_length=1024)
    disposition: _Disposition
    predecessor_event_id: NonEmptyString | None = None
    allocation_id: NonEmptyString | None = None
    component_id: NonEmptyString | None = None
    edge_id: NonEmptyString | None = None
    control_event_ref: NonEmptyString | None = None
    crossing_event_ref: NonEmptyString | None = None
    policy_decision_ref: NonEmptyString | None = None
    mapping_ref: NonEmptyString | None = None
    order_ref: NonEmptyString
    mapping_loss_refs: list[NonEmptyString] = Field(default_factory=list, max_length=64)
    evidence_refs: list[NonEmptyString] = Field(default_factory=list, max_length=64)
    provenance_refs: list[NonEmptyString] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def _validate_identity(self) -> MixedCompositionRuntimeEventModel:
        for name in ("active_component_ids", "active_allocation_ids", "active_edge_ids"):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must be unique")
        if self.event_kind == "phase-activated" and (self.phase_revision != 0 or self.predecessor_event_id):
            raise ValueError("initial phase fact must have revision zero and no predecessor")
        if self.event_kind != "phase-activated" and self.predecessor_event_id is None:
            raise ValueError("subsequent composition facts require a predecessor")
        action_fact = self.event_kind in {
            "decision",
            "attempt",
            "result",
            "delivery",
            "observation",
            "weakening",
        }
        action_coordinates = (
            self.allocation_id,
            self.component_id,
            self.control_event_ref,
            self.crossing_event_ref,
            self.policy_decision_ref,
        )
        if action_fact and any(value is None for value in action_coordinates):
            raise ValueError(
                "action coordination facts require exact allocation, component, control, and policy identity"
            )
        lifecycle_fact = self.event_kind in {
            "lifecycle-decision",
            "lifecycle-attempt",
            "lifecycle-result",
        }
        lifecycle_coordinates = (
            self.allocation_id,
            self.component_id,
            self.control_event_ref,
        )
        if lifecycle_fact and any(value is None for value in lifecycle_coordinates):
            raise ValueError("lifecycle coordination facts require exact allocation, component, and control identity")
        if lifecycle_fact and (self.crossing_event_ref is not None or self.policy_decision_ref is not None):
            raise ValueError("lifecycle coordination facts cannot claim a participant crossing decision")
        if self.event_kind == "failure":
            if self.crossing_event_ref is not None or self.policy_decision_ref is not None:
                if any(value is None for value in action_coordinates):
                    raise ValueError("action failure identity must be complete when present")
            elif (self.allocation_id is not None or self.component_id is not None) and any(
                value is None for value in lifecycle_coordinates
            ):
                raise ValueError("lifecycle failure identity must be complete when present")
        if self.edge_id is None and (self.mapping_ref is not None or self.mapping_loss_refs):
            raise ValueError("mapping facts require an exact composition edge")
        if self.edge_id is not None and self.mapping_ref is None:
            raise ValueError("composition edge facts require an exact time mapping")
        if self.event_kind == "weakening" and not self.mapping_loss_refs:
            raise ValueError("weakening facts require an admitted mapping loss")
        return self


class MixedCompositionRuntimeStateModel(ContractModel):
    """The current phase fold over a validated append-only event chain."""

    run_id: NonEmptyString
    plan_id: NonEmptyString
    plan_entry_id: NonEmptyString
    profile_id: NonEmptyString
    profile_digest: PrefixedDigestString
    phase_id: NonEmptyString
    phase_revision: int = Field(ge=0)
    active_component_ids: list[NonEmptyString] = Field(min_length=1, max_length=64)
    active_allocation_ids: list[NonEmptyString] = Field(min_length=1, max_length=1024)
    active_edge_ids: list[NonEmptyString] = Field(default_factory=list, max_length=1024)
    history_head: NonEmptyString
