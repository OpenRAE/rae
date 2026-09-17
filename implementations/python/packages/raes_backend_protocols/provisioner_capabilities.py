"""Provisioner-specific runtime capability declarations."""

from dataclasses import dataclass, field

from raes_contracts.controlled_vocabularies import (
    validate_controlled_vocabulary_scope_values,
    validate_controlled_vocabulary_value,
)
from raes_contracts.domain_profiles import DomainProfileCoordinateModel
from raes_contracts.operating_systems import OS_VERSION_RE, validate_operating_system_pair
from raes_contracts.vocabulary import (
    GeneratedArtifactDeliveryMode,
    GeneratedArtifactKind,
    GeneratedArtifactRegenerationScope,
)

PROVISIONER_DOMAIN_PROFILE_SCOPE = "capabilities.provisioner.supported_domain_profiles"
PROVISIONER_SERVICE_MATERIALIZATION_PROFILE_SCOPE = (
    "capabilities.provisioner.supported_service_materialization_profiles"
)


@dataclass(frozen=True)
class OperatingSystemCompatibility:
    """One inseparable OS family, distribution, and bounded release domain."""

    family: str
    distribution: str
    versions: frozenset[str]

    def __post_init__(self) -> None:
        validate_controlled_vocabulary_scope_values(
            "capabilities.provisioner.supported_os_families",
            (self.family,),
        )
        validate_controlled_vocabulary_value("os-distributions", self.distribution)
        validate_operating_system_pair(self.family, self.distribution)
        if not self.versions:
            raise ValueError("OperatingSystemCompatibility.versions must not be empty")
        if any(OS_VERSION_RE.fullmatch(version) is None for version in self.versions):
            raise ValueError(
                "OperatingSystemCompatibility.versions must contain bounded non-empty printable release tokens"
            )


def _require_string_values(name: str, values: frozenset[str], *, required: bool = False) -> None:
    if required and not values:
        raise ValueError(f"ProvisionerCapabilities.{name} must not be empty")
    if any(not value.strip() for value in values):
        raise ValueError(f"ProvisionerCapabilities.{name} must not contain empty strings")


def _validate_operating_system_rows(capabilities: "ProvisionerCapabilities") -> None:
    os_keys = [(entry.family, entry.distribution) for entry in capabilities.operating_systems]
    if len(os_keys) != len(set(os_keys)):
        raise ValueError(
            "ProvisionerCapabilities.operating_systems must not contain duplicate family/distribution rows"
        )
    undeclared_families = {
        entry.family
        for entry in capabilities.operating_systems
        if entry.family not in capabilities.supported_os_families
    }
    if undeclared_families:
        raise ValueError(
            "ProvisionerCapabilities.operating_systems families must be present in supported_os_families: "
            + ", ".join(sorted(undeclared_families))
        )


def _validated_artifact_kinds(
    capabilities: "ProvisionerCapabilities",
) -> frozenset[GeneratedArtifactKind | DomainProfileCoordinateModel]:
    try:
        normalized = frozenset(
            kind if isinstance(kind, DomainProfileCoordinateModel) else GeneratedArtifactKind(kind)
            for kind in capabilities.supported_generated_artifact_kinds
        )
    except ValueError as exc:
        raise ValueError("ProvisionerCapabilities contains an unknown generated artifact kind") from exc
    if capabilities.supports_generated_artifacts and not normalized:
        raise ValueError(
            "ProvisionerCapabilities that support generated artifacts must declare supported_generated_artifact_kinds"
        )
    if not capabilities.supports_generated_artifacts and normalized:
        raise ValueError(
            "ProvisionerCapabilities supported_generated_artifact_kinds require supports_generated_artifacts=True"
        )
    return normalized


def _validated_artifact_delivery_modes(
    capabilities: "ProvisionerCapabilities",
) -> frozenset[GeneratedArtifactDeliveryMode]:
    try:
        normalized = frozenset(
            GeneratedArtifactDeliveryMode(mode) for mode in capabilities.supported_generated_artifact_delivery_modes
        )
    except ValueError as exc:
        raise ValueError("ProvisionerCapabilities contains an unknown generated artifact delivery mode") from exc
    if not capabilities.supports_generated_artifacts and normalized:
        raise ValueError(
            "ProvisionerCapabilities supported_generated_artifact_delivery_modes require "
            "supports_generated_artifacts=True"
        )
    # Capability manifests that predate delivery modes described mount-only
    # support. Preserve that meaning without claiming value injection.
    if capabilities.supports_generated_artifacts and not normalized:
        normalized = frozenset({GeneratedArtifactDeliveryMode.MOUNT})
    return normalized


def _validated_regeneration_scopes(
    capabilities: "ProvisionerCapabilities",
) -> frozenset[GeneratedArtifactRegenerationScope]:
    try:
        normalized = frozenset(
            GeneratedArtifactRegenerationScope(scope) for scope in capabilities.supported_regeneration_scopes
        )
    except ValueError as exc:
        raise ValueError("ProvisionerCapabilities contains an unknown regeneration scope") from exc
    supports_random_value = GeneratedArtifactKind.RANDOM_VALUE in capabilities.supported_generated_artifact_kinds
    if supports_random_value and not normalized:
        raise ValueError(
            "ProvisionerCapabilities that support the random_value generator must declare supported_regeneration_scopes"
        )
    if not supports_random_value and normalized:
        raise ValueError(
            "ProvisionerCapabilities supported_regeneration_scopes require the random_value generated artifact kind"
        )
    return normalized


