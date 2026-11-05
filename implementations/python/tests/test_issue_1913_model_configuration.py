"""Model selection stays in SDL software configuration through trial realization."""

import json

import pytest
from jsonschema import Draft202012Validator
from paths import REPO_ROOT
from raes import SDLParseError, admit_scenario_family, parse_sdl, select_scenario_family
from raes.instantiate import instantiate_scenario
from raes.scenario import InstantiatedScenario
from raes_contracts.contracts import LiteralBindingValueModel
from test_issue_1200_mixed_runtime_constraints import _apply, _fixture

MODELS = ("vendor/model-a@revision-1", "vendor/model-b@revision-2")


def _component(**values):
    return {"component_id": "controller", "name": "controller", **values}


def _source(**values):
    return {
        "name": "model-family",
        "realization": {"default": "open"},
        "nodes": {"host": {"type": "compute", "runtime": {"software_components": [_component(**values)]}}},
    }


def _family():
    source = _source(model="${model_choice}")
    source["variables"] = {"model_choice": {"type": "string", "allowed_values": list(MODELS), "required": True}}
    source["variation_points"] = {
        "model-choice": {
            "kind": "parameter",
            "target": {"kind": "variable", "variable": "model_choice"},
            "domain": {"kind": "enum", "values": list(MODELS)},
        }
    }
    return admit_scenario_family(parse_sdl(json.dumps(source)))


def test_model_configuration_accepts_experiment_variation():
    family = _family()
    selected = select_scenario_family(family, {"model-choice": LiteralBindingValueModel(value=MODELS[0])})

    assert selected.nodes["host"].runtime.software_components[0].model == MODELS[0]
    assert not selected.agents


def test_model_configuration_preserves_realization_posture():
    scope = "/nodes/host/runtime/software_components"
    _, request, manifest = _fixture({"software_components": [_component(model=MODELS[0])]}, scope=scope)
    assert _apply(request, manifest, {"software_components": [_component(model=MODELS[0])]}, observe=False).success
    assert not _apply(request, manifest, {"software_components": [_component(model=MODELS[1])]}, observe=False).success

    _, request, manifest = _fixture({"software_components": [_component()]}, scope=scope)
    assert _apply(request, manifest, {"software_components": [_component(model=MODELS[1])]}, observe=False).success


def test_instantiation_retains_each_trial_model():
    family = _family()
    snapshots = []
    for model in MODELS:
        selected = select_scenario_family(family, {"model-choice": LiteralBindingValueModel(value=model)})
        serialized = selected.model_dump_json(by_alias=True)
        restored = InstantiatedScenario.model_validate_json(serialized)
        assert restored.nodes["host"].runtime.software_components[0].model == model
        assert "${model_choice}" not in serialized
        snapshots.append(serialized)
    assert snapshots[0] != snapshots[1]


def test_model_configuration_schema_and_absence():
    path = REPO_ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json"
    validator = Draft202012Validator(json.loads(path.read_text()))
    source = _source(model=MODELS[0])
    validator.validate(source)
    assert parse_sdl(json.dumps(source)).nodes["host"].runtime.software_components[0].model == MODELS[0]

    absent = _source()
    validator.validate(absent)
    concrete = instantiate_scenario(parse_sdl(json.dumps(absent)))
    assert concrete.nodes["host"].runtime.software_components[0].model is None
    assert "model" not in concrete.model_dump(mode="json")["nodes"]["host"]["runtime"]["software_components"][0]


@pytest.mark.parametrize("value", ["", "   ", 42, [], {}])
def test_invalid_model_configuration_is_rejected(value):
    source = _source(model=value)
    path = REPO_ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json"
    assert list(Draft202012Validator(json.loads(path.read_text())).iter_errors(source))
    with pytest.raises(SDLParseError):
        parse_sdl(json.dumps(source))
