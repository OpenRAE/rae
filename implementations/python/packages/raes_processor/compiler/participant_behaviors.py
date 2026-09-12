"""Participant behavior and behavior-specification compilation."""

from collections.abc import Callable, Mapping

from raes.scenario import InstantiatedScenario

from ..models import (
    Diagnostic,
    ParticipantBehaviorRuntime,
    ParticipantBehaviorSpecificationRuntime,
    ParticipantInteractiveAccessRuntime,
    ParticipantToolAffordanceRuntime,
)
from ._mixed_control import _compile_mixed_control
from .addresses import (
    _action_contract_address,
    _assertion_address,
    _behavior_specification_address,
    _content_address,
    _observation_boundary_address,
    _outcome_interpretation_rule_address,
    _participant_behavior_address,
    _participant_inject_delivery_address,
    _section_ref_name,
    _tool_affordance_address,
)
from .alias_index import (
    _account_addresses_for_refs,
    _initial_knowledge_addresses,
    _runtime_addressable_ref_index,
    _runtime_addresses_for_refs,
)
from .participant_autonomous_execution import _compile_autonomous_execution
from .support import _dedupe, _dump


def _participant_action_addresses(
    scenario: InstantiatedScenario,
    *,
    participant_name: str,
    action_names: list[str],
    diagnostics: list[Diagnostic],
) -> list[str]:
    action_addresses: list[str] = []
    if not scenario.action_contracts:
        return action_addresses
    for action_name in dict.fromkeys(action_names):
        if action_name in scenario.action_contracts:
            action_addresses.append(_action_contract_address(action_name))
            continue
        if action_name:
            diagnostics.append(
                Diagnostic(
                    code="participant.action-contract-ref-unbound",
                    domain="participant",
                    address=_participant_behavior_address(participant_name),
                    message=f"Reference '{action_name}' does not resolve to a declared participant action contract.",
                )
            )
    return action_addresses


def _participant_observation_addresses(
    scenario: InstantiatedScenario,
    *,
    participant_name: str,
    boundary_names: list[str],
    diagnostics: list[Diagnostic],
) -> list[str]:
    observation_addresses: list[str] = []
    for boundary_name in dict.fromkeys(boundary_names):
        if boundary_name in scenario.observation_boundaries:
            observation_addresses.append(_observation_boundary_address(boundary_name))
            continue
        if boundary_name:
            diagnostics.append(
                Diagnostic(
                    code="participant.observation-boundary-ref-unbound",
                    domain="participant",
                    address=_participant_behavior_address(participant_name),
                    message=(
                        f"Reference '{boundary_name}' does not resolve to a declared participant observation boundary."
                    ),
                )
            )
    return observation_addresses


def _compile_participant_behaviors(
    scenario: InstantiatedScenario,
    diagnostics: list[Diagnostic],
) -> dict[str, ParticipantBehaviorRuntime]:
    participant_behaviors: dict[str, ParticipantBehaviorRuntime] = {}
    addressable_ref_index = _runtime_addressable_ref_index(scenario)
    for name, agent in scenario.agents.items():
        action_addresses = _participant_action_addresses(
            scenario,
            participant_name=name,
            action_names=list(agent.actions),
            diagnostics=diagnostics,
        )
        observation_addresses = _participant_observation_addresses(
            scenario,
            participant_name=name,
            boundary_names=list(agent.observation_boundaries),
            diagnostics=diagnostics,
        )
        starting_account_refs = tuple(agent.starting_accounts)
        starting_account_addresses = _account_addresses_for_refs(scenario, list(agent.starting_accounts))
        initial_knowledge_addresses = _initial_knowledge_addresses(
            scenario,
            agent.initial_knowledge,
        )
        starting_assertion_refs = tuple(agent.starting_assertions)
        starting_assertion_addresses = tuple(_assertion_address(ref) for ref in agent.starting_assertions)
        authority_anchor_refs = tuple(agent.authority_anchors)
        authority_anchor_addresses = _runtime_addresses_for_refs(
            list(agent.authority_anchors),
            addressable_ref_index=addressable_ref_index,
        )
        operating_scope_refs = tuple(agent.operating_scope)
        operating_scope_addresses = _runtime_addresses_for_refs(
            list(agent.operating_scope),
            addressable_ref_index=addressable_ref_index,
        )
        interactive_access: list[ParticipantInteractiveAccessRuntime] = []
        interactive_access_addresses: list[str] = []
        for access_id, access in sorted(agent.interactive_access.items()):
            target_addresses = _runtime_addresses_for_refs(
                [access.target_ref],
                addressable_ref_index=addressable_ref_index,
            )
            account_addresses = _runtime_addresses_for_refs(
                [access.account_ref] if access.account_ref else [],
                addressable_ref_index=addressable_ref_index,
            )
            target_address = target_addresses[0]
            account_address = account_addresses[0] if account_addresses else ""
            channel = str(getattr(access.channel, "value", access.channel))
            interactive_access.append(
                ParticipantInteractiveAccessRuntime(
                    access_id=access_id,
                    target_ref=access.target_ref,
                    target_address=target_address,
                    channel=channel,
                    account_ref=access.account_ref or "",
                    account_address=account_address,
                )
            )
            interactive_access_addresses.extend(target_addresses)
            interactive_access_addresses.extend(account_addresses)
        dependency_addresses = _dedupe(
            [
                *action_addresses,
                *observation_addresses,
                *starting_account_addresses,
                *initial_knowledge_addresses,
                *starting_assertion_addresses,
                *authority_anchor_addresses,
                *operating_scope_addresses,
                *interactive_access_addresses,
            ]
        )
        participant_behaviors[_participant_behavior_address(name)] = ParticipantBehaviorRuntime(
            address=_participant_behavior_address(name),
            name=name,
            participant_name=name,
            entity_name=agent.entity,
            starting_account_refs=starting_account_refs,
            starting_account_addresses=starting_account_addresses,
            initial_knowledge_addresses=initial_knowledge_addresses,
            starting_assertion_refs=starting_assertion_refs,
            starting_assertion_addresses=starting_assertion_addresses,
            authority_anchor_refs=authority_anchor_refs,
            authority_anchor_addresses=authority_anchor_addresses,
            operating_scope_refs=operating_scope_refs,
            operating_scope_addresses=operating_scope_addresses,
            action_contract_addresses=tuple(action_addresses),
            observation_boundary_addresses=tuple(observation_addresses),
            interactive_access=tuple(interactive_access),
            refresh_dependencies=dependency_addresses,
            spec={"agent": _dump(agent), "interpretation_mode": "role-neutral-projection"},
        )
    return participant_behaviors


