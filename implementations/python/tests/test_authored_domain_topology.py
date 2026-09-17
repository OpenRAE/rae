"""Authored identity-domain topology contracts (issue #763)."""

from __future__ import annotations

import textwrap
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from raes import SDLParseError, SDLValidationError, parse_sdl, parse_sdl_file
from raes.language_service import language_completions
from raes_backend_libvirt.capability_envelope import capability_envelope_diagnostics
from raes_backend_libvirt.manifest import LIBVIRT_PROVISIONER_CAPABILITIES
from raes_backend_protocols.backend_manifest import BackendManifest
from raes_backend_protocols.domain_topology import domain_topology_plan_diagnostics
from raes_backend_stubs.stubs import create_stub_manifest, create_stub_target
from raes_contracts.contracts import schema_bundle
from raes_contracts.planning import ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import resource_payload
from raes_processor.planner import plan
from raes_processor.semantics.realization import realization_disclosure
from raes_reference_backend import create_reference_backend_manifest
from raes_runtime.control_plane import RuntimeControlPlane

_INSTANTIATION_PROVENANCE = {
    "authored_digest": {
        "profile": "raes-sdl-semantic/v2",
        "algorithm": "sha256",
        "value": "sha256:" + "a" * 64,
    }
}


def _scenario(source: str, *, skip_semantic_validation: bool = False):
    return parse_sdl(
        textwrap.dedent(source),
        skip_semantic_validation=skip_semantic_validation,
    )


def _valid_payload() -> dict[str, object]:
    return {
        "name": "domain-lab",
        "nodes": {
            "dc": {"type": "compute", "os": "windows"},
            "workstation": {"type": "compute", "os": "windows"},
        },
        "accounts": {
            "domain-admin": {"username": "Administrator", "node": "dc"},
            "web-service": {
                "username": "svc-web",
                "node": "workstation",
                "spn": "HTTP/workstation.corp.example",
                "domain_ref": "corp",
            },
        },
        "identity_domains": {
            "corp": {
                "profile": "active_directory",
                "dns_name": "corp.example",
                "netbios_name": "CORP",
                "authority_account_ref": "domain-admin",
            }
        },
        "relationships": {
            "dc-role": {
                "type": "domain_controller_for",
                "source": "dc",
                "target": "corp",
                "domain_controller": {},
            },
            "workstation-join": {
                "type": "joins_domain",
                "source": "workstation",
                "target": "corp",
                "domain_join": {"controller_refs": ["dc"]},
            },
        },
    }


def _parse_payload(payload: dict[str, object]):
    return parse_sdl(yaml.safe_dump(payload, sort_keys=False))


def _manifest_with_domain_profiles(*profiles: str) -> BackendManifest:
    base = create_stub_manifest()
    capabilities = replace(
        base.capabilities,
        provisioner=replace(
            base.provisioner,
            supported_domain_profiles=frozenset(profiles),
        ),
    )
    return BackendManifest(
        identity=base.identity,
        supported_contract_versions=base.supported_contract_versions,
        compatibility=base.compatibility,
        realization_support=base.realization_support,
        concept_bindings=base.concept_bindings,
        constraints=base.constraints,
        capabilities=capabilities,
        realization_envelope=base.realization_envelope,
    )


def _snapshot_entry_from_operation(operation: ProvisionOp) -> SnapshotEntry:
    return SnapshotEntry(
        address=operation.address,
        domain=RuntimeDomain.PROVISIONING,
        resource_type=operation.resource_type,
        payload=deepcopy(operation.payload),
        ordering_dependencies=operation.ordering_dependencies,
        refresh_dependencies=operation.refresh_dependencies,
    )


