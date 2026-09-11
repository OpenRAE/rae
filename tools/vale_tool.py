from __future__ import annotations

import io
import os
import shutil
import stat
import tarfile
import tempfile
from hashlib import sha256
from pathlib import Path

from tools.http_download import download_bytes
from tools.tool_versions import VALE_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]


def vale_binary_path(repo_root: Path = REPO_ROOT, *, version: str = VALE_VERSION) -> Path:
    return repo_root / ".cache" / "raes-sdl" / "tooling" / "vale" / version / "vale"


def _locked_binary_cache_hit(path: Path, *, expected_sha256: str, expected_size: int) -> bool:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(mode):
        path.unlink()
        return False
    if not stat.S_ISREG(mode):
        raise RuntimeError("unsafe Vale cache entry is not a regular file")
    return path.stat().st_size == expected_size and sha256(path.read_bytes()).hexdigest() == expected_sha256


def _extract_binary(
    archive_bytes: bytes,
    binary_path: Path,
    *,
    installed_path: str = "vale",
    expected_sha256: str | None = None,
    expected_size: int | None = None,
) -> None:
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        try:
            member = archive.getmember(installed_path)
        except KeyError as exc:
            raise RuntimeError("Vale archive does not contain a root vale binary") from exc
        if not member.isfile():
            raise RuntimeError("Vale archive root vale member is not a regular file")
        extracted = archive.extractfile(member)
        if extracted is None:
            raise RuntimeError("Vale archive root vale binary cannot be read")
        binary_bytes = extracted.read()
    if expected_size is not None and len(binary_bytes) != expected_size:
        raise RuntimeError("Vale installed binary size differs from the reviewed lock manifest")
    if expected_sha256 is not None and sha256(binary_bytes).hexdigest() != expected_sha256:
        raise RuntimeError("Vale installed binary digest differs from the reviewed lock manifest")

    descriptor, temporary_name = tempfile.mkstemp(prefix=".vale-", suffix=".download", dir=binary_path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(binary_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.chmod(temporary_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        shutil.move(temporary_path, binary_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def ensure_vale(repo_root: Path = REPO_ROOT, *, version: str = VALE_VERSION) -> Path:
    from tools.tooling_policy_gate import (
        host_platform_id,
        load_tooling_artifact_selection,
        safe_tooling_cache_parent,
    )

    platform_id = host_platform_id()
    selection = load_tooling_artifact_selection(
        artifact_id="vale",
        version=version,
        platform_id=platform_id,
        profile_id=f"public-{platform_id}",
    )
    if len(selection.source_urls) != 1 or len(selection.raw_manifest) != 1 or len(selection.installed_manifest) != 1:
        raise RuntimeError("Vale lock selection must contain one source, raw asset, and installed binary")
    raw = selection.raw_manifest[0]
    installed = selection.installed_manifest[0]
    requested_path = vale_binary_path(repo_root, version=version)
    binary_path = safe_tooling_cache_parent(repo_root, requested_path, artifact_id="Vale") / requested_path.name
    if _locked_binary_cache_hit(binary_path, expected_sha256=installed.sha256, expected_size=installed.size):
        return binary_path
    binary_path.unlink(missing_ok=True)

    asset_name = raw.path
    archive_bytes = download_bytes(selection.source_urls[0], description="Vale")
    actual = sha256(archive_bytes).hexdigest()
    if len(archive_bytes) != raw.size or actual != raw.sha256:
        raise RuntimeError(f"Vale checksum or size mismatch for locked asset {asset_name}")

    _extract_binary(
        archive_bytes,
        binary_path,
        installed_path=installed.path,
        expected_sha256=installed.sha256,
        expected_size=installed.size,
    )
    return binary_path
