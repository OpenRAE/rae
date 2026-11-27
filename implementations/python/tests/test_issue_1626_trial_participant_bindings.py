"""Explicit conditions retain participant configuration without scenario bindings."""

from dataclasses import replace

import pytest
from raes_contracts.canonical import canonical_json_bytes, canonical_json_digest
from raes_contracts.contracts import (
    AdmittedTrialPlanModel,
    ExperimentSpecModel,
    ParticipantImplementationManifestModel,
)
from raes_processor.trial_compiler import compile_admitted_trial_plan
from test_exp_719_factorial_allocation import _factorial_request
from test_issue_1015_mixed_staged_trial_admission import _mixed_request


def _with_spec(request, payload):
    spec = ExperimentSpecModel.model_validate(payload)
    request = request.with_experiment(spec)
    return replace(
        request,
        input_refs=request.input_refs.model_copy(
            update={
                "binding_descriptor_set_ref": request.input_refs.binding_descriptor_set_ref.model_copy(
                    update={"ref_digest": canonical_json_digest(spec.binding_descriptors.model_dump(mode="json"))}
                )
            }
        ),
    )


def _participant_request(*, mixed: bool = False):
    request = _factorial_request()
    payload = request.experiment.model_dump(mode="json")
    payload.pop("factorial_design")
    allocation = payload["run_plan"]["allocation"]
    allocation["condition_assignments"] = {
        key: assignment
        for key, assignment in allocation["condition_assignments"].items()
        if assignment["factor_levels"]["path"] == "a"
    }
    allocation["compared_conditions"] = sorted(allocation["condition_assignments"])
    for assignment in allocation["condition_assignments"].values():
        assignment["required_bindings"] = [
            binding
            for binding in assignment["required_bindings"]
            if binding["target"]["plane"] == "participant-implementation"
        ]
    payload["binding_descriptors"]["descriptors"] = [
        binding
        for binding in payload["binding_descriptors"]["descriptors"]
        if binding["target"]["plane"] == "participant-implementation"
        and binding["source_condition_id"] in allocation["condition_assignments"]
    ]
    payload["run_plan"]["selection_policies"] = {
        "fixed-path": {
            "kind": "fixed",
            "policy_id": "fixed-path",
            "purpose": "fixed-configuration",
            "point_ref": "payload-path",
            "outcome": {"kind": "literal", "value": "/opt/a"},
            "output_bound": 1,
        }
    }
    request = _with_spec(request, payload)
    if mixed:
        request = _mixed_request(base_request=request)
        request = replace(
            request,
            realization_assignments={
                key: binding.model_copy(
                    update={"participant_manifest_refs": list(request.apparatus.participant_manifest_refs)}
                )
                for key, binding in request.realization_assignments.items()
            },
        )
    return request


@pytest.mark.parametrize("mixed", [False, True])
def test_explicit_conditions_carry_complete_participant_configuration(mixed: bool) -> None:
    request = _participant_request(mixed=mixed)
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    plan = result.plan
    allocation = request.experiment.run_plan.allocation
    assert len(plan.entries) == 4
    digests = {}
    for entry in plan.entries.values():
        assignment = allocation.condition_assignments[entry.coordinate.condition_id]
        assert not assignment.required_refs
        assert not assignment.required_parameters
        assert [binding.descriptor for binding in entry.bindings] == assignment.required_bindings
        assert len(entry.participant_configurations) == 1
        configuration = entry.participant_configurations[0]
        values = {value.target_id: value for value in configuration.configuration.values}
        assert values["policy.mode"].value.value == "safe"
        assert values["policy.mode"].origin == "default"
        assert values["policy.temperature"].origin == "override"
        assert values["policy.temperature"].value.value == (0.0 if assignment.factor_levels["agent"] == "cold" else 1.0)
        assert configuration.configuration_digest == canonical_json_digest(
            configuration.configuration.model_dump(mode="json")
        )
        digests[assignment.factor_levels["agent"]] = configuration.configuration_digest
        assert entry.selections[0].outcome.value == "/opt/a"
    assert digests["cold"] != digests["warm"]
    restored = AdmittedTrialPlanModel.model_validate_json(plan.model_dump_json())
    assert restored.model_dump(mode="json") == plan.model_dump(mode="json")
    replay = compile_admitted_trial_plan(request, coordinate_partitions=((3, 1), (2, 0)))
    assert replay.plan is not None, replay.diagnostics
    assert canonical_json_bytes(replay.plan.model_dump(mode="json")) == canonical_json_bytes(
        plan.model_dump(mode="json")
    )


