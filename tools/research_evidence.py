"""Bounded, shared provenance and release selection for research captures."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from tools.evidence_bundle_index import revision_key
from tools.policy.common import PolicyFailure, load_bounded_json_object, safe_repo_path

# v2 binds the Release Please version literal as a placeholder, so a release
# commit does not change the identity of the source it releases. v1 captures
# hashed the literal and stay valid only as historical records.
SOURCE_PROFILE = "python-reference-source/v2"
HISTORICAL_SOURCE_PROFILES = frozenset({"python-reference-source/v1", SOURCE_PROFILE})
RELEASE_MANAGED_VERSION_SOURCE = "implementations/python/packages/raes/_version.py"
_RELEASE_VERSION_MARKER = "x-release-please-version"
_RELEASE_VERSION_LINE = re.compile(
    r'^(__version__ = ")\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?(" {2}# x-release-please-version)$',
    re.MULTILINE | re.ASCII,
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
    normalized, replaced = _RELEASE_VERSION_LINE.subn(
        r"\g<1>release-managed\g<2>", text
    )
    if replaced != 1 or text.count(_RELEASE_VERSION_MARKER) != 1:
        raise ValueError(
            "release-managed version source must carry exactly one marked version literal"
        )
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
        pins.append(
            [path.relative_to(root).as_posix(), hashlib.sha256(source).hexdigest()]
        )
    if not pins:
        raise ValueError("empty implementation surface")
    return hashlib.sha256(json.dumps(pins, separators=(",", ":")).encode()).hexdigest()


_CAPTURE_RE = re.compile(r"^capture-[0-9a-f]{64}$")
_PUBLISHED_HISTORY_PINS = {
    "formal-semantic-validation": "0f4268804b9a46742068435ea66dab067d50945ac7a7dd6fe317679878b9a572",
    "specification-coverage": "16a926f7995bc567c3ae6d3ed5981598c22e9067a421d4371f1708df800a4f2f",
}


def is_capture(value: object) -> bool:
    """A capture identity is content-addressed, never an allocated release number."""
    return isinstance(value, str) and _CAPTURE_RE.fullmatch(value) is not None


def evidence_key(value: object) -> tuple[int, tuple[int, int, int] | str]:
    if is_capture(value):
        return (1, str(value))
    return (0, revision_key(value))


def capture_identity(manifest: Mapping[str, object]) -> str:
    """Bind immutable document pins without depending on their storage paths."""
    pins = {
        key: value
        for key, value in manifest.items()
        if key not in {"revision", "snapshot_path", "analysis_path"}
    }
    encoded = json.dumps(pins, sort_keys=True, separators=(",", ":")).encode()
    return "capture-" + hashlib.sha256(encoded).hexdigest()


def validate_inventory(
    repo_root: Path, family: str, records: Sequence[tuple[str, Mapping[str, object]]]
) -> None:
    """Retain admitted history and reject changed or unaddressed capture records."""
    folder = f"docs/research/{family}"
    history_path = f"{folder}/published-history.json"
    history = safe_repo_path(repo_root, history_path)
    if (
        history is None
        or hashlib.sha256(history.read_bytes()).hexdigest()
        != _PUBLISHED_HISTORY_PINS[family]
    ):
        raise ValueError("published research history pin is invalid")
    expected = load_bounded_json_object(repo_root, history_path, max_bytes=512 * 1024)[
        "records"
    ]
    by_path = dict(records)
    if len(by_path) != len(records):
        raise ValueError("research evidence paths must be unique")
    by_revision = {
        manifest.get("revision"): (path, manifest) for path, manifest in records
    }
    if len(by_revision) != len(records):
        raise ValueError("research evidence release revisions must be unique")
    historical_paths = set()
    for pin in expected:
        selected = by_revision.get(pin["revision"])
        if selected is None:
            raise ValueError(
                "research evidence requires every supported published historical and current release"
            )
        relative, manifest = selected
        path = safe_repo_path(repo_root, relative)
        if (
            path is None
            or hashlib.sha256(path.read_bytes()).hexdigest() != pin["sha256"]
        ):
            raise ValueError("published research history manifest pin is stale")
        if manifest != load_bounded_json_object(
            repo_root, relative, max_bytes=512 * 1024
        ):
            raise ValueError("published research history record differs from its pin")
        historical_paths.add(relative)
    receipts = {}
    receipt_folder = repo_root / folder / "capture-records"
    for receipt_path in sorted(receipt_folder.glob("*.json")):
        relative = receipt_path.relative_to(repo_root).as_posix()
        receipt = load_bounded_json_object(repo_root, relative, max_bytes=4096)
        if set(receipt) != {"capture_path", "capture_sha256"}:
            raise ValueError("capture retention record has invalid fields")
        capture_path = receipt["capture_path"]
        if not isinstance(capture_path, str):
            raise ValueError("capture retention path must be a string")
        manifest = by_path.get(capture_path)
        if manifest is None or not is_capture(manifest.get("revision")):
            raise ValueError("capture retention requires every recorded manifest")
        if receipt_path.stem != manifest["revision"]:
            raise ValueError("capture retention identity differs from its manifest")
        pinned = safe_repo_path(repo_root, capture_path)
        if (
            pinned is None
            or hashlib.sha256(pinned.read_bytes()).hexdigest()
            != receipt["capture_sha256"]
        ):
            raise ValueError("capture retention manifest pin is stale")
        receipts[capture_path] = receipt
    capture_paths = {
        path for path, manifest in records if is_capture(manifest.get("revision"))
    }
    if set(receipts) != capture_paths:
        raise ValueError("every capture requires an independent retention record")
    identities = []
    for path, manifest in records:
        identity = manifest.get("revision")
        evidence_key(identity)
        identities.append(identity)
        if path not in historical_paths:
            if not is_capture(identity) or capture_identity(manifest) != identity:
                raise ValueError(
                    "new research evidence must use a content-addressed capture identity"
                )
            prefix = f"{folder}/captures/{identity}/"
            if (
                path != prefix + "manifest.json"
                or manifest.get("snapshot_path") != prefix + "snapshot.json"
                or manifest.get("analysis_path") != prefix + "analysis.json"
            ):
                raise ValueError(
                    "capture documents must stay in their unique capture directory"
                )
    if len(set(identities)) != len(identities):
        raise ValueError("research evidence release revisions must be unique")


def current_release_path(
    records: Sequence[tuple[str, Mapping[str, object]]], repo_root: Path | None = None
) -> str:
    """Select a live-source capture; legacy callers retain semantic selection."""
    if not records:
        raise ValueError("no research evidence releases")
    keys = [evidence_key(record.get("revision")) for _, record in records]
    if len(set(keys)) != len(keys):
        raise ValueError("research evidence release revisions must be unique")
    if repo_root is not None:
        digest = implementation_digest(repo_root)
        candidates = []
        legacy = [
            (path, record)
            for path, record in records
            if not is_capture(record.get("revision"))
        ]
        selectable = [
            (path, record)
            for path, record in records
            if is_capture(record.get("revision"))
        ]
        if legacy:
            selectable.append(
                max(legacy, key=lambda item: revision_key(item[1].get("revision")))
            )
        for path, record in selectable:
            snapshot = load_bounded_json_object(
                repo_root, str(record.get("snapshot_path")), max_bytes=2 * 1024 * 1024
            )
            state = snapshot.get("source_state")
            if (
                isinstance(state, Mapping)
                and state.get("profile") == SOURCE_PROFILE
                and state.get("implementation_digest") == digest
            ):
                candidates.append((snapshot.get("captured_at"), path, record))
        if not candidates:
            raise ValueError(
                "no current research capture binds the live implementation source"
            )
        # Capture dates select only among exact live-source matches. Full replay
        # and shape validation still run on the selected record.
        from datetime import datetime, timezone

        dated = []
        for captured_at, path, record in candidates:
            if not isinstance(captured_at, str):
                raise ValueError("capture date must be an offset-aware timestamp")
            date = datetime.fromisoformat(captured_at)
            if date.tzinfo is None or date > datetime.now(timezone.utc):
                raise ValueError(
                    "capture date must be offset-aware and cannot be in the future"
                )
            dated.append((date, path, record))
        latest = max(date for date, _, _ in dated)
        latest_records = [
            (path, record) for date, path, record in dated if date == latest
        ]
        # A content-addressed wrapper may retain an existing release verbatim.
        pins = {
            (record.get("snapshot_sha256"), record.get("analysis_sha256"))
            for _, record in latest_records
        }
        if len(pins) == 1 and any(
            is_capture(record.get("revision")) for _, record in latest_records
        ):
            latest_records = [
                (path, record)
                for path, record in latest_records
                if is_capture(record.get("revision"))
            ]
        selected = [path for path, _ in latest_records]
        if len(selected) != 1:
            raise ValueError("current research capture is ambiguous")
        return selected[0]
    return max(zip(keys, records, strict=True), key=lambda item: item[0])[1][0]


def implementation_digest(repo_root: Path) -> str:
    """Bind fixed source/configuration paths, never environment-selected files."""
    packages = repo_root / "implementations/python/packages"
    if not packages.is_dir() or packages.is_symlink():
        raise ValueError("missing or unsafe reference implementation")
    paths = sorted(packages.rglob("*.py"))
    if not paths or len(paths) > 10000:
        raise ValueError("reference implementation file count is invalid")
    paths.extend(
        repo_root / "implementations/python" / name
        for name in ("pyproject.toml", "uv.lock")
    )
    pins = []
    total = 0
    for path in sorted(paths):
        relative = path.relative_to(repo_root).as_posix()
        resolved = safe_repo_path(repo_root, relative)
        if resolved is None or not resolved.is_file() or path.is_symlink():
            raise ValueError("unsafe reference implementation source")
        total = _source_size(resolved, total)
        pins.append(
            [relative, hashlib.sha256(_source_bytes(resolved, relative)).hexdigest()]
        )
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


def source_state_failures(
    repo_root: Path, state: object, path: str, *, current: bool
) -> list[PolicyFailure]:
    """Historical source identity is retained; a current capture binds live code."""
    valid = _source_identity_valid(
        state, frozenset({SOURCE_PROFILE}) if current else HISTORICAL_SOURCE_PROFILES
    )
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
