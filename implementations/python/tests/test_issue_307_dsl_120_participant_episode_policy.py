"""DSL-120 authored participant episode structure and termination surface."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from raes._errors import SDLInstantiationError, SDLParseError, SDLValidationError
from raes.instantiate import instantiate_scenario
from raes.language_service import language_completions
from raes.parser import parse_sdl, parse_sdl_file
from raes_contracts.contracts import schema_bundle
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import ParticipantEpisodeConditionRuntime

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "contracts" / "fixtures" / "sdl" / "participant-episode-policy-v1"
VALID_FIXTURE = FIXTURE_ROOT / "valid" / "analyst-shift-episode.yaml"
INVALID_FIXTURE = FIXTURE_ROOT / "invalid" / "realized-episode-state.yaml"
POLICY_ADDRESS = "participant.episode-policy.analyst-triage"
SPEC_ADDRESS = "participant.behavior-specification.analyst-triage"
PARTICIPANT_ADDRESS = "participant.behavior.analyst"
REALIZED_STATE = "declare intent only"
CLOSED_RECORD = "Extra inputs are not permitted"


def _source() -> str:
    return VALID_FIXTURE.read_text(encoding="utf-8")


def _replace(source: str, old: str, new: str) -> str:
    assert old in source
    return source.replace(old, new, 1)


def _edit(old: str, new: str) -> str:
    return _replace(_source(), old, new)


def _policy_free_source() -> str:
    source = _source()
    start = source.index("    episode_policy:\n")
    return source[:start]


def test_authored_policy_compiles_to_episode_refs() -> None:
    model = compile_runtime_model(parse_sdl(_source()))
    compiled = model.participant_episode_policies[POLICY_ADDRESS]

    assert compiled.behavior_specification_address == SPEC_ADDRESS
    assert compiled.participant_addresses == (PARTICIPANT_ADDRESS,)
    assert PARTICIPANT_ADDRESS in model.participant_behaviors
    assert compiled.profile == "participant-episode-policy/v1"
    assert compiled.initialization_assertion_addresses == ("evaluation.assertion.console-ready",)
    assert compiled.turn_order_basis == "decision-epoch"
    assert compiled.turn_action_contract_addresses == ("participant.action-contract.triage-alert",)
    assert {
        (item.condition_id, item.terminal_reason, item.assertion_addresses, item.temporal_constraint_address)
        for item in compiled.conditions
    } == {
        ("ticket-closed", "completed", ("evaluation.assertion.ticket-closed",), ""),
        ("shift-ended", "timed_out", (), "time.constraint.shift-deadline"),
        ("queue-stalled", "truncated", ("evaluation.assertion.queue-stalled",), ""),
    }
    assert all(item.evidence_requirement_addresses for item in compiled.conditions)
    assert compiled.reset_control_actions == ("reset", "restart")
    assert compiled.participant_memory_scope == "persistent_across_episodes"
    assert compiled.reset_evidence_requirement_addresses == ("sdl.evidence-requirements.reset-evidence",)
    assert {SPEC_ADDRESS, PARTICIPANT_ADDRESS, "time.constraint.shift-deadline"} <= set(compiled.refresh_dependencies)


@pytest.mark.parametrize(
    ("old", "new", "realized"),
    [
        (
            "      profile: participant-episode-policy/v1\n",
            "      profile: participant-episode-policy/v1\n      episode_id: analyst-ep-0001\n",
            "episode_id",
        ),
        (
            "        assertion_refs: [console-ready]\n",
            "        assertion_refs: [console-ready]\n        initialized_at: '2026-10-09T00:00:00Z'\n",
            "initialized_at",
        ),
        (
            "        order_basis: decision-epoch\n",
            "        order_basis: decision-epoch\n        decision_epoch: 4\n",
            "decision_epoch",
        ),
        (
            "          terminal_reason: completed\n",
            "          terminal_reason: completed\n          terminated_at: '2026-10-09T08:00:00Z'\n",
            "terminated_at",
        ),
        (
            "        control_actions: [reset, restart]\n",
            "        control_actions: [reset, restart]\n        previous_episode_id: analyst-ep-0000\n",
            "previous_episode_id",
        ),
    ],
)
def test_policy_records_reject_realized_episode_state(old: str, new: str, realized: str) -> None:
    source = _edit(old, new)

    with pytest.raises(SDLParseError, match=rf"{REALIZED_STATE}.*{realized}"):
        parse_sdl(source)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (
            "      profile: participant-episode-policy/v1\n",
            "      profile: participant-episode-policy/v1\n      max_turns: 20\n",
            CLOSED_RECORD,
        ),
        (
            "          temporal_constraint_ref: shift-deadline\n",
            "          temporal_constraint_ref: shift-deadline\n          expression: clock > 480\n",
            CLOSED_RECORD,
        ),
        (
            "        assertion_refs: [console-ready]\n",
            "        assertion_refs: [console-ready]\n        command: ./check-console.sh\n",
            CLOSED_RECORD,
        ),
        ("profile: participant-episode-policy/v1", "profile: participant-episode-policy/v2", "participant-episode"),
        ("assertion_refs: [console-ready]", "assertion_refs: []", "at least 1 item"),
        ("assertion_refs: [console-ready]", "assertion_refs: [console-ready, console-ready]", "must not repeat"),
        ("control_actions: [reset, restart]", "control_actions: [initialize]", "control_actions"),
        ("order_basis: decision-epoch", "order_basis: wall-clock", "order_basis"),
        ("participant_memory_scope: persistent_across_episodes", "participant_memory_scope: global", "memory"),
        ("assertion_refs: [console-ready]", "assertion_refs: ['   ']", "should match pattern"),
        (
            "participant_memory_scope: persistent_across_episodes",
            "participant_memory_scope: episode_local_reset",
            "episode_local_reset memory scope requires memory_reset_authority_ref",
        ),
        (
            "participant_memory_scope: persistent_across_episodes",
            "participant_memory_scope: persistent_across_episodes\n        memory_reset_authority_ref: analyst-console-reset",
            "persistent_across_episodes memory scope must not claim a reset authority",
        ),
    ],
)
def test_policy_records_are_closed_and_typed(old: str, new: str, expected: str) -> None:
    source = _edit(old, new)

    with pytest.raises(SDLParseError, match=expected):
        parse_sdl(source)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("        ticket-closed:\n", "        ${closing_condition}:\n"),
        ("        queue-stalled:\n", "        ${stall_condition}:\n"),
    ],
)
def test_variable_created_condition_keys_are_rejected(old: str, new: str) -> None:
    source = _edit(old, new)

    with pytest.raises(SDLParseError, match="Variable placeholders are not allowed in user-defined mapping keys"):
        parse_sdl(source)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("terminal_reason: completed", "terminal_reason: truncated", "terminal_reason"),
        ("terminal_reason: completed", "terminal_reason: interrupted", "terminal_reason"),
        (
            "          assertion_refs: [queue-stalled]\n",
            "          assertion_refs: [queue-stalled]\n          temporal_constraint_ref: shift-deadline\n",
            CLOSED_RECORD,
        ),
        (
            "          temporal_constraint_ref: shift-deadline\n",
            "          temporal_constraint_ref: shift-deadline\n          assertion_refs: [ticket-closed]\n",
            CLOSED_RECORD,
        ),
        ("        queue-stalled:\n", "        ticket-closed:\n", "unique across terminal and truncation conditions"),
        (
            "          assertion_refs: [queue-stalled]\n",
            "          assertion_refs: [queue-stalled]\n          terminal_reason: truncated\n",
            "always end the episode as truncated and carry no terminal_reason",
        ),
    ],
)
def test_terminal_reasons_stay_distinct(old: str, new: str, expected: str) -> None:
    source = _edit(old, new)

    with pytest.raises(SDLParseError, match=expected):
        parse_sdl(source)


def test_policy_must_declare_an_episode_structure_element() -> None:
    source = _policy_free_source() + "    episode_policy:\n      profile: participant-episode-policy/v1\n"

    with pytest.raises(SDLParseError, match="at least one episode structure element"):
        parse_sdl(source)


_SHIFT_DEADLINE = """  shift-deadline:
    constraint_kind: deadline
    clock_ref: shift-clock
    subject_refs: [behavior_specifications.analyst-triage]
    end: {tick: 480}
