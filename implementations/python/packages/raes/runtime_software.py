"""Declarative runtime software component requirements for SDL nodes."""

from enum import Enum

from pydantic import Field, field_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel
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
    version: str = ""
    component_type: GovernedVocabulary[RuntimeSoftwareComponentType] = RuntimeSoftwareComponentType.UNKNOWN
    provenance: GovernedVocabulary[RuntimeSoftwareComponentProvenance] = RuntimeSoftwareComponentProvenance.UNKNOWN
    ecosystem: str = ""
    purl: str = ""
    cpe: str = ""
    package_manager: str = ""
    package_name: str = ""
    package_version: str = ""
    manifest_path: str = ""
    installed_paths: list[str] = Field(default_factory=list)
    hashes: list[RuntimeSoftwareComponentHash] = Field(default_factory=list)
    description: str = ""

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
