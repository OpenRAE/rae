"""Participant episode policy compilation (DSL-120).

Each admitted ``behavior_specifications.<name>.episode_policy`` compiles to one
``participant.episode-policy.<name>`` record of authored intent with resolved
canonical addresses. Compilation never creates episode identity, state,
history, or terminal facts; those remain ADR-013 runtime contracts.
"""

from collections.abc import Callable, Iterable

from raes.entities import flatten_entities
from raes.participant_episode_policy import (
    ParticipantEpisodePolicy,
    ParticipantEpisodeTimeoutCondition,
)
from raes.scenario import InstantiatedScenario
from raes.semantics.participant_behavior import select_participants
from raes_contracts.participant_episode import ParticipantEpisodeTerminalReason

from ..models.participant_episode_resources import (
    ParticipantEpisodeConditionRuntime,
    ParticipantEpisodePolicyRuntime,
)
from .addresses import (
    _action_contract_address,
    _assertion_address,
    _behavior_specification_address,
    _participant_behavior_address,
    _participant_episode_policy_address,
    _section_ref_name,
)
from .support import _address, _dedupe, _dump


def _compile_participant_episode_policies(
    scenario: InstantiatedScenario,
) -> dict[str, ParticipantEpisodePolicyRuntime]:
    """Compile admitted episode policies as participant metadata."""

    governed = [
        (spec_name, behavior_spec)
        for spec_name, behavior_spec in scenario.behavior_specifications.items()
        if behavior_spec.episode_policy is not None
    ]
    if not governed:
        return {}
    entities = flatten_entities(scenario.entities)
    roles = {name: agent.effective_role(entities) for name, agent in scenario.agents.items()}
    policies: dict[str, ParticipantEpisodePolicyRuntime] = {}
    for spec_name, behavior_spec in governed:
        participants = sorted(select_participants(behavior_spec, set(scenario.agents), roles))
        runtime = _compile_policy(scenario, spec_name, behavior_spec.episode_policy, participants)
        policies[runtime.address] = runtime
    return policies


def _addresses(
    scenario: InstantiatedScenario,
    refs: Iterable[str],
    section: str,
    render: Callable[[str], str],
) -> tuple[str, ...]:
    declarations = getattr(scenario, section)
    return tuple(render(_section_ref_name(ref, section, declarations)) for ref in refs)


def _evidence_addresses(scenario: InstantiatedScenario, refs: Iterable[str]) -> tuple[str, ...]:
    return _addresses(
        scenario,
        refs,
        "evidence_requirements",
        lambda name: _address("sdl", "evidence-requirements", name),
    )


def _assertion_condition(
    scenario: InstantiatedScenario,
    condition_id: str,
    terminal_reason: str,
    condition: object,
) -> ParticipantEpisodeConditionRuntime:
    return ParticipantEpisodeConditionRuntime(
        condition_id=condition_id,
        terminal_reason=terminal_reason,
        evidence_requirement_addresses=_evidence_addresses(scenario, condition.evidence_requirement_refs),
        assertion_addresses=_addresses(scenario, condition.assertion_refs, "assertions", _assertion_address),
    )


def _timeout_condition(
    scenario: InstantiatedScenario,
    condition_id: str,
    condition: ParticipantEpisodeTimeoutCondition,
) -> ParticipantEpisodeConditionRuntime:
    constraint = _section_ref_name(
        condition.temporal_constraint_ref, "temporal_constraints", scenario.temporal_constraints
    )
    return ParticipantEpisodeConditionRuntime(
        condition_id=condition_id,
        terminal_reason=condition.terminal_reason,
        evidence_requirement_addresses=_evidence_addresses(scenario, condition.evidence_requirement_refs),
        temporal_constraint_address=_address("time", "constraint", constraint),
    )


def _compile_conditions(
    scenario: InstantiatedScenario,
    policy: ParticipantEpisodePolicy,
) -> tuple[ParticipantEpisodeConditionRuntime, ...]:
    compiled = [
        _timeout_condition(scenario, condition_id, condition)
        if isinstance(condition, ParticipantEpisodeTimeoutCondition)
        else _assertion_condition(scenario, condition_id, condition.terminal_reason, condition)
        for condition_id, condition in policy.terminal_conditions.items()
    ]
    compiled.extend(
        _assertion_condition(scenario, condition_id, ParticipantEpisodeTerminalReason.TRUNCATED.value, condition)
        for condition_id, condition in policy.truncation_conditions.items()
    )
    return tuple(sorted(compiled, key=lambda item: item.condition_id))


def _condition_dependencies(conditions: Iterable[ParticipantEpisodeConditionRuntime]) -> list[str]:
    dependencies: list[str] = []
    for condition in conditions:
        dependencies.extend(condition.assertion_addresses)
        if condition.temporal_constraint_address:
            dependencies.append(condition.temporal_constraint_address)
        dependencies.extend(condition.evidence_requirement_addresses)
    return dependencies


def _compile_policy(
    scenario: InstantiatedScenario,
    spec_name: str,
    policy: ParticipantEpisodePolicy,
    participants: list[str],
) -> ParticipantEpisodePolicyRuntime:
    owner = _behavior_specification_address(spec_name)
    participant_addresses = tuple(_participant_behavior_address(name) for name in participants)
    initialization = policy.initialization
    initialization_addresses = _addresses(
        scenario,
        initialization.assertion_refs if initialization is not None else (),
        "assertions",
        _assertion_address,
    )
    structure = policy.interaction_structure
    turn_actions = _addresses(
        scenario,
        structure.action_contract_refs if structure is not None else (),
        "action_contracts",
        _action_contract_address,
    )
    reset = policy.reset_policy
    reset_evidence = _evidence_addresses(scenario, reset.evidence_requirement_refs if reset is not None else ())
    conditions = _compile_conditions(scenario, policy)
    return ParticipantEpisodePolicyRuntime(
        address=_participant_episode_policy_address(spec_name),
        name=spec_name,
        spec=_dump(policy),
        refresh_dependencies=_dedupe(
            [
                owner,
                *participant_addresses,
                *initialization_addresses,
                *turn_actions,
                *_condition_dependencies(conditions),
                *reset_evidence,
            ]
        ),
        behavior_specification_address=owner,
        participant_addresses=participant_addresses,
        profile=policy.profile,
        initialization_assertion_addresses=initialization_addresses,
        turn_order_basis=structure.order_basis.value if structure is not None else "",
        turn_action_contract_addresses=turn_actions,
        conditions=conditions,
        reset_control_actions=tuple(action.value for action in reset.control_actions) if reset is not None else (),
        participant_memory_scope=reset.participant_memory_scope.value if reset is not None else "",
        memory_reset_authority_ref=(reset.memory_reset_authority_ref or "") if reset is not None else "",
        reset_evidence_requirement_addresses=reset_evidence,
    )
