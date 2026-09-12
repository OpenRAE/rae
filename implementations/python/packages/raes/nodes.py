"""Node models — VMs and network switches.

Ports the OCR SDL Node/Compute/Switch/Resources/Role structs with
backend-agnostic Source references.
"""

from enum import Enum

from pydantic import Field, field_validator, model_validator
from pydantic.json_schema import GetJsonSchemaHandler, JsonSchemaValue
from pydantic_core import CoreSchema

from raes.runtime_values import parse_runtime_enum_or_var
from raes.runtime_vocabulary import GovernedVocabulary

from ._base import (
    SDLModel,
    is_variable_ref,
    normalize_enum_value,
    parse_enum_or_var,
    parse_int_or_var,
)
from ._classification_guard import LegacyClassificationGuard
from ._identifiers import OptionalPortableIdentifier, PortableIdentifier
from ._runtime_service_families import install_runtime_service_family_exports
from ._source import Source
from .architectures import (
    AuthoredNodeArchitectureString,
    NodeArchitecture,
    normalize_architecture,
)
from .deployment_tenancy import EndpointPersona
from .image_provenance import (
    ContainerImageBuildProvenance,
    DockerfileInstruction,
    DockerfileInstructionKind,
    ImageAttestation,
    ImageAttestationStatus,
    ImageAttestationType,
    ImageBuildArg,
    ImageConfig,
    ImageCopiedSource,
    ImageEnvironmentDefault,
    ImageLayer,
    ImageSourceInput,
    ImageVerificationStatus,
)
from .operating_systems import (
    AuthoredOSDistributionString,
    AuthoredOSVersionString,
    OSDistribution,
    normalize_os_distribution,
    normalize_os_version,
)
from .runtime_configuration import (
    RuntimeAptPackageRepository,
    RuntimeCapabilityOverrideScope,
    RuntimeCapabilityPolicy,
    RuntimeConfiguration,
    RuntimeContainerConfiguration,
    RuntimeControlInterface,
    RuntimeControlInterfaceAccess,
    RuntimeControlInterfaceKind,
    RuntimeDeviceMapping,
    RuntimeEnvironmentValueClassification,
    RuntimeEnvironmentVariable,
    RuntimeEnvironmentVariableProvenance,
    RuntimeExtraHost,
    RuntimeFilesystemEntry,
    RuntimeFilesystemEntryType,
    RuntimeFilesystemPresence,
    RuntimeFilesystemStability,
    RuntimeIdentityProvenance,
    RuntimeInitProcess,
    RuntimeLocalGroup,
    RuntimeLocalIdentityInventory,
    RuntimeLocalUser,
    RuntimeMount,
    RuntimeMountPropagation,
    RuntimeMountSourceKind,
    RuntimeNamespaceConfiguration,
    RuntimeNetworkBackendDetail,
    RuntimeNetworkDriver,
    RuntimeNetworkEndpoint,
    RuntimeNetworkNamespace,
    RuntimeNetworkRealization,
    RuntimeOperationalPolicy,
    RuntimePackage,
    RuntimePackageRepository,
    RuntimePackageRepositorySigningKey,
    RuntimeProcessCapabilityOverride,
    RuntimeProcessIdentity,
    RuntimeProcessLimitResource,
    RuntimeProcessLimitScope,
    RuntimeProcessResourceLimit,
    RuntimeProcessRole,
    RuntimePublishedPort,
    RuntimeResourceLimits,
    RuntimeRestartPolicy,
    RuntimeSensitivityClassification,
    RuntimeSoftwareComponent,
    RuntimeSoftwareComponentHash,
    RuntimeSoftwareComponentProvenance,
    RuntimeSoftwareComponentType,
    RuntimeSudoPrincipalKind,
    RuntimeSudoRule,
    parse_ram,
)

_RUNTIME_SERVICE_FAMILY_EXPORTS = install_runtime_service_family_exports(globals())

