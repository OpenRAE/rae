"""Verified, concurrent-safe installation of a complete reviewed archive tree.

The generic-tool installer in :mod:`tools.verified_tool_installation` admits
small in-memory carriers. A large prover distribution is a multi-gigabyte tree
with thousands of files and in-tree relative symbolic links, so it is streamed
into private staging instead. It still uses the same transaction rules: the
private-root guard, qualified filesystems, one native lock per identity,
exclusive staging, fsync, atomic rename, quarantine, and durable checkpoints.

The reviewed lock binds the raw archive digest and the SHA-256 of the canonical
installed-tree manifest. The manifest is reconstructed from the admitted
archive at installation. It is retained next to the immutable tree, and every
use checks the manifest against the reviewed digest and the whole tree against
the manifest. Neither a marker nor the presence of a file is ever treated as
trust.
"""

from __future__ import annotations

import errno
import gzip
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import tarfile
import tempfile
import uuid
import zlib
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol

from tools import verified_tool_installation as installation

INSTALLATION_TREE_POLICY_ID = "install-tree-v1"
TREE_MANIFEST_SCHEMA = "raes-installed-tree/v1"
TREE_FORMAT = "tar.gz"
TREE_CONTENT_NAME = "tree"
TREE_MANIFEST_NAME = "installed-tree.json"
RAW_OBJECT_NAME = "raw-object"
LEGACY_CARRIER_PREFIX = ".legacy-carrier-"
MAX_TREE_MEMBERS = 262_144
MAX_TREE_EXPANDED_BYTES = 16 * 1024 * 1024 * 1024
MAX_TREE_RAW_BYTES = 2 * 1024 * 1024 * 1024
MAX_TREE_PATH_BYTES = 1024
MAX_TREE_PATH_DEPTH = 64
MAX_SYMLINK_TARGET_BYTES = 1024
MAX_TREE_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_TREE_TRAILER_BYTES = 1024 * 1024
TREE_LOCK_TIMEOUT_SECONDS = 5400
_CHUNK_BYTES = 1024 * 1024
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class ManifestEntry(Protocol):
    path: str
    sha256: str
    size: int
    executable: bool


class InstalledTree(Protocol):
    format: str
    manifest_sha256: str
    file_count: int
    directory_count: int
    symlink_count: int
    expanded_bytes: int


class TreeSelection(Protocol):
    artifact_id: str
    platform_id: str
    policy_refs: tuple[str, ...]
    raw_manifest: tuple[ManifestEntry, ...]
    installed_manifest: tuple[ManifestEntry, ...]
    installed_tree: InstalledTree | None


@dataclass(frozen=True)
class TreeEntry:
    """One canonical installed-tree manifest entry."""

    path: str
    kind: str
    sha256: str | None = None
    size: int | None = None
    executable: bool | None = None
    target: str | None = None

    def document(self) -> dict[str, object]:
        if self.kind == "file":
            return {
                "executable": self.executable,
                "kind": self.kind,
                "path": self.path,
                "sha256": self.sha256,
                "size": self.size,
            }
        if self.kind == "symlink":
            return {"kind": self.kind, "path": self.path, "target": self.target}
        return {"kind": self.kind, "path": self.path}


@dataclass(frozen=True)
class LegacyTreeInputs:
    """Version-keyed legacy content that is migrated but never trusted."""

    raw_carrier: Path | None = None
    derived_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class _TreeLimits:
    file_count: int
    directory_count: int
    symlink_count: int
    expanded_bytes: int
    exact: bool


_CEILING_LIMITS = _TreeLimits(
    file_count=MAX_TREE_MEMBERS,
    directory_count=MAX_TREE_MEMBERS,
    symlink_count=MAX_TREE_MEMBERS,
    expanded_bytes=MAX_TREE_EXPANDED_BYTES,
    exact=False,
)


def _failure(reason: str) -> RuntimeError:
    return RuntimeError(f"tool-installation: {reason}")


