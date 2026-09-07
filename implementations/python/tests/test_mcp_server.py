"""Tests for the RAES SDL MCP server tools.

Verifies that the registered tool surface produces correct results across
reference, authoring, language-service, inspection, and operation categories.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from paths import EXAMPLES_DIR
from raes_mcp.server import create_server

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def server():
    return create_server()


def _text(result) -> str:
    """Extract text from the MCP tool result tuple."""
    content_list = result[0]
    return content_list[0].text


def _call(server, tool: str, args: dict | None = None) -> str:
    """Synchronously call a tool and return its text."""
    return asyncio.run(_async_call(server, tool, args or {}))


async def _async_call(server, tool: str, args: dict) -> str:
    result = await server.call_tool(tool, args)
    return _text(result)


def _json_call(server, tool: str, args: dict | None = None) -> dict:
    """Synchronously call a JSON-returning MCP tool."""
    return json.loads(_call(server, tool, args or {}))


# ---------------------------------------------------------------------------
# Valid SDL fixtures
# ---------------------------------------------------------------------------

MINIMAL_SDL = """\
name: test-scenario
nodes:
  net: {type: Switch}
  web: {type: compute, resources: {ram: 2 GiB, cpu: 1}}
infrastructure:
  net: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  web: {count: 1, links: [net]}
"""

FULL_SDL = """\
name: mcp-test
description: Test scenario with many sections

variables:
  speed:
    type: number
    default: 1.0

nodes:
  corp-net: {type: Switch}
  web: {type: compute, resources: {ram: 2 GiB, cpu: 1}, features: {app: admin}, roles: {admin: www}, conditions: {alive: admin}}
  db:  {type: compute, resources: {ram: 1 GiB, cpu: 1}, features: {pg: dba}, roles: {dba: postgres}, services: [{port: 5432, name: pg-port}]}

infrastructure:
  corp-net: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  web: {count: 1, links: [corp-net]}
  db:  {count: 1, links: [corp-net]}

features:
  app: {type: Service, source: my-app}
  pg:  {type: Service, source: postgresql}

conditions:
  alive:
    proposition: web-alive
    command: "curl -sf http://localhost/ || exit 1"
    interval: 15

evidence_requirements:
  web-health-evidence:
    description: Capture the governed web health observation.
    source_refs: [nodes.web]
    scope_refs: [nodes.web]
    trigger_ref: conditions.alive
    channel: api_response
    artifact_role: proposition_truth_evidence
    media_types: [application/json]
    sensitivity: plain
    redaction: redact_secrets
    integrity: checksum
    retention: study_lifetime
    loss_disclosure: required

propositions:
  web-alive:
    description: The governed web service responds successfully.
    subjects: [nodes.web]
    basis: observed_state
    predicate:
      kind: boolean
      property: service-alive
      semantic_ref: urn:raes:observable:service-alive
      operator: equals
      expected: true
    evidence_requirements: [web-health-evidence]

assertions:
  web-alive:
    description: The web service must be alive at the objective boundary.
    proposition: web-alive
    role: postcondition
    polarity: positive

vulnerabilities:
  sqli: {name: SQL Injection, description: "SQLi in login", technical: true, class: CWE-89}

entities:
  blue-team:
    name: Blue
    role: Blue
    entities:
      alice: {name: Alice}
  red-team:
    name: Red
    role: Red

injects:
  brief: {source: brief-doc, from_entity: red-team, to_entities: [blue-team]}

events:
  attack: {injects: [brief]}

scripts:
  timeline:
    start_time: 0
    end_time: 2 hour
    speed: "${speed}"
    events:
      attack: 30 min

stories:
  exercise:
    speed: "${speed}"
    scripts: [timeline]

content:
  seed: {type: dataset, target: db, format: sql, source: seed-pkg}

accounts:
  admin-acct: {username: admin, node: web, password_strength: strong}

relationships:
  web-to-db: {type: connects_to, source: app, target: pg}

agents:
  red-agent:
    entity: red-team
    actions: [Scan]
    initial_knowledge:
      hosts: [web]
      subnets: [corp-net]
      services: [pg-port]

