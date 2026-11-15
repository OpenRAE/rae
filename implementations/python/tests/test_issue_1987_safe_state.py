"""Safe-state declarations retain exact observed proof through admission."""

import copy

import pytest
import yaml
from raes import SDLParseError, SDLValidationError, parse_sdl
from raes_backend_stubs.manifest import create_stub_manifest
from raes_contracts.contracts.plan_projection import provisioning_plan_digest, provisioning_plan_model
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan


def payload(kind="safe-hold"):
    subjects = ["nodes.first", "nodes.second", "nodes.first.services.api"]
    state = {"kind": kind, "assertion_refs": ["safe"]}
    if kind == "continue":
        state["continuing_mode"] = "cooling"
    return {
        "name": "safe-state",
        "nodes": {
            "first": {"type": "compute", "os": "linux", "services": [{"name": "api", "port": 443}]},
            "second": {"type": "compute", "os": "linux"},
        },
        "propositions": {
            "safe": {
                "description": "The admitted safe-state condition holds.",
                "subjects": subjects,
                "basis": "observed_state",
                "predicate": {
                    "kind": "boolean",
                    "property": "safe",
                    "semantic_ref": "urn:example:safe",
                    "expected": True,
                },
                "evidence_requirements": ["readback"],
            }
        },
        "assertions": {"safe": {"proposition": "safe", "role": "postcondition"}},
        "evidence_requirements": {
            "readback": {
                "source_refs": subjects,
                "scope_refs": subjects,
                "window": "safe-state-verification",
                "channel": "api_response",
                "sensitivity": "plain",
                "redaction": "none",
                "integrity": "checksum",
                "retention": "run_lifetime",
                "loss_disclosure": "required",
            }
        },
        "safe_state": {"default": state},
    }


def scenario(value):
    return parse_sdl(yaml.safe_dump(value))


@pytest.mark.parametrize("kind", ["safe-hold", "controlled-stop", "continue"])
def test_all_modes_resolve_each_target_and_survive_native_plan_round_trip(kind):
    from raes_contracts.contracts import ProvisioningPlanModel
    from raes_runtime.control_plane_api_models import _provisioning_plan

    execution = plan(compile_runtime_model(scenario(payload(kind))), create_stub_manifest())
    states = execution.provisioning.safe_states
    assert {state.target_ref for state in states} == {"nodes.first", "nodes.second", "nodes.first.services.api"}
    assert all(state.state.kind == kind and state.governing_scope == "#/" for state in states)
    assert states == execution.orchestration.safe_states == execution.evaluation.safe_states
    assert all(state.proofs["safe"].proposition.basis == "observed_state" for state in states)
    published = provisioning_plan_model(execution.provisioning)
    restored = _provisioning_plan(ProvisioningPlanModel.model_validate_json(published.model_dump_json()))
    assert restored.safe_states == states
    assert provisioning_plan_digest(restored) == provisioning_plan_digest(execution.provisioning)


def test_nearest_scope_replaces_complete_state_and_keeps_sibling():
    value = payload("continue")
    value["safe_state"]["scopes"] = [
        {
            "scope": "/nodes/first",
            "state": {
                "kind": "controlled-stop",
                "assertion_refs": ["safe"],
            },
        }
    ]
    states = compile_runtime_model(scenario(value)).safe_states
    by_target = {state.target_ref: state for state in states}
    assert by_target["nodes.first"].state.kind == "controlled-stop"
    assert by_target["nodes.first.services.api"].state.continuing_mode is None
    assert by_target["nodes.second"].state.continuing_mode == "cooling"


@pytest.mark.parametrize(
    "state",
    [
        {"kind": "stop", "assertion_refs": ["safe"]},
        {"kind": "continue", "assertion_refs": ["safe"]},
        {"kind": "safe-hold", "continuing_mode": "cooling", "assertion_refs": ["safe"]},
        {"kind": "safe-hold", "assertion_refs": []},
        {"kind": "safe-hold", "assertion_refs": ["safe", "safe"]},
    ],
)
def test_invalid_state_is_rejected(state):
    value = payload()
    value["safe_state"]["default"] = state
    with pytest.raises(SDLParseError):
        scenario(value)


@pytest.mark.parametrize("change", ["declared", "precondition", "negative", "any", "subject", "evidence", "missing"])
def test_inadequate_proof_is_rejected(change):
    value = payload()
    if change == "declared":
        value["propositions"]["safe"]["basis"] = "declared_state"
    elif change == "precondition":
        value["assertions"]["safe"]["role"] = "precondition"
    elif change == "negative":
        value["assertions"]["safe"]["polarity"] = "negative"
    elif change == "any":
        value["propositions"]["safe"]["quantifier"] = "any"
    elif change == "subject":
        value["propositions"]["safe"]["subjects"] = ["nodes.first"]
    elif change == "evidence":
        value["evidence_requirements"]["readback"]["source_refs"] = ["nodes.first"]
        value["evidence_requirements"]["readback"]["scope_refs"] = ["nodes.first"]
    else:
        value["safe_state"]["default"]["assertion_refs"] = ["missing"]
    with pytest.raises(SDLValidationError, match="Safe.state"):
        scenario(value)


