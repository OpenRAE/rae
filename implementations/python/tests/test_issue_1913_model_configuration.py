"""Model selection stays in SDL software configuration through trial realization."""

import json
from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator
from paths import REPO_ROOT
from raes import SDLParseError, SDLSelectionError, admit_scenario_family, parse_sdl, select_scenario_family
from raes.canonical import canonical_sdl_digest
from raes.instantiate import instantiate_scenario
from raes.scenario import InstantiatedScenario
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import LiteralBindingValueModel
from raes_contracts.realization_structure import evaluate_realization_constraint
from raes_processor.compiler import compile_runtime_model
from raes_processor.semantics.realization_concerns import project_realization_concern
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_realization import instantiate_admitted_trial_entry
from test_issue_1200_mixed_runtime_constraints import _apply, _fixture
from test_sce_002_trial_compiler import _request

MODELS = ("vendor/model-a@revision-1", "vendor/model-b@revision-2")


def _component(**values):
    return {"component_id": "controller", "name": "controller", **values}


def _source(**values):
    return {
        "name": "model-family",
        "realization": {
            "default": "closed",
            "scopes": [{"field_pointer": "/nodes/host/runtime/software_components", "posture": "open"}],
        },
        "nodes": {
            "host": {"type": "compute", "os": "linux", "runtime": {"software_components": [_component(**values)]}}
        },
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
    selected = select_scenario_family(
        family, {"model-choice": LiteralBindingValueModel(kind="literal", value=MODELS[0])}
    )

    assert selected.nodes["host"].runtime.software_components[0].model == MODELS[0]
    assert not selected.agents


def test_model_configuration_preserves_realization_posture():
    scope = "/nodes/host/runtime/software_components"
    _, request, manifest = _fixture({"software_components": [_component(model=MODELS[0])]}, scope=scope)
    assert _apply(request, manifest, {"software_components": [_component(model=MODELS[0])]}, observe=False).success
    assert not _apply(request, manifest, {"software_components": [_component(model=MODELS[1])]}, observe=False).success
    assert not _apply(request, manifest, {"software_components": [_component()]}, observe=False).success

    _, request, manifest = _fixture({"software_components": [_component()]}, scope=scope)
    assert _apply(request, manifest, {"software_components": [_component(model=MODELS[1])]}, observe=False).success


def test_instantiation_retains_each_trial_model():
    family = _family()
    snapshots = []
    for model in MODELS:
        selected = select_scenario_family(
            family, {"model-choice": LiteralBindingValueModel(kind="literal", value=model)}
        )
        serialized = selected.model_dump_json(by_alias=True)
        restored = InstantiatedScenario.model_validate_json(serialized)
        assert restored.nodes["host"].runtime.software_components[0].model == model
        assert "${model_choice}" not in serialized
        snapshots.append(serialized)
    assert snapshots[0] != snapshots[1]


def test_admitted_trial_plan_retains_each_selected_model():
    original = _request()
    source = _family().model_dump(mode="json", by_alias=True, exclude_unset=True)
    source.pop("expansion_provenance", None)
    source["name"] = original.family.name
    family = admit_scenario_family(parse_sdl(json.dumps(source)))
    experiment_data = original.experiment.model_dump(mode="json")
    experiment_data["run_plan"]["selection_policies"]["enumerate-path"]["point_ref"] = "model-choice"
    experiment = type(original.experiment).model_validate(experiment_data)
    references = original.input_refs.model_copy(
        update={
            "scenario_family_ref": original.input_refs.scenario_family_ref.model_copy(
                update={"ref_digest": canonical_sdl_digest(family).value}
            ),
            "authoring_input_ref": original.input_refs.authoring_input_ref.model_copy(
                update={"ref_digest": canonical_json_digest(experiment.model_dump(mode="json"))}
            ),
        }
    )
    result = compile_admitted_trial_plan(replace(original, family=family, experiment=experiment, input_refs=references))
    assert result.plan is not None, result.diagnostics
    models = set()
    for entry in result.plan.entries.values():
        concrete = instantiate_admitted_trial_entry(plan=result.plan, plan_entry_id=entry.plan_entry_id, family=family)
        restored = InstantiatedScenario.model_validate_json(concrete.model_dump_json())
        models.add(restored.nodes["host"].runtime.software_components[0].model)
    assert models == set(MODELS)


def _model_satisfied(concrete, **values):
    kind = "runtime-software-components"
    compiled = compile_runtime_model(concrete)
    requirement = next(item for item in compiled.realization_requirements if item.requirement_kind == kind)
    assert requirement.constraint_document is not None
    projected = project_realization_concern(kind, [_component(**values)], recursive=True)
    return evaluate_realization_constraint(requirement.constraint_document, projected).status.value == "conformant"


def test_constrained_model_parameter_retains_its_finite_domain():
    source = _source(model="${model_choice}")
    source["variables"] = {"model_choice": {"type": "string", "allowed_values": list(MODELS), "required": True}}
    concrete = instantiate_scenario(parse_sdl(json.dumps(source)), parameters={"model_choice": MODELS[0]})
    assert _model_satisfied(concrete, model=MODELS[1])
    assert not _model_satisfied(concrete, model="outside-domain")


def test_selected_model_factor_cannot_be_substituted():
    selected = select_scenario_family(
        _family(), {"model-choice": LiteralBindingValueModel(kind="literal", value=MODELS[0])}
    )
    assert _model_satisfied(selected, model=MODELS[0], version="backend-choice")
    assert not _model_satisfied(selected, model=MODELS[1])


def test_model_variation_rejects_an_undeclared_choice():
    with pytest.raises(SDLSelectionError):
        select_scenario_family(
            _family(), {"model-choice": LiteralBindingValueModel(kind="literal", value="outside-domain")}
        )


def test_model_configuration_schema_and_absence():
    path = REPO_ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json"
    validator = Draft202012Validator(json.loads(path.read_text()))
    source = _source(model=MODELS[0])
    validator.validate(source)
    assert parse_sdl(json.dumps(source)).nodes["host"].runtime.software_components[0].model == MODELS[0]

    for absent in (_source(), _source(model=None)):
        validator.validate(absent)
        concrete = instantiate_scenario(parse_sdl(json.dumps(absent)))
        assert concrete.nodes["host"].runtime.software_components[0].model is None
        assert "model" not in concrete.model_dump(mode="json")["nodes"]["host"]["runtime"]["software_components"][0]
        assert _model_satisfied(concrete, model=MODELS[1])


@pytest.mark.parametrize(
    "relative",
    [
        "sdl/instantiated-scenario-v1.json",
        "sdl/instantiated-scenario-snapshot-v1.json",
        "sdl/materialized-scenario-v1.json",
        "satisfiability/scenario-satisfiability-evidence-v1.json",
    ],
)
def test_concrete_model_schema_rejects_unresolved_variables(relative):
    schema = json.loads((REPO_ROOT / "contracts/schemas" / relative).read_text())
    component_schema = {"$ref": "#/$defs/RuntimeSoftwareComponent", "$defs": schema["$defs"]}
    validator = Draft202012Validator(component_schema)
    validator.validate(_component(model=MODELS[0]))
    assert list(validator.iter_errors(_component(model="${model_choice}")))


@pytest.mark.parametrize("value", ["", "   ", 42, [], {}])
def test_invalid_model_configuration_is_rejected(value):
    source = _source(model=value)
    path = REPO_ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json"
    assert list(Draft202012Validator(json.loads(path.read_text())).iter_errors(source))
    with pytest.raises(SDLParseError):
        parse_sdl(json.dumps(source))
