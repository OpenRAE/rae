"""Issue #601: libvirt provisioning backend protocol behavior."""

from __future__ import annotations

from raes_backend_libvirt import LibvirtProvisioner
from raes_backend_libvirt.driver import DomainHandle, DriverResult, NetworkHandle
from raes_backend_libvirt.envelopes import load_libvirt_realization_envelope
from raes_contracts.bounded_domains import ExactDomain
from raes_contracts.contracts import RealizationEnvelopeIdentityModel
from raes_contracts.planning import (
    ChangeAction,
    EvaluationPlan,
    PlannedRealizationConstraint,
    PlannedResource,
    ProvisioningPlan,
    ProvisionOp,
    RuntimeDomain,
)
from raes_contracts.realization_envelope import ObservationStrength, RealizationConcern
from raes_contracts.realization_observation import RealizationObservation
from raes_contracts.runtime_state import RealizationObservationDisclosure, RuntimeSnapshot, SnapshotEntry
from raes_contracts.vocabulary import RealizationVerificationScope
from realization_authority_fixtures import (
    complete_test_realization_authority,
    with_compute_substrate_collection_demand,
)


class _RecordingDriver:
    def __init__(self) -> None:
        self.realize_calls: list[dict[str, object]] = []
        self.destroy_calls: list[dict[str, object]] = []
        self.observe_calls: list[dict[str, object]] = []
        self._realized: set[str] = set()

    def realize(self, *, networks, domains):
        self.realize_calls.append({"networks": networks, "domains": domains})
        self._realized.update(spec.address for spec in networks)
        self._realized.update(spec.address for spec in domains)
        return DriverResult(
            networks=tuple(NetworkHandle(address=spec.address) for spec in networks),
            domains=tuple(DomainHandle(address=spec.address) for spec in domains),
        )

    def destroy(self, *, networks, domains):
        self.destroy_calls.append({"networks": networks, "domains": domains})
        self._realized.difference_update(networks)
        self._realized.difference_update(domains)
        return DriverResult(
            networks=tuple(NetworkHandle(address=address, realized=False) for address in networks),
            domains=tuple(DomainHandle(address=address, realized=False) for address in domains),
        )

    def observe(self, *, domains):
        self.observe_calls.append({"domains": domains})
        envelope = load_libvirt_realization_envelope("generic")
        return DriverResult(
            domains=tuple(DomainHandle(address=spec.address) for spec in domains),
            observations=tuple(
                RealizationObservation(
                    address=spec.address,
                    field_path="compute-substrate",
                    concern=RealizationConcern.COMPUTE_SUBSTRATE,
                    source=ObservationStrength.DAEMON_OBSERVED,
                    value="virtual-machine",
                    envelope_digest=envelope.digest,
                    configuration_digest=envelope.configuration.configuration_digest,
                    observer_version="recording-libvirt-readback/v1",
                    sequence=index,
                    binding_verified=True,
                )
                for index, spec in enumerate(domains)
            ),
        )

    def realized_addresses(self):
        return frozenset(self._realized)


def _node_resource(address: str = "provision.node.web") -> PlannedResource:
    return PlannedResource(
        address=address,
        domain=RuntimeDomain.PROVISIONING,
        resource_type="node",
        payload={
            "name": "web",
            "node_name": "web",
            "node_kind": "compute",
            "os_family": "linux",
            "spec": {
                "node": {
                    "type": "compute",
                    "source": {"name": "/var/lib/libvirt/images/base.qcow2"},
                    "resources": {"ram": 1073741824, "cpu": 2},
                },
                "infrastructure": {"networks": ["lan"]},
            },
        },
    )


def _network_resource(address: str = "provision.network.lan") -> PlannedResource:
    return PlannedResource(
        address=address,
        domain=RuntimeDomain.PROVISIONING,
        resource_type="network",
        payload={"name": "lan", "spec": {"infrastructure": {"properties": {"internal": True}}}},
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
                    ordering_dependencies=resource.ordering_dependencies,
                    refresh_dependencies=resource.refresh_dependencies,
                )
                for resource in resources
            ],
            realization_envelope=load_libvirt_realization_envelope("generic").identity,
        )
    )


