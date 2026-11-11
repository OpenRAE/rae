"""Runtime normalization for the bounded participant-opacity profile."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingGateDisposition,
    ParticipantCrossingOccurrenceModel,
)
from raes_contracts.errors import ConflictError, EvidenceIntegrityError

_PERSISTED_BINDING_NOT_ADMITTED = "persisted participant opacity binding is not admitted by restart context"

if TYPE_CHECKING:
    from raes_contracts.contracts.participant_crossing import ParticipantOpacityRuntimeSupportModel

    from .participant_crossing_mediation import (
        ParticipantCrossingPolicyResolution,
        ParticipantCrossingValidationContext,
    )


def bind_active_participant_opacity_support(
    resolution: ParticipantCrossingPolicyResolution,
    supports: tuple[ParticipantOpacityRuntimeSupportModel, ...],
) -> ParticipantCrossingPolicyResolution:
    """Make the trusted support index authoritative over route-local omission."""

    if resolution.opacity_enforcement is not None or not supports:
        return resolution
    if len(supports) != 1:
        raise ConflictError("participant opacity runtime support is ambiguous at the exact state cut")
    return cast(
        "ParticipantCrossingPolicyResolution",
        replace(resolution, opacity_enforcement=supports[0].binding),
    )


def normalize_participant_opacity_resolution(
    resolution: ParticipantCrossingPolicyResolution,
) -> ParticipantCrossingPolicyResolution:
    """Force the exact supported profile to one secret-independent result."""

    from .participant_crossing_mediation import ParticipantCrossingSemanticGates

    denied = ParticipantCrossingGateDisposition.DENY
    return cast(
        "ParticipantCrossingPolicyResolution",
        replace(
            resolution,
            gates=ParticipantCrossingSemanticGates(
                participant_authority=denied,
                action_admission=denied,
                visibility=denied,
                marking_authorization=denied,
                declassification=denied,
                transformation_validity=denied,
            ),
            reason_code="participant-opacity-contained",
            required_operation=None,
            allowed_downgrades={},
            downgrade_policy_ref=None,
            downgrade_provenance_ref=None,
            transformation=None,
        ),
    )


def validate_persisted_participant_opacity(
    records: list[ParticipantCrossingOccurrenceModel],
    context: ParticipantCrossingValidationContext,
) -> None:
    """Rejoin each compact durable binding to trusted restart support."""

    from raes_contracts.participant_opacity_runtime import (
        validate_participant_opacity_runtime_enforcement,
    )

    for record in records:
        binding = getattr(record.occurrence, "opacity_enforcement", None)
        if binding is None:
            continue
        support = next(
            (candidate for candidate in context.opacity_enforcement_supports if candidate.binding == binding),
            None,
        )
        if support is None:
            raise EvidenceIntegrityError(_PERSISTED_BINDING_NOT_ADMITTED)
        try:
            validate_participant_opacity_runtime_enforcement(
                binding,
                support=support,
                participant_address=record.participant_address,
                audience_scope_ref=record.occurrence.audience_scope_ref,
            )
        except ValueError as exc:
            raise EvidenceIntegrityError(_PERSISTED_BINDING_NOT_ADMITTED) from exc


__all__ = [
    "bind_active_participant_opacity_support",
    "normalize_participant_opacity_resolution",
    "validate_persisted_participant_opacity",
]
