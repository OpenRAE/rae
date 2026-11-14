"""Durable workflow checkpoints through the incumbent atomic store commit."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from raes_contracts.errors import ConflictError
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
    SnapshotEntry,
)

from .workflow_continuation import WorkflowContinuation, WorkflowInvocation, WorkflowOperationState
from .workflow_result_contracts import workflow_result_contract_diagnostics

if TYPE_CHECKING:
    from .workflow_execution import WorkflowCut, WorkflowPorts


def latest_continuation(cut: WorkflowCut, root: str) -> WorkflowContinuation:
    candidates = [
        record.workflow.continuation
        for record in cut.records.values()
        if record.workflow is not None
        and record.workflow.root_operation_id == root
        and record.workflow.continuation is not None
        and (record.workflow.kind == "root" or record.status.state is OperationState.SUCCEEDED)
    ]
    if not candidates:
        raise ConflictError("workflow continuation is unavailable")
    return max(candidates, key=lambda state: state.sequence).model_copy(deep=True)


def checkpoint(ports: WorkflowPorts, state: WorkflowContinuation, snapshot: RuntimeSnapshot, *, revision: int) -> None:
    state.sequence = (
        max(
            state.sequence,
            *(
                [
                    record.workflow.continuation.sequence
                    for record in ports.read().records.values()
                    if record.workflow is not None
                    and record.workflow.root_operation_id == state.root_operation_id
                    and record.workflow.continuation is not None
                ]
                or [0]
            ),
        )
        + 1
    )
    rendered = render_snapshot(state, snapshot)
    baseline_revision = revision
    now = ports.now()
    identity = str(uuid5(NAMESPACE_URL, f"workflow-checkpoint:{state.root_operation_id}:{state.sequence}"))
    context = ports.context(OperationKind.COMPOSITION_PHASE, state.model_dump(mode="json"), state.root_operation_id)
    receipt = OperationReceipt(
        operation_id=identity, domain=RuntimeDomain.ORCHESTRATION, submitted_at=now, accepted=True, context=context
    )
    status = OperationStatus(
        operation_id=identity,
        domain=RuntimeDomain.ORCHESTRATION,
        submitted_at=now,
        updated_at=now,
        state=OperationState.RUNNING,
        context=context,
    )
    running = ports.record(
        receipt=receipt,
        status=status,
        idempotency_key=f"workflow-checkpoint:{state.root_operation_id}:{state.sequence}",
        request_fingerprint=context.request_commitment,
        workflow=WorkflowOperationState(
            root_operation_id=state.root_operation_id,
            kind="checkpoint",
            continuation=state.model_copy(deep=True),
            baseline_revision=baseline_revision,
        ),
    )
    claimed = ports.claim(running)
    if claimed.status.state is OperationState.SUCCEEDED:
        return
    changed = changed_workflow_addresses(state)
    terminal = replace(
        claimed, status=replace(claimed.status, state=OperationState.SUCCEEDED, changed_addresses=changed)
    )
    ports.commit(rendered, terminal)


def render_snapshot(state: WorkflowContinuation, snapshot: RuntimeSnapshot) -> RuntimeSnapshot:
    results = dict(snapshot.orchestration_results)
    for invocation in state.invocations.values():
        results[invocation.workflow_address] = invocation_result(invocation)
    rendered = snapshot.with_entries(
        dict(snapshot.entries),
        orchestration_results=results,
        orchestration_history={
            **snapshot.orchestration_history,
            **{
                address: [
                    item.model_dump(mode="json", exclude_none=True) if hasattr(item, "model_dump") else item
                    for item in events
                ]
                for address, events in state.events.items()
            },
        },
    )
    if workflow_result_contract_diagnostics(rendered):
        raise ConflictError("runtime workflow continuation violates its compiled result contract")
    return rendered


def installation_snapshot(state: WorkflowContinuation, snapshot: RuntimeSnapshot) -> RuntimeSnapshot:
    entries = dict(snapshot.entries)
    results = dict(snapshot.orchestration_results)
    histories = dict(snapshot.orchestration_history)
    for operation in state.installation:
        if operation.action == "unchanged":
            continue
        if operation.action == "delete":
            entries.pop(operation.address, None)
            results.pop(operation.address, None)
            histories.pop(operation.address, None)
        else:
            entries[operation.address] = SnapshotEntry(
                address=operation.address,
                domain=RuntimeDomain.ORCHESTRATION,
                resource_type="workflow",
                payload=operation.payload,
                ordering_dependencies=tuple(operation.ordering_dependencies),
                refresh_dependencies=tuple(operation.refresh_dependencies),
                profile_bindings=operation.profile_bindings,
                status="loaded",
            )
    return snapshot.with_entries(entries, orchestration_results=results, orchestration_history=histories)


def recover_checkpoints(ports: WorkflowPorts, root: str) -> None:
    cut = ports.read()
    pending = sorted(
        (
            record
            for record in cut.records.values()
            if record.workflow is not None
            and record.workflow.root_operation_id == root
            and record.workflow.kind == "checkpoint"
            and record.status.state is OperationState.RUNNING
        ),
        key=lambda record: record.workflow.continuation.sequence,
    )
    for record in pending:
        cut = ports.read()
        if record.workflow.baseline_revision != cut.revision:
            ports.commit(
                cut.snapshot,
                replace(record, status=replace(record.status, state=OperationState.CANCELLED, updated_at=ports.now())),
            )
            continue
        state = record.workflow.continuation
        snapshot = installation_snapshot(state, cut.snapshot) if state.sequence == 1 else cut.snapshot
        ports.commit(
            render_snapshot(state, snapshot),
            replace(
                record,
                status=replace(
                    record.status, state=OperationState.SUCCEEDED, changed_addresses=changed_workflow_addresses(state)
                ),
            ),
        )
    cut = ports.read()
    state = latest_continuation(cut, root)
    if state.sequence == 0:
        checkpoint(ports, state, installation_snapshot(state, cut.snapshot), revision=cut.revision)


def changed_workflow_addresses(state: WorkflowContinuation) -> list[str]:
    """Account for definition changes and invoked workflow state, in stable order."""
    return list(
        dict.fromkeys(
            [
                *(operation.address for operation in state.installation if operation.action != "unchanged"),
                *(invocation.workflow_address for invocation in state.invocations.values()),
            ]
        )
    )


def invocation_result(invocation: WorkflowInvocation) -> dict[str, object]:
    return {
        "state_schema_version": "workflow-step-state/v1",
        "workflow_status": invocation.status,
        "run_id": invocation.invocation_id,
        "started_at": invocation.started_at,
        "updated_at": invocation.updated_at,
        "terminal_reason": invocation.terminal_reason,
        "steps": {key: value.model_dump(mode="json") for key, value in invocation.steps.items()},
        "compensation_status": invocation.compensation_status,
        "compensation_started_at": invocation.compensation_started_at,
        "compensation_updated_at": invocation.compensation_updated_at,
        "compensation_failures": invocation.compensation_failures,
    }


def retained_invocation_result(records, workflow_address: str, invocation_id: str):
    checkpoints = [
        record.workflow.continuation
        for record in records.values()
        if record.workflow is not None
        and record.workflow.continuation is not None
        and record.status.state is OperationState.SUCCEEDED
        and record.workflow.kind == "checkpoint"
        and invocation_id in record.workflow.continuation.invocations
    ]
    if not checkpoints:
        return None
    state = max(checkpoints, key=lambda item: item.sequence)
    invocation = state.invocations[invocation_id]
    return invocation_result(invocation) if invocation.workflow_address == workflow_address else None
