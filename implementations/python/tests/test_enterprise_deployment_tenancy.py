"""Enterprise identity and deployment-tenancy authoring contracts (#857)."""

from __future__ import annotations

import textwrap
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from raes import SDLParseError, SDLValidationError, parse_sdl, parse_sdl_file
from raes.scenario import Scenario
from raes.semantics.deployment_tenancy import analyze_deployment_tenancy
from raes_contracts.contracts import schema_bundle
from raes_processor.compiler import compile_runtime_model

_INSTANTIATION_PROVENANCE = {
    "authored_digest": {
        "profile": "raes-sdl-semantic/v2",
        "algorithm": "sha256",
        "value": "sha256:" + "a" * 64,
    }
}


def _valid_payload() -> dict[str, object]:
    return {
        "name": "enterprise-lab",
        "nodes": {
            "dc": {
                "type": "compute",
                "os": "windows",
                "endpoint_persona": "service",
                "services": [{"name": "ldap", "port": 389}],
            },
            "idp": {
                "type": "compute",
                "os": "linux",
                "endpoint_persona": "service",
                "services": [{"name": "oidc", "port": 8443}],
            },
            "carrier": {
                "type": "compute",
                "os": "linux",
                "endpoint_persona": "carrier",
            },
            "workstation": {
                "type": "compute",
                "os": "windows",
                "endpoint_persona": "workforce",
            },
            "inference": {
                "type": "compute",
                "os": "linux",
                "endpoint_persona": "service",
                "services": [
                    {"name": "inference-api", "port": 8080},
                    {"name": "metrics", "port": 9090},
                ],
            },
        },
        "accounts": {
            "domain-admin": {"username": "Administrator", "node": "dc"},
        },
        "identity_domains": {
            "corp": {
                "profile": "active_directory",
                "dns_name": "corp.example",
                "netbios_name": "CORP",
                "authority_account_ref": "domain-admin",
            }
        },
        "identity_forests": {
            "enterprise": {
                "root_domain_ref": "corp",
                "domain_refs": ["corp"],
            }
        },
        "identity_facades": {
            "workforce-oidc": {
                "service_ref": "nodes.idp.services.oidc",
                "protocol": "oidc",
            }
        },
        "persistent_volumes": {
            "range-state": {
                "lifecycle": "ephemeral",
                "access_mode": "read_write_once",
                "consumers": [
                    {
                        "node": "idp",
                        "mount_destination": "/var/lib/range",
                        "access_mode": "read_write",
                    }
                ],
            }
        },
        "deployment_tenants": {
            "range-a": {},
            "shared-platform": {},
        },
        "deployment_cells": {
            "range-a-cell": {
                "tenant_ref": "range-a",
                "node_refs": ["dc", "idp", "carrier", "workstation"],
                "cross_tenant_isolation": "default_deny",
            },
            "shared-cell": {
                "tenant_ref": "shared-platform",
                "node_refs": ["inference"],
                "cross_tenant_isolation": "default_deny",
            },
        },
        "relationships": {
            "dc-role": {
                "type": "domain_controller_for",
                "source": "dc",
                "target": "corp",
                "domain_controller": {},
            },
            "workforce-federation": {
                "type": "directory_federates_to",
                "source": "enterprise",
                "target": "workforce-oidc",
                "identity_federation": {
                    "direction": "authority_to_facade",
                    "protocol": "ldap_tls",
                    "mapping_intent": "groups_to_roles",
                    "tenant_claim_name": "range_instance",
                    "tenant_claim_owner": "facade",
                },
            },
            "workstation-placement": {
                "type": "placed_on_carrier",
                "source": "workstation",
                "target": "carrier",
                "carrier_placement": {
                    "kernel_boundary": "shared_kernel",
                },
            },
            "range-inference": {
                "type": "uses_shared_service",
                "source": "range-a",
                "target": "nodes.inference.services.inference-api",
                "shared_service": {
                    "tenant_isolation": "stateless",
                    "workload_authentication": "tenant_scoped_workload_identity",
                    "mutable_state_refs": ["range-state"],
                    "mutable_state_owner": "consumer_tenant",
                    "reset_generation_owner": "consumer_tenant",
                },
            },
            "inference-call": {
                "type": "connects_to",
                "source": "workstation",
                "target": "nodes.inference.services.inference-api",
            },
        },
    }


