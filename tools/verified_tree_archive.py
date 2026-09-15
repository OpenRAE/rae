"""Bounded admission of a reviewed tar.gz tree and its canonical manifest.

This module owns what a proof-distribution archive may contain and how the
admitted tree is described: portable member paths, confined relative symbolic
links, exact counts and bytes, and the canonical manifest whose SHA-256 the
reviewed lock records. :mod:`tools.verified_tree_installation` owns the
filesystem transaction that publishes and revalidates the tree.
"""

from __future__ import annotations

import errno
import gzip
import hashlib
import json
import os
import posixpath
import re
import tarfile
import zlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol

TREE_MANIFEST_SCHEMA = "raes-installed-tree/v1"
TREE_FORMAT = "tar.gz"
MAX_TREE_MEMBERS = 262_144
MAX_TREE_EXPANDED_BYTES = 16 * 1024 * 1024 * 1024
MAX_TREE_PATH_BYTES = 1024
MAX_TREE_PATH_DEPTH = 64
MAX_SYMLINK_TARGET_BYTES = 1024
MAX_TREE_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_TREE_TRAILER_BYTES = 1024 * 1024
CHUNK_BYTES = 1024 * 1024
SHA256_RE = re.compile(r"[0-9a-f]{64}")
_UNSAFE_PATH_PARTS = frozenset({"", ".", ".."})


class InstalledTree(Protocol):
    format: str
    manifest_sha256: str
    file_count: int
    directory_count: int
    symlink_count: int
    expanded_bytes: int


def failure(reason: str) -> RuntimeError:
    return RuntimeError(f"tool-installation: {reason}")


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
class TreeLimits:
    file_count: int
    directory_count: int
    symlink_count: int
    expanded_bytes: int
    exact: bool

    def for_kind(self, kind: str) -> int:
        return {"file": self.file_count, "directory": self.directory_count, "symlink": self.symlink_count}[kind]


CEILING_LIMITS = TreeLimits(
    file_count=MAX_TREE_MEMBERS,
    directory_count=MAX_TREE_MEMBERS,
    symlink_count=MAX_TREE_MEMBERS,
    expanded_bytes=MAX_TREE_EXPANDED_BYTES,
    exact=False,
)


def _path_is_unsafe(value: str, path: PurePosixPath) -> bool:
    violations = (
        not value,
        value != path.as_posix(),
        path.is_absolute(),
        "\\" in value,
        "\x00" in value,
        re.match(r"^[A-Za-z]:", value) is not None,
        len(value.encode("utf-8")) > MAX_TREE_PATH_BYTES,
        len(path.parts) > MAX_TREE_PATH_DEPTH,
        bool(_UNSAFE_PATH_PARTS.intersection(path.parts)),
    )
    return any(violations)


def tree_path(value: object) -> PurePosixPath:
    """Return a portable, normalized relative member path or fail closed."""

    if not isinstance(value, str):
        raise failure("unsafe-archive-member")
    path = PurePosixPath(value)
    if _path_is_unsafe(value, path):
        raise failure("unsafe-archive-member")
    return path


def symlink_target_shape_is_safe(target: object) -> bool:
    return (
        isinstance(target, str)
        and bool(target)
        and "\x00" not in target
        and "\\" not in target
        and not target.startswith("/")
        and len(target.encode("utf-8")) <= MAX_SYMLINK_TARGET_BYTES
    )


def _resolution_step(parts: list[str], component: str, is_last: bool, kinds: Mapping[str, str]) -> bool | None:
    """Advance one symlink-target component; return a final verdict or ``None`` to continue."""

    verdict: bool | None = None
    if component in {"", "."} or (component == ".." and not parts):
        verdict = False
    elif component == "..":
        parts.pop()
    else:
        parts.append(component)
        kind = kinds.get("/".join(parts))
        if kind is None:
            verdict = True
        elif kind == "symlink" or (not is_last and kind != "directory"):
            verdict = False
    return verdict


