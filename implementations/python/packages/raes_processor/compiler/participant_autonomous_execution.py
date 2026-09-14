"""Compilation of autonomous participant execution policies."""

from typing import Any

from raes.scenario import InstantiatedScenario

from ..models import (
    ParticipantAutonomousExecutionRuntime,
    ParticipantExecutionBindingRuntime,
    ParticipantResourceDemandRuntime,
    ParticipantResourceFairnessRuntime,
    ParticipantResourceOwnerRuntime,
)
from .addresses import (
    _action_contract_address,
    _behavior_specification_address,
    _objective_address,
    _observation_boundary_address,
    _resolve_node_service_ref,
    _section_ref_name,
)
from .alias_index import _runtime_addressable_ref_index, _runtime_addresses_for_refs
from .support import _address, _dump


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


def _legacy_resource_demands(
    policy: object,
    participant_addresses: tuple[str, ...],
) -> tuple[
    tuple[ParticipantResourceOwnerRuntime, ...],
    tuple[ParticipantResourceDemandRuntime, ...],
    ParticipantResourceFairnessRuntime,
]:
    owner_address = participant_addresses[0]
    owner = ParticipantResourceOwnerRuntime(
        owner_id="legacy-participant",
        kind="participant",
        address=owner_address,
    )
    demands = (
        ParticipantResourceDemandRuntime(
            budget_id="legacy-action-rate",
            owner_id=owner.owner_id,
            owner_kind=owner.kind,
            owner_address=owner.address,
            pool_ref="legacy-participant",
            resource_kind="action_rate",
            unit="actions",
            accounting_mode="windowed_counter",
            meter_profile_ref="raes.action-attempt/v1",
            limit=policy.max_action_attempts,
            reservation=1,
            reset="time_segment",
            window_ticks=policy.max_action_attempts,
            provenance="legacy_maximum",
        ),
        ParticipantResourceDemandRuntime(
            budget_id="legacy-concurrent-actions",
            owner_id=owner.owner_id,
            owner_kind=owner.kind,
            owner_address=owner.address,
            pool_ref="legacy-participant",
            resource_kind="concurrent_actions",
            unit="actions",
            accounting_mode="reservable_gauge",
            meter_profile_ref="raes.concurrent-action/v1",
            limit=policy.max_in_flight,
            reservation=1,
            reset="reconciled",
            provenance="legacy_maximum",
        ),
    )
    return (owner,), demands, ParticipantResourceFairnessRuntime()


def _compiled_resource_budget(
    scenario: InstantiatedScenario,
    policy: object,
    participant_addresses: tuple[str, ...],
) -> tuple[
    tuple[ParticipantResourceOwnerRuntime, ...],
    tuple[ParticipantResourceDemandRuntime, ...],
    ParticipantResourceFairnessRuntime,
]:
    authored = getattr(policy, "resource_budget", None)
    if authored is None:
        return _legacy_resource_demands(policy, participant_addresses)
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


