"""Atomic evidence-release loading."""

from __future__ import annotations

from pathlib import Path

from tools.evidence_bundle_index import load_index_records
from tools.formal_semantic_validation._types import (
    _MAX_FILE_BYTES,
    MANIFEST_PATH,
    MANIFEST_SCHEMA_VERSION,
    REPO_ROOT,
    EvidenceRelease,
)
from tools.policy.common import load_bounded_json_object, safe_repo_path
from tools.research_evidence import (
    current_release_path,
    evidence_key,
    validate_inventory,
)


def load_release_bundles(repo_root: Path = REPO_ROOT) -> list[EvidenceRelease]:
    """Load every atomically indexed evidence release in semantic order."""

    records = load_index_records(
        repo_root,
        index_path=MANIFEST_PATH,
        schema_version=MANIFEST_SCHEMA_VERSION,
        directory_key="bundles_directory",
        max_bytes=_MAX_FILE_BYTES,
    )
    validate_inventory(repo_root, "formal-semantic-validation", records)
    releases: list[EvidenceRelease] = []
    for manifest_path, manifest in records:
        evidence_key(manifest.get("revision"))
        loaded: list[dict[str, object]] = []
        for label in ("protocol", "corpus", "snapshot", "analysis"):
            path_value = manifest.get(f"{label}_path")
            path = (
                safe_repo_path(repo_root, path_value)
                if isinstance(path_value, str)
                else None
            )
            if path is None or not path.is_file():
                raise ValueError(
                    f"{manifest_path!r} contains unsafe or missing {label}_path"
                )
            loaded.append(
                load_bounded_json_object(
                    repo_root, path_value, max_bytes=_MAX_FILE_BYTES
                )
            )
        releases.append(
            EvidenceRelease(
                manifest_path=manifest_path,
                manifest=manifest,
                protocol=loaded[0],
                corpus=loaded[1],
                snapshot=loaded[2],
                analysis=loaded[3],
            )
        )
    return sorted(
        releases,
        key=lambda item: (
            evidence_key(item.manifest.get("revision")),
            item.manifest_path,
        ),
    )


def load_retest_bundle(
    repo_root: Path = REPO_ROOT,
) -> tuple[
    EvidenceRelease,
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    """Load the latest coherent issue-828 retest release."""

    releases = load_release_bundles(repo_root)
    if not releases:
        raise ValueError(
            "the formal semantic-validation index selects no v2 retest release"
        )
    current_path = current_release_path(
        [(item.manifest_path, item.manifest) for item in releases], repo_root
    )
    release = next(item for item in releases if item.manifest_path == current_path)
    if release.protocol.get("revision") != "2.0.0":
        raise ValueError("the current formal capture must bind retest protocol 2.0.0")
    return release, release.protocol, release.corpus, release.snapshot, release.analysis
