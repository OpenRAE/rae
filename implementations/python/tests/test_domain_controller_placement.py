"""Issue #845 domain-controller placement invariants.

The focused contract is: (i) the resource type belongs to provisioning;
(ii) addresses are unique per controller-node/domain pair; (iii) members and
domain accounts order after the matching controller placements; (iv) payloads
are typed and secret-free; (v) the shared topology gate admits the carrier; and
(vi) every placement has an exact SEM-218 realization requirement.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
import yaml
from jsonschema import Draft202012Validator
from raes import parse_sdl
from raes_backend_protocols.backend_manifest import BackendManifest
from raes_backend_protocols.domain_topology import DomainTopologyBinding, domain_topology_plan_diagnostics
from raes_backend_stubs.stubs import create_stub_manifest
from raes_conformance._realization_validation import operation_inventory_diagnostics
from raes_conformance.realization import RealizationProbeEvidence
from raes_contracts.contracts import ProvisioningPlanModel
from raes_contracts.contracts.plan_projection import planned_provisioning_resources, provisioning_plan_model
from raes_contracts.planning import (
    PLAN_RESOURCE_TYPES_BY_DOMAIN,
    ChangeAction,
    ProvisioningPlan,
    ProvisionOp,
    RuntimeDomain,
)
from raes_contracts.realization_envelope import ObservationStrength, RealizationConcern
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import DomainControllerPlacement, resource_payload
from raes_processor.planner import plan
from raes_processor.semantics.realization import realization_disclosure
from raes_schemas import schema_bundle

_RESOURCE_TYPE = "domain-controller-placement"


def _scenario_payload(domain_count: int = 1, controllers_per_domain: int = 1) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "controller-placement",
        "nodes": {},
        "accounts": {},
        "identity_domains": {},
        "relationships": {},
    }
    nodes = payload["nodes"]
    accounts = payload["accounts"]
    domains = payload["identity_domains"]
    relationships = payload["relationships"]
    assert isinstance(nodes, dict)
    assert isinstance(accounts, dict)
    assert isinstance(domains, dict)
    assert isinstance(relationships, dict)
    for domain_index in range(domain_count):
        domain_name = f"domain-{domain_index}"
        controller_names = [
            f"dc-{domain_index}-{controller_index}" for controller_index in range(controllers_per_domain)
        ]
        member_name = f"member-{domain_index}"
        for controller_name in controller_names:
            nodes[controller_name] = {"type": "compute", "os": "windows"}
            relationships[f"{controller_name}-role"] = {
                "type": "domain_controller_for",
                "source": controller_name,
                "target": domain_name,
                "domain_controller": {},
            }
        nodes[member_name] = {"type": "compute", "os": "windows"}
        relationships[f"{member_name}-join"] = {
            "type": "joins_domain",
            "source": member_name,
            "target": domain_name,
            "domain_join": {"controller_refs": controller_names},
        }
        authority_name = f"authority-{domain_index}"
        accounts[authority_name] = {
            "username": f"administrator-{domain_index}",
            "node": controller_names[0],
        }
        accounts[f"subject-{domain_index}"] = {
            "username": f"subject-{domain_index}",
            "node": member_name,
            "domain_ref": domain_name,
        }
        domains[domain_name] = {
            "profile": "active_directory",
            "dns_name": f"domain{domain_index}.example",
            "netbios_name": f"D{domain_index}",
            "authority_account_ref": authority_name,
        }
    return payload


def _compile(domain_count: int = 1, controllers_per_domain: int = 1):
    scenario = parse_sdl(
        yaml.safe_dump(
            _scenario_payload(domain_count, controllers_per_domain),
            sort_keys=False,
        )
    )
    return compile_runtime_model(scenario)


def _manifest() -> BackendManifest:
    base = create_stub_manifest()
    return replace(
        base,
        capabilities=replace(
            base.capabilities,
            provisioner=replace(
                base.provisioner,
                supported_domain_profiles=frozenset({"active_directory"}),
            ),
        ),
    )


def _snapshot_entry(operation: ProvisionOp) -> SnapshotEntry:
    return SnapshotEntry(
        address=operation.address,
        domain=RuntimeDomain.PROVISIONING,
        resource_type=operation.resource_type,
        payload=deepcopy(operation.payload),
        ordering_dependencies=operation.ordering_dependencies,
        refresh_dependencies=operation.refresh_dependencies,
    )


def test_compiler_emits_typed_secret_free_controller_placement() -> None:
    model = _compile()

    assert set(model.domain_controller_placements) == {"provision.domain-controller.domain-0.dc-0-0"}
    placement = next(iter(model.domain_controller_placements.values()))
    controller = model.node_deployments["provision.node.dc-0-0"]
    assert isinstance(placement, DomainControllerPlacement)
    assert isinstance(placement.domain_topology, DomainTopologyBinding)
    assert placement.target_address == controller.address
    assert placement.domain_topology == controller.domain_topology
    assert placement.spec == {}
    assert placement.ordering_dependencies == (controller.address,)
    assert placement.refresh_dependencies == (controller.address,)

    payload = resource_payload(placement)
    assert payload["domain_topology"] == {
        "domain_id": "domain-0",
        "profile": "active_directory",
        "dns_name": "domain0.example",
        "netbios_name": "D0",
        "authority_account_address": "provision.account.authority-0",
        "role": "controller",
        "controller_addresses": ("provision.node.dc-0-0",),
    }
    assert not (set(payload) & {"argv", "command", "password", "secret", "keytab", "host_path"})


def test_controller_placement_rejects_untyped_extension_payload() -> None:
    binding = next(iter(_compile().domain_controller_placements.values())).domain_topology

    with pytest.raises(ValueError, match="typed non-secret fields"):
        DomainControllerPlacement(
            address="provision.domain-controller.domain-0.dc-0-0",
            name="dc-0-0.domain-0",
            target_address="provision.node.dc-0-0",
            domain_topology=binding,
            spec={"argv": ["directory-tool"]},
        )


@pytest.mark.parametrize(
    ("domain_count", "controllers_per_domain"),
    [(1, 1), (1, 3), (2, 2)],
)
def test_multi_domain_controller_addresses_and_dependencies_are_total(
    domain_count: int,
    controllers_per_domain: int,
) -> None:
    model = _compile(domain_count, controllers_per_domain)

    assert len(model.domain_controller_placements) == domain_count * controllers_per_domain
    assert len(set(model.domain_controller_placements)) == len(model.domain_controller_placements)
    for domain_index in range(domain_count):
        domain_name = f"domain-{domain_index}"
        placement_addresses = tuple(
            f"provision.domain-controller.{domain_name}.dc-{domain_index}-{controller_index}"
            for controller_index in range(controllers_per_domain)
        )
        member = model.node_deployments[f"provision.node.member-{domain_index}"]
        authority = model.account_placements[f"provision.account.authority-{domain_index}"]
        subject = model.account_placements[f"provision.account.subject-{domain_index}"]
        assert member.ordering_dependencies == placement_addresses
        assert member.refresh_dependencies == placement_addresses
        assert authority.ordering_dependencies == (
            f"provision.node.dc-{domain_index}-0",
            *placement_addresses,
        )
        assert authority.refresh_dependencies == authority.ordering_dependencies
        assert subject.ordering_dependencies == (
            f"provision.node.member-{domain_index}",
            *placement_addresses,
        )
        assert subject.refresh_dependencies == subject.ordering_dependencies


def test_controller_placement_survives_planning_and_published_contract_projection() -> None:
    execution = plan(_compile(), _manifest())
    operation = next(
        operation for operation in execution.provisioning.operations if operation.resource_type == _RESOURCE_TYPE
    )

    assert _RESOURCE_TYPE in PLAN_RESOURCE_TYPES_BY_DOMAIN[RuntimeDomain.PROVISIONING]
    assert execution.provisioning.resources[operation.address].payload == operation.payload
    projected = provisioning_plan_model(execution.provisioning)
    dumped = projected.model_dump(mode="json")
    ProvisioningPlanModel.model_validate(dumped)
    Draft202012Validator(schema_bundle()["provisioning-plan-v1"]).validate(dumped)


def test_plan_identity_rejects_controller_placement_when_vocabulary_omits_it(monkeypatch) -> None:
    admitted = PLAN_RESOURCE_TYPES_BY_DOMAIN[RuntimeDomain.PROVISIONING]
    monkeypatch.setitem(
        PLAN_RESOURCE_TYPES_BY_DOMAIN,
        RuntimeDomain.PROVISIONING,
        admitted - {_RESOURCE_TYPE},
    )

    operation = ProvisionOp(
        action=ChangeAction.CREATE,
        address="provision.domain-controller.domain-0.dc-0-0",
        resource_type=_RESOURCE_TYPE,
        payload={},
    )

    with pytest.raises(ValueError, match="resource_type must belong"):
        ProvisioningPlan(operations=[operation])


def test_topology_admission_rejects_unknown_binding_field_and_missing_account_edges() -> None:
    provisioning = plan(_compile(), _manifest()).provisioning
    malformed_operations = []
    missing_edge_operations = []
    for operation in provisioning.operations:
        payload = deepcopy(operation.payload)
        if operation.resource_type == _RESOURCE_TYPE:
            payload["domain_topology"]["argv"] = ["directory-tool"]
        malformed_operations.append(replace(operation, payload=payload))
        if operation.address == "provision.account.subject-0":
            missing_edge_operations.append(
                replace(
                    operation,
                    ordering_dependencies=("provision.node.member-0",),
                    refresh_dependencies=("provision.node.member-0",),
                )
            )
        else:
            missing_edge_operations.append(operation)

    malformed_codes = {
        diagnostic.code
        for diagnostic in domain_topology_plan_diagnostics(ProvisioningPlan(operations=malformed_operations))
    }
    missing_edge_codes = {
        diagnostic.code
        for diagnostic in domain_topology_plan_diagnostics(ProvisioningPlan(operations=missing_edge_operations))
    }
    assert "provisioning.domain-topology.binding-invalid" in malformed_codes
    assert "provisioning.domain-topology.controller-placement-ordering-missing" in missing_edge_codes
    assert "provisioning.domain-topology.controller-placement-refresh-missing" in missing_edge_codes


@pytest.mark.parametrize(
    ("malformation", "expected_code"),
    [
        ("scalar-type", "provisioning.domain-topology.binding-invalid"),
        ("controller-address-type", "provisioning.domain-topology.binding-invalid"),
        ("missing-binding", "provisioning.domain-topology.binding-missing"),
    ],
)
def test_topology_admission_rejects_malformed_or_missing_controller_placement_binding(
    malformation: str,
    expected_code: str,
) -> None:
    operations = list(plan(_compile(), _manifest()).provisioning.operations)
    placement = next(operation for operation in operations if operation.resource_type == _RESOURCE_TYPE)
    payload = deepcopy(placement.payload)
    if malformation == "scalar-type":
        payload["domain_topology"]["role"] = 1
    elif malformation == "controller-address-type":
        payload["domain_topology"]["controller_addresses"] = [placement.payload["target_address"], 1]
    else:
        del payload["domain_topology"]
    malformed = replace(placement, payload=payload)
    diagnostics = domain_topology_plan_diagnostics(
        ProvisioningPlan(
            operations=[malformed if operation.address == placement.address else operation for operation in operations]
        )
    )

    assert any(
        diagnostic.code == expected_code and diagnostic.address == placement.address for diagnostic in diagnostics
    )


def test_topology_admission_rejects_duplicate_or_missing_controller_placement() -> None:
    provisioning = plan(_compile(), _manifest()).provisioning
    operations = list(provisioning.operations)
    placement = next(operation for operation in operations if operation.resource_type == _RESOURCE_TYPE)
    duplicate = replace(
        placement,
        address="provision.domain-controller.domain-0.dc-0-0-copy",
    )

    duplicate_diagnostics = domain_topology_plan_diagnostics(ProvisioningPlan(operations=[*operations, duplicate]))
    missing_diagnostics = domain_topology_plan_diagnostics(
        ProvisioningPlan(
            operations=[operation for operation in operations if operation.resource_type != _RESOURCE_TYPE]
        )
    )

    assert any(
        diagnostic.code == "provisioning.domain-topology.controller-placement-cardinality-invalid"
        for diagnostic in duplicate_diagnostics
    )
    assert any(
        diagnostic.code == "provisioning.domain-topology.controller-placement-cardinality-invalid"
        for diagnostic in missing_diagnostics
    )


def test_topology_admission_rejects_invalid_controller_placement_edges_and_binding() -> None:
    operations = list(plan(_compile(), _manifest()).provisioning.operations)
    placement = next(operation for operation in operations if operation.resource_type == _RESOURCE_TYPE)
    placement_address = placement.address
    target_address = placement.payload["target_address"]

    missing_edges = replace(
        placement,
        ordering_dependencies=tuple(
            dependency for dependency in placement.ordering_dependencies if dependency != target_address
        ),
        refresh_dependencies=tuple(
            dependency for dependency in placement.refresh_dependencies if dependency != target_address
        ),
    )
    missing_edge_plan = ProvisioningPlan(
        operations=[missing_edges if operation.address == placement_address else operation for operation in operations]
    )
    missing_edge_diagnostics = domain_topology_plan_diagnostics(missing_edge_plan)

    assert any(
        diagnostic.code == "provisioning.domain-topology.controller-placement-ordering-missing"
        and diagnostic.address == placement_address
        for diagnostic in missing_edge_diagnostics
    )
    assert any(
        diagnostic.code == "provisioning.domain-topology.controller-placement-refresh-missing"
        and diagnostic.address == placement_address
        for diagnostic in missing_edge_diagnostics
    )

    mismatched_payload = deepcopy(placement.payload)
    mismatched_payload["domain_topology"]["role"] = "member"
    mismatched_placement = replace(placement, payload=mismatched_payload)
    mismatched_plan = ProvisioningPlan(
        operations=[
            mismatched_placement if operation.address == placement_address else operation for operation in operations
        ]
    )
    mismatch_diagnostics = domain_topology_plan_diagnostics(mismatched_plan)

    assert any(
        diagnostic.code == "provisioning.domain-topology.controller-placement-invalid"
        and diagnostic.address == placement_address
        for diagnostic in mismatch_diagnostics
    )


def test_controller_placement_is_exact_and_readback_rejects_approximation() -> None:
    model = _compile()
    provisioning = plan(model, _manifest()).provisioning
    placement_address = "provision.domain-controller.domain-0.dc-0-0"
    requirement = next(
        requirement
        for requirement in model.realization_requirements
        if requirement.address == placement_address and requirement.requirement_kind == "domain-topology"
    )
    assert requirement.explicitness.value == "exact"

    entries = {operation.address: _snapshot_entry(operation) for operation in provisioning.operations}
    approximated = deepcopy(entries[placement_address].payload)
    approximated["domain_topology"]["dns_name"] = "other.example"
    entries[placement_address] = replace(
        entries[placement_address],
        payload=approximated,
    )

    diagnostics, _ = realization_disclosure(
        model.realization_requirements,
        provisioning,
        RuntimeSnapshot(entries=entries),
    )
    assert any(
        diagnostic.code == "runtime.backend-contract-invalid" and diagnostic.address == placement_address
        for diagnostic in diagnostics
    )


def test_backend_facing_plan_dispatches_controller_placement_without_product_commands() -> None:
    model = _compile()
    provisioning = plan(model, _manifest()).provisioning

    placement_address = "provision.domain-controller.domain-0.dc-0-0"
    resources = {resource.address: resource for resource in planned_provisioning_resources(provisioning)}
    placement = resources[placement_address]
    assert placement.resource_type == _RESOURCE_TYPE
    assert placement.payload["target_address"] == "provision.node.dc-0-0"
    assert placement.payload["spec"] == {}
    assert placement.payload["domain_topology"]["controller_addresses"] == ("provision.node.dc-0-0",)
    controller = resources["provision.node.dc-0-0"].payload
    assert not {"runcmd", "commands", "cloud_init"} & set(controller.get("spec", {}))


def test_conformance_requires_topology_observation_for_controller_placement() -> None:
    operation = ProvisionOp(
        action=ChangeAction.CREATE,
        address="provision.domain-controller.domain-0.dc-0-0",
        resource_type=_RESOURCE_TYPE,
        payload={},
    )
    diagnostics = operation_inventory_diagnostics(
        ProvisioningPlan(operations=[operation]),
        RealizationProbeEvidence(
            accepted=True,
            accounted_operations=(operation.address,),
            changed_addresses=(operation.address,),
            driver_invoked=True,
            native_mutated=True,
            portable_state_before="sha256:" + "0" * 64,
            portable_state_after="sha256:" + "1" * 64,
            native_state_before="sha256:" + "2" * 64,
            native_state_after="sha256:" + "3" * 64,
            cleanup_verified=True,
        ),
        {RealizationConcern.TOPOLOGY: ObservationStrength.DRIVER_REPORTED},
    )

    assert [diagnostic.code for diagnostic in diagnostics] == ["conformance.observation-inventory-incomplete"]
