"""Runtime-owned dispatch through the existing operation and persistence boundaries."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal, cast
from uuid import uuid4

if TYPE_CHECKING:
    from .control_plane_execution import OperationExecutionRequest
    from .control_plane_store import ControlPlaneOperationRecord

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.execution_state import PropositionTruthResultModel, WorkflowHistoryEventModel
from raes_contracts.contracts.plan_projection import orchestration_plan_model, runtime_plan_digest
from raes_contracts.contracts.workflow_dispatch import WorkflowProgram, WorkflowStepDispatch
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import ConflictError
from raes_contracts.evaluation import EvaluationExecutionState, EvaluationResultStatus
from raes_contracts.planning import ChangeAction, OrchestrationPlan, RuntimeDomain
from raes_contracts.runtime_state import (
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
)
from raes_contracts.timestamps import parse_offset_timestamp_utc
from raes_contracts.versions import WORKFLOW_DISPATCH_CONTRACTS

from .control_plane_timeouts import workflow_timeout_update
from .operation_reconciliation_ledger import valid_reconciliation_child
from .workflow_checkpoints import (
    changed_workflow_addresses,
    checkpoint,
    installation_snapshot,
    invocation_result,
    latest_continuation,
    recover_checkpoints,
)
from .workflow_compensation import advance_compensation
from .workflow_continuation import WorkflowContinuation, WorkflowInvocation, WorkflowOperationState
from .workflow_evidence import require_success_evidence
from .workflow_transitions import (
    accept_response,
    event,
    finish_invocation,
    invocation_identity,
    new_invocation,
    observation_addresses,
    prepare_dispatch,
    reconcile_ready,
)


@dataclass(frozen=True)
class WorkflowCut:
    snapshot: RuntimeSnapshot
    revision: int
    records: dict[str, ControlPlaneOperationRecord]


@dataclass(frozen=True)
class WorkflowPorts:
    """Bound owner methods; the controller cannot acquire another runtime's state."""

    read: Callable[[], WorkflowCut]
    context: Callable[[OperationKind, object, str | None], OperationAdmissionContext]
    claim: Callable[[ControlPlaneOperationRecord], ControlPlaneOperationRecord]
    commit: Callable[[RuntimeSnapshot, ControlPlaneOperationRecord], None]
    execute: Callable[[OperationExecutionRequest], OperationReceipt]
    mutation: Callable[[], AbstractContextManager[None]]
    now: Callable[[], str]
    authorize_projection: Callable[[OrchestrationPlan, OrchestrationPlan], None]
    start: Callable[..., object]
    dispatch_step: Callable[..., object]
    contracts: frozenset[str]
    record: Callable[..., ControlPlaneOperationRecord]
    request: Callable[..., OperationExecutionRequest]


def workflow_programs(plan: OrchestrationPlan) -> dict[str, WorkflowProgram]:
    programs = {}
    for operation in plan.operations:
        if operation.resource_type != "workflow" or operation.action is ChangeAction.DELETE:
            continue
        payload = operation.payload
        contract = payload["execution_contract"]
        programs[operation.address] = WorkflowProgram(
            workflow_address=operation.address,
            start_step=payload["start_step"],
            steps=payload["control_steps"],
            execution_policies=tuple(
                policy
                for policy in (operation.execution_policy, *operation.execution_policy_scopes)
                if policy is not None
            ),
            **{
                name: contract[name]
                for name in (
                    "timeout_seconds",
                    "compensation_mode",
                    "compensation_triggers",
                    "compensation_failure_policy",
                )
                if name in contract
            },
        )
    return programs


def has_workflow_program(plan: object) -> bool:
    return isinstance(plan, OrchestrationPlan) and any(op.resource_type == "workflow" for op in plan.operations)


def nonworkflow_projection(plan: OrchestrationPlan) -> OrchestrationPlan:
    excluded = {op.address for op in plan.operations if op.resource_type == "workflow"}
    return cast(
        OrchestrationPlan,
        replace(
            plan,
            operations=[op for op in plan.operations if op.address not in excluded],
            resources={key: value for key, value in plan.resources.items() if key not in excluded},
            startup_order=[key for key in plan.startup_order if key not in excluded],
            operation_id=None,
            observation_demands=(),
        ),
    )


