"""Typed participant execution-service readback."""

from __future__ import annotations

from pydantic import ValidationError
from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel
from raes_contracts.errors import EvidenceIntegrityError, NotFoundError
from raes_contracts.runtime_state import RuntimeSnapshot


def participant_execution_state(
    execution_scope_ref: str,
    snapshot: RuntimeSnapshot,
) -> ParticipantExecutionServiceStateModel:
    """Read backend-observed state without synthesizing lifecycle success.

    Raise ``NotFoundError`` when the snapshot does not configure the scope, and
    ``EvidenceIntegrityError`` when the stored state does not satisfy its contract.
    """

    payload = snapshot.participant_execution_services.get(execution_scope_ref)
    if payload is None:
        raise NotFoundError("participant execution scope is not configured")
    try:
        return ParticipantExecutionServiceStateModel.model_validate(payload)
    except ValidationError as exc:
        raise EvidenceIntegrityError("stored participant execution-service state does not validate") from exc


__all__ = ["participant_execution_state"]