def confined_symlink_target(link: str, target: str, kinds: Mapping[str, str]) -> bool:
    """Return whether kernel resolution of ``target`` cannot leave the tree.

    Every existing component that resolution passes through must be a real
    directory, never another symbolic link. Resolution that reaches a component
    absent from the immutable tree stops there with ENOENT, so a dangling link
    whose resolved prefix stays inside the tree is confined.
    """

    link_directory = posixpath.dirname(link) or "."
    canonical = posixpath.relpath(posixpath.normpath(posixpath.join(link_directory, target)), link_directory)
    verdict: bool | None = None if symlink_target_shape_is_safe(target) and canonical == target else False
    parts = list(PurePosixPath(link).parts[:-1])
    components = target.split("/") if verdict is None else []
    for index, component in enumerate(components):
        verdict = _resolution_step(parts, component, index == len(components) - 1, kinds)
        if verdict is not None:
            break
    return True if verdict is None else verdict


class StageSink:
    """Materialize admitted members inside one private staging directory."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, path: PurePosixPath) -> str:
        # The member path is already portable and every parent is a real staged
        # directory; the canonical containment check also refuses any escape a
        # concurrently substituted parent could introduce.
        root = os.path.realpath(self.root)
        candidate = os.path.realpath(os.path.join(root, *path.parts))
        if os.path.commonpath((root, candidate)) != root or candidate == root:
            raise failure("unsafe-archive-member")
        return candidate

    def directory(self, path: PurePosixPath) -> None:
        os.mkdir(self._path(path), 0o700)

    def file(self, path: PurePosixPath, source: BinaryIO, size: int) -> str:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(self._path(path), flags, 0o600)
        try:
            return _copy_member(source, size, descriptor)
        finally:
            os.close(descriptor)

    def symlink(self, path: PurePosixPath, target: str) -> None:
        """Create one confined link after the complete tree has been admitted.

        The written target is recomputed from its resolved in-stage location, so
        only a canonical relative path that stays inside the stage is created.
        """

        link = self._path(path)
        link_directory = os.path.dirname(link)
        root = os.path.realpath(self.root)
        resolved = os.path.realpath(os.path.join(link_directory, target))
        if os.path.commonpath((root, resolved)) != root:
            raise failure("unsafe-archive-member")
        canonical = os.path.relpath(resolved, link_directory)
        if canonical != target:
            raise failure("unsafe-archive-member")
        os.symlink(canonical, link)


def _copy_member(source: BinaryIO, size: int, descriptor: int | None) -> str:
    """Hash exactly ``size`` member bytes, writing them when a descriptor is given."""

    digest = hashlib.sha256()
    total = 0
    while chunk := source.read(min(CHUNK_BYTES, size + 1 - total)):
        total += len(chunk)
        if total > size:
            raise failure("installed-manifest-mismatch")
        digest.update(chunk)
        view = memoryview(chunk)
        while descriptor is not None and view:
            view = view[os.write(descriptor, view) :]
    if total != size:
        raise failure("installed-manifest-mismatch")
    return digest.hexdigest()


class TreeAdmission:
    """Streaming, bounded admission of one tar.gz carrier into canonical entries."""

    def __init__(self, limits: TreeLimits, sink: StageSink | None) -> None:
        self.limits = limits
        self.sink = sink
        self.kinds: dict[str, str] = {}
        self.entries: dict[str, TreeEntry] = {}
        self.explicit_directories: set[str] = set()
        self.counts = {"file": 0, "directory": 0, "symlink": 0}
        self.expanded_bytes = 0

    def _record(self, entry: TreeEntry) -> None:
        self.counts[entry.kind] += 1
        if self.counts[entry.kind] > self.limits.for_kind(entry.kind) or sum(self.counts.values()) > MAX_TREE_MEMBERS:
            raise failure("archive-member-limit")
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
                raise failure("conflicting-archive-member")

    def _directory(self, path: PurePosixPath) -> None:
        name = path.as_posix()
        existing = self.kinds.get(name)
        if existing is not None and (existing != "directory" or name in self.explicit_directories):
            raise failure("duplicate-archive-member")
        self.explicit_directories.add(name)
        if existing is None:
            self._record(TreeEntry(name, "directory"))
            if self.sink is not None:
                self.sink.directory(path)

    def _file(self, path: PurePosixPath, member: tarfile.TarInfo, archive: tarfile.TarFile) -> None:
        self.expanded_bytes += member.size
        if member.size < 0 or self.expanded_bytes > self.limits.expanded_bytes:
            raise failure("archive-size-limit")
        source = archive.extractfile(member)
        if source is None:
            raise failure("unsafe-archive-member")
        if self.sink is not None:
            digest = self.sink.file(path, source, member.size)
        else:
            digest = _copy_member(source, member.size, None)
        self._record(TreeEntry(path.as_posix(), "file", digest, member.size, bool(member.mode & 0o100)))

    def _symlink(self, path: PurePosixPath, member: tarfile.TarInfo) -> None:
        if not symlink_target_shape_is_safe(member.linkname):
            raise failure("unsafe-archive-member")
        # Links are created only after every member is admitted and confined.
        self._record(TreeEntry(path.as_posix(), "symlink", target=member.linkname))

    def admit(self, member: tarfile.TarInfo, archive: tarfile.TarFile) -> None:
        path = tree_path(member.name)
        self._ensure_parents(path)
        if member.isdir():
            self._directory(path)
        elif path.as_posix() in self.kinds:
            raise failure("duplicate-archive-member")
        elif member.isreg() and not member.issparse():
            self._file(path, member, archive)
        elif member.issym():
            self._symlink(path, member)
        else:
            raise failure("unsafe-archive-member")

    def finish(self) -> list[TreeEntry]:
        for entry in self.entries.values():
            if entry.kind == "symlink" and not confined_symlink_target(entry.path, str(entry.target), self.kinds):
                raise failure("unsafe-archive-member")
        observed = (self.counts["file"], self.counts["directory"], self.counts["symlink"], self.expanded_bytes)
        expected = (
            self.limits.file_count,
            self.limits.directory_count,
            self.limits.symlink_count,
            self.limits.expanded_bytes,
        )
        if self.limits.exact and observed != expected:
            raise failure("installed-manifest-mismatch")
        entries = [self.entries[name] for name in sorted(self.entries)]
        if self.sink is not None:
            for entry in entries:
                if entry.kind == "symlink":
                    self.sink.symlink(PurePosixPath(entry.path), str(entry.target))
        return entries


def _drain_compressed_trailer(decompressed: gzip.GzipFile) -> None:
    """Read to the gzip end so its CRC and length are validated, within a bound."""

    remaining = MAX_TREE_TRAILER_BYTES
    while chunk := decompressed.read(min(CHUNK_BYTES, remaining + 1)):
        remaining -= len(chunk)
        if remaining < 0:
            raise failure("archive-size-limit")


def admit_archive_stream(stream: BinaryIO, limits: TreeLimits, sink: StageSink | None) -> list[TreeEntry]:
    """Admit one tar.gz stream completely and return its canonical entries."""

    admission = TreeAdmission(limits, sink)
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
        raise failure("unsafe-archive") from exc
    return admission.finish()


def manifest_bytes(entries: Iterable[TreeEntry]) -> bytes:
    """Return the canonical installed-tree manifest encoding."""

    document = {
        "entries": [entry.document() for entry in sorted(entries, key=lambda item: item.path)],
        "format": TREE_FORMAT,
        "schema": TREE_MANIFEST_SCHEMA,
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def bounded_manifest_bytes(entries: Iterable[TreeEntry]) -> bytes:
    """Return the canonical manifest only when a validator can reopen it later."""

    payload = manifest_bytes(entries)
    if len(payload) > MAX_TREE_MANIFEST_BYTES:
        raise failure("archive-size-limit")
    return payload


def tree_descriptor(entries: list[TreeEntry]) -> dict[str, object]:
    return {
        "directory_count": sum(entry.kind == "directory" for entry in entries),
        "expanded_bytes": sum(entry.size or 0 for entry in entries if entry.kind == "file"),
        "file_count": sum(entry.kind == "file" for entry in entries),
        "format": TREE_FORMAT,
        "manifest_sha256": hashlib.sha256(manifest_bytes(entries)).hexdigest(),
        "symlink_count": sum(entry.kind == "symlink" for entry in entries),
    }


__all__ = [
    "CEILING_LIMITS",
    "MAX_TREE_EXPANDED_BYTES",
    "MAX_TREE_MANIFEST_BYTES",
    "MAX_TREE_MEMBERS",
    "StageSink",
    "TreeEntry",
    "TreeLimits",
    "admit_archive_stream",
    "bounded_manifest_bytes",
    "confined_symlink_target",
    "manifest_bytes",
    "tree_descriptor",
    "tree_path",
]
