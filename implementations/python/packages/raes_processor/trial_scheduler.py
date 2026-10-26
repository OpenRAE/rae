"""Deterministic batch-trial scheduling over the one-entry realization seam (SCE-006).

This is the repository-owned, schedule-independent handoff an orchestrator (APTL, or
any other coordinator) uses to run an admitted trial plan. It is an outer
coordinator over :func:`realize_admitted_trial_entry`: it may only choose
placement, deterministic order, bounded parallelism, timeouts, cancellation, and
cleanup (SVR-031). It never composes SDL, selects a variation, draws randomness,
allocates a ``run_id``, interprets factors, or scores.

:func:`plan_batch_schedule` is pure. It validates and integrity-checks the
*complete* admitted plan before exposing any entry, derives the canonical
dispatch order from the plan's ``trial-coordinate-v1`` coordinates, and reports
the *admitted parallelism ceiling* -- the maximum concurrency the sealed plan's
own embedded isolation proof authorizes (one when there is no such proof). It
deliberately does NOT decide the effective concurrency: proving live,
non-overlapping, currently-owned range/host/port/storage/lock/secret leases is
the downstream allocator's responsibility, and a non-empty tuple of caller
reference strings is not proof of any of that. The allocator decides an
effective bound no greater than the ceiling and records it, with its live lease
evidence, in a :class:`BatchExecutionReceiptModel` via
:func:`build_batch_execution_receipt`; that receipt records the allocator's
decision rather than authorizing it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from raes_contracts.admitted_trial_plan_ingress import revalidate_admitted_trial_plan
from raes_contracts.contracts import (
    AdmittedTrialPlanModel,
    BatchExecutionReceiptModel,
    validate_scheduler_isolation_proof,
)
from raes_contracts.contracts.trial_cleanup import TrialOutcome
from raes_contracts.contracts.trial_coordinate_order import (
    CANONICAL_ORDER_POLICY_ID,
    canonical_entry_order,
    scheduling_policy_id,
)

_T = TypeVar("_T")


@dataclass(frozen=True)
class ScheduledEntry:
    """One admitted entry at its canonical dispatch position."""

    plan_entry_id: str
    run_id: str
    dispatch_ordinal: int


@dataclass(frozen=True)
class BatchSchedule:
    """A deterministic, schedule-independent dispatch decision for one plan.

    ``admitted_parallelism_ceiling`` is the maximum concurrency the sealed plan's
    embedded isolation proof authorizes (one by default). The effective bound
    actually run is the downstream allocator's decision, no greater than this
    ceiling; it is not decided here.
    """

    plan_id: str
    plan_digest: str
    scheduling_policy_id: str
    admitted_parallelism_ceiling: int
    isolation_proof_ref: str | None
    entries: tuple[ScheduledEntry, ...]


@dataclass(frozen=True)
class AttemptOutcome:
    """The realized disposition and portable evidence of one execution attempt.

    ``cleanup_receipt_ref`` names the cleanup receipt proving the attempt's
    terminal cleanup; ``operation_refs`` are control-plane operation ids and
    ``attempt_deadline`` is an optional RFC 3339 deadline.
    """

    execution_attempt_id: str
    trial_outcome: TrialOutcome
    cleanup_receipt_ref: str
    operation_refs: Sequence[str] = ()
    attempt_deadline: str | None = None


@dataclass(frozen=True)
class AllocatorGrant:
    """The downstream allocator's live-lease parallelism decision for one attempt.

    ``effective_parallelism`` (serial by default) and ``lease_evidence_refs`` are
    the allocator's decision and its live lease evidence; ``isolation_proof_ref``
    defaults to the schedule's admitted proof for a bounded-parallel attempt.
    """

    effective_parallelism: int = 1
    lease_evidence_refs: Sequence[str] = ()
    isolation_proof_ref: str | None = None


def plan_batch_schedule(plan: AdmittedTrialPlanModel) -> BatchSchedule:
    """Compute the canonical dispatch order and admitted parallelism ceiling.

    The complete plan is revalidated before any per-entry consumption. The
    ceiling comes only from the plan's *embedded* isolation proof -- which the
    sealed ``plan_digest`` binds to the plan -- so a caller cannot inject a
    standalone or replayed proof to widen it. Serial (ceiling one) is the default
    whenever the plan carries no bounded-parallelism proof.
    """

    admitted = revalidate_admitted_trial_plan(plan)
    order = canonical_entry_order(admitted)
    scheduled = tuple(
        ScheduledEntry(plan_entry_id=entry_id, run_id=admitted.entries[entry_id].run_id, dispatch_ordinal=index)
        for index, entry_id in enumerate(order)
    )
    ceiling = 1
    proof_ref: str | None = None
    proof = admitted.isolation_proof
    if proof is not None:
        validate_scheduler_isolation_proof(admitted, proof)
        if proof.requested_parallelism > 1:
            ceiling = min(proof.requested_parallelism, len(scheduled))
            proof_ref = proof.proof_id
    return BatchSchedule(
        plan_id=admitted.plan_id,
        plan_digest=admitted.plan_digest,
        scheduling_policy_id=scheduling_policy_id(admitted),
        admitted_parallelism_ceiling=ceiling,
        isolation_proof_ref=proof_ref,
        entries=scheduled,
    )


def dispatch_batch_schedule(schedule: BatchSchedule, *, realize: Callable[[str], _T]) -> list[_T]:
    """Commit dispatch decisions in canonical order over the one-entry seam.

    One serialized coordinator calls ``realize`` once per scheduled entry, in
    canonical dispatch order, even when the caller's transport runs the resulting
    work concurrently (SVR-031). ``realize`` is the caller's binding to
    :func:`realize_admitted_trial_entry` (or an equivalent one-entry executor);
    live leasing and concurrent execution remain the caller's responsibility.
    Results are returned in dispatch order.
    """

    return [realize(entry.plan_entry_id) for entry in schedule.entries]


def build_batch_execution_receipt(
    schedule: BatchSchedule,
    plan_entry_id: str,
    *,
    receipt_id: str,
    outcome: AttemptOutcome,
    grant: AllocatorGrant | None = None,
) -> BatchExecutionReceiptModel:
    """Record one attempt's evidence, binding it to this schedule's decision.

    ``grant`` is the downstream allocator's live-lease parallelism decision
    (serial by default); its effective bound cannot exceed the schedule's
    admitted ceiling, and for a bounded-parallel attempt its isolation proof
    reference defaults to the schedule's admitted proof.
    """

    grant = grant if grant is not None else AllocatorGrant()
    scheduled = next((entry for entry in schedule.entries if entry.plan_entry_id == plan_entry_id), None)
    if scheduled is None:
        raise ValueError("plan_entry_id is not part of the batch schedule")
    if grant.effective_parallelism > schedule.admitted_parallelism_ceiling:
        raise ValueError("effective_parallelism cannot exceed the schedule's admitted parallelism ceiling")
    parallel = grant.effective_parallelism > 1
    proof_ref = grant.isolation_proof_ref
    if parallel and proof_ref is None:
        proof_ref = schedule.isolation_proof_ref
    return BatchExecutionReceiptModel(
        receipt_id=receipt_id,
        plan_id=schedule.plan_id,
        plan_digest=schedule.plan_digest,
        plan_entry_id=plan_entry_id,
        run_id=scheduled.run_id,
        execution_attempt_id=outcome.execution_attempt_id,
        dispatch_ordinal=scheduled.dispatch_ordinal,
        scheduling_policy_id=schedule.scheduling_policy_id,
        effective_parallelism=grant.effective_parallelism,
        isolation_proof_ref=proof_ref if parallel else None,
        lease_evidence_refs=list(grant.lease_evidence_refs) if parallel else [],
        attempt_deadline=outcome.attempt_deadline,
        trial_outcome=outcome.trial_outcome,
        operation_refs=list(outcome.operation_refs),
        cleanup_receipt_ref=outcome.cleanup_receipt_ref,
    )


__all__ = [
    "AllocatorGrant",
    "AttemptOutcome",
    "BatchSchedule",
    "CANONICAL_ORDER_POLICY_ID",
    "ScheduledEntry",
    "build_batch_execution_receipt",
    "dispatch_batch_schedule",
    "plan_batch_schedule",
]
