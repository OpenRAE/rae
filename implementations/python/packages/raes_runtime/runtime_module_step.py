"""One durable module step through the incumbent operation admission path."""

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.runtime_state import OperationState

from .control_plane_recovery import unresolved_indeterminate_operation_ids_from_records
from .runtime_decisions import RunPhaseDecision


def step_key(execution_id, phase):
    return "runtime-step:" + canonical_json_digest((execution_id, phase)).removeprefix("sha256:")


def step_records(run, execution_id, phase):
    run._reload_derived_state()
    key = step_key(execution_id, phase)
    return tuple(record for record in run._operations.values() if record.idempotency_key == key)


def advance_step(run, *, execution_id, phase, dispatch):
    """A missing acknowledgement never becomes permission for a new operation."""
    started = RunPhaseDecision(run_scope=run._run_scope, execution_id=execution_id, phase=phase, state="started")
    terminal_id = started.model_copy(update={"state": "succeeded"}).decision_id
    for decision in run._store.load_runtime_decisions():
        if decision.decision_id == terminal_id:
            return decision.state
    run._store.claim_runtime_decision(started)
    records = step_records(run, execution_id, phase)
    result = None
    if not records:
        result = dispatch(step_key(execution_id, phase))
        records = step_records(run, execution_id, phase)
    states = phase_states(run, records)
    if states.intersection({OperationState.ACCEPTED, OperationState.RUNNING}):
        return "pending"
    state = next(
        (
            candidate.value
            for candidate in (OperationState.INDETERMINATE, OperationState.CANCELLED, OperationState.FAILED)
            if candidate in states
        ),
        "failed" if result is not None and not result.success else "succeeded",
    )
    # Unknown is a recovery cut, not a final semantic outcome. Reconciled records
    # can later supply terminal evidence without redispatching the operation.
    if state != "indeterminate":
        run._store.claim_runtime_decision(
            started.model_copy(
                update={
                    "state": state,
                    "operation_ids": tuple(record.receipt.operation_id for record in records),
                }
            )
        )
    return state


def phase_states(run, records):
    """A resolved unknown attempt remains failed; resolution never creates success."""
    unresolved = set(unresolved_indeterminate_operation_ids_from_records(run._operations))
    return {
        OperationState.FAILED
        if record.status.state is OperationState.INDETERMINATE and record.receipt.operation_id not in unresolved
        else record.status.state
        for record in records
    }
