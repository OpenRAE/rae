"""#1678: semantic validation errors carry their owner and pointer as data (ADR-116 rule E7).

The consumers read ``SDLValidationError.findings``. They do not parse message text.
The old text parsing below is an oracle only: for a message with a label that the
old parsing knew, each finding carries the owner and the pointer that the old
parsing found. The messages that the old parsing did not anchor have their own
anchoring tests.
"""

from __future__ import annotations

import copy
import re
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest
import raes._language_relationship_candidates as relationship_candidates
import yaml
from _act_614_temporal_fixtures import _bound_deadline_payload
from mixed_control_rev1_scenarios import rev1_policy_of, rev1_scenario
from paths import REPO_ROOT
from raes import SDLParseError, SDLValidationError, SDLValidationFinding, parse_sdl, parse_sdl_file
from raes._declaration_sources import semantic_source_diagnostics
from raes._declarations import build_declaration_index
from raes.language_service import language_completions
from raes.mixed_control_migration import _error_pointers, migrate_mixed_control_to_finite_script
from raes.semantics.objective_semantics import ObjectiveIssue
from raes.semantics.participant_behavior import ParticipantBehaviorIssue, analyze_participant_affiliations
from raes.semantics.participant_outcome import ParticipantOutcomeIssue
from raes.validator import SemanticValidator
from raes.validator._content_objectives import _PARTICIPANT_BEHAVIOR_ISSUE_RENDERERS
from raes.validator._issue_owners import (
    objective_issue_owner,
    participant_behavior_issue_owner,
    participant_outcome_issue_owner,
)
from raes.validator._objective_issue_renderers import OBJECTIVE_ISSUE_RENDERERS
from raes.validator._participant_outcome_renderers import PARTICIPANT_OUTCOME_ISSUE_RENDERERS
from test_enterprise_deployment_tenancy import _valid_payload
from test_issue_1339_relationship_candidate_parity import _controlled_relationship
from test_issue_1339_relationship_endpoints import _ENDPOINT_RELATIONSHIPS, matrix_payload
from test_issue_1363_mixed_control_migration import HANDOFF_CHAIN, POINTER, _legacy, _link_case, _source, _state

# The label table and the transition pattern that the consumers parsed before #1678.
_OLD_OWNER_LABELS = {
    "Node": "nodes",
    "Infrastructure": "infrastructure",
    "Relationship": "relationships",
    "Behavior specification": "behavior_specifications",
    "Action contract": "action_contracts",
    "Agent": "agents",
    "Participant": "agents",
    "Objective": "objectives",
    "Proposition": "propositions",
    "Assertion": "assertions",
    "Condition": "conditions",
    "Feature": "features",
    "Content": "content",
    "Account": "accounts",
    "Workflow": "workflows",
    "Identity domain": "identity_domains",
    "Identity forest": "identity_forests",
    "Identity facade": "identity_facades",
    "Deployment cell": "deployment_cells",
    "Deployment tenant": "deployment_tenants",
    "Evidence requirement": "evidence_requirements",
    "Entity": "entities",
    "Compute node": "nodes",
    "Inject": "injects",
    "Event": "events",
    "Script": "scripts",
    "Story": "stories",
    "Generated artifact": "generated_artifacts",
    "Persistent volume": "persistent_volumes",
    "Observation boundary": "observation_boundaries",
    "Outcome interpretation rule": "outcome_interpretation_rules",
    "Time domain": "time_domains",
    "Clock": "clocks",
    "Time domain mapping": "time_domain_mappings",
    "Time progression policy": "time_progression_policies",
    "Temporal constraint": "temporal_constraints",
    "Variable": "variables",
    "Variation point": "variation_points",
}
_OLD_TRANSITION_TEXT = re.compile(
    r"Behavior specification '([^']+)' mixed_control (transition|permitted transition) '([^']+)'"
)
_SPECIFICATION_OWNER = ("behavior_specifications", "controlled-red")
_INVALID_FIXTURES = sorted(
    [
        *REPO_ROOT.glob("contracts/fixtures/sdl/*/invalid/*.yaml"),
        *REPO_ROOT.glob("docs/research/formal-semantic-validation/corpus/semantic-invalid-*.sdl.yaml"),
    ]
)


