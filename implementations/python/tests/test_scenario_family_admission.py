"""Public admission of import-free SDL families for experiment consumers."""

import warnings
from pathlib import Path

import pytest
from paths import REPO_ROOT
from raes import (
    ExpandedScenarioBindingTargetResolver,
    SDLMigrationPolicy,
    SDLParseError,
    SDLValidationError,
    admit_scenario_family,
    canonical_sdl_digest,
    instantiate_scenario,
    parse_sdl,
    parse_sdl_file,
    select_scenario_family,
)
from raes.scenario import ExpandedScenario, Scenario
from raes_contracts.contracts import LiteralBindingValueModel
from raes_contracts.contracts.experiment_treatments import ExperimentFactorLevelSelectionModel

_SOURCE = """name: example-family
nodes:
  server:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
variables:
  image: {type: string, default: linux, allowed_values: [linux, bsd]}
variation_points:
  image-choice:
    kind: parameter
    target: {kind: variable, variable: image}
    domain: {kind: enum, values: [linux, bsd]}
"""


@pytest.mark.parametrize("skip", [False, True])
def test_public_admission_validates_and_isolates_import_free_family(skip: bool) -> None:
    authored = parse_sdl(_SOURCE, skip_semantic_validation=skip)
    assert type(authored) is Scenario
    family = admit_scenario_family(authored)

    assert isinstance(family, ExpandedScenario)
    assert family.semantic_validated
    assert family.variation_points == authored.variation_points
    assert not family.expansion_provenance.imports
    assert family.declaration_sources == authored.declaration_sources
    assert family.nodes["server"] is not authored.nodes["server"]
    assert authored.semantic_validated is not skip
    family.nodes["server"].os = "bsd"
    assert authored.nodes["server"].os == "linux"


def test_typed_descriptor_resolver_and_selector_accept_publicly_admitted_family() -> None:
    family = admit_scenario_family(parse_sdl(_SOURCE))
    resolver = ExpandedScenarioBindingTargetResolver(family)
    resolution = resolver.resolve(family.name, "image-choice", "variables.image")
    outcome = LiteralBindingValueModel(kind="literal", value="bsd")
    treatment = ExperimentFactorLevelSelectionModel(
        target={
            "plane": "scenario",
            "scenario_family_id": family.name,
            "variation_point_id": "image-choice",
            "target_id": resolution.canonical_target_id,
        },
        scenario_family_digest=canonical_sdl_digest(family).value,
        owner=resolution.owner,
        outcome=outcome,
    )
    resolver.validate_selection(treatment.descriptor("image", "bsd", "condition-bsd"))
    selected = select_scenario_family(family, {"image-choice": outcome})
    assert selected.semantic_validated
    assert selected.instantiation_provenance.bindings[0].value == "bsd"


