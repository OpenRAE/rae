"""Portable execution-service behavior shared by participant runtimes."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from raes_contracts.contracts.participant_action_admission import ParticipantActionAdmissionRequest
from raes_contracts.contracts.participant_execution import (
    ParticipantExecutionServiceStateModel,
)
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.participant_binding import ParticipantActionApplyResult
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .participant_action_commit import reject_participant_action_outcome
from .participant_execution_service import participant_execution_state

_LOGGER = get_logger(__name__)


class ParticipantExecutionRuntimeMixin:
    """Generation fencing, lifecycle readback, and bounded native dispatch."""

    @staticmethod
    def execution_state(
        execution_scope_ref: str,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantExecutionServiceStateModel:
        """Return typed health/readiness and lifecycle readback."""

        return participant_execution_state(execution_scope_ref, snapshot)

    @staticmethod
    def _execution_generation_changed(
        state: ParticipantExecutionServiceStateModel,
        request: ParticipantActionAdmissionRequest,
    ) -> bool:
        return (
            state.generation != request.execution_generation
            or state.observed_generation != request.execution_generation
        )

    @staticmethod
    def _execution_service_accepts_work(state: ParticipantExecutionServiceStateModel) -> bool:
        return state.observed_lifecycle == "running" and state.accepting_new_work and state.readiness == "ready"

    @staticmethod
    def _execution_generation_failure_reason(
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        completion: bool,
    ) -> str | None:
        scope = request.execution_scope_ref
        payload = snapshot.participant_execution_services.get(scope) if scope is not None else None
        reason = "execution-service state is missing" if payload is None else None
        if payload is not None:
            state = ParticipantExecutionServiceStateModel.model_validate(payload)
            if ParticipantExecutionRuntimeMixin._execution_generation_changed(state, request):
                reason = "execution generation changed"
            if (
                reason is None
                and not completion
                and not ParticipantExecutionRuntimeMixin._execution_service_accepts_work(state)
            ):
                reason = "execution service is not accepting work"
        return reason

    @staticmethod
    def _execution_generation_failure(
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        completion: bool,
        predecessor: RuntimeSnapshot | None = None,
    ) -> ParticipantActionApplyResult | None:
        if request.execution_scope_ref is None:
            return None
        reason = ParticipantExecutionRuntimeMixin._execution_generation_failure_reason(
            request,
            snapshot,
            completion=completion,
        )
        if reason is None:
            return None
        phase = "completion" if completion else "work"
        original = predecessor or snapshot
        return reject_participant_action_outcome(
            original,
            ApplyResult(success=False, snapshot=snapshot),
            request.participant_address,
            f"runtime.participant-execution-stale-{phase}",
            (f"Participant action {phase} was rejected because its generation-bound {reason}."),
        )

    def admit_actions_concurrently(
        self,
        requests: tuple[ParticipantActionAdmissionRequest, ...],
        snapshot: RuntimeSnapshot,
        max_workers: int,
    ) -> tuple[ParticipantActionApplyResult, ...]:
        """Execute independent native actions with a finite worker bound.

        Each call receives the same immutable predecessor. The scheduler owns
        revision-checked serialized merge and scheduler-state commit.
        """

        if max_workers < 2:
            raise ValueError("concurrent participant execution requires at least two workers")
        if len(requests) > max_workers:
            raise ValueError("participant action batch exceeds its worker bound")
        # RuntimeSnapshot is a mutable carrier even though workers are required
        # to treat their predecessor as immutable.  Give each native call an
        # independently owned copy so an in-place adapter bug cannot race with
        # or contaminate a peer's input.
        predecessors = tuple(deepcopy(snapshot) for _request in requests)
        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="raes-participant",
        ) as executor:
            futures = [
                executor.submit(self.admit_action, request, predecessor)
                for request, predecessor in zip(requests, predecessors, strict=True)
            ]
            failures = [error for error in (future.exception() for future in futures) if error is not None]
        # The first failure propagates unchanged; each later failure would otherwise be lost. A
        # participant runtime can be backend code, so the record omits foreign content.
        for failure in failures[1:]:
            _LOGGER.warning(
                "participant action failed after an earlier failure in its batch",
                exc_info=foreign_failure_record(failure),
            )
        if failures:
            raise failures[0]
        return tuple(future.result() for future in futures)
