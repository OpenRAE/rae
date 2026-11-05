"""Advance admitted experiment entries without changing trial retry authority."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.errors import ConflictError

from .runtime_assignment_decisions import TrialAssignmentDecision
from .runtime_decisions import RunContextDecision
from .runtime_trial_binding import ExperimentProgress, trial_terminal_decision
from .runtime_trial_decisions import ExperimentCancellationDecision, TrialAttemptDecision, TrialTerminalDecision
from .runtime_trial_ledger import attempt_assignment, entry_attempts

if TYPE_CHECKING:
    from raes_processor.trial_scheduler import AllocatorGrant

    from .runtime_decisions import RuntimeDecision
    from .runtime_experiment import RuntimeExperiment, TrialSlot
    from .runtime_remote_trial import RemoteTrialUnit
    from .runtime_trial_unit import RuntimeTrialUnit


def advance_experiment(experiment: RuntimeExperiment, identity: object | None) -> ExperimentProgress:
    records = experiment.engine._store.load_runtime_decisions()
    cancelled = any(
        isinstance(record, ExperimentCancellationDecision) and record.experiment_id == experiment.experiment_id
        for record in records
    )
    terminals = {record.execution_attempt_id: record for record in records if isinstance(record, TrialTerminalDecision)}
    for slot in _pending_slots(experiment, records):
        progress = advance_trial_slot(experiment, slot, records, terminals, cancelled, identity)
        if progress is not None:
            return progress
    return ExperimentProgress(experiment.experiment_id, "cancelled" if cancelled else "completed")


def _pending_slots(experiment: RuntimeExperiment, records: tuple[RuntimeDecision, ...]) -> tuple[TrialSlot, ...]:
    retired = {
        record.run_scope for record in records if isinstance(record, RunContextDecision) and record.status == "retired"
    }
    return tuple(slot for slot in experiment._slots(records) if "run:" + slot.entry.run_id not in retired)


def advance_trial_slot(
    experiment: RuntimeExperiment,
    slot: TrialSlot,
    records: tuple[RuntimeDecision, ...],
    terminals: dict[str, TrialTerminalDecision],
    cancelled: bool,
    identity: object | None,
) -> ExperimentProgress | None:
    existing = entry_attempts(records, experiment.experiment_id, slot.entry.plan_entry_id)
    if cancelled and not existing:
        return ExperimentProgress(experiment.experiment_id, "cancelled")
    assigned_entries = {item.assignment.plan_entry_id for item in records if isinstance(item, TrialAssignmentDecision)}
    if not existing and slot.root_entry_id in assigned_entries:
        return ExperimentProgress(experiment.experiment_id, "ready", slot.entry.plan_entry_id)
    return _advance_existing_slot(experiment, slot, existing, terminals, records, cancelled, identity)


def _advance_existing_slot(
    experiment: RuntimeExperiment,
    slot: TrialSlot,
    existing: tuple[TrialAttemptDecision, ...],
    terminals: dict[str, TrialTerminalDecision],
    records: tuple[RuntimeDecision, ...],
    cancelled: bool,
    identity: object | None,
) -> ExperimentProgress | None:
    assigned_entries = {item.assignment.plan_entry_id for item in records if isinstance(item, TrialAssignmentDecision)}
    if (
        not existing
        and slot.root_entry_id not in assigned_entries
        and experiment.schedule.admitted_parallelism_floor > 1
    ):
        raise ConflictError("trial parallelism requires an allocator assignment before execution")
    attempt = existing[-1] if existing else experiment._attempt(slot, 1, records)
    records = experiment.store.load_runtime_decisions()
    assigned = attempt_assignment(records, attempt.execution_attempt_id) is not None
    if assigned and attempt.execution_attempt_id not in terminals:
        return ExperimentProgress(
            experiment.experiment_id, "pending", slot.entry.plan_entry_id, attempt.execution_attempt_id
        )
    if not assigned and slot.entry.plan_entry_id in assigned_entries:
        return ExperimentProgress(
            experiment.experiment_id, "ready", slot.entry.plan_entry_id, attempt.execution_attempt_id
        )
    for prior_attempt in existing:
        experiment._unit(slot, prior_attempt, identity)
    unit = experiment._unit(slot, attempt, identity)
    terminal = terminals.get(attempt.execution_attempt_id)
    return (
        _finish_attempt(experiment, slot, unit, terminal, records, cancelled)
        if terminal is not None
        else _advance_unit(experiment, slot, unit, cancelled)
    )


def _finish_attempt(
    experiment: RuntimeExperiment,
    slot: TrialSlot,
    unit: RuntimeTrialUnit | RemoteTrialUnit,
    terminal: TrialTerminalDecision,
    records: tuple[RuntimeDecision, ...],
    cancelled: bool,
) -> ExperimentProgress | None:
    if not terminal.reusable:
        return experiment._progress("cleanup-failed", slot.entry, unit.attempt)
    retry = "not-permitted" if cancelled else retry_attempt(unit, terminal)
    if retry != "not-permitted":
        attempt = unit.attempt
        if retry == "ready":
            attempt = experiment._attempt(slot, attempt.attempt + 1, records)
            retry = "progress"
        return experiment._progress(retry, slot.entry, attempt)
    from .runtime_experiment_replacement import archive_and_replace

    allocated = archive_and_replace(experiment, slot, unit, records, allow_replacement=not cancelled)
    unit.retire()
    return experiment._progress("progress", slot.entry, unit.attempt) if allocated else None


def _advance_unit(
    experiment: RuntimeExperiment, slot: TrialSlot, unit: RuntimeTrialUnit, cancelled: bool
) -> ExperimentProgress:
    state = unit.advance_runtime(cancelled=cancelled)
    if state == "succeeded":
        record_trial_terminal(experiment, slot, unit)
        state = "progress"
    return experiment._progress(state, slot.entry, unit.attempt)


def record_trial_terminal(
    experiment: RuntimeExperiment,
    slot: TrialSlot,
    unit: RuntimeTrialUnit | RemoteTrialUnit,
    *,
    grant: AllocatorGrant | None = None,
) -> None:
    experiment.store.claim_runtime_decision(
        trial_terminal_decision(
            unit.attempt,
            unit.result(),
            slot.schedule,
            slot.entry.plan_entry_id,
            capture_succeeded=unit.capture_succeeded(),
            reusable=unit.reusable(),
            grant=grant,
        )
    )


def retry_attempt(unit: RuntimeTrialUnit | RemoteTrialUnit, terminal: TrialTerminalDecision) -> str:
    permission = retry_permission(unit, terminal)
    return _prepare_retry(unit) if permission == "prepare" else permission


def retry_permission(unit: RuntimeTrialUnit | RemoteTrialUnit, terminal: TrialTerminalDecision) -> str:
    """Read policy and retained observations without preparing or dispatching effects."""
    policy = unit.request.cleanup_plan.retry_policy
    if terminal.receipt.trial_outcome != "failed" or unit.attempt.attempt >= policy.max_attempts:
        return "not-permitted"
    observed = unit.observations()
    execution = observed["execution"].observation
    if not execution.ceased or not terminal.reusable:
        return "not-permitted"
    return "ready" if execution.effects_absent else _retry_after_effects(unit)


def _retry_after_effects(unit: RuntimeTrialUnit | RemoteTrialUnit) -> str:
    policy = unit.request.cleanup_plan.retry_policy
    state = "not-permitted"
    if policy.after_effect_policy == "idempotent":
        if unit.observations()["cleanup"].observation.idempotent_effects:
            state = "ready"
    elif policy.after_effect_policy in {"reset", "compensate"}:
        state = "prepare"
    return state


def _prepare_retry(unit: RuntimeTrialUnit | RemoteTrialUnit) -> str:
    state = unit.prepare_retry_runtime()
    if state != "succeeded":
        return state if state in {"pending", "indeterminate"} else "cleanup-failed"
    retry = unit.observations().get("retry")
    return "ready" if retry is not None and retry.observation.ready else "cleanup-failed"
