"""Conversions between observation capabilities and manifest contract models."""

from __future__ import annotations

from raes_contracts.capture_dimensions import capture_offer_fields
from raes_contracts.contracts import ObservationCapabilitiesModel

from .capabilities import ObservationCapabilities
from .observation_capture import ObservationCaptureOffer


def observation_capability_payload(observation: ObservationCapabilities | None) -> dict[str, object] | None:
    """Render observation capabilities as their canonical manifest payload."""

    if observation is None:
        return None
    return ObservationCapabilitiesModel(
        name=observation.name,
        supported_capture_kinds=sorted(observation.supported_capture_kinds),
        supported_channel_kinds=sorted(observation.supported_channel_kinds),
        supported_evidence_contracts=sorted(observation.supported_evidence_contracts),
        supported_media_types=sorted(observation.supported_media_types),
        supported_sealing_modes=sorted(observation.supported_sealing_modes),
        supports_redaction=observation.supports_redaction,
        supports_loss_disclosure=observation.supports_loss_disclosure,
        supports_chain_of_custody=observation.supports_chain_of_custody,
        capture_offers=[offer.to_payload() for offer in observation.capture_offers],
        constraints=dict(observation.constraints),
    ).model_dump(mode="json")


def observation_from_model(model: ObservationCapabilitiesModel | None) -> ObservationCapabilities | None:
    """Reconstruct typed observation capabilities from a manifest model."""

    if model is None:
        return None
    return ObservationCapabilities(
        name=model.name,
        supported_capture_kinds=frozenset(model.supported_capture_kinds),
        supported_channel_kinds=frozenset(model.supported_channel_kinds),
        supported_evidence_contracts=frozenset(model.supported_evidence_contracts),
        supported_media_types=frozenset(model.supported_media_types),
        supported_sealing_modes=frozenset(model.supported_sealing_modes),
        supports_redaction=model.supports_redaction,
        supports_loss_disclosure=model.supports_loss_disclosure,
        supports_chain_of_custody=model.supports_chain_of_custody,
        capture_offers=tuple(ObservationCaptureOffer(**capture_offer_fields(offer)) for offer in model.capture_offers),
        constraints=dict(model.constraints),
    )


__all__ = ["observation_capability_payload", "observation_from_model"]