def submit_workflows(
    ports: WorkflowPorts, plan: OrchestrationPlan, context: OperationAdmissionContext, idempotency_key: str
) -> OperationReceipt:
    if not set(WORKFLOW_DISPATCH_CONTRACTS) <= ports.contracts:
        raise ConflictError("backend does not declare runtime workflow step dispatch")
    with ports.mutation():
        root = claim_workflow_root(ports, plan, context, idempotency_key)
        if root.status.state not in {OperationState.ACCEPTED, OperationState.RUNNING}:
            return root.receipt
    with ports.mutation():
        recover_checkpoints(ports, root.receipt.operation_id)
        install_resources(ports, plan, root)
    advance_workflows(ports, root.receipt.operation_id)
    return root.receipt


def claim_workflow_root(
    ports: WorkflowPorts, plan: OrchestrationPlan, context: OperationAdmissionContext, key: str
) -> ControlPlaneOperationRecord:
    cut = ports.read()
    existing = next(
        (
            record
            for record in cut.records.values()
            if record.idempotency_key == key and record.receipt.context == context
        ),
        None,
    )
    if existing is not None:
        if existing.workflow is None or existing.workflow.kind != "root":
            raise ConflictError("orchestration identity belongs to another operation")
        return existing
    require_no_workflow_overlap(plan, cut)
    return create_root(ports, plan, context, key, workflow_programs(plan))


def require_no_workflow_overlap(plan: OrchestrationPlan, cut: WorkflowCut) -> None:
    changed = {
        op.address
        for op in plan.operations
        if op.resource_type == "workflow" and op.action is not ChangeAction.UNCHANGED
    }
    if any(
        record.workflow is not None
        and record.workflow.kind == "root"
        and record.status.state in {OperationState.ACCEPTED, OperationState.RUNNING}
        and changed.intersection(record.workflow.continuation.programs)
        for record in cut.records.values()
    ):
        raise ConflictError("workflow update overlaps an active runtime invocation")


def install_resources(ports: WorkflowPorts, plan: OrchestrationPlan, root: ControlPlaneOperationRecord) -> None:
    projection = nonworkflow_projection(plan)
    if not projection.actionable_operations:
        return
    ports.authorize_projection(plan, projection)
    context = ports.context(OperationKind.ORCHESTRATION, projection, root.receipt.operation_id)
    receipt = ports.execute(
        ports.request(
            domain=RuntimeDomain.ORCHESTRATION,
            method=ports.start,
            plan=projection,
            address="runtime.workflow.resources",
            diagnostics=[],
            base_snapshot=None,
            idempotency_key=f"workflow-resources:{root.receipt.operation_id}",
            request_fingerprint=context.request_commitment,
            context=context,
            execute_observation=False,
        )
    )
    if not receipt.accepted:
        cut = ports.read()
        state = latest_continuation(cut, root.receipt.operation_id)
        fail_setup(ports, root, state, cut, OperationState.FAILED, receipt.diagnostics)


def root_programs(plan: OrchestrationPlan, programs: dict[str, WorkflowProgram]) -> dict[str, WorkflowProgram]:
    targets = referenced_workflows(programs)
    changed = {
        op.address
        for op in plan.operations
        if op.resource_type == "workflow" and op.action not in {ChangeAction.UNCHANGED, ChangeAction.DELETE}
    }
    return {address: program for address, program in programs.items() if address not in targets and address in changed}


def referenced_workflows(programs: dict[str, WorkflowProgram]) -> set[str]:
    return {
        target
        for program in programs.values()
        for step in program.steps.values()
        for target in (step.called_workflow_address, step.compensation_workflow_address)
        if target
    }


