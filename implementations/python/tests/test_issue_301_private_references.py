"""Authored participant references cannot bypass module exports (#1498)."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from raes import SDLInstantiationError, SDLParseError, instantiate_scenario, parse_sdl_file
from raes._behavior_authoring import validate_authored_behavior_references
from test_issue_297_behavior_authoring import UNIT
from tool_profile_support import toolkit_text

PRIVATE = "alpha.__private.hidden"
AGENT_FIELDS = (
    "affiliations",
    "actions",
    "observation_boundaries",
    "starting_accounts",
    "allowed_subnets",
    "starting_assertions",
    "authority_anchors",
    "operating_scope",
)
LIST_PATHS = [*(("agents", "subject", field, 0) for field in AGENT_FIELDS)]
LIST_PATHS += [
    ("agents", "subject", "initial_knowledge", field, 0) for field in ("hosts", "subnets", "services", "accounts")
]
LIST_PATHS += [
    ("behavior_specifications", "profile", "tool_affordances", "binding", field, 0)
    for field in ("participant_refs", "action_contract_refs", "observation_boundary_refs")
]
SCALAR_PATHS = [("agents", "subject", "interactive_access", "shell", field) for field in ("target_ref", "account_ref")]
SCALAR_PATHS += [("behavior_specifications", "profile", "tool_affordances", "binding", "tool_ref")]
SCALAR_PATHS += [
    ("behavior_specifications", "profile", "participant_inject_deliveries", "delivery", field)
    for field in (
        "participant_ref",
        "inject_ref",
        "observation_boundary_ref",
        "source_item_ref",
        "result_item_ref",
        "controller_ref",
    )
]
LIST_PATHS += [
    ("behavior_specifications", "profile", "participant_inject_deliveries", "delivery", field, 0)
    for field in (
        "temporal_constraint_refs",
        "evidence_requirement_refs",
        "control_authority_scope_refs",
        "control_evidence_refs",
    )
]
SCALAR_PATHS += [
    ("behavior_specifications", "profile", "participant_inject_deliveries", "delivery", "occurrence", field)
    for field in ("event_ref", "script_ref", "story_ref")
]


def _document_at(path, value):
    node = value
    for part in reversed(path):
        node = [node] if part == 0 else {part: node}
    return node


@pytest.mark.parametrize("path", LIST_PATHS + SCALAR_PATHS)
def test_private_reference_guard_checks_each_participant_reference_boundary(path):
    document = _document_at(path, PRIVATE)
    with pytest.raises(ValidationError) as excinfo:
        validate_authored_behavior_references(document)
    assert [error["loc"] for error in excinfo.value.errors()] == [path]

    # Only the exact value at the exact location may come from composition.
    validate_authored_behavior_references(document, generated_from=deepcopy(document))
    with pytest.raises(ValidationError):
        validate_authored_behavior_references(document, generated_from=_document_at(path, PRIVATE + "-other"))


def _importer(tmp_path: Path, document):
    unit = yaml.safe_load(UNIT.read_text())
    unit["module"].pop("exports")
    unit["content"] = {"scanner-package": {"type": "file", "target": "web", "path": "/opt/scanner"}}
    (tmp_path / "unit.sdl.yaml").write_text(yaml.safe_dump(unit))
    document["imports"] = [{"source": "local:unit.sdl.yaml", "namespace": "alpha", "version": "1.2.0"}]
    root = tmp_path / "importer.sdl.yaml"
    root.write_text(yaml.safe_dump(document))
    return root


def test_importing_participant_cannot_name_private_module_declarations(tmp_path):
    root = _importer(
        tmp_path,
        {
            "name": "private-importer",
            "agents": {
                "subject": {
                    "affiliations": ["alpha.__private.red-team"],
                    "actions": ["alpha.__private.scan"],
                    "observation_boundaries": ["alpha.__private.red-view"],
                }
            },
        },
    )
    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl_file(root)
    assert {d.pointer for d in excinfo.value.diagnostics} == {
        f"/agents/subject/{field}/0" for field in ("affiliations", "actions", "observation_boundaries")
    }
    assert all(d.source == str(root) for d in excinfo.value.diagnostics)


@pytest.mark.parametrize("prefix", ("", "content."))
def test_tool_reference_cannot_name_private_module_content(tmp_path, prefix):
    document = yaml.safe_load(toolkit_text())
    document["behavior_specifications"]["toolkit"]["tool_affordances"]["scanner-blue"]["tool_ref"] = (
        prefix + "alpha.__private.scanner-package"
    )
    root = _importer(tmp_path, document)
    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl_file(root)
    assert [d.pointer for d in excinfo.value.diagnostics] == [
        "/behavior_specifications/toolkit/tool_affordances/scanner-blue/tool_ref"
    ]
    assert excinfo.value.diagnostics[0].source == str(root)


def test_parameter_cannot_introduce_private_tool_reference(tmp_path):
    document = yaml.safe_load(toolkit_text())
    document["variables"] = {"selected": {"type": "string", "default": "alpha.__private.scanner-package"}}
    document["behavior_specifications"]["toolkit"]["tool_affordances"]["scanner-blue"]["tool_ref"] = "${selected}"
    scenario = parse_sdl_file(_importer(tmp_path, document))
    with pytest.raises(SDLInstantiationError, match="tool_affordances/scanner-blue/tool_ref"):
        instantiate_scenario(scenario)
