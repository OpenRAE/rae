"""Closed child contracts joining admitted trials to instantiation and runs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonEmptyString, PrefixedDigestString
from .experiment_references import ExperimentReferenceModel
from .random_stream import TrialCoordinateModel
from .schema_invariants import add_raes_invariant

ProcessorPlanKind = Literal["provisioning", "orchestration", "evaluation"]

_PROCESSOR_PLAN_CONTRACTS: dict[str, str] = {
    "provisioning": "provisioning-plan-v1",
    "orchestration": "orchestration-plan-v1",
    "evaluation": "evaluation-plan-v1",
}


class TrialProcessorPlanReferenceModel(ContractModel):
    """Digest-bound reference to one published processor plan projection."""

    plan_kind: ProcessorPlanKind
    artifact_ref: ExperimentReferenceModel

    @model_validator(mode="after")
    def _validate_typed_reference(self) -> TrialProcessorPlanReferenceModel:
        expected_contract = _PROCESSOR_PLAN_CONTRACTS[self.plan_kind]
        reference = self.artifact_ref
        if (
            reference.ref_kind != "other"
            or reference.ref_version != expected_contract
            or reference.ref_digest is None
            or reference.ref_path is not None
        ):
            raise ValueError("processor plan reference must be digest-bound to its published contract")
        return self


class TrialExecutionAttemptReferenceModel(ContractModel):
    """Identity-only archival reference to one effect-capable execution attempt."""

    execution_attempt_id: NonEmptyString
    cleanup_receipt_ref: NonEmptyString
    operation_refs: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def _validate_attempt(self) -> TrialExecutionAttemptReferenceModel:
        if len(self.operation_refs) != len(set(self.operation_refs)):
            raise ValueError("execution attempt operation_refs must be unique")
        return self


class TrialRunProvenanceModel(ContractModel):
    """Typed admitted-entry, snapshot, processor-plan, and attempt linkage on a run."""

    plan_id: NonEmptyString
    plan_digest: PrefixedDigestString
    plan_entry_id: NonEmptyString
    entry_digest: PrefixedDigestString
    admitted_run_id: NonEmptyString
    coordinate: TrialCoordinateModel
    instantiated_scenario_digest: PrefixedDigestString
    processor_plan_refs: list[TrialProcessorPlanReferenceModel] = Field(min_length=3, max_length=3)
    execution_attempts: list[TrialExecutionAttemptReferenceModel] = Field(min_length=1)
    terminal_attempt_id: NonEmptyString

    @model_validator(mode="after")
    def _validate_linkage(self) -> TrialRunProvenanceModel:
        plan_kinds = [reference.plan_kind for reference in self.processor_plan_refs]
        if set(plan_kinds) != set(_PROCESSOR_PLAN_CONTRACTS) or len(plan_kinds) != len(set(plan_kinds)):
            raise ValueError("trial run provenance must reference each processor plan kind exactly once")
        attempt_ids = [attempt.execution_attempt_id for attempt in self.execution_attempts]
        if len(attempt_ids) != len(set(attempt_ids)):
            raise ValueError("trial run execution_attempt_id values must be unique")
        receipt_refs = [attempt.cleanup_receipt_ref for attempt in self.execution_attempts]
        if len(receipt_refs) != len(set(receipt_refs)):
            raise ValueError("trial run cleanup_receipt_ref values must be unique")
        if self.terminal_attempt_id not in set(attempt_ids):
            raise ValueError("terminal_attempt_id must resolve to an execution attempt")
        if self.admitted_run_id in set(attempt_ids):
            raise ValueError("execution attempt identities must remain distinct from admitted run identity")
        return self


def validate_trial_run_provenance_binding(
    provenance: TrialRunProvenanceModel | None,
    *,
    run_id: str,
    scenario_digest: str,
) -> None:
    """Validate the run-local identity joins carried by trial provenance."""

    if provenance is None:
        return
    if provenance.admitted_run_id != run_id:
        raise ValueError("trial_provenance admitted_run_id must equal run_id")
    if scenario_digest != provenance.instantiated_scenario_digest:
        raise ValueError("scenario_snapshot_ref digest must equal trial_provenance instantiated_scenario_digest")


def add_trial_run_provenance_invariant(json_schema: dict[str, Any]) -> None:
    """Describe the cross-contract admitted-trial validation boundary."""

    add_raes_invariant(
        json_schema,
        "experiment-run-admitted-trial-provenance",
        "When present, trial provenance binds the archival run id to one admitted plan entry, the canonical "
        "instantiated snapshot, all three published processor-plan projections, and distinct execution attempts.",
        validator="raes_contracts.contracts.validate_admitted_trial_run",
        inputs=[
            {"contract_id": "admitted-trial-plan-v1", "instance_path": "#"},
            {"contract_id": "experiment-run-v1", "instance_path": "#/trial_provenance"},
            {"contract_id": "trial-cleanup-receipt-v1", "instance_path": "#"},
        ],
    )


__all__ = [
    "ProcessorPlanKind",
    "TrialExecutionAttemptReferenceModel",
    "TrialProcessorPlanReferenceModel",
    "TrialRunProvenanceModel",
    "add_trial_run_provenance_invariant",
    "validate_trial_run_provenance_binding",
]
