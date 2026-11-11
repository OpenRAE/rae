"""Backend-native participant action execution DTO."""

from dataclasses import dataclass

from raes_contracts.contracts.participant_binding_validation import require_non_empty
from raes_contracts.contracts.participant_runtime import ParticipantActionResultModel

from .runtime_state import ApplyResult


@dataclass(frozen=True)
class ParticipantNativeActionExecution:
    """Backend-native execution output used to commit portable action history."""

    apply_result: ApplyResult
    action_result: ParticipantActionResultModel | None = None
    post_state_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.apply_result, ApplyResult):
            raise TypeError("apply_result must be an ApplyResult")
        if self.action_result is not None and not isinstance(self.action_result, ParticipantActionResultModel):
            raise TypeError("action_result must be a ParticipantActionResultModel or None")
        if self.post_state_digest is not None:
            require_non_empty(self.post_state_digest, "post_state_digest")