def test_authored_active_directory_topology_has_typed_shape() -> None:
    scenario = _scenario(
        """
        name: domain-lab
        nodes:
          dc:
            type: compute
            os: windows
          workstation:
            type: compute
            os: windows
        accounts:
          domain-admin:
            username: Administrator
            node: dc
          web-service:
            username: svc-web
            node: workstation
            spn: HTTP/workstation.corp.example
            domain_ref: corp
        identity_domains:
          corp:
            profile: active_directory
            dns_name: corp.example
            netbios_name: CORP
            authority_account_ref: domain-admin
        relationships:
          dc-role:
            type: domain_controller_for
            source: dc
            target: corp
            domain_controller: {}
          workstation-join:
            type: joins_domain
            source: workstation
            target: corp
            domain_join:
              controller_refs: [dc]
        """
    )

    domain = scenario.identity_domains["corp"]
    assert domain.profile.value == "active_directory"
    assert domain.dns_name == "corp.example"
    assert domain.netbios_name == "CORP"
    assert domain.authority_account_ref == "domain-admin"
    assert scenario.accounts["web-service"].domain_ref == "corp"
    assert scenario.relationships["dc-role"].domain_controller is not None
    assert scenario.relationships["workstation-join"].domain_join.controller_refs == ["dc"]


def test_domain_profile_schemas_are_closed_at_each_phase_boundary() -> None:
    bundle = schema_bundle()
    authoring_payload = _valid_payload()
    authored_variable = deepcopy(authoring_payload)
    authored_variable["identity_domains"]["corp"]["profile"] = "${profile}"
    authored_unknown = deepcopy(authoring_payload)
    authored_unknown["identity_domains"]["corp"]["profile"] = "ldap"

    authoring = Draft202012Validator(bundle["sdl-authoring-input-v1"])
    assert authoring.is_valid(authoring_payload)
    assert authoring.is_valid(authored_variable)
    assert not authoring.is_valid(authored_unknown)

    instantiated_payload = {**authoring_payload, "instantiation_provenance": _INSTANTIATION_PROVENANCE}
    instantiated_variable = {**authored_variable, "instantiation_provenance": _INSTANTIATION_PROVENANCE}
    instantiated_unknown = {**authored_unknown, "instantiation_provenance": _INSTANTIATION_PROVENANCE}
    instantiated = Draft202012Validator(bundle["instantiated-scenario-v1"])
    assert instantiated.is_valid(instantiated_payload)
    assert not instantiated.is_valid(instantiated_variable)
    assert not instantiated.is_valid(instantiated_unknown)

    snapshot = Draft202012Validator(bundle["instantiated-scenario-snapshot-v1"])
    assert snapshot.is_valid({"profile": "raes-sdl-instantiated-snapshot/v2", "scenario": instantiated_payload})
    assert not snapshot.is_valid({"profile": "raes-sdl-instantiated-snapshot/v2", "scenario": instantiated_variable})
    assert not snapshot.is_valid({"profile": "raes-sdl-instantiated-snapshot/v2", "scenario": instantiated_unknown})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dns_name", "-invalid.example"),
        ("dns_name", "invalid name.example"),
        ("netbios_name", "NAME-THAT-IS-TOO-LONG"),
        ("netbios_name", "INVALID/NAME"),
    ],
)
def test_active_directory_profile_rejects_invalid_names(field: str, value: str) -> None:
    dns_name = value if field == "dns_name" else "corp.example"
    netbios_name = value if field == "netbios_name" else "CORP"
    with pytest.raises(SDLParseError, match=field):
        _scenario(
            f"""
            name: invalid-domain-name
            identity_domains:
              corp:
                profile: active_directory
                dns_name: {dns_name!r}
                netbios_name: {netbios_name!r}
                authority_account_ref: domain-admin
            """
        )


def test_domain_join_rejects_duplicate_controller_candidates() -> None:
    with pytest.raises(SDLParseError, match="controller_refs must be unique"):
        _scenario(
            """
            name: duplicate-controller-candidates
            relationships:
              join:
                type: joins_domain
                source: member
                target: corp
                domain_join:
                  controller_refs: [dc, dc]
            """,
            skip_semantic_validation=True,
        )