def create_root(
    ports: WorkflowPorts,
    plan: OrchestrationPlan,
    context: OperationAdmissionContext,
    key: str,
    programs: dict[str, WorkflowProgram],
) -> ControlPlaneOperationRecord:
    now, identity = ports.now(), str(uuid4())
    selected = root_programs(plan, programs)
    roots = tuple(invocation_identity(identity, "", address) for address in selected)
    invocations = {
        invocation_identity(identity, "", address): new_invocation(
            program, invocation_identity(identity, "", address), now
        )
        for address, program in selected.items()
    }
    state = WorkflowContinuation(
        root_operation_id=identity,
        program_digest=runtime_plan_digest(plan),
        programs=programs,
        invocations=invocations,
        roots=roots,
        installation=tuple(op for op in orchestration_plan_model(plan).operations if op.resource_type == "workflow"),
        resources_required=bool(nonworkflow_projection(plan).actionable_operations),
    )
    initial = ports.read().snapshot
    state.events = {
        address: [
            WorkflowHistoryEventModel.model_validate(item) for item in initial.orchestration_history.get(address, [])
        ]
        for address in programs
    }
    for invocation in state.invocations.values():
        event(state, invocation, "workflow_started", now, origin="runtime")
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
    record = ports.claim(
        ports.record(
            receipt=receipt,
            status=status,
            idempotency_key=key,
            request_fingerprint=context.request_commitment,
            workflow=WorkflowOperationState(
                root_operation_id=identity, kind="root", continuation=state.model_copy(deep=True)
            ),
        )
    )
    if record.receipt.operation_id == identity:
        cut = ports.read()
        checkpoint(ports, state, installation_snapshot(state, cut.snapshot), revision=cut.revision)
    return record


def advance_workflows(ports: WorkflowPorts, root_id: str) -> None:
    """Reconcile one original invocation before any successor is considered."""
    while True:
        with ports.mutation():
            progress = workflow_progress_cut(ports, root_id)
            if progress is None:
                return
            cut, root, state = progress
            synchronize_stops(state, cut.snapshot, ports.now())
            if state.outstanding is not None:
                disposition = reconcile_outstanding(ports, state, cut)
                if disposition == "settled":
                    continue
                if disposition == "waiting":
                    return
                dispatch = state.outstanding
            else:
                dispatch = next_dispatch(ports, state, cut)
                if dispatch is None:
                    finish_root(ports, root, state, cut)
                    break
            request = step_request(ports, dispatch)
        receipt = ports.execute(request)
        if not receipt.accepted and not checkpoint_refused_dispatch(ports, root_id, dispatch):
            return


def workflow_progress_cut(
    ports: WorkflowPorts, root_id: str
) -> tuple[WorkflowCut, ControlPlaneOperationRecord, WorkflowContinuation] | None:
    cut = ports.read()
    root = cut.records[root_id]
    if root.status.state not in {OperationState.ACCEPTED, OperationState.RUNNING}:
        return None
    recover_checkpoints(ports, root_id)
    cut = ports.read()
    state = latest_continuation(cut, root_id)
    if state.resources_required and not resources_ready(ports, root, state, cut):
        return None
    return cut, root, state


def resources_ready(
    ports: WorkflowPorts, root: ControlPlaneOperationRecord, state: WorkflowContinuation, cut: WorkflowCut
) -> bool:
    resource = next(
        (
            item
            for item in cut.records.values()
            if item.idempotency_key == f"workflow-resources:{state.root_operation_id}"
        ),
        None,
    )
    if resource is not None:
        if resource.status.state in {OperationState.FAILED, OperationState.CANCELLED} and (
            resource.invocation is None or not resource.invocation.reserved
        ):
            fail_setup(ports, root, state, cut, resource.status.state, resource.status.diagnostics)
        return resource.status.state is OperationState.SUCCEEDED
    return False


def reconcile_outstanding(
    ports: WorkflowPorts, state: WorkflowContinuation, cut: WorkflowCut
) -> Literal["dispatch", "settled", "waiting"]:
    dispatch = state.outstanding
    record = next(
        (
            record
            for record in cut.records.values()
            if record.invocation is not None and record.invocation.request.workflow_step == dispatch
        ),
        None,
    )
    disposition = "dispatch"
    if record is not None:
        disposition = reconcile_step_operation(state, record, cut, ports.now())
        if disposition == "settled":
            checkpoint(ports, state, cut.snapshot, revision=cut.revision)
    return disposition


