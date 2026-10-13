"""Tool-affordance relation, action/boundary widening, and view-classification checks."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from ...participant_behavior_specification import tool_affordance_reference
from ._references import _observation_boundary_declared_refs, _tool_affordance_participants, select_participants
from ._types import (
    ParticipantBehaviorIssue,
    _BehaviorSpecificationReferenceContext,
)


def _tool_affordance_duplicate_issue(
    *,
    spec_name: str,
    affordance_id: str,
    tool_ref: object,
    action_refs: list[str],
    boundary_refs: list[str],
    seen_relations: dict[tuple[str, tuple[str, ...], tuple[str, ...]], str],
) -> ParticipantBehaviorIssue | None:
    signature = (str(tool_ref or ""), tuple(sorted(action_refs)), tuple(sorted(boundary_refs)))
    duplicate_of = seen_relations.get(signature)
    if duplicate_of is None:
        seen_relations[signature] = affordance_id
        return None
    return ParticipantBehaviorIssue(
        code="participant.tool-affordance-duplicate-relation",
        participant_name="",
        spec_name=spec_name,
        ref=affordance_id,
        message=duplicate_of,
    )


def _tool_affordance_action_issues(
    *,
    spec_name: str,
    affordance_id: str,
    action_ref: str,
    parent_actions: set[str],
    participants: set[str],
    agents_by_name: Mapping[str, object],
) -> list[ParticipantBehaviorIssue]:
    issues: list[ParticipantBehaviorIssue] = []
    if action_ref not in parent_actions:
        issues.append(
            ParticipantBehaviorIssue(
                code="participant.tool-affordance-action-widens-parent",
                participant_name="",
                spec_name=spec_name,
                ref=action_ref,
                action_name=affordance_id,
            )
        )
    for participant_name in sorted(participants):
        agent_actions = {str(ref) for ref in getattr(agents_by_name[participant_name], "actions", []) or []}
        if action_ref not in agent_actions:
            issues.append(
                ParticipantBehaviorIssue(
                    code="participant.tool-affordance-action-outside-participant",
                    participant_name=participant_name,
                    spec_name=spec_name,
                    ref=action_ref,
                    action_name=affordance_id,
                )
            )
    return issues


def _tool_affordance_boundary_issues(
    *,
    spec_name: str,
    affordance_id: str,
    boundary_ref: str,
    parent_boundaries: set[str],
    participants: set[str],
    agents_by_name: Mapping[str, object],
    observation_boundaries: Mapping[str, object],
) -> list[ParticipantBehaviorIssue]:
    issues: list[ParticipantBehaviorIssue] = []
    if boundary_ref not in parent_boundaries:
        issues.append(
            ParticipantBehaviorIssue(
                code="participant.tool-affordance-boundary-widens-parent",
                participant_name="",
                spec_name=spec_name,
                ref=boundary_ref,
                action_name=affordance_id,
            )
        )
    for participant_name in sorted(participants):
        agent_boundaries = {
            str(ref) for ref in getattr(agents_by_name[participant_name], "observation_boundaries", []) or []
        }
        if boundary_ref not in agent_boundaries:
            issues.append(
                ParticipantBehaviorIssue(
                    code="participant.tool-affordance-boundary-outside-participant",
                    participant_name=participant_name,
                    spec_name=spec_name,
                    ref=boundary_ref,
                    action_name=affordance_id,
                )
            )
    boundary = observation_boundaries.get(boundary_ref)
    if boundary is None:
        return issues
    binding_ref = tool_affordance_reference(spec_name, affordance_id)
    declared_refs = _observation_boundary_declared_refs(boundary)
    view_rule_refs = {str(getattr(rule, "information_ref", "")) for rule in getattr(boundary, "view_rules", []) or []}
    if binding_ref not in declared_refs or binding_ref not in view_rule_refs:
        issues.append(
            ParticipantBehaviorIssue(
                code="participant.tool-affordance-view-unclassified",
                participant_name="",
                spec_name=spec_name,
                ref=binding_ref,
                action_name=affordance_id,
                boundary_name=boundary_ref,
            )
        )
    return issues


def _tool_affordance_is_scoped(binding: object) -> bool:
    """Return whether a binding authors its own participant selector (ACT-619).

    Scoped is a syntactic property of the two raw selector lists, never of the
    resolved participant set: a scoped binding that resolves to nobody stays scoped.
    """

    return bool(getattr(binding, "participant_refs", None) or getattr(binding, "participant_role_refs", None))


def _tool_affordance_selector_issues(
    *,
    spec_name: str,
    affordance_id: str,
    binding: object,
    behavior_spec: object,
    spec_participants: set[str],
    reference_context: _BehaviorSpecificationReferenceContext,
    is_unresolved: Callable[[object], bool],
) -> tuple[set[str], list[ParticipantBehaviorIssue]]:
    """Resolve a scoped binding selector with the shared PI-03 resolver and check it only narrows."""

    def unbound(refs: list[object], known: set[str], code: str) -> list[ParticipantBehaviorIssue]:
        return [
            ParticipantBehaviorIssue(
                code=code, participant_name="", spec_name=spec_name, ref=str(ref), action_name=affordance_id
            )
            for ref in refs
            if not is_unresolved(ref) and str(ref) not in known
        ]

    issues = unbound(
        list(getattr(binding, "participant_refs", []) or []),
        reference_context.participant_names,
        "participant.tool-affordance-participant-unbound",
    ) + unbound(
        list(getattr(binding, "participant_role_refs", []) or []),
        reference_context.participant_roles,
        "participant.tool-affordance-role-unbound",
    )
    selected = select_participants(
        binding, reference_context.participant_names, reference_context.participant_roles_by_agent
    )
    spec_selector = [
        *(getattr(behavior_spec, "participant_refs", []) or []),
        *(getattr(behavior_spec, "participant_role_refs", []) or []),
    ]
    if not any(is_unresolved(ref) for ref in spec_selector):
        issues.extend(
            ParticipantBehaviorIssue(
                code="participant.tool-affordance-participant-widens-parent",
                participant_name=participant_name,
                spec_name=spec_name,
                ref=participant_name,
                action_name=affordance_id,
            )
            for participant_name in sorted(selected - spec_participants)
        )
    return selected, issues


def _resolved_reference_issues(
    refs: list[str],
    is_unresolved: Callable[[object], bool],
    build_issues: Callable[[str], list[ParticipantBehaviorIssue]],
) -> list[ParticipantBehaviorIssue]:
    issues: list[ParticipantBehaviorIssue] = []
    for ref in refs:
        if not is_unresolved(ref):
            issues.extend(build_issues(ref))
    return issues


def _tool_affordance_reference_issues(
    *,
    spec_name: str,
    behavior_spec: object,
    agents_by_name: Mapping[str, object],
    observation_boundaries: Mapping[str, object],
    reference_context: _BehaviorSpecificationReferenceContext,
    is_unresolved: Callable[[object], bool],
) -> list[ParticipantBehaviorIssue]:
    issues: list[ParticipantBehaviorIssue] = []
    parent_actions = {str(ref) for ref in getattr(behavior_spec, "action_contract_refs", []) or []}
    parent_boundaries = {str(ref) for ref in getattr(behavior_spec, "observation_boundary_refs", []) or []}
    spec_participants = _tool_affordance_participants(behavior_spec, reference_context)
    seen_relations: dict[tuple[str, tuple[str, ...], tuple[str, ...]], str] = {}
    for affordance_id, binding in getattr(behavior_spec, "tool_affordances", {}).items():
        affordance_id = str(affordance_id)
        action_refs = [str(ref) for ref in getattr(binding, "action_contract_refs", []) or []]
        boundary_refs = [str(ref) for ref in getattr(binding, "observation_boundary_refs", []) or []]
        duplicate_issue = _tool_affordance_duplicate_issue(
            spec_name=spec_name,
            affordance_id=affordance_id,
            tool_ref=getattr(binding, "tool_ref", None),
            action_refs=action_refs,
            boundary_refs=boundary_refs,
            seen_relations=seen_relations,
        )
        if duplicate_issue is not None:
            issues.append(duplicate_issue)
        participants = spec_participants
        if _tool_affordance_is_scoped(binding):
            participants, selector_issues = _tool_affordance_selector_issues(
                spec_name=spec_name,
                affordance_id=affordance_id,
                binding=binding,
                behavior_spec=behavior_spec,
                spec_participants=spec_participants,
                reference_context=reference_context,
                is_unresolved=is_unresolved,
            )
            issues.extend(selector_issues)

        issues.extend(
            _resolved_reference_issues(
                action_refs,
                is_unresolved,
                lambda action_ref, affordance_id=affordance_id, participants=participants: (
                    _tool_affordance_action_issues(
                        spec_name=spec_name,
                        affordance_id=affordance_id,
                        action_ref=action_ref,
                        parent_actions=parent_actions,
                        participants=participants,
                        agents_by_name=agents_by_name,
                    )
                ),
            )
        )
        issues.extend(
            _resolved_reference_issues(
                boundary_refs,
                is_unresolved,
                lambda boundary_ref, affordance_id=affordance_id, participants=participants: (
                    _tool_affordance_boundary_issues(
                        spec_name=spec_name,
                        affordance_id=affordance_id,
                        boundary_ref=boundary_ref,
                        parent_boundaries=parent_boundaries,
                        participants=participants,
                        agents_by_name=agents_by_name,
                        observation_boundaries=observation_boundaries,
                    )
                ),
            )
        )
    return issues