def _resolve_behavior_spec_refs(
    *,
    refs: list[str],
    declared: Mapping[str, object],
    address_for_ref: Callable[[str], str],
    owner_address: str,
    diagnostic_code: str,
    diagnostic_label: str,
    diagnostics: list[Diagnostic],
) -> tuple[str, ...]:
    addresses: list[str] = []
    for ref in dict.fromkeys(refs):
        if ref in declared:
            addresses.append(address_for_ref(ref))
            continue
        if ref:
            diagnostics.append(
                Diagnostic(
                    code=diagnostic_code,
                    domain="participant",
                    address=owner_address,
                    message=f"Reference '{ref}' does not resolve to a declared {diagnostic_label}.",
                )
            )
    return tuple(addresses)


def _compile_behavior_specifications(
    scenario: InstantiatedScenario,
    diagnostics: list[Diagnostic],
) -> dict[str, ParticipantBehaviorSpecificationRuntime]:
    behavior_specifications: dict[str, ParticipantBehaviorSpecificationRuntime] = {}
    addressable_ref_index = _runtime_addressable_ref_index(scenario)
    for name, behavior_spec in scenario.behavior_specifications.items():
        address = _behavior_specification_address(name)
        spec = _dump(behavior_spec)
        participant_addresses = _resolve_behavior_spec_refs(
            refs=list(behavior_spec.participant_refs),
            declared=scenario.agents,
            address_for_ref=_participant_behavior_address,
            owner_address=address,
            diagnostic_code="participant.behavior-specification-participant-ref-unbound",
            diagnostic_label="agent",
            diagnostics=diagnostics,
        )
        action_addresses = _resolve_behavior_spec_refs(
            refs=list(behavior_spec.action_contract_refs),
            declared=scenario.action_contracts,
            address_for_ref=_action_contract_address,
            owner_address=address,
            diagnostic_code="participant.behavior-specification-action-contract-ref-unbound",
            diagnostic_label="participant action contract",
            diagnostics=diagnostics,
        )
        observation_addresses = _resolve_behavior_spec_refs(
            refs=list(behavior_spec.observation_boundary_refs),
            declared=scenario.observation_boundaries,
            address_for_ref=_observation_boundary_address,
            owner_address=address,
            diagnostic_code="participant.behavior-specification-observation-boundary-ref-unbound",
            diagnostic_label="participant observation boundary",
            diagnostics=diagnostics,
        )
        outcome_rule_addresses = _resolve_behavior_spec_refs(
            refs=list(behavior_spec.outcome_interpretation_rule_refs),
            declared=scenario.outcome_interpretation_rules,
            address_for_ref=_outcome_interpretation_rule_address,
            owner_address=address,
            diagnostic_code="participant.behavior-specification-outcome-rule-ref-unbound",
            diagnostic_label="participant outcome interpretation rule",
            diagnostics=diagnostics,
        )
        authority_scope_addresses = _runtime_addresses_for_refs(
            list(behavior_spec.authority_scope_refs),
            addressable_ref_index=addressable_ref_index,
        )
        (
            mixed_control_participant_address,
            mixed_control_policy_revision,
            mixed_control_order_strategy,
            mixed_control_initial_state_address,
            mixed_control_dispositions,
            controller_states,
            control_transitions,
            mixed_control_dependencies,
        ) = _compile_mixed_control(
            spec_name=name,
            behavior_spec=behavior_spec,
            addressable_ref_index=addressable_ref_index,
        )
        dependencies = _dedupe(
            [
                *participant_addresses,
                *action_addresses,
                *observation_addresses,
                *outcome_rule_addresses,
                *authority_scope_addresses,
                *mixed_control_dependencies,
            ]
        )
        tool_affordance_addresses = tuple(
            _tool_affordance_address(name, affordance_id) for affordance_id in sorted(behavior_spec.tool_affordances)
        )
        participant_inject_delivery_addresses = tuple(
            _participant_inject_delivery_address(name, binding_id)
            for binding_id in sorted(behavior_spec.participant_inject_deliveries)
        )
        autonomous_execution = _compile_autonomous_execution(
            scenario=scenario,
            spec_name=name,
            participant_addresses=participant_addresses,
            behavior_spec=behavior_spec,
        )
        behavior_specifications[address] = ParticipantBehaviorSpecificationRuntime(
            address=address,
            name=name,
            spec_name=name,
            semantic_version=str(behavior_spec.semantic_version),
            lifecycle_state=str(getattr(behavior_spec.lifecycle_state, "value", behavior_spec.lifecycle_state)),
            participant_addresses=participant_addresses,
            participant_role_refs=tuple(behavior_spec.participant_role_refs),
            action_contract_addresses=action_addresses,
            observation_boundary_addresses=observation_addresses,
            outcome_interpretation_rule_addresses=outcome_rule_addresses,
            authority_scope_refs=tuple(behavior_spec.authority_scope_refs),
            authority_scope_addresses=authority_scope_addresses,
            behavior_mode=str(behavior_spec.behavior_mode or ""),
            autonomous_execution=autonomous_execution,
            mixed_control_participant_address=mixed_control_participant_address,
            mixed_control_policy_revision=mixed_control_policy_revision,
            mixed_control_order_strategy=mixed_control_order_strategy,
            mixed_control_initial_state_address=mixed_control_initial_state_address,
            mixed_control_dispositions=mixed_control_dispositions,
            controller_states=controller_states,
            control_transitions=control_transitions,
            realization_profile_ref=str(behavior_spec.realization_profile_ref or ""),
            backend_feature_support_refs=tuple(behavior_spec.backend_feature_support_refs),
            evidence_contract_refs=tuple(behavior_spec.evidence_contract_refs),
            tool_affordance_addresses=tool_affordance_addresses,
            participant_inject_delivery_addresses=participant_inject_delivery_addresses,
            extension_policy=str(behavior_spec.extension_policy),
            extension_keys=tuple(sorted(behavior_spec.extensions)),
            refresh_dependencies=dependencies,
            spec=spec,
        )
    return behavior_specifications


