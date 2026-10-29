"""Durable progress through the runtime's existing application phases."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.errors import ConflictError
from raes_contracts.runtime_state import OperationKind, OperationState

from .control_plane_operation_context import operation_actor_scope, operation_idempotency_fingerprint
from .interaction import _RuntimeApplyState
from .runtime_decisions import DecisionIdentity, RunPhaseDecision, RunProgramDecision, RuntimeDecision
from .runtime_module_step import phase_states
from .runtime_run_preparation import prepare_run, restore_run_modules

# These are existing runtime modules. Both synchronous apply and durable driving
# consume this order; backend selection cannot supply a different interpreter.
APPLICATION_PHASES = (
    "_apply_provisioning_phase",
    "_apply_time_phase",
    "_apply_participant_execution_phase",
    "_apply_evaluation_phase",
    "_apply_orchestration_phase",
    "_apply_participant_start_phase",
)


if TYPE_CHECKING:
    from raes_contracts.augmentation_preparation import AugmentationPreparation
    from raes_contracts.planning import RuntimeDomain
    from raes_processor.models import ExecutionPlan

    from .control_plane_store import ControlPlaneOperationRecord
    from .runtime_run_context import RuntimeRunContext


class RunProgress(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    execution_id: DecisionIdentity
    run_scope: DecisionIdentity
    phase: int = Field(ge=0, le=64)
    state: Literal["progress", "pending", "succeeded", "failed", "cancelled", "indeterminate"]
    operation_ids: tuple[DecisionIdentity, ...] = Field(default=(), max_length=64)


def program_decision(
    run: RuntimeRunContext, plan: ExecutionPlan, execution_id: str, identity: object | None
) -> RunProgramDecision:
    actor, scopes = operation_actor_scope(identity)
    digest = operation_idempotency_fingerprint(
        kind=OperationKind.COMPOSITION_PHASE,
        request={
            "model": plan.model,
            "provisioning": plan.provisioning,
            "evaluation": plan.evaluation,
            "orchestration": plan.orchestration,
            "observation_owner": plan.observation_owner,
        },
        base_snapshot=plan.base_snapshot,
    )
    return RunProgramDecision(
        run_scope=run._run_scope,
        execution_id=execution_id,
        plan_digest=digest,
        actor_id=actor,
        authorization_scope=scopes,
    )


def advance_plan(
    run: RuntimeRunContext, plan: ExecutionPlan, *, execution_id: str, identity: object | None = None
) -> RunProgress:
    """Advance one phase; a pending or unknown operation is never re-invoked."""
    plan = deepcopy(plan)
    admission = program_decision(run, plan, execution_id, identity)
    decisions = {item.decision_id: item for item in run._store.load_runtime_decisions()}
    _admit_program(run, plan, admission, decisions)
    plan, preparation = prepare_run(run, plan, admission, decisions)
    if not preparation.admitted:
        return RunProgress(execution_id=execution_id, run_scope=run._run_scope, phase=0, state="failed")
    run.register_planner_produced_plan(plan)
    run._interaction_plan = plan
    phases = {
        record.phase: record
        for record in decisions.values()
        if isinstance(record, RunPhaseDecision)
        and record.execution_id == execution_id
        and record.run_scope == run._run_scope
        and record.state != "started"
    }
    restore_run_modules(run, plan, phases)
    return _advance_phases(run, plan, admission, identity, preparation.previews, phases)


def _admit_program(
    run: RuntimeRunContext, plan: ExecutionPlan, admission: RunProgramDecision, decisions: dict[str, RuntimeDecision]
) -> None:
    prior = decisions.get(admission.decision_id)
    if prior is None:
        failure = run._apply_precondition_failure(plan, list(plan.diagnostics))
        if failure is not None:
            raise ConflictError("run plan admission failed")
        if run._participant_driver_apply_precondition() is not None:
            raise ConflictError("run participant driver remains active")
        run._store.claim_runtime_decision(admission)
    elif prior != admission or plan.manifest != run._target.manifest:
        raise ConflictError("run execution identity conflicts with its admitted inputs or actor")


def _advance_phases(
    run: RuntimeRunContext,
    plan: ExecutionPlan,
    admission: RunProgramDecision,
    identity: object | None,
    previews: dict[RuntimeDomain, AugmentationPreparation],
    phases: dict[int, RunPhaseDecision],
) -> RunProgress:
    for phase in range(len(APPLICATION_PHASES)):
        prior_phase = phases.get(phase)
        if prior_phase is not None:
            if prior_phase.state != "succeeded":
                return _progress(prior_phase)
            continue
        return _advance_phase(run, plan, admission, phase, identity, previews)
    return _finalize_run(run, admission.execution_id, phases)


def _finalize_run(run: RuntimeRunContext, execution_id: str, phases: dict[int, RunPhaseDecision]) -> RunProgress:
    finalization = phases.get(len(APPLICATION_PHASES))
    if finalization is not None and finalization.state != "succeeded":
        return _progress(finalization)
    if run._participant_clock_driver is None:
        state = _RuntimeApplyState(working_snapshot=run.snapshot, diagnostics=[], changed_addresses=[], details={})
        run._finalize_participant_driver_apply(state)
        if not state.failure.success:
            failed = RunPhaseDecision(
                run_scope=run._run_scope, execution_id=execution_id, phase=len(APPLICATION_PHASES), state="failed"
            )
            run._store.claim_runtime_decision(failed)
            return _progress(failed)
    return RunProgress(
        execution_id=execution_id, run_scope=run._run_scope, phase=len(APPLICATION_PHASES), state="succeeded"
    )


def _advance_phase(
    run: RuntimeRunContext,
    plan: ExecutionPlan,
    admission: RunProgramDecision,
    phase: int,
    identity: object | None,
    previews: dict[RuntimeDomain, AugmentationPreparation],
) -> RunProgress:
    started = RunPhaseDecision(
        run_scope=run._run_scope, execution_id=admission.execution_id, phase=phase, state="started"
    )
    run._store.claim_runtime_decision(started)
    key = "run-phase:" + canonical_json_digest((admission.decision_id, phase)).removeprefix("sha256:")
    records = _phase_records(run, admission, key)
    state = None
    if not records:
        state = _RuntimeApplyState(
            working_snapshot=run.snapshot,
            diagnostics=[],
            changed_addresses=[],
            details={},
            phase_key=key,
            identity=identity,
            augmentation_previews=previews,
        )
        getattr(run, APPLICATION_PHASES[phase])(plan, state)
        records = _phase_records(run, admission, key)
    operation_ids = tuple(record.receipt.operation_id for record in records)
    states = phase_states(run, records)
    if states.intersection({OperationState.ACCEPTED, OperationState.RUNNING}):
        return RunProgress(
            execution_id=admission.execution_id,
            run_scope=run._run_scope,
            phase=phase,
            state="pending",
            operation_ids=operation_ids,
        )
    outcome = _phase_outcome(states, state)
    terminal = started.model_copy(update={"state": outcome, "operation_ids": operation_ids})
    if outcome != "indeterminate":
        run._store.claim_runtime_decision(terminal)
    if outcome != "succeeded":
        return _progress(terminal)
    return RunProgress(
        execution_id=admission.execution_id,
        run_scope=run._run_scope,
        phase=phase + 1,
        state="progress",
        operation_ids=operation_ids,
    )


def _phase_outcome(states: set[OperationState], state: _RuntimeApplyState | None) -> str:
    outcome = "succeeded"
    for candidate in (OperationState.INDETERMINATE, OperationState.CANCELLED, OperationState.FAILED):
        if candidate in states:
            outcome = candidate.value
            break
    if state is not None and state.failure is not None and not state.failure.success and outcome == "succeeded":
        outcome = "failed"
    return outcome


def _phase_records(
    run: RuntimeRunContext, admission: RunProgramDecision, key: str
) -> tuple[ControlPlaneOperationRecord, ...]:
    run._reload_derived_state()
    return tuple(
        record
        for record in run._operations.values()
        if record.idempotency_key == key and record.receipt.context.actor_id == admission.actor_id
    )


def _progress(phase: RunPhaseDecision) -> RunProgress:
    return RunProgress(
        execution_id=phase.execution_id,
        run_scope=phase.run_scope,
        phase=phase.phase,
        state=phase.state,
        operation_ids=phase.operation_ids,
    )
