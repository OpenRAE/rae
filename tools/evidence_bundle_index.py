"""Shared discovery for immutable, sharded research evidence manifests."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from raes_contracts.errors import InvalidInputError  # noqa: E402

from tools.policy.common import load_bounded_json_object, safe_repo_path  # noqa: E402

_REVISION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def revision_key(value: object) -> tuple[int, int, int]:
    """Return a sortable semantic-version key for a manifest revision."""

    match = _REVISION_RE.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise InvalidInputError(f"invalid evidence manifest revision: {value!r}")
    try:
        return tuple(int(part) for part in match.groups())
    except ValueError as exc:
        # The pattern admits only decimal digits, so int() fails only beyond the interpreter digit limit.
        raise InvalidInputError("evidence manifest revision exceeds the integer digit limit") from exc


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
        raise InvalidInputError(f"{index_path!r} fields must exactly match {sorted(expected_keys)}")
    if index.get("schema_version") != schema_version:
        raise InvalidInputError(f"{index_path!r} schema_version must be {schema_version!r}")
    directory_value = index.get(directory_key)
    directory = safe_repo_path(repo_root, directory_value) if isinstance(directory_value, str) else None
    if directory is None or not directory.is_dir():
        raise InvalidInputError(f"{index_path!r} contains an unsafe or missing {directory_key}")
    paths = sorted(
        [
            *directory.glob("*.json"),
            *(directory.parent / "captures").glob("*/manifest.json"),
        ]
    )
    if not paths:
        raise InvalidInputError(f"{index_path!r} selects no evidence records")
    records: list[tuple[str, dict[str, object]]] = []
    for path in paths:
        relative = path.relative_to(repo_root).as_posix()
        try:
            record = load_bounded_json_object(repo_root, relative, max_bytes=max_bytes)
        except (OSError, InvalidInputError) as exc:
            raise InvalidInputError(f"cannot load evidence record {relative!r}") from exc
        records.append((relative, record))
    return records


__all__ = ["load_index_records", "revision_key"]
