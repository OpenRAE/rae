"""Admission, one-use dispatch and settlement around isolated external work."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass, replace
from time import monotonic
from typing import TYPE_CHECKING, cast
from uuid import uuid4

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import BackendOperationRequestModel, inject_occurrence_reference
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import (
    OperationReceipt,
    OperationState,
    OperationStatus,
    operation_terminal_diagnostics,
)

from .backend_calls import _call_backend_diagnostics, _RealizationApplyContext
from .backend_observation_calls import _call_backend_apply_with_observation, _ObservationApplyRequest
from .control_plane_execution import _utc_now
from .control_plane_store import ControlPlaneOperationRecord, NewClaimRejected, TerminalCommitMode
from .control_plane_store_snapshots import _snapshot_payload
from .diagnostics import _has_error_diagnostic
from .operation_command_commitment import native_command_commitment
from .operation_invocation_ledger import InvocationLedger
from .operation_policy_admission import execution_budget_ms

if TYPE_CHECKING:
    from raes_backend_protocols.inject_execution import ResolvedInjectOutcome
    from raes_contracts.contracts import BackendOperationResponseModel
    from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

    from .control_plane import RuntimeControlPlane
    from .control_plane_execution import OperationExecutionRequest


def invocation_request(
    plane: RuntimeControlPlane, request: OperationExecutionRequest, operation_id: str, submitted_at: str
) -> BackendOperationRequestModel:
    return BackendOperationRequestModel(
        binding={
            "operation_id": operation_id,
            "invocation_id": str(uuid4()),
            "attempt_id": f"attempt:{uuid4()}",
            "worker_id": plane._distributed_execution.worker_identity
            if plane._distributed_execution is not None
            else f"local:{plane._deployment_id}",
            "deployment_id": plane._deployment_id,
            "owner_generation": plane._execution_generation,
            "execution_generation": 1,
            "backend_id": plane._target.name,
            "baseline_revision": str(plane._snapshot_state.revision),
            "context": request.context,
        },
        command=inject_occurrence_reference(request.inject_occurrence)
        if request.inject_occurrence is not None
        else {
            "contract_id": f"{request.domain.value}-plan-v1",
            "artifact_id": getattr(request.plan, "operation_id", None) or operation_id,
            "digest": native_command_commitment(plane, request.plan),
        },
        requirement_refs=() if request.inject_occurrence is None else request.inject_occurrence.evidence_requirements,
        required_guarantees=() if request.inject_occurrence is None else ("effect-observation", "cessation-evidence"),
        budget={
            "origin_id": "execution:" + canonical_json_digest(operation_id).removeprefix("sha256:"),
            "started_at": submitted_at,
            "limit_ms": execution_budget_ms(request.plan, plane._supervision),
            "remaining_ms": execution_budget_ms(request.plan, plane._supervision),
        },
    )


def claim_accepted(
    plane: RuntimeControlPlane,
    request: OperationExecutionRequest,
    *,
    backend_request: BackendOperationRequestModel | None = None,
    native: bool = True,
    responses: tuple[BackendOperationResponseModel, ...] = (),
) -> tuple[ControlPlaneOperationRecord | None, OperationReceipt]:
    submitted_at = _utc_now() if backend_request is None else backend_request.budget.started_at
    operation_id = str(uuid4()) if backend_request is None else backend_request.binding.operation_id
    receipt = OperationReceipt(
        operation_id=operation_id,
        domain=request.domain,
        submitted_at=submitted_at,
        accepted=True,
        context=request.context,
        diagnostics=list(request.diagnostics),
    )
    status = OperationStatus(
        operation_id=operation_id,
        domain=request.domain,
        submitted_at=submitted_at,
        updated_at=submitted_at,
        state=OperationState.ACCEPTED,
        context=request.context,
        diagnostics=list(request.diagnostics),
    )
    invocation = InvocationLedger(
        request=backend_request or invocation_request(plane, request, operation_id, submitted_at),
        native=native,
        responses=responses,
    )
    record = ControlPlaneOperationRecord(
        receipt=receipt,
        status=status,
        request_fingerprint=request.request_fingerprint,
        idempotency_key=request.idempotency_key,
        invocation=invocation,
        inject_occurrence=request.inject_occurrence,
    )
    options, diagnostics = _admission_claim_options(plane, request)
    try:
        claimed = plane._claim_record(record, **options)
    except NewClaimRejected:
        return None, plane._reject_diagnostics(
            domain=request.domain,
            context=request.context,
            diagnostics=diagnostics
            or [
                Diagnostic(
                    code="runtime.control-plane.effect-admission-closed",
                    domain="runtime",
                    address="runtime.control-plane",
                    message="Effect admission is closed or reserved.",
                )
            ],
        )
    return (record if claimed == record else None), claimed.receipt


def _admission_claim_options(
    plane: RuntimeControlPlane, request: OperationExecutionRequest
) -> tuple[dict[str, object], list[Diagnostic]]:
    options = {}
    if request.exact_retry_fingerprint is not None:
        options["exact_retry_fingerprint"] = request.exact_retry_fingerprint
    if request.legacy_request_fingerprint:
        options["legacy_request_fingerprint"] = request.legacy_request_fingerprint
    if request.base_snapshot is not None and request.base_snapshot != plane._snapshot:
        options["new_claim_blocked"] = "stale-base-snapshot"
    diagnostics = [] if request.admission_diagnostics is None else request.admission_diagnostics()
    if diagnostics or plane._effect_admission_stopped or plane._store.effect_admission_stopped():
        options["new_claim_blocked"] = "current-state"
    return options, diagnostics


@dataclass(frozen=True)
class OperationSettlement:
    state: OperationState
    result: ApplyResult | None = None
    diagnostics: tuple[Diagnostic, ...] = ()
    release_commitment: str | None = None
    result_payload: dict[str, object] | None = None
    inject_resolution: ResolvedInjectOutcome | None = None


def settle(
    plane: RuntimeControlPlane,
    record: ControlPlaneOperationRecord,
    state: OperationState,
    *,
    result: ApplyResult | None = None,
    diagnostics: Iterable[Diagnostic] = (),
    release_commitment: str | None = None,
    result_payload: dict[str, object] | None = None,
) -> None:
    plane._require_state_writer()
    commit_settlement(
        plane,
        record,
        OperationSettlement(
            state=state,
            result=result,
            diagnostics=tuple(diagnostics),
            release_commitment=release_commitment,
            result_payload=result_payload,
        ),
    )


def commit_settlement(
    plane: RuntimeControlPlane, record: ControlPlaneOperationRecord, outcome: OperationSettlement
) -> None:
    state, result = outcome.state, outcome.result
    diagnostics, release_commitment = outcome.diagnostics, outcome.release_commitment
    result_payload, inject_resolution = outcome.result_payload, outcome.inject_resolution
    inject_outcome, inject_evidence = (
        (None, None) if inject_resolution is None else (inject_resolution.outcome, inject_resolution.evidence)
    )
    plane._require_state_writer()
    plane._reload_derived_state()
    current = plane._operations[record.receipt.operation_id]
    if current.status.state not in {OperationState.ACCEPTED, OperationState.RUNNING}:
        return
    if current.invocation.request.binding != record.invocation.request.binding:
        raise ValueError("invocation binding changed before settlement")
    if current.invocation.request.binding.owner_generation != plane._execution_generation:
        raise RuntimeError("stale execution owner cannot publish state")
    snapshot = plane._snapshot
    mode = TerminalCommitMode.OPERATION_ONLY
    if result is not None:
        if str(plane._snapshot_state.revision) != record.invocation.request.binding.baseline_revision:
            state, result, release_commitment = OperationState.INDETERMINATE, None, None
        elif result.snapshot != snapshot:
            snapshot, mode = result.snapshot, TerminalCommitMode.SNAPSHOT_BEARING
    released = not current.invocation.consumed or release_commitment is not None
    final = replace(
        current,
        status=replace(
            current.status,
            state=state,
            updated_at=_utc_now(),
            diagnostics=operation_terminal_diagnostics(state, [*current.status.diagnostics, *diagnostics]),
            changed_addresses=[] if result is None else list(result.changed_addresses),
        ),
        invocation=current.invocation.model_copy(
            update={
                "reserved": not released,
                "release_commitment": release_commitment,
            }
        ),
        result_payload=result_payload,
        inject_outcome=inject_outcome,
        inject_evidence=inject_evidence,
    )
    plane._commit_terminal_operation(snapshot, final, mode=mode)
    plane._execution_adapter.cancel_deadline(record.receipt.operation_id)
    plane._admitted_backend_requests.pop(record.receipt.operation_id, None)
    plane._execution_deadlines.pop(record.receipt.operation_id, None)


def execute_supervised_operation(plane: RuntimeControlPlane, request: OperationExecutionRequest) -> OperationReceipt:
    receipt = _existing_supervised_receipt(plane, request)
    if receipt is None:
        try:
            budget = execution_budget_ms(request.plan, plane._supervision)
        except ValueError:
            receipt = plane._reject_diagnostics(
                domain=request.domain,
                context=request.context,
                diagnostics=[
                    Diagnostic(
                        code="runtime.control-plane.execution-policy-unsupported",
                        domain="runtime",
                        address=request.address,
                        message="The selected execution policy cannot be enforced by this runtime composition.",
                    )
                ],
            )
        else:
            if request.local_executor is None and getattr(plane._target, "operation_provider", None) is not None:
                from .operation_provider_execution import execute_provider_operation

                receipt = execute_provider_operation(plane, request)
            else:
                receipt = _execute_admitted_native(plane, request, budget)
    return receipt


def _existing_supervised_receipt(
    plane: RuntimeControlPlane, request: OperationExecutionRequest
) -> OperationReceipt | None:
    if not request.idempotency_key:
        return None
    from .control_plane_execution import _claim_running_operation

    exact = (
        {"exact_retry_fingerprint": request.exact_retry_fingerprint}
        if request.exact_retry_fingerprint is not None
        else {}
    )
    try:
        candidate_id, _, _, _, incumbent = _claim_running_operation(
            plane,
            request,
            exact,
            current_state_rejects_new_claim=True,
        )
    except NewClaimRejected:
        return None
    if candidate_id == incumbent.operation_id:
        raise AssertionError("a replay probe cannot create an invocation")
    return incumbent


def _execute_admitted_native(
    plane: RuntimeControlPlane, request: OperationExecutionRequest, budget: int
) -> OperationReceipt:
    deadline = monotonic() + budget / 1000
    record, receipt = claim_accepted(plane, request)
    if record is None:
        return receipt
    snapshot = deepcopy(request.base_snapshot if request.base_snapshot is not None else plane._snapshot)
    diagnostics = list(request.diagnostics)

    def remaining() -> int:
        budget = int((deadline - monotonic()) * 1000)
        if budget <= 0:
            raise TimeoutError("execution budget exhausted")
        return budget

    try:
        if _validate_native_invocation(plane, request, record, diagnostics, remaining):
            running = _dispatch_native_invocation(plane, request, record, remaining)
            if running is not None:
                _complete_native_invocation(plane, request, running, snapshot, diagnostics, remaining)
    except Exception:
        if plane._durability_poisoned:
            raise
        plane._reload_derived_state()
        record = plane._operations[record.receipt.operation_id]
        settle(plane, record, OperationState.INDETERMINATE if record.invocation.consumed else OperationState.CANCELLED)
    return receipt


def _validate_native_invocation(
    plane: RuntimeControlPlane,
    request: OperationExecutionRequest,
    record: ControlPlaneOperationRecord,
    diagnostics: list[Diagnostic],
    remaining: Callable[[], int],
) -> bool:
    if request.validation_method is None:
        return True
    with plane._mutation_authority.external_call():
        validation_diagnostics = plane._execution_adapter.call(
            "effect",
            _call_backend_diagnostics,
            request.validation_method,
            request.plan,
            address=f"{request.address}.validate",
            timeout_ms=remaining(),
        )
    diagnostics.extend(validation_diagnostics)
    if _has_error_diagnostic(validation_diagnostics):
        settle(plane, record, OperationState.CANCELLED, diagnostics=diagnostics)
        return False
    return True


def _dispatch_native_invocation(
    plane: RuntimeControlPlane,
    request: OperationExecutionRequest,
    record: ControlPlaneOperationRecord,
    remaining: Callable[[], int],
) -> ControlPlaneOperationRecord | None:
    plane._reload_derived_state()
    current = plane._operations[record.receipt.operation_id]
    if current.status.state is not OperationState.ACCEPTED:
        return None
    if plane._effect_admission_stopped or plane._store.effect_admission_stopped():
        settle(plane, record, OperationState.CANCELLED)
        return None
    remaining()
    if current.invocation.request.command.digest != native_command_commitment(plane, request.plan):
        raise ValueError("admitted native command changed before dispatch")
    running = cast(
        ControlPlaneOperationRecord,
        replace(
            current,
            status=replace(current.status, state=OperationState.RUNNING, updated_at=_utc_now()),
            invocation=current.invocation.model_copy(update={"consumed": True}),
        ),
    )
    # A confirmed write-ahead cut is the one-use grant. A lost reply never
    # reaches the callback, even if authoritative readback finds RUNNING.
    try:
        plane._store.save_record(running)
    except BaseException:
        plane._poison_runtime_durability()
        raise
    return running


def _complete_native_invocation(
    plane: RuntimeControlPlane,
    request: OperationExecutionRequest,
    record: ControlPlaneOperationRecord,
    snapshot: RuntimeSnapshot,
    diagnostics: list[Diagnostic],
    remaining: Callable[[], int],
) -> None:
    if request.local_executor is not None:
        with plane._mutation_authority.external_call():
            result, observation = plane._execution_adapter.call(
                "effect",
                request.local_executor,
                snapshot,
                record.receipt.operation_id,
                record.invocation.request.binding.attempt_id,
                timeout_ms=remaining(),
            )
    else:
        result, observation = _invoke_plan_phase(plane, request, record, snapshot, remaining)
    if record.invocation.request.command.digest != native_command_commitment(plane, request.plan):
        raise ValueError("admitted native command changed before finalization")
    if result.success:
        settle(
            plane,
            record,
            OperationState.SUCCEEDED,
            result=result,
            diagnostics=[*diagnostics, *result.diagnostics],
            release_commitment=canonical_json_digest(_snapshot_payload(result.snapshot)),
            result_payload=None if observation is None else observation.result_payload,
        )
    else:
        settle(
            plane,
            record,
            OperationState.INDETERMINATE,
            result=result,
            diagnostics=[*diagnostics, *result.diagnostics],
            result_payload=None if observation is None else observation.result_payload,
        )
    if request.result_sink is not None:
        request.result_sink(result)


def _invoke_plan_phase(plane, request, record, snapshot, remaining):
    from .backend_calls import _BackendCallContext, _call_backend_apply

    realization = request.realization or (
        _RealizationApplyContext(plan=request.plan, manifest=plane._target.manifest)
        if isinstance(request.plan, ProvisioningPlan)
        else None
    )
    with plane._mutation_authority.external_call():
        if not request.execute_observation:
            result = plane._execution_adapter.call(
                "effect",
                _call_backend_apply,
                request.method,
                request.plan,
                snapshot,
                timeout_ms=remaining(),
                address=request.address,
                snapshot=snapshot,
                realization=realization,
                call=_BackendCallContext(
                    materialization_archive=plane._materialization_archive,
                    operation_id=record.receipt.operation_id,
                    attempt_id=record.invocation.request.binding.attempt_id,
                    information_state_context_resolver=plane._information_state_context_resolver,
                ),
            )
            return result, None
        result, observation = plane._execution_adapter.call(
            "effect",
            _call_backend_apply_with_observation,
            request.method,
            request.plan,
            snapshot,
            timeout_ms=remaining(),
            request=_ObservationApplyRequest(
                materialization_archive=plane._materialization_archive,
                address=request.address,
                snapshot=snapshot,
                plan=request.plan,
                manifest=plane._target.manifest,
                runtime=plane._target.observation_runtime,
                durable_lifecycle_available=plane._store_commits.crash_atomic,
                operation_id=record.receipt.operation_id,
                attempt_id=record.invocation.request.binding.attempt_id,
            ),
            realization=realization,
            information_state_context_resolver=plane._information_state_context_resolver,
        )
    return result, observation


__all__ = ("execute_supervised_operation", "invocation_request", "settle")
