"""Dependency-free projection of a reviewed installed-tree identity from the lock."""

from __future__ import annotations

import re
from dataclasses import dataclass

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_COUNT_FLOORS = {"file_count": 1, "directory_count": 1, "symlink_count": 0, "expanded_bytes": 1}
_INVALID_INSTALLED_TREE = "development artifact policy failed before acquisition: invalid installed tree"


@dataclass(frozen=True)
class LockedInstalledTree:
    """The reviewed canonical identity of a complete extracted installation tree."""

    format: str
    manifest_sha256: str
    file_count: int
    directory_count: int
    symlink_count: int
    expanded_bytes: int


def _count_is_valid(value: object, floor: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= floor


def _installed_tree_is_closed(value: dict[str, object]) -> bool:
    digest = value.get("manifest_sha256")
    return (
        set(value) == {"format", "manifest_sha256", *_COUNT_FLOORS}
        and value.get("format") == "tar.gz"
        and isinstance(digest, str)
        and SHA256_PATTERN.fullmatch(digest) is not None
        and all(_count_is_valid(value.get(name), floor) for name, floor in _COUNT_FLOORS.items())
    )


def locked_installed_tree(value: object) -> LockedInstalledTree | None:
    """Return the closed installed-tree identity when the lock declares one."""

    if value is None:
        return None
    if not isinstance(value, dict) or not _installed_tree_is_closed(value):
        raise RuntimeError(_INVALID_INSTALLED_TREE)
    return LockedInstalledTree(**value)


__all__ = ["SHA256_PATTERN", "LockedInstalledTree", "locked_installed_tree"]
