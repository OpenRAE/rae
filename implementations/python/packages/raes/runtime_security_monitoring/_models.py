"""Security-monitoring manager runtime inventory models."""

from pydantic import Field, ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from .._base import SDLModel, parse_int_or_var
from ..runtime_filesystem import RuntimeSensitivityClassification
from ..runtime_security_monitoring_definitions import (
    RuntimeSecurityMonitoringDetectionDefinition,
)
from ..runtime_values import (
    absolute_path_or_var,
    coerce_string_list,
    enforce_observed_value_redaction,
    parse_optional_bool_or_var,
    parse_runtime_enum_or_var,
    require_non_empty,
    require_symbol,
    validate_absolute_paths,
)
from ._enums import (
    RuntimeSecurityMonitoringAgentStatus,
    RuntimeSecurityMonitoringComponentKind,
    RuntimeSecurityMonitoringComponentStatus,
    RuntimeSecurityMonitoringContentFormat,
    RuntimeSecurityMonitoringContentKind,
    RuntimeSecurityMonitoringImplementation,
    RuntimeSecurityMonitoringListenerRole,
    RuntimeSecurityMonitoringManagerKind,
    RuntimeSecurityMonitoringSettingProvenance,
)

_REDACTED_SENSITIVITIES = (
    RuntimeSensitivityClassification.REDACTED,
    RuntimeSensitivityClassification.OPERATOR_SECRET,
)


class RuntimeSecurityMonitoringListener(SDLModel):
    """A manager listener bound to a same-node transport service."""

    listener_id: str
    service: str = ""
    role: GovernedVocabulary[RuntimeSecurityMonitoringListenerRole] = RuntimeSecurityMonitoringListenerRole.OTHER
    protocol: str = ""
    auth_required: bool | str | None = None
    tls_enabled: bool | str | None = None
    description: str = ""

    @field_validator("listener_id")
    @classmethod
    def validate_listener_id(cls, v: str) -> str:
        return require_symbol(v, field_name="listener_id")

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(
        cls,
        v: RuntimeSecurityMonitoringListenerRole | str,
    ) -> RuntimeSecurityMonitoringListenerRole | str:
        return parse_runtime_enum_or_var(v, RuntimeSecurityMonitoringListenerRole, field_name="role")

    @field_validator("auth_required", "tls_enabled", mode="before")
    @classmethod
    def parse_optional_bool(cls, v: object, info: ValidationInfo) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name=info.field_name)


class RuntimeSecurityMonitoringComponent(SDLModel):
    """A manager daemon, module, or internal component."""

    component_id: str
    kind: GovernedVocabulary[RuntimeSecurityMonitoringComponentKind] = RuntimeSecurityMonitoringComponentKind.OTHER
    name: str
    status: GovernedVocabulary[RuntimeSecurityMonitoringComponentStatus] = (
        RuntimeSecurityMonitoringComponentStatus.UNKNOWN
    )
    enabled: bool | str | None = None
    process_ref: str = ""
    description: str = ""

    @field_validator("component_id")
    @classmethod
    def validate_component_id(cls, v: str) -> str:
        return require_symbol(v, field_name="component_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(
        cls,
        v: RuntimeSecurityMonitoringComponentKind | str,
    ) -> RuntimeSecurityMonitoringComponentKind | str:
        return parse_runtime_enum_or_var(v, RuntimeSecurityMonitoringComponentKind, field_name="kind")

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(
        cls,
        v: RuntimeSecurityMonitoringComponentStatus | str,
    ) -> RuntimeSecurityMonitoringComponentStatus | str:
        return parse_runtime_enum_or_var(v, RuntimeSecurityMonitoringComponentStatus, field_name="status")

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_enabled(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="enabled")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return require_non_empty(v, field_name="component name")


class RuntimeSecurityMonitoringAgent(SDLModel):
    """An agent or sensor enrolled with the manager."""

    agent_id: str
    name: str
    status: GovernedVocabulary[RuntimeSecurityMonitoringAgentStatus] = RuntimeSecurityMonitoringAgentStatus.UNKNOWN
    address: str = ""
    version: str = ""
    os: str = ""
    node_ref: str = ""
    group_refs: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        return require_symbol(v, field_name="agent_id")

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(
        cls,
        v: RuntimeSecurityMonitoringAgentStatus | str,
    ) -> RuntimeSecurityMonitoringAgentStatus | str:
        return parse_runtime_enum_or_var(v, RuntimeSecurityMonitoringAgentStatus, field_name="status")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return require_non_empty(v, field_name="agent name")

    @field_validator("group_refs", mode="before")
    @classmethod
    def coerce_group_refs(cls, v: object) -> list[str]:
        return coerce_string_list(v)


