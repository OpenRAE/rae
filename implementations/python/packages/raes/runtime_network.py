"""Declarative container network contract models for SDL nodes.

Values authored here are exact, constrained, or explicitly open scenario
requirements. Generated backend identifiers and harness-only observations
belong in evidence records instead.
"""

import re
from enum import Enum
from typing import Any

from pydantic import Field, ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import (
    SDLModel,
    is_variable_ref,
    parse_int_or_var,
)
from .runtime_values import (
    coerce_string_list,
    ip_address_or_var,
    parse_runtime_enum_or_var,
)

__all__ = [
    "RuntimeNetworkBackendDetail",
    "RuntimeNetworkDriver",
    "RuntimeNetworkEndpoint",
    "RuntimeNetworkRealization",
    "RuntimePublishedPort",
]

_MAC_ADDRESS_RE = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")
# IPv6 endpoints carry prefix lengths up to 128; IPv4 up to 32.
_MAX_IP_PREFIX_LENGTH = 128
_MIN_PORT = 1
_MAX_PORT = 65535


class RuntimeNetworkDriver(str, Enum):
    """Backend network driver class required by the scenario."""

    BRIDGE = "bridge"
    OVERLAY = "overlay"
    HOST = "host"
    IPVLAN = "ipvlan"
    MACVLAN = "macvlan"
    NONE = "none"
    OTHER = "other"
    UNKNOWN = "unknown"


def _mac_address_or_var(value: str, *, field_name: str) -> str:
    """Validate a required MAC address, allowing empty and ``${var}`` values."""
    if not value or is_variable_ref(value):
        return value
    if not isinstance(value, str) or not _MAC_ADDRESS_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a colon-separated MAC address")
    return value


class RuntimeNetworkBackendDetail(SDLModel):
    """Required backend network driver and IPAM detail for an endpoint's network.

    ``driver_options`` and ``ipam_options`` are the bounded extension seam for
    backend-native key/value facts; raw backend inspect payloads are not stored.
    """

    driver: GovernedVocabulary[RuntimeNetworkDriver] = RuntimeNetworkDriver.OTHER
    ipam_driver: str = ""
    driver_options: dict[str, str] = Field(default_factory=dict)
    ipam_options: dict[str, str] = Field(default_factory=dict)
    description: str = ""

    @field_validator("driver", mode="before")
    @classmethod
    def normalize_driver(cls, v: RuntimeNetworkDriver | str) -> RuntimeNetworkDriver | str:
        return parse_runtime_enum_or_var(v, RuntimeNetworkDriver, field_name="driver")


class RuntimePublishedPort(SDLModel):
    """A required host-published port binding for a container endpoint.

    Host IP, host port, container port, and protocol are kept distinct; this is
    a runtime/host exposure fact, not a node service declaration (ADR-025).
    """

    container_port: int | str
    protocol: str = "tcp"
    host_ip: str = ""
    host_port: int | str | None = None
    description: str = ""

    @field_validator("container_port", mode="before")
    @classmethod
    def parse_container_port(cls, v: int | str) -> int | str:
        return parse_int_or_var(v, minimum=_MIN_PORT, maximum=_MAX_PORT, field_name="container_port")

    @field_validator("host_port", mode="before")
    @classmethod
    def parse_host_port(cls, v: int | str | None) -> int | str | None:
        if v is None:
            return v
        return parse_int_or_var(v, minimum=_MIN_PORT, maximum=_MAX_PORT, field_name="host_port")

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        if is_variable_ref(v):
            return v
        if not isinstance(v, str) or not v.strip():
            raise ValueError("protocol must be a non-empty string")
        return v.strip().lower()

    @field_validator("host_ip")
    @classmethod
    def validate_host_ip(cls, v: str) -> str:
        return ip_address_or_var(v, field_name="host_ip")


class RuntimeNetworkEndpoint(SDLModel):
    """A required container network attachment.

    ``network`` references a declared switch-backed infrastructure network by
    name. Runtime-generated identifiers and names are capture evidence, not
    declaration identity.
    """

    network: str
    ip_address: str = ""
    ip_prefix_length: int | str | None = None
    gateway: str = ""
    mac_address: str = ""
    aliases: list[str] = Field(default_factory=list)
    dns_names: list[str] = Field(default_factory=list)
    backend: RuntimeNetworkBackendDetail | None = None
    description: str = ""

    @field_validator("network")
    @classmethod
    def validate_network(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("network must be a non-empty string")
        return v

    @field_validator("ip_address", "gateway")
    @classmethod
    def validate_addresses(cls, v: str, info: ValidationInfo) -> str:
        return ip_address_or_var(v, field_name=info.field_name)

    @field_validator("ip_prefix_length", mode="before")
    @classmethod
    def parse_ip_prefix_length(cls, v: int | str | None) -> int | str | None:
        if v is None:
            return v
        return parse_int_or_var(v, minimum=0, maximum=_MAX_IP_PREFIX_LENGTH, field_name="ip_prefix_length")

    @field_validator("mac_address")
    @classmethod
    def validate_mac_address(cls, v: str) -> str:
        return _mac_address_or_var(v, field_name="mac_address")

    @field_validator("aliases", "dns_names", mode="before")
    @classmethod
    def coerce_name_lists(cls, v: Any) -> list[str]:
        return coerce_string_list(v)

    @model_validator(mode="after")
    def validate_unique_names(self) -> "RuntimeNetworkEndpoint":
        for field_name in ("aliases", "dns_names"):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate runtime network {field_name} entry on endpoint '{self.network}'")
        return self


class RuntimeNetworkRealization(SDLModel):
    """Declarative container network state for a node.

    ``hostname`` and ``domainname`` are required container network identities,
    kept distinct from per-network aliases and DNS names.
    """

    hostname: str = ""
    domainname: str = ""
    endpoints: list[RuntimeNetworkEndpoint] = Field(default_factory=list)
    published_ports: list[RuntimePublishedPort] = Field(default_factory=list)
    description: str = ""

    @model_validator(mode="after")
    def validate_unique_network_records(self) -> "RuntimeNetworkRealization":
        seen_networks: set[str] = set()
        for endpoint in self.endpoints:
            if endpoint.network in seen_networks:
                raise ValueError(f"Duplicate runtime network endpoint for network '{endpoint.network}'")
            seen_networks.add(endpoint.network)

        seen_bindings: set[tuple[str, int | str, str]] = set()
        for binding in self.published_ports:
            if binding.host_port is None:
                continue
            key = (binding.host_ip, binding.host_port, binding.protocol)
            if key in seen_bindings:
                raise ValueError(
                    f"Duplicate host-published binding for {binding.host_ip or '*'}:"
                    f"{binding.host_port}/{binding.protocol}"
                )
            seen_bindings.add(key)
        return self
