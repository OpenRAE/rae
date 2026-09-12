"""ASR-519 TechVault admission, observation, and recovery falsification tests."""

from __future__ import annotations

from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_backend_libvirt.driver import (
    DomainHandle,
    DriverResult,
    NetworkHandle,
    RealizationObservation,
)
from raes_backend_libvirt.envelopes import load_libvirt_realization_envelope
from raes_backend_libvirt.provisioner import LibvirtProvisioner
from raes_backend_libvirt.target import create_libvirt_target
from raes_contracts.planning import ChangeAction, PlannedResource, ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_contracts.realization_envelope import ObservationStrength, RealizationConcern
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import LocalControlPlaneStore
from raes_runtime.manager import RuntimeManager
from realization_authority_fixtures import complete_test_realization_authority


class _RecordingTechVaultDriver:
    driver_mode = "techvault-appliance"

    def __init__(self) -> None:
        self.realize_calls: list[dict[str, object]] = []
        self.destroy_calls: list[dict[str, object]] = []

    def realize(self, *, networks, domains):
        self.realize_calls.append({"networks": networks, "domains": domains})
        return DriverResult(
            networks=tuple(NetworkHandle(address=spec.address) for spec in networks),
            domains=tuple(DomainHandle(address=spec.address) for spec in domains),
        )

    def destroy(self, *, networks, domains):
        self.destroy_calls.append({"networks": networks, "domains": domains})
        return DriverResult(
            networks=tuple(NetworkHandle(address=address, realized=False) for address in networks),
            domains=tuple(DomainHandle(address=address, realized=False) for address in domains),
        )

    def realized_addresses(self):
        return frozenset()


class _ObservedTechVaultDriver(_RecordingTechVaultDriver):
    def __init__(self, *, observed_memory_mib: int = 128, observed_vcpus: object | None = None) -> None:
        super().__init__()
        self.observed_memory_mib = observed_memory_mib
        self.observed_vcpus = observed_vcpus

    def realize(self, *, networks, domains):
        self.realize_calls.append({"networks": networks, "domains": domains})
        observations: list[RealizationObservation] = []
        for spec in domains:
            observations.extend(
                (
                    _observation(spec.address, "exists", RealizationConcern.TOPOLOGY, True),
                    _observation(spec.address, "architecture", RealizationConcern.ARCHITECTURE, "x86_64"),
                    _observation(
                        spec.address,
                        "image-policy",
                        RealizationConcern.IMAGE,
                        "generated-initramfs-appliance",
                    ),
                    _observation(
                        spec.address,
                        "memory-mib",
                        RealizationConcern.RESOURCE_ALLOCATION,
                        self.observed_memory_mib,
                    ),
                    _observation(
                        spec.address,
                        "vcpus",
                        RealizationConcern.RESOURCE_ALLOCATION,
                        spec.vcpus if self.observed_vcpus is None else self.observed_vcpus,
                    ),
                    _observation(
                        spec.address,
                        "network-attachments",
                        RealizationConcern.NETWORK,
                        tuple(spec.networks),
                    ),
                )
            )
        return DriverResult(
            domains=tuple(DomainHandle(address=spec.address) for spec in domains),
            observations=tuple(observations),
        )


class _DuplicateObservationDriver(_ObservedTechVaultDriver):
    def realize(self, *, networks, domains):
        result = super().realize(networks=networks, domains=domains)
        duplicate = next(item for item in result.observations if item.field_path == "vcpus")
        return DriverResult(
            networks=result.networks,
            domains=result.domains,
            observations=(*result.observations, duplicate),
        )


def _observation(address: str, field_path: str, concern: RealizationConcern, value: object):
    return RealizationObservation(
        address=address,
        field_path=field_path,
        concern=concern,
        source=ObservationStrength.DAEMON_OBSERVED,
        value=value,
    )


def _node_resource(
    *,
    memory_mib: int = 128,
    vcpus: int = 1,
    image_ref: str | None = None,
    services: list[dict[str, object]] | None = None,
    acls: list[dict[str, object]] | None = None,
) -> PlannedResource:
    node: dict[str, object] = {
        "type": "compute",
        "resources": {"ram": memory_mib, "cpu": vcpus},
        "services": services or [],
    }
    if image_ref is not None:
        node["source"] = {"name": image_ref}
    infrastructure: dict[str, object] = {"networks": []}
    if acls is not None:
        infrastructure["acls"] = acls
    return PlannedResource(
        address="provision.node.demo",
        domain=RuntimeDomain.PROVISIONING,
        resource_type="node",
        payload={
            "name": "demo",
            "node_kind": "compute",
            "os_family": "linux",
            "spec": {"node": node, "infrastructure": infrastructure},
        },
    )


