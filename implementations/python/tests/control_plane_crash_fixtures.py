"""Supervised process-kill hooks delegating to real control-plane transactions."""

from __future__ import annotations

import os
import signal
from multiprocessing import get_context
from pathlib import Path
from threading import Event

from control_plane_conformance_fixtures import profile_harness
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane_store import InMemoryControlPlaneStore
from raes_runtime.control_plane_store_local import LocalControlPlaneStore

# Separate cuts around dispatch, effect and response are intentional: neither
# dispatch nor a missing response determines whether a backend effect happened.
CRASH_BOUNDARIES = (
    "before-claim",
    "after-claim-write",
    "after-claim",
    "before-invoke",
    "after-dispatch",
    "after-invoke",
    "before-terminal",
    "after-snapshot",
    "after-record",
    "after-audit",
    "after-terminal",
    "after-response",
)
UNCLAIMED = frozenset({"before-claim", "after-claim-write"})
COMMITTED = frozenset({"after-terminal", "after-response"})
APPLIED = frozenset({"after-invoke", "before-terminal", "after-snapshot", "after-record", "after-audit", *COMMITTED})


class CrashHooks:
    def __init__(self, selected: str, channel) -> None:
        self.selected, self.channel = selected, channel
        self.operation_id = ""

    def hit(self, name: str) -> None:
        if name == self.selected:
            self.channel.send((name, self.operation_id))
            # The parent kills this exact child while it is stopped at the cut.
            # A timeout is a harness failure, never successful crash evidence.
            Event().wait(90)
            raise AssertionError("supervisor did not terminate the acknowledged child")

    def install(self, store) -> None:
        claim = store.claim_record
        commit = store.commit_terminal_operation

        def claim_record(record, **options):
            self.operation_id = record.receipt.operation_id
            self.hit("before-claim")
            result = claim(record, **options)
            self.hit("after-claim")
            return result

        def commit_terminal(snapshot, record, **options):
            self.operation_id = record.receipt.operation_id
            self.hit("before-terminal")
            result = commit(snapshot, record, **options)
            self.hit("after-terminal")
            return result

        store.claim_record = claim_record
        store.commit_terminal_operation = commit_terminal
        if isinstance(store, LocalControlPlaneStore):
            self._install_sqlite_hooks(store)

    def _install_sqlite_hooks(self, store) -> None:
        upsert_record, upsert_snapshot, insert_audit = store._upsert_record, store._upsert_snapshot, store._insert_audit

        def write_record(connection, record, **options):
            upsert_record(connection, record, **options)
            self.operation_id = record.receipt.operation_id
            self.hit("after-claim-write" if record.status.state is OperationState.RUNNING else "after-record")

        def write_snapshot(connection, snapshot, **options):
            upsert_snapshot(connection, snapshot, **options)
            self.hit("after-snapshot")

        def write_audit(connection, event):
            insert_audit(connection, event)
            if event.action.endswith("_terminal"):
                self.hit("after-audit")

        store._upsert_record = write_record
        store._upsert_snapshot = write_snapshot
        store._insert_audit = write_audit


def crash_worker(profile: str, directory: str, boundary: str, channel, recovering: bool = False) -> None:
    # These are worker-topology settings, not authentication material. Avoid a
    # developer shell's unrelated service configuration changing test topology.
    for name in ("WEB_CONCURRENCY", "UVICORN_WORKERS", "UVICORN_RELOAD"):
        os.environ.pop(name, None)
    path = Path(directory)
    store = InMemoryControlPlaneStore() if profile == "P0" else LocalControlPlaneStore(path / "store")
    hooks = CrashHooks(boundary, channel)
    if recovering:
        # Initializing an existing database happens before runtime recovery.
        # Hook only terminal writes so the selected cut cannot be hit by schema
        # admission. All writes and transactions still belong to the provider.
        commit = store.commit_terminal_operation

        def recovery_commit(snapshot, record, **options):
            hooks.operation_id = record.receipt.operation_id
            hooks._install_sqlite_hooks(store)
            hooks.hit("before-terminal")
            result = commit(snapshot, record, **options)
            hooks.hit("after-terminal")
            return result

        store.commit_terminal_operation = recovery_commit
        with profile_harness(profile, path, observe=True, store=store):
            raise AssertionError("recovery did not reach its selected crash cut")
    else:
        with profile_harness(profile, path, boundary=hooks.hit, store=store) as harness:
            hooks.install(store)
            operation_id = harness.submit()
            hooks.operation_id = operation_id
            hooks.hit("after-response")
            raise AssertionError("submission did not reach its selected crash cut")


def kill_at(profile: str, path: Path, boundary: str, *, recovering: bool = False) -> str:
    context = get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(target=crash_worker, args=(profile, str(path), boundary, writer, recovering))
    process.start()
    writer.close()
    try:
        assert reader.poll(40), f"no acknowledgement for {profile}/{boundary}"
        observed_boundary, operation_id = reader.recv()
        assert observed_boundary == boundary
        assert operation_id
        assert process.is_alive(), "child exited instead of waiting at the acknowledged cut"
        process.kill()
        process.join(timeout=10)
        assert not process.is_alive()
        assert process.exitcode == (-signal.SIGKILL if os.name == "posix" else 1)
        return operation_id
    finally:
        if process.is_alive():
            process.kill()
            process.join(timeout=10)
        reader.close()
        if not process.is_alive():
            process.close()
