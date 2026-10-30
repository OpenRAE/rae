"""Runtime-manager control for autonomous ordinary participants."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ParticipantActionResultModel, ParticipantAutonomousExecutionStateModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import ConflictError, OperationalError
from raes_contracts.participant_episode import ParticipantEpisodeResetRequest
from raes_contracts.participant_tool_actions import ParticipantToolActionRequest, ParticipantToolActionSettlement
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    ApplyResult,
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
)

from .backend_calls import _BackendCallContext, _RealizationApplyContext
from .control_plane_lifecycle import runtime_owned
from .control_plane_mutation import control_plane_mutation
from .control_plane_store import ControlPlaneOperationRecord, NewClaimRejected, TerminalCommitMode
from .control_plane_store_revision import SnapshotRevisionConflict
from .diagnostics import _has_error_diagnostic
from .interaction_dispatch import ComposedOperation
from .participant_clock_driver import ParticipantClockDriver
from .participant_invocation_tool_actions import InvocationToolActionConfiguration
from .participant_invocation_tool_claims import (
    TOOL_ACTION_IDEMPOTENCY_PREFIX,
    TOOL_ACTION_RECORD_KIND,
    TOOL_ADMISSION_PARENT_NOT_LIVE,
    TOOL_ADMISSION_STOPPED,
    TOOL_ADMISSION_UNRESOLVED,
)

if TYPE_CHECKING:
    from raes_processor.models import ExecutionPlan

    from .manager import _RuntimeApplyState


# Issue #1740: each tool action of an autonomous invocation is one child
# control-plane operation record of the enclosing due operation. Admission
# claims an accepted record, the one-use dispatch grant moves it to running, and
# settlement commits a terminal record with an actor audit. Every write completes
# before the port answers, so the selected store retains claims, consumed grants
# and uncertainty across restart. Startup reconciliation classifies a
# non-terminal record; RAES never repeats the tool effect.
_TERMINAL_STATES = {
    ParticipantToolActionSettlement.COMPLETED: OperationState.SUCCEEDED,
    ParticipantToolActionSettlement.WITHHELD: OperationState.CANCELLED,
    ParticipantToolActionSettlement.INDETERMINATE: OperationState.INDETERMINATE,
}
_REVISION_RETRIES = 3


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _request_payload(request: ParticipantToolActionRequest) -> dict[str, object]:
    return {
        "kind": TOOL_ACTION_RECORD_KIND,
        "tool_call_id": request.tool_call_id,
        "invocation_action_instance_id": request.invocation_action_instance_id,
        "participant_address": request.participant_address,
        "episode_id": request.episode_id,
        "participant_implementation_ref": request.participant_implementation_ref,
        "tool_affordance_address": request.tool_affordance_address,
        "action_contract_address": request.action_contract_address,
        "observation_boundary_address": request.observation_boundary_address,
        "target_addresses": list(request.target_addresses),
        "execution_scope_ref": request.execution_scope_ref,
        "execution_generation": request.execution_generation,
    }


@dataclass(frozen=True)
class InvocationToolActionLedger:
    """Write child operation records for one enclosing due operation."""

    store: object
    parent_operation_id: str
    parent_context: OperationAdmissionContext
    engine_admission: Callable[[], None] | None = None

    def effect_admission_refusal(self) -> str | None:
        """Return why the store refuses new tool effects now, or ``None``.

        The enclosing operation must still be live, effect admission must be
        open, and the run must hold no unresolved indeterminate operation. The
        check reads the store, not a cached record cut.
        """

        from .control_plane_recovery import unresolved_indeterminate_operation_ids_from_records

        if self.engine_admission is not None:
            try:
                self.engine_admission()
            # The engine refuses a stopped, closing or retired owner exactly as for ordinary claims.
            except ConflictError, OperationalError:
                return TOOL_ADMISSION_STOPPED
        records = self.store.load_records()
        parent = records.get(self.parent_operation_id)
        stopped = getattr(self.store, "effect_admission_stopped", None)
        if parent is None or parent.status.state not in {OperationState.ACCEPTED, OperationState.RUNNING}:
            return TOOL_ADMISSION_PARENT_NOT_LIVE
        if callable(stopped) and stopped():
            return TOOL_ADMISSION_STOPPED
        if unresolved_indeterminate_operation_ids_from_records(
            records, target_scope=self.parent_context.target_scope, run_scope=self.parent_context.run_scope
        ):
            return TOOL_ADMISSION_UNRESOLVED
        return None

    def record_admission(
        self,
        action_instance_id: str,
        request: ParticipantToolActionRequest,
        admitted_at: str,
    ) -> ControlPlaneOperationRecord:
        """Claim the accepted child record before the port returns its decision."""

        payload = _request_payload(request)
        context = OperationAdmissionContext(
            actor_id=self.parent_context.actor_id,
            authorization_scope=self.parent_context.authorization_scope,
            target_scope=self.parent_context.target_scope,
            run_scope=self.parent_context.run_scope,
            operation_kind=OperationKind.PARTICIPANT_ACTION,
            request_commitment=canonical_json_digest(payload),
            parent_operation_id=self.parent_operation_id,
        )
        record = ControlPlaneOperationRecord(
            receipt=OperationReceipt(
                operation_id=action_instance_id,
                domain=RuntimeDomain.PARTICIPANT,
                submitted_at=admitted_at,
                accepted=True,
                context=context,
            ),
            status=OperationStatus(
                operation_id=action_instance_id,
                domain=RuntimeDomain.PARTICIPANT,
                state=OperationState.ACCEPTED,
                submitted_at=admitted_at,
                updated_at=admitted_at,
                context=context,
            ),
            request_fingerprint=context.request_commitment,
            idempotency_key=TOOL_ACTION_IDEMPOTENCY_PREFIX + action_instance_id,
            result_payload=payload,
        )
        return self.store.claim_record(record)

    def record_dispatch(self, record: ControlPlaneOperationRecord) -> ControlPlaneOperationRecord:
        """Persist the consumed one-use grant before the port returns it."""

        running = replace(
            record,
            status=replace(record.status, state=OperationState.RUNNING, updated_at=_now_iso()),
        )
        self.store.save_record(running)
        return running

    def record_settlement(
        self,
        record: ControlPlaneOperationRecord,
        settlement: ParticipantToolActionSettlement,
        action_result: ParticipantActionResultModel,
    ) -> ControlPlaneOperationRecord:
        """Commit the terminal child record and its actor audit; the snapshot does not change."""

        terminal = replace(
            record,
            status=replace(record.status, state=_TERMINAL_STATES[settlement], updated_at=_now_iso()),
            result_payload={
                **(record.result_payload or {}),
                "settlement": settlement.value,
                "action_result": action_result.model_dump(mode="json", exclude_none=True),
            },
        )
        retries = _REVISION_RETRIES
        while True:
            state = self.store.load_snapshot_state()
            try:
                self.store.commit_terminal_operation(
                    state.snapshot,
                    terminal,
                    mode=TerminalCommitMode.OPERATION_ONLY,
                    expected_revision=state.revision,
                )
            except SnapshotRevisionConflict:
                # A concurrent supervisory cut advanced the revision; this commit changes no snapshot.
                retries -= 1
                if retries == 0:
                    raise
            else:
                return terminal


class RuntimeParticipantExecutionMixin:
    """Autonomous participant portion of the runtime manager."""

    def _participant_driver_apply_precondition(self) -> ApplyResult | None:
        if self._stop_participant_clock_driver():
            return None
        return ApplyResult(
            success=False,
            snapshot=self._snapshot,
            diagnostics=[
                Diagnostic(
                    code="runtime.participant-clock-driver-stop-timeout",
                    domain="participant",
                    address="runtime.apply",
                    message="Apply did not start because the participant clock driver is still active.",
                )
            ],
        )

    def _finalize_participant_driver_apply(self, state: _RuntimeApplyState) -> None:
        driver_started = self._start_participant_clock_driver()
        if not driver_started:
            state.diagnostics.append(
                Diagnostic(
                    code="runtime.participant-clock-driver-stop-timeout",
                    domain="participant",
                    address="runtime.apply",
                    message="Apply completed but the prior participant clock driver remained active.",
                )
            )
        state.failure = ApplyResult(
            materialization_attestation=state.materialization_attestation,
            success=driver_started and not _has_error_diagnostic(state.diagnostics),
            snapshot=self._snapshot,
            diagnostics=state.diagnostics,
            changed_addresses=list(dict.fromkeys(state.changed_addresses)),
            details=state.details,
        )

    def _apply_participant_execution_phase(
        self,
        execution_plan: ExecutionPlan,
        state: _RuntimeApplyState,
    ) -> None:
        policies = tuple(
            spec.autonomous_execution
            for spec in execution_plan.model.behavior_specifications.values()
            if spec.autonomous_execution is not None
        )
        self._participant_execution_policies = policies
        self._participant_execution_time_model = execution_plan.model.time_model
        if not policies:
            return
        if self._target.participant_runtime is None:
            self._fail_apply_state(state)
            return
        from .participant_scheduler import ParticipantScheduler

        if self._participant_scheduler is None:
            self._participant_scheduler = ParticipantScheduler()
        result = self._participant_scheduler_call(
            "initialize",
            state.working_snapshot,
            lambda predecessor, _cancellation_sink, _operation: self._participant_scheduler.initialize(
                policies,
                execution_plan.model.time_model,
                self._target.participant_runtime,
                predecessor,
                self._participant_activity_controls,
                self._target.manifest.participant_runtime.resource_budgets
                if self._target.manifest.participant_runtime is not None
                else None,
            ),
            idempotency_key=state.phase_key,
            identity=state.identity,
        )
        self._record_phase_result(state, result)
        if not result.success:
            self._fail_apply_state(state)

    def _start_participant_execution_phase(
        self,
        execution_plan: ExecutionPlan,
        state: _RuntimeApplyState,
    ) -> bool:
        if not self._participant_execution_policies:
            return True
        due = self._participant_scheduler_call(
            "start",
            state.working_snapshot,
            lambda predecessor, cancellation_sink, operation: self._participant_scheduler.run_due(
                self._participant_execution_policies,
                execution_plan.model.time_model,
                self._target.participant_runtime,
                predecessor,
                self._participant_activity_controls,
                cancellation_sink=cancellation_sink,
                invocation_tools=self._invocation_tool_configuration(operation),
            ),
            idempotency_key=state.phase_key,
            identity=state.identity,
        )
        self._record_phase_result(state, due)
        return due.success

    def run_due_participant_actions(self) -> ApplyResult:
        with self._participant_execution_lock:
            if self._target.participant_runtime is None or self._participant_scheduler is None:
                raise ConflictError("runtime manager has no participant runtime")
            result = self._participant_scheduler_call(
                "due",
                self._snapshot,
                lambda predecessor, cancellation_sink, operation: self._participant_scheduler.run_due(
                    self._participant_execution_policies,
                    self._participant_execution_time_model,
                    self._target.participant_runtime,
                    predecessor,
                    self._participant_activity_controls,
                    cancellation_sink=cancellation_sink,
                    invocation_tools=self._invocation_tool_configuration(operation),
                ),
            )
            return result

    def _invocation_tool_configuration(self, operation: ComposedOperation) -> InvocationToolActionConfiguration | None:
        """Return the claimed tool-action composition for one enclosing due operation.

        Tool actions persist as child records of ``operation`` in the selected store.
        An installed crossing policy refuses the composition.
        """

        return InvocationToolActionConfiguration.from_manifest(
            self._target.manifest.participant_runtime,
            ledger=InvocationToolActionLedger(
                store=self._store,
                parent_operation_id=operation.operation_id,
                parent_context=operation.context,
                engine_admission=self._tool_engine_admission,
            ),
            crossing_installed=getattr(self, "_crossing_policy_resolver", None) is not None,
        )

    def _tool_engine_admission(self) -> None:
        """Apply the owner's effect-admission checks to a hosted tool claim or grant.

        The engine reservation is idempotent for the run that already holds it and
        refuses a stopped, closing or retired owner. The run's own stop flag also refuses.
        """

        if getattr(self, "_effect_admission_stopped", False):
            raise NewClaimRejected("runtime effect admission is closed")
        engine = getattr(self, "_engine", None)
        if engine is not None:
            engine.reserve(self)

    def _participant_scheduler_call(
        self,
        phase: str,
        predecessor: RuntimeSnapshot,
        method: Callable[[RuntimeSnapshot, Callable[[ApplyResult], None], ComposedOperation], ApplyResult],
        *,
        idempotency_key: str = "",
        identity: object | None = None,
    ) -> ApplyResult:
        """Run one scheduler phase as a composition operation.

        The method receives the predecessor, a sink for the state it settled
        before a cancellation, and the enclosing operation. The operation commits
        the sunk state, then the cancellation propagates.
        """

        return self._interaction_backend_call(
            method,
            predecessor,
            address=f"runtime.participant.{phase}",
            snapshot=predecessor,
            realization=_RealizationApplyContext(effect_owners=frozenset({"participant"})),
            call=_BackendCallContext(information_state_context_resolver=self._information_state_context_resolver),
            runtime_composition=True,
            operation_aware=True,
            idempotency_key=idempotency_key,
            identity=identity,
        )

    def _start_participant_clock_driver(self) -> bool:
        if not self._stop_participant_clock_driver():
            return False
        if not self._participant_execution_policies or self._participant_execution_time_model is None:
            return True
        self._participant_clock_driver = ParticipantClockDriver(
            self._participant_execution_policies,
            self._participant_execution_time_model,
            snapshot=lambda: self._snapshot,
            advance=lambda clock_address, ticks: self.advance_time(clock_address, ticks=ticks),
            service_due=self.run_due_participant_actions,
            lock=self._participant_execution_lock,
            publish_failure=self._publish_participant_clock_driver_failure,
            mutation_scope=lambda: control_plane_mutation(self, OperationKind.COMPOSITION_PHASE),
        )
        self._participant_clock_driver.start()
        return True

    def _publish_participant_clock_driver_failure(
        self,
        result: ApplyResult,
    ) -> None:
        from .participant_driver_failure import commit_driver_failure

        with self._lifecycle_condition:
            if self._closing or self._closed:
                return
            self._runtime_ready = False
        commit_driver_failure(self, result)

    def _stop_participant_clock_driver(self) -> bool:
        if self._participant_clock_driver is not None:
            if not self._participant_clock_driver.stop():
                return False
        self._participant_clock_driver = None
        return True

    @runtime_owned
    def participant_clock_driver_status(self) -> dict[str, object]:
        driver = self._participant_clock_driver
        failure = driver.failure if driver is not None else None
        return {
            "active": bool(driver is not None and driver.active),
            "failure": ([diagnostic.message for diagnostic in failure.diagnostics] if failure is not None else None),
        }

    def _sync_participant_execution_clock(
        self,
        method_name: str,
    ) -> ApplyResult | None:
        if method_name in {"advance", "jump", "resume"} and self._participant_scheduler is not None:
            return self.run_due_participant_actions()
        return None

    def _participant_execution_clock_reset_requests(
        self,
        clock_address: str,
    ) -> tuple[ParticipantEpisodeResetRequest, ...]:
        segment = self._next_clock_segment(clock_address)
        if segment is None:
            return ()
        participant_addresses = {
            participant_address
            for policy in self._participant_execution_policies
            if policy.clock_address == clock_address
            for participant_address in policy.participant_addresses
        }
        return tuple(
            ParticipantEpisodeResetRequest(
                participant_address=participant_address,
                episode_id=f"{participant_address}-autonomous-{segment}",
                reason=f"shared clock reset to segment {segment}",
            )
            for participant_address in sorted(participant_addresses)
        )

    def _next_clock_segment(self, clock_address: str) -> int | None:
        if self._snapshot.time_model_state is None:
            return None
        clock = self._snapshot.time_model_state.clocks.get(clock_address)
        return None if clock is None else clock.coordinate.segment + 1

    def _participant_execution_clock_preflight(
        self,
        method_name: str,
        args: tuple[object, ...],
    ) -> ApplyResult | None:
        transition = self._participant_clock_transition(method_name, args)
        if transition is None:
            return None
        clock_address, current_tick, resulting_tick = transition
        for state_address, payload in self._snapshot.participant_autonomous_execution_states.items():
            state = ParticipantAutonomousExecutionStateModel.model_validate(payload)
            failure = self._participant_cadence_skip_failure(
                state_address,
                state,
                clock_address,
                current_tick,
                resulting_tick,
            )
            if failure is not None:
                return failure
        return None

    def _participant_clock_transition(
        self,
        method_name: str,
        args: tuple[object, ...],
    ) -> tuple[str, int, int] | None:
        if method_name not in {"advance", "jump"} or self._snapshot.time_model_state is None:
            return None
        clock_address = str(args[0])
        clock = self._snapshot.time_model_state.clocks.get(clock_address)
        if clock is None:
            return None
        current_tick = clock.coordinate.tick
        resulting_tick = current_tick + int(args[1]) if method_name == "advance" else int(args[1])
        return (clock_address, current_tick, resulting_tick) if resulting_tick > current_tick else None

    def _participant_cadence_skip_failure(
        self,
        state_address: str,
        state: ParticipantAutonomousExecutionStateModel,
        clock_address: str,
        current_tick: int,
        resulting_tick: int,
    ) -> ApplyResult | None:
        belongs_to_clock = state.clock_address == clock_address and state.lifecycle_state == "running"
        skips_cadence = state.next_tick < current_tick or current_tick < state.next_tick < resulting_tick
        if not belongs_to_clock or not skips_cadence:
            return None
        return ApplyResult(
            success=False,
            snapshot=self._snapshot,
            diagnostics=[
                Diagnostic(
                    code="runtime.participant-autonomous-cadence-skipped",
                    domain="participant",
                    address=state_address,
                    message=(
                        f"Clock transition to tick {resulting_tick} would skip governed participant "
                        f"cadence tick {state.next_tick}; advance to the cadence boundary first."
                    ),
                )
            ],
        )

    def _initialize_participant_scheduler(self) -> None:
        self._participant_execution_lock = threading.RLock()
        self._participant_scheduler = None
        self._participant_execution_policies = ()
        self._participant_execution_time_model = None
        self._participant_clock_driver = None


__all__ = ["InvocationToolActionLedger", "RuntimeParticipantExecutionMixin"]