def test_validate_rejects_non_provisioning_plan_with_invalid_plan_diagnostic():
    diagnostics = LibvirtProvisioner(_RecordingDriver()).validate(EvaluationPlan())  # type: ignore[arg-type]

    assert [diag.code for diag in diagnostics] == ["libvirt-backend.invalid-plan"]
    assert diagnostics[0].address == "runtime.libvirt.provisioning"


def test_apply_rejects_non_provisioning_plan_without_mutating_snapshot():
    snapshot = RuntimeSnapshot()

    result = LibvirtProvisioner(_RecordingDriver()).apply(EvaluationPlan(), snapshot)  # type: ignore[arg-type]

    assert result.success is False
    assert result.snapshot is snapshot
    assert [diag.code for diag in result.diagnostics] == ["libvirt-backend.invalid-plan"]


def test_apply_reconciles_snapshot_and_drives_libvirt_driver_for_create():
    driver = _RecordingDriver()
    plan = _plan(_network_resource(), _node_resource())

    result = LibvirtProvisioner(driver).apply(plan, RuntimeSnapshot())

    assert result.success is True
    assert sorted(result.changed_addresses) == ["provision.network.lan", "provision.node.web"]
    assert result.snapshot.entries["provision.node.web"].status == "applied"
    assert result.snapshot.entries["provision.node.web"].payload["os_family"] == "linux"
    assert driver.realize_calls
    assert result.snapshot.realization_envelope == plan.realization_envelope
    domains = driver.realize_calls[0]["domains"]
    networks = driver.realize_calls[0]["networks"]
    assert [spec.address for spec in domains] == ["provision.node.web"]
    assert [spec.address for spec in networks] == ["provision.network.lan"]


def test_delete_of_last_compute_removes_stale_substrate_observation() -> None:
    envelope = load_libvirt_realization_envelope("generic")
    resource = _node_resource()
    previous = RealizationObservationDisclosure(
        address=resource.address,
        field_path="compute-substrate",
        domain="runtime-realization",
        requirement_kind="compute-substrate",
        verification_scope=RealizationVerificationScope.PRESENCE,
        observation_strength=ObservationStrength.DAEMON_OBSERVED,
        observed_value="virtual-machine",
        operation_id="previous-operation",
        envelope_digest=envelope.digest,
        configuration_digest=envelope.configuration.configuration_digest,
        observer_version="libvirt-test-readback/v1",
        sequence=0,
        binding_verified=True,
    )
    snapshot = RuntimeSnapshot(
        entries={
            resource.address: SnapshotEntry(
                address=resource.address,
                domain=resource.domain,
                resource_type=resource.resource_type,
                payload=resource.payload,
            )
        },
        realization_observations=(previous,),
        realization_envelope=envelope.identity,
    )

    result = LibvirtProvisioner(_RecordingDriver()).apply(
        _plan(resource, action=ChangeAction.DELETE),
        snapshot,
    )

    assert result.success is True
    assert result.snapshot.realization_observations == ()


def test_apply_rejects_missing_envelope_identity_before_driver_io():
    driver = _RecordingDriver()
    plan = ProvisioningPlan(operations=_plan(_node_resource()).operations)
    baseline = RuntimeSnapshot()

    result = LibvirtProvisioner(driver).apply(plan, baseline)

    assert result.success is False
    assert result.snapshot is baseline
    assert [diag.code for diag in result.diagnostics] == ["libvirt-backend.realization-envelope.missing"]
    assert not driver.realize_calls


def test_apply_rejects_mismatched_envelope_identity_before_driver_io():
    driver = _RecordingDriver()
    plan = _plan(_node_resource())
    wrong = RealizationEnvelopeIdentityModel(
        **{**plan.realization_envelope.model_dump(), "digest": "sha256:" + "f" * 64}  # type: ignore[union-attr]
    )
    plan = ProvisioningPlan(
        resources=plan.resources,
        operations=plan.operations,
        realization_envelope=wrong,
    )
    baseline = RuntimeSnapshot()

    result = LibvirtProvisioner(driver).apply(plan, baseline)

    assert result.success is False
    assert result.snapshot is baseline
    assert [diag.code for diag in result.diagnostics] == ["libvirt-backend.realization-envelope.mismatch"]
    assert not driver.realize_calls


