"""Offline admission of an exported OCI image layout against the reviewed lock.

An export is an untrusted carrier. A client exit code, a cache hit, or a digest
the layout asserts about itself are not evidence, so every object named by the
reviewed lock is re-hashed here, from the opened file, before anything is
imported or executed. The reviewed *index* identity is the anchor: a selected
platform manifest is evidence inside that index, never a replacement for it.

This module performs no acquisition and speaks no registry protocol. It reads
bounded regular files from one directory and compares bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_BLOB_NAME_RE = re.compile(r"^[0-9a-f]{64}$")
_HASH_CHUNK_BYTES = 1024 * 1024
# A manifest, index or config is a small document. Anything larger is refused
# before it is parsed rather than after.
MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
MAX_BLOB_BYTES = 2 * 1024 * 1024 * 1024
MAX_BLOB_COUNT = 4096
_LAYOUT_VERSION = "1.0.0"


class LayoutRejected(Exception):
    """An exported layout does not match the reviewed record.

    The message carries a stable reason code only. Layout-controlled content --
    digests, paths, media types, native output -- never reaches it, so a
    rejection cannot echo attacker-chosen text into a log or evidence file.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"exported OCI layout rejected: {reason}")
        self.reason = reason


@dataclass(frozen=True)
class OciDescriptor:
    digest: str
    size: int


@dataclass(frozen=True)
class LockedPlatformGraph:
    """One platform's complete reviewed object graph."""

    platform_id: str
    index: OciDescriptor
    manifest: OciDescriptor
    config: OciDescriptor
    layers: tuple[OciDescriptor, ...]
    diff_ids: tuple[str, ...]
    architecture: str
    os: str
    variant: str | None = None


def _reject(reason: str) -> LayoutRejected:
    return LayoutRejected(reason)


def _opened_regular_file(path: Path, *, maximum_bytes: int) -> tuple[int, int]:
    """Return the size and file descriptor of a bounded, non-symlinked regular file."""

    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
    except OSError as exc:
        # ELOOP is a symlink the caller must not follow; anything else is an
        # object that is not a readable regular file.
        raise _reject("unsafe-path") from exc
    state = os.fstat(descriptor)
    if not stat.S_ISREG(state.st_mode) or state.st_nlink != 1:
        os.close(descriptor)
        raise _reject("unsafe-path")
    if state.st_size > maximum_bytes:
        os.close(descriptor)
        raise _reject("layout-shape")
    return state.st_size, descriptor


def _read_bounded(path: Path, *, maximum_bytes: int) -> bytes:
    size, descriptor = _opened_regular_file(path, maximum_bytes=maximum_bytes)
    try:
        payload = os.read(descriptor, size)
    finally:
        os.close(descriptor)
    if len(payload) != size:
        raise _reject("blob-corrupt")
    return payload


def _hashed_file(path: Path, *, maximum_bytes: int) -> tuple[str, int]:
    size, descriptor = _opened_regular_file(path, maximum_bytes=maximum_bytes)
    digest = hashlib.sha256()
    read = 0
    try:
        while chunk := os.read(descriptor, _HASH_CHUNK_BYTES):
            digest.update(chunk)
            read += len(chunk)
    finally:
        os.close(descriptor)
    if read != size:
        raise _reject("blob-corrupt")
    return f"sha256:{digest.hexdigest()}", size


def _blob_path(layout_root: Path, digest: str) -> Path:
    if _DIGEST_RE.fullmatch(digest) is None:
        raise _reject("graph-mismatch")
    return layout_root / "blobs" / "sha256" / digest.removeprefix("sha256:")


def _require_blob(layout_root: Path, descriptor: OciDescriptor) -> None:
    path = _blob_path(layout_root, descriptor.digest)
    if not path.exists():
        raise _reject("blob-missing")
    observed_digest, observed_size = _hashed_file(path, maximum_bytes=MAX_BLOB_BYTES)
    if observed_digest != descriptor.digest or observed_size != descriptor.size:
        raise _reject("blob-corrupt")


def _document(layout_root: Path, descriptor: OciDescriptor) -> dict[str, Any]:
    _require_blob(layout_root, descriptor)
    payload = _read_bounded(_blob_path(layout_root, descriptor.digest), maximum_bytes=MAX_DOCUMENT_BYTES)
    try:
        document = json.loads(payload)
    except ValueError as exc:
        raise _reject("graph-mismatch") from exc
    if not isinstance(document, dict):
        raise _reject("graph-mismatch")
    return document


def _descriptors(value: object) -> list[OciDescriptor]:
    if not isinstance(value, list):
        raise _reject("graph-mismatch")
    parsed: list[OciDescriptor] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            raise _reject("graph-mismatch")
        digest, size = entry.get("digest"), entry.get("size")
        if not isinstance(digest, str) or not isinstance(size, int) or isinstance(size, bool):
            raise _reject("graph-mismatch")
        parsed.append(OciDescriptor(digest=digest, size=size))
    return parsed


def _layout_version(layout_root: Path) -> None:
    marker = layout_root / "oci-layout"
    if not marker.exists():
        raise _reject("layout-shape")
    try:
        document = json.loads(_read_bounded(marker, maximum_bytes=MAX_DOCUMENT_BYTES))
    except ValueError as exc:
        raise _reject("layout-shape") from exc
    if not isinstance(document, dict) or document.get("imageLayoutVersion") != _LAYOUT_VERSION:
        raise _reject("layout-shape")


