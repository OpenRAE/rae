"""Original admitted parallel allocation for separate synthetic execution hosts."""

from dataclasses import replace

from issue_1629_trial_fixture import factorial_inputs
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import AdmittedTrialPlanModel
from test_sce_006_batch_scheduler import _proof


def parallel_inputs(*, omit_first_from_proof=False):
    request, inputs, target = factorial_inputs()
    # This is the original admission fixture, before any coordinator or worker
    # exists. Its cleanup ranges are independently owned synthetic resources.
    payload = inputs.plan.model_dump(mode="json")
    for index, cleanup in enumerate(payload["cleanup_plans"].values()):
        for boundary in cleanup["resource_boundaries"].values():
            boundary["resource_refs"] = [f"range:synthetic-owner-{index}"]
    covered = list(payload["entries"])[1:] if omit_first_from_proof else list(payload["entries"])
    payload["isolation_proof"] = _proof(covered).model_dump(mode="json")
    payload["plan_digest"] = canonical_json_digest(
        {key: value for key, value in payload.items() if key != "plan_digest"}
    )
    plan = AdmittedTrialPlanModel.model_validate(payload)
    return request, replace(inputs, plan=plan), target


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