def test_apply_rejects_snapshot_bound_to_another_envelope_before_driver_io():
    driver = _RecordingDriver()
    plan = _plan(_node_resource())
    wrong = RealizationEnvelopeIdentityModel(
        **{**plan.realization_envelope.model_dump(), "configuration_digest": "sha256:" + "e" * 64}  # type: ignore[union-attr]
    )
    baseline = RuntimeSnapshot(
        entries={
            "provision.node.existing": SnapshotEntry("provision.node.existing", RuntimeDomain.PROVISIONING, "node", {})
        },
        realization_envelope=wrong,
    )

    result = LibvirtProvisioner(driver).apply(plan, baseline)

    assert result.success is False
    assert result.snapshot is baseline
    assert [diag.code for diag in result.diagnostics] == ["libvirt-backend.realization-envelope.baseline-mismatch"]
    assert not driver.realize_calls


def _account_resource() -> PlannedResource:
    return PlannedResource(
        address="provision.account.admin",
        domain=RuntimeDomain.PROVISIONING,
        resource_type="account-placement",
        payload={
            "name": "admin",
            "account_name": "admin",
            "target_address": "provision.node.web",
            "spec": {"username": "administrator", "groups": ["sudo"], "shell": "/bin/bash"},
        },
    )


def _content_resource() -> PlannedResource:
    return PlannedResource(
        address="provision.content.flag",
        domain=RuntimeDomain.PROVISIONING,
        resource_type="content-placement",
        payload={
            "name": "flag",
            "target_address": "provision.node.web",
            "spec": {"type": "file", "path": "/srv/flag.txt", "text": "ctf{x}\n"},
        },
    )


def _feature_resource() -> PlannedResource:
    return PlannedResource(
        address="provision.feature.wazuh",
        domain=RuntimeDomain.PROVISIONING,
        resource_type="feature-binding",
        payload={
            "name": "wazuh-agent",
            "node_address": "provision.node.web",
            "spec": {"template": {"type": "service", "source": {"name": "wazuh-agent"}}},
        },
    )


def test_apply_realizes_placements_into_domain_cloud_init_and_snapshot():
    driver = _RecordingDriver()
    plan = _plan(_node_resource(), _account_resource(), _content_resource(), _feature_resource())

    result = LibvirtProvisioner(driver).apply(plan, RuntimeSnapshot())

    assert result.success is True
    domain = driver.realize_calls[0]["domains"][0]
    cloud_init = domain.cloud_init
    assert cloud_init.users[0].name == "administrator"
    assert any(file.path == "/srv/flag.txt" for file in cloud_init.write_files)
    assert "wazuh-agent" in cloud_init.packages
    # Every placement is reflected back into the snapshot as a portable entry.
    assert result.snapshot.entries["provision.account.admin"].status == "applied"
    assert result.snapshot.entries["provision.content.flag"].resource_type == "content-placement"
    assert result.snapshot.entries["provision.feature.wazuh"].status == "applied"


def test_apply_unchanged_placement_is_noop_with_unchanged_status():
    driver = _RecordingDriver()
    # The target node is part of the plan's desired state (here also UNCHANGED), so
    # the placement is bound; nothing is CREATE/UPDATE, so the host is never driven.
    plan = _plan(_node_resource(), _account_resource(), action=ChangeAction.UNCHANGED)

    result = LibvirtProvisioner(driver).apply(plan, RuntimeSnapshot())

    assert result.success is True
    assert driver.realize_calls == []  # UNCHANGED never drives the host
    assert result.changed_addresses == []
    assert result.snapshot.entries["provision.account.admin"].status == "unchanged"


