"""Known execution facts for complete and partial records of started trials."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonEmptyString, PositiveInteger, PrefixedDigestString, Rfc3339DateTimeString
from .experiment_bindings import ParticipantConfigurationResultModel
from .experiment_evidence import ExperimentEvidenceRecordModel
from .experiment_manifest_references import ExperimentEvidenceRecordReferenceModel
from .trial_cleanup import TrialCleanupReceiptModel

if TYPE_CHECKING:
    from .experiment_run import ExperimentRunModel


class ExperimentAttemptAccountingModel(ContractModel):
    execution_attempt_id: NonEmptyString
    attempt: PositiveInteger
    started_at: Rfc3339DateTimeString
    ended_at: Rfc3339DateTimeString | None = None
    execution_status: Literal["unknown", "running", "succeeded", "failed", "cancelled", "timed-out", "aborted"]
    configuration_status: Literal["unobserved", "observed", "failed"] = "unobserved"
    capture_status: Literal["unobserved", "complete", "partial", "failed"] = "unobserved"
    cleanup_status: Literal[
        "unobserved", "succeeded", "failed", "partial", "unsupported", "unverified", "not-required"
    ] = "unobserved"
    cleanup_receipt: TrialCleanupReceiptModel | None = None
    operation_refs: list[NonEmptyString] = Field(default_factory=list, max_length=4096)
    evidence_record_refs: list[ExperimentEvidenceRecordReferenceModel] = Field(default_factory=list, max_length=20480)
    evidence_records: list[ExperimentEvidenceRecordModel] = Field(default_factory=list, max_length=1024)

    @model_validator(mode="after")
    def _validate_attempt(self) -> ExperimentAttemptAccountingModel:
        from .base import _parse_rfc3339_datetime

        start = _parse_rfc3339_datetime("started_at", self.started_at)
        if self.ended_at is not None:
            if self.execution_status in {"unknown", "running"}:
                raise ValueError("unresolved execution must not claim an end time")
            if _parse_rfc3339_datetime("ended_at", self.ended_at) < start:
                raise ValueError("attempt end time precedes its start")
        if self.cleanup_receipt is not None and self.cleanup_receipt.execution_attempt_id != self.execution_attempt_id:
            raise ValueError("cleanup receipt must belong to its execution attempt")
        if self.cleanup_receipt is not None and self.cleanup_receipt.cleanup_status != self.cleanup_status:
            raise ValueError("cleanup status must match its retained receipt")
        if len(self.operation_refs) != len(set(self.operation_refs)):
            raise ValueError("attempt operation references must be unique")
        ids = [(item.evidence_record_id, item.record_version) for item in self.evidence_records]
        if len(ids) != len(set(ids)):
            raise ValueError("attempt evidence identities must be unique")
        return self


class ExperimentExecutionAccountingModel(ContractModel):
    plan_id: NonEmptyString
    plan_digest: PrefixedDigestString
    plan_entry_id: NonEmptyString
    entry_digest: PrefixedDigestString
    attempts: list[ExperimentAttemptAccountingModel] = Field(min_length=1, max_length=1000)
    participant_configurations: list[ParticipantConfigurationResultModel] = Field(default_factory=list, max_length=4096)

    @model_validator(mode="after")
    def _validate_accounting(self) -> ExperimentExecutionAccountingModel:
        ids = [item.execution_attempt_id for item in self.attempts]
        if len(ids) != len(set(ids)) or [item.attempt for item in self.attempts] != list(range(1, len(ids) + 1)):
            raise ValueError("execution accounting must retain unique, contiguous ordered attempts")
        return self


def validate_run_record_shape(run: ExperimentRunModel) -> None:
    if run.record_state == "partial":
        _validate_partial_record_shape(run)
    else:
        _validate_archival_record_shape(run)
    if run.run_status in {"in-progress", "indeterminate"} and run.ended_at is not None:
        raise ValueError("unresolved runs must not claim an end time")
    if run.ended_at is None and (run.difficulty_provenance is not None or run.realized_time_model is not None):
        raise ValueError("bounded time provenance requires an observed end time")
    if run.execution_accounting is not None:
        _validate_accounting_consistency(run)
        _validate_attempt_membership(run)


def _validate_partial_record_shape(run: ExperimentRunModel) -> None:
    if run.execution_accounting is None:
        raise ValueError("partial records require execution accounting")
    if run.outcome_status == "succeeded" or run.run_status == "sealed":
        raise ValueError("partial records cannot claim scientific success or sealing")


def _validate_archival_record_shape(run: ExperimentRunModel) -> None:
    if run.run_status in {"in-progress", "indeterminate"}:
        raise ValueError("archival records require a resolved execution status")
    required = (run.ended_at, run.apparatus_context, run.traceability, run.evidence_artifacts, run.result_summaries)
    if run.execution_accounting is None and (not run.parameter_set or not run.stochastic_controls):
        raise ValueError("legacy archival records require parameters and stochastic controls")
    if not all(required):
        raise ValueError("archival records require end time, apparatus, traceability, evidence and results")


def _validate_attempt_membership(run: ExperimentRunModel) -> None:
    for attempt in run.execution_accounting.attempts:
        if attempt.cleanup_receipt is not None and attempt.cleanup_receipt.run_id != run.run_id:
            raise ValueError("cleanup receipt must belong to its run")
        if any(
            item.run_ref.ref_id != run.run_id or item.run_ref.ref_kind != "run" for item in attempt.evidence_records
        ):
            raise ValueError("execution evidence must belong to its run")


def _validate_accounting_consistency(run: ExperimentRunModel) -> None:
    from .base import _parse_rfc3339_datetime

    attempts = run.execution_accounting.attempts
    start = _parse_rfc3339_datetime("started_at", run.started_at)
    starts = [_parse_rfc3339_datetime("attempt started_at", item.started_at) for item in attempts]
    if start != starts[0] or starts != sorted(starts):
        raise ValueError("run start must match its first ordered attempt start")
    _validate_accounting_status(run)
    if run.ended_at is not None:
        end = _parse_rfc3339_datetime("ended_at", run.ended_at)
        if any(
            item.ended_at is not None and _parse_rfc3339_datetime("attempt ended_at", item.ended_at) > end
            for item in attempts
        ):
            raise ValueError("run end must cover its retained attempt intervals")
    if run.record_state == "archival":
        if any(item.cleanup_receipt is None for item in attempts):
            raise ValueError("complete accounting requires explicit cleanup receipts for every attempt")
        _validate_archival_accounting_provenance(run)


def _validate_accounting_status(run: ExperimentRunModel) -> None:
    expected = {
        "unknown": "indeterminate",
        "running": "in-progress",
        "succeeded": "completed",
        "failed": "failed",
        "timed-out": "failed",
        "cancelled": "aborted",
        "aborted": "aborted",
    }
    latest = run.execution_accounting.attempts[-1]
    permitted = {expected[latest.execution_status], "invalidated", "superseded"}
    if latest.execution_status == "succeeded":
        permitted.add("sealed")
    if run.run_status not in permitted:
        raise ValueError("run status contradicts its latest execution attempt")
    if latest.execution_status in {"unknown", "running"} and run.ended_at is not None:
        raise ValueError("unresolved attempt cannot establish a run end time")


def _validate_archival_accounting_provenance(run: ExperimentRunModel) -> None:
    accounting, linkage = run.execution_accounting, run.trial_provenance
    if linkage is None:
        raise ValueError("archival execution accounting requires admitted trial provenance")
    fields = ("plan_id", "plan_digest", "plan_entry_id", "entry_digest")
    if any(getattr(accounting, field) != getattr(linkage, field) for field in fields):
        raise ValueError("archival accounting identities contradict trial provenance")
    accounted = {
        item.execution_attempt_id: (item.cleanup_receipt.receipt_id, frozenset(item.operation_refs))
        for item in accounting.attempts
    }
    linked = {
        item.execution_attempt_id: (item.cleanup_receipt_ref, frozenset(item.operation_refs))
        for item in linkage.execution_attempts
    }
    if accounted != linked or linkage.terminal_attempt_id != accounting.attempts[-1].execution_attempt_id:
        raise ValueError("archival accounting attempt history contradicts trial provenance")
