"""Declarative runtime contract models for SDL nodes."""

from collections.abc import Iterable
from enum import Enum

from pydantic import Field, ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from . import runtime_app_authorization as _runtime_app_authorization
from . import runtime_application as _runtime_application
from . import runtime_database as _runtime_database
from . import runtime_datastore as _runtime_datastore
from . import runtime_directory_identity as _runtime_directory_identity
from . import runtime_dns as _runtime_dns
from . import runtime_file_service as _runtime_file_service
from . import runtime_forwarding_agent as _runtime_forwarding_agent
from . import runtime_listeners as _runtime_listeners
from . import runtime_mail_service as _runtime_mail_service
from . import runtime_network_detection as _runtime_network_detection
from . import runtime_network_sensor as _runtime_network_sensor
from . import runtime_orchestration as _runtime_orchestration
from . import runtime_platform_application as _runtime_platform_application
from . import runtime_scheduled_job as _runtime_scheduled_job
from . import runtime_security_monitoring as _runtime_security_monitoring
from . import runtime_ssh_server as _runtime_ssh_server
from ._base import (
    SDLModel,
    parse_float_or_var,
    parse_int_or_var,
)
from ._runtime_service_families import install_runtime_service_family_exports
from .runtime_capabilities import (
    RuntimeCapabilityOverrideScope,
    RuntimeCapabilityPolicy,
    RuntimeProcessCapabilityOverride,
    RuntimeProcessIdentity,
    RuntimeProcessRole,
)
from .runtime_container import (
    RuntimeContainerConfiguration,
    RuntimeDeviceMapping,
    RuntimeExtraHost,
    RuntimeInitProcess,
    RuntimeNamespaceConfiguration,
    RuntimeNetworkNamespace,
)
from .runtime_environment import (
    GeneratedArtifactValueSource,
    RuntimeEnvironmentFile,
    RuntimeEnvironmentValueClassification,
    RuntimeEnvironmentVariable,
    RuntimeEnvironmentVariableProvenance,
)
from .runtime_filesystem import (
    RuntimeFilesystemEntry,
    RuntimeFilesystemEntryType,
    RuntimeFilesystemPresence,
    RuntimeFilesystemStability,
    RuntimeMountPropagation,
    RuntimeSensitivityClassification,
)
from .runtime_identity import (
    RuntimeIdentityProvenance,
    RuntimeLocalGroup,
    RuntimeLocalIdentityInventory,
    RuntimeLocalUser,
    RuntimeSudoPrincipalKind,
    RuntimeSudoRule,
)
from .runtime_mounts import (
    RuntimeControlInterface,
    RuntimeControlInterfaceAccess,
    RuntimeControlInterfaceKind,
    RuntimeMount,
    RuntimeMountSourceKind,
)
from .runtime_network import (
    RuntimeNetworkBackendDetail,
    RuntimeNetworkDriver,
    RuntimeNetworkEndpoint,
    RuntimeNetworkRealization,
    RuntimePublishedPort,
)
from .runtime_packages import (
    RuntimeAptPackageRepository,
    RuntimePackage,
    RuntimePackageRepository,
    RuntimePackageRepositorySigningKey,
)
from .runtime_resource_limits import (
    RuntimeProcessLimitResource,
    RuntimeProcessLimitScope,
    RuntimeProcessResourceLimit,
    reject_duplicate_process_resource_limits,
)
from .runtime_service_units import (
    ServiceManagerKind,
    ServiceManagerUnit,
    ServiceUnitActiveState,
    ServiceUnitEnabledState,
    ServiceUnitExecStart,
    ServiceUnitExecStartKind,
    ServiceUnitKind,
    ServiceUnitLoadState,
    ServiceUnitResult,
)
from .runtime_software import (
    RuntimeSoftwareComponent,
    RuntimeSoftwareComponentHash,
    RuntimeSoftwareComponentProvenance,
    RuntimeSoftwareComponentType,
)
from .runtime_values import absolute_path_or_var as _abs_path_or_var
from .runtime_values import parse_ram
from .runtime_values import parse_runtime_enum_or_var as _parse_runtime_enum_or_var

