"""Deterministic, versioned pytest node-id partitioning for CI shards.

CI distributes the canonical default-marker test suite across concurrent shard
jobs. One code-owned partition function assigns each collected pytest node id to
exactly one shard by the SHA-256 of the node id, independent of collection
order, xdist scheduling, wall-clock, filesystem order, or GitHub matrix order.

A reducer proves that the shard manifests produced by one full run are pairwise
disjoint and that their union is exactly a freshly collected canonical suite, so
coverage is combined only over a provably complete run. The partition applies
*after* the incumbent marker expression selects the suite; xdist may still
schedule work inside a single shard but is never the cross-job partitioner.

This module is intentionally free of any ``pytest`` import so the reducer can use
it without a test-runner dependency; the pytest hooks live in
``tools.pytest_shard_plugin``.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

# Bumping the algorithm changes ownership for every node id, so it is versioned
# and recorded in each manifest; the reducer refuses to combine mixed versions.
SHARD_ALGORITHM_VERSION = "sha256-nodeid-v1"

MIN_SHARD_COUNT = 1
MAX_SHARD_COUNT = 64


class ShardConfigurationError(ValueError):
    """Raised when ``shard_count`` / ``shard_index`` are outside admitted bounds."""


class ShardManifestError(ValueError):
    """Raised when shard manifests do not form a complete, disjoint partition."""


def validate_shard_count(shard_count: object) -> int:
    """Return ``shard_count`` when it is a bounded positive integer."""

    if isinstance(shard_count, bool) or not isinstance(shard_count, int):
        raise ShardConfigurationError(f"shard_count must be an integer, got {shard_count!r}")
    if not MIN_SHARD_COUNT <= shard_count <= MAX_SHARD_COUNT:
        raise ShardConfigurationError(f"shard_count {shard_count} is outside [{MIN_SHARD_COUNT}, {MAX_SHARD_COUNT}]")
    return shard_count


def validate_shard_index(shard_index: object, shard_count: object) -> tuple[int, int]:
    """Return ``(shard_index, shard_count)`` when both are consistent and bounded."""

    count = validate_shard_count(shard_count)
    if isinstance(shard_index, bool) or not isinstance(shard_index, int):
        raise ShardConfigurationError(f"shard_index must be an integer, got {shard_index!r}")
    if not 0 <= shard_index < count:
        raise ShardConfigurationError(f"shard_index {shard_index} is outside [0, {count})")
    return shard_index, count


def shard_for_nodeid(nodeid: str, shard_count: int) -> int:
    """Map one pytest node id to its owning shard index."""

    count = validate_shard_count(shard_count)
    if not isinstance(nodeid, str) or not nodeid:
        raise ShardConfigurationError("node id must be a non-empty string")
    digest = hashlib.sha256(nodeid.encode("utf-8")).digest()
    return int.from_bytes(digest, "big") % count


def owned_nodeids(nodeids: Iterable[str], shard_count: int, shard_index: int) -> list[str]:
    """Return, in input order, the node ids owned by ``shard_index``."""

    index, count = validate_shard_index(shard_index, shard_count)
    return [nodeid for nodeid in nodeids if shard_for_nodeid(nodeid, count) == index]


@dataclass(frozen=True)
class ShardManifest:
    """The exact ownership a single shard proved for one full-suite run."""

    algorithm_version: str
    source_sha: str
    suite_expression: str
    shard_count: int
    shard_index: int
    node_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "algorithm_version": self.algorithm_version,
            "source_sha": self.source_sha,
            "suite_expression": self.suite_expression,
            "shard_count": self.shard_count,
            "shard_index": self.shard_index,
            "node_ids": list(self.node_ids),
        }

    @classmethod
    def from_dict(cls, data: object) -> ShardManifest:
        if not isinstance(data, dict):
            raise ShardManifestError("shard manifest must be a JSON object")
        try:
            node_ids = data["node_ids"]
            manifest = cls(
                algorithm_version=str(data["algorithm_version"]),
                source_sha=str(data["source_sha"]),
                suite_expression=str(data["suite_expression"]),
                shard_count=data["shard_count"],
                shard_index=data["shard_index"],
                node_ids=tuple(str(nodeid) for nodeid in node_ids),
            )
        except (KeyError, TypeError) as exc:
            raise ShardManifestError(f"shard manifest is missing required fields: {exc}") from exc
        if not isinstance(manifest.shard_count, int) or isinstance(manifest.shard_count, bool):
            raise ShardManifestError("shard manifest shard_count must be an integer")
        if not isinstance(manifest.shard_index, int) or isinstance(manifest.shard_index, bool):
            raise ShardManifestError("shard manifest shard_index must be an integer")
        if not isinstance(node_ids, list):
            raise ShardManifestError("shard manifest node_ids must be a JSON array")
        return manifest


def write_manifest(path: Path, manifest: ShardManifest) -> None:
    """Persist ``manifest`` as deterministic JSON, atomically.

    Under xdist every worker's collection hook computes the identical complete
    owned set and writes this manifest, so the write must be atomic: each writer
    stages a per-process temp file and renames it into place, leaving the final
    file always complete and identical regardless of concurrent writers.
    """

    payload = json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n"
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def read_manifest(path: Path) -> ShardManifest:
    """Load a shard manifest, failing closed on malformed data."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ShardManifestError(f"could not read shard manifest {path}: {exc}") from exc
    return ShardManifest.from_dict(data)


