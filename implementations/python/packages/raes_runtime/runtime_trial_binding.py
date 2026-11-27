"""Runtime trial bindings with no dependency on execution implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from raes_contracts.trial_unit import TrialUnitRequest
from raes_processor.trial_scheduler import AttemptOutcome, build_batch_execution_receipt

from .runtime_trial_decisions import TrialTerminalDecision

if TYPE_CHECKING:
    from raes_contracts.contracts import AdmittedTrialPlanModel
    from raes_contracts.trial_unit import TrialUnitResult
    from raes_processor.trial_realization import TrialRealization
    from raes_processor.trial_scheduler import AllocatorGrant, BatchSchedule, ScheduledEntry

    from .runtime_trial_decisions import TrialAttemptDecision


@dataclass(frozen=True)
class ExperimentProgress:
    experiment_id: str
    state: str
    plan_entry_id: str | None = None
    execution_attempt_id: str | None = None


@dataclass(frozen=True)
class TrialSlot:
    plan: AdmittedTrialPlanModel
    schedule: BatchSchedule
    entry: ScheduledEntry
    realization: TrialRealization
    root_entry_id: str


def trial_request(
    plan: AdmittedTrialPlanModel, entry_id: str, realization: TrialRealization, attempt_id: str
) -> TrialUnitRequest:
    return TrialUnitRequest(
        plan=plan,
        plan_entry_id=entry_id,
        execution_attempt_id=attempt_id,
        instantiated_sdl_digest=realization.snapshot_digest,
        provisioning_plan=realization.provisioning_plan,
        orchestration_plan=realization.orchestration_plan,
        evaluation_plan=realization.evaluation_plan,
    )


def trial_terminal_decision(
    attempt: TrialAttemptDecision,
    result: TrialUnitResult,
    schedule: BatchSchedule,
    entry_id: str,
    *,
    capture_succeeded: bool,
    reusable: bool,
    grant: AllocatorGrant | None = None,
) -> TrialTerminalDecision:
    """Use one checked terminal projection for coordinator and execution owner."""
    receipt = build_batch_execution_receipt(
        schedule,
        entry_id,
        receipt_id="batch:" + attempt.execution_attempt_id,
        outcome=AttemptOutcome(
            execution_attempt_id=attempt.execution_attempt_id,
            trial_outcome=result.cleanup_receipt.trial_outcome,
            cleanup_receipt_ref=result.cleanup_receipt.receipt_id,
            operation_refs=tuple(receipt.operation_id for receipt in result.operation_receipts),
            attempt_deadline=attempt.deadline,
        ),
        grant=grant,
    )
    return TrialTerminalDecision(
        execution_attempt_id=attempt.execution_attempt_id,
        receipt=receipt,
        capture_status="succeeded" if capture_succeeded else "failed",
        reusable=reusable,
    )
