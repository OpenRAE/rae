"""Reusable and scenario-local participant behavior authoring (issue #297, DSL-116).

One reusable unit is parsed on its own and then imported twice under distinct
namespaces next to a scenario-local declaration. Each reference kind is checked
after composition and compilation. Broken references, ambiguous names, invalid
declaration versions, and conflicting declarations must fail closed with
diagnostics that name the declaration and the offending ref, field or name.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from paths import REPO_ROOT
from raes import SDLParseError, SDLValidationError, parse_sdl_file
from raes_processor.compiler import compile_runtime_model

FIXTURES = Path(__file__).parent / "fixtures" / "behavior-authoring"
UNIT = FIXTURES / "scan-behavior.sdl.yaml"
ROOT = FIXTURES / "twice-imported.sdl.yaml"
AUTHORING_SCHEMA = REPO_ROOT / "contracts" / "schemas" / "sdl" / "sdl-authoring-input-v1.json"
NAMESPACES = ("alpha", "bravo")
REUSABLE = "red-scan-behavior"
LOCAL = "joint-oversight"
SPEC_ADDRESS = "participant.behavior-specification."
AUDIT_UNIT = """\
name: audit-behavior
module:
  id: acme/audit-behavior
  version: 1.0.0
  exports:
    behavior_specifications: [red-scan-behavior]
behavior_specifications:
  red-scan-behavior:
    semantic_version: 2.0.0
    participant_role_refs: [red]
    behavior_mode: scripted
