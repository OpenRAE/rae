"""Declarative runtime software component requirements for SDL nodes."""

from enum import Enum

from pydantic import Field, field_validator, model_validator
from raes_contracts.realization_structure import RealizationPresence
from raes_contracts.software_versions import VersionDomain, version_membership

from ._base import SDLModel
from ._identifiers import PortableIdentifier
from .runtime_packages import RuntimePackage
from .runtime_software_profiles import RuntimeSoftwareComponentRefinement, RuntimeSoftwarePackageReference
from .runtime_values import (
    absolute_path_or_var,
    coerce_string_list,
    parse_runtime_enum_or_var,
    require_symbol,
    validate_absolute_paths,
)


class RuntimeSoftwareComponentType(str, Enum):
    """Portable type for a software component required on a runtime node."""

    APPLICATION = "application"
    FRAMEWORK = "framework"
    LIBRARY = "library"
    CONTAINER = "container"
    PLATFORM = "platform"
    OPERATING_SYSTEM = "operating_system"
    DEVICE = "device"
    DEVICE_DRIVER = "device_driver"
    FIRMWARE = "firmware"
    FILE = "file"
    DATA = "data"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeSoftwareComponentProvenance(str, Enum):
    """Required source origin for a runtime software component."""

    PACKAGE_MANAGER = "package_manager"
    DEPENDENCY_MANIFEST = "dependency_manifest"
    IMAGE_METADATA = "image_metadata"
    OPERATOR = "operator"
    SELF_REPORTED = "self_reported"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeSoftwareComponentHash(SDLModel):
    """Digest required for a runtime software component."""

    algorithm: str
    value: str

    @field_validator("algorithm", "value")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("software component hash fields must be non-empty strings")
        return v


class RuntimeSoftwareComponent(SDLModel):
    """A software component required as part of a runtime node's state."""

    component_id: str
    name: str
    presence: RealizationPresence = RealizationPresence.REQUIRED
    version: str = ""
    version_constraint: VersionDomain | None = None
    component_type: RuntimeSoftwareComponentType | str = RuntimeSoftwareComponentType.UNKNOWN
    provenance: RuntimeSoftwareComponentProvenance | str = RuntimeSoftwareComponentProvenance.UNKNOWN
    ecosystem: str = ""
    purl: str = ""
    cpe: str = ""
    package_manager: str = ""
    package_name: str = ""
    package_version: str = ""
    package_version_constraint: VersionDomain | None = None
    package_ref: RuntimeSoftwarePackageReference | None = None
    package: RuntimePackage | None = None
    repository_refs: list[PortableIdentifier] = Field(default_factory=list, max_length=256)
    refinements: list[RuntimeSoftwareComponentRefinement] = Field(default_factory=list, max_length=256)
    manifest_path: str = ""
    installed_paths: list[str] = Field(default_factory=list)
    hashes: list[RuntimeSoftwareComponentHash] = Field(default_factory=list)
    description: str = ""

    @field_validator("repository_refs")
    @classmethod
    def validate_repository_refs(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Duplicate software repository reference")
        return [require_symbol(value, field_name="repository_refs") for value in values]

    @model_validator(mode="after")
    def validate_version_constraints(self) -> "RuntimeSoftwareComponent":
        identities = [item.refinement_id for item in self.refinements]
        if len(set(identities)) != len(identities):
            raise ValueError("Duplicate software refinement identity")
        if self.package is not None:
            self.validate_package_correspondence(self.package)
        for field in ("version", "package_version"):
            constraint = getattr(self, f"{field}_constraint")
            if constraint is not None and field in self.model_fields_set and getattr(self, field):
                result = version_membership(getattr(self, field), constraint)
                if result in {"nonconformant", "unresolved"}:
                    raise ValueError(f"{field} contradicts its version constraint")
        return self

    def validate_package_correspondence(self, package: RuntimePackage) -> None:
        """Conjoin explicitly selected distribution coordinates, never app versions."""

        for field, actual in (
            ("package_manager", package.manager),
            ("package_name", package.name),
            ("package_version", package.version),
        ):
            if getattr(self, field) and getattr(self, field) != actual:
                raise ValueError(f"Software {field} contradicts its exact package refinement")
        if self.package is not None and self.package != package:
            raise ValueError("Software exact package contradicts its referenced package")
        if self.package_version_constraint is not None:
            result = version_membership(package.version, self.package_version_constraint)
            if result in {"nonconformant", "unresolved"}:
                raise ValueError("Software package version contradicts its version constraint")

    @field_validator("component_id")
    @classmethod
    def validate_component_id(cls, v: str) -> str:
        return require_symbol(v, field_name="component_id")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("software component name must be a non-empty string")
        return v

    @field_validator("component_type", mode="before")
    @classmethod
    def normalize_component_type(
        cls,
        v: RuntimeSoftwareComponentType | str,
    ) -> RuntimeSoftwareComponentType | str:
        return parse_runtime_enum_or_var(v, RuntimeSoftwareComponentType, field_name="component_type")

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(
        cls,
        v: RuntimeSoftwareComponentProvenance | str,
    ) -> RuntimeSoftwareComponentProvenance | str:
        return parse_runtime_enum_or_var(v, RuntimeSoftwareComponentProvenance, field_name="provenance")

    @field_validator("manifest_path")
    @classmethod
    def validate_manifest_path(cls, v: str) -> str:
        return absolute_path_or_var(v, field_name="manifest_path") if v else v

    @field_validator("installed_paths", mode="before")
    @classmethod
    def coerce_installed_paths(cls, v: object) -> object:
        return coerce_string_list(v)

    @field_validator("installed_paths")
    @classmethod
    def validate_installed_paths(cls, v: list[str]) -> list[str]:
        return validate_absolute_paths(v, field_name="installed_paths")
