"""ACT-623 participant episode structure as a first-class participant concern."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from raes._errors import SDLParseError
from raes.parser import parse_sdl, parse_sdl_file
from raes_backend_stubs.stubs import create_stub_target
from raes_conformance.conformance import participant_episode_structure_conformance_diagnostics
from raes_contracts.participant_episode import ParticipantEpisodeTerminalReason
from raes_processor.compiler import compile_runtime_model
from raes_runtime.control_plane import RuntimeControlPlane

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "contracts" / "fixtures" / "sdl" / "participant-episode-policy-v1"
ANALYST_FIXTURE = FIXTURE_ROOT / "valid" / "analyst-shift-episode.yaml"
STANDALONE_FIXTURE = FIXTURE_ROOT / "valid" / "standalone-episode-structure.yaml"
AUTONOMOUS_PROFILE_FIXTURE = FIXTURE_ROOT / "invalid" / "autonomous-profile-episode-structure.yaml"
MIXED_CONTROL_FIXTURE = (
    REPO_ROOT / "contracts" / "fixtures" / "sdl" / "mixed-control-v1" / "valid" / ("mixed-control-participant.yaml")
)
ANALYST = "participant.behavior.analyst"
REPLAYER = "participant.behavior.replayer"
CONFORMANCE_CODE = "conformance.participant-episode-structure-invalid"
MIXED_CONTROL_EPISODE_DECLARATIONS = """propositions:
  web-ready:
    description: The web node is reachable before a red episode starts.
    subjects: [nodes.web]
    basis: declared_state
    predicate:
      kind: boolean
      property: web-reachable
      semantic_ref: urn:raes:observable:web-reachable
      expected: true
assertions:
  web-ready:
    proposition: web-ready
    role: precondition
agents:
"""
MIXED_CONTROL_EPISODE_POLICY = """    episode_policy:
      profile: participant-episode-policy/v1
      initialization:
        assertion_refs: [web-ready]
