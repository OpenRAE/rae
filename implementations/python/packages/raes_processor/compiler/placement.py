"""Content and account placement compilation."""

from raes.content import Content, ServiceSearchIndexSchemaMaterialization
from raes.nodes import NodeType
from raes.scenario import InstantiatedScenario
from raes.semantics.domain_topology import (
    DomainNodeRole,
    DomainTopologyAnalysis,
)
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.domain_profiles import DomainProfileBindingModel

from ..models import (
    AccountPlacement,
    ContentPlacement,
    Diagnostic,
    DomainControllerPlacement,
    ServiceContentMaterializationBinding,
    ServiceSearchIndexSchemaMaterializationBinding,
)
from .addresses import (
    _account_address,
    _assertion_address,
    _compiled_domain_binding,
    _content_address,
    _domain_controller_address,
    _node_address,
    _observation_boundary_address,
    _resolve_node_service_ref,
    _section_ref_name,
    _service_address,
)
from .ref_resolution import _resolve_node_ref
from .support import _dedupe, _dump


def _compile_content_placements(
    scenario: InstantiatedScenario,
    diagnostics: list[Diagnostic],
) -> dict[str, ContentPlacement]:
    content_placements: dict[str, ContentPlacement] = {}
    for name, content in scenario.content.items():
        address = _content_address(name)
        target_address, target_diagnostics = _resolve_node_ref(
            scenario,
            ref_name=content.target,
            owner_address=address,
            domain="provisioning",
            code_prefix="provisioning.content-target-ref",
            node_label="content target",
            required_type=NodeType.COMPUTE,
        )
        diagnostics.extend(target_diagnostics)
        if target_address is None:
            continue
        compiled = _compile_service_materialization(scenario, content, address, diagnostics)
        if compiled is None:
            continue
        service_materialization, content_dependencies = compiled
        ordering_dependencies = [target_address, *content_dependencies]
        dependencies = _dedupe(ordering_dependencies)
        content_placements[address] = ContentPlacement(
            address=address,
            name=name,
            content_name=name,
            target_node=content.target,
            target_address=target_address,
            service_materialization=service_materialization,
            ordering_dependencies=dependencies,
            refresh_dependencies=dependencies,
            spec=_dump(content),
        )
    return content_placements


def _compile_service_materialization(
    scenario: InstantiatedScenario,
    content: Content,
    address: str,
    diagnostics: list[Diagnostic],
) -> (
    tuple[
        ServiceContentMaterializationBinding | ServiceSearchIndexSchemaMaterializationBinding | None,
        list[str],
    ]
    | None
):
    binding = content.service_materialization
    if binding is None:
        return None, []
    if isinstance(binding, DomainProfileBindingModel):
        # Preserve the authored binding in spec for exact profile admission;
        # only the two built-in contracts use the legacy compiled carrier.
        return None, []
    split = _resolve_node_service_ref(scenario, binding.target_service_ref)
    if split is None or split[0] != content.target:
        diagnostics.append(
            Diagnostic(
                code="provisioning.content-service-target-ref-unbound",
                domain="provisioning",
                address=address,
                message="Service materialization target does not resolve on the content target node.",
            )
        )
        return None
    node_name, service_name = split
    consumer_tenant_ref, mutable_state_owner, reset_generation_owner = _service_state_ownership(scenario, binding)
    requirements = binding.requirements
    common = {
        "target_service_address": _service_address(node_name, service_name),
        "interface_profile": binding.interface_profile,
        "profile_version": binding.profile_version,
        "content_type": content.type.value,
        "operation": requirements.operation,
        "conflict_policy": requirements.conflict_policy,
        "readback": requirements.readback,
        "canonical_content_digest": _canonical_content_digest(content),
        "shared_service_relationship_ref": binding.shared_service_relationship_ref,
        "consumer_tenant_ref": consumer_tenant_ref,
        "mutable_state_owner": mutable_state_owner,
        "reset_generation_owner": reset_generation_owner,
        "readback_assertion_addresses": tuple(_assertion_address(ref) for ref in binding.readback_assertion_refs),
        "evidence_requirement_refs": tuple(binding.evidence_requirement_refs),
        "observation_boundary_addresses": tuple(
            _observation_boundary_address(ref) for ref in binding.observation_boundary_refs
        ),
    }
    if isinstance(binding, ServiceSearchIndexSchemaMaterialization):
        field_semantics = {
            str(field_name): semantic.value for field_name, semantic in requirements.field_semantics.items()
        }
        compiled = ServiceSearchIndexSchemaMaterializationBinding(
            **common,
            field_semantics=field_semantics,
            canonical_field_schema_digest=_canonical_field_schema_digest(
                binding.interface_profile,
                binding.profile_version,
                field_semantics,
            ),
        )
    else:
        compiled = ServiceContentMaterializationBinding(**common)
    dependencies = [_content_address(ref) for ref in binding.ordering_content_refs]
    return compiled, dependencies


