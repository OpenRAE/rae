"""Issue #1678 review cycle 2: durable-store and retained-evidence refusal categories (ADR-116)."""

from __future__ import annotations

import errno
import hashlib
import os
import sqlite3
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from raes_contracts.errors import ConflictError, EvidenceIntegrityError, OperationalError
from raes_operations import run_artifacts
from raes_operations.run_artifacts import RunMaterializationArchive
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_local_codec import encode_payload
from raes_runtime.control_plane_store_postgresql import PostgreSQLControlPlaneStore, PostgreSQLStoreConfiguration
from raes_runtime.control_plane_store_postgresql_schema import (
    LEDGER_COLUMNS,
    PROJECTION_COLUMNS,
    initialize_projection_schema,
    initialize_schema,
    require_ledger_tables,
)
from raes_runtime.control_plane_store_records import _record_payload
from raes_runtime.inject_claims import require_inject_history, require_stored_inject_history
from test_issue_1367_inject_claims import claimed_record
from test_issue_1678_sweep_r1 import (
    _SNAPSHOT_REFUSAL,
    _bound_store,
    _check,
    _create_store,
    _rewrite_snapshot_header,
    _set,
)

_SCOPE = {"target_scope": "target:stub", "run_scope": "run:ops"}
_INJECT_SCOPE = {"target_scope": "target:reference", "run_scope": "run:environment-1"}


def _damage_root_page(database: Path, table: str) -> None:
    with sqlite3.connect(database) as connection:
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        root = connection.execute("SELECT rootpage FROM sqlite_master WHERE name=?", (table,)).fetchone()[0]
    content = bytearray(database.read_bytes())
    content[(root - 1) * page_size : root * page_size] = b"\xff" * page_size
    with database.open("r+b") as handle:
        handle.write(bytes(content))


# core-F3: the SQLite corruption translation covers every use of a local-store connection.


@pytest.mark.parametrize("table", ["audit_events", "operations", "snapshot_history"])
def test_runtime_admission_refuses_a_store_with_a_damaged_page(tmp_path: Path, table: str) -> None:
    store_path = tmp_path / "store"
    _damage_root_page(_bound_store(store_path), table)

    with pytest.raises(EvidenceIntegrityError, match="not a valid SQLite database") as caught:
        LocalControlPlaneStore(store_path).admit_runtime(**_SCOPE)
    assert isinstance(caught.value.__cause__, sqlite3.DatabaseError)


def test_a_store_read_refuses_a_page_damaged_after_admission(tmp_path: Path) -> None:
    store_path = tmp_path / "store"
    database = _create_store(store_path)
    store = LocalControlPlaneStore(store_path)
    lease = store.admit_runtime(**_SCOPE)
    try:
        _damage_root_page(database, "audit_events")
        with pytest.raises(EvidenceIntegrityError, match="not a valid SQLite database"):
            store.read_audit()
    finally:
        store.close()
        lease.close()


def test_a_store_connection_keeps_other_sqlite_errors(tmp_path: Path) -> None:
    store_path = tmp_path / "store"
    _create_store(store_path)
    store = LocalControlPlaneStore(store_path)
    lease = store.admit_runtime(**_SCOPE)
    try:
        with pytest.raises(sqlite3.OperationalError), store._connection() as connection:
            connection.execute("SELECT * FROM no_such_table")
    finally:
        store.close()
        lease.close()


# core-F5: every snapshot carrier element and entry must be an object before reconstruction.


@pytest.mark.parametrize(
    "change",
    [
        _set("entries", value={"provision.node.other": 1}),
        _set("realization_provenance", value=[1]),
        _set("realization_observations", value=["observation"]),
        _set("materialization_attestations", value=[None]),
    ],
    ids=["entry", "provenance-item", "observation-item", "attestation-item"],
)
def test_a_stored_snapshot_with_a_non_object_element_is_an_integrity_failure(tmp_path: Path, change: object) -> None:
    store_path = tmp_path / "store"
    database = _bound_store(store_path)
    with sqlite3.connect(database) as connection:
        # Without the history format marker, the header carries the histories itself.
        connection.execute("DELETE FROM metadata WHERE key='snapshot-history-format'")
        connection.execute("DELETE FROM snapshot_history")
        connection.execute("DELETE FROM snapshot_history_streams")
    _rewrite_snapshot_header(database, change)

    with pytest.raises(EvidenceIntegrityError, match=_SNAPSHOT_REFUSAL):
        _check(store_path)
    with pytest.raises(EvidenceIntegrityError, match=_SNAPSHOT_REFUSAL):
        LocalControlPlaneStore(store_path).admit_runtime(**_SCOPE)


