"""Runtime-owned startup reconciliation and linked administrative resolution."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from enum import Enum
from uuid import uuid4

from raes_backend_protocols.recovery_observation import (
    RecoveryEffectClassification,
    RecoveryObservationRequest,
    RecoveryObservationResult,
    RecoveryObserver,
)
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.operation_lifecycle import OperationAdmissionContext
from raes_contracts.runtime_state import (
    ApplyResult,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
    operation_terminal_diagnostics,
)

from .backend_calls import _BackendCallContext, _RealizationApplyContext, _validated_backend_result
from .control_plane_execution import _utc_now
from .control_plane_lifecycle import runtime_owned
from .control_plane_mutation import control_plane_mutation, external_control_plane_call, mutation_entry
from .control_plane_operation_context import operation_admission_context
from .control_plane_store import ControlPlaneOperationRecord, TerminalCommitMode


class IndeterminateResolutionDisposition(str, Enum):
    """Closed administrative acceptance of the currently stored state cut."""

    ACCEPT_CURRENT_SNAPSHOT = "accept-current-snapshot"


class RuntimeRecoveryMixin:
    """Runtime-owned administrative recovery entry points."""

    @runtime_owned
    @mutation_entry(OperationKind.INDETERMINATE_RESOLUTION)
    def resolve_indeterminate_operation(
        self,
        operation_id: str,
        *,
        disposition: IndeterminateResolutionDisposition,
        idempotency_key: str,
        identity: object | None = None,
    ) -> OperationReceipt:
        self._assert_runtime_owner()
        return resolve_indeterminate_operation(
            self,
            operation_id,
            disposition=disposition,
            idempotency_key=idempotency_key,
            identity=identity,
        )


_RECOVERY_ADDRESS = "runtime.control-plane.recovery"
_RECOVERY_ABSENT = Diagnostic(
    code="runtime.control-plane.recovery-effect-absent",
    domain="runtime",
    address=_RECOVERY_ADDRESS,
    message="Recovery observation established that the interrupted effect was absent.",
)
_RECOVERY_APPLIED = Diagnostic(
    code="runtime.control-plane.recovery-effect-applied",
    domain="runtime",
    address=_RECOVERY_ADDRESS,
    message="Recovery observation established and validated the interrupted effect.",
    severity=Severity.INFO,
)
_RECOVERY_UNOBSERVABLE = Diagnostic(
    code="runtime.control-plane.recovery-effect-unobservable",
    domain="runtime",
    address=_RECOVERY_ADDRESS,
    message="The interrupted effect could not be established by recovery observation.",
)


def reconcile_startup_operations(control_plane: object) -> None:
    """Classify every durable non-terminal claim before runtime readiness."""

    records = sorted(
        (
            record
            for record in control_plane._operations.values()
            if record.status.state in {OperationState.ACCEPTED, OperationState.RUNNING}
        ),
        key=lambda record: (record.receipt.submitted_at, record.receipt.operation_id),
    )
    if not records:
        return
    with control_plane_mutation(control_plane, records[0].status.context.operation_kind):
        for record in records:
            _reconcile_record(control_plane, record)


def _reconcile_record(control_plane: object, record: ControlPlaneOperationRecord) -> None:
    if record.status.state is OperationState.ACCEPTED:
        _reconcile_accepted_record(control_plane, record)
    else:
        _reconcile_running_record(control_plane, record)


def _reconcile_accepted_record(control_plane: object, record: ControlPlaneOperationRecord) -> None:
    state = OperationState.CANCELLED
    diagnostic = _RECOVERY_ABSENT
    if not _accepted_claim_has_write_ahead_provenance(record):
        state = OperationState.INDETERMINATE
        diagnostic = _RECOVERY_UNOBSERVABLE
    _commit_recovery_terminal(
        control_plane,
        record,
        state=state,
        diagnostics=[diagnostic],
        mode=TerminalCommitMode.OPERATION_ONLY,
    )


def _reconcile_running_record(control_plane: object, record: ControlPlaneOperationRecord) -> None:
    classification, applied = _observe_running_record(control_plane, record)
    if classification is RecoveryEffectClassification.EFFECT_ABSENT:
        state = OperationState.FAILED
        diagnostics = [_RECOVERY_ABSENT]
        mode = TerminalCommitMode.OPERATION_ONLY
        snapshot = None
        changed_addresses = None
    elif classification is RecoveryEffectClassification.EFFECT_APPLIED and applied is not None:
        state = OperationState.SUCCEEDED
        diagnostics = [_RECOVERY_APPLIED, *applied.diagnostics]
        mode = TerminalCommitMode.SNAPSHOT_BEARING
        snapshot = applied.snapshot
        changed_addresses = list(applied.changed_addresses)
    else:
        state = OperationState.INDETERMINATE
        diagnostics = [_RECOVERY_UNOBSERVABLE]
        mode = TerminalCommitMode.OPERATION_ONLY
        snapshot = None
        changed_addresses = None
    _commit_recovery_terminal(
        control_plane,
        record,
        state=state,
        diagnostics=diagnostics,
        mode=mode,
        snapshot=snapshot,
        changed_addresses=changed_addresses,
    )


def _accepted_claim_has_write_ahead_provenance(record: ControlPlaneOperationRecord) -> bool:
    """Exclude migrated claims whose pre-effect ordering cannot be established."""

    return "legacy:unattributed" not in record.status.context.authorization_scope


def _observe_running_record(
    control_plane: object,
    record: ControlPlaneOperationRecord,
) -> tuple[RecoveryEffectClassification, ApplyResult | None]:
    observer = control_plane._target.recovery_observer
    capability = control_plane._target.manifest.recovery_observation
    kind = record.status.context.operation_kind
    if observer is None or capability is None or kind not in capability.supported_operation_kinds:
        return RecoveryEffectClassification.INDETERMINATE, None
    baseline = deepcopy(control_plane._snapshot)
    request = RecoveryObservationRequest(
        operation_id=record.receipt.operation_id,
        operation_kind=kind,
        target_scope=record.status.context.target_scope,
        run_scope=record.status.context.run_scope,
        request_commitment=record.status.context.request_commitment,
        baseline_snapshot=deepcopy(baseline),
    )
    result = _bound_observation_result(control_plane, observer, request)
    classification = RecoveryEffectClassification.INDETERMINATE
    applied = None
    if result is not None:
        classification = result.classification
        if classification is RecoveryEffectClassification.EFFECT_APPLIED:
            applied = _validated_applied_observation(control_plane, record, baseline, result)
            if applied is None:
                classification = RecoveryEffectClassification.INDETERMINATE
    return classification, applied


def _bound_observation_result(
    control_plane: object,
    observer: RecoveryObserver,
    request: RecoveryObservationRequest,
) -> RecoveryObservationResult | None:
    try:
        with external_control_plane_call(control_plane):
            result = observer.observe_effect(request)
    except Exception:
        return None
    if not isinstance(result, RecoveryObservationResult) or (
        result.operation_id != request.operation_id or result.request_commitment != request.request_commitment
    ):
        return None
    return result


def _validated_applied_observation(
    control_plane: object,
    record: ControlPlaneOperationRecord,
    baseline: RuntimeSnapshot,
    result: RecoveryObservationResult,
) -> ApplyResult | None:
    assert result.snapshot is not None
    candidate = ApplyResult(
        success=True,
        snapshot=result.snapshot,
        changed_addresses=list(result.changed_addresses),
    )
    validated = _validated_backend_result(
        candidate,
        address=_RECOVERY_ADDRESS,
        baseline_snapshot=baseline,
        realization=_RealizationApplyContext(),
        call=_BackendCallContext(
            operation_id=record.receipt.operation_id,
            information_state_context_resolver=getattr(
                control_plane,
                "_information_state_context_resolver",
                None,
            ),
        ),
    )
    return validated if validated.success else None


def _commit_recovery_terminal(
    control_plane: object,
    record: ControlPlaneOperationRecord,
    *,
    state: OperationState,
    diagnostics: list[Diagnostic],
    mode: TerminalCommitMode,
    snapshot: RuntimeSnapshot | None = None,
    changed_addresses: list[str] | None = None,
) -> None:
    status = replace(
        record.status,
        state=state,
        updated_at=_utc_now(),
        diagnostics=operation_terminal_diagnostics(
            state,
            [*record.status.diagnostics, *diagnostics],
        ),
        changed_addresses=list(changed_addresses or []),
    )
    control_plane._commit_terminal_operation(
        control_plane._snapshot if snapshot is None else snapshot,
        replace(record, status=status),
        mode=mode,
    )


def unresolved_indeterminate_operation_ids(
    control_plane: object,
    *,
    target_scope: str | None = None,
    run_scope: str | None = None,
) -> tuple[str, ...]:
    """Return immutable indeterminate parents without a successful resolution child."""

    records = control_plane._store.load_records()
    resolved = {
        parent_id
        for record in records.values()
        if (parent_id := record.status.context.parent_operation_id) is not None
        and (parent := records.get(parent_id)) is not None
        and _is_valid_resolution_child(parent, record)
    }
    return tuple(
        sorted(
            operation_id
            for operation_id, record in records.items()
            if record.status.state is OperationState.INDETERMINATE
            and operation_id not in resolved
            and (target_scope is None or record.status.context.target_scope == target_scope)
            and (run_scope is None or record.status.context.run_scope == run_scope)
        )
    )


def resolve_indeterminate_operation(
    control_plane: object,
    operation_id: str,
    *,
    disposition: IndeterminateResolutionDisposition,
    idempotency_key: str,
    identity: object | None,
) -> OperationReceipt:
    """Record a separately authorized linked administrative disposition."""

    if not isinstance(disposition, IndeterminateResolutionDisposition):
        raise TypeError("disposition must be an IndeterminateResolutionDisposition")
    with control_plane_mutation(control_plane, OperationKind.INDETERMINATE_RESOLUTION):
        control_plane._reload_derived_state()
        parent = control_plane._operations.get(operation_id)
        if parent is None:
            raise KeyError("indeterminate operation was not found")
        context = operation_admission_context(
            control_plane,
            kind=OperationKind.INDETERMINATE_RESOLUTION,
            request={"disposition": disposition.value},
            identity=identity,
            run_scope=parent.status.context.run_scope,
            parent_operation_id=operation_id,
        )
        existing = control_plane._idempotent_receipt(
            idempotency_key=idempotency_key,
            request_fingerprint=context.request_commitment,
            context=context,
        )
        if existing is not None:
            return existing
        _authorize_resolution(control_plane, parent, context, identity)
        if parent.status.state is not OperationState.INDETERMINATE:
            raise ValueError("resolution parent must be indeterminate")
        if operation_id not in unresolved_indeterminate_operation_ids(control_plane):
            raise ValueError("indeterminate operation is already resolved")
        if not idempotency_key:
            raise ValueError("resolution requires an idempotency key")
        if idempotency_key == parent.idempotency_key:
            raise ValueError("resolution requires a fresh idempotency key")
        child_id = str(uuid4())
        submitted_at = _utc_now()
        receipt = OperationReceipt(
            operation_id=child_id,
            domain=parent.receipt.domain,
            submitted_at=submitted_at,
            accepted=True,
            context=context,
        )
        running = OperationStatus(
            operation_id=child_id,
            domain=parent.receipt.domain,
            state=OperationState.RUNNING,
            submitted_at=submitted_at,
            updated_at=submitted_at,
            context=context,
        )
        claimed = control_plane._claim_record(
            ControlPlaneOperationRecord(
                receipt=receipt,
                status=running,
                request_fingerprint=context.request_commitment,
                idempotency_key=idempotency_key,
            )
        )
        if claimed.receipt.operation_id != child_id:
            return claimed.receipt
        terminal = replace(running, state=OperationState.SUCCEEDED, updated_at=_utc_now())
        control_plane._commit_terminal_operation(
            control_plane._snapshot,
            ControlPlaneOperationRecord(
                receipt=receipt,
                status=terminal,
                request_fingerprint=context.request_commitment,
                idempotency_key=idempotency_key,
                result_payload={"resolution_disposition": disposition.value},
            ),
            mode=TerminalCommitMode.OPERATION_ONLY,
        )
        return receipt


def _authorize_resolution(
    control_plane: object,
    parent: ControlPlaneOperationRecord,
    context: OperationAdmissionContext,
    identity: object | None,
) -> None:
    roles = {getattr(role, "value", role) for role in getattr(identity, "roles", ())}
    target_name = getattr(identity, "target_name", None)
    required_subjects = {
        scope for scope in parent.status.context.authorization_scope if scope.startswith("participant-control:")
    }
    supplied_scopes = set(context.authorization_scope)
    allowed = (
        "operator" in roles
        and target_name == control_plane._target.name
        and parent.status.context.target_scope == context.target_scope
        and parent.status.context.run_scope == context.run_scope
        and required_subjects.issubset(supplied_scopes)
    )
    if allowed:
        return
    control_plane.record_audit(
        action="resolve_indeterminate_operation",
        identity=getattr(identity, "identity", "unattributed"),
        allowed=False,
        target=parent.status.context.target_scope,
        operation_id=parent.receipt.operation_id,
        reason="resolution-forbidden",
    )
    raise PermissionError("indeterminate resolution is forbidden")


def _is_valid_resolution_child(
    parent: ControlPlaneOperationRecord,
    child: ControlPlaneOperationRecord,
) -> bool:
    context = child.status.context
    return (
        parent.status.state is OperationState.INDETERMINATE
        and child.status.state is OperationState.SUCCEEDED
        and context.operation_kind is OperationKind.INDETERMINATE_RESOLUTION
        and context.parent_operation_id == parent.receipt.operation_id
        and context.target_scope == parent.status.context.target_scope
        and context.run_scope == parent.status.context.run_scope
        and "role:operator" in context.authorization_scope
        and bool(child.idempotency_key)
        and child.idempotency_key != parent.idempotency_key
        and child.result_payload
        == {"resolution_disposition": IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT.value}
    )


__all__ = (
    "IndeterminateResolutionDisposition",
    "RuntimeRecoveryMixin",
    "reconcile_startup_operations",
    "resolve_indeterminate_operation",
    "unresolved_indeterminate_operation_ids",
)
