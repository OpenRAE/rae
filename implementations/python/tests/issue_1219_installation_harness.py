"""Execute issue #1219's real-lock local qualification cases."""

from __future__ import annotations

import errno
import hashlib
import json
import multiprocessing
import platform
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import verified_tool_installation as installation

PAYLOAD = b"issue-1219-reviewed-local-tool"
CHECKPOINTS = ("staged-written", "staged-durable", "published", "parent-durable")


def _entry(path: str, payload: bytes, *, executable: bool) -> SimpleNamespace:
    return SimpleNamespace(
        path=path,
        sha256=hashlib.sha256(payload).hexdigest(),
        size=len(payload),
        executable=executable,
    )


def _selection() -> SimpleNamespace:
    system = {"Linux": "linux", "Darwin": "macos"}[platform.system()]
    machine = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "x86_64"}[platform.machine().lower()]
    return SimpleNamespace(
        artifact_id="conftest",
        platform_id=f"{system}-{machine}",
        policy_refs=("artifact-integrity-v1",),
        raw_manifest=(_entry("conftest", PAYLOAD, executable=False),),
        installed_manifest=(_entry("conftest", PAYLOAD, executable=True),),
    )


def _ensure(root: Path, acquire: Any = None) -> Path:
    return installation.ensure_verified_installation(
        root,
        _selection(),
        acquire=acquire or (lambda: PAYLOAD),
        materialize=installation.materialize_direct,
    )


def _worker(
    root_text: str,
    result_queue: multiprocessing.Queue,
    start: Any = None,
    acquisitions: Any = None,
    lock_timeout: float | None = None,
) -> None:
    try:
        if lock_timeout is not None:
            installation.LOCK_TIMEOUT_SECONDS = lock_timeout
        if start is not None:
            start.wait(10)

        def acquire() -> bytes:
            if acquisitions is not None:
                with acquisitions.get_lock():
                    acquisitions.value += 1
            time.sleep(0.03)
            return PAYLOAD

        result = _ensure(Path(root_text), acquire)
        result_queue.put({"path": str(result), "payload": result.read_bytes().hex()})
    except BaseException as exc:  # noqa: BLE001 - the parent must observe exact worker failure.
        result_queue.put({"error": f"{type(exc).__name__}:{exc}"})


def _crashing_worker(
    root_text: str,
    checkpoint: str,
    reached: Any,
) -> None:
    def pause_at_checkpoint(name: str, _path: Path) -> None:
        if name == checkpoint:
            reached.set()
            while True:
                time.sleep(1)

    installation._publication_checkpoint = pause_at_checkpoint
    _ensure(Path(root_text))


def _assert_worker_result(result: dict[str, str]) -> str:
    if "error" in result:
        raise AssertionError(result["error"])
    if bytes.fromhex(result["payload"]) != PAYLOAD:
        raise AssertionError("worker observed non-reviewed bytes")
    return result["path"]


def _cold_convergence(root: Path) -> float:
    root.mkdir(parents=True, mode=0o700)
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    start = context.Event()
    acquisitions = context.Value("i", 0)
    processes = [
        context.Process(target=_worker, args=(str(root), result_queue, start, acquisitions)) for _ in range(32)
    ]
    began = time.monotonic()
    for process in processes:
        process.start()
    start.set()
    results = [result_queue.get(timeout=30) for _ in processes]
    for process in processes:
        process.join(30)
        if process.exitcode != 0:
            raise AssertionError(f"cold worker exited {process.exitcode}")
    paths = {_assert_worker_result(result) for result in results}
    if len(paths) != 1 or acquisitions.value != 1:
        raise AssertionError(f"cold convergence failed: paths={len(paths)} acquisitions={acquisitions.value}")
    return time.monotonic() - began


