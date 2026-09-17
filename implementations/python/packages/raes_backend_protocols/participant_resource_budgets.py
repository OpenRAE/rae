"""Backend participant resource-budget capability declarations."""

from __future__ import annotations

from dataclasses import dataclass

from raes_contracts.contracts.participant_resource_budgets import (
    ParticipantResourceBudgetCapabilitiesModel,
    ParticipantResourcePoolCapacityModel,
)
from raes_contracts.domain_profiles import DomainProfileCoordinateModel, DomainProfileResolutionContextModel


@dataclass(frozen=True)
class ParticipantResourcePoolCapacity:
    pool_ref: str
    owner_kind: str
    owner_ref: str
    resource_kind: str | DomainProfileCoordinateModel
    unit: str
    accounting_mode: str
    meter_profile_ref: str
    capacity: int
    tenant_isolation: str
    configuration_digest: str
    fairness_policy: str
    priority_classes: tuple[str, ...]
    borrowing: str
    reclaim: str
    max_queue_ticks: int
    starvation_bound_ticks: int
    protected_capacity: int
    evidence_contract_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        ParticipantResourcePoolCapacityModel.model_validate(self.__dict__)


@dataclass(frozen=True)
class ParticipantResourceBudgetCapabilities:
    support_strength: str
    supported_owner_kinds: frozenset[str]
    supported_resource_kinds: frozenset[str | DomainProfileCoordinateModel]
    supported_accounting_modes: frozenset[str]
    supported_reset_modes: frozenset[str]
    supported_fairness_policies: frozenset[str]
    supported_isolation_strengths: frozenset[str]
    configured_pools: tuple[ParticipantResourcePoolCapacity, ...]
    realization_contract_ids: frozenset[str]
    cross_range_pool_refs: frozenset[str] = frozenset()
    domain_profile_context: DomainProfileResolutionContextModel | None = None

    def __post_init__(self) -> None:
        ParticipantResourceBudgetCapabilitiesModel.model_validate(
            {
                "support_strength": self.support_strength,
                "supported_owner_kinds": sorted(self.supported_owner_kinds),
                "supported_resource_kinds": sorted(self.supported_resource_kinds, key=str),
                "supported_accounting_modes": sorted(self.supported_accounting_modes),
                "supported_reset_modes": sorted(self.supported_reset_modes),
                "supported_fairness_policies": sorted(self.supported_fairness_policies),
                "supported_isolation_strengths": sorted(self.supported_isolation_strengths),
                "configured_pools": [pool.__dict__ for pool in self.configured_pools],
                "realization_contract_ids": sorted(self.realization_contract_ids),
                "cross_range_pool_refs": sorted(self.cross_range_pool_refs),
                "domain_profile_context": self.domain_profile_context,
            }
        )


def participant_resource_budget_capability_payload(
    capability: ParticipantResourceBudgetCapabilities,
) -> ParticipantResourceBudgetCapabilitiesModel:
    return ParticipantResourceBudgetCapabilitiesModel.model_validate(
        {
            "support_strength": capability.support_strength,
            "supported_owner_kinds": sorted(capability.supported_owner_kinds),
            "supported_resource_kinds": sorted(capability.supported_resource_kinds, key=str),
            "supported_accounting_modes": sorted(capability.supported_accounting_modes),
            "supported_reset_modes": sorted(capability.supported_reset_modes),
            "supported_fairness_policies": sorted(capability.supported_fairness_policies),
            "supported_isolation_strengths": sorted(capability.supported_isolation_strengths),
            "configured_pools": [pool.__dict__ for pool in capability.configured_pools],
            "realization_contract_ids": sorted(capability.realization_contract_ids),
            "cross_range_pool_refs": sorted(capability.cross_range_pool_refs),
            "domain_profile_context": capability.domain_profile_context,
        }
    )


def participant_resource_budget_capability_from_model(
    model: ParticipantResourceBudgetCapabilitiesModel,
) -> ParticipantResourceBudgetCapabilities:
    return ParticipantResourceBudgetCapabilities(
        support_strength=model.support_strength,
        supported_owner_kinds=frozenset(model.supported_owner_kinds),
        supported_resource_kinds=frozenset(model.supported_resource_kinds),
        supported_accounting_modes=frozenset(model.supported_accounting_modes),
        supported_reset_modes=frozenset(model.supported_reset_modes),
        supported_fairness_policies=frozenset(model.supported_fairness_policies),
        supported_isolation_strengths=frozenset(model.supported_isolation_strengths),
        configured_pools=tuple(
            ParticipantResourcePoolCapacity(
                pool_ref=pool.pool_ref,
                owner_kind=pool.owner_kind,
                owner_ref=pool.owner_ref,
                resource_kind=pool.resource_kind,
                unit=pool.unit,
                accounting_mode=pool.accounting_mode,
                meter_profile_ref=pool.meter_profile_ref,
                capacity=pool.capacity,
                tenant_isolation=pool.tenant_isolation,
                configuration_digest=pool.configuration_digest,
                fairness_policy=pool.fairness_policy,
                priority_classes=tuple(pool.priority_classes),
                borrowing=pool.borrowing,
                reclaim=pool.reclaim,
                max_queue_ticks=pool.max_queue_ticks,
                starvation_bound_ticks=pool.starvation_bound_ticks,
                protected_capacity=pool.protected_capacity,
                evidence_contract_ids=tuple(pool.evidence_contract_ids),
            )
            for pool in model.configured_pools
        ),
        realization_contract_ids=frozenset(model.realization_contract_ids),
        cross_range_pool_refs=frozenset(model.cross_range_pool_refs),
        domain_profile_context=model.domain_profile_context,
    )


__all__ = [
    "ParticipantResourceBudgetCapabilities",
    "ParticipantResourcePoolCapacity",
    "participant_resource_budget_capability_from_model",
    "participant_resource_budget_capability_payload",
]
