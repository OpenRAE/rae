"""Atomic append-only runtime decisions using incumbent store transactions."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from raes_contracts.errors import ConflictError, EvidenceIntegrityError

from .control_plane_store_local_codec import decode_contract, encode_payload, transaction
from .runtime_decisions import require_identical_decision, validate_runtime_decision

_DECISION_KIND = "runtime decision"

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from sqlite3 import Connection as SQLiteConnection

    from psycopg import Connection as PostgreSQLConnection

    from .runtime_decisions import RuntimeDecision


class MemoryRuntimeDecisionStoreMixin:
    def load_runtime_decisions(self) -> tuple[RuntimeDecision, ...]:
        with self._lock:
            # Entries were reconstructed at the append boundary. Return detached
            # copies without re-running compiler/archive validation on every
            # progress read; callers cannot mutate the retained decisions.
            return tuple(value.model_copy(deep=True) for value in self._runtime_decisions.values())

    def claim_runtime_decision(self, decision: object) -> bool:
        candidate = validate_runtime_decision(decision)
        with self._lock:
            existing = self._runtime_decisions.get(candidate.decision_id)
            if existing is not None:
                require_identical_decision(existing, candidate)
                return False
            self._runtime_decisions[candidate.decision_id] = candidate
            return True

    def claim_runtime_decisions(self, decisions: tuple[object, ...], *, expected_ids: tuple[str, ...]) -> bool:
        """Compare and append one bounded decision cut without partial writes."""
        candidates = decision_candidates(decisions)
        with self._lock:
            if not require_decision_cut(self._runtime_decisions, candidates, expected_ids):
                return False
            self._runtime_decisions.update({item.decision_id: item for item in candidates})
            return True


class SQLRuntimeDecisionStoreMixin:
    _decision_placeholder = "?"

    @contextmanager
    def _decision_transaction(self) -> Iterator[SQLiteConnection | PostgreSQLConnection[tuple[object, ...]]]:
        with self._connection() as connection:
            cut = transaction(connection) if self._decision_placeholder == "?" else connection.transaction()
            with cut:
                if self._decision_placeholder != "?":
                    # All append paths share this lock, including cancellation.
                    connection.execute("LOCK TABLE runtime_decisions IN SHARE ROW EXCLUSIVE MODE")
                yield connection

    def load_runtime_decisions(self) -> tuple[RuntimeDecision, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT decision_id, payload, digest FROM runtime_decisions ORDER BY decision_id"
            ).fetchall()
        return decisions_from_rows(rows)

    def claim_runtime_decisions(self, decisions: tuple[object, ...], *, expected_ids: tuple[str, ...]) -> bool:
        candidates = decision_candidates(decisions)
        encoded = [(item.decision_id, *encode_payload(item.model_dump(mode="json"))) for item in candidates]
        insert = (
            "INSERT INTO runtime_decisions(decision_id, payload, digest) VALUES (?, ?, ?)"
            if self._decision_placeholder == "?"
            else "INSERT INTO runtime_decisions(decision_id, payload, digest) VALUES (%s, %s, %s)"
        )
        with self._decision_transaction() as connection:
            rows = connection.execute("SELECT decision_id, payload, digest FROM runtime_decisions").fetchall()
            existing = {item.decision_id: item for item in decisions_from_rows(rows)}
            if not require_decision_cut(existing, candidates, expected_ids):
                return False
            for values in encoded:
                if values[0] not in existing:
                    connection.execute(insert, values)
            return True

    def claim_runtime_decision(self, decision: object) -> bool:
        candidate = validate_runtime_decision(decision)
        content, digest = encode_payload(candidate.model_dump(mode="json"))
        insert, select = (
            (
                "INSERT INTO runtime_decisions(decision_id, payload, digest) VALUES (?, ?, ?) "
                "ON CONFLICT(decision_id) DO NOTHING",
                "SELECT payload, digest FROM runtime_decisions WHERE decision_id=?",
            )
            if self._decision_placeholder == "?"
            else (
                "INSERT INTO runtime_decisions(decision_id, payload, digest) VALUES (%s, %s, %s) "
                "ON CONFLICT(decision_id) DO NOTHING",
                "SELECT payload, digest FROM runtime_decisions WHERE decision_id=%s",
            )
        )
        with self._decision_transaction() as connection:
            cursor = connection.execute(
                insert,
                (candidate.decision_id, content, digest),
            )
            inserted = cursor.rowcount == 1
            row = connection.execute(
                select,
                (candidate.decision_id,),
            ).fetchone()
            existing = decode_contract(*row, kind=_DECISION_KIND, rebuild=validate_runtime_decision)
            require_identical_decision(existing, candidate)
            return inserted


def initialize_runtime_decisions(connection: SQLiteConnection | PostgreSQLConnection[tuple[object, ...]]) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS runtime_decisions(decision_id TEXT PRIMARY KEY, "
        "payload TEXT NOT NULL, digest TEXT NOT NULL)"
    )


def decision_candidates(decisions: tuple[object, ...]) -> tuple[RuntimeDecision, ...]:
    if not isinstance(decisions, tuple) or not 1 <= len(decisions) <= 64:
        raise ValueError("runtime decision cuts require a bounded nonempty tuple")
    candidates = tuple(validate_runtime_decision(item) for item in decisions)
    if len({item.decision_id for item in candidates}) != len(candidates):
        raise ValueError("runtime decision cuts require unique identities")
    return candidates


def require_decision_cut(
    existing: dict[str, RuntimeDecision], candidates: tuple[RuntimeDecision, ...], expected_ids: tuple[str, ...]
) -> bool:
    for item in candidates:
        if item.decision_id in existing:
            require_identical_decision(existing[item.decision_id], item)
    if all(item.decision_id in existing for item in candidates):
        return False
    if not isinstance(expected_ids, tuple) or set(expected_ids) != existing.keys():
        raise ConflictError("runtime decision set changed before admission")
    return True


def decisions_from_rows(rows: Iterable[tuple[str, str, str]]) -> tuple[RuntimeDecision, ...]:
    decisions = []
    for identity, content, digest in rows:
        decision = decode_contract(content, digest, kind=_DECISION_KIND, rebuild=validate_runtime_decision)
        if decision.decision_id != identity:
            raise EvidenceIntegrityError("runtime decision identity does not match its durable key")
        decisions.append(decision)
    return tuple(decisions)
