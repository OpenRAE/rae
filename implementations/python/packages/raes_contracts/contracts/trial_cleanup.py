"""Portable clean-state, cleanup, and scheduler-isolation contracts (SCE-007)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..execution_retry import ExecutionRetryPolicyModel as ExecutionRetryPolicyModel
from ..versions import (
    SCHEDULER_ISOLATION_PROOF_SCHEMA_VERSION,
    TRIAL_CLEANUP_PLAN_SCHEMA_VERSION,
    TRIAL_CLEANUP_RECEIPT_SCHEMA_VERSION,
)
from ._trial_cleanup_validation import validate_reset_retry_obligations
from .base import ContractModel, NonEmptyString, PositiveInteger
from .schema_invariants import _add_raes_invariant

CleanupTrigger = Literal["success", "failure", "cancellation", "timeout", "retry", "abort"]
CleanupRequirement = Literal["required", "best-effort"]
CleanupActionKind = Literal["destroy", "reset", "restore", "compensate", "verify", "custom"]
CleanupIdempotency = Literal["idempotent", "requires-reset", "requires-compensation", "not-repeatable"]
CleanupOutcome = Literal["succeeded", "failed", "partial", "unsupported", "unverified", "not-required"]
TrialOutcome = Literal["succeeded", "failed", "cancelled", "timed-out", "aborted"]
IsolationDimension = Literal[
    "range-instance",
    "host-capacity",
    "ports",
    "storage",
    "control-plane-locks",
    "secret-scope",
    "cleanup",
]

REQUIRED_PARALLEL_ISOLATION_DIMENSIONS = frozenset(
    {
        "range-instance",
        "host-capacity",
        "ports",
        "storage",
        "control-plane-locks",
        "secret-scope",
        "cleanup",
    }
)


def _require_unique(field_name: str, values: Iterable[str]) -> None:
    materialized = list(values)
    if len(materialized) != len(set(materialized)):
        raise ValueError(f"{field_name} must not contain duplicates")


def _validate_cleanup_plan_map_keys(plan: TrialCleanupPlanModel) -> None:
    for key, boundary in plan.resource_boundaries.items():
        if key != boundary.boundary_id:
            raise ValueError("resource boundary map keys must equal embedded boundary_id")
    for key, obligation in plan.cleanup_obligations.items():
        if key != obligation.obligation_id:
            raise ValueError("cleanup obligation map keys must equal embedded obligation_id")


def _validate_cleanup_plan_references(plan: TrialCleanupPlanModel) -> None:
    referenced_boundaries = set(plan.clean_state.boundary_refs)
    for obligation in plan.cleanup_obligations.values():
        referenced_boundaries.update(obligation.boundary_refs)
    unknown_boundaries = sorted(referenced_boundaries - set(plan.resource_boundaries))
    if unknown_boundaries:
        raise ValueError(f"cleanup plan references unknown resource boundaries: {', '.join(unknown_boundaries)}")

    unknown_dependencies = sorted(
        {ref for obligation in plan.cleanup_obligations.values() for ref in obligation.depends_on}
        - set(plan.cleanup_obligations)
    )
    if unknown_dependencies:
        raise ValueError(f"cleanup plan references unknown cleanup dependencies: {', '.join(unknown_dependencies)}")


def _validate_cleanup_retry_safety(plan: TrialCleanupPlanModel) -> None:
    if plan.retry_policy.max_attempts <= 1:
        return
    non_idempotent = any(obligation.idempotency != "idempotent" for obligation in plan.cleanup_obligations.values())
    safe_policy = plan.retry_policy.after_effect_policy in {"reset", "compensate"}
    if non_idempotent and not safe_policy:
        raise ValueError("non-idempotent effects require explicit reset or compensation before retry")


class CleanupResourceBoundaryModel(ContractModel):
    """Owned resource scope to which cleanup and restoration claims are bounded."""

    boundary_id: NonEmptyString
    resource_kind: NonEmptyString
    owner_ref: NonEmptyString
    resource_refs: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def _validate_resource_refs(self) -> CleanupResourceBoundaryModel:
        _require_unique("resource_refs", self.resource_refs)
        return self


class CleanStateRequirementModel(ContractModel):
    """Pre-execution state requirement without claiming universal reversal."""

    mode: Literal["fresh", "verified-reset", "declared-reusable", "fresh-range-required"]
    boundary_refs: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    verification_probe_refs: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    reusable_state_claim_ref: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_evidence_boundary(self) -> CleanStateRequirementModel:
        _require_unique("clean_state boundary_refs", self.boundary_refs)
        _require_unique("clean_state verification_probe_refs", self.verification_probe_refs)
        if self.mode in {"fresh", "verified-reset"} and not self.verification_probe_refs:
            raise ValueError(f"{self.mode} clean state requires verification_probe_refs")
        if self.mode == "declared-reusable" and (
            not self.verification_probe_refs or self.reusable_state_claim_ref is None
        ):
            raise ValueError(
                "declared-reusable clean state requires verification_probe_refs and reusable_state_claim_ref"
            )
        if self.mode != "declared-reusable" and self.reusable_state_claim_ref is not None:
            raise ValueError("reusable_state_claim_ref is only valid for declared-reusable clean state")
        return self


class CleanupObligationModel(ContractModel):
    """One portable cleanup action and the conditions under which it is owed."""

    obligation_id: NonEmptyString
    boundary_refs: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    action_kind: CleanupActionKind
    action_profile_ref: NonEmptyString | None = None
    triggers: list[CleanupTrigger] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    requirement: CleanupRequirement
    depends_on: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    idempotency: CleanupIdempotency
    compensation_refs: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    verification_probe_refs: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    timeout_seconds: PositiveInteger

    @model_validator(mode="after")
    def _validate_obligation(self) -> CleanupObligationModel:
        for field_name, values in (
            ("boundary_refs", self.boundary_refs),
            ("triggers", self.triggers),
            ("depends_on", self.depends_on),
            ("compensation_refs", self.compensation_refs),
            ("verification_probe_refs", self.verification_probe_refs),
        ):
            _require_unique(field_name, values)
        if self.action_kind == "custom" and self.action_profile_ref is None:
            raise ValueError("custom cleanup actions require action_profile_ref")
        if self.action_kind != "custom" and self.action_profile_ref is not None:
            raise ValueError("action_profile_ref is only valid for custom cleanup actions")
        if self.requirement == "required" and not self.verification_probe_refs:
            raise ValueError("required cleanup obligations require verification_probe_refs")
        if self.idempotency == "requires-compensation" and not self.compensation_refs:
            raise ValueError("requires-compensation cleanup obligations require compensation_refs")
        return self


class TrialCleanupPlanModel(ContractModel):
    """Schedule-independent cleanup intent carried by one admitted trial entry."""

    schema_version: Literal[TRIAL_CLEANUP_PLAN_SCHEMA_VERSION] = TRIAL_CLEANUP_PLAN_SCHEMA_VERSION
    plan_id: NonEmptyString
    plan_entry_id: NonEmptyString
    run_id: NonEmptyString
    clean_state: CleanStateRequirementModel
    resource_boundaries: dict[NonEmptyString, CleanupResourceBoundaryModel] = Field(min_length=1)
    cleanup_obligations: dict[NonEmptyString, CleanupObligationModel] = Field(min_length=1)
    retry_policy: ExecutionRetryPolicyModel

    @model_validator(mode="after")
    def _validate_plan(self) -> TrialCleanupPlanModel:
        _validate_cleanup_plan_map_keys(self)
        _validate_cleanup_plan_references(self)
        self._validate_acyclic_dependencies()
        validate_reset_retry_obligations(self.cleanup_obligations, self.retry_policy)
        _validate_cleanup_retry_safety(self)
        return self

    def _validate_acyclic_dependencies(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(obligation_id: str) -> None:
            if obligation_id in visiting:
                raise ValueError("cleanup dependency graph must be acyclic")
            if obligation_id in visited:
                return
            visiting.add(obligation_id)
            for dependency in self.cleanup_obligations[obligation_id].depends_on:
                visit(dependency)
            visiting.remove(obligation_id)
            visited.add(obligation_id)

        for obligation_id in self.cleanup_obligations:
            visit(obligation_id)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        _add_raes_invariant(
            json_schema,
            "trial-cleanup-plan-references-and-retry-safe",
            "Cleanup boundary and dependency references resolve, ordering is acyclic, required cleanup is "
            "verifiable, and retries after non-idempotent effects declare required retry-triggered reset "
            "obligations covering the affected boundaries or compensation.",
            validator="raes_contracts.contracts.TrialCleanupPlanModel._validate_plan",
            inputs=[{"contract_id": "trial-cleanup-plan-v1", "instance_path": "#"}],
        )
        return json_schema


class CleanupObligationResultModel(ContractModel):
    """Attempt outcome for one declared cleanup obligation."""

    obligation_id: NonEmptyString
    status: Literal["succeeded", "failed", "skipped", "unsupported", "unverified", "not-triggered"]
    evidence_refs: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    residual_state_refs: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def _validate_result(self) -> CleanupObligationResultModel:
        _require_unique("cleanup result evidence_refs", self.evidence_refs)
        _require_unique("cleanup result residual_state_refs", self.residual_state_refs)
        if self.status == "succeeded" and not self.evidence_refs:
            raise ValueError("successful cleanup results require evidence_refs")
        if self.status in {"failed", "unverified"} and not (self.evidence_refs or self.residual_state_refs):
            raise ValueError(f"{self.status} cleanup results require failure evidence or residual state disclosure")
        if self.status == "succeeded" and self.residual_state_refs:
            raise ValueError("successful cleanup results cannot disclose residual state")
        return self


class CleanStateClaimModel(ContractModel):
    """Evidence-bounded post-cleanup state disposition."""

    disposition: Literal["verified-clean", "declared-reusable", "fresh-range-required"]
    boundary_refs: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    evidence_refs: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def _validate_refs(self) -> CleanStateClaimModel:
        _require_unique("clean state claim boundary_refs", self.boundary_refs)
        _require_unique("clean state claim evidence_refs", self.evidence_refs)
        return self


class TrialCleanupReceiptModel(ContractModel):
    """Immutable attempt receipt that reports cleanup separately from trial outcome."""

    schema_version: Literal[TRIAL_CLEANUP_RECEIPT_SCHEMA_VERSION] = TRIAL_CLEANUP_RECEIPT_SCHEMA_VERSION
    receipt_id: NonEmptyString
    cleanup_plan_ref: NonEmptyString
    plan_entry_id: NonEmptyString
    run_id: NonEmptyString
    execution_attempt_id: NonEmptyString
    trial_outcome: TrialOutcome
    cleanup_status: CleanupOutcome
    obligation_results: dict[NonEmptyString, CleanupObligationResultModel] = Field(default_factory=dict)
    clean_state_claim: CleanStateClaimModel | None = None

    @model_validator(mode="after")
    def _validate_receipt(self) -> TrialCleanupReceiptModel:
        if self.execution_attempt_id == self.run_id:
            raise ValueError("execution_attempt_id must remain distinct from run_id")
        for key, result in self.obligation_results.items():
            if key != result.obligation_id:
                raise ValueError("obligation result map keys must equal embedded obligation_id")
        if self.cleanup_status == "succeeded" and any(
            result.status not in {"succeeded", "not-triggered"} for result in self.obligation_results.values()
        ):
            raise ValueError("succeeded cleanup status cannot include unsuccessful obligation results")
        if self.cleanup_status == "not-required" and self.obligation_results:
            raise ValueError("not-required cleanup status cannot include obligation results")
        if self.clean_state_claim is not None and self.cleanup_status != "succeeded":
            raise ValueError("clean_state_claim requires succeeded cleanup")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {"cleanup_status": {"not": {"const": "succeeded"}}},
                    "required": ["cleanup_status"],
                },
                "then": {"properties": {"clean_state_claim": {"type": "null"}}},
            }
        )
        _add_raes_invariant(
            json_schema,
            "trial-cleanup-receipt-binds-plan-and-required-outcomes",
            "A cleanup receipt keeps attempt identity distinct, reports cleanup independently from trial outcome, "
            "covers every triggered required obligation, and permits clean-state claims only after verified success.",
            validator="raes_contracts.contracts.validate_trial_cleanup_receipt",
            inputs=[
                {"contract_id": "trial-cleanup-plan-v1", "instance_path": "#"},
                {"contract_id": "trial-cleanup-receipt-v1", "instance_path": "#"},
            ],
        )
        return json_schema


_OUTCOME_TRIGGER: dict[TrialOutcome, CleanupTrigger] = {
    "succeeded": "success",
    "failed": "failure",
    "cancelled": "cancellation",
    "timed-out": "timeout",
    "aborted": "abort",
}


def validate_trial_cleanup_receipt(plan: TrialCleanupPlanModel, receipt: TrialCleanupReceiptModel) -> None:
    """Validate one immutable receipt against the admitted cleanup plan it cites."""

    if receipt.cleanup_plan_ref != plan.plan_id:
        raise ValueError("cleanup receipt cleanup_plan_ref must match plan_id")
    if receipt.plan_entry_id != plan.plan_entry_id or receipt.run_id != plan.run_id:
        raise ValueError("cleanup receipt plan_entry_id and run_id must match the cleanup plan")
    unknown_results = sorted(set(receipt.obligation_results) - set(plan.cleanup_obligations))
    if unknown_results:
        raise ValueError(f"cleanup receipt references unknown obligations: {', '.join(unknown_results)}")
    _validate_triggered_cleanup_results(plan, receipt)
    _validate_clean_state_claim_boundaries(plan, receipt)


def _validate_triggered_cleanup_results(plan: TrialCleanupPlanModel, receipt: TrialCleanupReceiptModel) -> None:
    trigger = _OUTCOME_TRIGGER[receipt.trial_outcome]
    triggered_required = {
        obligation_id
        for obligation_id, obligation in plan.cleanup_obligations.items()
        if obligation.requirement == "required" and trigger in obligation.triggers
    }
    for obligation_id in sorted(triggered_required):
        result = receipt.obligation_results.get(obligation_id)
        if result is None or result.status != "succeeded":
            raise ValueError(f"required cleanup obligation '{obligation_id}' must succeed for trigger '{trigger}'")


def _validate_clean_state_claim_boundaries(plan: TrialCleanupPlanModel, receipt: TrialCleanupReceiptModel) -> None:
    if receipt.clean_state_claim is not None:
        unknown_boundaries = sorted(set(receipt.clean_state_claim.boundary_refs) - set(plan.resource_boundaries))
        if unknown_boundaries:
            raise ValueError(
                f"clean state claim references unknown resource boundaries: {', '.join(unknown_boundaries)}"
            )


class IsolationDimensionEvidenceModel(ContractModel):
    """Evidence for one bounded-parallelism isolation dimension."""

    dimension: IsolationDimension
    independent: bool
    evidence_refs: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def _validate_evidence(self) -> IsolationDimensionEvidenceModel:
        _require_unique("isolation evidence_refs", self.evidence_refs)
        return self


class SchedulerIsolationProofModel(ContractModel):
    """Schedule-independent proof permitting a bounded parallelism request."""

    schema_version: Literal[SCHEDULER_ISOLATION_PROOF_SCHEMA_VERSION] = SCHEDULER_ISOLATION_PROOF_SCHEMA_VERSION
    proof_id: NonEmptyString
    plan_entry_ids: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    requested_parallelism: PositiveInteger = 1
    dimensions: list[IsolationDimensionEvidenceModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_isolation(self) -> SchedulerIsolationProofModel:
        _require_unique("plan_entry_ids", self.plan_entry_ids)
        dimension_ids = [dimension.dimension for dimension in self.dimensions]
        _require_unique("isolation dimensions", dimension_ids)
        if self.requested_parallelism > 1:
            provided = set(dimension_ids)
            missing = sorted(REQUIRED_PARALLEL_ISOLATION_DIMENSIONS - provided)
            if missing:
                raise ValueError(f"parallel isolation proof requires dimensions: {', '.join(missing)}")
            non_independent = sorted(dimension.dimension for dimension in self.dimensions if not dimension.independent)
            if non_independent:
                raise ValueError(
                    "parallel isolation proof requires independent dimensions: " + ", ".join(non_independent)
                )
            if len(self.plan_entry_ids) < self.requested_parallelism:
                raise ValueError("requested_parallelism cannot exceed the number of plan entries")
        elif self.dimensions:
            raise ValueError("serial scheduling does not require a parallel isolation proof")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        parallel_then: dict[str, object] = {
            "properties": {
                "dimensions": {
                    "minItems": len(REQUIRED_PARALLEL_ISOLATION_DIMENSIONS),
                    "allOf": [
                        {
                            "contains": {
                                "type": "object",
                                "required": ["dimension", "independent", "evidence_refs"],
                                "properties": {
                                    "dimension": {"const": dimension},
                                    "independent": {"const": True},
                                    "evidence_refs": {"minItems": 1},
                                },
                            }
                        }
                        for dimension in sorted(REQUIRED_PARALLEL_ISOLATION_DIMENSIONS)
                    ],
                }
            }
        }
        json_schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {"requested_parallelism": {"minimum": 2}},
                    "required": ["requested_parallelism"],
                },
                "then": parallel_then,
            }
        )
        _add_raes_invariant(
            json_schema,
            "scheduler-isolation-serial-default-and-complete-parallel-proof",
            "Scheduling defaults to serial; bounded parallelism requires independent evidence for range, capacity, "
            "ports, storage, control-plane locks, secret scope, and cleanup.",
            validator="raes_contracts.contracts.SchedulerIsolationProofModel._validate_isolation",
            inputs=[{"contract_id": "scheduler-isolation-proof-v1", "instance_path": "#"}],
        )
        return json_schema


__all__ = [
    "CleanupActionKind",
    "CleanupIdempotency",
    "CleanupObligationModel",
    "CleanupObligationResultModel",
    "CleanupOutcome",
    "CleanupRequirement",
    "CleanupResourceBoundaryModel",
    "CleanupTrigger",
    "CleanStateClaimModel",
    "CleanStateRequirementModel",
    "ExecutionRetryPolicyModel",
    "IsolationDimension",
    "IsolationDimensionEvidenceModel",
    "REQUIRED_PARALLEL_ISOLATION_DIMENSIONS",
    "SchedulerIsolationProofModel",
    "TrialCleanupPlanModel",
    "TrialCleanupReceiptModel",
    "TrialOutcome",
    "validate_trial_cleanup_receipt",
]
