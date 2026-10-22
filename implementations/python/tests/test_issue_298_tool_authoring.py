"""Participant tool authoring across composition and compilation (issue #298, DSL-117).

The example pair in ``examples/scenarios/participant-tools`` is the fixture. A
reusable unit that declares a tool affordance and an SSH access carrier is
parsed on its own and imported twice under distinct namespaces. The importing
scenario adds local participants and a local tool affordance over an imported
action and tool. Each binding is checked after composition and compilation.
Broken, ambiguous and unsupported bindings fail closed with the diagnostics the
unit gets on its own, and a declared or displayed tool neither admits an
invocation nor records one. Composition and declaration rename share one
reference rewrite, so renaming the tool content and the access account is
checked here too.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from paths import REPO_ROOT
from raes import (
    RenameSDLDeclarationRequest,
    SDLParseError,
    SDLValidationError,
    parse_sdl,
    parse_sdl_file,
    rename_sdl_declaration,
)
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.compiler import compile_runtime_model
from raes_runtime.control_plane import RuntimeControlPlane

EXAMPLES = REPO_ROOT / "examples" / "scenarios" / "participant-tools"
UNIT = EXAMPLES / "tool-kit.sdl.yaml"
ROOT = EXAMPLES / "twice-imported.sdl.yaml"
AUTHORING_SCHEMA = REPO_ROOT / "contracts" / "schemas" / "sdl" / "sdl-authoring-input-v1.json"
NAMESPACES = ("alpha", "bravo")
REUSABLE = "red-scan-behavior"
LOCAL = "operator-scan"
SHARED = "shared-scanner"
SPEC_ADDRESS = "participant.behavior-specification."
REUSABLE_AFFORDANCE = f"{SPEC_ADDRESS}{REUSABLE}.tool-affordance.network-scanner"
LOCAL_AFFORDANCE = f"{SPEC_ADDRESS}{LOCAL}.tool-affordance.{SHARED}"
OPERATOR = "participant.behavior.operator"
AUDITOR = "participant.behavior.auditor"
IMPORTED_SCAN = "participant.action-contract.alpha.scan"
IMPORTED_TOOLS = [f"provision.content.{namespace}.scanner-package" for namespace in NAMESPACES]
UNIT_CARRIER = "{target_ref: web, channel: ssh, account_ref: operator}"
LOCAL_CARRIER = "{target_ref: alpha.web, channel: rdp}"
RELATIONSHIP_CLASH = (
    "\nbehavior_specifications:\n",
    "\nrelationships:\n  scanner-package: {type: connects_to, source: web, target: lan}\nbehavior_specifications:\n",
)
CONTENT_ITEM_CLASH = (
    "content:\n  scanner-package:\n",
    "content:\n  bundle: {type: dataset, target: web, items: [{name: scanner-package}]}\n  scanner-package:\n",
)
CLASH_IDS = ["relationship", "content-item"]


def _rewritten(source: Path, edits: tuple[tuple[str, str], ...]) -> str:
    text = source.read_text(encoding="utf-8")
    for authored, replacement in edits:
        assert text.count(authored) == 1, authored
        text = text.replace(authored, replacement)
    return text


def _tool_ref_edit(authored: str, spelling: str) -> tuple[str, str]:
    """Edit that respells an example affordance's authored tool_ref."""

    return f"        tool_ref: {authored}\n", f"        tool_ref: {spelling}\n"


def _parse_pair(tmp_path: Path, *, unit_edits=(), root_edits=()):
    """Parse edited copies of both examples from one directory, as authored."""

    for source, edits in ((UNIT, unit_edits), (ROOT, root_edits)):
        (tmp_path / source.name).write_text(_rewritten(source, edits), encoding="utf-8")
    return parse_sdl_file(tmp_path / ROOT.name)


def _local_issue(detail: str) -> str:
    return f"Behavior specification '{LOCAL}' tool affordance '{SHARED}' {detail}"


