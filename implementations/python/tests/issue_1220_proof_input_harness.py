"""Execute issue #1220's proof-input qualification slices.

The harness runs the real portable lock, real processes, real crashes, real
filesystem durability calls, and, when Bubblewrap can create a network
namespace, a real egress-denied admission. Its evidence names local slices and
never records a canonical passed T05/T11/T13 case.
"""

from __future__ import annotations

import argparse
import errno
import gzip
import hashlib
import io
import json
import multiprocessing
import os
import platform
import shutil
import socket
import subprocess
import sys
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from importlib.metadata import version
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import isabelle_tool  # noqa: E402
from tools import maintained_client_acquisition as client  # noqa: E402
from tools import verified_tool_installation as installation  # noqa: E402
from tools import verified_tree_archive as tree_archive  # noqa: E402
from tools import verified_tree_installation as tree_installation  # noqa: E402
from tools.tooling_policy_gate import (  # noqa: E402
    LockedArtifactSelection,
    LockedInstalledTree,
    LockedManifestEntry,
)

SCHEMA = "issue-1220-proof-input-qualification/v1"
ROOT = f"Isabelle{isabelle_tool.ISABELLE_VERSION}"
BINARY = b"#!/bin/sh\nexit 0\n"
BWRAP = Path("/usr/bin/bwrap")
CHECKPOINTS = (
    "raw-staged-durable",
    "raw-published",
    "staged-written",
    "staged-durable",
    *(("renamed-unsealed",) if installation._directory_rename_requires_writable_source() else ()),
    "published",
    "parent-durable",
)
# The closed slice names this harness can emit; qualification evidence rejects any other.
SLICE_CASE_NAMES = (
    "T05-cold-convergence",
    "T05-warm-validation",
    "T05-crash-recovery",
    "T05-live-publisher-exclusion",
    "T05-bounded-lock-timeout",
    "T05-quota-failure-recovery",
    "T05-real-cold-convergence",
    "T05-real-crash-recovery",
    "T05-real-live-publisher-exclusion",
    "T11-egress-denied-admission",
    "T13-corrupt-local-input",
    "T13-malicious-archive",
    "T13-missing-native-closure",
)
COLD_PROCESSES = 32
WARM_CLIENTS = 100
CASE_WAIT_SECONDS = 120


def _tar_member(name: str, *, kind: bytes, payload: bytes = b"", mode: int = 0o644, target: str = "") -> tuple:
    member = tarfile.TarInfo(name)
    member.type = kind
    member.mode = mode
    member.mtime = 0
    member.linkname = target
    member.size = len(payload) if kind == tarfile.REGTYPE else 0
    return member, payload if kind == tarfile.REGTYPE else None


def _archive_bytes(extra: tuple = ()) -> bytes:
    """Return a deterministic tree carrying the real distribution's shape classes."""

    members = [
        _tar_member(ROOT, kind=tarfile.DIRTYPE, mode=0o755),
        _tar_member(f"{ROOT}/bin/isabelle", kind=tarfile.REGTYPE, payload=BINARY, mode=0o755),
    ]
    for module in range(24):
        members.append(
            _tar_member(
                f"{ROOT}/contrib/module-{module}/lib/payload.jar",
                kind=tarfile.REGTYPE,
                payload=hashlib.sha256(f"module-{module}".encode()).digest() * 64,
            )
        )
        members.append(
            _tar_member(
                f"{ROOT}/contrib/module-{module}/legal/LICENSE",
                kind=tarfile.SYMTYPE,
                target="../../module-0/lib/payload.jar",
            )
        )
    members.append(_tar_member(f"{ROOT}/src/lib/ABSENT.a", kind=tarfile.SYMTYPE, target="../ABSENT/ABSENT.a"))
    members.extend(extra)
    buffer = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        for member, payload in members:
            archive.addfile(member, io.BytesIO(payload) if payload is not None else None)
    return buffer.getvalue()


