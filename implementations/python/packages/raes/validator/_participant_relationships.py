"""Participant relationship endpoint and refinement agreement checks."""

from ..entities import flatten_entities
from ..participant_relationships import PARTICIPANT_RELATIONSHIP_REFERENCE_SECTIONS, ParticipantRelationship
from ..relationships import Relationship
from ..semantics._domain_topology_types import resolve_section_ref


class _ParticipantRelationshipsMixin:
    def _verify_participant_relationship(self, name: str, relationship: Relationship) -> None:
        label = f"Relationship '{name}'"
        endpoints = []
        for field in ("source", "target"):
            ref = getattr(relationship, field)
            if self._is_unresolved_var(ref):
                endpoints.append(None)
                continue
            resolved = resolve_section_ref(ref, "agents", self._s.agents)
            candidates = self._named_ref_index(targetable=True).get(ref, set())
            if resolved is None or candidates != {f"agents.{resolved}"}:
                self._err(f"{label} {field} participant endpoint must resolve unambiguously to a declared agent")
                resolved = None
            endpoints.append(resolved)
        source, target = endpoints
        if source is not None and source == target:
            self._err(f"{label} requires distinct participants")
        detail = relationship.participant
        refs = {
            field: self._participant_relation_refs(label, detail, field, section)
            for field, section in PARTICIPANT_RELATIONSHIP_REFERENCE_SECTIONS.items()
            if section != "named"
        }
        self._participant_relation_action_refs(label, detail, refs, source, target)
        self._participant_relation_behavior_refs(label, refs, source, target)
        self._participant_relation_authority(label, detail, source)
        self._participant_relation_scope(label, detail, source, target)
        self._participant_relation_visibility(label, detail, source)
        self._participant_relation_control(label, detail, source, target)

    def _participant_relation_control(
        self,
        label: str,
        detail: ParticipantRelationship,
        source: str | None,
        target: str | None,
    ) -> None:
        ref = detail.control_specification_ref
        if ref is None or self._is_unresolved_var(ref):
            return
        name = resolve_section_ref(ref, "behavior_specifications", self._s.behavior_specifications)
        if name is None:
            self._err(f"{label} control_specification_ref must reference declared behavior_specifications")
            return
        control = self._s.behavior_specifications[name].mixed_control
        if control is None:
            self._err(f"{label} control_specification_ref requires an existing mixed_control declaration")
            return
        if source is None or target is None:
            return
        controlled, controller = (source, target) if detail.kind == "delegation" else (target, source)
        states = [
            state
            for state in control.controller_states.values()
            if state.controller_ref == controller and state.authority_status == "active"
        ]
        if control.participant_ref != controlled or not states:
            self._err(f"{label} control_specification_ref contradicts participant/controller direction")
            return
        scope_index = self._operating_scope_ref_index()
        policy_scope = self._resolved_mixed_control_refs(
            [ref for state in states for ref in state.scope_refs], index=scope_index
        )
        for ref in detail.scope_refs:
            if not self._is_unresolved_var(ref) and not scope_index.get(ref, set()).issubset(policy_scope):
                self._err(f"{label} control_specification_ref must cover the selected relationship scope")

    def _participant_relation_refs(
        self,
        label: str,
        detail: ParticipantRelationship,
        field: str,
        section: str,
    ) -> set[str]:
        resolved = set()
        declarations = getattr(self._s, section)
        for ref in getattr(detail, field):
            if self._is_unresolved_var(ref):
                continue
            name = resolve_section_ref(ref, section, declarations)
            if name is None:
                self._err(f"{label} {field} must reference declared {section}")
            elif name in resolved:
                self._err(f"{label} {field} repeats a canonical reference")
            else:
                resolved.add(name)
        return resolved

    def _participant_relation_action_refs(
        self,
        label: str,
        detail: ParticipantRelationship,
        refs: dict[str, set[str]],
        source: str | None,
        target: str | None,
    ) -> None:
        for field, participant in (("source_action_refs", source), ("target_action_refs", target)):
            if participant is None:
                continue
            available = self._s.agents[participant].actions
            if not any(self._is_unresolved_var(ref) for ref in available) and not refs[field].issubset(available):
                self._err(f"{label} {field} must be available to participant '{participant}'")
        if detail.kind != "coordination":
            return
        for action_name in refs["source_action_refs"]:
            related = self._participant_coordination_actions(action_name, target)
            if any(self._is_unresolved_var(ref) for ref in related):
                continue
            if refs["target_action_refs"] and not refs["target_action_refs"].issubset(related):
                self._err(f"{label} coordination refinements must agree with an action interaction")

    def _participant_coordination_actions(self, action_name: str, target: str | None) -> set[str]:
        related = set()
        for interaction in self._s.action_contracts[action_name].interactions:
            if interaction.interaction_class != "coordination":
                continue
            peer = resolve_section_ref(interaction.target, "agents", self._s.agents)
            # Resource-targeted synchronization does not invent a peer target.
            # An explicitly named participant, however, must agree with the edge.
            if target is not None and peer is not None and peer != target:
                continue
            related.update(interaction.related_actions)
        return related

    def _participant_relation_behavior_refs(
        self,
        label: str,
        refs: dict[str, set[str]],
        source: str | None,
        target: str | None,
    ) -> None:
        if source is None or target is None:
            return
        endpoints = {source, target}
        entities = flatten_entities(self._s.entities)
        roles = {
            entities[self._s.agents[name].entity].role for name in endpoints if self._s.agents[name].entity in entities
        }
        unresolved_role = any(self._is_unresolved_var(self._s.agents[name].entity) for name in endpoints) or any(
            self._is_unresolved_var(role) for role in roles
        )
        for name in refs["behavior_specification_refs"]:
            behavior = self._s.behavior_specifications[name]
            if any(
                self._is_unresolved_var(ref) for ref in (*behavior.participant_refs, *behavior.participant_role_refs)
            ):
                continue
            if not (
                endpoints.intersection(behavior.participant_refs)
                or roles.intersection(behavior.participant_role_refs)
                or (behavior.participant_role_refs and unresolved_role)
            ):
                self._err(f"{label} behavior_specification_refs must include a relationship endpoint")
        self._participant_relation_objectives(label, refs["objective_refs"], endpoints)

    def _participant_relation_objectives(self, label: str, refs: set[str], endpoints: set[str]) -> None:
        endpoint_entities = {self._s.agents[participant].entity for participant in endpoints}
        for name in refs:
            objective = self._s.objectives[name]
            if self._is_unresolved_var(objective.agent) or self._is_unresolved_var(objective.entity):
                continue
            if objective.entity and any(self._is_unresolved_var(entity) for entity in endpoint_entities):
                continue
            if objective.agent not in endpoints and objective.entity not in endpoint_entities:
                self._err(f"{label} objective_refs must belong to a relationship endpoint")

    def _participant_relation_unique_named_refs(
        self, label: str, field: str, refs: list[str], index: dict[str, set[str]]
    ) -> None:
        seen: set[str] = set()
        for ref in refs:
            if self._is_unresolved_var(ref):
                continue
            canonical = index.get(ref, set())
            # The owning reference validator reports missing or ambiguous refs.
            if len(canonical) != 1:
                continue
            if seen.intersection(canonical):
                self._err(f"{label} {field} repeats a canonical reference")
            seen.update(canonical)

    def _participant_relation_authority(
        self,
        label: str,
        detail: ParticipantRelationship,
        source: str | None,
    ) -> None:
        index = self._named_ref_index()
        self._participant_relation_unique_named_refs(label, "authority_basis_refs", detail.authority_basis_refs, index)
        for ref in detail.authority_basis_refs:
            if self._is_unresolved_var(ref):
                continue
            self._validate_named_ref(ref, owner_label=label, ref_label="authority_basis_refs")
            if source is not None:
                anchors = self._s.agents[source].authority_anchors
                authority = self._resolved_mixed_control_refs(anchors, index=index)
                if not any(self._is_unresolved_var(item) for item in anchors) and not index.get(ref, set()).issubset(
                    authority
                ):
                    self._err(f"{label} authority_basis_refs must not widen source authority")

    def _participant_relation_scope(
        self,
        label: str,
        detail: ParticipantRelationship,
        source: str | None,
        target: str | None,
    ) -> None:
        scope_index = self._operating_scope_ref_index()
        self._participant_relation_unique_named_refs(label, "scope_refs", detail.scope_refs, scope_index)
        for ref in detail.scope_refs:
            if self._is_unresolved_var(ref):
                continue
            self._validate_operating_scope_ref(ref, owner_label=label)
            for participant in (source, target):
                if participant is None:
                    continue
                scopes = self._s.agents[participant].operating_scope
                allowed = self._resolved_mixed_control_refs(scopes, index=scope_index)
                if not any(self._is_unresolved_var(item) for item in scopes) and not scope_index.get(
                    ref, set()
                ).issubset(allowed):
                    self._err(f"{label} scope_refs must stay within participant '{participant}' operating_scope")

    def _participant_relation_visibility(
        self,
        label: str,
        detail: ParticipantRelationship,
        source: str | None,
    ) -> None:
        if source is None:
            return
        available = self._s.agents[source].observation_boundaries
        for ref in detail.observation_boundary_refs:
            if self._is_unresolved_var(ref) or any(self._is_unresolved_var(item) for item in available):
                continue
            name = resolve_section_ref(ref, "observation_boundaries", self._s.observation_boundaries)
            if name is not None and name not in available:
                self._err(f"{label} observation_boundary_refs must be available to the source participant")
