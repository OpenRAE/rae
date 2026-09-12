"""Security-monitoring detection definition models."""

from enum import Enum
from typing import Any

from pydantic import Field, ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel, parse_int_or_var
from .runtime_values import (
    absolute_path_or_var,
    coerce_string_list,
    parse_optional_bool_or_var,
    parse_runtime_enum_or_var,
    require_non_empty,
    require_symbol,
    validate_absolute_paths,
)

__all__ = [
    "RuntimeSecurityMonitoringDetectionDefinition",
    "RuntimeSecurityMonitoringDetectionDefinitionKind",
    "RuntimeSecurityMonitoringDetectionEngine",
    "RuntimeSecurityMonitoringFieldPredicate",
    "RuntimeSecurityMonitoringFieldPredicateOperator",
]


class RuntimeSecurityMonitoringDetectionEngine(str, Enum):
    """Portable detection-definition engine family."""

    WAZUH = "wazuh"
    OSSEC = "ossec"
    SIGMA = "sigma"
    YARA = "yara"
    SURICATA = "suricata"
    ELASTIC_SECURITY = "elastic_security"
    SPLUNK_ENTERPRISE_SECURITY = "splunk_enterprise_security"
    MICROSOFT_SENTINEL = "microsoft_sentinel"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeSecurityMonitoringDetectionDefinitionKind(str, Enum):
    """Portable kind of parsed security-monitoring detection definition."""

    RULE = "rule"
    CORRELATION_RULE = "correlation_rule"
    DECODER = "decoder"
    LIST_BACKED_RULE = "list_backed_rule"
    SCA_POLICY_CHECK = "sca_policy_check"
    ACTIVE_RESPONSE_TRIGGER = "active_response_trigger"
    SIGMA_RULE = "sigma_rule"
    YARA_RULE = "yara_rule"
    SURICATA_RULE = "suricata_rule"
    SIEM_ANALYTIC = "siem_analytic"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeSecurityMonitoringFieldPredicateOperator(str, Enum):
    """Portable operator for a parsed field-level predicate."""

    EQUALS = "equals"
    MATCHES = "matches"
    CONTAINS = "contains"
    EXISTS = "exists"
    IN = "in"
    REGEX = "regex"
    LESS_THAN = "less_than"
    GREATER_THAN = "greater_than"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeSecurityMonitoringFieldPredicate(SDLModel):
    """A normalized field predicate extracted from a detection definition."""

    field: str
    operator: GovernedVocabulary[RuntimeSecurityMonitoringFieldPredicateOperator] = (
        RuntimeSecurityMonitoringFieldPredicateOperator.OTHER
    )
    value: str = ""
    description: str = ""

    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        return require_non_empty(v, field_name="field predicate field")

    @field_validator("operator", mode="before")
    @classmethod
    def normalize_operator(
        cls,
        v: RuntimeSecurityMonitoringFieldPredicateOperator | str,
    ) -> RuntimeSecurityMonitoringFieldPredicateOperator | str:
        return parse_runtime_enum_or_var(v, RuntimeSecurityMonitoringFieldPredicateOperator, field_name="operator")