def _tree_path(value: object) -> PurePosixPath:
    if not isinstance(value, str):
        raise _failure("unsafe-archive-member")
    path = PurePosixPath(value)
    if (
        not value
        or value != path.as_posix()
        or path.is_absolute()
        or "\\" in value
        or "\x00" in value
        or re.match(r"^[A-Za-z]:", value)
        or len(value.encode("utf-8")) > MAX_TREE_PATH_BYTES
        or len(path.parts) > MAX_TREE_PATH_DEPTH
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise _failure("unsafe-archive-member")
    return path


def _symlink_target_shape_is_safe(target: object) -> bool:
    return (
        isinstance(target, str)
        and bool(target)
        and "\x00" not in target
        and "\\" not in target
        and not target.startswith("/")
        and len(target.encode("utf-8")) <= MAX_SYMLINK_TARGET_BYTES
    )


def _confined_symlink_target(link: str, target: str, kinds: Mapping[str, str]) -> bool:
    """Return whether kernel resolution of ``target`` cannot leave the tree.

    Every existing component that resolution passes through must be a real
    directory, never another symbolic link. Resolution that reaches a component
    absent from the immutable tree stops there with ENOENT, so a dangling link
    whose resolved prefix stays inside the tree is confined.
    """

    if not _symlink_target_shape_is_safe(target):
        return False
    parts = list(PurePosixPath(link).parts[:-1])
    components = target.split("/")
    for index, component in enumerate(components):
        if component in {"", "."}:
            return False
        if component == "..":
            if not parts:
                return False
            parts.pop()
            continue
        parts.append(component)
        kind = kinds.get("/".join(parts))
        if kind is None:
            return True
        if kind == "symlink" or (index < len(components) - 1 and kind != "directory"):
            return False
    return True


class _StageSink:
    """Materialize admitted members inside one private staging directory."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, path: PurePosixPath) -> Path:
        return self.root.joinpath(*path.parts)

    def directory(self, path: PurePosixPath) -> None:
        self._path(path).mkdir(mode=0o700)

    def file(self, path: PurePosixPath, source: BinaryIO, size: int) -> str:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(self._path(path), flags, 0o600)
        digest = hashlib.sha256()
        total = 0
        try:
            while chunk := source.read(min(_CHUNK_BYTES, size + 1 - total)):
                total += len(chunk)
                if total > size:
                    raise _failure("installed-manifest-mismatch")
                digest.update(chunk)
                view = memoryview(chunk)
                while view:
                    view = view[os.write(descriptor, view) :]
        finally:
            os.close(descriptor)
        if total != size:
            raise _failure("installed-manifest-mismatch")
        return digest.hexdigest()

    def symlink(self, path: PurePosixPath, target: str) -> None:
        os.symlink(target, self._path(path))


def _hash_member(source: BinaryIO, size: int) -> str:
    digest = hashlib.sha256()
    total = 0
    while chunk := source.read(min(_CHUNK_BYTES, size + 1 - total)):
        total += len(chunk)
        if total > size:
            raise _failure("installed-manifest-mismatch")
        digest.update(chunk)
    if total != size:
        raise _failure("installed-manifest-mismatch")
    return digest.hexdigest()


class _TreeAdmission:
    """Streaming, bounded admission of one tar.gz carrier into canonical entries."""

    def __init__(self, limits: _TreeLimits, sink: _StageSink | None) -> None:
        self.limits = limits
        self.sink = sink
        self.kinds: dict[str, str] = {}
        self.entries: dict[str, TreeEntry] = {}
        self.explicit_directories: set[str] = set()
        self.counts = {"file": 0, "directory": 0, "symlink": 0}
        self.expanded_bytes = 0

    def _record(self, entry: TreeEntry) -> None:
        self.counts[entry.kind] += 1
        limit = {
            "file": self.limits.file_count,
            "directory": self.limits.directory_count,
            "symlink": self.limits.symlink_count,
        }[entry.kind]
        if self.counts[entry.kind] > limit or sum(self.counts.values()) > MAX_TREE_MEMBERS:
            raise _failure("archive-member-limit")
        self.kinds[entry.path] = entry.kind
        self.entries[entry.path] = entry

    def _ensure_parents(self, path: PurePosixPath) -> None:
        for parent in list(path.parents)[-2::-1]:
            key = parent.as_posix()
            kind = self.kinds.get(key)
            if kind is None:
                self._record(TreeEntry(key, "directory"))
                if self.sink is not None:
                    self.sink.directory(parent)
            elif kind != "directory":
                raise _failure("conflicting-archive-member")

    def _directory(self, path: PurePosixPath) -> None:
        name = path.as_posix()
        existing = self.kinds.get(name)
        if existing == "directory" and name not in self.explicit_directories:
            self.explicit_directories.add(name)
            return
        if existing is not None:
            raise _failure("duplicate-archive-member")
        self._record(TreeEntry(name, "directory"))
        self.explicit_directories.add(name)
        if self.sink is not None:
            self.sink.directory(path)

    def _file(self, path: PurePosixPath, member: tarfile.TarInfo, archive: tarfile.TarFile) -> None:
        if member.size < 0:
            raise _failure("archive-size-limit")
        self.expanded_bytes += member.size
        if self.expanded_bytes > self.limits.expanded_bytes:
            raise _failure("archive-size-limit")
        source = archive.extractfile(member)
        if source is None:
            raise _failure("unsafe-archive-member")
        digest = (
            self.sink.file(path, source, member.size) if self.sink is not None else _hash_member(source, member.size)
        )
        self._record(TreeEntry(path.as_posix(), "file", digest, member.size, bool(member.mode & 0o100)))

    def _symlink(self, path: PurePosixPath, member: tarfile.TarInfo) -> None:
        if not _symlink_target_shape_is_safe(member.linkname):
            raise _failure("unsafe-archive-member")
        self._record(TreeEntry(path.as_posix(), "symlink", target=member.linkname))
        if self.sink is not None:
            self.sink.symlink(path, member.linkname)

    def admit(self, member: tarfile.TarInfo, archive: tarfile.TarFile) -> None:
        path = _tree_path(member.name)
        self._ensure_parents(path)
        if member.isdir():
            self._directory(path)
        elif path.as_posix() in self.kinds:
            raise _failure("duplicate-archive-member")
        elif member.isreg() and not member.issparse():
            self._file(path, member, archive)
        elif member.issym():
            self._symlink(path, member)
        else:
            raise _failure("unsafe-archive-member")

    def finish(self) -> list[TreeEntry]:
        for entry in self.entries.values():
            if entry.kind == "symlink" and not _confined_symlink_target(entry.path, str(entry.target), self.kinds):
                raise _failure("unsafe-archive-member")
        observed = (
            self.counts["file"],
            self.counts["directory"],
            self.counts["symlink"],
            self.expanded_bytes,
        )
        expected = (
            self.limits.file_count,
            self.limits.directory_count,
            self.limits.symlink_count,
            self.limits.expanded_bytes,
        )
        if self.limits.exact and observed != expected:
            raise _failure("installed-manifest-mismatch")
        return [self.entries[name] for name in sorted(self.entries)]


def _drain_compressed_trailer(decompressed: gzip.GzipFile) -> None:
    """Read to the gzip end so its CRC and length are validated, within a bound."""

    remaining = MAX_TREE_TRAILER_BYTES
    while chunk := decompressed.read(min(_CHUNK_BYTES, remaining + 1)):
        remaining -= len(chunk)
        if remaining < 0:
            raise _failure("archive-size-limit")


def _admit_archive_stream(stream: BinaryIO, limits: _TreeLimits, sink: _StageSink | None) -> list[TreeEntry]:
    admission = _TreeAdmission(limits, sink)
    try:
        # tarfile's own streaming gzip reader stops at the tar end marker without
        # checking the gzip trailer, so decompression is delegated to GzipFile.
        with gzip.GzipFile(fileobj=stream, mode="rb") as decompressed:
            with tarfile.open(fileobj=decompressed, mode="r|", encoding="utf-8", errors="strict") as archive:
                for member in archive:
                    admission.admit(member, archive)
            _drain_compressed_trailer(decompressed)
    except RuntimeError:
        raise
    except (OSError, EOFError, UnicodeError, tarfile.TarError, zlib.error) as exc:
        if isinstance(exc, OSError) and exc.errno in {errno.ENOSPC, getattr(errno, "EDQUOT", -1)}:
            raise
        raise _failure("unsafe-archive") from exc
    return admission.finish()


def manifest_bytes(entries: Iterable[TreeEntry]) -> bytes:
    """Return the canonical installed-tree manifest encoding."""

    document = {
        "entries": [entry.document() for entry in sorted(entries, key=lambda item: item.path)],
        "format": TREE_FORMAT,
        "schema": TREE_MANIFEST_SCHEMA,
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _bounded_manifest_bytes(entries: Iterable[TreeEntry]) -> bytes:
    """Return the canonical manifest only when a validator can reopen it later."""

    payload = manifest_bytes(entries)
    if len(payload) > MAX_TREE_MANIFEST_BYTES:
        raise _failure("archive-size-limit")
    return payload


def _tree_descriptor(entries: list[TreeEntry]) -> dict[str, object]:
    return {
        "directory_count": sum(entry.kind == "directory" for entry in entries),
        "expanded_bytes": sum(entry.size or 0 for entry in entries if entry.kind == "file"),
        "file_count": sum(entry.kind == "file" for entry in entries),
        "format": TREE_FORMAT,
        "manifest_sha256": hashlib.sha256(manifest_bytes(entries)).hexdigest(),
        "symlink_count": sum(entry.kind == "symlink" for entry in entries),
    }


def _validated_descriptor(
    selection: TreeSelection,
) -> InstalledTree:  # NOSONAR -- closed selection checks fail closed.
    descriptor = selection.installed_tree
    raw = selection.raw_manifest
    counts = (
        (
            (descriptor.file_count, 1),
            (descriptor.directory_count, 1),
            (descriptor.symlink_count, 0),
            (descriptor.expanded_bytes, 1),
        )
        if descriptor is not None
        else ()
    )
    if (
        descriptor is None
        or descriptor.format != TREE_FORMAT
        or not isinstance(descriptor.manifest_sha256, str)
        or _SHA256_RE.fullmatch(descriptor.manifest_sha256) is None
        or any(not isinstance(value, int) or isinstance(value, bool) or value < floor for value, floor in counts)
        or descriptor.file_count + descriptor.directory_count + descriptor.symlink_count > MAX_TREE_MEMBERS
        or descriptor.expanded_bytes > MAX_TREE_EXPANDED_BYTES
        or len(raw) != 1
        or not isinstance(raw[0].sha256, str)
        or _SHA256_RE.fullmatch(raw[0].sha256) is None
        or not isinstance(raw[0].size, int)
        or isinstance(raw[0].size, bool)
        or not 1 <= raw[0].size <= MAX_TREE_RAW_BYTES
        or not selection.installed_manifest
        or sum(entry.executable is True for entry in selection.installed_manifest) != 1
        or not selection.policy_refs
        or not all(isinstance(reference, str) and reference for reference in selection.policy_refs)
    ):
        raise _failure("invalid-selection")
    for entry in selection.installed_manifest:
        _tree_path(entry.path)
    return descriptor


def _policy_identity(selection: TreeSelection) -> str:
    encoded = json.dumps(
        {
            "installation_policy": INSTALLATION_TREE_POLICY_ID,
            "policy_refs": list(selection.policy_refs),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _raw_parent(installation_root: Path, selection: TreeSelection) -> Path:
    return (
        installation_root
        / installation._safe_component(selection.artifact_id)
        / installation._safe_component(selection.platform_id)
        / selection.raw_manifest[0].sha256
    )


def tree_installation_path(installation_root: Path, selection: TreeSelection) -> Path:
    """Return the content-addressed installation path for a validated tree selection."""

    descriptor = _validated_descriptor(selection)
    return (
        _raw_parent(installation_root, selection)
        / INSTALLATION_TREE_POLICY_ID
        / _policy_identity(selection)
        / descriptor.manifest_sha256
    )


def _open_flags() -> int:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    return flags | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOINHERIT", 0)


def _raw_state_is_admissible(state: os.stat_result, entry: ManifestEntry, mode: str) -> bool:
    permissions = state.st_mode & 0o777
    expected_mode = {"installed": 0o400, "staged": 0o600, "carrier": 0o600}.get(mode)
    private = mode == "input" or (state.st_uid == os.geteuid() and state.st_nlink == 1 and permissions == expected_mode)
    return stat.S_ISREG(state.st_mode) and state.st_size == entry.size and private


@contextmanager
def _opened_verified_raw(path: Path, entry: ManifestEntry, *, mode: str) -> Iterator[BinaryIO]:
    """Yield one opened raw inode after verifying its exact size and digest through it."""

    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not _raw_state_is_admissible(before, entry, mode):
        raise _failure("raw-manifest-mismatch")
    descriptor = os.open(path, _open_flags())
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened):
            raise _failure("raw-manifest-mismatch")
        digest = hashlib.sha256()
        total = 0
        while chunk := stream.read(min(_CHUNK_BYTES, entry.size + 1 - total)):
            total += len(chunk)
            digest.update(chunk)
        if total != entry.size or digest.hexdigest() != entry.sha256:
            raise _failure("raw-manifest-mismatch")
        stream.seek(0)
        yield stream
        after = os.fstat(stream.fileno())
        unchanged = (
            after.st_size == opened.st_size
            and after.st_mtime_ns == opened.st_mtime_ns
            and after.st_ctime_ns == opened.st_ctime_ns
            and os.path.samestat(opened, path.lstat())
        )
        if not unchanged:
            raise _failure("raw-manifest-mismatch")


def _verify_raw_file(path: Path, entry: ManifestEntry, *, mode: str) -> None:
    with _opened_verified_raw(path, entry, mode=mode):
        pass


def describe_archive_tree(archive: Path, raw_entry: ManifestEntry) -> dict[str, object]:
    """Return the reviewable installed-tree descriptor of one lock-verified archive."""

    try:
        with _opened_verified_raw(archive, raw_entry, mode="input") as stream:
            entries = _admit_archive_stream(stream, _CEILING_LIMITS, None)
    except RuntimeError:
        raise
    except OSError:
        raise _failure("raw-manifest-mismatch") from None
    _bounded_manifest_bytes(entries)
    return _tree_descriptor(entries)


def _verify_tree_file(path: Path, before: os.stat_result, entry: TreeEntry) -> None:
    expected_mode = 0o500 if entry.executable else 0o400
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size != entry.size
        or before.st_mode & 0o777 != expected_mode
    ):
        raise _failure("tree-integrity-failure")
    descriptor = os.open(path, _open_flags())
    digest = hashlib.sha256()
    total = 0
    size = int(entry.size or 0)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not os.path.samestat(before, opened):
            raise _failure("tree-integrity-failure")
        while chunk := stream.read(min(_CHUNK_BYTES, size + 1 - total)):
            total += len(chunk)
            digest.update(chunk)
    if total != size or digest.hexdigest() != entry.sha256 or not os.path.samestat(opened, path.lstat()):
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


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key")
        result[key] = value
    return result


def _manifest_entry(
    value: object,
) -> TreeEntry:  # NOSONAR -- closed manifest entry shapes fail closed.
    if not isinstance(value, dict):
        raise ValueError("manifest entry")
    kind = value.get("kind")
    path = _tree_path(value.get("path")).as_posix()
    if kind == "directory" and set(value) == {"kind", "path"}:
        return TreeEntry(path, "directory")
    if (
        kind == "symlink"
        and set(value) == {"kind", "path", "target"}
        and _symlink_target_shape_is_safe(value["target"])
    ):
        return TreeEntry(path, "symlink", target=value["target"])
    size = value.get("size")
    if (
        kind == "file"
        and set(value) == {"executable", "kind", "path", "sha256", "size"}
        and isinstance(value["executable"], bool)
        and isinstance(value["sha256"], str)
        and _SHA256_RE.fullmatch(value["sha256"]) is not None
        and isinstance(size, int)
        and not isinstance(size, bool)
        and size >= 0
    ):
        return TreeEntry(path, "file", value["sha256"], size, value["executable"])
    raise ValueError("manifest entry")


def _parse_manifest(payload: bytes, descriptor: InstalledTree) -> dict[str, TreeEntry]:
    try:
        document = json.loads(payload.decode("ascii"), object_pairs_hook=_reject_duplicate_keys)
        if (
            not isinstance(document, dict)
            or set(document) != {"entries", "format", "schema"}
            or document["schema"] != TREE_MANIFEST_SCHEMA
            or document["format"] != TREE_FORMAT
            or not isinstance(document["entries"], list)
        ):
            raise ValueError("manifest shape")
        entries = [_manifest_entry(value) for value in document["entries"]]
    except (RuntimeError, UnicodeError, ValueError) as exc:
        raise _failure("tree-integrity-failure") from exc
    by_path = {entry.path: entry for entry in entries}
    if (
        len(by_path) != len(entries)
        or manifest_bytes(entries) != payload
        or _tree_descriptor(entries)
        != {
            "directory_count": descriptor.directory_count,
            "expanded_bytes": descriptor.expanded_bytes,
            "file_count": descriptor.file_count,
            "format": descriptor.format,
            "manifest_sha256": descriptor.manifest_sha256,
            "symlink_count": descriptor.symlink_count,
        }
    ):
        raise _failure("tree-integrity-failure")
    kinds = {entry.path: entry.kind for entry in entries}
    for entry in entries:
        parent = PurePosixPath(entry.path).parent.as_posix()
        if parent != "." and kinds.get(parent) != "directory":
            raise _failure("tree-integrity-failure")
        if entry.kind == "symlink" and not _confined_symlink_target(entry.path, str(entry.target), kinds):
            raise _failure("tree-integrity-failure")
    return by_path


def _require_installed_manifest(selection: TreeSelection, entries: Mapping[str, TreeEntry]) -> None:
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
        or before.st_size > MAX_TREE_MANIFEST_BYTES
    ):
        raise _failure("tree-integrity-failure")
    descriptor = os.open(path, _open_flags())
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not os.path.samestat(before, opened):
            raise _failure("tree-integrity-failure")
        payload = stream.read(MAX_TREE_MANIFEST_BYTES + 1)
    if len(payload) != before.st_size or not os.path.samestat(opened, path.lstat()):
        raise _failure("tree-integrity-failure")
    return payload


def _validated_installation(target: Path, selection: TreeSelection) -> Path:
    descriptor = _validated_descriptor(selection)
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
    entries = _parse_manifest(payload, descriptor)
    _require_installed_manifest(selection, entries)
    _validate_tree_contents(target / TREE_CONTENT_NAME, entries)
    return target / TREE_CONTENT_NAME


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _make_stage_durable(stage: Path, entries: list[TreeEntry]) -> None:
    """Make every sealed staged file, mode, and directory entry durable.

    Linux ``sync(2)`` waits for I/O completion and gives the same guarantee as
    calling fsync on every file in the system (sync(2) manual page), so one call
    replaces tens of thousands of per-file fsyncs for a proof distribution.
    Other platforms keep explicit per-entry synchronization.
    """

    content = stage / TREE_CONTENT_NAME
    if platform.system() == "Linux":
        os.sync()
    else:
        for entry in entries:
            if entry.kind == "file":
                _fsync_file(content.joinpath(*PurePosixPath(entry.path).parts))
        for entry in entries:
            if entry.kind == "directory":
                installation._fsync_directory(content.joinpath(*PurePosixPath(entry.path).parts))
        _fsync_file(stage / TREE_MANIFEST_NAME)
    installation._fsync_directory(content)
    installation._fsync_directory(stage)


def _seal_stage(stage: Path, entries: list[TreeEntry]) -> None:
    content = stage / TREE_CONTENT_NAME
    for entry in entries:
        if entry.kind == "file":
            content.joinpath(*PurePosixPath(entry.path).parts).chmod(0o500 if entry.executable else 0o400)
    directories = [entry for entry in entries if entry.kind == "directory"]
    for entry in sorted(directories, key=lambda item: len(PurePosixPath(item.path).parts), reverse=True):
        content.joinpath(*PurePosixPath(entry.path).parts).chmod(0o500)
    content.chmod(0o500)
    (stage / TREE_MANIFEST_NAME).chmod(0o400)
    _make_stage_durable(stage, entries)


def _discard(path: Path) -> None:
    if installation._tree_present(path):
        installation._make_quarantine_non_executable(path)
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


def _install_from_raw(target: Path, raw_object: Path, selection: TreeSelection) -> Path:
    descriptor = _validated_descriptor(selection)
    limits = _TreeLimits(
        file_count=descriptor.file_count,
        directory_count=descriptor.directory_count,
        symlink_count=descriptor.symlink_count,
        expanded_bytes=descriptor.expanded_bytes,
        exact=True,
    )
    stage = Path(tempfile.mkdtemp(prefix=f".stage-{target.name}-", dir=target.parent))
    try:
        stage.chmod(0o700)
        content = stage / TREE_CONTENT_NAME
        content.mkdir(mode=0o700)
        with _opened_verified_raw(raw_object, selection.raw_manifest[0], mode="installed") as stream:
            entries = _admit_archive_stream(stream, limits, _StageSink(content))
        payload = _bounded_manifest_bytes(entries)
        if hashlib.sha256(payload).hexdigest() != descriptor.manifest_sha256:
            raise _failure("installed-manifest-mismatch")
        _require_installed_manifest(selection, {entry.path: entry for entry in entries})
        installation._write_file(stage / TREE_MANIFEST_NAME, payload)
        installation._publication_checkpoint("staged-written", stage)
        _seal_stage(stage, entries)
        installation._seal_staged_root(stage)
        installation._publication_checkpoint("staged-durable", stage)
        installation._publish_staged_root(stage, target)
        installation._publication_checkpoint("published", target)
        installation._fsync_directory(target.parent)
        installation._publication_checkpoint("parent-durable", target)
    finally:
        _discard(stage)
    return _validated_installation(target, selection)


def _publish_raw(source: Path, raw_object: Path) -> None:
    source.chmod(0o400)
    _fsync_file(source)
    installation._publication_checkpoint("raw-staged-durable", source)
    os.rename(source, raw_object)
    installation._fsync_directory(raw_object.parent)
    installation._publication_checkpoint("raw-published", raw_object)


def _admit_raw_object(
    raw_parent: Path,
    selection: TreeSelection,
    acquire_raw: Callable[[Path], None],
    quarantine_root: Path,
) -> Path:
    entry = selection.raw_manifest[0]
    raw_object = raw_parent / RAW_OBJECT_NAME
    carriers = sorted(raw_parent.glob(f"{LEGACY_CARRIER_PREFIX}*"))
    if installation._tree_present(raw_object):
        for carrier in carriers:
            installation._quarantine(carrier, quarantine_root, prefix="legacy")
        try:
            _verify_raw_file(raw_object, entry, mode="installed")
        except (OSError, RuntimeError):
            installation._quarantine(raw_object, quarantine_root, prefix="raw")
            raise _failure("raw-integrity-failure") from None
        return raw_object
    if carriers:
        for extra in carriers[1:]:
            installation._quarantine(extra, quarantine_root, prefix="legacy")
        try:
            _verify_raw_file(carriers[0], entry, mode="carrier")
        except (OSError, RuntimeError):
            installation._quarantine(carriers[0], quarantine_root, prefix="legacy")
            raise _failure("legacy-integrity-failure") from None
        _publish_raw(carriers[0], raw_object)
        return raw_object
    descriptor, staged_name = tempfile.mkstemp(prefix=".stage-raw-", dir=raw_parent)
    os.close(descriptor)
    staged = Path(staged_name)
    try:
        acquire_raw(staged)
        try:
            _verify_raw_file(staged, entry, mode="staged")
        except (OSError, RuntimeError):
            raise _failure("raw-manifest-mismatch") from None
        _publish_raw(staged, raw_object)
    finally:
        staged.unlink(missing_ok=True)
    return raw_object


def _migrate_legacy(legacy: LegacyTreeInputs, raw_parent: Path, quarantine_root: Path) -> None:
    carrier = legacy.raw_carrier
    if carrier is not None and installation._tree_present(carrier):
        state = carrier.lstat()
        if not stat.S_ISREG(state.st_mode) or state.st_uid != os.geteuid():
            installation._quarantine(carrier, quarantine_root, prefix="legacy")
            raise _failure("legacy-integrity-failure")
        destination = raw_parent / f"{LEGACY_CARRIER_PREFIX}{uuid.uuid4().hex}"
        os.replace(carrier, destination)
        destination.chmod(0o600)
        installation._fsync_directory(carrier.parent)
        installation._fsync_directory(raw_parent)
    for derived in legacy.derived_paths:
        if installation._tree_present(derived):
            installation._quarantine(derived, quarantine_root, prefix="legacy")


def _validated_or_quarantined(target: Path, selection: TreeSelection, quarantine_root: Path) -> Path:
    try:
        installation._complete_interrupted_seal(target)
        return _validated_installation(target, selection)
    except (OSError, RuntimeError):
        installation._quarantine(target, quarantine_root, prefix="cache")
        raise _failure("cache-integrity-failure") from None


def _ensure_tree(
    install_root: Path,
    selection: TreeSelection,
    *,
    acquire_raw: Callable[[Path], None],
    legacy: LegacyTreeInputs | None,
) -> Path:
    installation._require_qualified_filesystem(install_root)
    target = tree_installation_path(install_root, selection)
    raw_parent = _raw_parent(install_root, selection)
    artifact_root = install_root / selection.artifact_id
    lock_root = artifact_root / ".locks"
    quarantine_root = artifact_root / ".quarantine"
    for directory in (target.parent, lock_root, quarantine_root):
        installation._ensure_private_subdirectory(directory, install_root)
    identity_lock = lock_root / f"install-tree-{selection.raw_manifest[0].sha256}.lock"
    migration_lock = lock_root / f"migration-tree-{selection.platform_id}.lock"

    if installation._tree_present(target):
        try:
            return _validated_installation(target, selection)
        except (OSError, RuntimeError):
            with installation._portable_lock(identity_lock, timeout=TREE_LOCK_TIMEOUT_SECONDS):
                if installation._tree_present(target):  # NOSONAR -- recheck under the lock closes the race.
                    return _validated_or_quarantined(target, selection, quarantine_root)
            raise _failure("cache-integrity-failure") from None

    if legacy is not None:
        with installation._portable_lock(migration_lock, timeout=TREE_LOCK_TIMEOUT_SECONDS):
            _migrate_legacy(legacy, raw_parent, quarantine_root)

    with installation._portable_lock(identity_lock, timeout=TREE_LOCK_TIMEOUT_SECONDS):
        installation._clean_staging(target.parent, target.name)
        for staged_raw in raw_parent.glob(".stage-raw-*"):
            _discard(staged_raw)
        if installation._tree_present(target):
            return _validated_or_quarantined(target, selection, quarantine_root)
        raw_object = _admit_raw_object(raw_parent, selection, acquire_raw, quarantine_root)
        return _install_from_raw(target, raw_object, selection)


def _storage_failure(exc: OSError) -> RuntimeError:
    reason = "storage-exhausted" if exc.errno in {errno.ENOSPC, getattr(errno, "EDQUOT", -1)} else "filesystem-failure"
    return _failure(reason)


def ensure_verified_tree_installation(
    repo_root: Path,
    selection: TreeSelection,
    *,
    acquire_raw: Callable[[Path], None],
    legacy: LegacyTreeInputs | None = None,
    installation_root: Path | None = None,
) -> Path:
    """Return the root of one fully admitted, immutable installed tree."""

    try:
        install_root = installation_root or installation.default_installation_root(repo_root)
        with installation._private_root_guard(repo_root, install_root):
            return _ensure_tree(install_root, selection, acquire_raw=acquire_raw, legacy=legacy)
    except RuntimeError:
        raise
    except OSError as exc:
        raise _storage_failure(exc) from None


def require_verified_tree_installation(
    repo_root: Path,
    selection: TreeSelection,
    *,
    installation_root: Path | None = None,
) -> Path:
    """Verify an existing installed tree completely without acquiring or installing."""

    try:
        install_root = installation_root or installation.default_installation_root(repo_root)
        with installation._private_root_guard(repo_root, install_root):
            installation._require_qualified_filesystem(install_root)
            target = tree_installation_path(install_root, selection)
            if not installation._tree_present(target):
                raise _failure("installation-missing")
            try:
                return _validated_installation(target, selection)
            except (OSError, RuntimeError):
                raise _failure("cache-integrity-failure") from None
    except RuntimeError:
        raise
    except OSError as exc:
        raise _storage_failure(exc) from None


__all__ = [
    "INSTALLATION_TREE_POLICY_ID",
    "LegacyTreeInputs",
    "TreeEntry",
    "describe_archive_tree",
    "ensure_verified_tree_installation",
    "manifest_bytes",
    "require_verified_tree_installation",
    "tree_installation_path",
]