def _owned_ids(manifest: ShardManifest, count: int, source_sha: str | None, seen: set[str]) -> set[str]:
    """Validate one manifest against the partition invariants and return its ids."""

    if manifest.algorithm_version != SHARD_ALGORITHM_VERSION:
        raise ShardManifestError(
            f"shard {manifest.shard_index} used algorithm {manifest.algorithm_version!r}, "
            f"expected {SHARD_ALGORITHM_VERSION!r}"
        )
    if manifest.shard_count != count:
        raise ShardManifestError(
            f"shard {manifest.shard_index} recorded shard_count {manifest.shard_count}, expected {count}"
        )
    if source_sha is not None and manifest.source_sha != source_sha:
        raise ShardManifestError(
            f"shard {manifest.shard_index} recorded source {manifest.source_sha!r}, expected {source_sha!r}"
        )
    ids = set(manifest.node_ids)
    if len(ids) != len(manifest.node_ids):
        raise ShardManifestError(f"shard {manifest.shard_index} recorded duplicate node ids")
    overlap = seen & ids
    if overlap:
        raise ShardManifestError(f"shard {manifest.shard_index} overlaps earlier shards on {len(overlap)} node ids")
    misowned = [nodeid for nodeid in ids if shard_for_nodeid(nodeid, count) != manifest.shard_index]
    if misowned:
        raise ShardManifestError(f"shard {manifest.shard_index} claims {len(misowned)} node ids it does not own")
    return ids


def verify_shard_partition(
    manifests: Sequence[ShardManifest],
    canonical_nodeids: Sequence[str],
    *,
    shard_count: int,
    source_sha: str | None = None,
) -> None:
    """Prove ``manifests`` form a complete, disjoint partition of the canonical suite.

    Raises :class:`ShardManifestError` unless every index in ``range(shard_count)``
    is present exactly once, every manifest agrees on the algorithm version, shard
    count, and (when given) the source SHA, no node id appears in two shards, each
    node id is owned by the shard that recorded it, and the union of the shards is
    exactly the freshly collected canonical suite.
    """

    count = validate_shard_count(shard_count)

    canonical = list(canonical_nodeids)
    canonical_set = set(canonical)
    if len(canonical_set) != len(canonical):
        raise ShardManifestError("canonical collection contains duplicate node ids")
    if not canonical_set:
        raise ShardManifestError("canonical collection is empty")

    indices = sorted(manifest.shard_index for manifest in manifests)
    if indices != list(range(count)):
        raise ShardManifestError(f"shard indices {indices} are not exactly the complete set 0..{count - 1}")

    seen: set[str] = set()
    for manifest in manifests:
        seen |= _owned_ids(manifest, count, source_sha, seen)

    if seen != canonical_set:
        missing = sorted(canonical_set - seen)
        extra = sorted(seen - canonical_set)
        raise ShardManifestError(
            f"shard union does not equal the canonical suite: {len(missing)} missing, {len(extra)} unexpected"
        )