class RuntimeSecurityMonitoringAgentGroup(SDLModel):
    """A manager-side enrolled-agent group."""

    group_id: str
    name: str = ""
    member_refs: list[str] = Field(default_factory=list)
    configuration_file_refs: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("group_id")
    @classmethod
    def validate_group_id(cls, v: str) -> str:
        return require_symbol(v, field_name="group_id")

    @field_validator("member_refs", "configuration_file_refs", mode="before")
    @classmethod
    def coerce_lists(cls, v: object) -> list[str]:
        return coerce_string_list(v)

    @field_validator("configuration_file_refs")
    @classmethod
    def validate_configuration_file_refs(cls, v: list[str]) -> list[str]:
        return validate_absolute_paths(v, field_name="configuration_file_refs")


class RuntimeSecurityMonitoringContentSet(SDLModel):
    """A manager-owned rule, decoder, policy, list, or query corpus."""

    content_id: str
    kind: GovernedVocabulary[RuntimeSecurityMonitoringContentKind] = RuntimeSecurityMonitoringContentKind.OTHER
    format: GovernedVocabulary[RuntimeSecurityMonitoringContentFormat] = RuntimeSecurityMonitoringContentFormat.UNKNOWN
    name: str = ""
    file_count: int | str | None = None
    file_refs: list[str] = Field(default_factory=list)
    loaded: bool | str | None = None
    description: str = ""

    @field_validator("content_id")
    @classmethod
    def validate_content_id(cls, v: str) -> str:
        return require_symbol(v, field_name="content_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(
        cls,
        v: RuntimeSecurityMonitoringContentKind | str,
    ) -> RuntimeSecurityMonitoringContentKind | str:
        return parse_runtime_enum_or_var(v, RuntimeSecurityMonitoringContentKind, field_name="kind")

    @field_validator("format", mode="before")
    @classmethod
    def normalize_format(
        cls,
        v: RuntimeSecurityMonitoringContentFormat | str,
    ) -> RuntimeSecurityMonitoringContentFormat | str:
        return parse_runtime_enum_or_var(v, RuntimeSecurityMonitoringContentFormat, field_name="format")

    @field_validator("file_count", mode="before")
    @classmethod
    def parse_file_count(cls, v: object) -> int | str | None:
        return parse_int_or_var(v, minimum=0, field_name="file_count") if v is not None else v

    @field_validator("file_refs", mode="before")
    @classmethod
    def coerce_file_refs(cls, v: object) -> list[str]:
        return coerce_string_list(v)

    @field_validator("file_refs")
    @classmethod
    def validate_file_refs(cls, v: list[str]) -> list[str]:
        return validate_absolute_paths(v, field_name="file_refs")

    @field_validator("loaded", mode="before")
    @classmethod
    def parse_loaded(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="loaded")


class RuntimeSecurityMonitoringSetting(SDLModel):
    """A bounded manager setting with sensitivity classification."""

    setting_id: str
    component_ref: str = ""
    name: str
    value: str = ""
    value_classification: GovernedVocabulary[RuntimeSensitivityClassification] = (
        RuntimeSensitivityClassification.UNKNOWN
    )
    provenance: GovernedVocabulary[RuntimeSecurityMonitoringSettingProvenance] = (
        RuntimeSecurityMonitoringSettingProvenance.UNKNOWN
    )
    source_path: str = ""
    description: str = ""

    @field_validator("setting_id")
    @classmethod
    def validate_setting_id(cls, v: str) -> str:
        return require_symbol(v, field_name="setting_id")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return require_non_empty(v, field_name="setting name")

    @field_validator("value_classification", mode="before")
    @classmethod
    def normalize_value_classification(
        cls,
        v: RuntimeSensitivityClassification | str,
    ) -> RuntimeSensitivityClassification | str:
        return parse_runtime_enum_or_var(v, RuntimeSensitivityClassification, field_name="value_classification")

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(
        cls,
        v: RuntimeSecurityMonitoringSettingProvenance | str,
    ) -> RuntimeSecurityMonitoringSettingProvenance | str:
        return parse_runtime_enum_or_var(v, RuntimeSecurityMonitoringSettingProvenance, field_name="provenance")

    @field_validator("source_path")
    @classmethod
    def validate_source_path(cls, v: str) -> str:
        return absolute_path_or_var(v, field_name="source_path") if v else v

    @model_validator(mode="after")
    def validate_redacted_value(self) -> "RuntimeSecurityMonitoringSetting":
        enforce_observed_value_redaction(
            owner_label=f"security-monitoring setting '{self.name}'",
            value=self.value,
            classification=self.value_classification,
            redacted_classifications=_REDACTED_SENSITIVITIES,
        )
        return self


