"""Declarative container runtime requirements for SDL nodes."""

import re
from typing import Any

from pydantic import ConfigDict, Field, ValidationInfo, field_validator, model_validator

from raes.runtime_filesystem import flagged_raw_value_schema

from ._base import SDLModel, is_variable_ref, parse_bool_or_var
from .runtime_values import (
    absolute_path_or_var,
    coerce_string_list,
    parse_optional_bool_or_var,
    parse_ram,
    validate_absolute_paths,
)


class RuntimeNetworkNamespace(SDLModel):
    """A request to use the exact network namespace owned by another node."""

    target_node_ref: str

    @field_validator("target_node_ref")
    @classmethod
    def validate_target_node_ref(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("target_node_ref must be a non-empty node reference")
        return v


class RuntimeNamespaceConfiguration(SDLModel):
    """Required namespace modes for a runtime node or container."""

    cgroup: str = ""
    ipc: str = ""
    network: RuntimeNetworkNamespace | None = None
    pid: str = ""
    userns: str = ""
    uts: str = ""


class RuntimeDeviceMapping(SDLModel):
    """A host device mapping required in runtime configuration."""

    host_path: str
    container_path: str
    permissions: str = ""
    description: str = ""

    @field_validator("host_path", "container_path")
    @classmethod
    def validate_device_path(cls, v: str, info: ValidationInfo) -> str:
        return absolute_path_or_var(v, field_name=info.field_name)


class RuntimeExtraHost(SDLModel):
    """A required extra host mapping in runtime configuration."""

    hostname: str
    address: str
    description: str = ""

    @field_validator("hostname", "address")
    @classmethod
    def validate_non_empty(cls, v: str, info: ValidationInfo) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string")
        return v


class RuntimeInitProcess(SDLModel):
    """Required backend-injected container init / PID-1 reaper configuration.

    Models authored container runtime intent — for example Docker Compose
    ``init: true`` causing PID 1 to be ``/sbin/docker-init`` (tini). This is
    distinct from the observed PID-1 process recorded in
    ``runtime.processes``; see ADR-027.
    """

    model_config = ConfigDict(
        json_schema_extra=flagged_raw_value_schema(flag_field="argv_redacted", raw_field="argv", array=True)
    )

    enabled: bool | str | None = None
    implementation: str = ""
    executable_path: str = ""
    reaps_children: bool | str | None = None
    argv: list[str] = Field(default_factory=list)
    argv_redacted: bool | str = False
    description: str = ""

    @field_validator("enabled", "reaps_children", mode="before")
    @classmethod
    def parse_optional_init_flags(cls, v: bool | str | None, info: ValidationInfo) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name=info.field_name)

    @field_validator("argv_redacted", mode="before")
    @classmethod
    def parse_argv_redacted(cls, v: bool | str) -> bool | str:
        return parse_bool_or_var(v, field_name="argv_redacted")

    @field_validator("argv", mode="before")
    @classmethod
    def normalize_argv(cls, v: Any) -> list[str]:
        return coerce_string_list(v)

    @field_validator("executable_path")
    @classmethod
    def validate_executable_path(cls, v: str, info: ValidationInfo) -> str:
        if not v:
            return v
        return absolute_path_or_var(v, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_redacted_argv(self) -> "RuntimeInitProcess":
        if self.argv_redacted is True and self.argv:
            raise ValueError("redacted init process argv must omit argv")
        return self


# Recognized Docker/Compose spellings of a seccomp security option (`seccomp:value`
# or `seccomp=value`). Used only for the seccomp_profile/security_opt consistency
# check; it does not turn the option list into a typed Docker dialect.
_SECCOMP_OPTION_RE = re.compile(r"^seccomp[:=](.+)$", re.IGNORECASE)


def _seccomp_values_from_security_opt(security_opt: list[str]) -> list[str]:
    """Extract seccomp profile values from recognized ``security_opt`` entries."""
    values: list[str] = []
    for option in security_opt:
        match = _SECCOMP_OPTION_RE.match(option)
        if match:
            values.append(match.group(1).strip())
    return values


class RuntimeContainerConfiguration(SDLModel):
    """Required container runtime host and security configuration facts."""

    entrypoint: list[str] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
    log_driver: str = ""
    log_options: dict[str, str] = Field(default_factory=dict)
    namespaces: RuntimeNamespaceConfiguration | None = None
    privileged: bool | str | None = None
    read_only_rootfs: bool | str | None = None
    publish_all_ports: bool | str | None = None
    autoremove: bool | str | None = None
    shm_size: int | str | None = None
    masked_paths: list[str] = Field(default_factory=list)
    read_only_paths: list[str] = Field(default_factory=list)
    cgroup_parent: str = ""
    runtime_name: str = ""
    init_process: RuntimeInitProcess | None = None
    devices: list[RuntimeDeviceMapping] = Field(default_factory=list)
    device_cgroup_rules: list[str] = Field(default_factory=list)
    seccomp_profile: str = ""
    security_opt: list[str] = Field(default_factory=list)
    extra_hosts: list[RuntimeExtraHost] = Field(default_factory=list)
    dns: list[str] = Field(default_factory=list)
    dns_options: list[str] = Field(default_factory=list)
    dns_search: list[str] = Field(default_factory=list)
    group_add: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("entrypoint", "command", mode="before")
    @classmethod
    def normalize_command_list(cls, v: Any) -> list[str]:
        return coerce_string_list(v)

    @field_validator(
        "masked_paths",
        "read_only_paths",
        "device_cgroup_rules",
        "security_opt",
        "dns",
        "dns_options",
        "dns_search",
        "group_add",
        mode="before",
    )
    @classmethod
    def normalize_string_lists(cls, v: Any) -> list[str]:
        return coerce_string_list(v)

    @field_validator("privileged", "read_only_rootfs", "publish_all_ports", "autoremove", mode="before")
    @classmethod
    def parse_optional_flags(cls, v: bool | str | None, info: ValidationInfo) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name=info.field_name)

    @field_validator("shm_size", mode="before")
    @classmethod
    def parse_shm_size(cls, v: int | str | None) -> int | str | None:
        return parse_ram(v) if v is not None else v

    @field_validator("masked_paths", "read_only_paths")
    @classmethod
    def validate_path_lists(cls, v: list[str], info: ValidationInfo) -> list[str]:
        return validate_absolute_paths(v, field_name=info.field_name)

    @field_validator("security_opt")
    @classmethod
    def validate_security_opt(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        for option in v:
            if not isinstance(option, str) or not option.strip():
                raise ValueError("security_opt entries must be non-empty strings")
            if option in seen:
                raise ValueError(f"Duplicate runtime security option '{option}'")
            seen.add(option)
        return v

    @model_validator(mode="after")
    def validate_seccomp_consistency(self) -> "RuntimeContainerConfiguration":
        observed: set[str] = set()
        if self.seccomp_profile and not is_variable_ref(self.seccomp_profile):
            observed.add(self.seccomp_profile)
        for value in _seccomp_values_from_security_opt(self.security_opt):
            if value and not is_variable_ref(value):
                observed.add(value)
        if len(observed) > 1:
            raise ValueError(
                "seccomp_profile and security_opt seccomp entries disagree: " + ", ".join(sorted(observed))
            )
        return self

    @model_validator(mode="after")
    def validate_unique_container_entries(self) -> "RuntimeContainerConfiguration":
        seen_devices: set[tuple[str, str]] = set()
        for device in self.devices:
            key = (device.host_path, device.container_path)
            if key in seen_devices:
                raise ValueError(f"Duplicate runtime device mapping '{device.host_path}:{device.container_path}'")
            seen_devices.add(key)

        seen_hosts: set[str] = set()
        for host in self.extra_hosts:
            if host.hostname in seen_hosts:
                raise ValueError(f"Duplicate runtime extra host '{host.hostname}'")
            seen_hosts.add(host.hostname)
        return self
