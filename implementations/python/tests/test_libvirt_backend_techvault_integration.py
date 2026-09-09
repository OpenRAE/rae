"""Issue #601: TechVault scenarios drive libvirt provisioning."""

from __future__ import annotations

import re
from collections import Counter

from libvirt_conformance_fixtures import daemon_compute_substrate_observations
from paths import EXAMPLES_DIR
from raes import parse_sdl
from raes_backend_libvirt import create_libvirt_target
from raes_backend_libvirt.driver import DomainHandle, DriverResult, NetworkHandle
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.manager import RuntimeManager

_TECHVAULT_PARAMETERS = {
    "app_py_sha256": "a" * 64,
    "requirements_sha256": "b" * 64,
    "style_css_sha256": "c" * 64,
    "webapp_conf_sha256": "d" * 64,
    "wazuh_conf_sha256": "e" * 64,
}


def _without_os_identity(source: str):
    return parse_sdl(re.sub(r"(?m)^\s+os(?:_distribution|_version)?:.*\n", "", source))


def _without_unsupported_runtime_realization(source: str):
    scenario = _without_os_identity(source)
    return scenario.model_copy(
        update={"nodes": {name: node.model_copy(update={"runtime": None}) for name, node in scenario.nodes.items()}}
    )


class _RecordingLibvirtDriver:
    driver_mode = "generic"

    def __init__(self) -> None:
        self.realize_calls: list[dict[str, object]] = []
        self.destroy_calls: list[dict[str, object]] = []
        self._realized: set[str] = set()

    def realize(self, *, networks, domains):
        self.realize_calls.append({"networks": networks, "domains": domains})
        self._realized.update(spec.address for spec in networks)
        self._realized.update(spec.address for spec in domains)
        return DriverResult(
            networks=tuple(NetworkHandle(address=spec.address) for spec in networks),
            domains=tuple(DomainHandle(address=spec.address) for spec in domains),
            observations=daemon_compute_substrate_observations(domains),
        )

    def destroy(self, *, networks, domains):
        self.destroy_calls.append({"networks": networks, "domains": domains})
        self._realized.difference_update(networks)
        self._realized.difference_update(domains)
        return DriverResult(
            networks=tuple(NetworkHandle(address=address, realized=False) for address in networks),
            domains=tuple(DomainHandle(address=address, realized=False) for address in domains),
        )

    def realized_addresses(self):
        return frozenset(self._realized)


def test_techvault_runtime_inventory_is_honestly_rejected_by_libvirt():
    driver = _RecordingLibvirtDriver()
    target = create_libvirt_target(driver=driver, name_prefix="techvault-unsupported")
    manager = RuntimeManager(target)
    scenario = _without_os_identity((EXAMPLES_DIR / "techvault.sdl.yaml").read_text(encoding="utf-8"))

    execution_plan = manager.plan(scenario, parameters=_TECHVAULT_PARAMETERS)

    assert not execution_plan.is_valid
    assert any(
        diagnostic.code == "realization.unsupported-constraint-requirement"
        and "runtime-filesystem-inventory" in diagnostic.message
        for diagnostic in execution_plan.diagnostics
    )
    assert not driver.realize_calls


