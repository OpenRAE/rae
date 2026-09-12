"""Observed generic service-listener runtime inventory models for SDL nodes.

These models record in-node listener facts: transport, bind endpoint, scope,
owning service/process, evidence, and optional correlation to host-published
ports. They deliberately do not redefine ``Node.services`` or
``runtime.network.published_ports``.
"""

from __future__ import annotations

import ipaddress
import re
from enum import Enum
from typing import Any

from pydantic import Field, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel, is_variable_ref, parse_int_or_var
from .runtime_values import (
    coerce_string_list,
    ip_address_or_var,
    parse_runtime_enum_or_var,
    require_symbol,
)

__all__ = [
    "RuntimeListenerAddressFamily",
    "RuntimeListenerProvenance",
    "RuntimeListenerProtocol",
    "RuntimeListenerReadiness",
    "RuntimeListenerScope",
    "RuntimePublishedPortRef",
    "RuntimeServiceListener",
]

_MIN_PORT = 1
_MAX_PORT = 65535
_HOSTNAME_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_INTERFACE_NAME = re.compile(r"^[A-Za-z0-9_.:@-]+$")


class RuntimeListenerProtocol(str, Enum):
    """Transport or IPC family for an observed listener."""

    TCP = "tcp"
    UDP = "udp"
    SCTP = "sctp"
    UNIX = "unix"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeListenerAddressFamily(str, Enum):
    """Address family observed for a runtime listener."""

    IPV4 = "ipv4"
    IPV6 = "ipv6"
    UNIX = "unix"
    UNSPECIFIED = "unspecified"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeListenerScope(str, Enum):
    """Reachability class of the bind endpoint in the node namespace."""

    WILDCARD = "wildcard"
    LOOPBACK_ONLY = "loopback_only"
    NETWORK_FACING = "network_facing"
    NODE_LOCAL = "node_local"
    LOCAL_SOCKET = "local_socket"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeListenerProvenance(str, Enum):
    """Source class for an observed runtime listener fact."""

    OSQUERY = "osquery"
    SS = "ss"
    NETSTAT = "netstat"
    LSOF = "lsof"
    NMAP = "nmap"
    DOCKER_INSPECT = "docker_inspect"
    KUBERNETES = "kubernetes"
    SYSTEMD = "systemd"
    OPERATOR = "operator"
    SCANNER = "scanner"
    UNKNOWN = "unknown"
    OTHER = "other"


def _value(value: object) -> object:
    return value.value if isinstance(value, Enum) else value


def _is_concrete(value: object) -> bool:
    return value not in (None, "") and not is_variable_ref(value)


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not _is_concrete(value) or value == "*":
        return None
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _listener_address_or_var(value: str, *, field_name: str) -> str:
    if not value or is_variable_ref(value):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if any(ch.isspace() for ch in value):
        raise ValueError(f"{field_name} must not contain whitespace")
    if value == "*":
        return value
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    if all(_HOSTNAME_LABEL.fullmatch(label) for label in value.split(".")):
        return value
    raise ValueError(f"{field_name} must be '*', an IP address, or a hostname")


def _socket_path_or_var(value: str, *, field_name: str) -> str:
    if not value or is_variable_ref(value):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if value.startswith("/") or value.startswith("@"):
        return value
    raise ValueError(f"{field_name} must be an absolute Unix socket path or abstract socket name")


def _bind_interface_or_var(value: str, *, field_name: str) -> str:
    if not value or is_variable_ref(value):
        return value
    if not isinstance(value, str) or not _INTERFACE_NAME.fullmatch(value):
        raise ValueError(f"{field_name} must be an interface name without whitespace")
    return value


class RuntimePublishedPortRef(SDLModel):
    """Typed reference to an observed host-published port binding.

    ``RuntimePublishedPort`` currently has no stable id, so the tuple is the
    reference shape used by semantic validation.
    """

    container_port: int | str
    protocol: str = "tcp"
    host_ip: str = ""
    host_port: int | str | None = None

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


class RuntimeListenerReadiness(SDLModel):
    """Optional readiness/probe evidence for an observed listener."""

    probe: str = ""
    criteria: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def coerce_evidence_refs(cls, v: Any) -> list[str]:
        return coerce_string_list(v)