_RUNTIME_SERVICE_FAMILY_EXPORTS = install_runtime_service_family_exports(globals())
__all__ = [
    *_RUNTIME_SERVICE_FAMILY_EXPORTS,
    "RuntimeCapabilityOverrideScope",
    "RuntimeCapabilityPolicy",
    "RuntimeConfiguration",
    "RuntimeContainerConfiguration",
    "RuntimeControlInterface",
    "RuntimeControlInterfaceAccess",
    "RuntimeControlInterfaceKind",
    "RuntimeDependencyManifest",
    "RuntimeDeviceMapping",
    "GeneratedArtifactValueSource",
    "RuntimeEnvironmentFile",
    "RuntimeEnvironmentValueClassification",
    "RuntimeEnvironmentVariable",
    "RuntimeEnvironmentVariableProvenance",
    "RuntimeExtraHost",
    "RuntimeFilesystemEntry",
    "RuntimeFilesystemEntryType",
    "RuntimeFilesystemPresence",
    "RuntimeFilesystemStability",
    "RuntimeIdentityProvenance",
    "RuntimeInitProcess",
    "RuntimeLocalGroup",
    "RuntimeLocalIdentityInventory",
    "RuntimeLocalUser",
    "RuntimeMount",
    "RuntimeMountPropagation",
    "RuntimeMountSourceKind",
    "RuntimeNamespaceConfiguration",
    "RuntimeNetworkNamespace",
    "RuntimeNetworkBackendDetail",
    "RuntimeNetworkDriver",
    "RuntimeNetworkEndpoint",
    "RuntimeNetworkRealization",
    "RuntimeOperationalPolicy",
    "RuntimeAptPackageRepository",
    "RuntimePackage",
    "RuntimePackageRepository",
    "RuntimePackageRepositorySigningKey",
    "RuntimeProcessCapabilityOverride",
    "RuntimeProcessIdentity",
    "RuntimeProcessLimitResource",
    "RuntimeProcessLimitScope",
    "RuntimeProcessResourceLimit",
    "RuntimeProcessRole",
    "RuntimePublishedPort",
    "RuntimeResourceLimits",
    "RuntimeRestartPolicy",
    "RuntimeSensitivityClassification",
    "RuntimeSoftwareComponent",
    "RuntimeSoftwareComponentHash",
    "RuntimeSoftwareComponentProvenance",
    "RuntimeSoftwareComponentType",
    "RuntimeSudoPrincipalKind",
    "RuntimeSudoRule",
    "ServiceManagerKind",
    "ServiceManagerUnit",
    "ServiceUnitActiveState",
    "ServiceUnitEnabledState",
    "ServiceUnitExecStart",
    "ServiceUnitExecStartKind",
    "ServiceUnitKind",
    "ServiceUnitLoadState",
    "ServiceUnitResult",
    "parse_ram",
]


class RuntimeRestartPolicy(str, Enum):
    """Portable restart policy required by the scenario."""

    NO = "no"
    ALWAYS = "always"
    ON_FAILURE = "on_failure"
    UNLESS_STOPPED = "unless_stopped"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeResourceLimits(SDLModel):
    """Required capacity and process-resource policy for a runtime node."""

    memory: int | str | None = None
    memory_swap: int | str | None = None
    cpu: float | str | None = None
    pids: int | str | None = None
    process_limits: list[RuntimeProcessResourceLimit] = Field(default_factory=list)
    description: str = ""

    @field_validator("memory", "memory_swap", mode="before")
    @classmethod
    def parse_memory_limit(cls, v: int | str | None) -> int | str | None:
        return parse_ram(v) if v is not None else v

    @field_validator("cpu", mode="before")
    @classmethod
    def parse_cpu_limit(cls, v: float | str | None) -> float | str | None:
        return parse_float_or_var(v, minimum=0, field_name="cpu") if v is not None else v

    @field_validator("pids", mode="before")
    @classmethod
    def parse_count_limit(cls, v: int | str | None, info: ValidationInfo) -> int | str | None:
        return parse_int_or_var(v, minimum=1, field_name=info.field_name) if v is not None else v

    @model_validator(mode="after")
    def validate_process_limits(self) -> "RuntimeResourceLimits":
        reject_duplicate_process_resource_limits(self.process_limits)
        return self


