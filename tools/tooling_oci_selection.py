"""Closed projection of a locked OCI image's per-platform object graph.

An index-only image has no graph; an export-bearing one is refused by the
artifact-policy gate before selection unless it carries a complete graph, so a
value that reaches here is already coherent. This module only validates the
response shape the frozen validator returned, before any client runs.

It lives beside `tooling_installed_tree`, the equivalent projection for an
extracted installed tree, so the selection gate stays a thin assembler.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

OCI_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")

INVALID_SELECTION_RESPONSE = "development artifact policy failed before acquisition: invalid selection response"


@dataclass(frozen=True)
class LockedOciDescriptor:
    digest: str
    size: int


@dataclass(frozen=True)
class LockedOciGraph:
    """One platform's reviewed index-to-layer object graph."""

    index: LockedOciDescriptor
    manifest: LockedOciDescriptor
    config: LockedOciDescriptor
    layers: tuple[LockedOciDescriptor, ...]
    diff_ids: tuple[str, ...]
    architecture: str
    os: str
    variant: str | None = None


def _refuse() -> RuntimeError:
    return RuntimeError(INVALID_SELECTION_RESPONSE)


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and OCI_DIGEST_PATTERN.fullmatch(value) is not None


def locked_oci_descriptor(value: object) -> LockedOciDescriptor:
    """Project one content descriptor, or refuse the whole response."""

    if not isinstance(value, dict):
        raise _refuse()
    digest, size = value.get("digest"), value.get("size")
    if not _is_digest(digest) or not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise _refuse()
    assert isinstance(digest, str)
    return LockedOciDescriptor(digest=digest, size=size)


def _locked_diff_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(_is_digest(item) for item in value):
        raise _refuse()
    return tuple(value)


def _locked_layers(value: object) -> tuple[LockedOciDescriptor, ...]:
    if not isinstance(value, list) or not value:
        raise _refuse()
    return tuple(locked_oci_descriptor(layer) for layer in value)


def _locked_platform_identity(graph: dict[str, object]) -> tuple[str, str, str | None]:
    architecture, operating_system, variant = graph.get("architecture"), graph.get("os"), graph.get("variant")
    named = isinstance(architecture, str) and architecture and isinstance(operating_system, str) and operating_system
    if not named or not (variant is None or (isinstance(variant, str) and variant)):
        raise _refuse()
    assert isinstance(architecture, str) and isinstance(operating_system, str)
    return architecture, operating_system, variant


def locked_oci_graph(value: object) -> LockedOciGraph | None:
    """Project a validated platform graph, or None for an index-only image."""

    if value is None:
        return None
    if not isinstance(value, dict):
        raise _refuse()
    architecture, operating_system, variant = _locked_platform_identity(value)
    return LockedOciGraph(
        index=locked_oci_descriptor(value.get("index")),
        manifest=locked_oci_descriptor(value.get("manifest")),
        config=locked_oci_descriptor(value.get("config")),
        layers=_locked_layers(value.get("layers")),
        diff_ids=_locked_diff_ids(value.get("diff_ids")),
        architecture=architecture,
        os=operating_system,
        variant=variant,
    )


__all__ = [
    "INVALID_SELECTION_RESPONSE",
    "OCI_DIGEST_PATTERN",
    "LockedOciDescriptor",
    "LockedOciGraph",
    "locked_oci_descriptor",
    "locked_oci_graph",
]