def reconcile_step_operation(
    state: WorkflowContinuation, record: ControlPlaneOperationRecord, cut: WorkflowCut, now: str
) -> Literal["settled", "waiting"]:
    dispatch = state.outstanding
    invocation = state.invocations[dispatch.invocation_id]
    if conclusive_step_failure(record):
        finish_failed_dispatch(state, record, now)
    elif record.status.state is OperationState.INDETERMINATE and any(
        valid_reconciliation_child(record, child) for child in cut.records.values()
    ):
        if invocation.status == "running":
            invocation.terminal_reason = "workflow step absence reconciled after uncertain execution"
            finish_invocation(state, invocation, "failed", now)
        state.outstanding = None
    elif response_ready(record):
        accept_step_operation(state, record, cut.snapshot, now)
    else:
        return "waiting"
    return "settled"


def conclusive_step_failure(record: ControlPlaneOperationRecord) -> bool:
    return (
        record.status.state in {OperationState.CANCELLED, OperationState.FAILED}
        and (record.workflow is None or record.workflow.response is None)
        and not record.invocation.reserved
    )


def response_ready(record: ControlPlaneOperationRecord) -> bool:
    return (
        record.status.state in {OperationState.SUCCEEDED, OperationState.FAILED}
        and record.workflow is not None
        and record.workflow.response is not None
        and not record.invocation.reserved
    )


def finish_failed_dispatch(state: WorkflowContinuation, record: ControlPlaneOperationRecord, now: str) -> None:
    dispatch = state.outstanding
    invocation = state.invocations[dispatch.invocation_id]
    if record.invocation.consumed:
        event(
            state,
            invocation,
            "step_reported",
            now,
            dispatch=dispatch,
            step_name=dispatch.step_name,
            origin="backend",
            details={"operation_state": record.status.state.value, "operation_id": record.receipt.operation_id},
        )
    if invocation.status == "running":
        invocation.terminal_reason = f"workflow step operation {record.status.state.value}"
        finish_invocation(state, invocation, record.status.state.value, now)
    state.outstanding = None


def accept_step_operation(
    state: WorkflowContinuation, record: ControlPlaneOperationRecord, snapshot: RuntimeSnapshot, now: str
) -> None:
    dispatch = state.outstanding
    invocation = state.invocations[dispatch.invocation_id]
    if invocation.status == "running":
        _, current_digests = admitted_observations(snapshot, dispatch.observation_addresses)
        if current_digests != dispatch.observation_digests:
            raise ConflictError("workflow predicate observations changed before acceptance")
        require_success_evidence(snapshot, dispatch, record.workflow.response)
        accept_response(state, record.workflow.response, now)
    else:
        event(
            state,
            invocation,
            "step_reported",
            now,
            dispatch=dispatch,
            step_name=dispatch.step_name,
            outcome=record.workflow.response.outcome,
            origin="backend",
        )
        state.outstanding = None


def next_dispatch(ports: WorkflowPorts, state: WorkflowContinuation, cut: WorkflowCut) -> WorkflowStepDispatch | None:
    advance_compensation(state, ports.now())
    ready = reconcile_ready(state, ports.now())
    if ready is None:
        # Result reuse can terminate a compensation callee during reconciliation.
        advance_compensation(state, ports.now())
        ready = reconcile_ready(state, ports.now())
    if ready is None:
        return None
    invocation, location = ready
    addresses = observation_addresses(state.programs[invocation.workflow_address], location.step_name)
    truths, digests = admitted_observations(cut.snapshot, addresses)
    state.observation_truths = truths
    dispatch = prepare_dispatch(state, cut.revision, ports.now(), digests)
    allowance = remaining_workflow_budget(state, invocation, ports.now())
    if (
        allowance is not None
        and dispatch.execution_policy is not None
        and dispatch.execution_policy.retry_unit == "native-operation"
    ):
        dispatch = dispatch.model_copy(update={"remaining_budget_ms": allowance})
        state.outstanding = dispatch
    checkpoint(ports, state, cut.snapshot, revision=cut.revision)
    return dispatch


