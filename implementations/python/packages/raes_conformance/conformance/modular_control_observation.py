"""Observe the installed input boundaries without lending them new authority."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from raes_backend_protocols.protocols import ParticipantControlProviderV2
from raes_contracts.contracts.participant_control_invocation import (
    ControlInvocationV2Model,
    ControlMechanismResultV2Model,
)
from raes_runtime.control_plane import (
    ParticipantControlResolution,
    ParticipantControlRuntimeBinding,
    ParticipantControlRuntimeResolver,
)

if TYPE_CHECKING:
    from .modular_control_execution import _Measurement


class _ResolverObserver:
    def __init__(self, inner: ParticipantControlRuntimeResolver, measured: _Measurement) -> None:
        self.inner, self.measured = inner, measured

    def __getattr__(self, name: str) -> object:
        return getattr(self.inner, name)

    def resolve(self, **coordinates: object) -> ParticipantControlResolution | None:
        resolved = self.inner.resolve(**coordinates)
        # A returned absence is distinct from a callback that failed before
        # supplying any authoritative applicability input.
        self.measured.resolutions.append((coordinates["crossing"].record.receipt.operation_id, resolved))
        return resolved


class _ProviderObserver:
    def __init__(self, inner: ParticipantControlProviderV2, measured: _Measurement) -> None:
        self.inner, self.measured = inner, measured

    def resolve_stage(self, invocation: ControlInvocationV2Model) -> tuple[ControlMechanismResultV2Model, ...]:
        try:
            results = self.inner.resolve_stage(invocation)
        except Exception:
            self.measured.integrity_slots.update(
                (invocation.context_digest, slot) for slot in invocation.requested_slot_ids
            )
            raise
        if type(results) is not tuple or any(type(item) is not ControlMechanismResultV2Model for item in results):
            self.measured.integrity_slots.update(
                (invocation.context_digest, slot) for slot in invocation.requested_slot_ids
            )
        return results


def observed_binding(
    binding: ParticipantControlRuntimeBinding, measured: _Measurement
) -> ParticipantControlRuntimeBinding:
    """Retain exact selection/stage/schema pins and the runtime's callback fences."""

    return cast(
        ParticipantControlRuntimeBinding,
        replace(
            binding,
            resolver=_ResolverObserver(binding.resolver, measured),
            providers={key: _ProviderObserver(value, measured) for key, value in binding.providers.items()},
        ),
    )
