"""Atomic release validation dispatch (v1 legacy and v2 integrated retest)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from tools.evidence_bundle_index import revision_key
from tools.formal_semantic_validation._analysis import _validate_analysis
from tools.formal_semantic_validation._baseline import _validate_baseline_drift
from tools.formal_semantic_validation._bundle import validate_bundle
from tools.formal_semantic_validation._corpus import _validate_corpus
from tools.formal_semantic_validation._protocol import _validate_protocol
from tools.formal_semantic_validation._retest import (
    _RetestScope,
    _validate_retest_snapshot,
)
from tools.formal_semantic_validation._satisfiability import (
    validate_satisfiability_analysis,
)
from tools.formal_semantic_validation._shape import (
    _closed_object,
    _failure,
    _is_sequence,
    _sha256_file,
    _stable_ids,
)
from tools.formal_semantic_validation._types import (
    _MAX_FILE_BYTES,
    _RELEASE_ARTIFACT_PIN_KEYS,
    _RELEASE_MANIFEST_KEYS,
    _RETAINED_CASE_TEXT_REPLACEMENTS,
    _SHA256_RE,
    EvidenceRelease,
)
from tools.policy.common import PolicyFailure, load_bounded_json_object, safe_repo_path
from tools.research_evidence import source_state_failures


def _stale_pin(repo_root: Path, path_value: object, digest_value: object) -> bool:
    resolved = safe_repo_path(repo_root, path_value) if isinstance(path_value, str) else None
    return (
        resolved is None
        or not resolved.is_file()
        or not isinstance(digest_value, str)
        or not _SHA256_RE.fullmatch(digest_value)
        or _sha256_file(resolved) != digest_value
    )


def _release_document_pin_failures(
    repo_root: Path,
    manifest: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    for label in ("protocol", "corpus", "snapshot", "analysis"):
        if _stale_pin(repo_root, manifest.get(f"{label}_path"), manifest.get(f"{label}_sha256")):
            failures.append(
                _failure(
                    "formal-validation-release-digest",
                    f"release {label} path or SHA-256 pin is stale",
                    path,
                )
            )


def _pinned_release_artifacts(
    repo_root: Path,
    manifest: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> list[object]:
    artifacts = manifest.get("artifacts")
    if not _is_sequence(artifacts):
        failures.append(
            _failure(
                "formal-validation-release-artifacts",
                "release artifacts must be a bounded list",
                path,
            )
        )
        artifacts = []
    _, unique_artifact_ids = _stable_ids(artifacts, "artifact_id")
    artifact_paths: list[str] = []
    for artifact in artifacts:
        if not _closed_object(
            artifact,
            _RELEASE_ARTIFACT_PIN_KEYS,
            rule_id="formal-validation-release-artifact-shape",
            label="release artifact",
            failures=failures,
            path=path,
        ):
            continue
        artifact_path = artifact.get("path")
        if isinstance(artifact_path, str):
            artifact_paths.append(artifact_path)
        if _stale_pin(repo_root, artifact_path, artifact.get("sha256")):
            failures.append(
                _failure(
                    "formal-validation-release-digest",
                    f"release artifact {artifact.get('artifact_id')!r} path or SHA-256 pin is stale",
                    path,
                )
            )
    if not unique_artifact_ids or len(artifact_paths) != len(set(artifact_paths)):
        failures.append(
            _failure(
                "formal-validation-release-artifacts",
                "release artifact ids and paths must be unique",
                path,
            )
        )
    return list(artifacts)


def validate_release_bundle(repo_root: Path, release: EvidenceRelease) -> list[PolicyFailure]:
    """Validate one atomic release record, all digest pins, and its evidence."""

    failures: list[PolicyFailure] = []
    manifest = release.manifest
    path = release.manifest_path
    if not _closed_object(
        manifest,
        _RELEASE_MANIFEST_KEYS,
        rule_id="formal-validation-release-shape",
        label="release manifest",
        failures=failures,
        path=path,
    ):
        return failures
    try:
        revision_key(manifest.get("revision"))
    except ValueError:
        failures.append(
            _failure(
                "formal-validation-release-revision",
                "release revision must be semantic",
                path,
            )
        )

    _release_document_pin_failures(repo_root, manifest, failures, path)
    artifacts = _pinned_release_artifacts(repo_root, manifest, failures, path)

    if release.protocol.get("revision") == "2.0.0":
        failures.extend(
            validate_retest_bundle(
                repo_root,
                release,
                release.protocol,
                release.corpus,
                release.snapshot,
                release.analysis,
                replay_current=manifest.get("revision") == "9.0.0",
            )
        )
    else:
        legacy_manifest = {
            "bundle_id": manifest.get("bundle_id"),
            "revision": manifest.get("revision"),
            "protocol_path": manifest.get("protocol_path"),
            "corpus_path": manifest.get("corpus_path"),
            "snapshot_path": manifest.get("snapshot_path"),
            "analysis_path": manifest.get("analysis_path"),
            "satisfiability_snapshot_path": None,
            "satisfiability_analysis_path": None,
        }
        failures.extend(
            validate_bundle(
                repo_root,
                legacy_manifest,
                release.protocol,
                release.corpus,
                release.snapshot,
                release.analysis,
                replay_cases=False,
            )
        )
        artifact_by_kind = {item.get("kind"): item for item in artifacts if isinstance(item, Mapping)}
        sat_snapshot_pin = artifact_by_kind.get("satisfiability-snapshot")
        sat_analysis_pin = artifact_by_kind.get("satisfiability-analysis")
        if sat_snapshot_pin is not None or sat_analysis_pin is not None:
            if sat_snapshot_pin is None or sat_analysis_pin is None:
                failures.append(
                    _failure(
                        "formal-validation-release-artifacts",
                        "historical satisfiability evidence must be selected atomically",
                        path,
                    )
                )
            else:
                legacy_manifest["revision"] = "2.0.0"
                legacy_manifest["satisfiability_snapshot_path"] = sat_snapshot_pin.get("path")
                legacy_manifest["satisfiability_analysis_path"] = sat_analysis_pin.get("path")
                snapshot = load_bounded_json_object(
                    repo_root,
                    str(sat_snapshot_pin.get("path")),
                    max_bytes=_MAX_FILE_BYTES,
                )
                analysis = load_bounded_json_object(
                    repo_root,
                    str(sat_analysis_pin.get("path")),
                    max_bytes=_MAX_FILE_BYTES,
                )
                failures.extend(
                    validate_satisfiability_analysis(
                        repo_root,
                        legacy_manifest,
                        snapshot,
                        analysis,
                        replay_current=False,
                    )
                )
    return failures


def validate_retest_bundle(
    repo_root: Path,
    release: EvidenceRelease,
    protocol: dict[str, object],
    corpus: dict[str, object],
    snapshot: dict[str, object],
    analysis: dict[str, object],
    *,
    replay_current: bool = True,
) -> list[PolicyFailure]:
    """Validate the integrated issue-828 evidence release."""

    failures: list[PolicyFailure] = []
    protocol_path = str(release.manifest.get("protocol_path"))
    corpus_path = str(release.manifest.get("corpus_path"))
    snapshot_path = str(release.manifest.get("snapshot_path"))
    analysis_path = str(release.manifest.get("analysis_path"))
    release_revision = release.manifest.get("revision")
    if not replay_current and release_revision not in {
        "3.0.0",
        "4.0.0",
        "5.0.0",
        "6.0.0",
        "7.0.0",
        "8.0.0",
    }:
        return [
            _failure(
                "formal-validation-current-replay-required",
                "only releases 3.0.0 through 8.0.0 can use integrated historical validation",
                snapshot_path,
            )
        ]
    if release_revision not in {"3.0.0", "4.0.0", "5.0.0", "6.0.0", "7.0.0", "8.0.0", "9.0.0"}:
        failures.append(
            _failure(
                "formal-validation-retest-release",
                "integrated retest requires an explicitly supported release revision",
                release.manifest_path,
            )
        )
    if protocol.get("revision") != "2.0.0" or corpus.get("revision") != "2.0.0":
        failures.append(
            _failure(
                "formal-validation-retest-revision",
                "the integrated retest must bind protocol and corpus revision 2.0.0",
                release.manifest_path,
            )
        )

    if release_revision in {"4.0.0", "5.0.0", "6.0.0", "7.0.0", "8.0.0", "9.0.0"}:
        _current_retest_source_failures(
            repo_root,
            snapshot,
            failures,
            snapshot_path,
            release_revision=str(release_revision),
            replay_current=replay_current,
        )
    _validate_protocol(repo_root, protocol, failures, protocol_path)
    cases_by_id = _validate_corpus(repo_root, protocol, corpus, failures, corpus_path)
    historical_cases = _retained_historical_cases(repo_root, cases_by_id, failures, corpus_path)
    _validate_retest_snapshot(
        _RetestScope(
            repo_root=repo_root,
            release=release,
            protocol=protocol,
            corpus=corpus,
            snapshot=snapshot,
            cases_by_id=cases_by_id,
            replay_current=replay_current,
        ),
        failures,
        snapshot_path,
    )
    baseline_cases = (
        cases_by_id if release_revision in {"4.0.0", "5.0.0", "6.0.0", "7.0.0", "8.0.0", "9.0.0"} else historical_cases
    )
    _validate_baseline_drift(repo_root, snapshot, baseline_cases, failures, snapshot_path)
    _validate_analysis(repo_root, protocol, corpus, snapshot, analysis, failures, analysis_path)
    return failures


def _current_retest_source_failures(
    repo_root: Path,
    snapshot: dict[str, object],
    failures: list[PolicyFailure],
    path: str,
    *,
    release_revision: str,
    replay_current: bool,
) -> None:
    failures.extend(source_state_failures(repo_root, snapshot.get("source_state"), path, current=replay_current))
    state = snapshot.get("source_state")
    if not isinstance(state, Mapping) or state.get("base_revision") != snapshot.get("raes_revision"):
        failures.append(
            _failure(
                "research-evidence-source-state",
                "base revision must join source identity",
                path,
            )
        )
    baseline = snapshot.get("baseline")
    expected_baseline = {
        "4.0.0": "3.0.0",
        "5.0.0": "4.0.0",
        "6.0.0": "5.0.0",
        "7.0.0": "6.0.0",
        "8.0.0": "7.0.0",
        "9.0.0": "8.0.0",
    }[release_revision]
    if not isinstance(baseline, Mapping) or baseline.get("release_revision") != expected_baseline:
        failures.append(
            _failure(
                "formal-validation-baseline-selection",
                f"release {release_revision} must retain the {expected_baseline} baseline",
                path,
            )
        )


def _retained_historical_cases(
    repo_root: Path,
    cases_by_id: Mapping[str, Mapping[str, object]],
    failures: list[PolicyFailure],
    corpus_path: str,
) -> dict[object, Mapping[str, object]]:
    try:
        historical_corpus = load_bounded_json_object(
            repo_root,
            "docs/research/formal-semantic-validation/corpus/manifest-v1.json",
            max_bytes=_MAX_FILE_BYTES,
        )
    except (OSError, ValueError) as exc:
        failures.append(
            _failure(
                "formal-validation-historical-retention",
                f"could not load the immutable v1 corpus ({type(exc).__name__})",
                corpus_path,
            )
        )
        historical_corpus = {}
    historical_cases = {
        item.get("case_id"): item for item in historical_corpus.get("cases", []) if isinstance(item, Mapping)
    }
    retained_cases_match = all(
        cases_by_id.get(str(case_id))
        == {
            **case,
            "limitation": _RETAINED_CASE_TEXT_REPLACEMENTS.get(
                str(case.get("limitation")),
                case.get("limitation"),
            ),
        }
        for case_id, case in historical_cases.items()
    )
    if not historical_cases or not retained_cases_match:
        failures.append(
            _failure(
                "formal-validation-historical-retention",
                "the v2 corpus must retain every v1 case semantically unchanged, "
                "allowing only the governed identity wording",
                corpus_path,
            )
        )

    return historical_cases
