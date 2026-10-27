"""Runtime-manager control for autonomous ordinary participants."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_episode import ParticipantEpisodeResetRequest
from raes_contracts.runtime_state import ApplyResult, OperationKind, RuntimeSnapshot

from .backend_calls import _BackendCallContext, _RealizationApplyContext
from .control_plane_lifecycle import runtime_owned
from .control_plane_mutation import control_plane_mutation
from .diagnostics import _has_error_diagnostic
from .participant_clock_driver import ParticipantClockDriver

if TYPE_CHECKING:
    from raes_processor.models import ExecutionPlan

    from .manager import _RuntimeApplyState


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
            lambda predecessor: self._participant_scheduler.initialize(
                policies,
                execution_plan.model.time_model,
                self._target.participant_runtime,
                predecessor,
                self._participant_activity_controls,
                self._target.manifest.participant_runtime.resource_budgets
                if self._target.manifest.participant_runtime is not None
                else None,
            ),
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
            lambda predecessor: self._participant_scheduler.run_due(
                self._participant_execution_policies,
                execution_plan.model.time_model,
                self._target.participant_runtime,
                predecessor,
                self._participant_activity_controls,
            ),
        )
        self._record_phase_result(state, due)
        return due.success

    def run_due_participant_actions(self) -> ApplyResult:
        with self._participant_execution_lock:
            if self._target.participant_runtime is None or self._participant_scheduler is None:
                raise ValueError("runtime manager has no participant runtime")
            result = self._participant_scheduler_call(
                "due",
                self._snapshot,
                lambda predecessor: self._participant_scheduler.run_due(
                    self._participant_execution_policies,
                    self._participant_execution_time_model,
                    self._target.participant_runtime,
                    predecessor,
                    self._participant_activity_controls,
                ),
            )
            return result

    def _participant_scheduler_call(
        self, phase: str, predecessor: RuntimeSnapshot, method: Callable[[RuntimeSnapshot], ApplyResult]
    ) -> ApplyResult:
        return self._interaction_backend_call(
            method,
            predecessor,
            address=f"runtime.participant.{phase}",
            snapshot=predecessor,
            realization=_RealizationApplyContext(effect_owners=frozenset({"participant"})),
            call=_BackendCallContext(information_state_context_resolver=self._information_state_context_resolver),
            runtime_composition=True,
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


__all__ = ["RuntimeParticipantExecutionMixin"]
