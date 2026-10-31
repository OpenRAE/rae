"""Portable participant action commit helpers for backend runtimes."""

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.digests import sha256_digest
from raes_contracts.participant_binding import (
    ParticipantActionAdmissionRequest,
    ParticipantActionApplyResult,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot


def participant_binding_post_state_digest(request: ParticipantActionAdmissionRequest) -> str:
    """Derive the reference digest for an admitted participant action."""

    digest_input = "|".join(
        (
            request.participant_address,
            request.action_contract_address,
            request.observation_boundary_address,
            request.action_instance_id,
            *request.target_addresses,
            request.execution_scope_ref or "",
            (str(request.execution_generation) if request.execution_generation is not None else ""),
        )
    )
    return sha256_digest(digest_input.encode("utf-8"))


def as_participant_action_result(result: ApplyResult) -> ParticipantActionApplyResult:
    """Preserve a generic apply failure as a participant action result."""

    return ParticipantActionApplyResult(
        success=result.success,
        snapshot=result.snapshot,
        diagnostics=list(result.diagnostics),
        changed_addresses=list(result.changed_addresses),
        details=dict(result.details),
    )


def reject_participant_action_outcome(
    snapshot: RuntimeSnapshot,
    modeled: ApplyResult,
    address: str,
    code: str,
    message: str,
) -> ParticipantActionApplyResult:
    """Reject a native outcome without committing its modeled snapshot."""

    return ParticipantActionApplyResult(
        success=False,
        snapshot=snapshot,
        diagnostics=[
            *modeled.diagnostics,
            Diagnostic(code=code, domain="participant", address=address, message=message),
        ],
        action_result=None,
    )


__all__ = [
    "as_participant_action_result",
    "participant_binding_post_state_digest",
    "reject_participant_action_outcome",
]
