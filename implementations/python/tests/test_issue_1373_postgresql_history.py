"""Hosted PostgreSQL checks for history suffixes and operation-only changes."""

import os

import pytest

pytestmark = pytest.mark.integration


def test_postgresql_history_reopens_and_operation_only_changes_are_visible():
    if os.environ.get("RAES_EXECUTION_INTEGRATION") != "1":
        pytest.skip("requires the hosted runtime-execution integration composition")
    from postgresql_ledger_fixtures import disposable_ledger_database

    with disposable_ledger_database() as database:
        _exercise_history_reopening(database)


def _exercise_history_reopening(database):
    from participant_control_contract_fixtures import evaluation_payload
    from postgresql_ledger_fixtures import ledger_configuration
    from raes_contracts.immutable_history import append_history
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_runtime.control_plane_store_postgresql import PostgreSQLControlPlaneStore
    from test_issue_1181_unified_control_plane_mutations import _context, _running_record

    configuration = ledger_configuration(database)
    store = PostgreSQLControlPlaneStore(configuration)
    store.initialize_schema()
    scope = _context()
    lease = store.admit_runtime(target_scope=scope.target_scope, run_scope=scope.run_scope)
    payload = evaluation_payload()
    participant = payload["request"]["context"]["participant_address"]
    snapshot = RuntimeSnapshot(participant_control_evaluation_history={participant: [payload]})
    try:
        first = store.save_snapshot(snapshot, expected_revision=0)
        cursor = store.load_operation_changes().cursor
        running = _running_record("projection-operation-only")
        store.claim_record(running)
        changes = store.load_operation_changes(cursor)
        assert changes.records == {running.receipt.operation_id: running}
        assert store.load_snapshot_state().revision == first.revision
        second = snapshot.with_entries(
            {},
            participant_control_evaluation_history=append_history(
                snapshot,
                "participant_control_evaluation_history",
                participant,
                [{**payload, "evaluation_id": "evaluation-next"}],
            ),
        )
        store.save_snapshot(second, expected_revision=first.revision)
    finally:
        store.close()
        lease.close()
    reopened = PostgreSQLControlPlaneStore(configuration)
    lease = reopened.admit_runtime(target_scope=scope.target_scope, run_scope=scope.run_scope)
    try:
        assert reopened.load_snapshot_state().snapshot == second
        assert reopened.load_operation_changes().records[running.receipt.operation_id] == running
    finally:
        reopened.close()
        lease.close()