def step_request(ports: WorkflowPorts, dispatch: WorkflowStepDispatch) -> OperationExecutionRequest:
    context = ports.context(OperationKind.ORCHESTRATION, dispatch, dispatch.root_operation_id)
    return ports.request(
        domain=RuntimeDomain.ORCHESTRATION,
        method=ports.dispatch_step,
        plan=dispatch,
        address="runtime.workflow.step",
        diagnostics=[],
        base_snapshot=None,
        idempotency_key=f"workflow-step:{dispatch.dispatch_id}",
        request_fingerprint=context.request_commitment,
        context=context,
        execute_observation=False,
        admission_diagnostics=lambda: workflow_step_admission(ports, dispatch),
    )


def checkpoint_refused_dispatch(ports: WorkflowPorts, root_id: str, dispatch: WorkflowStepDispatch) -> bool:
    with ports.mutation():
        cut = ports.read()
        state = latest_continuation(cut, root_id)
        synchronize_stops(state, cut.snapshot, ports.now())
        stopped = state.invocations[dispatch.invocation_id].status != "running"
        if stopped:
            state.outstanding = None
            checkpoint(ports, state, cut.snapshot, revision=cut.revision)
        return stopped


def workflow_step_admission(ports: WorkflowPorts, dispatch: WorkflowStepDispatch) -> list[Diagnostic]:
    cut = ports.read()
    state = latest_continuation(cut, dispatch.root_operation_id)
    synchronize_stops(state, cut.snapshot, ports.now())
    root = cut.records[dispatch.root_operation_id]
    allowed = (
        root.status.state is OperationState.RUNNING
        and state.outstanding == dispatch
        and state.invocations[dispatch.invocation_id].status == "running"
        and cut.revision == dispatch.predecessor_revision + 1
    )
    return (
        []
        if allowed
        else [
            Diagnostic(
                code="runtime.workflow.dispatch-refused",
                domain="runtime",
                address="runtime.workflow.step",
                message="Workflow state no longer permits this dispatch.",
            )
        ]
    )


def finish_root(
    ports: WorkflowPorts,
    root: ControlPlaneOperationRecord,
    state: WorkflowContinuation,
    cut: WorkflowCut,
    *,
    forced_state: OperationState | None = None,
    source_diagnostics: list[Diagnostic] | None = None,
) -> None:
    if any(item.status == "running" for item in state.invocations.values()):
        return
    statuses = {state.invocations[key].status for key in state.roots}
    outcome = forced_state or root_outcome(statuses)
    checkpoint(ports, state, cut.snapshot, revision=cut.revision)
    diagnostics = root_diagnostics(root, cut, outcome, source_diagnostics)
    ports.commit(
        ports.read().snapshot,
        replace(
            root,
            status=replace(
                root.status,
                state=outcome,
                updated_at=ports.now(),
                changed_addresses=changed_workflow_addresses(state),
                diagnostics=diagnostics,
            ),
        ),
    )


def root_diagnostics(
    root: ControlPlaneOperationRecord,
    cut: WorkflowCut,
    outcome: OperationState,
    source_diagnostics: list[Diagnostic] | None,
) -> list[Diagnostic]:
    diagnostics = (
        []
        if outcome is OperationState.SUCCEEDED
        else [
            Diagnostic(
                code="runtime.workflow.terminated",
                domain="runtime",
                address="runtime.workflow",
                message="Workflow execution reached an unsuccessful terminal state.",
            )
        ]
    )
    if outcome is not OperationState.SUCCEEDED:
        diagnostics.extend(
            source_diagnostics
            or [
                diagnostic
                for child in cut.records.values()
                if child.status.context.parent_operation_id == root.receipt.operation_id
                and child.status.state in {OperationState.FAILED, OperationState.CANCELLED}
                for diagnostic in child.status.diagnostics
            ]
        )
    return diagnostics


def root_outcome(statuses: set[str]) -> OperationState:
    if statuses <= {"succeeded"}:
        return OperationState.SUCCEEDED
    return OperationState.CANCELLED if "cancelled" in statuses else OperationState.FAILED


def fail_setup(
    ports: WorkflowPorts,
    root: ControlPlaneOperationRecord,
    state: WorkflowContinuation,
    cut: WorkflowCut,
    outcome: OperationState,
    diagnostics: list[Diagnostic],
) -> None:
    for invocation in state.invocations.values():
        if invocation.status == "running":
            invocation.terminal_reason = f"workflow resource setup {outcome.value}"
            finish_invocation(state, invocation, outcome.value, ports.now())
    finish_root(ports, root, state, cut, forced_state=outcome, source_diagnostics=diagnostics)


