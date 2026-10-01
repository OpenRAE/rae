"""Name-level participant outcome interpretation semantics (SEM-215)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from raes.participant_outcome_semantics import (
    OutcomeInterpretationSourceLayer,
    OutcomeInterpretationTargetLayer,
)


@dataclass(frozen=True)
class ParticipantOutcomeIssue:
    """Machine-readable participant outcome interpretation consistency issue."""

    code: str
    rule_name: str
    binding_id: str
    ref: str
    layer: str


@dataclass(frozen=True)
class ParticipantOutcomeAnalysis:
    """Result of analyzing outcome interpretation rule references."""

    issues: tuple[ParticipantOutcomeIssue, ...] = ()

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)


def _source_ref_issue(
    *,
    rule_name: str,
    binding: object,
    action_contracts: Mapping[str, object],
    objectives: Mapping[str, object],
    workflows: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> ParticipantOutcomeIssue | None:
    layer = getattr(binding, "source_layer", None)
    ref = getattr(binding, "ref", "")
    binding_id = str(getattr(binding, "source_id", ""))
    if is_unresolved(ref):
        return None
    if layer == OutcomeInterpretationSourceLayer.PARTICIPANT_ACTION_OUTCOME and ref not in action_contracts:
        return ParticipantOutcomeIssue(
            code="participant.outcome.source-action-unbound",
            rule_name=rule_name,
            binding_id=binding_id,
            ref=str(ref),
            layer=layer.value,
        )
    if layer == OutcomeInterpretationSourceLayer.OBJECTIVE_RESULT and ref not in objectives:
        return ParticipantOutcomeIssue(
            code="participant.outcome.source-objective-unbound",
            rule_name=rule_name,
            binding_id=binding_id,
            ref=str(ref),
            layer=layer.value,
        )
    if layer == OutcomeInterpretationSourceLayer.WORKFLOW_RESULT and ref not in workflows:
        return ParticipantOutcomeIssue(
            code="participant.outcome.source-workflow-unbound",
            rule_name=rule_name,
            binding_id=binding_id,
            ref=str(ref),
            layer=layer.value,
        )
    # Per ADR-073 the SDL `evaluations` section was removed; the
    # EVALUATION_RESULT interpretation layer remains a governed
    # experiment/evaluator-plane concept whose ref is not bound to an SDL
    # section, so no SDL cross-reference check applies to it here.
    return None


def _target_ref_issue(
    *,
    rule_name: str,
    binding: object,
    objectives: Mapping[str, object],
    workflows: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> ParticipantOutcomeIssue | None:
    layer = getattr(binding, "target_layer", None)
    ref = getattr(binding, "ref", "")
    binding_id = str(getattr(binding, "target_id", ""))
    if is_unresolved(ref):
        return None
    if layer == OutcomeInterpretationTargetLayer.OBJECTIVE_RESULT and ref not in objectives:
        return ParticipantOutcomeIssue(
            code="participant.outcome.target-objective-unbound",
            rule_name=rule_name,
            binding_id=binding_id,
            ref=str(ref),
            layer=layer.value,
        )
    if layer == OutcomeInterpretationTargetLayer.WORKFLOW_RESULT and ref not in workflows:
        return ParticipantOutcomeIssue(
            code="participant.outcome.target-workflow-unbound",
            rule_name=rule_name,
            binding_id=binding_id,
            ref=str(ref),
            layer=layer.value,
        )
    # EVALUATION_RESULT targets are an experiment/evaluator-plane concept after
    # ADR-073 and carry no SDL-section cross-reference here.
    return None


def analyze_participant_outcome_interpretations(
    *,
    outcome_interpretation_rules: Mapping[str, object],
    action_contracts: Mapping[str, object],
    objectives: Mapping[str, object],
    workflows: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> ParticipantOutcomeAnalysis:
    """Validate source/target refs declared by SEM-215 interpretation rules."""

    issues: list[ParticipantOutcomeIssue] = []
    for rule_name, rule in outcome_interpretation_rules.items():
        issues.extend(_local_effect_issues(str(rule_name), rule, action_contracts))
        for binding in getattr(rule, "source_bindings", ()) or ():
            issue = _source_ref_issue(
                rule_name=str(rule_name),
                binding=binding,
                action_contracts=action_contracts,
                objectives=objectives,
                workflows=workflows,
                is_unresolved=is_unresolved,
            )
            if issue is not None:
                issues.append(issue)
        for binding in getattr(rule, "target_bindings", ()) or ():
            issue = _target_ref_issue(
                rule_name=str(rule_name),
                binding=binding,
                objectives=objectives,
                workflows=workflows,
                is_unresolved=is_unresolved,
            )
            if issue is not None:
                issues.append(issue)
    return ParticipantOutcomeAnalysis(issues=tuple(issues))


__all__ = [
    "ParticipantOutcomeAnalysis",
    "ParticipantOutcomeIssue",
    "analyze_participant_outcome_interpretations",
]


def _local_effect_issues(
    rule_name: str, rule: object, action_contracts: Mapping[str, object]
) -> list[ParticipantOutcomeIssue]:
    issues: list[ParticipantOutcomeIssue] = []
    local = getattr(rule, "local_outcome", None)
    if local is not None:
        sources = {source.source_id: source for source in rule.source_bindings}
        for criterion in local.criteria:
            source = sources[criterion.source_id]
            action = action_contracts.get(source.ref)
            if action is not None and criterion.effect_id not in {effect.effect_id for effect in action.effects}:
                issues.append(
                    ParticipantOutcomeIssue(
                        code="participant.outcome.local-effect-unbound",
                        rule_name=str(rule_name),
                        binding_id=criterion.criterion_id,
                        ref=criterion.effect_id,
                        layer="local_outcome_effect",
                    )
                )
    return issues