def test_file_parsing_and_singleton_family_need_no_ambient_io(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "family.yaml"
    source.write_text("name: singleton\n", encoding="utf-8")
    authored = parse_sdl_file(source)

    def refuse_io(*args, **kwargs):
        pytest.fail("family admission must not discover or read workspace files")

    monkeypatch.setattr(Path, "open", refuse_io)
    monkeypatch.setattr(Path, "resolve", refuse_io)
    family = admit_scenario_family(authored)
    assert select_scenario_family(family, {}).semantic_validated


@pytest.mark.parametrize("mutate", [False, True])
def test_invalid_semantics_cannot_use_skipped_validation_or_stale_flag(mutate: bool) -> None:
    authored = parse_sdl(_SOURCE, skip_semantic_validation=not mutate)
    authored.variation_points["image-choice"].target.variable = "missing"
    with pytest.raises(SDLValidationError):
        admit_scenario_family(authored)


def test_nested_shape_mutation_is_revalidated_without_raw_input_disclosure() -> None:
    authored = parse_sdl(_SOURCE)
    authored.nodes["server"].resources.cpu = "sensitive-invalid-cpu"
    with pytest.raises(SDLParseError) as raised:
        admit_scenario_family(authored)
    assert "sensitive-invalid-cpu" not in str(raised.value)


@pytest.mark.parametrize("identifier", ["forged.server", "forged.__private.server"])
def test_mutated_qualified_declarations_do_not_gain_expanded_privileges(identifier: str) -> None:
    authored = parse_sdl(_SOURCE)
    authored.nodes[identifier] = authored.nodes.pop("server")
    with pytest.raises(SDLParseError):
        admit_scenario_family(authored)


def test_mutated_private_references_are_rejected_before_expanded_construction() -> None:
    authored = parse_sdl(_SOURCE + "agents:\n  actor:\n    actions: []\n")
    authored.agents["actor"].actions.append("module.__private.action")
    with pytest.raises(SDLParseError):
        admit_scenario_family(authored)


def test_unresolved_imports_are_rejected_instead_of_removed() -> None:
    from raes.scenario import ImportDecl

    authored = parse_sdl(_SOURCE)
    authored.imports.append(ImportDecl(source="local:missing.yaml", namespace="missing"))
    with pytest.raises(SDLParseError, match="imports"):
        admit_scenario_family(authored)


@pytest.mark.parametrize("phase", ["expanded", "instantiated", "materialized"])
def test_other_document_phases_cannot_be_admitted_as_normalized_authoring(phase: str) -> None:
    if phase == "expanded":
        value = ExpandedScenario(name="wrong-phase")
    elif phase == "instantiated":
        value = instantiate_scenario(parse_sdl("name: wrong-phase\n"))
    else:
        path = REPO_ROOT / "contracts/fixtures/sdl/materialized-scenario-v1/valid/reference.json"
        value = parse_sdl_file(path)
    with pytest.raises(SDLParseError, match="Scenario"):
        admit_scenario_family(value)


def test_mutation_of_omitted_default_is_rejected_without_losing_content() -> None:
    authored = parse_sdl("name: singleton\n")
    authored.nodes["server"] = parse_sdl(_SOURCE).nodes["server"]
    with pytest.raises(SDLParseError, match="reparse"):
        admit_scenario_family(authored)


def test_nested_omitted_default_mutations_are_rejected() -> None:
    authored = parse_sdl(_SOURCE)
    authored.nodes["server"].features["missing"] = ""
    with pytest.raises(SDLParseError, match="reparse"):
        admit_scenario_family(authored)


def test_admission_preserves_explicitness_and_canonical_identity() -> None:
    implicit = admit_scenario_family(parse_sdl("name: singleton\n"))
    explicit = admit_scenario_family(parse_sdl("name: singleton\ndescription: ''\n"))
    assert implicit.model_fields_set == {"name", "expansion_provenance"}
    assert explicit.model_fields_set == {"name", "description", "expansion_provenance"}
    assert canonical_sdl_digest(implicit) != canonical_sdl_digest(explicit)
    before = parse_sdl(_SOURCE)
    family = admit_scenario_family(before)
    assert family.nodes["server"].model_fields_set == before.nodes["server"].model_fields_set
    assert {path: family.explicitness[path] for path in before.explicitness} == before.explicitness
    assert canonical_sdl_digest(family) == canonical_sdl_digest(admit_scenario_family(before))


def test_realization_intent_and_source_diagnostics_survive_admission() -> None:
    authored = parse_sdl(
        _SOURCE.replace("type: compute", "type: vm")
        + "realization:\n  default: closed\n  scopes:\n    - {field_pointer: /nodes/server/os, posture: open}\n",
        migration_policy=SDLMigrationPolicy.ACCEPT,
    )
    family = admit_scenario_family(authored)
    assert family.source_diagnostics == authored.source_diagnostics
    assert family.source_diagnostics
    assert family.advisories == authored.advisories
    assert family.declaration_sources == authored.declaration_sources
    provenance = family.expansion_provenance
    assert [entry.posture.value for entry in provenance.realization_designations] == ["closed", "open"]
    assert provenance.realization_constraints[0].provenance == "legacy-node-type-vm"
    selected = select_scenario_family(family, {"image-choice": LiteralBindingValueModel(kind="literal", value="linux")})
    assert selected.instantiation_provenance.realization_constraints == provenance.realization_constraints


@pytest.mark.parametrize("replacement", ["realization", "constraint"])
def test_realization_replacements_use_reconstructed_content(replacement: str) -> None:
    authored = parse_sdl(
        _SOURCE + "realization:\n  default: closed\n  constraints:\n"
        "    - {field_pointer: /nodes/server, concern: compute-substrate, posture: open}\n"
    )
    if replacement == "realization":
        authored.realization = authored.realization.model_dump(mode="python")
    else:
        authored.realization.constraints = (authored.realization.constraints[0].model_dump(mode="python"),)

    family = admit_scenario_family(authored)
    assert family.semantic_validated
    assert family.expansion_provenance.realization_designations[0].posture.value == "closed"
    assert family.expansion_provenance.realization_constraints[0].posture.value == "open"
    assert family.expansion_provenance.realization_constraints[0].provenance == "author-declared"


def test_semantic_failure_retains_authored_source_location(tmp_path: Path) -> None:
    path = tmp_path / "invalid-family.yaml"
    path.write_text(_SOURCE.replace("variable: image}", "variable: missing}"), encoding="utf-8")
    authored = parse_sdl_file(path, skip_semantic_validation=True)
    with pytest.raises(SDLValidationError) as raised:
        admit_scenario_family(authored)
    diagnostics = [item for item in raised.value.diagnostics if item is not None]
    assert diagnostics
    assert any(item.source == str(path) and item.primary_range.start.line > 1 for item in diagnostics)


@pytest.mark.parametrize("defect", ["literal-conflict", "classification", "private-output", "missing-output"])
def test_family_admission_revalidates_runtime_secret_boundaries(defect: str) -> None:
    source = """name: env-family
nodes:
  server:
    type: compute
    runtime:
      environment:
        - name: API_KEY
          value: ''
          value_from: {generated_artifact: credential, output: key}
          value_classification: redacted
          provenance: runtime
generated_artifacts:
  credential:
    generator: rendered_config
    lifecycle: reuse_valid
    provenance: bootstrap/credential.yaml
    outputs:
      - {name: key, path: key.env, sensitivity: secret, disposition: consumer_selected}
"""
    authored = parse_sdl(source)
    environment = authored.nodes["server"].runtime.environment[0]
    if defect == "literal-conflict":
        environment.value = "sensitive-conflicting-value"
        error = SDLParseError
    elif defect == "classification":
        environment.value_classification = "plain"
        error = SDLValidationError
    elif defect == "private-output":
        authored.generated_artifacts["credential"].outputs[0].disposition = "producer_private"
        error = SDLValidationError
    else:
        environment.value_from.output = "missing"
        error = SDLValidationError
    with warnings.catch_warnings(record=True) as emitted:
        warnings.simplefilter("always")
        with pytest.raises(error) as raised:
            admit_scenario_family(authored)
    assert not emitted
    assert "sensitive-conflicting-value" not in str(raised.value)
