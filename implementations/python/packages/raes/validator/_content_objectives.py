"""SemanticValidator _ContentObjectivesMixin (split from validator.py).

Part of the SemanticValidator mixin composition; see __init__.py.
"""

from collections.abc import Callable

from .._reference_targetability import ReferencePurpose
from .._relationship_endpoint_policy import relationship_endpoint_purposes
from ..entities import flatten_entities
from ..semantics.objective_semantics import (
    AssessmentResourceCatalog,
    ObjectiveIssue,
    ObjectiveRelationCatalog,
    WindowResourceCatalog,
    analyze_objective_semantics,
)
from ..semantics.participant_behavior import (
    ParticipantBehaviorIssue,
    analyze_participant_affiliations,
    analyze_participant_behavior,
)
from ..semantics.participant_interactive_access import analyze_participant_interactive_access
from ..semantics.participant_outcome import (
    ParticipantOutcomeIssue,
    analyze_participant_outcome_interpretations,
)
from ..semantics.participant_temporal_bindings import participant_temporal_binding_errors
from ._issue_owners import objective_issue_owner, participant_behavior_issue_owner, participant_outcome_issue_owner
from ._objective_issue_renderers import OBJECTIVE_ISSUE_RENDERERS
from ._participant_execution_renderers import AUTONOMOUS_PARTICIPANT_ISSUE_RENDERERS
from ._participant_outcome_renderers import PARTICIPANT_OUTCOME_ISSUE_RENDERERS
from ._participant_resource_budget_owners import participant_resource_budget_owner_errors
from ._participant_tool_affordance_renderers import PARTICIPANT_TOOL_AFFORDANCE_ISSUE_RENDERERS

_PARTICIPANT_BEHAVIOR_ISSUE_RENDERERS = {
    **AUTONOMOUS_PARTICIPANT_ISSUE_RENDERERS,
    **PARTICIPANT_TOOL_AFFORDANCE_ISSUE_RENDERERS,
    "participant.action-contract-unbound": (
        lambda i: f"Agent '{i.participant_name}' action '{i.ref}' does not reference a declared action_contract"
    ),
    "participant.observation-boundary-unbound": (
        lambda i: (
            f"Agent '{i.participant_name}' observation_boundary '{i.ref}' "
            "does not reference a declared observation_boundary"
        )
    ),
    "participant.interaction-action-unbound": (
        lambda i: (
            f"Action contract '{i.action_name}' interaction related_action '{i.ref}' "
            "does not reference a declared action_contract"
        )
    ),
    "participant.view-rule-ref-unbound": (
        lambda i: (
            f"Observation boundary '{i.boundary_name}' view_rule information_ref '{i.ref}' "
            "is not declared by observable_refs, hidden_refs, or evidence_refs"
        )
    ),
    "participant.view-rule-evidence-unbound": (
        lambda i: (
            f"Observation boundary '{i.boundary_name}' view_rule evidence_ref '{i.ref}' "
            "is not declared by evidence_refs"
        )
    ),
    "participant.view-transition-ref-unbound": (
        lambda i: (
            f"Observation boundary '{i.boundary_name}' view_transition '{i.transition_id}' "
            f"information_ref '{i.ref}' is not declared by observable_refs, hidden_refs, or evidence_refs"
        )
    ),
    "participant.view-transition-evidence-unbound": (
        lambda i: (
            f"Observation boundary '{i.boundary_name}' view_transition '{i.transition_id}' "
            f"evidence_ref '{i.ref}' is not declared by evidence_refs"
        )
    ),
    "participant.behavior-spec-participant-unbound": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' participant_ref '{i.ref}' does not reference a declared agent"
        )
    ),
    "participant.behavior-spec-role-unbound": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' participant_role_ref '{i.ref}' "
            "does not match a declared participant role"
        )
    ),
    "participant.behavior-spec-action-unbound": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' action_contract_ref '{i.ref}' "
            "does not reference a declared action_contract"
        )
    ),
    "participant.behavior-spec-observation-boundary-unbound": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' observation_boundary_ref '{i.ref}' "
            "does not reference a declared observation_boundary"
        )
    ),
    "participant.behavior-spec-outcome-rule-unbound": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' outcome_interpretation_rule_ref '{i.ref}' "
            "does not reference a declared outcome_interpretation_rule"
        )
    ),
    "participant.behavior-spec-mode-ungoverned": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' behavior_mode '{i.ref}' is not in "
            f"participant-decision-surface-modes: {i.message}"
        )
    ),
    "participant.behavior-spec-feature-ungoverned": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' backend_feature_support_ref '{i.ref}' is not a governed "
            f"participant runtime feature: {i.message}"
        )
    ),
    "participant.behavior-spec-offensive-behavior-ungoverned": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' offensive_behavior_ref '{i.ref}' is not in "
            f"participant-offensive-behavior-activities: {i.message}"
        )
    ),
    "participant.behavior-spec-ai-offensive-behavior-ungoverned": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' ai_offensive_behavior_ref '{i.ref}' is not in "
            f"participant-ai-offensive-behavior-activities: {i.message}"
        )
    ),
    "participant.behavior-spec-defensive-behavior-ungoverned": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' defensive_behavior_ref '{i.ref}' is not in "
            f"participant-defensive-behavior-activities: {i.message}"
        )
    ),
    "participant.behavior-spec-evidence-contract-unbound": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' evidence_contract_ref '{i.ref}' "
            f"does not reference a published contract: {i.message}"
        )
    ),
    "participant.tool-affordance-duplicate-relation": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' has duplicate tool affordance relation '{i.ref}' "
            f"matching '{i.message}'; mapping order has no priority or fallback meaning"
        )
    ),
    "participant.tool-affordance-action-widens-parent": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' tool affordance '{i.action_name}' action_contract_ref "
            f"'{i.ref}' widens its owning behavior specification"
        )
    ),
    "participant.tool-affordance-boundary-widens-parent": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' tool affordance '{i.action_name}' observation_boundary_ref "
            f"'{i.ref}' widens its owning behavior specification"
        )
    ),
    "participant.tool-affordance-action-outside-participant": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' tool affordance '{i.action_name}' action_contract_ref "
            f"'{i.ref}' is outside participant '{i.participant_name}' actions"
        )
    ),
    "participant.tool-affordance-boundary-outside-participant": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' tool affordance '{i.action_name}' observation_boundary_ref "
            f"'{i.ref}' is outside participant '{i.participant_name}' observation boundaries"
        )
    ),
    "participant.tool-affordance-view-unclassified": (
        lambda i: (
            f"Behavior specification '{i.spec_name}' tool affordance '{i.action_name}' reference '{i.ref}' "
            f"must be explicitly classified by observation boundary '{i.boundary_name}'"
        )
    ),
}


