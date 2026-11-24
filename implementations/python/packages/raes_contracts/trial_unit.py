"""Neutral values for an in-process, single-entry trial handoff."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Annotated, Any

from pydantic import BaseModel, Field, StrictStr, TypeAdapter, ValidationError

from raes_contracts.contracts.admitted_trial_plan import AdmittedTrialEntryModel, AdmittedTrialPlanModel
from raes_contracts.contracts.admitted_trial_plan_components import AdmittedExecutionControlModel
from raes_contracts.contracts.admitted_trial_plan_ingress import (
    AdmittedTrialPlanIngressError,
    revalidate_admitted_trial_plan,
)
from raes_contracts.contracts.experiment_bindings import ParticipantConfigurationResultModel
from raes_contracts.contracts.experiment_evidence import ExperimentEvidenceRecordModel
from raes_contracts.contracts.realization_plans import (
    EvaluationPlanModel,
    OrchestrationPlanModel,
    ProvisioningPlanModel,
)
from raes_contracts.contracts.trial_cleanup import (
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


class _ReadOnlyCopies[Value](Mapping[str, Value]):
    """Read one owned map without exposing its values; every lookup returns a copy."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, Value]) -> None:
        self._values = values

    def __getitem__(self, key: str) -> Value:
        return deepcopy(self._values[key])

    def __iter__(self) -> Iterator[str]:
        return iter(tuple(self._values))

    def __len__(self) -> int:
        return len(self._values)


class AdmittedTrialPlanView:
    """One complete admitted plan, reconstructed once and shared read-only.

    Construction bounds and reconstructs the complete plan once. Many single-entry
    handoffs can then share the view without repeating complete-plan work
    (issue #2046). The view owns its plan and exposes no mutable alias: every
    field read returns a copy, and map fields return read-only maps whose lookups
    return copies. ``snapshot()`` returns an independent plan model.
    """

    __slots__ = ("_plan",)

    def __init__(self, plan: AdmittedTrialPlanModel) -> None:
        if not isinstance(plan, AdmittedTrialPlanModel):
            raise TypeError("trial unit requires typed contract values")
        _require_bounded(plan)
        try:
            admitted = revalidate_admitted_trial_plan(plan)
        except AdmittedTrialPlanIngressError as exc:
            # Value-object checks raise ValueError (E3); the caller translates at its boundary.
            raise ValueError("Admitted trial plan contract validation failed") from exc
        object.__setattr__(self, "_plan", admitted)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("admitted trial plan view is read-only")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("admitted trial plan view is read-only")

    def __getattr__(self, name: str) -> Any:
        # Reached only for names that are not view members. Expose plan fields as copies.
        if name.startswith("_") or name not in AdmittedTrialPlanModel.model_fields:
            raise AttributeError(name)
        value = getattr(self._plan, name)
        if isinstance(value, dict):
            return _ReadOnlyCopies(value)
        return deepcopy(value)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AdmittedTrialPlanView):
            return NotImplemented
        return self is other or self._plan == other._plan

    __hash__ = None  # type: ignore[assignment]

    def __copy__(self) -> AdmittedTrialPlanView:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> AdmittedTrialPlanView:
        return self

    def __reduce__(self) -> tuple[type[AdmittedTrialPlanView], tuple[AdmittedTrialPlanModel]]:
        return AdmittedTrialPlanView, (self._plan,)

    def __repr__(self) -> str:
        return f"AdmittedTrialPlanView(plan_id={self._plan.plan_id!r}, plan_digest={self._plan.plan_digest!r})"

    @property
    def plan_id(self) -> str:
        return self._plan.plan_id

    @property
    def plan_digest(self) -> str:
        return self._plan.plan_digest

    @property
    def entries(self) -> Mapping[str, AdmittedTrialEntryModel]:
        return _ReadOnlyCopies(self._plan.entries)

    @property
    def cleanup_plans(self) -> Mapping[str, TrialCleanupPlanModel]:
        return _ReadOnlyCopies(self._plan.cleanup_plans)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        return self._plan.model_dump(**kwargs)

    def snapshot(self) -> AdmittedTrialPlanModel:
        """Return an independent copy of the complete admitted plan."""

        return self._plan.model_copy(deep=True)


@dataclass(frozen=True)
class TrialUnitRequest:
    """One exact sealed entry and its trusted processor outputs.

    ``plan`` accepts an ``AdmittedTrialPlanModel``, which construction bounds and
    reconstructs completely, or a shared ``AdmittedTrialPlanView``, which already
    did that once for a batch. The request stores the read-only view. Later
    reconstruction, for example ``replace(request)``, repeats only entry-scoped
    checks. Projection validity does not prove derivation, target support or
    permission. The adapter receives its RuntimeTarget through trusted composition.
    """

    plan: AdmittedTrialPlanView = field(repr=False)
    plan_entry_id: str
    execution_attempt_id: str
    instantiated_sdl_digest: str
    provisioning_plan: ProvisioningPlanModel = field(repr=False)
    orchestration_plan: OrchestrationPlanModel = field(repr=False)
    evaluation_plan: EvaluationPlanModel = field(repr=False)

    def __post_init__(self) -> None:
        try:
            _IDENTITY.validate_python(self.plan_entry_id)
            _IDENTITY.validate_python(self.execution_attempt_id)
            _DIGEST.validate_python(self.instantiated_sdl_digest)
        except ValidationError:
            raise ValueError("trial unit identity or SDL digest is invalid") from None
        view = self.plan if isinstance(self.plan, AdmittedTrialPlanView) else AdmittedTrialPlanView(self.plan)
        # The view bounded the complete plan once; bound the entry-scoped values here.
        _require_bounded(
            (
                self.plan_entry_id,
                self.execution_attempt_id,
                self.instantiated_sdl_digest,
                self.provisioning_plan,
                self.orchestration_plan,
                self.evaluation_plan,
            )
        )
        try:
            entry = view.entries[self.plan_entry_id]
        except KeyError:
            raise ValueError("trial unit entry does not resolve in admitted plan") from None
        if self.execution_attempt_id in {entry.run_id, entry.plan_entry_id, view.plan_id}:
            raise ValueError("trial unit attempt identity must remain distinct")
        object.__setattr__(self, "plan", view)
        # An owned entry copy, not a dataclass field: equality and commitments use the plan seal.
        object.__setattr__(self, "_entry", entry)
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
        return self._entry.run_id

    @property
    def participant_configurations(self) -> tuple[ParticipantConfigurationResultModel, ...]:
        return tuple(deepcopy(self._entry.participant_configurations))

    @property
    def execution_controls(self) -> AdmittedExecutionControlModel:
        return self._entry.execution_controls.model_copy(deep=True)

    @property
    def cleanup_plan(self) -> TrialCleanupPlanModel:
        return self.plan.cleanup_plans[self._entry.execution_controls.cleanup_plan_ref]


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


__all__ = ["AdmittedTrialPlanView", "TrialUnitRequest", "TrialUnitResult", "validate_trial_unit_result"]
