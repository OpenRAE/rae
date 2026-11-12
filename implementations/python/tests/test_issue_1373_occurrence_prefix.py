"""Retained API-409 state follows the same state machine as complete replay."""

from mixed_control_v2_support import History
from raes_contracts.contracts.participant_control_occurrence_v2_validation import fold_participant_control_episode_v2


def test_occurrence_prefix_matches_complete_fold_after_acceptance_and_refusal():
    from raes_contracts.contracts.participant_control_episode_prefix import ControlEpisodePrefix

    history = History()
    prefix = ControlEpisodePrefix(history.projection)
    for edge in ("take", "return", "take"):
        record = history.accept(edge)
        prefix = prefix.append([record])
        assert prefix.state == fold_participant_control_episode_v2(history.records, policy=history.projection).state
    rejected = history.reject("take", "stale-state")
    prefix = prefix.append([rejected])
    assert prefix.state == fold_participant_control_episode_v2(history.records, policy=history.projection).state
    assert prefix.state.state_revision == 3


def test_proposed_occurrence_does_not_change_the_prefix():
    from raes_contracts.contracts.participant_control_episode_prefix import ControlEpisodePrefix

    history = History()
    prefix = ControlEpisodePrefix(history.projection)
    candidate = history.candidate("take")
    trial = prefix.trial([candidate])
    assert trial.violation is None
    assert trial.state.state_revision == 1
    assert prefix.state.state_revision == 0
