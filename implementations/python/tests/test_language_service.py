"""Language-service support for SDL authoring surfaces."""

from __future__ import annotations

import pytest
from raes.language_service import (
    apply_structured_edit,
    language_completions,
    language_diagnostics,
    language_format,
    language_references,
)

SAMPLE_SDL = """\
name: language-service-test
nodes:
  net: {type: Switch}
  net2: {type: Switch}
  web: {type: compute, os: linux, resources: {ram: 2 GiB, cpu: 1}, features: {app: admin}, roles: {admin: www}}
infrastructure:
  net: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  net2: {count: 1, properties: {cidr: 10.0.1.0/24, gateway: 10.0.1.1}}
  web: {count: 1, links: [net]}
features:
  app: {type: Service, source: webapp}
"""

INVALID_REFERENCE_SDL = """\
name: broken
nodes:
  web:
    type: compute
    os: linux
    features: {ghost-feature: admin}
"""


def test_language_completions_include_top_level_sections_and_reference_targets() -> None:
    top_level = language_completions("name: x\n", cursor_path="/")
    top_level_labels = {item["label"] for item in top_level["items"]}
    assert "nodes" in top_level_labels
    assert "workflows" in top_level_labels
    assert "realization" in top_level_labels

    realization_fields = language_completions(
        "name: x\nrealization: {}\n",
        cursor_path="/realization",
    )
    assert {item["label"] for item in realization_fields["items"]} == {"default", "scopes"}

    feature_refs = language_completions(
        SAMPLE_SDL,
        cursor_path="/nodes/web/features",
    )
    labels = {item["label"] for item in feature_refs["items"]}
    assert "app" in labels
    assert any(item["detail"] == "features.app" for item in feature_refs["items"])


def test_language_completions_cover_contexts_and_filters() -> None:
    sdl = """\
name: completion-contexts
nodes:
  web: {type: compute, os: linux, resources: {ram: 2 GiB, cpu: 1}}
conditions:
  alive: {command: "true", interval: 5}
relationships:
  app-to-web: {type: hosted_on, source: web, target: alive}
workflows:
  flow:
    start: start-here
    steps:
      start-here: {type: end}
"""

    section_fields = language_completions(sdl, cursor_path="/nodes/web", prefix="res")
    assert section_fields["context"] == "section:nodes"
    assert [item["label"] for item in section_fields["items"]] == ["resources"]

    success_refs = language_completions(sdl, cursor_path="/objectives/goal/success/conditions")
    assert success_refs["context"] == "reference:conditions"
    assert [item["label"] for item in success_refs["items"]] == ["alive"]

    any_refs = language_completions(sdl, cursor_path="/relationships/app-to-web/source")
    assert any(item["detail"] == "nodes.web" for item in any_refs["items"])
    assert any(item["detail"] == "conditions.alive" for item in any_refs["items"])

    workflow_refs = language_completions(sdl, cursor_path="/workflows/flow/start")
    assert workflow_refs["context"] == "reference:workflow_steps"
    assert workflow_refs["items"][0]["detail"] == "workflows.flow.steps.start-here"


def test_targetable_completions_exclude_non_targetable_sections() -> None:
    sdl = """\
name: targetable-completions
nodes:
  web: {type: compute, os: linux, resources: {ram: 1 GiB, cpu: 1}}
variables:
  count: {type: integer, default: 1}
evidence_requirements:
  capture: {source_refs: [web], source_class: node}
objectives:
  inspect: {targets: [web], success: {conditions: []}}
workflows:
  flow: {start: done, steps: {done: {type: end}}}
"""

    result = language_completions(sdl, cursor_path="/objectives/inspect/targets")

    assert result["context"] == "reference:eligible:objective_subject"
    details = {item["detail"] for item in result["items"]}
    assert "nodes.web" in details
    assert not details & {
        "variables.count",
        "evidence_requirements.capture",
        "objectives.inspect",
        "workflows.flow",
    }