def test_techvault_scenario_plans_and_applies_supported_surface_through_libvirt_provisioning():
    driver = _RecordingLibvirtDriver()
    target = create_libvirt_target(driver=driver, name_prefix="techvault-test")
    manager = RuntimeManager(target)
    scenario = _without_unsupported_runtime_realization(
        (EXAMPLES_DIR / "techvault.sdl.yaml").read_text(encoding="utf-8")
    )

    execution_plan = manager.plan(scenario, parameters=_TECHVAULT_PARAMETERS)

    assert execution_plan.is_valid
    assert execution_plan.model.scenario_name == "techvault-runtime-parity"
    assert len(execution_plan.model.node_deployments) == 1
    assert len(execution_plan.model.networks) == 2
    assert Counter(resource.resource_type for resource in execution_plan.provisioning.resources.values()) == Counter(
        {"network": 2, "node": 1}
    )

    control_plane = RuntimeControlPlane(target)
    control_plane.register_planner_produced_plan(execution_plan)
    receipt = control_plane.submit_provisioning(execution_plan.provisioning)
    status = control_plane.get_operation(receipt.operation_id)

    assert status is not None
    assert status.state.value == "succeeded"
    assert not status.diagnostics
    assert len(driver.realize_calls) == 1
    networks = driver.realize_calls[0]["networks"]
    domains = driver.realize_calls[0]["domains"]
    assert [spec.address for spec in networks] == [
        "provision.network.aptl-dmz",
        "provision.network.aptl-internal",
    ]
    assert [spec.address for spec in domains] == ["provision.node.techvault-webapp"]
    assert domains[0].image_ref == "techvault-webapp"
    assert domains[0].memory_mib == 1024
    assert domains[0].vcpus == 1
    assert domains[0].networks == (
        "provision.network.aptl-dmz",
        "provision.network.aptl-internal",
    )

    snapshot = control_plane.snapshot
    assert set(snapshot.entries) == {
        "provision.network.aptl-dmz",
        "provision.network.aptl-internal",
        "provision.node.techvault-webapp",
    }
    rendered_snapshot = repr(snapshot.entries["provision.node.techvault-webapp"].payload)
    assert "${" not in rendered_snapshot
    assert _TECHVAULT_PARAMETERS["app_py_sha256"] in rendered_snapshot
    assert _TECHVAULT_PARAMETERS["webapp_conf_sha256"] in rendered_snapshot
    assert driver.realized_addresses() == frozenset(snapshot.entries)


def test_techvault_operational_scenario_drives_full_libvirt_surface():
    driver = _RecordingLibvirtDriver()
    target = create_libvirt_target(driver=driver, name_prefix="techvault-operational")
    manager = RuntimeManager(target)
    scenario = _without_os_identity((EXAMPLES_DIR / "techvault-operational.sdl.yaml").read_text(encoding="utf-8"))

    admission_plan = manager.plan(scenario)

    assert not admission_plan.is_valid
    assert any(diagnostic.code == "evaluator.missing" for diagnostic in admission_plan.diagnostics)

    provisioning_projection = scenario.model_copy(
        update={
            "conditions": {},
            "nodes": {name: node.model_copy(update={"conditions": {}}) for name, node in scenario.nodes.items()},
        }
    )
    execution_plan = manager.plan(provisioning_projection)

    assert execution_plan.is_valid
    assert execution_plan.model.scenario_name == "techvault"
    assert len(execution_plan.model.node_deployments) == 30
    assert len(execution_plan.model.networks) == 4
    assert Counter(resource.resource_type for resource in execution_plan.provisioning.resources.values()) == Counter(
        {"node": 30, "network": 4}
    )

    control_plane = RuntimeControlPlane(target)
    control_plane.register_planner_produced_plan(execution_plan)
    receipt = control_plane.submit_provisioning(execution_plan.provisioning)
    status = control_plane.get_operation(receipt.operation_id)

    assert status is not None
    assert status.state.value == "succeeded"
    assert not status.diagnostics
    assert len(driver.realize_calls) == 1
    networks = driver.realize_calls[0]["networks"]
    domains = driver.realize_calls[0]["domains"]
    assert [spec.address for spec in networks] == [
        "provision.network.dmz-net",
        "provision.network.internal-net",
        "provision.network.redteam-net",
        "provision.network.security-net",
    ]
    domain_by_name = {spec.name: spec for spec in domains}
    assert set(domain_by_name) == {
        "ad",
        "aptl-grafana-otel",
        "aptl-otel-collector",
        "aptl-tempo",
        "cortex",
        "db",
        "dns",
        "fileshare",
        "kali",
        "kali-capture",
        "misp",
        "misp-db",
        "misp-redis",
        "misp-suricata-sync",
        "shuffle-backend",
        "shuffle-frontend",
        "shuffle-opensearch",
        "shuffle-orborus",
        "suricata",
        "thehive",
        "thehive-cassandra",
        "thehive-es",
        "victim",
        "wazuh-dashboard",
        "wazuh-indexer",
        "wazuh-manager",
        "wazuh-sidecar-db",
        "wazuh-sidecar-suricata",
        "webapp",
        "workstation",
    }
    assert domain_by_name["wazuh-manager"].networks == (
        "provision.network.security-net",
        "provision.network.dmz-net",
        "provision.network.internal-net",
    )
    assert domain_by_name["kali"].networks == (
        "provision.network.redteam-net",
        "provision.network.dmz-net",
        "provision.network.internal-net",
    )
    assert domain_by_name["suricata"].networks == (
        "provision.network.security-net",
        "provision.network.dmz-net",
        "provision.network.internal-net",
    )
    assert domain_by_name["webapp"].networks == (
        "provision.network.dmz-net",
        "provision.network.internal-net",
    )
    assert domain_by_name["thehive"].services[0].name == "thehive-api"
    assert domain_by_name["thehive"].services[0].port == 9000
    assert domain_by_name["misp"].services[0].port == 443
    security = {spec.name: spec for spec in networks}["security-net"]
    assert security.cidr == "172.20.0.0/24"
    assert security.gateway == "172.20.0.1"

    snapshot = control_plane.snapshot
    assert len(snapshot.entries) == 34
    assert driver.realized_addresses() == frozenset(snapshot.entries)


