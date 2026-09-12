"""Batch orchestration helpers for the generic libvirt deployment driver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.diagnostics import Diagnostic

from raes_backend_libvirt.driver import DomainHandle, DomainSpec, NetworkHandle, NetworkSpec

if TYPE_CHECKING:
    from .deployment import LibvirtDeploymentDriver


def realize_network_specs(
    driver: LibvirtDeploymentDriver,
    connection: object,
    specs: tuple[NetworkSpec, ...],
    created: list[str],
    handles: list[NetworkHandle],
    diagnostics: list[Diagnostic],
) -> None:
    for spec in specs:
        failure = driver._realize_network(connection, spec, created)
        if failure is not None:
            diagnostics.append(failure)
        else:
            handles.append(NetworkHandle(address=spec.address, realized=True))


def realize_domain_specs(
    driver: LibvirtDeploymentDriver,
    connection: object,
    specs: tuple[DomainSpec, ...],
    created: list[str],
    handles: list[DomainHandle],
    diagnostics: list[Diagnostic],
) -> None:
    for spec in specs:
        failure = driver._realize_domain(connection, spec, created)
        if failure is not None:
            diagnostics.append(failure)
            continue
        handles.append(DomainHandle(address=spec.address, realized=True))


__all__ = ["realize_domain_specs", "realize_network_specs"]