def _parse_payload(payload: dict[str, object]):
    return parse_sdl(yaml.safe_dump(payload, sort_keys=False))


def test_enterprise_identity_and_tenancy_have_closed_typed_shape() -> None:
    scenario = _parse_payload(_valid_payload())

    forest = scenario.identity_forests["enterprise"]
    assert forest.root_domain_ref == "corp"
    assert forest.domain_refs == ["corp"]
    assert scenario.identity_facades["workforce-oidc"].service_ref == "nodes.idp.services.oidc"
    assert scenario.nodes["workstation"].endpoint_persona.value == "workforce"
    assert scenario.deployment_cells["range-a-cell"].tenant_ref == "range-a"
    federation = scenario.relationships["workforce-federation"].identity_federation
    assert federation.protocol.value == "ldap_tls"
    assert federation.tenant_claim_owner.value == "facade"
    placement = scenario.relationships["workstation-placement"].carrier_placement
    assert placement.kernel_boundary.value == "shared_kernel"
    binding = scenario.relationships["range-inference"].shared_service
    assert binding.tenant_isolation.value == "stateless"
    assert binding.mutable_state_refs == ["range-state"]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("nodes", "workstation", "endpoint_persona"), "employee"),
        (("deployment_cells", "range-a-cell", "cross_tenant_isolation"), "allow"),
        (
            ("relationships", "workstation-placement", "carrier_placement", "kernel_boundary"),
            "docker",
        ),
        (
            ("relationships", "range-inference", "shared_service", "workload_authentication"),
            "api-key",
        ),
    ],
)
def test_enterprise_vocabularies_reject_unknown_terms(path: tuple[str, ...], value: str) -> None:
    payload = _valid_payload()
    target: object = payload
    for segment in path[:-1]:
        target = target[segment]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]

    with pytest.raises(SDLParseError):
        _parse_payload(payload)


def test_forest_root_must_be_an_explicit_member() -> None:
    payload = _valid_payload()
    payload["identity_forests"]["enterprise"]["domain_refs"] = []

    with pytest.raises(SDLParseError, match="domain_refs"):
        _parse_payload(payload)

    payload["identity_forests"]["enterprise"]["domain_refs"] = ["other"]
    with pytest.raises(SDLValidationError, match="root_domain_ref.*must appear in domain_refs"):
        _parse_payload(payload)


def test_domain_cannot_belong_to_multiple_forests() -> None:
    payload = _valid_payload()
    payload["identity_forests"]["other"] = {
        "root_domain_ref": "corp",
        "domain_refs": ["corp"],
    }

    with pytest.raises(SDLValidationError, match="Identity domain 'corp'.*multiple forests"):
        _parse_payload(payload)


def test_forest_mode_requires_every_domain_to_have_one_forest() -> None:
    without_forest = _valid_payload()
    del without_forest["identity_forests"]
    del without_forest["relationships"]["workforce-federation"]
    assert _parse_payload(without_forest).identity_forests == {}

    payload = _valid_payload()
    payload["identity_domains"]["unassigned"] = {
        "profile": "active_directory",
        "dns_name": "unassigned.example",
        "netbios_name": "UNASSIGNED",
        "authority_account_ref": "domain-admin",
    }

    with pytest.raises(SDLValidationError, match="Identity domain 'unassigned'.*exactly one identity forest"):
        _parse_payload(payload)