def _access(participant) -> list[tuple[str, str, str, str]]:
    return [
        (item.access_id, item.target_address, item.channel, item.account_address)
        for item in participant.interactive_access
    ]


def _imported_affordance(namespace: str) -> str:
    return f"{SPEC_ADDRESS}{namespace}.{REUSABLE}.tool-affordance.network-scanner"


def _imported_tool_addresses(model) -> list[str]:
    return [model.tool_affordances[_imported_affordance(namespace)].tool_address for namespace in NAMESPACES]


@pytest.mark.parametrize(
    ("document", "prefix"),
    [(UNIT, ""), (ROOT, "alpha."), (ROOT, "bravo.")],
    ids=["standalone", "alpha", "bravo"],
)
def test_reusable_tool_bindings_resolve_inside_their_own_namespace(document: Path, prefix: str):
    scenario = parse_sdl_file(document)
    assert scenario.advisories == []
    model = compile_runtime_model(scenario)

    affordance = model.tool_affordances[f"{SPEC_ADDRESS}{prefix}{REUSABLE}.tool-affordance.network-scanner"]
    assert affordance.behavior_specification_address == f"{SPEC_ADDRESS}{prefix}{REUSABLE}"
    assert affordance.tool_address == f"provision.content.{prefix}scanner-package"
    assert affordance.action_contract_addresses == (f"participant.action-contract.{prefix}scan",)
    assert affordance.observation_boundary_addresses == (f"participant.observation-boundary.{prefix}red-view",)
    assert model.observation_boundaries[f"participant.observation-boundary.{prefix}red-view"].observable_refs == (
        f"behavior_specifications.{prefix}{REUSABLE}.tool_affordances.network-scanner",
    )
    participant = model.participant_behaviors[f"participant.behavior.{prefix}red-agent"]
    assert _access(participant) == [
        ("shell", f"provision.node.{prefix}web", "ssh", f"provision.account.{prefix}operator")
    ]


def test_invocation_interface_is_joined_through_each_imports_own_action_contract():
    """The affordance names the action; the action contract alone owns the arguments."""

    model = compile_runtime_model(parse_sdl_file(ROOT))

    shape_refs = []
    for namespace in NAMESPACES:
        affordance = model.tool_affordances[_imported_affordance(namespace)]
        assert affordance.action_contract_addresses == (f"participant.action-contract.{namespace}.scan",)
        contract = model.action_contracts[affordance.action_contract_addresses[0]]
        assert contract.argument_shape_ref.startswith(f"{contract.address}.argument-shape.sha256-")
        assert [definition["name"] for definition in contract.argument_definitions] == ["profile"]
        assert "argument" not in json.dumps(asdict(affordance))
        shape_refs.append(contract.argument_shape_ref)
    assert shape_refs[0] != shape_refs[1]


@pytest.mark.parametrize("tool_ref", ["scanner-package", "content.scanner-package"], ids=["bare", "qualified"])
def test_imported_affordance_keeps_its_own_tool_when_the_importer_declares_the_same_name(tmp_path: Path, tool_ref: str):
    model = compile_runtime_model(_parse_pair(tmp_path, unit_edits=(_tool_ref_edit("scanner-package", tool_ref),)))

    assert _imported_tool_addresses(model) == IMPORTED_TOOLS
    assert model.tool_affordances[LOCAL_AFFORDANCE].tool_address == "provision.content.alpha.scanner-package"


