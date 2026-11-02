"""Complete-prefix replay requires each episode's retained original context."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .control_plane import RuntimeControlPlane


from raes_contracts.contracts import validate_participant_control_occurrence_context
from raes_contracts.contracts.participant_control_occurrence_v2 import parse_participant_control_occurrence
from raes_contracts.errors import ConflictError, EvidenceIntegrityError

from .participant_control_runtime import archived_policies
from .participant_control_targets import archived_control_targets


def validate_restored_control_archive(plane: RuntimeControlPlane) -> None:
    """Refuse unverifiable v2 archives before exposing a recovered runtime."""

    for participant, history in plane._snapshot.participant_control_history.items():
        if not any(payload.get("schema_version") == "2.0.0" for payload in history):
            continue
        if plane._mixed_control is None:
            raise ConflictError("mixed-control archive requires its original policy context")
        try:
            validate_participant_control_occurrence_context(
                [parse_participant_control_occurrence(payload) for payload in history],
                declarations=plane._mixed_control.legacy_declarations,
                policies=archived_policies(plane, participant),
                available_targets=archived_control_targets(plane, participant),
            )
        # The published occurrence validators refuse retained history with ValueError (rule E9).
        except ValueError as exc:
            raise EvidenceIntegrityError("restored participant control archive does not validate") from exc

    from .participant_inject_control import validate_restored_inject_deliveries

    validate_restored_inject_deliveries(plane)
