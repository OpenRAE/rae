"""Section-level reference rewriters for module composition.

Foundational, proposition, narrative, observation, content, stateful-resource,
account/identity, deployment, and relationship sections, plus module-descriptor
export validation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .._errors import SDLParseError
from .._identifiers import QualifiedName
from .._module_symbols import FORWARDING_AGENTS_SECTION
from .._module_symbols import HASHMAP_SECTIONS as _HASHMAP_SECTIONS
from ..entities import flatten_entities
from ..scenario import ModuleDescriptor, ScenarioContent
from ._references import (
    _maybe_rename,
    _rewrite_node_or_service_ref,
    _rewrite_section_ref,
    _rewrite_stateful_dependency_ref,
)


def _validate_descriptor_exports(
    scenario: ScenarioContent,
    descriptor: ModuleDescriptor,
) -> None:
    for section_name, exported_names in descriptor.exports.items():
        if section_name not in {*_HASHMAP_SECTIONS, FORWARDING_AGENTS_SECTION}:
            raise SDLParseError(f"Module '{descriptor.id}' exports unknown SDL section '{section_name}'")
        for exported_name in exported_names:
            QualifiedName.parse(exported_name)
        if section_name == FORWARDING_AGENTS_SECTION:
            available_names = {agent.forwarding_agent_id for agent in scenario.forwarding_agents}
        elif section_name == "entities":
            available_names = set(flatten_entities(scenario.entities))
        else:
            section_payload = getattr(scenario, section_name, None)
            available_names = set(section_payload.keys()) if isinstance(section_payload, Mapping) else set()
        undefined = sorted(set(exported_names) - available_names)
        if undefined:
            raise SDLParseError(f"Module '{descriptor.id}' exports undefined {section_name}: " + ", ".join(undefined))


def _rewrite_node_named_mappings(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for section in ("features", "conditions", "injects"):
        payload[section] = {
            _maybe_rename(name, symbols[section]): role for name, role in payload.get(section, {}).items()
        }


def _rewrite_node_role_entities(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for role in payload.get("roles", {}).values():
        if isinstance(role, dict):
            role["entities"] = [_maybe_rename(name, symbols["entities"]) for name in role.get("entities", [])]


def _rewrite_node_network_namespace(
    runtime: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    container = runtime.get("container")
    namespaces = container.get("namespaces") if isinstance(container, dict) else None
    network = namespaces.get("network") if isinstance(namespaces, dict) else None
    if isinstance(network, dict) and network.get("target_node_ref"):
        network["target_node_ref"] = _rewrite_section_ref(
            str(network["target_node_ref"]),
            "nodes",
            symbols["nodes"],
        )


def _rewrite_generated_environment_sources(
    runtime: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for collection_name in ("environment", "environment_files"):
        for entry in runtime.get(collection_name, []):
            source = entry.get("value_from") if isinstance(entry, dict) else None
            if isinstance(source, dict) and source.get("generated_artifact"):
                source["generated_artifact"] = _rewrite_section_ref(
                    str(source["generated_artifact"]),
                    "generated_artifacts",
                    symbols["generated_artifacts"],
                )


def _rewrite_node(payload: dict[str, Any], symbols: dict[str, dict[str, str] | set[str]]) -> None:
    _rewrite_node_named_mappings(payload, symbols)
    _rewrite_node_role_entities(payload, symbols)
    runtime = payload.get("runtime")
    if isinstance(runtime, dict):
        _rewrite_node_network_namespace(runtime, symbols)
        _rewrite_generated_environment_sources(runtime, symbols)


def _rewrite_infrastructure(payload: dict[str, Any], symbols: dict[str, dict[str, str] | set[str]]) -> None:
    payload["dependencies"] = [_maybe_rename(name, symbols["named"]) for name in payload.get("dependencies", [])]
    payload["links"] = [_maybe_rename(name, symbols["named"]) for name in payload.get("links", [])]
    properties = payload.get("properties")
    if isinstance(properties, list):
        rewritten: list[dict[str, Any]] = []
        for item in properties:
            if isinstance(item, dict):
                rewritten.append({_maybe_rename(name, symbols["named"]): value for name, value in item.items()})
            else:
                rewritten.append(item)
        payload["properties"] = rewritten


def _rewrite_feature(payload: dict[str, Any], symbols: dict[str, dict[str, str] | set[str]]) -> None:
    payload["dependencies"] = [_maybe_rename(name, symbols["features"]) for name in payload.get("dependencies", [])]


def _rewrite_entity(payload: dict[str, Any], symbols: dict[str, dict[str, str] | set[str]]) -> None:
    payload["events"] = [_maybe_rename(name, symbols["events"]) for name in payload.get("events", [])]
    for child in payload.get("entities", {}).values():
        if isinstance(child, dict):
            _rewrite_entity(child, symbols)


def _rewrite_foundational_sections(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for node in payload.get("nodes", {}).values():
        if isinstance(node, dict):
            _rewrite_node(node, symbols)
    for infrastructure in payload.get("infrastructure", {}).values():
        if isinstance(infrastructure, dict):
            _rewrite_infrastructure(infrastructure, symbols)
    for feature in payload.get("features", {}).values():
        if isinstance(feature, dict):
            _rewrite_feature(feature, symbols)
    for entity in payload.get("entities", {}).values():
        if isinstance(entity, dict):
            _rewrite_entity(entity, symbols)


def _rewrite_proposition_sections(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for condition in payload.get("conditions", {}).values():
        if isinstance(condition, dict) and condition.get("proposition"):
            condition["proposition"] = _maybe_rename(str(condition["proposition"]), symbols["propositions"])
    for proposition in payload.get("propositions", {}).values():
        if isinstance(proposition, dict):
            proposition["subjects"] = [
                _maybe_rename(name, symbols["named"]) for name in proposition.get("subjects", [])
            ]
            proposition["evidence_requirements"] = [
                _maybe_rename(name, symbols["evidence_requirements"])
                for name in proposition.get("evidence_requirements", [])
            ]
    for assertion in payload.get("assertions", {}).values():
        if isinstance(assertion, dict) and assertion.get("proposition"):
            assertion["proposition"] = _maybe_rename(str(assertion["proposition"]), symbols["propositions"])


def _rewrite_narrative_sections(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for inject in payload.get("injects", {}).values():
        if isinstance(inject, dict):
            if inject.get("from_entity"):
                inject["from_entity"] = _maybe_rename(str(inject["from_entity"]), symbols["entities"])
            inject["to_entities"] = [_maybe_rename(name, symbols["entities"]) for name in inject.get("to_entities", [])]
    for event in payload.get("events", {}).values():
        if isinstance(event, dict):
            event["assertions"] = [_maybe_rename(name, symbols["assertions"]) for name in event.get("assertions", [])]
            event["injects"] = [_maybe_rename(name, symbols["injects"]) for name in event.get("injects", [])]
    for script in payload.get("scripts", {}).values():
        if isinstance(script, dict):
            script["events"] = {
                _maybe_rename(name, symbols["events"]): value for name, value in script.get("events", {}).items()
            }
    for story in payload.get("stories", {}).values():
        if isinstance(story, dict):
            story["scripts"] = [_maybe_rename(name, symbols["scripts"]) for name in story.get("scripts", [])]


def _rewrite_observation_boundaries(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
    tool_affordance_refs: Mapping[str, str],
) -> None:
    for boundary in payload.get("observation_boundaries", {}).values():
        if not isinstance(boundary, dict):
            continue
        for field_name in ("observable_refs", "hidden_refs", "evidence_refs"):
            boundary[field_name] = [
                tool_affordance_refs.get(ref, _maybe_rename(ref, symbols["named"]))
                for ref in boundary.get(field_name, [])
            ]
        for field_name in ("view_rules", "view_transitions"):
            for item in boundary.get(field_name, []):
                if isinstance(item, dict) and isinstance(item.get("information_ref"), str):
                    information_ref = item["information_ref"]
                    item["information_ref"] = tool_affordance_refs.get(
                        information_ref,
                        _maybe_rename(information_ref, symbols["named"]),
                    )


def _rewrite_service_materialization(
    materialization: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    if materialization.get("target_service_ref"):
        materialization["target_service_ref"] = _rewrite_node_or_service_ref(
            str(materialization["target_service_ref"]),
            symbols["nodes"],
        )
    if materialization.get("shared_service_relationship_ref"):
        materialization["shared_service_relationship_ref"] = _rewrite_section_ref(
            str(materialization["shared_service_relationship_ref"]),
            "relationships",
            symbols["relationships"],
        )
    for field_name, section_name in (
        ("ordering_content_refs", "content"),
        ("readback_assertion_refs", "assertions"),
        ("evidence_requirement_refs", "evidence_requirements"),
        ("observation_boundary_refs", "observation_boundaries"),
    ):
        materialization[field_name] = [
            _rewrite_section_ref(reference, section_name, symbols[section_name])
            for reference in materialization.get(field_name, [])
        ]


def _rewrite_content_sections(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for content in payload.get("content", {}).values():
        if not isinstance(content, dict):
            continue
        if content.get("target"):
            content["target"] = _rewrite_section_ref(str(content["target"]), "nodes", symbols["nodes"])
        materialization = content.get("service_materialization")
        if isinstance(materialization, dict):
            _rewrite_service_materialization(materialization, symbols)


def _rewrite_resource_consumers(
    resource: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for consumer in resource.get("consumers", []):
        if isinstance(consumer, dict) and consumer.get("node"):
            consumer["node"] = _maybe_rename(str(consumer["node"]), symbols["nodes"])


def _rewrite_resource_dependencies(
    resource: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
    *,
    owner: str,
) -> None:
    for dependency_field in ("ordering_dependencies", "refresh_dependencies"):
        resource[dependency_field] = [
            _rewrite_stateful_dependency_ref(reference, symbols, owner=owner)
            for reference in resource.get(dependency_field, [])
        ]


def _rewrite_stateful_resource(
    resource: object,
    symbols: dict[str, dict[str, str] | set[str]],
    *,
    owner: str,
) -> None:
    if isinstance(resource, dict):
        _rewrite_resource_consumers(resource, symbols)
        _rewrite_resource_dependencies(resource, symbols, owner=owner)


def _rewrite_stateful_resources(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for section_name in ("generated_artifacts", "persistent_volumes"):
        for resource_name, resource in payload.get(section_name, {}).items():
            _rewrite_stateful_resource(resource, symbols, owner=f"{section_name}.{resource_name}")


def _rewrite_account(
    account: object,
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    if not isinstance(account, dict):
        return
    if account.get("node"):
        account["node"] = _maybe_rename(str(account["node"]), symbols["nodes"])
    if account.get("domain_ref"):
        account["domain_ref"] = _maybe_rename(str(account["domain_ref"]), symbols["identity_domains"])


def _rewrite_identity_domain(
    domain: object,
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    if isinstance(domain, dict) and domain.get("authority_account_ref"):
        domain["authority_account_ref"] = _maybe_rename(
            str(domain["authority_account_ref"]),
            symbols["accounts"],
        )


def _rewrite_identity_forest(
    forest: object,
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    if not isinstance(forest, dict):
        return
    if forest.get("root_domain_ref"):
        forest["root_domain_ref"] = _maybe_rename(
            str(forest["root_domain_ref"]),
            symbols["identity_domains"],
        )
    forest["domain_refs"] = [_maybe_rename(name, symbols["identity_domains"]) for name in forest.get("domain_refs", [])]


def _rewrite_account_and_domain_sections(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for account in payload.get("accounts", {}).values():
        _rewrite_account(account, symbols)
    for domain in payload.get("identity_domains", {}).values():
        _rewrite_identity_domain(domain, symbols)
    for forest in payload.get("identity_forests", {}).values():
        _rewrite_identity_forest(forest, symbols)


def _rewrite_deployment_sections(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for facade in payload.get("identity_facades", {}).values():
        if isinstance(facade, dict) and facade.get("service_ref"):
            facade["service_ref"] = _maybe_rename(str(facade["service_ref"]), symbols["named"])
    for cell in payload.get("deployment_cells", {}).values():
        if not isinstance(cell, dict):
            continue
        if cell.get("tenant_ref"):
            cell["tenant_ref"] = _maybe_rename(str(cell["tenant_ref"]), symbols["deployment_tenants"])
        cell["node_refs"] = [_maybe_rename(name, symbols["nodes"]) for name in cell.get("node_refs", [])]


def _rewrite_relationship_sections(
    payload: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for relationship in payload.get("relationships", {}).values():
        if not isinstance(relationship, dict):
            continue
        if relationship.get("source"):
            relationship["source"] = _maybe_rename(str(relationship["source"]), symbols["named"])
        if relationship.get("target"):
            relationship["target"] = _maybe_rename(str(relationship["target"]), symbols["named"])
        domain_join = relationship.get("domain_join")
        if isinstance(domain_join, dict):
            domain_join["controller_refs"] = [
                _maybe_rename(name, symbols["nodes"]) for name in domain_join.get("controller_refs", [])
            ]
        shared_service = relationship.get("shared_service")
        if isinstance(shared_service, dict):
            shared_service["mutable_state_refs"] = [
                _maybe_rename(name, symbols["persistent_volumes"])
                for name in shared_service.get("mutable_state_refs", [])
            ]
        forwarding_edge = relationship.get("forwarding_edge")
        if isinstance(forwarding_edge, dict) and forwarding_edge.get("forwarder_ref"):
            forwarding_edge["forwarder_ref"] = _maybe_rename(
                str(forwarding_edge["forwarder_ref"]),
                symbols[FORWARDING_AGENTS_SECTION],
            )