def _old_owner(message: str) -> tuple[str, str] | None:
    """Return the owner that the old message parsing found."""

    label, separator, remainder = message.partition(" '")
    name, closing, _suffix = remainder.partition("'")
    section = _OLD_OWNER_LABELS.get(label)
    return (section, name) if section and separator and closing else None


def _old_pointer(message: str) -> str:
    """Return the refusal pointer that the old migration found in the message."""

    match = _OLD_TRANSITION_TEXT.search(message)
    if match is None:
        return ""
    spec_name, _kind, transition_id = match.groups()
    return f"/behavior_specifications/{spec_name}/mixed_control/transitions/{transition_id}"


def _old_anchors(error: SDLValidationError, scenario: object) -> list[str | None]:
    """Return the declaration address at which the old consumer anchored each message, or None."""

    index = build_declaration_index(scenario, raise_on_collision=False)
    anchors = []
    for message in error.errors:
        owner = _old_owner(message)
        declaration = index.declaration_for(".".join(owner)) if owner is not None else None
        location = declaration.source_location if declaration is not None else None
        anchors.append(declaration.address if location is not None and location.source is not None else None)
    return anchors


def _anchors(error: SDLValidationError) -> list[str | None]:
    return [diagnostic.canonical_address if diagnostic is not None else None for diagnostic in error.diagnostics]


def _validation_error(text: str, path: Path | None = None) -> SDLValidationError:
    with pytest.raises(SDLValidationError) as raised:
        if path is None:
            parse_sdl(text)
        else:
            path.write_text(text, encoding="utf-8")
            parse_sdl_file(path)
    return raised.value


def _refusals(payload: dict) -> set[tuple[str, str]]:
    report = migrate_mixed_control_to_finite_script(_source(payload)).report
    return {(item.code.removeprefix("mixed-control-migration."), item.address) for item in report.diagnostics}


def _old_semantic_errors(scenario: object) -> set[str]:
    try:
        SemanticValidator(scenario).validate()
    except SDLValidationError as exc:
        return set(exc.errors)
    return set()


def test_messages_alone_still_build_a_validation_error() -> None:
    error = SDLValidationError(["x"])
    assert error.errors == ["x"]
    assert error.findings == (SDLValidationFinding("x"),)
    assert (error.findings[0].owner, error.findings[0].pointer) == (None, None)
    assert error.diagnostics == ()
    assert str(error) == "1 validation error:\n  x"

    owned = SDLValidationFinding("Node 'web' failed", ("nodes", "web"))
    mixed = SDLValidationError([owned, "y"], path=Path("scenario.yaml"))
    assert mixed.errors == ["Node 'web' failed", "y"]
    assert mixed.findings == (owned, SDLValidationFinding("y"))
    assert str(mixed) == "scenario.yaml: 2 validation errors:\n  Node 'web' failed\n  y"


def _owner_payload() -> dict:
    payload = _valid_payload()
    payload["relationships"].pop("dc-role")
    payload["nodes"]["orphan"] = {"type": "compute", "os": "linux", "endpoint_persona": "service"}
    payload["identity_forests"]["enterprise"]["root_domain_ref"] = "missing"
    payload["relationships"]["inference-call"]["target"] = "nodes.missing"
    payload["features"] = {
        "a": {"type": "service", "dependencies": ["b"]},
        "b": {"type": "service", "dependencies": ["a"]},
    }
    return payload


