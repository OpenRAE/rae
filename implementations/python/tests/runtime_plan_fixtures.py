"""Pure processor planning for tests that compose a separate execution owner."""

from dataclasses import replace

from raes_contracts.planning import PlanScope
from raes_processor.compiler import compile_scenario_runtime_model
from raes_processor.planner import plan
from raes_runtime.manager_plan_admission import reference_participant_driver_diagnostics


def plan_for_target(target, scenario, snapshot=None, *, profile_authority=None, parameters=None):
    model = compile_scenario_runtime_model(scenario, profile_authority=profile_authority, parameters=parameters)
    planned = plan(
        model,
        target.manifest,
        snapshot,
        scope=PlanScope(target_name=target.name),
        profile_context=getattr(target.provisioner, "domain_profile_context", None),
    )
    return replace(planned, diagnostics=[*planned.diagnostics, *reference_participant_driver_diagnostics(model)])
