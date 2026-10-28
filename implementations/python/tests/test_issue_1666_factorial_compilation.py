"""Typed factorial effects through compilation, reconstruction and realization."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes.canonical import canonical_sdl_digest
from raes.participant_control_context import SDLControlContextConfigurationValidator
from raes_contracts.canonical import canonical_json_bytes, canonical_json_digest
from raes_contracts.contracts import (
    ExperimentReferenceModel,
    ExperimentSpecModel,
    ParticipantImplementationManifestModel,
)
from raes_contracts.participant_control_context import control_context_asset_reference
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_realization import instantiate_admitted_trial_entry, realize_admitted_trial_entry
from test_dsl_118_trial_control_context import context_request
from test_issue_1625_structural_variation import _family
from test_sce_002_trial_realization import _realization_inputs, _request_with_processor


def _with_design(request, payload):
    payload = deepcopy(payload)
    payload.pop("binding_descriptors", None)
    payload["run_plan"].pop("allocation", None)
    spec = ExperimentSpecModel.model_validate(payload)
    request = request.with_experiment(spec)
    descriptor_ref = request.input_refs.binding_descriptor_set_ref
    if spec.binding_descriptors is not None:
        descriptor_ref = ExperimentReferenceModel(
            ref_kind="other",
            ref_id="factorial-bindings",
            ref_digest=canonical_json_digest(spec.binding_descriptors.model_dump(mode="json")),
        )
    else:
        descriptor_ref = None
    return replace(
        request,
        input_refs=request.input_refs.model_copy(update={"binding_descriptor_set_ref": descriptor_ref}),
    )


def _treatment_request(*, multiple=False, same_prompts=False):
    request = context_request()
    family_payload = request.family.model_dump(mode="python", by_alias=True)
    family_payload["nodes"]["relay-47"] = deepcopy(family_payload["nodes"]["primary"])
    family_payload["nodes"]["relay-47"]["runtime"] = {
        "scheduled_jobs": [{"scheduled_job_id": "audit"}, {"scheduled_job_id": "rotate"}]
    }
    family_payload["infrastructure"]["relay-47"] = {"count": 1}
    family_payload["variation_points"]["deployment-shape"] = {
        "kind": "alternative",
        "target": {"kind": "structural", "owner": "relay-47", "slot": "nodes.presence"},
        "alternatives": {
            "offline": {"kind": "node-presence", "present": False},
            "instrumented": {
                "kind": "node-presence",
                "present": True,
                "inventory": {"nodes.runtime.scheduled_jobs": ["nodes.relay-47.runtime.scheduled_jobs.audit"]},
            },
        },
    }
    if not same_prompts:
        family_payload["control_context_assets"]["two"]["content"]["checksum"]["value"] = "b" * 64
    if multiple:
        family_payload["agents"]["observer-9"] = {"role": "blue"}
    family = _family(family_payload)
    request = request.with_family(family)
    key, manifest = next(iter(request.participant_manifests.items()))
    manifest_payload = manifest.model_dump(mode="json")
    registry = manifest_payload["configuration_registry"]
    registry["targets"]["policy.model"] = {
        "target_id": "policy.model",
        "value_type": "string",
        "allowed_value_kinds": ["literal"],
        "sensitivity": "public",
        "default": {"kind": "literal", "value": "compact"},
    }
    registry["targets"]["context.briefing"]["control_context"]["references"] = {
        "control_context_assets." + name: control_context_asset_reference(asset).model_dump(mode="json")
        for name, asset in family.control_context_assets.items()
    }
    manifest = ParticipantImplementationManifestModel.model_validate(manifest_payload)
    addresses = ["agents.red", "agents.observer-9"] if multiple else ["agents.red"]
    manifests = {(address, *key[1:]): manifest for address in addresses}
    refs = [
        request.apparatus.participant_manifest_refs[0].model_copy(
            update={
                "participant_address": address,
                "manifest_digest": canonical_json_digest(manifest.model_dump(mode="json")),
            }
        )
        for address in addresses
    ]
    request = replace(
        request,
        participant_manifests=manifests,
        apparatus=request.apparatus.model_copy(update={"participant_manifest_refs": refs}),
        participant_configuration_validators={
            ("participant-config", "1"): SDLControlContextConfigurationValidator(family)
        },
    )
    payload = request.experiment.model_dump(mode="json")
    payload["factors"] = {}
    effects = {}
    for index, address in enumerate(addresses):
        for suffix, target_id, levels in (
            ("engine", "policy.model", {"small": "compact", "wide": "large"}),
            (
                "brief",
                "context.briefing",
                {"plain": "control_context_assets.one", "revised": "control_context_assets.two"},
            ),
        ):
            factor = f"operator-{index}-{suffix}"
            payload["factors"][factor] = {"name": factor, "factor_kind": "treatment", "levels": list(levels)}
            effects[factor] = {
                level: {
                    "bindings": [
                        {
                            "target": {
                                "plane": "participant-implementation",
                                "participant_address": address,
                                "implementation_name": key[1],
                                "implementation_version": key[2],
                                "manifest_version": key[3],
                                "target_id": target_id,
                            },
                            "value_type": "string",
                            "value": {"kind": "literal", "value": value},
                            "owner": registry["owner"],
                        }
                    ]
                }
                for level, value in levels.items()
            }
    payload["factors"]["terrain-x"] = {
        "name": "Optional relay",
        "factor_kind": "treatment",
        "levels": ["isolated", "observed"],
    }
    effects["terrain-x"] = {
        level: {
            "selections": [
                {
                    "target": {
                        "plane": "scenario",
                        "scenario_family_id": family.name,
                        "variation_point_id": "deployment-shape",
                        "target_id": "nodes.relay-47.presence",
                    },
                    "scenario_family_digest": canonical_sdl_digest(family).value,
                    "owner": {
                        "contract_id": "sdl-authoring-input-v1",
                        "contract_version": "1",
                        "validator_id": "raes-selected-scenario",
                        "validator_version": "1",
                    },
                    "outcome": {"kind": "member", "member_id": member},
                }
            ]
        }
        for level, member in (("isolated", "offline"), ("observed", "instrumented"))
    }
    payload["factorial_design"] = {
        "profile": "factorial-treatments-v1",
        "factor_ids": list(effects),
        "level_effects": effects,
        "target_runs_per_condition": 1 if multiple else 2,
        "condition_bound": 32,
    }
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
    return _with_design(request, payload)


@pytest.mark.parametrize("multiple", [False, True])
def test_crossed_models_prompts_and_structure_retain_every_effect(multiple):
    request = _treatment_request(multiple=multiple)
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    plan = result.plan
    assert len(plan.entries) == (32 if multiple else 16)
    assert plan.profiles.treatment_profile == "factorial-treatments-v1"
    seen = set()
    for entry in plan.entries.values():
        assignment = request.experiment.run_plan.allocation.condition_assignments[entry.coordinate.condition_id]
        assert [
            selection.treatment for selection in entry.selections if selection.treatment
        ] == assignment.required_selections
        assert len(entry.participant_configurations) == (2 if multiple else 1)
        selected = instantiate_admitted_trial_entry(plan=plan, plan_entry_id=entry.plan_entry_id, family=request.family)
        present = "relay-47" in selected.nodes
        assert present == (assignment.factor_levels["terrain-x"] == "observed")
        if present:
            assert [job.scheduled_job_id for job in selected.nodes["relay-47"].runtime.scheduled_jobs] == ["audit"]
        assert selected.content["payload"].path == "/opt/a"
        configurations = []
        for configuration in entry.participant_configurations:
            values = {value.target_id: value for value in configuration.configuration.values}
            assert values["policy.mode"].origin == "default"
            assert values["context.briefing"].control_context_selection.asset_ref.asset_digest
            configurations.append((values["policy.model"].value.value, values["context.briefing"].value.value))
        seen.add((present, tuple(configurations)))
    assert len(seen) == (32 if multiple else 8)


def test_crossed_plan_reload_reconstruction_and_public_realization():
    from raes_contracts.admitted_trial_plan_ingress import parse_admitted_trial_plan_json

    request = _treatment_request()
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
    plan = parse_admitted_trial_plan_json(result.plan.model_dump_json())
    replay = compile_admitted_trial_plan(request, coordinate_partitions=(tuple(reversed(range(16))),))
    assert replay.plan is not None, replay.diagnostics
    assert canonical_json_bytes(plan.model_dump(mode="json")) == canonical_json_bytes(
        replay.plan.model_dump(mode="json")
    )
    entry = next(
        entry
        for entry in plan.entries.values()
        if any(selection.treatment and selection.outcome.member_id == "offline" for selection in entry.selections)
    )
    realized = realize_admitted_trial_entry(
        inputs=_realization_inputs(request, plan, request.task), plan_entry_id=entry.plan_entry_id
    )
    assert realized.participant_configurations == tuple(entry.participant_configurations)
    trial = realized.instantiated.instantiation_provenance.trial
    assert any(selection.record.get("treatment") for selection in trial.selections)


def test_distinct_prompt_descriptor_pins_with_equal_content_are_not_new_effects():
    result = compile_admitted_trial_plan(_treatment_request(same_prompts=True))
    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.factorial-conditions-indistinguishable"


@pytest.mark.parametrize("field", ["owner", "family", "digest", "target", "point", "member"])
def test_typed_owner_admission_rejects_the_whole_design(field):
    request = _treatment_request()
    payload = request.experiment.model_dump(mode="json")
    selection = payload["factorial_design"]["level_effects"]["terrain-x"]["isolated"]["selections"][0]
    if field == "owner":
        selection["owner"]["validator_id"] = "private-canary"
    elif field == "family":
        selection["target"]["scenario_family_id"] = "private-canary"
    elif field == "digest":
        selection["scenario_family_digest"] = "sha256:" + "f" * 64
    elif field in {"point", "target"}:
        selection["target"]["variation_point_id" if field == "point" else "target_id"] = "private-canary"
        if field == "point":
            payload["factorial_design"]["level_effects"]["terrain-x"]["observed"]["selections"][0]["target"][
                "variation_point_id"
            ] = "private-canary"
    else:
        selection["outcome"]["member_id"] = "private-canary"
    result = compile_admitted_trial_plan(_with_design(request, payload))
    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.selection-treatment-rejected"
    assert "private-canary" not in repr(result.diagnostics)


def test_public_example_runs_loader_compiler_readmission_and_one_entry():
    import runpy

    from paths import REPO_ROOT

    example = runpy.run_path(str(REPO_ROOT / "implementations/python/examples/factorial_treatments.py"))
    request = _treatment_request()
    processor = _request_with_processor()
    request = replace(
        request,
        apparatus_manifests=processor.apparatus_manifests,
        apparatus=processor.apparatus.model_copy(
            update={"participant_manifest_refs": request.apparatus.participant_manifest_refs}
        ),
    )
    plan = example["compile_example"](request)
    assert len(plan.entries) == 16
    entry = next(
        entry
        for entry in plan.entries.values()
        if any(selection.treatment and selection.outcome.member_id == "offline" for selection in entry.selections)
    )
    realized = example["realize_example"](
        plan,
        request,
        plan_entry_id=entry.plan_entry_id,
        backend_key=next(key for key in request.apparatus_manifests if key[0] == "backend"),
    )
    assert realized.participant_configurations == tuple(entry.participant_configurations)
    assert "relay-47" not in realized.instantiated.nodes


def test_typed_aliases_remain_canonical_through_source_aware_realization():
    request = _treatment_request()
    processor = _request_with_processor()
    key, manifest = next(iter(request.participant_manifests.items()))
    manifest_payload = manifest.model_dump(mode="json")
    manifest_payload["configuration_registry"]["targets"]["policy.model"]["aliases"] = ["model-choice"]
    manifest = ParticipantImplementationManifestModel.model_validate(manifest_payload)
    reference = request.apparatus.participant_manifest_refs[0].model_copy(
        update={"manifest_digest": canonical_json_digest(manifest.model_dump(mode="json"))}
    )
    request = replace(
        request,
        participant_manifests={key: manifest},
        apparatus_manifests=processor.apparatus_manifests,
        apparatus=processor.apparatus.model_copy(update={"participant_manifest_refs": [reference]}),
    )
    payload = request.experiment.model_dump(mode="json")
    for effects in payload["factorial_design"]["level_effects"]["operator-0-engine"].values():
        effects["bindings"][0]["target"]["target_id"] = "model-choice"
    request = _with_design(request, payload)
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    plan = result.plan
    entry = next(
        entry
        for entry in plan.entries.values()
        if any(selection.treatment and selection.outcome.member_id == "offline" for selection in entry.selections)
    )
    inputs = replace(
        _realization_inputs(request, plan, request.task), participant_manifests=request.participant_manifests
    )
    realized = realize_admitted_trial_entry(inputs=inputs, plan_entry_id=entry.plan_entry_id)
    assert realized.participant_configurations == tuple(entry.participant_configurations)
    assert {binding.descriptor.target.target_id for binding in entry.bindings} == {"policy.model", "context.briefing"}