def _techvault_manager() -> tuple[RuntimeManager, _RecordingLibvirtDriver, object]:
    driver = _RecordingLibvirtDriver()
    target = create_libvirt_target(driver=driver, name_prefix="techvault-recon")
    manager = RuntimeManager(target)
    scenario = _without_unsupported_runtime_realization(
        (EXAMPLES_DIR / "techvault.sdl.yaml").read_text(encoding="utf-8")
    )
    return manager, driver, scenario


def test_libvirt_reapply_of_unchanged_plan_is_a_full_stack_noop():
    # Issue #604: re-applying an unchanged scenario re-plans to all-UNCHANGED and
    # never drives the host a second time.
    manager, driver, scenario = _techvault_manager()

    first = manager.apply(manager.plan(scenario, parameters=_TECHVAULT_PARAMETERS))
    second = manager.apply(manager.plan(scenario, parameters=_TECHVAULT_PARAMETERS))

    assert first.success and second.success
    assert len(driver.realize_calls) == 1  # the second apply drove nothing
    assert set(manager.snapshot.entries) == {
        "provision.network.aptl-dmz",
        "provision.network.aptl-internal",
        "provision.node.techvault-webapp",
    }


def test_libvirt_update_reconverges_only_the_changed_node_through_runtime_manager():
    # Issue #604: a changed input re-plans the affected node to UPDATE while the
    # unchanged networks stay UNCHANGED; the backend re-converges only the node
    # and the snapshot reflects the new realized state.
    manager, driver, scenario = _techvault_manager()
    changed_parameters = {**_TECHVAULT_PARAMETERS, "app_py_sha256": "f" * 64}

    create = manager.apply(manager.plan(scenario, parameters=_TECHVAULT_PARAMETERS))
    update = manager.apply(manager.plan(scenario, parameters=changed_parameters))

    assert create.success and update.success
    assert len(driver.realize_calls) == 2
    reconverged = driver.realize_calls[1]
    assert [spec.address for spec in reconverged["networks"]] == []
    assert [spec.address for spec in reconverged["domains"]] == ["provision.node.techvault-webapp"]
    node_payload = repr(manager.snapshot.entries["provision.node.techvault-webapp"].payload)
    assert "f" * 64 in node_payload
    assert _TECHVAULT_PARAMETERS["app_py_sha256"] not in node_payload
    assert driver.realized_addresses() == frozenset(manager.snapshot.entries)


def test_libvirt_teardown_removes_all_resources_and_is_idempotent():
    # Issue #604: destroy tears down every realized domain/network, empties the
    # snapshot so it stays consistent with realized state, and a repeated destroy
    # against the now-empty snapshot is a clean idempotent no-op.
    manager, driver, scenario = _techvault_manager()
    manager.apply(manager.plan(scenario, parameters=_TECHVAULT_PARAMETERS))
    realized_addresses = set(manager.snapshot.entries)
    assert realized_addresses  # sanity: something was realized

    teardown = manager.destroy()

    assert teardown.success
    assert not teardown.diagnostics
    assert manager.snapshot.entries == {}
    assert driver.realized_addresses() == frozenset()
    assert len(driver.destroy_calls) == 1
    destroyed = set(driver.destroy_calls[0]["networks"]) | set(driver.destroy_calls[0]["domains"])
    assert destroyed == realized_addresses

    idempotent = manager.destroy()

    assert idempotent.success
    assert not idempotent.diagnostics
    assert manager.snapshot.entries == {}
    assert len(driver.destroy_calls) == 1  # empty snapshot drives no further destroy
