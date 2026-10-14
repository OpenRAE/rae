"""Admission, one-use dispatch and settlement around isolated external work."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from time import monotonic
from uuid import uuid4

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import BackendOperationRequestModel
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


def invocation_request(plane, request, operation_id, submitted_at) -> BackendOperationRequestModel:
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
        command={
            "contract_id": f"{request.domain.value}-plan-v1",
            "artifact_id": getattr(request.plan, "operation_id", None) or operation_id,
            "digest": native_command_commitment(plane, request.plan),
        },
        budget={
            "origin_id": "execution:" + canonical_json_digest(operation_id).removeprefix("sha256:"),
            "started_at": submitted_at,
            "limit_ms": execution_budget_ms(request.plan, plane._supervision),
            "remaining_ms": execution_budget_ms(request.plan, plane._supervision),
        },
    )


def claim_accepted(plane, request, *, backend_request=None, native=True, responses=()):
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
    )
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


def settle(plane, record, state, *, result=None, diagnostics=(), release_commitment=None, result_payload=None):
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
        else:
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
    )
    plane._commit_terminal_operation(snapshot, final, mode=mode)
    plane._execution_adapter.cancel_deadline(record.receipt.operation_id)
    plane._admitted_backend_requests.pop(record.receipt.operation_id, None)
    plane._execution_deadlines.pop(record.receipt.operation_id, None)


def execute_supervised_operation(plane, request):
    if request.idempotency_key:
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
            pass
        else:
            if candidate_id == incumbent.operation_id:
                raise AssertionError("a replay probe cannot create an invocation")
            return incumbent
    try:
        budget = execution_budget_ms(request.plan, plane._supervision)
    except ValueError:
        return plane._reject_diagnostics(
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
    if getattr(plane._target, "operation_provider", None) is not None:
        from .operation_provider_execution import execute_provider_operation

        return execute_provider_operation(plane, request)
    deadline = monotonic() + budget / 1000
    record, receipt = claim_accepted(plane, request)
    if record is None:
        return receipt
    snapshot = deepcopy(request.base_snapshot if request.base_snapshot is not None else plane._snapshot)
    diagnostics = list(request.diagnostics)

    def remaining():
        budget = int((deadline - monotonic()) * 1000)
        if budget <= 0:
            raise TimeoutError("execution budget exhausted")
        return budget

    try:
        if request.validation_method is not None:
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
                return receipt
        plane._reload_derived_state()
        current = plane._operations[record.receipt.operation_id]
        if current.status.state is not OperationState.ACCEPTED:
            return receipt
        if plane._effect_admission_stopped or plane._store.effect_admission_stopped():
            settle(plane, record, OperationState.CANCELLED)
            return receipt
        remaining()
        if current.invocation.request.command.digest != native_command_commitment(plane, request.plan):
            raise ValueError("admitted native command changed before dispatch")
        running = replace(
            current,
            status=replace(current.status, state=OperationState.RUNNING, updated_at=_utc_now()),
            invocation=current.invocation.model_copy(update={"consumed": True}),
        )
        # A confirmed write-ahead cut is the one-use grant. A lost reply never
        # reaches the callback, even if authoritative readback finds RUNNING.
        try:
            plane._store.save_record(running)
        except BaseException:
            plane._poison_runtime_durability()
            raise
        record = running
        with plane._mutation_authority.external_call():
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
                ),
                realization=_RealizationApplyContext(plan=request.plan, manifest=plane._target.manifest)
                if isinstance(request.plan, ProvisioningPlan)
                else None,
                information_state_context_resolver=plane._information_state_context_resolver,
            )
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
            settle(plane, record, OperationState.INDETERMINATE, diagnostics=[*diagnostics, *result.diagnostics])
    except Exception:
        if plane._durability_poisoned:
            raise
        plane._reload_derived_state()
        record = plane._operations[record.receipt.operation_id]
        settle(plane, record, OperationState.INDETERMINATE if record.invocation.consumed else OperationState.CANCELLED)
    return receipt


__all__ = ("execute_supervised_operation", "invocation_request", "settle")