def test_unchanged_compute_bootstraps_operational_substrate_evidence_with_readback() -> None:
    driver = _RecordingDriver()
    resource = _node_resource()
    created = LibvirtProvisioner(driver).apply(_plan(resource), RuntimeSnapshot())
    assert created.success
    legacy_snapshot = created.snapshot.with_entries(
        created.snapshot.entries,
        realization_observations=(),
    )
    envelope = load_libvirt_realization_envelope("generic")
    unchanged = _plan(resource, action=ChangeAction.UNCHANGED)
    unchanged = ProvisioningPlan(
        resources=unchanged.resources,
        operations=unchanged.operations,
        realization_envelope=envelope.identity,
        realization_constraints=(
            PlannedRealizationConstraint(
                address=resource.address,
                field_path="compute-substrate",
                concern="compute-substrate",
                posture="exact",
                value_domain=ExactDomain(value="virtual-machine"),
                governing_scope="#/nodes/web",
                provenance="author-declared",
            ),
        ),
        operation_id="libvirt-upgrade-noop",
    )

    without_demand = LibvirtProvisioner(driver).apply(unchanged, legacy_snapshot)

    assert without_demand.success
    assert driver.observe_calls == []
    assert without_demand.operational_realization_observations == ()

    unchanged = with_compute_substrate_collection_demand(
        unchanged,
        semantic_scope="/nodes/web",
        address=resource.address,
    )

    result = LibvirtProvisioner(driver).apply(unchanged, legacy_snapshot)

    assert result.success
    assert len(driver.realize_calls) == 1
    assert [spec.address for spec in driver.observe_calls[-1]["domains"]] == [resource.address]
    assert result.snapshot.realization_observations == ()
    [disclosure] = result.operational_realization_observations
    assert disclosure.observed_value == "virtual-machine"
    assert disclosure.operation_id == "libvirt-upgrade-noop"


def test_apply_realizes_target_domain_when_only_a_placement_changes():
    driver = _RecordingDriver()
    node = _node_resource()
    account = _account_resource()
    # Node is UNCHANGED, but a new account placement targets it: the domain's seed
    # now carries different cloud-init, so the domain must still be realized.
    plan = complete_test_realization_authority(
        ProvisioningPlan(
            resources={node.address: node, account.address: account},
            operations=[
                ProvisionOp(
                    action=ChangeAction.UNCHANGED,
                    address=node.address,
                    resource_type=node.resource_type,
                    payload=node.payload,
                ),
                ProvisionOp(
                    action=ChangeAction.CREATE,
                    address=account.address,
                    resource_type=account.resource_type,
                    payload=account.payload,
                ),
            ],
            realization_envelope=load_libvirt_realization_envelope("generic").identity,
        )
    )

    result = LibvirtProvisioner(driver).apply(plan, RuntimeSnapshot())

    assert result.success is True
    assert driver.realize_calls, "the placement change must drive realization of its target domain"
    realized_domains = [spec.address for spec in driver.realize_calls[0]["domains"]]
    assert realized_domains == ["provision.node.web"]
    assert driver.realize_calls[0]["domains"][0].cloud_init.users[0].name == "administrator"


def test_apply_delete_removes_snapshot_entry_and_drives_destroy():
    driver = _RecordingDriver()
    snapshot = RuntimeSnapshot(
        entries={
            "provision.node.web": SnapshotEntry(
                address="provision.node.web",
                domain=RuntimeDomain.PROVISIONING,
                resource_type="node",
                payload={},
            )
        },
        realization_envelope=load_libvirt_realization_envelope("generic").identity,
    )
    plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.DELETE,
                address="provision.node.web",
                resource_type="node",
                payload={},
            )
        ],
        realization_envelope=load_libvirt_realization_envelope("generic").identity,
    )

    result = LibvirtProvisioner(driver).apply(plan, snapshot)

    assert result.success is True
    assert "provision.node.web" not in result.snapshot.entries
    assert driver.destroy_calls == [{"networks": (), "domains": ("provision.node.web",)}]


def test_apply_delete_of_already_absent_entry_is_idempotent_success():
    # Issue #604: re-running a DELETE for an address that is no longer in the
    # snapshot (already torn down) is a clean, idempotent success — the driver
    # confirms "not realized" and no error is surfaced.
    driver = _RecordingDriver()
    plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.DELETE,
                address="provision.node.web",
                resource_type="node",
                payload={},
            )
        ],
        realization_envelope=load_libvirt_realization_envelope("generic").identity,
    )

    result = LibvirtProvisioner(driver).apply(plan, RuntimeSnapshot())

    assert result.success is True
    assert not result.diagnostics
    assert "provision.node.web" not in result.snapshot.entries
    assert driver.destroy_calls == [{"networks": (), "domains": ("provision.node.web",)}]