def test_typed_forest_trust_rejects_self_trust() -> None:
    payload = _valid_payload()
    payload["relationships"]["self-trust"] = {
        "type": "forest_trusts",
        "source": "enterprise",
        "target": "enterprise",
        "forest_trust": {
            "trust_type": "forest",
            "direction": "bidirectional",
        },
    }

    with pytest.raises(SDLValidationError, match="cannot trust a forest with itself"):
        _parse_payload(payload)


def test_identity_facade_must_reference_a_named_vm_service() -> None:
    payload = _valid_payload()
    payload["identity_facades"]["workforce-oidc"]["service_ref"] = "idp"

    with pytest.raises(SDLValidationError, match="service_ref 'idp'.*named compute service"):
        _parse_payload(payload)


def test_federation_requires_authority_and_facade_endpoints() -> None:
    payload = _valid_payload()
    payload["relationships"]["workforce-federation"]["source"] = "range-a"

    with pytest.raises(SDLValidationError, match="identity domain or forest.*identity facade"):
        _parse_payload(payload)


def test_typed_relationship_detail_must_match_relationship_type() -> None:
    payload = _valid_payload()
    payload["relationships"]["workstation-placement"]["type"] = "depends_on"

    with pytest.raises(SDLValidationError, match="carrier_placement.*type 'depends_on'"):
        _parse_payload(payload)


def test_existing_generic_trust_and_federation_relationships_remain_compatible() -> None:
    scenario = parse_sdl(
        textwrap.dedent(
            """
            name: generic-relationships
            nodes:
              source: {type: compute}
              target: {type: compute}
            relationships:
              generic-trust:
                type: trusts
                source: source
                target: target
              generic-federation:
                type: federates_with
                source: source
                target: target
            """
        )
    )

    assert scenario.relationships["generic-trust"].forest_trust is None
    assert scenario.relationships["generic-federation"].identity_federation is None


def test_endpoint_persona_is_compute_only() -> None:
    payload = _valid_payload()
    payload["nodes"]["workstation"] = {
        "type": "switch",
        "endpoint_persona": "workforce",
    }

    with pytest.raises(SDLParseError, match="Switch nodes cannot have compute-only fields.*endpoint_persona"):
        _parse_payload(payload)


def test_carrier_placement_rejects_self_cycles_and_non_carriers() -> None:
    payload = _valid_payload()
    payload["relationships"]["workstation-placement"]["target"] = "workstation"
    with pytest.raises(SDLValidationError, match="cannot place a node on itself"):
        _parse_payload(payload)

    payload = _valid_payload()
    payload["nodes"]["carrier"]["endpoint_persona"] = "service"
    with pytest.raises(SDLValidationError, match="carrier.*persona"):
        _parse_payload(payload)

    payload = _valid_payload()
    payload["relationships"]["carrier-placement"] = {
        "type": "placed_on_carrier",
        "source": "carrier",
        "target": "workstation",
        "carrier_placement": {"kernel_boundary": "shared_kernel"},
    }
    with pytest.raises(SDLValidationError, match="carrier placement cycle"):
        _parse_payload(payload)


def test_node_cannot_belong_to_multiple_deployment_cells() -> None:
    payload = _valid_payload()
    payload["deployment_cells"]["shared-cell"]["node_refs"].append("workstation")

    with pytest.raises(SDLValidationError, match="Node 'workstation'.*multiple deployment cells"):
        _parse_payload(payload)


def test_all_vm_nodes_require_cell_membership_when_tenancy_is_declared() -> None:
    without_tenancy = {
        "name": "standalone-vm",
        "nodes": {
            "standalone": {
                "type": "compute",
                "os": "linux",
            }
        },
    }
    assert _parse_payload(without_tenancy).deployment_cells == {}

    payload = _valid_payload()
    payload["deployment_cells"]["range-a-cell"]["node_refs"].remove("workstation")

    with pytest.raises(SDLValidationError, match="Compute node 'workstation'.*exactly one deployment cell"):
        _parse_payload(payload)


