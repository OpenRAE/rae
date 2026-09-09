"""Baseline-drift validation for the integrated retest release."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from tools.evidence_bundle_index import load_index_records
from tools.formal_semantic_validation._shape import (
    _closed_object,
    _failure,
    _is_sequence,
    _nonempty_string,
    _sha256_file,
    _stable_ids,
)
from tools.formal_semantic_validation._types import (
    _BASELINE_KEYS,
    _DEVIATION_KEYS,
    _MAX_FILE_BYTES,
    _SHA256_RE,
    MANIFEST_PATH,
    MANIFEST_SCHEMA_VERSION,
)
from tools.policy.common import PolicyFailure, load_bounded_json_object, safe_repo_path

_DRIFT_COMPARISON_KEYS = ("actual_outcome", "diagnostic_kind", "result_digest")


def _validated_baseline_pin(
    snapshot: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> Mapping[str, object] | None:
    baseline = snapshot.get("baseline")
    if not _closed_object(
        baseline,
        _BASELINE_KEYS,
        rule_id="formal-validation-baseline-selection",
        label="retest baseline",
        failures=failures,
        path=path,
    ):
        return None
    if (
        not isinstance(baseline.get("release_path"), str)
        or not isinstance(baseline.get("release_sha256"), str)
        or not _SHA256_RE.fullmatch(baseline.get("release_sha256"))
        or not _nonempty_string(baseline.get("release_revision"))
        or not _nonempty_string(baseline.get("execution_id"))
    ):
        failures.append(
            _failure(
                "formal-validation-baseline-selection",
                "retest baseline must pin a release path, digest, revision, and execution",
                path,
            )
        )
        return None
    return baseline


def _selected_baseline_manifest(
    repo_root: Path,
    baseline: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> Mapping[str, object] | None:
    baseline_path = baseline.get("release_path")
    try:
        indexed_records = dict(
            load_index_records(
                repo_root,
                index_path=MANIFEST_PATH,
                schema_version=MANIFEST_SCHEMA_VERSION,
                directory_key="bundles_directory",
                max_bytes=_MAX_FILE_BYTES,
            )
        )
    except (OSError, ValueError) as exc:
        failures.append(
            _failure(
                "formal-validation-baseline-selection",
                f"could not load the indexed baseline release ({type(exc).__name__})",
                path,
            )
        )
        return None
    baseline_manifest = indexed_records.get(baseline_path)
    resolved_baseline_path = safe_repo_path(repo_root, baseline_path)
    if (
        not isinstance(baseline_manifest, Mapping)
        or resolved_baseline_path is None
        or not resolved_baseline_path.is_file()
        or _sha256_file(resolved_baseline_path) != baseline.get("release_sha256")
        or baseline_manifest.get("revision") != baseline.get("release_revision")
        or (baseline_manifest.get("protocol_path"), baseline_manifest.get("corpus_path"))
        != (
            "docs/research/formal-semantic-validation/protocol-v2.json"
            if baseline.get("release_revision") == "3.0.0"
            else "docs/research/formal-semantic-validation/protocol-v1.json",
            "docs/research/formal-semantic-validation/corpus/manifest-v2.json"
            if baseline.get("release_revision") == "3.0.0"
            else "docs/research/formal-semantic-validation/corpus/manifest-v1.json",
        )
    ):
        failures.append(
            _failure(
                "formal-validation-baseline-selection",
                "retest baseline must select one indexed historical release with an exact digest and revision",
                path,
            )
        )
        return None
    return baseline_manifest


def _loaded_baseline_snapshot(
    repo_root: Path,
    baseline_manifest: Mapping[str, object],
    baseline: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> Mapping[str, object] | None:
    baseline_snapshot_path = baseline_manifest.get("snapshot_path")
    baseline_snapshot_digest = baseline_manifest.get("snapshot_sha256")
    resolved_snapshot_path = (
        safe_repo_path(repo_root, baseline_snapshot_path) if isinstance(baseline_snapshot_path, str) else None
    )
    if (
        resolved_snapshot_path is None
        or not resolved_snapshot_path.is_file()
        or not isinstance(baseline_snapshot_digest, str)
        or _sha256_file(resolved_snapshot_path) != baseline_snapshot_digest
    ):
        failures.append(
            _failure(
                "formal-validation-baseline-selection",
                "selected baseline release has a stale execution-snapshot pin",
                path,
            )
        )
        return None
    try:
        baseline_snapshot = load_bounded_json_object(
            repo_root,
            str(baseline_snapshot_path),
            max_bytes=_MAX_FILE_BYTES,
        )
    except (OSError, ValueError) as exc:
        failures.append(
            _failure(
                "formal-validation-baseline-selection",
                f"could not load the selected baseline snapshot ({type(exc).__name__})",
                path,
            )
        )
        return None
    if baseline_snapshot.get("execution_id") != baseline.get("execution_id"):
        failures.append(
            _failure(
                "formal-validation-baseline-selection",
                "selected baseline execution id does not match its pinned snapshot",
                path,
            )
        )
    return baseline_snapshot


def _resolved_baseline_snapshot(
    repo_root: Path,
    snapshot: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> Mapping[str, object] | None:
    baseline = _validated_baseline_pin(snapshot, failures, path)
    manifest = _selected_baseline_manifest(repo_root, baseline, failures, path) if baseline is not None else None
    if manifest is None:
        return None
    return _loaded_baseline_snapshot(repo_root, manifest, baseline, failures, path)


def _drift_join(
    baseline_snapshot: Mapping[str, object],
    snapshot: Mapping[str, object],
    historical_cases: Mapping[object, Mapping[str, object]],
    failures: list[PolicyFailure],
    path: str,
) -> tuple[dict[str, Mapping[str, object]], dict[str, Mapping[str, object]], set[str]] | None:
    baseline_observations = baseline_snapshot.get("observations")
    retest_observations = snapshot.get("observations")
    baseline_ids, baseline_unique = _stable_ids(baseline_observations, "case_id")
    retest_ids, retest_unique = _stable_ids(retest_observations, "case_id")
    retained_ids = {str(case_id) for case_id in historical_cases}
    if (
        not _is_sequence(baseline_observations)
        or not _is_sequence(retest_observations)
        or not baseline_unique
        or not retest_unique
        or not retained_ids.issubset(baseline_ids)
        or not retained_ids.issubset(retest_ids)
    ):
        failures.append(
            _failure(
                "formal-validation-baseline-drift",
                "every retained case must join uniquely to baseline and retest observations",
                path,
            )
        )
        return None
    baseline_by_id = {str(item.get("case_id")): item for item in baseline_observations if isinstance(item, Mapping)}
    retest_by_id = {str(item.get("case_id")): item for item in retest_observations if isinstance(item, Mapping)}
    return baseline_by_id, retest_by_id, retained_ids


def _deviation_entry_failures(
    case_id: str,
    baseline_observation: Mapping[str, object],
    retest_observation: Mapping[str, object],
    deviations_by_id: Mapping[str, Mapping[str, object]],
    failures: list[PolicyFailure],
    path: str,
) -> bool:
    """Check one retained case's drift disposition; return whether it changed."""

    changed_fields = [
        key for key in _DRIFT_COMPARISON_KEYS if baseline_observation.get(key) != retest_observation.get(key)
    ]
    if not changed_fields:
        return False
    deviation = deviations_by_id.get(case_id)
    if not _closed_object(
        deviation,
        _DEVIATION_KEYS,
        rule_id="formal-validation-baseline-drift",
        label=f"baseline deviation {case_id!r}",
        failures=failures,
        path=path,
    ):
        return True
    expected_baseline = {key: baseline_observation.get(key) for key in _DRIFT_COMPARISON_KEYS}
    expected_retest = {key: retest_observation.get(key) for key in _DRIFT_COMPARISON_KEYS}
    if (
        deviation.get("changed_fields") != changed_fields
        or deviation.get("baseline") != expected_baseline
        or deviation.get("retest") != expected_retest
        or deviation.get("disposition") != "accepted"
        or not _nonempty_string(deviation.get("category"))
        or not _nonempty_string(deviation.get("rationale"))
    ):
        failures.append(
            _failure(
                "formal-validation-baseline-drift",
                f"retained case {case_id!r} needs an exact accepted drift disposition",
                path,
            )
        )
    return True


