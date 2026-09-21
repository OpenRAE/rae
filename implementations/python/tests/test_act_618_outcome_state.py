"""Local outcome production, replay, evidence conflict and episode boundaries."""

from copy import deepcopy

import pytest
import yaml
from raes.parser import parse_sdl
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.compiler import compile_runtime_model
from test_act_618_outcome_definition import local_scenario
from test_sem_215_participant_outcome_interpretation import (
    EPISODE_ID,
    PARTICIPANT_ADDRESS,
    RULE_ADDRESS,
    T0,
    ParticipantActionResultStatus,
    _history_payloads,
)


def rule():
    return compile_runtime_model(parse_sdl(yaml.safe_dump(local_scenario()))).outcome_interpretation_rules[RULE_ADDRESS]


def snapshot(*, effect_class="evidence_effect", effects=True):
    from raes_backend_protocols.participant_runtime_base import BaseParticipantRuntime
    from raes_contracts.participant_episode import ParticipantEpisodeInitializeRequest

    events = _history_payloads(status=ParticipantActionResultStatus.SUCCEEDED)
    events[-1]["outcome_interpretations"] = []
    events[-1]["action_result"]["effects"] = events[-1]["action_result"]["effects"][:1] if effects else []
    if effects:
        events[-1]["action_result"]["effects"][0]["effect_class"] = effect_class
    initial = (
        BaseParticipantRuntime()
        .initialize(
            ParticipantEpisodeInitializeRequest(participant_address=PARTICIPANT_ADDRESS, episode_id=EPISODE_ID),
            RuntimeSnapshot(),
        )
        .snapshot
    )
    return initial.with_entries(
        {},
        participant_behavior_history={PARTICIPANT_ADDRESS: events},
    )


def produce(state, **kwargs):
    from raes_runtime.participant_outcome_state import ParticipantOutcomeUpdateRequest, produce_participant_outcome

    fields = dict(
        participant_address=PARTICIPANT_ADDRESS,
        episode_id=EPISODE_ID,
        outcome_id="local-task",
        event_id="report-1",
        expected_revision=0,
        rule_address=RULE_ADDRESS,
        expected_snapshot_revision=0,
    )
    return produce_participant_outcome(
        state,
        rule(),
        ParticipantOutcomeUpdateRequest(**(fields | kwargs)),
        timestamp=T0,
        actor_ref="operator",
        authorization_scope="runtime:control",
    )


def test_actual_effect_produces_local_attainment_without_downstream_result():
    report = produce(snapshot())
    assert report.category == "task_completion"
    assert report.attainment == "attained"
    assert report.knowledge == "supported"
    assert report.state_relationships == []


def test_action_success_does_not_establish_local_attainment():
    report = produce(snapshot(effects=False))
    assert report.attainment == "undetermined"
    assert report.knowledge == "unknown"


def test_conflicting_effect_evidence_is_retained():
    state = snapshot()
    other = deepcopy(state.participant_behavior_history[PARTICIPANT_ADDRESS])
    for event in other:
        event["action_instance_id"] = "scan-0002"
    other[-1]["action_result"]["action_instance_id"] = "scan-0002"
    other[-1]["action_result"]["observation_point"] = "observation:2"
    other[-1]["action_result"]["effects"][0]["effect_class"] = "no_effect"
    state.participant_behavior_history[PARTICIPANT_ADDRESS].extend(other)
    report = produce(state)
    assert report.attainment == "undetermined"
    assert report.knowledge == "conflicting"
    assert len(report.observation_refs) == 2


def test_wrong_episode_is_rejected():
    state = snapshot()
    state.participant_episode_results[PARTICIPANT_ADDRESS]["episode_id"] = "episode-2"
    with pytest.raises(ValueError, match="episode"):
        produce(state)


def test_wrong_nested_participant_is_rejected_without_echoing_evidence():
    state = snapshot()
    state.participant_behavior_history[PARTICIPANT_ADDRESS][-1]["action_result"]["participant_address"] = (
        "private-secret"
    )
    with pytest.raises(ValueError, match="binding") as error:
        produce(state)
    assert "private-secret" not in str(error.value)


def recorded_snapshot():
    state = snapshot()
    report = produce(state)
    return state.with_entries({}, participant_outcome_history={PARTICIPANT_ADDRESS: [report.model_dump(mode="json")]})


