"""Shared record of a rejected portable attempt that was never dispatched natively."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime

from raes_backend_protocols.participant_action_commit import participant_binding_post_state_digest
from raes_contracts.contracts import ParticipantActionResultModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_behavior import ParticipantAdmissionDisposition
from raes_contracts.participant_binding import (
    ParticipantActionAdmissionRequest,
    ParticipantActionApplyResult,
    participant_action_binding_events,
    participant_behavior_event_payload,
)
from raes_contracts.runtime_state import RuntimeSnapshot


def rejected_attempt_result(
    request: ParticipantActionAdmissionRequest,
    snapshot: RuntimeSnapshot,
    action_result: ParticipantActionResultModel,
    *,
    transition_kind: str,
    diagnostics: list[Diagnostic],
    terminal_update: Mapping[str, object] | None = None,
) -> ParticipantActionApplyResult:
    """Append the ordered rejected-attempt history without calling the native runtime."""

    events = list(
        participant_action_binding_events(
            replace(request, action_result=action_result, state_transition_kind=transition_kind),
            episode_id=action_result.episode_id,
            timestamp=datetime.now(UTC).isoformat(),
            post_state_digest=participant_binding_post_state_digest(request),
        )
    )
    events[0] = events[0].model_copy(update={"admission_disposition": ParticipantAdmissionDisposition.REJECTED})
    if terminal_update:
        events[-1] = events[-1].model_copy(update=dict(terminal_update))
    histories = dict(snapshot.participant_behavior_history)
    histories[request.participant_address] = [
        *histories.get(request.participant_address, ()),
        *(participant_behavior_event_payload(event) for event in events),
    ]
    return ParticipantActionApplyResult(
        success=False,
        snapshot=snapshot.with_entries(dict(snapshot.entries), participant_behavior_history=histories),
        action_result=action_result,
        diagnostics=list(diagnostics),
        changed_addresses=[request.participant_address],
    )


__all__ = ("rejected_attempt_result",)