def _placement_resource(resource_type: str) -> PlannedResource:
    specs: dict[str, dict[str, object]] = {
        "account-placement": {"username": "operator"},
        "content-placement": {"type": "file", "path": "/etc/demo", "text": "demo"},
        "feature-binding": {"template": {"type": "service", "source": {"name": "demo-agent"}}},
    }
    return PlannedResource(
        address=f"provision.{resource_type}.demo",
        domain=RuntimeDomain.PROVISIONING,
        resource_type=resource_type,
        payload={
            "name": "demo",
            "target_address": "provision.node.demo",
            "spec": specs[resource_type],
        },
    )


def _plan(*resources: PlannedResource, action: ChangeAction = ChangeAction.CREATE) -> ProvisioningPlan:
    return complete_test_realization_authority(
        ProvisioningPlan(
            resources={resource.address: resource for resource in resources},
            operations=[
                ProvisionOp(
                    action=action,
                    address=resource.address,
                    resource_type=resource.resource_type,
                    payload=resource.payload,
                )
                for resource in resources
            ],
            realization_envelope=load_libvirt_realization_envelope("techvault-appliance").identity,
        )
    )


@pytest.mark.parametrize(
    ("resource", "code"),
    (
        (_node_resource(memory_mib=1024), "libvirt-backend.techvault.resource-out-of-envelope"),
        (_node_resource(vcpus=4), "libvirt-backend.techvault.resource-out-of-envelope"),
        (_node_resource(image_ref="requested.qcow2"), "libvirt-backend.techvault.image-unsupported"),
        (
            _node_resource(services=[{"name": "api", "port": 8443, "protocol": "tcp"}]),
            "libvirt-backend.techvault.service-unsupported",
        ),
    ),
)
def test_techvault_rejects_silent_transformations_before_driver_io(resource, code):
    driver = _RecordingTechVaultDriver()
    baseline = RuntimeSnapshot()

    result = LibvirtProvisioner(driver).apply(_plan(resource), baseline)

    assert result.success is False
    assert result.snapshot is baseline
    assert result.changed_addresses == []
    assert code in {diagnostic.code for diagnostic in result.diagnostics}
    assert driver.realize_calls == []


@pytest.mark.parametrize(
    ("resource_type", "expected_codes"),
    (
        ("account-placement", ["libvirt-backend.techvault.guest-placement-unsupported"]),
        (
            "content-placement",
            [
                "libvirt-backend.realization.unsupported-content-type",
                "libvirt-backend.techvault.guest-placement-unsupported",
            ],
        ),
        ("feature-binding", ["libvirt-backend.techvault.guest-placement-unsupported"]),
    ),
)
def test_techvault_rejects_unsupported_guest_placements_before_driver_io(resource_type, expected_codes):
    driver = _RecordingTechVaultDriver()
    node = _node_resource()
    placement = _placement_resource(resource_type)
    baseline = RuntimeSnapshot()

    result = LibvirtProvisioner(driver).apply(_plan(node, placement), baseline)

    assert result.success is False
    assert result.snapshot is baseline
    assert result.changed_addresses == []
    assert [diagnostic.code for diagnostic in result.diagnostics] == expected_codes
    assert {diagnostic.address for diagnostic in result.diagnostics} == {placement.address}
    assert driver.realize_calls == []


def test_techvault_rejects_updates_before_native_mutation():
    driver = _RecordingTechVaultDriver()
    resource = _node_resource()
    plan = _plan(resource, action=ChangeAction.UPDATE)
    baseline = RuntimeSnapshot(realization_envelope=plan.realization_envelope)

    result = LibvirtProvisioner(driver).apply(plan, baseline)

    assert result.success is False
    assert result.snapshot is baseline
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["libvirt-backend.techvault.update-unsupported"]
    assert driver.realize_calls == []


