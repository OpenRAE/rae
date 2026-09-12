"""Aggregate backend manifest contract built from domain capability types."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypedDict, TypeVar, Unpack

from raes_contracts.apparatus import ApparatusIdentity, ConceptBinding, RealizationSupportDeclaration
from raes_contracts.manifest_authority import validate_backend_supported_contract_versions
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel

from .capabilities import (
    BackendCapabilitySet,
    CleanupCapabilities,
    EvaluatorCapabilities,
    ObservationCapabilities,
    OrchestratorCapabilities,
    ParticipantRuntimeCapabilities,
    ProvisionerCapabilities,
    TimeCapabilities,
)


@dataclass(frozen=True)
class BackendCompatibility:
    """Backend compatibility claims against processor surfaces."""

    processors: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.processors:
            raise ValueError("BackendCompatibility.processors must not be empty")
        if any(not processor.strip() for processor in self.processors):
            raise ValueError("BackendCompatibility.processors must not contain empty strings")


class _BackendManifestOptions(TypedDict, total=False):
    identity: ApparatusIdentity | None
    supported_contract_versions: frozenset[str]
    compatibility: BackendCompatibility | None
    realization_support: tuple[RealizationSupportDeclaration, ...]
    concept_bindings: tuple[ConceptBinding, ...]
    constraints: dict[str, str] | None
    capabilities: BackendCapabilitySet | None
    name: str | None
    version: str
    compatible_processors: frozenset[str]
    provisioner: ProvisionerCapabilities | None
    orchestrator: OrchestratorCapabilities | None
    evaluator: EvaluatorCapabilities | None
    participant_runtime: ParticipantRuntimeCapabilities | None
    observation: ObservationCapabilities | None
    cleanup: CleanupCapabilities | None
    time: TimeCapabilities | None
    realization_envelope: BackendRealizationEnvelopeModel | None
    domain_profile_context_digest: str | None


@dataclass(frozen=True, init=False)
class BackendManifest:
    """Complete runtime target capability declaration."""

    identity: ApparatusIdentity
    supported_contract_versions: frozenset[str]
    compatibility: BackendCompatibility
    realization_support: tuple[RealizationSupportDeclaration, ...]
    concept_bindings: tuple[ConceptBinding, ...]
    constraints: dict[str, str]
    capabilities: BackendCapabilitySet
    realization_envelope: BackendRealizationEnvelopeModel | None
    domain_profile_context_digest: str | None

    def __init__(self, **options: Unpack[_BackendManifestOptions]) -> None:
        _reject_unknown_options(options)
        identity = _resolve_identity(options)
        compatibility = _resolve_compatibility(options)
        capabilities = _resolve_capabilities(options)
        supported_contract_versions = _validate_supported_contract_versions(options)
        _validate_cleanup_capability_contracts(supported_contract_versions, capabilities.cleanup)
        _validate_time_capability_contracts(supported_contract_versions, capabilities.time)
        _validate_coordinated_reset_capabilities(capabilities)
        realization_envelope = options.get("realization_envelope")
        _validate_realization_envelope_contract(supported_contract_versions, realization_envelope)
        realization_support = _require_non_empty_tuple(options.get("realization_support", ()), "realization_support")
        concept_bindings = _require_non_empty_tuple(options.get("concept_bindings", ()), "concept_bindings")
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "supported_contract_versions", supported_contract_versions)
        object.__setattr__(self, "compatibility", compatibility)
        object.__setattr__(self, "realization_support", realization_support)
        object.__setattr__(self, "concept_bindings", concept_bindings)
        constraints = options.get("constraints")
        object.__setattr__(self, "constraints", {} if constraints is None else dict(constraints))
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "realization_envelope", realization_envelope)
        profile_digest = options.get("domain_profile_context_digest")
        if profile_digest is not None and (
            not isinstance(profile_digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", profile_digest)
        ):
            raise ValueError("Invalid domain profile context digest")
        object.__setattr__(self, "domain_profile_context_digest", profile_digest)

    @property
    def name(self) -> str:
        return self.identity.name

    @property
    def version(self) -> str:
        return self.identity.version

    @property
    def compatible_processors(self) -> frozenset[str]:
        return self.compatibility.processors

    @property
    def provisioner(self) -> ProvisionerCapabilities:
        return self.capabilities.provisioner

    @property
    def orchestrator(self) -> OrchestratorCapabilities | None:
        return self.capabilities.orchestrator

    @property
    def evaluator(self) -> EvaluatorCapabilities | None:
        return self.capabilities.evaluator

    @property
    def participant_runtime(self) -> ParticipantRuntimeCapabilities | None:
        return self.capabilities.participant_runtime

    @property
    def observation(self) -> ObservationCapabilities | None:
        return self.capabilities.observation

    @property
    def cleanup(self) -> CleanupCapabilities | None:
        return self.capabilities.cleanup

    @property
    def time(self) -> TimeCapabilities | None:
        return self.capabilities.time

    @property
    def has_orchestrator(self) -> bool:
        return self.orchestrator is not None

    @property
    def has_evaluator(self) -> bool:
        return self.evaluator is not None

    @property
    def has_participant_runtime(self) -> bool:
        return self.participant_runtime is not None

    @property
    def has_observation(self) -> bool:
        return self.observation is not None

    @property
    def has_cleanup(self) -> bool:
        return self.cleanup is not None

    @property
    def has_time(self) -> bool:
        return self.time is not None

    @property
    def evaluator_supported_sections(self) -> frozenset[str]:
        return self.evaluator.supported_sections if self.evaluator is not None else frozenset()

    @property
    def supports_scoring(self) -> bool:
        return self.evaluator.supports_scoring if self.evaluator is not None else False

    @property
    def supports_objectives(self) -> bool:
        return self.evaluator.supports_objectives if self.evaluator is not None else False


def _reject_unknown_options(options: _BackendManifestOptions) -> None:
    unknown = set(options) - set(_BackendManifestOptions.__annotations__)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise TypeError(f"BackendManifest got unexpected keyword argument(s): {names}")


def _resolve_identity(options: _BackendManifestOptions) -> ApparatusIdentity:
    identity = options.get("identity")
    if identity is not None:
        return identity
    name = options.get("name")
    if name is None:
        raise ValueError("BackendManifest requires either identity or name.")
    return ApparatusIdentity(name=name, version=options.get("version", "0.0.0+unknown"))


def _resolve_compatibility(options: _BackendManifestOptions) -> BackendCompatibility:
    compatibility = options.get("compatibility")
    if compatibility is not None:
        return compatibility
    return BackendCompatibility(processors=frozenset(options.get("compatible_processors", frozenset())))


def _resolve_capabilities(options: _BackendManifestOptions) -> BackendCapabilitySet:
    capabilities = options.get("capabilities")
    if capabilities is not None:
        return capabilities
    provisioner = options.get("provisioner")
    if provisioner is None:
        raise ValueError("BackendManifest requires either capabilities or provisioner.")
    return BackendCapabilitySet(
        provisioner=provisioner,
        orchestrator=options.get("orchestrator"),
        evaluator=options.get("evaluator"),
        participant_runtime=options.get("participant_runtime"),
        observation=options.get("observation"),
        cleanup=options.get("cleanup"),
        time=options.get("time"),
    )


def _validate_supported_contract_versions(options: _BackendManifestOptions) -> frozenset[str]:
    versions = frozenset(options.get("supported_contract_versions", frozenset()))
    if not versions:
        raise ValueError("BackendManifest.supported_contract_versions must not be empty")
    if any(not contract_id.strip() for contract_id in versions):
        raise ValueError("BackendManifest.supported_contract_versions must not contain empty strings")
    validate_backend_supported_contract_versions(versions)
    return versions


def _validate_realization_envelope_contract(
    supported_contract_versions: frozenset[str],
    realization_envelope: BackendRealizationEnvelopeModel | None,
) -> None:
    envelope_contract_declared = "realization-envelope-v1" in supported_contract_versions
    if realization_envelope is not None and not envelope_contract_declared:
        raise ValueError("realization_envelope requires realization-envelope-v1 support")
    if envelope_contract_declared and realization_envelope is None:
        raise ValueError("realization-envelope-v1 support requires realization_envelope")


def _validate_cleanup_capability_contracts(
    supported_contract_versions: frozenset[str],
    cleanup: CleanupCapabilities | None,
) -> None:
    cleanup_contracts = frozenset({"trial-cleanup-plan-v1", "trial-cleanup-receipt-v1"})
    declared = supported_contract_versions.intersection(cleanup_contracts)
    if cleanup is not None and declared != cleanup_contracts:
        raise ValueError("cleanup capabilities require both cleanup contract versions")
    if declared and cleanup is None:
        raise ValueError("cleanup contract support requires CleanupCapabilities")


def _validate_time_capability_contracts(
    supported_contract_versions: frozenset[str],
    time: TimeCapabilities | None,
) -> None:
    from .capabilities import TIME_CAPABILITY_REQUIRED_CONTRACTS

    declared = supported_contract_versions.intersection(TIME_CAPABILITY_REQUIRED_CONTRACTS)
    if time is not None and declared != TIME_CAPABILITY_REQUIRED_CONTRACTS:
        raise ValueError("time capabilities require the complete time contract family")
    dedicated = {"time-model-v1", "time-runtime-state-v1", "realized-time-model-v1"}
    if declared.intersection(dedicated) and time is None:
        raise ValueError("time contract support requires TimeCapabilities")


def _validate_coordinated_reset_capabilities(capabilities: BackendCapabilitySet) -> None:
    time = capabilities.time
    if time is not None and time.supports_coordinated_participant_reset and capabilities.participant_runtime is None:
        raise ValueError("coordinated participant reset support requires participant runtime capabilities")


_T = TypeVar("_T")


def _require_non_empty_tuple(values: tuple[_T, ...], field_name: str) -> tuple[_T, ...]:
    result = tuple(values)
    if not result:
        raise ValueError(f"BackendManifest.{field_name} must not be empty")
    return result


__all__ = ["BackendCompatibility", "BackendManifest"]