__all__ = [
    "AssetValue",
    "AssetValueLevel",
    "ContainerImageBuildProvenance",
    "DockerfileInstruction",
    "DockerfileInstructionKind",
    "ImageAttestation",
    "ImageAttestationStatus",
    "ImageAttestationType",
    "ImageBuildArg",
    "ImageConfig",
    "ImageCopiedSource",
    "ImageEnvironmentDefault",
    "ImageLayer",
    "ImageSourceInput",
    "ImageVerificationStatus",
    "MAX_NODE_NAME_LENGTH",
    "Node",
    "NodeArchitecture",
    "NodeType",
    "OSFamily",
    "Resources",
    "Role",
    "Source",
    *_RUNTIME_SERVICE_FAMILY_EXPORTS,
    "RuntimeCapabilityOverrideScope",
    "RuntimeCapabilityPolicy",
    "RuntimeContainerConfiguration",
    "RuntimeConfiguration",
    "RuntimeControlInterface",
    "RuntimeControlInterfaceAccess",
    "RuntimeControlInterfaceKind",
    "RuntimeDeviceMapping",
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
    "ServicePort",
    "parse_ram",
]

MAX_NODE_NAME_LENGTH = 35


class NodeType(str, Enum):
    """Structural resource kind, independent of its realization mechanism."""

    COMPUTE = "compute"
    SWITCH = "switch"


class Resources(SDLModel):
    """Compute resources for a compute node."""

    ram: int | str = Field(description="RAM in bytes (parsed from human-readable)")
    cpu: int | str = Field(description="Number of CPU cores")

    @field_validator("ram", mode="before")
    @classmethod
    def parse_ram_value(cls, v: str | int) -> int | str:
        return parse_ram(v)

    @field_validator("cpu", mode="before")
    @classmethod
    def parse_cpu_value(cls, v: int | str) -> int | str:
        return parse_int_or_var(v, minimum=1, field_name="cpu")


class Role(SDLModel):
    """A named role on a compute node with optional entity assignments.

    Shorthand: ``admin: "username"`` (just the username string).
    Longhand: ``admin: {username: "admin", entities: ["blue-team.bob"]}``.
    """

    username: str
    entities: list[str] = Field(default_factory=list)


class OSFamily(str, Enum):
    """Operating system family. Vocabulary from OCSF Device.os."""

    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    FREEBSD = "freebsd"
    OTHER = "other"


