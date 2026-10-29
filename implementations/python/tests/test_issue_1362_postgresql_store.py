"""PostgreSQL integration configuration fails closed before making a connection."""

import pytest


@pytest.mark.parametrize(
    "field,value",
    [
        ("port", True),
        ("port", 0),
        ("statement_timeout_ms", -1),
        ("connect_timeout_ms", "100"),
        ("database", "ledger;DROP"),
        ("sslmode", "invalid"),
    ],
)
def test_postgresql_settings_are_closed_and_bounded(field, value):
    from raes_runtime.control_plane_store_postgresql import PostgreSQLStoreConfiguration

    with pytest.raises((TypeError, ValueError)):
        PostgreSQLStoreConfiguration(
            **{"host": "127.0.0.1", "database": "rae_ledger", "user": "rae_ledger", field: value}
        )


def test_password_is_not_exposed_by_configuration_repr_and_connections_are_explicit():
    from pydantic import SecretStr
    from raes_runtime.control_plane_store_postgresql import PostgreSQLControlPlaneStore, PostgreSQLStoreConfiguration

    config = PostgreSQLStoreConfiguration(
        host="ledger.example", database="rae_ledger", user="rae_ledger", password=SecretStr("synthetic-password")
    )
    assert "synthetic-password" not in repr(config)
    store = PostgreSQLControlPlaneStore(config)
    assert "synthetic-password" not in repr(store)
    assert not store.admitted


def test_postgresql_store_refuses_access_until_the_scoped_owner_is_admitted():
    from raes_runtime.control_plane_store_postgresql import PostgreSQLControlPlaneStore, PostgreSQLStoreConfiguration

    store = PostgreSQLControlPlaneStore(
        PostgreSQLStoreConfiguration(host="ledger.example", database="rae_ledger", user="rae_ledger")
    )
    with pytest.raises(RuntimeError, match="admission"):
        store.load_records()


def test_postgresql_terminal_boundary_rejects_stale_revision_before_any_write():
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_runtime import control_plane_store_postgresql_mutations as mutations
    from raes_runtime.control_plane_store import SnapshotRevisionConflict
    from raes_runtime.control_plane_store_revision import SnapshotState
    from test_issue_1181_unified_control_plane_mutations import _running_record, _terminal_record

    writes = []
    running = _running_record("postgres-stale")

    class Ledger:
        def _load_records(self, connection):
            return {running.receipt.operation_id: running}

        def _load_snapshot_state(self, connection):
            return SnapshotState(RuntimeSnapshot(), 2)

        def _upsert_record(self, connection, record):
            writes.append(record)

        def _insert_audit(self, connection, event):
            writes.append(event)

    rejected_ledger = Ledger()
    rejected_snapshot = RuntimeSnapshot()
    rejected_terminal_record = _terminal_record(running)
    with pytest.raises(SnapshotRevisionConflict):
        mutations.commit_terminal_operation(
            rejected_ledger, None, rejected_snapshot, rejected_terminal_record, expected_revision=1
        )
    assert writes == []


@pytest.mark.parametrize("field", ["target_scope", "run_scope"])
def test_postgresql_mutation_admits_exact_record_scope_before_writing(monkeypatch, field):
    from contextlib import nullcontext
    from dataclasses import replace

    from raes_runtime import control_plane_store_postgresql_mutations as mutations
    from raes_runtime.control_plane_store_postgresql import PostgreSQLControlPlaneStore, PostgreSQLStoreConfiguration
    from test_issue_1181_unified_control_plane_mutations import _running_record

    store = PostgreSQLControlPlaneStore(
        PostgreSQLStoreConfiguration(host="ledger.example", database="rae_ledger", user="rae_ledger")
    )
    record = _running_record("postgres-scoped")
    context = record.status.context
    store._scope = (context.target_scope, context.run_scope)
    monkeypatch.setattr(store, "_connection", lambda: nullcontext(None))
    writes = []
    monkeypatch.setattr(mutations, "save_record", lambda store, connection, record: writes.append(record))

    store.save_record(record)
    assert writes == [record]
    foreign_context = context.model_copy(update={field: "foreign-scope"})
    foreign = replace(
        record,
        receipt=replace(record.receipt, context=foreign_context),
        status=replace(record.status, context=foreign_context),
    )
    with pytest.raises(RuntimeError, match="scope"):
        store.save_record(foreign)
    assert writes == [record]