def _validate_account_support(capabilities: "ProvisionerCapabilities") -> None:
    if capabilities.supports_accounts and not capabilities.supported_account_features:
        raise ValueError("ProvisionerCapabilities that support accounts must declare supported_account_features")
    if not capabilities.supports_accounts and capabilities.supported_account_features:
        raise ValueError("supported_account_features require supports_accounts=True")


def _profile_terms(values: frozenset[str | DomainProfileCoordinateModel]) -> frozenset[str]:
    if any(not isinstance(value, (str, DomainProfileCoordinateModel)) for value in values):
        raise ValueError("Profile capabilities require vocabulary terms or pinned coordinates")
    return frozenset(value for value in values if isinstance(value, str))


@dataclass(frozen=True)
class ProvisionerCapabilities:
    name: str
    supported_node_types: frozenset[str] = frozenset()
    supported_os_families: frozenset[str] = frozenset()
    operating_systems: tuple[OperatingSystemCompatibility, ...] = ()
    supported_node_architectures: frozenset[str] = frozenset()
    supported_content_types: frozenset[str] = frozenset()
    supported_account_features: frozenset[str] = frozenset()
    supported_domain_profiles: frozenset[str | DomainProfileCoordinateModel] = frozenset()
    supported_service_materialization_profiles: frozenset[str | DomainProfileCoordinateModel] = frozenset()
    max_total_nodes: int | None = None
    supports_acls: bool = False
    supports_accounts: bool = False
    supports_generated_artifacts: bool = False
    supported_generated_artifact_kinds: frozenset[GeneratedArtifactKind | DomainProfileCoordinateModel] = frozenset()
    supported_generated_artifact_delivery_modes: frozenset[GeneratedArtifactDeliveryMode] = frozenset()
    supported_regeneration_scopes: frozenset[GeneratedArtifactRegenerationScope] = frozenset()
    supports_persistent_volumes: bool = False
    constraints: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("ProvisionerCapabilities.name must be non-empty")
        _require_string_values("supported_node_types", self.supported_node_types, required=True)
        _require_string_values("supported_os_families", self.supported_os_families, required=True)
        _require_string_values("supported_node_architectures", self.supported_node_architectures)
        _require_string_values("supported_content_types", self.supported_content_types)
        _require_string_values("supported_account_features", self.supported_account_features)
        _require_string_values(
            "supported_domain_profiles",
            _profile_terms(self.supported_domain_profiles),
        )
        _require_string_values(
            "supported_service_materialization_profiles",
            _profile_terms(self.supported_service_materialization_profiles),
        )
        validate_controlled_vocabulary_scope_values(
            "capabilities.provisioner.supported_node_types",
            self.supported_node_types,
        )
        validate_controlled_vocabulary_scope_values(
            "capabilities.provisioner.supported_os_families",
            self.supported_os_families,
        )
        _validate_operating_system_rows(self)
        validate_controlled_vocabulary_scope_values(
            "capabilities.provisioner.supported_node_architectures",
            self.supported_node_architectures,
        )
        validate_controlled_vocabulary_scope_values(
            "capabilities.provisioner.supported_content_types",
            self.supported_content_types,
        )
        validate_controlled_vocabulary_scope_values(
            "capabilities.provisioner.supported_account_features",
            self.supported_account_features,
        )
        validate_controlled_vocabulary_scope_values(
            PROVISIONER_DOMAIN_PROFILE_SCOPE,
            tuple(value for value in self.supported_domain_profiles if isinstance(value, str)),
        )
        validate_controlled_vocabulary_scope_values(
            PROVISIONER_SERVICE_MATERIALIZATION_PROFILE_SCOPE,
            tuple(value for value in self.supported_service_materialization_profiles if isinstance(value, str)),
        )
        if self.max_total_nodes is not None and self.max_total_nodes < 1:
            raise ValueError("ProvisionerCapabilities.max_total_nodes must be positive when provided")
        _validate_account_support(self)
        object.__setattr__(self, "supported_generated_artifact_kinds", _validated_artifact_kinds(self))
        object.__setattr__(
            self,
            "supported_generated_artifact_delivery_modes",
            _validated_artifact_delivery_modes(self),
        )
        object.__setattr__(self, "supported_regeneration_scopes", _validated_regeneration_scopes(self))

    def supports_operating_system(
        self,
        *,
        family: str,
        distribution: str | None = None,
        version: str | None = None,
    ) -> bool:
        """Return whether one coupled capability row admits the requested identity."""

        if family not in self.supported_os_families:
            return False
        if distribution is None:
            return version is None
        return any(
            entry.family == family
            and entry.distribution == distribution
            and (version is None or version in entry.versions)
            for entry in self.operating_systems
        )


__all__ = [
    "PROVISIONER_DOMAIN_PROFILE_SCOPE",
    "PROVISIONER_SERVICE_MATERIALIZATION_PROFILE_SCOPE",
    "OperatingSystemCompatibility",
    "ProvisionerCapabilities",
]
