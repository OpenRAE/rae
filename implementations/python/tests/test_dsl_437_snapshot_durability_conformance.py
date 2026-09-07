"""DSL-437 autonomous scheduler-state snapshot boundary tests."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from hashlib import sha256
from pathlib import Path

import pytest
from raes_conformance.conformance import _semantic_diagnostics
from raes_conformance.conformance.snapshot_semantics import _snapshot_from_envelope
from raes_contracts.contracts.time_model import TimeRuntimeStateModel
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.control_plane_store import InMemoryControlPlaneStore, LocalControlPlaneStore

POLICY_ADDRESS = "participant.autonomous-execution.green-users"
PARTICIPANT_ADDRESS = "participant.behavior.green-user"
STATE_ADDRESS = f"{POLICY_ADDRESS}.state.{PARTICIPANT_ADDRESS}"


def _rewrite_durable_snapshot(
    store_path: Path,
    mutate: Callable[[dict[str, object]], None],
    *,
    update_digest: bool = True,
) -> None:
    with closing(sqlite3.connect(store_path / "control-plane.sqlite3")) as connection, connection:
        row = connection.execute("SELECT payload FROM state WHERE key='runtime-snapshot'").fetchone()
        assert row is not None
        payload = json.loads(row[0])
        mutate(payload)
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if update_digest:
            digest = sha256(content.encode("utf-8")).hexdigest()
            connection.execute(
                "UPDATE state SET payload=?, digest=? WHERE key='runtime-snapshot'",
                (content, digest),
            )
        else:
            connection.execute(
                "UPDATE state SET payload=? WHERE key='runtime-snapshot'",
                (content,),
            )


def _state(**updates: object) -> dict[str, object]:
    state: dict[str, object] = {
        "policy_address": POLICY_ADDRESS,
        "policy_digest": "sha256:" + "4" * 64,
        "participant_address": PARTICIPANT_ADDRESS,
        "episode_id": f"{PARTICIPANT_ADDRESS}-autonomous-0",
        "participant_implementation_ref": "participant-implementation-manifests.green-worker.v1",
        "clock_address": "time.clock.scenario-clock",
        "time_segment": 0,
        "lifecycle_state": "running",
        "next_tick": 10,
        "next_action_index": 1,
        "attempted_actions": 1,
        "succeeded_actions": 1,
        "failed_actions": 0,
        "in_flight": 0,
        "last_action_instance_id": "green-user-action-1",
    }
    state.update(updates)
    return state


def _envelope(state: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "schema_version": "runtime-snapshot/v1",
        "participant_episode_results": {PARTICIPANT_ADDRESS: _episode()},
        "participant_autonomous_execution_states": {
            STATE_ADDRESS: _state() if state is None else state,
        },
        "time_model_state": _time_state().model_dump(mode="json"),
    }


def _episode() -> dict[str, object]:
    return {
        "state_schema_version": "participant-episode-state/v1",
        "participant_address": PARTICIPANT_ADDRESS,
        "episode_id": f"{PARTICIPANT_ADDRESS}-autonomous-0",
        "sequence_number": 0,
        "status": "running",
        "terminal_reason": None,
        "initialized_at": "2026-07-24T00:00:00Z",
        "updated_at": "2026-07-24T00:00:00Z",
        "terminated_at": None,
        "last_control_action": "initialize",
        "previous_episode_id": None,
    }


def _time_state(*, segment: int = 0) -> TimeRuntimeStateModel:
    coordinate = {"segment": segment, "tick": 0, "microstep": 0}
    return TimeRuntimeStateModel.model_validate(
        {
            "schema_version": "time-runtime-state/v1",
            "declaration_digest": "sha256:" + "3" * 64,
            "clocks": {
                "time.clock.scenario-clock": {
                    "clock_address": "time.clock.scenario-clock",
                    "time_domain_address": "time.domain.scenario",
                    "progression_policy_address": "time.progression-policy.scenario",
                    "authority_kind": "runtime",
                    "authority_ref": "runtime.clock",
                    "state": "running",
                    "coordinate": coordinate,
                    "sequence": 0,
                    "history": [
                        {
                            "sequence": 0,
                            "kind": "initialize",
                            "previous": None,
                            "resulting": coordinate,
                            "resulting_state": "running",
                        }
                    ],
                }
            },
        }
    )


def _snapshot(state: dict[str, object] | None = None) -> RuntimeSnapshot:
    return RuntimeSnapshot(
        participant_episode_results={PARTICIPANT_ADDRESS: _episode()},
        participant_autonomous_execution_states={STATE_ADDRESS: _state() if state is None else state},
        time_model_state=_time_state(),
    )


def test_runtime_snapshot_rejects_misaddressed_autonomous_state() -> None:
    autonomous_states = {
        f"{POLICY_ADDRESS}.state.participant.behavior.other": _state(),
    }

    with pytest.raises(ValueError, match="map key must equal"):
        RuntimeSnapshot(participant_autonomous_execution_states=autonomous_states)


def test_runtime_snapshot_rejects_unaccounted_autonomous_attempts() -> None:
    autonomous_states = {
        STATE_ADDRESS: _state(
            lifecycle_state="completed",
            attempted_actions=2,
            succeeded_actions=1,
        )
    }

    with pytest.raises(ValueError, match="attempted_actions must equal"):
        RuntimeSnapshot(participant_autonomous_execution_states=autonomous_states)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("policy_digest", "not-a-digest", "canonical sha256 digest"),
        ("time_segment", -1, "time_segment"),
    ],
)
def test_runtime_snapshot_validates_policy_identity_and_time_segment(
    field: str,
    value: object,
    message: str,
) -> None:
    autonomous_states = {STATE_ADDRESS: _state(**{field: value})}

    with pytest.raises(ValueError, match=message):
        RuntimeSnapshot(participant_autonomous_execution_states=autonomous_states)


def test_control_plane_store_round_trips_valid_autonomous_state(tmp_path: Path) -> None:
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    snapshot = _snapshot()

    store.save_snapshot(snapshot, expected_revision=store.load_snapshot_state().revision)
    loaded = store.load_snapshot()

    assert loaded.participant_autonomous_execution_states == {STATE_ADDRESS: _state()}
    assert loaded.participant_autonomous_execution_states[STATE_ADDRESS]["policy_digest"] == "sha256:" + "4" * 64
    assert loaded.participant_autonomous_execution_states[STATE_ADDRESS]["time_segment"] == 0


def test_control_plane_stores_revalidate_mutated_autonomous_state(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot.participant_autonomous_execution_states[STATE_ADDRESS] = _state(attempted_actions=2)
    memory_store = InMemoryControlPlaneStore()
    local_store = LocalControlPlaneStore(tmp_path / "control-plane")

    with pytest.raises(ValueError, match="attempted_actions must equal"):
        memory_store.save_snapshot(snapshot, expected_revision=memory_store.load_snapshot_state().revision)
    with pytest.raises(ValueError, match="attempted_actions must equal"):
        local_store.save_snapshot(snapshot, expected_revision=local_store.load_snapshot_state().revision)


def test_local_control_plane_store_rejects_invalid_durable_state(tmp_path: Path) -> None:
    store_path = tmp_path / "control-plane"
    store = LocalControlPlaneStore(store_path)
    store.save_snapshot(_snapshot(), expected_revision=store.load_snapshot_state().revision)

    def mutate(payload: dict[str, object]) -> None:
        states = payload["participant_autonomous_execution_states"]
        assert isinstance(states, dict)
        state = states[STATE_ADDRESS]
        assert isinstance(state, dict)
        state["attempted_actions"] = 2

    _rewrite_durable_snapshot(store_path, mutate)

    with pytest.raises(ValueError, match="attempted_actions must equal"):
        store.load_snapshot()


def test_local_control_plane_store_rejects_durable_clock_segment_mismatch(tmp_path: Path) -> None:
    store_path = tmp_path / "control-plane"
    store = LocalControlPlaneStore(store_path)
    store.save_snapshot(_snapshot(), expected_revision=store.load_snapshot_state().revision)

    def mutate(payload: dict[str, object]) -> None:
        time_model = payload["time_model_state"]
        assert isinstance(time_model, dict)
        clocks = time_model["clocks"]
        assert isinstance(clocks, dict)
        clock = clocks["time.clock.scenario-clock"]
        assert isinstance(clock, dict)
        coordinate = clock["coordinate"]
        assert isinstance(coordinate, dict)
        coordinate["segment"] = 1
        history = clock["history"]
        assert isinstance(history, list)
        resulting = history[-1]["resulting"]
        assert isinstance(resulting, dict)
        resulting["segment"] = 1

    _rewrite_durable_snapshot(store_path, mutate)

    with pytest.raises(ValueError, match="must match the bound shared clock segment"):
        store.load_snapshot()


def test_local_control_plane_store_rejects_corrupted_payload(tmp_path: Path) -> None:
    store_path = tmp_path / "control-plane"
    store = LocalControlPlaneStore(store_path)
    store.save_snapshot(_snapshot(), expected_revision=store.load_snapshot_state().revision)

    _rewrite_durable_snapshot(store_path, lambda payload: payload.clear(), update_digest=False)

    with pytest.raises(ValueError, match="failed its durable integrity check"):
        store.load_snapshot()


def test_conformance_conversion_preserves_autonomous_state() -> None:
    snapshot = _snapshot_from_envelope(_envelope())

    assert snapshot.participant_autonomous_execution_states == {STATE_ADDRESS: _state()}
    assert snapshot.participant_autonomous_execution_states[STATE_ADDRESS]["policy_digest"] == "sha256:" + "4" * 64
    assert snapshot.participant_autonomous_execution_states[STATE_ADDRESS]["time_segment"] == 0


def test_conformance_reports_inconsistent_terminal_autonomous_state() -> None:
    payload = _envelope(
        _state(
            lifecycle_state="completed",
            attempted_actions=2,
            succeeded_actions=1,
        )
    )

    diagnostics = _semantic_diagnostics("runtime-snapshot-v1", payload)

    assert [diagnostic.code for diagnostic in diagnostics] == ["conformance.semantic-invalid"]
    assert "attempted_actions must equal" in diagnostics[0].message


def test_durable_snapshot_rejects_clock_segment_mismatch() -> None:
    snapshot = _snapshot()
    snapshot.time_model_state = _time_state(segment=1)
    store = InMemoryControlPlaneStore()

    with pytest.raises(ValueError, match="must match the bound shared clock segment"):
        store.save_snapshot(snapshot, expected_revision=store.load_snapshot_state().revision)


def test_durable_snapshot_rejects_episode_mismatch() -> None:
    snapshot = _snapshot()
    snapshot.participant_episode_results[PARTICIPANT_ADDRESS]["episode_id"] = "wrong-episode"
    store = InMemoryControlPlaneStore()

    with pytest.raises(ValueError, match="must match the live participant episode"):
        store.save_snapshot(snapshot, expected_revision=store.load_snapshot_state().revision)
