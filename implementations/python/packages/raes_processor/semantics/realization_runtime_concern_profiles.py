"""Typed profiles and exhaustive ownership for RuntimeConfiguration concerns.

The canonical registry in :mod:`realization_concerns` consumes these profiles;
they are split out only to keep that registry below the repository source-file
size limit.  No backend or compiler consumes this module directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import get_args

from pydantic import BaseModel
from raes.runtime_configuration import RuntimeConfiguration

RUNTIME_NON_REALIZATION_FIELDS = frozenset({"description", "evidence_refs", "readiness"})


@dataclass(frozen=True)
class RuntimeConcernProfile:
    """One typed runtime path added to the canonical concern registry."""

    authored_path: tuple[str, ...]
    concern_kind: str
    excluded_fields: frozenset[str] = frozenset()
    sort_scalar_sequence: bool = False
    collection_identity_fields: tuple[str, ...] = ()

    @property
    def payload_path(self) -> tuple[str, ...]:
        return ("spec", "node", "runtime", *self.authored_path)


@dataclass(frozen=True)
class RuntimeFieldBoundary:
    """The complete SEM-218 disposition for one RuntimeConfiguration field."""

    field_name: str
    concern_kinds: tuple[str, ...]
    semantic_owner: str = "canonical-runtime-realization-concern"
    enforcement_status: str = "registered-fail-closed"
    delegated_paths: tuple[str, ...] = ()
    observation_only_paths: tuple[str, ...] = ()


def _profile(
    path: str,
    kind: str,
    *,
    excluded: tuple[str, ...] = (),
    sort_scalars: bool = False,
    identity: tuple[str, ...] = (),
) -> RuntimeConcernProfile:
    return RuntimeConcernProfile(
        authored_path=tuple(path.split(".")),
        concern_kind=kind,
        excluded_fields=frozenset(excluded),
        sort_scalar_sequence=sort_scalars,
        collection_identity_fields=identity,
    )


_CONTAINER_SCALAR_COLLECTIONS = frozenset(
    {
        "masked_paths",
        "read_only_paths",
        "device_cgroup_rules",
        "security_opt",
        "dns",
        "dns_options",
        "dns_search",
        "group_add",
    }
)
_CONTAINER_PATHS = (
    "entrypoint",
    "command",
    "log_driver",
    "log_options",
    "namespaces",
    "privileged",
    "read_only_rootfs",
    "publish_all_ports",
    "autoremove",
    "shm_size",
    "masked_paths",
    "read_only_paths",
    "cgroup_parent",
    "runtime_name",
    "init_process",
    "devices",
    "device_cgroup_rules",
    "seccomp_profile",
    "security_opt",
    "extra_hosts",
    "dns",
    "dns_options",
    "dns_search",
    "group_add",
)


RUNTIME_CONCERN_PROFILES: tuple[RuntimeConcernProfile, ...] = (
    _profile("filesystem_inventory", "runtime-filesystem-inventory"),
    _profile("local_control_interfaces", "runtime-local-control-interfaces"),
    _profile("processes", "runtime-processes"),
    _profile("operational_policy.restart", "runtime-restart-policy"),
    _profile("operational_policy.resource_limits.memory", "runtime-node-memory-limit"),
    _profile("operational_policy.resource_limits.memory_swap", "runtime-node-memory-swap-limit"),
    _profile("operational_policy.resource_limits.cpu", "runtime-node-cpu-limit"),
    _profile("operational_policy.resource_limits.pids", "runtime-node-pids-limit"),
    *(
        _profile(
            f"container.{field}",
            f"runtime-container-{field.replace('_', '-')}",
            sort_scalars=field in _CONTAINER_SCALAR_COLLECTIONS,
        )
        for field in _CONTAINER_PATHS
    ),
    _profile("local_identity", "runtime-local-identity", excluded=("raw_entry",)),
    _profile("identity_authorities", "runtime-identity-authorities"),
    _profile("file_services", "runtime-file-services", excluded=("access_observations",)),
    _profile("mail_services", "runtime-mail-services", excluded=("message_count",)),
    _profile("network.hostname", "runtime-network-hostname"),
    _profile("network.domainname", "runtime-network-domainname"),
    _profile("network.endpoints", "runtime-network-endpoints"),
    _profile("applications", "runtime-applications"),
    _profile("database_services", "runtime-database-services", identity=("database_service_id",)),
    _profile("dns_services", "runtime-dns-services"),
    _profile("network_sensors", "runtime-network-sensors"),
    _profile("network_detection_engines", "runtime-network-detection-engines", excluded=("loaded",)),
    _profile(
        "security_monitoring_managers",
        "runtime-security-monitoring-managers",
        excluded=("status", "loaded"),
    ),
    _profile("ssh_servers", "runtime-ssh-servers"),
    _profile(
        "datastore_services",
        "runtime-datastore-services",
        excluded=(
            "doc_count",
            "doc_count_deleted",
            "store_size_bytes",
            "creation_timestamp",
            "open_closed_status",
        ),
    ),
    _profile("platform_applications", "runtime-platform-applications"),
    _profile(
        "orchestration_authorities",
        "runtime-orchestration-authorities",
        excluded=("realized_children",),
    ),
    _profile("app_authorizations", "runtime-app-authorizations"),
    _profile("scheduled_jobs", "runtime-scheduled-jobs", excluded=("run_state",)),
    _profile(
        "service_manager_units",
        "runtime-service-manager-units",
        excluded=("sub_state", "result", "exit_code", "status_text", "main_pid"),
    ),
    _profile("packages", "runtime-packages", identity=("manager", "name")),
    _profile("software_components", "runtime-software-components"),
    _profile("dependency_manifests", "runtime-dependency-manifests"),
)


_EXISTING_CONCERNS_BY_FIELD: dict[str, tuple[str, ...]] = {
    "mounts": ("runtime-mounts",),
    "environment": ("runtime-environment",),
    "linux_capabilities": ("linux-capabilities",),
    "operational_policy": ("process-resource-limits",),
    "network": ("published-ports",),
    "service_listeners": ("service-listeners",),
    "forwarding_agents": ("forwarding-agents",),
}
_DELEGATED_PATHS = {
    "environment_files": ("generated-artifact-output",),
    "mounts": ("source_kind:volume", "source_kind:image"),
}
_OBSERVATION_ONLY_PATHS = {
    "file_services": ("access_observations",),
    "mail_services": ("queues.message_count",),
    "network_sensors": ("evidence_refs",),
    "network_detection_engines": ("rule_sources.loaded", "evidence_refs"),
    "security_monitoring_managers": ("status", "loaded", "evidence_refs"),
    "orchestration_authorities": ("realized_children",),
    "scheduled_jobs": ("run_state",),
    "service_manager_units": ("sub_state", "result", "exit_code", "status_text", "main_pid"),
}


def _model_type(annotation: object) -> type[BaseModel]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for candidate in get_args(annotation):
        if isinstance(candidate, type) and issubclass(candidate, BaseModel):
            return candidate
    raise TypeError("runtime concern path does not traverse a typed model")


def runtime_path_annotation(path: tuple[str, ...]) -> object:
    """Return the closed Pydantic annotation at one runtime-relative path."""

    if not path:
        return RuntimeConfiguration
    annotation = RuntimeConfiguration.model_fields[path[0]].annotation
    for token in path[1:]:
        annotation = _model_type(annotation).model_fields[token].annotation
    return annotation


def _semantic_owner(field: str, concern_kinds: tuple[str, ...]) -> str:
    if field not in _DELEGATED_PATHS:
        return "canonical-runtime-realization-concern"
    if concern_kinds:
        return "canonical-runtime-realization-concern+existing-resource-owner"
    return "existing-resource-owner"


def _enforcement_status(field: str, concern_kinds: tuple[str, ...]) -> str:
    delegated = field in _DELEGATED_PATHS
    observation_only = field in _OBSERVATION_ONLY_PATHS
    if delegated and not concern_kinds:
        status = "delegated-to-existing-owner"
    elif delegated and observation_only:
        status = "registered-with-delegated-and-observation-only-paths"
    elif delegated:
        status = "registered-with-delegated-paths"
    elif observation_only:
        status = "registered-with-observation-only-paths"
    else:
        status = "registered-fail-closed"
    return status


def _runtime_field_boundary(
    field: str,
    concerns_by_field: dict[str, tuple[str, ...]],
) -> RuntimeFieldBoundary:
    concern_kinds = concerns_by_field[field]
    return RuntimeFieldBoundary(
        field_name=field,
        concern_kinds=concern_kinds,
        semantic_owner=_semantic_owner(field, concern_kinds),
        enforcement_status=_enforcement_status(field, concern_kinds),
        delegated_paths=_DELEGATED_PATHS.get(field, ()),
        observation_only_paths=_OBSERVATION_ONLY_PATHS.get(field, ()),
    )


def runtime_configuration_boundary_inventory() -> tuple[RuntimeFieldBoundary, ...]:
    """Return and validate the exhaustive RuntimeConfiguration ownership map."""

    concerns_by_field: dict[str, tuple[str, ...]] = {}
    for profile in RUNTIME_CONCERN_PROFILES:
        field = profile.authored_path[0]
        concerns_by_field[field] = (*concerns_by_field.get(field, ()), profile.concern_kind)
    for field, kinds in _EXISTING_CONCERNS_BY_FIELD.items():
        concerns_by_field[field] = (*concerns_by_field.get(field, ()), *kinds)
    for field in _DELEGATED_PATHS:
        concerns_by_field.setdefault(field, ())
    expected = tuple(RuntimeConfiguration.model_fields)
    if set(concerns_by_field) != set(expected):
        raise RuntimeError("RuntimeConfiguration concern inventory is incomplete or contains excess fields")
    return tuple(_runtime_field_boundary(field, concerns_by_field) for field in expected)


__all__ = [
    "RUNTIME_CONCERN_PROFILES",
    "RUNTIME_NON_REALIZATION_FIELDS",
    "RuntimeConcernProfile",
    "RuntimeFieldBoundary",
    "runtime_configuration_boundary_inventory",
    "runtime_path_annotation",
]
