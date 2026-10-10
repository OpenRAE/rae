"""Semantic validation for ACT-617 mixed-control participant operation."""

from .._reference_targetability import ReferencePurpose
from ..participant_behavior_specification import (
    MixedControlAuthorityStatus,
    MixedControlControllerState,
    MixedControlParticipantOperation,
    MixedControlTransition,
    MixedControlTransitionKind,
    ParticipantBehaviorSpecification,
)


class _MixedControlMixin:
    def _verify_mixed_control_semantics(self) -> None:
        for spec_name, behavior_spec in self._s.behavior_specifications.items():
            declaration = behavior_spec.mixed_control
            self._verify_mixed_control_pairing(
                spec_name=spec_name,
                behavior_mode=behavior_spec.behavior_mode,
                declaration=declaration,
            )
            if declaration is not None:
                self._verify_mixed_control_declaration(
                    spec_name=spec_name,
                    behavior_spec=behavior_spec,
                    declaration=declaration,
                )

    def _verify_mixed_control_pairing(
        self,
        *,
        spec_name: str,
        behavior_mode: str | None,
        declaration: MixedControlParticipantOperation | None,
    ) -> None:
        if behavior_mode == "mixed-control" and declaration is None:
            self._err(f"Behavior specification '{spec_name}' mixed-control mode requires mixed_control")
        if declaration is not None and behavior_mode != "mixed-control":
            self._err(f"Behavior specification '{spec_name}' mixed_control requires behavior_mode mixed-control")

    def _verify_mixed_control_declaration(
        self,
        *,
        spec_name: str,
        behavior_spec: ParticipantBehaviorSpecification,
        declaration: MixedControlParticipantOperation,
    ) -> None:
        label = f"Behavior specification '{spec_name}' mixed_control"
        if declaration.participant_ref not in behavior_spec.participant_refs:
            self._err(f"{label} must bind exactly one participant_ref owned by the behavior specification")
        if declaration.policy_revision != behavior_spec.semantic_version:
            self._err(f"{label} policy_revision must match the behavior specification semantic_version")

        named_index = self._named_ref_index(ReferencePurpose.AUTHORITY_ANCHOR)
        scope_index = self._named_ref_index(ReferencePurpose.AUTHORITY_SCOPE)
        owner_scope = self._resolved_mixed_control_refs(
            behavior_spec.authority_scope_refs,
            index=scope_index,
        )
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

        initial_state = declaration.controller_states[declaration.initial_state_ref]
        if self._enum_value(initial_state.authority_status) == "revoked":
            self._err(f"{label} initial state cannot use revoked authority")
        for transition_id, transition in declaration.transitions.items():
            self._verify_mixed_control_transition(
                transition_id=transition_id,
                transition=transition,
                declaration=declaration,
                label=label,
            )

    def _verify_mixed_control_state(
        self,
        *,
        state_id: str,
        state: MixedControlControllerState,
        declaration: MixedControlParticipantOperation,
        label: str,
        named_index: dict[str, set[str]],
        scope_index: dict[str, set[str]],
        owner_scope: set[str],
    ) -> None:
        controller_ref = declaration.participant_ref if state.controller_ref == "self" else state.controller_ref
        controller = self._s.agents.get(controller_ref)
        if controller is None:
            self._err(
                f"{label} controller state '{state_id}' controller_ref '{state.controller_ref}' "
                "must reference a declared agent or self"
            )
            return
        owner_label = f"{label} controller state '{state_id}'"
        controller_authority = self._resolved_mixed_control_refs(
            controller.authority_anchors,
            index=named_index,
        )
        self._verify_authority_basis_refs(
            refs=state.authority_basis_refs,
            controller_ref=state.controller_ref,
            controller_authority=controller_authority,
            named_index=named_index,
            owner_label=owner_label,
        )
        controller_scope = self._resolved_mixed_control_refs(
            controller.operating_scope,
            index=scope_index,
        )
        self._verify_scope_refs(
            refs=state.scope_refs,
            controller_ref=state.controller_ref,
            controller_scope=controller_scope,
            scope_index=scope_index,
            owner_scope=owner_scope,
            owner_label=owner_label,
        )
        self._verify_evidence_refs(state.evidence_refs, owner_label=owner_label)

    def _verify_authority_basis_refs(
        self,
        *,
        refs: list[str],
        controller_ref: str,
        controller_authority: set[str],
        named_index: dict[str, set[str]],
        owner_label: str,
    ) -> None:
        for ref in refs:
            self._validate_named_ref(
                ref, owner_label=owner_label, ref_label="authority_basis_ref", purpose=ReferencePurpose.AUTHORITY_ANCHOR
            )
            if not set(named_index.get(ref, ())).issubset(controller_authority):
                self._err(f"{owner_label} authority basis '{ref}' is not declared by controller '{controller_ref}'")

    def _verify_scope_refs(
        self,
        *,
        refs: list[str],
        controller_ref: str,
        controller_scope: set[str],
        scope_index: dict[str, set[str]],
        owner_scope: set[str],
        owner_label: str,
    ) -> None:
        for ref in refs:
            self._validate_named_ref(
                ref, owner_label=owner_label, ref_label="scope_ref", purpose=ReferencePurpose.AUTHORITY_SCOPE
            )
            resolved = set(scope_index.get(ref, ()))
            if not resolved.issubset(owner_scope):
                self._err(f"{owner_label} scope_ref '{ref}' widens the behavior specification authority scope")
            if not resolved.issubset(controller_scope):
                self._err(f"{owner_label} scope_ref '{ref}' is outside controller '{controller_ref}' operating_scope")

    def _verify_mixed_control_transition(
        self,
        *,
        transition_id: str,
        transition: MixedControlTransition,
        declaration: MixedControlParticipantOperation,
        label: str,
    ) -> None:
        from_state = declaration.controller_states[transition.from_state_ref]
        to_state = declaration.controller_states[transition.to_state_ref]
        owner_label = f"{label} transition '{transition_id}'"
        self._verify_transition_validity(
            transition=transition,
            from_state=from_state,
            to_state=to_state,
            owner_label=owner_label,
        )
        self._verify_proposal_transition(
            transition=transition,
            declaration=declaration,
            owner_label=owner_label,
        )
        self._verify_handoff_transition(
            transition=transition,
            from_state=from_state,
            to_state=to_state,
            owner_label=owner_label,
        )
        self._verify_evidence_refs(
            (*transition.evidence_refs, *transition.completion_evidence_refs),
            owner_label=owner_label,
        )

    def _verify_transition_validity(
        self,
        *,
        transition: MixedControlTransition,
        from_state: MixedControlControllerState,
        to_state: MixedControlControllerState,
        owner_label: str,
    ) -> None:
        if self._enum_value(from_state.authority_status) == "revoked":
            self._err(f"{owner_label} starts from revoked authority")
        if not from_state.valid_from_order <= transition.effective_order <= from_state.valid_until_order:
            self._err(f"{owner_label} is late for its from-state validity")
        if not to_state.valid_from_order <= transition.effective_order <= to_state.valid_until_order:
            self._err(f"{owner_label} precedes its to-state validity")

    def _verify_proposal_transition(
        self,
        *,
        transition: MixedControlTransition,
        declaration: MixedControlParticipantOperation,
        owner_label: str,
    ) -> None:
        if transition.proposal_ref is None:
            return
        proposal = declaration.transitions[transition.proposal_ref]
        if transition.from_state_ref != proposal.to_state_ref:
            self._err(f"{owner_label} must start from its proposal's resulting state")
        if transition.expected_state_revision != proposal.resulting_state_revision:
            self._err(f"{owner_label} must expect its proposal's resulting state revision")

    def _verify_handoff_transition(
        self,
        *,
        transition: MixedControlTransition,
        from_state: MixedControlControllerState,
        to_state: MixedControlControllerState,
        owner_label: str,
    ) -> None:
        if self._enum_value(transition.transition_kind) != "handoff":
            return
        if from_state.controller_ref == to_state.controller_ref:
            self._err(f"{owner_label.replace('transition', 'handoff transition', 1)} must change controller")
        if not transition.completion_evidence_refs:
            self._err(f"{owner_label.replace('transition', 'handoff transition', 1)} requires completion evidence")

    def _verify_evidence_refs(self, refs: tuple[str, ...] | list[str], *, owner_label: str) -> None:
        for ref in refs:
            self._validate_named_ref(ref, owner_label=owner_label, ref_label="evidence_ref")

    @staticmethod
    def _enum_value(value: MixedControlAuthorityStatus | MixedControlTransitionKind) -> str:
        return str(getattr(value, "value", value))

    @staticmethod
    def _resolved_mixed_control_refs(refs: list[str], *, index: dict[str, set[str]]) -> set[str]:
        resolved: set[str] = set()
        for ref in refs:
            resolved.update(index.get(ref, ()))
        return resolved
