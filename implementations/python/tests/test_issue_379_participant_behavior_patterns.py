"""Participant behavior pattern catalog: example links and documented behavior (issue #379)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from packaging.specifiers import InvalidSpecifier
from paths import REPO_ROOT
from pydantic import ValidationError
from raes import SDLParseError, SDLValidationError, parse_sdl_file
from raes_cli.main import app
from raes_processor.compiler import compile_runtime_model
from test_example_library_policy import _VALID_BODY, _read_catalog, _seed_repo, _write_catalog, _write_yaml
from tools.check_example_library import evaluate_example_library
from typer.testing import CliRunner

_Mutation = Callable[[Path, dict[str, Any]], None]
_RULE = "example-library-entry-examples"
_TEMPLATES = REPO_ROOT / "examples" / "library" / "templates" / "participant_behavior"
_SPEC = "red-scan-behavior"
_IMPORTED_AFFORDANCE = """\
behavior_specifications:
  local-scan:
    semantic_version: 1.0.0
    participant_refs: [alpha.red-agent]
    action_contract_refs: [alpha.scan]
    observation_boundary_refs: [alpha.red-view]
    tool_affordances:
      local-scanner:
        tool_ref: alpha.scanner-package
        action_contract_refs: [alpha.scan]
        observation_boundary_refs: [alpha.red-view]
"""
_BARE_NAME_REF = """\
behavior_specifications:
  local-scan:
    semantic_version: 1.0.0
    participant_refs: [red-agent]
    action_contract_refs: [alpha.scan]
"""
_PRIVATE_NAME_REF = """\
behavior_specifications:
  local-scan:
    semantic_version: 1.0.0
    participant_refs: [alpha.__private.red-agent]
    action_contract_refs: [alpha.__private.scan]
"""


def _link(value: Any, field: str = "patterns") -> _Mutation:
    def mutate(_repo_root: Path, catalog: dict[str, Any]) -> None:
        catalog["surfaces"]["participant_behavior"][field][0]["example_refs"] = value

    return mutate


def _link_validated_worked_example(repo_root: Path, catalog: dict[str, Any]) -> None:
    worked_path = "examples/scenarios/worked.sdl.yaml"
    _write_yaml(repo_root / worked_path, _VALID_BODY)
    catalog["surfaces"]["scenario"]["worked_examples"][0].update(
        path=worked_path, validation_status="validated", sdl_sections=["nodes"]
    )
    _link(["scenario-worked"])(repo_root, catalog)


def _set_study(value: Any, field: str | None = None) -> _Mutation:
    """Break the study surface's shape; the example_refs check must skip it without failing."""

    def mutate(_repo_root: Path, catalog: dict[str, Any]) -> None:
        if field is None:
            catalog["surfaces"]["study"] = value
        else:
            catalog["surfaces"]["study"][field] = value

    return mutate


def _edit_yaml(path: Path, **fields: Any) -> None:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document.update(fields)
    _write_yaml(path, document)


def _required_fields_as_text(repo_root: Path, _catalog: dict[str, Any]) -> None:
    _edit_yaml(repo_root / "examples/library/patterns/participant_behavior.yaml", required_fields="semantic_version")