def test_carrier_placement_must_stay_in_one_deployment_cell() -> None:
    payload = _valid_payload()
    payload["deployment_cells"]["range-a-cell"]["node_refs"].remove("carrier")
    payload["deployment_cells"]["shared-cell"]["node_refs"].append("carrier")

    with pytest.raises(SDLValidationError, match="carrier placement.*different deployment cells"):
        _parse_payload(payload)


def test_nested_carrier_placement_is_rejected_without_a_cycle() -> None:
    payload = _valid_payload()
    payload["nodes"]["outer-carrier"] = {
        "type": "compute",
        "os": "linux",
        "endpoint_persona": "carrier",
    }
    payload["deployment_cells"]["range-a-cell"]["node_refs"].append("outer-carrier")
    payload["relationships"]["carrier-placement"] = {
        "type": "placed_on_carrier",
        "source": "carrier",
        "target": "outer-carrier",
        "carrier_placement": {"kernel_boundary": "shared_kernel"},
    }

    with pytest.raises(SDLValidationError, match="cannot place a node on another placed node"):
        _parse_payload(payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("workload_authentication", "none"),
        ("tenant_isolation", "none"),
    ],
)
def test_cross_cell_shared_service_requires_tenant_safe_policy(field_name: str, value: str) -> None:
    payload = _valid_payload()
    payload["relationships"]["range-inference"]["shared_service"][field_name] = value

    with pytest.raises(SDLValidationError, match="isolation requires tenant-scoped workload authentication"):
        _parse_payload(payload)


def test_cross_cell_service_consumption_requires_an_explicit_shared_binding() -> None:
    payload = _valid_payload()
    del payload["relationships"]["range-inference"]

    with pytest.raises(SDLValidationError, match="cross-cell service consumption.*shared-service binding"):
        _parse_payload(payload)


def test_cross_cell_service_binding_must_match_the_exact_target_service() -> None:
    payload = _valid_payload()
    payload["relationships"]["range-inference"]["target"] = "nodes.inference.services.metrics"

    with pytest.raises(SDLValidationError, match="cross-cell service consumption.*shared-service binding"):
        _parse_payload(payload)


