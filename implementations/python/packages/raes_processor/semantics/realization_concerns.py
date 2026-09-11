"""Canonical registry of authored realization concerns."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from .realization_concern_observations import (
    validate_capability_policy_observation,
    validate_environment_observation,
    validate_forwarding_agents_observation,
    validate_mounts_observation,
    validate_process_resource_limits_observation,
    validate_published_ports_observation,
    validate_service_listeners_observation,
)
from .realization_concern_projections import (
    project_capability_policy,
    project_environment,
    project_forwarding_agents,
    project_mounts,
    project_process_resource_limits,
    project_published_ports,
    project_service_listeners,
    sanitize_mount_observation,
)
from .realization_runtime_concern_profiles import (
    RUNTIME_CONCERN_PROFILES,
    RUNTIME_NON_REALIZATION_FIELDS,
    RuntimeFieldBoundary,
    runtime_configuration_boundary_inventory,
    runtime_path_annotation,
)
from .realization_typed_runtime_projection import typed_runtime_projector


@dataclass(frozen=True)
class RealizationConcernDescriptor:
    """One authored concern's compiler, payload, and comparison contract."""

    section: str
    authored_path: tuple[str, ...]
    concern_kind: str
    payload_path: tuple[str, ...]
    projector: Callable[[object, bool], object] | None = None
    sanitizer: Callable[[object, bool], object] | None = None
    observed_validator: Callable[[object], None] | None = None
    non_stateful_mounts_only: bool = False
    explicitness_excluded_fields: frozenset[str] = RUNTIME_NON_REALIZATION_FIELDS
    collection_identity_fields: tuple[str, ...] = ()

    @property
    def authored_suffix(self) -> str:
        return ".".join(self.authored_path)

    def includes_authored_value(self, value: object) -> bool:
        """Return whether an authored value belongs to this concern."""

        includes = True
        if self.non_stateful_mounts_only and isinstance(value, list) and value:
            includes = any(_mount_source_kind(item) in {"bind", "tmpfs"} for item in value)
        return includes

    def project(self, value: object, *, observed: bool = False) -> object:
        if observed and self.observed_validator is not None:
            self.observed_validator(value)
        return self.projector(value, observed) if self.projector is not None else value

    def sanitize_observation(self, value: object) -> object:
        return self.sanitize(value, observed=True)

    def sanitize(self, value: object, *, observed: bool) -> object:
        if observed and self.observed_validator is not None:
            self.observed_validator(value)
        projector = self.sanitizer or self.projector
        return projector(value, observed) if projector is not None else value


@dataclass(frozen=True)
class RegisteredRealizationConcern:
    """A descriptor bound to one named declaration."""

    declaration_name: str
    descriptor: RealizationConcernDescriptor

    @property
    def field_path(self) -> str:
        return f"{self.descriptor.section}.{self.declaration_name}.{self.descriptor.authored_suffix}"


def _mount_source_kind(item: object) -> object:
    source_kind = item.get("source_kind") if isinstance(item, Mapping) else getattr(item, "source_kind", None)
    return getattr(source_kind, "value", source_kind)


_REALIZATION_CONCERNS: tuple[RealizationConcernDescriptor, ...] = (
    RealizationConcernDescriptor(
        section="nodes",
        authored_path=("type",),
        concern_kind="node-type",
        payload_path=("node_kind",),
    ),
    RealizationConcernDescriptor(
        section="nodes",
        authored_path=("os",),
        concern_kind="os-family",
        payload_path=("os_family",),
    ),
    RealizationConcernDescriptor(
        section="nodes",
        authored_path=("os_distribution",),
        concern_kind="os-distribution",
        payload_path=("os_distribution",),
    ),
    RealizationConcernDescriptor(
        section="nodes",
        authored_path=("os_version",),
        concern_kind="os-version",
        payload_path=("os_version",),
    ),
    RealizationConcernDescriptor(
        section="nodes",
        authored_path=("architecture",),
        concern_kind="node-architecture",
        payload_path=("architecture",),
    ),
    RealizationConcernDescriptor(
        section="content",
        authored_path=("type",),
        concern_kind="content-type",
        payload_path=("spec", "type"),
    ),
    RealizationConcernDescriptor(
        section="nodes",
        authored_path=("runtime", "environment"),
        concern_kind="runtime-environment",
        payload_path=("spec", "node", "runtime", "environment"),
        projector=project_environment,
        observed_validator=validate_environment_observation,
    ),
    RealizationConcernDescriptor(
        section="nodes",
        authored_path=("runtime", "mounts"),
        concern_kind="runtime-mounts",
        payload_path=("spec", "node", "runtime", "mounts"),
        projector=project_mounts,
        sanitizer=sanitize_mount_observation,
        observed_validator=validate_mounts_observation,
        non_stateful_mounts_only=True,
    ),
    RealizationConcernDescriptor(
        section="nodes",
        authored_path=("runtime", "linux_capabilities"),
        concern_kind="linux-capabilities",
        payload_path=("spec", "node", "runtime", "linux_capabilities"),
        projector=project_capability_policy,
        observed_validator=validate_capability_policy_observation,
    ),
    RealizationConcernDescriptor(
        section="nodes",
        authored_path=("runtime", "operational_policy", "resource_limits", "process_limits"),
        concern_kind="process-resource-limits",
        payload_path=(
            "spec",
            "node",
            "runtime",
            "operational_policy",
            "resource_limits",
            "process_limits",
        ),
        projector=project_process_resource_limits,
        observed_validator=validate_process_resource_limits_observation,
    ),
    RealizationConcernDescriptor(
        section="nodes",
        authored_path=("runtime", "network", "published_ports"),
        concern_kind="published-ports",
        payload_path=("spec", "node", "runtime", "network", "published_ports"),
        projector=project_published_ports,
        observed_validator=validate_published_ports_observation,
    ),
    RealizationConcernDescriptor(
        section="nodes",
        authored_path=("runtime", "forwarding_agents"),
        concern_kind="forwarding-agents",
        payload_path=("spec", "node", "runtime", "forwarding_agents"),
        projector=project_forwarding_agents,
        observed_validator=validate_forwarding_agents_observation,
        explicitness_excluded_fields=RUNTIME_NON_REALIZATION_FIELDS | {"ownership_role"},
    ),
    RealizationConcernDescriptor(
        section="nodes",
        authored_path=("runtime", "service_listeners"),
        concern_kind="service-listeners",
        payload_path=("spec", "node", "runtime", "service_listeners"),
        projector=project_service_listeners,
        observed_validator=validate_service_listeners_observation,
    ),
    *(
        RealizationConcernDescriptor(
            section="nodes",
            authored_path=("runtime", *profile.authored_path),
            concern_kind=profile.concern_kind,
            payload_path=profile.payload_path,
            projector=typed_runtime_projector(
                runtime_path_annotation(profile.authored_path),
                concern_kind=profile.concern_kind,
                excluded_fields=profile.excluded_fields,
                sort_scalar_sequence=profile.sort_scalar_sequence,
            ),
            explicitness_excluded_fields=RUNTIME_NON_REALIZATION_FIELDS | profile.excluded_fields,
            collection_identity_fields=profile.collection_identity_fields,
        )
        for profile in RUNTIME_CONCERN_PROFILES
    ),
)

