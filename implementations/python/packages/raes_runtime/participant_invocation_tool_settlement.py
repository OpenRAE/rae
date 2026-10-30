"""Scheduler integration for tool actions hosted by autonomous invocations (issue #1740).

The scheduler opens one port before it dispatches an outer invocation, closes
it before the outer result is validated, and commits every settled tool action
at the end of the due pass. Commit runs on every terminal path, so accepted
tool history survives an invalid, raised or cancelled outer invocation.
"""

from __future__ import annotations

from asyncio import CancelledError
from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING, Protocol

from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import OperationalError
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.participant_binding_events import participant_behavior_event_payload
from raes_contracts.participant_tool_actions import (
    ParticipantToolActionRecord,
    ParticipantToolActionSettlement,
    participant_tool_action_events,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .participant_invocation_tool_actions import InvocationToolActionConfiguration, ParticipantInvocationToolActions

if TYPE_CHECKING:
    from raes_processor.models import ParticipantAutonomousExecutionRuntime

    from .participant_scheduler_types import SchedulerRunState

_LOGGER = get_logger(__name__)


class HostedInvocationContext(Protocol):
    """Scheduler coordinates of one due participant invocation."""

    @property
    def policy(self) -> ParticipantAutonomousExecutionRuntime: ...

    @property
    def participant_runtime(self) -> object: ...

    @property
    def participant_address(self) -> str: ...

    @property
    def key(self) -> str: ...


_ATTACH_FAILED = "backend invocation tool-action attachment did not complete"
_INDETERMINATE_OUTER = object()


def open_invocation_tool_session(
    context: HostedInvocationContext,
    request: ParticipantActionAdmissionRequest,
    *,
    episode_id: str,
    predecessor: RuntimeSnapshot,
    run: SchedulerRunState,
) -> ParticipantInvocationToolActions | None:
    """Open and attach the port for one outer invocation, or return ``None`` without a claim.

    Raise ``OperationalError`` when the backend attachment fails; no dispatch has occurred.
    """

    configuration = run.invocation_tools
    hosts_tools = configuration is not None and any(
        context.participant_address in binding.participant_addresses
        for binding in context.policy.invocation_tool_bindings
    )
    if not hosts_tools:
        return None
    session = ParticipantInvocationToolActions(
        outer=request,
        episode_id=episode_id,
        policy=context.policy,
        configuration=configuration,
        scheduler_state_key=context.key,
        prior_history_length=len(predecessor.participant_behavior_history.get(context.participant_address, ())),
    )
    # Register cleanup ownership before backend code runs; the port stays inactive until dispatch.
    run.tool_sessions.append(session)
    try:
        context.participant_runtime.attach_invocation_tool_actions(session)
    except CancelledError:
        # Cleanup: close the inactive port, then propagate the cancellation (ADR-116 H4).
        session.close()
        raise
    # Isolation: the attach method is backend code that RAES does not own; log only RAES frames.
    except Exception as exc:
        _LOGGER.exception("backend invocation tool-action attachment failed", exc_info=foreign_failure_record(exc))
        session.close()
    else:
        return session
    # Raised after the handler, so the failure carries no backend exception as its context.
    raise OperationalError(_ATTACH_FAILED)


def invocation_effects_fenced(run: SchedulerRunState) -> bool:
    """Return whether a hosted action in this pass has unknown native effects."""

    return any(session.has_unresolved_effects for session in run.tool_sessions)


def fence_outer_dispatch(run: SchedulerRunState, address: str) -> bool:
    """Refuse a new outer dispatch, before it starts, once hosted effects are unknown."""

    if not invocation_effects_fenced(run):
        return False
    run.diagnostics.append(
        Diagnostic(
            code="runtime.participant-invocation-tool-effects-fenced",
            domain="participant",
            address=address,
            message="A hosted tool action has unknown native effects; no further invocation is dispatched.",
        )
    )
    run.failure = ApplyResult(
        success=False,
        snapshot=run.working,
        diagnostics=run.diagnostics,
        changed_addresses=list(dict.fromkeys(run.changed)),
    )
    return True


def open_serial_invocation_tool_session(
    context: HostedInvocationContext,
    request: ParticipantActionAdmissionRequest,
    *,
    episode_id: str,
    run: SchedulerRunState,
) -> tuple[bool, ParticipantInvocationToolActions | None]:
    """Open the port on the serial path; report a fence or attachment failure as a run failure."""

    if fence_outer_dispatch(run, context.participant_address):
        return False, None
    try:
        return True, open_invocation_tool_session(
            context, request, episode_id=episode_id, predecessor=run.working, run=run
        )
    except OperationalError:
        run.diagnostics.append(
            Diagnostic(
                code="runtime.participant-invocation-tool-attach-failed",
                domain="participant",
                address=context.participant_address,
                message="Backend invocation tool-action attachment did not complete before dispatch.",
            )
        )
        run.failure = ApplyResult(success=False, snapshot=run.working, diagnostics=run.diagnostics)
        return False, None


def admit_outer_action(
    context: HostedInvocationContext,
    request: ParticipantActionAdmissionRequest,
    predecessor: RuntimeSnapshot,
    session: ParticipantInvocationToolActions | None,
    run: SchedulerRunState,
) -> object:
    """Dispatch one outer invocation; with a port, a raised call becomes indeterminate work."""

    if session is None:
        return deepcopy(context.participant_runtime.admit_action(deepcopy(request), deepcopy(predecessor)))
    session.activate()
    try:
        return deepcopy(context.participant_runtime.admit_action(deepcopy(request), deepcopy(predecessor)))
    except CancelledError as exc:
        # Cleanup: settle the outer attempt and its tool actions first; run_due raises it again (ADR-116 H4).
        run.deferred_cancellation = exc
    # Isolation: admit_action is backend code that RAES does not own; log only RAES frames.
    except Exception as exc:
        _LOGGER.exception("backend autonomous invocation failed after dispatch", exc_info=foreign_failure_record(exc))
    finally:
        session.close()
    run.diagnostics.append(
        Diagnostic(
            code="runtime.participant-invocation-indeterminate",
            domain="participant",
            address=context.participant_address,
            message="Autonomous invocation did not return a result after dispatch; its native effects are unknown.",
        )
    )
    return _INDETERMINATE_OUTER


def activate_invocation_tool_sessions(sessions: tuple[ParticipantInvocationToolActions, ...]) -> None:
    for session in sessions:
        session.activate()


def close_invocation_tool_sessions(sessions: tuple[ParticipantInvocationToolActions, ...]) -> None:
    for session in sessions:
        session.close()


def settle_invocation_tool_sessions(run: SchedulerRunState) -> None:
    """Commit the settled tool actions of every port opened in this pass."""

    sessions, run.tool_sessions = tuple(run.tool_sessions), []
    changed_before = len(run.changed)
    for session in sessions:
        records = session.close()
        if records:
            _commit_session(run, session, records)
        if session.ledger_failures:
            _record_failure(
                run,
                Diagnostic(
                    code="runtime.participant-invocation-tool-ledger-failed",
                    domain="participant",
                    address=session.participant_address,
                    message="The store did not retain a hosted tool-action settlement; recovery classifies the record.",
                ),
                lambda snapshot: snapshot,
            )
    failure = run.failure
    if failure is not None and len(run.changed) > changed_before:
        changed = [*failure.changed_addresses, *run.changed[changed_before:]]
        run.failure = replace(failure, changed_addresses=list(dict.fromkeys(changed)))


def _commit_session(
    run: SchedulerRunState,
    session: ParticipantInvocationToolActions,
    records: tuple[ParticipantToolActionRecord, ...],
) -> None:
    stale = _stale_settlement_diagnostic(session, run.working)
    if stale is not None:
        _record_failure(run, stale, lambda snapshot: snapshot)
        return
    indeterminate = any(record.settlement is ParticipantToolActionSettlement.INDETERMINATE for record in records)

    def commit(snapshot: RuntimeSnapshot) -> RuntimeSnapshot:
        committed = _with_tool_history(snapshot, session, records)
        return _with_failed_scheduler(committed, session.scheduler_state_key) if indeterminate else committed

    if indeterminate:
        _record_failure(
            run,
            Diagnostic(
                code="runtime.participant-invocation-tool-action-indeterminate",
                domain="participant",
                address=session.participant_address,
                message="A hosted tool action has unknown native effects; the participant scheduler stopped.",
            ),
            commit,
        )
    else:
        _apply_to_run(run, commit)
    run.changed.extend([session.participant_address, *([session.scheduler_state_key] if indeterminate else [])])


def _stale_settlement_diagnostic(
    session: ParticipantInvocationToolActions,
    snapshot: RuntimeSnapshot,
) -> Diagnostic | None:
    live = snapshot.participant_episode_results.get(session.participant_address) or {}
    payload = snapshot.participant_execution_services.get(session.execution_scope_ref)
    service = None if payload is None else ParticipantExecutionServiceStateModel.model_validate(payload)
    generation = session.execution_generation
    current_generation = service is not None and (service.generation, service.observed_generation) == (
        generation,
        generation,
    )
    if current_generation and live.get("episode_id") == session.episode_id:
        return None
    return Diagnostic(
        code="runtime.participant-invocation-tool-settlement-stale",
        domain="participant",
        address=session.participant_address,
        message="Hosted tool actions were not committed because the episode or execution generation changed.",
    )


def _with_tool_history(
    snapshot: RuntimeSnapshot,
    session: ParticipantInvocationToolActions,
    records: tuple[ParticipantToolActionRecord, ...],
) -> RuntimeSnapshot:
    events = [
        participant_behavior_event_payload(event)
        for record in records
        for event in participant_tool_action_events(session.outer, record)
    ]
    history = {address: list(entries) for address, entries in snapshot.participant_behavior_history.items()}
    current = history.get(session.participant_address, [])
    position = next(
        (
            index
            for index in range(session.prior_history_length, len(current))
            if current[index].get("action_instance_id") == session.invocation_action_instance_id
            and current[index].get("event_type") == "action_attempted"
        ),
        len(current),
    )
    history[session.participant_address] = [*current[:position], *events, *current[position:]]
    return snapshot.with_entries(dict(snapshot.entries), participant_behavior_history=history)


def _with_failed_scheduler(snapshot: RuntimeSnapshot, state_key: str) -> RuntimeSnapshot:
    states = dict(snapshot.participant_autonomous_execution_states)
    state = ParticipantAutonomousExecutionStateModel.model_validate(states[state_key])
    states[state_key] = state.model_copy(update={"lifecycle_state": "failed"}).model_dump(mode="json")
    return snapshot.with_entries(dict(snapshot.entries), participant_autonomous_execution_states=states)


def _apply_to_run(run: SchedulerRunState, change: object) -> None:
    failure = run.failure
    working = change(run.working)
    if failure is not None:
        snapshot = working if failure.snapshot is run.working else change(failure.snapshot)
        run.failure = replace(failure, snapshot=snapshot)
    run.working = working


def _record_failure(run: SchedulerRunState, diagnostic: Diagnostic, change: object) -> None:
    _apply_to_run(run, change)
    run.diagnostics.append(diagnostic)
    failure = run.failure
    if failure is None:
        run.failure = ApplyResult(
            success=False,
            snapshot=run.working,
            diagnostics=run.diagnostics,
            changed_addresses=list(dict.fromkeys(run.changed)),
        )
    elif failure.diagnostics is not run.diagnostics:
        run.failure = replace(failure, diagnostics=[*failure.diagnostics, diagnostic])


__all__ = (
    "InvocationToolActionConfiguration",
    "activate_invocation_tool_sessions",
    "admit_outer_action",
    "close_invocation_tool_sessions",
    "fence_outer_dispatch",
    "invocation_effects_fenced",
    "open_invocation_tool_session",
    "open_serial_invocation_tool_session",
    "settle_invocation_tool_sessions",
)
