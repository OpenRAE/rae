"""Analysis validation for the formal-semantic evidence bundle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools.formal_semantic_validation._claims import recompute_claim_results
from tools.formal_semantic_validation._shape import (
    _closed_object,
    _failure,
    _hashable,
    _is_sequence,
    _lookup,
    _member,
    _members,
    _nonempty_string,
    _string_list,
)
from tools.formal_semantic_validation._types import (
    _ANALYSIS_KEYS,
    _CLAIM_KEYS,
    _CLAIM_RESULT_KEYS,
    _JsonObject,
)
from tools.policy.common import PolicyFailure, safe_repo_path


@dataclass(frozen=True)
class _AnalysisContext:
    repo_root: Path
    path: str
    snapshot_path: str | None = None


def _validate_analysis(
    context: _AnalysisContext,
    protocol: _JsonObject,
    corpus: _JsonObject,
    snapshot: _JsonObject,
    analysis: _JsonObject,
    failures: list[PolicyFailure],
) -> None:
    repo_root, path, snapshot_path = context.repo_root, context.path, context.snapshot_path
    if not _closed_object(
        analysis,
        _ANALYSIS_KEYS,
        rule_id="formal-validation-analysis-shape",
        label="analysis",
        failures=failures,
        path=path,
    ):
        return
    if (
        analysis.get("protocol_revision") != protocol.get("revision")
        or analysis.get("corpus_revision") != corpus.get("revision")
        or analysis.get("execution_id") != snapshot.get("execution_id")
    ):
        failures.append(
            _failure(
                "formal-validation-analysis-join",
                "analysis must bind the selected protocol, corpus, and execution",
                path,
            )
        )
    recomputed = recompute_claim_results(protocol, corpus, snapshot)
    expected_by_id = {item["claim_class_id"]: item for item in recomputed if _hashable(item["claim_class_id"])}
    _claim_results_failures(analysis, expected_by_id, failures, path)
    _overall_status_failures(recomputed, analysis, failures, path)
    _claim_record_failures(repo_root, analysis, failures, path, snapshot_path=snapshot_path)


def _claim_results_failures(
    analysis: _JsonObject,
    expected_by_id: dict[object, dict[str, object]],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    results = analysis.get("claim_results")
    if not _is_sequence(results):
        failures.append(
            _failure(
                "formal-validation-analysis-results",
                "claim_results must be a list",
                path,
            )
        )
        results = []
    result_ids: list[object] = []
    for item in results:
        if not _closed_object(
            item,
            _CLAIM_RESULT_KEYS,
            rule_id="formal-validation-claim-result-shape",
            label="claim result",
            failures=failures,
            path=path,
        ):
            continue
        result_ids.append(item.get("claim_class_id"))
        _claim_result_failures(item, expected_by_id, failures, path)
    if (
        not all(_hashable(item) for item in result_ids)
        or set(result_ids) != set(expected_by_id)
        or len(result_ids) != len(set(result_ids))
    ):
        failures.append(
            _failure(
                "formal-validation-analysis-result-coverage",
                "analysis must contain exactly one result per claim class",
                path,
            )
        )


def _claim_result_failures(
    item: dict[str, object],
    expected_by_id: dict[object, dict[str, object]],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    claim_class_id = item.get("claim_class_id")
    expected = _lookup(expected_by_id, claim_class_id)
    if expected is None:
        failures.append(
            _failure(
                "formal-validation-analysis-result-join",
                f"unknown claim result {claim_class_id!r}",
                path,
            )
        )
        return
    for key in (
        "evidence_status",
        "case_count",
        "matching_case_count",
        "replayable_case_count",
        "unsupported_case_count",
        "participant_obligation_count",
    ):
        if item.get(key) != expected[key]:
            failures.append(
                _failure(
                    "formal-validation-analysis-drift",
                    f"claim result {claim_class_id!r} field {key} does not match frozen observations",
                    path,
                )
            )
            break
    if _member(expected["evidence_status"], {"untested", "refuted"}) and _member(
        item.get("evidence_status"), {"partial", "demonstrated"}
    ):
        failures.append(
            _failure(
                "formal-validation-unsupported-overclaim",
                f"unproven or refuted class {claim_class_id!r} cannot be promoted",
                path,
            )
        )
    if not _string_list(item.get("limitations")):
        failures.append(
            _failure(
                "formal-validation-claim-limitations",
                f"claim result {claim_class_id!r} needs limitations",
                path,
            )
        )


def _overall_status_failures(
    recomputed: list[dict[str, object]],
    analysis: _JsonObject,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    statuses = {item["evidence_status"] for item in recomputed if _hashable(item["evidence_status"])}
    if "refuted" in statuses:
        overall = "refuted"
    elif statuses & {"partial", "demonstrated"}:
        overall = "partial"
    else:
        overall = "untested"
    if analysis.get("evidence_status") != overall:
        failures.append(
            _failure(
                "formal-validation-analysis-drift",
                "overall evidence status does not match claim results",
                path,
            )
        )


def _claim_record_failures(
    repo_root: Path,
    analysis: _JsonObject,
    failures: list[PolicyFailure],
    path: str,
    *,
    snapshot_path: str | None = None,
) -> None:
    if not _closed_object(
        analysis.get("claim"),
        _CLAIM_KEYS,
        rule_id="formal-validation-claim-record",
        label="claim",
        failures=failures,
        path=path,
    ):
        return
    claim = analysis["claim"]
    for key in (
        "threats_to_validity",
        "allowed_evidence",
        "disallowed_evidence",
        "evidence_artifacts",
    ):
        if not _string_list(claim.get(key)):
            failures.append(
                _failure(
                    "formal-validation-claim-record",
                    f"claim needs non-empty {key}",
                    path,
                )
            )
    for artifact in _members(claim.get("evidence_artifacts", [])):
        if not _claim_artifact_exists(repo_root, artifact, snapshot_path):
            failures.append(
                _failure(
                    "formal-validation-claim-artifact",
                    f"claim references missing or unsafe artifact {artifact!r}",
                    path,
                )
            )
    if not _string_list(analysis.get("limitations")) or not _nonempty_string(analysis.get("plain_language_outcome")):
        failures.append(
            _failure(
                "formal-validation-analysis-disclosure",
                "analysis needs a plain-language outcome and limitations",
                path,
            )
        )


def _claim_artifact_exists(repo_root: Path, artifact: object, snapshot_path: str | None) -> bool:
    selected = snapshot_path if artifact == "@snapshot" else artifact
    resolved = safe_repo_path(repo_root, selected) if isinstance(selected, str) else None
    return resolved is not None and resolved.is_file()
