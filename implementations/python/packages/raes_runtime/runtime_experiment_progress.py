"""Advance admitted experiment entries without changing trial retry authority."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.runtime_state import OperationKind
from raes_processor.trial_scheduler import AttemptOutcome, build_batch_execution_receipt

from .control_plane_mutation import control_plane_mutation
from .runtime_decisions import RunContextDecision
from .runtime_trial_decisions import ExperimentCancellationDecision, TrialAttemptDecision, TrialTerminalDecision

if TYPE_CHECKING:
    from .runtime_decisions import RuntimeDecision
    from .runtime_experiment import ExperimentProgress, RuntimeExperiment, TrialSlot
    from .runtime_trial_unit import RuntimeTrialUnit


def advance_experiment(experiment: RuntimeExperiment, identity: object | None) -> ExperimentProgress:
    from .runtime_experiment import ExperimentProgress

    records = experiment.engine._store.load_runtime_decisions()
    cancelled = any(
        isinstance(record, ExperimentCancellationDecision) and record.experiment_id == experiment.experiment_id
        for record in records
    )
    terminals = {record.execution_attempt_id: record for record in records if isinstance(record, TrialTerminalDecision)}
    for slot in _pending_slots(experiment, records):
        progress = _advance_slot(experiment, slot, records, terminals, cancelled, identity)
        if progress is not None:
            return progress
    return ExperimentProgress(experiment.experiment_id, "cancelled" if cancelled else "completed")


def _pending_slots(experiment: RuntimeExperiment, records: tuple[RuntimeDecision, ...]) -> tuple[TrialSlot, ...]:
    retired = {
        record.run_scope for record in records if isinstance(record, RunContextDecision) and record.status == "retired"
    }
    return tuple(slot for slot in experiment._slots(records) if "run:" + slot.entry.run_id not in retired)


def _advance_slot(
    experiment: RuntimeExperiment,
    slot: TrialSlot,
    records: tuple[RuntimeDecision, ...],
    terminals: dict[str, TrialTerminalDecision],
    cancelled: bool,
    identity: object | None,
) -> ExperimentProgress | None:
    from .runtime_experiment import ExperimentProgress

    existing = sorted(
        (
            record
            for record in records
            if isinstance(record, TrialAttemptDecision)
            and record.experiment_id == experiment.experiment_id
            and record.plan_entry_id == slot.entry.plan_entry_id
        ),
        key=lambda record: record.attempt,
    )
    if cancelled and not existing:
        return ExperimentProgress(experiment.experiment_id, "cancelled")
    attempt = existing[-1] if existing else experiment._attempt(slot, 1, records)
    for prior_attempt in existing:
        experiment._unit(slot, prior_attempt, identity)
    unit = experiment._unit(slot, attempt, identity)
    terminal = terminals.get(attempt.execution_attempt_id)
    if terminal is not None:
        return _finish_attempt(experiment, slot, unit, terminal, records, cancelled)
    return _advance_unit(experiment, slot, unit, cancelled)


def _finish_attempt(
    experiment: RuntimeExperiment,
    slot: TrialSlot,
    unit: RuntimeTrialUnit,
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
    experiment.engine.retire_run(unit.run._run_scope)
    return experiment._progress("progress", slot.entry, unit.attempt) if allocated else None


def _advance_unit(
    experiment: RuntimeExperiment, slot: TrialSlot, unit: RuntimeTrialUnit, cancelled: bool
) -> ExperimentProgress:
    run = unit.run
    run._engine.reserve(run)
    with (
        run._runtime_call(),
        run._resource_claim.runtime_call(experiment.engine),
        control_plane_mutation(run, OperationKind.COMPOSITION_PHASE),
    ):
        state = unit.advance(cancelled=cancelled)
    if state == "succeeded":
        _record_terminal(experiment, slot, unit)
        state = "progress"
    return experiment._progress(state, slot.entry, unit.attempt)


def _record_terminal(experiment: RuntimeExperiment, slot: TrialSlot, unit: RuntimeTrialUnit) -> None:
    result, attempt = unit.result(), unit.attempt
    receipt = build_batch_execution_receipt(
        slot.schedule,
        slot.entry.plan_entry_id,
        receipt_id="batch:" + attempt.execution_attempt_id,
        outcome=AttemptOutcome(
            execution_attempt_id=attempt.execution_attempt_id,
            trial_outcome=result.cleanup_receipt.trial_outcome,
            cleanup_receipt_ref=result.cleanup_receipt.receipt_id,
            operation_refs=tuple(receipt.operation_id for receipt in result.operation_receipts),
            attempt_deadline=attempt.deadline,
        ),
    )
    experiment.engine._store.claim_runtime_decision(
        TrialTerminalDecision(
            execution_attempt_id=attempt.execution_attempt_id,
            receipt=receipt,
            capture_status="succeeded" if unit.capture_succeeded() else "failed",
            reusable=unit.reusable(),
        )
    )


def retry_attempt(unit: RuntimeTrialUnit, terminal: TrialTerminalDecision) -> str:
    policy = unit.request.cleanup_plan.retry_policy
    if terminal.receipt.trial_outcome != "failed" or unit.attempt.attempt >= policy.max_attempts:
        return "not-permitted"
    observed = unit.observations()
    execution = observed["execution"].observation
    if not execution.ceased or not terminal.reusable:
        return "not-permitted"
    return "ready" if execution.effects_absent else _retry_after_effects(unit)


def _retry_after_effects(unit: RuntimeTrialUnit) -> str:
    policy = unit.request.cleanup_plan.retry_policy
    state = "not-permitted"
    if policy.after_effect_policy == "idempotent":
        if unit.observations()["cleanup"].observation.idempotent_effects:
            state = "ready"
    elif policy.after_effect_policy in {"reset", "compensate"}:
        state = _prepare_retry(unit)
    return state


def _prepare_retry(unit: RuntimeTrialUnit) -> str:
    run = unit.run
    run._engine.reserve(run)
    with (
        run._runtime_call(),
        run._resource_claim.runtime_call(run._engine.owner),
        control_plane_mutation(run, OperationKind.COMPOSITION_PHASE),
    ):
        state = unit.prepare_retry()
    if state != "succeeded":
        return state if state in {"pending", "indeterminate"} else "cleanup-failed"
    retry = unit.observations().get("retry")
    return "ready" if retry is not None and retry.observation.ready else "cleanup-failed"
