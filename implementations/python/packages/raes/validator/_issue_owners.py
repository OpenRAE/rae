"""Owners of semantic-analysis issues that the validator records as errors.

Each function returns the ``(section, name)`` pair of the declaration that the
error message of an issue names first, or None when the message names none.
"""

from operator import attrgetter

from ..semantics.objective_semantics import ObjectiveIssue
from ..semantics.participant_behavior import ParticipantBehaviorIssue
from ..semantics.participant_outcome import ParticipantOutcomeIssue

_AGENT_ISSUES = frozenset(
    {
        "participant.action-contract-unbound",
        "participant.affiliation-duplicate",
        "participant.affiliation-unbound",
        "participant.observation-boundary-unbound",
    }
)
_ACTION_CONTRACT_ISSUES = frozenset({"participant.interaction-action-unbound"})
_OBSERVATION_BOUNDARY_ISSUES = frozenset(
    {
        "participant.view-rule-evidence-unbound",
        "participant.view-rule-ref-unbound",
        "participant.view-transition-evidence-unbound",
        "participant.view-transition-ref-unbound",
    }
)
_BEHAVIOR_ISSUE_OWNERS = (
    (_AGENT_ISSUES, "agents", attrgetter("participant_name")),
    (_ACTION_CONTRACT_ISSUES, "action_contracts", attrgetter("action_name")),
    (_OBSERVATION_BOUNDARY_ISSUES, "observation_boundaries", attrgetter("boundary_name")),
)


def objective_issue_owner(issue: ObjectiveIssue) -> tuple[str, str] | None:
    """Return the objective of an objective issue. The global dependency cycle has no owner."""

    return None if issue.code == "objective.dependency-cycle" else ("objectives", issue.objective_name)


def participant_behavior_issue_owner(issue: ParticipantBehaviorIssue) -> tuple[str, str]:
    """Return the agent, action contract, observation boundary or behavior specification of a behavior issue."""

    for codes, section, name in _BEHAVIOR_ISSUE_OWNERS:
        if issue.code in codes:
            return section, name(issue)
    return "behavior_specifications", issue.spec_name


def participant_outcome_issue_owner(issue: ParticipantOutcomeIssue) -> tuple[str, str]:
    """Return the outcome interpretation rule of an outcome issue."""

    return "outcome_interpretation_rules", issue.rule_name


__all__ = ["objective_issue_owner", "participant_behavior_issue_owner", "participant_outcome_issue_owner"]
