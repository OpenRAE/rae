"""Optional public software refinements; execution support stays target-owned."""

from typing import Literal

from pydantic import Field, JsonValue, field_validator
from raes_contracts.domain_profiles import DomainProfileDefinitionModel
from raes_contracts.realization_structure import validate_realization_value

from ._base import SDLModel
from ._identifiers import PortableIdentifier
from .architectures import PackageArchitectureString, normalize_architecture
from .runtime_values import require_symbol


class RuntimeSoftwareRefinement(SDLModel):
    """An explicit pinned profile constraint, never acquisition authorization."""

    refinement_id: PortableIdentifier
    purpose: Literal["acquisition", "version-correspondence", "repository-state", "repository-trust"]
    definition: DomainProfileDefinitionModel
    profile_value: JsonValue

    @field_validator("refinement_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return require_symbol(value, field_name="refinement_id")

    @field_validator("profile_value", mode="before")
    @classmethod
    def bounded_value(cls, value: object) -> object:
        if not validate_realization_value(value).conformant:
            raise ValueError("Software profile value exceeds bounded public data limits")
        return value


class RuntimeSoftwareComponentRefinement(RuntimeSoftwareRefinement):
    """A component's acquisition or application/package correspondence constraint."""

    purpose: Literal["acquisition", "version-correspondence"]


class RuntimeSoftwareRepositoryRefinement(RuntimeSoftwareRefinement):
    """A final-state constraint attached to a shared repository identity."""

    purpose: Literal["repository-state"]


class RuntimeSoftwareTrustRefinement(RuntimeSoftwareRefinement):
    """A final-state constraint attached to a shared trust identity."""

    purpose: Literal["repository-trust"]


class RuntimeSoftwarePackageReference(SDLModel):
    """Explicit correspondence to a package row; no identity is inferred."""

    manager: str = Field(min_length=1)
    name: str = Field(min_length=1)
    architecture: PackageArchitectureString = ""

    @field_validator("architecture", mode="before")
    @classmethod
    def normalize_architecture(cls, value: object) -> object:
        normalized = normalize_architecture(value) if value else value
        return getattr(normalized, "value", normalized)
