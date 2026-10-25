"""Mixed commands reuse the bounded provider calls and incumbent invocation ledger."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING, TypeVar, cast
from uuid import uuid4

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    BackendOperationCapabilitiesModel,
    BackendOperationRequestModel,
    BackendOperationResponseModel,
    MixedBackendStageContext,
    MixedBackendStageReportModel,
    mixed_backend_binding_reference,
    require_mixed_backend_admission,
    validate_mixed_backend_stage_reports,
)
from raes_contracts.contracts.mixed_backend_transcript import established_mixed_backend_state
from raes_contracts.contracts.time_model import TimeRuntimeStateModel, validate_time_runtime_state
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import OperationReceipt, OperationState

from .control_plane_execution import _utc_now
from .control_plane_store_history import require_expected_history_heads
from .control_plane_supervision import persist_invocation_update
from .mixed_backend_installation import MixedBackendInstallation
from .mixed_runtime_state import runtime_state
from .operation_invocation_ledger import InvocationLedger
from .operation_provider_execution import accept_response, observe_provider_outcome, provider_call

if TYPE_CHECKING:
    from raes_contracts.contracts import BackendOperationControlModel, MixedBackendServiceModel
    from raes_contracts.runtime_state import RuntimeSnapshot

    from .control_plane import RuntimeControlPlane
    from .control_plane_store import ControlPlaneOperationRecord
    from .operation_execution_adapter import Lane

_T = TypeVar("_T")


@dataclass
class MixedInvocation:
    """Transient execution cursor; every accepted fact is retained in InvocationLedger."""

    installation: MixedBackendInstallation
    ledger: InvocationLedger
    deadline: float
    state: OperationState = OperationState.INDETERMINATE
    release_commitment: str | None = None
    outcome: BackendOperationResponseModel | None = None
    post_time: TimeRuntimeStateModel | None = None
    dispatched: bool = False
    effects_verified: bool = False
    native_validated: bool = False
    uncertain: bool = False

    def remaining(self, limit: int | None = None) -> int:
        budget = int((self.deadline - monotonic()) * 1000)
        if budget <= 0:
            raise TimeoutError("mixed invocation budget exhausted")
        return budget if limit is None else min(limit, budget)


def _external(
    plane: RuntimeControlPlane,
    execution: MixedInvocation,
    method: Callable[..., _T],
    *args: object,
    lane: Lane = "effect",
    limit: int | None = None,
    uncertain_on_timeout: bool = True,
) -> _T:
    try:
        with plane._mutation_authority.external_call():
            return plane._execution_adapter.call(lane, method, *deepcopy(args), timeout_ms=execution.remaining(limit))
    except TimeoutError:
        if uncertain_on_timeout:
            execution.uncertain = True
        raise


def _context(
    plane: RuntimeControlPlane,
    execution: MixedInvocation,
    *,
    post: TimeRuntimeStateModel | None = None,
) -> MixedBackendStageContext:
    ledger = execution.ledger
    time = execution.installation.binding.subject.time
    return MixedBackendStageContext(
        time_model=plane._mixed_runtime.context.time_models[time.time_model_ref],
        time_model_ref=time.time_model_ref,
        time_model_digest=time.time_model_digest,
        time_state=cast(TimeRuntimeStateModel, ledger.mixed_time_state),
        post_time_state=post,
        composition_state=ledger.mixed_composition_state,
    )


def prepare_mixed_invocation(
    plane: RuntimeControlPlane,
    installation: MixedBackendInstallation,
    record: ControlPlaneOperationRecord,
    snapshot: RuntimeSnapshot,
) -> MixedInvocation | None:
    declaration = installation.binding
    subject = declaration.subject
    pin = subject.bridge if subject.kind == "edge" else subject.transfer
    budget = plane._supervision.execution_ms
    request = BackendOperationRequestModel(
        binding={
            "operation_id": record.receipt.operation_id,
            "invocation_id": str(uuid4()),
            "attempt_id": str(uuid4()),
            "worker_id": f"local:{plane._deployment_id}",
            "deployment_id": plane._deployment_id,
            "owner_generation": plane._execution_generation,
            "execution_generation": 1,
            "backend_id": pin.service_ref,
            "baseline_revision": str(plane._snapshot_state.revision),
            "context": record.receipt.context,
        },
        command=mixed_backend_binding_reference(declaration),
        required_guarantees=("effect-observation", "cessation-evidence"),
        budget={"origin_id": str(uuid4()), "started_at": _utc_now(), "limit_ms": budget, "remaining_ms": budget},
    )
    time_state = snapshot.time_model_state
    if time_state is None:
        raise ValueError("mixed invocation requires committed time")
    execution = MixedInvocation(
        installation,
        InvocationLedger(
            request=request,
            mixed_binding=declaration,
            mixed_time_state=time_state,
            mixed_composition_state=runtime_state(plane._mixed_runtime, snapshot),
        ),
        monotonic() + budget / 1000,
    )
    try:
        _admit(plane, execution)
    except Exception:
        return None
    return execution


def reject_mixed_admission(plane: RuntimeControlPlane, record: ControlPlaneOperationRecord) -> OperationReceipt:
    return plane._reject_diagnostics(
        domain=record.receipt.domain,
        context=record.receipt.context,
        diagnostics=[
            Diagnostic(
                code="runtime.control-plane.backend-admission-refused",
                domain="runtime",
                address="runtime.control-plane",
                message="Mixed backend operation admission could not be established.",
            )
        ],
    )


def _admit(
    plane: RuntimeControlPlane,
    execution: MixedInvocation,
    *,
    record: ControlPlaneOperationRecord | None = None,
) -> None:
    provider, request = execution.installation.provider, execution.ledger.request
    installed = _external(plane, execution, provider.execution_binding, limit=plane._supervision.admission_ms)
    if installed != execution.installation.binding:
        raise ValueError("mixed provider changed its installed binding")
    caps = _probe(
        plane,
        execution,
        provider.operation_capabilities,
        budget_ms=execution.remaining(plane._supervision.admission_ms),
    )
    response = _probe(
        plane,
        execution,
        provider.check_operation,
        request=request,
        allowed={"admission"},
        budget_ms=execution.remaining(plane._supervision.admission_ms),
    )
    caps = cast(BackendOperationCapabilitiesModel, caps)
    response = cast(BackendOperationResponseModel, response)
    require_mixed_backend_admission(execution.installation.binding, request, caps, response)
    if record is None:
        execution.ledger = execution.ledger.model_copy(update={"responses": (response,)})
    else:
        accept_response(plane, record, response)


def _reload(plane: RuntimeControlPlane, execution: MixedInvocation) -> ControlPlaneOperationRecord:
    plane._reload_derived_state()
    record = plane._operations[execution.ledger.request.binding.operation_id]
    if (
        record.invocation.request != execution.ledger.request
        or record.invocation.mixed_binding != execution.installation.binding
    ):
        raise ValueError("mixed invocation changed its original authority")
    if record.invocation.request.binding.owner_generation != plane._execution_generation:
        raise ValueError("mixed invocation has a stale execution owner")
    require_expected_history_heads(plane._snapshot, record.result_history_heads)
    execution.ledger = record.invocation
    return record


def _probe(
    plane: RuntimeControlPlane,
    execution: MixedInvocation,
    method: Callable[..., object],
    **kwargs: object,
) -> BackendOperationCapabilitiesModel | BackendOperationResponseModel:
    try:
        return provider_call(plane, method, **kwargs)
    except TimeoutError:
        execution.uncertain = True
        raise


def _time_readback(plane: RuntimeControlPlane, execution: MixedInvocation) -> TimeRuntimeStateModel:
    value = _external(
        plane,
        execution,
        execution.installation.time_runtime.state,
        plane._snapshot,
        limit=plane._supervision.observation_ms,
    )
    if not isinstance(value, TimeRuntimeStateModel):
        raise ValueError("mixed time readback must be typed")
    validate_time_runtime_state(_context(plane, execution).time_model, value)
    if value != plane._snapshot.time_model_state:
        raise ValueError("mixed time readback differs from committed time")
    return value


def run_mixed_invocation(plane: RuntimeControlPlane, execution: MixedInvocation) -> None:
    """Consume once, collect independent evidence and leave publication to the owning path."""

    _reload(plane, execution)
    try:
        if _admit_running(plane, execution) and _coordinate_dispatch(plane, execution):
            _dispatch(plane, execution)
    except Exception:
        if plane._durability_poisoned:
            raise
        # A non-consumed grant proves no invocation; consumed or timed-out work
        # retains its reservation and every authenticated fact collected so far.
        _reload(plane, execution)
        execution.state = (
            OperationState.INDETERMINATE if execution.dispatched or execution.uncertain else OperationState.FAILED
        )
    finally:
        _reload(plane, execution)
        if not execution.dispatched and not execution.uncertain:
            confirm_no_dispatch(execution)


def _admit_running(
    plane: RuntimeControlPlane,
    execution: MixedInvocation,
    *,
    uncertain_state: bool = True,
) -> bool:
    try:
        _admit(plane, execution, record=_reload(plane, execution))
    except Exception:
        execution.state = OperationState.INDETERMINATE if execution.uncertain else OperationState.CANCELLED
        return False
    record = _reload(plane, execution)
    if record.status.state is not OperationState.RUNNING or plane._effect_admission_stopped:
        execution.state = (
            OperationState.INDETERMINATE if uncertain_state and execution.uncertain else OperationState.CANCELLED
        )
        return False
    return True


def _coordinate_dispatch(plane: RuntimeControlPlane, execution: MixedInvocation) -> bool:
    if _time_readback(plane, execution) != execution.ledger.mixed_time_state:
        raise ValueError("mixed time cut changed before dispatch")
    subject = execution.installation.binding.subject
    grant = _external(
        plane,
        execution,
        execution.installation.service(subject.time.coordinator).grant,
        execution.ledger.request,
        execution.ledger.mixed_time_state,
        limit=plane._supervision.admission_ms,
    )
    _retain(plane, execution, grant, subject.time.coordinator, "time-grant")
    if grant.stage.comparison != "ordered":
        execution.state = OperationState.FAILED
        return False
    return _admit_running(plane, execution, uncertain_state=False)


def _dispatch(plane: RuntimeControlPlane, execution: MixedInvocation) -> None:
    record = _reload(plane, execution)
    plane._execution_deadlines[record.receipt.operation_id] = execution.deadline
    execution.dispatched = True
    response = cast(
        BackendOperationResponseModel,
        provider_call(
            plane,
            execution.installation.provider.start_operation,
            request=execution.ledger.request,
            allowed={"acknowledgement"},
            budget_ms=execution.remaining(),
        ),
    )
    accept_response(plane, record, response)
    if response.message.disposition == "accepted":
        _collect_stages(plane, execution)


def confirm_no_dispatch(execution: MixedInvocation) -> None:
    execution.release_commitment = canonical_json_digest(
        {
            "request": execution.ledger.request.model_dump(mode="json"),
            "effect": "not-dispatched",
        }
    )


def _collect_stages(plane: RuntimeControlPlane, execution: MixedInvocation) -> None:
    record = _reload(plane, execution)
    # Supervision owns and persists the observation control, its one-use
    # delivery and the shared outcome; the mixed services use that same control.
    _record, execution.outcome, control = observe_provider_outcome(plane, record, execution.remaining)
    _reload(plane, execution)
    if execution.outcome is not None:
        execution.effects_verified = (
            _external(
                plane,
                execution,
                execution.installation.evidence.validate_effects,
                execution.ledger.request,
                execution.outcome,
                limit=plane._supervision.observation_ms,
            )
            is True
        )
    subject = execution.installation.binding.subject
    reports = _external(
        plane,
        execution,
        execution.installation.provider.stage_reports,
        control,
        lane="control",
        limit=plane._supervision.observation_ms,
    )
    if not isinstance(reports, tuple) or len(reports) > 64:
        raise ValueError("mixed provider stage reports exceed the transcript bound")
    # Validate the stages before checking a provider's proposed terminal state.
    producer = subject.bridge if subject.kind == "edge" else subject.transfer
    for report in reports:
        _retain(plane, execution, report, producer, "execution" if subject.kind == "edge" else "handoff")
    _read_stages(plane, execution, control, reports)
    _settle_stages(plane, execution)


def _settle_stages(plane: RuntimeControlPlane, execution: MixedInvocation) -> None:
    try:
        execution.post_time = _time_readback(plane, execution)
    except Exception:
        execution.post_time = None
    record = _reload(plane, execution)
    if execution.post_time is not None:
        ledger = record.invocation.model_copy(update={"mixed_post_time_state": execution.post_time})
        persist_invocation_update(plane, record, ledger)
        execution.ledger = ledger
    execution.state = established_mixed_backend_state(
        execution.installation.binding,
        execution.ledger.request,
        execution.ledger.responses,
        execution.ledger.mixed_reports,
        context=_context(plane, execution, post=execution.post_time),
        controls=execution.ledger.controls,
    )
    outcome = execution.outcome
    if (
        outcome is None
        or not execution.effects_verified
        or execution.uncertain
        or outcome.message.proposed_state is not execution.state
    ):
        execution.state = OperationState.INDETERMINATE
    if execution.state in {OperationState.SUCCEEDED, OperationState.FAILED}:
        execution.release_commitment = canonical_json_digest(outcome.message.effects.model_dump(mode="json"))


def _read_stages(
    plane: RuntimeControlPlane,
    execution: MixedInvocation,
    control: BackendOperationControlModel,
    reports: tuple[MixedBackendStageReportModel, ...],
) -> None:
    subject = execution.installation.binding.subject
    if not reports or (subject.kind == "edge" and reports[0].stage.status == "failed"):
        return
    readers = (
        [(subject.owner_reader, "owner-readback")]
        if subject.kind == "handoff"
        else [(subject.delivery_reader, "delivery")]
    )
    if subject.kind == "edge" and subject.observation_reader is not None:
        readers.append((subject.observation_reader, "observation"))
    for pin, kind in readers:
        try:
            report = _external(
                plane,
                execution,
                execution.installation.service(pin).read_stage,
                control,
                lane="control",
                limit=plane._supervision.observation_ms,
                uncertain_on_timeout=kind != "observation",
            )
        except Exception:
            # An unavailable observation adds no observation fact. Delivery and
            # time still determine edge settlement under the published model.
            break
        _retain(plane, execution, report, pin, kind)


def _retain(
    plane: RuntimeControlPlane,
    execution: MixedInvocation,
    report: MixedBackendStageReportModel,
    producer: MixedBackendServiceModel,
    kind: str,
) -> None:
    # Terminal proposals are retained honestly but cannot erase earlier stages
    # when an overclaim or missing later reader is detected.
    record = _reload(plane, execution)
    responses = tuple(r for r in record.invocation.responses if r.message.kind != "outcome")
    original = execution.ledger
    execution.ledger = original.model_copy(update={"responses": responses})
    if (
        not isinstance(report, MixedBackendStageReportModel)
        or report.stage.producer != producer
        or report.stage.stage != kind
    ):
        raise ValueError("mixed report did not come from its installed role")
    report = MixedBackendStageReportModel.model_validate(report.model_dump(mode="json"))
    if report in original.mixed_reports:
        execution.ledger = original
        return
    reports = (*original.mixed_reports, report)
    validate_mixed_backend_stage_reports(
        execution.installation.binding,
        original.request,
        responses,
        reports,
        context=_context(plane, execution, post=execution.post_time),
        controls=original.controls,
    )
    ledger = original.model_copy(update={"mixed_reports": reports})
    persist_invocation_update(plane, record, ledger)
    execution.ledger = ledger