class _ContentObjectivesMixin:
    def _verify_content(self) -> None:
        for name, item in self._s.content.items():
            with self._owner(("content", name)):
                if item.target and not self._is_unresolved_var(item.target) and item.target not in self._s.nodes:
                    self._err(f"Content '{name}' targets undefined node '{item.target}'")
                elif (
                    item.target and not self._is_unresolved_var(item.target) and not self._is_compute_node(item.target)
                ):
                    self._err(f"Content '{name}' target '{item.target}' must be a compute node")
                if item.service_materialization is not None:
                    self._verify_service_materialization(name, item)

    def _verify_relationships(self) -> None:
        for name, rel in self._s.relationships.items():
            with self._owner(("relationships", name)):
                if rel.participant is not None:
                    self._verify_participant_relationship(name, rel)
                    continue
                for field in ("source", "target"):
                    ref = getattr(rel, field)
                    if not self._is_unresolved_var(ref):
                        self._validate_named_ref(
                            ref,
                            owner_label=f"Relationship '{name}'",
                            ref_label=field,
                            purpose=relationship_endpoint_purposes(rel, field),
                        )

    def _verify_agents(self) -> None:
        flat_entity_names = self._all_entity_names()
        for issue in analyze_participant_affiliations(
            agents_by_name=self._s.agents, entity_names=flat_entity_names, is_unresolved=self._is_unresolved_var
        ).issues:
            with self._owner(participant_behavior_issue_owner(issue)):
                self._err(issue.message)
        service_names = {service.name for node in self._s.nodes.values() for service in node.services if service.name}
        for name, agent in self._s.agents.items():
            with self._owner(("agents", name)):
                self._verify_agent(name, agent, service_names)
        for issue in analyze_participant_interactive_access(
            agents_by_name=self._s.agents,
            nodes=self._s.nodes,
            accounts=self._s.accounts,
            is_vm_node=self._is_compute_node,
            is_unresolved=self._is_unresolved_var,
        ):
            with self._owner(issue.owner):
                self._err(issue.message)

    def _verify_agent(self, name: str, agent: object, service_names: set[str]) -> None:
        label = f"Agent '{name}'"
        self._verify_membership_refs(
            agent.starting_accounts,
            self._s.accounts,
            lambda ref: f"{label} starting_account '{ref}' not in accounts section",
        )
        self._verify_agent_subnet_refs(
            agent.allowed_subnets,
            undefined=lambda ref: f"{label} allowed_subnet '{ref}' not in infrastructure section",
            not_switch=lambda ref: f"{label} allowed_subnet '{ref}' must reference a switch/network entry",
        )
        if agent.initial_knowledge:
            self._verify_agent_initial_knowledge(name, agent.initial_knowledge, service_names)
        for anchor in agent.authority_anchors:
            if not self._is_unresolved_var(anchor):
                self._validate_named_ref(
                    anchor, owner_label=label, ref_label="authority_anchor", purpose=ReferencePurpose.AUTHORITY_ANCHOR
                )
        for scope in agent.operating_scope:
            if not self._is_unresolved_var(scope):
                self._validate_operating_scope_ref(scope, owner_label=label)

    def _verify_membership_refs(self, refs: list[str], valid: object, error_msg: Callable[[str], str]) -> None:
        for ref in refs:
            if not self._is_unresolved_var(ref) and ref not in valid:
                self._err(error_msg(ref))

    def _verify_agent_subnet_refs(
        self, refs: list[str], *, undefined: Callable[[str], str], not_switch: Callable[[str], str]
    ) -> None:
        for subnet in refs:
            if self._is_unresolved_var(subnet):
                continue
            if subnet not in self._s.infrastructure:
                self._err(undefined(subnet))
            elif not self._is_switch_node(subnet):
                self._err(not_switch(subnet))

    def _verify_agent_initial_knowledge(self, name: str, initial_knowledge: object, service_names: set[str]) -> None:
        label = f"Agent '{name}'"
        self._verify_agent_ik_hosts(label, initial_knowledge)
        self._verify_agent_subnet_refs(
            initial_knowledge.subnets,
            undefined=lambda ref: f"{label} initial_knowledge subnet '{ref}' not in infrastructure section",
            not_switch=lambda ref: f"{label} initial_knowledge subnet '{ref}' must reference a switch/network entry",
        )
        self._verify_membership_refs(
            initial_knowledge.services,
            service_names,
            lambda ref: f"{label} initial_knowledge service '{ref}' not in node service names",
        )
        self._verify_membership_refs(
            initial_knowledge.accounts,
            self._s.accounts,
            lambda ref: f"{label} initial_knowledge account '{ref}' not in accounts section",
        )

    def _verify_agent_ik_hosts(self, label: str, initial_knowledge: object) -> None:
        for host in initial_knowledge.hosts:
            if self._is_unresolved_var(host):
                continue
            if host not in self._s.nodes:
                self._err(f"{label} initial_knowledge host '{host}' not in nodes section")
            elif not self._is_compute_node(host):
                self._err(f"{label} initial_knowledge host '{host}' must reference a compute node")

    def _verify_participant_behavior(self) -> None:
        from ..participant_control_context import resolve_authored_control_context

        _, errors = resolve_authored_control_context(self._s, self._declaration_index)
        for error in errors:
            self._err(error)
        for finding in participant_temporal_binding_errors(self._s):
            with self._owner(finding.owner):
                self._err(finding.message)
        analysis = analyze_participant_behavior(
            agents_by_name=self._s.agents,
            action_contracts=self._s.action_contracts,
            observation_boundaries=self._s.observation_boundaries,
            outcome_interpretation_rules=self._s.outcome_interpretation_rules,
            behavior_specifications=self._s.behavior_specifications,
            participant_roles_by_agent=self._participant_roles_by_agent(),
            clocks=self._s.clocks,
            time_progression_policies=self._s.time_progression_policies,
            temporal_constraints=self._s.temporal_constraints,
            objectives=self._s.objectives,
            is_unresolved=self._is_unresolved_var,
        )
        for issue in analysis.issues:
            with self._owner(participant_behavior_issue_owner(issue)):
                self._err(self._format_participant_behavior_issue(issue))
        for finding in participant_resource_budget_owner_errors(
            self._s.behavior_specifications,
            self._s.action_contracts,
            self._s.deployment_tenants,
            self._s.deployment_cells,
            self._s.relationships,
            self._split_node_service_ref,
        ):
            with self._owner(finding.owner):
                self._err(finding.message)
        self._verify_tool_affordance_tool_refs()
        self._verify_participant_inject_deliveries()
        self._verify_participant_interaction_refs()
        self._verify_behavior_specification_authority_refs()
        self._verify_mixed_control_semantics()

    def _participant_roles_by_agent(self) -> dict[str, str]:
        entities = flatten_entities(self._s.entities)
        roles: dict[str, str] = {}
        for agent_name, agent in self._s.agents.items():
            role = agent.effective_role(entities)
            if role is None:
                continue
            roles[agent_name] = str(getattr(role, "value", role))
        return roles

    def _verify_behavior_specification_authority_refs(self) -> None:
        for spec_name, behavior_spec in self._s.behavior_specifications.items():
            label = f"Behavior specification '{spec_name}'"
            for ref in behavior_spec.authority_scope_refs:
                if self._is_unresolved_var(ref):
                    continue
                with self._owner(("behavior_specifications", spec_name)):
                    self._validate_named_ref(
                        ref,
                        owner_label=label,
                        ref_label="authority_scope_ref",
                        purpose=ReferencePurpose.AUTHORITY_SCOPE,
                    )

    def _verify_participant_interaction_refs(self) -> None:
        self._verify_effect_target_refs()
        for action_name, action_contract in self._s.action_contracts.items():
            for index, interaction in enumerate(action_contract.interactions):
                owner_label = f"Action contract '{action_name}' interaction[{index}]"
                with self._owner(("action_contracts", action_name)):
                    self._verify_purpose_refs(
                        owner_label, "target", [interaction.target], ReferencePurpose.ACTION_TARGET
                    )
                    self._verify_purpose_refs(
                        owner_label, "shared_state_ref", interaction.shared_state_refs, ReferencePurpose.SHARED_STATE
                    )

    def _verify_purpose_refs(
        self, owner_label: str, ref_label: str, refs: list[str], purpose: ReferencePurpose
    ) -> None:
        for ref in refs:
            if not self._is_unresolved_var(ref):
                self._validate_named_ref(ref, owner_label=owner_label, ref_label=ref_label, purpose=purpose)

    def _verify_participant_outcomes(self) -> None:
        analysis = analyze_participant_outcome_interpretations(
            outcome_interpretation_rules=self._s.outcome_interpretation_rules,
            action_contracts=self._s.action_contracts,
            objectives=self._s.objectives,
            workflows=self._s.workflows,
            is_unresolved=self._is_unresolved_var,
        )
        for issue in analysis.issues:
            with self._owner(participant_outcome_issue_owner(issue)):
                self._err(self._format_participant_outcome_issue(issue))

    def _verify_objectives(self) -> None:
        # The shared analyzer owns relations and dependency semantics (SEM-207).
        analysis = analyze_objective_semantics(
            objectives_by_name=self._s.objectives,
            relation_resources=ObjectiveRelationCatalog(
                agents=self._s.agents,
                entity_names=self._all_entity_names(),
                action_contracts=self._s.action_contracts,
            ),
            assessment_resources=AssessmentResourceCatalog(
                assertions=self._s.assertions,
            ),
            window_resources=WindowResourceCatalog(
                stories=self._s.stories,
                scripts=self._s.scripts,
                events=self._s.events,
                workflows=self._s.workflows,
            ),
            targetable_name_index=self._named_ref_index(ReferencePurpose.OBJECTIVE_SUBJECT),
            is_unresolved=self._is_unresolved_var,
        )
        for issue in analysis.issues:
            with self._owner(objective_issue_owner(issue)):
                self._err(self._objective_issue_message(issue))

    def _objective_issue_message(self, issue: ObjectiveIssue) -> str:
        """Render an objective issue, naming what the objective-subject purpose refuses."""

        if issue.code == "objective.target-ambiguous":
            choices = self._ambiguity_choices(issue.candidates, ReferencePurpose.OBJECTIVE_SUBJECT)
            return f"Objective '{issue.objective_name}' target '{issue.ref}' is ambiguous; use one of: {choices}"
        message = self._format_objective_issue(issue)
        unresolvable = issue.code == "objective.target-unresolvable"
        return f"{message}{self._ineligible_detail(issue.ref)}" if unresolvable else message

    @staticmethod
    def _format_objective_issue(issue: ObjectiveIssue) -> str:
        renderer = OBJECTIVE_ISSUE_RENDERERS.get(issue.code)
        if renderer is None:
            raise RuntimeError(f"unhandled objective-semantics issue code: {issue.code}")
        return renderer(issue)

    @staticmethod
    def _format_participant_behavior_issue(issue: ParticipantBehaviorIssue) -> str:
        renderer = _PARTICIPANT_BEHAVIOR_ISSUE_RENDERERS.get(issue.code)
        if renderer is None:
            raise RuntimeError(f"unhandled participant-behavior issue code: {issue.code}")
        return renderer(issue)

    @staticmethod
    def _format_participant_outcome_issue(issue: ParticipantOutcomeIssue) -> str:
        renderer = PARTICIPANT_OUTCOME_ISSUE_RENDERERS.get(issue.code)
        if renderer is None:
            raise RuntimeError(f"unhandled participant-outcome issue code: {issue.code}")
        return renderer(issue)
