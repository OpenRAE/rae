"""Resolve action-local temporal guarantees against shared-time declarations."""

import hashlib

import rfc8785
from raes.scenario import InstantiatedScenario
from raes_contracts.contracts.participant_temporal import ParticipantTemporalBindingModel

from .addresses import _action_contract_address, _section_ref_name
from .support import _address, _dump


def compile_participant_temporal_bindings(
    scenario: InstantiatedScenario,
    action_refs: list[str],
) -> tuple[ParticipantTemporalBindingModel, ...]:
    """Preserve explicit identity; never infer a binding from legacy strings."""

    bindings: list[ParticipantTemporalBindingModel] = []
    for action_ref in dict.fromkeys(action_refs):
        action_name = _section_ref_name(action_ref, "action_contracts", scenario.action_contracts)
        bindings.extend(_compile_action_bindings(scenario, action_name))
    return tuple(bindings)


def _compile_action_bindings(
    scenario: InstantiatedScenario,
    action_name: str,
) -> list[ParticipantTemporalBindingModel]:
    return [
        _compile_temporal_binding(scenario, action_name, temporal)
        for temporal in scenario.action_contracts[action_name].temporal_contracts
        if temporal.shared_time_binding is not None
    ]


def _compile_temporal_binding(
    scenario: InstantiatedScenario,
    action_name: str,
    temporal: object,
) -> ParticipantTemporalBindingModel:
    authored = temporal.shared_time_binding
    clock_name = _section_ref_name(authored.clock_ref, "clocks", scenario.clocks)
    constraint_name = _section_ref_name(authored.constraint_ref, "temporal_constraints", scenario.temporal_constraints)
    clock = scenario.clocks[clock_name]
    constraint = scenario.temporal_constraints[constraint_name]
    domain_name = _section_ref_name(clock.time_domain_ref, "time_domains", scenario.time_domains)
    boundary_name = _boundary_name(scenario, authored)
    digest = _binding_digest(scenario, action_name, temporal, clock, constraint, domain_name, boundary_name)
    return ParticipantTemporalBindingModel(
        action_contract_address=_action_contract_address(action_name),
        temporal_id=temporal.temporal_id,
        temporal_kind=temporal.temporal_kind.value,
        clock_address=_address("time", "clock", clock_name),
        constraint_address=_address("time", "constraint", constraint_name),
        event_point=authored.event_point,
        evidence_mode=authored.evidence_mode,
        end=constraint.end.model_dump(),
        start=constraint.start.model_dump() if constraint.start is not None else None,
        condition_precondition_id=authored.condition_precondition_id,
        observation_boundary_address=_observation_boundary_address(boundary_name),
        contract_digest=digest,
        time_domain=temporal.time_domain.value,
        clock_authority=temporal.clock_authority,
        event_points=tuple(point.value for point in temporal.event_points),
        backend_disclosure_refs=tuple(temporal.backend_disclosure_refs),
        reset_boundary=temporal.reset_boundary,
        replay_boundary=temporal.replay_boundary,
    )


def _boundary_name(scenario: InstantiatedScenario, authored: object) -> str | None:
    if authored.observation_boundary_ref is None:
        return None
    return _section_ref_name(
        authored.observation_boundary_ref,
        "observation_boundaries",
        scenario.observation_boundaries,
    )


def _binding_digest(
    scenario: InstantiatedScenario,
    action_name: str,
    temporal: object,
    clock: object,
    constraint: object,
    domain_name: str,
    boundary_name: str | None,
) -> str:
    payload = {
        "action": _action_contract_address(action_name),
        "temporal_contract": _dump(temporal),
        "clock": _dump(clock),
        "time_domain": _dump(scenario.time_domains[domain_name]),
        "constraint": _dump(constraint),
    }
    if boundary_name is not None:
        payload.update(_boundary_digest_fields(scenario, action_name, temporal.shared_time_binding, boundary_name))
    return "sha256:" + hashlib.sha256(rfc8785.dumps(payload)).hexdigest()


def _boundary_digest_fields(
    scenario: InstantiatedScenario,
    action_name: str,
    authored: object,
    boundary_name: str,
) -> dict[str, object]:
    condition = next(
        precondition
        for precondition in scenario.action_contracts[action_name].preconditions
        if precondition.precondition_id == authored.condition_precondition_id
    )
    return {
        "observation_boundary": _dump(scenario.observation_boundaries[boundary_name]),
        "condition": _dump(condition),
    }


def _observation_boundary_address(boundary_name: str | None) -> str | None:
    return _address("participant", "observation-boundary", boundary_name) if boundary_name is not None else None
