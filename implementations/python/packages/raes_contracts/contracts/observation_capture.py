"""Atomic backend observation capture-offer contract."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .base import ContractModel, NonEmptyString
from .validators import _validate_unique_string_values


class ObservationCaptureOfferModel(ContractModel):
    """One coherent, admission-bearing backend capture promise."""

    offer_id: NonEmptyString
    offer_version: NonEmptyString
    output_contract: NonEmptyString
    field_selectors: list[str] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    artifact_roles: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    media_types: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    capture_kind: NonEmptyString
    source_classes: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    source_refs: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    scopes: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    scope_refs: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    channel_kinds: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    channel_refs: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    window_kinds: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    integrity_modes: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    sensitivity: NonEmptyString
    availability: Literal["available", "unsupported", "unavailable"]
    fidelity: Literal["complete", "lossy"]
    disclosure: Literal["full", "redacted", "withheld"]
    retention_policy_refs: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    export_policy: Literal["not-required", "available", "unavailable", "withheld", "prohibited"]
    redaction_policy: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_capture_offer(self) -> ObservationCaptureOfferModel:
        for field_name in (
            "artifact_roles",
            "media_types",
            "source_classes",
            "source_refs",
            "scopes",
            "scope_refs",
            "channel_kinds",
            "channel_refs",
            "window_kinds",
            "integrity_modes",
            "retention_policy_refs",
        ):
            _validate_unique_string_values(field_name, getattr(self, field_name))
        if len(self.field_selectors) != len(set(self.field_selectors)):
            raise ValueError("field_selectors must not contain duplicate values")
        if not self.channel_kinds and not self.channel_refs:
            raise ValueError("capture offers must declare channel_kinds or channel_refs")
        if any(re.fullmatch(r"(?:/(?:[^~/]|~[01])*)*", selector) is None for selector in self.field_selectors):
            raise ValueError("capture offer field_selectors must be canonical RFC 6901 JSON Pointers")
        if "*" in self.scope_refs:
            raise ValueError("capture offer scope_refs must name exact authored targets")
        if (self.disclosure == "full") != (self.redaction_policy is None):
            raise ValueError("redacted or withheld capture offers require exactly one redaction_policy")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {"properties": {"disclosure": {"const": "full"}}, "required": ["disclosure"]},
                    "then": {"properties": {"redaction_policy": {"type": "null"}}},
                },
                {
                    "if": {
                        "properties": {"disclosure": {"enum": ["redacted", "withheld"]}},
                        "required": ["disclosure"],
                    },
                    "then": {
                        "required": ["redaction_policy"],
                        "properties": {"redaction_policy": {"type": "string", "minLength": 1}},
                    },
                },
            ]
        )
        return json_schema


__all__ = ["ObservationCaptureOfferModel"]