def test_valid_document_completions_use_typed_nested_declarations() -> None:
    sdl = """\
name: nested-completions
nodes:
  web:
    type: compute
    resources: {ram: 1 GiB, cpu: 1}
    services: [{name: http, port: 80}]
  api:
    type: compute
    resources: {ram: 1 GiB, cpu: 1}
    services: [{name: http, port: 8080}]
content:
  fixtures:
    type: dataset
    target: web
    items: [{name: seed-file, display_name: seed.json}]
relationships:
  serves: {type: connects_to, source: web, target: api}
"""

    result = language_completions(sdl, cursor_path="/relationships/serves/target")
    by_detail = {item["detail"]: item for item in result["items"]}

    assert result["context"] == "reference:eligible:relationship_endpoint"
    assert by_detail["content.fixtures.items.seed-file"]["label"] == "seed-file"
    assert by_detail["nodes.web.services.http"]["label"] == "nodes.web.services.http"
    assert by_detail["nodes.api.services.http"]["label"] == "nodes.api.services.http"


def test_qualified_targetable_reference_reports_occurrence() -> None:
    sdl = """\
name: targetable-reference
nodes:
  web: {type: compute, os: linux, resources: {ram: 1 GiB, cpu: 1}}
behavior_specifications:
  baseline:
    semantic_version: 1.0.0
    lifecycle_state: active
    participant_refs: []
    authority_scope_refs: [nodes.web]
    behavior_mode: baseline
"""

    result = language_references(sdl, "nodes.web")

    assert any(
        item["path"] == "/behavior_specifications/baseline/authority_scope_refs/0" for item in result["occurrences"]
    )


def test_qualified_targetable_reference_excludes_non_targetable_occurrence() -> None:
    sdl = """\
name: targetable-reference
nodes:
  web: {type: compute, os: linux, resources: {ram: 1 GiB, cpu: 1}}
objectives:
  inspect: {targets: [objectives.inspect], success: {conditions: []}}
"""

    result = language_references(sdl, "objectives.inspect")

    assert result["definitions"][0]["qualified_name"] == "objectives.inspect"
    assert not any(item["path"] == "/objectives/inspect/targets/0" for item in result["occurrences"])


def test_language_completions_report_parse_and_size_errors() -> None:
    parse_error = language_completions("name: [\n", cursor_path="/")
    assert parse_error["status"] == "invalid"
    assert parse_error["diagnostics"][0]["code"] == "sdl.parse"

    size_error = language_completions("x" * (64 * 1024 + 1), cursor_path="/")
    assert size_error["status"] == "invalid"
    assert size_error["diagnostics"][0]["code"] == "sdl.input_too_large"


def test_language_references_report_definitions_and_occurrences() -> None:
    payload = language_references(SAMPLE_SDL, "app")

    assert payload["status"] == "ok"
    assert any(item["qualified_name"] == "features.app" for item in payload["definitions"])
    assert any(item["path"] == "/nodes/web/features/app" for item in payload["occurrences"])


def test_qualified_language_references_do_not_match_other_sections() -> None:
    sdl = """\
name: qualified-reference-test
nodes:
  web: {type: compute, os: linux, resources: {ram: 2 GiB, cpu: 1}, features: {app: admin}, roles: {admin: www}}
features:
  app: {type: Service, source: webapp}
conditions:
  app: {command: "true", interval: 10}
"""

    payload = language_references(sdl, "features.app")

    assert [item["qualified_name"] for item in payload["definitions"]] == ["features.app"]
    assert any(item["path"] == "/nodes/web/features/app" for item in payload["occurrences"])
    assert not any(item["path"] == "/conditions/app" for item in payload["occurrences"])


def test_language_references_cover_empty_invalid_sequence_and_nested_entities() -> None:
    empty = language_references("", "web")
    assert empty["definitions"] == []
    assert empty["occurrences"] == []

    invalid = language_references("name: [\n", "web")
    assert invalid["status"] == "invalid"
    assert invalid["diagnostics"][0]["code"] == "sdl.parse"
    assert invalid["diagnostics"][0]["range"]["start"]["line"] == 2

    sequence = language_references("- web\n", "web")
    assert sequence["definitions"] == []
    assert sequence["occurrences"][0]["path"] == "/0"

    nested = language_references(
        """\
name: nested-entity-test
entities:
  team:
    name: Team
    entities:
      alice: {name: Alice}
""",
        "entities.team.alice",
    )
    assert [item["qualified_name"] for item in nested["definitions"]] == ["entities.team.alice"]


def test_language_format_normalizes_field_keys() -> None:
    payload = language_format(
        """\
Name: formatting-test
Nodes:
  sw:
    Type: Switch
"""
    )

    assert payload["status"] == "formatted_with_diagnostics"
    assert payload["content"].startswith("name: formatting-test\nnodes:\n")
    assert "type: switch" in payload["content"]
    assert [item["code"] for item in payload["diagnostics"]] == [
        "sdl.noncanonical_field",
        "sdl.noncanonical_field",
        "sdl.noncanonical_field",
    ]


