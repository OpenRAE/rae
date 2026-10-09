"""Projection of authored ADR-097 budget policies into the canonical runtime demand.

A v3 autonomous budget and an ACT-624 aggregate interaction budget share this
projection, so both compile into the same owner, demand, and fairness IR.
"""

from collections.abc import Callable

from raes.participant_resource_budgets import specification_action_contracts
from raes.scenario import InstantiatedScenario

from ..models import (
    ParticipantInteractionBudgetRuntime,
    ParticipantResourceDemandRuntime,
    ParticipantResourceFairnessRuntime,
    ParticipantResourceOwnerRuntime,
)
from .addresses import (
    _behavior_specification_address,
    _resolve_node_service_ref,
    _section_ref_name,
)
from .participant_resource_scopes import tool_action_contract_addresses
from .support import _address

ProjectedResourceBudget = tuple[
    tuple[ParticipantResourceOwnerRuntime, ...],
    tuple[ParticipantResourceDemandRuntime, ...],
    ParticipantResourceFairnessRuntime,
]


def _resource_owner_address(
    scenario: InstantiatedScenario,
    *,
    kind: str,
    ref: str,
    participant_addresses: tuple[str, ...],
) -> str:
    if kind == "participant":
        matching = tuple(address for address in participant_addresses if address.endswith(f".{ref}"))
        if len(matching) != 1:
            raise ValueError("participant resource owner must resolve to one policy participant")
        address = matching[0]
    elif kind == "deployment_tenant":
        name = _section_ref_name(ref, "deployment_tenants", scenario.deployment_tenants)
        address = _address("deployment", "tenant", name)
    elif kind == "shared_service":
        resolved = _resolve_node_service_ref(scenario, ref)
        if resolved is None:
            raise ValueError("shared-service resource owner must resolve to one node service")
        address = _address("provision", "node", resolved[0], "service", resolved[1])
    else:
        address = ref
    return address


def project_resource_budget(
    scenario: InstantiatedScenario,
    authored: object,
    participant_addresses: tuple[str, ...],
    *,
    behavior_spec: object,
    governed_actions: tuple[str, ...],
    disclosure_reference: Callable[[str], str | None],
) -> ProjectedResourceBudget:
    """Project one authored budget; ``governed_actions`` bounds every tool dimension's scope."""

    owners = tuple(
        ParticipantResourceOwnerRuntime(
            owner_id=str(owner_id),
            kind=owner.kind.value,
            address=_resource_owner_address(
                scenario,
                kind=owner.kind.value,
                ref=owner.ref,
                participant_addresses=participant_addresses,
            ),
        )
        for owner_id, owner in sorted(authored.owners.items())
    )
    owner_by_id = {owner.owner_id: owner for owner in owners}
    demands = tuple(
        ParticipantResourceDemandRuntime(
            budget_id=str(budget_id),
            owner_id=str(dimension.owner_ref),
            owner_kind=owner_by_id[str(dimension.owner_ref)].kind,
            owner_address=owner_by_id[str(dimension.owner_ref)].address,
            pool_ref=dimension.pool_ref,
            resource_kind=getattr(dimension.resource_kind, "value", dimension.resource_kind),
            unit=dimension.unit,
            accounting_mode=dimension.accounting_mode.value,
            meter_profile_ref=dimension.meter_profile_ref,
            limit=dimension.limit,
            reservation=dimension.reservation,
            reset=dimension.reset.value,
            window_ticks=dimension.window_ticks,
            parent_budget_ref=(str(dimension.parent_budget_ref) if dimension.parent_budget_ref is not None else None),
            evidence_refs=tuple(dimension.evidence_refs),
            action_contract_addresses=tool_action_contract_addresses(
                scenario,
                behavior_spec,
                governed_actions,
                [str(ref) for ref in dimension.tool_affordance_refs],
            ),
            participant_disclosure_ref=disclosure_reference(str(budget_id)),
        )
        for budget_id, dimension in sorted(authored.dimensions.items())
    )
    fairness = authored.fairness
    return (
        owners,
        demands,
        ParticipantResourceFairnessRuntime(
            policy=fairness.policy,
            priority_class=fairness.priority_class,
            weight=fairness.weight,
            protected=fairness.protected,
            borrowing=fairness.borrowing,
            reclaim=fairness.reclaim,
            max_queue_ticks=fairness.max_queue_ticks,
            starvation_bound_ticks=fairness.starvation_bound_ticks,
        ),
    )


def _no_disclosure(_budget_id: str) -> None:
    return None


def compile_participant_interaction_budget(
    scenario: InstantiatedScenario,
    *,
    spec_name: str,
    behavior_spec: object,
    participant_addresses: tuple[str, ...],
) -> ParticipantInteractionBudgetRuntime | None:
    """Compile an ACT-624 aggregate interaction budget; its quotas stay hidden from participants."""

    authored = getattr(behavior_spec, "resource_budget", None)
    if authored is None:
        return None
    owners, demands, fairness = project_resource_budget(
        scenario,
        authored,
        participant_addresses,
        behavior_spec=behavior_spec,
        governed_actions=specification_action_contracts(behavior_spec, scenario.action_contracts),
        disclosure_reference=_no_disclosure,
    )
    return ParticipantInteractionBudgetRuntime(
        address=_address("participant", "interaction-budget", spec_name),
        behavior_specification_address=_behavior_specification_address(spec_name),
        participant_addresses=participant_addresses,
        resource_owners=owners,
        resource_demands=demands,
        resource_fairness=fairness,
        clock_address=(
            _address("time", "clock", _section_ref_name(authored.clock_ref, "clocks", scenario.clocks))
            if authored.clock_ref is not None
            else ""
        ),
    )


__all__ = (
    "ProjectedResourceBudget",
    "compile_participant_interaction_budget",
    "project_resource_budget",
)
