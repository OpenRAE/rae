"""Backend-independent reference validity for explicit shared-time bindings."""

from collections.abc import Iterable, Iterator, Mapping, Sequence

from .._base import is_variable_ref
from ..participant_temporal_semantics import ParticipantSharedTimeBinding
from ..scenario import ScenarioContent
from .participant_behavior._references import _resolve_section_ref


def participant_temporal_binding_errors(scenario: ScenarioContent) -> Iterator[str]:
    """Check declaration ownership, not backend support or implementation style."""

    for action_name, action in scenario.action_contracts.items():
        for temporal in action.temporal_contracts:
            binding = temporal.shared_time_binding
            if binding is not None:
                yield from _binding_errors(scenario, action_name, temporal, binding)


def _binding_errors(
    scenario: ScenarioContent,
    action_name: str,
    temporal: object,
    binding: ParticipantSharedTimeBinding,
) -> tuple[str, ...]:
    label = f"Action '{action_name}' temporal binding '{temporal.temporal_id}'"
    clock_name = _resolve_section_ref(binding.clock_ref, "clocks", scenario.clocks)
    constraint_name = _resolve_section_ref(
        binding.constraint_ref, "temporal_constraints", scenario.temporal_constraints
    )
    errors = list(_binding_reference_errors(label, binding, clock_name, constraint_name))
    if clock_name is None or constraint_name is None:
        return tuple(errors)
    constraint = scenario.temporal_constraints[constraint_name]
    errors.extend(_shared_clock_errors(scenario, temporal, action_name, clock_name, constraint, label))
    if temporal.temporal_kind.value == "dwell":
        errors.extend(_dwell_binding_errors(scenario, action_name, binding, constraint, label))
    errors.extend(_policy_clock_errors(scenario, action_name, clock_name, label))
    return tuple(errors)


def _binding_reference_errors(
    label: str,
    binding: ParticipantSharedTimeBinding,
    clock_name: str | None,
    constraint_name: str | None,
) -> Iterator[str]:
    if clock_name is None and not is_variable_ref(binding.clock_ref):
        yield f"{label} clock_ref is not declared"
    if constraint_name is None and not is_variable_ref(binding.constraint_ref):
        yield f"{label} constraint_ref is not declared"


def _shared_clock_errors(
    scenario: ScenarioContent,
    temporal: object,
    action_name: str,
    clock_name: str,
    constraint: object,
    label: str,
) -> tuple[str, ...]:
    errors: list[str] = []
    if constraint.clock_ref != clock_name:
        errors.append(f"{label} constraint uses another clock")
    clock = scenario.clocks[clock_name]
    domain_name = _resolve_section_ref(clock.time_domain_ref, "time_domains", scenario.time_domains)
    if domain_name is not None and temporal.time_domain.value != _clock_domain(scenario, domain_name):
        errors.append(f"{label} time domain contradicts its shared clock declaration")
    expected_kind = "deadline" if temporal.temporal_kind.value == "deadline" else "window"
    if constraint.constraint_kind.value != expected_kind:
        errors.append(f"{label} requires a {expected_kind} constraint")
    if not _constraint_has_subject(constraint.subject_refs, action_name):
        errors.append(f"{label} constraint must name the bound action as a subject")
    return tuple(errors)


def _clock_domain(scenario: ScenarioContent, domain_name: str) -> str:
    return {
        "simulated": "simulation_time",
        "wall_clock": "wall_clock_time",
        "logical": "scenario_time",
        "monotonic": "scenario_time",
        "external": "backend_time",
    }[scenario.time_domains[domain_name].kind.value]


def _constraint_has_subject(subject_refs: Sequence[str], action_name: str) -> bool:
    return action_name in subject_refs or f"action_contracts.{action_name}" in subject_refs


def _dwell_binding_errors(
    scenario: ScenarioContent,
    action_name: str,
    binding: ParticipantSharedTimeBinding,
    constraint: object,
    label: str,
) -> tuple[str, ...]:
    errors: list[str] = []
    action = scenario.action_contracts[action_name]
    if binding.condition_precondition_id not in {item.precondition_id for item in action.preconditions}:
        errors.append(f"{label} condition_precondition_id must name a precondition of the bound action")
    boundary = _resolve_section_ref(
        binding.observation_boundary_ref,
        "observation_boundaries",
        scenario.observation_boundaries,
    )
    if boundary is None and not is_variable_ref(binding.observation_boundary_ref):
        errors.append(f"{label} observation_boundary_ref is not declared")
    if boundary is not None:
        errors.extend(_dwell_observation_errors(scenario, action_name, binding, boundary, label))
    if _invalid_dwell_interval(constraint):
        errors.append(f"{label} dwell requires a nonempty interval within one clock segment")
    return tuple(errors)