def _selection(archive: Path, tree: LockedInstalledTree | None = None) -> LockedArtifactSelection:
    payload = archive.read_bytes()
    raw = LockedManifestEntry(archive.name, hashlib.sha256(payload).hexdigest(), len(payload))
    if tree is None:
        tree = LockedInstalledTree(**tree_installation.describe_archive_tree(archive, raw))
    return LockedArtifactSelection(
        artifact_id="isabelle",
        artifact_class="native-tool",
        version=isabelle_tool.ISABELLE_VERSION,
        platform_id="linux-x86_64",
        profile_id="proof-linux-x86_64",
        repository="https://qualification.invalid/isabelle",
        release=ROOT,
        source_urls=("https://qualification.invalid/Isabelle.tar.gz",),
        locator_refs=("qualification-primary",),
        raw_manifest=(raw,),
        installed_manifest=(
            LockedManifestEntry(f"{ROOT}/bin/isabelle", hashlib.sha256(BINARY).hexdigest(), len(BINARY), True),
        ),
        installed_tree=tree,
    )


def _write_fixture(root: Path) -> tuple[Path, Path]:
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    archive = root / "Isabelle-qualification.tar.gz"
    archive.write_bytes(_archive_bytes())
    selection_path = root / "selection.json"
    selection_path.write_text(json.dumps(asdict(_selection(archive))), encoding="utf-8")
    return archive, selection_path


def _load_selection(path: Path) -> LockedArtifactSelection:
    document = json.loads(path.read_text(encoding="utf-8"))
    return LockedArtifactSelection(
        **{
            **document,
            "source_urls": tuple(document["source_urls"]),
            "locator_refs": tuple(document["locator_refs"]),
            "policy_refs": tuple(document["policy_refs"]),
            "installed_identity": (),
            "raw_manifest": tuple(LockedManifestEntry(**entry) for entry in document["raw_manifest"]),
            "installed_manifest": tuple(LockedManifestEntry(**entry) for entry in document["installed_manifest"]),
            "installed_tree": LockedInstalledTree(**document["installed_tree"]),
        }
    )


def _no_network(*_args: object, **_kwargs: object) -> dict[str, str]:
    raise AssertionError("qualification local-input admission attempted a network transfer")


def _ensure(repo_root: Path, archive: Path, selection: LockedArtifactSelection, counter: Any = None) -> Path:
    def acquire_raw(destination: Path) -> None:
        if counter is not None:
            with counter.get_lock():
                counter.value += 1
        time.sleep(0.05)
        client.acquire_locked_file(
            artifact_id="Isabelle",
            source_url=selection.source_urls[0],
            expected=selection.raw_manifest[0],
            destination=destination,
            local_input=archive,
        )

    client.run_curl_transfer = _no_network
    return tree_installation.ensure_verified_tree_installation(repo_root, selection, acquire_raw=acquire_raw)


def _tree_digest(tree: Path) -> str:
    return hashlib.sha256((tree / ROOT / "bin" / "isabelle").read_bytes()).hexdigest()


def _expected_digest(selection_path: Path) -> str:
    return _load_selection(selection_path).installed_manifest[0].sha256


def _worker(
    repo_text: str,
    archive_text: str,
    selection_text: str,
    result_queue: Any,
    start: Any = None,
    counter: Any = None,
    lock_timeout: float | None = None,
) -> None:
    try:
        if lock_timeout is not None:
            tree_installation.TREE_LOCK_TIMEOUT_SECONDS = lock_timeout
        if start is not None:
            start.wait(20)
        selection = _load_selection(Path(selection_text))
        tree = _ensure(Path(repo_text), Path(archive_text), selection, counter)
        result_queue.put({"path": str(tree), "digest": _tree_digest(tree)})
    except BaseException as exc:  # noqa: BLE001 - the parent must observe exact worker failure.
        result_queue.put({"error": f"{type(exc).__name__}:{exc}"})


def _crashing_worker(repo_text: str, archive_text: str, selection_text: str, checkpoint: str, reached: Any) -> None:
    def pause_at_checkpoint(name: str, _path: Path) -> None:
        if name == checkpoint:
            reached.set()
            while True:
                time.sleep(1)

    installation._publication_checkpoint = pause_at_checkpoint
    _ensure(Path(repo_text), Path(archive_text), _load_selection(Path(selection_text)))


