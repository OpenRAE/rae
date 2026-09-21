"""Autonomous-execution progression, cadence, evaluation-authority, and reference-issue orchestration."""

from __future__ import annotations

from collections.abc import Callable

from ._autonomous_bindings import (
    _autonomous_action_issues,
    _autonomous_boundary_issues,
    _autonomous_declaration_issues,
    _autonomous_issue,
    _autonomous_time_binding_issues,
    _AutonomousExecutionReferenceContext,
    _AutonomousTimeBindings,
)
from ._references import _resolve_section_ref, _tool_affordance_participants
from ._types import (
    ParticipantBehaviorIssue,
    _BehaviorSpecificationReferenceContext,
)


def _autonomous_progression_issues(
    context: _AutonomousExecutionReferenceContext,
    bindings: _AutonomousTimeBindings,
) -> list[ParticipantBehaviorIssue]:
    policy = context.policy
    progression_mode = getattr(getattr(bindings.progression, "advancement_mode", None), "value", "")
    clock_authority = getattr(getattr(bindings.clock, "authority_kind", None), "value", "")
    issues: list[ParticipantBehaviorIssue] = []
    if progression_mode == "externally_paced":
        issues.append(
            _autonomous_issue(
                context,
                "participant.autonomous-progression-driver-unsupported",
                policy.progression_policy_ref,
            )
        )
    if progression_mode in {"real_time", "dilated"} and clock_authority != "runtime":
        issues.append(
            _autonomous_issue(context, "participant.autonomous-clock-authority-unsupported", policy.clock_ref)
        )
    if bindings.cadence_count == 1 and bindings.cadence is not None:
        start = getattr(bindings.cadence, "start", None)
        start_tick = getattr(start, "tick", 0) if start is not None else 0
        if not isinstance(start_tick, int) or start_tick < 0:
            issues.append(
                _autonomous_issue(
                    context,
                    "participant.autonomous-cadence-unreachable",
                    policy.progression_policy_ref,
                )
            )
    issues.extend(_autonomous_stepped_cadence_issues(context, bindings, progression_mode))
    return issues


def _activity_timing_unreachable(
    policy: object,
    step_ticks: object,
) -> bool:
    minimum_ticks = policy.timing.minimum_ticks
    maximum_ticks = policy.timing.maximum_ticks
    return not (isinstance(step_ticks, int) and not minimum_ticks % step_ticks and not maximum_ticks % step_ticks)


def _cadence_unreachable(bindings: _AutonomousTimeBindings, step_ticks: object) -> bool:
    cadence_ticks = getattr(bindings.cadence, "cadence_ticks", None)
    start = getattr(bindings.cadence, "start", None)
    start_tick = getattr(start, "tick", 0) if start is not None else 0
    return not (
        isinstance(step_ticks, int)
        and isinstance(cadence_ticks, int)
        and start_tick >= 0
        and not start_tick % step_ticks
        and not cadence_ticks % step_ticks
    )


def _autonomous_stepped_issue_code(
    context: _AutonomousExecutionReferenceContext,
    bindings: _AutonomousTimeBindings,
) -> str | None:
    step_ticks = getattr(bindings.progression, "step_ticks", None)
    activity_policy = getattr(context.policy, "profile", "participant-autonomous-execution/v1") in {
        "participant-autonomous-execution/v2",
        "participant-autonomous-execution/v3",
    }
    if activity_policy and _activity_timing_unreachable(context.policy, step_ticks):
        return "participant.autonomous-activity-timing-unreachable"
    if (
        not activity_policy
        and bindings.cadence_count == 1
        and bindings.cadence is not None
        and _cadence_unreachable(bindings, step_ticks)
    ):
        return "participant.autonomous-cadence-unreachable"
    return None


def _autonomous_stepped_cadence_issues(
    context: _AutonomousExecutionReferenceContext,
    bindings: _AutonomousTimeBindings,
    progression_mode: str,
) -> list[ParticipantBehaviorIssue]:
    issues: list[ParticipantBehaviorIssue] = []
    if progression_mode == "stepped":
        issue_code = _autonomous_stepped_issue_code(
            context,
            bindings,
        )
        if issue_code is not None:
            issues.append(
                _autonomous_issue(
                    context,
                    issue_code,
                    context.policy.progression_policy_ref,
                )
            )
    return issues


