"""Compile authored typed treatments using previously acquired trusted inputs.

The caller supplies family, manifests, task, capture, and execution authority.
This example acquires no services, credentials, content, or backend resources.
"""

from __future__ import annotations

import json
from dataclasses import replace

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import AdmittedTrialPlanModel, ExperimentReferenceModel
from raes_contracts.experiment_bindings import ApparatusManifestKey
from raes_contracts.experiment_spec import parse_experiment_spec
from raes_processor.trial_compiler import (
    TrialCompilationRequest,
    compile_admitted_trial_plan,
    readmit_admitted_trial_plan,
)
from raes_processor.trial_realization import TrialRealization, TrialRealizationInputs, realize_admitted_trial_entry


def compile_example(request: TrialCompilationRequest) -> AdmittedTrialPlanModel:
    """Round-trip compact author intent and compile every requested combination."""
    compact = request.experiment.model_dump(mode="json")
    compact.pop("binding_descriptors", None)
    compact["run_plan"].pop("allocation", None)
    experiment = parse_experiment_spec(json.dumps(compact))
    request = request.with_experiment(experiment)
    descriptors = experiment.binding_descriptors
    reference = (
        None
        if descriptors is None
        else ExperimentReferenceModel(
            ref_kind="other",
            ref_id="example-treatment-bindings",
            ref_digest=canonical_json_digest(descriptors.model_dump(mode="json")),
        )
    )
    request = replace(
        request, input_refs=request.input_refs.model_copy(update={"binding_descriptor_set_ref": reference})
    )
    result = compile_admitted_trial_plan(request)
    if result.plan is None:
        # The public diagnostic codes contain no configuration values.
        raise ValueError(tuple(diagnostic.code for diagnostic in result.diagnostics))
    # Acquire these original inputs and expected pins independently of any
    # candidate plan before using this check for an externally supplied plan.
    return readmit_admitted_trial_plan(result.plan, request=request)


def realize_example(
    plan: AdmittedTrialPlanModel,
    request: TrialCompilationRequest,
    *,
    plan_entry_id: str,
    backend_key: ApparatusManifestKey,
) -> TrialRealization:
    """Realize one entry into processor plans without executing a model or backend."""
    return realize_admitted_trial_entry(
        inputs=TrialRealizationInputs(
            plan=plan,
            family=request.family,
            experiment=request.experiment,
            task=request.task,
            capture_specs=request.capture_specs,
            apparatus_manifests=request.apparatus_manifests,
            participant_manifests=request.participant_manifests,
            realization_envelope=request.realization_envelope,
            backend_key=backend_key,
        ),
        plan_entry_id=plan_entry_id,
    )