def _checked(result: dict[str, str], expected_digest: str) -> str:
    if "error" in result:
        raise AssertionError(result["error"])
    if result["digest"] != expected_digest:
        raise AssertionError("worker observed a non-reviewed executable")
    return result["path"]


def _repo(root: Path, name: str) -> Path:
    repo = root / name
    repo.mkdir(parents=True, mode=0o700)
    return repo


def _cold_convergence(root: Path, archive: Path, selection_path: Path) -> float:
    repo = _repo(root, "cold")
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    start = context.Event()
    counter = context.Value("i", 0)
    processes = [
        context.Process(
            target=_worker,
            args=(str(repo), str(archive), str(selection_path), result_queue, start, counter),
        )
        for _ in range(COLD_PROCESSES)
    ]
    began = time.monotonic()
    for process in processes:
        process.start()
    start.set()
    results = [result_queue.get(timeout=CASE_WAIT_SECONDS) for _ in processes]
    for process in processes:
        process.join(30)
        if process.exitcode != 0:
            raise AssertionError(f"cold worker exited {process.exitcode}")
    paths = {_checked(result, _expected_digest(selection_path)) for result in results}
    if len(paths) != 1 or counter.value != 1:
        raise AssertionError(f"cold convergence failed: paths={len(paths)} acquisitions={counter.value}")
    return time.monotonic() - began


def _warm_validation(root: Path, archive: Path, selection_path: Path) -> float:
    repo = root / "cold"
    selection = _load_selection(selection_path)
    installed = _ensure(repo, archive, selection)
    began = time.monotonic()
    with ThreadPoolExecutor(max_workers=16) as executor:
        paths = list(
            executor.map(
                lambda _index: tree_installation.require_verified_tree_installation(repo, selection),
                range(WARM_CLIENTS),
            )
        )
    if any(path != installed for path in paths):
        raise AssertionError("warm validation clients diverged")
    return time.monotonic() - began


def _crash_recovery(root: Path, archive: Path, selection_path: Path) -> float:
    context = multiprocessing.get_context("spawn")
    selection = _load_selection(selection_path)
    began = time.monotonic()
    for checkpoint in CHECKPOINTS:
        repo = _repo(root, f"crash-{checkpoint}")
        reached = context.Event()
        process = context.Process(
            target=_crashing_worker,
            args=(str(repo), str(archive), str(selection_path), checkpoint, reached),
        )
        process.start()
        if not reached.wait(CASE_WAIT_SECONDS):
            process.kill()
            process.join(5)
            raise AssertionError(f"publisher did not reach {checkpoint}")
        process.kill()
        process.join(5)
        if process.is_alive():
            raise AssertionError(f"publisher survived kill at {checkpoint}")
        tree = _ensure(repo, archive, selection)
        if _tree_digest(tree) != _expected_digest(selection_path):
            raise AssertionError(f"recovery produced wrong bytes after {checkpoint}")
        target = tree.parent
        raw_parent = target.parents[2]
        if list(target.parent.glob(".stage-*")) or list(raw_parent.glob(".stage-raw-*")):
            raise AssertionError(f"staging remained after recovery at {checkpoint}")
        tree_installation.require_verified_tree_installation(repo, selection)
    return time.monotonic() - began


def _live_publisher_exclusion(root: Path, archive: Path, selection_path: Path) -> float:
    repo = _repo(root, "live")
    context = multiprocessing.get_context("spawn")
    reached = context.Event()
    publisher = context.Process(
        target=_crashing_worker,
        args=(str(repo), str(archive), str(selection_path), "staged-durable", reached),
    )
    began = time.monotonic()
    publisher.start()
    if not reached.wait(CASE_WAIT_SECONDS):
        publisher.kill()
        publisher.join(5)
        raise AssertionError("publisher did not reach durable staging")
    result_queue = context.Queue()
    survivor = context.Process(target=_worker, args=(str(repo), str(archive), str(selection_path), result_queue))
    survivor.start()
    time.sleep(0.5)
    if not survivor.is_alive():
        raise AssertionError(f"survivor bypassed a live publisher: {result_queue.get(timeout=1)}")
    publisher.kill()
    publisher.join(5)
    result = result_queue.get(timeout=CASE_WAIT_SECONDS)
    survivor.join(30)
    if survivor.exitcode != 0:
        raise AssertionError(f"survivor exited {survivor.exitcode}")
    _checked(result, _expected_digest(selection_path))
    return time.monotonic() - began