def test_outcome_history_survives_snapshot_copy_and_store_codec():
    from raes_runtime.control_plane_store_snapshots import _snapshot_from_payload, _snapshot_payload

    state = recorded_snapshot()
    restored = _snapshot_from_payload(_snapshot_payload(state))
    assert restored.participant_outcome_history == state.participant_outcome_history
    assert restored.with_entries({}).participant_outcome_history == state.participant_outcome_history


def test_replay_rejects_tampered_attainment():
    state = recorded_snapshot()
    history = deepcopy(state.participant_outcome_history)
    history[PARTICIPANT_ADDRESS][0]["attainment"] = "not_attained"
    with pytest.raises(ValueError, match="disagrees"):
        state.with_entries({}, participant_outcome_history=history)


def test_current_projection_becomes_absent_on_reset_and_preserves_history():
    from raes_runtime.participant_outcome_state import current_participant_outcome

    state = recorded_snapshot()
    assert current_participant_outcome(state, PARTICIPANT_ADDRESS, "local-task")[1] == "current"
    state.participant_episode_results[PARTICIPANT_ADDRESS]["episode_id"] = "episode-2"
    assert current_participant_outcome(state, PARTICIPANT_ADDRESS, "local-task") == (None, "absent")
    assert len(state.participant_outcome_history[PARTICIPANT_ADDRESS]) == 1


def test_stale_predecessor_cannot_overwrite_current_report():
    state = recorded_snapshot()
    with pytest.raises(ValueError, match="stale"):
        produce(state)


def test_new_observation_cut_makes_previous_report_stale():
    from raes_runtime.participant_outcome_state import current_participant_outcome

    state = recorded_snapshot()
    event = deepcopy(state.participant_behavior_history[PARTICIPANT_ADDRESS][0])
    event["action_instance_id"] = "scan-0002"
    state.participant_behavior_history[PARTICIPANT_ADDRESS].append(event)
    assert current_participant_outcome(state, PARTICIPANT_ADDRESS, "local-task")[1] == "stale"


def test_explicit_correction_appends_without_rewriting_prior_report():
    state = recorded_snapshot()
    previous = deepcopy(state.participant_outcome_history)
    excluded = [previous[PARTICIPANT_ADDRESS][0]["observation_refs"][0]["observation_point"]]
    report = produce(
        state,
        event_id="report-2",
        expected_revision=1,
        excluded_observation_refs=excluded,
        correction_basis="provenance:retracted-capture",
    )
    assert report.knowledge == "unknown"
    assert report.predecessor_event_ref == "report-1"
    assert state.participant_outcome_history == previous


@pytest.mark.parametrize(
    "effect_class,attainment,knowledge",
    [
        ("no_effect", "not_attained", "supported"),
        ("unknown_effect", "undetermined", "unknown"),
    ],
)
def test_negative_and_unknown_evidence_have_distinct_meanings(effect_class, attainment, knowledge):
    report = produce(snapshot(effect_class=effect_class))
    assert (report.attainment, report.knowledge) == (attainment, knowledge)


def test_wire_roundtrip_replays_identical_history_with_normalized_defaults():
    from raes_contracts.contracts import RuntimeSnapshotEnvelopeModel
    from raes_runtime.control_plane_store_snapshots import _snapshot_from_payload, _snapshot_payload

    state = recorded_snapshot()
    wire = RuntimeSnapshotEnvelopeModel.model_validate(_snapshot_payload(state))
    restored = _snapshot_from_payload(wire.model_dump(mode="json"))
    assert restored.participant_outcome_history == state.participant_outcome_history


def test_backend_history_transition_cannot_erase_local_outcomes():
    from raes_runtime.participant_result_contracts import participant_runtime_history_transition_diagnostics

    state = recorded_snapshot()
    following = state.with_entries({}, participant_outcome_history={})
    diagnostics = participant_runtime_history_transition_diagnostics(state, following)
    assert any("outcome" in diagnostic.message for diagnostic in diagnostics)