def _service_state_ownership(scenario: InstantiatedScenario, binding: object) -> tuple[str, str, str]:
    if not binding.shared_service_relationship_ref:
        return "", "", ""
    relationship_name = _section_ref_name(
        binding.shared_service_relationship_ref,
        "relationships",
        scenario.relationships,
    )
    relationship = scenario.relationships[relationship_name]
    detail = relationship.shared_service
    if detail is None:
        return "", "", ""
    consumer_tenant_ref = relationship.source.removeprefix("deployment_tenants.")
    mutable_state_owner = getattr(detail.mutable_state_owner, "value", str(detail.mutable_state_owner))
    reset_generation_owner = getattr(detail.reset_generation_owner, "value", str(detail.reset_generation_owner))
    return consumer_tenant_ref, mutable_state_owner, reset_generation_owner


def _canonical_content_digest(content: object) -> str:
    payload = _dump(content)
    payload.pop("service_materialization", None)
    return canonical_json_digest(payload)


def _canonical_field_schema_digest(
    interface_profile: str,
    profile_version: str,
    field_semantics: dict[str, str],
) -> str:
    return canonical_json_digest(
        {
            "interface_profile": interface_profile,
            "profile_version": profile_version,
            "projection_scope": "declared-fields",
            "field_semantics": field_semantics,
        }
    )


def _compile_account_placements(
    scenario: InstantiatedScenario,
    diagnostics: list[Diagnostic],
    domain_analysis: DomainTopologyAnalysis,
    domain_controller_placements: dict[str, DomainControllerPlacement],
) -> dict[str, AccountPlacement]:
    account_placements: dict[str, AccountPlacement] = {}
    controller_placements_by_domain: dict[str, list[str]] = {}
    for placement in domain_controller_placements.values():
        controller_placements_by_domain.setdefault(placement.domain_topology.domain_id, []).append(placement.address)
    for name, account in scenario.accounts.items():
        address = _account_address(name)
        target_address, target_diagnostics = _resolve_node_ref(
            scenario,
            ref_name=account.node,
            owner_address=address,
            domain="provisioning",
            code_prefix="provisioning.account-node-ref",
            node_label="account node",
            required_type=NodeType.COMPUTE,
        )
        diagnostics.extend(target_diagnostics)
        if target_address is None:
            continue
        account_domain_binding = domain_analysis.account_bindings.get(name)
        node_domain_binding = (
            domain_analysis.node_bindings.get(account_domain_binding.node_name)
            if account_domain_binding is not None
            else None
        )
        domain_topology = (
            _compiled_domain_binding(scenario, node_domain_binding) if node_domain_binding is not None else None
        )
        dependencies = _dedupe(
            [
                target_address,
                *(
                    controller_placements_by_domain.get(domain_topology.domain_id, ())
                    if domain_topology is not None
                    else ()
                ),
            ]
        )
        account_placements[address] = AccountPlacement(
            address=address,
            name=name,
            account_name=name,
            node_name=account.node,
            target_address=target_address,
            domain_topology=domain_topology,
            ordering_dependencies=dependencies,
            refresh_dependencies=dependencies,
            spec=_dump(account),
        )
    return account_placements


def _compile_domain_controller_placements(
    scenario: InstantiatedScenario,
    domain_analysis: DomainTopologyAnalysis,
) -> dict[str, DomainControllerPlacement]:
    placements: dict[str, DomainControllerPlacement] = {}
    for controller_node_name, binding in domain_analysis.node_bindings.items():
        if binding.role is not DomainNodeRole.CONTROLLER:
            continue
        address = _domain_controller_address(controller_node_name, binding.domain_name)
        target_address = _node_address(controller_node_name)
        placements[address] = DomainControllerPlacement(
            address=address,
            name=f"{controller_node_name}.{binding.domain_name}",
            target_address=target_address,
            domain_topology=_compiled_domain_binding(scenario, binding),
            ordering_dependencies=(target_address,),
            refresh_dependencies=(target_address,),
            spec={},
        )
    return placements
