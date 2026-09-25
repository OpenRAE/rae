"""DSL-142 participant-directed inject authoring and compiler semantics."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from raes import build_declaration_index
from raes._errors import SDLInstantiationError, SDLParseError, SDLValidationError
from raes.instantiate import instantiate_scenario
from raes.parser import parse_sdl, parse_sdl_file
from raes_contracts.contracts import schema_bundle
from raes_processor.compiler.time_model import time_model_contract_model
from raes_processor.compiler import compile_runtime_model

REPO_ROOT = Path(__file__).resolve().parents[3]
BINDING_REF = "behavior_specifications.red-briefing.participant_inject_deliveries.briefing"
BINDING_ADDRESS = "participant.behavior-specification.red-briefing.inject-delivery.briefing"
INJECT_ADDRESS = "orchestration.inject.briefing-inject"


def _scenario_yaml() -> str:
    return textwrap.dedent(
        f"""
        name: dsl-142
        nodes:
          web:
            type: compute
            resources: {{ram: 1 gib, cpu: 1}}
        entities:
          red-team:
            role: red
        content:
          briefing:
            type: file
            target: web
            path: /opt/briefing.txt
            text: hidden inject content must not enter participant compiler metadata
            sensitive: true
        injects:
          briefing-inject:
            description: orchestration-only hidden briefing body
            environment: [set-exercise-banner]
        events:
          briefing-event:
            injects: [briefing-inject]
        scripts:
          briefing-script:
            start_time: 0
            end_time: 10
            speed: 1
            events:
              briefing-event: 5
        stories:
          briefing-story:
            scripts: [briefing-script]
        time_domains:
          exercise-time:
            kind: logical
            tick_period_seconds: {{numerator: 1, denominator: 1}}
            epoch: scenario_start
            visibility: participant_visible
            description: exercise logical time
        clocks:
          exercise-clock:
            time_domain_ref: exercise-time
            authority_kind: runtime
            authority_ref: runtime.scheduler
            monotonicity: non_decreasing
            description: exercise scheduler clock
        temporal_constraints:
          briefing-window:
            constraint_kind: window
            clock_ref: exercise-clock
            subject_refs: [{BINDING_REF}]
            start: {{tick: 4}}
            end: {{tick: 6}}
            description: participant briefing delivery window
        evidence_requirements:
          briefing-delivery-evidence:
            description: capture governed participant delivery evidence
            source_refs: [{BINDING_REF}]
            scope_refs: [web]
            window: briefing delivery window
            channel: log
            artifact_role: delivery_evidence
            sensitivity: plain
            redaction: none
            integrity: checksum
            retention: study_lifetime
            loss_disclosure: required
        observation_boundaries:
          red-view:
            projection_basis: participant-local governed briefing view
            observable_refs: [content.briefing]
            redaction_policy: hidden refs remain hidden
            latency_profile: delivery-order bound
            view_rules:
              - information_ref: content.briefing
                boundary_class: instruction
                disposition: disclosed
                visibility_basis: visibility-bases.briefing.v1
                disclosure_rule: disclosures.briefing.v1
        agents:
          red-agent:
            affiliations: [red-team]
            observation_boundaries: [red-view]
        behavior_specifications:
          red-briefing:
            semantic_version: 1.0.0
            participant_refs: [red-agent]
            observation_boundary_refs: [red-view]
            participant_inject_deliveries:
              briefing:
                participant_ref: red-agent
                inject_ref: briefing-inject
                occurrence:
                  event_ref: briefing-event
                  script_ref: briefing-script
                  story_ref: briefing-story
                source_item_ref: content.briefing
                result_item_ref: content.briefing
                observation_boundary_ref: red-view
                delivery_kind: disclosure
                delivery_policy:
                  policy_ref: projection-policy.red.v1
                  policy_revision: 1.0.0
                  exposure_policy_ref: exposure-policy.red.v1
                  audience_scope_ref: audience.participant.red-agent
                  visibility_basis_ref: visibility-bases.briefing.v1
                  disclosure_basis_ref: disclosures.briefing.v1
                order_basis: orchestration-occurrence-and-shared-time
                temporal_constraint_refs: [briefing-window]
                evidence_requirement_refs: [briefing-delivery-evidence]
                failure_disposition: reject-no-delivery
        """
    )


def _replace(source: str, old: str, new: str) -> str:
    assert old in source
    return source.replace(old, new, 1)


def test_participant_inject_delivery_parses_and_compiles_typed_metadata() -> None:
    scenario = parse_sdl(_scenario_yaml())
    binding = scenario.behavior_specifications["red-briefing"].participant_inject_deliveries["briefing"]

    assert binding.participant_ref == "red-agent"
    assert binding.inject_ref == "briefing-inject"
    assert binding.occurrence.event_ref == "briefing-event"

    model = compile_runtime_model(scenario)
    compiled = model.participant_inject_deliveries[BINDING_ADDRESS]
    assert compiled.behavior_specification_address == "participant.behavior-specification.red-briefing"
    assert compiled.participant_address == "participant.behavior.red-agent"
    assert compiled.inject_address == INJECT_ADDRESS
    assert compiled.event_address == "orchestration.event.briefing-event"
    assert compiled.script_address == "orchestration.script.briefing-script"
    assert compiled.story_address == "orchestration.story.briefing-story"
    assert compiled.temporal_constraint_addresses == ("time.constraint.briefing-window",)
    assert compiled.evidence_requirement_addresses == ("sdl.evidence-requirements.briefing-delivery-evidence",)
    assert INJECT_ADDRESS in compiled.refresh_dependencies


def test_participant_inject_delivery_is_a_valid_temporal_subject() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))

    declaration = time_model_contract_model(model.time_model)

    assert declaration is not None
    constraint = declaration.temporal_constraints["time.constraint.briefing-window"]
    assert constraint.subject_addresses == [BINDING_ADDRESS]


def test_compiler_preserves_inject_identity_without_copying_hidden_content() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    compiled = model.participant_inject_deliveries[BINDING_ADDRESS]
    rendered = json.dumps(compiled.spec, sort_keys=True)

    assert compiled.inject_address == INJECT_ADDRESS
    assert "orchestration-only hidden briefing body" not in rendered
    assert "hidden inject content must not enter participant compiler metadata" not in rendered
    assert "environment" not in compiled.spec
    assert model.injects[INJECT_ADDRESS].spec["environment"] == ["set-exercise-banner"]


def test_environment_only_injects_remain_orchestration_only() -> None:
    source = _scenario_yaml()
    block_start = source.index("    participant_inject_deliveries:\n")
    block_end_marker = "        failure_disposition: reject-no-delivery\n"
    block_end = source.index(block_end_marker, block_start) + len(block_end_marker)
    source = source[:block_start] + source[block_end:]
    source = source.replace(
        f"subject_refs: [{BINDING_REF}]",
        "subject_refs: [injects.briefing-inject]",
    ).replace(
        f"source_refs: [{BINDING_REF}]",
        "source_refs: [injects.briefing-inject]",
    )

    model = compile_runtime_model(parse_sdl(source))

    assert model.participant_inject_deliveries == {}
    assert set(model.injects) == {INJECT_ADDRESS}
    assert model.events["orchestration.event.briefing-event"].inject_addresses == (INJECT_ADDRESS,)


def test_delivery_binding_is_closed_and_requires_one_explicit_addressee() -> None:
    source = _replace(
        _scenario_yaml(),
        "        participant_ref: red-agent\n",
        "        participant_ref: red-agent\n        participant_refs: [red-agent]\n",
    )

    with pytest.raises(SDLParseError, match="Extra inputs are not permitted"):
        parse_sdl(source)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("participant_ref: red-agent", "participant_ref: missing-agent", "participant_ref 'missing-agent'"),
        ("inject_ref: briefing-inject", "inject_ref: missing-inject", "inject_ref 'missing-inject'"),
        ("event_ref: briefing-event", "event_ref: missing-event", "event_ref 'missing-event'"),
        ("script_ref: briefing-script", "script_ref: missing-script", "script_ref 'missing-script'"),
        ("story_ref: briefing-story", "story_ref: missing-story", "story_ref 'missing-story'"),
        (
            "observation_boundary_ref: red-view",
            "observation_boundary_ref: missing-view",
            "observation_boundary_ref 'missing-view'",
        ),
        (
            "temporal_constraint_refs: [briefing-window]",
            "temporal_constraint_refs: [missing-window]",
            "temporal_constraint_ref 'missing-window'",
        ),
        (
            "evidence_requirement_refs: [briefing-delivery-evidence]",
            "evidence_requirement_refs: [missing-evidence]",
            "evidence_requirement_ref 'missing-evidence'",
        ),
    ],
)
def test_delivery_references_fail_closed(old: str, new: str, expected: str) -> None:
    source = _replace(_scenario_yaml(), old, new)

    with pytest.raises(SDLValidationError, match=expected):
        parse_sdl(source)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("injects: [briefing-inject]", "injects: []", "does not contain inject"),
        ("events:\n      briefing-event: 5", "events:\n      other-event: 5", "script_ref"),
        ("scripts: [briefing-script]", "scripts: [other-script]", "story_ref"),
    ],
)
def test_occurrence_anchor_must_preserve_the_inject_event_script_story_chain(
    old: str,
    new: str,
    expected: str,
) -> None:
    source = _replace(_scenario_yaml(), old, new)

    with pytest.raises((SDLValidationError, SDLParseError), match=expected):
        parse_sdl(source)


def test_hidden_or_unclassified_items_cannot_cross_the_participant_boundary() -> None:
    hidden = (
        _scenario_yaml()
        .replace(
            "observable_refs: [content.briefing]",
            "observable_refs: [nodes.web]\n    hidden_refs: [content.briefing]",
        )
        .replace("disposition: disclosed", "disposition: hidden")
        .replace("        disclosure_rule: disclosures.briefing.v1\n", "")
    )

    with pytest.raises(SDLValidationError, match="must be disclosed or observable"):
        parse_sdl(hidden)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            "visibility_basis_ref: visibility-bases.briefing.v1",
            "visibility_basis_ref: visibility-bases.ungranted.v1",
        ),
        (
            "disclosure_basis_ref: disclosures.briefing.v1",
            "disclosure_basis_ref: disclosures.ungranted.v1",
        ),
    ],
)
def test_delivery_policy_basis_must_match_the_selected_participant_view_rule(
    old: str,
    new: str,
) -> None:
    source = _replace(_scenario_yaml(), old, new)

    with pytest.raises(SDLValidationError, match="visibility/disclosure basis does not agree"):
        parse_sdl(source)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("policy_ref: projection-policy.red.v1", "policy_ref: ''"),
        ("policy_revision: 1.0.0", "policy_revision: ''"),
        ("failure_disposition: reject-no-delivery", "failure_disposition: continue"),
        ("order_basis: orchestration-occurrence-and-shared-time", "order_basis: wall-clock"),
    ],
)
def test_delivery_policy_order_and_failure_disposition_are_closed(old: str, new: str) -> None:
    source = _replace(_scenario_yaml(), old, new)

    with pytest.raises(SDLParseError):
        parse_sdl(source)


def test_direction_and_intervention_require_a_compatible_mixed_control_transition() -> None:
    direction = _scenario_yaml().replace("delivery_kind: disclosure", "delivery_kind: external-direction")

    with pytest.raises(SDLParseError, match="control_transition_ref"):
        parse_sdl(direction)


def _external_direction_yaml() -> str:
    return (
        _scenario_yaml()
        .replace(
            "  red-team:\n    role: red\n",
            "  red-team:\n    role: red\n  blue-team:\n    role: blue\n",
        )
        .replace(
            "  red-agent:\n    affiliations: [red-team]\n    observation_boundaries: [red-view]\n",
            (
                "  red-agent:\n"
                "    affiliations: [red-team]\n"
                "    authority_anchors: [entities.red-team]\n"
                "    operating_scope: [nodes.web]\n"
                "    observation_boundaries: [red-view]\n"
                "  supervisor-agent:\n"
                "    affiliations: [blue-team]\n"
                "    authority_anchors: [entities.blue-team]\n"
                "    operating_scope: [nodes.web]\n"
            ),
        )
        .replace(
            "    observation_boundary_refs: [red-view]\n    participant_inject_deliveries:\n",
            (
                "    observation_boundary_refs: [red-view]\n"
                "    authority_scope_refs: [nodes.web]\n"
                "    behavior_mode: mixed-control\n"
                "    mixed_control:\n"
                "      participant_ref: red-agent\n"
                "      policy_revision: 1.0.0\n"
                "      order_strategy: total-effective-order\n"
                "      initial_state_ref: autonomous\n"
                "      dispositions:\n"
                "        duplicate: idempotent-if-equivalent\n"
                "        stale: reject-no-state-change\n"
                "        revoked: reject-no-state-change\n"
                "        late: reject-no-state-change\n"
                "        concurrent: order-then-revalidate\n"
                "        conflict: reject-no-state-change\n"
                "      controller_states:\n"
                "        autonomous:\n"
                "          controller_ref: self\n"
                "          authority_basis_refs: [entities.red-team]\n"
                "          scope_refs: [nodes.web]\n"
                "          policy_revision: 1.0.0\n"
                "          valid_from_order: 0\n"
                "          valid_until_order: 10\n"
                "          authority_status: active\n"
                "          evidence_refs: [entities.red-team]\n"
                "        pending:\n"
                "          controller_ref: self\n"
                "          authority_basis_refs: [entities.red-team]\n"
                "          scope_refs: [nodes.web]\n"
                "          policy_revision: 1.0.0\n"
                "          valid_from_order: 10\n"
                "          valid_until_order: 11\n"
                "          authority_status: active\n"
                "          evidence_refs: [entities.red-team]\n"
                "        directed:\n"
                "          controller_ref: supervisor-agent\n"
                "          authority_basis_refs: [entities.blue-team]\n"
                "          scope_refs: [nodes.web]\n"
                "          policy_revision: 1.0.0\n"
                "          valid_from_order: 11\n"
                "          valid_until_order: 99\n"
                "          authority_status: active\n"
                "          evidence_refs: [entities.blue-team]\n"
                "      transitions:\n"
                "        propose-direction:\n"
                "          transition_kind: proposal\n"
                "          from_state_ref: autonomous\n"
                "          to_state_ref: pending\n"
                "          policy_revision: 1.0.0\n"
                "          expected_state_revision: 0\n"
                "          resulting_state_revision: 1\n"
                "          effective_order: 10\n"
                "          valid_from_order: 0\n"
                "          valid_until_order: 10\n"
                "          evidence_refs: [entities.red-team]\n"
                "        direct-briefing:\n"
                "          transition_kind: external-direction\n"
                "          from_state_ref: pending\n"
                "          to_state_ref: directed\n"
                "          policy_revision: 1.0.0\n"
                "          expected_state_revision: 1\n"
                "          resulting_state_revision: 2\n"
                "          effective_order: 11\n"
                "          valid_from_order: 0\n"
                "          valid_until_order: 11\n"
                "          proposal_ref: propose-direction\n"
                "          proposal_revision: 1\n"
                "          evidence_refs: [entities.blue-team]\n"
                "    participant_inject_deliveries:\n"
            ),
        )
        .replace(
            "    scope_refs: [web]\n    window: briefing delivery window\n",
            "    scope_refs: [web, entities.blue-team]\n    window: briefing delivery window\n",
        )
        .replace("start: {tick: 4}", "start: {tick: 10}")
        .replace("end: {tick: 6}", "end: {tick: 12}")
        .replace("delivery_kind: disclosure", "delivery_kind: external-direction")
        .replace(
            "        failure_disposition: reject-no-delivery\n",
            (
                "        failure_disposition: reject-no-delivery\n"
                "        control_transition_ref: direct-briefing\n"
                "        controller_ref: supervisor-agent\n"
                "        control_authority_scope_refs: [nodes.web]\n"
                "        control_effective_order: 11\n"
                "        control_valid_from_order: 0\n"
                "        control_valid_until_order: 11\n"
                "        control_evidence_refs: [entities.blue-team]\n"
            ),
        )
    )


def _remove_mixed_control(source: str) -> str:
    start = source.index("    mixed_control:\n")
    end = source.index("    participant_inject_deliveries:\n", start)
    return source[:start] + source[end:]


def _replace_mixed_control_policy_revision(source: str, revision: str) -> str:
    start = source.index("    mixed_control:\n")
    end = source.index("    participant_inject_deliveries:\n", start)
    mixed_control = source[start:end].replace("policy_revision: 1.0.0", f"policy_revision: {revision}")
    return source[:start] + mixed_control + source[end:]


def _directed_control_legitimacy_case(case: str) -> str:
    source = _external_direction_yaml()
    if case == "missing-mixed-control":
        return _remove_mixed_control(source)
    if case == "unresolved-transition":
        return _replace(source, "control_transition_ref: direct-briefing", "control_transition_ref: missing")
    if case == "wrong-transition-kind":
        return _replace(source, "control_transition_ref: direct-briefing", "control_transition_ref: propose-direction")
    if case == "participant-mismatch":
        return _replace(source, "      participant_ref: red-agent", "      participant_ref: supervisor-agent")
    if case == "policy-revision-mismatch":
        return _replace_mixed_control_policy_revision(source, "2.0.0")
    raise AssertionError(f"unknown directed control legitimacy case: {case}")


def test_external_direction_binds_a_compatible_control_transition() -> None:
    compiled = compile_runtime_model(parse_sdl(_external_direction_yaml())).participant_inject_deliveries[
        BINDING_ADDRESS
    ]
    control_address = "participant.behavior-specification.red-briefing.control-transition.direct-briefing"

    assert compiled.delivery_kind == "external-direction"
    assert compiled.control_transition_address == control_address
    assert compiled.controller_address == "participant.behavior.supervisor-agent"
    assert compiled.control_authority_scope_addresses == ("provision.node.web",)
    assert compiled.control_effective_order == 11
    assert compiled.control_valid_from_order == 0
    assert compiled.control_valid_until_order == 11
    assert compiled.control_evidence_refs == ("entities.blue-team",)
    assert compiled.control_evidence_addresses == ()
    assert control_address in compiled.refresh_dependencies


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("missing-mixed-control", "control_transition_ref requires mixed_control"),
        ("unresolved-transition", "control_transition_ref 'missing' does not resolve"),
        ("wrong-transition-kind", "does not match delivery_kind"),
        ("participant-mismatch", "control transition participant disagrees"),
        ("policy-revision-mismatch", "control transition policy revision disagrees"),
    ],
)
def test_directed_delivery_rejects_illegitimate_control_transition_bindings(
    case: str,
    expected: str,
) -> None:
    source = _directed_control_legitimacy_case(case)

    with pytest.raises(SDLValidationError, match=expected):
        parse_sdl(source)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("controller_ref: supervisor-agent", "controller_ref: red-agent", "controller_ref"),
        (
            "control_authority_scope_refs: [nodes.web]",
            "control_authority_scope_refs: [content.briefing]",
            "authority scope",
        ),
        ("control_effective_order: 11", "control_effective_order: 10", "effective order"),
        ("control_valid_from_order: 0", "control_valid_from_order: 1", "validity interval"),
        ("control_valid_until_order: 11", "control_valid_until_order: 12", "validity interval"),
        ("end: {tick: 12}", "end: {tick: 10}", "temporal constraint"),
        (
            "control_evidence_refs: [entities.blue-team]",
            "control_evidence_refs: [entities.red-team]",
            "control evidence",
        ),
        (
            "scope_refs: [web, entities.blue-team]",
            "scope_refs: [web]",
            "evidence requirement",
        ),
    ],
)
def test_directed_delivery_rejects_incoherent_control_time_and_evidence_agreement(
    old: str,
    new: str,
    expected: str,
) -> None:
    source = _replace(_external_direction_yaml(), old, new)

    with pytest.raises(SDLValidationError, match=expected):
        parse_sdl(source)


def test_disclosure_cannot_smuggle_an_intervention_binding() -> None:
    source = _replace(
        _scenario_yaml(),
        "        failure_disposition: reject-no-delivery\n",
        ("        failure_disposition: reject-no-delivery\n        control_transition_ref: direct-briefing\n"),
    )

    with pytest.raises(SDLParseError, match="control_transition_ref"):
        parse_sdl(source)


def test_participant_delivery_refs_are_rewritten_by_module_composition(tmp_path: Path) -> None:
    module = tmp_path / "module.yaml"
    module.write_text(
        _scenario_yaml().replace(
            "name: dsl-142\n",
            textwrap.dedent(
                """
                name: dsl-142
                module:
                  id: acme/briefing
                  version: 1.0.0
                  exports:
                    nodes: [web]
                    entities: [red-team]
                    content: [briefing]
                    injects: [briefing-inject]
                    events: [briefing-event]
                    scripts: [briefing-script]
                    stories: [briefing-story]
                    agents: [red-agent]
                    observation_boundaries: [red-view]
                    behavior_specifications: [red-briefing]
                    evidence_requirements: [briefing-delivery-evidence]
                    time_domains: [exercise-time]
                    clocks: [exercise-clock]
                    temporal_constraints: [briefing-window]
                """
            ).lstrip(),
            1,
        ),
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        "name: root\nimports:\n  - source: local:module.yaml\n    namespace: shared\n",
        encoding="utf-8",
    )

    scenario = parse_sdl_file(root)
    binding = scenario.behavior_specifications["shared.red-briefing"].participant_inject_deliveries["briefing"]

    assert binding.participant_ref == "shared.red-agent"
    assert binding.inject_ref == "shared.briefing-inject"
    assert binding.occurrence.event_ref == "shared.briefing-event"
    assert binding.occurrence.script_ref == "shared.briefing-script"
    assert binding.occurrence.story_ref == "shared.briefing-story"
    assert binding.source_item_ref == "content.shared.briefing"
    assert binding.observation_boundary_ref == "shared.red-view"
    assert binding.temporal_constraint_refs == ["shared.briefing-window"]
    assert binding.evidence_requirement_refs == ["shared.briefing-delivery-evidence"]


def test_directed_delivery_control_refs_are_rewritten_by_module_composition(tmp_path: Path) -> None:
    module = tmp_path / "module.yaml"
    module.write_text(
        _external_direction_yaml().replace(
            "name: dsl-142\n",
            textwrap.dedent(
                """
                name: dsl-142
                module:
                  id: acme/directed-briefing
                  version: 1.0.0
                  exports:
                    nodes: [web]
                    entities: [red-team, blue-team]
                    content: [briefing]
                    injects: [briefing-inject]
                    events: [briefing-event]
                    scripts: [briefing-script]
                    stories: [briefing-story]
                    agents: [red-agent, supervisor-agent]
                    observation_boundaries: [red-view]
                    behavior_specifications: [red-briefing]
                    evidence_requirements: [briefing-delivery-evidence]
                    time_domains: [exercise-time]
                    clocks: [exercise-clock]
                    temporal_constraints: [briefing-window]
                """
            ).lstrip(),
            1,
        ),
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        "name: root\nimports:\n  - source: local:module.yaml\n    namespace: shared\n",
        encoding="utf-8",
    )

    binding = (
        parse_sdl_file(root).behavior_specifications["shared.red-briefing"].participant_inject_deliveries["briefing"]
    )

    assert binding.controller_ref == "shared.supervisor-agent"
    assert binding.control_authority_scope_refs == ["nodes.shared.web"]
    assert binding.control_evidence_refs == ["entities.shared.blue-team"]


def test_binding_is_a_typed_declaration_and_valid_temporal_subject() -> None:
    scenario = parse_sdl(_scenario_yaml())
    declaration = build_declaration_index(scenario).declaration_for(BINDING_REF)

    assert declaration is not None
    assert declaration.kind == "participant-inject-delivery"
    assert declaration.targetable is True
    constraint = next(
        item
        for item in compile_runtime_model(scenario).time_model.constraints
        if item.address == "time.constraint.briefing-window"
    )
    assert constraint.subject_addresses == (BINDING_ADDRESS,)


def test_invalid_substituted_participant_is_rejected_before_compilation() -> None:
    source = (
        _scenario_yaml()
        .replace(
            "name: dsl-142\n",
            textwrap.dedent(
                """
            name: dsl-142
            variables:
              delivery_participant:
                type: string
                default: red-agent
                allowed_values: [red-agent, missing-agent]
            """
            ).lstrip(),
            1,
        )
        .replace("participant_ref: red-agent", "participant_ref: ${delivery_participant}", 1)
    )
    authored = parse_sdl(source)

    instantiate_scenario(authored, parameters={"delivery_participant": "red-agent"})
    with pytest.raises(SDLInstantiationError, match="missing-agent"):
        instantiate_scenario(authored, parameters={"delivery_participant": "missing-agent"})


def test_all_scenario_contracts_publish_the_closed_delivery_shape() -> None:
    for contract_id in (
        "sdl-authoring-input-v1",
        "instantiated-scenario-v1",
        "instantiated-scenario-snapshot-v1",
        "scenario-satisfiability-evidence-v1",
    ):
        schema = schema_bundle()[contract_id]
        binding = schema["$defs"]["ParticipantInjectDelivery"]
        assert binding["additionalProperties"] is False
        assert {
            "participant_ref",
            "inject_ref",
            "occurrence",
            "source_item_ref",
            "result_item_ref",
            "observation_boundary_ref",
            "delivery_kind",
            "delivery_policy",
            "order_basis",
            "temporal_constraint_refs",
            "evidence_requirement_refs",
            "failure_disposition",
        } <= set(binding["required"])


def test_published_valid_and_invalid_delivery_fixtures() -> None:
    fixture_root = REPO_ROOT / "contracts" / "fixtures" / "sdl" / "participant-inject-delivery-v1"
    valid = fixture_root / "valid" / "participant-directed.yaml"
    invalid = fixture_root / "invalid" / "environment-only-leakage.yaml"

    assert parse_sdl_file(valid).behavior_specifications["red-briefing"].participant_inject_deliveries
    with pytest.raises(SDLValidationError, match="must be disclosed or observable"):
        parse_sdl_file(invalid)

    published = json.loads(
        (REPO_ROOT / "contracts" / "schemas" / "sdl" / "sdl-authoring-input-v1.json").read_text(encoding="utf-8")
    )
    payload = parse_sdl_file(valid).model_dump(mode="json", exclude_defaults=True)
    Draft202012Validator(published).validate(payload)
