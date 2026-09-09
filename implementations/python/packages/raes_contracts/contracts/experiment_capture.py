"""Experiment validity-note and capture-spec contracts."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..versions import EXPERIMENT_CAPTURE_SPEC_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString, Rfc3339DateTimeString, _parse_rfc3339_datetime
from .experiment_artifacts import (
    ExperimentArtifactRefModel,
    ExperimentChecksumModel,
    ExperimentMeasurementChannelReferenceModel,
)
from .experiment_references import ExperimentReferenceModel
from .schema_invariants import _add_raes_invariant, _add_raes_plane
from .validators import _validate_unique_string_values

__all__ = [
    "ExperimentCaptureRequirementModel",
    "ExperimentCaptureSpecModel",
    "ExperimentCaptureWindowModel",
    "ExperimentValidityNoteModel",
]


class ExperimentValidityNoteModel(ContractModel):
    """Validity threat, limitation, or mitigation note for experiment interpretation."""

    category: Literal[
        "construct",
        "internal",
        "external",
        "conclusion",
        "statistical",
        "apparatus",
        "reproducibility",
        "security",
        "other",
    ]
    note: NonEmptyString
    mitigation: NonEmptyString | None = None


class ExperimentCaptureWindowModel(ContractModel):
    """Declarative scope/window over which evidence must be captured."""

    window_id: NonEmptyString
    window_kind: Literal["task", "run", "apparatus", "event", "interval", "manual"]
    starts_at: Rfc3339DateTimeString | None = None
    ends_at: Rfc3339DateTimeString | None = None
    trigger_ref: ExperimentReferenceModel | None = None
    description: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_capture_window(self) -> ExperimentCaptureWindowModel:
        if self.starts_at is None and self.ends_at is None and self.trigger_ref is None:
            raise ValueError("capture windows must declare starts_at, ends_at, or trigger_ref")
        if self.starts_at is not None and self.ends_at is not None:
            starts_at = _parse_rfc3339_datetime("starts_at", self.starts_at)
            ends_at = _parse_rfc3339_datetime("ends_at", self.ends_at)
            if ends_at < starts_at:
                raise ValueError("capture window ends_at must be greater than or equal to starts_at")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("anyOf", []).extend(
            [
                {"required": ["starts_at"], "properties": {"starts_at": {"not": {"type": "null"}}}},
                {"required": ["ends_at"], "properties": {"ends_at": {"not": {"type": "null"}}}},
                {"required": ["trigger_ref"], "properties": {"trigger_ref": {"not": {"type": "null"}}}},
            ]
        )
        _add_raes_invariant(
            json_schema,
            "capture-window-interval-valid",
            "Capture window ends_at must not precede starts_at when both timestamps are present.",
            validator="raes_contracts.contracts.ExperimentCaptureWindowModel._validate_capture_window",
            inputs=[{"contract_id": "experiment-capture-spec-v1", "instance_path": "#/capture_windows"}],
        )
        return json_schema


class ExperimentCaptureRequirementModel(ContractModel):
    """One evidence capture requirement inside a capture specification."""

    requirement_id: NonEmptyString
    title: NonEmptyString
    capture_kind: Literal["artifact", "observation", "trace", "telemetry", "log", "packet-capture", "other"]
    capture_scope: Literal["task", "run", "apparatus", "participant", "backend", "processor", "network", "service"]
    channel_ref: ExperimentMeasurementChannelReferenceModel
    window_refs: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    expected_media_types: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    required_artifact_roles: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    output_contract: NonEmptyString
    field_selectors: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    sensitivity: Literal["public", "internal", "restricted", "redacted"]
    redaction_policy: NonEmptyString | None = None
    integrity_requirements: list[NonEmptyString] = Field(min_length=1)
    retention_policy: NonEmptyString | None = None
    loss_disclosure_required: bool = True
    notes: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_capture_requirement(self) -> ExperimentCaptureRequirementModel:
        _validate_unique_string_values("window_refs", self.window_refs)
        _validate_unique_string_values("expected_media_types", self.expected_media_types)
        _validate_unique_string_values("required_artifact_roles", self.required_artifact_roles)
        _validate_unique_string_values("field_selectors", self.field_selectors)
        if any(re.fullmatch(r"(?:/(?:[^~/]|~[01])*)*", selector) is None for selector in self.field_selectors):
            raise ValueError("field_selectors must be canonical RFC 6901 JSON Pointers")
        if self.sensitivity == "redacted" and self.redaction_policy is None:
            raise ValueError("redacted capture requirements must declare redaction_policy")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).append(
            {
                "if": {"properties": {"sensitivity": {"const": "redacted"}}, "required": ["sensitivity"]},
                "then": {
                    "required": ["redaction_policy"],
                    "properties": {"redaction_policy": {"type": "string", "minLength": 1}},
                },
            }
        )
        return json_schema


class ExperimentCaptureSpecModel(ContractModel):
    """Declarative EXP-707 specification of what experiment evidence to capture."""

    schema_version: Literal[EXPERIMENT_CAPTURE_SPEC_SCHEMA_VERSION]
    capture_spec_id: NonEmptyString
    spec_version: NonEmptyString
    title: NonEmptyString
    description: NonEmptyString
    scope_refs: list[ExperimentReferenceModel] = Field(min_length=1)
    capture_windows: list[ExperimentCaptureWindowModel] = Field(min_length=1)
    capture_requirements: dict[NonEmptyString, ExperimentCaptureRequirementModel] = Field(min_length=1)
    validity_notes: list[ExperimentValidityNoteModel] = Field(default_factory=list)
    artifact_refs: list[ExperimentArtifactRefModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_capture_spec(self) -> ExperimentCaptureSpecModel:
        _validate_unique_string_values(
            "capture window ids",
            [window.window_id for window in self.capture_windows],
        )
        mismatches = [
            requirement_key
            for requirement_key, requirement in self.capture_requirements.items()
            if requirement.requirement_id != requirement_key
        ]
        if mismatches:
            joined = ", ".join(sorted(mismatches))
            raise ValueError(f"capture_requirements keys must match embedded requirement_id: {joined}")
        window_ids = {window.window_id for window in self.capture_windows}
        missing_window_refs = sorted(
            {
                window_ref
                for requirement in self.capture_requirements.values()
                for window_ref in requirement.window_refs
                if window_ref not in window_ids
            }
        )
        if missing_window_refs:
            joined = ", ".join(missing_window_refs)
            raise ValueError(f"capture requirement window_refs must resolve to capture_windows: {joined}")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        _add_raes_invariant(
            json_schema,
            "capture-requirement-key-matches-requirement-id",
            "Every capture_requirements object key must match the embedded requirement_id value, capture window ids "
            "must be unique, and window_refs must resolve to declared capture_windows.",
            validator="raes_contracts.contracts.ExperimentCaptureSpecModel._validate_capture_spec",
            inputs=[{"contract_id": "experiment-capture-spec-v1", "instance_path": "#"}],
        )
        _add_raes_plane(json_schema, "experiment-capture-spec-v1")
        return json_schema


class ExperimentRawEvidenceContentModel(ContractModel):
    """Raw captured payload reference or bounded summary for EXP-708 records."""

    artifact_ref: ExperimentArtifactRefModel | None = None
    content_uri: NonEmptyString | None = None
    content_checksum: ExperimentChecksumModel | None = None
    payload_summary: NonEmptyString | None = None
    loss_disclosure: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_raw_content(self) -> ExperimentRawEvidenceContentModel:
        if self.artifact_ref is None and self.content_uri is None and self.payload_summary is None:
            raise ValueError("raw evidence content must include artifact_ref, content_uri, or payload_summary")
        if self.content_uri is not None and self.content_checksum is None:
            raise ValueError("content_uri raw evidence must include content_checksum")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("anyOf", []).extend(
            [
                {"required": ["artifact_ref"], "properties": {"artifact_ref": {"not": {"type": "null"}}}},
                {"required": ["content_uri"], "properties": {"content_uri": {"not": {"type": "null"}}}},
                {"required": ["payload_summary"], "properties": {"payload_summary": {"not": {"type": "null"}}}},
            ]
        )
        json_schema.setdefault("allOf", []).append(
            {
                "if": {"required": ["content_uri"], "properties": {"content_uri": {"not": {"type": "null"}}}},
                "then": {
                    "required": ["content_checksum"],
                    "properties": {"content_checksum": {"not": {"type": "null"}}},
                },
            }
        )
        return json_schema
