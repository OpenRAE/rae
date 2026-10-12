"""Shared discovery for immutable, sharded research evidence manifests."""

from __future__ import annotations

import re
from pathlib import Path

from tools.policy.common import load_bounded_json_object, safe_repo_path

_REVISION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def revision_key(value: object) -> tuple[int, int, int]:
    """Return a sortable semantic-version key for a manifest revision."""

    match = _REVISION_RE.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise ValueError(f"invalid evidence manifest revision: {value!r}")
    return tuple(int(part) for part in match.groups())


def load_index_records(
    repo_root: Path,
    *,
    index_path: str,
    schema_version: str,
    directory_key: str,
    max_bytes: int,
) -> list[tuple[str, dict[str, object]]]:
    """Load every JSON record selected by a stable evidence index."""

    index = load_bounded_json_object(repo_root, index_path, max_bytes=max_bytes)
    expected_keys = {"schema_version", directory_key}
    if set(index) != expected_keys:
        raise ValueError(f"{index_path!r} fields must exactly match {sorted(expected_keys)}")
    if index.get("schema_version") != schema_version:
        raise ValueError(f"{index_path!r} schema_version must be {schema_version!r}")
    directory_value = index.get(directory_key)
    directory = safe_repo_path(repo_root, directory_value) if isinstance(directory_value, str) else None
    if directory is None or not directory.is_dir():
        raise ValueError(f"{index_path!r} contains an unsafe or missing {directory_key}")
    paths = sorted(
        [
            *directory.glob("*.json"),
            *(directory.parent / "captures").glob("*/manifest.json"),
        ]
    )
    if not paths:
        raise ValueError(f"{index_path!r} selects no evidence records")
    records: list[tuple[str, dict[str, object]]] = []
    for path in paths:
        relative = path.relative_to(repo_root).as_posix()
        try:
            record = load_bounded_json_object(repo_root, relative, max_bytes=max_bytes)
        except (OSError, ValueError) as exc:
            raise ValueError(f"cannot load evidence record {relative!r}: {exc}") from exc
        records.append((relative, record))
    return records


__all__ = ["load_index_records", "revision_key"]