def test_domain_requires_a_controller_edge() -> None:
    payload = _valid_payload()
    del payload["relationships"]["dc-role"]

    with pytest.raises(SDLValidationError, match="Identity domain 'corp' has no controller"):
        _parse_payload(payload)


def test_domain_authority_account_must_be_placed_on_its_controller() -> None:
    payload = _valid_payload()
    payload["accounts"]["domain-admin"]["node"] = "workstation"

    with pytest.raises(SDLValidationError, match="authority account 'domain-admin'.*controller"):
        _parse_payload(payload)


def test_join_controller_candidate_must_control_the_same_domain() -> None:
    payload = _valid_payload()
    payload["nodes"]["other-dc"] = {"type": "compute", "os": "windows"}
    payload["accounts"]["other-admin"] = {"username": "Administrator", "node": "other-dc"}
    payload["identity_domains"]["other"] = {
        "profile": "active_directory",
        "dns_name": "other.example",
        "netbios_name": "OTHER",
        "authority_account_ref": "other-admin",
    }
    payload["relationships"]["other-controller"] = {
        "type": "domain_controller_for",
        "source": "other-dc",
        "target": "other",
        "domain_controller": {},
    }
    payload["relationships"]["workstation-join"]["domain_join"]["controller_refs"] = ["other-dc"]

    with pytest.raises(SDLValidationError, match="controller_ref 'other-dc'.*same domain 'corp'"):
        _parse_payload(payload)


def test_spn_requires_an_explicit_domain_binding() -> None:
    payload = _valid_payload()
    del payload["accounts"]["web-service"]["domain_ref"]

    with pytest.raises(SDLValidationError, match="Account 'web-service'.*SPN.*domain_ref"):
        _parse_payload(payload)


def test_domain_bound_account_node_must_belong_to_the_domain() -> None:
    payload = _valid_payload()
    payload["nodes"]["outsider"] = {"type": "compute", "os": "windows"}
    payload["accounts"]["web-service"]["node"] = "outsider"

    with pytest.raises(SDLValidationError, match="Account 'web-service'.*node 'outsider'.*domain 'corp'"):
        _parse_payload(payload)


def test_domain_relationship_type_requires_matching_typed_detail() -> None:
    payload = _valid_payload()
    del payload["relationships"]["dc-role"]["domain_controller"]

    with pytest.raises(SDLValidationError, match="Relationship 'dc-role'.*requires domain_controller"):
        _parse_payload(payload)


def test_controller_role_rejects_switch_nodes() -> None:
    payload = _valid_payload()
    payload["nodes"]["dc"] = {"type": "switch"}

    with pytest.raises(SDLValidationError, match="Relationship 'dc-role'.*controller source 'dc'.*compute"):
        _parse_payload(payload)


def test_node_cannot_control_multiple_active_directory_domains() -> None:
    payload = _valid_payload()
    payload["accounts"]["other-admin"] = {"username": "Administrator", "node": "dc"}
    payload["identity_domains"]["other"] = {
        "profile": "active_directory",
        "dns_name": "other.example",
        "netbios_name": "OTHER",
        "authority_account_ref": "other-admin",
    }
    payload["relationships"]["other-controller"] = {
        "type": "domain_controller_for",
        "source": "dc",
        "target": "other",
        "domain_controller": {},
    }

    with pytest.raises(SDLValidationError, match="Node 'dc'.*multiple active_directory domains"):
        _parse_payload(payload)


def test_duplicate_controller_edges_are_rejected() -> None:
    payload = _valid_payload()
    payload["relationships"]["duplicate-controller"] = dict(payload["relationships"]["dc-role"])

    with pytest.raises(SDLValidationError, match="duplicate controller fact"):
        _parse_payload(payload)


def test_controller_cannot_also_declare_a_redundant_join() -> None:
    payload = _valid_payload()
    payload["relationships"]["dc-join"] = {
        "type": "joins_domain",
        "source": "dc",
        "target": "corp",
        "domain_join": {"controller_refs": ["dc"]},
    }

    with pytest.raises(SDLValidationError, match="Node 'dc'.*controller.*redundant join"):
        _parse_payload(payload)