def test_validator_passes_and_analyses_record_the_owner_that_source_diagnostics_anchor(tmp_path: Path) -> None:
    error = _validation_error(yaml.safe_dump(_owner_payload(), sort_keys=False), tmp_path / "owners.yaml")

    def owner_of(start: str) -> tuple[str, str] | None:
        return next(finding.owner for finding in error.findings if finding.message.startswith(start))

    # Domain topology, deployment tenancy and enterprise identity analyses.
    assert owner_of("Identity domain 'corp' has no controller relationship") == ("identity_domains", "corp")
    assert owner_of("Compute node 'orphan' must belong to exactly one deployment cell") == ("nodes", "orphan")
    assert owner_of("Identity forest 'enterprise' root_domain_ref 'missing'") == ("identity_forests", "enterprise")
    # A validator pass inside an owner block, and an error that names no declaration.
    assert owner_of("Relationship 'inference-call' target 'nodes.missing'") == ("relationships", "inference-call")
    assert owner_of("Feature dependency graph contains a cycle") is None

    assert [finding.owner for finding in error.findings] == [_old_owner(message) for message in error.errors]
    assert all(finding.pointer is None for finding in error.findings)
    assert _anchors(error) == [".".join(finding.owner) if finding.owner else None for finding in error.findings]


def test_mixed_control_transition_errors_point_at_their_authored_transition() -> None:
    legacy = _link_case("denial", siblings=False)
    error = _validation_error(_source(legacy))
    assert {(finding.owner, finding.pointer) for finding in error.findings} == {
        (_SPECIFICATION_OWNER, f"{POINTER}second")
    }
    assert _refusals(legacy) == {("source-or-target-invalid", f"{POINTER}second")}

    rev1 = rev1_scenario()
    rev1_policy_of(rev1)["controller_states"]["supervised"]["authority_status"] = "revoked"
    error = _validation_error(_source(rev1))
    take = next(finding for finding in error.findings if "permitted transition 'take' enters" in finding.message)
    assert (take.owner, take.pointer) == (
        _SPECIFICATION_OWNER,
        "/behavior_specifications/controlled-red/mixed_control/permitted_transitions/take",
    )
    # A converted edge keeps its legacy id, so a refusal names the legacy transition, as before.
    assert _error_pointers(error) == [_old_pointer(message) for message in error.errors]
    assert ("source-or-target-invalid", f"{POINTER}take") in _refusals(rev1)


def test_a_handoff_error_points_at_its_transition() -> None:
    payload = _legacy(
        {"autonomous": _state("self"), "supervised": _state("self")},
        [("take", "handoff", "autonomous", "supervised", 0, 10, None)],
    )
    (finding,) = _validation_error(_source(payload)).findings
    assert finding.message.startswith("Behavior specification 'controlled-red' mixed_control handoff transition 'take'")
    assert (finding.owner, finding.pointer) == (_SPECIFICATION_OWNER, f"{POINTER}take")
    # The old text parsing did not match the handoff wording and gave no pointer.
    assert _old_pointer(finding.message) == ""
    assert _refusals(payload) == {("source-or-target-invalid", f"{POINTER}take")}


def test_authored_text_that_imitates_a_transition_label_does_not_move_the_refusal_pointer() -> None:
    payload = copy.deepcopy(HANDOFF_CHAIN)
    state = payload["behavior_specifications"]["controlled-red"]["mixed_control"]["controller_states"]["autonomous"]
    state["evidence_refs"] = ["Behavior specification 'controlled-red' mixed_control transition 'take'"]
    (finding,) = _validation_error(_source(payload)).findings
    assert (finding.owner, finding.pointer) == (_SPECIFICATION_OWNER, None)
    # The old text parsing found the imitated label and pointed at the wrong declaration.
    assert _old_pointer(finding.message) == f"{POINTER}take"
    assert _refusals(payload) == {("source-or-target-invalid", "")}


