"""The modular evaluation history is a first-class append-only snapshot carrier.

Authority lives in the runtime snapshot the ADR-104 store commits, never in
metadata, audit details, an operation result payload, or a second journal.
"""

import pytest
from participant_control_contract_fixtures import evaluation_payload
from raes_contracts.runtime_state import RuntimeSnapshot

PARTICIPANT = "participants.student"


def _evaluation(**changes: object) -> dict:
    return {**evaluation_payload(), **changes}


def test_snapshot_carries_participant_control_evaluation_history():
    snapshot = RuntimeSnapshot(participant_control_evaluation_history={PARTICIPANT: [_evaluation()]})
    assert snapshot.participant_control_evaluation_history[PARTICIPANT][0]["evaluation_id"] == "evaluation-1"


def test_carrier_is_runtime_owned_not_backend_writable():
    from raes_runtime.backend_snapshot_contracts import SNAPSHOT_CARRIER_OWNERS

    assert SNAPSHOT_CARRIER_OWNERS["participant_control_evaluation_history"] == "runtime"


def test_with_entries_accepts_and_preserves_the_new_carrier():
    snapshot = RuntimeSnapshot(participant_control_evaluation_history={PARTICIPANT: [_evaluation()]})
    extended = snapshot.with_entries(
        dict(snapshot.entries),
        participant_control_evaluation_history={
            PARTICIPANT: [
                *snapshot.participant_control_evaluation_history[PARTICIPANT],
                _evaluation(evaluation_id="evaluation-2"),
            ]
        },
    )
    assert len(extended.participant_control_evaluation_history[PARTICIPANT]) == 2
    untouched = snapshot.with_entries(dict(snapshot.entries))
    assert untouched.participant_control_evaluation_history == snapshot.participant_control_evaluation_history


def test_history_key_must_equal_the_embedded_participant_address():
    with pytest.raises(ValueError, match="participant control evaluation"):
        RuntimeSnapshot(participant_control_evaluation_history={"participants.other": [_evaluation()]})


def test_history_rejects_a_record_that_is_not_a_published_evaluation():
    with pytest.raises(ValueError, match="participant control evaluation"):
        RuntimeSnapshot(participant_control_evaluation_history={PARTICIPANT: [{"evaluation_id": "broken"}]})


def test_history_rejects_a_duplicate_evaluation_identity():
    with pytest.raises(ValueError, match="participant control evaluation"):
        RuntimeSnapshot(participant_control_evaluation_history={PARTICIPANT: [_evaluation(), _evaluation()]})


def test_history_head_resolves_for_the_expected_state_cut():
    from raes_runtime.control_plane_store_history import participant_history_head

    snapshot = RuntimeSnapshot(participant_control_evaluation_history={PARTICIPANT: [_evaluation()]})
    head = participant_history_head(snapshot, f"participant_control_evaluation_history:{PARTICIPANT}")
    assert head == "evaluation-1"


def test_expected_history_heads_bind_the_evaluation_carrier():
    from raes_runtime.participant_crossing_state_cut import expected_participant_history_heads

    snapshot = RuntimeSnapshot(participant_control_evaluation_history={PARTICIPANT: [_evaluation()]})
    heads = expected_participant_history_heads(snapshot, PARTICIPANT)
    assert heads[f"participant_control_evaluation_history:{PARTICIPANT}"] == "evaluation-1"


def test_store_round_trip_preserves_the_exact_history(tmp_path):
    from raes_runtime.control_plane_store_local import LocalControlPlaneStore
    from raes_runtime.control_plane_store_snapshots import _snapshot_from_payload, _snapshot_payload

    snapshot = RuntimeSnapshot(participant_control_evaluation_history={PARTICIPANT: [_evaluation()]})
    restored = _snapshot_from_payload(_snapshot_payload(snapshot))
    assert restored.participant_control_evaluation_history == snapshot.participant_control_evaluation_history
    assert LocalControlPlaneStore is not None


@pytest.mark.parametrize("length", [16, 200, 224])
def test_api_424_head_references_stay_inside_the_control_ref_bound(length: int):
    """A long admitted participant coordinate must still yield valid ControlRefs."""

    from pydantic import TypeAdapter
    from raes_contracts.contracts.participant_control_coordinates import ControlRef
    from raes_runtime.participant_crossing_state_cut import control_history_head_refs

    address = "participants." + "a" * (length - len("participants."))
    refs = control_history_head_refs(RuntimeSnapshot(), address)

    adapter = TypeAdapter(ControlRef)
    for ref in refs:
        assert adapter.validate_python(ref) == ref
    assert len(refs) == len(set(refs))


def test_api_424_head_references_change_with_the_head_they_name():
    from raes_runtime.participant_crossing_state_cut import control_history_head_refs

    empty = control_history_head_refs(RuntimeSnapshot(), PARTICIPANT)
    populated = control_history_head_refs(
        RuntimeSnapshot(participant_control_evaluation_history={PARTICIPANT: [_evaluation()]}),
        PARTICIPANT,
    )
    assert empty != populated
    assert control_history_head_refs(RuntimeSnapshot(), "participants.other") != empty