def test_compiler_projects_normalized_domain_topology_and_ordering() -> None:
    model = compile_runtime_model(_parse_payload(_valid_payload()))

    controller = model.node_deployments["provision.node.dc"]
    member = model.node_deployments["provision.node.workstation"]
    controller_binding = controller.domain_topology
    member_binding = member.domain_topology

    assert controller_binding.domain_id == "corp"
    assert controller_binding.profile == "active_directory"
    assert controller_binding.dns_name == "corp.example"
    assert controller_binding.netbios_name == "CORP"
    assert controller_binding.authority_account_address == "provision.account.domain-admin"
    assert controller_binding.role == "controller"
    assert controller_binding.controller_addresses == ("provision.node.dc",)

    assert member_binding.domain_id == "corp"
    assert member_binding.role == "member"
    assert member_binding.controller_addresses == ("provision.node.dc",)
    assert member.ordering_dependencies == ("provision.domain-controller.corp.dc",)
    assert member.refresh_dependencies == ("provision.domain-controller.corp.dc",)

    payload = resource_payload(member)
    assert payload["domain_topology"]["domain_id"] == "corp"
    assert payload["domain_topology"]["controller_addresses"] == ("provision.node.dc",)


def test_compiler_projects_domain_binding_to_subject_and_authority_accounts() -> None:
    model = compile_runtime_model(_parse_payload(_valid_payload()))

    authority = model.account_placements["provision.account.domain-admin"]
    subject = model.account_placements["provision.account.web-service"]

    assert authority.domain_topology.role == "controller"
    assert authority.domain_topology.domain_id == "corp"
    assert subject.domain_topology.role == "member"
    assert subject.domain_topology.domain_id == "corp"
    assert authority.ordering_dependencies == (
        "provision.node.dc",
        "provision.domain-controller.corp.dc",
    )
    assert subject.ordering_dependencies == (
        "provision.node.workstation",
        "provision.domain-controller.corp.dc",
    )


def test_domain_topology_variables_are_instantiated_before_compilation() -> None:
    scenario = _scenario(
        """
        name: parameterized-domain
        variables:
          profile: {type: string, default: active_directory}
          dns: {type: string, default: corp.example}
          netbios: {type: string, default: CORP}
          domain: {type: string, default: corp}
          controller: {type: string, default: dc}
        nodes:
          dc: {type: compute, os: windows}
          member: {type: compute, os: windows}
        accounts:
          admin: {username: Administrator, node: dc}
          service: {username: svc, node: member, spn: HTTP/member.corp.example, domain_ref: '${domain}'}
        identity_domains:
          corp:
            profile: '${profile}'
            dns_name: '${dns}'
            netbios_name: '${netbios}'
            authority_account_ref: admin
        relationships:
          controller:
            type: domain_controller_for
            source: dc
            target: corp
            domain_controller: {}
          join:
            type: joins_domain
            source: member
            target: corp
            domain_join: {controller_refs: ['${controller}']}
        """
    )

    model = compile_runtime_model(scenario)

    binding = model.node_deployments["provision.node.member"].domain_topology
    assert binding.profile == "active_directory"
    assert binding.dns_name == "corp.example"
    assert binding.netbios_name == "CORP"
    assert binding.controller_addresses == ("provision.node.dc",)