def _deviation_failures(
    snapshot: Mapping[str, object],
    retained_ids: set[str],
    baseline_by_id: Mapping[str, Mapping[str, object]],
    retest_by_id: Mapping[str, Mapping[str, object]],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    deviations = snapshot.get("deviations")
    deviation_ids, deviations_unique = _stable_ids(deviations, "case_id")
    if not _is_sequence(deviations) or not deviations_unique:
        failures.append(
            _failure(
                "formal-validation-baseline-drift",
                "baseline deviations must be a unique bounded list",
                path,
            )
        )
        deviations = []
    deviations_by_id = {str(item.get("case_id")): item for item in deviations if isinstance(item, Mapping)}
    expected_deviation_ids: set[str] = set()
    for case_id in sorted(retained_ids):
        if _deviation_entry_failures(
            case_id,
            baseline_by_id[case_id],
            retest_by_id[case_id],
            deviations_by_id,
            failures,
            path,
        ):
            expected_deviation_ids.add(case_id)
    if deviation_ids != expected_deviation_ids:
        failures.append(
            _failure(
                "formal-validation-baseline-drift",
                "deviations must cover exactly the retained cases whose governed observations changed",
                path,
            )
        )


def _validate_baseline_drift(
    repo_root: Path,
    snapshot: Mapping[str, object],
    historical_cases: Mapping[object, Mapping[str, object]],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    """Join retained retest observations to one immutable baseline release."""

    baseline_snapshot = _resolved_baseline_snapshot(repo_root, snapshot, failures, path)
    if baseline_snapshot is None:
        return
    join = _drift_join(baseline_snapshot, snapshot, historical_cases, failures, path)
    if join is None:
        return
    baseline_by_id, retest_by_id, retained_ids = join
    _deviation_failures(snapshot, retained_ids, baseline_by_id, retest_by_id, failures, path)