def test_a_specification_name_that_contains_transition_keeps_its_name_owner_and_pointer(tmp_path: Path) -> None:
    payload = _legacy(
        {"autonomous": _state("self"), "supervised": _state("self")},
        [("take", "handoff", "autonomous", "supervised", 0, 10, None)],
    )
    specifications = payload["behavior_specifications"]
    specifications["transition-red"] = specifications.pop("controlled-red")
    error = _validation_error(_source(payload), tmp_path / "handoff.yaml")
    (finding,) = error.findings
    pointer = "/behavior_specifications/transition-red/mixed_control/transitions/take"
    # The handoff wording no longer rewrites the specification name.
    assert finding.message.startswith("Behavior specification 'transition-red' mixed_control handoff transition 'take'")
    assert (finding.owner, finding.pointer) == (("behavior_specifications", "transition-red"), pointer)
    assert _anchors(error) == ["behavior_specifications.transition-red"]
    assert _refusals(payload) == {("source-or-target-invalid", pointer)}


def test_source_diagnostics_anchor_the_recorded_owner_and_not_the_message_text(tmp_path: Path) -> None:
    path = tmp_path / "nodes.yaml"
    path.write_text("name: anchors\nnodes:\n  web: {type: compute}\n  db: {type: compute}\n", encoding="utf-8")
    scenario = parse_sdl_file(path)
    error = SDLValidationError(
        [
            SDLValidationFinding("Node 'web' names another declaration than its owner", ("nodes", "db")),
            SDLValidationFinding("Node 'web' has no recorded owner"),
        ]
    )
    semantic_source_diagnostics(error, scenario)
    owned, unowned = error.diagnostics
    assert (owned.canonical_address, owned.message) == ("nodes.db", error.errors[0])
    assert unowned is None


_TIME_DOMAIN_MAPPING = """
    name: time-anchors
    time_domains:
      scenario:
        kind: simulated
        tick_period_seconds: {numerator: 1, denominator: 1000}
        epoch: scenario_start
        visibility: participant_visible
        description: scenario milliseconds
    time_domain_mappings:
      scenario-to-missing:
        source_domain_ref: scenario
        target_domain_ref: missing
        mapping_kind: affine_rational
        scale: {numerator: 1, denominator: 1}
        offset_ticks: 0
        description: mapping to an undeclared domain
"""
_SWITCH_COUNT = """
    name: switch-anchors
    nodes:
      lan: {type: switch}
    infrastructure:
      lan: {count: 2}
"""
_SCENARIO_FORWARDING_TARGET = """
    name: scenario-forwarding
    forwarding_agents:
      - forwarding_agent_id: relay
        agent_kind: other
        ship_targets:
          - {target_id: manager, target_node_ref: ghost, ingestion_port: 1514}
"""
_SCENARIO_APPARATUS = """
    name: scenario-apparatus
    forwarding_agents:
      - forwarding_agent_id: telemetry
        agent_kind: other
        ownership_role: measurement_apparatus
"""
_NODE_APPARATUS = """
    name: node-apparatus
    nodes:
      sensor:
        type: compute
        resources: {ram: 1 gib, cpu: 1}
        runtime:
          forwarding_agents:
            - forwarding_agent_id: telemetry
              agent_kind: other
              ownership_role: measurement_apparatus
"""
_STATEFUL_RESOURCES = """
    name: stateful-anchors
    nodes:
      web:
        type: compute
        runtime:
          environment:
            - name: API_KEY
              value_from: {generated_artifact: does-not-exist, output: api-key}
      worker:
        type: compute
        os: linux
        runtime:
          mounts:
            - {target: /data, source: /srv/data, source_kind: bind}
    content:
      flag-file:
        type: file
        target: web
        path: /srv/flag.txt
        sensitive: false
        text_from: {generated_artifact: techvault-flag, output: flag}
    propositions:
      flag-correct:
        description: submitted flag equals generated flag
        subjects: [nodes.web]
        basis: declared_state
        predicate:
          kind: string
          property: submitted.flag
          semantic_ref: urn:techvault:flag
          operator: equals
          expected_from: {generated_artifact: techvault-flag, output: flag}
    generated_artifacts:
      techvault-flag:
        generator: random_value
        lifecycle: reuse_valid
        regeneration_scope: per_run
        random_value: {alphabet: hex_lower, length: 32}
        provenance: techvault/ctf-flag
        outputs:
          - {name: flag, path: flag.txt, sensitivity: secret}
      orphan-flag:
        generator: random_value
        lifecycle: reuse_valid
        regeneration_scope: per_run
        random_value: {alphabet: hex_lower, length: 32}
        provenance: techvault/unused-flag
        outputs:
          - {name: flag, path: flag.txt, sensitivity: secret}
    persistent_volumes:
      data:
        lifecycle: retain
        access_mode: read_write_once
        consumers:
          - {node: worker, mount_destination: /data, access_mode: read_write}
      stray:
        lifecycle: retain
        access_mode: read_write_once
        consumers:
          - {node: missing, mount_destination: /stray, access_mode: read_write}
"""