def test_module_composition_namespaces_all_domain_topology_references(tmp_path: Path) -> None:
    imported = tmp_path / "domain.yaml"
    imported.write_text(
        textwrap.dedent(
            """
            name: domain-module
            version: 1.0.0
            module:
              id: raes/domain-module
              version: 1.0.0
              exports:
                nodes: [dc, member]
                accounts: [admin, service]
                identity_domains: [corp]
                relationships: [controller, join]
            nodes:
              dc: {type: compute, os: windows}
              member: {type: compute, os: windows}
            accounts:
              admin: {username: Administrator, node: dc}
              service: {username: svc, node: member, spn: HTTP/member.corp.example, domain_ref: corp}
            identity_domains:
              corp:
                profile: active_directory
                dns_name: corp.example
                netbios_name: CORP
                authority_account_ref: admin
            relationships:
              controller:
                type: domain_controller_for
                source: dc
                target: corp
                domain_controller: {}
              join:
                type: joins_domain
                source: member
                target: corp
                domain_join: {controller_refs: [dc]}
            """
        ),
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        textwrap.dedent(
            """
            name: root
            imports:
              - path: domain.yaml
                namespace: shared
                version: 1.0.0
            """
        ),
        encoding="utf-8",
    )

    scenario = parse_sdl_file(root)

    assert scenario.identity_domains["shared.corp"].authority_account_ref == "shared.admin"
    assert scenario.accounts["shared.service"].domain_ref == "shared.corp"
    assert scenario.relationships["shared.join"].domain_join.controller_refs == ["shared.dc"]
    model = compile_runtime_model(scenario)
    assert model.node_deployments["provision.node.shared.member"].domain_topology.domain_id == "shared.corp"


def test_planner_rejects_domain_profile_outside_provisioner_capabilities() -> None:
    model = compile_runtime_model(_parse_payload(_valid_payload()))

    execution_plan = plan(model, _manifest_with_domain_profiles())

    assert any(
        diagnostic.code == "provisioner.unsupported-domain-profile" and diagnostic.address == "provision.node.dc"
        for diagnostic in execution_plan.diagnostics
    )


def test_planner_accepts_explicitly_supported_domain_profile() -> None:
    model = compile_runtime_model(_parse_payload(_valid_payload()))

    execution_plan = plan(model, _manifest_with_domain_profiles("active_directory"))

    assert not any("domain-profile" in diagnostic.code for diagnostic in execution_plan.diagnostics)


def test_reference_backend_rejects_unrealized_domain_topology_and_spn() -> None:
    model = compile_runtime_model(_parse_payload(_valid_payload()))

    execution_plan = plan(model, create_reference_backend_manifest())

    codes = {diagnostic.code for diagnostic in execution_plan.diagnostics}
    assert "provisioner.unsupported-domain-profile" in codes
    assert "provisioner.unsupported-account-feature" in codes


def test_libvirt_capability_envelope_rejects_domain_profile_independently() -> None:
    model = compile_runtime_model(_parse_payload(_valid_payload()))
    provisioning = plan(model, _manifest_with_domain_profiles("active_directory")).provisioning

    diagnostics = capability_envelope_diagnostics(provisioning, LIBVIRT_PROVISIONER_CAPABILITIES)

    assert any(
        diagnostic.code == "libvirt-backend.realization.unsupported-domain-profile"
        and diagnostic.address == "provision.node.dc"
        for diagnostic in diagnostics
    )
    assert any(
        diagnostic.code == "libvirt-backend.realization.unsupported-domain-profile"
        and diagnostic.address == "provision.domain-controller.corp.dc"
        for diagnostic in diagnostics
    )


def test_libvirt_capability_envelope_ignores_resources_without_domain_topology() -> None:
    scenario = _scenario(
        """
        name: ordinary-workstation
        nodes:
          workstation: {type: compute, os: windows}
        accounts:
          local-user: {username: local, node: workstation}
        """
    )
    provisioning = plan(compile_runtime_model(scenario), _manifest_with_domain_profiles()).provisioning

    diagnostics = capability_envelope_diagnostics(provisioning, LIBVIRT_PROVISIONER_CAPABILITIES)

    assert not any(
        diagnostic.code == "libvirt-backend.realization.unsupported-domain-profile" for diagnostic in diagnostics
    )


def test_shared_plan_analysis_accepts_compiler_emitted_topology() -> None:
    model = compile_runtime_model(_parse_payload(_valid_payload()))
    provisioning = plan(model, _manifest_with_domain_profiles("active_directory")).provisioning

    diagnostics = domain_topology_plan_diagnostics(
        provisioning,
        supported_domain_profiles=frozenset({"active_directory"}),
    )

    assert diagnostics == []