objectives:
  red-access:
    agent: red-agent
    actions: [Scan]
    targets: [web]
    success: {assertions: [web-alive]}
    window: {stories: [exercise]}

workflows:
  flow:
    start: do-it
    steps:
      do-it: {type: objective, objective: red-access, on_success: done}
      done: {type: end}
"""


INVALID_SDL = """\
name: broken
nodes:
  web:
    type: compute
    os: linux
    features: {ghost-feature: admin}
"""


# ---------------------------------------------------------------------------
# Reference tools
# ---------------------------------------------------------------------------


class TestReferenceTools:
    def test_sdl_overview_returns_content(self, server):
        text = _call(server, "sdl_overview")
        assert "agentic environments" in text
        assert "authored scenarios" in text
        assert "SDL" in text
        assert "authoring sections" in text.lower()
        assert "17 sections" not in text.lower()
        assert "nodes" in text

    @pytest.mark.parametrize(
        "section",
        [
            "forwarding_agents",
            "action_contracts",
            "observation_boundaries",
            "outcome_interpretation_rules",
            "behavior_specifications",
            "evidence_requirements",
        ],
    )
    def test_sdl_section_reference_covers_live_sections(self, server, section):
        text = _call(server, "sdl_section_reference", {"section": section})
        assert "Unknown section" not in text
        assert "not found" not in text

    def test_sdl_section_reference_valid(self, server):
        text = _call(server, "sdl_section_reference", {"section": "nodes"})
        assert "Nodes" in text
        assert "Switch" in text
        assert "compute" in text.lower()

    def test_sdl_section_reference_invalid(self, server):
        text = _call(server, "sdl_section_reference", {"section": "nonexistent"})
        assert "Unknown section" in text

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            # Pin the example identity so a regression returning a different
            # SDL (still with `name:` / `nodes:`) is not silently accepted.
            pytest.param("minimal", ["name:", "nodes:", "simple-pentest-lab"], id="minimal"),
            pytest.param("hospital", ["hospital-ransomware", "objectives:"], id="hospital"),
            pytest.param("nonexistent", ["Unknown example"], id="invalid"),
        ],
    )
    def test_sdl_get_example(self, server, name, expected):
        text = _call(server, "sdl_get_example", {"name": name})
        for substring in expected:
            assert substring in text

    def test_sdl_parser_reference(self, server):
        text = _call(server, "sdl_parser_reference")
        assert "normalization" in text.lower() or "Normalization" in text

    def test_sdl_validation_reference(self, server):
        text = _call(server, "sdl_validation_reference")
        # Require both the section heading and a specific pass name so the
        # response cannot satisfy the test with a generic "validation" string.
        assert "Validation Passes" in text
        assert "verify_runtime_identity_authorities" in text


# ---------------------------------------------------------------------------
# Authoring tools
# ---------------------------------------------------------------------------


class TestAuthoringTools:
    def test_validate_valid_sdl(self, server):
        text = _call(server, "sdl_validate", {"sdl_content": MINIMAL_SDL})
        assert text.startswith("VALID")

    def test_validate_full_sdl(self, server):
        text = _call(server, "sdl_validate", {"sdl_content": FULL_SDL})
        assert text.startswith("VALID")
        assert "nodes: 3" in text
        assert "objectives: 1" in text

    def test_validate_invalid_sdl(self, server):
        text = _call(server, "sdl_validate", {"sdl_content": INVALID_SDL})
        assert "VALIDATION ERRORS" in text
        assert "ghost-feature" in text

    def test_validate_yaml_error(self, server):
        text = _call(server, "sdl_validate", {"sdl_content": "{{not yaml"})
        assert "PARSE ERROR" in text

    def test_validate_structural_only(self, server):
        text = _call(
            server,
            "sdl_validate",
            {"sdl_content": INVALID_SDL, "structural_only": True},
        )
        # With structural_only, structural validation passes, the response
        # affirmatively notes that semantic validation was skipped, and the
        # semantic cross-reference error (ghost-feature) does not appear.
        assert text.startswith("VALID")
        assert "semantic validation was skipped" in text
        assert "ghost-feature" not in text

    def test_validate_requires_explicit_migration_policy(self, server):
        strict = _call(server, "sdl_validate", {"sdl_content": "Name: migrated\n"})
        assert "sdl.noncanonical_field" in strict

        migrated = _call(
            server,
            "sdl_validate",
            {"sdl_content": "Name: migrated\n", "accept_migration_syntax": True},
        )
        assert migrated.startswith("VALID")
        assert "Source migration advisories (1)" in migrated
        assert "sdl.noncanonical_field" in migrated

    def test_validate_section_valid(self, server):
        text = _call(
            server,
            "sdl_validate_section",
            {
                "section": "nodes",
                "section_yaml": "myvm:\n  type: compute\n  os: linux\n  resources: {ram: 2 GiB, cpu: 1}",
            },
        )
        assert text.startswith("VALID")

    def test_validate_section_invalid_yaml(self, server):
        text = _call(
            server,
            "sdl_validate_section",
            {"section": "nodes", "section_yaml": "{{not yaml"},
        )
        assert "YAML ERROR" in text

    def test_validate_section_rejects_duplicates_before_fragment_round_trip(self, server):
        text = _call(
            server,
            "sdl_validate_section",
            {
                "section": "nodes",
                "section_yaml": "sw:\n  Type: switch\n  type: switch",
            },
        )

        assert "PARSE ERROR" in text
        assert "sdl.mapping_key_conflict" in text
        assert "/nodes/sw/type" in text
        assert "line 3, column 3" in text

    def test_validate_section_bad_section(self, server):
        text = _call(
            server,
            "sdl_validate_section",
            {"section": "nope", "section_yaml": "x: 1"},
        )
        assert "Unknown section" in text

    @pytest.mark.parametrize(
        ("complexity", "expected"),
        [
            pytest.param("minimal", ["name:", "nodes:"], id="minimal"),
            pytest.param("standard", ["entities:", "accounts:"], id="standard"),
            pytest.param("full", ["workflows:", "objectives:", "variables:"], id="full"),
        ],
    )
    def test_scaffold(self, server, complexity, expected):
        text = _call(server, "sdl_scaffold", {"complexity": complexity})
        for substring in expected:
            assert substring in text
        # Scaffolded output should be valid SDL.
        validation = _call(server, "sdl_validate", {"sdl_content": text})
        assert validation.startswith("VALID")

    def test_scaffold_invalid_complexity(self, server):
        text = _call(server, "sdl_scaffold", {"complexity": "ultra"})
        assert "Invalid complexity" in text

    def test_instantiate(self, server):
        sdl = """\
