"""Governed capture dimensions shared by closed offers and demand projections."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

Comparison = Literal[
    "equal", "optional-equal", "subset", "exact-subset", "pointers", "overlap", "sensitivity", "export"
]


@dataclass(frozen=True)
class CaptureDimension:
    name: str
    diagnostic: str
    comparison: Comparison
    sdl_attribute: str | None
    capture_attribute: str | None
    collection: Literal["scalar", "set", "ordered"] = "scalar"
    required_value: str | None = None
    default: str | None = ""

    def matches(self, required: object, supported: object) -> bool:
        """Apply the dimension's own wildcard/empty-value semantics."""

        if self.comparison == "equal":
            return required == supported
        if self.comparison == "optional-equal":
            return not required or required == supported
        if self.comparison == "sensitivity":
            return not required or supported == "*" or required == supported
        if self.comparison == "export":
            return required == "not-required" or required == supported
        if self.comparison == "overlap":
            return not required or bool(set(required).intersection(supported))
        wildcard = "" if self.comparison == "pointers" else "*"
        return (
            not required
            or self.comparison != "exact-subset"
            and wildcard in supported
            or set(required).issubset(supported)
        )


# @derived marks a projection owned by the processor, where channel/window or
# disclosure semantics require more than reading an attribute. Missing derived
# projections fail; adding a model field also requires parity-test coverage.
CAPTURE_DIMENSIONS = (
    CaptureDimension(
        "output_contract", "output-contract-mismatch", "optional-equal", "output_contract", "output_contract"
    ),
    CaptureDimension(
        "field_selectors", "field-selector-missing", "pointers", "field_selectors", "field_selectors", "ordered"
    ),
    CaptureDimension(
        "artifact_roles", "artifact-role-mismatch", "subset", "artifact_role", "required_artifact_roles", "set"
    ),
    CaptureDimension("media_types", "media-type-mismatch", "overlap", "media_types", "expected_media_types", "set"),
    CaptureDimension("capture_kind", "capture-kind-mismatch", "optional-equal", "@derived", "capture_kind"),
    CaptureDimension("source_classes", "source-class-mismatch", "subset", "source_class", None, "set"),
    CaptureDimension("source_refs", "source-ref-mismatch", "subset", "source_refs", None, "set"),
    CaptureDimension("scopes", "scope-mismatch", "subset", "scope", "capture_scope", "set"),
    CaptureDimension("scope_refs", "scope-ref-mismatch", "exact-subset", "scope_refs", None, "set"),
    CaptureDimension("channel_kinds", "channel-mismatch", "subset", "@derived", None, "set"),
    CaptureDimension("channel_refs", "channel-ref-mismatch", "subset", "channel_refs", "@derived", "set"),
    CaptureDimension("window_kinds", "window-mismatch", "subset", "@derived", "@derived", "set"),
    CaptureDimension("integrity_modes", "integrity-mismatch", "subset", "integrity", "integrity_requirements", "set"),
    CaptureDimension("sensitivity", "sensitivity-mismatch", "sensitivity", "sensitivity", "sensitivity"),
    CaptureDimension("availability", "availability-insufficient", "equal", None, None, required_value="available"),
    CaptureDimension("fidelity", "fidelity-insufficient", "equal", None, None, required_value="complete"),
    CaptureDimension("disclosure", "disclosure-insufficient", "equal", "@derived", "@derived"),
    CaptureDimension("retention_policy_refs", "retention-mismatch", "subset", "retention", "retention_policy", "set"),
    CaptureDimension("export_policy", "export-policy-mismatch", "export", None, None, default="not-required"),
    CaptureDimension(
        "redaction_policy", "redaction-policy-mismatch", "equal", "@derived", "redaction_policy", default=None
    ),
)
CAPTURE_SET_FIELDS = tuple(dimension.name for dimension in CAPTURE_DIMENSIONS if dimension.collection == "set")


def capture_offer_payload(offer: object) -> dict[str, object]:
    """Project all declared dimensions without weakening either closed model."""

    payload = {"offer_id": offer.offer_id, "offer_version": offer.offer_version}
    for dimension in CAPTURE_DIMENSIONS:
        value = getattr(offer, dimension.name)
        if dimension.collection == "set":
            value = sorted(value)
        elif dimension.collection == "ordered":
            value = list(value)
        payload[dimension.name] = value
    return payload


def capture_offer_fields(model: object) -> dict[str, object]:
    """Reconstruct protocol collection types from the validated wire model."""

    values = {"offer_id": model.offer_id, "offer_version": model.offer_version}
    for dimension in CAPTURE_DIMENSIONS:
        value = getattr(model, dimension.name)
        if dimension.collection == "set":
            value = frozenset(value)
        elif dimension.collection == "ordered":
            value = tuple(value)
        values[dimension.name] = value
    return values


def _projection_value(dimension: CaptureDimension, value: object) -> object:
    if dimension.collection != "scalar":
        if value is None or value == "":
            return ()
        if isinstance(value, str):
            return (str(getattr(value, "value", value)),)
        return tuple(value)
    return str(getattr(value, "value", value)) if value is not None else dimension.default


def project_capture_dimensions(
    requirement: object,
    *,
    source: Literal["sdl", "capture"],
    overrides: Mapping[str, object],
) -> dict[str, object]:
    """Project existing authored carriers through every governed dimension."""

    dimensions = tuple(dimension for dimension in CAPTURE_DIMENSIONS if dimension.required_value is None)
    if source not in {"sdl", "capture"} or set(overrides) - {dimension.name for dimension in dimensions}:
        raise ValueError("capture projection contains an unknown source or dimension")
    projected = {}
    for dimension in dimensions:
        attribute = dimension.sdl_attribute if source == "sdl" else dimension.capture_attribute
        if dimension.name in overrides:
            value = overrides[dimension.name]
        elif attribute == "@derived":
            raise ValueError(f"capture projection requires derived dimension {dimension.name}")
        else:
            value = None if attribute is None else getattr(requirement, attribute)
        projected[dimension.name] = _projection_value(dimension, value)
    return projected


__all__ = [
    "CAPTURE_DIMENSIONS",
    "CAPTURE_SET_FIELDS",
    "capture_offer_fields",
    "capture_offer_payload",
    "project_capture_dimensions",
]