def test_techvault_rejects_delete_combined_with_another_mutation():
    driver = _RecordingTechVaultDriver()
    created = _node_resource()
    deleted_address = "provision.node.prior"
    plan = ProvisioningPlan(
        resources={created.address: created},
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address=created.address,
                resource_type=created.resource_type,
                payload=created.payload,
            ),
            ProvisionOp(
                action=ChangeAction.DELETE,
                address=deleted_address,
                resource_type="node",
                payload={"name": "prior"},
            ),
        ],
        realization_envelope=load_libvirt_realization_envelope("techvault-appliance").identity,
    )
    baseline = RuntimeSnapshot(realization_envelope=plan.realization_envelope)

    result = LibvirtProvisioner(driver).apply(plan, baseline)

    assert result.success is False
    assert result.snapshot is baseline
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "libvirt-backend.techvault.transaction-unsupported"
    ]
    assert driver.realize_calls == []
    assert driver.destroy_calls == []


def test_techvault_rejects_fabricated_handle_without_daemon_observations():
    driver = _RecordingTechVaultDriver()
    baseline = RuntimeSnapshot()

    result = LibvirtProvisioner(driver).apply(_plan(_node_resource()), baseline)

    assert result.success is False
    assert result.snapshot is baseline
    assert result.changed_addresses == []
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["libvirt-backend.techvault.observation-missing"]
    assert len(driver.realize_calls) == 1
    assert driver.destroy_calls == [{"networks": (), "domains": ("provision.node.demo",)}]


def test_techvault_commits_snapshot_only_after_complete_matching_daemon_observations():
    driver = _ObservedTechVaultDriver()

    result = LibvirtProvisioner(driver).apply(_plan(_node_resource()), RuntimeSnapshot())

    assert result.success is True
    assert result.changed_addresses == ["provision.node.demo"]
    assert result.snapshot.entries["provision.node.demo"].status == "applied"


def test_techvault_detects_resource_clamping_in_daemon_readback():
    driver = _ObservedTechVaultDriver(observed_memory_mib=64)
    baseline = RuntimeSnapshot()

    result = LibvirtProvisioner(driver).apply(_plan(_node_resource()), baseline)

    assert result.success is False
    assert result.snapshot is baseline
    assert result.changed_addresses == []
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["libvirt-backend.techvault.observation-mismatch"]
    assert driver.destroy_calls == [{"networks": (), "domains": ("provision.node.demo",)}]


@pytest.mark.parametrize(
    "driver",
    (
        _ObservedTechVaultDriver(observed_vcpus=True),
        _DuplicateObservationDriver(),
    ),
)
def test_techvault_rejects_type_coercion_and_duplicate_daemon_observations(driver):
    baseline = RuntimeSnapshot()

    result = LibvirtProvisioner(driver).apply(_plan(_node_resource()), baseline)

    assert result.success is False
    assert result.snapshot is baseline
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["libvirt-backend.techvault.observation-mismatch"]
    assert driver.destroy_calls == [{"networks": (), "domains": ("provision.node.demo",)}]


def test_failed_techvault_admission_preserves_persisted_runtime_snapshot(tmp_path):
    driver = _RecordingTechVaultDriver()
    envelope = load_libvirt_realization_envelope("techvault-appliance").identity
    baseline = RuntimeSnapshot(
        entries={
            "provision.node.prior": SnapshotEntry(
                address="provision.node.prior",
                domain=RuntimeDomain.PROVISIONING,
                resource_type="node",
                payload={"name": "prior"},
            )
        },
        realization_envelope=envelope,
    )
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    store.save_snapshot(baseline, expected_revision=store.load_snapshot_state().revision)
    target = create_libvirt_target(driver=driver)
    control_plane = RuntimeControlPlane(target, store=store)
    invalid = _node_resource(services=[{"name": "api", "port": 8443, "protocol": "tcp"}])
    invalid_plan = _plan(invalid)
    authorization_plan = RuntimeManager(target, initial_snapshot=baseline).plan(
        parse_sdl("name: techvault-admission-authorization")
    )
    control_plane.register_planner_produced_plan(replace(authorization_plan, provisioning=invalid_plan))

    receipt = control_plane.submit_provisioning(invalid_plan)
    status = control_plane.get_operation(receipt.operation_id)
    control_plane.close()
    restarted = RuntimeControlPlane(create_libvirt_target(driver=driver), store=store)

    assert receipt.accepted is True
    assert status is not None and status.state.value == "failed"
    assert receipt.diagnostics == []
    assert [diagnostic.code for diagnostic in status.diagnostics] == [
        "libvirt-backend.techvault.service-unsupported",
        "runtime.control-plane.operation-failed",
    ]
    assert restarted.snapshot == baseline
    assert driver.realize_calls == []
    restarted.close()