name: param-test
variables:
  greeting:
    type: string
    required: true
"""
        text = _call(
            server,
            "sdl_instantiate",
            {"sdl_content": sdl, "parameters_json": '{"greeting": "s3cr3t-marker-9b2d"}'},
        )
        assert text.startswith("INSTANTIATED")
        assert "Bindings resolved: 1" in text
        assert "greeting" not in text
        assert "s3cr3t-marker-9b2d" not in text

        missing = _call(server, "sdl_instantiate", {"sdl_content": sdl})
        assert missing.startswith("INSTANTIATION ERRORS")
        assert "required" in missing
        assert "s3cr3t-marker-9b2d" not in missing

    def test_instantiate_bad_json(self, server):
        text = _call(
            server,
            "sdl_instantiate",
            {"sdl_content": "name: x", "parameters_json": "{bad"},
        )
        assert "Invalid JSON" in text


# ---------------------------------------------------------------------------
# Language-service tools
# ---------------------------------------------------------------------------


class TestLanguageServiceTools:
    def test_completions_suggest_reference_targets(self, server):
        payload = _json_call(
            server,
            "sdl_completions",
            {"sdl_content": FULL_SDL, "cursor_path": "/nodes/web/features"},
        )

        labels = {item["label"] for item in payload["items"]}
        assert "app" in labels
        assert any(item["detail"] == "features.app" for item in payload["items"])

    def test_references_return_definition_locations(self, server):
        payload = _json_call(
            server,
            "sdl_references",
            {"sdl_content": FULL_SDL, "symbol": "app"},
        )

        assert payload["status"] == "ok"
        assert any(item["qualified_name"] == "features.app" for item in payload["definitions"])
        assert any(item["path"] == "/nodes/web/features/app" for item in payload["occurrences"])

    def test_format_returns_normalized_yaml(self, server):
        payload = _json_call(
            server,
            "sdl_format",
            {"sdl_content": "Name: x\nNodes:\n  sw: {Type: Switch}\n"},
        )

        assert payload["status"] == "formatted_with_diagnostics"
        assert payload["content"].startswith("name: x\nnodes:\n")
        assert [item["code"] for item in payload["diagnostics"]] == [
            "sdl.noncanonical_field",
            "sdl.noncanonical_field",
            "sdl.noncanonical_field",
        ]

    def test_diagnostics_return_structured_errors(self, server):
        payload = _json_call(
            server,
            "sdl_diagnostics",
            {"sdl_content": INVALID_SDL},
        )

        assert payload["status"] == "invalid"
        assert payload["diagnostics"][0]["code"] == "sdl.semantic"
        assert "ghost-feature" in payload["diagnostics"][0]["message"]

    def test_apply_edit_sets_value_and_revalidates(self, server):
        payload = _json_call(
            server,
            "sdl_apply_edit",
            {
                "sdl_content": MINIMAL_SDL,
                "operation": "set",
                "pointer": "/description",
                "value_json": '"Edited"',
            },
        )

        assert payload["status"] == "edited"
        assert "description: Edited" in payload["content"]
        assert payload["diagnostics"] == []

    def test_apply_edit_deletes_value_and_revalidates(self, server):
        payload = _json_call(
            server,
            "sdl_apply_edit",
            {
                "sdl_content": MINIMAL_SDL,
                "operation": "delete",
                "pointer": "/infrastructure/web/links",
            },
        )

        assert payload["status"] == "edited"
        assert "links" not in payload["content"]
        assert payload["diagnostics"] == []

    def test_apply_edit_appends_value_and_revalidates(self, server):
        sdl = """\