def _compile_tool_affordances(
    scenario: InstantiatedScenario,
    diagnostics: list[Diagnostic],
) -> dict[str, ParticipantToolAffordanceRuntime]:
    tool_affordances: dict[str, ParticipantToolAffordanceRuntime] = {}
    for spec_name, behavior_spec in scenario.behavior_specifications.items():
        owner_address = _behavior_specification_address(spec_name)
        for affordance_id, binding in sorted(behavior_spec.tool_affordances.items()):
            address = _tool_affordance_address(spec_name, affordance_id)
            action_addresses = _resolve_behavior_spec_refs(
                refs=list(binding.action_contract_refs),
                declared=scenario.action_contracts,
                address_for_ref=_action_contract_address,
                owner_address=address,
                diagnostic_code="participant.tool-affordance-action-contract-ref-unbound",
                diagnostic_label="participant action contract",
                diagnostics=diagnostics,
            )
            observation_addresses = _resolve_behavior_spec_refs(
                refs=list(binding.observation_boundary_refs),
                declared=scenario.observation_boundaries,
                address_for_ref=_observation_boundary_address,
                owner_address=address,
                diagnostic_code="participant.tool-affordance-observation-boundary-ref-unbound",
                diagnostic_label="participant observation boundary",
                diagnostics=diagnostics,
            )
            tool_address = ""
            if binding.tool_ref:
                tool_name = _section_ref_name(binding.tool_ref, "content", scenario.content)
                tool_address = _content_address(tool_name)
            dependencies = _dedupe(
                [
                    owner_address,
                    *([tool_address] if tool_address else []),
                    *action_addresses,
                    *observation_addresses,
                ]
            )
            tool_affordances[address] = ParticipantToolAffordanceRuntime(
                address=address,
                name=affordance_id,
                affordance_id=affordance_id,
                behavior_specification_address=owner_address,
                tool_ref=str(binding.tool_ref or ""),
                tool_address=tool_address,
                action_contract_refs=tuple(binding.action_contract_refs),
                action_contract_addresses=action_addresses,
                observation_boundary_refs=tuple(binding.observation_boundary_refs),
                observation_boundary_addresses=observation_addresses,
                refresh_dependencies=dependencies,
                spec=_dump(binding),
            )
    return tool_affordances
