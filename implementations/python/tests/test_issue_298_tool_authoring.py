"""Participant tool authoring across composition and compilation (issue #298, DSL-117).

A reusable unit that declares a tool affordance and an SSH access carrier is
parsed on its own and imported twice under distinct namespaces. The importing
scenario adds local participants and a local tool affordance over an imported
action and tool. Each binding is checked after composition and compilation,
broken bindings fail closed, and a declared or displayed tool neither admits
an invocation nor records one. Composition and declaration rename share one
reference rewrite, so renaming the tool content is checked here too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from paths import REPO_ROOT
from raes import (
    RenameSDLDeclarationRequest,
    SDLValidationError,
    parse_sdl,
    parse_sdl_file,
    rename_sdl_declaration,
)
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.compiler import compile_runtime_model
from raes_runtime.control_plane import RuntimeControlPlane

FIXTURES = Path(__file__).parent / "fixtures" / "tool-authoring"
UNIT = FIXTURES / "scanner-toolkit.sdl.yaml"
ROOT = FIXTURES / "operator-console.sdl.yaml"
AUTHORING_SCHEMA = REPO_ROOT / "contracts" / "schemas" / "sdl" / "sdl-authoring-input-v1.json"
NAMESPACES = ("alpha", "bravo")
REUSABLE = "red-scan-behavior"
LOCAL = "operator-scan"
SHARED = "shared-scanner"
SPEC_ADDRESS = "participant.behavior-specification."
LOCAL_AFFORDANCE = f"{SPEC_ADDRESS}{LOCAL}.tool-affordance.{SHARED}"
OPERATOR = "participant.behavior.operator"
AUDITOR = "participant.behavior.auditor"
IMPORTED_SCAN = "participant.action-contract.alpha.scan"
IMPORTED_TOOLS = [f"provision.content.{namespace}.scanner-package" for namespace in NAMESPACES]


def _rewritten(source: Path, edits: tuple[tuple[str, str], ...]) -> str:
    text = source.read_text(encoding="utf-8")
    for authored, replacement in edits:
        assert text.count(authored) == 1, authored
        text = text.replace(authored, replacement)
    return text


def _tool_ref_edit(authored: str, spelling: str) -> tuple[str, str]:
    """Edit that respells a fixture affordance's authored tool_ref."""

    return f"        tool_ref: {authored}\n", f"        tool_ref: {spelling}\n"


def _parse_pair(tmp_path: Path, *, unit_edits=(), root_edits=()):
    """Parse edited copies of both fixtures from one directory, as authored."""

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


def _imported_tool_addresses(model) -> list[str]:
    return [
        model.tool_affordances[f"{SPEC_ADDRESS}{namespace}.{REUSABLE}.tool-affordance.network-scanner"].tool_address
        for namespace in NAMESPACES
    ]


@pytest.mark.parametrize(
    ("document", "prefix"),
    [(UNIT, ""), (ROOT, "alpha."), (ROOT, "bravo.")],
    ids=["standalone", "alpha", "bravo"],
)
def test_reusable_tool_bindings_resolve_inside_their_own_namespace(document: Path, prefix: str):
    model = compile_runtime_model(parse_sdl_file(document))

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


@pytest.mark.parametrize("tool_ref", ["scanner-package", "content.scanner-package"], ids=["bare", "qualified"])
def test_imported_affordance_keeps_its_own_tool_when_the_importer_declares_the_same_name(tmp_path: Path, tool_ref: str):
    model = compile_runtime_model(_parse_pair(tmp_path, unit_edits=(_tool_ref_edit("scanner-package", tool_ref),)))

    assert _imported_tool_addresses(model) == IMPORTED_TOOLS
    assert model.tool_affordances[LOCAL_AFFORDANCE].tool_address == "provision.content.alpha.scanner-package"


def test_bare_tool_ref_keeps_its_content_binding_when_a_private_unit_declaration_shares_the_name(tmp_path: Path):
    """The unit alone rejects the ambiguous bare ref; composition keeps the binding it had before #298."""

    shared_name = (
        "\nbehavior_specifications:\n",
        "\nrelationships:\n  scanner-package: {type: connects_to, source: web, target: lan}\nbehavior_specifications:\n",
    )
    with pytest.raises(SDLValidationError, match="tool_ref 'scanner-package' is ambiguous"):
        parse_sdl(_rewritten(UNIT, (shared_name,)))

    model = compile_runtime_model(_parse_pair(tmp_path, unit_edits=(shared_name,)))

    assert _imported_tool_addresses(model) == IMPORTED_TOOLS


@pytest.mark.parametrize(
    ("tool_ref", "renamed_ref"),
    [("scanner-package", "scanner-kit"), ("content.scanner-package", "content.scanner-kit")],
    ids=["bare", "qualified"],
)
def test_renaming_the_tool_content_rewrites_either_tool_ref_spelling(tool_ref: str, renamed_ref: str):
    unit = parse_sdl(_rewritten(UNIT, (_tool_ref_edit("scanner-package", tool_ref),)))

    result = rename_sdl_declaration(
        unit,
        RenameSDLDeclarationRequest(target_address="content.scanner-package", new_local_name="scanner-kit"),
    )

    assert [diagnostic.code for diagnostic in result.report.diagnostics] == []
    assert result.succeeded
    assert result.output.behavior_specifications[REUSABLE].tool_affordances["network-scanner"].tool_ref == renamed_ref
    affordance = compile_runtime_model(result.output).tool_affordances[
        f"{SPEC_ADDRESS}{REUSABLE}.tool-affordance.network-scanner"
    ]
    assert affordance.tool_address == "provision.content.scanner-kit"


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
            (("{target_ref: web, channel: ssh, account_ref: operator}", "{target_ref: lan, channel: ssh}"),),
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
            (("{target_ref: alpha.web, channel: rdp}", "{target_ref: alpha.lan, channel: rdp}"),),
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