def _compiled_execution_bindings(
    scenario: InstantiatedScenario,
    policy: object,
    action_refs: list[str],
) -> tuple[tuple[ParticipantExecutionBindingRuntime, ...], tuple[str, ...]]:
    addressable_ref_index = _runtime_addressable_ref_index(scenario)
    bindings_by_key: dict[tuple[str, tuple[str, ...]], ParticipantExecutionBindingRuntime] = {}
    for action_ref in action_refs:
        action_name = _section_ref_name(
            action_ref,
            "action_contracts",
            scenario.action_contracts,
        )
        action = scenario.action_contracts[action_name]
        target_refs = [
            *(str(ref) for effect in action.effects for ref in effect.target_refs),
            *(str(ref) for precondition in action.preconditions for ref in precondition.support_refs),
        ]
        action_contract_address = _action_contract_address(action_name)
        target_addresses = _runtime_addresses_for_refs(
            list(dict.fromkeys(target_refs)),
            addressable_ref_index=addressable_ref_index,
        )
        interactions = tuple(action.interactions)
        interaction_classes = tuple(dict.fromkeys(interaction.interaction_class.value for interaction in interactions))
        shared_state_refs = tuple(
            dict.fromkeys(str(ref) for interaction in interactions for ref in interaction.shared_state_refs)
        )
        related_action_contract_addresses = tuple(
            dict.fromkeys(
                _action_contract_address(_section_ref_name(ref, "action_contracts", scenario.action_contracts))
                for interaction in interactions
                for ref in interaction.related_actions
            )
        )
        commutative_shared_state_refs = tuple(
            dict.fromkeys(
                str(ref)
                for interaction in interactions
                if interaction.commutative
                for ref in interaction.shared_state_refs
            )
        )
        commutative_related_action_contract_addresses = tuple(
            dict.fromkeys(
                _action_contract_address(_section_ref_name(ref, "action_contracts", scenario.action_contracts))
                for interaction in interactions
                if interaction.commutative
                for ref in interaction.related_actions
            )
        )
        merge_rule_refs = tuple(
            dict.fromkeys(
                interaction.merge_rule_ref for interaction in interactions if interaction.merge_rule_ref is not None
            )
        )
        shared_state_merge_rules = tuple(
            dict.fromkeys(
                (str(ref), interaction.merge_rule_ref)
                for interaction in interactions
                if interaction.merge_rule_ref is not None
                for ref in interaction.shared_state_refs
            )
        )
        related_action_merge_rules = tuple(
            dict.fromkeys(
                (
                    _action_contract_address(_section_ref_name(ref, "action_contracts", scenario.action_contracts)),
                    interaction.merge_rule_ref,
                )
                for interaction in interactions
                if interaction.merge_rule_ref is not None
                for ref in interaction.related_actions
            )
        )
        bindings_by_key.setdefault(
            (action_contract_address, target_addresses),
            ParticipantExecutionBindingRuntime(
                action_contract_address=action_contract_address,
                target_addresses=target_addresses,
                participant_implementation_ref=policy.participant_implementation_ref,
                max_action_attempts=policy.max_action_attempts,
                max_in_flight=policy.max_in_flight,
                interaction_classes=interaction_classes,
                shared_state_refs=shared_state_refs,
                related_action_contract_addresses=related_action_contract_addresses,
                commutative_shared_state_refs=commutative_shared_state_refs,
                commutative_related_action_contract_addresses=commutative_related_action_contract_addresses,
                merge_rule_refs=merge_rule_refs,
                shared_state_merge_rules=shared_state_merge_rules,
                related_action_merge_rules=related_action_merge_rules,
            ),
        )
    bindings = tuple(bindings_by_key.values())
    targets = tuple(dict.fromkeys(target for binding in bindings for target in binding.target_addresses))
    return bindings, targets


def _temporal_constraint_addresses(
    scenario: InstantiatedScenario,
    refs: list[str],
) -> tuple[str, ...]:
    return tuple(
        _address(
            "time",
            "constraint",
            _section_ref_name(ref, "temporal_constraints", scenario.temporal_constraints),
        )
        for ref in refs
    )


def _activity_runtime_fields(
    scenario: InstantiatedScenario,
    policy: object,
    *,
    profile: str,
    work_window_refs: list[str],
    pause_window_refs: list[str],
    ordered_candidates: list[tuple[str, Any]],
) -> dict[str, object]:
    return {
        "profile": profile,
        "work_window_addresses": _temporal_constraint_addresses(scenario, work_window_refs),
        "pause_window_addresses": _temporal_constraint_addresses(scenario, pause_window_refs),
        "stochastic_control_ref": str(getattr(policy, "stochastic_control_ref", "")),
        "timing_minimum_ticks": int(getattr(getattr(policy, "timing", None), "minimum_ticks", 0)),
        "timing_maximum_ticks": int(getattr(getattr(policy, "timing", None), "maximum_ticks", 0)),
        "outside_window_disposition": str(getattr(policy, "outside_window_disposition", "")),
        "empty_eligible_disposition": str(getattr(policy, "empty_eligible_disposition", "")),
        "action_candidate_ids": tuple(str(candidate_id) for candidate_id, _ in ordered_candidates),
        "action_candidate_weights": tuple(candidate.weight for _, candidate in ordered_candidates),
        "action_candidate_dependencies": tuple(
            tuple(str(ref) for ref in candidate.depends_on) for _, candidate in ordered_candidates
        ),
        "action_candidate_retry_failure_classes": tuple(
            tuple(value.value for value in candidate.retryable_failure_classes) for _, candidate in ordered_candidates
        ),
        "action_candidate_max_retries": tuple(candidate.max_retries for _, candidate in ordered_candidates),
        "action_candidate_cooldown_ticks": tuple(candidate.cooldown_ticks for _, candidate in ordered_candidates),
        "max_occurrences": int(getattr(policy, "max_occurrences", 0)),
        "max_burst_size": int(getattr(policy, "max_burst_size", 1)),
    }


