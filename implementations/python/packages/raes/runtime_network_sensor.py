"""Network-sensor runtime monitoring posture models."""

from enum import Enum

from pydantic import Field, ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel
from .runtime_values import (
    coerce_string_list,
    parse_runtime_enum_or_var,
    require_symbol,
    validate_absolute_paths,
)

__all__ = [
    "RuntimeNetworkSensor",
    "RuntimeNetworkSensorCaptureMode",
    "RuntimeNetworkSensorImplementation",
    "RuntimeNetworkSensorKind",
    "RuntimeNetworkSensorMonitoringPosture",
]


class RuntimeNetworkSensorImplementation(str, Enum):
    """Observed product family for a network sensor."""

    SURICATA = "suricata"
    SNORT = "snort"
    ZEEK = "zeek"
    TCPDUMP = "tcpdump"
    SECURITY_ONION = "security_onion"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeNetworkSensorKind(str, Enum):
    """Portable network-sensor function."""

    IDS = "ids"
    IPS = "ips"
    NSM = "nsm"
    NDR = "ndr"
    PACKET_CAPTURE = "packet_capture"
    FLOW_COLLECTOR = "flow_collector"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeNetworkSensorMonitoringPosture(str, Enum):
    """Whether the sensor observes passively, inline, or locally."""

    PASSIVE = "passive"
    INLINE = "inline"
    HOST_LOCAL = "host_local"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeNetworkSensorCaptureMode(str, Enum):
    """Portable capture mechanism family for an observed sensor."""

    PCAP = "pcap"
    AF_PACKET = "af_packet"
    NFQUEUE = "nfqueue"
    NETMAP = "netmap"
    DPDK = "dpdk"
    FLOW = "flow"
    UNKNOWN = "unknown"
    OTHER = "other"


def _reject_duplicate_values(values: list[str], *, field_name: str, sensor_id: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"Duplicate runtime network sensor {field_name} entry on sensor '{sensor_id}'")
        seen.add(value)


class RuntimeNetworkSensor(SDLModel):
    """Node-scoped runtime inventory for a passive or inline network sensor."""

    network_sensor_id: str
    implementation: GovernedVocabulary[RuntimeNetworkSensorImplementation] = RuntimeNetworkSensorImplementation.UNKNOWN
    sensor_kind: GovernedVocabulary[RuntimeNetworkSensorKind] = RuntimeNetworkSensorKind.UNKNOWN
    monitoring_posture: GovernedVocabulary[RuntimeNetworkSensorMonitoringPosture] = (
        RuntimeNetworkSensorMonitoringPosture.UNKNOWN
    )
    capture_mode: GovernedVocabulary[RuntimeNetworkSensorCaptureMode] = RuntimeNetworkSensorCaptureMode.UNKNOWN
    capture_interfaces: list[str] = Field(default_factory=list)
    monitored_network_refs: list[str] = Field(default_factory=list)
    process_ref: str = ""
    version: str = ""
    revision: str = ""
    name: str = ""
    configuration_file_refs: list[str] = Field(default_factory=list)
    log_file_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("network_sensor_id")
    @classmethod
    def validate_network_sensor_id(cls, v: str) -> str:
        return require_symbol(v, field_name="network_sensor_id")

    @field_validator("implementation", mode="before")
    @classmethod
    def normalize_implementation(
        cls,
        v: RuntimeNetworkSensorImplementation | str,
    ) -> RuntimeNetworkSensorImplementation | str:
        return parse_runtime_enum_or_var(v, RuntimeNetworkSensorImplementation, field_name="implementation")

    @field_validator("sensor_kind", mode="before")
    @classmethod
    def normalize_sensor_kind(cls, v: RuntimeNetworkSensorKind | str) -> RuntimeNetworkSensorKind | str:
        return parse_runtime_enum_or_var(v, RuntimeNetworkSensorKind, field_name="sensor_kind")

    @field_validator("monitoring_posture", mode="before")
    @classmethod
    def normalize_monitoring_posture(
        cls,
        v: RuntimeNetworkSensorMonitoringPosture | str,
    ) -> RuntimeNetworkSensorMonitoringPosture | str:
        return parse_runtime_enum_or_var(v, RuntimeNetworkSensorMonitoringPosture, field_name="monitoring_posture")

    @field_validator("capture_mode", mode="before")
    @classmethod
    def normalize_capture_mode(
        cls,
        v: RuntimeNetworkSensorCaptureMode | str,
    ) -> RuntimeNetworkSensorCaptureMode | str:
        return parse_runtime_enum_or_var(v, RuntimeNetworkSensorCaptureMode, field_name="capture_mode")

    @field_validator("capture_interfaces", "monitored_network_refs", mode="before")
    @classmethod
    def coerce_ref_lists(cls, v: object) -> object:
        return coerce_string_list(v)

    @field_validator("configuration_file_refs", "log_file_refs", "evidence_refs", mode="before")
    @classmethod
    def coerce_file_refs(cls, v: object) -> object:
        return coerce_string_list(v)

    @field_validator("configuration_file_refs", "log_file_refs", "evidence_refs")
    @classmethod
    def validate_file_refs(cls, v: list[str], info: ValidationInfo) -> list[str]:
        return validate_absolute_paths(v, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_unique_refs(self) -> "RuntimeNetworkSensor":
        _reject_duplicate_values(
            self.capture_interfaces,
            field_name="capture_interfaces",
            sensor_id=self.network_sensor_id,
        )
        _reject_duplicate_values(
            self.monitored_network_refs,
            field_name="monitored_network_refs",
            sensor_id=self.network_sensor_id,
        )
        return self