def test_shared_service_state_and_reset_ownership_are_consistent() -> None:
    payload = _valid_payload()
    payload["relationships"]["range-inference"]["shared_service"]["mutable_state_owner"] = "none"
    with pytest.raises(SDLValidationError, match="mutable_state_refs.*owner"):
        _parse_payload(payload)

    payload = _valid_payload()
    payload["relationships"]["range-inference"]["shared_service"]["reset_generation_owner"] = "none"
    with pytest.raises(SDLValidationError, match="reset_generation_owner"):
        _parse_payload(payload)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("state-refs-missing", "shared-service.state-refs-missing"),
        ("reset-without-state", "shared-service.reset-owner-without-state"),
        ("state-owner-conflict", "shared-service.state-owner-conflict"),
        ("state-unbound", "shared-service.state-unbound"),
        ("tenant-unbound", "cell.tenant-unbound"),
        ("node-unbound", "cell.node-unbound"),
        ("multiple-carriers", "placement.multiple-carriers"),
        ("detail-mismatch", "relationship.detail-mismatch"),
        ("placement-endpoint", "placement.endpoint-invalid"),
        ("shared-service-endpoint", "shared-service.endpoint-invalid"),
        ("placement-detail-required", "relationship.detail-required"),
        ("shared-service-detail-required", "relationship.detail-required"),
    ],
)
def test_deployment_isolation_rejects_inconsistent_bindings(mutation: str, code: str) -> None:
    payload = _valid_payload()
    binding = payload["relationships"]["range-inference"]["shared_service"]
    if mutation == "state-refs-missing":
        binding["mutable_state_refs"] = []
    elif mutation == "reset-without-state":
        binding["mutable_state_refs"] = []
        binding["mutable_state_owner"] = "none"
    elif mutation == "state-owner-conflict":
        second_binding = deepcopy(payload["relationships"]["range-inference"])
        second_binding["source"] = "shared-platform"
        payload["relationships"]["second-inference"] = second_binding
    elif mutation == "state-unbound":
        binding["mutable_state_refs"] = ["missing-volume"]
    elif mutation == "tenant-unbound":
        payload["deployment_cells"]["range-a-cell"]["tenant_ref"] = "missing-tenant"
    elif mutation == "node-unbound":
        payload["deployment_cells"]["range-a-cell"]["node_refs"].append("missing-node")
    elif mutation == "multiple-carriers":
        payload["nodes"]["second-carrier"] = deepcopy(payload["nodes"]["carrier"])
        payload["deployment_cells"]["range-a-cell"]["node_refs"].append("second-carrier")
        second_placement = deepcopy(payload["relationships"]["workstation-placement"])
        second_placement["target"] = "second-carrier"
        payload["relationships"]["second-placement"] = second_placement
    elif mutation == "placement-endpoint":
        payload["relationships"]["workstation-placement"]["source"] = "missing-node"
    elif mutation == "shared-service-endpoint":
        payload["relationships"]["range-inference"]["source"] = "missing-tenant"
    elif mutation == "placement-detail-required":
        del payload["relationships"]["workstation-placement"]["carrier_placement"]
    elif mutation == "shared-service-detail-required":
        del payload["relationships"]["range-inference"]["shared_service"]
    else:
        payload["relationships"]["inference-call"]["carrier_placement"] = {"kernel_boundary": "shared_kernel"}

    # Check the named rule directly: another rejection must not mask a disabled
    # isolation check. Then verify rejection through the public parser as well.
    scenario = Scenario.model_validate(payload)
    issues = analyze_deployment_tenancy(
        deployment_tenants=scenario.deployment_tenants,
        deployment_cells=scenario.deployment_cells,
        nodes=scenario.nodes,
        persistent_volumes=scenario.persistent_volumes,
        relationships=scenario.relationships,
        is_unresolved=lambda _value: False,
    )
    assert f"deployment-tenancy.{code}" in {issue.code for issue in issues}
    with pytest.raises(SDLValidationError):
        _parse_payload(payload)


def test_consumer_owned_shared_state_must_stay_with_its_tenant() -> None:
    payload = _valid_payload()
    payload["persistent_volumes"]["range-state"]["consumers"][0]["node"] = "inference"

    with pytest.raises(SDLValidationError, match="consumed only by its tenant"):
        _parse_payload(payload)


def test_service_owned_shared_state_must_be_consumed_by_the_service_node() -> None:
    payload = _valid_payload()
    binding = payload["relationships"]["range-inference"]["shared_service"]
    binding["tenant_isolation"] = "tenant_partitioned"
    binding["mutable_state_owner"] = "shared_service"
    binding["reset_generation_owner"] = "shared_service"

    with pytest.raises(SDLValidationError, match="consumed by the service node"):
        _parse_payload(payload)


def test_shared_service_isolation_and_state_modes_remain_independent() -> None:
    payload = _valid_payload()
    binding = payload["relationships"]["range-inference"]["shared_service"]
    binding["mutable_state_owner"] = "shared_service"
    binding["reset_generation_owner"] = "shared_service"
    with pytest.raises(SDLValidationError, match="stateless isolation forbids shared-service-owned"):
        _parse_payload(payload)

    payload = _valid_payload()
    binding = payload["relationships"]["range-inference"]["shared_service"]
    binding["tenant_isolation"] = "tenant_partitioned"
    with pytest.raises(SDLValidationError, match="tenant_partitioned.*shared-service-owned"):
        _parse_payload(payload)


