"""Strict parsing of a retained installed-tree manifest against its reviewed identity."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import PurePosixPath

from tools.verified_tree_archive import (
    SHA256_RE,
    TREE_FORMAT,
    TREE_MANIFEST_SCHEMA,
    InstalledTree,
    TreeEntry,
    confined_symlink_target,
    failure,
    manifest_bytes,
    symlink_target_shape_is_safe,
    tree_descriptor,
    tree_path,
)

_ENTRY_FIELDS = {
    "directory": frozenset({"kind", "path"}),
    "symlink": frozenset({"kind", "path", "target"}),
    "file": frozenset({"executable", "kind", "path", "sha256", "size"}),
}


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key")
        result[key] = value
    return result


_INVALID_MANIFEST_ENTRY = "manifest entry"


def _file_manifest_entry(path: str, value: dict[str, object]) -> TreeEntry:
    digest = value["sha256"]
    size = value["size"]
    executable = value["executable"]
    valid = (
        isinstance(executable, bool)
        and isinstance(digest, str)
        and SHA256_RE.fullmatch(digest) is not None
        and isinstance(size, int)
        and not isinstance(size, bool)
        and size >= 0
    )
    if not valid:
        raise ValueError(_INVALID_MANIFEST_ENTRY)
    return TreeEntry(path, "file", digest, size, executable)


def _manifest_entry(value: object) -> TreeEntry:
    if not isinstance(value, dict):
        raise ValueError(_INVALID_MANIFEST_ENTRY)
    kind = value.get("kind")
    if not isinstance(kind, str) or set(value) != _ENTRY_FIELDS.get(kind, frozenset()):
        raise ValueError(_INVALID_MANIFEST_ENTRY)
    path = tree_path(value["path"]).as_posix()
    target = value.get("target")
    if kind == "symlink" and not symlink_target_shape_is_safe(target):
        raise ValueError(_INVALID_MANIFEST_ENTRY)
    entries = {
        "directory": lambda: TreeEntry(path, "directory"),
        "symlink": lambda: TreeEntry(path, "symlink", target=str(target)),
        "file": lambda: _file_manifest_entry(path, value),
    }
    return entries[kind]()


def _manifest_entries(payload: bytes) -> list[TreeEntry]:
    try:
        document = json.loads(payload.decode("ascii"), object_pairs_hook=_reject_duplicate_keys)
        shape_valid = (
            isinstance(document, dict)
            and set(document) == {"entries", "format", "schema"}
            and document["schema"] == TREE_MANIFEST_SCHEMA
            and document["format"] == TREE_FORMAT
            and isinstance(document["entries"], list)
        )
        if not shape_valid:
            raise ValueError("manifest shape")
        return [_manifest_entry(value) for value in document["entries"]]
    except (RuntimeError, ValueError) as exc:
        raise failure("tree-integrity-failure") from exc


def _descriptor_document(descriptor: InstalledTree) -> dict[str, object]:
    return {
        "directory_count": descriptor.directory_count,
        "expanded_bytes": descriptor.expanded_bytes,
        "file_count": descriptor.file_count,
        "format": descriptor.format,
        "manifest_sha256": descriptor.manifest_sha256,
        "symlink_count": descriptor.symlink_count,
    }


def _entry_structure_is_valid(entry: TreeEntry, kinds: Mapping[str, str]) -> bool:
    parent = PurePosixPath(entry.path).parent.as_posix()
    parent_valid = parent == "." or kinds.get(parent) == "directory"
    link_valid = entry.kind != "symlink" or confined_symlink_target(entry.path, str(entry.target), kinds)
    return parent_valid and link_valid


def parse_manifest(payload: bytes, descriptor: InstalledTree) -> dict[str, TreeEntry]:
    """Parse a retained manifest that must canonically match the reviewed descriptor."""

    entries = _manifest_entries(payload)
    by_path = {entry.path: entry for entry in entries}
    kinds = {entry.path: entry.kind for entry in entries}
    consistent = (
        len(by_path) == len(entries)
        and manifest_bytes(entries) == payload
        and tree_descriptor(entries) == _descriptor_document(descriptor)
        and all(_entry_structure_is_valid(entry, kinds) for entry in entries)
    )
    if not consistent:
        raise failure("tree-integrity-failure")
    return by_path


__all__ = ["parse_manifest"]