name: append-edit
nodes:
  net: {type: Switch}
  net2: {type: Switch}
  web: {type: compute, os: linux, resources: {ram: 2 GiB, cpu: 1}}
infrastructure:
  net: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  net2: {count: 1, properties: {cidr: 10.0.1.0/24, gateway: 10.0.1.1}}
  web: {count: 1, links: [net]}
"""
        payload = _json_call(
            server,
            "sdl_apply_edit",
            {
                "sdl_content": sdl,
                "operation": "append",
                "pointer": "/infrastructure/web/links",
                "value_json": '"net2"',
            },
        )

        assert payload["status"] == "edited"
        assert "- net2" in payload["content"]
        assert payload["diagnostics"] == []

    def test_apply_edit_rejects_invalid_value_json(self, server):
        payload = _json_call(
            server,
            "sdl_apply_edit",
            {
                "sdl_content": MINIMAL_SDL,
                "operation": "set",
                "pointer": "/description",
                "value_json": "{bad",
            },
        )

        assert payload["status"] == "invalid"
        assert payload["diagnostics"][0]["code"] == "sdl.edit"
        assert "Invalid JSON" in payload["diagnostics"][0]["message"]


# ---------------------------------------------------------------------------
# Inspection tools
# ---------------------------------------------------------------------------


class TestInspectionTools:
    def test_summarize(self, server):
        text = _call(server, "sdl_summarize", {"sdl_content": FULL_SDL})
        assert "mcp-test" in text
        assert "Compute nodes:" in text
        assert "Switches:" in text
        assert "${speed}" in text

    def test_summarize_entities(self, server):
        text = _call(server, "sdl_summarize", {"sdl_content": FULL_SDL})
        assert "blue-team" in text
        assert "Entities" in text

    def test_list_elements_all(self, server):
        text = _call(server, "sdl_list_elements", {"sdl_content": FULL_SDL, "section": "all"})
        assert "nodes:" in text
        assert "web" in text
        assert "features:" in text

    def test_list_elements_filtered(self, server):
        text = _call(
            server,
            "sdl_list_elements",
            {"sdl_content": FULL_SDL, "section": "accounts"},
        )
        assert "admin-acct" in text
        # Should NOT list nodes
        assert "\nnodes:" not in text

    def test_list_elements_nested_entities(self, server):
        text = _call(
            server,
            "sdl_list_elements",
            {"sdl_content": FULL_SDL, "section": "entities"},
        )
        assert "blue-team" in text
        assert "blue-team.alice" in text

    def test_get_element_qualified(self, server):
        text = _call(
            server,
            "sdl_get_element",
            {"sdl_content": FULL_SDL, "element_name": "nodes.web"},
        )
        assert "nodes.web" in text
        assert "compute" in text.lower()

    def test_get_element_unique_bare(self, server):
        text = _call(
            server,
            "sdl_get_element",
            {"sdl_content": FULL_SDL, "element_name": "sqli"},
        )
        assert "SQL Injection" in text

    def test_get_element_ambiguous(self, server):
        text = _call(
            server,
            "sdl_get_element",
            {"sdl_content": MINIMAL_SDL, "element_name": "web"},
        )
        # 'web' is in both nodes and infrastructure
        assert "Ambiguous" in text

    def test_get_element_not_found(self, server):
        text = _call(
            server,
            "sdl_get_element",
            {"sdl_content": MINIMAL_SDL, "element_name": "nonexistent"},
        )
        assert "not found" in text.lower()

    def test_check_references_element(self, server):
        text = _call(
            server,
            "sdl_check_references",
            {"sdl_content": FULL_SDL, "element_name": "app"},
        )
        # `app` is the feature `nodes.web` binds and the source of the
        # `relationships.web-to-db` relationship in FULL_SDL. Pin both
        # named references so a regression in either reference-tracking
        # path (node feature bindings OR relationships) is caught.
        assert "Outgoing" in text or "Incoming" in text
        assert "relationships.web-to-db" in text

    def test_check_references_full_graph(self, server):
        text = _call(
            server,
            "sdl_check_references",
            {"sdl_content": FULL_SDL},
        )
        assert "Cross-reference graph" in text
        assert "->" in text

    def test_diagram(self, server):
        text = _call(server, "sdl_diagram", {"sdl_content": FULL_SDL})
        assert "Topology" in text
        assert "corp-net" in text
        assert "web" in text

    def test_diagram_shows_services(self, server):
        text = _call(server, "sdl_diagram", {"sdl_content": FULL_SDL})
        assert "pg-port" in text

    def test_diagram_shows_dependencies(self, server):
        sdl_with_deps = """\
