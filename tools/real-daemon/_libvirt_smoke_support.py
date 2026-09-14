"""Shared harness support for the libvirt real-daemon smoke test (#604).

Split out of ``libvirt_smoke.py`` so each file stays a focused, reviewable unit
(issue #1222): this module owns the connection helpers, the scoped-run/CirrOS
configuration, the leftover purge, the result recorder, and the plan/payload
builders. The smoke cases and the entry point live in ``libvirt_smoke.py``.
"""

from __future__ import annotations

import contextlib
import os
import traceback
from collections.abc import Callable

import libvirt
from _object_identity import verify_object_identity
from raes_backend_libvirt.drivers.libvirt import LibvirtDeploymentDriver
from raes_contracts.planning import (
    ChangeAction,
    PlannedResource,
    ProvisioningPlan,
    ProvisionOp,
)

URI = "qemu:///system"
PREFIX = "raestest"

# Scoped per-run private directory (issue #1222). When set by the runner it lives
# under the libvirt images tree so the guest disk overlay and cloud-init seed
# media are reachable by the daemon under its *default* security driver — the
# scripts no longer weaken host security (no security_driver="none", no root
# QEMU user/group). Seeds render inside this workspace via the driver.
RUN_DIR = os.environ.get("RAES_LIBVIRT_RUN_DIR") or None

# The admitted CirrOS guest disk. Its path and reviewed digest/size are supplied
# by the runner from the pinned artifact lock (cirros-guest-disk); the harness
# reverifies the bytes before booting them (fail-closed) so an unpinned or
# tampered image cannot be executed.
CIRROS = os.environ.get("RAES_CIRROS_IMAGE", "/var/lib/libvirt/images/cirros.img")
CIRROS_SHA256 = os.environ.get("RAES_CIRROS_SHA256") or None
CIRROS_SIZE = int(os.environ["RAES_CIRROS_SIZE"]) if os.environ.get("RAES_CIRROS_SIZE") else None
LAN_ADDRESS = "provision.network.lan"
WEB_ADDRESS = "provision.node.web"
FW_ADDRESS = "provision.node.fw"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn: Callable[[], str | None]) -> None:
    try:
        detail = fn()
        RESULTS.append((name, True, detail or ""))
        print(f"PASS  {name}  {detail or ''}")
    except Exception as exc:  # noqa: BLE001  # harness reports every failure
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))
        print(f"FAIL  {name}  {type(exc).__name__}: {exc}")
        traceback.print_exc()


def raw() -> libvirt.virConnect:
    return libvirt.open(URI)


def dom_exists(conn: libvirt.virConnect, name: str) -> bool:
    try:
        conn.lookupByName(name)
        return True
    except libvirt.libvirtError as e:
        if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
            return False
        raise


def net_exists(conn: libvirt.virConnect, name: str) -> bool:
    try:
        conn.networkLookupByName(name)
        return True
    except libvirt.libvirtError as e:
        if e.get_error_code() == libvirt.VIR_ERR_NO_NETWORK:
            return False
        raise


def dom_state_running(conn: libvirt.virConnect, name: str) -> bool:
    dom = conn.lookupByName(name)
    return dom.isActive() == 1


def new_driver() -> LibvirtDeploymentDriver:
    return LibvirtDeploymentDriver(connection_uri=URI, name_prefix=PREFIX, workspace=RUN_DIR)


def _verify_cirros_image() -> None:
    """Fail closed unless the CirrOS image matches its reviewed size and digest.

    The runner exports the pinned identity from the artifact lock
    (cirros-guest-disk); this is the on-host reverification of pre-seeded bytes
    the plan calls for. The pure verification lives in ``_object_identity`` so it
    is exercised by the hermetic test suite (this module cannot be imported there
    because it imports ``libvirt``).
    """

    verify_object_identity(CIRROS, expected_sha256=CIRROS_SHA256, expected_size=CIRROS_SIZE)


def purge() -> None:
    """Best-effort removal of any leftover raestest-* / raesprov-* objects."""
    conn = raw()
    for obj in [*conn.listAllDomains(), *conn.listAllNetworks()]:
        try:
            nm = obj.name()
        except libvirt.libvirtError:
            continue
        if not nm.startswith((PREFIX, "raesprov")):
            continue
        with contextlib.suppress(libvirt.libvirtError):
            if obj.isActive():
                obj.destroy()
        with contextlib.suppress(libvirt.libvirtError):
            obj.undefine()
    for nf in conn.listAllNWFilters():
        try:
            nm = nf.name()
        except libvirt.libvirtError:
            continue
        if nm.startswith((PREFIX, "raesprov")):
            with contextlib.suppress(libvirt.libvirtError):
                nf.undefine()
    conn.close()


def _node_payload(addr_tail: str, *, source: str | None = None, networks: tuple[str, ...] = ()) -> dict[str, object]:
    node = {"type": "compute", "resources": {"ram": 268435456, "cpu": 1}}
    if source is not None:
        node["source"] = {"name": source}
    spec = {"node": node, "infrastructure": {"networks": list(networks)}}
    return {"name": addr_tail, "node_name": addr_tail, "node_type": "vm", "os_family": "linux", "spec": spec}


def _net_payload(addr_tail: str, cidr: str, gw: str) -> dict[str, object]:
    return {
        "name": addr_tail,
        "spec": {"infrastructure": {"properties": {"internal": True, "cidr": cidr, "gateway": gw}}},
    }


def _plan(*resources: PlannedResource, action: ChangeAction = ChangeAction.CREATE) -> ProvisioningPlan:
    return ProvisioningPlan(
        resources={r.address: r for r in resources},
        operations=[
            ProvisionOp(
                action=action,
                address=r.address,
                resource_type=r.resource_type,
                payload=r.payload,
                ordering_dependencies=r.ordering_dependencies,
                refresh_dependencies=r.refresh_dependencies,
            )
            for r in resources
        ],
    )
