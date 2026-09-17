"""Analysis recomputation and claim-honesty validation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from copy import deepcopy

from tools.policy.common import PolicyFailure
from tools.specification_coverage._keys import (
    _ANALYSIS_KEYS,
    _CLAIM_KEYS,
    _REQUEST_RESULT_KEYS,
    EXPECTED_CLASSIFICATIONS,
)
from tools.specification_coverage._primitives import (
    _exact_keys,
    _failure,
    _json_sha256,
)

_FAILING_STAGE_OUTCOMES = {"failed", "not_run", "tool_failed"}


def _records_by_concept_id(records: Sequence[object]) -> dict[str, dict[str, object]]:
    return {
        item["concept_id"]: item
        for item in records
        if isinstance(item, dict) and isinstance(item.get("concept_id"), str)
    }


def _classification_counts(snapshot: dict[str, object]) -> dict[str, int]:
    counts = Counter(
        item.get("classification") for item in snapshot.get("concept_results", []) if isinstance(item, dict)
    )
    return {
        classification: counts[classification]
        for classification in (
            "directly-expressible",
            "profile-or-manifest-constraint",
            "deliberately-backend-specific",
            "missing",
        )
    }


def _has_non_passing_stage(observed: dict[str, object]) -> bool:
    return any(
        stage.get("outcome") != "passed" for stage in observed.get("stage_results", []) if isinstance(stage, dict)
    )


def _load_bearing_summary(
    concept_by_id: dict[str, dict[str, object]],
    result_by_id: dict[str, dict[str, object]],
) -> dict[str, int]:
    load_bearing = [item for item in concept_by_id.values() if item.get("load_bearing") is True]
    missing = 0
    failed = 0
    passed = 0
    for concept in load_bearing:
        observed = result_by_id.get(concept["concept_id"], {})
        if observed.get("classification") == "missing":
            missing += 1
        elif observed.get("classification") != concept.get("expected_classification") or _has_non_passing_stage(
            observed
        ):
            failed += 1
        else:
            passed += 1
    return {
        "total": len(load_bearing),
        "passed": passed,
        "failed": failed,
        "missing": missing,
    }


def _load_bearing_result_bad(
    item: dict[str, object],
    concept_by_id: dict[str, dict[str, object]],
) -> bool:
    concept = concept_by_id.get(item.get("concept_id"), {})
    if concept.get("load_bearing") is not True:
        return False
    return (
        item.get("classification") == "missing"
        or item.get("classification") != concept.get("expected_classification")
        or _has_non_passing_stage(item)
    )


def _request_result_entry(
    request: dict[str, object],
    concept_by_id: dict[str, dict[str, object]],
    result_by_id: dict[str, dict[str, object]],
) -> tuple[dict[str, object], bool]:
    observed = [result_by_id.get(concept_id, {}) for concept_id in request.get("concept_ids", [])]
    missing_count = sum(item.get("classification") == "missing" for item in observed)
    failed_stage_count = sum(
        stage.get("outcome") in _FAILING_STAGE_OUTCOMES
        for item in observed
        for stage in item.get("stage_results", [])
        if isinstance(stage, dict)
    )
    critical_bad = any(_load_bearing_result_bad(item, concept_by_id) for item in observed)
    if critical_bad:
        status = "refuted"
    elif missing_count or failed_stage_count:
        status = "partial"
    else:
        status = "demonstrated"
    entry = {
        "request_id": request.get("request_id"),
        "status": status,
        "concept_count": len(observed),
        "missing_count": missing_count,
        "failed_stage_count": failed_stage_count,
    }
    return entry, bool(missing_count or failed_stage_count)


def _backend_leakage(snapshot: dict[str, object]) -> list[dict[str, object]]:
    leakage: list[dict[str, object]] = []
    for concept_result in snapshot.get("concept_results", []):
        if not isinstance(concept_result, dict):
            continue
        for occurrence in concept_result.get("backend_vocabulary_occurrences", []):
            if isinstance(occurrence, dict) and occurrence.get("allowed") is not True:
                leakage.append({"concept_id": concept_result.get("concept_id"), **occurrence})
    return leakage


def recompute_analysis(
    protocol: dict[str, object],
    snapshot: dict[str, object],
    analysis: dict[str, object],
) -> dict[str, object]:
    """Return the analysis with every outcome-bearing field recomputed."""

    result = deepcopy(analysis)
    result["snapshot_sha256"] = _json_sha256(snapshot)
    concept_by_id = _records_by_concept_id(protocol.get("concepts", []))
    result_by_id = _records_by_concept_id(snapshot.get("concept_results", []))
    result["classification_counts"] = _classification_counts(snapshot)
    load_summary = _load_bearing_summary(concept_by_id, result_by_id)
    result["load_bearing_results"] = load_summary

    request_results: list[dict[str, object]] = []
    any_noncritical_failure = False
    for request in protocol.get("requests", []):
        if not isinstance(request, dict):
            continue
        entry, noncritical_failure = _request_result_entry(request, concept_by_id, result_by_id)
        any_noncritical_failure = any_noncritical_failure or noncritical_failure
        request_results.append(entry)
    result["request_results"] = request_results

    leakage = _backend_leakage(snapshot)
    result["backend_leakage"] = leakage

    if load_summary["missing"] or load_summary["failed"] or leakage:
        evidence_status = "refuted"
    elif any_noncritical_failure:
        evidence_status = "partial"
    else:
        evidence_status = "demonstrated"
    result["execution_status"] = snapshot.get("execution_status")
    result["evidence_status"] = evidence_status
    return result


def _analysis_shape_failures(analysis: dict[str, object], failures: list[PolicyFailure], path: str) -> None:
    counts = analysis.get("classification_counts")
    if not isinstance(counts, dict) or set(counts) != EXPECTED_CLASSIFICATIONS:
        failures.append(
            _failure(
                "specification-coverage-analysis-shape",
                "classification_counts is invalid",
                path,
            )
        )
    load_results = analysis.get("load_bearing_results")
    if not isinstance(load_results, dict) or set(load_results) != {
        "total",
        "passed",
        "failed",
        "missing",
    }:
        failures.append(
            _failure(
                "specification-coverage-analysis-shape",
                "load_bearing_results is invalid",
                path,
            )
        )
    request_results = analysis.get("request_results")
    if not isinstance(request_results, list):
        failures.append(
            _failure(
                "specification-coverage-analysis-shape",
                "request_results must be a list",
                path,
            )
        )
    else:
        for index, request_result in enumerate(request_results):
            _exact_keys(
                request_result,
                _REQUEST_RESULT_KEYS,
                failures,
                rule_id="specification-coverage-analysis-shape",
                label=f"request_results[{index}]",
                path=path,
            )
    _exact_keys(
        analysis.get("claim"),
        _CLAIM_KEYS,
        failures,
        rule_id="specification-coverage-analysis-shape",
        label="claim",
        path=path,
    )


def _validate_analysis(
    protocol: dict[str, object],
    snapshot: dict[str, object],
    analysis: dict[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    if not _exact_keys(
        analysis,
        _ANALYSIS_KEYS,
        failures,
        rule_id="specification-coverage-analysis-shape",
        label="analysis",
        path=path,
    ):
        return
    if analysis.get("protocol_revision") != protocol.get("revision") or analysis.get("snapshot_id") != snapshot.get(
        "snapshot_id"
    ):
        failures.append(_failure("specification-coverage-analysis-join", "analysis joins are stale", path))
    if analysis.get("snapshot_sha256") != _json_sha256(snapshot):
        failures.append(
            _failure(
                "specification-coverage-analysis-join",
                "analysis is not bound to the complete execution snapshot",
                path,
            )
        )
    _analysis_shape_failures(analysis, failures, path)
    if analysis != recompute_analysis(protocol, snapshot, analysis):
        failures.append(
            _failure(
                "specification-coverage-analysis-stale",
                "analysis outcome fields do not match the protocol-derived snapshot result",
                path,
            )
        )
