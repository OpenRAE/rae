"""Semantic validation for DSL-124 authored evidence requirements."""

from __future__ import annotations

from raes.observation_scope import resolve_observation_scope
from raes.runtime_forwarding_agent import RuntimeForwardingAgentOwnershipRole


class _EvidenceRequirementsMixin:
    def _verify_evidence_requirements(self) -> None:
        for name, requirement in self._s.evidence_requirements.items():
            owner_label = f"Evidence requirement '{name}'"
            self._verify_evidence_requirement_refs(requirement.source_refs, owner_label, "source_ref")
            self._verify_evidence_requirement_refs(requirement.scope_refs, owner_label, "scope_ref")
            self._verify_evidence_requirement_refs(requirement.channel_refs, owner_label, "channel_ref")
            self._verify_evidence_requirement_ref(requirement.trigger_ref, owner_label, "trigger_ref")
            self._verify_evidence_requirement_ref(requirement.boundary_ref, owner_label, "boundary_ref")
            demand = requirement.observation_demand
            if demand is not None:
                self._verify_observation_scope(demand.scope, owner_label, "observation_demand.scope")
                if demand.selector is not None:
                    for excluded in demand.selector.excluded_scopes:
                        self._verify_observation_scope(excluded, owner_label, "observation_demand.selector.exclusion")
                    self._verify_observation_scope(
                        demand.selector.semantic_scope,
                        owner_label,
                        "observation_demand.selector.semantic_scope",
                    )
                    self._verify_evidence_requirement_refs(
                        list(demand.selector.component_refs), owner_label, "observation_demand.selector.component_ref"
                    )
        self._verify_forwarding_agent_evidence_roles()

    def _verify_observation_scope(self, pointer: str, owner_label: str, field_label: str) -> None:
        found, _value = resolve_observation_scope(self._s, pointer)
        if not found:
            self._err(f"{owner_label} {field_label} '{pointer}' does not resolve to a stable SDL semantic scope")

    def _verify_forwarding_agent_evidence_roles(self) -> None:
        agents = self._forwarding_agents_by_address()
        apparatus_bindings: set[str] = set()
        for requirement in self._s.evidence_requirements.values():
            source_class = getattr(requirement.source_class, "value", requirement.source_class)
            if source_class != "apparatus":
                continue
            for source_ref in requirement.source_refs:
                apparatus_bindings.update(self._declaration_index.resolve(source_ref) & agents.keys())

        for address, agent in agents.items():
            role = agent.ownership_role
            if role is RuntimeForwardingAgentOwnershipRole.MEASUREMENT_APPARATUS and address not in apparatus_bindings:
                self._err(
                    f"Forwarding agent '{address}' ownership_role 'measurement_apparatus' requires an inbound "
                    "EvidenceRequirement.source_refs binding with source_class 'apparatus'"
                )
            elif role is RuntimeForwardingAgentOwnershipRole.SYSTEM_UNDER_TEST and address in apparatus_bindings:
                self._err(
                    f"Forwarding agent '{address}' ownership_role 'system_under_test' cannot be targeted by an "
                    "evidence requirement with source_class 'apparatus'"
                )

    def _forwarding_agents_by_address(self) -> dict[str, object]:
        agents = {f"forwarding_agents.{agent.forwarding_agent_id}": agent for agent in self._s.forwarding_agents}
        for node_name, node in self._s.nodes.items():
            runtime = node.runtime
            if runtime is None:
                continue
            agents.update(
                {
                    f"nodes.{node_name}.runtime.forwarding_agents.{agent.forwarding_agent_id}": agent
                    for agent in runtime.forwarding_agents
                }
            )
        return agents

    def _verify_evidence_requirement_refs(
        self,
        refs: list[str],
        owner_label: str,
        ref_label: str,
    ) -> None:
        for ref in refs:
            self._verify_evidence_requirement_ref(ref, owner_label, ref_label)

    def _verify_evidence_requirement_ref(
        self,
        ref: str,
        owner_label: str,
        ref_label: str,
    ) -> None:
        if not ref or self._is_unresolved_var(ref):
            return
        self._validate_named_ref(ref, owner_label=owner_label, ref_label=ref_label, targetable=True)