def _bounded_lock_timeout(root: Path, archive: Path, selection_path: Path) -> float:
    repo = _repo(root, "timeout")
    context = multiprocessing.get_context("spawn")
    reached = context.Event()
    publisher = context.Process(
        target=_crashing_worker,
        args=(str(repo), str(archive), str(selection_path), "staged-durable", reached),
    )
    began = time.monotonic()
    publisher.start()
    if not reached.wait(CASE_WAIT_SECONDS):
        publisher.kill()
        publisher.join(5)
        raise AssertionError("publisher did not reach durable staging")
    result_queue = context.Queue()
    contender = context.Process(
        target=_worker,
        args=(str(repo), str(archive), str(selection_path), result_queue, None, None, 0.2),
    )
    contender.start()
    result = result_queue.get(timeout=30)
    contender.join(10)
    if result.get("error") != "RuntimeError:tool-installation: lock-timeout":
        raise AssertionError(f"contender did not time out safely: {result}")
    publisher.kill()
    publisher.join(5)
    _ensure(repo, archive, _load_selection(selection_path))
    return time.monotonic() - began


def _quota_failure_recovery(root: Path, archive: Path, selection_path: Path) -> float:
    repo = _repo(root, "quota")
    selection = _load_selection(selection_path)
    began = time.monotonic()
    original = tree_archive.StageSink.file

    def disk_full(self: Any, path: Any, source: Any, size: int) -> str:
        raise OSError(errno.ENOSPC, "qualification disk quota")

    tree_archive.StageSink.file = disk_full
    try:
        try:
            _ensure(repo, archive, selection)
        except RuntimeError as exc:
            if str(exc) != "tool-installation: storage-exhausted":
                raise
        else:
            raise AssertionError("quota failure was not terminal")
    finally:
        tree_archive.StageSink.file = original
    target = tree_installation.tree_installation_path(installation.default_installation_root(repo), selection)
    if target.exists() or list(target.parent.glob(".stage-*")):
        raise AssertionError("quota failure exposed partial state")
    _ensure(repo, archive, selection)
    return time.monotonic() - began


def _expect_failure(action: Any, expected: str) -> None:
    try:
        action()
    except RuntimeError as exc:
        if expected not in str(exc):
            raise AssertionError(f"expected {expected}, observed {exc}") from exc
    else:
        raise AssertionError(f"expected failure {expected}")


