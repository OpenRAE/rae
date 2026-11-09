"""The public snapshot projection preserves original supported evidence."""

from raes_contracts.runtime_state import RuntimeSnapshot, RuntimeSnapshotEnvelope
from raes_runtime.snapshot_contract import runtime_snapshot_contract_model, runtime_snapshot_from_contract


def test_snapshot_handoff_preserves_episode_closure_evidence():
    records = {"participant.agent-a": [{"closure_id": "closed-attempt", "evidence_refs": ["evidence:original"]}]}
    original = RuntimeSnapshot(participant_episode_closure_records=records)
    carrier = runtime_snapshot_contract_model(RuntimeSnapshotEnvelope(snapshot=original), include_trial_history=True)
    reconstructed = runtime_snapshot_from_contract(carrier)
    assert reconstructed.participant_episode_closure_records == records


def test_private_outcome_history_is_retained_only_for_the_explicit_scoped_handoff():
    from test_act_618_outcome_control import PARTICIPANT_ADDRESS, control_plane, identity, request

    with control_plane() as runtime:
        runtime.record_participant_outcome(request(), identity=identity())
        envelope = RuntimeSnapshotEnvelope(snapshot=runtime.snapshot)
        public = runtime_snapshot_contract_model(envelope)
        scoped = runtime_snapshot_contract_model(envelope, include_trial_history=True)
        assert public.participant_outcome_history == {}
        assert scoped.participant_outcome_history[PARTICIPANT_ADDRESS]
        restored = runtime_snapshot_from_contract(scoped)
        assert restored.participant_outcome_history == runtime.snapshot.participant_outcome_history
