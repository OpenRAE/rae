"""Provider-private history rows; portable snapshot JSON remains complete."""

from __future__ import annotations

from raes_contracts.immutable_history import HISTORY_FIELDS, HistoryMap, seal_history

from .control_plane_store_local_codec import decode_payload, encode_payload


def initialize_history_rows(connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS snapshot_history_streams (field TEXT NOT NULL, participant TEXT NOT NULL, "
        "length INTEGER NOT NULL, head TEXT NOT NULL, PRIMARY KEY(field, participant))"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS snapshot_history (field TEXT NOT NULL, participant TEXT NOT NULL, "
        "position INTEGER NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(field, participant, position))"
    )
    connection.execute("INSERT OR IGNORE INTO metadata(key,value) VALUES ('snapshot-history-generation','0')")
    for table in ("state", "snapshot_history", "snapshot_history_streams"):
        for event in ("INSERT", "UPDATE", "DELETE"):
            # Fixed provider identifiers; values are never supplied by callers.
            connection.execute(
                f"CREATE TRIGGER IF NOT EXISTS history_generation_{table}_{event} AFTER {event} ON {table} "  # noqa: S608 -- fixed provider identifiers
                "BEGIN UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='snapshot-history-generation'; END"
            )


def history_generation(connection):
    from .control_plane_store_local_invocations import LocalInvocationStoreMixin

    row = connection.execute("SELECT value FROM metadata WHERE key='snapshot-history-generation'").fetchone()
    return 0 if row is None else LocalInvocationStoreMixin._generation(row[0])


def persist_history_rows(connection, snapshot) -> None:
    prior = {
        (field, participant): (length, head)
        for field, participant, length, head in connection.execute(
            "SELECT field, participant, length, head FROM snapshot_history_streams"
        )
    }
    retained = set()
    for field in HISTORY_FIELDS:
        histories = seal_history(field, getattr(snapshot, field))
        for participant, records in histories.items():
            key = (field, participant)
            retained.add(key)
            length, head = prior.get(key, (0, records.prefix_digest(0)))
            if length > len(records) or records.prefix_digest(length) != head:
                connection.execute("DELETE FROM snapshot_history WHERE field=? AND participant=?", key)
                length = 0
            for position in range(length, len(records)):
                payload, digest = encode_payload(records[position])
                connection.execute(
                    "INSERT INTO snapshot_history(field, participant, position, payload, digest) VALUES (?, ?, ?, ?, ?)",
                    (*key, position, payload, digest),
                )
            current_head = records.prefix_digest(len(records))
            if prior.get(key) != (len(records), current_head):
                connection.execute(
                    "INSERT INTO snapshot_history_streams(field, participant, length, head) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(field, participant) DO UPDATE SET length=excluded.length, head=excluded.head",
                    (*key, len(records), current_head),
                )
    for key in prior.keys() - retained:
        connection.execute("DELETE FROM snapshot_history WHERE field=? AND participant=?", key)
        connection.execute("DELETE FROM snapshot_history_streams WHERE field=? AND participant=?", key)


def restore_history_rows(connection, payload: dict) -> dict:
    marker = connection.execute("SELECT value FROM metadata WHERE key='snapshot-history-format'").fetchone()
    if marker is None:
        return payload
    if marker != ("1",):
        raise ValueError("snapshot history format is unsupported")
    histories = {field: HistoryMap(field, {}) for field in HISTORY_FIELDS}
    streams = connection.execute(
        "SELECT field, participant, length, head FROM snapshot_history_streams ORDER BY field, participant"
    ).fetchall()
    count = connection.execute("SELECT COUNT(*) FROM snapshot_history").fetchone()[0]
    if count != sum(length for _, _, length, _ in streams):
        raise ValueError("snapshot history contains unbound records")
    for field, participant, length, head in streams:
        if field not in histories or type(length) is not int or length < 0:
            raise ValueError("snapshot history stream coordinates are invalid")
        rows = connection.execute(
            "SELECT position, payload, digest FROM snapshot_history WHERE field=? AND participant=? ORDER BY position",
            (field, participant),
        ).fetchall()
        if len(rows) != length or any(position != index for index, (position, _, _) in enumerate(rows)):
            raise ValueError("snapshot history stream is incomplete")
        records = [decode_payload(content, digest, kind="snapshot history record") for _, content, digest in rows]
        histories[field] = histories[field].append(participant, records)
        if histories[field][participant].prefix_digest(length) != head:
            raise ValueError("snapshot history stream failed its prefix integrity check")
    if any(payload.get(field) for field in HISTORY_FIELDS):
        raise ValueError("normalized snapshot header contains duplicate history")
    return {**payload, **histories}


def require_empty_history_without_snapshot(connection) -> None:
    if connection.execute("SELECT COUNT(*) FROM snapshot_history_streams").fetchone()[0]:
        raise ValueError("snapshot history has no committed snapshot header")
    if connection.execute("SELECT COUNT(*) FROM snapshot_history").fetchone()[0]:
        raise ValueError("snapshot history has no committed snapshot header")