@pytest.mark.parametrize(
    ("clash", "candidates"),
    [
        (RELATIONSHIP_CLASH, "content.scanner-package, relationships.scanner-package"),
        (CONTENT_ITEM_CLASH, "content.bundle.items.scanner-package, content.scanner-package"),
    ],
    ids=CLASH_IDS,
)
def test_bare_tool_ref_naming_two_unit_declarations_fails_composition_as_it_fails_alone(
    tmp_path: Path, clash: tuple[str, str], candidates: str
):
    """The composed import reports the unit's own addresses, anchored at the unit file, and binds nothing."""

    expected = [
        f"Behavior specification '{REUSABLE}' tool affordance 'network-scanner' "
        f"tool_ref 'scanner-package' is ambiguous; use one of: {candidates}"
    ]
    unit_text = _rewritten(UNIT, (clash,))
    with pytest.raises(SDLValidationError) as standalone:
        parse_sdl(unit_text)
    with pytest.raises(SDLValidationError) as composed:
        _parse_pair(tmp_path, unit_edits=(clash,))

    assert standalone.value.errors == expected
    assert composed.value.errors == expected
    assert composed.value.path == tmp_path / UNIT.name


@pytest.mark.parametrize("clash", [RELATIONSHIP_CLASH, CONTENT_ITEM_CLASH], ids=CLASH_IDS)
def test_qualified_tool_ref_binds_its_own_content_beside_a_clashing_unit_declaration(
    tmp_path: Path, clash: tuple[str, str]
):
    edits = (clash, _tool_ref_edit("scanner-package", "content.scanner-package"))
    assert parse_sdl(_rewritten(UNIT, edits)).advisories == []

    model = compile_runtime_model(_parse_pair(tmp_path, unit_edits=edits))

    assert _imported_tool_addresses(model) == IMPORTED_TOOLS


def test_imported_tool_ref_that_names_only_root_content_binds_the_root_content(tmp_path: Path):
    """Refs that name nothing in the unit resolve against the composed scenario (issue-297 decision)."""

    model = compile_runtime_model(
        _parse_pair(
            tmp_path,
            unit_edits=(_tool_ref_edit("scanner-package", "console-scanner"),),
            root_edits=(("content:\n  scanner-package:\n", "content:\n  console-scanner:\n"),),
        )
    )

    assert _imported_tool_addresses(model) == ["provision.content.console-scanner"] * len(NAMESPACES)


@pytest.mark.parametrize("scope_ref", ["web", "nodes.web"], ids=["ambiguous", "qualified"])
def test_imported_authority_scope_preserves_the_units_resolution(tmp_path: Path, scope_ref: str):
    edits = (
        (
            "\nbehavior_specifications:\n",
            "\nrelationships:\n  web: {type: connects_to, source: nodes.web, target: nodes.lan}\n"
            "behavior_specifications:\n",
        ),
        ("authority_scope_refs: [nodes.web.services.http]", f"authority_scope_refs: [{scope_ref}]"),
    )
    if scope_ref == "web":
        unit_text = _rewritten(UNIT, edits)
        with pytest.raises(SDLValidationError) as standalone:
            parse_sdl(unit_text)
        with pytest.raises(SDLValidationError) as composed:
            _parse_pair(tmp_path, unit_edits=edits)
        assert (
            standalone.value.errors
            == composed.value.errors
            == [
                f"Behavior specification '{REUSABLE}' authority_scope_ref 'web' "
                "is ambiguous; use one of: nodes.web, relationships.web"
            ]
        )
        assert composed.value.path == tmp_path / UNIT.name
    else:
        model = compile_runtime_model(_parse_pair(tmp_path, unit_edits=edits))
        for namespace in NAMESPACES:
            assert model.behavior_specifications[f"{SPEC_ADDRESS}{namespace}.{REUSABLE}"].authority_scope_refs == (
                f"nodes.{namespace}.web",
            )


@pytest.mark.parametrize("spelling", ["alpha.__private.scanner-package", "content.alpha.__private.scanner-package"])
def test_importer_cannot_author_a_private_tool_ref(tmp_path: Path, spelling: str):
    root_edits = (_tool_ref_edit("alpha.scanner-package", spelling),)
    with pytest.raises(SDLParseError) as excinfo:
        _parse_pair(
            tmp_path,
            unit_edits=(("    content: [scanner-package]\n", ""),),
            root_edits=root_edits,
        )
    (diagnostic,) = excinfo.value.diagnostics
    assert diagnostic.code == "sdl.identifier.invalid"
    assert diagnostic.pointer == f"/behavior_specifications/{LOCAL}/tool_affordances/{SHARED}/tool_ref"
    assert diagnostic.source == str(tmp_path / ROOT.name)


