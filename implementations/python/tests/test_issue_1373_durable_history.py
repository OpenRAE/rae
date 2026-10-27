"""SQLite appends retain atomic history without re-encoding its old prefix."""

import json
import sqlite3

import pytest
from participant_control_contract_fixtures import evaluation_payload
from raes_contracts.immutable_history import EventHistory, append_history
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.control_plane_store import LocalControlPlaneStore


def test_local_append_does_not_visit_old_history_and_reopens_exactly(tmp_path, monkeypatch):
    directory = tmp_path / "ledger"
    store = LocalControlPlaneStore(directory)
    lease = store.admit_runtime(target_scope="target:test", run_scope="run:test")
    payload = evaluation_payload()
    participant = payload["request"]["context"]["participant_address"]
    snapshot = RuntimeSnapshot(participant_control_evaluation_history={participant: [payload]})
    first = store.save_snapshot(snapshot, expected_revision=0)
    second_payload = {**payload, "evaluation_id": "evaluation-next"}
    candidate = snapshot.with_entries(
        {},
        participant_control_evaluation_history=append_history(
            snapshot, "participant_control_evaluation_history", participant, [second_payload]
        ),
    )

    def prefix_read(_):
        raise AssertionError("durable append visited old immutable history")

    with monkeypatch.context() as guarded:
        guarded.setattr(EventHistory, "__iter__", prefix_read)
        committed = store.save_snapshot(candidate, expected_revision=first.revision)
        assert len(committed.snapshot.participant_control_evaluation_history[participant]) == 2
    store.close()
    lease.close()
    reopened = LocalControlPlaneStore(directory)
    lease = reopened.admit_runtime(target_scope="target:test", run_scope="run:test")
    try:
        assert reopened.load_snapshot_state().snapshot == candidate
        with sqlite3.connect(directory / "control-plane.sqlite3") as connection:
            header = json.loads(
                connection.execute("SELECT payload FROM state WHERE key='runtime-snapshot'").fetchone()[0]
            )
            assert header["participant_control_evaluation_history"] == {}
            assert connection.execute("SELECT COUNT(*) FROM snapshot_history").fetchone() == (2,)
    finally:
        reopened.close()
        lease.close()


def test_history_suffix_rolls_back_with_the_snapshot_transaction(tmp_path, monkeypatch):
    store = LocalControlPlaneStore(tmp_path / "rollback")
    lease = store.admit_runtime(target_scope="target:test", run_scope="run:test")
    original = store._upsert_snapshot

    def interrupted(connection, snapshot, **options):
        original(connection, snapshot, **options)
        raise OSError("synthetic interruption before commit")

    monkeypatch.setattr(store, "_upsert_snapshot", interrupted)
    payload = evaluation_payload()
    participant = payload["request"]["context"]["participant_address"]
    try:
        with pytest.raises(OSError):
            store.save_snapshot(
                RuntimeSnapshot(participant_control_evaluation_history={participant: [payload]}), expected_revision=0
            )
        assert store.load_snapshot_state().revision == 0
        assert store.load_snapshot_state().snapshot.participant_control_evaluation_history == {}
    finally:
        store.close()
        lease.close()


def test_replacing_a_cached_history_does_not_change_durable_authority(tmp_path):
    store = LocalControlPlaneStore(tmp_path / "replaced-cache")
    lease = store.admit_runtime(target_scope="target:test", run_scope="run:test")
    payload = evaluation_payload()
    participant = payload["request"]["context"]["participant_address"]
    try:
        store.save_snapshot(
            RuntimeSnapshot(participant_control_evaluation_history={participant: [payload]}), expected_revision=0
        )
        cached = store.load_snapshot_state()
        cached.snapshot.participant_control_evaluation_history = {}
        restored = store.load_snapshot_state()
        assert (
            restored.snapshot.participant_control_evaluation_history[participant][0]["evaluation_id"]
            == payload["evaluation_id"]
        )
    finally:
        store.close()
        lease.close()


def test_external_history_change_invalidates_the_sqlite_snapshot_cache(tmp_path):
    directory = tmp_path / "external-change"
    store = LocalControlPlaneStore(directory)
    lease = store.admit_runtime(target_scope="target:test", run_scope="run:test")
    try:
        store.save_snapshot(RuntimeSnapshot(evaluation_history={"run": [{"n": 1}]}), expected_revision=0)
        store.load_snapshot_state()
        with sqlite3.connect(directory / "control-plane.sqlite3") as connection:
            connection.execute("UPDATE snapshot_history SET payload='{}'")
        with pytest.raises(ValueError, match="integrity"):
            store.load_snapshot_state()
    finally:
        store.close()
        lease.close()


def test_rejected_scope_does_not_create_projection_schema(tmp_path):
    directory = tmp_path / "wrong-scope"
    store = LocalControlPlaneStore(directory)
    lease = store.admit_runtime(target_scope="target:test", run_scope="run:test")
    store.close()
    lease.close()
    with sqlite3.connect(directory / "control-plane.sqlite3") as connection:
        for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
            assert name.replace("_", "").isalnum()
            connection.execute('DROP TRIGGER "' + name + '"')
        for name in ("snapshot_history_streams", "snapshot_history", "operation_changes"):
            connection.execute('DROP TABLE "' + name + '"')
        connection.execute("DELETE FROM metadata WHERE key='snapshot-history-generation'")
        connection.execute("UPDATE metadata SET value='10' WHERE key='schema-version'")
        before = connection.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
    refused = LocalControlPlaneStore(directory)
    with pytest.raises(RuntimeError, match="scope"):
        refused.admit_runtime(target_scope="target:other", run_scope="run:other")
    with sqlite3.connect(directory / "control-plane.sqlite3") as connection:
        assert connection.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall() == before


def test_post_commit_projection_failure_clears_caches_and_poison_readiness(monkeypatch):
    from governed_effect_runtime_fixtures import effect_plane
    from raes_runtime import participant_control_projection

    plane, _ = effect_plane()
    with plane:
        prior = plane._snapshot_state
        snapshot = prior.snapshot.with_entries({}, evaluation_history={"run": [{"n": 1}]})
        committed = plane._store.save_snapshot(snapshot, expected_revision=prior.revision)

        def failed_projection(_):
            raise RuntimeError("synthetic projection failure after store commit")

        monkeypatch.setattr(participant_control_projection, "control_projection", failed_projection)
        with pytest.raises(RuntimeError, match="synthetic"):
            plane._publish_committed_state(committed)
        assert plane._durability_poisoned
        assert plane._control_state_projection is None
        assert plane._control_operation_index is None
        assert plane._store.load_snapshot_state().revision == committed.revision
        assert plane._store.load_snapshot_state().snapshot.evaluation_history["run"][0] == {"n": 1}