def test_shared_plan_analysis_resolves_controller_from_snapshot_for_incremental_member() -> None:
    model = compile_runtime_model(_parse_payload(_valid_payload()))
    provisioning = plan(model, _manifest_with_domain_profiles("active_directory")).provisioning
    operations = {operation.address: operation for operation in provisioning.operations}
    snapshot_addresses = (
        "provision.node.dc",
        "provision.domain-controller.corp.dc",
        "provision.account.domain-admin",
    )
    snapshot = RuntimeSnapshot(
        entries={address: _snapshot_entry_from_operation(operations[address]) for address in snapshot_addresses}
    )
    incremental_plan = ProvisioningPlan(
        operations=[operations["provision.node.workstation"]],
    )

    diagnostics = domain_topology_plan_diagnostics(
        incremental_plan,
        snapshot=snapshot,
        supported_domain_profiles=frozenset({"active_directory"}),
    )

    assert diagnostics == []


def test_shared_plan_analysis_operation_overrides_stale_snapshot_entry() -> None:
    model = compile_runtime_model(_parse_payload(_valid_payload()))
    provisioning = plan(model, _manifest_with_domain_profiles("active_directory")).provisioning
    operations = {operation.address: operation for operation in provisioning.operations}
    member_address = "provision.node.workstation"
    stale_member = _snapshot_entry_from_operation(operations[member_address])
    stale_payload = deepcopy(stale_member.payload)
    stale_payload["domain_topology"]["dns_name"] = "legacy.example"
    stale_member = replace(stale_member, payload=stale_payload)
    snapshot_entries = {
        address: _snapshot_entry_from_operation(operations[address])
        for address in (
            "provision.node.dc",
            "provision.domain-controller.corp.dc",
            "provision.account.domain-admin",
        )
    }
    snapshot_entries[member_address] = stale_member
    snapshot = RuntimeSnapshot(entries=snapshot_entries)
    update_plan = ProvisioningPlan(operations=[operations[member_address]])

    diagnostics = domain_topology_plan_diagnostics(
        update_plan,
        snapshot=snapshot,
        supported_domain_profiles=frozenset({"active_directory"}),
    )

    assert diagnostics == []


def test_shared_plan_analysis_rejects_member_without_controller_ordering() -> None:
    model = compile_runtime_model(_parse_payload(_valid_payload()))
    provisioning = plan(model, _manifest_with_domain_profiles("active_directory")).provisioning
    operations = [
        replace(operation, ordering_dependencies=(), refresh_dependencies=())
        if operation.address == "provision.node.workstation"
        else operation
        for operation in provisioning.operations
    ]
    direct_plan = replace(provisioning, operations=operations)

    diagnostics = domain_topology_plan_diagnostics(direct_plan)

    assert any(
        diagnostic.code == "provisioning.domain-topology.controller-dependency-missing"
        and diagnostic.address == "provision.node.workstation"
        for diagnostic in diagnostics
    )


def test_shared_plan_analysis_rejects_account_binding_that_disagrees_with_node() -> None:
    model = compile_runtime_model(_parse_payload(_valid_payload()))
    provisioning = plan(model, _manifest_with_domain_profiles("active_directory")).provisioning
    operations = []
    for operation in provisioning.operations:
        if operation.address != "provision.account.web-service":
            operations.append(operation)
            continue
        payload = deepcopy(operation.payload)
        payload["domain_topology"]["domain_id"] = "other"
        operations.append(replace(operation, payload=payload))
    direct_plan = replace(provisioning, operations=operations)

    diagnostics = domain_topology_plan_diagnostics(direct_plan)

    assert any(
        diagnostic.code == "provisioning.domain-topology.account-node-mismatch"
        and diagnostic.address == "provision.account.web-service"
        for diagnostic in diagnostics
    )


