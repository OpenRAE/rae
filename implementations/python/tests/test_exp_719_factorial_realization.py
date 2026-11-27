"""The public one-entry seam exposes the admitted participant configurations."""

from dataclasses import replace

from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_realization import realize_admitted_trial_entry
from test_exp_719_factorial_allocation import _factorial_request
from test_sce_002_trial_realization import _realization_inputs, _request_with_processor


def test_public_realization_preserves_complete_participant_configuration() -> None:
    request = _factorial_request()
    processor = _request_with_processor()
    request = replace(
        request,
        apparatus_manifests=processor.apparatus_manifests,
        apparatus=processor.apparatus.model_copy(
            update={"participant_manifest_refs": request.apparatus.participant_manifest_refs}
        ),
    )
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    entry = next(iter(result.plan.entries.values()))
    realized = realize_admitted_trial_entry(
        inputs=_realization_inputs(request, result.plan, request.task), plan_entry_id=entry.plan_entry_id
    )
    assert realized.participant_configurations == tuple(entry.participant_configurations)
