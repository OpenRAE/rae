"""Runtime-addressable reference index and initial-knowledge address resolution."""

from collections.abc import Callable, Iterable

from raes.nodes import NodeType
from raes.scenario import InstantiatedScenario

from .addresses import (
    _account_address,
    _action_contract_address,
    _behavior_specification_address,
    _content_address,
    _content_item_address,
    _observation_boundary_address,
    _outcome_interpretation_rule_address,
    _resolve_node_service_ref,
    _resource_address_for_node,
    _service_address,
    _template_address,
)
from .support import _dedupe


def _add_alias(index: dict[str, set[str]], alias: str, address: str) -> None:
    if alias:
        index.setdefault(alias, set()).add(address)


def _add_node_aliases(index: dict[str, set[str]], scenario: InstantiatedScenario) -> None:
    for node_name, node in scenario.nodes.items():
        address = _resource_address_for_node(scenario, node_name)
        _add_alias(index, node_name, address)
        _add_alias(index, f"nodes.{node_name}", address)
        if node.type == NodeType.SWITCH:
            _add_alias(index, f"infrastructure.{node_name}", address)

        for service in node.services:
            service_name = service.name
            if not service_name:
                continue
            service_address = _service_address(node_name, service_name)
            _add_alias(index, service_name, service_address)
            _add_alias(index, f"nodes.{node_name}.services.{service_name}", service_address)


def _add_infrastructure_aliases(index: dict[str, set[str]], scenario: InstantiatedScenario) -> None:
    for infra_name in scenario.infrastructure:
        node = scenario.nodes.get(infra_name)
        if node is None:
            continue
        address = _resource_address_for_node(scenario, infra_name)
        _add_alias(index, f"infrastructure.{infra_name}", address)
        if node.type == NodeType.SWITCH:
            _add_alias(index, infra_name, address)


def _add_content_aliases(index: dict[str, set[str]], scenario: InstantiatedScenario) -> None:
    for content_name, content in scenario.content.items():
        content_address = _content_address(content_name)
        _add_alias(index, content_name, content_address)
        _add_alias(index, f"content.{content_name}", content_address)
        for item in content.items:
            if not item.name:
                continue
            item_address = _content_item_address(content_name, item.name)
            _add_alias(index, item.name, item_address)
            _add_alias(index, f"content.{content_name}.items.{item.name}", item_address)


def _add_qualified_aliases(
    index: dict[str, set[str]],
    names: Iterable[str],
    *,
    address_for: Callable[[str], str],
    qualified_prefix: str,
) -> None:
    for name in names:
        address = address_for(name)
        _add_alias(index, name, address)
        _add_alias(index, f"{qualified_prefix}.{name}", address)


def _runtime_addressable_ref_index(scenario: InstantiatedScenario) -> dict[str, set[str]]:
    """Map SDL authority/scope refs to compiled runtime addresses.

    This deliberately omits semantic-only anchors such as entities and
    relationships. The raw refs stay on participant runtime records; only
    refs backed by runtime-addressable surfaces become addresses/dependencies.
    """
    index: dict[str, set[str]] = {}
    _add_node_aliases(index, scenario)
    _add_infrastructure_aliases(index, scenario)
    _add_content_aliases(index, scenario)
    _add_qualified_aliases(
        index,
        scenario.accounts,
        address_for=_account_address,
        qualified_prefix="accounts",
    )
    _add_qualified_aliases(
        index,
        scenario.conditions,
        address_for=lambda name: _template_address("condition", name),
        qualified_prefix="conditions",
    )
    _add_qualified_aliases(
        index,
        scenario.features,
        address_for=lambda name: _template_address("feature", name),
        qualified_prefix="features",
    )
    _add_qualified_aliases(
        index,
        scenario.action_contracts,
        address_for=_action_contract_address,
        qualified_prefix="action_contracts",
    )
    _add_qualified_aliases(
        index,
        scenario.observation_boundaries,
        address_for=_observation_boundary_address,
        qualified_prefix="observation_boundaries",
    )
    _add_qualified_aliases(
        index,
        scenario.outcome_interpretation_rules,
        address_for=_outcome_interpretation_rule_address,
        qualified_prefix="outcome_interpretation_rules",
    )
    _add_qualified_aliases(
        index,
        scenario.behavior_specifications,
        address_for=_behavior_specification_address,
        qualified_prefix="behavior_specifications",
    )
    return index