def test_module_composition_rewrites_all_enterprise_references(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["module"] = {
        "id": "raes/enterprise",
        "version": "1.0.0",
        "exports": {
            section: list(values)
            for section, values in {
                "nodes": payload["nodes"],
                "accounts": payload["accounts"],
                "identity_domains": payload["identity_domains"],
                "identity_forests": payload["identity_forests"],
                "identity_facades": payload["identity_facades"],
                "persistent_volumes": payload["persistent_volumes"],
                "deployment_tenants": payload["deployment_tenants"],
                "deployment_cells": payload["deployment_cells"],
                "relationships": payload["relationships"],
            }.items()
        },
    }
    imported = tmp_path / "enterprise.yaml"
    imported.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    root = tmp_path / "root.yaml"
    root.write_text(
        textwrap.dedent(
            """
            name: root
            imports:
              - path: enterprise.yaml
                namespace: shared
                version: 1.0.0
            """
        ),
        encoding="utf-8",
    )

    scenario = parse_sdl_file(root)

    assert scenario.identity_forests["shared.enterprise"].root_domain_ref == "shared.corp"
    assert scenario.identity_facades["shared.workforce-oidc"].service_ref == "nodes.shared.idp.services.oidc"
    assert scenario.deployment_cells["shared.range-a-cell"].tenant_ref == "shared.range-a"
    assert "shared.workstation" in scenario.deployment_cells["shared.range-a-cell"].node_refs
    assert scenario.relationships["shared.workstation-placement"].source == "shared.workstation"
    shared = scenario.relationships["shared.range-inference"].shared_service
    assert shared.mutable_state_refs == ["shared.range-state"]


def test_enterprise_variables_revalidate_before_compilation() -> None:
    payload = _valid_payload()
    payload["variables"] = {
        "persona": {"type": "string", "default": "workforce"},
        "isolation": {"type": "string", "default": "default_deny"},
    }
    payload["nodes"]["workstation"]["endpoint_persona"] = "${persona}"
    payload["deployment_cells"]["range-a-cell"]["cross_tenant_isolation"] = "${isolation}"

    model = compile_runtime_model(_parse_payload(payload))

    assert model.node_deployments["provision.node.workstation"].spec["node"]["endpoint_persona"] == "workforce"
    assert model.realization_instance.deployment_cells["range-a-cell"].cross_tenant_isolation.value == "default_deny"


def test_compiler_preserves_enterprise_intent_without_new_policy_resources() -> None:
    model = compile_runtime_model(_parse_payload(_valid_payload()))

    workstation = model.node_deployments["provision.node.workstation"]
    assert workstation.spec["node"]["endpoint_persona"] == "workforce"
    assert model.relationship_specs["workstation-placement"]["carrier_placement"] == {
        "kernel_boundary": "shared_kernel"
    }
    assert model.relationship_specs["range-inference"]["shared_service"]["tenant_isolation"] == "stateless"
    assert model.realization_instance.identity_forests["enterprise"].root_domain_ref == "corp"


def test_published_phase_schemas_carry_closed_enterprise_shape() -> None:
    bundle = schema_bundle()
    payload = _valid_payload()
    authoring = Draft202012Validator(bundle["sdl-authoring-input-v1"])
    assert authoring.is_valid(payload)

    unknown = deepcopy(payload)
    unknown["deployment_cells"]["range-a-cell"]["provider_region"] = "europe-west4"
    assert not authoring.is_valid(unknown)

    instantiated_payload = {**payload, "instantiation_provenance": _INSTANTIATION_PROVENANCE}
    instantiated = Draft202012Validator(bundle["instantiated-scenario-v1"])
    assert instantiated.is_valid(instantiated_payload)

    snapshot = Draft202012Validator(bundle["instantiated-scenario-snapshot-v1"])
    assert snapshot.is_valid(
        {
            "profile": "raes-sdl-instantiated-snapshot/v2",
            "scenario": instantiated_payload,
        }
    )


def test_absent_enterprise_sections_preserve_existing_documents() -> None:
    scenario = parse_sdl("name: minimal\nnodes: {}\n")

    assert scenario.identity_forests == {}
    assert scenario.identity_facades == {}
    assert scenario.deployment_tenants == {}
    assert scenario.deployment_cells == {}
