"""Dependency-free launcher for the frozen development artifact policy gate."""

from __future__ import annotations

import json
import platform
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
_VALIDATOR_TIMEOUT_SECONDS = 180
_INVALID_SELECTION_RESPONSE = "development artifact policy failed before acquisition: invalid selection response"
_INVALID_HOST_RESPONSE = "development artifact policy failed before acquisition: invalid host selection response"


@dataclass(frozen=True)
class LockedManifestEntry:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class LockedArtifactSelection:
    artifact_id: str
    version: str
    platform_id: str
    profile_id: str
    repository: str
    release: str
    source_urls: tuple[str, ...]
    raw_manifest: tuple[LockedManifestEntry, ...]
    installed_manifest: tuple[LockedManifestEntry, ...]


def _is_portable_manifest_path(path: str) -> bool:
    relative = PurePosixPath(path)
    return not (
        path != relative.as_posix()
        or relative.is_absolute()
        or "\\" in path
        or re.match(r"^[A-Za-z]:", path)
        or any(part in {"", ".", ".."} for part in relative.parts)
    )


def _locked_manifest_entry(value: object) -> LockedManifestEntry:
    if not isinstance(value, dict):
        raise RuntimeError("development artifact policy failed before acquisition: invalid manifest entry")
    path = value.get("path")
    digest = value.get("sha256")
    size = value.get("size")
    if not isinstance(path, str) or not _is_portable_manifest_path(path):
        raise RuntimeError("development artifact policy failed before acquisition: invalid manifest path")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise RuntimeError("development artifact policy failed before acquisition: invalid manifest digest")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise RuntimeError("development artifact policy failed before acquisition: invalid manifest size")
    return LockedManifestEntry(path, digest, size)


def safe_tooling_cache_parent(repo_root: Path, target: Path, *, artifact_id: str) -> Path:
    """Create a fixed repository cache chain without following symlinks."""

    canonical_root = repo_root.resolve()
    try:
        parts = target.parent.relative_to(repo_root).parts
    except ValueError as exc:
        raise RuntimeError(f"{artifact_id} cache path escapes the repository") from exc
    current = canonical_root
    for part in parts:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            try:
                current.mkdir()
                continue
            except FileExistsError:
                mode = current.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise RuntimeError(f"unsafe {artifact_id} cache directory")
    return current


def host_platform_id() -> str:
    system = {"Linux": "linux", "Darwin": "macos"}.get(platform.system())
    machine = {
        "aarch64": "arm64",
        "amd64": "x86_64",
        "arm64": "arm64",
        "x86_64": "x86_64",
    }.get(platform.machine().lower())
    if system is None or machine is None:
        raise RuntimeError("development artifact policy does not support this host platform")
    return f"{system}-{machine}"


def _frozen_validator_command(policy_root: Path) -> list[str]:
    validator_python = policy_root / "implementations" / "python" / ".venv" / "bin" / "python"
    project_root = policy_root / "implementations" / "python"
    validator = policy_root / "tools" / "check_tooling_artifact_policy.py"
    if not validator.is_file():
        raise RuntimeError(
            "development artifact policy failed before acquisition: the frozen project validator is unavailable"
        )
    if validator_python.is_file():
        return [str(validator_python), str(validator)]
    uv_executable = shutil.which("uv")
    if (
        uv_executable is None
        or not (project_root / "pyproject.toml").is_file()
        or not (project_root / "uv.lock").is_file()
    ):
        raise RuntimeError(
            "development artifact policy failed before acquisition: the frozen project validator is unavailable"
        )
    return [
        uv_executable,
        "run",
        "--project",
        str(project_root),
        "--frozen",
        "python",
        str(validator),
    ]


