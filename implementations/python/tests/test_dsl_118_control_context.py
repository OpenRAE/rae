"""DSL-118 exact authored control-context selection across SDL boundaries."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from raes import SDLParseError, SDLValidationError, instantiate_scenario, parse_sdl, parse_sdl_file
from raes.language_service import language_completions, language_references
from raes_contracts.contracts.participant_control_context import ParticipantControlContextAssetModel
from raes_contracts.participant_control_context import control_context_asset_reference
from raes_processor.compiler import compile_runtime_model

ROOT = Path(__file__).resolve().parents[3]


def asset_payload(*, version: str = "one", roles: list[str] | None = None) -> dict:
    path = ROOT / "contracts/fixtures/participant-runtime/participant-control-context-asset-v1/valid/instruction.json"
    asset = json.loads(path.read_text())
    asset["asset_version"] = version
    asset["role_refs"] = roles if roles is not None else ["red", "blue"]
    return asset


def selection(asset: dict, reference: str = "shared", *, disposition: str = "selected") -> dict:
    pin = control_context_asset_reference(ParticipantControlContextAssetModel.model_validate(asset))
    return {"declaration_ref": reference, "asset_ref": pin.model_dump(mode="json"), "disposition": disposition}


def source_payload() -> dict:
    asset = asset_payload()
    return {
        "name": "context-example",
        "control_context_assets": {"shared": asset},
        "agents": {
            "red": {"role": "red", "control_context": {"briefing": selection(asset)}},
            "blue": {"role": "blue", "control_context": {"briefing": selection(asset, disposition="withheld")}},
        },
    }


def test_shared_exact_asset_and_withheld_intent_are_typed_without_delivery() -> None:
    payload = source_payload()
    scenario = parse_sdl(yaml.safe_dump(payload))
    assert scenario.control_context_assets["shared"].asset_version == "one"
    assert scenario.agents["red"].control_context["briefing"].asset_ref == control_context_asset_reference(
        scenario.control_context_assets["shared"]
    )
    model = compile_runtime_model(instantiate_scenario(scenario))
    red = next(item for item in model.participant_behaviors.values() if item.participant_name == "red").control_context
    blue = next(
        item for item in model.participant_behaviors.values() if item.participant_name == "blue"
    ).control_context
    assert len(red) == len(blue) == 1
    assert red[0].participant_address == "agents.red"
    assert red[0].declaration_address == "control_context_assets.shared"
    assert red[0].asset_ref == blue[0].asset_ref
    assert red[0].disposition == "selected"
    assert blue[0].disposition == "withheld"
    assert not model.content_placements
    assert not model.participant_inject_deliveries
    assert not model.observation_boundaries
    from raes_processor.models import resource_payload

    json.dumps(resource_payload(next(iter(model.participant_behaviors.values()))))


@pytest.mark.parametrize("mutation", ["missing", "stale-version", "stale-digest", "wrong-participant", "competing"])
def test_invalid_reference_fails_closed_without_private_values(mutation: str) -> None:
    payload = source_payload()
    binding = payload["agents"]["red"]["control_context"]["briefing"]
    if mutation == "missing":
        binding["declaration_ref"] = "private-missing-sentinel"
    elif mutation == "stale-version":
        binding["asset_ref"]["asset_version"] = "private-version-sentinel"
    elif mutation == "stale-digest":
        binding["asset_ref"]["asset_digest"] = "sha256:" + "0" * 64
    elif mutation == "wrong-participant":
        asset = asset_payload(roles=["blue"])
        payload["control_context_assets"]["shared"] = asset
        for agent in payload["agents"].values():
            agent["control_context"]["briefing"] = selection(asset)
    else:
        payload["behavior_specifications"] = {
            "duplicate": {
                "semantic_version": "1",
                "participant_refs": ["red"],
                "control_context": {"briefing": deepcopy(binding)},
            }
        }
    with pytest.raises(SDLValidationError) as error:
        parse_sdl(yaml.safe_dump(payload))
    assert "control-context" in str(error.value)
    assert "private-" not in str(error.value)


def test_imports_keep_descriptor_identity_and_participant_scope(tmp_path: Path) -> None:
    payload = source_payload()
    payload["module"] = {
        "id": "examples/context-kit",
        "version": "1.0.0",
        "exports": {"agents": ["red", "blue"], "control_context_assets": ["shared"]},
    }
    (tmp_path / "kit.yaml").write_text(yaml.safe_dump(payload))
    root = {
        "name": "twice",
        "imports": [{"source": "local:kit.yaml", "namespace": name} for name in ("first", "second")],
    }
    path = tmp_path / "root.yaml"
    path.write_text(yaml.safe_dump(root))
    scenario = parse_sdl_file(path)
    assert scenario.control_context_assets["first.shared"] == scenario.control_context_assets["second.shared"]
    assert scenario.agents["first.red"].control_context["briefing"].declaration_ref == "first.shared"
    assert scenario.agents["second.red"].control_context["briefing"].declaration_ref == "second.shared"
    compiled = compile_runtime_model(scenario)
    assert {
        selection.participant_address
        for participant in compiled.participant_behaviors.values()
        for selection in participant.control_context
    } == {"agents.first.red", "agents.first.blue", "agents.second.red", "agents.second.blue"}
    completions = language_completions(
        path.read_text(), cursor_path="/agents/new/control_context/briefing/declaration_ref", path=path
    )
    assert {"first.shared", "second.shared"} <= {item["label"] for item in completions["items"]}
    references = language_references(yaml.safe_dump(payload), "control_context_assets.shared")
    assert len(references["occurrences"]) == 2


@pytest.mark.parametrize("mutation", ["private", "descriptor-token", "ambiguous", "wrong-kind", "descriptor-conflict"])
def test_reference_boundary_rejects_unsafe_authored_forms(mutation: str) -> None:
    payload = source_payload()
    if mutation == "private":
        payload["agents"]["red"]["control_context"]["briefing"]["declaration_ref"] = "lib.__private.shared"
    elif mutation == "descriptor-token":
        payload["control_context_assets"]["shared"]["retention_policy_ref"] = "${private_sentinel}"
    elif mutation == "ambiguous":
        payload["agents"]["shared"] = {}
    elif mutation == "wrong-kind":
        for participant in payload["agents"].values():
            participant["control_context"]["briefing"]["declaration_ref"] = "agents.red"
    else:
        payload["control_context_assets"]["other"] = asset_payload(roles=["red"])
    with pytest.raises((SDLParseError, SDLValidationError), match="control.context|private"):
        parse_sdl(yaml.safe_dump(payload))


def test_reusable_scope_and_direct_artifact_revalidation() -> None:
    from raes.scenario import InstantiatedScenario

    payload = source_payload()
    payload["agents"]["red"].pop("control_context")
    payload["behavior_specifications"] = {
        "briefings": {
            "semantic_version": "1",
            "participant_role_refs": ["red"],
            "control_context": {"briefing": selection(payload["control_context_assets"]["shared"])},
        }
    }
    concrete = instantiate_scenario(parse_sdl(yaml.safe_dump(payload)))
    roundtrip = InstantiatedScenario.model_validate_json(concrete.model_dump_json())
    compiled = compile_runtime_model(roundtrip)
    assert next(iter(compiled.behavior_specifications.values())).control_context[0].participant_address == "agents.red"
    roundtrip.control_context_assets["shared"].asset_version = "changed"
    with pytest.raises(SDLValidationError, match="control-context.reference-stale"):
        compile_runtime_model(roundtrip)


def test_variable_bound_reference_rechecks_pin() -> None:
    from raes import SDLInstantiationError

    payload = source_payload()
    payload["variables"] = {"selected_asset": {"type": "string", "default": "shared"}}
    payload["agents"]["red"]["control_context"]["briefing"]["declaration_ref"] = "${selected_asset}"
    scenario = parse_sdl(yaml.safe_dump(payload))
    assert instantiate_scenario(scenario).agents["red"].control_context["briefing"].declaration_ref == "shared"
    with pytest.raises(SDLInstantiationError, match="control-context.reference-missing"):
        instantiate_scenario(scenario, parameters={"selected_asset": "private-sentinel"})


def test_pinned_descriptor_never_accepts_even_declared_substitution_tokens() -> None:
    payload = source_payload()
    payload["variables"] = {"retention": {"type": "string", "default": "retention.changed"}}
    asset = payload["control_context_assets"]["shared"]
    asset["retention_policy_ref"] = "${retention}"
    for agent in payload["agents"].values():
        agent["control_context"]["briefing"] = selection(asset)
    with pytest.raises(SDLParseError, match="control-context"):
        parse_sdl(yaml.safe_dump(payload))


def test_legacy_serialization_omits_empty_additions() -> None:
    from raes import canonical_instantiated_sdl_bytes

    scenario = instantiate_scenario(parse_sdl("name: legacy\nagents: {red: {role: red}}"))
    payload = scenario.model_dump(mode="json")
    assert "control_context_assets" not in payload
    assert "control_context" not in payload["agents"]["red"]
    assert b'"control_context' not in canonical_instantiated_sdl_bytes(scenario)


def test_published_schema_rejects_invalid_selection_slot_keys() -> None:
    from jsonschema import Draft202012Validator
    from raes_contracts.contracts import schema_bundle

    payload = source_payload()
    payload["agents"]["red"]["control_context"]["_invalid"] = payload["agents"]["red"]["control_context"].pop(
        "briefing"
    )
    assert list(Draft202012Validator(schema_bundle()["sdl-authoring-input-v1"]).iter_errors(payload))


def test_published_examples_preserve_exact_assets_across_two_imports() -> None:
    path = ROOT / "examples/scenarios/participant-control-context/twice-imported.sdl.yaml"
    scenario = parse_sdl_file(path)
    model = compile_runtime_model(scenario)
    selected = [
        selection for participant in model.participant_behaviors.values() for selection in participant.control_context
    ]
    assert {selection.asset_ref.asset_version for selection in selected} >= {"one", "two"}
    assert {selection.disposition for selection in selected} == {"selected", "withheld"}
    assert scenario.control_context_assets["alpha.shared"] == scenario.control_context_assets["bravo.shared"]
    assert not model.content_placements


def test_rename_transports_only_local_symbol_and_preserves_asset_commitment() -> None:
    from raes import RenameSDLDeclarationRequest, rename_sdl_declaration

    original = parse_sdl(yaml.safe_dump(source_payload()))
    result = rename_sdl_declaration(
        original, RenameSDLDeclarationRequest(target_address="control_context_assets.shared", new_local_name="renamed")
    )
    assert result.output is not None
    assert result.output.control_context_assets["renamed"] == original.control_context_assets["shared"]
    assert result.output.agents["red"].control_context["briefing"].declaration_ref == "renamed"
    assert (
        result.output.agents["red"].control_context["briefing"].asset_ref
        == original.agents["red"].control_context["briefing"].asset_ref
    )


def test_import_refuses_ambiguous_unit_reference_before_namespacing(tmp_path: Path) -> None:
    payload = source_payload()
    payload["agents"]["shared"] = {}
    payload["module"] = {
        "id": "examples/ambiguous",
        "version": "1",
        "exports": {"agents": ["red", "blue", "shared"], "control_context_assets": ["shared"]},
    }
    (tmp_path / "kit.yaml").write_text(yaml.safe_dump(payload))
    root = tmp_path / "root.yaml"
    root.write_text("name: ambiguous-import\nimports: [{source: 'local:kit.yaml', namespace: lib}]\n")
    with pytest.raises((SDLParseError, SDLValidationError), match="control-context.reference-ambiguous"):
        parse_sdl_file(root)


def test_selection_pin_is_immutable_while_declaration_reference_can_vary() -> None:
    payload = source_payload()
    payload["variables"] = {
        "asset_name": {"type": "string", "default": "shared"},
        "identity": {"type": "string", "default": "privacy-instruction"},
    }
    binding = payload["agents"]["red"]["control_context"]["briefing"]
    binding["declaration_ref"] = "${asset_name}"
    binding["asset_ref"]["asset_id"] = "${identity}"
    with pytest.raises(SDLParseError, match="control-context"):
        parse_sdl(yaml.safe_dump(payload))


def test_import_ambiguity_is_checked_before_external_participants_resolve(tmp_path: Path) -> None:
    asset = asset_payload()
    unit = {
        "name": "external-scope",
        "module": {
            "id": "examples/external",
            "version": "1",
            "exports": {"behavior_specifications": ["briefing"], "control_context_assets": ["shared"], "agents": []},
        },
        "control_context_assets": {"shared": asset},
        "agents": {"shared": {}},
        "behavior_specifications": {
            "briefing": {
                "semantic_version": "1",
                "participant_refs": ["operator"],
                "control_context": {"briefing": selection(asset)},
            }
        },
    }
    (tmp_path / "kit.yaml").write_text(yaml.safe_dump(unit))
    root = tmp_path / "root.yaml"
    root.write_text(
        "name: external-scope\nagents: {operator: {role: red}}\nimports: [{source: 'local:kit.yaml', namespace: lib}]\n"
    )
    with pytest.raises((SDLParseError, SDLValidationError), match="control-context.reference-ambiguous"):
        parse_sdl_file(root)
