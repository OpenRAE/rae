"""Reusable and scenario-local participant behavior authoring (issue #297, DSL-116).

One reusable unit is parsed on its own and then imported twice under distinct
namespaces next to a scenario-local declaration. Each reference kind is checked
after composition and compilation. Broken references, ambiguous names, invalid
declaration versions, and conflicting declarations must fail closed with
diagnostics that name the declaration and the offending ref, field or name.

Some cases pin gaps that the DSL-116 Fulfillment boundary records rather than
fixes: authored ``__private`` refs and role refs still reach unexported
declarations, a unit ref that dangles on its own binds a same-named declaration
of the importing scenario, and the published schema admits an empty
``semantic_version`` that the parser rejects.
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
DANGLING_ACTION = ("    action_contract_refs: [scan]\n", "    action_contract_refs: [exploit]\n")
IMPORTER_EXPLOIT = """\
action_contracts:
  exploit:
    semantic_version: 1.0.0
    behavioral_granularity: atomic
    procedure_basis: exploit step declared by the importing scenario
    realization_profile: backend-declared
    fidelity_claim: records participant exploit intent
    preconditions:
      - precondition_id: authority-in-scope
        precondition_class: authority
        description: the participant is authorized to act on the web node
    effects:
      - effect_id: no-effect
        effect_class: no_effect
        description: the fixture declares no environment effect
    failure_classes: [unknown]
"""
IMPORTER_GATEWAY = """\
nodes:
  gateway:
    type: compute
    resources: {ram: 1 GiB, cpu: 1}
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

    # Parity gap in the DSL-116 Fulfillment boundary: the parser rejects this empty version.
    authored["behavior_specifications"][spec_name]["semantic_version"] = ""
    assert list(validator.iter_errors(authored)) == []


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
def test_scenario_local_declaration_rejects_unbound_refs(tmp_path: Path, authored: str, replacement: str, message: str):
    with pytest.raises(SDLValidationError) as excinfo:
        _compose(tmp_path, root_edits=((authored, replacement),))

    assert excinfo.value.errors == [f"Behavior specification '{LOCAL}' {message}"]


def test_unexported_declarations_are_unreachable_under_their_exported_name(tmp_path: Path):
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
    ("unexport", "authored", "respelled", "field", "address"),
    [
        (
            ("    agents: [red-agent]\n", ""),
            "participant_role_refs: [red]",
            "participant_refs: [alpha.__private.red-agent, bravo.__private.red-agent]",
            "participant_addresses",
            "participant.behavior.{ns}.__private.red-agent",
        ),
        (
            ("    action_contracts: [scan]\n", ""),
            "action_contract_refs: [alpha.scan, bravo.scan]",
            "action_contract_refs: [alpha.__private.scan, bravo.__private.scan]",
            "action_contract_addresses",
            "participant.action-contract.{ns}.__private.scan",
        ),
        (
            # The unit's agent repeats this export line, so the edit anchors on the next export.
            ("    observation_boundaries: [red-view]\n    outcome", "    outcome"),
            "observation_boundary_refs: [alpha.red-view, bravo.red-view]",
            "observation_boundary_refs: [alpha.__private.red-view, bravo.__private.red-view]",
            "observation_boundary_addresses",
            "participant.observation-boundary.{ns}.__private.red-view",
        ),
        (
            ("    outcome_interpretation_rules: [scan-outcome]\n", ""),
            "outcome_interpretation_rule_refs: [alpha.scan-outcome, bravo.scan-outcome]",
            "outcome_interpretation_rule_refs: [alpha.__private.scan-outcome, bravo.__private.scan-outcome]",
            "outcome_interpretation_rule_addresses",
            "participant.outcome-interpretation-rule.{ns}.__private.scan-outcome",
        ),
        (
            ("    nodes: [web]\n", ""),
            "authority_scope_refs: [nodes.alpha.web.services.http, nodes.bravo.web.services.http]",
            "authority_scope_refs: [nodes.alpha.__private.web.services.http, nodes.bravo.__private.web.services.http]",
            "authority_scope_addresses",
            "provision.node.{ns}.__private.web.service.http",
        ),
        (
            # Only the unit's exports change; the role ref stays as authored.
            ("    entities: [red-team]\n    agents: [red-agent]\n", ""),
            "participant_role_refs: [red]",
            "participant_role_refs: [red]",
            "participant_addresses",
            "participant.behavior.{ns}.__private.red-agent",
        ),
    ],
    ids=["participant", "action", "observation", "outcome", "authority", "role"],
)
def test_unexported_declarations_stay_reachable_by_private_name_and_role(
    tmp_path: Path, unexport: tuple[str, str], authored: str, respelled: str, field: str, address: str
):
    """Pins a gap in the DSL-116 Fulfillment boundary rather than the language rule.

    ``specs/sdl/document-model.md`` and ADR-076 make ``__private`` invalid author
    input, and ADR-053 makes its use a hard error, yet these authored refs bind.
    The role case reaches the unexported participants without naming them.
    """

    scenario = _compose(tmp_path, unit_edits=(unexport,), root_edits=((authored, respelled),))

    compiled = compile_runtime_model(scenario).behavior_specifications[SPEC_ADDRESS + LOCAL]
    assert getattr(compiled, field) == _per_namespace(address)


