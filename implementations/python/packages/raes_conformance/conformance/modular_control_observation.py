"""Observe the installed input boundaries without lending them new authority."""

from dataclasses import replace

from raes_contracts.contracts.participant_control_invocation import ControlMechanismResultV2Model


class _ResolverObserver:
    def __init__(self, inner, measured):
        self.inner, self.measured = inner, measured

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def resolve(self, **coordinates):
        resolved = self.inner.resolve(**coordinates)
        # A returned absence is distinct from a callback that failed before
        # supplying any authoritative applicability input.
        self.measured.resolutions.append((coordinates["crossing"].record.receipt.operation_id, resolved))
        return resolved


class _ProviderObserver:
    def __init__(self, inner, measured):
        self.inner, self.measured = inner, measured

    def resolve_stage(self, invocation):
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


def observed_binding(binding, measured):
    """Retain exact selection/stage/schema pins and the runtime's callback fences."""

    return replace(
        binding,
        resolver=_ResolverObserver(binding.resolver, measured),
        providers={key: _ProviderObserver(value, measured) for key, value in binding.providers.items()},
    )
