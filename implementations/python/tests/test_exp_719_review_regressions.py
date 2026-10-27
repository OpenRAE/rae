"""Admission regressions for effective treatments and owner identity joins."""

from dataclasses import replace

import pytest
from pydantic import ValidationError
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    AdmittedTrialPlanModel,
    ExperimentRunModel,
    ExperimentSpecModel,
    ParticipantImplementationManifestModel,
    RealizedBindingProvenanceModel,
)
from raes_contracts.contracts.experiment_conditions import _run_satisfies_condition_assignment
from raes_processor.trial_compiler import compile_admitted_trial_plan
from test_exp_719_factorial_allocation import _factorial_request, _payload
from test_sce_002_trial_realization import _archival_run_and_receipt


@pytest.mark.parametrize("different_participant", [False, True])
def test_different_override_subsets_cannot_hide_identical_effective_treatments(different_participant: bool) -> None:
    request = _factorial_request()
    key, manifest = next(iter(request.participant_manifests.items()))
    payload = manifest.model_dump(mode="json")
    registry = payload["configuration_registry"]["targets"]
    registry["policy.temperature"]["default"] = {"kind": "literal", "value": 0.0}
    registry["policy.other"] = {**registry["policy.temperature"], "target_id": "policy.other"}
    manifest = ParticipantImplementationManifestModel.model_validate(payload)
    reference = request.apparatus.participant_manifest_refs[0].model_copy(
        update={"manifest_digest": canonical_json_digest(manifest.model_dump(mode="json"))}
    )
    manifests = {key: manifest}
    references = [reference]
    payload = _payload()
    for bindings in payload["factorial_design"]["level_bindings"]["agent"].values():
        bindings[0]["target"].update(
            participant_address=key[0],
            implementation_name=key[1],
            implementation_version=key[2],
            manifest_version=key[3],
        )
    warm = payload["factorial_design"]["level_bindings"]["agent"]["warm"][0]
    warm["value"]["value"] = 0.0
    if different_participant:
        other_key = ("participants.other", *key[1:])
        manifests[other_key] = manifest
        references.append(reference.model_copy(update={"participant_address": other_key[0]}))
        warm["target"]["participant_address"] = other_key[0]
    else:
        warm["target"]["target_id"] = "policy.other"
    spec = ExperimentSpecModel.model_validate(payload)
    request = request.with_experiment(spec)
    refs = request.input_refs.model_copy(
        update={
            "binding_descriptor_set_ref": request.input_refs.binding_descriptor_set_ref.model_copy(
                update={"ref_digest": canonical_json_digest(spec.binding_descriptors.model_dump(mode="json"))}
            )
        }
    )
    request = replace(
        request,
        participant_manifests=manifests,
        apparatus=request.apparatus.model_copy(update={"participant_manifest_refs": references}),
        input_refs=refs,
    )
    result = compile_admitted_trial_plan(request)
    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.factorial-conditions-indistinguishable"


@pytest.mark.parametrize("field", ["implementation_identity", "manifest_version"])
def test_resealed_configuration_identity_must_match_selected_manifest(field: str) -> None:
    result = compile_admitted_trial_plan(_factorial_request())
    assert result.plan is not None
    payload = result.plan.model_dump(mode="json")
    entry = next(iter(payload["entries"].values()))
    configuration = entry["participant_configurations"][0]
    if field == "implementation_identity":
        configuration["configuration"][field]["name"] = "foreign-implementation"
    else:
        configuration["configuration"][field] = "participant-implementation-manifest/v2"
    configuration["configuration_digest"] = canonical_json_digest(configuration["configuration"])
    entry["entry_digest"] = canonical_json_digest({key: value for key, value in entry.items() if key != "entry_digest"})
    payload["plan_digest"] = canonical_json_digest(
        {key: value for key, value in payload.items() if key != "plan_digest"}
    )
    with pytest.raises(ValidationError, match="configuration.*identity|configuration.*manifest"):
        AdmittedTrialPlanModel.model_validate(payload)


def test_archival_participant_criterion_requires_matching_selected_configuration() -> None:
    request = _factorial_request()
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None
    entry = next(iter(result.plan.entries.values()))
    assignment = request.experiment.run_plan.allocation.condition_assignments[entry.coordinate.condition_id]
    _, _, baseline, _ = _archival_run_and_receipt()
    payload = baseline.model_dump(mode="json")
    payload["realized_bindings"] = [
        RealizedBindingProvenanceModel(
            descriptor=binding.descriptor,
            origin="selection",
            configuration_digest=entry.participant_configurations[0].configuration_digest
            if binding.descriptor.target.plane == "participant-implementation"
            else None,
        ).model_dump(mode="json")
        for binding in entry.bindings
    ]
    missing = _run_satisfies_condition_assignment(ExperimentRunModel.model_validate(payload), assignment)
    participant = next(
        binding.descriptor
        for binding in entry.bindings
        if binding.descriptor.target.plane == "participant-implementation"
    )
    assert missing == [f"binding:{participant.binding_id}"]
