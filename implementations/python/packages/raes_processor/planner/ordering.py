"""Dependency ordering, cycle detection, and delete ordering for planned resources."""

from ..models import Diagnostic, PlannedResource, RuntimeDomain, SnapshotEntry
from ..semantics.planner import (
    resource_delete_order,
    resource_dependency_cycles,
    resource_topological_order,
)
from ..semantics.realization import CompiledRealizationRequirement
from ..semantics.realization_snapshot_sanitization import realization_payloads_match


def _ordering_cycles(resources: dict[str, PlannedResource]) -> list[tuple[str, ...]]:
    return resource_dependency_cycles(resources)


def _ordering_cycle_diagnostics(
    resources: dict[str, PlannedResource],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    for domain in RuntimeDomain:
        domain_resources = {address: resource for address, resource in resources.items() if resource.domain == domain}
        for cycle in _ordering_cycles(domain_resources):
            rendered = ", ".join(cycle)
            diagnostics.append(
                Diagnostic(
                    code=f"{domain.value}.ordering-cycle",
                    domain=domain.value,
                    address=cycle[0],
                    message=(
                        f"{domain.value.capitalize()} ordering dependencies "
                        f"must be acyclic; detected cycle: {rendered}."
                    ),
                )
            )

    return diagnostics


def _topological_order(resources: dict[str, PlannedResource]) -> list[str]:
    return resource_topological_order(resources)


def _entry_matches_resource(
    entry: SnapshotEntry,
    resource: PlannedResource,
    realization_requirements: tuple[CompiledRealizationRequirement, ...] = (),
) -> bool:
    return (
        entry.domain == resource.domain
        and entry.profile_bindings == resource.profile_bindings
        and entry.resource_type == resource.resource_type
        and realization_payloads_match(
            entry.address,
            resource.payload,
            entry.payload,
            realization_requirements,
        )
        and entry.ordering_dependencies == resource.ordering_dependencies
        and entry.refresh_dependencies == resource.refresh_dependencies
    )


def _delete_order(entries: dict[str, SnapshotEntry]) -> list[str]:
    resources = {
        address: PlannedResource(
            address=entry.address,
            domain=entry.domain,
            resource_type=entry.resource_type,
            payload=entry.payload,
            ordering_dependencies=entry.ordering_dependencies,
            refresh_dependencies=entry.refresh_dependencies,
        )
        for address, entry in entries.items()
    }
    return resource_delete_order(resources)


def snapshot_delete_order(entries: dict[str, SnapshotEntry]) -> list[str]:
    """Return delete order for existing snapshot entries."""

    return _delete_order(entries)