def _temporal_binding_text() -> str:
    payload = _bound_deadline_payload()
    action = payload["action_contracts"]["probe-customer-portal-login"]
    action["temporal_contracts"][0]["shared_time_binding"]["constraint_ref"] = "missing"
    return yaml.safe_dump(payload, sort_keys=False)


# Each case maps the start of an error message to the declaration that the error must anchor at.
_UNANCHORED_BEFORE = {
    "time-domain-mapping": (
        lambda: _TIME_DOMAIN_MAPPING,
        {"Time-domain mapping 'scenario-to-missing' ": "time_domain_mappings.scenario-to-missing"},
    ),
    "switch-node": (lambda: _SWITCH_COUNT, {"Switch node 'lan' ": "nodes.lan"}),
    "scenario-forwarding-agent": (
        lambda: _SCENARIO_FORWARDING_TARGET,
        {"Scenario forwarding agent 'relay' ": "forwarding_agents.relay"},
    ),
    "scenario-forwarding-agent-role": (
        lambda: _SCENARIO_APPARATUS,
        {"Forwarding agent 'forwarding_agents.telemetry' ": "forwarding_agents.telemetry"},
    ),
    "node-forwarding-agent-role": (
        lambda: _NODE_APPARATUS,
        {
            "Forwarding agent 'nodes.sensor.runtime.forwarding_agents.telemetry' ": (
                "nodes.sensor.runtime.forwarding_agents.telemetry"
            )
        },
    ),
    "action-temporal-binding": (
        _temporal_binding_text,
        {"Action 'probe-customer-portal-login' temporal binding ": "action_contracts.probe-customer-portal-login"},
    ),
    "stateful-resources": (
        lambda: _STATEFUL_RESOURCES,
        {
            "persistent_volumes.stray consumer node reference ": "persistent_volumes.stray",
            "node 'web' environment variable 'API_KEY' ": "nodes.web",
            "content 'flag-file' text_from ": "content.flag-file",
            "proposition 'flag-correct' expected_from ": "propositions.flag-correct",
            "generated_artifacts.orphan-flag is declared ": "generated_artifacts.orphan-flag",
            "runtime mount target '/data' on node 'worker' ": "nodes.worker",
        },
    ),
}


@pytest.mark.parametrize("case", sorted(_UNANCHORED_BEFORE))
def test_errors_that_the_old_parsing_left_unanchored_anchor_at_their_declaration(case: str, tmp_path: Path) -> None:
    build, expected = _UNANCHORED_BEFORE[case]
    error = _validation_error(textwrap.dedent(build()), tmp_path / f"{case}.yaml")
    anchored = {}
    for finding, diagnostic in zip(error.findings, error.diagnostics, strict=True):
        start = next((start for start in expected if finding.message.startswith(start)), None)
        if start is None:
            continue
        assert ".".join(finding.owner) == expected[start]
        assert _old_owner(finding.message) is None
        anchored[start] = diagnostic.canonical_address if diagnostic is not None else None
    assert anchored == expected


def _typed_endpoint_payload() -> tuple[dict, str]:
    payload = matrix_payload()
    payload["relationships"]["probe"] = copy.deepcopy(_ENDPOINT_RELATIONSHIPS["uses_shared_service"])
    return payload, "/relationships/probe/source"