def admitted_observations(
    snapshot: RuntimeSnapshot, addresses: tuple[str, ...]
) -> tuple[dict[str, bool], dict[str, str]]:
    truths, digests = {}, {}
    for address in addresses:
        if address.startswith("evaluation.assertion."):
            payload = snapshot.proposition_truth_results.get(address)
            if payload is None:
                raise ConflictError("workflow assertion has no accepted proposition truth")
            truth = PropositionTruthResultModel.model_validate(payload)
            if truth.assertion_outcome.value not in {"true", "false"}:
                raise ConflictError("workflow assertion truth is indeterminate")
            truths[address] = truth.assertion_outcome.value == "true"
            digests[address] = canonical_json_digest(payload)
            continue
        result = snapshot.evaluation_results.get(address)
        if not isinstance(result, dict):
            raise ConflictError("workflow predicate has no current accepted evaluation result")
        observed = EvaluationExecutionState.from_payload(result)
        if observed.status is not EvaluationResultStatus.READY or type(observed.passed) is not bool:
            raise ConflictError("workflow predicate evaluation is not ready")
        truths[address] = observed.passed
        digests[address] = canonical_json_digest(result)
    return truths, digests


def synchronize_stops(state: WorkflowContinuation, snapshot: RuntimeSnapshot, now: str) -> None:
    results = dict(snapshot.orchestration_results)
    histories = {address: list(events) for address, events in snapshot.orchestration_history.items()}
    for invocation in state.invocations.values():
        if invocation.status != "running":
            continue
        address = invocation.workflow_address
        persisted = stopped_invocation_result(state, invocation, snapshot, results, histories, now)
        if persisted is None:
            continue
        status = persisted.get("workflow_status")
        if status not in {"cancelled", "timed_out"}:
            continue
        invocation.status = status
        invocation.locations = []
        invocation.updated_at = persisted["updated_at"]
        invocation.terminal_reason = persisted["terminal_reason"]
        invocation.compensation_status = persisted["compensation_status"]
        invocation.compensation_updated_at = persisted.get("compensation_updated_at")
        state.events[address] = [WorkflowHistoryEventModel.model_validate(item) for item in histories[address]]


def stopped_invocation_result(
    state: WorkflowContinuation,
    invocation: WorkflowInvocation,
    snapshot: RuntimeSnapshot,
    results: dict[str, object],
    histories: dict[str, list[dict[str, object]]],
    now: str,
) -> dict[str, object] | None:
    address = invocation.workflow_address
    persisted = snapshot.orchestration_results.get(address)
    if not isinstance(persisted, dict) or persisted.get("run_id") != invocation.invocation_id:
        persisted = invocation_result(invocation)
    results[address] = persisted
    allowance = remaining_workflow_budget(state, invocation, now)
    if allowance is not None and allowance <= 0:
        invocation.terminal_reason = "workflow apparatus budget exhausted"
        finish_invocation(state, invocation, "failed", now)
        return None
    entry = snapshot.entries.get(address)
    if entry is not None and persisted.get("workflow_status") == "running":
        timed_out = workflow_timeout_update(snapshot, address, entry, results, histories, now)
        if timed_out is not None:
            results[address], histories[address] = timed_out
            persisted = timed_out[0]
    return persisted


def remaining_workflow_budget(state: WorkflowContinuation, invocation: WorkflowInvocation, now: str) -> int | None:
    policies = state.programs[invocation.workflow_address].execution_policies
    budgets = [
        item.policy.budget_ms
        for item in policies
        if item.retry_unit == "native-operation" and item.policy.budget_ms is not None
    ]
    if not budgets:
        return None
    elapsed = parse_offset_timestamp_utc(now) - parse_offset_timestamp_utc(invocation.started_at)
    if elapsed.days < 0:
        raise ConflictError("workflow apparatus clock precedes its start")
    elapsed_ms = elapsed.days * 86400000 + elapsed.seconds * 1000 + elapsed.microseconds // 1000
    return max(0, min(budgets) - elapsed_ms)
