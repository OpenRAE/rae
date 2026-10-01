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
        _require_unique_membership(self)
        _require_event_position(self)
        _require_coordination_identity(self)
        _require_mapping_identity(self)
        return self


_ACTION_FACT_KINDS = frozenset({"decision", "attempt", "result", "delivery", "observation", "weakening"})
_LIFECYCLE_FACT_KINDS = frozenset({"lifecycle-decision", "lifecycle-attempt", "lifecycle-result"})


def _require_unique_membership(event: MixedCompositionRuntimeEventModel) -> None:
    for name in ("active_component_ids", "active_allocation_ids", "active_edge_ids"):
        values = getattr(event, name)
        if len(values) != len(set(values)):
            raise ValueError(f"{name} must be unique")


def _require_event_position(event: MixedCompositionRuntimeEventModel) -> None:
    initial = event.event_kind == "phase-activated"
    if initial and (event.phase_revision != 0 or event.predecessor_event_id):
        raise ValueError("initial phase fact must have revision zero and no predecessor")
    if not initial and event.predecessor_event_id is None:
        raise ValueError("subsequent composition facts require a predecessor")


def _require_coordination_identity(event: MixedCompositionRuntimeEventModel) -> None:
    action_coordinates = (
        event.allocation_id,
        event.component_id,
        event.control_event_ref,
        event.crossing_event_ref,
        event.policy_decision_ref,
    )
    lifecycle_coordinates = (event.allocation_id, event.component_id, event.control_event_ref)
    if event.event_kind in _ACTION_FACT_KINDS and any(value is None for value in action_coordinates):
        raise ValueError("action coordination facts require exact allocation, component, control, and policy identity")
    if event.event_kind in _LIFECYCLE_FACT_KINDS:
        _require_lifecycle_coordinates(event, lifecycle_coordinates)
    if event.event_kind == "failure":
        _require_failure_coordinates(event, action_coordinates, lifecycle_coordinates)


def _require_lifecycle_coordinates(
    event: MixedCompositionRuntimeEventModel,
    coordinates: tuple[object | None, ...],
) -> None:
    if any(value is None for value in coordinates):
        raise ValueError("lifecycle coordination facts require exact allocation, component, and control identity")
    if event.crossing_event_ref is not None or event.policy_decision_ref is not None:
        raise ValueError("lifecycle coordination facts cannot claim a participant crossing decision")


def _require_failure_coordinates(
    event: MixedCompositionRuntimeEventModel,
    action_coordinates: tuple[object | None, ...],
    lifecycle_coordinates: tuple[object | None, ...],
) -> None:
    action_failure = event.crossing_event_ref is not None or event.policy_decision_ref is not None
    if action_failure and any(value is None for value in action_coordinates):
        raise ValueError("action failure identity must be complete when present")
    lifecycle_failure = event.allocation_id is not None or event.component_id is not None
    if not action_failure and lifecycle_failure and any(value is None for value in lifecycle_coordinates):
        raise ValueError("lifecycle failure identity must be complete when present")


def _require_mapping_identity(event: MixedCompositionRuntimeEventModel) -> None:
    if event.edge_id is None and (event.mapping_ref is not None or event.mapping_loss_refs):
        raise ValueError("mapping facts require an exact composition edge")
    if event.edge_id is not None and event.mapping_ref is None:
        raise ValueError("composition edge facts require an exact time mapping")
    if event.event_kind == "weakening" and not event.mapping_loss_refs:
        raise ValueError("weakening facts require an admitted mapping loss")


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
