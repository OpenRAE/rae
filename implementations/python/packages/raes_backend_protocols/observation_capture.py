"""Atomic backend observation capture-offer declaration."""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass

from raes_contracts.capture_dimensions import CAPTURE_SET_FIELDS, capture_offer_payload
from raes_contracts.evidence_output_validation import validate_evidence_output_offer


def _validate_unique_non_empty_strings(field_name: str, values: Collection[str]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} must not contain empty strings")
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must not contain duplicate values")


_JSON_POINTER_RE = re.compile(r"^(?:/(?:[^~/]|~[01])*)*$")


@dataclass(frozen=True)
class ObservationCaptureOffer:
    """One atomic field/artifact capture promise used for admission."""

    offer_id: str
    offer_version: str
    output_contract: str
    field_selectors: tuple[str, ...]
    artifact_roles: frozenset[str]
    media_types: frozenset[str]
    capture_kind: str
    source_classes: frozenset[str]
    source_refs: frozenset[str]
    scopes: frozenset[str]
    channel_kinds: frozenset[str]
    channel_refs: frozenset[str]
    window_kinds: frozenset[str]
    integrity_modes: frozenset[str]
    sensitivity: str
    availability: str
    fidelity: str
    disclosure: str
    retention_policy_refs: frozenset[str]
    export_policy: str
    redaction_policy: str | None = None
    scope_refs: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _validate_offer_identity(self)
        _validate_offer_collections(self)
        _validate_offer_governance(self)
        validate_evidence_output_offer(self.output_contract, self.media_types)

    def to_payload(self) -> dict[str, object]:
        """Return the canonical plain-data representation."""

        return capture_offer_payload(self)


def _validate_offer_identity(offer: ObservationCaptureOffer) -> None:
    scalar_fields = ("offer_id", "offer_version", "output_contract", "capture_kind", "sensitivity")
    if any(not getattr(offer, field_name).strip() for field_name in scalar_fields):
        raise ValueError("capture offer identity and semantic fields must be non-empty")
    if len(offer.field_selectors) != len(set(offer.field_selectors)):
        raise ValueError("ObservationCaptureOffer.field_selectors must not contain duplicate values")
    if any(_JSON_POINTER_RE.fullmatch(selector) is None for selector in offer.field_selectors):
        raise ValueError("capture offer field_selectors must be canonical RFC 6901 JSON Pointers")


def _validate_offer_collections(offer: ObservationCaptureOffer) -> None:
    for field_name in CAPTURE_SET_FIELDS:
        _validate_unique_non_empty_strings(f"ObservationCaptureOffer.{field_name}", getattr(offer, field_name))
    if not all((offer.field_selectors, offer.artifact_roles, offer.media_types, offer.source_classes, offer.scopes)):
        raise ValueError("capture offers require fields, artifact roles, media types, source classes, and scopes")
    if not offer.channel_kinds and not offer.channel_refs:
        raise ValueError("capture offers must declare channel_kinds or channel_refs")
    if not offer.window_kinds or not offer.integrity_modes:
        raise ValueError("capture offers require window and integrity semantics")
    if "*" in offer.scope_refs:
        raise ValueError("capture offer scope_refs must name exact authored targets")


def _validate_offer_governance(offer: ObservationCaptureOffer) -> None:
    if offer.availability not in {"available", "unsupported", "unavailable"}:
        raise ValueError("capture offer availability is not governed")
    if offer.fidelity not in {"complete", "lossy"}:
        raise ValueError("capture offer fidelity is not governed")
    if offer.disclosure not in {"full", "redacted", "withheld"}:
        raise ValueError("capture offer disclosure is not governed")
    if (offer.disclosure == "full") != (offer.redaction_policy is None):
        raise ValueError("redacted or withheld capture offers require exactly one redaction_policy")
    if offer.redaction_policy is not None and not offer.redaction_policy.strip():
        raise ValueError("capture offer redaction_policy must be non-empty")
    if offer.export_policy not in {"not-required", "available", "unavailable", "withheld", "prohibited"}:
        raise ValueError("capture offer export_policy is not governed")


__all__ = ["ObservationCaptureOffer"]
