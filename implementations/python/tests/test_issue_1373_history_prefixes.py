"""Immutable control prefixes preserve validation and isolate proposed appends."""

from copy import deepcopy

import pytest
from participant_control_contract_fixtures import evaluation_payload
from raes_contracts.immutable_history import DEFAULT_HISTORY_POLICY, HistoryMap
from raes_contracts.participant_control_evaluation_history import (
    iter_participant_control_evaluation_snapshot_violations,
)
from raes_contracts.participant_control_history import iter_participant_control_history_snapshot_violations
from raes_contracts.participant_crossing_history import iter_participant_crossing_history_snapshot_violations
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.snapshot_histories import history_policy, is_sealed_history, seal_history


def evaluation(identity="evaluation-1"):
    payload = evaluation_payload()
    payload["evaluation_id"] = identity
    return payload


def test_validated_prefix_is_shared_and_new_suffix_is_isolated():
    from raes_contracts.snapshot_histories import seal_history

    payload = evaluation()
    participant = payload["request"]["context"]["participant_address"]
    history = seal_history("participant_control_evaluation_history", {participant: [payload]})
    first = RuntimeSnapshot(participant_control_evaluation_history=history)
    second = first.with_entries({})
    assert second.participant_control_evaluation_history is history
    extended = history.append(participant, [evaluation("evaluation-2")])
    assert len(history[participant]) == 1
    assert len(extended[participant]) == 2
    assert extended[participant].prefix_digest(1) == history[participant].prefix_digest(1)
    assert deepcopy(history) is history
    payload["evaluation_id"] = "changed-original-input"
    assert history[participant][0]["evaluation_id"] == "evaluation-1"
    detached = history[participant][0]
    detached["request"]["context"]["attempt"] = 999
    assert history[participant][0]["request"]["context"]["attempt"] != 999
    with pytest.raises(TypeError):
        dict.__setitem__(history, participant, [])
    with pytest.raises(TypeError):
        history[participant] = []


def test_duplicate_or_invalid_suffix_cannot_change_a_valid_prefix():
    from raes_contracts.snapshot_histories import seal_history

    payload = evaluation()
    participant = payload["request"]["context"]["participant_address"]
    history = seal_history("participant_control_evaluation_history", {participant: [payload]})
    with pytest.raises(ValueError, match="unique"):
        history.append(participant, [payload])
    invalid = evaluation("evaluation-2")
    invalid["request"]["context"]["attempt"] = True
    with pytest.raises(ValueError):
        history.append(participant, [invalid])
    assert len(history[participant]) == 1


def test_replaced_mutable_history_is_validated_again():
    payload = evaluation()
    participant = payload["request"]["context"]["participant_address"]
    snapshot = RuntimeSnapshot(participant_control_evaluation_history={participant: [payload]})
    invalid = evaluation("evaluation-2")
    invalid["schema_version"] = "unknown"
    with pytest.raises(ValueError):
        snapshot.with_entries({}, participant_control_evaluation_history={participant: [invalid]})


@pytest.mark.parametrize(
    ("field", "violations"),
    [
        ("participant_control_evaluation_history", iter_participant_control_evaluation_snapshot_violations),
        ("participant_control_history", iter_participant_control_history_snapshot_violations),
        ("participant_crossing_history", iter_participant_crossing_history_snapshot_violations),
    ],
)
def test_a_history_map_with_a_caller_selected_policy_is_not_trusted(field, violations):
    forged = HistoryMap(field, {"participant-a": [{"schema_version": "unknown"}]}, DEFAULT_HISTORY_POLICY)

    assert forged.shape_valid
    assert not is_sealed_history(field, forged)
    assert list(violations(forged))


def test_sealing_validates_a_history_map_with_a_caller_selected_policy_again():
    field = "participant_crossing_history"
    forged = HistoryMap(field, {"participant-a": [{"schema_version": "unknown"}]}, DEFAULT_HISTORY_POLICY)

    sealed = seal_history(field, forged)

    assert sealed is not forged
    assert sealed.policy is history_policy(field)
    assert not sealed.shape_valid
    with pytest.raises(ValueError):
        seal_history(
            "participant_control_evaluation_history",
            HistoryMap("participant_control_evaluation_history", forged, DEFAULT_HISTORY_POLICY),
        )


def test_portable_export_is_plain_json_and_cannot_mutate_the_retained_history():
    from raes_runtime.control_plane_store_snapshots import _snapshot_payload

    payload = evaluation()
    participant = payload["request"]["context"]["participant_address"]
    snapshot = RuntimeSnapshot(participant_control_evaluation_history={participant: [payload]})
    exported = _snapshot_payload(snapshot)
    exported["participant_control_evaluation_history"][participant][0]["evaluation_id"] = "changed-export"
    assert snapshot.participant_control_evaluation_history[participant][0]["evaluation_id"] == "evaluation-1"


def test_append_work_does_not_read_the_retained_prefix(monkeypatch):
    from raes_contracts.immutable_history import EventHistory
    from raes_contracts.snapshot_histories import seal_history

    history = seal_history("evaluation_history", {"run": [{"number": n} for n in range(1000)]})

    def forbidden_iteration(_):
        raise AssertionError("append visited the retained prefix")

    monkeypatch.setattr(EventHistory, "__iter__", forbidden_iteration)
    extended = history.append("run", [{"number": 1000}])
    assert len(extended["run"]) == 1001
    assert extended["run"][-1] == {"number": 1000}


@pytest.mark.parametrize(
    "limit,value",
    [("max_nodes", 8), ("max_depth", 2), ("max_members", 2), ("max_scalar_bytes", 8), ("max_total_scalar_bytes", 30)],
)
def test_cached_value_costs_preserve_the_portable_limits(limit, value):
    from raes_contracts.realization_structure import RealizationConstraintLimits, validate_realization_value
    from raes_contracts.snapshot_histories import seal_history

    plain = {"run": [{"nested": {"value": "a long retained value"}} for _ in range(3)]}
    sealed = seal_history("evaluation_history", plain)
    limits = RealizationConstraintLimits(**{limit: value})
    mutable_result = validate_realization_value(plain, limits=limits, python_carriers=True)
    sealed_result = validate_realization_value(sealed, limits=limits, python_carriers=True)
    assert sealed_result == mutable_result
    assert not sealed_result.conformant
