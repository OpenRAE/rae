"""Selection and loading of the historical satisfiability supplement."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from raes_contracts.errors import InvalidInputError

from tools.evidence_bundle_index import revision_key
from tools.formal_semantic_validation._loading import load_release_bundles
from tools.formal_semantic_validation._shape import _hashable, _members, _nonempty_string
from tools.formal_semantic_validation._types import (
    _HISTORICAL_BUNDLE_ID,
    _MAX_FILE_BYTES,
    MANIFEST_PATH,
    REPO_ROOT,
    _JsonObject,
)
from tools.policy.common import load_bounded_json_object, safe_repo_path


def load_bundle(repo_root: Path = REPO_ROOT) -> tuple[_JsonObject, _JsonObject, _JsonObject, _JsonObject, _JsonObject]:
    manifest = _assembled_manifest(repo_root)
    paths: list[str] = []
    for key in ("protocol_path", "corpus_path", "snapshot_path", "analysis_path"):
        value = manifest.get(key)
        if not _nonempty_string(value) or safe_repo_path(repo_root, str(value)) is None:
            raise InvalidInputError(f"manifest {key} must be a safe repository path")
        paths.append(str(value))
    protocol, corpus, snapshot, analysis = (
        load_bounded_json_object(repo_root, path, max_bytes=_MAX_FILE_BYTES) for path in paths
    )
    return manifest, protocol, corpus, snapshot, analysis


def load_satisfiability_analysis(
    repo_root: Path = REPO_ROOT,
) -> tuple[_JsonObject, _JsonObject, _JsonObject]:
    """Load the revisioned issue-826 supplement selected by the bundle."""

    manifest = _assembled_manifest(repo_root)
    values = [
        manifest.get("satisfiability_snapshot_path"),
        manifest.get("satisfiability_analysis_path"),
    ]
    for key, value in zip(
        ("satisfiability_snapshot_path", "satisfiability_analysis_path"),
        values,
        strict=True,
    ):
        path = safe_repo_path(repo_root, str(value)) if _nonempty_string(value) else None
        if path is None:
            raise InvalidInputError(f"manifest {key} must be a safe repository path")
    snapshot, analysis = (
        load_bounded_json_object(repo_root, str(value), max_bytes=_MAX_FILE_BYTES) for value in values
    )
    return manifest, snapshot, analysis


def _assembled_manifest(repo_root: Path) -> dict[str, object]:
    releases = load_release_bundles(repo_root)
    historical = [
        item
        for item in releases
        if item.protocol.get("revision") == "1.0.0"
        and any(
            isinstance(artifact, Mapping) and artifact.get("kind") == "satisfiability-analysis"
            for artifact in _members(item.manifest.get("artifacts", []))
        )
    ]
    if not historical:
        raise InvalidInputError(f"{MANIFEST_PATH!r} must select an atomic historical satisfiability release")
    release = max(historical, key=lambda item: revision_key(item.manifest.get("revision")))
    artifact_by_kind = {
        artifact.get("kind"): artifact
        for artifact in _members(release.manifest.get("artifacts", []))
        if isinstance(artifact, Mapping) and _hashable(artifact.get("kind"))
    }
    supplement_snapshot = artifact_by_kind.get("satisfiability-snapshot")
    supplement_analysis = artifact_by_kind["satisfiability-analysis"]
    if (
        not isinstance(supplement_snapshot, Mapping)
        or "path" not in supplement_snapshot
        or "path" not in supplement_analysis
    ):
        raise InvalidInputError(f"{MANIFEST_PATH!r} must select an atomic historical satisfiability release")
    return {
        "bundle_id": _HISTORICAL_BUNDLE_ID,
        "revision": release.manifest["revision"],
        "protocol_path": release.manifest["protocol_path"],
        "corpus_path": release.manifest["corpus_path"],
        "snapshot_path": release.manifest["snapshot_path"],
        "analysis_path": release.manifest["analysis_path"],
        "satisfiability_snapshot_path": supplement_snapshot["path"],
        "satisfiability_analysis_path": supplement_analysis["path"],
    }