@pytest.mark.parametrize("spelling", ["scanner-package", "content.scanner-package"])
def test_composition_and_instantiation_preserve_generated_private_tool_refs(tmp_path: Path, spelling: str):
    from raes import instantiate_scenario

    scenario = _parse_pair(
        tmp_path,
        unit_edits=(("    content: [scanner-package]\n", ""), _tool_ref_edit("scanner-package", spelling)),
        root_edits=(_tool_ref_edit("alpha.scanner-package", "scanner-package"),),
    )
    model = compile_runtime_model(instantiate_scenario(scenario))
    assert _imported_tool_addresses(model) == [
        f"provision.content.{namespace}.__private.scanner-package" for namespace in NAMESPACES
    ]


def test_instantiation_cannot_mint_a_private_tool_ref(tmp_path: Path):
    from raes import SDLInstantiationError, instantiate_scenario

    scenario = _parse_pair(
        tmp_path,
        unit_edits=(("    content: [scanner-package]\n", ""),),
        root_edits=(
            (
                "\nbehavior_specifications:\n",
                "\nvariables:\n  selected-tool:\n    type: string\n    default: alpha.__private.scanner-package\n"
                "behavior_specifications:\n",
            ),
            _tool_ref_edit("alpha.scanner-package", "'${selected-tool}'"),
        ),
    )
    with pytest.raises(SDLInstantiationError, match=f"tool_affordances/{SHARED}/tool_ref"):
        instantiate_scenario(scenario)


@pytest.mark.parametrize("field", ["action_contract_refs", "observation_boundary_refs"])
def test_private_tool_relations_are_rejected_before_semantic_validation(tmp_path: Path, field: str):
    authored = "alpha.scan" if field == "action_contract_refs" else "operator-view"
    with pytest.raises(SDLParseError) as excinfo:
        _parse_pair(
            tmp_path,
            root_edits=((f"        {field}: [{authored}]", f"        {field}: [alpha.__private.binding]"),),
        )
    (diagnostic,) = excinfo.value.diagnostics
    assert diagnostic.code == "sdl.identifier.invalid"
    assert diagnostic.pointer == f"/behavior_specifications/{LOCAL}/tool_affordances/{SHARED}/{field}/0"


@pytest.mark.parametrize("affordances", [None, []])
def test_malformed_affordances_retain_structural_diagnostics(affordances):
    payload = yaml.safe_load(UNIT.read_text(encoding="utf-8"))
    payload["behavior_specifications"][REUSABLE]["tool_affordances"] = affordances
    source = yaml.safe_dump(payload)
    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(source)
    assert excinfo.value.diagnostics[0].code == "sdl.model.invalid"


def test_issue_branch_resolves_dsl_117_and_enforces_all_delivery_ownership(monkeypatch):
    from tools.policy.repository_requirements import RepositoryRequirementClient
    from tools.policy.requirement_scope import evaluate_requirement_scope
    from tools.requirement_context import resolve_requirement_context

    monkeypatch.delenv("RAES_REQUIREMENT_UID", raising=False)
    uid, scope = resolve_requirement_context(REPO_ROOT, "298-tool-authoring-verification")
    assert uid == "DSL-117"
    assert scope is not None
    assert (
        evaluate_requirement_scope(
            REPO_ROOT, list(scope.bindings), client=RepositoryRequirementClient(REPO_ROOT), scope=scope
        )
        == []
    )


