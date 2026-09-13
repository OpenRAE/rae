"""Shared final repository state, independent of acquisition and authorization."""

from collections.abc import Sequence

from pydantic import Field, field_validator, model_validator
from raes_contracts.realization_structure import RealizationPresence

from ._base import SDLModel
from ._identifiers import PortableIdentifier
from .runtime_software_profiles import (
    RuntimeSoftwareRefinement,
    RuntimeSoftwareRepositoryRefinement,
    RuntimeSoftwareTrustRefinement,
)
from .runtime_values import require_symbol


class RuntimeSoftwareTrustBinding(SDLModel):
    """An author-owned trust identity; concrete trust semantics require a profile."""

    trust_id: PortableIdentifier
    presence: RealizationPresence = RealizationPresence.REQUIRED
    refinements: list[RuntimeSoftwareTrustRefinement] = Field(default_factory=list, max_length=256)

    @field_validator("trust_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return require_symbol(value, field_name="trust_id")

    @model_validator(mode="after")
    def validate_refinements(self) -> "RuntimeSoftwareTrustBinding":
        validate_repository_refinements(self.refinements, "repository-trust")
        return self


class RuntimeSoftwareRepository(SDLModel):
    """A stable final-state repository identity shared by software requirements."""

    repository_id: PortableIdentifier
    presence: RealizationPresence = RealizationPresence.REQUIRED
    trust_ref: PortableIdentifier | None = None
    refinements: list[RuntimeSoftwareRepositoryRefinement] = Field(default_factory=list, max_length=256)

    @field_validator("repository_id", "trust_ref")
    @classmethod
    def validate_id(cls, value: str | None) -> str | None:
        return require_symbol(value, field_name="repository identity") if value is not None else None

    @model_validator(mode="after")
    def validate_refinements(self) -> "RuntimeSoftwareRepository":
        validate_repository_refinements(self.refinements, "repository-state")
        return self


def validate_repository_refinements(refinements: Sequence[RuntimeSoftwareRefinement], purpose: str) -> None:
    if any(item.purpose != purpose for item in refinements):
        raise ValueError(f"Repository refinement requires purpose {purpose}")
    if len({item.refinement_id for item in refinements}) != len(refinements):
        raise ValueError("Duplicate repository refinement identity")


def require_compatible_presence(source: RealizationPresence, target: RealizationPresence) -> None:
    """A final-state reference cannot require an absent or merely optional target."""

    if source is RealizationPresence.FORBIDDEN:
        return
    if target is RealizationPresence.FORBIDDEN or (
        source is RealizationPresence.REQUIRED and target is RealizationPresence.OPTIONAL
    ):
        raise ValueError("Final-state reference contradicts target presence")


class RuntimeSoftwareRepositoryState(SDLModel):
    """Bounded shared repository and trust identities, not an installation route."""

    repositories: list[RuntimeSoftwareRepository] = Field(default_factory=list, max_length=256)
    trust_bindings: list[RuntimeSoftwareTrustBinding] = Field(default_factory=list, max_length=256)

    @model_validator(mode="after")
    def validate_references(self) -> "RuntimeSoftwareRepositoryState":
        repositories = {item.repository_id: item for item in self.repositories}
        trusts = {item.trust_id: item for item in self.trust_bindings}
        if len(repositories) != len(self.repositories) or len(trusts) != len(self.trust_bindings):
            raise ValueError("Duplicate final repository or trust identity")
        for repository in self.repositories:
            if repository.trust_ref is None:
                continue
            if repository.trust_ref not in trusts:
                raise ValueError("Final repository trust reference does not resolve")
            require_compatible_presence(repository.presence, trusts[repository.trust_ref].presence)
        return self
