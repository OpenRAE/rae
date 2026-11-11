"""Processor-level capability declarations."""

from __future__ import annotations

from dataclasses import dataclass

from raes_contracts.apparatus import ApparatusIdentity, ConceptBinding
from raes_contracts.contracts.participant_tool_support import ProcessorParticipantToolsModel
from raes_contracts.manifest_authority import (
    validate_processor_supported_contract_versions,
    validate_processor_supported_sdl_versions,
)
from raes_contracts.vocabulary import ProcessorFeature


@dataclass(frozen=True)
class ProcessorCapabilitySet:
    """Processor-specific capability declarations."""

    supported_sdl_versions: frozenset[str] = frozenset()
    supported_features: frozenset[ProcessorFeature] = frozenset()
    participant_tools: ProcessorParticipantToolsModel | None = None

    def __post_init__(self) -> None:
        if not self.supported_sdl_versions:
            raise ValueError("ProcessorCapabilitySet.supported_sdl_versions must not be empty")
        if any(not version.strip() for version in self.supported_sdl_versions):
            raise ValueError("ProcessorCapabilitySet.supported_sdl_versions must not contain empty strings")
        validate_processor_supported_sdl_versions(self.supported_sdl_versions)
        if not self.supported_features:
            raise ValueError("ProcessorCapabilitySet.supported_features must not be empty")
        if self.participant_tools is not None:
            object.__setattr__(
                self,
                "participant_tools",
                ProcessorParticipantToolsModel.model_validate(self.participant_tools.model_dump(mode="json")),
            )


@dataclass(frozen=True)
class ProcessorCompatibility:
    """Processor compatibility claims against backend surfaces."""

    backends: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.backends:
            raise ValueError("ProcessorCompatibility.backends must not be empty")
        if any(not backend.strip() for backend in self.backends):
            raise ValueError("ProcessorCompatibility.backends must not contain empty strings")


@dataclass(frozen=True, init=False)
class ProcessorManifest:
    """Processor identity, capability, and compatibility declaration."""

    identity: ApparatusIdentity
    supported_contract_versions: frozenset[str]
    compatibility: ProcessorCompatibility
    concept_bindings: tuple[ConceptBinding, ...]
    constraints: dict[str, str]
    capabilities: ProcessorCapabilitySet

    def __init__(
        self,
        *,
        identity: ApparatusIdentity | None = None,
        supported_contract_versions: frozenset[str] = frozenset(),
        compatibility: ProcessorCompatibility | None = None,
        concept_bindings: tuple[ConceptBinding, ...] = (),
        constraints: dict[str, str] | None = None,
        capabilities: ProcessorCapabilitySet | None = None,
        name: str | None = None,
        version: str = "0.0.0+unknown",
        supported_sdl_versions: frozenset[str] = frozenset(),
        supported_features: frozenset[ProcessorFeature] = frozenset(),
        compatible_backends: frozenset[str] = frozenset(),
    ) -> None:
        if identity is None:
            if name is None:
                raise ValueError("ProcessorManifest requires either identity or name.")
            identity = ApparatusIdentity(name=name, version=version)
        if compatibility is None:
            compatibility = ProcessorCompatibility(backends=frozenset(compatible_backends))
        if capabilities is None:
            capabilities = ProcessorCapabilitySet(
                supported_sdl_versions=frozenset(supported_sdl_versions),
                supported_features=frozenset(supported_features),
            )
        supported_contract_versions = frozenset(supported_contract_versions)
        if not supported_contract_versions:
            raise ValueError("ProcessorManifest.supported_contract_versions must not be empty")
        if any(not version.strip() for version in supported_contract_versions):
            raise ValueError("ProcessorManifest.supported_contract_versions must not contain empty strings")
        validate_processor_supported_contract_versions(supported_contract_versions)
        concept_bindings = tuple(concept_bindings)
        if not concept_bindings:
            raise ValueError("ProcessorManifest.concept_bindings must not be empty")
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "supported_contract_versions", supported_contract_versions)
        object.__setattr__(self, "compatibility", compatibility)
        object.__setattr__(self, "concept_bindings", concept_bindings)
        object.__setattr__(self, "constraints", {} if constraints is None else dict(constraints))
        object.__setattr__(self, "capabilities", capabilities)

    @property
    def name(self) -> str:
        return self.identity.name

    @property
    def version(self) -> str:
        return self.identity.version

    @property
    def supported_sdl_versions(self) -> frozenset[str]:
        return self.capabilities.supported_sdl_versions

    @property
    def supported_features(self) -> frozenset[ProcessorFeature]:
        return self.capabilities.supported_features

    @property
    def compatible_backends(self) -> frozenset[str]:
        return self.compatibility.backends