"""


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (
            "        assertion_refs: [console-ready]\n",
            "        assertion_refs: [missing-assertion]\n",
            "initialization assertion 'missing-assertion' not in assertions section",
        ),
        (
            "        assertion_refs: [console-ready]\n",
            "        assertion_refs: [ticket-closed]\n",
            "initialization assertion 'ticket-closed' must be a precondition",
        ),
        (
            "        action_contract_refs: [triage-alert]\n",
            "        action_contract_refs: [escalate-alert]\n",
            "action_contract_ref 'escalate-alert' is outside the owning behavior specification",
        ),
        (
            "          assertion_refs: [ticket-closed]\n",
            "          assertion_refs: [missing-assertion]\n",
            "terminal condition 'ticket-closed' assertion 'missing-assertion' not in assertions section",
        ),
        (
            "          assertion_refs: [ticket-closed]\n",
            "          assertion_refs: [console-ready]\n",
            "terminal condition 'ticket-closed' assertion 'console-ready' must be an invariant or postcondition",
        ),
        (
            "          assertion_refs: [queue-stalled]\n",
            "          assertion_refs: [console-ready]\n",
            "truncation condition 'queue-stalled' assertion 'console-ready' must be an invariant or postcondition",
        ),
        (
            "temporal_constraint_ref: shift-deadline",
            "temporal_constraint_ref: missing-deadline",
            "temporal_constraint_ref 'missing-deadline' does not reference a declared temporal constraint",
        ),
        (
            _SHIFT_DEADLINE,
            _SHIFT_DEADLINE.replace("constraint_kind: deadline", "constraint_kind: cadence").replace(
                "end: {tick: 480}", "cadence_ticks: 60"
            ),
            "temporal_constraint_ref 'shift-deadline' must be a deadline, window, or duration constraint",
        ),
        (
            _SHIFT_DEADLINE,
            _SHIFT_DEADLINE.replace("[behavior_specifications.analyst-triage]", "[nodes.siem]"),
            "temporal_constraint_ref 'shift-deadline' binds neither the owning behavior specification",
        ),
        (
            "    actions: [triage-alert]\n",
            "    actions: []\n",
            "action_contract_ref 'triage-alert' is outside participant 'analyst'",
        ),
        (
            "          evidence_requirement_refs: [ticket-evidence]\n",
            "          evidence_requirement_refs: [missing-evidence]\n",
            "terminal condition 'ticket-closed' evidence_requirement_ref 'missing-evidence' does not reference",
        ),
        (
            "          evidence_requirement_refs: [queue-evidence]\n",
            "          evidence_requirement_refs: [missing-evidence]\n",
            "truncation condition 'queue-stalled' evidence_requirement_ref 'missing-evidence' does not reference",
        ),
        (
            "        evidence_requirement_refs: [reset-evidence]\n",
            "        evidence_requirement_refs: [missing-evidence]\n",
            "reset policy evidence_requirement_ref 'missing-evidence' does not reference",
        ),
    ],
)
def test_policy_references_fail_closed(old: str, new: str, expected: str) -> None:
    source = _edit(old, new)

    with pytest.raises(SDLValidationError, match=expected):
        parse_sdl(source)


def test_role_selected_participants_own_the_timeout_and_the_compiled_policy() -> None:
    source = _replace(
        _edit("    participant_refs: [analyst]\n", "    participant_role_refs: [blue]\n"),
        "subject_refs: [behavior_specifications.analyst-triage]",
        "subject_refs: [agents.analyst]",
    )

    compiled = compile_runtime_model(parse_sdl(source)).participant_episode_policies[POLICY_ADDRESS]

    assert compiled.participant_addresses == (PARTICIPANT_ADDRESS,)


_SECOND_ANALYST = "  analyst-2:\n    affiliations: [blue-team]\n    actions: [triage-alert]\n"


def _two_analyst_source(subjects: str) -> str:
    source = _replace(
        _edit("    participant_refs: [analyst]\n", "    participant_role_refs: [blue]\n"),
        "subject_refs: [behavior_specifications.analyst-triage]",
        f"subject_refs: {subjects}",
    )
    return _replace(source, "agents:\n", "agents:\n" + _SECOND_ANALYST)


def test_a_timeout_must_bind_every_selected_participant() -> None:
    bound = compile_runtime_model(parse_sdl(_two_analyst_source("[agents.analyst, agents.analyst-2]")))
    source = _two_analyst_source("[agents.analyst]")

    assert bound.participant_episode_policies[POLICY_ADDRESS].participant_addresses == (
        PARTICIPANT_ADDRESS,
        "participant.behavior.analyst-2",
    )
    with pytest.raises(
        SDLValidationError, match="binds neither the owning behavior specification nor every participant"
    ):
        parse_sdl(source)


_SECOND_POLICY = """  analyst-escalation:
    semantic_version: 1.0.0
    {selector}
    action_contract_refs: [triage-alert]
    episode_policy:
      profile: participant-episode-policy/v1
      interaction_structure:
        order_basis: decision-epoch
        action_contract_refs: [triage-alert]
