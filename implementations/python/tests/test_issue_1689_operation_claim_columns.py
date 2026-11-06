"""Issue #1689: store admission refuses operation claim columns that do not match their records."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from raes_contracts.errors import EvidenceIntegrityError
from raes_contracts.runtime_state import OperationKind, OperationState
from raes_runtime.control_plane_store_claim_columns import ledger_operation_claim_columns
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_local_codec import encode_payload
from raes_runtime.control_plane_store_postgresql import PostgreSQLControlPlaneStore
from raes_runtime.control_plane_store_postgresql_mutations import find_by_idempotency
from raes_runtime.control_plane_store_postgresql_projection import stored_record
from raes_runtime.control_plane_store_records import _record_payload
from raes_runtime.control_plane_store_transitions import _require_operation_record_transition
from raes_runtime.record_immutability import is_immutable_value_error
from test_issue_1184_atomic_idempotency_claims import _context, _record

_SCOPE = {"target_scope": "target:stub", "run_scope": "run:default"}
_DATABASE = "control-plane.sqlite3"
_OPAQUE_KEY = f"participant-control:{'a' * 64}"
# One changed value for each claim column. Each value differs from the value that the record gives.
_CHANGED_COLUMNS = {
    "idempotency_key": (
        "UPDATE operations SET idempotency_key=? WHERE operation_id=?",
        "other-key",
    ),
    "actor_id": (
        "UPDATE operations SET actor_id=? WHERE operation_id=?",
        "operator-z",
    ),
    "operation_kind": (
        "UPDATE operations SET operation_kind=? WHERE operation_id=?",
        "evaluation",
    ),
    "target_scope": (
        "UPDATE operations SET target_scope=? WHERE operation_id=?",
        "target:other",
    ),
    "run_scope": (
        "UPDATE operations SET run_scope=? WHERE operation_id=?",
        "run:other",
    ),
    "request_commitment": (
        "UPDATE operations SET request_commitment=? WHERE operation_id=?",
        f"sha256:{'b' * 64}",
    ),
    "legacy_opaque_claim": (
        "UPDATE operations SET legacy_opaque_claim=? WHERE operation_id=?",
        1,
    ),
    "request_fingerprint": (
        "UPDATE operations SET request_fingerprint=? WHERE operation_id=?",
        "changed-fingerprint",
    ),
}


def _valid_store(path: Path) -> Path:
    store = LocalControlPlaneStore(path)
    lease = store.admit_runtime(**_SCOPE)
    try:
        store.claim_record(_record("keyed-operation", key="client-key"))
        store.claim_record(_record("unkeyed-operation", key=""))
        # A client can choose a key with a legacy prefix. Only a migrated record quarantines it.
        store.claim_record(_record("prefixed-operation", key=_OPAQUE_KEY))
    finally:
        store.close()
        lease.close()
    return path / _DATABASE


def _change_column(database: Path, column: str, value: object, operation_id: str = "keyed-operation") -> None:
    statement, _value = _CHANGED_COLUMNS[column]
    with sqlite3.connect(database) as connection:
        connection.execute(statement, (value, operation_id))


def _admit(path: Path, *, maintenance: bool) -> None:
    store = LocalControlPlaneStore(path)
    admit = store.admit_maintenance if maintenance else store.admit_runtime
    lease = admit(**_SCOPE)
    store.close()
    lease.close()


@pytest.mark.parametrize("maintenance", [False, True], ids=["runtime", "maintenance"])
def test_admission_accepts_a_store_whose_claim_columns_match_their_records(tmp_path: Path, maintenance: bool) -> None:
    store_path = tmp_path / "store"
    _valid_store(store_path)

    _admit(store_path, maintenance=maintenance)

    store = LocalControlPlaneStore(store_path)
    lease = store.admit_runtime(**_SCOPE)
    try:
        assert set(store.load_records()) == {"keyed-operation", "unkeyed-operation", "prefixed-operation"}
        found = store.find_by_idempotency("client-key", context=_record("probe").receipt.context)
        assert found is not None
        assert found.receipt.operation_id == "keyed-operation"
    finally:
        store.close()
        lease.close()


@pytest.mark.parametrize("maintenance", [False, True], ids=["runtime", "maintenance"])
@pytest.mark.parametrize("column", sorted(_CHANGED_COLUMNS))
def test_admission_refuses_a_store_with_a_changed_claim_column(tmp_path: Path, column: str, maintenance: bool) -> None:
    store_path = tmp_path / "store"
    _change_column(_valid_store(store_path), column, _CHANGED_COLUMNS[column][1])

    with pytest.raises(EvidenceIntegrityError, match="operation claim columns do not match the operation record"):
        _admit(store_path, maintenance=maintenance)


def test_admission_refuses_a_cleared_quarantine_of_an_opaque_legacy_claim(tmp_path: Path) -> None:
    store_path = tmp_path / "store"
    store = LocalControlPlaneStore(store_path)
    lease = store.admit_runtime(**_SCOPE)
    legacy = replace(
        _record("legacy-operation", context=_context(kind=OperationKind.PARTICIPANT_CONTROL), key=_OPAQUE_KEY),
        legacy_request_commitment=True,
    )
    try:
        store.claim_record(legacy)
    finally:
        store.close()
        lease.close()
    database = store_path / _DATABASE
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT legacy_opaque_claim FROM operations").fetchone() == (1,)
    _admit(store_path, maintenance=False)

    _change_column(database, "legacy_opaque_claim", 0, operation_id="legacy-operation")

    with pytest.raises(EvidenceIntegrityError, match="operation claim columns do not match the operation record"):
        _admit(store_path, maintenance=False)


@pytest.mark.parametrize("context", [True, False], ids=["scoped", "key-only"])
def test_an_idempotency_lookup_refuses_a_row_whose_claim_columns_do_not_match(tmp_path: Path, context: bool) -> None:
    store_path = tmp_path / "store"
    database = _valid_store(store_path)
    store = LocalControlPlaneStore(store_path)
    lease = store.admit_runtime(**_SCOPE)
    try:
        # The lookup finds the row by its key. The changed fingerprint belongs to no record.
        _change_column(database, "request_fingerprint", "changed-fingerprint")
        lookup_context = _record("probe").receipt.context if context else None
        with pytest.raises(EvidenceIntegrityError, match="operation claim columns do not match"):
            store.find_by_idempotency("client-key", context=lookup_context)
    finally:
        store.close()
        lease.close()


def test_a_transition_cannot_drop_the_legacy_request_commitment() -> None:
    existing = replace(_record("legacy-operation", key="legacy-key"), legacy_request_commitment=True)
    replacement = replace(
        existing,
        status=replace(existing.status, state=OperationState.SUCCEEDED),
        legacy_request_commitment=False,
    )

    with pytest.raises(ValueError, match="operation identity is immutable") as caught:
        _require_operation_record_transition(existing, replacement)
    assert is_immutable_value_error(caught.value)


def _ledger_row(record: object, **changes: str) -> tuple[object, ...]:
    actor_id, operation_kind, idempotency_key = ledger_operation_claim_columns(record)
    columns = {"actor_id": actor_id, "operation_kind": operation_kind, "idempotency_key": idempotency_key, **changes}
    payload, digest = encode_payload(_record_payload(record))
    return (
        record.receipt.operation_id,
        columns["actor_id"],
        columns["operation_kind"],
        columns["idempotency_key"],
        payload,
        digest,
    )


def _ledger_connection(*rows: tuple[object, ...]) -> SimpleNamespace:
    cursor = SimpleNamespace(fetchall=lambda: list(rows), fetchone=lambda: rows[0] if rows else None)
    return SimpleNamespace(execute=lambda _statement, _parameters=(): cursor)


def test_the_postgresql_ledger_accepts_rows_whose_claim_columns_match_their_records() -> None:
    record = _record("ledger-operation", key="client-key")
    connection = _ledger_connection(_ledger_row(record))

    assert PostgreSQLControlPlaneStore._load_records(connection) == {"ledger-operation": record}
    assert stored_record(connection, "ledger-operation") == record
    assert find_by_idempotency(None, connection, "client-key", context=record.receipt.context) == record


@pytest.mark.parametrize(
    "change",
    [{"actor_id": "operator-z"}, {"operation_kind": "evaluation"}, {"idempotency_key": "other-key"}],
    ids=["actor", "kind", "key"],
)
def test_the_postgresql_ledger_refuses_a_row_with_a_changed_claim_column(change: dict[str, str]) -> None:
    record = _record("ledger-operation", key="client-key")
    connection = _ledger_connection(_ledger_row(record, **change))

    for read in (
        lambda: PostgreSQLControlPlaneStore._load_records(connection),
        lambda: stored_record(connection, "ledger-operation"),
        lambda: find_by_idempotency(None, connection, "client-key"),
    ):
        with pytest.raises(EvidenceIntegrityError, match="operation claim columns do not match"):
            read()


def test_a_migrated_store_with_an_opaque_legacy_claim_admits_again(tmp_path: Path) -> None:
    store_path = tmp_path / "v3-store"
    store = LocalControlPlaneStore(store_path)
    lease = store.admit_runtime(**_SCOPE)
    try:
        store.claim_record(
            _record("legacy-operation", context=_context(kind=OperationKind.PARTICIPANT_CONTROL), key=_OPAQUE_KEY)
        )
    finally:
        store.close()
        lease.close()
    with sqlite3.connect(store_path / _DATABASE) as connection:
        # Schema 3 had no claim columns. The migration derives them and marks the legacy request commitment.
        connection.execute("DROP INDEX operations_idempotency_claim")
        for statement in (
            "ALTER TABLE operations DROP COLUMN legacy_opaque_claim",
            "ALTER TABLE operations DROP COLUMN request_commitment",
            "ALTER TABLE operations DROP COLUMN run_scope",
            "ALTER TABLE operations DROP COLUMN target_scope",
            "ALTER TABLE operations DROP COLUMN operation_kind",
            "ALTER TABLE operations DROP COLUMN actor_id",
        ):
            connection.execute(statement)
        connection.execute("UPDATE metadata SET value='3' WHERE key='schema-version'")

    _admit(store_path, maintenance=False)
    _admit(store_path, maintenance=True)

    with sqlite3.connect(store_path / _DATABASE) as connection:
        assert connection.execute("SELECT legacy_opaque_claim FROM operations").fetchone() == (1,)