"""


def _edited(text: str, edits: tuple[tuple[str, str], ...]) -> str:
    for authored, replacement in edits:
        assert text.count(authored) == 1, authored
        text = text.replace(authored, replacement)
    return text


def _compose(tmp_path: Path, *, unit_edits=(), root_edits=()):
    """Parse an edited copy of the fixture pair, keeping the import layout."""

    (tmp_path / UNIT.name).write_text(_edited(UNIT.read_text(encoding="utf-8"), unit_edits), encoding="utf-8")
    (tmp_path / ROOT.name).write_text(_edited(ROOT.read_text(encoding="utf-8"), root_edits), encoding="utf-8")
    return parse_sdl_file(tmp_path / ROOT.name)


def _per_namespace(template: str) -> tuple[str, ...]:
    return tuple(template.format(ns=namespace) for namespace in NAMESPACES)


@pytest.mark.parametrize(
    ("document", "prefix"),
    [(UNIT, ""), (ROOT, "alpha."), (ROOT, "bravo.")],
    ids=["standalone", "alpha", "bravo"],
)
def test_reusable_declaration_resolves_inside_its_own_namespace(document: Path, prefix: str):
    scenario = parse_sdl_file(document)

    spec = scenario.behavior_specifications[prefix + REUSABLE]
    assert spec.participant_refs == [f"{prefix}red-agent"]
    assert spec.action_contract_refs == [f"{prefix}scan"]
    assert spec.observation_boundary_refs == [f"{prefix}red-view"]
    assert spec.outcome_interpretation_rule_refs == [f"{prefix}scan-outcome"]
    assert spec.authority_scope_refs == [f"nodes.{prefix}web.services.http"]

    compiled = compile_runtime_model(scenario).behavior_specifications[SPEC_ADDRESS + prefix + REUSABLE]
    assert compiled.participant_addresses == (f"participant.behavior.{prefix}red-agent",)
    assert compiled.action_contract_addresses == (f"participant.action-contract.{prefix}scan",)
    assert compiled.observation_boundary_addresses == (f"participant.observation-boundary.{prefix}red-view",)
    assert compiled.outcome_interpretation_rule_addresses == (
        f"participant.outcome-interpretation-rule.{prefix}scan-outcome",
    )
    assert compiled.authority_scope_addresses == (f"provision.node.{prefix}web.service.http",)
    assert (compiled.semantic_version, compiled.lifecycle_state) == ("1.0.0", "active")


def test_scenario_local_declaration_binds_both_imports_by_qualified_name_and_role():
    compiled = compile_runtime_model(parse_sdl_file(ROOT)).behavior_specifications[SPEC_ADDRESS + LOCAL]

    assert compiled.participant_role_refs == ("red",)
    assert compiled.participant_addresses == _per_namespace("participant.behavior.{ns}.red-agent")
    assert compiled.action_contract_addresses == _per_namespace("participant.action-contract.{ns}.scan")
    assert compiled.observation_boundary_addresses == _per_namespace("participant.observation-boundary.{ns}.red-view")
    assert compiled.outcome_interpretation_rule_addresses == _per_namespace(
        "participant.outcome-interpretation-rule.{ns}.scan-outcome"
    )
    assert compiled.authority_scope_addresses == _per_namespace("provision.node.{ns}.web.service.http")
    assert compiled.lifecycle_state == "draft"


@pytest.mark.parametrize(("document", "spec_name"), [(UNIT, REUSABLE), (ROOT, LOCAL)], ids=["reusable", "local"])
def test_published_authoring_schema_admits_both_declaration_forms(document: Path, spec_name: str):
    validator = Draft202012Validator(json.loads(AUTHORING_SCHEMA.read_text(encoding="utf-8")))
    authored = yaml.safe_load(document.read_text(encoding="utf-8"))
    assert list(validator.iter_errors(authored)) == []

    del authored["behavior_specifications"][spec_name]["semantic_version"]
    errors = [(list(error.path), error.validator) for error in validator.iter_errors(authored)]
    assert errors == [(["behavior_specifications", spec_name], "required")]


@pytest.mark.parametrize(
    ("authored", "replacement", "message"),
    [
        (
            "participant_role_refs: [red]",
            "participant_refs: [red-agent]",
            "participant_ref 'red-agent' does not reference a declared agent",
        ),
        (
            "participant_role_refs: [red]",
            "participant_role_refs: [blue]",
            "participant_role_ref 'blue' does not match a declared participant role",
        ),
        (
            "action_contract_refs: [alpha.scan, bravo.scan]",
            "action_contract_refs: [scan]",
            "action_contract_ref 'scan' does not reference a declared action_contract",
        ),
        (
            "observation_boundary_refs: [alpha.red-view, bravo.red-view]",
            "observation_boundary_refs: [red-view]",
            "observation_boundary_ref 'red-view' does not reference a declared observation_boundary",
        ),
        (
            "outcome_interpretation_rule_refs: [alpha.scan-outcome, bravo.scan-outcome]",
            "outcome_interpretation_rule_refs: [scan-outcome]",
            "outcome_interpretation_rule_ref 'scan-outcome' does not reference a declared outcome_interpretation_rule",
        ),
        (
            "authority_scope_refs: [nodes.alpha.web.services.http, nodes.bravo.web.services.http]",
            "authority_scope_refs: [nodes.web.services.http]",
            "authority_scope_ref 'nodes.web.services.http' does not reference any defined targetable element",
        ),
    ],
    ids=["participant", "role", "action", "observation", "outcome", "authority"],
)
def test_scenario_local_declaration_cannot_reach_unqualified_import_names(
    tmp_path: Path, authored: str, replacement: str, message: str
):
    with pytest.raises(SDLValidationError) as excinfo:
        _compose(tmp_path, root_edits=((authored, replacement),))

    assert excinfo.value.errors == [f"Behavior specification '{LOCAL}' {message}"]


def test_unexported_declarations_stay_private_to_each_import(tmp_path: Path):
    unexport = ("    outcome_interpretation_rules: [scan-outcome]\n", "")
    with pytest.raises(SDLValidationError) as excinfo:
        _compose(tmp_path, unit_edits=(unexport,))

    assert excinfo.value.errors == list(
        _per_namespace(
            f"Behavior specification '{LOCAL}' outcome_interpretation_rule_ref '{{ns}}.scan-outcome' "
            "does not reference a declared outcome_interpretation_rule"
        )
    )

    drop_local_outcomes = ("    outcome_interpretation_rule_refs: [alpha.scan-outcome, bravo.scan-outcome]\n", "")
    scenario = _compose(tmp_path, unit_edits=(unexport,), root_edits=(drop_local_outcomes,))
    compiled = compile_runtime_model(scenario).behavior_specifications
    private_rules = tuple(
        compiled[f"{SPEC_ADDRESS}{namespace}.{REUSABLE}"].outcome_interpretation_rule_addresses
        for namespace in NAMESPACES
    )
    assert private_rules == tuple(
        (address,) for address in _per_namespace("participant.outcome-interpretation-rule.{ns}.__private.scan-outcome")
    )


@pytest.mark.parametrize(
    ("unit_edits", "message"),
    [
        (
            (("    action_contract_refs: [scan]\n", "    action_contract_refs: [exploit]\n"),),
            "action_contract_ref 'exploit' does not reference a declared action_contract",
        ),
        (
            (
                ("    nodes: [web]\n", "    nodes: [web]\n    content: [web]\n"),
                (
                    "entities:\n",
                    "content:\n  web:\n    type: file\n    target: web\n    path: /srv/index.html\nentities:\n",
                ),
                ("    authority_scope_refs: [nodes.web.services.http]\n", "    authority_scope_refs: [web]\n"),
            ),
            "authority_scope_ref '{ns}.web' is ambiguous; use one of: content.{ns}.web, nodes.{ns}.web",
        ),
    ],
    ids=["dangling", "ambiguous"],
)
def test_reused_unit_reports_each_broken_reference_once_per_namespace(
    tmp_path: Path, unit_edits: tuple[tuple[str, str], ...], message: str
):
    with pytest.raises(SDLValidationError) as excinfo:
        _compose(tmp_path, unit_edits=unit_edits)

    assert excinfo.value.errors == list(_per_namespace(f"Behavior specification '{{ns}}.{REUSABLE}' {message}"))


def test_conflicting_behavior_declarations_in_one_namespace_are_rejected(tmp_path: Path):
    (tmp_path / "audit-behavior.sdl.yaml").write_text(AUDIT_UNIT, encoding="utf-8")
    second_alpha_import = (
        '    version: ">=1.2,<2"\n',
        '    version: ">=1.2,<2"\n  - source: local:audit-behavior.sdl.yaml\n    namespace: alpha\n',
    )

    with pytest.raises(SDLParseError, match=r"collides on behavior_specifications: alpha\.red-scan-behavior$"):
        _compose(tmp_path, root_edits=(second_alpha_import,))


@pytest.mark.parametrize(
    ("authored", "replacement", "field"),
    [
        ("    semantic_version: 1.0.0\n", "    semantic_version: ''\n", "semantic_version"),
        ("    lifecycle_state: draft\n", "    lifecycle_state: retired\n", "lifecycle_state"),
    ],
    ids=["empty-version", "unknown-lifecycle"],
)
def test_scenario_local_declaration_version_fields_fail_closed(
    tmp_path: Path, authored: str, replacement: str, field: str
):
    with pytest.raises(SDLParseError) as excinfo:
        _compose(tmp_path, root_edits=((authored, replacement),))

    diagnostics = [(diagnostic.code, diagnostic.pointer) for diagnostic in excinfo.value.diagnostics]
    assert diagnostics == [("sdl.model.invalid", f"/behavior_specifications/{LOCAL}/{field}")]
