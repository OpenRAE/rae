"""Analysis validation and evidence-status honesty for the DSL evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from raes_contracts.errors import InvalidInputError

from tools.dsl_language_evaluation._keys import (
    _ANALYSIS_KEYS,
    _CLAIM_KEYS,
    _DIMENSION_RESULT_KEYS,
    _MAX_CATALOG_ITEMS,
    _MEASURE_RESULT_KEYS,
    _STRATUM_RESULT_KEYS,
    EVIDENCE_STATUSES,
)
from tools.dsl_language_evaluation._measures import (
    recompute_dimension_results,
    recompute_measure_results,
    recompute_stratum_results,
)
from tools.dsl_language_evaluation._shape import (
    _bounded_list,
    _exact_keys,
    _failure,
    _record_ids,
    _string_list,
)
from tools.policy.common import PolicyFailure, safe_repo_path


@dataclass(frozen=True)
class _AnalysisContext:
    """Frozen upstream artifacts and joins the analysis is validated against."""

    repo_root: Path
    protocol: Mapping[str, object]
    snapshot: Mapping[str, object]
    scope: Mapping[str, set[str]]
    strata: Sequence[Mapping[str, object]]
    observation_ids: set[str]


def _analysis_header_failures(
    protocol: Mapping[str, object],
    snapshot: Mapping[str, object],
    analysis: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    if analysis["protocol_revision"] != protocol.get("revision"):
        failures.append(_failure("dsl-evaluation-analysis-join", "protocol revision mismatch", path))
    if analysis["snapshot_id"] != snapshot.get("snapshot_id"):
        failures.append(_failure("dsl-evaluation-analysis-join", "snapshot id mismatch", path))
    if analysis["execution_status"] != snapshot.get("execution_status"):
        failures.append(_failure("dsl-evaluation-analysis-join", "execution status mismatch", path))
    if analysis["evidence_status"] not in EVIDENCE_STATUSES:
        failures.append(_failure("dsl-evaluation-evidence-status", "invalid evidence status", path))


def _measure_result_failures(
    protocol: Mapping[str, object],
    snapshot: Mapping[str, object],
    analysis: Mapping[str, object],
    scope: Mapping[str, set[str]],
    failures: list[PolicyFailure],
    path: str,
) -> dict[str, dict[str, object]]:
    measure_results = _bounded_list(
        analysis["measure_results"],
        _MAX_CATALOG_ITEMS,
        failures,
        rule_id="dsl-evaluation-analysis-shape",
        label="measure_results",
        path=path,
    )
    measure_result_ids = _record_ids(
        measure_results,
        "measure_id",
        failures,
        rule_id="dsl-evaluation-analysis-id",
        label="measure result",
        path=path,
    )
    if measure_result_ids != scope.get("measure_ids", set()):
        failures.append(
            _failure(
                "dsl-evaluation-analysis-measure-coverage",
                "analysis must contain one result for every claim-scoped measure",
                path,
            )
        )
    try:
        recomputed_measures = recompute_measure_results(protocol, snapshot, scope=scope)
    except InvalidInputError as exc:
        failures.append(_failure("dsl-evaluation-observation-value", str(exc), path))
        recomputed_measures = {}
    for index, result in enumerate(measure_results):
        if not _exact_keys(
            result,
            _MEASURE_RESULT_KEYS,
            failures,
            rule_id="dsl-evaluation-analysis-shape",
            label=f"measure_results[{index}]",
            path=path,
        ):
            continue
        expected = recomputed_measures.get(result["measure_id"])
        if expected and expected["denominator"] == 0:
            expected_status = "not_evaluated"
        elif expected and expected["observed_count"] != expected["denominator"]:
            expected_status = "incomplete"
        else:
            expected_status = "evaluated"
        if expected is None or result != {
            "measure_id": result["measure_id"],
            "status": expected_status,
            **expected,
        }:
            failures.append(
                _failure(
                    "dsl-evaluation-analysis-measure-drift",
                    f"{result['measure_id']}: stored aggregate does not match frozen observations",
                    path,
                )
            )
    return recomputed_measures


def _dimension_result_failures(
    context: _AnalysisContext,
    analysis: Mapping[str, object],
    recomputed_measures: dict[str, dict[str, object]],
    failures: list[PolicyFailure],
    path: str,
) -> list[object]:
    try:
        recomputed_dimensions = recompute_dimension_results(
            context.protocol,
            recomputed_measures,
            dimension_ids=context.scope.get("dimension_ids", set()),
        )
    except InvalidInputError as exc:
        failures.append(_failure("dsl-evaluation-threshold-evaluation", str(exc), path))
        recomputed_dimensions = {}

    results = _bounded_list(
        analysis["dimension_results"],
        _MAX_CATALOG_ITEMS,
        failures,
        rule_id="dsl-evaluation-analysis-shape",
        label="dimension_results",
        path=path,
    )
    result_ids = _record_ids(
        results,
        "dimension_id",
        failures,
        rule_id="dsl-evaluation-analysis-id",
        label="dimension result",
        path=path,
    )
    if result_ids != context.scope.get("dimension_ids", set()):
        failures.append(
            _failure(
                "dsl-evaluation-analysis-dimension-coverage",
                "analysis must contain one result for every claim-scoped dimension",
                path,
            )
        )
    for index, result in enumerate(results):
        if not _exact_keys(
            result,
            _DIMENSION_RESULT_KEYS,
            failures,
            rule_id="dsl-evaluation-analysis-shape",
            label=f"dimension_results[{index}]",
            path=path,
        ):
            continue
        refs = _string_list(result["supporting_observation_ids"])
        if refs is None or not set(refs).issubset(context.observation_ids):
            failures.append(
                _failure(
                    "dsl-evaluation-analysis-observation-join",
                    f"{result['dimension_id']}: unknown supporting observations",
                    path,
                )
            )
        expected_dimension = recomputed_dimensions.get(result["dimension_id"])
        if expected_dimension is None or result != {
            "dimension_id": result["dimension_id"],
            **expected_dimension,
        }:
            failures.append(
                _failure(
                    "dsl-evaluation-analysis-dimension-drift",
                    f"{result['dimension_id']}: stored threshold result does not match recomputed measures",
                    path,
                )
            )
    return results


def _recomputed_stratum_failures(
    context: _AnalysisContext,
    stored_strata: list[object],
    failures: list[PolicyFailure],
    path: str,
) -> list[dict[str, object]]:
    expected_strata: list[dict[str, object]] = []
    try:
        expected_strata = recompute_stratum_results(context.protocol, context.snapshot, context.strata)
    except InvalidInputError as exc:
        failures.append(_failure("dsl-evaluation-stratum-drift", str(exc), path))
    expected_by_id = {item["stratum_id"]: item for item in expected_strata}
    stored_ids = _record_ids(
        stored_strata,
        "stratum_id",
        failures,
        rule_id="dsl-evaluation-analysis-id",
        label="stratum result",
        path=path,
    )
    if stored_ids != set(expected_by_id):
        failures.append(
            _failure(
                "dsl-evaluation-stratum-coverage",
                "analysis must persist one independently recomputed result for every bound stratum",
                path,
            )
        )
    for index, result in enumerate(stored_strata):
        if not _exact_keys(
            result,
            _STRATUM_RESULT_KEYS,
            failures,
            rule_id="dsl-evaluation-analysis-shape",
            label=f"stratum_results[{index}]",
            path=path,
        ):
            continue
        assert isinstance(result, dict)
        if result != expected_by_id.get(result["stratum_id"]):
            failures.append(
                _failure(
                    "dsl-evaluation-stratum-drift",
                    f"{result['stratum_id']}: stored stratum result does not match frozen observations",
                    path,
                )
            )
    return expected_strata


def _stratum_result_failures(
    context: _AnalysisContext,
    analysis: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> list[dict[str, object]]:
    stored_strata = _bounded_list(
        analysis["stratum_results"],
        _MAX_CATALOG_ITEMS,
        failures,
        rule_id="dsl-evaluation-analysis-shape",
        label="stratum_results",
        path=path,
    )
    if context.snapshot.get("execution_status") == "not_started":
        if stored_strata:
            failures.append(
                _failure(
                    "dsl-evaluation-stratum-drift",
                    "not-started analysis cannot persist derived stratum results",
                    path,
                )
            )
        return []
    return _recomputed_stratum_failures(context, stored_strata, failures, path)


def _claim_evidence_failures(
    repo_root: Path,
    analysis: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    claim = analysis["claim"]
    if not _exact_keys(
        claim,
        _CLAIM_KEYS,
        failures,
        rule_id="dsl-evaluation-analysis-shape",
        label="claim",
        path=path,
    ):
        return
    evidence_artifacts = claim["evidence_artifacts"]
    if not isinstance(evidence_artifacts, list) or len(evidence_artifacts) != 3:
        failures.append(
            _failure(
                "dsl-evaluation-claim-evidence",
                "claim must name protocol, snapshot, and analysis artifacts",
                path,
            )
        )
        return
    for artifact in evidence_artifacts:
        resolved = safe_repo_path(repo_root, artifact) if isinstance(artifact, str) else None
        if resolved is None or not resolved.is_file():
            failures.append(
                _failure(
                    "dsl-evaluation-claim-evidence-path",
                    f"unsafe or missing claim evidence artifact {artifact!r}",
                    path,
                )
            )


def _not_started_analysis_failures(
    status: object,
    results: list[object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    if status != "untested":
        failures.append(
            _failure(
                "dsl-evaluation-evidence-status",
                "not-started execution must remain untested",
                path,
            )
        )
    for result in results:
        if not isinstance(result, Mapping):
            continue
        expected = {
            "status": "not_evaluated",
            "threshold_result": "not_evaluated",
            "condition_results": [],
            "supporting_observation_ids": [],
        }
        if any(result.get(field) != value for field, value in expected.items()):
            failures.append(
                _failure(
                    "dsl-evaluation-not-started-analysis",
                    f"{result.get('dimension_id')}: not-started result contains derived evidence",
                    path,
                )
            )


def _dimension_outcome(result: object, threshold_result: str) -> bool:
    return (
        isinstance(result, Mapping)
        and result.get("status") == "evaluated"
        and result.get("threshold_result") == threshold_result
    )


def _all_gating_pass(gating_strata: list[dict[str, object]], gating_dimensions: list[object]) -> bool:
    return (
        bool(gating_strata)
        and len(gating_dimensions) == len(gating_strata)
        and all(
            dimension_results and all(_dimension_outcome(result, "pass") for result in dimension_results)
            for dimension_results in gating_dimensions
        )
    )


def _any_record_matches(snapshot: Mapping[str, object], field_name: str, field: str, value: str) -> bool:
    return any(isinstance(item, Mapping) and item.get(field) == value for item in snapshot.get(field_name, []))


def _gating_dimension_lists(
    expected_strata: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[object]]:
    gating_strata = [item for item in expected_strata if item.get("role") == "gating"]
    gating_dimensions = [
        item.get("dimension_results", []) for item in gating_strata if isinstance(item.get("dimension_results"), list)
    ]
    return gating_strata, gating_dimensions


def _gating_qualification(
    snapshot: Mapping[str, object],
    expected_strata: list[dict[str, object]],
) -> tuple[bool, bool]:
    gating_strata, gating_dimensions = _gating_dimension_lists(expected_strata)
    all_pass = _all_gating_pass(gating_strata, gating_dimensions)
    any_fail = any(
        _dimension_outcome(result, "fail") for dimension_results in gating_dimensions for result in dimension_results
    )
    unresolved = _any_record_matches(snapshot, "disagreements", "status", "unresolved")
    invalidating_deviation = _any_record_matches(snapshot, "deviations", "severity", "invalidating")
    execution_complete = snapshot.get("execution_status") == "complete"
    qualifies_demonstrated = execution_complete and all_pass and not unresolved and not invalidating_deviation
    qualifies_refuted = execution_complete and any_fail
    return qualifies_demonstrated, qualifies_refuted


def _evidence_status_failures(
    snapshot: Mapping[str, object],
    status: object,
    expected_strata: list[dict[str, object]],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    qualifies_demonstrated, qualifies_refuted = _gating_qualification(snapshot, expected_strata)
    execution_records_present = any(
        isinstance(snapshot.get(field), list) and bool(snapshot[field])
        for field in ("subjects", "attempts", "observations", "reviews", "deviations", "withdrawals")
    )
    if status == "demonstrated" and not qualifies_demonstrated:
        failures.append(
            _failure(
                "dsl-evaluation-evidence-status",
                "demonstrated requires every bound gating stratum to pass "
                "without unresolved critical disagreement or invalidating deviation",
                path,
            )
        )
    elif status == "refuted" and not qualifies_refuted:
        failures.append(
            _failure(
                "dsl-evaluation-evidence-status",
                "refuted requires a complete execution with at least one gating-stratum dimension failure",
                path,
            )
        )
    elif status == "partial" and (
        snapshot.get("execution_status") == "not_started"
        or not execution_records_present
        or qualifies_demonstrated
        or qualifies_refuted
    ):
        failures.append(
            _failure(
                "dsl-evaluation-evidence-status",
                "partial requires relevant execution evidence that is not yet a demonstrated or refuted result",
                path,
            )
        )
    elif status == "untested" and snapshot.get("execution_status") != "not_started":
        failures.append(
            _failure(
                "dsl-evaluation-evidence-status",
                "untested is reserved for a not-started execution without evidence records",
                path,
            )
        )


def _validate_analysis(
    context: _AnalysisContext,
    analysis: dict[str, object],
    failures: list[PolicyFailure],
    *,
    path: str = "docs/research/dsl-language-evaluation/analysis-v1.json",
) -> None:
    if not _exact_keys(
        analysis,
        _ANALYSIS_KEYS,
        failures,
        rule_id="dsl-evaluation-analysis-shape",
        label="analysis",
        path=path,
    ):
        return
    _analysis_header_failures(context.protocol, context.snapshot, analysis, failures, path)
    recomputed_measures = _measure_result_failures(
        context.protocol, context.snapshot, analysis, context.scope, failures, path
    )
    results = _dimension_result_failures(context, analysis, recomputed_measures, failures, path)
    expected_strata = _stratum_result_failures(context, analysis, failures, path)
    _claim_evidence_failures(context.repo_root, analysis, failures, path)
    status = analysis["evidence_status"]
    if context.snapshot.get("execution_status") == "not_started":
        _not_started_analysis_failures(status, results, failures, path)
    _evidence_status_failures(context.snapshot, status, expected_strata, failures, path)