def _imitating_baseline_payload() -> tuple[dict, str]:
    payload = _controlled_relationship()
    state = payload["behavior_specifications"]["controlled-red"]["mixed_control"]["controller_states"]["autonomous"]
    state["evidence_refs"] = ["Relationship 'supervises' scope_refs 'Behavior specification 'controlled-red''"]
    return payload, "/relationships/supervises/participant/scope_refs"


@pytest.mark.parametrize("build", [_typed_endpoint_payload, _imitating_baseline_payload])
def test_relationship_completion_keeps_the_candidates_that_message_comparison_kept(
    build, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, cursor = build()
    text = yaml.safe_dump(payload, sort_keys=False)
    baseline = relationship_candidates._semantic_errors(parse_sdl(text, skip_semantic_validation=True))
    assert all(isinstance(finding, SDLValidationFinding) for finding in baseline)
    assert all(finding.owner == _old_owner(finding.message) for finding in baseline)

    completion = language_completions(text, cursor_path=cursor)
    monkeypatch.setattr(relationship_candidates, "_semantic_errors", _old_semantic_errors)
    assert completion["items"]
    assert completion == language_completions(text, cursor_path=cursor)


def test_each_rendered_issue_owner_is_the_declaration_that_its_message_names_first() -> None:
    behavior = {
        code: ParticipantBehaviorIssue(
            code,
            "agent-a",
            "ref-r",
            action_name="action-c",
            boundary_name="boundary-b",
            transition_id="transition-t",
            spec_name="spec-s",
            message="detail",
        )
        for code in _PARTICIPANT_BEHAVIOR_ISSUE_RENDERERS
    }
    objective = {
        code: ObjectiveIssue(
            code, "objective-o", ref="ref-r", actor_name="actor-a", workflow_name="workflow-w", step_name="step-s"
        )
        for code in OBJECTIVE_ISSUE_RENDERERS
    }
    outcome = {
        code: ParticipantOutcomeIssue(code, "rule-u", "binding-b", "ref-r", "layer")
        for code in PARTICIPANT_OUTCOME_ISSUE_RENDERERS
    }
    mismatches = [
        code
        for issues, renderers, owner in (
            (behavior, _PARTICIPANT_BEHAVIOR_ISSUE_RENDERERS, participant_behavior_issue_owner),
            (objective, OBJECTIVE_ISSUE_RENDERERS, objective_issue_owner),
            (outcome, PARTICIPANT_OUTCOME_ISSUE_RENDERERS, participant_outcome_issue_owner),
        )
        for code, issue in issues.items()
        if owner(issue) != _old_owner(renderers[code](issue))
    ]
    assert mismatches == []
    assert objective_issue_owner(objective["objective.dependency-cycle"]) is None

    affiliations = analyze_participant_affiliations(
        agents_by_name={"red": SimpleNamespace(affiliations=["ghost", "team", "team"])},
        entity_names={"team"},
        is_unresolved=lambda _value: False,
    ).issues
    assert {issue.code for issue in affiliations} == {
        "participant.affiliation-unbound",
        "participant.affiliation-duplicate",
    }
    assert all(participant_behavior_issue_owner(issue) == _old_owner(issue.message) for issue in affiliations)


def test_existing_invalid_fixtures_keep_their_owners_pointers_and_diagnostics() -> None:
    checked = []
    for path in _INVALID_FIXTURES:
        try:
            scenario = parse_sdl_file(path, skip_semantic_validation=True)
        except SDLParseError:
            continue
        with pytest.raises(SDLValidationError) as raised:
            SemanticValidator(scenario).validate()
        error = raised.value
        semantic_source_diagnostics(error, scenario)
        assert [finding.owner for finding in error.findings] == [_old_owner(m) for m in error.errors], path.name
        assert _error_pointers(error) == [_old_pointer(message) for message in error.errors], path.name
        assert _anchors(error) == _old_anchors(error, scenario), path.name
        checked.append(path.name)
    assert len(checked) >= 6, checked
