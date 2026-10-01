"""Behavior-specification aggregation, semantic-registry binding, and the top-level analyzer."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ._autonomous import _autonomous_execution_reference_issues
from ._behavior_spec import (
    _behavior_specification_reference_issues,
    _behavior_specification_vocabulary_issues,
)
from ._references import (
    _action_references_for_agent,
    _interaction_references_for_action_contracts,
    _observation_boundary_references_for_agent,
    _visibility_issues_for_observation_boundaries,
    select_participants,
)
from ._tool_affordance import _tool_affordance_reference_issues
from ._types import (
    ParticipantBehaviorAnalysis,
    ParticipantBehaviorIssue,
    ParticipantBehaviorReference,
    _BehaviorSpecificationReferenceContext,
)


def _behavior_specification_issues(
    behavior_specifications: Mapping[str, object],
    reference_context: _BehaviorSpecificationReferenceContext,
    is_unresolved: Callable[[object], bool],
) -> list[ParticipantBehaviorIssue]:
    issues: list[ParticipantBehaviorIssue] = []
    for spec_name, behavior_spec in behavior_specifications.items():
        normalized_spec_name = str(spec_name)
        issues.extend(
            _behavior_specification_reference_issues(
                spec_name=normalized_spec_name,
                behavior_spec=behavior_spec,
                reference_context=reference_context,
                is_unresolved=is_unresolved,
            )
        )
        issues.extend(
            _behavior_specification_vocabulary_issues(
                spec_name=normalized_spec_name,
                behavior_spec=behavior_spec,
                is_unresolved=is_unresolved,
            )
        )
        issues.extend(
            _autonomous_execution_reference_issues(
                spec_name=normalized_spec_name,
                behavior_spec=behavior_spec,
                reference_context=reference_context,
                is_unresolved=is_unresolved,
            )
        )
        issues.extend(
            _tool_affordance_reference_issues(
                spec_name=normalized_spec_name,
                behavior_spec=behavior_spec,
                agents_by_name=reference_context.agents_by_name,
                observation_boundaries=reference_context.observation_boundaries,
                reference_context=reference_context,
                is_unresolved=is_unresolved,
            )
        )
    autonomous_owner_by_participant: dict[str, str] = {}
    for spec_name, behavior_spec in behavior_specifications.items():
        if getattr(behavior_spec, "autonomous_execution", None) is None:
            continue
        participant_names = select_participants(
            behavior_spec, reference_context.participant_names, reference_context.participant_roles_by_agent
        )
        for participant_name in sorted(participant_names):
            prior_owner = autonomous_owner_by_participant.setdefault(participant_name, str(spec_name))
            if prior_owner != str(spec_name):
                issues.append(
                    ParticipantBehaviorIssue(
                        code="participant.autonomous-participant-owner-conflict",
                        participant_name=participant_name,
                        spec_name=str(spec_name),
                        ref=prior_owner,
                    )
                )
    return issues


@dataclass(frozen=True)
class _ParticipantBehaviorSemanticRegistries:
    participant_roles_by_agent: Mapping[str, str]
    outcome_interpretation_rules: Mapping[str, object]
    clocks: Mapping[str, object]
    time_progression_policies: Mapping[str, object]
    temporal_constraints: Mapping[str, object]
    objectives: Mapping[str, object]

    @classmethod
    def from_keywords(
        cls,
        semantic_registries: Mapping[str, object],
    ) -> _ParticipantBehaviorSemanticRegistries:
        expected = {
            "participant_roles_by_agent",
            "outcome_interpretation_rules",
            "clocks",
            "time_progression_policies",
            "temporal_constraints",
            "objectives",
        }
        missing = expected - semantic_registries.keys()
        unexpected = semantic_registries.keys() - expected
        if missing or unexpected:
            details = []
            if missing:
                details.append(f"missing {', '.join(sorted(missing))}")
            if unexpected:
                details.append(f"unexpected {', '.join(sorted(unexpected))}")
            raise TypeError("invalid participant behavior semantic registries: " + "; ".join(details))
        return cls(
            participant_roles_by_agent=semantic_registries["participant_roles_by_agent"],
            outcome_interpretation_rules=semantic_registries["outcome_interpretation_rules"],
            clocks=semantic_registries["clocks"],
            time_progression_policies=semantic_registries["time_progression_policies"],
            temporal_constraints=semantic_registries["temporal_constraints"],
            objectives=semantic_registries["objectives"],
        )


def _behavior_reference_context(
    agents_by_name: Mapping[str, object],
    action_contracts: Mapping[str, object],
    observation_boundaries: Mapping[str, object],
    registries: _ParticipantBehaviorSemanticRegistries,
) -> _BehaviorSpecificationReferenceContext:
    return _BehaviorSpecificationReferenceContext(
        participant_names={str(name) for name in agents_by_name},
        participant_roles_by_agent=registries.participant_roles_by_agent,
        action_names={str(name) for name in action_contracts},
        observation_boundary_names={str(name) for name in observation_boundaries},
        outcome_rule_names={str(name) for name in registries.outcome_interpretation_rules},
        agents_by_name=agents_by_name,
        action_contracts=action_contracts,
        observation_boundaries=observation_boundaries,
        clocks=registries.clocks,
        time_progression_policies=registries.time_progression_policies,
        temporal_constraints=registries.temporal_constraints,
        objectives=registries.objectives,
    )


def analyze_participant_behavior(
    *,
    agents_by_name: Mapping[str, object],
    action_contracts: Mapping[str, object],
    observation_boundaries: Mapping[str, object],
    behavior_specifications: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
    **semantic_registries: object,
) -> ParticipantBehaviorAnalysis:
    """Validate and normalize participant action/observation references.

    ``agents.*.actions`` can stay as a legacy authoring affordance when no
    action-contract registry exists. Once a scenario declares
    ``action_contracts``, every authored action name must resolve to that
    governed registry so the compiler never treats raw names as behavior
    semantics.
    """

    references: list[ParticipantBehaviorReference] = []
    issues: list[ParticipantBehaviorIssue] = []
    registries = _ParticipantBehaviorSemanticRegistries.from_keywords(semantic_registries)
    reference_context = _behavior_reference_context(
        agents_by_name,
        action_contracts,
        observation_boundaries,
        registries,
    )

    for participant_name, agent in agents_by_name.items():
        action_references, action_issues = _action_references_for_agent(
            participant_name=participant_name,
            action_names=list(getattr(agent, "actions", []) or []),
            action_contracts=action_contracts,
            is_unresolved=is_unresolved,
        )
        boundary_references, boundary_issues = _observation_boundary_references_for_agent(
            participant_name=participant_name,
            boundary_names=list(getattr(agent, "observation_boundaries", []) or []),
            observation_boundaries=observation_boundaries,
            is_unresolved=is_unresolved,
        )
        references.extend(action_references)
        references.extend(boundary_references)
        issues.extend(action_issues)
        issues.extend(boundary_issues)

    issues.extend(
        _interaction_references_for_action_contracts(
            action_contracts=action_contracts,
            is_unresolved=is_unresolved,
        )
    )
    issues.extend(
        _visibility_issues_for_observation_boundaries(
            observation_boundaries=observation_boundaries,
            is_unresolved=is_unresolved,
        )
    )
    issues.extend(
        _behavior_specification_issues(
            behavior_specifications,
            reference_context,
            is_unresolved,
        )
    )

    return ParticipantBehaviorAnalysis(references=tuple(references), issues=tuple(issues))
