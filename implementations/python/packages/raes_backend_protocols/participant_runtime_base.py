"""Shared participant episode lifecycle base for RAES backends.

Provides ``BaseParticipantRuntime``, which implements the complete RUN-311
episode state machine. Backend-specific runtimes subclass this and override
``_model_action`` to inject domain side-effects (e.g. native virtual-machine
calls) before behavior history events are recorded.
"""

from __future__ import annotations

from dataclasses import replace

from raes_contracts.contracts.participant_action_admission import ParticipantActionAdmissionRequest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_binding import (
    ParticipantActionApplyResult,
    ParticipantNativeActionExecution,
    participant_action_binding_events,
    participant_behavior_event_payload,
)
from raes_contracts.participant_episode import (
    ParticipantEpisodeControlAction,
    ParticipantEpisodeExecutionState,
    ParticipantEpisodeHistoryEvent,
    ParticipantEpisodeHistoryEventType,
    ParticipantEpisodeInitializeRequest,
    ParticipantEpisodeResetRequest,
    ParticipantEpisodeRestartRequest,
    ParticipantEpisodeStatus,
    ParticipantEpisodeTerminalReason,
    ParticipantEpisodeTerminateRequest,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_contracts.timestamps import WallClock, isoformat_z, utc_now

from .participant_action_commit import (
    as_participant_action_result,
    participant_binding_post_state_digest,
    reject_participant_action_outcome,
)
from .participant_execution_runtime import ParticipantExecutionRuntimeMixin
from .participant_reset import reset_many_atomically

_EMPTY_ADDRESS_MSG = "participant_address must be non-empty"

_TERMINAL_EVENT_FOR_REASON: dict[ParticipantEpisodeTerminalReason, ParticipantEpisodeHistoryEventType] = {
    ParticipantEpisodeTerminalReason.COMPLETED: ParticipantEpisodeHistoryEventType.EPISODE_COMPLETED,
    ParticipantEpisodeTerminalReason.TIMED_OUT: ParticipantEpisodeHistoryEventType.EPISODE_TIMED_OUT,
    ParticipantEpisodeTerminalReason.TRUNCATED: ParticipantEpisodeHistoryEventType.EPISODE_TRUNCATED,
    ParticipantEpisodeTerminalReason.INTERRUPTED: ParticipantEpisodeHistoryEventType.EPISODE_INTERRUPTED,
}


class BaseParticipantRuntime(ParticipantExecutionRuntimeMixin):
    """Shared RUN-311 episode lifecycle base for RAES participant runtimes.

    Implements the full episode state machine (initialize, reset, restart,
    terminate, admit_action) using the RUN-311 invariants that
    ``iter_participant_episode_snapshot_violations`` enforces. Subclasses that
    need to inject domain side-effects before behavior history events are
    recorded override ``_model_action``.

    This class is backend-neutral; the concrete driver connection, native
    domain calls, or any other infrastructure concerns belong in subclasses.
    """

    def __init__(self, *, wall_clock: WallClock = utc_now) -> None:
        self._wall_clock = wall_clock
        self._results: dict[str, dict[str, object]] = {}
        self._history: dict[str, list[dict[str, object]]] = {}
        self._episode_counter: dict[str, int] = {}

    def initialize(
        self,
        request: ParticipantEpisodeInitializeRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        address = request.participant_address
        if not address:
            return self._reject(snapshot, _EMPTY_ADDRESS_MSG, address)
        if address in snapshot.participant_episode_results:
            return self._reject(
                snapshot,
                f"participant {address!r} already has a live episode; use reset or restart",
                address,
            )
        now = isoformat_z(self._wall_clock())
        episode_id = request.episode_id or self._allocate_episode_id(address)
        state = ParticipantEpisodeExecutionState(
            participant_address=address,
            episode_id=episode_id,
            sequence_number=0,
            status=ParticipantEpisodeStatus.RUNNING,
            initialized_at=now,
            updated_at=now,
            last_control_action=ParticipantEpisodeControlAction.INITIALIZE,
        )
        events = [
            ParticipantEpisodeHistoryEvent(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_INITIALIZED,
                timestamp=now,
                participant_address=address,
                episode_id=episode_id,
                sequence_number=0,
                control_action=ParticipantEpisodeControlAction.INITIALIZE,
            ),
            ParticipantEpisodeHistoryEvent(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_RUNNING,
                timestamp=now,
                participant_address=address,
                episode_id=episode_id,
                sequence_number=0,
            ),
        ]
        return self._apply(snapshot, address, state, events, replace_history=True)

    def reset(
        self,
        request: ParticipantEpisodeResetRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        return self._new_episode(
            request,
            snapshot,
            control_action=ParticipantEpisodeControlAction.RESET,
            reset_event=ParticipantEpisodeHistoryEventType.EPISODE_RESET,
            require_terminated=False,
            no_episode_message="cannot reset participant {address!r}: no live episode",
            wrong_state_message="cannot reset terminated participant {address!r}; use restart",
        )

    def reset_many(
        self,
        requests: tuple[ParticipantEpisodeResetRequest, ...],
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Atomically reset a batch for the in-memory reference implementation."""

        if type(self).reset is not BaseParticipantRuntime.reset:
            return self._reject(
                snapshot,
                "participant runtimes with native reset behavior must implement their own atomic reset_many",
                "",
            )
        return reset_many_atomically(self, requests, snapshot)

    def restart(
        self,
        request: ParticipantEpisodeRestartRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        return self._new_episode(
            request,
            snapshot,
            control_action=ParticipantEpisodeControlAction.RESTART,
            reset_event=ParticipantEpisodeHistoryEventType.EPISODE_RESTARTED,
            require_terminated=True,
            no_episode_message="cannot restart participant {address!r}: no live episode",
            wrong_state_message="cannot restart non-terminated participant {address!r}; use reset",
        )

    def _new_episode(
        self,
        request: ParticipantEpisodeResetRequest | ParticipantEpisodeRestartRequest,
        snapshot: RuntimeSnapshot,
        *,
        control_action: ParticipantEpisodeControlAction,
        reset_event: ParticipantEpisodeHistoryEventType,
        require_terminated: bool,
        no_episode_message: str,
        wrong_state_message: str,
    ) -> ApplyResult:
        address = request.participant_address
        current_state = self._live_predecessor(snapshot, address, no_episode_message)
        if isinstance(current_state, ApplyResult):
            return current_state
        if (current_state.status == ParticipantEpisodeStatus.TERMINATED) != require_terminated:
            return self._reject(snapshot, wrong_state_message.format(address=address), address)
        now = isoformat_z(self._wall_clock())
        new_episode_id = request.episode_id or self._allocate_episode_id(address)
        new_sequence = current_state.sequence_number + 1
        new_state = ParticipantEpisodeExecutionState(
            participant_address=address,
            episode_id=new_episode_id,
            sequence_number=new_sequence,
            status=ParticipantEpisodeStatus.RUNNING,
            initialized_at=now,
            updated_at=now,
            last_control_action=control_action,
            previous_episode_id=current_state.episode_id,
        )
        events = [
            ParticipantEpisodeHistoryEvent(
                event_type=reset_event,
                timestamp=now,
                participant_address=address,
                episode_id=new_episode_id,
                sequence_number=new_sequence,
                control_action=control_action,
                details={
                    "previous_episode_id": current_state.episode_id,
                    "reason": request.reason,
                },
            ),
            ParticipantEpisodeHistoryEvent(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_RUNNING,
                timestamp=now,
                participant_address=address,
                episode_id=new_episode_id,
                sequence_number=new_sequence,
            ),
        ]
        return self._apply(snapshot, address, new_state, events, replace_history=False)

    def terminate(
        self,
        request: ParticipantEpisodeTerminateRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        address = request.participant_address
        current_state = self._live_predecessor(
            snapshot, address, "cannot terminate participant {address!r}: no live episode"
        )
        if isinstance(current_state, ApplyResult):
            return current_state
        if current_state.status == ParticipantEpisodeStatus.TERMINATED:
            return self._reject(snapshot, f"participant {address!r} is already terminated", address)
        now = isoformat_z(self._wall_clock())
        terminal_reason = request.terminal_reason
        new_state = ParticipantEpisodeExecutionState(
            participant_address=address,
            episode_id=current_state.episode_id,
            sequence_number=current_state.sequence_number,
            status=ParticipantEpisodeStatus.TERMINATED,
            terminal_reason=terminal_reason,
            initialized_at=current_state.initialized_at,
            updated_at=now,
            terminated_at=now,
            last_control_action=current_state.last_control_action,
            previous_episode_id=current_state.previous_episode_id,
        )
        events = [
            ParticipantEpisodeHistoryEvent(
                event_type=_TERMINAL_EVENT_FOR_REASON[terminal_reason],
                timestamp=now,
                participant_address=address,
                episode_id=current_state.episode_id,
                sequence_number=current_state.sequence_number,
                terminal_reason=terminal_reason,
                details={"detail": request.detail},
            ),
        ]
        return self._apply(snapshot, address, new_state, events, replace_history=False)

    def admit_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantActionApplyResult:
        address = request.participant_address
        predecessor = self._live_predecessor(
            snapshot,
            address,
            "cannot admit participant action for {address!r}: no live episode",
        )
        failure = self._action_precondition_failure(predecessor, snapshot, address)
        if failure is None:
            failure = self._execution_generation_failure(
                request,
                snapshot,
                completion=False,
            )
        native = None
        if failure is None:
            current_state = predecessor
            native = self._model_action(request, snapshot, episode_id=current_state.episode_id)
            failure = self._native_action_failure(
                request,
                native,
                current_state,
                snapshot,
            )
        if failure is not None:
            return failure
        assert native is not None
        modeled = native.apply_result
        try:
            request = replace(
                request,
                action_result=native.action_result,
                post_state_digest=native.post_state_digest or request.post_state_digest,
            )
        except TypeError, ValueError:
            # The validation text can repeat native outcome values; the diagnostic stays value-free (E7).
            return reject_participant_action_outcome(
                snapshot,
                modeled,
                address,
                "runtime.participant-autonomous-native-outcome-mismatch",
                "Native action outcome contradicts its autonomous binding.",
            )
        working_snapshot = modeled.snapshot
        now = isoformat_z(self._wall_clock())
        post_state_digest = request.post_state_digest or participant_binding_post_state_digest(request)
        events = participant_action_binding_events(
            request,
            episode_id=current_state.episode_id,
            timestamp=now,
            post_state_digest=post_state_digest,
        )
        behavior_history = {
            participant_address: list(events)
            for participant_address, events in working_snapshot.participant_behavior_history.items()
        }
        behavior_history.setdefault(address, [])
        behavior_history[address].extend(participant_behavior_event_payload(event) for event in events)
        return ParticipantActionApplyResult(
            success=True,
            snapshot=working_snapshot.with_entries(
                dict(working_snapshot.entries),
                participant_behavior_history=behavior_history,
            ),
            diagnostics=list(modeled.diagnostics),
            changed_addresses=list(dict.fromkeys([*modeled.changed_addresses, address])),
            details=dict(modeled.details),
            action_result=native.action_result,
        )

    def _action_precondition_failure(
        self,
        predecessor: ParticipantEpisodeExecutionState | ApplyResult,
        snapshot: RuntimeSnapshot,
        address: str,
    ) -> ParticipantActionApplyResult | None:
        if isinstance(predecessor, ApplyResult):
            return as_participant_action_result(predecessor)
        if predecessor.status == ParticipantEpisodeStatus.TERMINATED:
            rejected = self._reject(
                snapshot,
                f"cannot admit participant action for terminated participant {address!r}",
                address,
            )
            return as_participant_action_result(rejected)
        return None

    def _native_action_failure(
        self,
        request: ParticipantActionAdmissionRequest,
        native: ParticipantNativeActionExecution,
        current_state: ParticipantEpisodeExecutionState,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantActionApplyResult | None:
        modeled = native.apply_result
        failure = None
        if not modeled.success:
            failure = ParticipantActionApplyResult(
                success=False,
                snapshot=modeled.snapshot,
                diagnostics=list(modeled.diagnostics),
                changed_addresses=list(modeled.changed_addresses),
                details=dict(modeled.details),
                action_result=native.action_result,
            )
        elif native.action_result is not None and native.action_result.episode_id != current_state.episode_id:
            rejected = self._reject(
                snapshot,
                "native action result episode_id must match the live participant episode",
                request.participant_address,
            )
            failure = as_participant_action_result(rejected)
        elif request.requires_terminal_outcome and native.action_result is None:
            failure = reject_participant_action_outcome(
                snapshot,
                modeled,
                request.participant_address,
                "runtime.participant-autonomous-native-outcome-missing",
                "Autonomous native execution did not publish a typed action outcome.",
            )
        terminal_statuses = {"succeeded", "failed", "partial_success", "rejected", "withheld"}
        if (
            request.requires_terminal_outcome
            and native.action_result is not None
            and native.action_result.status not in terminal_statuses
        ):
            failure = reject_participant_action_outcome(
                snapshot,
                modeled,
                request.participant_address,
                "runtime.participant-autonomous-native-outcome-nonterminal",
                "Autonomous native execution must publish a terminal typed action outcome.",
            )
        return failure

    @staticmethod
    def _model_action(
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
    ) -> ParticipantNativeActionExecution:
        """Execute one native participant action before portable history is committed.

        Backend participant runtimes override this method to call their product
        or service adapter. The default reference behavior is an explicit
        no-op used only by the in-tree conformance implementations.
        """

        del episode_id
        return ParticipantNativeActionExecution(
            apply_result=ApplyResult(success=True, snapshot=snapshot),
            action_result=request.action_result,
            post_state_digest=request.post_state_digest,
        )

    def status(self) -> dict[str, object]:
        return {
            "participants": len(self._results),
            "running": sum(1 for result in self._results.values() if result.get("status") == "running"),
        }

    def results(self) -> dict[str, dict[str, object]]:
        return {address: dict(result) for address, result in self._results.items()}

    def history(self) -> dict[str, list[dict[str, object]]]:
        return {address: list(events) for address, events in self._history.items()}

    def _live_predecessor(
        self,
        snapshot: RuntimeSnapshot,
        address: str,
        no_episode_message: str,
    ) -> ParticipantEpisodeExecutionState | ApplyResult:
        """Resolve the participant's current episode state, or return an error result.

        Collapses the empty-address, no-live-episode, and invalid-payload guards
        into a single resolver so each caller has one error-return path plus its
        own state-specific check.
        """
        current = snapshot.participant_episode_results.get(address) if address else None
        if current is None:
            message = _EMPTY_ADDRESS_MSG if not address else no_episode_message.format(address=address)
            return self._reject(snapshot, message, address)
        try:
            return ParticipantEpisodeExecutionState.from_payload(current)
        except TypeError, ValueError:
            # The validation text can repeat stored state values; the diagnostic stays value-free (E7).
            return self._reject(snapshot, "current state is invalid", address)

    def _apply(
        self,
        snapshot: RuntimeSnapshot,
        address: str,
        state: ParticipantEpisodeExecutionState,
        new_events: list[ParticipantEpisodeHistoryEvent],
        *,
        replace_history: bool,
    ) -> ApplyResult:
        results = {addr: dict(result) for addr, result in snapshot.participant_episode_results.items()}
        history = {addr: list(events) for addr, events in snapshot.participant_episode_history.items()}
        results[address] = state.to_payload()
        if replace_history:
            history[address] = [event.to_payload() for event in new_events]
        else:
            history.setdefault(address, [])
            history[address].extend(event.to_payload() for event in new_events)
        self._results = results
        self._history = history
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                dict(snapshot.entries),
                participant_episode_results=results,
                participant_episode_history=history,
            ),
            changed_addresses=[address],
        )

    @staticmethod
    def _reject(snapshot: RuntimeSnapshot, message: str, address: str) -> ApplyResult:
        diagnostic = Diagnostic(
            code="runtime.participant-runtime.rejected",
            domain="runtime",
            address=address or "runtime.participant-runtime",
            message=message,
        )
        return ApplyResult(success=False, snapshot=snapshot, diagnostics=[diagnostic])

    def _allocate_episode_id(self, address: str) -> str:
        next_index = self._episode_counter.get(address, 0) + 1
        self._episode_counter[address] = next_index
        return f"{address}-episode-{next_index}"
