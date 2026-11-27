"""Exact control-context factors through ADR-094 participant configuration."""

from dataclasses import replace

import pytest
from raes.scenario import ExpandedScenario
from raes.validator import SemanticValidator
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import AdmittedTrialPlanModel, ParticipantImplementationManifestModel
from raes_processor.trial_compiler import compile_admitted_trial_plan
from test_dsl_118_control_context import asset_payload, selection
from test_issue_1626_trial_participant_bindings import _participant_request, _with_spec


def context_request(*, validator: bool = True):
    request = _participant_request()
    key, manifest = next(iter(request.participant_manifests.items()))
    # The SDL participant address is explicit, not inferred from an implementation label.
    participant_address = "agents.red"
    new_key = (participant_address, *key[1:])
    family_payload = request.family.model_dump(mode="python")
    family_payload["agents"] = {"red": {"role": "red"}}
    assets = {version: asset_payload(version=version) for version in ("one", "two")}
    family_payload["control_context_assets"] = assets
    family = ExpandedScenario.model_validate(family_payload)
    SemanticValidator(family).validate()
    family._set_semantic_validated(True)
    request = request.with_family(family)
    manifest_payload = manifest.model_dump(mode="json")
    registry = manifest_payload["configuration_registry"]
    registry["targets"].pop("policy.temperature")
    registry["targets"]["context.briefing"] = {
        "target_id": "context.briefing",
        "value_type": "string",
        "allowed_value_kinds": ["literal"],
        "sensitivity": "restricted",
        "control_context": {
            "slot_id": "briefing",
            "references": {
                "control_context_assets." + name: selection(asset)["asset_ref"] for name, asset in assets.items()
            },
        },
    }
    manifest = ParticipantImplementationManifestModel.model_validate(manifest_payload)
    refs = [
        ref.model_copy(
            update={
                "participant_address": participant_address,
                "manifest_digest": canonical_json_digest(manifest.model_dump(mode="json")),
            }
        )
        for ref in request.apparatus.participant_manifest_refs
    ]
    payload = request.experiment.model_dump(mode="json")
    for descriptor in payload["binding_descriptors"]["descriptors"]:
        descriptor["target"].update(participant_address=participant_address, target_id="context.briefing")
        descriptor["value_type"] = "string"
        descriptor["value"]["value"] = "control_context_assets." + (
            "one" if descriptor["value"]["value"] == 0 else "two"
        )
    for assignment in payload["run_plan"]["allocation"]["condition_assignments"].values():
        assignment["required_bindings"] = [
            d
            for d in payload["binding_descriptors"]["descriptors"]
            if d["source_condition_id"] == assignment["condition_id"]
        ]
    validators = {}
    if validator:
        from raes.participant_control_context import SDLControlContextConfigurationValidator

        validators[(registry["owner"]["validator_id"], registry["owner"]["validator_version"])] = (
            SDLControlContextConfigurationValidator(family)
        )
    request = replace(
        request,
        participant_manifests={new_key: manifest},
        apparatus=request.apparatus.model_copy(update={"participant_manifest_refs": refs}),
        participant_configuration_validators=validators,
    )
    return _with_spec(request, payload)


def test_factor_selection_is_exact_and_retained_in_sealed_configuration() -> None:
    request = context_request()
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    restored = AdmittedTrialPlanModel.model_validate_json(result.plan.model_dump_json())
    selected_versions = set()
    for entry in restored.entries.values():
        configuration = entry.participant_configurations[0]
        value = next(value for value in configuration.configuration.values if value.target_id == "context.briefing")
        selected = value.control_context_selection
        assert selected.slot_id == "briefing"
        assert selected.declaration_ref == value.value.value
        assert (
            selected.asset_ref.asset_digest
            == selection(
                request.family.control_context_assets[selected.asset_ref.asset_version].model_dump(mode="json")
            )["asset_ref"]["asset_digest"]
        )
        selected_versions.add(selected.asset_ref.asset_version)
    assert selected_versions == {"one", "two"}
    assert request.family.agents["red"].control_context == {}


@pytest.mark.parametrize("mutation", ["absent-validator", "stale-descriptor", "wrong-scope", "direct-conflict"])
def test_invalid_context_factor_refuses_whole_plan(mutation: str) -> None:
    request = context_request(validator=mutation != "absent-validator")
    payload = request.family.model_dump(mode="python")
    if mutation == "stale-descriptor":
        payload["control_context_assets"]["one"]["retention_policy_ref"] = "changed-retention"
    elif mutation == "wrong-scope":
        payload["agents"]["red"]["role"] = "green"
    elif mutation == "direct-conflict":
        payload["agents"]["red"]["control_context"] = {"briefing": selection(asset_payload(), "one")}
    if mutation != "absent-validator":
        from raes.participant_control_context import SDLControlContextConfigurationValidator

        family = ExpandedScenario.model_validate(payload)
        SemanticValidator(family).validate()
        family._set_semantic_validated(True)
        request = request.with_family(family)
        request = replace(
            request,
            participant_configuration_validators={
                ("participant-config", "1"): SDLControlContextConfigurationValidator(family)
            },
        )
    result = compile_admitted_trial_plan(request)
    assert result.plan is None
    assert {diagnostic.code for diagnostic in result.diagnostics} == {
        "trial-compiler.participant-configuration-rejected"
    }
    assert "changed-retention" not in repr(result.diagnostics)