class RuntimeOperationalPolicy(SDLModel):
    """Required restart and resource-limit policy for a runtime node."""

    restart: GovernedVocabulary[RuntimeRestartPolicy] = RuntimeRestartPolicy.UNKNOWN
    resource_limits: RuntimeResourceLimits | None = None
    description: str = ""

    @field_validator("restart", mode="before")
    @classmethod
    def normalize_restart(cls, v: RuntimeRestartPolicy | str | bool) -> RuntimeRestartPolicy | str:
        if v is False:
            return RuntimeRestartPolicy.NO
        return _parse_runtime_enum_or_var(v, RuntimeRestartPolicy, field_name="restart")


class RuntimeDependencyManifest(SDLModel):
    """A dependency manifest required in the runtime artifact."""

    ecosystem: str
    path: str
    format: str = ""
    name: str = ""
    version: str = ""

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        return _abs_path_or_var(v, field_name="path")


def _reject_duplicate_keys(items: Iterable[object], *, attr: str, label: str) -> None:
    """Raise on the first repeated non-empty key read from ``attr``."""
    seen: set[object] = set()
    for item in items:
        key = getattr(item, attr)
        if key is None or key == "":
            continue
        if key in seen:
            raise ValueError(f"Duplicate runtime {label} '{key}'")
        seen.add(key)


def _reject_duplicate_package_identities(packages: Iterable[RuntimePackage]) -> None:
    """Reject ambiguous package rows by their stable semantic identity."""

    seen: set[tuple[str, str, str]] = set()
    for package in packages:
        identity = (package.manager, package.name, package.architecture)
        if identity in seen:
            rendered = ":".join(identity)
            raise ValueError(f"Duplicate runtime package identity '{rendered}'")
        seen.add(identity)


