"""CP-5 single-owner store admission and immutable scope tests."""

from __future__ import annotations

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from multiprocessing import get_context
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.planning import EvaluationPlan
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime import control_plane_store_local as local_store_module
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_memory import InMemoryControlPlaneStore
from starlette.testclient import TestClient

pytestmark = pytest.mark.control_plane_conformance


def _competing_runtime_result(store_path: str, queue: object) -> None:
    try:
        control_plane = RuntimeControlPlane(
            create_stub_target(),
            store=LocalControlPlaneStore(Path(store_path)),
        )
    except RuntimeError as exc:
        queue.put(str(exc))  # type: ignore[attr-defined]
        return
    control_plane.close()
    queue.put("acquired")  # type: ignore[attr-defined]


def test_local_store_constructor_is_inert_until_runtime_admission(tmp_path: Path) -> None:
    store_path = tmp_path / "control-plane"

    store = LocalControlPlaneStore(store_path)

    assert not store_path.exists()
    with pytest.raises(RuntimeError, match="runtime admission"):
        store.load_snapshot()


def test_runtime_admission_binds_and_reopens_one_immutable_scope(tmp_path: Path) -> None:
    store_path = tmp_path / "control-plane"
    target = create_stub_target()

    first = RuntimeControlPlane(target, store=LocalControlPlaneStore(store_path), run_scope="run:first")
    first.close()

    with sqlite3.connect(store_path / "control-plane.sqlite3") as connection:
        assert dict(
            connection.execute("SELECT key, value FROM metadata WHERE key IN ('target-scope', 'run-scope')").fetchall()
        ) == {"target-scope": f"target:{target.name}", "run-scope": "run:first"}

    reopened = RuntimeControlPlane(target, store=LocalControlPlaneStore(store_path), run_scope="run:first")
    reopened.close()

    second_run_store = LocalControlPlaneStore(store_path)
    with pytest.raises(RuntimeError, match="scope does not match"):
        RuntimeControlPlane(target, store=second_run_store, run_scope="run:second")

    other_target = replace(target, name="other")
    other_target_store = LocalControlPlaneStore(store_path)
    with pytest.raises(RuntimeError, match="scope does not match"):
        RuntimeControlPlane(other_target, store=other_target_store, run_scope="run:first")


def test_scope_mismatch_fails_before_schema_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_path = tmp_path / "control-plane"
    owner = RuntimeControlPlane(
        create_stub_target(),
        store=LocalControlPlaneStore(store_path),
        run_scope="run:first",
    )
    owner.close()
    monkeypatch.setattr(
        local_store_module,
        "migrate_sqlite_schema",
        lambda *_args, **_kwargs: pytest.fail("scope mismatch must precede schema migration"),
    )

    target = create_stub_target()
    mismatched_store = LocalControlPlaneStore(store_path)
    with pytest.raises(RuntimeError, match="scope does not match"):
        RuntimeControlPlane(target, store=mismatched_store, run_scope="run:second")


def test_unscoped_store_is_adopted_once_and_partial_scope_fails_closed(tmp_path: Path) -> None:
    unscoped_path = tmp_path / "unscoped"
    unscoped_path.mkdir(mode=0o700)
    unscoped_database = unscoped_path / "control-plane.sqlite3"
    with sqlite3.connect(unscoped_database) as connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    if os.name != "nt":
        unscoped_database.chmod(0o600)

    adopted = RuntimeControlPlane(
        create_stub_target(),
        store=LocalControlPlaneStore(unscoped_path),
        run_scope="run:adopted",
    )
    adopted.close()
    with sqlite3.connect(unscoped_database) as connection:
        assert dict(
            connection.execute("SELECT key, value FROM metadata WHERE key IN ('target-scope', 'run-scope')").fetchall()
        ) == {"target-scope": "target:stub", "run-scope": "run:adopted"}

    partial_path = tmp_path / "partial"
    partial_path.mkdir(mode=0o700)
    partial_database = partial_path / "control-plane.sqlite3"
    with sqlite3.connect(partial_database) as connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO metadata(key, value) VALUES ('target-scope', 'target:stub')")
    if os.name != "nt":
        partial_database.chmod(0o600)

    target = create_stub_target()
    partial_store = LocalControlPlaneStore(partial_path)
    with pytest.raises(RuntimeError, match="scope metadata is incomplete"):
        RuntimeControlPlane(target, store=partial_store, run_scope="run:adopted")


def test_duplicate_scope_metadata_fails_closed_before_store_reads(tmp_path: Path) -> None:
    store_path = tmp_path / "duplicate"
    store_path.mkdir(mode=0o700)
    database = store_path / "control-plane.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE metadata (key TEXT NOT NULL, value TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            (
                ("target-scope", "target:stub"),
                ("target-scope", "target:other"),
                ("run-scope", "run:default"),
            ),
        )
    if os.name != "nt":
        database.chmod(0o600)

    target = create_stub_target()
    duplicate_store = LocalControlPlaneStore(store_path)
    with pytest.raises(RuntimeError, match="scope metadata contains duplicate keys"):
        RuntimeControlPlane(target, store=duplicate_store)


