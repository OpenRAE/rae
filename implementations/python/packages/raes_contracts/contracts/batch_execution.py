"""Isolated batch-trial scheduling handoff and evidence contracts (SCE-006).

The scheduler is an outer coordinator over the existing one-entry realization
seam (ADR-084; ``specs/formal/scenario-variation-trial-realization/README.md``
invariants SVR-014, SVR-019..022, SVR-031). It may choose placement, order,
bounded parallelism, timeouts, cancellation, and cleanup only; it never composes
SDL, selects a variation, draws randomness, allocates a ``run_id``, or scores.

Authority boundary. This layer never turns a caller-presented reference string
into live parallelism authority. The *admitted* concurrency ceiling comes only
from an isolation proof that is embedded in the sealed plan (bound to the plan
by its digest). The *effective* concurrency actually run, and the live lease
evidence backing it, are decided by the downstream allocator (APTL) against
resources this repository cannot certify; a receipt therefore *records* that
prior allocator decision as evidence and this layer verifies only that the
recorded claim is authorized by the sealed plan's own proof -- it does not, and
cannot, verify live lease ownership, currentness, or fencing.

This module publishes:

- :func:`validate_scheduler_isolation_proof` -- structural consistency of an
  isolation proof against a plan's admitted entries (membership plus, for
  bounded parallelism, cleanup-boundary resource non-overlap). It is a
  consistency check, not an authorization: parallel authority is only ever the
  plan's *embedded* proof, which the sealed ``plan_digest`` binds to the plan.
- :class:`BatchExecutionReceiptModel` -- one immutable attempt receipt that
  *composes* (never replaces) the incumbent operation and cleanup authorities.
  :func:`validate_batch_execution_receipt` joins it to the exact sealed plan,
  verifies the recorded dispatch ordinal against the one canonical order,
  authorizes any bounded-parallelism claim only from the plan's embedded proof,
  and requires a matching, successfully validated cleanup receipt so a failed or
  suppressed cleanup can never be reported as a clean successful trial.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..versions import BATCH_EXECUTION_RECEIPT_SCHEMA_VERSION
from .admitted_trial_plan import AdmittedTrialPlanModel, isolation_resource_overlaps
from .base import (
    ContractModel,
    NonEmptyString,
    NonNegativeInteger,
    PositiveInteger,
    PrefixedDigestString,
    Rfc3339DateTimeString,
)
from .schema_invariants import _add_raes_invariant
from .trial_cleanup import (
    SchedulerIsolationProofModel,
    TrialCleanupReceiptModel,
    TrialOutcome,
    validate_trial_cleanup_receipt,
)
from .trial_coordinate_order import CANONICAL_ORDER_POLICY_ID, canonical_entry_order, scheduling_policy_id


def validate_scheduler_isolation_proof(plan: AdmittedTrialPlanModel, proof: SchedulerIsolationProofModel) -> None:
    """Check one isolation proof for structural consistency against the plan.

    ``SchedulerIsolationProofModel`` structurally validates its dimensions and
    bounds, but not membership in a particular plan. This confirms every named
    entry belongs to the plan and, for a bounded-parallelism request, that the
    authorized entries own non-overlapping cleanup resources. It is a
    consistency check only: it is not an authorization, and a standalone proof
    presented by a caller is never a substitute for the plan's own embedded
    proof, which the sealed ``plan_digest`` binds to the plan.
    """

    unknown = sorted(set(proof.plan_entry_ids) - set(plan.entries))
    if unknown:
        raise ValueError(f"isolation proof references entries outside the admitted plan: {', '.join(unknown)}")
    if proof.requested_parallelism <= 1:
        return
    overlap = isolation_resource_overlaps(plan, list(proof.plan_entry_ids))
    if overlap:
        raise ValueError("isolation proof authorizes parallel entries that share resources: " + ", ".join(overlap))


class BatchExecutionReceiptModel(ContractModel):
    """Immutable receipt for one admitted-trial execution attempt (SCE-006).

    It composes the scheduling decision and the incumbent operation/cleanup
    evidence for a single attempt without becoming queue state or a second run.
    ``effective_parallelism``, ``isolation_proof_ref``, and ``lease_evidence_refs``
    record a prior allocator decision; they do not authorize execution.
    """

    schema_version: Literal[BATCH_EXECUTION_RECEIPT_SCHEMA_VERSION] = BATCH_EXECUTION_RECEIPT_SCHEMA_VERSION
    receipt_id: NonEmptyString
    plan_id: NonEmptyString
    plan_digest: PrefixedDigestString
    plan_entry_id: NonEmptyString
    run_id: NonEmptyString
    execution_attempt_id: NonEmptyString
    dispatch_ordinal: NonNegativeInteger
    scheduling_policy_id: Literal["trial-coordinate-canonical-v1", "experiment-recorded-allocation-v1"] = (
        CANONICAL_ORDER_POLICY_ID
    )
    effective_parallelism: PositiveInteger = 1
    isolation_proof_ref: NonEmptyString | None = None
    lease_evidence_refs: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    attempt_deadline: Rfc3339DateTimeString | None = None
    trial_outcome: TrialOutcome
    operation_refs: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    cleanup_receipt_ref: NonEmptyString

    @model_validator(mode="after")
    def _validate_receipt(self) -> BatchExecutionReceiptModel:
        # Preallocated archival run identity, plan identity, and attempt identity
        # must stay distinct (SVR-020..022): an attempt is never a run, and a
        # retry is a new attempt, never a silently new trial.
        if self.execution_attempt_id in {self.run_id, self.plan_entry_id, self.plan_id}:
            raise ValueError("execution_attempt_id must be distinct from run_id, plan_entry_id, and plan_id")
        if len(self.lease_evidence_refs) != len(set(self.lease_evidence_refs)):
            raise ValueError("lease_evidence_refs must not contain duplicates")
        if len(self.operation_refs) != len(set(self.operation_refs)):
            raise ValueError("operation_refs must not contain duplicates")
        if self.effective_parallelism == 1:
            if self.isolation_proof_ref is not None:
                raise ValueError("serial execution (effective_parallelism 1) must not cite an isolation proof")
            if self.lease_evidence_refs:
                raise ValueError("serial execution (effective_parallelism 1) must not cite live lease evidence")
        else:
            if self.isolation_proof_ref is None:
                raise ValueError("bounded parallelism requires an isolation_proof_ref")
            if not self.lease_evidence_refs:
                raise ValueError("bounded parallelism requires live lease_evidence_refs")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {"effective_parallelism": {"minimum": 2}},
                    "required": ["effective_parallelism"],
                },
                "then": {
                    "required": ["isolation_proof_ref", "lease_evidence_refs"],
                    "properties": {
                        "isolation_proof_ref": {"type": "string"},
                        "lease_evidence_refs": {"minItems": 1},
                    },
                },
            }
        )
        _add_raes_invariant(
            json_schema,
            "batch-execution-receipt-binds-plan-schedule-and-attempt",
            "A batch execution receipt keeps attempt identity distinct from plan, entry, and run identities, records "
            "the canonical dispatch ordinal under the closed canonical order policy, cites an isolation proof plus "
            "live lease evidence only for bounded parallelism (serial default cites neither), and references the "
            "cleanup receipt that proves its terminal cleanup.",
            validator="raes_contracts.contracts.batch_execution.BatchExecutionReceiptModel._validate_receipt",
            inputs=[{"contract_id": "batch-execution-receipt-v1", "instance_path": "#"}],
        )
        return json_schema


def validate_batch_execution_receipt(
    plan: AdmittedTrialPlanModel,
    receipt: BatchExecutionReceiptModel,
    *,
    cleanup_receipt: TrialCleanupReceiptModel,
) -> None:
    """Join one immutable attempt receipt to the exact sealed plan and cleanup.

    The receipt binds to the sealed plan identity and one of its entries; its
    dispatch ordinal must equal that entry's position in the one canonical
    order; any bounded-parallelism claim is authorized only by the plan's own
    embedded isolation proof; and the supplied cleanup receipt must match the
    attempt and pass :func:`validate_trial_cleanup_receipt`, so a failed,
    unverified, or suppressed cleanup can never be reported as a clean trial.
    """

    if receipt.plan_id != plan.plan_id:
        raise ValueError("batch execution receipt plan_id must match the admitted plan_id")
    if receipt.plan_digest != plan.plan_digest:
        raise ValueError("batch execution receipt plan_digest must match the sealed admitted plan_digest")
    entry = plan.entries.get(receipt.plan_entry_id)
    if entry is None:
        raise ValueError("batch execution receipt plan_entry_id does not resolve inside the admitted plan")
    if receipt.run_id != entry.run_id:
        raise ValueError("batch execution receipt run_id must match the admitted entry run_id")
    if receipt.scheduling_policy_id != scheduling_policy_id(plan):
        raise ValueError("batch execution receipt scheduling policy must match the admitted allocation")
    expected_ordinal = canonical_entry_order(plan).index(receipt.plan_entry_id)
    if receipt.dispatch_ordinal != expected_ordinal:
        raise ValueError("batch execution receipt dispatch_ordinal does not match the canonical dispatch order")
    _validate_receipt_isolation(plan, receipt)
    _validate_receipt_cleanup(plan, receipt, entry, cleanup_receipt)


def _validate_receipt_isolation(plan: AdmittedTrialPlanModel, receipt: BatchExecutionReceiptModel) -> None:
    if receipt.effective_parallelism <= 1:
        return
    proof = plan.isolation_proof
    if proof is None:
        raise ValueError("bounded-parallel receipt requires an admitted plan isolation proof")
    if receipt.isolation_proof_ref != proof.proof_id:
        raise ValueError("batch execution receipt isolation_proof_ref must match the admitted plan isolation proof")
    if receipt.effective_parallelism > proof.requested_parallelism:
        raise ValueError("effective_parallelism cannot exceed the admitted isolation proof requested_parallelism")
    if receipt.plan_entry_id not in proof.plan_entry_ids:
        raise ValueError("bounded-parallel receipt entry is not authorized by the isolation proof")
    validate_scheduler_isolation_proof(plan, proof)


def _validate_receipt_cleanup(
    plan: AdmittedTrialPlanModel,
    receipt: BatchExecutionReceiptModel,
    entry: object,
    cleanup_receipt: TrialCleanupReceiptModel,
) -> None:
    if receipt.cleanup_receipt_ref != cleanup_receipt.receipt_id:
        raise ValueError("batch execution receipt cleanup_receipt_ref must match the cleanup receipt id")
    if (
        cleanup_receipt.plan_entry_id != receipt.plan_entry_id
        or cleanup_receipt.run_id != receipt.run_id
        or cleanup_receipt.execution_attempt_id != receipt.execution_attempt_id
    ):
        raise ValueError("cleanup receipt identities must match the batch execution receipt attempt")
    if cleanup_receipt.trial_outcome != receipt.trial_outcome:
        raise ValueError("cleanup receipt trial_outcome must match the batch execution receipt trial_outcome")
    cleanup_plan_ref = entry.execution_controls.cleanup_plan_ref  # type: ignore[attr-defined]
    cleanup_plan = plan.cleanup_plans.get(cleanup_plan_ref)
    if cleanup_plan is None:
        raise ValueError("admitted entry cleanup_plan_ref does not resolve to a plan cleanup block")
    validate_trial_cleanup_receipt(cleanup_plan, cleanup_receipt)


__all__ = [
    "BATCH_EXECUTION_RECEIPT_SCHEMA_VERSION",
    "BatchExecutionReceiptModel",
    "validate_batch_execution_receipt",
    "validate_scheduler_isolation_proof",
]