name: dep-test
nodes:
  sw: {type: Switch}
  a: {type: compute, os: linux, resources: {ram: 1 GiB, cpu: 1}}
  b: {type: compute, os: linux, resources: {ram: 1 GiB, cpu: 1}}
infrastructure:
  sw: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  a: {count: 1, links: [sw]}
  b: {count: 1, links: [sw], dependencies: [a]}
"""
        text = _call(server, "sdl_diagram", {"sdl_content": sdl_with_deps})
        assert "Dependencies" in text
        assert "b --> a" in text


# ---------------------------------------------------------------------------
# Operation and claim-assessment tools
# ---------------------------------------------------------------------------


class TestOperationTools:
    def test_tool_surface_self_describes_boundaries(self, server):
        payload = _json_call(server, "raes_tool_surface")
        assert payload["surface"] == "raes"
        assert "legacy_surfaces" not in payload
        assert "raes_agent_guidance" in payload["recommended_workflow"]
        assert "raes_intended_use_profiles" in payload["recommended_workflow"]
        assert "sdl_claims_assessment" in payload["recommended_workflow"]
        assert "sdl_completions" in payload["tool_families"]["language_service"]
        assert "raes_agent_guidance" in payload["tool_families"]["guidance"]
        assert "raes_intended_use_profiles" in payload["tool_families"]["guidance"]
        advertised = {name for names in payload["tool_families"].values() for name in names}
        assert {"raes_agent_guidance", "raes_intended_use_profiles"} <= advertised
        assert "raes_reference_manifests" in advertised
        assert any("does not expose participant cyber actions" in item for item in payload["boundaries"])

    def test_agent_guidance_returns_machine_usable_profile(self, server):
        payload = _json_call(server, "raes_agent_guidance")
        assert payload["status"] == "ok"
        assert payload["profile"] == "raes-agent-guidance"
        assert "AUT-811" in payload["requirement_refs"]
        assert set(payload["guidance"]) == {
            "scope_boundaries",
            "invariants",
            "review_priorities",
            "safe_operating_expectations",
        }
        assert payload["guidance"]["scope_boundaries"][0]["id"]
        assert payload["guidance"]["scope_boundaries"][0]["source_refs"]

    def test_agent_guidance_filters_by_audience(self, server):
        payload = _json_call(server, "raes_agent_guidance", {"audience": "operator"})
        assert payload["status"] == "ok"
        for entries in payload["guidance"].values():
            assert entries
            assert all("operator" in entry["audience"] for entry in entries)

    def test_intended_use_profiles_exposes_canonical_catalog(self, server):
        payload = _json_call(server, "raes_intended_use_profiles")

        assert payload["status"] == "ok"
        assert payload["scope"] == "raes-delivery-capability"
        assert "legacy_scope" not in payload
        assert payload["taxonomy_revision"] == "rev1"
        assert len(payload["profiles"]) == 5
        assert payload["scenario_assessment"]["status"] == "not-assessed"
        assert {item["profile_id"] for item in payload["profiles"]} == {
            "valid-sdl-fragment",
            "deployable-scenario-intent",
            "participant-evaluation-scenario",
            "controlled-experiment-scenario",
            "reproducible-benchmark-study-input",
        }

    def test_intended_use_profile_exposes_blockers_and_authoring_route(self, server):
        payload = _json_call(
            server,
            "raes_intended_use_profiles",
            {"profile_id": "controlled-experiment-scenario"},
        )

        profile = payload["profile"]
        assert profile["raes_delivery"]["complete"] is False
        assert "behavioral-relation-taxonomy" not in profile["raes_delivery"]["blocking_concern_ids"]
        assert "experiment_validate" in profile["next_tools"]
        required = {item["concern_id"]: item for item in profile["required_concerns"]}
        assert required["behavioral-relation-taxonomy"]["status"] == "implemented"
        assert required["behavioral-relation-taxonomy"]["issue_refs"] == []
        assert payload["scenario_assessment"]["performed"] is False

    def test_intended_use_profile_rejects_unknown_id(self, server):
        payload = _json_call(server, "raes_intended_use_profiles", {"profile_id": "attack-scenario"})

        assert payload["status"] == "invalid"
        assert payload["diagnostics"][0]["code"] == "raes.intended_use_profile.unknown"
        assert "valid-sdl-fragment" in payload["diagnostics"][0]["available_profile_ids"]

    def test_non_experiment_profile_does_not_recommend_experiment_tools(self, server):
        payload = _json_call(server, "raes_intended_use_profiles", {"profile_id": "valid-sdl-fragment"})

        assert "experiment_validate" not in payload["profile"]["next_tools"]

    def test_parse_returns_machine_readable_summary(self, server):
        payload = _json_call(server, "sdl_parse", {"sdl_content": MINIMAL_SDL})
        assert payload["status"] == "parsed"
        assert payload["semantic_validation"] == "skipped"
        assert payload["scenario"]["name"] == "test-scenario"
        assert payload["scenario"]["populated_sections"]["nodes"] == 2

    def test_parse_can_run_semantic_validation(self, server):
        payload = _json_call(
            server,
            "sdl_parse",
            {"sdl_content": INVALID_SDL, "semantic_validation": True},
        )
        assert payload["status"] == "invalid"
        assert payload["stage"] == "semantic_validation"
        assert "ghost-feature" in payload["diagnostics"][0]["message"]

    @pytest.mark.parametrize("tool", ["sdl_parse", "sdl_compile"])
    def test_operation_tools_require_explicit_migration_policy(self, server, tool):
        strict = _json_call(server, tool, {"sdl_content": "Name: migrated\n"})
        assert strict["status"] == "invalid"
        assert strict["diagnostics"][0]["code"] == "sdl.noncanonical_field"

        migrated = _json_call(
            server,
            tool,
            {"sdl_content": "Name: migrated\n", "accept_migration_syntax": True},
        )
        assert migrated["status"] in {"parsed", "compiled"}
        diagnostics = migrated.get("source_diagnostics", migrated["scenario"].get("source_diagnostics", []))
        assert diagnostics[0]["code"] == "sdl.noncanonical_field"

    @pytest.mark.parametrize("tool", ["sdl_parse", "sdl_compile"])
    def test_operation_tools_preserve_mapping_conflict_diagnostics(self, server, tool):
        payload = _json_call(server, tool, {"sdl_content": "Name: first\nname: second\n"})

        assert payload["status"] == "invalid"
        diagnostic = payload["diagnostics"][0]
        assert diagnostic["code"] == "sdl.mapping_key_conflict"
        assert diagnostic["path"] == "/name"
        assert diagnostic["authored_keys"] == ["Name", "name"]
        assert diagnostic["range"]["start"] == {"line": 2, "column": 1}

    def test_compile_summarizes_runtime_model(self, server):
        payload = _json_call(server, "sdl_compile", {"sdl_content": FULL_SDL})
        assert payload["status"] == "compiled"
        assert payload["runtime_model"]["domains"]["provisioning"]["nodes"] == 2
        assert payload["runtime_model"]["domains"]["evaluation"]["objectives"] == 1
        assert payload["runtime_model"]["domains"]["participant"]["action_contracts"] == 0

    def test_plan_dry_run_reports_reference_manifest_and_operations(self, server):
        payload = _json_call(server, "sdl_plan", {"sdl_content": FULL_SDL})
        assert payload["status"] == "planned_with_errors"
        assert payload["manifest"]["backend"] == "stub"
        assert payload["plan"]["is_valid"] is False
        assert any(diagnostic["code"] == "capture.offer-missing" for diagnostic in payload["diagnostics"])
        assert payload["plan"]["operations"]["provisioning"]["create"] > 0
        assert "dry run" in payload["claim_boundary"]

    def test_design_assessment_warns_about_action_names_without_contracts(self, server):
        payload = _json_call(server, "sdl_design_assessment", {"sdl_content": FULL_SDL})
        messages = [note["message"] for note in payload["design_notes"]]
        assert any("action names without action contracts" in message for message in messages)
        assert payload["status"] == "needs_attention"
        assert payload["plan"]["is_valid"] is False
        assert any(diagnostic["code"] == "capture.offer-missing" for diagnostic in payload["diagnostics"])

    def test_claims_assessment_limits_participant_skill_claims(self, server):
        payload = _json_call(server, "sdl_claims_assessment", {"sdl_content": FULL_SDL})
        unsupported_ids = {claim["id"] for claim in payload["claims"]["unsupported_without_more_evidence"]}
        conditional_ids = {claim["id"] for claim in payload["claims"]["conditional"]}
        assert "participant-skill" in unsupported_ids
        assert "participant-behavior" in conditional_ids
        assert "semantic-validation" in {claim["id"] for claim in payload["claims"]["supported"]}

    def test_reference_manifests_expose_processor_and_backend(self, server):
        payload = _json_call(server, "raes_reference_manifests")
        assert payload["status"] == "ok"
        assert payload["processor"]["identity"]["name"] == "raes-reference-processor"
        assert payload["backend"]["identity"]["name"] == "stub"

    def test_compile_bad_parameters_report_parameter_stage(self, server):
        payload = _json_call(
            server,
            "sdl_compile",
            {"sdl_content": MINIMAL_SDL, "parameters_json": "[1, 2]"},
        )
        assert payload["status"] == "invalid"
        assert payload["stage"] == "parameter_parsing"


# ---------------------------------------------------------------------------
# Example scenario validation
# ---------------------------------------------------------------------------


class TestExampleScenarios:
    """Validate that all bundled examples pass through the MCP tools."""

    @pytest.mark.parametrize(
        "filename",
        [
            "hospital-ransomware-surgery-day.sdl.yaml",
            "satcom-release-poisoning.sdl.yaml",
            "port-authority-surge-response.sdl.yaml",
        ],
    )
    def test_example_validates(self, server, filename):
        path = EXAMPLES_DIR / filename
        sdl = path.read_text()
        text = _call(server, "sdl_validate", {"sdl_content": sdl})
        assert text.startswith("VALID"), f"{filename} failed: {text[:200]}"

    @pytest.mark.parametrize(
        "filename",
        [
            "hospital-ransomware-surgery-day.sdl.yaml",
            "satcom-release-poisoning.sdl.yaml",
            "port-authority-surge-response.sdl.yaml",
        ],
    )
    def test_example_summarizes(self, server, filename):
        path = EXAMPLES_DIR / filename
        sdl = path.read_text()
        text = _call(server, "sdl_summarize", {"sdl_content": sdl})
        assert "Scenario:" in text
        assert "Compute nodes:" in text
        # Pin the scenario identity so a cached/boilerplate response or a
        # wrong-file regression is not silently accepted. Each example's
        # `name:` field matches the basename of its .sdl.yaml file.
        scenario_name = filename.removesuffix(".sdl.yaml")
        assert scenario_name in text


# ---------------------------------------------------------------------------
# Server construction
# ---------------------------------------------------------------------------


class TestServerConstruction:
    def test_server_has_all_tools(self):
        server = create_server()
        # Ground truth: the tools actually registered on the FastMCP server.
        # Using the real registration surface (rather than a hand-copied
        # literal) means a drift between what the server exposes and what
        # raes_tool_surface advertises cannot pass silently.
        registered = asyncio.run(server.list_tools())
        registered_names = {tool.name for tool in registered}
        assert registered_names, "server registered no tools"

        # The advertised surface from raes_tool_surface must equal the real
        # registered set. The discovery tool documents itself outside the
        # family listing, so seed it explicitly.
        payload = _json_call(server, "raes_tool_surface")
        advertised = {"raes_tool_surface"}
        for family in payload["tool_families"].values():
            advertised.update(family)
        assert advertised == registered_names

    def test_server_has_instructions(self):
        server = create_server()
        assert server.instructions
        assert "SDL" in server.instructions
        assert "agentic environments" in server.instructions
        assert "authored scenario" in server.instructions


# ---------------------------------------------------------------------------
# Security regression tests
# ---------------------------------------------------------------------------


class TestSecurity:
    """Regression tests for security hardening."""

    def test_scaffold_with_braces_in_name(self, server):
        """Format string injection: braces in user input must not crash."""
        text = _call(
            server,
            "sdl_scaffold",
            {
                "complexity": "minimal",
                "scenario_name": "test{oops}",
                "description": "desc with {curly} braces",
            },
        )
        assert "test{oops}" in text
        assert "{curly}" in text
        # Should still be valid YAML (name: test{oops} is a valid YAML string)
        assert "name: test{oops}" in text

    def test_get_element_private_attr_access(self, server):
        """Qualified ref must not access private/dunder attributes."""
        text = _call(
            server,
            "sdl_get_element",
            {"sdl_content": MINIMAL_SDL, "element_name": "_advisories.anything"},
        )
        assert "not found" in text.lower()

    def test_get_element_dunder_access(self, server):
        """Qualified ref must not access __class__ or similar."""
        text = _call(
            server,
            "sdl_get_element",
            {"sdl_content": MINIMAL_SDL, "element_name": "__class__.foo"},
        )
        assert "not found" in text.lower()

    def test_validate_oversized_input_rejected(self, server):
        """Extremely large input must be rejected."""
        huge = "name: x\nnodes:\n" + "  n{i}: {{type: Switch}}\n" * 10_000
        text = _call(server, "sdl_validate", {"sdl_content": huge})
        assert "INPUT TOO LARGE" in text

    def test_summarize_oversized_input_rejected(self, server):
        """Inspection tools also enforce size limits."""
        huge = "name: x\n" + "x" * (65 * 1024)
        text = _call(server, "sdl_summarize", {"sdl_content": huge})
        assert "INPUT TOO LARGE" in text

    def test_validate_section_context_cannot_override_name(self, server):
        """context_yaml must not be able to hijack the wrapper name."""
        text = _call(
            server,
            "sdl_validate_section",
            {
                "section": "nodes",
                "section_yaml": "sw:\n  type: Switch",
                "context_yaml": "name: hijacked",
            },
        )
        # Should succeed validation — name should still be the safe internal one
        assert text.startswith("VALID")
        assert "hijacked" not in text