def test_trial_scope_uses_the_concrete_participant_role() -> None:
    from raes.participant_control_context import SDLControlContextConfigurationValidator

    request = context_request()
    payload = request.family.model_dump(mode="python")
    payload["variables"]["role_choice"] = {"type": "string", "default": "green"}
    payload["agents"]["red"]["role"] = "${role_choice}"
    family = ExpandedScenario.model_validate(payload)
    SemanticValidator(family).validate()
    family._set_semantic_validated(True)
    request = request.with_family(family)
    request = replace(
        request,
        participant_configuration_validators={
            ("participant-config", "1"): SDLControlContextConfigurationValidator(family)
        },
    )
    result = compile_admitted_trial_plan(request)
    assert result.plan is None
    assert {diagnostic.code for diagnostic in result.diagnostics} == {
        "trial-compiler.participant-configuration-rejected"
    }


def test_public_trial_result_passes_exact_selection_to_run_producer() -> None:
    from raes_processor.trial_realization import realize_admitted_trial_entry
    from test_sce_002_trial_realization import _realization_inputs, _request_with_processor

    request = context_request()
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
    restored = AdmittedTrialPlanModel.model_validate_json(result.plan.model_dump_json())
    for entry in restored.entries.values():
        realized = realize_admitted_trial_entry(
            inputs=_realization_inputs(request, restored, request.task), plan_entry_id=entry.plan_entry_id
        )
        assert realized.participant_configurations == tuple(entry.participant_configurations)
        selected = next(
            value.control_context_selection
            for value in realized.participant_configurations[0].configuration.values
            if value.control_context_selection
        )
        assert selected.asset_ref.asset_version in {"one", "two"}
        assert selected.declaration_ref == "control_context_assets." + selected.asset_ref.asset_version


@pytest.mark.parametrize("phase", ["context", "complete"])
def test_owner_cannot_mutate_the_admitted_pin_in_place(phase: str) -> None:
    from raes.participant_control_context import SDLControlContextConfigurationValidator

    class MutatingOwner(SDLControlContextConfigurationValidator):
        def validate_control_context_reference(self, participant_address, selection):
            super().validate_control_context_reference(participant_address, selection)
            if phase == "context":
                selection.asset_ref.asset_digest = "sha256:" + "f" * 64

        def validate_and_normalize(self, configuration):
            if phase == "complete":
                for value in configuration.values:
                    if value.control_context_selection is not None:
                        value.control_context_selection.asset_ref.asset_digest = "sha256:" + "f" * 64
            return configuration

    request = context_request()
    manifest_before = next(iter(request.participant_manifests.values())).model_dump(mode="json")
    request = replace(
        request, participant_configuration_validators={("participant-config", "1"): MutatingOwner(request.family)}
    )
    result = compile_admitted_trial_plan(request)
    assert result.plan is None
    assert {diagnostic.code for diagnostic in result.diagnostics} == {
        "trial-compiler.participant-configuration-rejected"
    }
    assert next(iter(request.participant_manifests.values())).model_dump(mode="json") == manifest_before


@pytest.mark.parametrize("mutation", ["newline-slot", "newline-reference", "private-reference"])
def test_context_domain_model_and_schema_reject_invalid_names(mutation: str) -> None:
    from jsonschema import Draft202012Validator
    from pydantic import ValidationError
    from raes_contracts.contracts.experiment_bindings import ParticipantControlContextTargetModel

    domain = {
        "slot_id": "briefing",
        "references": {"control_context_assets.one": selection(asset_payload())["asset_ref"]},
    }
    if mutation == "newline-slot":
        domain["slot_id"] += "\n"
    else:
        reference = (
            "control_context_assets.one\n"
            if mutation == "newline-reference"
            else "control_context_assets.lib.__private.one"
        )
        domain["references"] = {reference: selection(asset_payload())["asset_ref"]}
    with pytest.raises(ValidationError):
        ParticipantControlContextTargetModel.model_validate(domain)
    assert list(Draft202012Validator(ParticipantControlContextTargetModel.model_json_schema()).iter_errors(domain))
