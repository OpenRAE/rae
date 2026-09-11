from __future__ import annotations

import json
import shutil
import stat
import subprocess
import tarfile
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

from tools.http_download import download_bytes

from ..tool_versions import CONTFEST_VERSION
from .common import REPO_ROOT, PolicyFailure

if TYPE_CHECKING:
    from tools.tooling_policy_gate import LockedManifestEntry

POLICY_DIR = REPO_ROOT / "tools" / "policy" / "conftest"
CACHE_ROOT = REPO_ROOT / ".cache" / "raes-sdl" / "tooling" / "conftest"


def conftest_binary_path(repo_root: Path = REPO_ROOT, *, version: str = CONTFEST_VERSION) -> Path:
    return repo_root / ".cache" / "raes-sdl" / "tooling" / "conftest" / version / "conftest"


def _locked_binary_cache_hit(path: Path, *, expected_sha256: str, expected_size: int) -> bool:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(mode):
        path.unlink()
        return False
    if not stat.S_ISREG(mode):
        raise RuntimeError("unsafe conftest cache entry is not a regular file")
    return path.stat().st_size == expected_size and _sha256_file(path) == expected_sha256


def _install_locked_binary(
    archive_bytes: bytes,
    installed: LockedManifestEntry,
    binary_path: Path,
) -> None:
    with tempfile.TemporaryDirectory(prefix="raes-conftest-") as tmpdir:
        archive_path = Path(tmpdir) / "locked-conftest-archive.tar.gz"
        archive_path.write_bytes(archive_bytes)
        with tarfile.open(archive_path, "r:gz") as archive:
            member = archive.getmember(installed.path)
            if not member.isfile():
                raise RuntimeError("conftest installed manifest does not select a regular archive member")
            extracted_stream = archive.extractfile(member)
            if extracted_stream is None:
                raise RuntimeError("conftest installed archive member cannot be read")
            extracted_bytes = extracted_stream.read()
        if len(extracted_bytes) != installed.size or sha256(extracted_bytes).hexdigest() != installed.sha256:
            raise RuntimeError("conftest installed binary differs from the reviewed lock manifest")
        extracted = Path(tmpdir) / "locked-conftest-binary"
        extracted.write_bytes(extracted_bytes)
        extracted.chmod(extracted.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        shutil.move(extracted, binary_path)


def ensure_conftest(repo_root: Path = REPO_ROOT, *, version: str = CONTFEST_VERSION) -> Path:
    from tools.tooling_policy_gate import (
        host_platform_id,
        load_tooling_artifact_selection,
        safe_tooling_cache_parent,
    )

    platform_id = host_platform_id()
    selection = load_tooling_artifact_selection(
        artifact_id="conftest",
        version=version,
        platform_id=platform_id,
        profile_id=f"public-{platform_id}",
    )
    if len(selection.source_urls) != 1 or len(selection.raw_manifest) != 1 or len(selection.installed_manifest) != 1:
        raise RuntimeError("conftest lock selection must contain one source, raw asset, and installed binary")
    raw = selection.raw_manifest[0]
    installed = selection.installed_manifest[0]
    requested_path = conftest_binary_path(repo_root, version=version)
    binary_path = safe_tooling_cache_parent(repo_root, requested_path, artifact_id="conftest") / requested_path.name
    if _locked_binary_cache_hit(binary_path, expected_sha256=installed.sha256, expected_size=installed.size):
        return binary_path
    binary_path.unlink(missing_ok=True)

    asset_name = raw.path
    archive_bytes = download_bytes(selection.source_urls[0], description="conftest")
    actual_checksum = sha256(archive_bytes).hexdigest()
    if len(archive_bytes) != raw.size or actual_checksum != raw.sha256:
        raise RuntimeError(f"conftest checksum or size mismatch for locked asset {asset_name}")

    _install_locked_binary(archive_bytes, installed, binary_path)
    return binary_path


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_conftest_policy(
    input_document: dict[str, object],
    *,
    repo_root: Path = REPO_ROOT,
    policy_dir: Path = POLICY_DIR,
) -> list[PolicyFailure]:
    binary = ensure_conftest(repo_root)

    with tempfile.TemporaryDirectory(prefix="raes-conftest-input-") as tmpdir:
        input_path = Path(tmpdir) / "repo-policy-input.json"
        input_path.write_text(json.dumps(input_document, indent=2, sort_keys=True), encoding="utf-8")
        proc = subprocess.run(
            [
                str(binary),
                "test",
                str(input_path),
                "--policy",
                str(policy_dir),
                "--output",
                "json",
            ],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )

    if proc.returncode not in {0, 1}:
        details = proc.stderr.strip() or proc.stdout.strip() or "unknown conftest failure"
        raise RuntimeError(f"conftest repo policy evaluation failed: {details}")

    if not proc.stdout.strip():
        return []

    raw_results = json.loads(proc.stdout)
    failures: list[PolicyFailure] = []
    for result in raw_results:
        for failure in result.get("failures", []):
            metadata = failure.get("metadata", {})
            failures.append(
                PolicyFailure(
                    metadata.get("rule_id", "conftest-policy-failure"),
                    failure["msg"],
                    metadata.get("path"),
                )
            )
    failures.sort(key=lambda item: (item.path or "", item.rule_id, item.message))
    return failures


def verify_conftest_policy(*, repo_root: Path = REPO_ROOT, policy_dir: Path = POLICY_DIR) -> None:
    binary = ensure_conftest(repo_root)
    proc = subprocess.run(
        [
            str(binary),
            "verify",
            "--policy",
            str(policy_dir),
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        details = proc.stderr.strip() or proc.stdout.strip() or "unknown conftest verify failure"
        raise RuntimeError(f"conftest policy verification failed: {details}")
