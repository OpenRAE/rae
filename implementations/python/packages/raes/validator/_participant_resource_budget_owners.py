"""Semantic validation for authored participant resource-budget owners."""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass

from .._base import is_variable_ref
from ..participant_resource_budgets import dispatched_action_contracts, specification_action_contracts
from ..scenario import ScenarioContent
from ..semantics.participant_behavior import select_participants

_NODE_PREFIX = "nodes."
_TENANT_PREFIX = "deployment_tenants."


@dataclass(frozen=True)
class _OwnerScope:
    # Names a participant owner may use: the authored participant_refs plus
    # every governed participant. Only the governed participants are counted,
    # and they are None until participant variables resolve; instantiation
    # validates again.
    participant_refs: set[str]
    governed_participants: set[str] | None
    deployment_tenants: Mapping[str, object]
    target_tenants: set[str]
    action_targets: set[str]
    declared_tenants: set[str]
    shared_permissions: set[tuple[str, str]]


def _action_targets(action_keys: tuple[str, ...], action_contracts: Mapping[str, object]) -> set[str]:
    return {
        str(target)
        for action_key in action_keys
        for effect in getattr(action_contracts.get(action_key), "effects", ())
        for target in getattr(effect, "target_refs", ())
    }


def _governed_budgets(
    behavior_specifications: Mapping[str, object],
    action_contracts: Mapping[str, object],
) -> Iterator[tuple[str, object, object, tuple[str, ...]]]:
    """Yield each authored budget with the actions it governs.

    A v3 autonomous budget governs the actions its policy dispatches; an
    ACT-624 aggregate budget governs the actions its specification declares.
    """

    for spec_name, behavior_spec in behavior_specifications.items():
        policy = getattr(behavior_spec, "autonomous_execution", None)
        autonomous_budget = getattr(policy, "resource_budget", None)
        if autonomous_budget is not None:
            yield (
                str(spec_name),
                behavior_spec,
                autonomous_budget,
                dispatched_action_contracts(policy, action_contracts),
            )
        aggregate_budget = getattr(behavior_spec, "resource_budget", None)
        if aggregate_budget is not None:
            yield (
                str(spec_name),
                behavior_spec,
                aggregate_budget,
                specification_action_contracts(behavior_spec, action_contracts),
            )


def _target_tenants(action_targets: set[str], deployment_cells: Mapping[str, object]) -> set[str]:
    target_nodes = {
        target.removeprefix(_NODE_PREFIX).split(".services.", 1)[0]
        for target in action_targets
        if target.startswith(_NODE_PREFIX)
    }
    return {
        str(getattr(cell, "tenant_ref", "")).removeprefix(_TENANT_PREFIX)
        for cell in deployment_cells.values()
        if target_nodes & {str(node_ref).removeprefix(_NODE_PREFIX) for node_ref in getattr(cell, "node_refs", ())}
    }


def _shared_permissions(relationships: Mapping[str, object]) -> set[tuple[str, str]]:
    return {
        (
            str(getattr(relationship, "source", "")).removeprefix(_TENANT_PREFIX),
            str(getattr(relationship, "target", "")),
        )
        for relationship in relationships.values()
        if getattr(getattr(relationship, "type", ""), "value", getattr(relationship, "type", ""))
        == "uses_shared_service"
    }


def _owner_scope(
    scenario: ScenarioContent,
    behavior_spec: object,
    budget: object,
    governed: set[str] | None,
    governed_actions: tuple[str, ...],
) -> _OwnerScope:
    action_targets = _action_targets(governed_actions, scenario.action_contracts)
    target_tenants = _target_tenants(action_targets, scenario.deployment_cells)
    shared_permissions = _shared_permissions(scenario.relationships)
    target_tenants.update(tenant for tenant, target in shared_permissions if target in action_targets)
    authored = {str(ref).removeprefix("agents.") for ref in getattr(behavior_spec, "participant_refs", ())}
    return _OwnerScope(
        participant_refs=authored | (governed or set()),
        governed_participants=governed,
        deployment_tenants=scenario.deployment_tenants,
        target_tenants=target_tenants,
        action_targets=action_targets,
        declared_tenants={
            str(owner.ref).removeprefix(_TENANT_PREFIX)
            for owner in budget.owners.values()
            if getattr(owner.kind, "value", owner.kind) == "deployment_tenant"
        },
        shared_permissions=shared_permissions,
    )


