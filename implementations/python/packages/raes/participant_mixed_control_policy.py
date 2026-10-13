"""Reusable mixed-control policies and finite scripts (ACT-617, MC-01 and MC-02).

A rev1 policy is selected only by the required
``semantics: mixed-control-policy-occurrence/rev1`` pin and by its required
``form``. Its permitted transitions are reusable permissions: they carry no
fixed state revision, effective order or proposal identity, so one edge can be
applied any number of times. Each application is a separate API-409
``participant-control-occurrence-v2`` occurrence. A finite script pins an
ordered list of steps over those edges.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StrictInt, field_validator, model_validator

from ._base import SDLModel
from ._identifiers import PortableIdentifier
from .participant_mixed_control_vocabulary import (
    MIXED_CONTROL_COORDINATE_LIMIT,
    MixedControlControllerState,
    MixedControlDispositionRules,
    MixedControlOrderStrategy,
    MixedControlTransitionKind,
    ParticipantControlTargetKind,
)

MIXED_CONTROL_POLICY_SEMANTICS = "mixed-control-policy-occurrence/rev1"
MixedControlCoordinate = Annotated[StrictInt, Field(ge=0, le=MIXED_CONTROL_COORDINATE_LIMIT)]
MixedControlRef = Annotated[str, Field(min_length=1, pattern=r"\S")]
_UNIQUE_REFS = {"uniqueItems": True}

MIXED_CONTROL_KIND_TARGETS: dict[MixedControlTransitionKind, frozenset[ParticipantControlTargetKind]] = {
    MixedControlTransitionKind.PROPOSAL: frozenset(),
    MixedControlTransitionKind.APPROVAL: frozenset({ParticipantControlTargetKind.PROPOSAL}),
    MixedControlTransitionKind.DENIAL: frozenset({ParticipantControlTargetKind.PROPOSAL}),
    MixedControlTransitionKind.EXTERNAL_DIRECTION: frozenset(
        {
            ParticipantControlTargetKind.PROPOSAL,
            ParticipantControlTargetKind.ACTION,
            ParticipantControlTargetKind.CONTROL,
        }
    ),
    MixedControlTransitionKind.INTERVENTION: frozenset(
        {
            ParticipantControlTargetKind.ACTION,
            ParticipantControlTargetKind.CONTROL,
            ParticipantControlTargetKind.ATTEMPT,
        }
    ),
    MixedControlTransitionKind.HANDOFF: frozenset(),
    MixedControlTransitionKind.OVERRIDE: frozenset(
        {ParticipantControlTargetKind.CONTROL, ParticipantControlTargetKind.DECISION}
    ),
    MixedControlTransitionKind.CANCELLATION: frozenset(
        {
            ParticipantControlTargetKind.PROPOSAL,
            ParticipantControlTargetKind.DECISION,
            ParticipantControlTargetKind.ADMITTED_ACTION,
            ParticipantControlTargetKind.ATTEMPT,
        }
    ),
}
"""The closed MC-05 target set of each kind; a direction edge narrows its own set with ``target_kinds``."""


def _require_unique(values: list[str], label: str) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError(f"mixed-control {label} must be unique")
    return values


class MixedControlPolicyControllerState(MixedControlControllerState):
    """Legacy controller-state binding whose order window fits the MC-08 range."""

    valid_from_order: MixedControlCoordinate
    valid_until_order: MixedControlCoordinate


class _MixedControlEdgeBase(SDLModel):
    """One reusable permission: kind, source/destination states, window and evidence."""

    transition_kind: MixedControlTransitionKind
    from_state_ref: PortableIdentifier
    to_state_ref: PortableIdentifier
    valid_from_order: MixedControlCoordinate
    valid_until_order: MixedControlCoordinate
    evidence_refs: list[MixedControlRef] = Field(min_length=1, json_schema_extra=_UNIQUE_REFS)

    @field_validator("evidence_refs")
    @classmethod
    def _unique_evidence(cls, values: list[str]) -> list[str]:
        return _require_unique(values, "permitted-transition evidence refs")

    @model_validator(mode="after")
    def _validate_window(self) -> _MixedControlEdgeBase:
        if self.valid_until_order < self.valid_from_order:
            raise ValueError("mixed-control permitted-transition window must not be inverted")
        return self

    def target_kinds_allowed(self) -> frozenset[ParticipantControlTargetKind]:
        """Return the MC-05 target kinds this edge permits."""

        return MIXED_CONTROL_KIND_TARGETS[MixedControlTransitionKind(self.transition_kind)]


class MixedControlProposalEdge(_MixedControlEdgeBase):
    """Permission to record a fresh proposal occurrence."""

    transition_kind: Literal[MixedControlTransitionKind.PROPOSAL]


class MixedControlApprovalEdge(_MixedControlEdgeBase):
    """Permission to approve one live, unresolved proposal."""

    transition_kind: Literal[MixedControlTransitionKind.APPROVAL]


class MixedControlDenialEdge(_MixedControlEdgeBase):
    """Permission to deny one live, unresolved proposal."""

    transition_kind: Literal[MixedControlTransitionKind.DENIAL]


DirectionTargetKind = Literal[
    ParticipantControlTargetKind.PROPOSAL,
    ParticipantControlTargetKind.ACTION,
    ParticipantControlTargetKind.CONTROL,
]


class MixedControlExternalDirectionEdge(_MixedControlEdgeBase):
    """Permission to direct an existing proposal, action or control occurrence."""

    transition_kind: Literal[MixedControlTransitionKind.EXTERNAL_DIRECTION]
    target_kinds: list[DirectionTargetKind] = Field(min_length=1, json_schema_extra=_UNIQUE_REFS)

    @field_validator("target_kinds")
    @classmethod
    def _unique_target_kinds(cls, values: list[ParticipantControlTargetKind]) -> list[ParticipantControlTargetKind]:
        if len(set(values)) != len(values):
            raise ValueError("mixed-control direction target_kinds must be unique")
        return values

    def target_kinds_allowed(self) -> frozenset[ParticipantControlTargetKind]:
        return frozenset(ParticipantControlTargetKind(kind) for kind in self.target_kinds)


class MixedControlInterventionEdge(_MixedControlEdgeBase):
    """Permission to intervene in an existing action, control occurrence or attempt."""

    transition_kind: Literal[MixedControlTransitionKind.INTERVENTION]


class MixedControlHandoffEdge(_MixedControlEdgeBase):
    """Permission to transfer control; each transfer supplies its own completion evidence."""

    transition_kind: Literal[MixedControlTransitionKind.HANDOFF]
    completion_evidence_refs: list[MixedControlRef] = Field(min_length=1, json_schema_extra=_UNIQUE_REFS)

    @field_validator("completion_evidence_refs")
    @classmethod
    def _unique_completion_evidence(cls, values: list[str]) -> list[str]:
        return _require_unique(values, "completion evidence refs")


class MixedControlOverrideEdge(_MixedControlEdgeBase):
    """Permission to supersede an existing control or decision occurrence."""

    transition_kind: Literal[MixedControlTransitionKind.OVERRIDE]


class MixedControlCancellationEdge(_MixedControlEdgeBase):
    """Permission to cancel an existing proposal, decision, admitted action or attempt."""

    transition_kind: Literal[MixedControlTransitionKind.CANCELLATION]


MixedControlPermittedTransition = Annotated[
    MixedControlProposalEdge
    | MixedControlApprovalEdge
    | MixedControlDenialEdge
    | MixedControlExternalDirectionEdge
    | MixedControlInterventionEdge
    | MixedControlHandoffEdge
    | MixedControlOverrideEdge
    | MixedControlCancellationEdge,
    Field(discriminator="transition_kind"),
]


class MixedControlScriptStep(SDLModel):
    """One finite-script step; it may only narrow its permitted transition."""

    step_id: PortableIdentifier
    permitted_transition_ref: PortableIdentifier
    expected_state_revision: MixedControlCoordinate | None = None
    valid_from_order: MixedControlCoordinate | None = None
    valid_until_order: MixedControlCoordinate | None = None
    target_kind: ParticipantControlTargetKind | None = None
    target_step_ref: PortableIdentifier | None = None

    @model_validator(mode="after")
    def _validate_step_window(self) -> MixedControlScriptStep:
        if (self.valid_from_order is None) != (self.valid_until_order is None):
            raise ValueError("mixed-control script step window requires both valid_from_order and valid_until_order")
        if self.valid_from_order is not None and self.valid_until_order < self.valid_from_order:
            raise ValueError("mixed-control script step window must not be inverted")
        if self.target_step_ref == self.step_id:
            raise ValueError("mixed-control script step cannot target itself")
        return self


class _MixedControlPolicyBase(SDLModel):
    """Fields shared by the reusable-policy and finite-script forms."""

    semantics: Literal["mixed-control-policy-occurrence/rev1"]
    form: str
    participant_ref: str
    policy_revision: str
    order_strategy: MixedControlOrderStrategy
    initial_state_ref: PortableIdentifier
    dispositions: MixedControlDispositionRules
    controller_states: dict[PortableIdentifier, MixedControlPolicyControllerState] = Field(min_length=1)
    permitted_transitions: dict[PortableIdentifier, MixedControlPermittedTransition] = Field(min_length=1)

    @field_validator("participant_ref", "policy_revision")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mixed-control participant and policy revision must be non-empty")
        return value

    @model_validator(mode="after")
    def _validate_policy_graph(self) -> _MixedControlPolicyBase:
        if self.initial_state_ref not in self.controller_states:
            raise ValueError("mixed_control initial_state_ref must resolve to controller_states")
        for state_id, state in self.controller_states.items():
            if state.policy_revision != self.policy_revision:
                raise ValueError(f"mixed-control controller state '{state_id}' has a stale policy revision")
        for transition_id, transition in self.permitted_transitions.items():
            if any(ref not in self.controller_states for ref in (transition.from_state_ref, transition.to_state_ref)):
                raise ValueError(
                    f"mixed-control permitted transition '{transition_id}' has an unknown controller-state ref"
                )
        return self


class ReusableMixedControlPolicy(_MixedControlPolicyBase):
    """Permits any finite trace its edges and the ordinary gates admit; no edge schedules itself."""

    form: Literal["reusable-policy"]


class FiniteScriptMixedControlPolicy(_MixedControlPolicyBase):
    """Pins an ordered list of distinct steps; exhaustion admits no further application."""

    form: Literal["finite-script"]
    script_steps: list[MixedControlScriptStep] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_script(self) -> FiniteScriptMixedControlPolicy:
        step_ids = [step.step_id for step in self.script_steps]
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("mixed-control script step identities must be distinct")
        for step in self.script_steps:
            if step.permitted_transition_ref not in self.permitted_transitions:
                raise ValueError(f"mixed-control script step '{step.step_id}' names an unknown permitted transition")
        return self


MixedControlPolicy = Annotated[
    ReusableMixedControlPolicy | FiniteScriptMixedControlPolicy,
    Field(discriminator="form"),
]


def mixed_control_policy_semantics(declaration: object) -> str:
    """Return the explicit interpretation pin of one authored ``mixed_control`` value."""

    return MIXED_CONTROL_POLICY_SEMANTICS if isinstance(declaration, _MixedControlPolicyBase) else ""


__all__ = [
    "MIXED_CONTROL_KIND_TARGETS",
    "MIXED_CONTROL_POLICY_SEMANTICS",
    "DirectionTargetKind",
    "FiniteScriptMixedControlPolicy",
    "MixedControlApprovalEdge",
    "MixedControlCancellationEdge",
    "MixedControlCoordinate",
    "MixedControlDenialEdge",
    "MixedControlExternalDirectionEdge",
    "MixedControlHandoffEdge",
    "MixedControlInterventionEdge",
    "MixedControlOverrideEdge",
    "MixedControlPermittedTransition",
    "MixedControlPolicy",
    "MixedControlPolicyControllerState",
    "MixedControlProposalEdge",
    "MixedControlScriptStep",
    "ReusableMixedControlPolicy",
    "mixed_control_policy_semantics",
]
