"""Neutral values for an in-process, single-entry trial handoff."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Annotated

from pydantic import BaseModel, Field, StrictStr, TypeAdapter, ValidationError

from .admitted_trial_plan_ingress import revalidate_admitted_trial_plan
from .contracts import (
    AdmittedExecutionControlModel,
    AdmittedTrialPlanModel,
    EvaluationPlanModel,
    ExperimentEvidenceRecordModel,
    OrchestrationPlanModel,
    ParticipantConfigurationResultModel,
    ProvisioningPlanModel,
    TrialCleanupPlanModel,
    TrialCleanupReceiptModel,
    validate_trial_cleanup_receipt,
)
from .operation_lifecycle import OperationAdmissionContext
from .realization_structure import RealizationRelationStatus, validate_realization_value
from .runtime_state import OperationReceipt, RuntimeSnapshot
from .runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS

_IDENTITY = TypeAdapter(Annotated[StrictStr, Field(min_length=1, max_length=256, pattern=r"^\S(?:.*\S)?$")])
_DIGEST = TypeAdapter(Annotated[StrictStr, Field(pattern=r"^sha256:[a-f0-9]{64}$")])
MAX_TRIAL_UNIT_ITEMS = 4096


def _require_bounded(value: object) -> None:
    result = validate_realization_value(value, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS, python_carriers=True)
    if result.status is not RealizationRelationStatus.CONFORMANT:
        raise ValueError("trial unit value exceeds portable value limits")


def _reconstruct[Model: BaseModel](model_type: type[Model], value: Model) -> Model:
    if not isinstance(value, model_type):
        raise TypeError("trial unit requires typed contract values")
    try:
        return model_type.model_validate(value.model_dump(mode="python"))
    except ValidationError:
        raise ValueError("trial unit child contract validation failed") from None


@dataclass(frozen=True)
class TrialUnitRequest:
    """One exact sealed entry and its trusted processor outputs.

    Reconstruct again at dispatch if the caller retained mutable child values.
    Projection validity does not prove derivation, target support or permission.
    The adapter receives its RuntimeTarget through trusted composition.
    """

    plan: AdmittedTrialPlanModel = field(repr=False)
    plan_entry_id: str
    execution_attempt_id: str
    instantiated_sdl_digest: str
    provisioning_plan: ProvisioningPlanModel = field(repr=False)
    orchestration_plan: OrchestrationPlanModel = field(repr=False)
    evaluation_plan: EvaluationPlanModel = field(repr=False)

    def __post_init__(self) -> None:
        _require_bounded(self)
        try:
            _IDENTITY.validate_python(self.plan_entry_id)
            _IDENTITY.validate_python(self.execution_attempt_id)
            _DIGEST.validate_python(self.instantiated_sdl_digest)
        except ValidationError:
            raise ValueError("trial unit identity or SDL digest is invalid") from None
        admitted = revalidate_admitted_trial_plan(self.plan)
        entry = admitted.entries.get(self.plan_entry_id)
        if entry is None:
            raise ValueError("trial unit entry does not resolve in admitted plan")
        if self.execution_attempt_id in {entry.run_id, entry.plan_entry_id, admitted.plan_id}:
            raise ValueError("trial unit attempt identity must remain distinct")
        object.__setattr__(self, "plan", admitted)
        for name, model_type in (
            ("provisioning_plan", ProvisioningPlanModel),
            ("orchestration_plan", OrchestrationPlanModel),
            ("evaluation_plan", EvaluationPlanModel),
        ):
            projection = _reconstruct(model_type, getattr(self, name))
            if projection.purpose != "execution":
                raise ValueError("trial unit requires execution plans")
            if name != "orchestration_plan" and (
                projection.run_id != entry.run_id or projection.instantiation_id != entry.plan_entry_id
            ):
                raise ValueError("trial unit processor plan scope does not match entry")
            object.__setattr__(self, name, projection)

    @property
    def run_id(self) -> str:
        return self.plan.entries[self.plan_entry_id].run_id

    @property
    def participant_configurations(self) -> tuple[ParticipantConfigurationResultModel, ...]:
        return tuple(self.plan.entries[self.plan_entry_id].participant_configurations)

    @property
    def execution_controls(self) -> AdmittedExecutionControlModel:
        return self.plan.entries[self.plan_entry_id].execution_controls

    @property
    def cleanup_plan(self) -> TrialCleanupPlanModel:
        return self.plan.cleanup_plans[self.execution_controls.cleanup_plan_ref]


@dataclass(frozen=True)
class TrialUnitResult:
    """Execution observations before cleanup, plus independent cleanup evidence.

    The adapter validates snapshots and resolves evidence through their owners.
    This handoff does not publish runtime state or create an archival run.
    """

    operation_receipts: tuple[OperationReceipt, ...] = field(repr=False)
    execution_snapshot: RuntimeSnapshot = field(repr=False)
    evidence: tuple[ExperimentEvidenceRecordModel, ...] = field(repr=False)
    cleanup_receipt: TrialCleanupReceiptModel = field(repr=False)
    cleanup_evidence: tuple[ExperimentEvidenceRecordModel, ...] = field(repr=False)

    def __post_init__(self) -> None:
        _require_bounded(self)
        for name in ("operation_receipts", "evidence", "cleanup_evidence"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or len(values) > MAX_TRIAL_UNIT_ITEMS:
                raise ValueError("trial unit collections require bounded tuples")
        if not isinstance(self.execution_snapshot, RuntimeSnapshot):
            raise TypeError("trial unit requires a typed execution snapshot")
        object.__setattr__(self, "execution_snapshot", deepcopy(self.execution_snapshot))
        object.__setattr__(self, "cleanup_receipt", _reconstruct(TrialCleanupReceiptModel, self.cleanup_receipt))
        receipts = []
        for receipt in self.operation_receipts:
            if not isinstance(receipt, OperationReceipt):
                raise TypeError("trial unit requires typed operation receipts")
            receipts.append(
                replace(deepcopy(receipt), context=_reconstruct(OperationAdmissionContext, receipt.context))
            )
        if len({receipt.operation_id for receipt in receipts}) != len(receipts):
            raise ValueError("trial unit operation receipts must be unique")
        object.__setattr__(self, "operation_receipts", tuple(receipts))
        for name in ("evidence", "cleanup_evidence"):
            records = tuple(_reconstruct(ExperimentEvidenceRecordModel, record) for record in getattr(self, name))
            if len({record.evidence_record_id for record in records}) != len(records):
                raise ValueError("trial unit evidence records must be unique")
            object.__setattr__(self, name, records)


def validate_trial_unit_result(request: TrialUnitRequest, result: TrialUnitResult, *, target_scope: str) -> None:
    """Check structural joins against caller-owned request and trusted target scope.

    This does not establish runtime authorization, evidence content, cessation,
    snapshot transition validity or successful authored execution.
    """

    request = replace(request)
    result = replace(result)
    try:
        _IDENTITY.validate_python(target_scope)
    except ValidationError:
        raise ValueError("trial unit target scope is invalid") from None
    validate_trial_cleanup_receipt(request.cleanup_plan, result.cleanup_receipt)
    if result.cleanup_receipt.execution_attempt_id != request.execution_attempt_id:
        raise ValueError("trial unit cleanup receipt attempt does not match request")
    for receipt in result.operation_receipts:
        if receipt.context.target_scope != target_scope or receipt.context.run_scope != f"run:{request.run_id}":
            raise ValueError("trial unit operation receipt scope does not match request")
    for record in (*result.evidence, *result.cleanup_evidence):
        if record.run_ref.ref_kind != "run" or record.run_ref.ref_id != request.run_id:
            raise ValueError("trial unit evidence run does not match request")
    cleanup_refs = {
        reference
        for obligation in result.cleanup_receipt.obligation_results.values()
        for reference in obligation.evidence_refs
    }
    claim = result.cleanup_receipt.clean_state_claim
    if claim is not None:
        cleanup_refs.update(claim.evidence_refs)
    if not cleanup_refs <= {record.evidence_record_id for record in result.cleanup_evidence}:
        raise ValueError("trial unit cleanup evidence does not cover receipt references")


__all__ = ["TrialUnitRequest", "TrialUnitResult", "validate_trial_unit_result"]