class RuntimeConfiguration(SDLModel):
    """Declarative runtime state required by a compute node.

    Captured observations remain in evidence records unless an author
    deliberately promotes the fact to one of these contract fields.
    """

    mounts: list[RuntimeMount] = Field(default_factory=list)
    filesystem_inventory: list[RuntimeFilesystemEntry] = Field(default_factory=list)
    local_control_interfaces: list[RuntimeControlInterface] = Field(default_factory=list)
    processes: list[RuntimeProcessIdentity] = Field(default_factory=list)
    environment: list[RuntimeEnvironmentVariable] = Field(default_factory=list)
    environment_files: list[RuntimeEnvironmentFile] = Field(default_factory=list)
    linux_capabilities: RuntimeCapabilityPolicy | None = None
    operational_policy: RuntimeOperationalPolicy | None = None
    container: RuntimeContainerConfiguration | None = None
    local_identity: RuntimeLocalIdentityInventory | None = None
    identity_authorities: list[_runtime_directory_identity.RuntimeIdentityAuthority] = Field(default_factory=list)
    file_services: list[_runtime_file_service.RuntimeFileService] = Field(default_factory=list)
    mail_services: list[_runtime_mail_service.RuntimeMailService] = Field(default_factory=list)
    network: RuntimeNetworkRealization | None = None
    service_listeners: list[_runtime_listeners.RuntimeServiceListener] = Field(default_factory=list)
    applications: list[_runtime_application.RuntimeApplicationSurface] = Field(default_factory=list)
    database_services: list[_runtime_database.RuntimeDatabaseService] = Field(default_factory=list)
    dns_services: list[_runtime_dns.RuntimeDnsService] = Field(default_factory=list)
    network_sensors: list[_runtime_network_sensor.RuntimeNetworkSensor] = Field(default_factory=list)
    network_detection_engines: list[_runtime_network_detection.RuntimeNetworkDetectionEngine] = Field(
        default_factory=list
    )
    security_monitoring_managers: list[_runtime_security_monitoring.RuntimeSecurityMonitoringManager] = Field(
        default_factory=list
    )
    ssh_servers: list[_runtime_ssh_server.RuntimeSshServer] = Field(default_factory=list)
    datastore_services: list[_runtime_datastore.RuntimeDatastoreService] = Field(default_factory=list)
    platform_applications: list[_runtime_platform_application.RuntimePlatformApplication] = Field(default_factory=list)
    forwarding_agents: list[_runtime_forwarding_agent.RuntimeForwardingAgent] = Field(default_factory=list)
    orchestration_authorities: list[_runtime_orchestration.RuntimeOrchestrationAuthority] = Field(default_factory=list)
    app_authorizations: list[_runtime_app_authorization.RuntimeAppAuthorization] = Field(default_factory=list)
    scheduled_jobs: list[_runtime_scheduled_job.RuntimeScheduledJob] = Field(default_factory=list)
    service_manager_units: list[ServiceManagerUnit] = Field(default_factory=list)
    packages: list[RuntimePackage] = Field(default_factory=list)
    software_components: list[RuntimeSoftwareComponent] = Field(default_factory=list)
    dependency_manifests: list[RuntimeDependencyManifest] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_runtime_entries(self) -> "RuntimeConfiguration":
        _reject_duplicate_keys(self.environment, attr="name", label="environment variable")
        _reject_duplicate_keys(self.environment_files, attr="name", label="environment file")
        _reject_duplicate_keys(self.mounts, attr="target", label="mount target")
        _reject_duplicate_keys(
            self.local_control_interfaces,
            attr="control_interface_id",
            label="control_interface_id",
        )
        _reject_duplicate_keys(self.filesystem_inventory, attr="path", label="filesystem path")
        _reject_duplicate_keys(self.processes, attr="name", label="process name")
        _reject_duplicate_keys(self.processes, attr="pid", label="process pid")
        _reject_duplicate_keys(
            self.service_listeners, attr="service_listener_id", label="service_listener service_listener_id"
        )
        _reject_duplicate_keys(self.applications, attr="application_id", label="application_id")
        _reject_duplicate_keys(self.database_services, attr="database_service_id", label="database_service_id")
        _reject_duplicate_keys(self.dns_services, attr="dns_service_id", label="dns_service_id")
        _reject_duplicate_keys(self.network_sensors, attr="network_sensor_id", label="network sensor")
        _reject_duplicate_keys(
            self.network_detection_engines, attr="network_detection_engine_id", label="network detection engine"
        )
        _reject_duplicate_keys(
            self.security_monitoring_managers, attr="security_monitoring_manager_id", label="security manager"
        )
        _reject_duplicate_keys(self.ssh_servers, attr="ssh_server_id", label="ssh_server ssh_server_id")
        _reject_duplicate_keys(
            self.datastore_services,
            attr="datastore_service_id",
            label="datastore_service_id",
        )
        _reject_duplicate_keys(
            self.platform_applications,
            attr="platform_application_id",
            label="platform_application_id",
        )
        _reject_duplicate_keys(
            self.forwarding_agents,
            attr="forwarding_agent_id",
            label="forwarding_agent_id",
        )
        _reject_duplicate_keys(
            self.orchestration_authorities,
            attr="orchestration_authority_id",
            label="orchestration_authority_id",
        )
        _reject_duplicate_keys(
            self.app_authorizations,
            attr="app_authorization_id",
            label="app_authorization_id",
        )
        _reject_duplicate_keys(self.scheduled_jobs, attr="scheduled_job_id", label="scheduled_job_id")
        _reject_duplicate_keys(
            self.service_manager_units,
            attr="unit_id",
            label="service_manager_unit unit_id",
        )
        _reject_duplicate_keys(
            self.service_manager_units,
            attr="unit_name",
            label="service_manager_unit unit_name",
        )
        _reject_duplicate_keys(self.identity_authorities, attr="identity_authority_id", label="identity authority")
        _reject_duplicate_keys(self.file_services, attr="file_service_id", label="file_service file_service_id")
        _reject_duplicate_keys(self.mail_services, attr="mail_service_id", label="mail_service mail_service_id")
        _reject_duplicate_package_identities(self.packages)
        _reject_duplicate_keys(self.software_components, attr="component_id", label="software component")
        return self
