"""Semantic validation for authored participant resource-budget owners."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ..semantics.participant_behavior import select_participants

_NODE_PREFIX = "nodes."
_TENANT_PREFIX = "deployment_tenants."


@dataclass(frozen=True)
class _OwnerScope:
    # Names a participant owner may use: the authored participant_refs, so an
    # unresolved template variable still names its owner, plus every governed
    # participant. Only declared governed participants are counted.
    participant_refs: set[str]
    governed_participants: set[str]
    deployment_tenants: Mapping[str, object]
    target_tenants: set[str]
    action_targets: set[str]
    declared_tenants: set[str]
    shared_permissions: set[tuple[str, str]]


def _action_targets(policy: object, action_contracts: Mapping[str, object]) -> set[str]:
    action_refs = tuple(getattr(policy, "action_order", ())) or tuple(
        getattr(candidate, "action_ref", "") for candidate in getattr(policy, "action_candidates", {}).values()
    )
    return {
        str(target)
        for action_ref in action_refs
        for effect in getattr(action_contracts.get(str(action_ref).removeprefix("action_contracts.")), "effects", ())
        for target in getattr(effect, "target_refs", ())
    }


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
    if kind == "participant":
        if ref.removeprefix("agents.") not in scope.participant_refs:
            error = f"{label} participant ref '{ref}' is outside the policy participant scope"
        elif len(scope.governed_participants) > 1:
            # The policy reserves one vector for every governed participant, so
            # this would be a policy-wide counter presented as participant-local.
            governed = ", ".join(sorted(scope.governed_participants))
            error = f"{label} participant ref '{ref}' would count every governed participant's use ({governed})"
    elif kind == "deployment_tenant":
        error = _tenant_owner_error(label, ref, scope)
    elif kind == "shared_service":
        error = _shared_service_owner_error(label, ref, scope, split_node_service_ref)
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


def participant_resource_budget_owner_errors(
    behavior_specifications: Mapping[str, object],
    action_contracts: Mapping[str, object],
    deployment_tenants: Mapping[str, object],
    deployment_cells: Mapping[str, object],
    relationships: Mapping[str, object],
    split_node_service_ref: Callable[[str], object | None],
    *,
    participant_roles: Mapping[str, str | None],
) -> tuple[str, ...]:
    """Return errors for resource owners outside their declared SDL scope.

    ``participant_roles`` maps every declared agent to its effective role, or
    ``None``. A policy governs the participants the compiler selects with it:
    the ``participant_refs`` that name declared agents and every agent whose
    effective role is in ``participant_role_refs``.
    """

    errors: list[str] = []
    for spec_name, behavior_spec in behavior_specifications.items():
        policy = getattr(behavior_spec, "autonomous_execution", None)
        budget = getattr(policy, "resource_budget", None)
        if budget is None:
            continue
        governed_participants = select_participants(behavior_spec, set(participant_roles), participant_roles)
        participant_refs = {str(ref).removeprefix("agents.") for ref in getattr(behavior_spec, "participant_refs", ())}
        action_targets = _action_targets(policy, action_contracts)
        target_tenants = _target_tenants(action_targets, deployment_cells)
        declared_tenants = {
            str(owner.ref).removeprefix(_TENANT_PREFIX)
            for owner in budget.owners.values()
            if getattr(owner.kind, "value", owner.kind) == "deployment_tenant"
        }
        shared_permissions = _shared_permissions(relationships)
        target_tenants.update(tenant for tenant, target in shared_permissions if target in action_targets)
        scope = _OwnerScope(
            participant_refs=participant_refs | governed_participants,
            governed_participants=governed_participants,
            deployment_tenants=deployment_tenants,
            target_tenants=target_tenants,
            action_targets=action_targets,
            declared_tenants=declared_tenants,
            shared_permissions=shared_permissions,
        )
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
