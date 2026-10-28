"""Atomic append-only runtime decisions using incumbent store transactions."""

from contextlib import contextmanager

from .control_plane_store_local_codec import decode_payload, encode_payload, transaction
from .runtime_decisions import require_identical_decision, validate_runtime_decision


class MemoryRuntimeDecisionStoreMixin:
    def load_runtime_decisions(self):
        with self._lock:
            # Entries were reconstructed at the append boundary. Return detached
            # copies without re-running compiler/archive validation on every
            # progress read; callers cannot mutate the retained decisions.
            return tuple(value.model_copy(deep=True) for value in self._runtime_decisions.values())

    def claim_runtime_decision(self, decision) -> bool:
        candidate = validate_runtime_decision(decision)
        with self._lock:
            existing = self._runtime_decisions.get(candidate.decision_id)
            if existing is not None:
                require_identical_decision(existing, candidate)
                return False
            self._runtime_decisions[candidate.decision_id] = candidate
            return True


class SQLRuntimeDecisionStoreMixin:
    _decision_placeholder = "?"

    @contextmanager
    def _decision_transaction(self):
        with self._connection() as connection:
            cut = transaction(connection) if self._decision_placeholder == "?" else connection.transaction()
            with cut:
                yield connection

    def load_runtime_decisions(self):
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT decision_id, payload, digest FROM runtime_decisions ORDER BY decision_id"
            ).fetchall()
        decisions = []
        for identity, content, digest in rows:
            decision = validate_runtime_decision(decode_payload(content, digest, kind="runtime decision"))
            if decision.decision_id != identity:
                raise ValueError("runtime decision identity does not match its durable key")
            decisions.append(decision)
        return tuple(decisions)

    def claim_runtime_decision(self, decision) -> bool:
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
            existing = validate_runtime_decision(decode_payload(*row, kind="runtime decision"))
            require_identical_decision(existing, candidate)
            return inserted


def initialize_runtime_decisions(connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS runtime_decisions(decision_id TEXT PRIMARY KEY, "
        "payload TEXT NOT NULL, digest TEXT NOT NULL)"
    )
