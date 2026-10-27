"""Runtime-manager shared-time initialization, control, and readback."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, cast

from raes_backend_protocols.protocols import CoordinatedParticipantTimeRuntime
from raes_contracts.contracts.time_model import TimeRuntimeStateModel, validate_time_runtime_state
from raes_contracts.runtime_state import ApplyResult
from raes_processor.compiler.time_model import time_model_contract_model

from .backend_calls import _BackendCallContext, _RealizationApplyContext
from .diagnostics import _failure_diagnostic, _has_error_diagnostic
from .interaction_time import finalize_time_result

if TYPE_CHECKING:
    from raes_processor.models import ExecutionPlan

    from .manager import _RuntimeApplyState

_APPLY_TIME_ADDRESS = "runtime.apply.time"
_TIME_READBACK_INVALID = "runtime.time-readback-invalid"


class RuntimeTimeControlMixin:
    """Shared-time portion of the runtime manager."""

    def _apply_time_phase(
        self,
        execution_plan: ExecutionPlan,
        state: _RuntimeApplyState,
    ) -> None:
        declaration = time_model_contract_model(execution_plan.model.time_model)
        if declaration is None:
            return
        if self._target.time_runtime is None:
            state.diagnostics.append(
                _failure_diagnostic(
                    "runtime.apply-missing-time-runtime",
                    _APPLY_TIME_ADDRESS,
                    "Execution plan requires shared-time control, but the target does not provide it.",
                )
            )
            self._fail_apply_state(state)
            return
        result = self._interaction_backend_call(
            self._target.time_runtime.initialize,
            declaration,
            state.working_snapshot,
            address=_APPLY_TIME_ADDRESS,
            snapshot=state.working_snapshot,
            realization=_RealizationApplyContext(
                effect_owners=frozenset({"time"}), effect_targets=frozenset(declaration.clocks)
            ),
            call=_BackendCallContext(
                information_state_context_resolver=self._information_state_context_resolver,
            ),
            result_validator=lambda result, predecessor: finalize_time_result(
                self,
                result,
                predecessor,
                declaration=declaration,
                method="initialize",
            ),
        )
        self._record_phase_result(state, result)
        if result.success:
            self._time_declaration = declaration
            return
        if not _has_error_diagnostic(result.diagnostics):
            state.diagnostics.append(
                _failure_diagnostic(
                    "runtime.apply-phase-failed",
                    _APPLY_TIME_ADDRESS,
                    "Shared-time runtime failed to initialize.",
                )
            )
        self._fail_apply_state(state)

    def read_time_state(self) -> TimeRuntimeStateModel:
        """Read and validate target-provided shared-time state."""

        lock = getattr(self, "_participant_execution_lock", None)
        if lock is not None:
            with lock:
                return self._read_time_state_locked()
        return self._read_time_state_locked()

    def _read_time_state_locked(self) -> TimeRuntimeStateModel:
        if self._target.time_runtime is None or self._time_declaration is None:
            raise ValueError("runtime manager has no initialized shared-time model")
        with self._mutation_authority.external_call():
            state = self._execution_adapter.call(
                "control",
                self._target.time_runtime.state,
                deepcopy(self._snapshot),
                timeout_ms=self._supervision.observation_ms,
            )
        validate_time_runtime_state(self._time_declaration, state)
        if state != self._snapshot.time_model_state:
            raise ValueError("time runtime readback disagrees with the runtime snapshot")
        return state

    def advance_time(self, clock_address: str, *, ticks: int, microstep: int = 0) -> ApplyResult:
        return self._apply_time_control("advance", clock_address, ticks, microstep)

    def pause_time(self, clock_address: str) -> ApplyResult:
        return self._apply_time_control("pause", clock_address)

    def resume_time(self, clock_address: str) -> ApplyResult:
        return self._apply_time_control("resume", clock_address)

    def jump_time(self, clock_address: str, *, tick: int, microstep: int = 0) -> ApplyResult:
        return self._apply_time_control("jump", clock_address, tick, microstep)

    def reset_time(self, clock_address: str, *, replay: bool = False) -> ApplyResult:
        return self._apply_time_control("reset", clock_address, replay)

    def _apply_time_control(self, method_name: str, *args: object) -> ApplyResult:
        lock = getattr(self, "_participant_execution_lock", None)
        if lock is not None:
            with lock:
                return self._apply_time_control_locked(method_name, *args)
        return self._apply_time_control_locked(method_name, *args)

    def _apply_time_control_locked(self, method_name: str, *args: object) -> ApplyResult:
        if self._target.time_runtime is None or self._time_declaration is None:
            raise ValueError("runtime manager has no initialized shared-time model")
        preflight_failure = self._time_control_preflight(method_name, args)
        if preflight_failure is not None:
            return preflight_failure
        invocation = self._time_control_invocation(method_name, args)
        if isinstance(invocation, ApplyResult):
            return invocation
        method, method_args, authority = invocation
        result = self._interaction_backend_call(
            method,
            *method_args,
            address=f"runtime.time.{method_name}",
            snapshot=self._snapshot,
            realization=authority,
            call=_BackendCallContext(
                information_state_context_resolver=self._information_state_context_resolver,
                service_dependencies=(self._target.participant_runtime,),
            ),
            result_validator=lambda result, predecessor: finalize_time_result(
                self,
                result,
                predecessor,
                declaration=self._time_declaration,
                method=method_name,
                clock_address=str(args[0]),
            ),
        )
        if result.success:
            result = self._synchronize_participant_clock(method_name, args, result)
        return result

    def _time_control_preflight(
        self,
        method_name: str,
        args: tuple[object, ...],
    ) -> ApplyResult | None:
        participant_preflight = getattr(self, "_participant_execution_clock_preflight", None)
        if participant_preflight is not None:
            return participant_preflight(method_name, args)
        return None

    def _time_control_invocation(
        self,
        method_name: str,
        args: tuple[object, ...],
    ) -> tuple[object, tuple[object, ...], _RealizationApplyContext] | ApplyResult:
        method = getattr(self._target.time_runtime, method_name)
        method_args = (*args, self._snapshot)
        if method_name != "reset":
            return (
                method,
                method_args,
                _RealizationApplyContext(effect_owners=frozenset({"time"}), effect_targets=frozenset({str(args[0])})),
            )
        return self._coordinated_reset_invocation(method, method_args, args)

    def _coordinated_reset_invocation(
        self,
        default_method: object,
        default_args: tuple[object, ...],
        args: tuple[object, ...],
    ) -> tuple[object, tuple[object, ...], _RealizationApplyContext] | ApplyResult:
        reset_requests_factory = getattr(self, "_participant_execution_clock_reset_requests", None)
        reset_requests = reset_requests_factory(str(args[0])) if reset_requests_factory is not None else ()
        if not reset_requests:
            return (
                default_method,
                default_args,
                _RealizationApplyContext(effect_owners=frozenset({"time"}), effect_targets=frozenset({str(args[0])})),
            )
        capability = self._target.manifest.time
        if (
            capability is None
            or not capability.supports_coordinated_participant_reset
            or self._target.participant_runtime is None
        ):
            return ApplyResult(
                success=False,
                snapshot=self._snapshot,
                diagnostics=[
                    _failure_diagnostic(
                        "runtime.coordinated-participant-reset-unsupported",
                        "runtime.time.reset",
                        "Autonomous clock reset requires one atomic time and participant reset operation.",
                    )
                ],
            )
        coordinated_time_runtime = cast(
            CoordinatedParticipantTimeRuntime,
            self._target.time_runtime,
        )
        return (
            coordinated_time_runtime.reset_with_participants,
            (str(args[0]), bool(args[1]), self._target.participant_runtime, reset_requests, self._snapshot),
            _RealizationApplyContext(
                effect_owners=frozenset({"time", "participant"}),
                effect_targets=frozenset({str(args[0]), *(request.participant_address for request in reset_requests)}),
            ),
        )

    def _synchronize_participant_clock(
        self,
        method_name: str,
        args: tuple[object, ...],
        result: ApplyResult,
    ) -> ApplyResult:
        sync = getattr(self, "_sync_participant_execution_clock", None)
        sync_result = sync(method_name, str(args[0])) if sync is not None else None
        if sync_result is not None and not sync_result.success:
            return ApplyResult(
                success=False,
                snapshot=sync_result.snapshot,
                diagnostics=[*result.diagnostics, *sync_result.diagnostics],
                changed_addresses=list(dict.fromkeys([*result.changed_addresses, *sync_result.changed_addresses])),
            )
        return ApplyResult(
            success=True,
            snapshot=self._snapshot,
            diagnostics=[
                *result.diagnostics,
                *(sync_result.diagnostics if sync_result is not None else ()),
            ],
            changed_addresses=list(
                dict.fromkeys(
                    [
                        *result.changed_addresses,
                        *(sync_result.changed_addresses if sync_result is not None else ()),
                    ]
                )
            ),
        )
