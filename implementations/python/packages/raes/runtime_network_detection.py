"""Network detection-engine runtime inventory models."""

from enum import Enum

from pydantic import Field, ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel, parse_int_or_var
from .runtime_values import (
    absolute_path_or_var,
    coerce_string_list,
    control_interface_path_or_var,
    parse_optional_bool_or_var,
    parse_runtime_enum_or_var,
    require_symbol,
    validate_absolute_paths,
)

__all__ = [
    "RuntimeNetworkDetectionAppProtocol",
    "RuntimeNetworkDetectionControlCapability",
    "RuntimeNetworkDetectionControlChannel",
    "RuntimeNetworkDetectionControlChannelKind",
    "RuntimeNetworkDetectionEngine",
    "RuntimeNetworkDetectionEngineImplementation",
    "RuntimeNetworkDetectionEngineKind",
    "RuntimeNetworkDetectionEventType",
    "RuntimeNetworkDetectionNetworkSet",
    "RuntimeNetworkDetectionNetworkSetKind",
    "RuntimeNetworkDetectionOutputFormat",
    "RuntimeNetworkDetectionOutputStream",
    "RuntimeNetworkDetectionRuleFormat",
    "RuntimeNetworkDetectionRuleSource",
    "RuntimeNetworkDetectionRuleSourceKind",
]


class RuntimeNetworkDetectionEngineImplementation(str, Enum):
    """Observed product family for a network detection engine."""

    SURICATA = "suricata"
    SNORT = "snort"
    ZEEK = "zeek"
    SECURITY_ONION = "security_onion"
    ARKIME = "arkime"
    CORELIGHT = "corelight"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeNetworkDetectionEngineKind(str, Enum):
    """Portable detection-engine role/family."""

    IDS = "ids"
    IPS = "ips"
    NDR = "ndr"
    NSM = "nsm"
    NTA = "nta"
    DETECTION_ENGINE = "detection_engine"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeNetworkDetectionAppProtocol(str, Enum):
    """App-layer parser family enabled in the detection engine."""

    HTTP = "http"
    TLS = "tls"
    DNS = "dns"
    SSH = "ssh"
    SMTP = "smtp"
    FTP = "ftp"
    SMB = "smb"
    HTTP2 = "http2"
    NFS = "nfs"
    RDP = "rdp"
    KRB5 = "krb5"
    MQTT = "mqtt"
    MODBUS = "modbus"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeNetworkDetectionRuleSourceKind(str, Enum):
    """Portable rule-source provenance/family."""

    BUILT_IN = "built_in"
    COMMUNITY = "community"
    MANAGED = "managed"
    LOCAL = "local"
    THREAT_INTEL = "threat_intel"
    IOC = "ioc"
    EMERGING_THREATS = "emerging_threats"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeNetworkDetectionRuleFormat(str, Enum):
    """Portable rule/content syntax family."""

    SURICATA_RULE = "suricata_rule"
    SNORT_RULE = "snort_rule"
    ZEEK_SCRIPT = "zeek_script"
    SIGMA = "sigma"
    YARA = "yara"
    STIX = "stix"
    JSON = "json"
    YAML = "yaml"
    TEXT = "text"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeNetworkDetectionNetworkSetKind(str, Enum):
    """Portable network/address-set variable role."""

    HOME_NET = "home_net"
    EXTERNAL_NET = "external_net"
    DMZ_NET = "dmz_net"
    INTERNAL_NET = "internal_net"
    SERVICE_GROUP = "service_group"
    CUSTOM = "custom"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeNetworkDetectionOutputFormat(str, Enum):
    """Portable detection output stream format."""

    EVE_JSON = "eve_json"
    FAST_LOG = "fast_log"
    JSON = "json"
    PCAP = "pcap"
    NETFLOW = "netflow"
    SYSLOG = "syslog"
    TEXT = "text"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeNetworkDetectionEventType(str, Enum):
    """Event family emitted by a detection output stream."""

    ALERT = "alert"
    HTTP = "http"
    DNS = "dns"
    TLS = "tls"
    SSH = "ssh"
    SMTP = "smtp"
    FTP = "ftp"
    SMB = "smb"
    FLOW = "flow"
    NETFLOW = "netflow"
    STATS = "stats"
    FILEINFO = "fileinfo"
    ANOMALY = "anomaly"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeNetworkDetectionControlChannelKind(str, Enum):
    """Portable local or remote control-channel family."""

    UNIX_SOCKET = "unix_socket"
    TCP_API = "tcp_api"
    HTTP_API = "http_api"
    CLI = "cli"
    SIGNAL = "signal"
    FILE_DROP = "file_drop"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeNetworkDetectionControlCapability(str, Enum):
    """Operation supported by a detection-engine control channel."""

    RULE_RELOAD = "rule_reload"
    RULESET_UPDATE = "ruleset_update"
    CONFIG_RELOAD = "config_reload"
    STATS_QUERY = "stats_query"
    PAUSE = "pause"
    RESUME = "resume"
    SHUTDOWN = "shutdown"
    UNKNOWN = "unknown"
    OTHER = "other"


