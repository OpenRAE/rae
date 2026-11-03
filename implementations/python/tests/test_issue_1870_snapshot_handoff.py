"""The public snapshot projection preserves original supported evidence."""

from raes_contracts.runtime_state import RuntimeSnapshot, RuntimeSnapshotEnvelope
from raes_runtime.snapshot_contract import runtime_snapshot_contract_model, runtime_snapshot_from_contract


def test_snapshot_handoff_preserves_episode_closure_evidence():
    records = {"participant.agent-a": [{"closure_id": "closed-attempt", "evidence_refs": ["evidence:original"]}]}
    original = RuntimeSnapshot(participant_episode_closure_records=records)
    carrier = runtime_snapshot_contract_model(RuntimeSnapshotEnvelope(snapshot=original))
    reconstructed = runtime_snapshot_from_contract(carrier)
    assert reconstructed.participant_episode_closure_records == records
