"""Shared observable guarantees for the landed P0, P1, and P2 compositions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from control_plane_conformance_fixtures import (
    DURABLE_PROFILES,
    PROFILES,
    RUN_SCOPE,
    profile_harness,
    terminal_audits,
    witness_events,
)
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import SnapshotRevisionConflict
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_maintenance import (
    LocalStoreMaintenanceOperation,
    maintain_local_control_plane_store,
)

pytestmark = pytest.mark.control_plane_conformance


@pytest.mark.parametrize("profile", PROFILES)
def test_profile_scoped_retry_status_audit_and_cache_coherence(profile, tmp_path) -> None:
    with profile_harness(profile, tmp_path) as harness:
        assert harness.snapshot_cut() == ({}, 0)
        first = harness.submit()
        assert harness.status(first) is OperationState.SUCCEEDED
        assert harness.submit() == first
        assert harness.status(first, actor="bob") is None
        assert harness.status(first, actor="changed-scope") is None
        assert harness.status(first, actor="other-target") is None
        second = harness.submit(actor="bob")
        assert second != first
        assert harness.status(second, actor="bob") is OperationState.SUCCEEDED
        assert [item["event"] for item in witness_events(tmp_path / "effects.jsonl")] == ["invoke", "applied"] * 2
        for operation_id, actor in ((first, "alice"), (second, "bob")):
            audits = terminal_audits(harness.store, operation_id)
            assert len(audits) == 1
            assert (audits[0].identity, audits[0].reason, audits[0].target) == (
                actor,
                "operation-succeeded",
                "target:stub",
            )
        observed = harness.store.load_snapshot_state()
        harness.store.save_snapshot(
            RuntimeSnapshot(metadata={"coherence": "new-cut"}), expected_revision=observed.revision
        )
        with pytest.raises(SnapshotRevisionConflict):
            harness.store.save_snapshot(
                RuntimeSnapshot(metadata={"coherence": "stale"}), expected_revision=observed.revision
            )
        assert harness.snapshot_cut() == ({"coherence": "new-cut"}, observed.revision + 1)
        assert harness.status(first) is OperationState.SUCCEEDED


@pytest.mark.parametrize("profile", PROFILES)
def test_concurrent_same_actor_submissions_have_one_effect_and_terminal_cut(profile, tmp_path) -> None:
    barrier = Barrier(4)
    with profile_harness(profile, tmp_path) as harness:

        def submit(_index):
            barrier.wait(timeout=10)
            return harness.submit()

        with ThreadPoolExecutor(max_workers=4) as executor:
            operation_ids = list(executor.map(submit, range(4)))
        assert len(set(operation_ids)) == 1
        assert len(harness.store.load_records()) == 1
        assert len(terminal_audits(harness.store, operation_ids[0])) == 1
        assert harness.snapshot_cut() == ({}, 1)
        assert [item["event"] for item in witness_events(tmp_path / "effects.jsonl")] == ["invoke", "applied"]


@pytest.mark.parametrize("profile", DURABLE_PROFILES)
def test_profile_lease_scope_and_restore_keep_receipts_and_claims(profile, tmp_path) -> None:
    with profile_harness(profile, tmp_path) as harness:
        operation_id = harness.submit()
        with pytest.raises(RuntimeError, match="exactly one worker"), profile_harness(profile, tmp_path):
            pytest.fail("second owner was admitted")
    for target_name, run in (("other", RUN_SCOPE), ("stub", "run:other")):
        with pytest.raises(RuntimeError, match="scope does not match"):
            RuntimeControlPlane(
                replace(create_stub_target(), name=target_name),
                store=LocalControlPlaneStore(tmp_path / "store"),
                run_scope=run,
            )
    backup = tmp_path / "backup.sqlite3"
    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.BACKUP,
        store_path=tmp_path / "store",
        backup_path=backup,
        target_name="stub",
        run_scope=RUN_SCOPE,
    )
    restored = tmp_path / "restored"
    restored.mkdir()
    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.RESTORE,
        store_path=restored / "store",
        backup_path=backup,
        target_name="stub",
        run_scope=RUN_SCOPE,
    )
    with profile_harness(profile, restored) as harness:
        assert harness.status(operation_id) is OperationState.SUCCEEDED
        assert harness.submit() == operation_id
        assert harness.snapshot_cut() == ({}, 1)
        assert len(terminal_audits(harness.store, operation_id)) == 1
        assert witness_events(restored / "effects.jsonl") == []


def test_p2_spoofed_headers_and_invalid_bearer_never_disclose_receipts(tmp_path) -> None:
    with profile_harness("P2", tmp_path) as harness:
        operation_id = harness.submit()
        spoofed = {"x-raes-client-identity": "alice", "x-raes-client-verified": "true"}
        for headers in (spoofed, {**spoofed, "authorization": "Bearer invalid"}):
            response = harness.client.get(f"/operations/{operation_id}", headers=headers)
            assert response.status_code == 401
            assert operation_id not in response.text
        assert len(harness.store.load_records()) == 1
        assert len(terminal_audits(harness.store, operation_id)) == 1
