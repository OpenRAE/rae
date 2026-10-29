"""Trusted, non-wire inputs to API-409 v2 contextual validation.

``ParticipantControlOccurrencePolicyModel`` is the episode's pinned rev1 policy
projection, the v2 counterpart of ``ParticipantControlDeclarationModel``; the
compiler builds it from compiled policy children. ``ParticipantControlOccurrenceTarget``
is an owner-supplied target with the participant-wide position after which it
exists. Neither is a published contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Self

from pydantic import Field, model_validator
from raes.participant_mixed_control_vocabulary import MixedControlTransitionKind, ParticipantControlTargetKind

from .base import ContractModel, NonEmptyString
from .participant_control_coordinates import ControlCount, ControlRef
from .participant_control_occurrence_v2 import ControlRefList, ParticipantControlPolicyPinModel


class ParticipantControlPolicyStateModel(ContractModel):
    """One controller state with its canonical controller, grant, scope and order window."""

    state_ref: ControlRef
    controller_ref: ControlRef
    authority_basis_refs: ControlRefList
    scope_refs: ControlRefList
    authority_status: Literal["active", "revoked"]
    valid_from_order: ControlCount
    valid_until_order: ControlCount


class ParticipantControlPolicyTransitionModel(ContractModel):
    """One reusable permission and the MC-05 target kinds it admits."""

    transition_ref: ControlRef
    kind: MixedControlTransitionKind
    from_state_ref: ControlRef
    to_state_ref: ControlRef
    valid_from_order: ControlCount
    valid_until_order: ControlCount
    target_kinds: list[ParticipantControlTargetKind] = Field(default_factory=list)


class ParticipantControlPolicyStepModel(ContractModel):
    """One finite-script step; every optional field narrows its transition."""

    step_ref: ControlRef
    transition_ref: ControlRef
    expected_state_revision: ControlCount | None = None
    valid_from_order: ControlCount | None = None
    valid_until_order: ControlCount | None = None
    target_kind: ParticipantControlTargetKind | None = None
    target_step_ref: ControlRef | None = None


class ParticipantControlOccurrencePolicyModel(ContractModel):
    """The pinned rev1 policy of one participant episode, resolved to canonical addresses."""

    semantics: Literal["mixed-control-policy-occurrence/rev1"]
    participant_address: ControlRef
    episode_id: ControlRef
    pin: ParticipantControlPolicyPinModel
    order_strategy: NonEmptyString
    initial_state_ref: ControlRef
    behavior_scope_refs: ControlRefList
    states: list[ParticipantControlPolicyStateModel] = Field(min_length=1)
    transitions: list[ParticipantControlPolicyTransitionModel] = Field(min_length=1)
    script_steps: list[ParticipantControlPolicyStepModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_projection(self) -> Self:
        states = {state.state_ref for state in self.states}
        transitions = {transition.transition_ref for transition in self.transitions}
        steps = [step.step_ref for step in self.script_steps]
        if (
            len(states) != len(self.states)
            or len(transitions) != len(self.transitions)
            or len(set(steps)) != len(steps)
        ):
            raise ValueError("participant control policy projection identities must be unique")
        if self.initial_state_ref not in states or any(
            {transition.from_state_ref, transition.to_state_ref} - states for transition in self.transitions
        ):
            raise ValueError("participant control policy projection state refs must resolve")
        if (self.pin.form == "finite-script") != bool(self.script_steps):
            raise ValueError("participant control policy projection has script steps exactly when finite-script")
        if any(step.transition_ref not in transitions for step in self.script_steps):
            raise ValueError("participant control policy projection step refs must resolve")
        return self

    def state(self, state_ref: str) -> ParticipantControlPolicyStateModel:
        """Return one controller state by its canonical ref."""

        return next(state for state in self.states if state.state_ref == state_ref)

    def transition(self, transition_ref: str) -> ParticipantControlPolicyTransitionModel | None:
        """Return one permitted transition, or ``None`` for a ref the policy does not declare."""

        return next((item for item in self.transitions if item.transition_ref == transition_ref), None)

    def step(self, step_ref: str | None) -> ParticipantControlPolicyStepModel | None:
        """Return one finite-script step, or ``None``."""

        return next((step for step in self.script_steps if step.step_ref == step_ref), None)


@dataclass(frozen=True)
class ParticipantControlOccurrenceTarget:
    """Owner-supplied target; eligible at position ``p`` only when ``available_at < p``."""

    target_kind: ParticipantControlTargetKind
    target_ref: str
    target_revision: int
    participant_address: str
    episode_id: str
    available_at: int


def participant_control_validity_bounds(
    policy: ParticipantControlOccurrencePolicyModel,
    transition_ref: str,
    step_ref: str | None = None,
) -> tuple[int, int] | None:
    """Return the evaluated window: edge, step, source-state and destination-state windows intersected.

    ``None`` means the ref does not resolve or the windows do not intersect.
    """

    transition = policy.transition(transition_ref)
    if transition is None:
        return None
    windows = [
        (transition.valid_from_order, transition.valid_until_order),
        *(
            (state.valid_from_order, state.valid_until_order)
            for state in (policy.state(transition.from_state_ref), policy.state(transition.to_state_ref))
        ),
    ]
    step = policy.step(step_ref)
    if step is not None and step.valid_from_order is not None and step.valid_until_order is not None:
        windows.append((step.valid_from_order, step.valid_until_order))
    low = max(window[0] for window in windows)
    high = min(window[1] for window in windows)
    return (low, high) if low <= high else None


__all__ = [
    "ParticipantControlOccurrencePolicyModel",
    "ParticipantControlOccurrenceTarget",
    "ParticipantControlPolicyStateModel",
    "ParticipantControlPolicyStepModel",
    "ParticipantControlPolicyTransitionModel",
    "participant_control_validity_bounds",
]