def _invalid_dwell_interval(constraint: object) -> bool:
    if constraint.start is None or constraint.end is None:
        return False
    return (constraint.start.tick, constraint.start.microstep) >= (constraint.end.tick, constraint.end.microstep)


def _dwell_observation_errors(
    scenario: ScenarioContent,
    action_name: str,
    binding: ParticipantSharedTimeBinding,
    boundary_name: str,
    label: str,
) -> Iterator[str]:
    boundary = scenario.observation_boundaries[boundary_name]
    condition = next(
        (
            item
            for item in scenario.action_contracts[action_name].preconditions
            if item.precondition_id == binding.condition_precondition_id
        ),
        None,
    )
    observable = set(boundary.observable_refs)
    for rule in boundary.view_rules:
        if rule.disposition.value in {"observable", "disclosed", "discovered", "inferred", "deceptive"}:
            observable.add(rule.information_ref)
        else:
            observable.discard(rule.information_ref)
    if condition is not None:
        if any(ref not in observable and not is_variable_ref(ref) for ref in condition.support_refs):
            yield f"{label} condition support must be observable through its boundary"
        if any(ref not in boundary.evidence_refs and not is_variable_ref(ref) for ref in condition.evidence_refs):
            yield f"{label} condition evidence must be declared by its boundary"
    yield from _dwell_boundary_ownership_errors(scenario, action_name, boundary_name, label)


def _resolved_names(refs: Iterable[str], section: str, declarations: Mapping[str, object]) -> set[str | None]:
    return {_resolve_section_ref(ref, section, declarations) for ref in refs}


def _dwell_boundary_ownership_errors(
    scenario: ScenarioContent, action_name: str, boundary_name: str, label: str
) -> Iterator[str]:
    yield from _agent_boundary_ownership_errors(scenario, action_name, boundary_name, label)
    yield from _behavior_boundary_ownership_errors(scenario, action_name, boundary_name, label)


def _agent_boundary_ownership_errors(
    scenario: ScenarioContent, action_name: str, boundary_name: str, label: str
) -> Iterator[str]:
    for participant_name, agent in scenario.agents.items():
        if action_name in _resolved_names(agent.actions, "action_contracts", scenario.action_contracts):
            authorized = _resolved_names(
                agent.observation_boundaries, "observation_boundaries", scenario.observation_boundaries
            )
            if boundary_name not in authorized:
                yield f"{label} observation boundary is outside participant '{participant_name}'"


def _behavior_boundary_ownership_errors(
    scenario: ScenarioContent, action_name: str, boundary_name: str, label: str
) -> Iterator[str]:
    for spec in scenario.behavior_specifications.values():
        if action_name not in _resolved_names(spec.action_contract_refs, "action_contracts", scenario.action_contracts):
            continue
        authorized = _resolved_names(
            spec.observation_boundary_refs, "observation_boundaries", scenario.observation_boundaries
        )
        if boundary_name not in authorized:
            yield f"{label} observation boundary is outside its behavior specification"
        if spec.autonomous_execution is not None:
            selected = _autonomous_boundary_name(scenario, spec.autonomous_execution)
            if selected is not None and selected != boundary_name:
                yield f"{label} must use its autonomous policy's observation boundary"


def _autonomous_boundary_name(scenario: ScenarioContent, policy: object) -> str | None:
    return _resolve_section_ref(
        policy.observation_boundary_ref,
        "observation_boundaries",
        scenario.observation_boundaries,
    )


def _policy_clock_errors(
    scenario: ScenarioContent,
    action_name: str,
    clock_name: str,
    label: str,
) -> Iterator[str]:
    for spec in scenario.behavior_specifications.values():
        policy = spec.autonomous_execution
        if policy is None:
            continue
        candidates = getattr(policy, "action_candidates", None)
        refs = (
            [candidate.action_ref for candidate in candidates.values()]
            if candidates is not None
            else policy.action_order
        )
        if any(_resolve_section_ref(ref, "action_contracts", scenario.action_contracts) == action_name for ref in refs):
            policy_clock = _resolve_section_ref(policy.clock_ref, "clocks", scenario.clocks)
            if policy_clock is not None and policy_clock != clock_name:
                yield f"{label} must use its autonomous policy's shared clock"