@pytest.mark.parametrize("mixed", [False, True])
@pytest.mark.parametrize(
    "mutation", ["unknown-target", "wrong-owner", "missing-required", "duplicate-alias", "binding-limit"]
)
def test_participant_binding_failures_refuse_the_entire_plan(mixed: bool, mutation: str) -> None:
    request = _participant_request(mixed=mixed)
    key, manifest = next(iter(request.participant_manifests.items()))
    manifest_payload = manifest.model_dump(mode="json")
    payload = request.experiment.model_dump(mode="json")
    descriptor = payload["binding_descriptors"]["descriptors"][0]
    expected = "trial-compiler.binding-target-rejected"
    if mutation == "unknown-target":
        descriptor["target"]["target_id"] = "unknown-target"
    elif mutation == "wrong-owner":
        descriptor["owner"]["validator_id"] = "wrong-owner"
    elif mutation == "missing-required":
        manifest_payload["configuration_registry"]["targets"]["policy.mode"].pop("default")
        expected = "trial-compiler.participant-configuration-rejected"
    else:
        duplicate = {**descriptor, "binding_id": descriptor["binding_id"] + "-extra"}
        if mutation == "duplicate-alias":
            manifest_payload["configuration_registry"]["targets"]["policy.temperature"]["aliases"] = ["temperature"]
            duplicate["target"] = {**descriptor["target"], "target_id": "temperature"}
        else:
            duplicate["target"] = {**descriptor["target"], "target_id": "policy.mode"}
            duplicate["value_type"] = "string"
            duplicate["value"] = {"kind": "literal", "value": "custom"}
            request = replace(request, limits=request.limits.model_copy(update={"max_bindings_per_entry": 1}))
            expected = "trial-compiler.binding-limit-exceeded"
        payload["binding_descriptors"]["descriptors"].append(duplicate)
    manifest = ParticipantImplementationManifestModel.model_validate(manifest_payload)
    references = [
        ref.model_copy(update={"manifest_digest": canonical_json_digest(manifest.model_dump(mode="json"))})
        for ref in request.apparatus.participant_manifest_refs
    ]
    request = replace(
        request,
        participant_manifests={key: manifest},
        apparatus=request.apparatus.model_copy(update={"participant_manifest_refs": references}),
        realization_assignments={
            key: binding.model_copy(update={"participant_manifest_refs": references})
            for key, binding in request.realization_assignments.items()
        },
    )
    result = compile_admitted_trial_plan(_with_spec(request, payload))
    assert result.plan is None
    assert [diagnostic.code for diagnostic in result.diagnostics] == [expected]


@pytest.mark.parametrize("mixed", [False, True])
def test_owner_rejection_does_not_expose_configuration_or_partial_output(mixed: bool) -> None:
    class RejectConfiguration:
        def validate_and_normalize(self, configuration):
            raise ValueError("private-owner-error-sentinel")

    request = _participant_request(mixed=mixed)
    request = replace(
        request, participant_configuration_validators={("participant-config", "1"): RejectConfiguration()}
    )
    result = compile_admitted_trial_plan(request)
    assert result.plan is None
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "trial-compiler.participant-configuration-rejected"
    ]
    assert "private-owner-error-sentinel" not in repr(result.diagnostics)
