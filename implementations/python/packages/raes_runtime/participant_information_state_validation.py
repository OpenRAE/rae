"""Production validation boundary for participant information-state snapshots."""

from __future__ import annotations

from raes_contracts.contracts import ParticipantInformationStateContextResolver
from raes_contracts.errors import EvidenceIntegrityError
from raes_contracts.participant_information_state_history import (
    iter_participant_information_state_snapshot_violations,
)
from raes_contracts.runtime_state import RuntimeSnapshot


def require_participant_information_state_snapshot(
    snapshot: RuntimeSnapshot,
    resolver: ParticipantInformationStateContextResolver | None,
) -> None:
    """Fail closed when a persisted information-state history cannot be resolved."""

    violations = list(
        iter_participant_information_state_snapshot_violations(
            snapshot.information_state_history,
            information_state_context_resolver=resolver,
            context_scope=snapshot,
        )
    )
    if violations:
        raise EvidenceIntegrityError(violations[0][1])


__all__ = ["require_participant_information_state_snapshot"]
