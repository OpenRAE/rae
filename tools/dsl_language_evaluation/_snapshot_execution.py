"""Attempt, observation, and opportunity-coverage joins for the snapshot."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from raes_contracts.errors import InvalidInputError

from tools.dsl_language_evaluation._keys import (
    _ATTEMPT_KEYS,
    _OBSERVATION_KEYS,
    ATTEMPT_OUTCOMES,
    OBSERVATION_OUTCOMES,
)
from tools.dsl_language_evaluation._measures import _measure_stage_ids
from tools.dsl_language_evaluation._shape import (
    _bounded_text,
    _failure,
    _string_list,
    _valid_id,
)
from tools.policy.common import PolicyFailure, safe_repo_path


@dataclass(frozen=True)
class _ExecutionJoins:
    attempts_by_id: Mapping[str, Mapping[str, object]]
    attempt_ids: set[str]
    tasks: Mapping[str, Mapping[str, object]]
    measures: Mapping[str, Mapping[str, object]]


def _attempt_parents(
    attempt: Mapping[str, object],
    tasks: Mapping[str, Mapping[str, object]],
    subjects_by_id: Mapping[str, Mapping[str, object]],
) -> tuple[Mapping[str, object] | None, Mapping[str, object] | None]:
    task_id = attempt.get("task_id")
    subject_id = attempt.get("subject_id")
    task = tasks.get(task_id) if isinstance(task_id, str) else None
    subject = subjects_by_id.get(subject_id) if isinstance(subject_id, str) else None
    return task, subject


def _attempt_join_failures(
    attempt: Mapping[str, object],
    attempt_id: str,
    task: Mapping[str, object],
    subject: Mapping[str, object],
    variants: Mapping[str, Mapping[str, object]],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    task_personas = _string_list(task.get("persona_ids"), non_empty=True) or []
    task_conditions = _string_list(task.get("tooling_condition_ids"), non_empty=True) or []
    task_variants = _string_list(task.get("variant_ids"), non_empty=True) or []
    if (
        attempt.get("persona_id") != subject.get("persona_id")
        or attempt.get("persona_id") not in task_personas
        or attempt.get("tooling_condition_id") not in task_conditions
        or attempt.get("variant_id") not in task_variants
    ):
        failures.append(
            _failure(
                "dsl-evaluation-attempt-join",
                f"{attempt_id}: subject, persona, task, condition, or variant mismatch",
                path,
            )
        )
    variant = variants.get(attempt.get("variant_id"))
    if variant is None or variant.get("task_id") != attempt.get("task_id"):
        failures.append(_failure("dsl-evaluation-attempt-join", f"{attempt_id}: variant belongs to another task", path))


def _attempt_identity_failures(
    attempt: Mapping[str, object],
    attempt_id: str,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    if not _valid_id(attempt.get("study_run_id")):
        failures.append(_failure("dsl-evaluation-attempt-identity", f"{attempt_id}: invalid study run id", path))
    if not _bounded_text(attempt.get("started_at"), maximum=100) or not _bounded_text(
        attempt.get("ended_at"), maximum=100
    ):
        failures.append(_failure("dsl-evaluation-attempt-identity", f"{attempt_id}: timestamps must be text", path))
    if _string_list(attempt.get("observation_ids")) is None:
        failures.append(
            _failure("dsl-evaluation-attempt-observation-join", f"{attempt_id}: invalid observation ids", path)
        )


def _attempt_failures(
    attempts: list[object],
    tasks: Mapping[str, Mapping[str, object]],
    variants: Mapping[str, Mapping[str, object]],
    subjects_by_id: Mapping[str, Mapping[str, object]],
    withdrawal_subject_ids: set[str],
    failures: list[PolicyFailure],
    path: str,
) -> dict[str, Mapping[str, object]]:
    attempts_by_id: dict[str, Mapping[str, object]] = {}
    for attempt in attempts:
        if not isinstance(attempt, Mapping) or set(attempt) != _ATTEMPT_KEYS:
            continue
        attempt_id = attempt.get("attempt_id")
        if not isinstance(attempt_id, str):
            continue
        attempts_by_id[attempt_id] = attempt
        task, subject = _attempt_parents(attempt, tasks, subjects_by_id)
        outcome = attempt.get("outcome")
        if outcome not in ATTEMPT_OUTCOMES:
            failures.append(_failure("dsl-evaluation-attempt-outcome", f"{attempt_id}: invalid outcome", path))
        if task is None or subject is None:
            failures.append(_failure("dsl-evaluation-attempt-join", f"{attempt_id}: unknown task or subject", path))
            continue
        _attempt_join_failures(attempt, attempt_id, task, subject, variants, failures, path)
        if (attempt.get("subject_id") in withdrawal_subject_ids) != (outcome == "withdrawn"):
            failures.append(
                _failure(
                    "dsl-evaluation-withdrawal-join",
                    f"{attempt_id}: withdrawn subject and attempt outcome disagree",
                    path,
                )
            )
        _attempt_identity_failures(attempt, attempt_id, failures, path)
    return attempts_by_id


def _observation_identity(
    observation: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> tuple[str, str, str, str] | None:
    observation_id = observation.get("observation_id")
    attempt_id = observation.get("attempt_id")
    measure_id = observation.get("measure_id")
    artifact_stage = observation.get("artifact_stage")
    if (
        not isinstance(observation_id, str)
        or not isinstance(attempt_id, str)
        or not isinstance(measure_id, str)
        or not isinstance(artifact_stage, str)
    ):
        failures.append(
            _failure("dsl-evaluation-observation-identity", "observation identity fields must be text", path)
        )
        return None
    return observation_id, attempt_id, measure_id, artifact_stage


def _observation_parent_failures(
    protocol: Mapping[str, object],
    observation: Mapping[str, object],
    observation_id: str,
    attempt: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    parent_fields = (
        "study_run_id",
        "task_id",
        "persona_id",
        "subject_id",
        "tooling_condition_id",
        "variant_id",
        "outcome",
    )
    if observation.get("protocol_revision") != protocol.get("revision") or any(
        observation.get(field) != attempt.get(field) for field in parent_fields
    ):
        failures.append(
            _failure(
                "dsl-evaluation-observation-parent-join",
                f"{observation_id}: observation does not match its parent attempt",
                path,
            )
        )


def _observation_stage_failures(
    observation: Mapping[str, object],
    observation_id: str,
    attempt: Mapping[str, object],
    task: Mapping[str, object],
    measure: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    observation_dimensions = _string_list(observation.get("dimension_ids"), non_empty=True)
    task_stages = _string_list(task.get("artifact_stage_ids"), non_empty=True) or []
    measure_tasks = _string_list(measure.get("task_ids"), non_empty=True) or []
    task_dimensions = set(_string_list(task.get("dimension_ids"), non_empty=True) or [])
    measure_dimensions = set(_string_list(measure.get("dimension_ids"), non_empty=True) or [])
    expected_dimensions = task_dimensions & measure_dimensions
    parent_task_id = attempt.get("task_id")
    parent_variant_id = attempt.get("variant_id")
    try:
        applicable_stages = (
            _measure_stage_ids(measure, parent_task_id, parent_variant_id)
            if isinstance(parent_task_id, str) and isinstance(parent_variant_id, str)
            else []
        )
    except InvalidInputError:
        applicable_stages = []
    undeclared = any(
        (
            observation.get("artifact_stage") not in task_stages,
            observation.get("artifact_stage") not in applicable_stages,
            observation.get("task_id") not in measure_tasks,
            observation_dimensions is None,
            set(observation_dimensions or []) != expected_dimensions,
        )
    )
    if undeclared:
        failures.append(
            _failure(
                "dsl-evaluation-observation-task-join",
                f"{observation_id}: stage, measure, or dimensions are not declared for the task",
                path,
            )
        )


def _observation_value_failures(
    observation: Mapping[str, object],
    observation_id: str,
    measure_id: str,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    outcome = observation.get("outcome")
    value = observation.get("value")
    if outcome not in OBSERVATION_OUTCOMES:
        failures.append(_failure("dsl-evaluation-observation-outcome", f"{observation_id}: invalid outcome", path))
    if measure_id == "task-completion":
        expected_value = 1 if outcome == "completed" else 0
        valid_value = value == expected_value and not isinstance(value, bool)
    elif outcome in {"completed", "failed"}:
        valid_value = not isinstance(value, bool) and isinstance(value, (int, float))
    else:
        valid_value = value is None
    if not valid_value:
        failures.append(
            _failure(
                "dsl-evaluation-observation-value",
                f"{observation_id}: value does not represent its attempt outcome",
                path,
            )
        )


def _observation_evidence_failures(
    repo_root: Path,
    observation: Mapping[str, object],
    observation_id: str,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    refs = _string_list(observation.get("evidence_refs"))
    if refs is None or any(safe_repo_path(repo_root, ref) is None for ref in refs):
        failures.append(
            _failure(
                "dsl-evaluation-observation-evidence",
                f"{observation_id}: evidence refs must be repository-confined paths",
                path,
            )
        )


def _observation_failures(
    repo_root: Path,
    protocol: Mapping[str, object],
    observations: list[object],
    joins: _ExecutionJoins,
    failures: list[PolicyFailure],
    path: str,
) -> tuple[dict[tuple[str, str, str], Mapping[str, object]], dict[str, set[str]]]:
    observations_by_opportunity: dict[tuple[str, str, str], Mapping[str, object]] = {}
    child_observations: dict[str, set[str]] = {attempt_id: set() for attempt_id in joins.attempt_ids}
    for observation in observations:
        if not isinstance(observation, Mapping) or set(observation) != _OBSERVATION_KEYS:
            continue
        identity = _observation_identity(observation, failures, path)
        if identity is None:
            continue
        observation_id, attempt_id, measure_id, artifact_stage = identity
        opportunity = (attempt_id, measure_id, artifact_stage)
        if opportunity in observations_by_opportunity:
            failures.append(
                _failure(
                    "dsl-evaluation-observation-identity",
                    f"duplicate attempt-measure-stage observation at {observation_id}",
                    path,
                )
            )
        observations_by_opportunity[opportunity] = observation
        child_observations.setdefault(attempt_id, set()).add(observation_id)
        attempt = joins.attempts_by_id.get(attempt_id)
        measure = joins.measures.get(measure_id)
        task = joins.tasks.get(observation.get("task_id"))
        if attempt is None or measure is None or task is None:
            failures.append(
                _failure(
                    "dsl-evaluation-observation-join",
                    f"{observation_id}: unknown parent attempt, task, or measure",
                    path,
                )
            )
            continue
        _observation_parent_failures(protocol, observation, observation_id, attempt, failures, path)
        _observation_stage_failures(observation, observation_id, attempt, task, measure, failures, path)
        _observation_value_failures(observation, observation_id, measure_id, failures, path)
        _observation_evidence_failures(repo_root, observation, observation_id, failures, path)
    return observations_by_opportunity, child_observations


def _opportunity_stages(
    measure: Mapping[str, object],
    task_id: object,
    variant_id: object,
) -> list[str]:
    measure_tasks = _string_list(measure.get("task_ids"), non_empty=True) or []
    if task_id not in measure_tasks or not isinstance(task_id, str) or not isinstance(variant_id, str):
        return []
    try:
        return _measure_stage_ids(measure, task_id, variant_id)
    except InvalidInputError:
        return []


def _expected_opportunities(
    attempts_by_id: Mapping[str, Mapping[str, object]],
    measures: Mapping[str, Mapping[str, object]],
) -> tuple[set[tuple[str, str, str]], set[tuple[str, str, str]]]:
    expected: set[tuple[str, str, str]] = set()
    withdrawn: set[tuple[str, str, str]] = set()
    for attempt_id, attempt in attempts_by_id.items():
        task_id = attempt.get("task_id")
        variant_id = attempt.get("variant_id")
        target = withdrawn if attempt.get("outcome") == "withdrawn" else expected
        for measure_id, measure in measures.items():
            for artifact_stage in _opportunity_stages(measure, task_id, variant_id):
                target.add((attempt_id, measure_id, artifact_stage))
    return expected, withdrawn


def _opportunity_coverage_failures(
    joins: _ExecutionJoins,
    observations_by_opportunity: Mapping[tuple[str, str, str], Mapping[str, object]],
    child_observations: Mapping[str, set[str]],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    expected_opportunities, withdrawn_opportunities = _expected_opportunities(joins.attempts_by_id, joins.measures)
    actual_opportunities = set(observations_by_opportunity)
    if actual_opportunities != expected_opportunities or actual_opportunities & withdrawn_opportunities:
        failures.append(
            _failure(
                "dsl-evaluation-opportunity-coverage",
                "observations must exactly cover every non-withdrawn "
                "protocol-declared attempt-measure-stage opportunity",
                path,
            )
        )
    for attempt_id, attempt in joins.attempts_by_id.items():
        stored_ids = _string_list(attempt.get("observation_ids"))
        if stored_ids is not None and set(stored_ids) != child_observations.get(attempt_id, set()):
            failures.append(
                _failure(
                    "dsl-evaluation-attempt-observation-join",
                    f"{attempt_id}: observation ids do not match child records",
                    path,
                )
            )