def _template_id_as_list(repo_root: Path, catalog: dict[str, Any]) -> None:
    """Give a validated template a list id; the example_refs check must skip it without failing."""
    catalog["surfaces"]["participant_behavior"]["templates"][0]["id"] = ["x"]
    _edit_yaml(repo_root / "examples/library/templates/participant_behavior/template.yaml", id=["x"])


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        pytest.param(_link(["participant_behavior-template", "scenario-template"]), [], id="validated-templates"),
        pytest.param(_link_validated_worked_example, [], id="validated-worked-example"),
        pytest.param(_link(["scenario-worked"]), [_RULE], id="guidance-worked-example"),
        pytest.param(_link(["workflow-pattern"]), [_RULE], id="pattern"),
        pytest.param(_link(["missing-template"]), [_RULE], id="unknown-id"),
        pytest.param(_link([]), [_RULE], id="empty"),
        pytest.param(_link("participant_behavior-template"), [_RULE], id="not-a-list"),
        pytest.param(_link(["scenario-template"], field="templates"), [_RULE], id="on-template"),
        pytest.param(_link(["scenario-template"], field="worked_examples"), [_RULE], id="on-worked-example"),
        pytest.param(_required_fields_as_text, ["example-library-pattern-field-type"], id="required-fields-not-a-list"),
        pytest.param(_set_study("not-a-mapping"), ["example-library-surface"], id="surface-not-a-mapping"),
        pytest.param(_set_study("not-a-list", "patterns"), ["example-library-surface-entry"], id="patterns-not-a-list"),
        pytest.param(
            _set_study(["not-a-mapping"], "patterns"), ["example-library-entry-shape"], id="entry-not-a-mapping"
        ),
        pytest.param(_template_id_as_list, ["example-library-entry-id"], id="template-id-not-text"),
    ),
)
def test_patterns_link_only_validated_examples(tmp_path: Path, mutation: _Mutation, expected: list[str]) -> None:
    repo_root = _seed_repo(tmp_path)
    catalog = _read_catalog(repo_root)
    mutation(repo_root, catalog)
    _write_catalog(repo_root, catalog)

    assert [failure.rule_id for failure in evaluate_example_library(repo_root)] == expected


def _template_body(name: str) -> dict[str, Any]:
    return yaml.safe_load((_TEMPLATES / f"{name}.yaml").read_text(encoding="utf-8"))["body"]