def test_omission_preserves_legacy_validation_and_serialization():
    value = payload()
    value.pop("safe_state")
    old = scenario(value)
    assert "safe_state" not in old.model_dump(mode="json")
    execution = plan(compile_runtime_model(old), create_stub_manifest())
    assert execution.provisioning.safe_states == ()
    assert "safe_states" not in provisioning_plan_model(execution.provisioning).model_dump(mode="json")


def test_declaration_changes_commitment_but_does_not_change_retained_plan():
    value = payload()
    original = plan(compile_runtime_model(scenario(value)), create_stub_manifest()).provisioning
    changed = copy.deepcopy(value)
    changed["safe_state"]["default"]["kind"] = "controlled-stop"
    newer = plan(compile_runtime_model(scenario(changed)), create_stub_manifest()).provisioning
    assert provisioning_plan_digest(original) != provisioning_plan_digest(newer)
    assert original.safe_states[0].state.kind == "safe-hold"


def test_imported_defaults_retain_private_proof_and_repeated_identity(tmp_path):
    from raes import parse_sdl_file

    module = payload()
    module["module"] = {"id": "example/safe", "version": "1.0.0", "exports": {"nodes": ["first", "second"]}}
    (tmp_path / "module.yaml").write_text(yaml.safe_dump(module))
    root = {
        "name": "root",
        "imports": [{"source": "local:module.yaml", "namespace": name} for name in ("left", "right")],
    }
    path = tmp_path / "root.yaml"
    path.write_text(yaml.safe_dump(root))
    states = compile_runtime_model(parse_sdl_file(path)).safe_states
    assert len(states) == 6
    assert {state.governing_scope for state in states} == {"left#/", "right#/"}
    assert all(state.state.assertion_refs[0].startswith(state.namespace[0] + ".") for state in states)
    assert all(state.target_ref in next(iter(state.proofs.values())).proposition.subjects for state in states)


@pytest.mark.parametrize(
    "scope,namespace",
    [
        ("/nodes/absent", []),
        ("/nodes/first/os", []),
        ("/nodes/first/services/0", []),
        ("/nodes/first", ["absent"]),
    ],
)
def test_invalid_scope_and_namespace_are_rejected(scope, namespace):
    value = payload()
    value["safe_state"] = {
        "scopes": [{"scope": scope, "namespace": namespace, "state": value["safe_state"]["default"]}]
    }
    with pytest.raises(SDLValidationError, match="Safe.state"):
        scenario(value)


def test_named_service_scope_is_stable_across_reordering_and_unnamed_ports():
    value = payload()
    service_scope = next(
        state.scope
        for state in compile_runtime_model(scenario(value)).safe_states
        if state.target_ref == "nodes.first.services.api"
    )
    value["safe_state"] = {"scopes": [{"scope": service_scope, "state": value["safe_state"]["default"]}]}
    value["nodes"]["first"]["services"].extend([{"port": 80}, {"port": 8080}])
    original = compile_runtime_model(scenario(value)).safe_states
    value["nodes"]["first"]["services"].reverse()
    assert compile_runtime_model(scenario(value)).safe_states == original
    assert [state.target_ref for state in original] == ["nodes.first.services.api"]


def test_logical_service_is_a_target_but_its_children_are_not():
    value = payload()
    value["nodes"]["first"]["runtime"] = {"dns_services": [{"dns_service_id": "resolver", "zones": []}]}
    target = "nodes.first.runtime.dns_services.resolver"
    value["propositions"]["safe"]["subjects"].append(target)
    # YAML may share the same list; assign exact coverage independently.
    value["evidence_requirements"]["readback"]["source_refs"] = list(value["propositions"]["safe"]["subjects"])
    states = compile_runtime_model(scenario(value)).safe_states
    assert target in {state.target_ref for state in states}


def test_admitted_trial_entry_carries_safe_state_and_seals_its_proof():
    from dataclasses import replace

    from raes import canonical_sdl_digest
    from raes.scenario import ExpandedScenario
    from raes_processor.trial_compiler import compile_admitted_trial_plan
    from test_sce_002_trial_compiler import _request

    request = _request()
    data = request.family.model_dump(mode="json")
    added = payload()
    for section in ("safe_state", "assertions", "propositions", "evidence_requirements"):
        data[section] = added[section]
    data["propositions"]["safe"]["subjects"] = ["nodes.primary"]
    data["evidence_requirements"]["readback"]["source_refs"] = ["nodes.primary"]
    data["evidence_requirements"]["readback"]["scope_refs"] = ["nodes.primary"]
    from raes.validator import SemanticValidator

    data["evidence_requirements"]["readback"]["observation_demand"] = {
        "rule_id": "operational-readback",
        "scope": "",
        "purpose": "operational",
        "mode": "operational-only",
    }
    family = ExpandedScenario.model_validate(data)
    SemanticValidator(family).validate()
    family._set_semantic_validated(True)
    refs = request.input_refs.model_copy(
        update={
            "scenario_family_ref": request.input_refs.scenario_family_ref.model_copy(
                update={"ref_digest": canonical_sdl_digest(family).value}
            )
        }
    )
    request = replace(request, family=family, input_refs=refs)
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    assert all(entry.safe_states for entry in result.plan.entries.values())


