"""Require explicit installed-owner admission for rev1 mixed-control planning.

Manifest declarations alone cannot establish the runtime consumer path.
Without an exact host admission, planning retains the migration refusal.
"""

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass

from raes.participant_mixed_control_policy import MIXED_CONTROL_POLICY_SEMANTICS
from raes_contracts.diagnostics import Diagnostic

from ..models import ParticipantBehaviorSpecificationRuntime, ParticipantInjectDeliveryRuntime, RuntimeModel


@dataclass(frozen=True)
class MixedControlPlanningAdmission:
    """Explicit host context for the installed reusable-control consumer path.

    Planning alone grants no execution: the runtime also checks this retained
    model against its installed owners before registering the result.
    """

    model: RuntimeModel

    def __post_init__(self):
        object.__setattr__(self, "model", deepcopy(self.model))


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
    """Describe rev1 paths lacking explicit installed-owner admission."""

    addresses = mixed_control_policy_addresses(
        model.behavior_specifications.values(),
        model.participant_inject_deliveries.values(),
    )
    return [
        Diagnostic(
            code="participant.mixed-control-semantics-unsupported",
            domain="participant",
            address=address,
            message=("Reusable mixed-control planning requires an explicit matching installed-owner admission."),
        )
        for address in addresses
    ]


__all__ = ["mixed_control_policy_addresses", "mixed_control_semantics_diagnostics"]
