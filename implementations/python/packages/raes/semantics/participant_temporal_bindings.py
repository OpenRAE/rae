"""Backend-independent reference validity for explicit shared-time bindings."""

from collections.abc import Iterator

from .._base import is_variable_ref
from ..participant_temporal_semantics import ParticipantSharedTimeBinding
from ..scenario import ScenarioContent
from .participant_behavior._references import _resolve_section_ref


def participant_temporal_binding_errors(scenario: ScenarioContent) -> Iterator[str]:
    """Check declaration ownership, not backend support or implementation style."""

    for action_name, action in scenario.action_contracts.items():
        for temporal in action.temporal_contracts:
            binding = temporal.shared_time_binding
            if binding is None:
                continue
            label = f"Action '{action_name}' temporal binding '{temporal.temporal_id}'"
            clock_name = _resolve_section_ref(binding.clock_ref, "clocks", scenario.clocks)
            constraint_name = _resolve_section_ref(
                binding.constraint_ref, "temporal_constraints", scenario.temporal_constraints
            )
            if clock_name is None and not is_variable_ref(binding.clock_ref):
                yield f"{label} clock_ref is not declared"
            if constraint_name is None and not is_variable_ref(binding.constraint_ref):
                yield f"{label} constraint_ref is not declared"
            if clock_name is None or constraint_name is None:
                continue
            constraint = scenario.temporal_constraints[constraint_name]
            if constraint.clock_ref != clock_name:
                yield f"{label} constraint uses another clock"
            clock = scenario.clocks[clock_name]
            domain_name = _resolve_section_ref(clock.time_domain_ref, "time_domains", scenario.time_domains)
            if domain_name is not None:
                expected_domain = {
                    "simulated": "simulation_time",
                    "wall_clock": "wall_clock_time",
                    "logical": "scenario_time",
                    "monotonic": "scenario_time",
                    "external": "backend_time",
                }[scenario.time_domains[domain_name].kind.value]
                if temporal.time_domain.value != expected_domain:
                    yield f"{label} time domain contradicts its shared clock declaration"
            expected_kind = "deadline" if temporal.temporal_kind.value == "deadline" else "window"
            if constraint.constraint_kind.value != expected_kind:
                yield f"{label} requires a {expected_kind} constraint"
            if (
                action_name not in constraint.subject_refs
                and f"action_contracts.{action_name}" not in constraint.subject_refs
            ):
                yield f"{label} constraint must name the bound action as a subject"
            if temporal.temporal_kind.value == "dwell":
                if binding.condition_precondition_id not in {item.precondition_id for item in action.preconditions}:
                    yield f"{label} condition_precondition_id must name a precondition of the bound action"
                boundary = _resolve_section_ref(
                    binding.observation_boundary_ref, "observation_boundaries", scenario.observation_boundaries
                )
                if boundary is None and not is_variable_ref(binding.observation_boundary_ref):
                    yield f"{label} observation_boundary_ref is not declared"
                if boundary is not None:
                    yield from _dwell_observation_errors(scenario, action_name, binding, boundary, label)
                if constraint.start is not None and constraint.end is not None:
                    start = (constraint.start.tick, constraint.start.microstep)
                    end = (constraint.end.tick, constraint.end.microstep)
                    if start >= end:
                        yield f"{label} dwell requires a nonempty interval within one clock segment"
            yield from _policy_clock_errors(scenario, action_name, clock_name, label)


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


def _resolved_names(refs, section, declarations) -> set[str | None]:
    return {_resolve_section_ref(ref, section, declarations) for ref in refs}


def _dwell_boundary_ownership_errors(
    scenario: ScenarioContent, action_name: str, boundary_name: str, label: str
) -> Iterator[str]:
    for participant_name, agent in scenario.agents.items():
        if action_name in _resolved_names(agent.actions, "action_contracts", scenario.action_contracts):
            authorized = _resolved_names(
                agent.observation_boundaries, "observation_boundaries", scenario.observation_boundaries
            )
            if boundary_name not in authorized:
                yield f"{label} observation boundary is outside participant '{participant_name}'"
    for spec in scenario.behavior_specifications.values():
        if action_name not in _resolved_names(spec.action_contract_refs, "action_contracts", scenario.action_contracts):
            continue
        authorized = _resolved_names(
            spec.observation_boundary_refs, "observation_boundaries", scenario.observation_boundaries
        )
        if boundary_name not in authorized:
            yield f"{label} observation boundary is outside its behavior specification"
        if spec.autonomous_execution is not None:
            selected = _resolve_section_ref(
                spec.autonomous_execution.observation_boundary_ref,
                "observation_boundaries",
                scenario.observation_boundaries,
            )
            if selected is not None and selected != boundary_name:
                yield f"{label} must use its autonomous policy's observation boundary"


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