def _warm_validation(root: Path) -> float:
    installed = _ensure(root)
    began = time.monotonic()
    with ThreadPoolExecutor(max_workers=32) as executor:
        paths = list(executor.map(lambda _index: _ensure(root), range(100)))
    if any(path != installed or path.read_bytes() != PAYLOAD for path in paths):
        raise AssertionError("warm clients diverged")
    return time.monotonic() - began


def _crash_recovery(root: Path) -> float:
    root.mkdir(parents=True, mode=0o700)
    context = multiprocessing.get_context("spawn")
    began = time.monotonic()
    for index, checkpoint in enumerate(CHECKPOINTS):
        case_root = root / str(index)
        case_root.mkdir(mode=0o700)
        reached = context.Event()
        process = context.Process(target=_crashing_worker, args=(str(case_root), checkpoint, reached))
        process.start()
        if not reached.wait(15):
            process.kill()
            process.join(5)
            raise AssertionError(f"publisher did not reach {checkpoint}")
        process.kill()
        process.join(5)
        if process.is_alive():
            raise AssertionError(f"publisher survived kill at {checkpoint}")
        target = installation.installation_tree_path(installation.default_installation_root(case_root), _selection())
        durability_calls: list[Path] = []
        original_fsync_directory = installation._fsync_directory

        def observe_fsync(
            path: Path,
            calls: list[Path] = durability_calls,
            fsync_directory: Any = original_fsync_directory,
        ) -> None:
            calls.append(path)
            fsync_directory(path)

        installation._fsync_directory = observe_fsync
        try:
            installed = _ensure(case_root)
        finally:
            installation._fsync_directory = original_fsync_directory
        if installed.read_bytes() != PAYLOAD:
            raise AssertionError(f"recovery produced wrong bytes after {checkpoint}")
        target_parent = target.parent
        if target_parent not in durability_calls:
            raise AssertionError(f"recovery did not make the publication parent durable after {checkpoint}")
        if list(target_parent.glob(".stage-*")):
            raise AssertionError(f"staging remained after recovery at {checkpoint}")
    return time.monotonic() - began


def _live_publisher_exclusion(root: Path) -> float:
    root.mkdir(parents=True, mode=0o700)
    context = multiprocessing.get_context("spawn")
    reached = context.Event()
    publisher = context.Process(target=_crashing_worker, args=(str(root), "staged-durable", reached))
    began = time.monotonic()
    publisher.start()
    if not reached.wait(15):
        publisher.kill()
        publisher.join(5)
        raise AssertionError("publisher did not reach durable staging")
    result_queue = context.Queue()
    survivor = context.Process(target=_worker, args=(str(root), result_queue))
    survivor.start()
    time.sleep(0.3)
    if not survivor.is_alive():
        result = result_queue.get(timeout=1)
        raise AssertionError(f"survivor bypassed a live publisher: {result}")
    publisher.kill()
    publisher.join(5)
    result = result_queue.get(timeout=15)
    survivor.join(15)
    if survivor.exitcode != 0:
        raise AssertionError(f"survivor exited {survivor.exitcode}")
    _assert_worker_result(result)
    return time.monotonic() - began


def _bounded_lock_timeout(root: Path) -> float:
    root.mkdir(parents=True, mode=0o700)
    context = multiprocessing.get_context("spawn")
    reached = context.Event()
    publisher = context.Process(target=_crashing_worker, args=(str(root), "staged-durable", reached))
    began = time.monotonic()
    publisher.start()
    if not reached.wait(15):
        publisher.kill()
        publisher.join(5)
        raise AssertionError("publisher did not reach durable staging")
    result_queue = context.Queue()
    contender = context.Process(target=_worker, args=(str(root), result_queue, None, None, 0.2))
    contender.start()
    result = result_queue.get(timeout=5)
    contender.join(5)
    if result.get("error") != "RuntimeError:tool-installation: lock-timeout":
        raise AssertionError(f"contender did not time out safely: {result}")
    publisher.kill()
    publisher.join(5)
    if _ensure(root).read_bytes() != PAYLOAD:
        raise AssertionError("dead lock owner prevented recovery")
    return time.monotonic() - began


