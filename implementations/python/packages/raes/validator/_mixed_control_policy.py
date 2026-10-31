"""Semantic validation for rev1 reusable mixed-control policies (ACT-617, MC-01 to MC-05)."""

from __future__ import annotations

from raes_contracts.participant_mixed_control_vocabulary import (
    MixedControlAuthorityStatus,
    MixedControlControllerState,
    MixedControlTransitionKind,
    ParticipantControlTargetKind,
)

from .._reference_targetability import ReferencePurpose
from ..participant_behavior_specification import ParticipantBehaviorSpecification
from ..participant_mixed_control_policy import (
    MixedControlPermittedTransition,
    MixedControlPolicy,
    MixedControlScriptStep,
)
from ._mixed_control import transition_pointer

_Policy = MixedControlPolicy
_REVOKED = MixedControlAuthorityStatus.REVOKED
_PROPOSAL = MixedControlTransitionKind.PROPOSAL
_DECIDING = frozenset({MixedControlTransitionKind.APPROVAL, MixedControlTransitionKind.DENIAL})


def _produced_target_kinds(kind: MixedControlTransitionKind) -> frozenset[ParticipantControlTargetKind]:
    """Targets an accepted application of ``kind`` registers (control always; proposal or decision too)."""

    produced = {ParticipantControlTargetKind.CONTROL}
    if kind is _PROPOSAL:
        produced.add(ParticipantControlTargetKind.PROPOSAL)
    elif kind in _DECIDING:
        produced.add(ParticipantControlTargetKind.DECISION)
    return frozenset(produced)


def _windows_intersect(first: tuple[int, int], second: tuple[int, int]) -> bool:
    return max(first[0], second[0]) <= min(first[1], second[1])


class _MixedControlPolicyMixin:
    def _verify_mixed_control_policy(
        self,
        *,
        spec_name: str,
        behavior_spec: ParticipantBehaviorSpecification,
        declaration: _Policy,
    ) -> None:
        label = f"Behavior specification '{spec_name}' mixed_control"
        if declaration.participant_ref not in behavior_spec.participant_refs:
            self._err(f"{label} must bind exactly one participant_ref owned by the behavior specification")
        if declaration.policy_revision != behavior_spec.semantic_version:
            self._err(f"{label} policy_revision must match the behavior specification semantic_version")
        named_index = self._named_ref_index(ReferencePurpose.AUTHORITY_ANCHOR)
        scope_index = self._named_ref_index(ReferencePurpose.AUTHORITY_SCOPE)
        owner_scope = self._resolved_mixed_control_refs(behavior_spec.authority_scope_refs, index=scope_index)
        for state_id, state in declaration.controller_states.items():
            self._verify_mixed_control_state(
                state_id=state_id,
                state=state,
                declaration=declaration,
                label=label,
                named_index=named_index,
                scope_index=scope_index,
                owner_scope=owner_scope,
            )
        if declaration.controller_states[declaration.initial_state_ref].authority_status is _REVOKED:
            self._err(f"{label} initial state cannot use revoked authority")
        for transition_id, transition in declaration.permitted_transitions.items():
            pointer = transition_pointer(spec_name, "permitted_transitions", transition_id)
            self._verify_permitted_transition(label, declaration, transition_id, transition, pointer)
        if declaration.script_steps is not None:
            self._verify_script_steps(label, declaration)

    def _verify_permitted_transition(
        self,
        label: str,
        declaration: _Policy,
        transition_id: str,
        transition: MixedControlPermittedTransition,
        pointer: str,
    ) -> None:
        owner_label = f"{label} permitted transition '{transition_id}'"
        source = declaration.controller_states[transition.from_state_ref]
        destination = declaration.controller_states[transition.to_state_ref]
        if source.authority_status is _REVOKED:
            self._err(f"{owner_label} starts from revoked authority", pointer=pointer)
        if destination.authority_status is _REVOKED:
            self._err(f"{owner_label} enters revoked authority", pointer=pointer)
        window = (transition.valid_from_order, transition.valid_until_order)
        if not _windows_intersect(window, _state_window(source)):
            self._err(f"{owner_label} window does not intersect its from-state validity", pointer=pointer)
        if not _windows_intersect(window, _state_window(destination)):
            self._err(f"{owner_label} window does not intersect its to-state validity", pointer=pointer)
        changes_controller = _resolved_controller(declaration, source) != _resolved_controller(declaration, destination)
        if transition.transition_kind == MixedControlTransitionKind.HANDOFF and not changes_controller:
            self._err(f"{owner_label} handoff must change controller", pointer=pointer)
        if transition.transition_kind != MixedControlTransitionKind.HANDOFF and changes_controller:
            self._err(f"{owner_label} changes controller; only a handoff changes controller identity", pointer=pointer)
        self._verify_evidence_refs(
            (*transition.evidence_refs, *(transition.completion_evidence_refs or ())),
            owner_label=owner_label,
            pointer=pointer,
        )

    def _verify_script_steps(self, label: str, declaration: MixedControlPolicy) -> None:
        earlier: dict[str, MixedControlTransitionKind] = {}
        for step in declaration.script_steps:
            transition = declaration.permitted_transitions[step.permitted_transition_ref]
            owner_label = f"{label} script step '{step.step_id}'"
            self._verify_step_window(owner_label, declaration, step, transition)
            allowed = transition.target_kinds_allowed()
            if step.target_kind is not None and step.target_kind not in allowed:
                self._err(f"{owner_label} target_kind '{step.target_kind.value}' widens its permitted transition")
            if step.target_step_ref is not None:
                self._verify_step_target(owner_label, step, allowed, earlier)
            earlier[step.step_id] = MixedControlTransitionKind(transition.transition_kind)

    def _verify_step_window(
        self,
        owner_label: str,
        declaration: _Policy,
        step: MixedControlScriptStep,
        transition: MixedControlPermittedTransition,
    ) -> None:
        if step.valid_from_order is None:
            return
        window = (step.valid_from_order, step.valid_until_order)
        if not transition.valid_from_order <= window[0] <= window[1] <= transition.valid_until_order:
            self._err(f"{owner_label} window widens its permitted transition window")
        for side, state_ref in (("from", transition.from_state_ref), ("to", transition.to_state_ref)):
            if not _windows_intersect(window, _state_window(declaration.controller_states[state_ref])):
                self._err(f"{owner_label} window does not intersect its {side}-state validity")

    def _verify_step_target(
        self,
        owner_label: str,
        step: MixedControlScriptStep,
        allowed: frozenset[ParticipantControlTargetKind],
        earlier: dict[str, MixedControlTransitionKind],
    ) -> None:
        producer = earlier.get(step.target_step_ref)
        if producer is None:
            self._err(f"{owner_label} target_step_ref '{step.target_step_ref}' must name an earlier step")
            return
        wanted = {step.target_kind} if step.target_kind is not None else set(allowed)
        if len(wanted & _produced_target_kinds(producer)) != 1:
            self._err(
                f"{owner_label} target_step_ref '{step.target_step_ref}' must produce exactly one eligible target"
            )


def _state_window(state: MixedControlControllerState) -> tuple[int, int]:
    return state.valid_from_order, state.valid_until_order


def _resolved_controller(declaration: _Policy, state: MixedControlControllerState) -> str:
    return declaration.participant_ref if state.controller_ref == "self" else state.controller_ref
