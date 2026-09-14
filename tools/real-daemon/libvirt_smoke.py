"""Real-daemon smoke test for the libvirt backend (#604 reconciliation/teardown).

Runs against a real libvirtd (qemu:///system) with real QEMU domains, virtual
networks, and nwfilters. Validates the create/update/delete/unchanged
reconciliation and the idempotent, orphan-free, fail-closed teardown the #604 fix
adds. Exits non-zero if any check fails.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import libvirt
from _libvirt_smoke_support import (
    CIRROS,
    FW_ADDRESS,
    LAN_ADDRESS,
    PREFIX,
    RESULTS,
    RUN_DIR,
    URI,
    WEB_ADDRESS,
    _net_payload,
    _node_payload,
    _plan,
    _verify_cirros_image,
    check,
    dom_exists,
    dom_state_running,
    net_exists,
    new_driver,
    purge,
    raw,
)
from raes_backend_libvirt import LibvirtProvisioner
from raes_backend_libvirt.cloudinit import CloudInitSpec, CloudInitUser
from raes_backend_libvirt.driver import DomainSpec, NetworkAcl, NetworkSpec
from raes_backend_libvirt.drivers.libvirt import (
    LibvirtDeploymentDriver,
    _filter_owner_uuid,
)
from raes_contracts.planning import (
    ChangeAction,
    PlannedResource,
    ProvisioningPlan,
    ProvisionOp,
    RuntimeDomain,
)
from raes_contracts.runtime_state import RuntimeSnapshot

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def t_abi_absence_behavior() -> str:
    conn = raw()
    try:
        try:
            conn.lookupByName("raestest-nope-xyz")
            raise AssertionError("expected libvirtError for missing domain")
        except libvirt.libvirtError as e:
            assert e.get_error_code() == 42, e.get_error_code()
        try:
            conn.networkLookupByName("raestest-nope-xyz")
            raise AssertionError("expected libvirtError for missing network")
        except libvirt.libvirtError as e:
            assert e.get_error_code() == 43, e.get_error_code()
        return "missing lookups raise VIR_ERR_NO_DOMAIN(42)/NO_NETWORK(43)"
    finally:
        conn.close()


def t_create_network_and_domain() -> str:
    d = new_driver()
    res = d.realize(
        networks=(NetworkSpec(address=LAN_ADDRESS, name="lan", cidr="192.168.221.0/24", gateway="192.168.221.1"),),
        domains=(
            DomainSpec(
                address=WEB_ADDRESS,
                name="web",
                image_ref=None,
                memory_mib=256,
                vcpus=1,
                networks=(LAN_ADDRESS,),
            ),
        ),
    )
    assert not res.diagnostics, [x.code for x in res.diagnostics]
    assert d.realized_addresses() == {LAN_ADDRESS, WEB_ADDRESS}
    conn = raw()
    try:
        assert net_exists(conn, "raestest-lan"), "network not defined"
        assert conn.networkLookupByName("raestest-lan").isActive() == 1, "network not active"
        assert dom_exists(conn, "raestest-web"), "domain not defined"
        assert dom_state_running(conn, "raestest-web"), "domain not running"
    finally:
        conn.close()
    return "real network active + real domain running under QEMU"


def t_update_reconverges_no_duplicate() -> str:
    # Same driver instance, re-realize -> converge (stop+undefine+redefine), no dup.
    d = new_driver()
    specs = {
        "networks": (
            NetworkSpec(
                address="provision.network.lan2", name="lan2", cidr="192.168.224.0/24", gateway="192.168.224.1"
            ),
        ),
        "domains": (DomainSpec(address="provision.node.web2", name="web2", image_ref=None, memory_mib=256, vcpus=1),),
    }
    r1 = d.realize(**specs)
    assert not r1.diagnostics, [x.code for x in r1.diagnostics]
    # UPDATE / converge
    r2 = d.realize(**specs)
    assert not r2.diagnostics, [x.code for x in r2.diagnostics]
    conn = raw()
    try:
        doms = [x.name() for x in conn.listAllDomains() if x.name() == "raestest-web2"]
        nets = [x.name() for x in conn.listAllNetworks() if x.name() == "raestest-lan2"]
        assert len(doms) == 1, f"duplicate domains: {doms}"
        assert len(nets) == 1, f"duplicate networks: {nets}"
        assert dom_state_running(conn, "raestest-web2")
    finally:
        conn.close()
    # teardown
    d.destroy(networks=("provision.network.lan2",), domains=("provision.node.web2",))
    return "re-realize converged in place; exactly one domain/network, no duplicate"


def t_teardown_removes_everything() -> str:
    # tear down the objects from t_create via a FRESH driver (snapshot-style teardown).
    d = new_driver()
    res = d.destroy(networks=(LAN_ADDRESS,), domains=(WEB_ADDRESS,))
    assert not res.diagnostics, [x.code for x in res.diagnostics]
    assert all(not h.realized for h in (*res.networks, *res.domains))
    conn = raw()
    try:
        assert not dom_exists(conn, "raestest-web"), "domain orphaned after teardown"
        assert not net_exists(conn, "raestest-lan"), "network orphaned after teardown"
    finally:
        conn.close()
    return "fresh-driver teardown removed real domain + network (no orphans)"


def t_teardown_idempotent() -> str:
    d = new_driver()
    res = d.destroy(networks=(LAN_ADDRESS,), domains=(WEB_ADDRESS,))
    assert not res.diagnostics, [x.code for x in res.diagnostics]
    assert all(not h.realized for h in (*res.networks, *res.domains))
    # also a never-realized address
    res2 = d.destroy(networks=(), domains=("provision.node.ghost",))
    assert not res2.diagnostics, [x.code for x in res2.diagnostics]
    assert res2.domains[0].realized is False
    return "repeated teardown + never-realized teardown are clean no-ops"


def t_teardown_inactive_domain() -> str:
    # finding-2 benign path: stop out-of-band (inactive+defined), then teardown.
    d = new_driver()
    r = d.realize(
        networks=(), domains=(DomainSpec(address="provision.node.inact", name="inact", image_ref=None, memory_mib=256),)
    )
    assert not r.diagnostics, [x.code for x in r.diagnostics]
    conn = raw()
    try:
        dom = conn.lookupByName("raestest-inact")
        # stop it out of band -> defined but inactive
        dom.destroy()
        assert dom.isActive() == 0
    finally:
        conn.close()
    res = d.destroy(networks=(), domains=("provision.node.inact",))
    assert not res.diagnostics, f"inactive teardown should be clean: {[x.code for x in res.diagnostics]}"
    conn = raw()
    try:
        assert not dom_exists(conn, "raestest-inact"), "inactive domain not undefined"
    finally:
        conn.close()
    return "teardown of an already-inactive domain (VIR_ERR_OPERATION_INVALID on stop) succeeds"


def t_ownership_conflict_not_destroyed() -> str:
    # Define a FOREIGN domain at our runtime name with a different UUID; driver
    # teardown must refuse and leave it intact.
    name = "raestest-foreign"
    foreign_uuid = "11111111-2222-3333-4444-555555555555"
    xml = f"""<domain type='qemu'><name>{name}</name><uuid>{foreign_uuid}</uuid>
      <memory unit='MiB'>64</memory><vcpu>1</vcpu>
      <os><type arch='x86_64'>hvm</type></os><devices></devices></domain>"""
    conn = raw()
    try:
        conn.defineXML(xml)
    finally:
        conn.close()
    d = new_driver()
    res = d.destroy(networks=(), domains=("provision.node.foreign",))
    assert [x.code for x in res.diagnostics] == ["libvirt-backend.driver.ownership-conflict"], [
        x.code for x in res.diagnostics
    ]
    conn = raw()
    try:
        assert dom_exists(conn, name), "foreign domain was wrongly destroyed"
        assert conn.lookupByName(name).UUIDString() == foreign_uuid
        # cleanup foreign
        conn.lookupByName(name).undefine()
    finally:
        conn.close()
    return "foreign domain at same name refused (ownership-conflict), left intact"


def t_nwfilter_lifecycle() -> str:
    d = new_driver()
    acl = NetworkAcl(name="deny", action="drop", direction="inout", protocol="all")
    r = d.realize(
        networks=(),
        domains=(DomainSpec(address=FW_ADDRESS, name="fw", image_ref=None, memory_mib=256, network_acls=(acl,)),),
    )
    assert not r.diagnostics, [x.code for x in r.diagnostics]
    conn = raw()
    try:
        # raises if missing
        nf = conn.nwfilterLookupByName("raestest-fw-acl")
        assert nf.UUIDString() == _filter_owner_uuid(FW_ADDRESS)
    finally:
        conn.close()
    d.destroy(networks=(), domains=(FW_ADDRESS,))
    conn = raw()
    try:
        gone = False
        try:
            conn.nwfilterLookupByName("raestest-fw-acl")
        except libvirt.libvirtError:
            gone = True
        assert gone, "nwfilter not undefined after teardown"
    finally:
        conn.close()
    return "nwfilter defined on realize, owner-stamped, undefined on teardown"


def t_partial_create_rollback() -> str:
    # Real partial CREATE: define succeeds, create() fails (bad disk) -> the driver
    # must roll back the just-defined domain so nothing is orphaned.
    d = new_driver()
    res = d.realize(
        networks=(),
        domains=(
            DomainSpec(address="provision.node.bad", name="bad", image_ref="/nonexistent/nope.qcow2", memory_mib=256),
        ),
    )
    assert res.diagnostics and res.diagnostics[0].code == "libvirt-backend.driver.operation-failed", [
        x.code for x in res.diagnostics
    ]
    conn = raw()
    try:
        assert not dom_exists(conn, "raestest-bad"), "partial-create domain orphaned (not rolled back)"
    finally:
        conn.close()
    return "domain whose start failed was rolled back (undefined) - no orphan"


def t_provisioner_full_stack() -> str:
    # LibvirtProvisioner -> real driver: CREATE then DELETE (teardown) then idempotent re-DELETE.
    drv = LibvirtDeploymentDriver(connection_uri=URI, name_prefix="raesprov", workspace=RUN_DIR)
    prov = LibvirtProvisioner(drv)
    net = PlannedResource(
        address="provision.network.pnet",
        domain=RuntimeDomain.PROVISIONING,
        resource_type="network",
        payload=_net_payload("pnet", "192.168.225.0/24", "192.168.225.1"),
    )
    node = PlannedResource(
        address="provision.node.pweb",
        domain=RuntimeDomain.PROVISIONING,
        resource_type="node",
        payload=_node_payload("pweb"),
    )

    create = prov.apply(_plan(net, node), RuntimeSnapshot())
    assert create.success, [x.code for x in create.diagnostics]
    assert set(create.snapshot.entries) == {"provision.network.pnet", "provision.node.pweb"}
    conn = raw()
    try:
        assert net_exists(conn, "raesprov-pnet") and conn.networkLookupByName("raesprov-pnet").isActive() == 1
        assert dom_exists(conn, "raesprov-pweb") and dom_state_running(conn, "raesprov-pweb")
    finally:
        conn.close()

    # teardown via a DELETE plan built from the snapshot (as RuntimeManager.destroy does)
    del_ops = []
    for addr, e in create.snapshot.entries.items():
        del_ops.append(
            ProvisionOp(
                action=ChangeAction.DELETE,
                address=addr,
                resource_type=e.resource_type,
                payload=e.payload,
                ordering_dependencies=e.ordering_dependencies,
                refresh_dependencies=e.refresh_dependencies,
            )
        )
    delete_plan = ProvisioningPlan(resources={}, operations=del_ops)
    teardown = prov.apply(delete_plan, create.snapshot)
    assert teardown.success, [x.code for x in teardown.diagnostics]
    assert teardown.snapshot.entries == {}
    conn = raw()
    try:
        assert not dom_exists(conn, "raesprov-pweb"), "provisioner teardown orphaned domain"
        assert not net_exists(conn, "raesprov-pnet"), "provisioner teardown orphaned network"
    finally:
        conn.close()

    # idempotent re-DELETE against the now-empty snapshot
    again = prov.apply(delete_plan, teardown.snapshot)
    assert again.success, [x.code for x in again.diagnostics]
    return "provisioner CREATE->teardown->idempotent re-teardown through real libvirt"


def t_cirros_real_boot_and_teardown() -> str:
    # Full realize path: cirros overlay disk + cloud-init seed (genisoimage) ->
    # a real guest OS boots, then is torn down. The backing image is reverified
    # against its pinned identity before it is booted, and the overlay lives in
    # the scoped run directory (under the libvirt images tree) so no host
    # security downgrade is needed.
    _verify_cirros_image()
    overlay_dir = RUN_DIR or tempfile.gettempdir()
    overlay = os.path.join(overlay_dir, "raes-cirros-overlay.qcow2")
    subprocess.run(
        ["qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", CIRROS, overlay], check=True, capture_output=True
    )
    d = new_driver()
    ci = CloudInitSpec(hostname="cirros", users=(CloudInitUser(name="tester"),))
    r = d.realize(
        networks=(),
        domains=(
            DomainSpec(
                address="provision.node.cirros",
                name="cirros",
                image_ref=overlay,
                memory_mib=256,
                vcpus=1,
                cloud_init=ci,
            ),
        ),
    )
    assert not r.diagnostics, [x.code for x in r.diagnostics]
    conn = raw()
    try:
        assert dom_state_running(conn, "raestest-cirros"), "cirros domain not running"
        xml = conn.lookupByName("raestest-cirros").XMLDesc()
        assert "cdrom" in xml and ".iso" in xml, "cloud-init seed ISO not attached"
    finally:
        conn.close()
    res = d.destroy(networks=(), domains=("provision.node.cirros",))
    assert not res.diagnostics, [x.code for x in res.diagnostics]
    conn = raw()
    try:
        assert not dom_exists(conn, "raestest-cirros"), "cirros domain orphaned"
    finally:
        conn.close()
    return "real cirros guest booted with cloud-init seed ISO, then torn down cleanly"


def t_no_orphans_at_end() -> str:
    conn = raw()
    try:
        doms = [x.name() for x in conn.listAllDomains() if x.name().startswith((PREFIX, "raesprov"))]
        nets = [x.name() for x in conn.listAllNetworks() if x.name().startswith((PREFIX, "raesprov"))]
        nfs = [x.name() for x in conn.listAllNWFilters() if x.name().startswith((PREFIX, "raesprov"))]
        assert not doms and not nets and not nfs, f"orphans left: doms={doms} nets={nets} nfs={nfs}"
    finally:
        conn.close()
    return "no raestest/raesprov domains, networks, or nwfilters remain"


def main() -> int:
    print("=== purge any prior leftovers ===")
    purge()
    tests = [
        t_abi_absence_behavior,
        t_create_network_and_domain,
        t_update_reconverges_no_duplicate,
        t_teardown_removes_everything,
        t_teardown_idempotent,
        t_teardown_inactive_domain,
        t_ownership_conflict_not_destroyed,
        t_nwfilter_lifecycle,
        t_partial_create_rollback,
        t_provisioner_full_stack,
        t_cirros_real_boot_and_teardown,
        t_no_orphans_at_end,
    ]
    for t in tests:
        check(t.__name__, t)
    print("\n=== final purge ===")
    purge()
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\nSUMMARY: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
