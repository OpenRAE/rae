"""Scenario needs select existing optional factory components before creation."""

from __future__ import annotations


def scenario_component_options(scenario: object) -> dict[str, bool]:
    """Select services for the whole declared interaction, including evaluation."""
    from raes_contracts.errors import InvalidInputError
    from raes_processor.compiler import compile_scenario_runtime_model
    from raes_processor.models import RuntimeModel

    model = scenario if isinstance(scenario, RuntimeModel) else compile_scenario_runtime_model(scenario)
    if any(item.is_error for item in model.diagnostics):
        raise InvalidInputError("component selection requires a valid compiled scenario")
    return {
        "with_orchestrator": any(
            (model.injects, model.inject_bindings, model.events, model.scripts, model.stories, model.workflows)
        ),
        "with_evaluator": any((model.condition_bindings, model.propositions, model.assertions, model.objectives)),
        "with_participant_runtime": bool(model.behavior_specifications or model.participant_behaviors),
        "with_time": bool(model.time_model.clocks),
        "with_observation": bool(model.observation_demands or model.capture_demands),
    }


def participant_temporal_probe_manager(target: object, *, stochastic_controls: object = ()) -> object:
    """Create the runtime used by the finite temporal conformance probe."""
    from .manager import RuntimeManager

    return RuntimeManager(target, stochastic_controls=stochastic_controls)