def test_noop_plan_and_service_without_an_operation_keep_declarations():
    from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry

    compiled = compile_runtime_model(scenario(payload()))
    initial = plan(compiled, create_stub_manifest())
    snapshot = RuntimeSnapshot(
        entries={
            address: SnapshotEntry(
                address=address,
                domain=resource.domain,
                resource_type=resource.resource_type,
                payload=resource.payload,
                ordering_dependencies=resource.ordering_dependencies,
                refresh_dependencies=resource.refresh_dependencies,
            )
            for domain in (initial.provisioning, initial.orchestration, initial.evaluation)
            for address, resource in domain.resources.items()
        }
    )
    unchanged = plan(compiled, create_stub_manifest(), snapshot)
    assert not unchanged.provisioning.actionable_operations
    assert unchanged.provisioning.safe_states == initial.provisioning.safe_states
    assert "nodes.first.services.api" in {state.target_ref for state in unchanged.provisioning.safe_states}


def test_portable_plan_rejects_duplicate_and_mutated_proof():
    from pydantic import ValidationError
    from raes_contracts.contracts import ProvisioningPlanModel

    original = plan(compile_runtime_model(scenario(payload())), create_stub_manifest()).provisioning
    data = provisioning_plan_model(original).model_dump(mode="json")
    data["safe_states"].append(copy.deepcopy(data["safe_states"][0]))
    with pytest.raises(ValidationError):
        ProvisioningPlanModel.model_validate(data)

    data["safe_states"].pop()
    data["safe_states"][0]["proofs"]["safe"]["proposition"]["basis"] = "declared_state"
    with pytest.raises(ValidationError):
        ProvisioningPlanModel.model_validate(data)


def test_native_plan_refuses_untyped_safe_state():
    from raes_contracts.planning import ProvisioningPlan

    with pytest.raises((TypeError, ValueError)):
        ProvisioningPlan(safe_states=({"kind": "safe-hold"},))


def test_continuing_mode_is_instantiated_before_compilation():
    value = payload("continue")
    value["variables"] = {"mode": {"type": "string", "default": "cooling"}}
    value["safe_state"]["default"]["continuing_mode"] = "${mode}"
    assert all(state.state.continuing_mode == "cooling" for state in compile_runtime_model(scenario(value)).safe_states)


def test_shadowed_declaration_still_requires_resolving_proof():
    value = payload()
    state = copy.deepcopy(value["safe_state"]["default"])
    value["safe_state"]["default"]["assertion_refs"] = ["absent"]
    value["safe_state"]["scopes"] = [{"scope": "/nodes", "state": state}]
    with pytest.raises(SDLValidationError, match="Safe.state"):
        scenario(value)


def test_normative_example_and_published_schema_agree():
    import json
    from pathlib import Path

    from jsonschema import Draft202012Validator

    root = Path(__file__).resolve().parents[3]
    source = (root / "specs/sdl/safe-state.md").read_text().split("```yaml\n", 1)[1].split("```", 1)[0]
    assert parse_sdl(source).safe_state.scopes[0].state.kind == "safe-hold"
    validator = Draft202012Validator(
        json.loads((root / "contracts/schemas/sdl/sdl-authoring-input-v1.json").read_text())
    )
    assert validator.is_valid(payload())
    invalid = payload("continue")
    invalid["safe_state"]["default"].pop("continuing_mode")
    assert not validator.is_valid(invalid)


def test_safe_state_assertion_reference_completion():
    from raes.language_service import language_completions

    result = language_completions(yaml.safe_dump(payload()), cursor_path="/safe_state/default/assertion_refs")
    assert result["context"] == "reference:assertions"
    assert "safe" in {item["label"] for item in result["items"]}


def test_assertion_reference_is_resolved_after_variable_binding():
    value = payload()
    value["variables"] = {"proof": {"type": "string", "default": "safe"}}
    value["safe_state"]["default"]["assertion_refs"] = ["${proof}"]
    compiled = compile_runtime_model(scenario(value))
    assert all(state.state.assertion_refs == ("safe",) for state in compiled.safe_states)


@pytest.mark.parametrize("field", ["proposition", "subjects", "evidence_requirements", "source_refs", "scope_refs"])
def test_proof_references_support_variable_binding(field):
    value = payload()
    if field == "proposition":
        owner, expected = value["assertions"]["safe"], "safe"
    elif field in {"subjects", "evidence_requirements"}:
        owner = value["propositions"]["safe"]
        expected = owner[field][0]
    else:
        owner = value["evidence_requirements"]["readback"]
        expected = owner[field][0]
    value["variables"] = {"reference": {"type": "string", "default": expected}}
    if field == "proposition":
        owner[field] = "${reference}"
    else:
        owner[field] = ["${reference}", *owner[field][1:]]
    assert len(compile_runtime_model(scenario(value)).safe_states) == 3
