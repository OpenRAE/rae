"""Original admitted parallel allocation for separate synthetic execution hosts."""

from issue_1629_trial_fixture import factorial_inputs


def with_parallelism(request, intent):
    """Author ``trial_parallelism`` on the family and re-pin factorial selections to it."""
    from pydantic import TypeAdapter
    from raes.canonical import canonical_sdl_digest
    from raes_contracts.trial_parallelism import TrialParallelismModel
    from test_issue_1666_factorial_compilation import _with_design

    family = request.family.model_copy(
        update={"trial_parallelism": TypeAdapter(TrialParallelismModel).validate_python(intent)}
    )
    request = request.with_family(family)
    design = request.experiment.model_dump(mode="json")
    for levels in design["factorial_design"]["level_effects"].values():
        for effect in levels.values():
            for selection in effect.get("selections", []):
                selection["scenario_family_digest"] = canonical_sdl_digest(family).value
    return _with_design(request, design)


def parallel_inputs(*, intent=None, transform=None):
    """Compile the original factorial admission with authored trial parallelism (open by default)."""
    intent = intent or {"posture": "open"}

    def authored(request):
        return with_parallelism(transform(request) if transform else request, intent)

    return factorial_inputs(authored)


def replacement_inputs():
    """Author and compile one original condition, with one permitted replacement."""
    from issue_1630_record_fixture import record_request
    from test_issue_1629_experiment_replacement import replacement_request
    from test_issue_1666_factorial_compilation import _with_design

    def authored(request):
        request = record_request(replacement_request(request))
        design = request.experiment.model_dump(mode="json")
        for key, factor in design["factors"].items():
            first = factor["levels"][0]
            factor["levels"] = [first]
            effects = design["factorial_design"]["level_effects"][key]
            design["factorial_design"]["level_effects"][key] = {first: effects[first]}
        design["factorial_design"]["target_runs_per_condition"] = 1
        return _with_design(request, design)

    return factorial_inputs(authored)