def _out_of_envelope_node(address: str = "provision.node.gw") -> PlannedResource:
    return PlannedResource(
        address=address,
        domain=RuntimeDomain.PROVISIONING,
        resource_type="node",
        payload={
            "name": "gw",
            "node_name": "gw",
            "node_kind": "router",
            "os_family": "linux",
            "spec": {"node": {"type": "router"}, "infrastructure": {}},
        },
    )


def test_apply_fails_closed_on_out_of_envelope_node_type():
    driver = _RecordingDriver()
    snapshot = RuntimeSnapshot()

    result = LibvirtProvisioner(driver).apply(_plan(_out_of_envelope_node()), snapshot)

    assert result.success is False
    assert result.snapshot is snapshot
    assert driver.realize_calls == []  # no partial/silent realization on error
    assert [diag.code for diag in result.diagnostics] == ["libvirt-backend.realization.unsupported-node-type"]


def test_validate_reports_out_of_envelope_node_type():
    diagnostics = LibvirtProvisioner(_RecordingDriver()).validate(_plan(_out_of_envelope_node()))

    assert [diag.code for diag in diagnostics] == ["libvirt-backend.realization.unsupported-node-type"]


def test_apply_validates_operation_payloads_not_only_resources():
    # An out-of-envelope term carried by a CREATE operation whose address is absent
    # from plan.resources must still fail closed before any snapshot is persisted:
    # operations, not just resources, materialize snapshot entries and driver work.
    driver = _RecordingDriver()
    snapshot = RuntimeSnapshot()
    plan = ProvisioningPlan(
        resources={},
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.node.gw",
                resource_type="node",
                payload={"name": "gw", "node_kind": "router", "os_family": "linux", "spec": {}},
            )
        ],
        realization_envelope=load_libvirt_realization_envelope("generic").identity,
    )

    result = LibvirtProvisioner(driver).apply(plan, snapshot)

    assert result.success is False
    assert driver.realize_calls == []
    assert "provision.node.gw" not in result.snapshot.entries
    assert [diag.code for diag in result.diagnostics] == ["libvirt-backend.realization.unsupported-node-type"]


def test_apply_fails_closed_when_driver_omits_realization_confirmation():
    class _SilentRealizeDriver(_RecordingDriver):
        def realize(self, *, networks, domains):
            self.realize_calls.append({"networks": networks, "domains": domains})
            return DriverResult()

    snapshot = RuntimeSnapshot()
    plan = _plan(_node_resource())

    result = LibvirtProvisioner(_SilentRealizeDriver()).apply(plan, snapshot)

    assert result.success is False
    assert result.snapshot is snapshot
    assert [diag.code for diag in result.diagnostics] == ["libvirt-backend.driver.unconfirmed-realization"]
    assert result.diagnostics[0].address == "provision.node.web"


def test_apply_fails_closed_when_driver_omits_destroy_confirmation():
    class _SilentDestroyDriver(_RecordingDriver):
        def destroy(self, *, networks, domains):
            self.destroy_calls.append({"networks": networks, "domains": domains})
            return DriverResult()

    snapshot = RuntimeSnapshot(
        entries={
            "provision.node.web": SnapshotEntry(
                address="provision.node.web",
                domain=RuntimeDomain.PROVISIONING,
                resource_type="node",
                payload={},
            )
        },
        realization_envelope=load_libvirt_realization_envelope("generic").identity,
    )
    plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.DELETE,
                address="provision.node.web",
                resource_type="node",
                payload={},
            )
        ],
        realization_envelope=load_libvirt_realization_envelope("generic").identity,
    )

    result = LibvirtProvisioner(_SilentDestroyDriver()).apply(plan, snapshot)

    assert result.success is False
    assert result.snapshot is snapshot
    assert "provision.node.web" in result.snapshot.entries
    assert [diag.code for diag in result.diagnostics] == ["libvirt-backend.driver.unconfirmed-destroy"]