@pytest.mark.parametrize(
    ("document", "carrier", "pointer"),
    [
        (UNIT, UNIT_CARRIER, "/agents/red-agent/interactive_access/shell/channel"),
        (ROOT, LOCAL_CARRIER, "/agents/operator/interactive_access/console/channel"),
    ],
    ids=["imported", "local"],
)
def test_unsupported_channel_is_a_bounded_parse_diagnostic_in_the_unit_and_the_importer(
    tmp_path: Path, document: Path, carrier: str, pointer: str
):
    edits = ((carrier, carrier.replace("ssh", "telnet").replace("rdp", "telnet")),)
    edited = {"unit_edits": edits} if document == UNIT else {"root_edits": edits}

    with pytest.raises(SDLParseError) as excinfo:
        _parse_pair(tmp_path, **edited)

    message = "channel must be one of: ssh, rdp"
    assert str(excinfo.value) == f"{tmp_path / document.name}: SDL model validation failed at {pointer}: {message}"
    assert [(item.code, item.pointer, item.message) for item in excinfo.value.diagnostics] == [
        ("sdl.model.invalid", pointer, message)
    ]


def _tool_ref(scenario) -> str:
    return scenario.behavior_specifications[REUSABLE].tool_affordances["network-scanner"].tool_ref


def _account_ref(scenario) -> str:
    return scenario.agents["red-agent"].interactive_access["shell"].account_ref


def _compiled_tool(model) -> str:
    return model.tool_affordances[REUSABLE_AFFORDANCE].tool_address


def _compiled_account(model) -> str:
    return _access(model.participant_behaviors["participant.behavior.red-agent"])[0][3]


@pytest.mark.parametrize(
    ("target", "new_name", "edit", "read_ref", "renamed_ref", "read_compiled", "compiled"),
    [
        (
            "content.scanner-package",
            "scanner-kit",
            _tool_ref_edit("scanner-package", spelling),
            _tool_ref,
            renamed,
            _compiled_tool,
            "provision.content.scanner-kit",
        )
        for spelling, renamed in (
            ("scanner-package", "scanner-kit"),
            ("content.scanner-package", "content.scanner-kit"),
        )
    ]
    + [
        (
            "accounts.operator",
            "analyst",
            ("account_ref: operator}", f"account_ref: {spelling}}}"),
            _account_ref,
            renamed,
            _compiled_account,
            "provision.account.analyst",
        )
        for spelling, renamed in (("operator", "analyst"), ("accounts.operator", "accounts.analyst"))
    ],
    ids=["tool-bare", "tool-qualified", "account-bare", "account-qualified"],
)
def test_renaming_a_declaration_rewrites_either_spelling_of_its_tool_or_access_ref(
    target, new_name, edit, read_ref, renamed_ref, read_compiled, compiled
):
    unit = parse_sdl(_rewritten(UNIT, (edit,)))

    result = rename_sdl_declaration(unit, RenameSDLDeclarationRequest(target_address=target, new_local_name=new_name))

    assert [diagnostic.code for diagnostic in result.report.diagnostics] == []
    assert result.succeeded
    assert read_ref(result.output) == renamed_ref
    assert read_compiled(compile_runtime_model(result.output)) == compiled


def test_local_affordance_binds_an_imported_action_and_tool_for_one_role():
    model = compile_runtime_model(parse_sdl_file(ROOT))

    spec = model.behavior_specifications[SPEC_ADDRESS + LOCAL]
    assert spec.participant_role_refs == ("blue",)
    assert spec.participant_addresses == (OPERATOR,)
    assert spec.tool_affordance_addresses == (LOCAL_AFFORDANCE,)
    affordance = model.tool_affordances[LOCAL_AFFORDANCE]
    assert affordance.tool_address == "provision.content.alpha.scanner-package"
    assert affordance.action_contract_addresses == (IMPORTED_SCAN,)
    assert affordance.observation_boundary_addresses == ("participant.observation-boundary.operator-view",)
    assert _access(model.participant_behaviors[OPERATOR]) == [("console", "provision.node.alpha.web", "rdp", "")]