def _owner_error(
    owner: object,
    *,
    label: str,
    scope: _OwnerScope,
    split_node_service_ref: Callable[[str], object | None],
) -> str | None:
    kind = getattr(getattr(owner, "kind", ""), "value", getattr(owner, "kind", ""))
    ref = str(getattr(owner, "ref", ""))
    error = None
    if kind == "participant" and scope.governed_participants is not None:
        error = _participant_owner_error(label, ref, scope.participant_refs, scope.governed_participants)
    elif kind == "deployment_tenant":
        error = _tenant_owner_error(label, ref, scope)
    elif kind == "shared_service":
        error = _shared_service_owner_error(label, ref, scope, split_node_service_ref)
    return error


def _participant_owner_error(label: str, ref: str, names: set[str], governed: set[str]) -> str | None:
    error = None
    if ref.removeprefix("agents.") not in names:
        error = f"{label} participant ref '{ref}' is outside the policy participant scope"
    elif len(governed) > 1:
        # The policy reserves one vector for every governed participant, so
        # this would be a policy-wide counter presented as participant-local.
        listed = ", ".join(sorted(governed))
        error = f"{label} participant ref '{ref}' would count every governed participant's use ({listed})"
    return error


def _tenant_owner_error(label: str, ref: str, scope: _OwnerScope) -> str | None:
    tenant_ref = ref.removeprefix(_TENANT_PREFIX)
    error = None
    if tenant_ref not in scope.deployment_tenants:
        error = f"{label} deployment tenant ref '{ref}' is undefined"
    elif tenant_ref not in scope.target_tenants:
        error = f"{label} deployment tenant ref '{ref}' does not own an authorized action target"
    return error


def _shared_service_owner_error(
    label: str,
    ref: str,
    scope: _OwnerScope,
    split_node_service_ref: Callable[[str], object | None],
) -> str | None:
    error = None
    if split_node_service_ref(ref) is None:
        error = f"{label} shared service ref '{ref}' is undefined"
    elif ref not in scope.action_targets:
        error = f"{label} shared service ref '{ref}' is not an exact execution target"
    elif not any((tenant, ref) in scope.shared_permissions for tenant in scope.declared_tenants):
        error = f"{label} shared service ref '{ref}' lacks an authorized tenant uses_shared_service edge"
    return error


def _selected_participants(
    behavior_spec: object,
    participant_names: set[str],
    participant_roles: Mapping[str, str],
) -> set[str] | None:
    """Select participants as the compiler does, or ``None`` while a participant or role ref is a variable."""

    refs = (*getattr(behavior_spec, "participant_refs", ()), *getattr(behavior_spec, "participant_role_refs", ()))
    if any(is_variable_ref(ref) for ref in refs):
        return None
    return select_participants(behavior_spec, participant_names, participant_roles)


def _second_budget_errors(spec_name: str, participants: set[str], budgeted_by: dict[str, str]) -> list[str]:
    """Record the budget that governs each participant; a second one would govern its attempts twice."""

    errors: list[str] = []
    for participant in sorted(participants):
        prior = budgeted_by.setdefault(participant, spec_name)
        if prior != spec_name:
            errors.append(
                f"Behavior specification '{spec_name}' resource budget governs participant '{participant}', "
                f"which behavior specification '{prior}' already budgets; an attempt has one governing budget"
            )
    return errors


def participant_resource_budget_owner_errors(
    scenario: ScenarioContent,
    participant_roles: Mapping[str, str],
    split_node_service_ref: Callable[[str], object | None],
) -> tuple[str, ...]:
    """Return errors for resource owners outside their SDL scope and for participants two budgets govern.

    A budget governs the participants its specification selects the way the
    compiler selects them: its ``participant_refs`` that name declared agents and
    every agent whose effective role is one of its ``participant_role_refs``.
    ``participant_roles`` maps each agent that has an effective role to that
    role. While a participant or role ref is a variable, the participant checks
    wait for instantiation, which validates the resolved scenario again.
    """

    errors: list[str] = []
    budgeted_by: dict[str, str] = {}
    participant_names = {str(name) for name in scenario.agents}
    for spec_name, behavior_spec, budget, governed_actions in _governed_budgets(
        scenario.behavior_specifications, scenario.action_contracts
    ):
        governed = _selected_participants(behavior_spec, participant_names, participant_roles)
        if governed is not None:
            errors.extend(_second_budget_errors(spec_name, governed, budgeted_by))
        scope = _owner_scope(scenario, behavior_spec, budget, governed, governed_actions)
        for owner_id, owner in budget.owners.items():
            label = f"Behavior specification '{spec_name}' resource-budget owner '{owner_id}'"
            error = _owner_error(
                owner,
                label=label,
                scope=scope,
                split_node_service_ref=split_node_service_ref,
            )
            if error is not None:
                errors.append(error)
    return tuple(errors)


__all__ = ["participant_resource_budget_owner_errors"]
