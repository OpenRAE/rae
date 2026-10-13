"""Backend-agnostic refusal of rev1 mixed-control semantics before execution.

The migration contract requires refusing admission of a new live episode until
every selected compiler, runtime and downstream consumer path supports the rev1
semantics. No backend executes them yet, so planning refuses every rev1
behavior specification and every rev1 directed-delivery binding, whatever any
manifest declares. Validation and compilation of the form are unaffected.
"""

from collections.abc import Iterable

from raes.participant_mixed_control_policy import MIXED_CONTROL_POLICY_SEMANTICS
from raes_contracts.diagnostics import Diagnostic

from ..models import ParticipantBehaviorSpecificationRuntime, ParticipantInjectDeliveryRuntime, RuntimeModel


def mixed_control_policy_addresses(
    specifications: Iterable[ParticipantBehaviorSpecificationRuntime],
    deliveries: Iterable[ParticipantInjectDeliveryRuntime] = (),
) -> tuple[str, ...]:
    """Return compiled addresses that carry the ``mixed-control-policy-occurrence/rev1`` pin."""

    specification_addresses = [
        specification.address
        for specification in specifications
        if specification.mixed_control_semantics == MIXED_CONTROL_POLICY_SEMANTICS
    ]
    delivery_addresses = [
        delivery.address
        for delivery in deliveries
        if delivery.control is not None and delivery.control.semantics == MIXED_CONTROL_POLICY_SEMANTICS
    ]
    return tuple(sorted({*specification_addresses, *delivery_addresses}))


def mixed_control_semantics_diagnostics(model: RuntimeModel) -> list[Diagnostic]:
    """Refuse planning for every rev1 mixed-control address, for every backend."""

    addresses = mixed_control_policy_addresses(
        model.behavior_specifications.values(),
        model.participant_inject_deliveries.values(),
    )
    return [
        Diagnostic(
            code="participant.mixed-control-semantics-unsupported",
            domain="participant",
            address=address,
            message=(
                "Reusable mixed-control policy and occurrence semantics validate and compile, but no runtime "
                "executes them; planning refuses this path for every backend."
            ),
        )
        for address in addresses
    ]


__all__ = ["mixed_control_policy_addresses", "mixed_control_semantics_diagnostics"]