@pytest.mark.parametrize(
    ("unit_edits", "message"),
    [
        (
            (DANGLING_ACTION,),
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
    """The importing scenario declares nothing the broken ref names; the next test covers the case where it does."""

    with pytest.raises(SDLValidationError) as excinfo:
        _compose(tmp_path, unit_edits=unit_edits)

    assert excinfo.value.errors == list(_per_namespace(f"Behavior specification '{{ns}}.{REUSABLE}' {message}"))


@pytest.mark.parametrize(
    ("unit_edit", "importer_section", "field", "addresses"),
    [
        (DANGLING_ACTION, IMPORTER_EXPLOIT, "action_contract_addresses", ("participant.action-contract.exploit",)),
        (
            (
                "    authority_scope_refs: [nodes.web.services.http]\n",
                "    authority_scope_refs: [nodes.web.services.http, nodes.gateway]\n",
            ),
            IMPORTER_GATEWAY,
            "authority_scope_addresses",
            ("provision.node.{ns}.web.service.http", "provision.node.gateway"),
        ),
    ],
    ids=["action", "authority"],
)
def test_dangling_unit_ref_binds_a_same_named_declaration_of_the_importing_scenario(
    tmp_path: Path, unit_edit: tuple[str, str], importer_section: str, field: str, addresses: tuple[str, ...]
):
    """Pins a gap in the DSL-116 Fulfillment boundary: composition renames only the names a unit declares."""

    declare = ("behavior_specifications:\n", importer_section + "behavior_specifications:\n")
    scenario = _compose(tmp_path, unit_edits=(unit_edit,), root_edits=(declare,))

    compiled = compile_runtime_model(scenario).behavior_specifications
    for namespace in NAMESPACES:
        bound = getattr(compiled[f"{SPEC_ADDRESS}{namespace}.{REUSABLE}"], field)
        assert bound == tuple(address.format(ns=namespace) for address in addresses)


def test_conflicting_behavior_declarations_in_one_namespace_are_rejected(tmp_path: Path):
    (tmp_path / "audit-behavior.sdl.yaml").write_text(AUDIT_UNIT, encoding="utf-8")
    second_alpha_import = (
        '    version: ">=1.2,<2"\n',
        '    version: ">=1.2,<2"\n  - source: local:audit-behavior.sdl.yaml\n    namespace: alpha\n',
    )

    with pytest.raises(SDLParseError, match=r"collides on behavior_specifications: alpha\.red-scan-behavior$"):
        _compose(tmp_path, root_edits=(second_alpha_import,))


def test_ranged_import_rejects_a_module_version_outside_its_range(tmp_path: Path):
    out_of_range = ('    version: ">=1.2,<2"\n', '    version: ">=2,<3"\n')

    with pytest.raises(SDLParseError, match=r"requested version '>=2,<3' but module declares '1\.2\.0'$"):
        _compose(tmp_path, root_edits=(out_of_range,))


@pytest.mark.parametrize(
    ("authored", "replacement", "field"),
    [
        ("    semantic_version: 1.0.0\n", "    semantic_version: ''\n", "semantic_version"),
        ("    lifecycle_state: draft\n", "    lifecycle_state: retired\n", "lifecycle_state"),
    ],
    ids=["empty-version", "unknown-lifecycle"],
)
def test_scenario_local_declaration_version_and_lifecycle_fields_fail_closed(
    tmp_path: Path, authored: str, replacement: str, field: str
):
    with pytest.raises(SDLParseError) as excinfo:
        _compose(tmp_path, root_edits=((authored, replacement),))

    diagnostics = [(diagnostic.code, diagnostic.pointer) for diagnostic in excinfo.value.diagnostics]
    assert diagnostics == [("sdl.model.invalid", f"/behavior_specifications/{LOCAL}/{field}")]