class AssetValueLevel(str, Enum):
    """CIA triad value level. Adapted from CybORG ConfidentialityValue."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AssetValue(SDLModel):
    """CIA triad asset valuation for scoring and risk assessment."""

    confidentiality: AssetValueLevel | str = AssetValueLevel.MEDIUM
    integrity: AssetValueLevel | str = AssetValueLevel.MEDIUM
    availability: AssetValueLevel | str = AssetValueLevel.MEDIUM

    @field_validator(
        "confidentiality",
        "integrity",
        "availability",
        mode="before",
    )
    @classmethod
    def normalize_asset_value(
        cls,
        v: AssetValueLevel | str,
    ) -> AssetValueLevel | str:
        return parse_enum_or_var(
            v,
            AssetValueLevel,
            field_name="asset_value",
        )


class ServicePort(SDLModel):
    """Authored identity of a node-local transport binding.

    A service declaration does not authorize traffic, prove a live listener,
    publish a host port, or classify an internal/external audience. Traffic
    authorization belongs to infrastructure ACLs; observed bind state and host
    publication belong to their dedicated runtime surfaces.
    """

    port: int | str
    protocol: str = "tcp"
    name: OptionalPortableIdentifier = ""
    description: str = ""

    @field_validator("port", mode="before")
    @classmethod
    def parse_port_value(cls, v: int | str) -> int | str:
        return parse_int_or_var(v, minimum=1, maximum=65535, field_name="port")


class Node(LegacyClassificationGuard):
    """A scenario node — either a compute endpoint or a strict switch.

    The ``type`` field determines which structural variant is active. Compute
    fields are only valid for compute nodes; switches carry no extra data.
    """

    legacy_classification_fields = ("vulnerabilities",)

    type: NodeType = Field(alias="type")
    description: str = ""
    source: Source | None = None

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v: str) -> str:
        return normalize_enum_value(v)

    resources: Resources | None = None
    os: GovernedVocabulary[OSFamily] | None = None
    os_distribution: OSDistribution | AuthoredOSDistributionString | None = None
    os_version: AuthoredOSVersionString = ""
    architecture: NodeArchitecture | AuthoredNodeArchitectureString | None = None
    features: dict[str, str] = Field(default_factory=dict)
    conditions: dict[str, str] = Field(default_factory=dict)
    injects: dict[str, str] = Field(default_factory=dict)
    roles: dict[PortableIdentifier, Role] = Field(default_factory=dict)
    services: list[ServicePort] = Field(default_factory=list)
    asset_value: AssetValue | None = None
    endpoint_persona: EndpointPersona | str | None = None
    runtime: RuntimeConfiguration | None = None

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        """Publish the same OS dependency chain enforced by semantic validation."""

        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "required": ["os_version"],
                        "properties": {"os_version": {"type": "string", "minLength": 1}},
                    },
                    "then": {
                        "required": ["os_distribution"],
                        "properties": {"os_distribution": {"not": {"type": "null"}}},
                    },
                },
                {
                    "if": {
                        "required": ["os_distribution"],
                        "properties": {"os_distribution": {"not": {"type": "null"}}},
                    },
                    "then": {
                        "required": ["os"],
                        "properties": {"os": {"not": {"type": "null"}}},
                    },
                },
            ]
        )
        return json_schema

    @field_validator("os", mode="before")
    @classmethod
    def normalize_os(cls, v):
        return parse_runtime_enum_or_var(v, OSFamily, field_name="os") if v is not None else v

    @field_validator("os_distribution", mode="before")
    @classmethod
    def normalize_os_distribution_value(cls, v: object) -> object:
        return normalize_os_distribution(v) if v is not None else v

    @field_validator("os_version", mode="before")
    @classmethod
    def normalize_os_version_value(cls, v: object) -> object:
        return normalize_os_version(v)

    @field_validator("architecture", mode="before")
    @classmethod
    def normalize_architecture_value(cls, v: object) -> object:
        return normalize_architecture(v)

    @field_validator("endpoint_persona", mode="before")
    @classmethod
    def normalize_endpoint_persona(cls, v: object) -> object:
        return parse_enum_or_var(v, EndpointPersona, field_name="endpoint_persona") if v is not None else v

    @model_validator(mode="after")
    def validate_type_constraints(self) -> "Node":
        """Switch nodes cannot carry compute-only fields."""
        if self.type != NodeType.SWITCH:
            return self

        disallowed_fields = self._populated_compute_only_fields()
        if disallowed_fields:
            raise ValueError("Switch nodes cannot have compute-only fields: " + ", ".join(disallowed_fields))
        return self

    def _populated_compute_only_fields(self) -> list[str]:
        fields = {
            "source": self.source is not None,
            "resources": self.resources is not None,
            "os": self.os is not None,
            "os_distribution": self.os_distribution is not None,
            "os_version": bool(self.os_version),
            "architecture": self.architecture is not None,
            "features": bool(self.features),
            "conditions": bool(self.conditions),
            "injects": bool(self.injects),
            "roles": bool(self.roles),
            "services": bool(self.services),
            "asset_value": self.asset_value is not None,
            "endpoint_persona": self.endpoint_persona is not None,
            "runtime": self.runtime is not None,
        }
        return [field_name for field_name, is_populated in fields.items() if is_populated]

    @model_validator(mode="after")
    def validate_unique_service_ports(self) -> "Node":
        """Concrete compute service bindings must stay uniquely addressable."""
        if self.type != NodeType.COMPUTE:
            return self

        seen: set[tuple[str, int]] = set()
        seen_names: set[str] = set()
        for service in self.services:
            if not isinstance(service.port, int):
                pass
            elif not is_variable_ref(service.protocol):
                key = (service.protocol.lower(), service.port)
                if key in seen:
                    raise ValueError(f"Duplicate service binding '{service.protocol}/{service.port}' on node")
                seen.add(key)
            if service.name:
                if service.name in seen_names:
                    raise ValueError(f"Duplicate named service '{service.name}' on node")
                seen_names.add(service.name)
        return self
