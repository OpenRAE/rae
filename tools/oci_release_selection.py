#!/usr/bin/env python3
"""Projection of the reviewed release-test image from the development lock.

The image identity is reviewed lock data, never a literal in a consumer. This
module resolves that data into the per-platform object graph the admission
boundary verifies, and is the recorded consumer of the locked artifact because
the literal selection call lives here.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

# Runnable as a script's import root, like every other tool entry point here.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.oci_image_layout import LockedPlatformGraph, OciDescriptor  # noqa: E402
from tools.tooling_oci_selection import LockedOciDescriptor  # noqa: E402
from tools.tooling_policy_gate import LockedArtifactSelection  # noqa: E402

# The reviewed lock selection this module admits.
RELEASE_TEST_IMAGE_ARTIFACT_ID = "release-test-alpine"
RELEASE_TEST_IMAGE_VERSION = "3.20.10"
# Every platform a mirror or offline export must carry.
REQUIRED_PLATFORM_IDS = ("linux-x86_64", "linux-arm64")
# The one platform the release lane executes on. arm64 is retained and exported,
# but claiming arm64 execution would need daemon evidence this repository does
# not have (see `docs/decisions/package-artifacts/architecture.md`).
EXECUTION_PLATFORM_ID = "linux-x86_64"
EXECUTION_PROFILE_ID = "public-linux-x86_64"

_REPOSITORY_RE = re.compile(
    r"^(?:(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)(?:\.(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?))*"
    r"(?::[0-9]{1,5})?/)?[a-z0-9]+(?:(?:[._]|__|[-]+)[a-z0-9]+)*"
    r"(?:/[a-z0-9]+(?:(?:[._]|__|[-]+)[a-z0-9]+)*)*$"
)


class ImageAdmissionError(Exception):
    """The reviewed release-test image could not be admitted.

    Carries a stable reason code only. A mirror endpoint, credential, image
    reference or native client output never reaches the message. Defined here,
    at the projection layer, so every refusal the client boundary above can
    raise is one type.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"release-test image admission failed: {reason}")
        self.reason = reason


SelectionLoader = Callable[..., "object"]

# The lock admits arm64 for retention and export; only the execution platform
# has a profile that also claims a daemon can run it.
_PLATFORM_PROFILES = {
    "linux-x86_64": "public-linux-x86_64",
    "linux-arm64": "public-linux-arm64",
}


def _default_selection_loader(*, version: str, platform_id: str, profile_id: str) -> LockedArtifactSelection:
    """Load one reviewed lock selection through the canonical policy gate.

    The artifact id is a literal here on purpose: the selector policy reads it
    statically, so a computed id would make this consumer invisible to the
    coverage gate that proves every locked artifact has exactly one consumer.
    """

    from tools.tooling_policy_gate import load_tooling_artifact_selection

    return load_tooling_artifact_selection(
        artifact_id="release-test-alpine",
        version=version,
        platform_id=platform_id,
        profile_id=profile_id,
    )


def _descriptor(value: LockedOciDescriptor) -> OciDescriptor:
    return OciDescriptor(digest=value.digest, size=value.size)


def locked_repository(*, loader: SelectionLoader = _default_selection_loader) -> str:
    """Return the reviewed image repository, without its registry-neutral scheme."""

    selection = _select(EXECUTION_PLATFORM_ID, loader)
    return _asset(selection)


def _asset(selection: LockedArtifactSelection) -> str:
    """Return the reviewed OCI repository the locked index digest lives in."""

    asset = getattr(selection, "asset", "")
    if not isinstance(asset, str) or _REPOSITORY_RE.fullmatch(asset) is None:
        raise ImageAdmissionError("image-identity")
    return asset


def _select(platform_id: str, loader: SelectionLoader) -> LockedArtifactSelection:
    return loader(
        version=RELEASE_TEST_IMAGE_VERSION,
        platform_id=platform_id,
        profile_id=_PLATFORM_PROFILES[platform_id],
    )


def locked_platform_graphs(*, loader: SelectionLoader = _default_selection_loader) -> tuple[LockedPlatformGraph, ...]:
    """Project the reviewed graph of every platform a mirror or export must carry.

    A selection without a graph is refused rather than degraded to an index-only
    check, and every platform must sit under one reviewed index -- two indexes
    would mean two images wearing one artifact id.
    """

    graphs: list[LockedPlatformGraph] = []
    for platform_id in REQUIRED_PLATFORM_IDS:
        selection = _select(platform_id, loader)
        graph = getattr(selection, "oci_graph", None)
        if graph is None:
            raise ImageAdmissionError("graph-unavailable")
        graphs.append(
            LockedPlatformGraph(
                platform_id=platform_id,
                index=_descriptor(graph.index),
                manifest=_descriptor(graph.manifest),
                config=_descriptor(graph.config),
                layers=tuple(_descriptor(layer) for layer in graph.layers),
                diff_ids=tuple(graph.diff_ids),
                architecture=graph.architecture,
                os=graph.os,
                variant=graph.variant,
            )
        )
    if len({graph.index for graph in graphs}) != 1:
        raise ImageAdmissionError("index-identity")
    return tuple(graphs)


def execution_graph(graphs: Sequence[LockedPlatformGraph]) -> LockedPlatformGraph:
    """Return the one platform graph the release lane executes."""

    for graph in graphs:
        if graph.platform_id == EXECUTION_PLATFORM_ID:
            return graph
    raise ImageAdmissionError("graph-unavailable")


__all__ = [
    "EXECUTION_PLATFORM_ID",
    "EXECUTION_PROFILE_ID",
    "RELEASE_TEST_IMAGE_ARTIFACT_ID",
    "RELEASE_TEST_IMAGE_VERSION",
    "REQUIRED_PLATFORM_IDS",
    "SelectionLoader",
    "ImageAdmissionError",
    "execution_graph",
    "locked_platform_graphs",
    "locked_repository",
]