def test_mutated_snapshot_report_is_rejected_at_backend_boundary():
    from raes_runtime.participant_result_contracts import participant_runtime_state_contract_diagnostics

    state = recorded_snapshot()
    state.participant_outcome_history[PARTICIPANT_ADDRESS][0]["attainment"] = "not_attained"
    diagnostics = participant_runtime_state_contract_diagnostics(state)
    assert any("outcome" in diagnostic.message for diagnostic in diagnostics)


def test_partial_attainment_is_separate_from_unknown_knowledge():
    from raes_runtime.participant_outcome_state import ParticipantOutcomeUpdateRequest, produce_participant_outcome

    scenario = local_scenario()
    definition = scenario["outcome_interpretation_rules"]["scan-evidence-objective"]["local_outcome"]
    definition["criteria"].append(
        {"criterion_id": "alert", "source_id": "local-action", "effect_id": "detection-alert"}
    )
    compiled = compile_runtime_model(parse_sdl(yaml.safe_dump(scenario))).outcome_interpretation_rules[RULE_ADDRESS]
    report = produce_participant_outcome(
        snapshot(),
        compiled,
        ParticipantOutcomeUpdateRequest(
            participant_address=PARTICIPANT_ADDRESS,
            episode_id=EPISODE_ID,
            outcome_id="local-task",
            event_id="report-1",
            expected_revision=0,
            rule_address=RULE_ADDRESS,
            expected_snapshot_revision=0,
        ),
        timestamp=T0,
        actor_ref="operator",
        authorization_scope="role:operator",
    )
    assert (report.attainment, report.knowledge) == ("partial", "unknown")


def test_withheld_action_does_not_disclose_an_attained_outcome():
    state = snapshot()
    state.participant_behavior_history[PARTICIPANT_ADDRESS][-1]["action_result"]["status"] = "withheld"
    report = produce(state)
    assert (report.attainment, report.knowledge, report.evidence_refs) == ("undetermined", "withheld", [])


def test_live_episode_map_key_cannot_hide_a_different_participant():
    state = snapshot()
    state.participant_episode_results[PARTICIPANT_ADDRESS]["participant_address"] = "participant.behavior.other"
    with pytest.raises(ValueError, match="binding"):
        produce(state)


def test_v1_decoder_preserves_historical_record_without_synthetic_local_state():
    import json
    from pathlib import Path

    from raes_contracts.contracts.participant_outcomes import decode_participant_outcome_report

    root = Path(__file__).resolve().parents[3]
    payload = json.loads(
        (
            root
            / "contracts/fixtures/participant-runtime/participant-outcome-report-v1/valid/exfiltration-outcome.json"
        ).read_text()
    )
    decoded = decode_participant_outcome_report(payload)
    assert decoded.model_dump(mode="json") == payload
    assert not hasattr(decoded, "attainment")
    with pytest.raises(ValueError, match="unsupported"):
        decode_participant_outcome_report(payload | {"schema_version": "9.0.0"})


def test_conformance_snapshot_projection_preserves_sibling_control_history():
    from raes_conformance.conformance.snapshot_semantics import _snapshot_from_envelope
    from raes_runtime.control_plane_store_snapshots import _snapshot_payload
    from test_run_310_supervisory_lifecycle import _control_event

    state = recorded_snapshot()
    state.participant_control_history[PARTICIPANT_ADDRESS] = [_control_event("control-1")]
    restored = _snapshot_from_envelope(_snapshot_payload(state))
    assert restored.participant_control_history[PARTICIPANT_ADDRESS][0]["event_id"] == "control-1"
    assert restored.participant_outcome_history == state.participant_outcome_history


def test_real_episode_reset_preserves_reports_without_carrying_attainment():
    from raes_backend_protocols.participant_runtime_base import BaseParticipantRuntime
    from raes_contracts.participant_episode import ParticipantEpisodeResetRequest
    from raes_runtime.participant_outcome_state import current_participant_outcome

    state = recorded_snapshot()
    result = BaseParticipantRuntime().reset(
        ParticipantEpisodeResetRequest(
            participant_address=PARTICIPANT_ADDRESS, episode_id="episode-2", reason="new trial"
        ),
        state,
    )
    assert result.success
    assert result.snapshot.participant_outcome_history == state.participant_outcome_history
    assert current_participant_outcome(result.snapshot, PARTICIPANT_ADDRESS, "local-task") == (None, "absent")