def _runtime_refresh_dependencies(
    scenario: InstantiatedScenario,
    participant_addresses: tuple[str, ...],
    action_refs: list[str],
    objective_refs: tuple[str, ...],
    target_addresses: tuple[str, ...],
) -> tuple[str, ...]:
    return (
        *participant_addresses,
        *tuple(
            _action_contract_address(_section_ref_name(ref, "action_contracts", scenario.action_contracts))
            for ref in action_refs
        ),
        *tuple(_objective_address(_section_ref_name(ref, "objectives", scenario.objectives)) for ref in objective_refs),
        *target_addresses,
    )


def _compile_autonomous_execution(
    *,
    scenario: InstantiatedScenario,
    spec_name: str,
    participant_addresses: tuple[str, ...],
    behavior_spec: object,
) -> ParticipantAutonomousExecutionRuntime | None:
    policy = behavior_spec.autonomous_execution
    if policy is None:
        return None
    address = _address("participant", "autonomous-execution", spec_name)
    authority = policy.evaluation_authority
    profile = getattr(policy, "profile", "participant-autonomous-execution/v1")
    activity_candidates = getattr(policy, "action_candidates", None)
    ordered_candidates = sorted(activity_candidates.items()) if activity_candidates is not None else []
    action_refs = (
        [candidate.action_ref for _, candidate in ordered_candidates]
        if ordered_candidates
        else list(policy.action_order)
    )
    work_window_refs = list(getattr(policy, "work_window_refs", ()))
    pause_window_refs = list(getattr(policy, "pause_window_refs", ()))
    temporal_constraint_refs = (
        [*work_window_refs, *pause_window_refs]
        if profile in {"participant-autonomous-execution/v2", "participant-autonomous-execution/v3"}
        else list(policy.temporal_constraint_refs)
    )
    execution_bindings, target_addresses = _compiled_execution_bindings(scenario, policy, action_refs)
    resource_owners, resource_demands, resource_fairness = _compiled_resource_budget(
        scenario,
        policy,
        participant_addresses,
    )
    return ParticipantAutonomousExecutionRuntime(
        address=address,
        name=spec_name,
        behavior_specification_address=_behavior_specification_address(spec_name),
        participant_addresses=participant_addresses,
        participant_implementation_ref=policy.participant_implementation_ref,
        clock_address=_address("time", "clock", _section_ref_name(policy.clock_ref, "clocks", scenario.clocks)),
        progression_policy_address=_address(
            "time",
            "policy",
            _section_ref_name(
                policy.progression_policy_ref,
                "time_progression_policies",
                scenario.time_progression_policies,
            ),
        ),
        temporal_constraint_addresses=_temporal_constraint_addresses(scenario, temporal_constraint_refs),
        action_contract_addresses=tuple(
            _action_contract_address(_section_ref_name(ref, "action_contracts", scenario.action_contracts))
            for ref in action_refs
        ),
        target_addresses=target_addresses,
        execution_bindings=execution_bindings,
        observation_boundary_address=_observation_boundary_address(
            _section_ref_name(
                policy.observation_boundary_ref,
                "observation_boundaries",
                scenario.observation_boundaries,
            )
        ),
        selection_strategy=policy.selection_strategy,
        max_action_attempts=policy.max_action_attempts,
        max_in_flight=policy.max_in_flight,
        failure_policy=policy.failure_policy.value,
        evaluation_authority_mode=authority.mode.value,
        objective_refs=tuple(
            _objective_address(_section_ref_name(ref, "objectives", scenario.objectives))
            for ref in authority.objective_refs
        ),
        proof_producer_refs=tuple(authority.proof_producer_refs),
        score_authority_refs=tuple(authority.score_authority_refs),
        receipt_authority_refs=tuple(authority.receipt_authority_refs),
        **_activity_runtime_fields(
            scenario,
            policy,
            profile=profile,
            work_window_refs=work_window_refs,
            pause_window_refs=pause_window_refs,
            ordered_candidates=ordered_candidates,
        ),
        resource_owners=resource_owners,
        resource_demands=resource_demands,
        resource_fairness=resource_fairness,
        refresh_dependencies=_runtime_refresh_dependencies(
            scenario,
            participant_addresses,
            action_refs,
            tuple(authority.objective_refs),
            target_addresses,
        ),
        spec=_dump(policy),
    )


__all__ = ["_compile_autonomous_execution"]