# core-F6: stored inject history that does not replay is damaged evidence, not a request conflict.


def _store_rows(database: Path, *records: object) -> None:
    with sqlite3.connect(database) as connection:
        for record in records:
            payload, digest = encode_payload(_record_payload(record))
            context = record.receipt.context
            connection.execute(
                "INSERT INTO operations(operation_id, idempotency_key, actor_id, operation_kind, target_scope, "
                "run_scope, request_commitment, legacy_opaque_claim, request_fingerprint, payload, digest) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
                (
                    record.receipt.operation_id,
                    record.idempotency_key,
                    context.actor_id,
                    context.operation_kind.value,
                    context.target_scope,
                    context.run_scope,
                    context.request_commitment,
                    record.request_fingerprint,
                    payload,
                    digest,
                ),
            )


_BROKEN_HISTORIES = {
    "duplicate-claim": lambda: (claimed_record(), claimed_record(key="other-key", operation_id="other-operation")),
    "order-position": lambda: (claimed_record(position=2),),
    "order-head": lambda: (claimed_record(predecessor="foreign-head"),),
}


@pytest.mark.parametrize("history", sorted(_BROKEN_HISTORIES))
def test_stored_inject_history_that_does_not_replay_is_an_integrity_failure(tmp_path: Path, history: str) -> None:
    store_path = tmp_path / "ledger"
    store = LocalControlPlaneStore(store_path)
    lease = store.admit_runtime(**_INJECT_SCOPE)
    try:
        _store_rows(store_path / "control-plane.sqlite3", *_BROKEN_HISTORIES[history]())
        with pytest.raises(EvidenceIntegrityError) as caught:
            store.load_records()
        assert type(caught.value) is EvidenceIntegrityError
    finally:
        store.close()
        lease.close()
    with pytest.raises(EvidenceIntegrityError):
        LocalControlPlaneStore(store_path).admit_runtime(**_INJECT_SCOPE)


def test_postgresql_loader_refuses_stored_inject_history_that_does_not_replay() -> None:
    rows = []
    for record in _BROKEN_HISTORIES["duplicate-claim"]():
        payload, digest = encode_payload(_record_payload(record))
        rows.append((record.receipt.operation_id, payload, digest))
    connection = SimpleNamespace(execute=lambda _statement: SimpleNamespace(fetchall=lambda: rows))

    with pytest.raises(EvidenceIntegrityError) as caught:
        PostgreSQLControlPlaneStore._load_records(connection)
    assert type(caught.value) is EvidenceIntegrityError


def _orphan_delivery() -> object:
    application = SimpleNamespace(world_operation_id="world-operation", delivery_address="participant", control=None)
    return SimpleNamespace(
        receipt=SimpleNamespace(operation_id="delivery-operation"),
        inject_delivery=SimpleNamespace(application=application),
        inject_occurrence=None,
    )


def test_a_delivery_without_its_world_predecessor_keeps_the_category_of_its_caller() -> None:
    with pytest.raises(ConflictError) as claimed:
        require_inject_history((_orphan_delivery(),))
    assert type(claimed.value) is ConflictError
    with pytest.raises(EvidenceIntegrityError) as stored:
        require_stored_inject_history((_orphan_delivery(),))
    assert type(stored.value) is EvidenceIntegrityError


def test_a_live_claim_against_a_valid_stored_history_stays_a_conflict(tmp_path: Path) -> None:
    store = LocalControlPlaneStore(tmp_path / "ledger")
    lease = store.admit_runtime(**_INJECT_SCOPE)
    try:
        store.claim_record(claimed_record())
        with pytest.raises(ConflictError) as caught:
            store.claim_record(claimed_record(key="other-key", operation_id="other-operation"))
        assert type(caught.value) is ConflictError
    finally:
        store.close()
        lease.close()


# core-F7: PostgreSQL admission verifies the columns that the ledger queries read.

_COLUMN_QUERY = "SELECT attname FROM pg_attribute WHERE attrelid = to_regclass(%s) AND attnum > 0 AND NOT attisdropped"