class RuntimeSecurityMonitoringDetectionDefinition(SDLModel):
    """A parsed detection definition loaded by a security-monitoring manager."""

    definition_id: str
    engine: GovernedVocabulary[RuntimeSecurityMonitoringDetectionEngine] = (
        RuntimeSecurityMonitoringDetectionEngine.UNKNOWN
    )
    definition_kind: GovernedVocabulary[RuntimeSecurityMonitoringDetectionDefinitionKind] = (
        RuntimeSecurityMonitoringDetectionDefinitionKind.OTHER
    )
    native_id: str = ""
    name: str = ""
    content_set_ref: str = ""
    source_artifact_ref: str = ""
    source_file_ref: str = ""
    source_start_line: int | str | None = None
    source_end_line: int | str | None = None
    digest_algorithm: str = ""
    canonical_digest: str = ""
    enabled: bool | str | None = None
    loaded: bool | str | None = None
    parser_accepted: bool | str | None = None
    level: int | str | None = None
    severity: str = ""
    description: str = ""
    match_strings: list[str] = Field(default_factory=list)
    regex_patterns: list[str] = Field(default_factory=list)
    field_predicates: list[RuntimeSecurityMonitoringFieldPredicate] = Field(default_factory=list)
    decoded_as: list[str] = Field(default_factory=list)
    decoder_names: list[str] = Field(default_factory=list)
    decoder_fields: list[str] = Field(default_factory=list)
    if_sid_refs: list[str] = Field(default_factory=list)
    if_matched_sid_refs: list[str] = Field(default_factory=list)
    parent_definition_refs: list[str] = Field(default_factory=list)
    frequency: int | str | None = None
    timeframe_seconds: int | str | None = None
    same_source_constraints: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)
    mitre_attack_ids: list[str] = Field(default_factory=list)
    compliance_tags: list[str] = Field(default_factory=list)
    tactic_labels: list[str] = Field(default_factory=list)
    technique_labels: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    target_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("definition_id")
    @classmethod
    def validate_definition_id(cls, v: str) -> str:
        return require_symbol(v, field_name="definition_id")

    @field_validator("engine", mode="before")
    @classmethod
    def normalize_engine(
        cls,
        v: RuntimeSecurityMonitoringDetectionEngine | str,
    ) -> RuntimeSecurityMonitoringDetectionEngine | str:
        return parse_runtime_enum_or_var(v, RuntimeSecurityMonitoringDetectionEngine, field_name="engine")

    @field_validator("definition_kind", mode="before")
    @classmethod
    def normalize_definition_kind(
        cls,
        v: RuntimeSecurityMonitoringDetectionDefinitionKind | str,
    ) -> RuntimeSecurityMonitoringDetectionDefinitionKind | str:
        return parse_runtime_enum_or_var(
            v, RuntimeSecurityMonitoringDetectionDefinitionKind, field_name="definition_kind"
        )

    @field_validator("source_file_ref")
    @classmethod
    def validate_source_file_ref(cls, v: str) -> str:
        return absolute_path_or_var(v, field_name="source_file_ref") if v else v

    @field_validator("source_start_line", "source_end_line", mode="before")
    @classmethod
    def parse_source_line(cls, v: Any, info: ValidationInfo) -> int | str | None:
        return parse_int_or_var(v, minimum=1, field_name=info.field_name) if v is not None else v

    @field_validator("frequency", "timeframe_seconds", mode="before")
    @classmethod
    def parse_non_negative_int(cls, v: Any, info: ValidationInfo) -> int | str | None:
        return parse_int_or_var(v, minimum=0, field_name=info.field_name) if v is not None else v

    @field_validator("level", mode="before")
    @classmethod
    def parse_level(cls, v: Any) -> int | str | None:
        return parse_int_or_var(v, minimum=0, field_name="level") if v is not None else v

    @field_validator("enabled", "loaded", "parser_accepted", mode="before")
    @classmethod
    def parse_optional_state_bool(cls, v: Any, info: ValidationInfo) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name=info.field_name)

    @field_validator(
        "match_strings",
        "regex_patterns",
        "decoded_as",
        "decoder_names",
        "decoder_fields",
        "if_sid_refs",
        "if_matched_sid_refs",
        "parent_definition_refs",
        "same_source_constraints",
        "groups",
        "mitre_attack_ids",
        "compliance_tags",
        "tactic_labels",
        "technique_labels",
        "tags",
        "target_refs",
        "evidence_refs",
        mode="before",
    )
    @classmethod
    def coerce_lists(cls, v: Any) -> list[str]:
        return coerce_string_list(v)

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, v: list[str]) -> list[str]:
        return validate_absolute_paths(v, field_name="evidence_refs")

    @model_validator(mode="after")
    def validate_definition(self) -> "RuntimeSecurityMonitoringDetectionDefinition":
        if self.canonical_digest and not self.digest_algorithm:
            raise ValueError("canonical_digest requires digest_algorithm")
        if self.digest_algorithm and not self.canonical_digest:
            raise ValueError("digest_algorithm requires canonical_digest")
        if (
            isinstance(self.source_start_line, int)
            and isinstance(self.source_end_line, int)
            and self.source_end_line < self.source_start_line
        ):
            raise ValueError("source_end_line must be >= source_start_line")
        return self
