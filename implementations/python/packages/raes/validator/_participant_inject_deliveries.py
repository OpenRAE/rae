"""Participant-directed inject binding validation (DSL-142)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .._reference_targetability import ReferencePurpose

_DECLARATION_INDEX_REQUIRED = "declaration index must be built before reference validation"


class _ParticipantInjectDeliveriesMixin:
    def _verify_participant_inject_deliveries(self) -> None:
        if self._declaration_index is None:
            raise RuntimeError(_DECLARATION_INDEX_REQUIRED)
        for spec_name, behavior_spec in self._s.behavior_specifications.items():
            for binding_id, binding in behavior_spec.participant_inject_deliveries.items():
                self._verify_participant_inject_delivery(
                    spec_name=str(spec_name),
                    binding_id=str(binding_id),
                    behavior_spec=behavior_spec,
                    binding=binding,
                )

    def _verify_participant_inject_delivery(
        self,
        *,
        spec_name: str,
        binding_id: str,
        behavior_spec: object,
        binding: object,
    ) -> None:
        label = f"Behavior specification '{spec_name}' participant inject delivery '{binding_id}'"
        self._verify_delivery_participant(label, behavior_spec, binding)
        self._verify_delivery_occurrence(label, binding)
        self._verify_delivery_items(label, binding)
        self._verify_delivery_time_and_evidence(label, spec_name, binding_id, binding)
        self._verify_delivery_control(label, behavior_spec, binding)

    def _verify_delivery_participant(self, label: str, behavior_spec: object, binding: object) -> None:
        participant_ref = binding.participant_ref
        if self._is_unresolved_var(participant_ref):
            return
        if participant_ref not in self._s.agents:
            self._err(f"{label} participant_ref '{participant_ref}' does not reference a declared agent")
            return
        if participant_ref not in behavior_spec.participant_refs:
            self._err(f"{label} participant_ref '{participant_ref}' is outside the owning behavior specification")
        boundary_ref = binding.observation_boundary_ref
        if not self._is_unresolved_var(boundary_ref):
            if boundary_ref not in behavior_spec.observation_boundary_refs:
                self._err(
                    f"{label} observation_boundary_ref '{boundary_ref}' is outside the owning behavior specification"
                )
            agent = self._s.agents[participant_ref]
            if boundary_ref not in agent.observation_boundaries:
                self._err(
                    f"{label} observation_boundary_ref '{boundary_ref}' is outside participant '{participant_ref}'"
                )

    def _verify_delivery_occurrence(self, label: str, binding: object) -> None:
        inject_ref = binding.inject_ref
        occurrence = binding.occurrence
        refs = (
            ("inject_ref", inject_ref, self._s.injects),
            ("event_ref", occurrence.event_ref, self._s.events),
            ("script_ref", occurrence.script_ref, self._s.scripts),
            ("story_ref", occurrence.story_ref, self._s.stories),
        )
        missing = False
        for field_name, ref, declarations in refs:
            if self._is_unresolved_var(ref):
                missing = True
                continue
            if ref not in declarations:
                self._err(f"{label} {field_name} '{ref}' does not reference a declared {field_name[:-4]}")
                missing = True
        if missing:
            return
        event = self._s.events[occurrence.event_ref]
        if inject_ref not in event.injects:
            self._err(f"{label} event_ref '{occurrence.event_ref}' does not contain inject '{inject_ref}'")
        script = self._s.scripts[occurrence.script_ref]
        if occurrence.event_ref not in script.events:
            self._err(f"{label} script_ref '{occurrence.script_ref}' does not contain event '{occurrence.event_ref}'")
        story = self._s.stories[occurrence.story_ref]
        if occurrence.script_ref not in story.scripts:
            self._err(f"{label} story_ref '{occurrence.story_ref}' does not contain script '{occurrence.script_ref}'")

    def _verify_delivery_items(self, label: str, binding: object) -> None:
        self._verify_delivery_item_refs(label, binding)
        self._verify_delivery_observation(label, binding)

    def _verify_delivery_item_refs(self, label: str, binding: object) -> None:
        for field_name in ("source_item_ref", "result_item_ref"):
            ref = getattr(binding, field_name)
            if self._is_unresolved_var(ref):
                continue
            self._validate_named_ref(
                ref,
                owner_label=label,
                ref_label=field_name,
                purpose=ReferencePurpose.TARGETABLE,
            )

    def _verify_delivery_observation(self, label: str, binding: object) -> None:
        boundary_ref = binding.observation_boundary_ref
        if self._is_unresolved_var(boundary_ref) or boundary_ref not in self._s.observation_boundaries:
            if not self._is_unresolved_var(boundary_ref):
                self._err(f"{label} observation_boundary_ref '{boundary_ref}' does not reference a declared boundary")
            return
        boundary = self._s.observation_boundaries[boundary_ref]
        result_ref = binding.result_item_ref
        if self._is_unresolved_var(result_ref):
            return
        matching_rules = [
            rule for rule in boundary.view_rules if self._references_overlap(rule.information_ref, result_ref)
        ]
        allowed = {"observable", "disclosed"}
        if not matching_rules or not any(
            str(getattr(rule.disposition, "value", rule.disposition)) in allowed for rule in matching_rules
        ):
            self._err(
                f"{label} result_item_ref '{result_ref}' must be disclosed or observable "
                f"through observation_boundary_ref '{boundary_ref}'"
            )
            return
        policy = binding.delivery_policy
        if not any(
            rule.visibility_basis == policy.visibility_basis_ref and rule.disclosure_rule == policy.disclosure_basis_ref
            for rule in matching_rules
        ):
            self._err(
                f"{label} delivery policy visibility/disclosure basis does not agree with "
                f"observation_boundary_ref '{boundary_ref}'"
            )

    def _references_overlap(self, left: str, right: str) -> bool:
        if self._declaration_index is None:
            raise RuntimeError(_DECLARATION_INDEX_REQUIRED)
        left_targets = self._declaration_index.resolve(left)
        right_targets = self._declaration_index.resolve(right)
        return bool(left_targets and right_targets and left_targets.intersection(right_targets))

    def _verify_delivery_time_and_evidence(
        self,
        label: str,
        spec_name: str,
        binding_id: str,
        binding: object,
    ) -> None:
        binding_ref = f"behavior_specifications.{spec_name}.participant_inject_deliveries.{binding_id}"
        self._verify_delivery_registry_refs(
            label=label,
            binding_ref=binding_ref,
            refs=binding.temporal_constraint_refs,
            registry=self._s.temporal_constraints,
            ref_label="temporal_constraint_ref",
            subject_field="subject_refs",
        )
        self._verify_delivery_registry_refs(
            label=label,
            binding_ref=binding_ref,
            refs=binding.evidence_requirement_refs,
            registry=self._s.evidence_requirements,
            ref_label="evidence_requirement_ref",
            subject_field="source_refs",
        )

    def _verify_delivery_registry_refs(
        self,
        *,
        label: str,
        binding_ref: str,
        refs: Iterable[str],
        registry: Mapping[str, object],
        ref_label: str,
        subject_field: str,
    ) -> None:
        for ref in refs:
            if self._is_unresolved_var(ref):
                continue
            if ref not in registry:
                self._err(f"{label} {ref_label} '{ref}' does not reference a declared resource")
                continue
            declared = getattr(registry[ref], subject_field)
            if not any(self._references_overlap(binding_ref, subject) for subject in declared):
                self._err(f"{label} {ref_label} '{ref}' does not bind this delivery declaration")

    def _verify_delivery_control(self, label: str, behavior_spec: object, binding: object) -> None:
        delivery_kind = str(getattr(binding.delivery_kind, "value", binding.delivery_kind))
        if delivery_kind == "disclosure":
            return
        control = self._resolve_delivery_control(label, behavior_spec, binding)
        if control is None:
            return
        declaration, transition, target_state = control
        self._verify_delivery_control_agreement(
            label,
            binding,
            delivery_kind,
            declaration,
            transition,
            target_state,
        )
        self._verify_delivery_control_time(label, binding)
        self._verify_delivery_control_evidence(label, binding, transition, target_state)

    def _resolve_delivery_control(
        self,
        label: str,
        behavior_spec: object,
        binding: object,
    ) -> tuple[object, object, object] | None:
        declaration = behavior_spec.mixed_control
        if declaration is None:
            self._err(f"{label} control_transition_ref requires mixed_control on the owning behavior specification")
            return None
        transition_ref = binding.control_transition_ref
        transition = declaration.transitions.get(transition_ref) if transition_ref is not None else None
        if transition is None:
            self._err(f"{label} control_transition_ref '{transition_ref}' does not resolve")
            return None
        return declaration, transition, declaration.controller_states[transition.to_state_ref]

    def _verify_delivery_control_agreement(
        self,
        label: str,
        binding: object,
        delivery_kind: str,
        declaration: object,
        transition: object,
        target_state: object,
    ) -> None:
        self._verify_delivery_control_identity(
            label,
            binding,
            delivery_kind,
            declaration,
            transition,
            target_state,
        )
        self._verify_delivery_control_bounds(label, binding, transition, target_state)

    def _verify_delivery_control_identity(
        self,
        label: str,
        binding: object,
        delivery_kind: str,
        declaration: object,
        transition: object,
        target_state: object,
    ) -> None:
        transition_kind = str(getattr(transition.transition_kind, "value", transition.transition_kind))
        if transition_kind != delivery_kind:
            self._err(
                f"{label} control_transition_ref '{binding.control_transition_ref}' kind '{transition_kind}' "
                f"does not match delivery_kind '{delivery_kind}'"
            )
        if declaration.participant_ref != binding.participant_ref:
            self._err(f"{label} control transition participant disagrees with participant_ref")
        if declaration.policy_revision != binding.delivery_policy.policy_revision:
            self._err(f"{label} control transition policy revision disagrees with delivery policy")
        expected_controller = (
            declaration.participant_ref if target_state.controller_ref == "self" else target_state.controller_ref
        )
        delivered_controller = binding.participant_ref if binding.controller_ref == "self" else binding.controller_ref
        if delivered_controller != expected_controller:
            self._err(f"{label} controller_ref disagrees with the control transition target state")
        if self._resolved_control_refs(binding.control_authority_scope_refs) != self._resolved_control_refs(
            target_state.scope_refs
        ):
            self._err(f"{label} control authority scope disagrees with the control transition target state")

    def _verify_delivery_control_bounds(
        self,
        label: str,
        binding: object,
        transition: object,
        target_state: object,
    ) -> None:
        if binding.control_effective_order != transition.effective_order:
            self._err(f"{label} control effective order disagrees with the control transition")
        if (
            binding.control_valid_from_order != transition.valid_from_order
            or binding.control_valid_until_order != transition.valid_until_order
        ):
            self._err(f"{label} control validity interval disagrees with the control transition")
        if not target_state.valid_from_order <= binding.control_effective_order <= target_state.valid_until_order:
            self._err(f"{label} control effective order falls outside the target controller-state validity interval")

    def _resolved_control_refs(self, refs: Iterable[str]) -> set[str]:
        if self._declaration_index is None:
            raise RuntimeError(_DECLARATION_INDEX_REQUIRED)
        resolved: set[str] = set()
        for ref in refs:
            resolved.update(self._declaration_index.resolve(ref))
        return resolved

    def _verify_delivery_control_time(self, label: str, binding: object) -> None:
        control_coordinate = (binding.control_effective_order, 0)
        bounded = False
        for ref in binding.temporal_constraint_refs:
            constraint = self._s.temporal_constraints.get(ref)
            if constraint is None:
                continue
            if constraint.start is not None:
                bounded = True
                if control_coordinate < (constraint.start.tick, constraint.start.microstep):
                    self._err(f"{label} temporal constraint excludes the control effective order")
            if constraint.end is not None:
                bounded = True
                if control_coordinate > (constraint.end.tick, constraint.end.microstep):
                    self._err(f"{label} temporal constraint excludes the control effective order")
        if not bounded:
            self._err(f"{label} directed control requires a bounded temporal constraint")

    def _verify_delivery_control_evidence(
        self,
        label: str,
        binding: object,
        transition: object,
        target_state: object,
    ) -> None:
        delivered_evidence = self._resolved_control_refs(binding.control_evidence_refs)
        transition_evidence = self._resolved_control_refs(transition.evidence_refs)
        target_state_evidence = self._resolved_control_refs(target_state.evidence_refs)
        if delivered_evidence != transition_evidence or delivered_evidence != target_state_evidence:
            self._err(f"{label} control evidence basis disagrees with the transition or target state")

        required_scope: set[str] = set()
        for ref in binding.evidence_requirement_refs:
            requirement = self._s.evidence_requirements.get(ref)
            if requirement is not None:
                required_scope.update(self._resolved_control_refs(requirement.scope_refs))
        if not delivered_evidence or not delivered_evidence.issubset(required_scope):
            self._err(f"{label} evidence requirement does not cover the control evidence basis")
