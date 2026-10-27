"""Confirmed operation changes do not borrow the snapshot's revision counter."""

import pytest
from raes_runtime.control_plane_store import InMemoryControlPlaneStore, LocalControlPlaneStore, TerminalCommitMode
from test_issue_1181_unified_control_plane_mutations import (
    _context,
    _running_record,
    _terminal_audit,
    _terminal_record,
)


@pytest.mark.parametrize("durable", [False, True])
def test_operation_only_commit_and_duplicate_have_exact_change_cursors(tmp_path, durable):
    store = LocalControlPlaneStore(tmp_path / "changes") if durable else InMemoryControlPlaneStore()
    scope = _context()
    lease = (
        store.admit_runtime(target_scope=scope.target_scope, run_scope=scope.run_scope)
        if durable
        else store.bind_scope(target_scope=scope.target_scope, run_scope=scope.run_scope)
    )
    try:
        snapshot = store.load_snapshot_state()
        first = store.load_operation_changes()
        running = store.claim_record(_running_record("changed"))
        claimed = store.load_operation_changes(first.cursor)
        assert claimed.records == {running.receipt.operation_id: running}
        assert not claimed.reset
        terminal = _terminal_record(running)
        store.commit_terminal_operation(
            snapshot.snapshot,
            terminal,
            audit_event=_terminal_audit(terminal),
            expected_revision=snapshot.revision,
            mode=TerminalCommitMode.OPERATION_ONLY,
        )
        closed = store.load_operation_changes(claimed.cursor)
        assert closed.cursor > claimed.cursor
        assert closed.records == {terminal.receipt.operation_id: terminal}
        assert store.load_snapshot_state().revision == snapshot.revision
        store.commit_terminal_operation(
            snapshot.snapshot,
            terminal,
            audit_event=_terminal_audit(terminal),
            expected_revision=snapshot.revision,
            mode=TerminalCommitMode.OPERATION_ONLY,
        )
        assert store.load_operation_changes(closed.cursor).records == {}
    finally:
        store.close() if durable else None
        lease.close()


def test_rolled_back_record_and_cursor_are_not_visible(tmp_path, monkeypatch):
    store = LocalControlPlaneStore(tmp_path / "rolled-back-change")
    scope = _context()
    lease = store.admit_runtime(target_scope=scope.target_scope, run_scope=scope.run_scope)
    try:
        cursor = store.load_operation_changes().cursor
        original = store._upsert_record

        def interrupted(connection, record):
            original(connection, record)
            raise OSError("synthetic interruption after record insertion")

        monkeypatch.setattr(store, "_upsert_record", interrupted)
        with pytest.raises(OSError):
            store.claim_record(_running_record("rolled-back"))
        changes = store.load_operation_changes(cursor)
        assert changes.cursor == cursor
        assert changes.records == {}
    finally:
        store.close()
        lease.close()