@pytest.mark.parametrize("relation", ["action_contract_refs", "observation_boundary_refs"])
@pytest.mark.parametrize(
    ("document", "spec_name", "affordance_id"),
    [(UNIT, REUSABLE, "network-scanner"), (ROOT, LOCAL, SHARED)],
    ids=["reusable", "local"],
)
def test_published_authoring_schema_requires_both_affordance_relations(
    document: Path, spec_name: str, affordance_id: str, relation: str
):
    schema = Draft202012Validator(json.loads(AUTHORING_SCHEMA.read_text(encoding="utf-8")))
    payload = yaml.safe_load(document.read_text(encoding="utf-8"))
    assert not list(schema.iter_errors(payload))

    binding = payload["behavior_specifications"][spec_name]["tool_affordances"][affordance_id]
    binding.pop(relation)
    assert [(list(error.path), error.validator, error.message) for error in schema.iter_errors(payload)] == [
        (
            ["behavior_specifications", spec_name, "tool_affordances", affordance_id],
            "required",
            f"'{relation}' is a required property",
        )
    ]


@pytest.mark.parametrize(
    ("unit_edits", "message"),
    [
        (
            (_tool_ref_edit("scanner-package", "scanner-suite"),),
            f"Behavior specification '{{ns}}.{REUSABLE}' tool affordance 'network-scanner' "
            "tool_ref 'scanner-suite' does not reference a declared scenario content identity",
        ),
        (
            (_tool_ref_edit("scanner-package", "web"),),
            f"Behavior specification '{{ns}}.{REUSABLE}' tool affordance 'network-scanner' "
            "tool_ref '{ns}.web' must resolve through the scenario-content tools-and-artifacts reference model",
        ),
        (
            (("    actions: [scan]\n", "    actions: []\n"),),
            f"Behavior specification '{{ns}}.{REUSABLE}' tool affordance 'network-scanner' "
            "action_contract_ref '{ns}.scan' is outside participant '{ns}.red-agent' actions",
        ),
        (
            ((UNIT_CARRIER, "{target_ref: lan, channel: ssh}"),),
            "Agent '{ns}.red-agent' interactive_access 'shell' target_ref '{ns}.lan' must reference a compute node",
        ),
    ],
    ids=["dangling-tool", "tool-is-a-node", "action-outside-participant", "switch-carrier"],
)
def test_broken_binding_in_a_reused_unit_is_reported_once_per_namespace(
    tmp_path: Path, unit_edits: tuple[tuple[str, str], ...], message: str
):
    with pytest.raises(SDLValidationError) as excinfo:
        _parse_pair(tmp_path, unit_edits=unit_edits)

    assert excinfo.value.errors == [message.format(ns=namespace) for namespace in NAMESPACES]