def _write_sdl(path: Path, body: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    return path


def _importing_scenario(tmp_path: Path, unit: dict[str, Any], versions: dict[str, str], local: str = "") -> Path:
    """Save the unit next to a scenario that imports it once per namespace."""
    _write_sdl(tmp_path / "unit.sdl.yaml", unit)
    imports = "".join(
        f"  - source: local:unit.sdl.yaml\n    namespace: {namespace}\n    version: '{version}'\n"
        for namespace, version in versions.items()
    )
    root = tmp_path / "my-scenario.sdl.yaml"
    root.write_text(f"name: my-scenario\nimports:\n{imports}{local}", encoding="utf-8")
    return root


def _saved_body(name: str) -> Callable[[Path], Path]:
    def write(tmp_path: Path) -> Path:
        return _write_sdl(tmp_path / "my-scenario.sdl.yaml", _template_body(name))

    return write


def _saved_importing_scenario(tmp_path: Path) -> Path:
    return _importing_scenario(tmp_path, _template_body("reusable-behavior-unit"), {"alpha": "1.0.0"})


@pytest.mark.parametrize(
    ("write_source", "exit_code", "status"),
    (
        pytest.param(
            _saved_body("action-contract-observation-boundary"), 0, "validate: success", id="contract-binding"
        ),
        pytest.param(_saved_body("tool-affordance"), 0, "validate: success", id="tool-affordance"),
        pytest.param(_saved_body("reusable-behavior-unit"), 0, "validate: success", id="reusable-unit"),
        pytest.param(_saved_importing_scenario, 1, "validate: invalid", id="importing-scenario-rejected"),
    ),
)
def test_documented_cli_command_on_template_bodies(
    tmp_path: Path, write_source: Callable[[Path], Path], exit_code: int, status: str
) -> None:
    result = CliRunner().invoke(app, ["semantic", "validate", str(write_source(tmp_path))])

    assert (result.exit_code, result.output.splitlines()[0]) == (exit_code, status)


@pytest.mark.parametrize(
    ("local", "exit_code", "verified"),
    (
        pytest.param("", 0, True, id="namespaced-refs"),
        pytest.param(_BARE_NAME_REF, 1, False, id="bare-name-ref"),
    ),
)
def test_documented_import_commands_check_the_importing_scenario(
    tmp_path: Path, local: str, exit_code: int, verified: bool
) -> None:
    root = _importing_scenario(tmp_path, _template_body("reusable-behavior-unit"), {"alpha": "1.0.0"}, local)
    runner = CliRunner()

    resolved = runner.invoke(app, ["sdl", "resolve", str(root)])
    checked = runner.invoke(app, ["sdl", "verify-imports", str(root)])

    assert (resolved.exit_code, resolved.output) == (0, f"{tmp_path / 'raes.lock.json'}\n")
    assert (checked.exit_code, "imports verified" in checked.output) == (exit_code, verified)


@pytest.mark.parametrize(
    ("participants", "covered"),
    (
        pytest.param(
            {"participant_refs": ["red-agent"]}, {"alpha": ["alpha"], "bravo": ["bravo"]}, id="participant-refs"
        ),
        pytest.param(
            {"participant_role_refs": ["red"]},
            {"alpha": ["alpha", "bravo"], "bravo": ["alpha", "bravo"]},
            id="role-refs",
        ),
    ),
)
def test_reusable_unit_template_composes_under_each_namespace(
    tmp_path: Path, participants: dict[str, list[str]], covered: dict[str, list[str]]
) -> None:
    unit = _template_body("reusable-behavior-unit")
    spec = unit["behavior_specifications"][_SPEC]
    del spec["participant_refs"]
    spec.update(participants)
    root = _importing_scenario(tmp_path, unit, {"alpha": "1.0.0", "bravo": ">=1,<2"})

    compiled = compile_runtime_model(parse_sdl_file(root)).behavior_specifications

    assert {
        namespace: compiled[f"participant.behavior-specification.{namespace}.{_SPEC}"].participant_addresses
        for namespace in covered
    } == {
        namespace: tuple(f"participant.behavior.{owner}.red-agent" for owner in owners)
        for namespace, owners in covered.items()
    }


def test_importing_scenario_cannot_add_an_affordance_for_an_imported_participant(tmp_path: Path) -> None:
    unit = _template_body("tool-affordance")
    unit["module"] = {
        "id": "example/scanner-toolkit",
        "version": "1.0.0",
        "exports": {
            "content": ["scanner-package"],
            "agents": ["red-agent"],
            "action_contracts": ["scan"],
            "observation_boundaries": ["red-view"],
        },
    }
    root = _importing_scenario(tmp_path, unit, {"alpha": "1.0.0"}, _IMPORTED_AFFORDANCE)

    with pytest.raises(
        SDLValidationError, match="must be explicitly classified by observation boundary 'alpha.red-view'"
    ):
        parse_sdl_file(root)


def test_invalid_declaration_reports_a_diagnostic_only_outside_an_import(tmp_path: Path) -> None:
    unit = _template_body("reusable-behavior-unit")
    unit["behavior_specifications"][_SPEC]["lifecycle_state"] = "retired"
    root = _importing_scenario(tmp_path, unit, {"alpha": "1.0.0"})

    with pytest.raises(SDLParseError, match="lifecycle_state"):
        parse_sdl_file(tmp_path / "unit.sdl.yaml")
    with pytest.raises(ValidationError):
        parse_sdl_file(root)


def test_malformed_import_version_range_raises_a_raw_specifier_error(tmp_path: Path) -> None:
    root = _importing_scenario(tmp_path, _template_body("reusable-behavior-unit"), {"alpha": ">=1,<<2"})

    with pytest.raises(InvalidSpecifier, match="<<2"):
        parse_sdl_file(root)


def test_importing_scenario_can_bind_an_unexported_declaration_by_its_private_name(tmp_path: Path) -> None:
    unit = _template_body("reusable-behavior-unit")
    unit["module"]["exports"] = {"behavior_specifications": [_SPEC]}
    root = _importing_scenario(tmp_path, unit, {"alpha": "1.0.0"}, _PRIVATE_NAME_REF)

    compiled = compile_runtime_model(parse_sdl_file(root)).behavior_specifications

    assert compiled["participant.behavior-specification.local-scan"].participant_addresses == (
        "participant.behavior.alpha.__private.red-agent",
    )