def test_language_format_reports_parse_error() -> None:
    payload = language_format("name: [\n")

    assert payload["status"] == "invalid"
    assert payload["diagnostics"][0]["code"] == "sdl.parse"


def test_language_diagnostics_are_structured() -> None:
    payload = language_diagnostics(INVALID_REFERENCE_SDL)

    assert payload["status"] == "invalid"
    assert payload["diagnostics"][0]["stage"] == "semantic_validation"
    assert payload["diagnostics"][0]["code"] == "sdl.semantic"
    assert "ghost-feature" in payload["diagnostics"][0]["message"]


def test_language_diagnostics_support_parse_only_mode_and_parse_errors() -> None:
    parse_only = language_diagnostics(INVALID_REFERENCE_SDL, semantic_validation=False)
    assert parse_only == {"status": "valid", "stage": "parse", "diagnostics": []}

    parse_error = language_diagnostics("name: [\n")
    assert parse_error["status"] == "invalid"
    assert parse_error["diagnostics"][0]["code"] == "sdl.parse"


def test_structured_edit_updates_yaml_and_revalidates() -> None:
    payload = apply_structured_edit(
        SAMPLE_SDL,
        operation="set",
        pointer="/description",
        value="Edited through the language service",
    )

    assert payload["status"] == "edited"
    assert "description: Edited through the language service" in payload["content"]
    assert payload["diagnostics"] == []


def test_structured_edit_deletes_value_and_revalidates() -> None:
    payload = apply_structured_edit(
        SAMPLE_SDL,
        operation="delete",
        pointer="/nodes/web/features/app",
    )

    assert payload["status"] == "edited"
    assert "app: admin" not in payload["content"]
    assert payload["diagnostics"] == []


def test_structured_edit_appends_value_and_revalidates() -> None:
    payload = apply_structured_edit(
        SAMPLE_SDL,
        operation="append",
        pointer="/infrastructure/web/links",
        value="net2",
    )

    assert payload["status"] == "edited"
    assert "- net2" in payload["content"]
    assert payload["diagnostics"] == []


def test_structured_edit_handles_root_and_list_mutations() -> None:
    root = apply_structured_edit(SAMPLE_SDL, operation="set", pointer="", value={"name": "replacement"})
    assert root["status"] == "edited"
    assert root["content"] == "name: replacement\n"

    list_set = apply_structured_edit(SAMPLE_SDL, operation="set", pointer="/infrastructure/web/links/0", value="net2")
    assert list_set["status"] == "edited"
    assert "- net2" in list_set["content"]

    list_delete = apply_structured_edit(SAMPLE_SDL, operation="delete", pointer="/infrastructure/web/links/0")
    assert list_delete["status"] == "edited"
    assert "links: []" in list_delete["content"]

    created = apply_structured_edit(SAMPLE_SDL, operation="set", pointer="/nodes/web/custom/value", value=True)
    assert created["status"] == "edited_with_diagnostics"
    assert "custom:" in created["content"]


@pytest.mark.parametrize(
    ("operation", "pointer", "value", "expected"),
    [
        pytest.param("delete", "", None, "root pointer supports only the set operation", id="root-delete-unsupported"),
        pytest.param("replace", "/description", "x", "operation must be one of", id="unknown-operation"),
        pytest.param(
            "set", "description", "x", "pointer must be empty or start with '/'", id="pointer-missing-leading-slash"
        ),
        pytest.param("append", "/name", "x", "is not a list", id="append-non-list"),
        pytest.param("delete", "/missing", None, "missing path segment", id="delete-missing-segment"),
        pytest.param("delete", "/infrastructure/web/links/nope", None, "is not an integer", id="index-not-integer"),
        pytest.param("delete", "/infrastructure/web/links/10", None, "out of range", id="index-out-of-range"),
        pytest.param(
            "set",
            "/infrastructure/web/links/0/name",
            "x",
            "does not address a mapping or list",
            id="non-container-parent",
        ),
    ],
)
def test_structured_edit_reports_invalid_edit_requests(operation, pointer, value, expected) -> None:
    payload = apply_structured_edit(SAMPLE_SDL, operation=operation, pointer=pointer, value=value)
    assert payload["status"] == "invalid"
    assert expected in payload["diagnostics"][0]["message"]