_DESCRIPTOR_BY_KIND = {descriptor.concern_kind: descriptor for descriptor in _REALIZATION_CONCERNS}

CONCERN_PAYLOAD_PATH: dict[str, tuple[str, ...]] = {
    **{descriptor.concern_kind: descriptor.payload_path for descriptor in _REALIZATION_CONCERNS},
    "domain-topology": ("domain_topology",),
    "generated-artifact": ("spec",),
    "persistent-volume": ("spec",),
    "service-content-materialization": ("service_materialization",),
    "service-search-index-schema-materialization": ("service_materialization",),
}


def registered_realization_concern_descriptors(
    *,
    declaration_names: Mapping[str, Iterable[str]],
) -> tuple[RegisteredRealizationConcern, ...]:
    """Bind every canonical descriptor to declarations in its section."""

    return tuple(
        RegisteredRealizationConcern(
            declaration_name=declaration_name,
            descriptor=descriptor,
        )
        for descriptor in _REALIZATION_CONCERNS
        for declaration_name in declaration_names.get(descriptor.section, ())
    )


def registered_realization_concerns(
    *,
    declaration_names: Mapping[str, Iterable[str]],
) -> tuple[tuple[str, str, str, str], ...]:
    """Enumerate legacy tuple registrations from the canonical descriptors."""

    return tuple(
        (
            registered.descriptor.section,
            registered.declaration_name,
            registered.descriptor.authored_suffix,
            registered.descriptor.concern_kind,
        )
        for registered in registered_realization_concern_descriptors(declaration_names=declaration_names)
    )


def resolve_realization_concern(
    field_path: str,
    *,
    declaration_names: Mapping[str, Iterable[str]],
) -> str | None:
    """Return the registered realization concern kind for a classifier path."""

    return next(
        (
            registered.descriptor.concern_kind
            for registered in registered_realization_concern_descriptors(declaration_names=declaration_names)
            if registered.field_path == field_path
        ),
        None,
    )


def realization_concern_descriptor(
    concern_kind: str,
) -> RealizationConcernDescriptor | None:
    """Return the canonical descriptor for a concern kind, when registered."""

    return _DESCRIPTOR_BY_KIND.get(concern_kind)


def realization_concern_descriptors() -> tuple[RealizationConcernDescriptor, ...]:
    """Return the canonical unbound concern inventory in declaration order."""

    return _REALIZATION_CONCERNS


def processor_derived_provisioning_concern_kinds(
    resource_type: object,
    payload: object,
) -> tuple[str, ...]:
    """Return exact provisioning concerns derived from a typed resource."""

    if not isinstance(resource_type, str) or not isinstance(payload, Mapping):
        return ()
    concerns: list[str] = []
    if payload.get("domain_topology") is not None:
        concerns.append("domain-topology")
    if resource_type == "generated-artifact":
        concerns.append("generated-artifact")
    elif resource_type == "persistent-volume":
        concerns.append("persistent-volume")
    elif resource_type == "content-placement":
        binding = payload.get("service_materialization")
        if isinstance(binding, Mapping):
            concerns.append(
                "service-search-index-schema-materialization"
                if binding.get("interface_profile") == "service-search-index-schema"
                else "service-content-materialization"
            )
    return tuple(concerns)


def project_realization_concern(
    concern_kind: str,
    value: object,
    *,
    observed: bool = False,
) -> object:
    """Project one value through its canonical registered descriptor."""

    descriptor = realization_concern_descriptor(concern_kind)
    return descriptor.project(value, observed=observed) if descriptor is not None else value


__all__ = [
    "CONCERN_PAYLOAD_PATH",
    "RealizationConcernDescriptor",
    "RegisteredRealizationConcern",
    "RuntimeFieldBoundary",
    "project_realization_concern",
    "processor_derived_provisioning_concern_kinds",
    "realization_concern_descriptor",
    "realization_concern_descriptors",
    "registered_realization_concern_descriptors",
    "registered_realization_concerns",
    "resolve_realization_concern",
    "runtime_configuration_boundary_inventory",
]