@pytest.mark.parametrize(
    ("unit_edits", "root_edits", "errors"),
    [
        (
            (("    content: [scanner-package]\n", ""),),
            (),
            [_local_issue("tool_ref 'alpha.scanner-package' does not reference a declared scenario content identity")],
        ),
        (
            (),
            (_tool_ref_edit("alpha.scanner-package", "alpha.web"),),
            [
                _local_issue(
                    "tool_ref 'alpha.web' must resolve through the scenario-content tools-and-artifacts reference model"
                )
            ],
        ),
        (
            (
                ("    content: [scanner-package]\n", "    content: [scanner-package, web]\n"),
                (
                    "content:\n  scanner-package:\n",
                    "content:\n  web: {type: file, target: web, path: /opt/raes/tools/web}\n  scanner-package:\n",
                ),
            ),
            (_tool_ref_edit("alpha.scanner-package", "alpha.web"),),
            [_local_issue("tool_ref 'alpha.web' is ambiguous; use one of: content.alpha.web, nodes.alpha.web")],
        ),
        (
            (),
            (("        action_contract_refs: [alpha.scan]\n", "        action_contract_refs: [bravo.scan]\n"),),
            [
                _local_issue("action_contract_ref 'bravo.scan' widens its owning behavior specification"),
                _local_issue("action_contract_ref 'bravo.scan' is outside participant 'operator' actions"),
            ],
        ),
        (
            (),
            (("    participant_role_refs: [blue]\n", "    participant_role_refs: [red]\n"),),
            [
                _local_issue("action_contract_ref 'alpha.scan' is outside participant 'bravo.red-agent' actions"),
                _local_issue(
                    "observation_boundary_ref 'operator-view' is outside participant 'alpha.red-agent' "
                    "observation boundaries"
                ),
                _local_issue(
                    "observation_boundary_ref 'operator-view' is outside participant 'bravo.red-agent' "
                    "observation boundaries"
                ),
            ],
        ),
        (
            (),
            (
                ("    participant_role_refs: [blue]\n", "    participant_refs: [alpha.red-agent]\n"),
                ("[operator-view]\n    authority", "[alpha.red-view]\n    authority"),
                (
                    "        observation_boundary_refs: [operator-view]\n",
                    "        observation_boundary_refs: [alpha.red-view]\n",
                ),
            ),
            [
                _local_issue(
                    f"reference 'behavior_specifications.{LOCAL}.tool_affordances.{SHARED}' "
                    "must be explicitly classified by observation boundary 'alpha.red-view'"
                )
            ],
        ),
        (
            (),
            ((LOCAL_CARRIER, "{target_ref: alpha.lan, channel: rdp}"),),
            ["Agent 'operator' interactive_access 'console' target_ref 'alpha.lan' must reference a compute node"],
        ),
    ],
    ids=[
        "unexported-tool",
        "tool-is-a-node",
        "ambiguous-tool",
        "action-from-other-import",
        "role-spans-both-imports",
        "imported-participant-boundary",
        "switch-carrier",
    ],
)
def test_importing_scenario_bindings_fail_closed(
    tmp_path: Path,
    unit_edits: tuple[tuple[str, str], ...],
    root_edits: tuple[tuple[str, str], ...],
    errors: list[str],
):
    with pytest.raises(SDLValidationError) as excinfo:
        _parse_pair(tmp_path, unit_edits=unit_edits, root_edits=root_edits)

    assert excinfo.value.errors == errors


@pytest.mark.parametrize(
    ("participant_address", "action_address", "reason"),
    [
        (
            AUDITOR,
            IMPORTED_SCAN,
            f"action_contract_address '{IMPORTED_SCAN}' is not declared by compiled participant behavior '{AUDITOR}'",
        ),
        (
            OPERATOR,
            LOCAL_AFFORDANCE,
            f"action_contract_address '{LOCAL_AFFORDANCE}' is not declared by compiled participant behavior "
            f"'{OPERATOR}'",
        ),
        (OPERATOR, IMPORTED_SCAN, "'implementation_manifest' and 'implementation_selection'"),
    ],
    ids=["shown-to-a-participant-without-the-action", "tool-address-as-action", "no-implementation-binding"],
)
def test_declared_and_displayed_tool_neither_admits_nor_records_an_invocation(
    participant_address: str, action_address: str, reason: str
):
    model = compile_runtime_model(parse_sdl_file(ROOT))
    participant = model.participant_behaviors[participant_address]
    shown_refs = model.observation_boundaries["participant.observation-boundary.operator-view"].observable_refs
    assert shown_refs == (f"behavior_specifications.{LOCAL}.tool_affordances.{SHARED}",)
    assert participant.observation_boundary_addresses == ("participant.observation-boundary.operator-view",)
    control_plane = RuntimeControlPlane(create_stub_target())
    control_plane.initialize_participant_episode(participant.address, episode_id="episode-1")

    receipt = control_plane.admit_participant_action(
        participant,
        action_contract_address=action_address,
        observation_boundary_address=participant.observation_boundary_addresses[0],
        action_instance_id="scan-0001",
    )

    assert receipt.accepted is False
    assert [reason in diagnostic.message for diagnostic in receipt.diagnostics] == [True]
    assert control_plane.get_operation(receipt.operation_id) is None
    assert control_plane.get_snapshot().snapshot.participant_behavior_history == {}