class RuntimeSecurityMonitoringManager(SDLModel):
    """Node-scoped runtime inventory for a SIEM/security-monitoring manager."""

    security_monitoring_manager_id: str
    service: str = ""
    implementation: GovernedVocabulary[RuntimeSecurityMonitoringImplementation] = (
        RuntimeSecurityMonitoringImplementation.UNKNOWN
    )
    manager_kind: GovernedVocabulary[RuntimeSecurityMonitoringManagerKind] = (
        RuntimeSecurityMonitoringManagerKind.UNKNOWN
    )
    version: str = ""
    revision: str = ""
    name: str = ""
    configuration_file_refs: list[str] = Field(default_factory=list)
    log_file_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    listeners: list[RuntimeSecurityMonitoringListener] = Field(default_factory=list)
    components: list[RuntimeSecurityMonitoringComponent] = Field(default_factory=list)
    agents: list[RuntimeSecurityMonitoringAgent] = Field(default_factory=list)
    agent_groups: list[RuntimeSecurityMonitoringAgentGroup] = Field(default_factory=list)
    content_sets: list[RuntimeSecurityMonitoringContentSet] = Field(default_factory=list)
    detection_definitions: list[RuntimeSecurityMonitoringDetectionDefinition] = Field(default_factory=list)
    settings: list[RuntimeSecurityMonitoringSetting] = Field(default_factory=list)
    description: str = ""

    @field_validator("security_monitoring_manager_id")
    @classmethod
    def validate_security_monitoring_manager_id(cls, v: str) -> str:
        return require_symbol(v, field_name="security_monitoring_manager_id")

    @field_validator("implementation", mode="before")
    @classmethod
    def normalize_implementation(
        cls,
        v: RuntimeSecurityMonitoringImplementation | str,
    ) -> RuntimeSecurityMonitoringImplementation | str:
        return parse_runtime_enum_or_var(v, RuntimeSecurityMonitoringImplementation, field_name="implementation")

    @field_validator("manager_kind", mode="before")
    @classmethod
    def normalize_manager_kind(
        cls,
        v: RuntimeSecurityMonitoringManagerKind | str,
    ) -> RuntimeSecurityMonitoringManagerKind | str:
        return parse_runtime_enum_or_var(v, RuntimeSecurityMonitoringManagerKind, field_name="manager_kind")

    @field_validator("configuration_file_refs", "log_file_refs", "evidence_refs", mode="before")
    @classmethod
    def coerce_file_refs(cls, v: object) -> list[str]:
        return coerce_string_list(v)

    @field_validator("configuration_file_refs", "log_file_refs", "evidence_refs")
    @classmethod
    def validate_file_refs(cls, v: list[str], info: ValidationInfo) -> list[str]:
        return validate_absolute_paths(v, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_manager(self) -> "RuntimeSecurityMonitoringManager":
        _reject_duplicate_local_ref_ids(self)
        return self


def _reject_duplicate_local_ref_ids(manager: RuntimeSecurityMonitoringManager) -> None:
    entries: list[tuple[str, str]] = [("security_monitoring_manager_id", manager.security_monitoring_manager_id)]
    for label, collection_name in (
        ("listener_id", "listeners"),
        ("component_id", "components"),
        ("agent_id", "agents"),
        ("group_id", "agent_groups"),
        ("content_id", "content_sets"),
        ("definition_id", "detection_definitions"),
        ("setting_id", "settings"),
    ):
        entries.extend((label, getattr(item, label)) for item in getattr(manager, collection_name))

    seen: dict[str, str] = {}
    for label, value in entries:
        prior = seen.get(value)
        if prior is not None:
            raise ValueError(
                f"Duplicate runtime security-monitoring stable id '{value}' in manager "
                f"'{manager.security_monitoring_manager_id}' across {prior} and {label}"
            )
        seen[value] = label
