"""Participant execution-service and episode lifecycle submissions."""

from __future__ import annotations

from raes_contracts.contracts.participant_execution import (
    ParticipantExecutionControlRequestModel,
    ParticipantExecutionServiceStateModel,
)
from raes_contracts.participant_episode import (
    ParticipantEpisodeInitializeRequest,
    ParticipantEpisodeResetRequest,
    ParticipantEpisodeRestartRequest,
    ParticipantEpisodeTerminalReason,
    ParticipantEpisodeTerminateRequest,
)
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import OperationKind, OperationReceipt

from .control_plane_execution import execute_participant_action
from .control_plane_lifecycle import runtime_owned, store_authoritative_state
from .control_plane_mutation import mutation_entry
from .participant_control_diagnostics import _NO_PARTICIPANT_RUNTIME_MESSAGE
from .participant_execution_control_boundary import backend_execution_control_method


class ParticipantEpisodeControlMixin:
    """Execution-service and participant-episode mutation methods."""

    @runtime_owned
    @mutation_entry(OperationKind.PARTICIPANT_ACTION)
    def control_participant_execution(
        self,
        request: ParticipantExecutionControlRequestModel,
        *,
        idempotency_key: str = "",
        request_fingerprint: str = "",
        identity: object | None = None,
    ) -> OperationReceipt:
        participant_runtime = self._target.participant_runtime
        method = getattr(participant_runtime, "control_execution", None)
        if participant_runtime is None or not callable(method):
            return self._reject_submission(
                domain=RuntimeDomain.PARTICIPANT,
                message="Participant runtime does not expose portable execution control.",
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                identity=identity,
                request=request,
            )
        return execute_participant_action(
            self,
            method=backend_execution_control_method(
                method,
                information_state_context_resolver=getattr(
                    self,
                    "_information_state_context_resolver",
                    None,
                ),
            ),
            request=request,
            address=f"runtime.control-plane.participant-execution.{request.execution_scope_ref}.{request.action}",
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            identity=identity,
        )

    @runtime_owned
    @store_authoritative_state
    def participant_execution_state(
        self,
        execution_scope_ref: str,
    ) -> ParticipantExecutionServiceStateModel:
        participant_runtime = self._target.participant_runtime
        method = getattr(participant_runtime, "execution_state", None)
        if participant_runtime is None or not callable(method):
            raise ValueError("participant runtime does not expose execution-service readback")
        return method(execution_scope_ref, self._snapshot)

    @runtime_owned
    @mutation_entry(OperationKind.PARTICIPANT_ACTION)
    def initialize_participant_episode(
        self,
        participant_address: str,
        *,
        episode_id: str | None = None,
        idempotency_key: str = "",
        request_fingerprint: str = "",
        identity: object | None = None,
    ) -> OperationReceipt:
        request = ParticipantEpisodeInitializeRequest(
            participant_address=participant_address,
            episode_id=episode_id,
        )
        return self._submit_participant_episode_operation(
            request,
            method_name="initialize",
            action="initialize",
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            identity=identity,
        )

    @runtime_owned
    @mutation_entry(OperationKind.PARTICIPANT_ACTION)
    def reset_participant_episode(
        self,
        participant_address: str,
        *,
        episode_id: str | None = None,
        reason: str = "reset by operator",
        idempotency_key: str = "",
        request_fingerprint: str = "",
        identity: object | None = None,
    ) -> OperationReceipt:
        request = ParticipantEpisodeResetRequest(
            participant_address=participant_address,
            episode_id=episode_id,
            reason=reason,
        )
        return self._submit_participant_episode_operation(
            request,
            method_name="reset",
            action="reset",
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            identity=identity,
        )

    @runtime_owned
    @mutation_entry(OperationKind.PARTICIPANT_ACTION)
    def restart_participant_episode(
        self,
        participant_address: str,
        *,
        episode_id: str | None = None,
        reason: str = "restarted by operator",
        idempotency_key: str = "",
        request_fingerprint: str = "",
        identity: object | None = None,
    ) -> OperationReceipt:
        request = ParticipantEpisodeRestartRequest(
            participant_address=participant_address,
            episode_id=episode_id,
            reason=reason,
        )
        return self._submit_participant_episode_operation(
            request,
            method_name="restart",
            action="restart",
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            identity=identity,
        )

    @runtime_owned
    @mutation_entry(OperationKind.PARTICIPANT_ACTION)
    def terminate_participant_episode(
        self,
        participant_address: str,
        *,
        terminal_reason: ParticipantEpisodeTerminalReason = ParticipantEpisodeTerminalReason.INTERRUPTED,
        detail: str = "terminated by operator",
        idempotency_key: str = "",
        request_fingerprint: str = "",
        identity: object | None = None,
    ) -> OperationReceipt:
        request = ParticipantEpisodeTerminateRequest(
            participant_address=participant_address,
            terminal_reason=terminal_reason,
            detail=detail,
        )
        return self._submit_participant_episode_operation(
            request,
            method_name="terminate",
            action="terminate",
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            identity=identity,
        )

    def _submit_participant_episode_operation(
        self,
        request: (
            ParticipantEpisodeInitializeRequest
            | ParticipantEpisodeResetRequest
            | ParticipantEpisodeRestartRequest
            | ParticipantEpisodeTerminateRequest
        ),
        *,
        method_name: str,
        action: str,
        idempotency_key: str,
        request_fingerprint: str,
        identity: object | None,
    ) -> OperationReceipt:
        participant_runtime = self._target.participant_runtime
        if participant_runtime is None:
            return self._reject_submission(
                domain=RuntimeDomain.PARTICIPANT,
                message=_NO_PARTICIPANT_RUNTIME_MESSAGE,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                identity=identity,
                request=request,
            )
        participant_address = request.participant_address
        return execute_participant_action(
            self,
            method=getattr(participant_runtime, method_name),
            request=request,
            address=f"runtime.control-plane.participant.{participant_address}.{action}",
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            identity=identity,
        )


__all__ = ("ParticipantEpisodeControlMixin",)
