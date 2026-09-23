"""Small SQLite boundary experiment, NOT a production RAE refinement proof."""

from pathlib import Path
import sqlite3
import threading

from witness import record


def main():
    Path(".probe-state").mkdir(exist_ok=True)
    path = ".probe-state/publication.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE outcome (id INTEGER PRIMARY KEY, state TEXT, revision INTEGER);
        CREATE TABLE audit (state TEXT);
        INSERT INTO outcome VALUES (1, 'RUNNING', 0);
    """)
    connection.close()
    barrier = threading.Barrier(3)
    cuts = []
    lock = threading.Lock()

    def settle(state):
        db = sqlite3.connect(path, timeout=3)
        barrier.wait(timeout=3)
        with db:
            cursor = db.execute(
                "UPDATE outcome SET state=?,revision=revision+1 WHERE id=1 AND state='RUNNING' AND revision=0",
                (state,),
            )
            if cursor.rowcount:
                db.execute("INSERT INTO audit VALUES (?)", (state,))
        with lock:
            cuts.append({"requested": state, "won": cursor.rowcount == 1})
        db.close()

    threads = [
        threading.Thread(target=settle, args=(state,))
        for state in ("SUCCEEDED", "CANCELLED")
    ]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=3)
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()
    db = sqlite3.connect(path)
    state = db.execute("SELECT state,revision FROM outcome").fetchone()
    audit = db.execute("SELECT state FROM audit").fetchall()
    assert sum(cut["won"] for cut in cuts) == 1
    assert audit == [(state[0],)] and state[1] == 1
    # A lost acknowledgement after commit must be resolved from persisted state.
    try:
        with db:
            db.execute("INSERT INTO outcome VALUES (2,'SUCCEEDED',1)")
            db.execute("INSERT INTO audit VALUES ('ACK-LOST-SUCCESS')")
        raise TimeoutError("synthetic acknowledgement loss AFTER durable commit")
    except TimeoutError:
        db.close()
    reopened = sqlite3.connect(path)
    readback = reopened.execute(
        "SELECT state,revision FROM outcome WHERE id=2"
    ).fetchone()
    reopened.close()
    assert readback == ("SUCCEEDED", 1)
    record(
        "publication",
        {
            "race": cuts,
            "terminal": state,
            "audit": audit,
            "lost_ack_readback": readback,
            "scope": "SQLite toy transaction boundary; no external fencing claim",
        },
    )


if __name__ == "__main__":
    main()
