"""Stable errors shared by participant-opacity assurance lanes."""

from raes_contracts.errors import EvidenceIntegrityError, InvalidInputError, OperationalError


class ParticipantOpacityEvidenceError(EvidenceIntegrityError):
    """Stored evidence does not replay against its governed finite input."""


class ParticipantOpacityInputError(InvalidInputError):
    """A supplied opacity input document is not strict JSON or fails its governed contract."""


class ParticipantOpacityOperationalError(OperationalError):
    """An opacity analyzer failed outside its typed outcome domain."""


__all__ = (
    "ParticipantOpacityEvidenceError",
    "ParticipantOpacityInputError",
    "ParticipantOpacityOperationalError",
)