class RuntimeServiceListener(SDLModel):
    """Observed generic runtime listener attached to a node."""

    service_listener_id: str
    service: str = ""
    address: str = ""
    port: int | str | None = None
    protocol: GovernedVocabulary[RuntimeListenerProtocol] = RuntimeListenerProtocol.TCP
    address_family: GovernedVocabulary[RuntimeListenerAddressFamily] = RuntimeListenerAddressFamily.UNSPECIFIED
    scope: GovernedVocabulary[RuntimeListenerScope] = RuntimeListenerScope.UNKNOWN
    bind_interface: str = ""
    socket_path: str = ""
    process_ref: str = ""
    process_name: str = ""
    published_port_refs: list[RuntimePublishedPortRef] = Field(default_factory=list)
    readiness: RuntimeListenerReadiness | None = None
    provenance: GovernedVocabulary[RuntimeListenerProvenance] = RuntimeListenerProvenance.UNKNOWN
    evidence_refs: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("service_listener_id")
    @classmethod
    def validate_service_listener_id(cls, v: str) -> str:
        return require_symbol(v, field_name="service_listener_id")

    @field_validator("port", mode="before")
    @classmethod
    def parse_port(cls, v: int | str | None) -> int | str | None:
        if v is None:
            return v
        return parse_int_or_var(v, minimum=_MIN_PORT, maximum=_MAX_PORT, field_name="listener port")

    @field_validator("protocol", mode="before")
    @classmethod
    def normalize_protocol(cls, v: RuntimeListenerProtocol | str) -> RuntimeListenerProtocol | str:
        return parse_runtime_enum_or_var(v, RuntimeListenerProtocol, field_name="protocol")

    @field_validator("address_family", mode="before")
    @classmethod
    def normalize_address_family(
        cls,
        v: RuntimeListenerAddressFamily | str,
    ) -> RuntimeListenerAddressFamily | str:
        return parse_runtime_enum_or_var(v, RuntimeListenerAddressFamily, field_name="address_family")

    @field_validator("scope", mode="before")
    @classmethod
    def normalize_scope(cls, v: RuntimeListenerScope | str) -> RuntimeListenerScope | str:
        return parse_runtime_enum_or_var(v, RuntimeListenerScope, field_name="scope")

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(
        cls,
        v: RuntimeListenerProvenance | str,
    ) -> RuntimeListenerProvenance | str:
        return parse_runtime_enum_or_var(v, RuntimeListenerProvenance, field_name="provenance")

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        return _listener_address_or_var(v, field_name="address")

    @field_validator("socket_path")
    @classmethod
    def validate_socket_path(cls, v: str) -> str:
        return _socket_path_or_var(v, field_name="socket_path")

    @field_validator("bind_interface")
    @classmethod
    def validate_bind_interface(cls, v: str) -> str:
        return _bind_interface_or_var(v, field_name="bind_interface")

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def coerce_evidence_refs(cls, v: Any) -> list[str]:
        return coerce_string_list(v)

    @model_validator(mode="after")
    def validate_listener_shape(self) -> RuntimeServiceListener:
        protocol = _value(self.protocol)
        if protocol == RuntimeListenerProtocol.UNIX.value:
            self._validate_unix_listener()
        else:
            self._validate_network_listener()
        self._validate_address_family()
        self._validate_scope()
        self._validate_published_refs()
        return self

    def _validate_unix_listener(self) -> None:
        if not self.socket_path:
            raise ValueError("Unix listeners require socket_path")
        if self.port is not None:
            raise ValueError("Unix listeners must not set port")
        if self.address:
            raise ValueError("Unix listeners must not set address")
        scope = _value(self.scope)
        if scope not in {RuntimeListenerScope.LOCAL_SOCKET.value, RuntimeListenerScope.UNKNOWN.value}:
            raise ValueError(f"scope '{scope}' contradicts Unix socket listener")

    def _validate_network_listener(self) -> None:
        if self.socket_path:
            raise ValueError("Network listeners must not set socket_path")
        if self.port is None:
            raise ValueError("Network listeners require port")
        if not self.address and not self.bind_interface:
            raise ValueError("Network listeners require address or bind_interface")

    def _validate_address_family(self) -> None:
        family = _value(self.address_family)
        protocol = _value(self.protocol)
        if is_variable_ref(family) or family in {RuntimeListenerAddressFamily.UNSPECIFIED.value, "other"}:
            return
        if protocol == RuntimeListenerProtocol.UNIX.value:
            if family != RuntimeListenerAddressFamily.UNIX.value:
                raise ValueError(f"address_family '{family}' contradicts Unix socket listener")
            return
        if family == RuntimeListenerAddressFamily.UNIX.value:
            raise ValueError(f"address_family '{family}' contradicts network listener")
        ip = _parse_ip(self.address)
        if ip is None:
            return
        expected = (
            RuntimeListenerAddressFamily.IPV4.value if ip.version == 4 else RuntimeListenerAddressFamily.IPV6.value
        )
        if family != expected:
            raise ValueError(f"address_family '{family}' contradicts address '{self.address}'")

    def _validate_scope(self) -> None:
        scope = _value(self.scope)
        if is_variable_ref(scope) or scope in {RuntimeListenerScope.UNKNOWN.value, RuntimeListenerScope.OTHER.value}:
            return
        protocol = _value(self.protocol)
        if protocol != RuntimeListenerProtocol.UNIX.value and scope == RuntimeListenerScope.LOCAL_SOCKET.value:
            raise ValueError("scope 'local_socket' requires Unix socket listener")
        ip = _parse_ip(self.address)
        is_wildcard = self.address == "*" or (ip is not None and ip.is_unspecified)
        is_loopback = self.address == "localhost" or (ip is not None and ip.is_loopback)
        if is_wildcard and scope != RuntimeListenerScope.WILDCARD.value:
            raise ValueError(f"scope '{scope}' contradicts wildcard address '{self.address}'")
        if is_loopback and scope == RuntimeListenerScope.NETWORK_FACING.value:
            raise ValueError(f"scope '{scope}' contradicts loopback address '{self.address}'")
        if ip is not None and not ip.is_loopback and scope == RuntimeListenerScope.LOOPBACK_ONLY.value:
            raise ValueError(f"scope '{scope}' contradicts non-loopback address '{self.address}'")

    def _validate_published_refs(self) -> None:
        seen: set[tuple[str, int | str | None, int | str, str]] = set()
        for ref in self.published_port_refs:
            key = (ref.host_ip, ref.host_port, ref.container_port, ref.protocol)
            if key in seen:
                raise ValueError("Duplicate published_port_refs entry")
            seen.add(key)