def _reviewed_index(layout_root: Path, index: OciDescriptor) -> dict[str, Any]:
    """Resolve the layout's entry point to exactly the reviewed index.

    A client may write the reviewed index as the entry file itself, or write it
    as a blob and wrap it in an entry index that points at it. Both spellings
    are admissible; neither may resolve to a different image, and in both cases
    the identity is proven by re-hashing bytes rather than by trusting a
    descriptor the layout supplies about itself.
    """

    entry = layout_root / "index.json"
    if not entry.exists():
        raise _reject("layout-shape")
    payload = _read_bounded(entry, maximum_bytes=MAX_DOCUMENT_BYTES)
    if f"sha256:{hashlib.sha256(payload).hexdigest()}" == index.digest and len(payload) == index.size:
        document = json.loads(payload)
        if not isinstance(document, dict):
            raise _reject("layout-shape")
        return document
    try:
        document = json.loads(payload)
    except ValueError as exc:
        raise _reject("layout-shape") from exc
    if not isinstance(document, dict):
        raise _reject("layout-shape")
    referenced = _descriptors(document.get("manifests"))
    if not any(item == index for item in referenced):
        raise _reject("index-identity")
    return _document(layout_root, index)


def _platform_closure(
    layout_root: Path,
    graph: LockedPlatformGraph,
    index_children: Sequence[OciDescriptor],
) -> set[str]:
    """Verify one platform's objects and return the digests they account for."""

    if graph.manifest not in index_children:
        raise _reject("graph-mismatch")
    manifest = _document(layout_root, graph.manifest)
    config = _descriptors([manifest.get("config")])[0]
    layers = tuple(_descriptors(manifest.get("layers")))
    if config != graph.config or layers != graph.layers:
        raise _reject("graph-mismatch")
    config_document = _document(layout_root, graph.config)
    rootfs = config_document.get("rootfs")
    diff_ids = tuple(rootfs.get("diff_ids")) if isinstance(rootfs, Mapping) else ()
    observed = (
        config_document.get("architecture"),
        config_document.get("os"),
        config_document.get("variant"),
        diff_ids,
    )
    if observed != (graph.architecture, graph.os, graph.variant, graph.diff_ids):
        raise _reject("graph-mismatch")
    for layer in graph.layers:
        _require_blob(layout_root, layer)
    return {graph.manifest.digest, graph.config.digest, *(layer.digest for layer in graph.layers)}


def _index_closure(layout_root: Path, index: OciDescriptor, children: Sequence[OciDescriptor]) -> set[str]:
    """Return every digest the reviewed index legitimately accounts for.

    Platforms outside the required set still belong to the reviewed index, so
    their objects are admitted as part of it. Anything the index does not reach
    is an object nobody reviewed.
    """

    closure = {index.digest, *(child.digest for child in children)}
    for child in children:
        path = _blob_path(layout_root, child.digest)
        if not path.exists():
            continue
        document = _document(layout_root, child)
        config = document.get("config")
        if isinstance(config, Mapping):
            closure.update(item.digest for item in _descriptors([config]))
        if isinstance(document.get("layers"), list):
            closure.update(item.digest for item in _descriptors(document.get("layers")))
    return closure


def _reject_objects_outside(layout_root: Path, closure: Iterable[str]) -> None:
    admitted = {digest.removeprefix("sha256:") for digest in closure}
    blobs = layout_root / "blobs" / "sha256"
    if blobs.is_symlink() or not blobs.is_dir():
        raise _reject("unsafe-path")
    names = sorted(entry.name for entry in blobs.iterdir())
    if len(names) > MAX_BLOB_COUNT:
        raise _reject("layout-shape")
    for name in names:
        if _BLOB_NAME_RE.fullmatch(name) is None:
            raise _reject("layout-shape")
        if name not in admitted:
            raise _reject("blob-unexpected")


def verify_layout(layout_root: Path, graphs: Sequence[LockedPlatformGraph]) -> None:
    """Admit an exported layout only when it is exactly the reviewed graph.

    Raises `LayoutRejected` with a stable reason code on the first
    discrepancy. Returning normally means every required platform's manifest,
    config and layers were present at the reviewed digest and size, the layout
    resolves to the reviewed index, and nothing outside that index is present.
    """

    if not graphs:
        raise _reject("graph-mismatch")
    if layout_root.is_symlink() or not layout_root.is_dir():
        raise _reject("unsafe-path")
    index = graphs[0].index
    if any(graph.index != index for graph in graphs):
        raise _reject("index-identity")
    _layout_version(layout_root)
    index_document = _reviewed_index(layout_root, index)
    children = _descriptors(index_document.get("manifests"))
    closure = _index_closure(layout_root, index, children)
    for graph in graphs:
        closure |= _platform_closure(layout_root, graph, children)
    _reject_objects_outside(layout_root, closure)


__all__ = [
    "LayoutRejected",
    "LockedPlatformGraph",
    "MAX_BLOB_BYTES",
    "MAX_BLOB_COUNT",
    "MAX_DOCUMENT_BYTES",
    "OciDescriptor",
    "verify_layout",
]