def _reject_duplicate_values(values: list[object], *, field_name: str, owner: str) -> None:
    seen: set[object] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"Duplicate runtime network detection {field_name} entry on '{owner}'")
        seen.add(value)


class RuntimeNetworkDetectionRuleSource(SDLModel):
    """A loaded rule, IOC, script, or managed detection-content source."""

    source_id: str
    kind: GovernedVocabulary[RuntimeNetworkDetectionRuleSourceKind] = RuntimeNetworkDetectionRuleSourceKind.UNKNOWN
    format: GovernedVocabulary[RuntimeNetworkDetectionRuleFormat] = RuntimeNetworkDetectionRuleFormat.UNKNOWN
    name: str = ""
    rule_count: int | str | None = None
    file_refs: list[str] = Field(default_factory=list)
    generated_by: str = ""
    loaded: bool | str | None = None
    description: str = ""

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, v: str) -> str:
        return require_symbol(v, field_name="source_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeNetworkDetectionRuleSourceKind | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeNetworkDetectionRuleSourceKind, field_name="kind")

    @field_validator("format", mode="before")
    @classmethod
    def normalize_format(cls, v: RuntimeNetworkDetectionRuleFormat | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeNetworkDetectionRuleFormat, field_name="format")

    @field_validator("rule_count", mode="before")
    @classmethod
    def parse_rule_count(cls, v: object) -> int | str | None:
        return parse_int_or_var(v, minimum=0, field_name="rule_count") if v is not None else v

    @field_validator("file_refs", mode="before")
    @classmethod
    def coerce_file_refs(cls, v: object) -> object:
        return coerce_string_list(v)

    @field_validator("file_refs")
    @classmethod
    def validate_file_refs(cls, v: list[str]) -> list[str]:
        return validate_absolute_paths(v, field_name="file_refs")

    @field_validator("loaded", mode="before")
    @classmethod
    def parse_loaded(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="loaded")


class RuntimeNetworkDetectionNetworkSet(SDLModel):
    """A network zoning or service-group address-set variable."""

    set_id: str
    kind: GovernedVocabulary[RuntimeNetworkDetectionNetworkSetKind] = RuntimeNetworkDetectionNetworkSetKind.UNKNOWN
    name: str = ""
    selector_values: list[str] = Field(default_factory=list)
    network_refs: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("set_id")
    @classmethod
    def validate_set_id(cls, v: str) -> str:
        return require_symbol(v, field_name="set_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeNetworkDetectionNetworkSetKind | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeNetworkDetectionNetworkSetKind, field_name="kind")

    @field_validator("selector_values", "network_refs", mode="before")
    @classmethod
    def coerce_lists(cls, v: object) -> object:
        return coerce_string_list(v)

    @model_validator(mode="after")
    def validate_unique_values(self) -> "RuntimeNetworkDetectionNetworkSet":
        _reject_duplicate_values(self.selector_values, field_name="selector_values", owner=self.set_id)
        _reject_duplicate_values(self.network_refs, field_name="network_refs", owner=self.set_id)
        return self


class RuntimeNetworkDetectionOutputStream(SDLModel):
    """A detection alert, telemetry, or summary output stream."""

    stream_id: str
    format: GovernedVocabulary[RuntimeNetworkDetectionOutputFormat] = RuntimeNetworkDetectionOutputFormat.UNKNOWN
    path: str = ""
    event_types: list[GovernedVocabulary[RuntimeNetworkDetectionEventType]] = Field(default_factory=list)
    enabled: bool | str | None = None
    description: str = ""

    @field_validator("stream_id")
    @classmethod
    def validate_stream_id(cls, v: str) -> str:
        return require_symbol(v, field_name="stream_id")

    @field_validator("format", mode="before")
    @classmethod
    def normalize_format(cls, v: RuntimeNetworkDetectionOutputFormat | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeNetworkDetectionOutputFormat, field_name="format")

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        return absolute_path_or_var(v, field_name="path") if v else v

    @field_validator("event_types", mode="before")
    @classmethod
    def normalize_event_types(cls, v: object) -> object:
        values = coerce_string_list(v)
        if isinstance(values, list):
            return [
                parse_runtime_enum_or_var(item, RuntimeNetworkDetectionEventType, field_name="event_types")
                for item in values
            ]
        return values

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_enabled(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="enabled")

    @model_validator(mode="after")
    def validate_unique_events(self) -> "RuntimeNetworkDetectionOutputStream":
        _reject_duplicate_values(self.event_types, field_name="event_types", owner=self.stream_id)
        return self


class RuntimeNetworkDetectionControlChannel(SDLModel):
    """A bounded detection-engine control or reload channel."""

    channel_id: str
    kind: GovernedVocabulary[RuntimeNetworkDetectionControlChannelKind] = (
        RuntimeNetworkDetectionControlChannelKind.UNKNOWN
    )
    path: str = ""
    service: str = ""
    capabilities: list[GovernedVocabulary[RuntimeNetworkDetectionControlCapability]] = Field(default_factory=list)
    auth_required: bool | str | None = None
    description: str = ""

    @field_validator("channel_id")
    @classmethod
    def validate_channel_id(cls, v: str) -> str:
        return require_symbol(v, field_name="channel_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeNetworkDetectionControlChannelKind | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeNetworkDetectionControlChannelKind, field_name="kind")

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        return control_interface_path_or_var(v, field_name="path") if v else v

    @field_validator("capabilities", mode="before")
    @classmethod
    def normalize_capabilities(cls, v: object) -> object:
        values = coerce_string_list(v)
        if isinstance(values, list):
            return [
                parse_runtime_enum_or_var(item, RuntimeNetworkDetectionControlCapability, field_name="capabilities")
                for item in values
            ]
        return values

    @field_validator("auth_required", mode="before")
    @classmethod
    def parse_auth_required(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="auth_required")

    @model_validator(mode="after")
    def validate_unique_capabilities(self) -> "RuntimeNetworkDetectionControlChannel":
        _reject_duplicate_values(self.capabilities, field_name="capabilities", owner=self.channel_id)
        return self


class RuntimeNetworkDetectionEngine(SDLModel):
    """Node-scoped runtime inventory for an IDS/NDR detection engine."""

    network_detection_engine_id: str
    implementation: GovernedVocabulary[RuntimeNetworkDetectionEngineImplementation] = (
        RuntimeNetworkDetectionEngineImplementation.UNKNOWN
    )
    engine_kind: GovernedVocabulary[RuntimeNetworkDetectionEngineKind] = RuntimeNetworkDetectionEngineKind.UNKNOWN
    version: str = ""
    revision: str = ""
    name: str = ""
    process_ref: str = ""
    sensor_ref: str = ""
    configuration_file_refs: list[str] = Field(default_factory=list)
    log_file_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    app_layer_protocols: list[GovernedVocabulary[RuntimeNetworkDetectionAppProtocol]] = Field(default_factory=list)
    rule_sources: list[RuntimeNetworkDetectionRuleSource] = Field(default_factory=list)
    network_sets: list[RuntimeNetworkDetectionNetworkSet] = Field(default_factory=list)
    output_streams: list[RuntimeNetworkDetectionOutputStream] = Field(default_factory=list)
    control_channels: list[RuntimeNetworkDetectionControlChannel] = Field(default_factory=list)
    description: str = ""

    @field_validator("network_detection_engine_id")
    @classmethod
    def validate_network_detection_engine_id(cls, v: str) -> str:
        return require_symbol(v, field_name="network_detection_engine_id")

    @field_validator("implementation", mode="before")
    @classmethod
    def normalize_implementation(cls, v: RuntimeNetworkDetectionEngineImplementation | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeNetworkDetectionEngineImplementation, field_name="implementation")

    @field_validator("engine_kind", mode="before")
    @classmethod
    def normalize_engine_kind(cls, v: RuntimeNetworkDetectionEngineKind | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeNetworkDetectionEngineKind, field_name="engine_kind")

    @field_validator("configuration_file_refs", "log_file_refs", "evidence_refs", mode="before")
    @classmethod
    def coerce_file_refs(cls, v: object) -> object:
        return coerce_string_list(v)

    @field_validator("configuration_file_refs", "log_file_refs", "evidence_refs")
    @classmethod
    def validate_file_refs(cls, v: list[str], info: ValidationInfo) -> list[str]:
        return validate_absolute_paths(v, field_name=info.field_name)

    @field_validator("app_layer_protocols", mode="before")
    @classmethod
    def normalize_app_layer_protocols(cls, v: object) -> object:
        values = coerce_string_list(v)
        if isinstance(values, list):
            return [
                parse_runtime_enum_or_var(item, RuntimeNetworkDetectionAppProtocol, field_name="app_layer_protocols")
                for item in values
            ]
        return values

    @model_validator(mode="after")
    def validate_engine(self) -> "RuntimeNetworkDetectionEngine":
        _reject_duplicate_values(
            self.app_layer_protocols, field_name="app_layer_protocols", owner=self.network_detection_engine_id
        )
        _reject_duplicate_local_ref_ids(self)
        return self


def _reject_duplicate_local_ref_ids(engine: RuntimeNetworkDetectionEngine) -> None:
    entries: list[tuple[str, str]] = [("network_detection_engine_id", engine.network_detection_engine_id)]
    for label, collection_name in (
        ("source_id", "rule_sources"),
        ("set_id", "network_sets"),
        ("stream_id", "output_streams"),
        ("channel_id", "control_channels"),
    ):
        entries.extend((label, getattr(item, label)) for item in getattr(engine, collection_name))

    seen: dict[str, str] = {}
    for label, value in entries:
        prior = seen.get(value)
        if prior is not None:
            raise ValueError(
                f"Duplicate runtime network detection stable id '{value}' in engine "
                f"'{engine.network_detection_engine_id}' across {prior} and {label}"
            )
        seen[value] = label
