"""Rev1 directed-delivery control bindings (DSL-142, MC-04 and MC-09).

A rev1 binding names one reusable permitted transition. The acting controller is
the transition's source-state controller, the bound scope may only narrow that
state's scope, and the control and delivery policies are pinned independently.
"""

from __future__ import annotations

from ..participant_mixed_control_policy import MixedControlPolicy


def _cross_form_message(label: str, control: object) -> str:
    if control is None:
        return f"{label} flat control fields cannot bind a mixed-control-policy-occurrence/rev1 policy"
    return f"{label} control block requires a mixed-control-policy-occurrence/rev1 mixed_control policy"


class _ParticipantInjectDeliveryControlMixin:
    def _verify_delivery_policy_control(
        self,
        label: str,
        behavior_spec: object,
        binding: object,
        delivery_kind: str,
    ) -> None:
        control = binding.control
        declaration = behavior_spec.mixed_control
        if control is None or not isinstance(declaration, MixedControlPolicy):
            self._err(_cross_form_message(label, control))
            return
        if (control.semantics, control.policy_revision) != (declaration.semantics, declaration.policy_revision):
            self._err(f"{label} control policy pin disagrees with the owning mixed_control policy")
        if declaration.participant_ref != binding.participant_ref:
            self._err(f"{label} control transition participant disagrees with participant_ref")
        transition = declaration.permitted_transitions.get(control.permitted_transition_ref)
        if transition is None:
            self._err(f"{label} control permitted_transition_ref '{control.permitted_transition_ref}' does not resolve")
            return
        transition_kind = str(getattr(transition.transition_kind, "value", transition.transition_kind))
        if transition_kind != delivery_kind:
            self._err(
                f"{label} control permitted_transition_ref '{control.permitted_transition_ref}' kind "
                f"'{transition_kind}' does not match delivery_kind '{delivery_kind}'"
            )
        source_state = declaration.controller_states[transition.from_state_ref]
        self._verify_delivery_policy_authority(label, binding, declaration, source_state)
        self._verify_delivery_policy_evidence(label, binding, transition, source_state)

    def _verify_delivery_policy_authority(
        self,
        label: str,
        binding: object,
        declaration: object,
        source_state: object,
    ) -> None:
        control = binding.control
        expected_controller = (
            declaration.participant_ref if source_state.controller_ref == "self" else source_state.controller_ref
        )
        bound_controller = binding.participant_ref if control.controller_ref == "self" else control.controller_ref
        if bound_controller != expected_controller:
            self._err(f"{label} control controller_ref must be the permitted transition's source-state controller")
        bound_scope = self._resolved_control_refs(control.authority_scope_refs)
        if not bound_scope or not bound_scope.issubset(self._resolved_control_refs(source_state.scope_refs)):
            self._err(f"{label} control authority scope widens the source-state scope")

    def _verify_delivery_policy_evidence(
        self,
        label: str,
        binding: object,
        transition: object,
        source_state: object,
    ) -> None:
        bound_evidence = self._resolved_control_refs(binding.control.evidence_refs)
        permitted = self._resolved_control_refs((*transition.evidence_refs, *source_state.evidence_refs))
        if not bound_evidence or not bound_evidence.issubset(permitted):
            self._err(f"{label} control evidence lies outside the permitted transition and source-state evidence")
        required_scope: set[str] = set()
        for ref in binding.evidence_requirement_refs:
            requirement = self._s.evidence_requirements.get(ref)
            if requirement is not None:
                required_scope.update(self._resolved_control_refs(requirement.scope_refs))
        if not bound_evidence.issubset(required_scope):
            self._err(f"{label} evidence requirement does not cover the control evidence basis")