"""


def _analyst_source() -> str:
    return ANALYST_FIXTURE.read_text(encoding="utf-8")


def _replace(source: str, old: str, new: str) -> str:
    assert old in source
    return source.replace(old, new, 1)


def _mixed_control_source() -> str:
    source = _replace(
        MIXED_CONTROL_FIXTURE.read_text(encoding="utf-8"), "agents:\n", MIXED_CONTROL_EPISODE_DECLARATIONS
    )
    return source.rstrip("\n") + "\n" + MIXED_CONTROL_EPISODE_POLICY


@pytest.mark.parametrize(
    ("source", "spec_name", "participant"),
    [
        *(
            (
                _replace(_analyst_source(), "behavior_mode: human-supervised", f"behavior_mode: {mode}"),
                "analyst-triage",
                ANALYST,
            )
            for mode in (
                "autonomous",
                "human-control-proxy",
                "human-supervised",
                "policy-directed",
                "replayed",
                "scripted",
            )
        ),
        (_mixed_control_source(), "controlled-red", "participant.behavior.red-agent"),
        (STANDALONE_FIXTURE.read_text(encoding="utf-8"), "replay-episodes", REPLAYER),
    ],
    ids=[
        "autonomous",
        "human-control-proxy",
        "human-supervised",
        "policy-directed",
        "replayed",
        "scripted",
        "mixed-control",
        "no-behavior-mode",
    ],
)
def test_episode_structure_is_a_member_of_every_participant_kind_aggregate(
    source: str,
    spec_name: str,
    participant: str,
) -> None:
    model = compile_runtime_model(parse_sdl(source))
    aggregate = model.behavior_specifications[f"participant.behavior-specification.{spec_name}"]

    assert aggregate.episode_policy_address == f"participant.episode-policy.{spec_name}"
    assert model.participant_episode_policies[aggregate.episode_policy_address].participant_addresses == (participant,)


def test_episode_structure_alone_satisfies_the_behavior_aggregate() -> None:
    scenario = parse_sdl_file(STANDALONE_FIXTURE)
    specification = scenario.behavior_specifications["replay-episodes"]

    assert not specification.action_contract_refs
    assert specification.behavior_mode is None
    assert specification.episode_policy is not None


def test_policy_free_aggregates_name_no_episode_structure() -> None:
    source = _analyst_source()
    model = compile_runtime_model(parse_sdl(source[: source.index("    episode_policy:\n")]))

    assert (
        model.behavior_specifications["participant.behavior-specification.analyst-triage"].episode_policy_address == ""
    )


def test_the_autonomous_profile_cannot_carry_episode_structure() -> None:
    with pytest.raises(
        SDLParseError, match="autonomous_execution/ParticipantAutonomousExecutionPolicyV1/episode_policy"
    ):
        parse_sdl_file(AUTONOMOUS_PROFILE_FIXTURE)


def _history(control_plane: RuntimeControlPlane) -> dict[str, object]:
    return control_plane.get_snapshot().snapshot.participant_episode_history


def _messages(diagnostics: tuple[object, ...]) -> list[str]:
    assert {diagnostic.code for diagnostic in diagnostics} <= {CONFORMANCE_CODE}
    return [diagnostic.message for diagnostic in diagnostics]


def test_recorded_episodes_conform_to_their_authored_structure() -> None:
    policies = compile_runtime_model(parse_sdl_file(ANALYST_FIXTURE)).participant_episode_policies
    control_plane = RuntimeControlPlane(create_stub_target())
    control_plane.initialize_participant_episode(ANALYST)
    control_plane.terminate_participant_episode(ANALYST, terminal_reason=ParticipantEpisodeTerminalReason.COMPLETED)
    control_plane.restart_participant_episode(ANALYST)
    control_plane.reset_participant_episode(ANALYST)
    control_plane.terminate_participant_episode(ANALYST, terminal_reason=ParticipantEpisodeTerminalReason.TRUNCATED)
    control_plane.restart_participant_episode(ANALYST)
    control_plane.terminate_participant_episode(ANALYST, terminal_reason=ParticipantEpisodeTerminalReason.INTERRUPTED)

    history = _history(control_plane)[ANALYST]
    assert [event["event_type"] for event in history][-1] == "episode_interrupted"
    assert participant_episode_structure_conformance_diagnostics(policies, _history(control_plane)) == ()


def test_recorded_episodes_that_contradict_their_structure_are_reported() -> None:
    policies = compile_runtime_model(parse_sdl_file(STANDALONE_FIXTURE)).participant_episode_policies
    control_plane = RuntimeControlPlane(create_stub_target())
    control_plane.initialize_participant_episode(REPLAYER)
    control_plane.reset_participant_episode(REPLAYER)
    control_plane.terminate_participant_episode(REPLAYER, terminal_reason=ParticipantEpisodeTerminalReason.TIMED_OUT)
    control_plane.restart_participant_episode(REPLAYER)
    control_plane.terminate_participant_episode(REPLAYER, terminal_reason=ParticipantEpisodeTerminalReason.COMPLETED)
    control_plane.initialize_participant_episode("participant.behavior.observer")
    control_plane.terminate_participant_episode(
        "participant.behavior.observer",
        terminal_reason=ParticipantEpisodeTerminalReason.TRUNCATED,
    )

    history = _history(control_plane)
    diagnostics = participant_episode_structure_conformance_diagnostics(policies, history)

    assert _messages(diagnostics) == [
        "control action 'restart' is not admitted by the reset policy of 'participant.episode-policy.replay-episodes'",
        "terminal reason 'completed' has no authored condition in 'participant.episode-policy.replay-episodes'; "
        "only an interruption may end a governed episode without one",
    ]
    event_types = [event["event_type"] for event in history[REPLAYER]]
    assert [diagnostic.address for diagnostic in diagnostics] == [
        f"runtime.snapshot.participant-episode-history.{REPLAYER}[{event_types.index(event_type)}]"
        for event_type in ("episode_restarted", "episode_completed")
    ]


def test_conformance_refuses_a_participant_with_two_compiled_structures() -> None:
    policies = compile_runtime_model(parse_sdl_file(STANDALONE_FIXTURE)).participant_episode_policies
    original = policies["participant.episode-policy.replay-episodes"]
    duplicate = replace(original, address="participant.episode-policy.replay-copy", name="replay-copy")

    diagnostics = participant_episode_structure_conformance_diagnostics(
        {original.address: original, duplicate.address: duplicate},
        {},
    )

    assert _messages(diagnostics) == [
        "participant is governed by more than one episode policy: "
        "participant.episode-policy.replay-copy, participant.episode-policy.replay-episodes"
    ]