class _Ledger:
    """A PostgreSQL connection double with the catalog of a ledger whose tables can lose columns."""

    def __init__(self, *, lost: dict[str, str] | None = None, absent: frozenset[str] = frozenset()) -> None:
        self.lost = lost or {}
        self.absent = absent
        self.statements: list[str] = []

    def execute(self, statement: str, parameters: tuple[str, ...] = ()) -> object:
        self.statements.append(statement)
        table = parameters[0] if parameters else ""
        if statement == "SELECT to_regclass(%s)":
            return SimpleNamespace(fetchone=lambda: (None,) if table in self.absent else parameters)
        if statement == _COLUMN_QUERY:
            columns = {**LEDGER_COLUMNS, **PROJECTION_COLUMNS}.get(table, frozenset())
            present = [] if table in self.absent else sorted(columns - {self.lost.get(table)})
            return SimpleNamespace(fetchall=lambda: [(name,) for name in present])
        # A bootstrap statement; the bootstrap reads back the current schema version.
        return SimpleNamespace(fetchone=lambda: ("4",))

    def transaction(self) -> object:
        return nullcontext()


@pytest.mark.parametrize(
    ("lost", "projection"),
    [
        ({"raes_ledger_state": "revision"}, False),
        ({"raes_ledger_operations": "actor_id"}, False),
        ({"raes_ledger_audit": "sequence"}, False),
        ({"raes_ledger_history": "position"}, True),
        ({"raes_ledger_changes": "removed"}, True),
    ],
    ids=["state-revision", "operations-actor", "audit-sequence", "history-position", "changes-removed"],
)
def test_postgresql_admission_refuses_a_ledger_that_lost_a_column(lost: dict[str, str], projection: bool) -> None:
    with pytest.raises(EvidenceIntegrityError, match="missing a required table or column") as caught:
        require_ledger_tables(_Ledger(lost=lost), projection=projection)
    assert type(caught.value) is EvidenceIntegrityError


@pytest.mark.parametrize("projection", [False, True])
def test_postgresql_admission_accepts_a_complete_ledger(projection: bool) -> None:
    require_ledger_tables(_Ledger(), projection=projection)


def test_postgresql_bootstrap_refuses_a_damaged_existing_table_before_any_statement() -> None:
    ledger = _Ledger(lost={"raes_ledger_operations": "actor_id"})
    with pytest.raises(EvidenceIntegrityError, match="missing a required table or column"):
        initialize_schema(ledger)
    assert all(statement == _COLUMN_QUERY for statement in ledger.statements)


def test_postgresql_projection_bootstrap_refuses_a_damaged_existing_table_before_any_statement() -> None:
    ledger = _Ledger(lost={"raes_ledger_changes": "operation_id"})
    with pytest.raises(EvidenceIntegrityError, match="missing a required table or column"):
        initialize_projection_schema(ledger)
    assert all(statement == _COLUMN_QUERY for statement in ledger.statements)


def test_postgresql_bootstrap_checks_only_the_tables_that_exist() -> None:
    absent = frozenset(LEDGER_COLUMNS) | frozenset(PROJECTION_COLUMNS)
    ledger = _Ledger(absent=absent)
    initialize_schema(ledger)
    assert any(
        statement.startswith("CREATE TABLE IF NOT EXISTS raes_ledger_metadata") for statement in ledger.statements
    )
    assert any(
        statement.startswith("CREATE TABLE IF NOT EXISTS raes_ledger_changes") for statement in ledger.statements
    )


# The PostgreSQL connection boundary classifies a corruption report like the SQLite boundary.


class _Connection:
    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def transaction(self) -> object:
        return nullcontext()


def _admitted_postgresql_store(monkeypatch: pytest.MonkeyPatch) -> PostgreSQLControlPlaneStore:
    store = PostgreSQLControlPlaneStore(PostgreSQLStoreConfiguration(host="ledger", database="raes", user="raes"))
    store._owner = SimpleNamespace(closed=False, assert_owner=lambda: None)
    monkeypatch.setattr(store, "_connect", lambda **_options: _Connection())
    return store


@pytest.mark.parametrize("corruption", [psycopg.errors.DataCorrupted, psycopg.errors.IndexCorrupted])
def test_postgresql_ledger_corruption_is_an_integrity_failure(
    monkeypatch: pytest.MonkeyPatch, corruption: type[Exception]
) -> None:
    store = _admitted_postgresql_store(monkeypatch)
    with pytest.raises(EvidenceIntegrityError, match="PostgreSQL ledger") as caught, store._connection():
        raise corruption("damaged page")
    assert isinstance(caught.value.__cause__, corruption)


def test_postgresql_connection_keeps_other_driver_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _admitted_postgresql_store(monkeypatch)
    with pytest.raises(psycopg.errors.SerializationFailure), store._connection():
        raise psycopg.errors.SerializationFailure("retry")