"""


@pytest.mark.parametrize("selector", ["participant_refs: [analyst]", "participant_role_refs: [blue]"])
def test_one_episode_policy_governs_each_participant(selector: str) -> None:
    source = _edit(
        "behavior_specifications:\n", "behavior_specifications:\n" + _SECOND_POLICY.format(selector=selector)
    )

    with pytest.raises(
        SDLValidationError,
        match=r"Participant 'analyst' is governed by more than one episode policy "
        r"\(behavior specifications 'analyst-escalation', 'analyst-triage'\)",
    ):
        parse_sdl(source)


def test_a_policy_free_specification_may_share_the_governed_participant() -> None:
    second = _SECOND_POLICY.format(selector="participant_refs: [analyst]")
    second = second[: second.index("    episode_policy:\n")]
    model = compile_runtime_model(parse_sdl(_edit("behavior_specifications:\n", "behavior_specifications:\n" + second)))

    assert set(model.participant_episode_policies) == {POLICY_ADDRESS}


_VARIABLES = """name: dsl-120
variables:
  {name}:
    type: string
    default: {default}
    allowed_values: [{default}]
"""


@pytest.mark.parametrize(
    ("variable", "default", "old", "new"),
    [
        ("who", "analyst", "    participant_refs: [analyst]\n", "    participant_refs: ['${who}']\n"),
        (
            "contract",
            "triage-alert",
            "    action_contract_refs: [triage-alert]\n    behavior_mode",
            ("    action_contract_refs: ['${contract}']\n    behavior_mode"),
        ),
    ],
)
def test_checks_that_need_a_resolved_selection_wait_for_instantiation(
    variable: str,
    default: str,
    old: str,
    new: str,
) -> None:
    source = _replace(_edit(old, new), "name: dsl-120\n", _VARIABLES.format(name=variable, default=default))
    if variable == "who":
        source = _replace(
            source,
            "subject_refs: [behavior_specifications.analyst-triage]",
            "subject_refs: [agents.analyst]",
        )

    instantiated = instantiate_scenario(parse_sdl(source), parameters={variable: default})

    assert compile_runtime_model(instantiated).participant_episode_policies[POLICY_ADDRESS].participant_addresses == (
        PARTICIPANT_ADDRESS,
    )


def test_episode_local_reset_names_the_reset_authority() -> None:
    source = _edit(
        "participant_memory_scope: persistent_across_episodes",
        "participant_memory_scope: episode_local_reset\n        memory_reset_authority_ref: analyst-console-reset",
    )

    compiled = compile_runtime_model(parse_sdl(source)).participant_episode_policies[POLICY_ADDRESS]

    assert compiled.participant_memory_scope == "episode_local_reset"
    assert compiled.memory_reset_authority_ref == "analyst-console-reset"


def test_module_composition_rewrites_policy_refs_and_keeps_condition_ids(tmp_path: Path) -> None:
    module = textwrap.dedent(
        """
        name: dsl-120
        module:
          id: acme/analyst-episode
          version: 1.0.0
          exports:
            nodes: [siem]
            entities: [blue-team]
            propositions: [console-ready, ticket-closed, queue-stalled]
            assertions: [console-ready, ticket-closed, queue-stalled]
            time_domains: [shift-time]
            clocks: [shift-clock]
            temporal_constraints: [shift-deadline]
            evidence_requirements: [ticket-evidence, queue-evidence, shift-clock-evidence, reset-evidence]
            action_contracts: [triage-alert]
            agents: [analyst]
            behavior_specifications: [analyst-triage]
        """
    ).lstrip()
    (tmp_path / "module.yaml").write_text(_replace(_source(), "name: dsl-120\n", module), encoding="utf-8")
    root = tmp_path / "root.yaml"
    root.write_text("name: root\nimports:\n  - source: local:module.yaml\n    namespace: shared\n", encoding="utf-8")

    scenario = parse_sdl_file(root)
    policy = scenario.behavior_specifications["shared.analyst-triage"].episode_policy

    assert policy.initialization.assertion_refs == ["shared.console-ready"]
    assert policy.interaction_structure.action_contract_refs == ["shared.triage-alert"]
    assert set(policy.terminal_conditions) == {"ticket-closed", "shift-ended"}
    assert policy.terminal_conditions["ticket-closed"].assertion_refs == ["shared.ticket-closed"]
    assert policy.terminal_conditions["shift-ended"].temporal_constraint_ref == "shared.shift-deadline"
    assert policy.truncation_conditions["queue-stalled"].evidence_requirement_refs == ["shared.queue-evidence"]
    assert policy.reset_policy.evidence_requirement_refs == ["shared.reset-evidence"]
    compiled = compile_runtime_model(scenario).participant_episode_policies
    assert set(compiled) == {"participant.episode-policy.shared.analyst-triage"}


def test_variable_refs_are_revalidated_after_instantiation() -> None:
    source = _replace(
        _edit("        assertion_refs: [console-ready]\n", "        assertion_refs: ['${start_assertion}']\n"),
        "name: dsl-120\n",
        textwrap.dedent(
            """
            name: dsl-120
            variables:
              start_assertion:
                type: string
                default: console-ready
                allowed_values: [console-ready, missing-assertion]
            """
        ).lstrip(),
    )
    authored = parse_sdl(source)

    instantiated = instantiate_scenario(authored, parameters={"start_assertion": "console-ready"})
    compiled = compile_runtime_model(instantiated).participant_episode_policies[POLICY_ADDRESS]
    assert compiled.initialization_assertion_addresses == ("evaluation.assertion.console-ready",)
    with pytest.raises(SDLInstantiationError, match="missing-assertion"):
        instantiate_scenario(authored, parameters={"start_assertion": "missing-assertion"})


def test_policy_free_behavior_specifications_keep_their_existing_shape() -> None:
    scenario = parse_sdl(_policy_free_source())
    model = compile_runtime_model(scenario)

    assert "episode_policy" not in scenario.behavior_specifications["analyst-triage"].model_dump(mode="json")
    assert "episode_policy" not in model.behavior_specifications[SPEC_ADDRESS].spec
    assert model.participant_episode_policies == {}


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"terminal_reason": "interrupted", "assertion_addresses": ("evaluation.assertion.a",)}, "interrupted"),
        ({"terminal_reason": "completed", "evidence_requirement_addresses": ()}, "evidence"),
        ({"terminal_reason": "timed_out", "assertion_addresses": ("evaluation.assertion.a",)}, "temporal"),
        (
            {
                "terminal_reason": "completed",
                "assertion_addresses": ("evaluation.assertion.a",),
                "temporal_constraint_address": "time.constraint.t",
            },
            "temporal",
        ),
    ],
)
def test_compiled_conditions_reassert_the_authored_pairing(fields: dict[str, object], expected: str) -> None:
    values: dict[str, object] = {
        "condition_id": "c",
        "evidence_requirement_addresses": ("sdl.evidence-requirements.e",),
        **fields,
    }

    with pytest.raises(ValueError, match=expected):
        ParticipantEpisodeConditionRuntime(**values)


@pytest.mark.parametrize(
    ("cursor_path", "label"),
    [
        ("/behavior_specifications/analyst-triage", "episode_policy"),
        ("/behavior_specifications/analyst-triage/episode_policy/initialization/assertion_refs", "console-ready"),
        (
            "/behavior_specifications/analyst-triage/episode_policy/terminal_conditions/shift-ended/"
            "temporal_constraint_ref",
            "shift-deadline",
        ),
    ],
)
def test_language_service_offers_the_policy_surface(cursor_path: str, label: str) -> None:
    result = language_completions(_source(), cursor_path=cursor_path)

    assert result["status"] == "ok"
    assert label in {item["label"] for item in result["items"]}


@pytest.mark.parametrize(
    "contract_id",
    [
        "sdl-authoring-input-v1",
        "instantiated-scenario-v1",
        "instantiated-scenario-snapshot-v1",
        "scenario-satisfiability-evidence-v1",
    ],
)
def test_scenario_contracts_publish_the_closed_policy_shape(contract_id: str) -> None:
    definitions = schema_bundle()[contract_id]["$defs"]

    assert "episode_policy" in definitions["ParticipantBehaviorSpecification"]["properties"]
    for name in (
        "ParticipantEpisodePolicy",
        "ParticipantEpisodeInitialization",
        "ParticipantEpisodeInteractionStructure",
        "ParticipantEpisodeCompletionCondition",
        "ParticipantEpisodeTimeoutCondition",
        "ParticipantEpisodeTruncationCondition",
        "ParticipantEpisodeResetPolicy",
    ):
        assert definitions[name]["additionalProperties"] is False
    assert definitions["ParticipantEpisodePolicy"]["required"] == ["profile"]


def _published_authoring_schema() -> dict[str, object]:
    return json.loads(
        (REPO_ROOT / "contracts" / "schemas" / "sdl" / "sdl-authoring-input-v1.json").read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda policy: policy["initialization"].update(assertion_refs=["   "]),
        lambda policy: policy["reset_policy"].update(participant_memory_scope="episode_local_reset"),
        lambda policy: policy["reset_policy"].update(memory_reset_authority_ref="analyst-console-reset"),
    ],
    ids=["blank-ref", "local-reset-without-authority", "persistent-with-authority"],
)
def test_published_schema_states_the_parser_rules(mutate: object) -> None:
    payload = parse_sdl_file(VALID_FIXTURE).model_dump(mode="json", exclude_defaults=True)
    mutate(payload["behavior_specifications"]["analyst-triage"]["episode_policy"])

    assert list(Draft202012Validator(_published_authoring_schema()).iter_errors(payload))


def test_published_valid_and_invalid_policy_fixtures() -> None:
    scenario = parse_sdl_file(VALID_FIXTURE)

    Draft202012Validator(_published_authoring_schema()).validate(
        scenario.model_dump(mode="json", exclude_defaults=True)
    )
    with pytest.raises(
        SDLParseError, match=rf"{REALIZED_STATE}.*decision_epoch, initialized_at, status, terminal_reason"
    ):
        parse_sdl_file(INVALID_FIXTURE)