def _runtime_addresses_for_refs(
    refs: list[str],
    *,
    addressable_ref_index: dict[str, set[str]],
) -> tuple[str, ...]:
    addresses: list[str] = []
    for ref in dict.fromkeys(refs):
        matches = addressable_ref_index.get(ref, ())
        if len(matches) == 1:
            addresses.extend(matches)
    return _dedupe(addresses)


def _account_addresses_for_refs(scenario: InstantiatedScenario, refs: list[str]) -> tuple[str, ...]:
    addresses: list[str] = []
    for ref in dict.fromkeys(refs):
        if ref in scenario.accounts:
            addresses.append(_account_address(ref))
    return _dedupe(addresses)


def _service_addresses_for_refs(scenario: InstantiatedScenario, refs: list[str]) -> tuple[str, ...]:
    addresses: list[str] = []
    for ref in dict.fromkeys(refs):
        split = _resolve_node_service_ref(scenario, ref)
        if split is not None:
            node_name, service_name = split
            node = scenario.nodes.get(node_name)
            if node is None:
                continue
            if any(service.name == service_name for service in node.services):
                addresses.append(_service_address(node_name, service_name))
            continue
        for node_name, node in scenario.nodes.items():
            if any(service.name == ref for service in node.services):
                addresses.append(_service_address(node_name, ref))
    return _dedupe(addresses)


def _initial_knowledge_values(initial_knowledge: object, attribute: str) -> tuple[object, ...]:
    return tuple(getattr(initial_knowledge, attribute, ()) or ())


def _initial_knowledge_host_addresses(
    scenario: InstantiatedScenario,
    initial_knowledge: object,
) -> list[str]:
    addresses: list[str] = []
    for host in _initial_knowledge_values(initial_knowledge, "hosts"):
        if host in scenario.nodes:
            addresses.append(_resource_address_for_node(scenario, str(host)))
    return addresses


def _initial_knowledge_subnet_addresses(
    scenario: InstantiatedScenario,
    initial_knowledge: object,
) -> list[str]:
    addresses: list[str] = []
    for subnet in _initial_knowledge_values(initial_knowledge, "subnets"):
        if subnet in scenario.infrastructure and subnet in scenario.nodes:
            addresses.append(_resource_address_for_node(scenario, str(subnet)))
    return addresses


def _initial_knowledge_service_addresses(
    scenario: InstantiatedScenario,
    initial_knowledge: object,
) -> tuple[str, ...]:
    return _service_addresses_for_refs(
        scenario,
        [str(service) for service in _initial_knowledge_values(initial_knowledge, "services")],
    )


def _initial_knowledge_account_addresses(
    scenario: InstantiatedScenario,
    initial_knowledge: object,
) -> tuple[str, ...]:
    return _account_addresses_for_refs(
        scenario,
        [str(account) for account in _initial_knowledge_values(initial_knowledge, "accounts")],
    )


def _initial_knowledge_addresses(
    scenario: InstantiatedScenario,
    initial_knowledge: object | None,
) -> tuple[str, ...]:
    if initial_knowledge is None:
        return ()
    addresses: list[str] = []
    addresses.extend(_initial_knowledge_host_addresses(scenario, initial_knowledge))
    addresses.extend(_initial_knowledge_subnet_addresses(scenario, initial_knowledge))
    addresses.extend(_initial_knowledge_service_addresses(scenario, initial_knowledge))
    addresses.extend(_initial_knowledge_account_addresses(scenario, initial_knowledge))
    return _dedupe(addresses)