@pytest.mark.integration
def test_second_process_fails_before_accessing_the_owned_store(tmp_path: Path) -> None:
    store_path = tmp_path / "control-plane"
    owner = RuntimeControlPlane(create_stub_target(), store=LocalControlPlaneStore(store_path))
    context = get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=_competing_runtime_result, args=(str(store_path), queue))
    process.start()
    process.join(timeout=15)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
    try:
        assert process.exitcode == 0
        assert "exactly one worker" in queue.get(timeout=2)
    finally:
        owner.close()


def test_request_run_scope_cannot_widen_the_admitted_store_scope(tmp_path: Path) -> None:
    control_plane = RuntimeControlPlane(
        create_stub_target(),
        store=LocalControlPlaneStore(tmp_path / "control-plane"),
        run_scope="run:admitted",
    )
    request = EvaluationPlan(run_id="different")

    try:
        with pytest.raises(ValueError, match="run scope does not match"):
            control_plane.submit_evaluation(request)
    finally:
        control_plane.close()


class _OrderedCloseStore(InMemoryControlPlaneStore):
    def __init__(self, events: list[str], *, fail_close: bool = False) -> None:
        super().__init__()
        self.events = events
        self.fail_close = fail_close
        self.lease = SimpleNamespace(
            closed=False,
            assert_owner=lambda: None,
        )

        def close_lease() -> None:
            self.lease.closed = True
            self.events.append("lease-close")

        self.lease.close = close_lease

    def admit_runtime(self, *, target_scope: str, run_scope: str) -> object:
        self.events.append(f"admit:{target_scope}:{run_scope}")
        return self.lease

    def close(self) -> None:
        self.events.append("provider-close")
        if self.fail_close:
            raise RuntimeError("provider close failed")


def test_runtime_closes_provider_before_releasing_lease() -> None:
    events: list[str] = []
    control_plane = RuntimeControlPlane(create_stub_target(), store=_OrderedCloseStore(events))

    control_plane.close()

    assert events[-2:] == ["provider-close", "lease-close"]


def test_provider_close_failure_retains_lease_and_poison_runtime() -> None:
    events: list[str] = []
    store = _OrderedCloseStore(events, fail_close=True)
    control_plane = RuntimeControlPlane(create_stub_target(), store=store)

    with pytest.raises(RuntimeError, match="provider close failed"):
        control_plane.close()

    assert store.lease.closed is False
    with pytest.raises(RuntimeError, match="requires restart"):
        control_plane.get_snapshot()


def test_concurrent_close_callers_do_not_deadlock_after_provider_failure() -> None:
    active_call_entered = Event()
    release_active_call = Event()
    close_calls = 0

    class _FailedCloseStore(_OrderedCloseStore):
        def close(self) -> None:
            nonlocal close_calls
            close_calls += 1
            raise RuntimeError("provider close failed")

    control_plane = RuntimeControlPlane(create_stub_target(), store=_FailedCloseStore([]))

    def hold_runtime_call() -> None:
        with control_plane._runtime_call():
            active_call_entered.set()
            assert release_active_call.wait(timeout=5)

    def wait_for_close_waiters(expected: int) -> None:
        deadline = monotonic() + 5
        while len(getattr(control_plane._lifecycle_condition, "_waiters", ())) < expected:
            if monotonic() >= deadline:
                pytest.fail(f"expected {expected} concurrent close waiters")
            sleep(0.001)

    with ThreadPoolExecutor(max_workers=3) as executor:
        active_call = executor.submit(hold_runtime_call)
        assert active_call_entered.wait(timeout=5)
        first = executor.submit(control_plane.close)
        wait_for_close_waiters(1)
        second = executor.submit(control_plane.close)
        wait_for_close_waiters(2)
        release_active_call.set()
        active_call.result(timeout=5)
        for result in (first, second):
            with pytest.raises(RuntimeError, match="provider close failed"):
                result.result(timeout=5)

    assert close_calls == 2


@pytest.mark.parametrize("target_name", ["", "x" * 250])
def test_invalid_target_name_is_rejected_before_store_admission(tmp_path: Path, target_name: str) -> None:
    store_path = tmp_path / "control-plane"
    target = replace(create_stub_target(), name=target_name)
    store = LocalControlPlaneStore(store_path)

    with pytest.raises(ValueError, match="runtime target name"):
        RuntimeControlPlane(target, store=store)

    assert not store_path.exists()


def test_control_plane_api_lifespan_closes_the_owned_runtime() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())

    with TestClient(create_control_plane_app(control_plane)):
        assert control_plane.get_snapshot().snapshot == RuntimeSnapshot()

    with pytest.raises(RuntimeError, match="closed"):
        control_plane.get_snapshot()


def test_control_plane_api_rejects_multiple_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    control_plane = RuntimeControlPlane(create_stub_target())

    with pytest.raises(RuntimeError, match="exactly one worker"):
        create_control_plane_app(control_plane)

    control_plane.close()


@pytest.mark.parametrize("run_scope", ["default", "run:", "run:contains space"])
def test_control_plane_rejects_non_normalized_or_invalid_run_scope(run_scope: str) -> None:
    target = create_stub_target()
    with pytest.raises(ValueError, match="run_scope|run_id"):
        RuntimeControlPlane(target, run_scope=run_scope)
