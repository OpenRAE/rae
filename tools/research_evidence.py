"""Bounded, shared provenance and release selection for research captures."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from tools.evidence_bundle_index import revision_key
from tools.policy.common import PolicyFailure, safe_repo_path

# v2 binds the Release Please version literal as a placeholder, so a release
# commit does not change the identity of the source it releases. v1 captures
# hashed the literal and stay valid only as historical records.
SOURCE_PROFILE = "python-reference-source/v2"
HISTORICAL_SOURCE_PROFILES = frozenset({"python-reference-source/v1", SOURCE_PROFILE})
RELEASE_MANAGED_VERSION_SOURCE = "implementations/python/packages/raes/_version.py"
_RELEASE_VERSION_MARKER = "x-release-please-version"
_RELEASE_VERSION_LINE = re.compile(
    r'^(__version__ = ")[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?("  # x-release-please-version)$',
    re.MULTILINE,
)
_SOURCE_KEYS = {"profile", "base_revision", "checkout_state", "implementation_digest"}


def _source_size(path: Path, total: int) -> int:
    size = path.stat().st_size
    total += size
    if size > 2 * 1024 * 1024 or total > 128 * 1024 * 1024:
        raise ValueError("implementation source budget exceeded")
    return total


def _source_bytes(path: Path, relative: str) -> bytes:
    """Return the bytes a source pin binds; only the release version literal is abstracted."""
    content = path.read_bytes()
    if relative != RELEASE_MANAGED_VERSION_SOURCE:
        return content
    text = content.decode("utf-8")
    normalized, replaced = _RELEASE_VERSION_LINE.subn(r"\g<1>release-managed\g<2>", text)
    if replaced != 1 or text.count(_RELEASE_VERSION_MARKER) != 1:
        raise ValueError("release-managed version source must carry exactly one marked version literal")
    return normalized.encode("utf-8")


def surface_digest(repo_root: Path, relative: str) -> str:
    """Digest a registered package's Python files with relative path binding."""
    root = safe_repo_path(repo_root, relative)
    if root is None or not root.is_dir():
        raise ValueError("unsafe implementation surface")
    pins = []
    total = 0
    for path in sorted(root.rglob("*.py")):
        resolved = safe_repo_path(repo_root, path.relative_to(repo_root).as_posix())
        if resolved != path or path.is_symlink() or not path.is_file():
            raise ValueError("unsafe implementation source")
        total = _source_size(path, total)
        if len(pins) >= 10000:
            raise ValueError("implementation source budget exceeded")
        source = _source_bytes(path, path.relative_to(repo_root).as_posix())
        pins.append([path.relative_to(root).as_posix(), hashlib.sha256(source).hexdigest()])
    if not pins:
        raise ValueError("empty implementation surface")
    return hashlib.sha256(json.dumps(pins, separators=(",", ":")).encode()).hexdigest()


def current_release_path(records: Sequence[tuple[str, Mapping[str, object]]]) -> str:
    """Select one complete release; ambiguous revisions fail closed."""
    if not records:
        raise ValueError("no research evidence releases")
    revisions = [revision_key(record.get("revision")) for _, record in records]
    if len(set(revisions)) != len(revisions):
        raise ValueError("research evidence release revisions must be unique")
    return max(zip(revisions, records, strict=True), key=lambda item: item[0])[1][0]


def implementation_digest(repo_root: Path) -> str:
    """Bind fixed source/configuration paths, never environment-selected files."""
    packages = repo_root / "implementations/python/packages"
    if not packages.is_dir() or packages.is_symlink():
        raise ValueError("missing or unsafe reference implementation")
    paths = sorted(packages.rglob("*.py"))
    if not paths or len(paths) > 10000:
        raise ValueError("reference implementation file count is invalid")
    paths.extend(repo_root / "implementations/python" / name for name in ("pyproject.toml", "uv.lock"))
    pins = []
    total = 0
    for path in sorted(paths):
        relative = path.relative_to(repo_root).as_posix()
        resolved = safe_repo_path(repo_root, relative)
        if resolved is None or not resolved.is_file() or path.is_symlink():
            raise ValueError("unsafe reference implementation source")
        total = _source_size(resolved, total)
        pins.append([relative, hashlib.sha256(_source_bytes(resolved, relative)).hexdigest()])
    encoded = json.dumps(pins, ensure_ascii=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _source_identity_valid(state: object, profiles: frozenset[str]) -> bool:
    return (
        isinstance(state, Mapping)
        and set(state) == _SOURCE_KEYS
        and isinstance(state.get("profile"), str)
        and state.get("profile") in profiles
        and isinstance(state.get("checkout_state"), str)
        and state.get("checkout_state") in {"clean", "modified"}
        and isinstance(state.get("base_revision"), str)
        and re.fullmatch(r"[0-9a-f]{40}", state["base_revision"]) is not None
        and isinstance(state.get("implementation_digest"), str)
        and re.fullmatch(r"[0-9a-f]{64}", state["implementation_digest"]) is not None
    )


def source_state_failures(repo_root: Path, state: object, path: str, *, current: bool) -> list[PolicyFailure]:
    """Historical source identity is retained; a current capture binds live code."""
    valid = _source_identity_valid(state, frozenset({SOURCE_PROFILE}) if current else HISTORICAL_SOURCE_PROFILES)
    if valid and current:
        try:
            valid = state["implementation_digest"] == implementation_digest(repo_root)
        except (OSError, ValueError):
            valid = False
    return (
        []
        if valid
        else [
            PolicyFailure(
                "research-evidence-source-state",
                "capture source identity is invalid or differs from current code",
                path,
            )
        ]
    )
