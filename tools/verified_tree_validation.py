"""Complete verification of a reviewed tree selection, raw object, and installed tree.

Every function here only reads. A selection is accepted only inside closed
implementation-owned bounds, a raw object only by exact size and digest through
the opened inode, and an installed tree only when its retained manifest matches
the reviewed digest and every entry on disk matches that manifest exactly.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Protocol

from tools import verified_tree_archive as archive
from tools.verified_tree_archive import MAX_TREE_EXPANDED_BYTES, MAX_TREE_MEMBERS, TREE_FORMAT, InstalledTree, TreeEntry
from tools.verified_tree_manifest import parse_manifest

TREE_CONTENT_NAME = "tree"
TREE_MANIFEST_NAME = "installed-tree.json"
MAX_TREE_RAW_BYTES = 2 * 1024 * 1024 * 1024
_failure = archive.failure


class ManifestEntry(Protocol):
    path: str
    sha256: str
    size: int
    executable: bool


class TreeSelection(Protocol):
    artifact_id: str
    platform_id: str
    policy_refs: tuple[str, ...]
    raw_manifest: tuple[ManifestEntry, ...]
    installed_manifest: tuple[ManifestEntry, ...]
    installed_tree: InstalledTree | None


def _is_int_at_least(value: object, floor: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= floor


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and archive.SHA256_RE.fullmatch(value) is not None


def _descriptor_is_bounded(descriptor: InstalledTree | None) -> bool:
    if descriptor is None or descriptor.format != TREE_FORMAT or not _is_sha256(descriptor.manifest_sha256):
        return False
    counts = (
        (descriptor.file_count, 1),
        (descriptor.directory_count, 1),
        (descriptor.symlink_count, 0),
        (descriptor.expanded_bytes, 1),
    )
    if not all(_is_int_at_least(value, floor) for value, floor in counts):
        return False
    members = descriptor.file_count + descriptor.directory_count + descriptor.symlink_count
    return members <= MAX_TREE_MEMBERS and descriptor.expanded_bytes <= MAX_TREE_EXPANDED_BYTES


def _raw_manifest_is_bounded(raw: tuple[ManifestEntry, ...]) -> bool:
    return (
        len(raw) == 1
        and _is_sha256(raw[0].sha256)
        and _is_int_at_least(raw[0].size, 1)
        and raw[0].size <= MAX_TREE_RAW_BYTES
    )


def _installation_policy_is_closed(selection: TreeSelection) -> bool:
    return (
        bool(selection.installed_manifest)
        and sum(entry.executable is True for entry in selection.installed_manifest) == 1
        and bool(selection.policy_refs)
        and all(isinstance(reference, str) and reference for reference in selection.policy_refs)
    )


def validated_descriptor(selection: TreeSelection) -> InstalledTree:
    descriptor = selection.installed_tree
    valid = (
        _descriptor_is_bounded(descriptor)
        and _raw_manifest_is_bounded(selection.raw_manifest)
        and _installation_policy_is_closed(selection)
    )
    if not valid or descriptor is None:
        raise _failure("invalid-selection")
    for entry in selection.installed_manifest:
        archive.tree_path(entry.path)
    return descriptor


def open_flags() -> int:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    return flags | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOINHERIT", 0)


def _raw_state_is_admissible(state: os.stat_result, entry: ManifestEntry, mode: str) -> bool:
    permissions = state.st_mode & 0o777
    expected_mode = {"installed": 0o400, "staged": 0o600, "carrier": 0o600}.get(mode)
    private = mode == "input" or (state.st_uid == os.geteuid() and state.st_nlink == 1 and permissions == expected_mode)
    return stat.S_ISREG(state.st_mode) and state.st_size == entry.size and private


def digest_stream(stream: BinaryIO, size: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    while chunk := stream.read(min(archive.CHUNK_BYTES, size + 1 - total)):
        total += len(chunk)
        digest.update(chunk)
    return total, digest.hexdigest()


def _open_verified_raw(path: Path, entry: ManifestEntry, mode: str) -> tuple[BinaryIO, os.stat_result]:
    """Open one raw inode and verify its exact size and digest through that descriptor."""

    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not _raw_state_is_admissible(before, entry, mode):
        raise _failure("raw-manifest-mismatch")
    stream = os.fdopen(os.open(path, open_flags()), "rb")
    try:
        opened = os.fstat(stream.fileno())
        same_inode = stat.S_ISREG(opened.st_mode) and os.path.samestat(before, opened)
        if not same_inode or digest_stream(stream, entry.size) != (entry.size, entry.sha256):
            raise _failure("raw-manifest-mismatch")
        stream.seek(0)
    except BaseException:
        stream.close()
        raise
    return stream, opened


def _raw_unchanged(path: Path, stream: BinaryIO, opened: os.stat_result) -> bool:
    after = os.fstat(stream.fileno())
    return (
        after.st_size == opened.st_size
        and after.st_mtime_ns == opened.st_mtime_ns
        and after.st_ctime_ns == opened.st_ctime_ns
        and os.path.samestat(opened, path.lstat())
    )


@contextmanager
def opened_verified_raw(path: Path, entry: ManifestEntry, *, mode: str) -> Iterator[BinaryIO]:
    """Yield one verified raw inode and require that it stayed unchanged while used."""

    stream, opened = _open_verified_raw(path, entry, mode)
    with stream:
        yield stream
        if not _raw_unchanged(path, stream, opened):
            raise _failure("raw-manifest-mismatch")


def verify_raw_file(path: Path, entry: ManifestEntry, *, mode: str) -> None:
    stream, _opened = _open_verified_raw(path, entry, mode)
    stream.close()


def _tree_file_state_is_valid(before: os.stat_result, entry: TreeEntry) -> bool:
    expected_mode = 0o500 if entry.executable else 0o400
    return (
        stat.S_ISREG(before.st_mode)
        and before.st_nlink == 1
        and before.st_size == entry.size
        and before.st_mode & 0o777 == expected_mode
    )


def _verify_tree_file(path: Path, before: os.stat_result, entry: TreeEntry) -> None:
    if not _tree_file_state_is_valid(before, entry):
        raise _failure("tree-integrity-failure")
    size = int(entry.size or 0)
    with os.fdopen(os.open(path, open_flags()), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not os.path.samestat(before, opened):
            raise _failure("tree-integrity-failure")
        observed = digest_stream(stream, size)
    if observed != (size, entry.sha256) or not os.path.samestat(opened, path.lstat()):
        raise _failure("tree-integrity-failure")


def _verify_tree_entry(path: Path, state: os.stat_result, expected: TreeEntry | None) -> bool:
    """Verify one on-disk entry and return whether it is a directory to descend."""

    if expected is None or state.st_uid != os.geteuid():
        raise _failure("tree-integrity-failure")
    if stat.S_ISLNK(state.st_mode):
        if expected.kind != "symlink" or os.readlink(path) != expected.target:
            raise _failure("tree-integrity-failure")
        return False
    if stat.S_ISDIR(state.st_mode):
        if expected.kind != "directory" or state.st_mode & 0o777 != 0o500:
            raise _failure("tree-integrity-failure")
        return True
    if expected.kind != "file":
        raise _failure("tree-integrity-failure")
    _verify_tree_file(path, state, expected)
    return False


def _validate_tree_contents(root: Path, entries: Mapping[str, TreeEntry]) -> None:
    state = root.lstat()
    if not stat.S_ISDIR(state.st_mode) or state.st_uid != os.geteuid() or state.st_mode & 0o777 != 0o500:
        raise _failure("tree-integrity-failure")
    seen: set[str] = set()
    pending: list[tuple[Path, str]] = [(root, "")]
    while pending:
        directory, prefix = pending.pop()
        with os.scandir(directory) as iterator:
            children = sorted(iterator, key=lambda item: item.name)
        for child in children:
            relative = f"{prefix}/{child.name}" if prefix else child.name
            child_path = Path(child.path)
            if _verify_tree_entry(child_path, child.stat(follow_symlinks=False), entries.get(relative)):
                pending.append((child_path, relative))
            seen.add(relative)
    if seen != set(entries):
        raise _failure("tree-integrity-failure")


def require_installed_manifest(selection: TreeSelection, entries: Mapping[str, TreeEntry]) -> None:
    for expected in selection.installed_manifest:
        entry = entries.get(expected.path)
        if (
            entry is None
            or entry.kind != "file"
            or entry.sha256 != expected.sha256
            or entry.size != expected.size
            or entry.executable is not expected.executable
        ):
            raise _failure("installed-manifest-mismatch")


def _read_manifest(path: Path) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.geteuid()
        or before.st_nlink != 1
        or before.st_mode & 0o777 != 0o400
        or before.st_size > archive.MAX_TREE_MANIFEST_BYTES
    ):
        raise _failure("tree-integrity-failure")
    descriptor = os.open(path, open_flags())
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not os.path.samestat(before, opened):
            raise _failure("tree-integrity-failure")
        payload = stream.read(archive.MAX_TREE_MANIFEST_BYTES + 1)
    if len(payload) != before.st_size or not os.path.samestat(opened, path.lstat()):
        raise _failure("tree-integrity-failure")
    return payload


def validated_installation(target: Path, selection: TreeSelection) -> Path:
    descriptor = validated_descriptor(selection)
    state = target.lstat()
    if (
        stat.S_ISLNK(state.st_mode)
        or not stat.S_ISDIR(state.st_mode)
        or state.st_uid != os.geteuid()
        or state.st_mode & 0o777 != 0o500
        or sorted(os.listdir(target)) != sorted((TREE_CONTENT_NAME, TREE_MANIFEST_NAME))
    ):
        raise _failure("tree-integrity-failure")
    payload = _read_manifest(target / TREE_MANIFEST_NAME)
    if hashlib.sha256(payload).hexdigest() != descriptor.manifest_sha256:
        raise _failure("tree-integrity-failure")
    entries = parse_manifest(payload, descriptor)
    require_installed_manifest(selection, entries)
    _validate_tree_contents(target / TREE_CONTENT_NAME, entries)
    return target / TREE_CONTENT_NAME
