"""Closed identity and authority-shape checks for native planning carriers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .addressing import require_compiled_address

if TYPE_CHECKING:
    from .planning import PlannedResource, PlanOperation, ResolvedRealizationAuthority, RuntimeDomain


def _validate_plan_addresses(
    resources: dict[str, PlannedResource],
    operations: list[PlanOperation],
    startup_order: list[str] | None = None,
    *,
    domain: RuntimeDomain,
) -> None:
    from .planning import require_plan_operation_identity

    for map_key, resource in resources.items():
        require_compiled_address(map_key, field_name="resource map key")
        if map_key != resource.address:
            raise ValueError("Plan resource map key must equal embedded address")
        if resource.domain is not domain:
            raise ValueError("Plan resource domain must equal the plan domain")
        require_plan_operation_identity(domain, resource.address, resource.resource_type)
    operation_addresses = [operation.address for operation in operations]
    for operation in operations:
        require_plan_operation_identity(domain, operation.address, operation.resource_type)
    if len(operation_addresses) != len(set(operation_addresses)):
        raise ValueError("Plan operation addresses must be unique")
    if startup_order is None:
        return
    for address in startup_order:
        require_compiled_address(address, field_name="startup_order address")
    if len(startup_order) != len(set(startup_order)):
        raise ValueError("Plan startup_order addresses must be unique")
    unknown = set(startup_order) - set(operation_addresses)
    if unknown:
        raise ValueError("Plan startup_order must reference admitted operation addresses")


def _validate_realization_authority(
    operations: list[PlanOperation],
    authority: tuple[ResolvedRealizationAuthority, ...],
) -> None:
    from .planning import ChangeAction

    identities = [(entry.address, entry.requirement_kind) for entry in authority]
    if len(identities) != len(set(identities)):
        raise ValueError("Provisioning plan realization authority must identify unique concerns")
    pointers = [(entry.address, entry.payload_pointer) for entry in authority]
    if len(pointers) != len(set(pointers)):
        raise ValueError("Provisioning plan realization authority payload pointers must be unique per resource")
    admitted_addresses = {operation.address for operation in operations if operation.action is not ChangeAction.DELETE}
    stale = sorted({entry.address for entry in authority} - admitted_addresses)
    if stale:
        raise ValueError("Provisioning plan realization authority must reference non-delete operations")
