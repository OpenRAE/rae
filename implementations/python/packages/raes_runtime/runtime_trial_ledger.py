"""Read-only queries over the existing closed trial decision ledger."""

from __future__ import annotations

from collections.abc import Iterable

from raes_contracts.assigned_trial import TrialAssignmentModel

from .runtime_assignment_decisions import TrialAssignmentDecision
from .runtime_decisions import RuntimeDecision
from .runtime_trial_decisions import ExperimentCancellationDecision, TrialAttemptDecision, TrialTerminalDecision


def entry_attempts(
    records: Iterable[RuntimeDecision], experiment_id: str, entry_id: str
) -> tuple[TrialAttemptDecision, ...]:
    return tuple(
        sorted(
            (
                item
                for item in records
                if isinstance(item, TrialAttemptDecision)
                and item.experiment_id == experiment_id
                and item.plan_entry_id == entry_id
            ),
            key=lambda item: item.attempt,
        )
    )


def latest_entry_attempts(records: Iterable[RuntimeDecision], experiment_id: str) -> dict[str, TrialAttemptDecision]:
    latest = {}
    for item in records:
        if not isinstance(item, TrialAttemptDecision) or item.experiment_id != experiment_id:
            continue
        previous = latest.get(item.plan_entry_id)
        if previous is None or previous.attempt < item.attempt:
            latest[item.plan_entry_id] = item
    return latest


def trial_terminals(records: Iterable[RuntimeDecision]) -> dict[str, TrialTerminalDecision]:
    return {item.execution_attempt_id: item for item in records if isinstance(item, TrialTerminalDecision)}


def experiment_cancelled(records: Iterable[RuntimeDecision], experiment_id: str) -> bool:
    return any(
        isinstance(item, ExperimentCancellationDecision) and item.experiment_id == experiment_id for item in records
    )


def attempt_assignment(records: Iterable[RuntimeDecision], attempt_id: str) -> TrialAssignmentModel | None:
    return next(
        (
            item.assignment
            for item in records
            if isinstance(item, TrialAssignmentDecision) and item.assignment.execution_attempt_id == attempt_id
        ),
        None,
    )


def retained_assignment(
    records: Iterable[RuntimeDecision], experiment_id: str, digest: str
) -> TrialAssignmentModel | None:
    return next(
        (
            item.assignment
            for item in records
            if isinstance(item, TrialAssignmentDecision)
            and item.assignment.experiment_id == experiment_id
            and item.assignment.content_digest == digest
        ),
        None,
    )


def entries_assigned(records: Iterable[RuntimeDecision], entry_ids: set[str]) -> bool:
    return any(
        isinstance(item, TrialAssignmentDecision) and item.assignment.plan_entry_id in entry_ids for item in records
    )


def retained_attempt(records: Iterable[RuntimeDecision], attempt_id: str) -> TrialAttemptDecision:
    return next(
        item for item in records if isinstance(item, TrialAttemptDecision) and item.execution_attempt_id == attempt_id
    )
