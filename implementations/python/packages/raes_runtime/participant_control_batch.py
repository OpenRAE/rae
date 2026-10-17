"""Admitted control groups are ordered before any application commits."""

from raes_contracts.runtime_state import OperationKind

from .control_plane_lifecycle import runtime_owned
from .control_plane_mutation import control_plane_mutation, mutation_entry


class ParticipantControlBatchMixin:
    """The group boundary has no implicit arrival or lock-order tiebreaker."""

    @runtime_owned
    @mutation_entry(OperationKind.PARTICIPANT_CONTROL)
    def record_participant_controls(self, participant_address, applications, *, identity):
        """Apply one bounded, single-episode group in distinct admitted order."""

        if not applications or len(applications) > 256:
            raise ValueError("control group must contain between 1 and 256 applications")
        detached = [(type(intent).model_validate(intent.model_dump(mode="json")), key) for intent, key in applications]
        if any(intent.application is None or not key for intent, key in detached):
            raise ValueError("control group requires explicit applications and retry keys")
        coordinates = [intent.application.effective_order for intent, _ in detached]
        if len(set(coordinates)) != len(coordinates) or len({intent.episode_id for intent, _ in detached}) != 1:
            raise ValueError("control group has ambiguous order or episode scope")
        with control_plane_mutation(self, OperationKind.PARTICIPANT_CONTROL):
            return [
                self.record_participant_control(participant_address, intent, identity=identity, idempotency_key=key)
                for intent, key in sorted(detached, key=lambda item: item[0].application.effective_order)
            ]
