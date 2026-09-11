"""Exact baseline and source-deviation joins for the versioned current capture."""

from pathlib import Path

from tools.policy.common import PolicyFailure, load_bounded_json_object, safe_repo_path
from tools.specification_coverage._keys import _MAX_FILE_BYTES
from tools.specification_coverage._primitives import _failure, _sha256

_BASELINE_PATH = (
    "docs/research/specification-coverage/bundles/" + "a" + "ces-standardized-specification-coverage-9347f64-v1.json"
)


def _baseline_snapshot(repo_root: Path, baseline: object) -> dict[str, object]:
    if not isinstance(baseline, dict) or set(baseline) != {"release_sha256", "release_revision"}:
        raise ValueError("current coverage capture requires an exact baseline")
    if baseline["release_revision"] != "1.1.0":
        raise ValueError("current coverage capture must retain baseline 1.1.0")
    path = safe_repo_path(repo_root, _BASELINE_PATH)
    if path is None or _sha256(path) != baseline["release_sha256"]:
        raise ValueError("stale baseline release pin")
    manifest = load_bounded_json_object(repo_root, _BASELINE_PATH, max_bytes=_MAX_FILE_BYTES)
    snapshot_path = manifest.get("snapshot_path")
    path = safe_repo_path(repo_root, snapshot_path) if isinstance(snapshot_path, str) else None
    if path is None or _sha256(path) != manifest.get("snapshot_sha256"):
        raise ValueError("stale baseline snapshot pin")
    return load_bounded_json_object(repo_root, snapshot_path, max_bytes=_MAX_FILE_BYTES)


def validate_current_deviations(repo_root: Path, snapshot: dict[str, object]) -> list[PolicyFailure]:
    """Retain every artifact and require an exact disposition for each changed pin."""
    path = "docs/research/specification-coverage/execution-snapshot-v3.json"
    try:
        baseline = _baseline_snapshot(repo_root, snapshot.get("baseline"))
        old = {item["path"]: item for item in baseline["artifacts"]}
        new = {item["path"]: item for item in snapshot["artifacts"]}
        changed = _changed_artifacts(old, new)
        deviations = snapshot.get("deviations")
        if not isinstance(deviations, list) or len(deviations) != len(changed):
            raise ValueError("deviations must exactly cover changed source pins")
        seen = set()
        for item in deviations:
            artifact = _deviation_artifact(item, old, new, changed)
            if artifact in seen:
                raise ValueError("duplicate source deviation")
            seen.add(artifact)
    except (OSError, ValueError, KeyError, TypeError):
        return [
            _failure(
                "specification-coverage-baseline-drift",
                "current source deviations do not join the exact historical baseline",
                path,
            )
        ]
    return []


def _deviation_artifact(
    item: object,
    old: dict[str, dict[str, object]],
    new: dict[str, dict[str, object]],
    changed: set[str],
) -> str:
    if not isinstance(item, dict) or set(item) != {"artifact_path", "baseline_sha256", "retest_sha256", "rationale"}:
        raise ValueError("invalid source deviation shape")
    artifact = item["artifact_path"]
    if (
        not isinstance(artifact, str)
        or artifact not in changed
        or item["baseline_sha256"] != old[artifact]["sha256"]
        or item["retest_sha256"] != new[artifact]["sha256"]
        or not isinstance(item["rationale"], str)
        or not item["rationale"].strip()
    ):
        raise ValueError("stale or ambiguous source deviation")
    return artifact


def _changed_artifacts(old: dict[str, dict[str, object]], new: dict[str, dict[str, object]]) -> set[str]:
    if old.keys() != new.keys() or any(old[p]["kind"] != new[p]["kind"] for p in old):
        raise ValueError("current capture must retain the preregistered artifacts")
    return {p for p in old if old[p]["sha256"] != new[p]["sha256"]}