def test_control_plane_rejects_incoherent_domain_topology_before_backend_validation() -> None:
    payload = _valid_payload()
    for node in payload["nodes"].values():
        node.pop("os", None)
    model = compile_runtime_model(_parse_payload(payload))
    provisioning = plan(model, _manifest_with_domain_profiles("active_directory")).provisioning
    operations = [
        replace(operation, ordering_dependencies=(), refresh_dependencies=())
        if operation.address == "provision.node.workstation"
        else operation
        for operation in provisioning.operations
    ]
    direct_plan = replace(provisioning, operations=operations)
    control_plane = RuntimeControlPlane(create_stub_target())

    receipt = control_plane.submit_provisioning(direct_plan)

    assert receipt.accepted is False
    assert [diagnostic.code for diagnostic in receipt.diagnostics] == [
        "provisioning.domain-topology.controller-dependency-missing"
    ]


def test_domain_topology_is_an_exact_realization_requirement_for_every_carrier() -> None:
    model = compile_runtime_model(_parse_payload(_valid_payload()))

    requirements = [
        requirement
        for requirement in model.realization_requirements
        if requirement.requirement_kind == "domain-topology"
    ]

    assert {requirement.address for requirement in requirements} == {
        "provision.node.dc",
        "provision.node.workstation",
        "provision.account.domain-admin",
        "provision.account.web-service",
        "provision.domain-controller.corp.dc",
    }
    assert all(requirement.explicitness.value == "exact" for requirement in requirements)
    assert all(requirement.provenance.value == "processor-derived" for requirement in requirements)
    provisioning = plan(model, _manifest_with_domain_profiles("active_directory")).provisioning
    authority = [entry for entry in provisioning.realization_authority if entry.requirement_kind == "domain-topology"]
    assert {entry.address for entry in authority} == {requirement.address for requirement in requirements}
    assert all(entry.mode.value == "exact" and entry.payload_pointer == "/domain_topology" for entry in authority)


def test_domain_topology_readback_rejects_silent_approximation() -> None:
    model = compile_runtime_model(_parse_payload(_valid_payload()))
    provisioning = plan(model, _manifest_with_domain_profiles("active_directory")).provisioning
    entries = {}
    for operation in provisioning.operations:
        payload = deepcopy(operation.payload)
        if operation.address == "provision.node.workstation":
            payload["domain_topology"]["dns_name"] = "approximated.example"
        entries[operation.address] = SnapshotEntry(
            address=operation.address,
            domain=RuntimeDomain.PROVISIONING,
            resource_type=operation.resource_type,
            payload=payload,
            ordering_dependencies=operation.ordering_dependencies,
            refresh_dependencies=operation.refresh_dependencies,
        )
    snapshot = RuntimeSnapshot(entries=entries)

    diagnostics, _provenance = realization_disclosure(
        model.realization_requirements,
        provisioning,
        snapshot,
    )

    assert any(
        diagnostic.code == "runtime.backend-contract-invalid" and diagnostic.address == "provision.node.workstation"
        for diagnostic in diagnostics
    )


def test_language_service_completes_domain_fields_and_references() -> None:
    source = yaml.safe_dump(_valid_payload(), sort_keys=False)

    domain_fields = language_completions(source, cursor_path="/identity_domains/corp")
    account_domains = language_completions(source, cursor_path="/accounts/web-service/domain_ref")
    authority_accounts = language_completions(
        source,
        cursor_path="/identity_domains/corp/authority_account_ref",
    )
    join_controllers = language_completions(
        source,
        cursor_path="/relationships/workstation-join/domain_join/controller_refs",
    )

    assert {item["label"] for item in domain_fields["items"]} >= {
        "profile",
        "dns_name",
        "netbios_name",
        "authority_account_ref",
    }
    assert {item["label"] for item in account_domains["items"]} == {"corp"}
    assert {item["label"] for item in authority_accounts["items"]} == {
        "domain-admin",
        "web-service",
    }
    assert {item["label"] for item in join_controllers["items"]} == {"dc", "workstation"}
