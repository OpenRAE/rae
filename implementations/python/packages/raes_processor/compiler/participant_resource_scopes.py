"""DSL-121 scope and disclosure projection for authored participant resource budgets."""

from raes.participant_resource_budgets import disclosed_resource_budget_refs, tool_affordance_action_contracts
from raes.scenario import InstantiatedScenario

from .addresses import _action_contract_address, _section_ref_name


def tool_action_contract_addresses(
    scenario: InstantiatedScenario,
    behavior_spec: object,
    governed_actions: tuple[str, ...],
    tool_affordance_refs: list[str],
) -> tuple[str, ...]:
    """Return the governed action contracts a tool_invocations dimension counts.

    Validation and compilation share one scope rule, so the compiled scope is
    exactly the set of governed actions the validator checked.
    """

    addresses: set[str] = set()
    for affordance_id in tool_affordance_refs:
        scope = tool_affordance_action_contracts(
            behavior_spec, affordance_id, governed_actions, scenario.action_contracts
        )
        if not scope:
            raise ValueError("validated tool_invocations resource budget must bind a governed tool action")
        addresses.update(_action_contract_address(action_name) for action_name in scope)
    return tuple(sorted(addresses))


def disclosed_budget_refs(scenario: InstantiatedScenario, policy: object) -> frozenset[str]:
    """Budget dimension refs that the policy's observation boundary explicitly discloses."""

    boundary_name = _section_ref_name(
        str(policy.observation_boundary_ref),
        "observation_boundaries",
        scenario.observation_boundaries,
    )
    return disclosed_resource_budget_refs(scenario.observation_boundaries.get(boundary_name))


__all__ = ("disclosed_budget_refs", "tool_action_contract_addresses")
