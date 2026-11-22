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
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_contracts.snapshot_histories import append_history
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


def test_shared_database_namespaces_isolate_every_ledger_surface():
    if os.environ.get("RAES_EXECUTION_INTEGRATION") != "1":
        pytest.skip("requires the hosted runtime-execution integration composition")
    from postgresql_ledger_fixtures import disposable_ledger_database

    with disposable_ledger_database() as database:
        _exercise_namespace_isolation(database)


def _exercise_namespace_isolation(database):
    from contextlib import ExitStack
    from dataclasses import replace

    from participant_control_contract_fixtures import evaluation_payload
    from postgresql_ledger_fixtures import ledger_configuration
    from raes_contracts.errors import ConflictError
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_runtime.control_plane_store import AuditEvent
    from raes_runtime.control_plane_store_postgresql import PostgreSQLControlPlaneStore
    from raes_runtime.runtime_decisions import RunOperationGuaranteesDecision, runtime_store_digest
    from test_issue_1181_unified_control_plane_mutations import _context, _running_record

    base = ledger_configuration(database)
    configs = [base, replace(base, namespace="trial_one"), replace(base, namespace="trial_two")]
    stores = [PostgreSQLControlPlaneStore(config) for config in configs]
    context = _context()
    decision = RunOperationGuaranteesDecision(run_scope=context.run_scope, required_guarantees=())
    event = AuditEvent(
        timestamp="2026-11-14T10:00:00Z", action="test", identity="operator", allowed=True, target="stub"
    )
    record = _running_record("same-operation")
    payload = evaluation_payload()
    participant = payload["request"]["context"]["participant_address"]
    snapshot = RuntimeSnapshot(participant_control_evaluation_history={participant: [payload]})
    with ExitStack() as cleanup:
        for store in stores:
            store.initialize_schema()
            lease = store.admit_runtime(target_scope=context.target_scope, run_scope=context.run_scope)
            cleanup.callback(lease.close)
            cleanup.callback(store.close)
        for store in stores:
            duplicate = PostgreSQLControlPlaneStore(store._configuration)
            with pytest.raises(ConflictError, match="runtime owner"):
                duplicate.admit_runtime(target_scope="other", run_scope="run:other")
            with pytest.raises(ConflictError, match="runtime owner|bootstrap"):
                duplicate.initialize_schema()
        for index, store in enumerate(stores):
            assert store.load_records() == {}
            assert store.load_runtime_decisions() == ()
            assert store.load_snapshot_state().revision == 0
            assert not store.effect_admission_stopped()
            assert store.claim_record(record) == record
            assert store.find_by_idempotency(record.idempotency_key, context=context) == record
            assert store.claim_runtime_decision(decision)
            assert not store.claim_runtime_decision(decision)
            assert store.save_snapshot(snapshot, expected_revision=0).revision == 1
            store.append_audit(replace(event, reason=str(index)))
            # The next ledger still accepts identical IDs and starts with an empty history.
        first_cursor = stores[1].load_operation_changes().cursor
        second_cursor = stores[2].load_operation_changes().cursor
        with stores[2]._connection() as connection:
            # The caller's search path points to trial_two. Both triggers must use trial_one.
            connection.execute("UPDATE trial_one.raes_ledger_operations SET payload=payload")
            connection.execute("UPDATE trial_one.raes_ledger_state SET payload=payload")
        assert stores[1].load_operation_changes(first_cursor).records == {record.receipt.operation_id: record}
        assert stores[2].load_operation_changes(second_cursor).records == {}
        with stores[1]._connection() as first, stores[2]._connection() as second:
            query = "SELECT value FROM raes_ledger_metadata WHERE key='snapshot-history-generation'"
            assert int(first.execute(query).fetchone()[0]) == int(second.execute(query).fetchone()[0]) + 1
        stores[1].stop_effect_admission(event)
        assert stores[1].effect_admission_stopped()
        assert not stores[0].effect_admission_stopped()
        assert not stores[2].effect_admission_stopped()
        digests = [runtime_store_digest(store) for store in stores]
    for index, config in enumerate(configs):
        reopened = PostgreSQLControlPlaneStore(config)
        lease = reopened.admit_runtime(target_scope=context.target_scope, run_scope=context.run_scope)
        try:
            assert reopened.admit_execution_generation() == 2
            assert runtime_store_digest(reopened) == digests[index]
            assert reopened.load_records() == {record.receipt.operation_id: record}
            assert reopened.load_runtime_decisions() == (decision,)
            assert reopened.load_snapshot() == snapshot
            assert reopened.load_snapshot_state().revision == 1
            assert reopened.read_audit() == [replace(event, reason=str(index)), *([event] if index == 1 else [])]
            assert reopened.effect_admission_stopped() == (index == 1)
        finally:
            reopened.close()
            lease.close()


def test_named_catalog_checks_refuse_public_and_temporary_decoys(monkeypatch):
    if os.environ.get("RAES_EXECUTION_INTEGRATION") != "1":
        pytest.skip("requires the hosted runtime-execution integration composition")
    from dataclasses import replace

    from postgresql_ledger_fixtures import disposable_ledger_database, ledger_configuration
    from raes_contracts.errors import ConflictError, EvidenceIntegrityError
    from raes_runtime.control_plane_store_postgresql import PostgreSQLControlPlaneStore

    with disposable_ledger_database() as database:
        base = ledger_configuration(database)
        PostgreSQLControlPlaneStore(base).initialize_schema()
        store = PostgreSQLControlPlaneStore(replace(base, namespace="trial_one"))
        # Ambient defaults must not let an uninitialized named store open public's ledger.
        monkeypatch.setenv("PGOPTIONS", "-c search_path=public")
        with pytest.raises(ConflictError, match="schema is missing"):
            store.admit_runtime(target_scope="target:test", run_scope="run:one")
        store.initialize_schema()
        with store._connect() as connection:
            connection.execute("DROP TABLE trial_one.raes_ledger_audit")
        original = store._connect

        def with_decoy(**options):
            connection = original(**options)
            connection.execute("CREATE TEMP TABLE raes_ledger_audit(sequence BIGINT, payload TEXT, digest TEXT)")
            if not options.get("autocommit"):
                connection.commit()
            return connection

        monkeypatch.setattr(store, "_connect", with_decoy)
        with pytest.raises(EvidenceIntegrityError, match="missing a required table"):
            store.admit_runtime(target_scope="target:test", run_scope="run:one")
        assert not store.admitted
