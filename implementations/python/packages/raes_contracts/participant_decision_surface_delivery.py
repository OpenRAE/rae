"""Trusted delivery realization and re-resolution for decision-surface v2."""

from __future__ import annotations

from typing import Protocol

from raes_contracts.contracts.participant_decision_surface_v2 import (
    ParticipantDecisionSurfaceDeliveryV2Model,
    ParticipantDecisionSurfaceV2Model,
)

from ._host_isolation import isolated_host_call


class ParticipantDecisionSurfaceDeliveryResolverV2(Protocol):
    """Resolve an authoritative delivery occurrence by stable reference."""

    def __call__(
        self,
        *,
        delivery_ref: str,
    ) -> ParticipantDecisionSurfaceDeliveryV2Model | None: ...


def deliver_participant_decision_surface_v2(
    surface: ParticipantDecisionSurfaceV2Model,
    *,
    delivery_ref: str,
    resolver: ParticipantDecisionSurfaceDeliveryResolverV2,
) -> ParticipantDecisionSurfaceV2Model:
    """Bind an authoritative delivery occurrence to an exact projected view."""

    if surface.surface_state != "projected" or surface.delivery is not None:
        raise ValueError("only a projected decision surface can transition to delivered")
    with isolated_host_call("participant decision-surface delivery resolution failed"):
        delivery = resolver(delivery_ref=delivery_ref)
    if delivery is None or delivery.delivery_ref != delivery_ref:
        raise ValueError("participant decision-surface delivery_ref did not resolve")
    payload = surface.model_dump(mode="json")
    payload["surface_state"] = "delivered"
    payload["delivery"] = delivery.model_dump(mode="json")
    return ParticipantDecisionSurfaceV2Model.model_validate(payload)


def validate_participant_decision_surface_v2_delivery(
    surface: ParticipantDecisionSurfaceV2Model,
    resolver: ParticipantDecisionSurfaceDeliveryResolverV2,
) -> None:
    """Require delivered state and re-resolve the exact delivery occurrence."""

    if surface.surface_state != "delivered" or surface.delivery is None:
        raise ValueError("participant decision-surface selection requires delivered state")
    with isolated_host_call("participant decision-surface delivery resolution failed"):
        resolved = resolver(delivery_ref=surface.delivery.delivery_ref)
    if resolved is None:
        raise ValueError("participant decision-surface delivery_ref did not resolve")
    if resolved != surface.delivery:
        raise ValueError("participant decision-surface delivery evidence is stale or forged")


__all__ = (
    "ParticipantDecisionSurfaceDeliveryResolverV2",
    "deliver_participant_decision_surface_v2",
    "validate_participant_decision_surface_v2_delivery",
)