def _unsafe_lock_rejection(root: Path) -> float:
    root.mkdir(parents=True, mode=0o700)
    began = time.monotonic()

    def unavailable() -> bytes:
        raise RuntimeError("qualification-acquisition-unavailable")

    try:
        _ensure(root, unavailable)
    except RuntimeError as exc:
        if str(exc) != "qualification-acquisition-unavailable":
            raise
    else:
        raise AssertionError("setup acquisition unexpectedly succeeded")
    target = installation.installation_tree_path(installation.default_installation_root(root), _selection())
    lock = installation.default_installation_root(root) / "conftest" / ".locks" / f"install-{target.name}.lock"
    lock.unlink()
    outside = root / "outside-lock-target"
    outside.write_bytes(b"unchanged")
    lock.symlink_to(outside)
    try:
        _ensure(root, unavailable)
    except RuntimeError as exc:
        if str(exc) != "tool-installation: unsafe-lock-file":
            raise
    else:
        raise AssertionError("unsafe lock path was accepted")
    if outside.read_bytes() != b"unchanged":
        raise AssertionError("unsafe lock target was modified")
    return time.monotonic() - began


def _quota_failure_recovery(root: Path) -> float:
    root.mkdir(parents=True, mode=0o700)
    began = time.monotonic()
    original = installation._write_file

    def disk_full(_path: Path, _payload: bytes) -> None:
        raise OSError(errno.ENOSPC, "qualification disk quota")

    installation._write_file = disk_full
    try:
        try:
            _ensure(root)
        except RuntimeError as exc:
            if str(exc) != "tool-installation: storage-exhausted":
                raise
        else:
            raise AssertionError("quota failure was not terminal")
    finally:
        installation._write_file = original
    target = installation.installation_tree_path(installation.default_installation_root(root), _selection())
    if target.exists() or list(target.parent.glob(".stage-*")):
        raise AssertionError("quota failure exposed partial state")
    if _ensure(root).read_bytes() != PAYLOAD:
        raise AssertionError("quota recovery produced wrong bytes")
    return time.monotonic() - began


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    cases = {
        "cold-convergence": _cold_convergence(root / "cold"),
        "warm-validation": _warm_validation(root / "cold"),
        "crash-recovery": _crash_recovery(root / "crashes"),
        "live-publisher-exclusion": _live_publisher_exclusion(root / "live"),
        "bounded-lock-timeout": _bounded_lock_timeout(root / "timeout"),
        "unsafe-lock-rejection": _unsafe_lock_rejection(root / "unsafe-lock"),
        "quota-failure-recovery": _quota_failure_recovery(root / "quota"),
    }
    evidence = {
        "schema": "issue-1219-local-installation-qualification/v1",
        "installation_policy": installation.INSTALLATION_POLICY_ID,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "filesystem": installation._filesystem_type(root),
        "filelock": version("filelock"),
        "cold_processes": 32,
        "warm_clients": 100,
        "crash_checkpoints": list(CHECKPOINTS),
        "passed_cases": list(cases),
        "coverage": {
            "scope": "generic-cli-installation-mechanism",
            "fixture": "synthetic-direct-carrier",
            "canonical_cases": {
                "T05": "local-cli-process-and-crash-slice-only",
                "T06": "local-owner-and-hostile-filesystem-slice-only",
                "T07": "local-cli-client-and-storage-failure-slice-only",
                "T16": "local-install-read-and-promotion-slice-only",
            },
            "canonical_outcome_recorded": False,
        },
        "elapsed_seconds": {name: round(elapsed, 3) for name, elapsed in cases.items()},
        "limitations": [
            "This local harness does not claim the distinct-principal T06 execution case.",
            "Service, proof, OCI, export, and broader T05/T07/T16 cases remain downstream scope.",
        ],
    }
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