def _corrupt_inputs(root: Path, archive: Path, selection_path: Path) -> float:
    selection = _load_selection(selection_path)
    payload = archive.read_bytes()
    flipped = bytearray(payload)
    flipped[len(flipped) // 2] ^= 1
    began = time.monotonic()
    carriers = {
        "truncated": payload[:-1],
        "oversize": payload + b"x",
        "bit-flip": bytes(flipped),
    }
    for name, carrier_bytes in carriers.items():
        repo = _repo(root, f"corrupt-{name}")
        carrier = repo / "carrier.tar.gz"
        carrier.write_bytes(carrier_bytes)
        _expect_failure(lambda repo=repo, carrier=carrier: _ensure(repo, carrier, selection), "local input failed")
        raw_parent = tree_installation.tree_installation_path(
            installation.default_installation_root(repo), selection
        ).parents[2]
        if (raw_parent / tree_installation.RAW_OBJECT_NAME).exists() or list(raw_parent.glob(".stage-*")):
            raise AssertionError(f"corrupt {name} input left admitted or staged bytes")
    repo = _repo(root, "corrupt-symlink")
    link = repo / "carrier.tar.gz"
    link.symlink_to(archive)
    _expect_failure(lambda: _ensure(repo, link, selection), "local input failed")
    return time.monotonic() - began


def _malicious_archives(root: Path, archive: Path, selection_path: Path) -> float:
    benign = _load_selection(selection_path)
    began = time.monotonic()
    shapes = {
        "absolute-symlink": _tar_member(f"{ROOT}/escape", kind=tarfile.SYMTYPE, target="/etc/passwd"),
        "escaping-symlink": _tar_member(f"{ROOT}/escape", kind=tarfile.SYMTYPE, target="../../outside"),
        "hardlink": _tar_member(f"{ROOT}/linked", kind=tarfile.LNKTYPE, target=f"{ROOT}/bin/isabelle"),
        "device": _tar_member(f"{ROOT}/device", kind=tarfile.CHRTYPE),
        "traversal": _tar_member(f"{ROOT}/../outside", kind=tarfile.REGTYPE, payload=b"x"),
    }
    for name, member in shapes.items():
        repo = _repo(root, f"malicious-{name}")
        carrier = repo / "malicious.tar.gz"
        carrier.write_bytes(_archive_bytes((member,)))
        payload = carrier.read_bytes()
        raw = LockedManifestEntry(carrier.name, hashlib.sha256(payload).hexdigest(), len(payload))
        # Reviewed counts include the hostile member so rejection comes from the
        # shape rule itself, not from a count mismatch.
        reviewed_tree = replace(
            benign.installed_tree,
            symlink_count=benign.installed_tree.symlink_count + int(member[0].issym()),
        )
        selection = replace(benign, raw_manifest=(raw,), installed_tree=reviewed_tree)
        _expect_failure(
            lambda repo=repo, carrier=carrier, selection=selection: _ensure(repo, carrier, selection),
            "unsafe-archive",
        )
        target = tree_installation.tree_installation_path(installation.default_installation_root(repo), selection)
        if target.exists() or list(target.parent.glob(".stage-*")) or (repo / "outside").exists():
            raise AssertionError(f"malicious {name} archive exposed installed or escaped content")
    return time.monotonic() - began


def _missing_native_closure(root: Path, archive: Path, selection_path: Path) -> float:
    selection = _load_selection(selection_path)
    repo = _repo(root, "missing-closure")
    began = time.monotonic()
    original_select = sys.modules["tools.tooling_policy_gate"].load_tooling_artifact_selection
    original_run = isabelle_tool.subprocess.run
    original_paths = isabelle_tool.ISABELLE_REQUIRED_FONTCONFIG_PATHS

    def must_not_execute(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("preflight executed a process")

    sys.modules["tools.tooling_policy_gate"].load_tooling_artifact_selection = lambda **_kwargs: selection
    isabelle_tool.subprocess.run = must_not_execute
    isabelle_tool.ISABELLE_REQUIRED_FONTCONFIG_PATHS = (repo / "absent-fonts",)
    try:
        result = isabelle_tool.proof_host_preflight(
            repo,
            bwrap=repo / "absent-bwrap",
            font_query=lambda: False,
            locale_query=lambda: False,
        )
    finally:
        sys.modules["tools.tooling_policy_gate"].load_tooling_artifact_selection = original_select
        isabelle_tool.subprocess.run = original_run
        isabelle_tool.ISABELLE_REQUIRED_FONTCONFIG_PATHS = original_paths
    if result["missing"] != list(isabelle_tool.PROOF_PREREQUISITE_IDS) or result["outcome"] != "failed":
        raise AssertionError(f"preflight did not list the complete missing closure: {result}")
    return time.monotonic() - began


def _bubblewrap_network_namespace_available() -> bool:
    if not BWRAP.is_file():
        return False
    try:
        completed = subprocess.run(
            [str(BWRAP), "--dev-bind", "/", "/", "--unshare-net", "--die-with-parent", "/bin/true"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _network_namespace_identity() -> str:
    return os.readlink("/proc/self/ns/net")


def _egress_oracle(parent_namespace: str, parent_port: int) -> dict[str, bool]:
    """Observe the network boundary deterministically instead of an unreachable address.

    A distinct network namespace identity proves the process left the parent
    namespace, and a refused connection to a parent-owned loopback listener proves
    the parent's network is not reachable from inside it.
    """

    try:
        socket.create_connection(("127.0.0.1", parent_port), timeout=2).close()
    except OSError:
        parent_listener_reachable = False
    else:
        parent_listener_reachable = True
    return {
        "namespace_isolated": _network_namespace_identity() != parent_namespace,
        "parent_listener_reachable": parent_listener_reachable,
    }


def _bubblewrap_worker(isolated: bool, *arguments: str) -> dict[str, object]:
    network = ["--unshare-net"] if isolated else []
    completed = subprocess.run(
        [
            str(BWRAP),
            "--dev-bind",
            "/",
            "/",
            *network,
            "--die-with-parent",
            sys.executable,
            str(Path(__file__).resolve()),
            *arguments,
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if completed.returncode != 0:
        raise AssertionError(f"bubblewrap worker failed: {completed.stderr[-2000:]}")
    return json.loads(completed.stdout)


def _egress_denied_admission(root: Path, archive: Path, selection_path: Path) -> float | None:
    if not _bubblewrap_network_namespace_available():
        return None
    repo = _repo(root, "egress-denied")
    began = time.monotonic()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(8)
        oracle_arguments = (_network_namespace_identity(), str(listener.getsockname()[1]))
        # The negative control proves the oracle detects a missing boundary.
        control = _bubblewrap_worker(False, "--oracle-worker", *oracle_arguments)
        if control["namespace_isolated"] or not control["parent_listener_reachable"]:
            raise AssertionError(f"egress oracle cannot detect a shared network: {control}")
        observed = _bubblewrap_worker(
            True,
            "--offline-worker",
            str(repo),
            str(archive),
            str(selection_path),
            *oracle_arguments,
        )
    if (
        not observed["namespace_isolated"]
        or observed["parent_listener_reachable"]
        or observed["digest"] != _expected_digest(selection_path)
    ):
        raise AssertionError(f"egress-denied admission evidence is invalid: {observed}")
    tree_installation.require_verified_tree_installation(repo, _load_selection(selection_path))
    return time.monotonic() - began


def _oracle_worker(parent_namespace: str, parent_port: str) -> int:
    print(json.dumps(_egress_oracle(parent_namespace, int(parent_port))))
    return 0


def _offline_worker(
    repo_text: str,
    archive_text: str,
    selection_text: str,
    parent_namespace: str,
    parent_port: str,
) -> int:
    oracle = _egress_oracle(parent_namespace, int(parent_port))
    tree = _ensure(Path(repo_text), Path(archive_text), _load_selection(Path(selection_text)))
    print(json.dumps({**oracle, "digest": _tree_digest(tree)}))
    return 0


def _real_proof_closure() -> dict[str, object]:
    from tools.check_tooling_artifact_policy import tooling_policy_sha256

    selection = isabelle_tool._load_selection()
    began = time.monotonic()
    isabelle_tool.require_isabelle(REPO_ROOT)
    verification_seconds = time.monotonic() - began
    preflight = isabelle_tool.proof_host_preflight(REPO_ROOT)
    if preflight["outcome"] != "passed":
        raise AssertionError(f"real proof closure preflight failed: {preflight}")
    return {
        "raw_sha256": selection.raw_manifest[0].sha256,
        "raw_size": selection.raw_manifest[0].size,
        "installed_tree": asdict(selection.installed_tree),
        "tooling_policy_sha256": tooling_policy_sha256(REPO_ROOT),
        "full_tree_verification_seconds": round(verification_seconds, 3),
        "preflight": preflight,
    }


def _native_version(argv: list[str]) -> str:
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    line = (completed.stdout or completed.stderr).strip().splitlines()
    return line[0][:128] if completed.returncode == 0 and line else "unavailable"


def _real_archive_cases(root: Path, archive: Path) -> dict[str, float]:
    """Run the process and crash slices against the real reviewed proof archive."""

    global CASE_WAIT_SECONDS
    CASE_WAIT_SECONDS = 3600
    fixture = root / "real-fixture"
    fixture.mkdir(parents=True, mode=0o700)
    selection_path = fixture / "selection.json"
    selection_path.write_text(json.dumps(asdict(isabelle_tool._load_selection())), encoding="utf-8")
    real_root = root / "real"
    real_root.mkdir(mode=0o700)
    return {
        "T05-real-cold-convergence": _cold_convergence(real_root, archive, selection_path),
        "T05-real-crash-recovery": _crash_recovery(real_root, archive, selection_path),
        "T05-real-live-publisher-exclusion": _live_publisher_exclusion(real_root, archive, selection_path),
    }


def _parse_harness_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute issue #1220 proof-input qualification slices.")
    parser.add_argument("root", type=Path)
    parser.add_argument("--real-installation", action="store_true")
    parser.add_argument("--real-archive", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    if argv[:1] == ["--offline-worker"]:
        return _offline_worker(*argv[1:6])
    if argv[:1] == ["--oracle-worker"]:
        return _oracle_worker(*argv[1:3])
    args = _parse_harness_args(argv)
    real_installation = args.real_installation
    real_archive = args.real_archive
    root = args.root.resolve()
    archive, selection_path = _write_fixture(root / "fixture")
    cases: dict[str, float] = {}
    not_run: dict[str, str] = {}
    for name, case in (
        ("T05-cold-convergence", _cold_convergence),
        ("T05-warm-validation", _warm_validation),
        ("T05-crash-recovery", _crash_recovery),
        ("T05-live-publisher-exclusion", _live_publisher_exclusion),
        ("T05-bounded-lock-timeout", _bounded_lock_timeout),
        ("T05-quota-failure-recovery", _quota_failure_recovery),
        ("T13-corrupt-local-input", _corrupt_inputs),
        ("T13-malicious-archive", _malicious_archives),
        ("T13-missing-native-closure", _missing_native_closure),
    ):
        cases[name] = case(root, archive, selection_path)
    egress = _egress_denied_admission(root, archive, selection_path)
    if egress is None:
        not_run["T11-egress-denied-admission"] = "bubblewrap-network-namespace-unavailable"
    else:
        cases["T11-egress-denied-admission"] = egress
    if real_archive is not None:
        cases.update(_real_archive_cases(root, real_archive.resolve()))
    if not (set(cases) | set(not_run)) <= set(SLICE_CASE_NAMES):
        raise AssertionError("harness emitted an unregistered slice")
    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "installation_policy": tree_installation.INSTALLATION_TREE_POLICY_ID,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "filesystem": installation._filesystem_type(root),
        "filelock": version("filelock"),
        "bubblewrap": _native_version([str(BWRAP), "--version"]),
        "large_object_budget": asdict(client.LARGE_OBJECT_TRANSFER_BUDGET),
        "tree_lock_timeout_seconds": tree_installation.TREE_LOCK_TIMEOUT_SECONDS,
        "cold_processes": COLD_PROCESSES,
        "warm_clients": WARM_CLIENTS,
        "crash_checkpoints": list(CHECKPOINTS),
        "passed_cases": sorted(cases),
        "not_run_cases": not_run,
        "coverage": {
            "scope": "proof-input-installation-mechanism",
            "fixture": "synthetic-multi-file-symlink-tree"
            + ("+real-reviewed-proof-archive" if real_archive is not None else ""),
            "canonical_cases": {
                "T05": "proof-tree-process-and-crash-slice-only",
                "T08": "large-object-real-curl-fixture-in-bootstrap-qualification",
                "T11": "egress-denied-proof-input-admission-slice-only",
                "T13": "proof-input-and-native-closure-preflight-slice-only",
            },
            "canonical_outcome_recorded": False,
        },
        "elapsed_seconds": {name: round(elapsed, 3) for name, elapsed in cases.items()},
        "limitations": [
            "Required CI mechanism cases use a synthetic tree with the real distribution's member classes;"
            " the real 1.2 GB archive cases run only with --real-archive.",
            "Complete air-gapped export/import (T11) and whole-closure preflight (T13) remain owned by #1225.",
        ],
    }
    if real_installation:
        evidence["real_proof_closure"] = _real_proof_closure()
    for path in root.rglob("*"):
        if path.is_dir() and not path.is_symlink():
            path.chmod(0o700)
    shutil.rmtree(root / "fixture", ignore_errors=True)
    encoded = json.dumps(evidence, sort_keys=True)
    if args.output is not None:
        args.output.write_text(f"{encoded}\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
