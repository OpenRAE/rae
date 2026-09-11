from __future__ import annotations

import shutil
import stat
import tarfile
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

from tools.maintained_client_acquisition import acquire_locked_bytes
from tools.tool_versions import GITLEAKS_VERSION

if TYPE_CHECKING:
    from tools.tooling_policy_gate import LockedManifestEntry

REPO_ROOT = Path(__file__).resolve().parents[1]


def gitleaks_binary_path(repo_root: Path = REPO_ROOT, *, version: str = GITLEAKS_VERSION) -> Path:
    return repo_root / ".cache" / "raes-sdl" / "tooling" / "gitleaks" / version / "gitleaks"


def _locked_binary_cache_hit(path: Path, *, expected_sha256: str, expected_size: int) -> bool:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(mode):
        path.unlink()
        return False
    if not stat.S_ISREG(mode):
        raise RuntimeError("unsafe gitleaks cache entry is not a regular file")
    return path.stat().st_size == expected_size and _sha256_file(path) == expected_sha256


def _install_locked_binary(
    archive_bytes: bytes,
    installed: LockedManifestEntry,
    binary_path: Path,
) -> None:
    with tempfile.TemporaryDirectory(prefix="raes-gitleaks-") as tmpdir:
        archive_path = Path(tmpdir) / "locked-gitleaks-archive.tar.gz"
        archive_path.write_bytes(archive_bytes)
        with tarfile.open(archive_path, "r:gz") as archive:
            member = archive.getmember(installed.path)
            if not member.isfile():
                raise RuntimeError("gitleaks installed manifest does not select a regular archive member")
            extracted_stream = archive.extractfile(member)
            if extracted_stream is None:
                raise RuntimeError("gitleaks installed archive member cannot be read")
            extracted_bytes = extracted_stream.read(installed.size + 1)
        if len(extracted_bytes) != installed.size or sha256(extracted_bytes).hexdigest() != installed.sha256:
            raise RuntimeError("gitleaks installed binary differs from the reviewed lock manifest")
        extracted = Path(tmpdir) / "locked-gitleaks-binary"
        extracted.write_bytes(extracted_bytes)
        extracted.chmod(extracted.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        shutil.move(extracted, binary_path)


def ensure_gitleaks(
    repo_root: Path = REPO_ROOT,
    *,
    version: str = GITLEAKS_VERSION,
    local_input: Path | None = None,
) -> Path:
    from tools.tooling_policy_gate import (
        host_platform_id,
        load_tooling_artifact_selection,
        safe_tooling_cache_parent,
    )

    platform_id = host_platform_id()
    selection = load_tooling_artifact_selection(
        artifact_id="gitleaks",
        version=version,
        platform_id=platform_id,
        profile_id=f"public-{platform_id}",
    )
    if len(selection.source_urls) != 1 or len(selection.raw_manifest) != 1 or len(selection.installed_manifest) != 1:
        raise RuntimeError("gitleaks lock selection must contain one source, raw asset, and installed binary")
    raw = selection.raw_manifest[0]
    installed = selection.installed_manifest[0]
    requested_path = gitleaks_binary_path(repo_root, version=version)
    binary_path = safe_tooling_cache_parent(repo_root, requested_path, artifact_id="gitleaks") / requested_path.name
    if _locked_binary_cache_hit(binary_path, expected_sha256=installed.sha256, expected_size=installed.size):
        return binary_path
    binary_path.unlink(missing_ok=True)

    archive_bytes = acquire_locked_bytes(
        artifact_id="gitleaks",
        source_url=selection.source_urls[0],
        expected=raw,
        local_input=local_input,
    )

    _install_locked_binary(archive_bytes, installed, binary_path)
    return binary_path


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
