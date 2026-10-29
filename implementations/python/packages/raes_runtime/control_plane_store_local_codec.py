"""Canonical payload and transaction primitives for the local store."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from raes_contracts.errors import EvidenceIntegrityError

# SQLite reports a file that is not a database, or a damaged database page, with these primary result codes.
_INVALID_DATABASE_RESULT_CODES = frozenset({sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB})
# The columns that the store queries read in each table of the current schema.
CURRENT_LOCAL_TABLES: Mapping[str, frozenset[str]] = {
    "metadata": frozenset({"key", "value"}),
    "state": frozenset({"key", "payload", "digest", "revision"}),
    "operations": frozenset(
        {
            "operation_id",
            "idempotency_key",
            "actor_id",
            "operation_kind",
            "target_scope",
            "run_scope",
            "request_commitment",
            "legacy_opaque_claim",
            "request_fingerprint",
            "payload",
            "digest",
        }
    ),
    "audit_events": frozenset({"sequence", "payload", "digest"}),
    "operation_changes": frozenset({"sequence", "operation_id", "removed"}),
    "snapshot_history_streams": frozenset({"field", "participant", "length", "head"}),
    "snapshot_history": frozenset({"field", "participant", "position", "payload", "digest"}),
}
# The tables and columns that every supported schema has; the schema migration reads them.
CORE_LOCAL_TABLES: Mapping[str, frozenset[str]] = {
    "metadata": frozenset({"key", "value"}),
    "state": frozenset({"key", "payload", "digest"}),
    "operations": frozenset({"operation_id", "idempotency_key", "request_fingerprint", "payload", "digest"}),
    "audit_events": frozenset({"payload", "digest"}),
}
# The container nesting that a stored value stays within. Admitted runtime values nest much less deeply.
# The recursive value objects that rebuild a stored value need many more frames than this limit allows.
DURABLE_MAX_NESTING = 128


def exceeds_durable_nesting(text: str, value: object) -> bool:
    """Return whether ``value``, encoded as ``text``, nests containers deeper than ``DURABLE_MAX_NESTING``.

    Each nesting level needs an opening bracket in ``text``. Thus text with few brackets needs no walk.
    """

    if text.count("{") + text.count("[") <= DURABLE_MAX_NESTING:
        return False
    level = [value] if isinstance(value, (dict, list, tuple)) else []
    for _ in range(DURABLE_MAX_NESTING):
        level = [
            child
            for item in level
            for child in (item.values() if isinstance(item, dict) else item)
            if isinstance(child, (dict, list, tuple))
        ]
        if not level:
            return False
    return True


def durable_text(value: bytes) -> str | bytes:
    """Decode one stored text value; keep undecodable bytes, which the codec refuses as damaged state.

    Valid UTF-8 decodes to the same ``str`` as the default SQLite text factory.
    """

    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value


def require_local_tables(connection: sqlite3.Connection, required: Mapping[str, frozenset[str]]) -> None:
    """Refuse a database that misses a table or a column that the store reads (EvidenceIntegrityError)."""

    for table, columns in required.items():
        present = {row[0] for row in connection.execute("SELECT name FROM pragma_table_info(?)", (table,))}
        if not columns <= present:
            raise EvidenceIntegrityError("local control-plane database is missing a required table or column")


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    """Commit all local-store changes together or roll them all back."""

    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()
        publish = getattr(connection, "publish_store_caches", None)
        if publish is not None:
            publish()


def encode_payload(payload: dict[str, Any]) -> tuple[str, str]:
    """Encode one canonical durable object with its integrity digest."""

    content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if exceeds_durable_nesting(content, payload):
        # Admission bounds each runtime value, so only a defect gives a deeper value.
        # The store does not write a value that it refuses to read.
        raise ValueError("durable value exceeds the durable nesting limit")
    return content, hashlib.sha256(content.encode("utf-8")).hexdigest()


def decode_payload(content: object, expected_digest: object, *, kind: str) -> dict[str, Any]:
    """Validate and decode one canonical durable object.

    Stored state that is not the text and digest that the store wrote raises
    ``EvidenceIntegrityError``.
    """

    if not isinstance(content, str) or not isinstance(expected_digest, str):
        raise EvidenceIntegrityError(f"{kind} failed its durable integrity check")
    actual_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if actual_digest != expected_digest:
        raise EvidenceIntegrityError(f"{kind} failed its durable integrity check")
    try:
        payload = json.loads(content)
    except (ValueError, RecursionError) as exc:
        # The digest matches, so the stored text is not a JSON value within the decoder limits.
        raise EvidenceIntegrityError(f"{kind} failed its durable integrity check") from exc
    if not isinstance(payload, dict):
        raise EvidenceIntegrityError(f"{kind} payload must be an object")
    if exceeds_durable_nesting(content, payload):
        raise EvidenceIntegrityError(f"{kind} exceeds the durable nesting limit")
    return payload


def decode_contract[T](
    content: object,
    expected_digest: object,
    *,
    kind: str,
    rebuild: Callable[[dict[str, Any]], T],
) -> T:
    """Decode one durable object and rebuild its governed value.

    The value-object validators refuse an invalid value with ``ValueError``
    (E3). For a stored object, that refusal means the durable state does not
    hold a valid value, so the store raises ``EvidenceIntegrityError`` (E9).
    """

    payload = decode_payload(content, expected_digest, kind=kind)
    try:
        return rebuild(payload)
    except ValueError as exc:
        raise EvidenceIntegrityError(f"{kind} failed its durable contract check") from exc


@contextmanager
def refuse_invalid_database() -> Iterator[None]:
    """Change a SQLite report of a malformed database file into ``EvidenceIntegrityError``."""

    try:
        yield
    except sqlite3.DatabaseError as exc:
        # The extended result code keeps the primary result code in its low byte. An error
        # that the sqlite3 module raises itself, such as use of a closed connection, has no code.
        code = getattr(exc, "sqlite_errorcode", None)
        if not isinstance(code, int) or (code & 0xFF) not in _INVALID_DATABASE_RESULT_CODES:
            raise
        raise EvidenceIntegrityError("local control-plane database file is not a valid SQLite database") from exc


__all__ = (
    "CORE_LOCAL_TABLES",
    "CURRENT_LOCAL_TABLES",
    "DURABLE_MAX_NESTING",
    "decode_contract",
    "decode_payload",
    "durable_text",
    "encode_payload",
    "exceeds_durable_nesting",
    "refuse_invalid_database",
    "require_local_tables",
    "transaction",
)
