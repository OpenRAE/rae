"""Publish core clock-driver failure through the canonical state writer."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import uuid4

from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, OperationKind, OperationReceipt, OperationState, OperationStatus

from .control_plane_execution import _utc_now
from .control_plane_operation_context import operation_admission_context
from .control_plane_store import ControlPlaneOperationRecord
from .interaction_results import validated_composition_result

if TYPE_CHECKING:
    from .control_plane import RuntimeControlPlane


def commit_driver_failure(plane: RuntimeControlPlane, result: ApplyResult) -> None:
    # This records a core failure observation. It grants no backend invocation
    # and remains available while effects are uncertain or admission is closed.
    with plane._mutation_authority.supervision(), plane._participant_execution_lock:
        plane.stop_admission()
        plane._reload_derived_state()
        driver = plane._participant_clock_driver
        if driver is None:
            return
        predecessor = plane._snapshot
        result = validated_composition_result(
            plane,
            replace(result, snapshot=driver._pacing_failure_snapshot(predecessor)),
            predecessor,
            "runtime.participant-clock-driver",
        )
        operation_id, timestamp = str(uuid4()), _utc_now()
        context = operation_admission_context(
            plane,
            kind=OperationKind.COMPOSITION_PHASE,
            request={"clock_driver_failure": [diagnostic.code for diagnostic in result.diagnostics]},
        )
        receipt = OperationReceipt(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            submitted_at=timestamp,
            accepted=True,
            context=context,
        )
        status = OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            submitted_at=timestamp,
            updated_at=timestamp,
            state=OperationState.FAILED,
            context=context,
            diagnostics=result.diagnostics,
        )
        record = ControlPlaneOperationRecord(
            receipt=receipt, status=status, request_fingerprint=context.request_commitment
        )
        plane._store.save_record(replace(record, status=replace(status, state=OperationState.RUNNING, diagnostics=[])))
        plane._commit_terminal_operation(result.snapshot, record)
