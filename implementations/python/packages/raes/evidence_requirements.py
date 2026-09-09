"""Authored evidence requirement models for SDL (DSL-124).

These models describe portable capture intent in SDL. They are not raw
evidence records and they are not proof that capture occurred.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import Field, ValidationInfo, field_validator, model_validator

from ._base import SDLModel, parse_enum_or_var
from .runtime_filesystem import RuntimeSensitivityClassification
from .runtime_values import coerce_string_list, reject_duplicates


class EvidenceRequirementSourceClass(str, Enum):
    """Closed source classes for requirements without a concrete source ref."""

    SCENARIO_NATIVE_OBSERVABILITY = "scenario_native_observability"
    PARTICIPANT_ACTION = "participant_action"
    PARTICIPANT_OBSERVATION = "participant_observation"
    SCENARIO_STATE = "scenario_state"
    PROCESSOR_BACKEND = "processor_backend"
    APPARATUS = "apparatus"
    EXTERNAL = "external"
    OTHER = "other"


class EvidenceRequirementChannel(str, Enum):
    """Capture channel or modality for an authored requirement."""

    PACKET_CAPTURE = "packet_capture"
    LOG = "log"
    TRACE = "trace"
    METRIC = "metric"
    FILE_ARTIFACT = "file_artifact"
    SCREEN_CAPTURE = "screen_capture"
    API_RESPONSE = "api_response"
    DATABASE_RECORD = "database_record"
    PARTICIPANT_OUTPUT = "participant_output"
    OTHER = "other"


class EvidenceRedactionExpectation(str, Enum):
    """Expected redaction treatment for captured output."""

    NONE = "none"
    REDACT_SENSITIVE = "redact_sensitive"
    REDACT_SECRETS = "redact_secrets"
    AGGREGATE_ONLY = "aggregate_only"
    DERIVED_ONLY = "derived_only"
    OTHER = "other"


class EvidenceIntegrityExpectation(str, Enum):
    """Expected integrity or chain-of-custody treatment."""

    NONE = "none"
    CHECKSUM = "checksum"
    SIGNATURE = "signature"
    CHAIN_OF_CUSTODY = "chain_of_custody"
    TIMESTAMPED = "timestamped"
    OTHER = "other"


class EvidenceRetentionExpectation(str, Enum):
    """Expected retention boundary for captured output."""

    NOT_RETAINED = "not_retained"
    RUN_LIFETIME = "run_lifetime"
    STUDY_LIFETIME = "study_lifetime"
    ARCHIVAL = "archival"
    POLICY_DEFINED = "policy_defined"
    OTHER = "other"


class EvidenceLossDisclosureExpectation(str, Enum):
    """Expected disclosure when capture is incomplete or lossy."""

    NOT_EXPECTED = "not_expected"
    BEST_EFFORT = "best_effort"
    REQUIRED = "required"
    OTHER = "other"


def _coerce_string_list(value: object) -> object:
    return coerce_string_list(value)


def _validate_string_list(values: list[str], *, field_name: str) -> list[str]:
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} entries must be non-empty strings")
    reject_duplicates(values, label=field_name, container_label=field_name, skip_empty=False)
    return values


class EvidenceRequirement(SDLModel):
    """One authored data, evidence, or output capture requirement.

    The model records capture intent only. Executable capture contracts may map
    this to ``experiment-capture-spec-v1`` later, but captured payloads and
    proof of capture belong to experiment evidence records.
    """

    description: str = ""
    source_refs: list[str] = Field(default_factory=list)
    source_class: EvidenceRequirementSourceClass | str | None = None
    scope_refs: list[str] = Field(default_factory=list)
    scope: str = ""
    window: str = ""
    trigger_ref: str = ""
    boundary_ref: str = ""
    boundary_kind: str = ""
    channel: EvidenceRequirementChannel | str | None = None
    channel_refs: list[str] = Field(default_factory=list)
    artifact_role: str = ""
    media_types: list[str] = Field(default_factory=list)
    sensitivity: RuntimeSensitivityClassification | str
    redaction: EvidenceRedactionExpectation | str
    integrity: EvidenceIntegrityExpectation | str
    retention: EvidenceRetentionExpectation | str
    loss_disclosure: EvidenceLossDisclosureExpectation | str
    capture_spec_ref: str = ""
    capture_requirement_ref: str = ""
    output_contract: str = ""
    field_selectors: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator(
        "source_refs",
        "scope_refs",
        "channel_refs",
        "media_types",
        "field_selectors",
        "notes",
        mode="before",
    )
    @classmethod
    def _coerce_lists(cls, value: object) -> object:
        return _coerce_string_list(value)

    @field_validator("source_refs", "scope_refs", "channel_refs", "media_types", "field_selectors", "notes")
    @classmethod
    def _validate_lists(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return _validate_string_list(values, field_name=info.field_name)

    @field_validator("source_class", mode="before")
    @classmethod
    def _parse_source_class(cls, value: object) -> object:
        if value is None:
            return value
        return parse_enum_or_var(value, EvidenceRequirementSourceClass, field_name="source_class")

    @field_validator("channel", mode="before")
    @classmethod
    def _parse_channel(cls, value: object) -> object:
        if value is None:
            return value
        return parse_enum_or_var(value, EvidenceRequirementChannel, field_name="channel")

    @field_validator("sensitivity", mode="before")
    @classmethod
    def _parse_sensitivity(cls, value: object) -> object:
        return parse_enum_or_var(value, RuntimeSensitivityClassification, field_name="sensitivity")

    @field_validator("redaction", mode="before")
    @classmethod
    def _parse_redaction(cls, value: object) -> object:
        return parse_enum_or_var(value, EvidenceRedactionExpectation, field_name="redaction")

    @field_validator("integrity", mode="before")
    @classmethod
    def _parse_integrity(cls, value: object) -> object:
        return parse_enum_or_var(value, EvidenceIntegrityExpectation, field_name="integrity")

    @field_validator("retention", mode="before")
    @classmethod
    def _parse_retention(cls, value: object) -> object:
        return parse_enum_or_var(value, EvidenceRetentionExpectation, field_name="retention")

    @field_validator("loss_disclosure", mode="before")
    @classmethod
    def _parse_loss_disclosure(cls, value: object) -> object:
        return parse_enum_or_var(value, EvidenceLossDisclosureExpectation, field_name="loss_disclosure")

    @model_validator(mode="after")
    def _validate_capture_intent(self) -> EvidenceRequirement:
        _validate_capture_dimensions(self)
        _validate_capture_contract(self)
        return self


def _validate_capture_dimensions(requirement: EvidenceRequirement) -> None:
    if not requirement.source_refs and requirement.source_class is None:
        raise ValueError("evidence requirement must declare source_refs or source_class")
    if not requirement.scope_refs and not requirement.scope:
        raise ValueError("evidence requirement must declare scope_refs or scope")
    if not any((requirement.window, requirement.trigger_ref, requirement.boundary_ref, requirement.boundary_kind)):
        raise ValueError("evidence requirement must declare window, trigger_ref, boundary_ref, or boundary_kind")
    if requirement.channel is None and not requirement.channel_refs and not requirement.boundary_kind:
        raise ValueError("evidence requirement must declare channel, channel_refs, or boundary_kind")


def _validate_capture_contract(requirement: EvidenceRequirement) -> None:
    if bool(requirement.output_contract) != bool(requirement.field_selectors):
        raise ValueError("output_contract and field_selectors must be declared together")
    if bool(requirement.capture_spec_ref) != bool(requirement.capture_requirement_ref):
        raise ValueError("capture_spec_ref and capture_requirement_ref must be declared together")
    if any(re.fullmatch(r"(?:/(?:[^~/]|~[01])*)*", selector) is None for selector in requirement.field_selectors):
        raise ValueError("field_selectors must be canonical RFC 6901 JSON Pointers")


__all__ = [
    "EvidenceIntegrityExpectation",
    "EvidenceLossDisclosureExpectation",
    "EvidenceRedactionExpectation",
    "EvidenceRequirement",
    "EvidenceRequirementChannel",
    "EvidenceRequirementSourceClass",
    "EvidenceRetentionExpectation",
]
