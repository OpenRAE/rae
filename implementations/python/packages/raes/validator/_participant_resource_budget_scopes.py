"""Semantic validation for DSL-121 resource-budget tool scopes and quota disclosure."""

from collections.abc import Callable, Mapping

from ..participant_resource_budgets import (
    is_resource_budget_dimension_reference,
    is_resource_budget_view_rule,
    resource_budget_dimension_reference,
    tool_affordance_action_contracts,
)
from ..scenario import ScenarioContent
from ..semantics._domain_topology_types import resolve_section_ref
from ._participant_resource_budget_owners import participant_resource_budget_owner_errors

_BUDGET_DISPOSITIONS = frozenset({"hidden", "disclosed"})


def _value(item: object) -> str:
    return str(getattr(item, "value", item))


def _tool_scope_errors(
    spec_name: str,
    behavior_spec: object,
    policy: object,
    budget: object,
    action_contracts: Mapping[str, object],
) -> list[str]:
    errors: list[str] = []
    for budget_id, dimension in budget.dimensions.items():
        for affordance_id in dimension.tool_affordance_refs:
            label = (
                f"Behavior specification '{spec_name}' resource-budget dimension '{budget_id}' "
                f"tool_affordance_ref '{affordance_id}'"
            )
            scope = tool_affordance_action_contracts(behavior_spec, policy, str(affordance_id), action_contracts)
            if scope is None:
                errors.append(f"{label} does not name a tool affordance of the behavior specification")
            elif not scope:
                errors.append(f"{label} binds no action contract the autonomous policy dispatches")
    return errors


def _governed_budget_refs(
    behavior_specifications: Mapping[str, object],
    observation_boundaries: Mapping[str, object],
) -> dict[str, set[str]]:
    """Budget dimension refs keyed by the observation boundary of the policy that governs them."""

    governed: dict[str, set[str]] = {}
    for spec_name, behavior_spec in behavior_specifications.items():
        policy = getattr(behavior_spec, "autonomous_execution", None)
        budget = getattr(policy, "resource_budget", None)
        boundary = resolve_section_ref(
            str(getattr(policy, "observation_boundary_ref", "")),
            "observation_boundaries",
            observation_boundaries,
        )
        if budget is None or boundary is None:
            continue
        governed.setdefault(boundary, set()).update(
            resource_budget_dimension_reference(str(spec_name), str(budget_id)) for budget_id in budget.dimensions
        )
    return governed


def _view_rule_error(label: str, rule: object, governed: set[str], hidden: set[str]) -> str | None:
    ref = str(rule.information_ref)
    budget_class = is_resource_budget_view_rule(rule)
    error = None
    if budget_class != is_resource_budget_dimension_reference(ref):
        error = f"{label} view_rule '{ref}' must pair the resource_budget class with a resource-budget dimension ref"
    elif budget_class and ref not in governed:
        error = f"{label} resource_budget view_rule '{ref}' does not name a dimension governed through this boundary"
    elif budget_class and _value(rule.disposition) not in _BUDGET_DISPOSITIONS:
        error = f"{label} resource_budget view_rule '{ref}' must be hidden or disclosed"
    elif budget_class and ref not in hidden:
        error = f"{label} resource_budget view_rule '{ref}' must declare its dimension in hidden_refs"
    return error


def _visibility_errors(boundary_name: str, boundary: object, governed: set[str]) -> list[str]:
    label = f"Observation boundary '{boundary_name}'"
    errors = [
        f"{label} exposes resource budget '{ref}' as observable; a quota is disclosed only through a "
        "resource_budget view rule"
        for ref in getattr(boundary, "observable_refs", [])
        if is_resource_budget_dimension_reference(str(ref))
    ]
    hidden = {str(ref) for ref in getattr(boundary, "hidden_refs", [])}
    errors.extend(
        error
        for rule in getattr(boundary, "view_rules", [])
        if (error := _view_rule_error(label, rule, governed, hidden)) is not None
    )
    errors.extend(
        f"{label} view_transition '{transition.transition_id}' cannot change a resource-budget disclosure"
        for transition in getattr(boundary, "view_transitions", [])
        if is_resource_budget_dimension_reference(str(transition.information_ref))
    )
    return errors


def participant_resource_budget_scope_errors(
    behavior_specifications: Mapping[str, object],
    observation_boundaries: Mapping[str, object],
    action_contracts: Mapping[str, object],
) -> tuple[str, ...]:
    """Return errors for unbound tool-use scopes and quota disclosure outside an explicit view rule."""

    errors: list[str] = []
    for spec_name, behavior_spec in behavior_specifications.items():
        policy = getattr(behavior_spec, "autonomous_execution", None)
        budget = getattr(policy, "resource_budget", None)
        if budget is not None:
            errors.extend(_tool_scope_errors(str(spec_name), behavior_spec, policy, budget, action_contracts))
    governed = _governed_budget_refs(behavior_specifications, observation_boundaries)
    for boundary_name, boundary in observation_boundaries.items():
        errors.extend(_visibility_errors(str(boundary_name), boundary, governed.get(str(boundary_name), set())))
    return tuple(errors)


def participant_resource_budget_errors(
    scenario: ScenarioContent,
    participant_roles: Mapping[str, str],
    split_node_service_ref: Callable[[str], object | None],
) -> tuple[str, ...]:
    """Return the owner errors, then the tool-scope and disclosure errors, of every resource budget.

    ``participant_roles`` maps each agent that has an effective role to that role.
    """

    return participant_resource_budget_owner_errors(
        scenario.behavior_specifications,
        scenario.action_contracts,
        scenario.deployment_tenants,
        scenario.deployment_cells,
        scenario.relationships,
        split_node_service_ref,
        participant_roles=dict.fromkeys(scenario.agents) | dict(participant_roles),
    ) + participant_resource_budget_scope_errors(
        scenario.behavior_specifications, scenario.observation_boundaries, scenario.action_contracts
    )


__all__ = ["participant_resource_budget_errors", "participant_resource_budget_scope_errors"]