def _autonomous_non_evaluated_issues(
    context: _AutonomousExecutionReferenceContext,
) -> list[ParticipantBehaviorIssue]:
    issues: list[ParticipantBehaviorIssue] = []
    for participant_name in sorted(context.participants):
        role = context.references.participant_roles_by_agent.get(participant_name, "")
        if role != "green":
            issues.append(
                _autonomous_issue(
                    context,
                    "participant.autonomous-non-evaluated-role-not-green",
                    role,
                    participant_name=participant_name,
                )
            )
        has_objective = any(
            getattr(objective, "assigned_participant", None) == participant_name
            for objective in context.references.objectives.values()
        )
        if has_objective:
            issues.append(
                _autonomous_issue(
                    context,
                    "participant.autonomous-non-evaluated-objective-authority",
                    participant_name,
                    participant_name=participant_name,
                )
            )
    has_widened_authority = getattr(context.behavior_spec, "outcome_interpretation_rule_refs", None) or getattr(
        context.behavior_spec, "authority_scope_refs", None
    )
    if has_widened_authority:
        issues.append(
            _autonomous_issue(
                context,
                "participant.autonomous-non-evaluated-authority-widening",
                context.spec_name,
            )
        )
    return issues


def _autonomous_declared_authority_issues(
    context: _AutonomousExecutionReferenceContext,
) -> list[ParticipantBehaviorIssue]:
    authority = context.policy.evaluation_authority
    issues: list[ParticipantBehaviorIssue] = []
    for objective_ref in authority.objective_refs:
        if context.is_unresolved(objective_ref):
            continue
        objective_name = _resolve_section_ref(objective_ref, "objectives", context.references.objectives)
        if objective_name is None:
            issues.append(
                _autonomous_issue(
                    context,
                    "participant.autonomous-evaluation-objective-unbound",
                    objective_ref,
                )
            )
        else:
            assignment = getattr(context.references.objectives[objective_name], "assigned_participant", None)
            if not context.is_unresolved(assignment) and assignment not in context.participants:
                issues.append(
                    _autonomous_issue(context, "participant.autonomous-objective-not-assigned", objective_ref)
                )
    unsupported_authority_refs = (
        ("proof_producer_refs", authority.proof_producer_refs),
        ("score_authority_refs", authority.score_authority_refs),
        ("receipt_authority_refs", authority.receipt_authority_refs),
    )
    for field_name, refs in unsupported_authority_refs:
        for ref in refs:
            if not context.is_unresolved(ref):
                issues.append(
                    _autonomous_issue(
                        context,
                        "participant.autonomous-evaluation-authority-namespace-unsupported",
                        ref,
                        message=field_name,
                    )
                )
    return issues


def _autonomous_evaluation_issues(
    context: _AutonomousExecutionReferenceContext,
) -> list[ParticipantBehaviorIssue]:
    authority_mode = getattr(context.policy.evaluation_authority.mode, "value", "")
    if authority_mode == "none":
        return _autonomous_non_evaluated_issues(context)
    if authority_mode == "declared":
        return _autonomous_declared_authority_issues(context)
    return []


def _autonomous_execution_reference_issues(
    *,
    spec_name: str,
    behavior_spec: object,
    reference_context: _BehaviorSpecificationReferenceContext,
    is_unresolved: Callable[[object], bool],
) -> list[ParticipantBehaviorIssue]:
    policy = getattr(behavior_spec, "autonomous_execution", None)
    if policy is None:
        return []
    context = _AutonomousExecutionReferenceContext(
        spec_name=spec_name,
        behavior_spec=behavior_spec,
        policy=policy,
        references=reference_context,
        participants=_tool_affordance_participants(behavior_spec, reference_context),
        is_unresolved=is_unresolved,
    )
    time_issues, bindings = _autonomous_time_binding_issues(context)
    return [
        *_autonomous_declaration_issues(context),
        *_autonomous_action_issues(context),
        *_autonomous_boundary_issues(context),
        *time_issues,
        *_autonomous_progression_issues(context, bindings),
        *_autonomous_evaluation_issues(context),
    ]
