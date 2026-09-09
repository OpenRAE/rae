"""Conversions between observation capabilities and manifest contract models."""

from __future__ import annotations

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
        capture_offers=tuple(
            ObservationCaptureOffer(
                offer_id=offer.offer_id,
                offer_version=offer.offer_version,
                output_contract=offer.output_contract,
                field_selectors=tuple(offer.field_selectors),
                artifact_roles=frozenset(offer.artifact_roles),
                media_types=frozenset(offer.media_types),
                capture_kind=offer.capture_kind,
                source_classes=frozenset(offer.source_classes),
                source_refs=frozenset(offer.source_refs),
                scopes=frozenset(offer.scopes),
                scope_refs=frozenset(offer.scope_refs),
                channel_kinds=frozenset(offer.channel_kinds),
                channel_refs=frozenset(offer.channel_refs),
                window_kinds=frozenset(offer.window_kinds),
                integrity_modes=frozenset(offer.integrity_modes),
                sensitivity=offer.sensitivity,
                availability=offer.availability,
                fidelity=offer.fidelity,
                disclosure=offer.disclosure,
                retention_policy_refs=frozenset(offer.retention_policy_refs),
                export_policy=offer.export_policy,
                redaction_policy=offer.redaction_policy,
            )
            for offer in model.capture_offers
        ),
        constraints=dict(model.constraints),
    )


__all__ = ["observation_capability_payload", "observation_from_model"]
