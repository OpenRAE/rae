"""Measure opportunity derivation and result recomputation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import median

from raes_contracts.errors import InvalidInputError

from tools.dsl_language_evaluation._claims import _attempt_matches_scope
from tools.dsl_language_evaluation._keys import _STRATUM_ROLES
from tools.dsl_language_evaluation._shape import _protocol_records_by_id, _string_list

_AGGREGATIONS = {"proportion", "median", "count"}
_THRESHOLD_OPERATORS = {
    ">=": lambda actual, target: actual >= target,
    "<=": lambda actual, target: actual <= target,
    "==": lambda actual, target: actual == target,
}


def _measure_stage_ids(
    measure: Mapping[str, object],
    task_id: str,
    variant_id: str,
) -> list[str]:
    """Return the single preregistered stage set for a task/variant/measure."""

    declarations = measure.get("stage_applicability", [])
    if not isinstance(declarations, list):
        raise InvalidInputError(f"{measure.get('measure_id')}: stage applicability must be a list")
    matches: list[list[str]] = []
    for declaration in declarations:
        if not isinstance(declaration, Mapping) or declaration.get("task_id") != task_id:
            continue
        variant_ids = _string_list(declaration.get("variant_ids"), non_empty=True)
        stage_ids = _string_list(declaration.get("artifact_stage_ids"), non_empty=True)
        if variant_ids is not None and variant_id in variant_ids and stage_ids is not None:
            matches.append(stage_ids)
    if len(matches) != 1:
        raise InvalidInputError(
            f"{measure.get('measure_id')}: expected one stage declaration for {task_id}/{variant_id}"
        )
    return matches[0]


def _scoped_measures(
    protocol: Mapping[str, object],
    scope_sets: Mapping[str, set[str]] | None,
) -> dict[str, Mapping[str, object]]:
    measures = _protocol_records_by_id(protocol, "measures", "measure_id")
    if scope_sets is None:
        return measures
    return {
        measure_id: measure
        for measure_id, measure in measures.items()
        if measure_id in scope_sets.get("measure_ids", set())
    }


def _observation_index(observations: list[object]) -> dict[tuple[str, str, str], Mapping[str, object]]:
    index: dict[tuple[str, str, str], Mapping[str, object]] = {}
    for observation in observations:
        if not isinstance(observation, Mapping):
            continue
        attempt_id = observation.get("attempt_id")
        measure_id = observation.get("measure_id")
        artifact_stage = observation.get("artifact_stage")
        if not isinstance(attempt_id, str) or not isinstance(measure_id, str) or not isinstance(artifact_stage, str):
            continue
        key = (attempt_id, measure_id, artifact_stage)
        if key in index:
            raise InvalidInputError(f"duplicate observation opportunity {attempt_id}/{measure_id}/{artifact_stage}")
        index[key] = observation
    return index


def _attempt_in_scope(
    attempt: Mapping[str, object],
    scope_sets: Mapping[str, set[str]] | None,
    subjects_by_id: Mapping[object, Mapping[str, object]],
) -> bool:
    if scope_sets is None:
        return True
    in_scope = _attempt_matches_scope(attempt, scope_sets)
    if in_scope and "experience_band_ids" in scope_sets:
        subject = subjects_by_id.get(attempt.get("subject_id"))
        in_scope = isinstance(subject, Mapping) and subject.get("experience_band") in scope_sets["experience_band_ids"]
    return in_scope


def _attempt_opportunities(
    attempt: Mapping[str, object],
    measures: Mapping[str, Mapping[str, object]],
    scope_sets: Mapping[str, set[str]] | None,
    *,
    withdrawn: bool,
) -> tuple[list[tuple[Mapping[str, object], Mapping[str, object], str, bool]], set[tuple[str, str, str]]]:
    attempt_id = str(attempt.get("attempt_id"))
    task_id = str(attempt.get("task_id"))
    variant_id = str(attempt.get("variant_id"))
    opportunities: list[tuple[Mapping[str, object], Mapping[str, object], str, bool]] = []
    expected_keys: set[tuple[str, str, str]] = set()
    for measure in measures.values():
        task_ids = _string_list(measure.get("task_ids"), non_empty=True)
        if task_ids is None or task_id not in task_ids:
            continue
        measure_id = measure.get("measure_id")
        if not isinstance(measure_id, str):
            continue
        for artifact_stage in _measure_stage_ids(measure, task_id, variant_id):
            if scope_sets is not None and artifact_stage not in scope_sets.get("artifact_stage_ids", set()):
                continue
            opportunities.append((attempt, measure, artifact_stage, withdrawn))
            expected_keys.add((attempt_id, measure_id, artifact_stage))
    return opportunities, expected_keys


def _check_observed_keys(
    observation_by_opportunity: Mapping[tuple[str, str, str], Mapping[str, object]],
    expected_keys: set[tuple[str, str, str]],
    selected_attempt_ids: set[str],
    scope_sets: Mapping[str, set[str]] | None,
) -> None:
    observed_keys = set(observation_by_opportunity)
    if scope_sets is not None:
        observed_keys = {
            key
            for key in observed_keys
            if key[0] in selected_attempt_ids
            and key[1] in scope_sets.get("measure_ids", set())
            and key[2] in scope_sets.get("artifact_stage_ids", set())
        }
    extras = sorted(observed_keys - expected_keys)
    if extras:
        raise InvalidInputError(f"observations without protocol-declared opportunities: {extras[:5]}")


def _subjects_by_id(snapshot: Mapping[str, object]) -> dict[object, Mapping[str, object]]:
    return {
        subject.get("subject_id"): subject
        for subject in snapshot.get("subjects", [])
        if isinstance(subject, Mapping) and isinstance(subject.get("subject_id"), str)
    }


def _withdrawn_subjects(withdrawals: list[object]) -> set[str]:
    return {
        withdrawal["subject_id"]
        for withdrawal in withdrawals
        if isinstance(withdrawal, Mapping) and isinstance(withdrawal.get("subject_id"), str)
    }


def _attempt_withdrawn(attempt: Mapping[str, object], withdrawn_subjects: set[str]) -> bool:
    subject_id = attempt.get("subject_id")
    if isinstance(subject_id, str) and subject_id in withdrawn_subjects:
        return True
    return attempt.get("outcome") == "withdrawn"


def _selected_opportunities(
    attempts: list[object],
    tasks: Mapping[str, Mapping[str, object]],
    measures: Mapping[str, Mapping[str, object]],
    scope_sets: Mapping[str, set[str]] | None,
    subjects_by_id: Mapping[object, Mapping[str, object]],
    withdrawn_subjects: set[str],
) -> tuple[
    list[tuple[Mapping[str, object], Mapping[str, object], str, bool]],
    set[tuple[str, str, str]],
    set[str],
]:
    opportunities: list[tuple[Mapping[str, object], Mapping[str, object], str, bool]] = []
    expected_keys: set[tuple[str, str, str]] = set()
    selected_attempt_ids: set[str] = set()
    for attempt in attempts:
        if not isinstance(attempt, Mapping):
            continue
        attempt_id = attempt.get("attempt_id")
        task_id = attempt.get("task_id")
        if (
            not isinstance(attempt_id, str)
            or not isinstance(task_id, str)
            or not isinstance(attempt.get("variant_id"), str)
        ):
            continue
        if tasks.get(task_id) is None or not _attempt_in_scope(attempt, scope_sets, subjects_by_id):
            continue
        selected_attempt_ids.add(attempt_id)
        withdrawn = _attempt_withdrawn(attempt, withdrawn_subjects)
        attempt_opportunities, attempt_keys = _attempt_opportunities(attempt, measures, scope_sets, withdrawn=withdrawn)
        opportunities.extend(attempt_opportunities)
        expected_keys.update(attempt_keys)
    return opportunities, expected_keys, selected_attempt_ids


def _measure_opportunities(
    protocol: Mapping[str, object],
    snapshot: Mapping[str, object],
    scope: Mapping[str, Sequence[str] | set[str]] | None = None,
) -> tuple[
    dict[str, Mapping[str, object]],
    list[tuple[Mapping[str, object], Mapping[str, object], str, bool]],
    dict[tuple[str, str, str], Mapping[str, object]],
]:
    """Derive every attempt-measure-stage opportunity and frozen observation."""

    tasks = _protocol_records_by_id(protocol, "tasks", "task_id")
    scope_sets = {field: set(values) for field, values in scope.items()} if scope is not None else None
    measures = _scoped_measures(protocol, scope_sets)
    attempts = snapshot.get("attempts", [])
    observations = snapshot.get("observations", [])
    withdrawals = snapshot.get("withdrawals", [])
    subjects_by_id = _subjects_by_id(snapshot)
    if not isinstance(attempts, list) or not isinstance(observations, list) or not isinstance(withdrawals, list):
        raise InvalidInputError("snapshot execution records must be lists")

    withdrawn_subjects = _withdrawn_subjects(withdrawals)
    observation_by_opportunity = _observation_index(observations)
    opportunities, expected_keys, selected_attempt_ids = _selected_opportunities(
        attempts, tasks, measures, scope_sets, subjects_by_id, withdrawn_subjects
    )
    _check_observed_keys(observation_by_opportunity, expected_keys, selected_attempt_ids, scope_sets)
    return measures, opportunities, observation_by_opportunity


def _validated_value(measure_id: str, aggregation: object, value: object) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidInputError(f"{measure_id}: observation values must be numeric or null")
    if aggregation == "proportion" and value not in {0, 1}:
        raise InvalidInputError(f"{measure_id}: proportion observations must be 0 or 1")
    return value


def _observation_tallies(
    measure_id: str,
    aggregation: object,
    eligible: list[tuple[Mapping[str, object], str]],
    observation_by_opportunity: Mapping[tuple[str, str, str], Mapping[str, object]],
) -> tuple[list[int | float], list[str], dict[str, int]]:
    values: list[int | float] = []
    supporting_ids: list[str] = []
    counts = {"missing": 0, "abandoned": 0, "tool_failed": 0}
    for attempt, artifact_stage in eligible:
        attempt_id = attempt.get("attempt_id")
        observation = (
            observation_by_opportunity.get((attempt_id, measure_id, artifact_stage))
            if isinstance(attempt_id, str)
            else None
        )
        if observation is None:
            counts["missing"] += 1
            continue
        observation_id = observation.get("observation_id")
        if not isinstance(observation_id, str):
            raise InvalidInputError(f"{measure_id}: observations require ids")
        supporting_ids.append(observation_id)
        outcome = observation.get("outcome")
        if outcome in counts:
            counts[outcome] += 1
        value = _validated_value(measure_id, aggregation, observation.get("value"))
        if value is not None:
            values.append(value)
    return values, supporting_ids, counts


def _aggregated_value(
    aggregation: object,
    values: list[int | float],
    denominator: int,
) -> tuple[int | float | None, int | float | None]:
    if denominator == 0 or len(values) != denominator:
        return None, None
    if aggregation == "median":
        return None, float(median(values))
    numerator = sum(values)
    return numerator, numerator / denominator if aggregation == "proportion" else numerator


def _measure_result(
    measure_id: str,
    measure: Mapping[str, object],
    opportunities: list[tuple[Mapping[str, object], Mapping[str, object], str, bool]],
    observation_by_opportunity: Mapping[tuple[str, str, str], Mapping[str, object]],
) -> dict[str, object]:
    aggregation = measure.get("aggregation")
    if aggregation not in _AGGREGATIONS:
        raise InvalidInputError(f"invalid measure aggregation for {measure_id!r}")
    matching = [item for item in opportunities if item[1].get("measure_id") == measure_id]
    withdrawn_count = sum(withdrawn for _, _, _, withdrawn in matching)
    eligible = [(attempt, artifact_stage) for attempt, _, artifact_stage, withdrawn in matching if not withdrawn]
    denominator = len(eligible)
    values, supporting_ids, counts = _observation_tallies(measure_id, aggregation, eligible, observation_by_opportunity)
    numerator, value = _aggregated_value(aggregation, values, denominator)
    return {
        "statistic": aggregation,
        "numerator": numerator,
        "denominator": denominator,
        "opportunity_count": len(matching),
        "observed_count": len(values),
        "missing_count": counts["missing"],
        "abandoned_count": counts["abandoned"],
        "tool_failed_count": counts["tool_failed"],
        "withdrawn_count": withdrawn_count,
        "value": value,
        "supporting_observation_ids": supporting_ids,
    }


def recompute_measure_results(
    protocol: Mapping[str, object],
    snapshot: Mapping[str, object],
    *,
    scope: Mapping[str, Sequence[str] | set[str]] | None = None,
) -> dict[str, dict[str, object]]:
    """Recompute measures from the complete protocol-derived opportunity matrix."""

    measures, opportunities, observation_by_opportunity = _measure_opportunities(protocol, snapshot, scope)
    return {
        measure_id: _measure_result(measure_id, measure, opportunities, observation_by_opportunity)
        for measure_id, measure in measures.items()
    }


def _resolved_conditions(
    dimension_id: str,
    conditions: list[object],
    measure_results: Mapping[str, Mapping[str, object]],
) -> list[tuple[Mapping[str, object], Mapping[str, object]]]:
    resolved: list[tuple[Mapping[str, object], Mapping[str, object]]] = []
    for condition in conditions:
        if not isinstance(condition, Mapping):
            raise InvalidInputError(f"{dimension_id}: threshold condition must be an object")
        measure_id = condition.get("measure_id")
        operator = condition.get("operator")
        target = condition.get("target")
        measure = measure_results.get(measure_id) if isinstance(measure_id, str) else None
        if operator not in _THRESHOLD_OPERATORS or isinstance(target, bool) or not isinstance(target, (int, float)):
            raise InvalidInputError(f"{dimension_id}: invalid threshold operator or target")
        if measure is None:
            raise InvalidInputError(f"{dimension_id}: threshold references unknown measure {measure_id!r}")
        resolved.append((condition, measure))
    return resolved


def _condition_outcomes(
    dimension_id: str,
    resolved: list[tuple[Mapping[str, object], Mapping[str, object]]],
) -> tuple[list[dict[str, object]], list[str]]:
    condition_results: list[dict[str, object]] = []
    supporting_ids: list[str] = []
    for condition, measure in resolved:
        actual = measure["value"]
        operator = condition["operator"]
        target = condition["target"]
        if isinstance(actual, bool) or not isinstance(actual, (int, float)):
            raise InvalidInputError(f"{dimension_id}: measure value must be numeric")
        condition_results.append(
            {
                "measure_id": condition["measure_id"],
                "operator": operator,
                "target": target,
                "actual": actual,
                "passed": _THRESHOLD_OPERATORS[operator](actual, target),
            }
        )
        refs = measure.get("supporting_observation_ids", [])
        if not isinstance(refs, list) or not all(isinstance(item, str) for item in refs):
            raise InvalidInputError(f"{dimension_id}: measure observation refs must be text ids")
        for observation_id in refs:
            if observation_id not in supporting_ids:
                supporting_ids.append(observation_id)
    return condition_results, supporting_ids


def _dimension_result(
    dimension_id: str,
    conditions: list[object],
    measure_results: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    resolved = _resolved_conditions(dimension_id, conditions, measure_results)
    if any(measure.get("value") is None for _, measure in resolved):
        return {
            "status": "not_evaluated",
            "threshold_result": "not_evaluated",
            "condition_results": [],
            "supporting_observation_ids": [],
        }
    condition_results, supporting_ids = _condition_outcomes(dimension_id, resolved)
    return {
        "status": "evaluated",
        "threshold_result": "pass" if all(item["passed"] for item in condition_results) else "fail",
        "condition_results": condition_results,
        "supporting_observation_ids": supporting_ids,
    }


def recompute_dimension_results(
    protocol: Mapping[str, object],
    measure_results: Mapping[str, Mapping[str, object]],
    *,
    dimension_ids: Sequence[str] | set[str] | None = None,
) -> dict[str, dict[str, object]]:
    """Apply protocol-declared threshold conditions to recomputed measures."""

    results: dict[str, dict[str, object]] = {}
    selected_dimensions = set(dimension_ids) if dimension_ids is not None else None
    for threshold in protocol.get("thresholds", []):
        if not isinstance(threshold, Mapping):
            continue
        dimension_id = threshold.get("dimension_id")
        conditions = threshold.get("conditions")
        if (
            not isinstance(dimension_id, str)
            or threshold.get("logic") != "all"
            or not isinstance(conditions, list)
            or not conditions
        ):
            raise InvalidInputError(f"invalid threshold for {dimension_id!r}")
        if selected_dimensions is not None and dimension_id not in selected_dimensions:
            continue
        results[dimension_id] = _dimension_result(dimension_id, conditions, measure_results)
    return results


def recompute_stratum_results(
    protocol: Mapping[str, object],
    snapshot: Mapping[str, object],
    strata: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Recompute independently persisted results for every bound claim stratum."""

    results: list[dict[str, object]] = []
    for stratum in strata:
        stratum_id = stratum.get("stratum_id")
        role = stratum.get("role")
        scope = stratum.get("scope")
        if not isinstance(stratum_id, str) or role not in _STRATUM_ROLES or not isinstance(scope, Mapping):
            raise InvalidInputError("invalid resolved claim stratum")
        measures = recompute_measure_results(protocol, snapshot, scope=scope)
        measure_results = [
            {
                "measure_id": measure_id,
                "status": (
                    "not_evaluated"
                    if result["denominator"] == 0
                    else "incomplete"
                    if result["observed_count"] != result["denominator"]
                    else "evaluated"
                ),
                **result,
            }
            for measure_id, result in measures.items()
        ]
        dimensions = recompute_dimension_results(
            protocol,
            measures,
            dimension_ids=scope.get("dimension_ids", set()),
        )
        dimension_results = [{"dimension_id": dimension_id, **result} for dimension_id, result in dimensions.items()]
        results.append(
            {
                "stratum_id": stratum_id,
                "role": role,
                "measure_results": measure_results,
                "dimension_results": dimension_results,
            }
        )
    return results
