"""Scenario needs select existing optional factory components before creation."""

from __future__ import annotations


def scenario_component_options(scenario: object) -> dict[str, bool]:
    """Select services for the whole declared interaction, including evaluation."""
    from raes_processor.compiler import compile_scenario_runtime_model
    from raes_processor.models import RuntimeModel

    model = scenario if isinstance(scenario, RuntimeModel) else compile_scenario_runtime_model(scenario)
    if any(item.is_error for item in model.diagnostics):
        raise ValueError("component selection requires a valid compiled scenario")
    return {
        "with_orchestrator": bool(
            model.injects or model.inject_bindings or model.events or model.scripts or model.stories or model.workflows
        ),
        "with_evaluator": bool(model.condition_bindings or model.propositions or model.assertions or model.objectives),
        "with_participant_runtime": bool(model.behavior_specifications or model.participant_behaviors),
        "with_time": bool(model.time_model.clocks),
        "with_observation": bool(model.observation_demands or model.capture_demands),
    }


def participant_temporal_probe_manager(target: object, *, stochastic_controls: object = ()) -> object:
    """Create the runtime used by the finite temporal conformance probe."""
    from .manager import RuntimeManager

    return RuntimeManager(target, stochastic_controls=stochastic_controls)