class _CorruptedCatalog(_Connection):
    def execute(self, *_arguments: object) -> object:
        raise psycopg.errors.DataCorrupted("damaged page")


def test_postgresql_bootstrap_classifies_ledger_corruption(monkeypatch: pytest.MonkeyPatch) -> None:
    store = PostgreSQLControlPlaneStore(PostgreSQLStoreConfiguration(host="ledger", database="raes", user="raes"))
    monkeypatch.setattr(store, "_connect", lambda **_options: _CorruptedCatalog())
    with pytest.raises(EvidenceIntegrityError, match="PostgreSQL ledger storage is damaged"):
        store.initialize_schema()


# core-F13: the run archive classifies a rejected retained artifact at its read boundary.


@pytest.fixture
def retained(tmp_path: Path) -> tuple[RunMaterializationArchive, object, Path]:
    from test_issue_1242_scope_runtime import apply

    result, _ = apply(tmp_path, {"default": "open"}, addition=True)
    assert result.success
    record = result.snapshot.materialization_attestations[-1]
    return RunMaterializationArchive(tmp_path), record, tmp_path / record.reference.ref_path


def test_a_missing_retained_artifact_is_an_integrity_failure(retained: tuple[object, object, Path]) -> None:
    archive, record, path = retained
    path.unlink()
    with pytest.raises(EvidenceIntegrityError) as caught:
        archive.read(record)
    assert isinstance(caught.value.__cause__, FileNotFoundError)


def test_a_retained_artifact_directory_replaced_by_a_symlink_is_an_integrity_failure(
    retained: tuple[object, object, Path],
) -> None:
    archive, record, path = retained
    directory = path.parent
    moved = directory.with_name("moved")
    directory.rename(moved)
    directory.symlink_to(moved, target_is_directory=True)
    with pytest.raises(EvidenceIntegrityError):
        archive.read(record)


def test_a_retained_record_whose_bytes_are_not_text_is_an_integrity_failure(
    retained: tuple[object, object, Path],
) -> None:
    archive, record, path = retained
    data = b"\xff\xfe"
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    artifact = record.artifact.model_copy(
        update={
            "size_bytes": len(data),
            "uri": f"urn:sha256:{digest}",
            "checksum": record.artifact.checksum.model_copy(update={"value": digest}),
        }
    )
    with pytest.raises(EvidenceIntegrityError) as caught:
        archive.read(record.model_copy(update={"artifact": artifact}))
    assert isinstance(caught.value.__cause__, UnicodeDecodeError)


def test_a_host_read_failure_is_an_operational_error(
    retained: tuple[object, object, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, record, path = retained
    real_open = os.open

    def _failing_open(name: object, *args: object, **kwargs: object) -> int:
        if name == path.name:
            raise OSError(errno.EIO, "input/output error")
        return real_open(name, *args, **kwargs)

    monkeypatch.setattr(run_artifacts.os, "open", _failing_open)
    with pytest.raises(OperationalError) as caught:
        archive.read(record)
    assert type(caught.value) is OperationalError


def test_an_unusable_archive_root_is_an_operational_error(
    retained: tuple[object, object, Path], tmp_path: Path
) -> None:
    _archive, record, _path = retained
    with pytest.raises(OperationalError):
        RunMaterializationArchive(tmp_path / "absent").read(record)


def test_a_planted_symlink_at_a_published_name_is_an_integrity_failure(
    retained: tuple[RunMaterializationArchive, object, Path],
) -> None:
    archive, record, path = retained
    content = path.read_text()
    moved = path.with_suffix(".retained")
    path.rename(moved)
    path.symlink_to(moved)
    with pytest.raises(EvidenceIntegrityError):
        archive.publish(content)


def test_a_host_publication_failure_is_an_operational_error(
    retained: tuple[RunMaterializationArchive, object, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, _record, path = retained
    content = path.read_text()

    def _failing_link(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.ENOSPC, "no space left on device")

    monkeypatch.setattr(run_artifacts.os, "link", _failing_link)
    with pytest.raises(OperationalError):
        archive.publish(content)


def test_the_archive_read_lets_a_defect_propagate(
    retained: tuple[RunMaterializationArchive, object, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, record, _path = retained

    def _defect(_records: object) -> None:
        raise KeyError("defect")

    monkeypatch.setattr("raes_contracts.materialization.require_materialization_records", _defect)
    with pytest.raises(KeyError):
        archive.read(record)