def _validator_stdout(
    validator_command: list[str],
    *,
    artifact_id: str,
    version: str,
    platform_id: str,
    profile_id: str,
) -> str:
    try:
        proc = subprocess.run(
            [
                *validator_command,
                "--select-artifact",
                artifact_id,
                "--version",
                version,
                "--platform-id",
                platform_id,
                "--profile-id",
                profile_id,
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=_VALIDATOR_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            "development artifact policy failed before acquisition: the frozen project validator could not complete"
        ) from exc
    if proc.returncode != 0:
        details = proc.stderr.strip() or "the frozen project validator rejected the selection"
        raise RuntimeError(f"development artifact policy failed before acquisition:\n{details}")
    return proc.stdout


def _validator_host_stdout(validator_command: list[str], *, host_profile_id: str) -> str:
    try:
        proc = subprocess.run(
            [*validator_command, "--select-host-profile", host_profile_id],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=_VALIDATOR_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            "development artifact policy failed before acquisition: the frozen project validator could not complete"
        ) from exc
    if proc.returncode != 0:
        details = proc.stderr.strip() or "the frozen project validator rejected the host selection"
        raise RuntimeError(f"development artifact policy failed before acquisition:\n{details}")
    return proc.stdout


def _selection_document(payload: str, invalid_response: str = _INVALID_SELECTION_RESPONSE) -> dict[str, object]:
    try:
        selection = json.loads(payload)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise RuntimeError(invalid_response) from exc
    if not isinstance(selection, dict):
        raise RuntimeError(invalid_response)
    return selection


def _selection_from_document(
    selection: dict[str, object],
    profile_id: str,
) -> tuple[LockedArtifactSelection, object]:
    try:
        source = selection["source"]
        platform = selection["platform"]
        if not isinstance(source, dict) or not isinstance(platform, dict):
            raise TypeError
        raw_manifest = tuple(_locked_manifest_entry(item) for item in platform["raw_manifest"])
        installed_manifest = tuple(_locked_manifest_entry(item) for item in platform["installed_manifest"])
        result = LockedArtifactSelection(
            artifact_id=selection["artifact_id"],
            version=selection["version"],
            platform_id=platform["platform_id"],
            profile_id=profile_id,
            repository=source["repository"],
            release=source["release"],
            source_urls=tuple(platform["source_urls"]),
            raw_manifest=raw_manifest,
            installed_manifest=installed_manifest,
        )
        selected_profile_ids = platform["profile_ids"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(_INVALID_SELECTION_RESPONSE) from exc
    return result, selected_profile_ids


def _selection_is_valid(
    selection: LockedArtifactSelection,
    selected_profile_ids: object,
    *,
    artifact_id: str,
    version: str,
    platform_id: str,
    profile_id: str,
) -> bool:
    identity = (selection.artifact_id, selection.version, selection.platform_id, selection.profile_id)
    expected_identity = (artifact_id, version, platform_id, profile_id)
    scalar_values = (
        selection.platform_id,
        selection.repository,
        selection.release,
        *selection.source_urls,
    )
    required_collections = (
        selection.source_urls,
        selection.raw_manifest,
        selection.installed_manifest,
    )
    return all(
        (
            identity == expected_identity,
            isinstance(selected_profile_ids, list),
            isinstance(selected_profile_ids, list) and profile_id in selected_profile_ids,
            all(required_collections),
            all(isinstance(value, str) and value for value in scalar_values),
        )
    )


def load_tooling_artifact_selection(
    *,
    artifact_id: str,
    version: str,
    platform_id: str,
    profile_id: str,
) -> LockedArtifactSelection:
    """Load one reviewed lock selection before cache lookup or acquisition."""

    validator_command = _frozen_validator_command(REPO_ROOT)
    payload = _validator_stdout(
        validator_command,
        artifact_id=artifact_id,
        version=version,
        platform_id=platform_id,
        profile_id=profile_id,
    )
    result, selected_profile_ids = _selection_from_document(_selection_document(payload), profile_id)
    if not _selection_is_valid(
        result,
        selected_profile_ids,
        artifact_id=artifact_id,
        version=version,
        platform_id=platform_id,
        profile_id=profile_id,
    ):
        raise RuntimeError(_INVALID_SELECTION_RESPONSE)
    return result


def load_tooling_host_profile_selection(host_profile_id: str) -> dict[str, object]:
    """Load one schema- and semantics-validated host/bootstrap selection."""

    payload = _validator_host_stdout(_frozen_validator_command(REPO_ROOT), host_profile_id=host_profile_id)
    selection = _selection_document(payload, _INVALID_HOST_RESPONSE)
    host = selection.get("host_profile")
    artifacts = selection.get("artifacts")
    policy_sha256 = selection.get("policy_sha256")
    if (
        not isinstance(host, dict)
        or host.get("host_profile_id") != host_profile_id
        or not isinstance(artifacts, list)
        or not artifacts
        or not all(isinstance(item, dict) for item in artifacts)
        or not isinstance(policy_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", policy_sha256) is None
    ):
        raise RuntimeError(_INVALID_HOST_RESPONSE)
    expected_ids = host.get("bootstrap_payload_ids")
    selected_ids = [item.get("artifact_id") for item in artifacts]
    if (
        not isinstance(expected_ids, list)
        or not all(isinstance(value, str) and value for value in expected_ids)
        or not all(isinstance(value, str) and value for value in selected_ids)
        or sorted(expected_ids) != sorted(selected_ids)
        or len(set(selected_ids)) != len(selected_ids)
    ):
        raise RuntimeError(_INVALID_HOST_RESPONSE)
    try:
        for artifact in artifacts:
            source = artifact["source"]
            platform_data = artifact["platform"]
            if not isinstance(source, dict) or not isinstance(platform_data, dict):
                raise TypeError
            raw_values = platform_data["raw_manifest"]
            installed_values = platform_data.get("installed_manifest", [])
            source_urls = platform_data["source_urls"]
            host_profile_ids = platform_data.get("host_profile_ids", [])
            if (
                not isinstance(raw_values, list)
                or not isinstance(installed_values, list)
                or not isinstance(source_urls, list)
                or not source_urls
                or not all(isinstance(value, str) and value for value in source_urls)
                or not isinstance(host_profile_ids, list)
                or not all(isinstance(value, str) and value for value in host_profile_ids)
            ):
                raise TypeError
            raw_manifest = tuple(_locked_manifest_entry(item) for item in raw_values)
            installed_manifest = tuple(_locked_manifest_entry(item) for item in installed_values)
            installed_identity = platform_data.get("installed_identity")
            scalar_values = (
                artifact["artifact_id"],
                artifact["artifact_class"],
                artifact["version"],
                source["repository"],
                source["release"],
                platform_data["platform_id"],
                *source_urls,
            )
            if (
                platform_data["platform_id"] != host.get("platform_id")
                or (host_profile_ids and host_profile_id not in host_profile_ids)
                or not raw_manifest
                or not (
                    installed_manifest
                    or isinstance(installed_identity, dict)
                    and installed_identity.get("version") == artifact["version"]
                )
                or not all(isinstance(value, str) and value for value in scalar_values)
            ):
                raise TypeError
    except (KeyError, TypeError, RuntimeError):
        raise RuntimeError(_INVALID_HOST_RESPONSE) from None
    return selection
