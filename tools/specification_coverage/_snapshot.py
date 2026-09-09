"""Execution-snapshot validation for the specification-coverage bundle."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.policy.common import PolicyFailure, safe_repo_path
from tools.research_evidence import source_state_failures
from tools.specification_coverage._artifacts import (
    _validate_artifacts,
    _validate_implementation_surfaces,
)
from tools.specification_coverage._baseline import validate_current_deviations
from tools.specification_coverage._keys import (
    _BACKEND_OCCURRENCE_KEYS,
    _CONCEPT_RESULT_KEYS,
    _EXECUTION_SNAPSHOT_PATH,
    _HISTORICAL_REVISION_FIELD,
    _SNAPSHOT_KEYS,
    _STAGE_RESULT_KEYS,
    EXPECTED_CLASSIFICATIONS,
    PROTOCOL_PATH,
)
from tools.specification_coverage._primitives import (
    _bounded_list,
    _exact_keys,
    _failure,
    _json_pointer_get,
    _record_ids,
    _sha256,
)

_TYPED_CLASSIFICATIONS = {"directly-expressible", "profile-or-manifest-constraint"}


@dataclass(frozen=True)
class _SnapshotContext:
    """Shared read-only state threaded through the per-result validators."""

    repo_root: Path
    executed: dict[str, dict[str, object]]
    valid_outcomes: set[object] = field(default_factory=set)
    valid_strengths: set[object] = field(default_factory=set)
    replay_current: bool = True


def _snapshot_join_failures(
    repo_root: Path,
    protocol: dict[str, object],
    snapshot: dict[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    if snapshot.get("protocol_revision") != protocol.get("revision"):
        failures.append(
            _failure(
                "specification-coverage-snapshot-join",
                "snapshot protocol revision is stale",
                path,
            )
        )
    protocol_path = safe_repo_path(repo_root, PROTOCOL_PATH)
    if protocol_path is None or snapshot.get("protocol_sha256") != _sha256(protocol_path):
        failures.append(
            _failure(
                "specification-coverage-snapshot-join",
                "snapshot protocol digest is stale",
                path,
            )
        )
    if snapshot.get("execution_status") != "complete":
        failures.append(
            _failure(
                "specification-coverage-snapshot-status",
                "execution snapshot must be complete",
                path,
            )
        )
    revision = snapshot.get("raes_revision" if "source_state" in snapshot else _HISTORICAL_REVISION_FIELD)
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        failures.append(
            _failure(
                "specification-coverage-snapshot-shape",
                "historical revision is invalid",
                path,
            )
        )


def _result_classification_failures(
    result: dict[str, object],
    concept: dict[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    concept_id = result.get("concept_id")
    classification = result.get("classification")
    if classification not in EXPECTED_CLASSIFICATIONS:
        failures.append(
            _failure(
                "specification-coverage-classifications",
                "result classification is invalid",
                path,
            )
        )
    if classification != concept.get("expected_classification"):
        failures.append(
            _failure(
                "specification-coverage-classification-boundary",
                f"{concept_id!r} observed classification differs from the preregistered boundary",
                path,
            )
        )
    pointer = result.get("typed_pointer")
    if classification in _TYPED_CLASSIFICATIONS and (not isinstance(pointer, str) or not pointer.startswith("/")):
        failures.append(
            _failure(
                "specification-coverage-typed-evidence",
                f"{concept_id!r} claims typed coverage without a typed pointer",
                path,
            )
        )
    if classification == "missing" and pointer is not None:
        failures.append(
            _failure(
                "specification-coverage-typed-evidence",
                "missing concept has a typed pointer",
                path,
            )
        )


def _stage_entry_failures(
    context: _SnapshotContext,
    stage: dict[str, object],
    concept: dict[str, object],
    classification: object,
    concept_id: object,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    stage_id = stage.get("stage_id")
    outcome = stage.get("outcome")
    _stage_outcome_failures(context, stage, concept_id, failures, path)
    _stage_classification_failures(stage_id, outcome, classification, concept, concept_id, failures, path)


def _stage_outcome_failures(
    context: _SnapshotContext,
    stage: dict[str, object],
    concept_id: object,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    stage_id = stage.get("stage_id")
    outcome = stage.get("outcome")
    if outcome not in context.valid_outcomes:
        failures.append(
            _failure(
                "specification-coverage-stage-coverage",
                "stage outcome is invalid",
                path,
            )
        )
    if stage.get("validation_strength") not in context.valid_strengths:
        failures.append(
            _failure(
                "specification-coverage-stage-coverage",
                "validation strength is invalid",
                path,
            )
        )
    artifact_path = stage.get("artifact_path")
    if not isinstance(artifact_path, str) or artifact_path not in context.executed:
        failures.append(
            _failure(
                "specification-coverage-artifact-path",
                f"stage result for {concept_id!r} references an unknown artifact",
                path,
            )
        )
    if outcome == "passed" and context.replay_current:
        payload = context.executed.get(artifact_path, {}).get(stage_id)
        exists, _ = _json_pointer_get(payload, stage.get("pointer"))
        if payload is None or not exists:
            failures.append(
                _failure(
                    "specification-coverage-typed-evidence",
                    f"{concept_id!r} stage {stage_id!r} does not resolve its declared pointer",
                    artifact_path if isinstance(artifact_path, str) else path,
                )
            )


def _stage_classification_failures(
    stage_id: object,
    outcome: object,
    classification: object,
    concept: dict[str, object],
    concept_id: object,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    if classification in _TYPED_CLASSIFICATIONS and outcome != "passed":
        failures.append(
            _failure(
                "specification-coverage-stage-coverage",
                f"typed concept {concept_id!r} has non-passing stage {stage_id!r}",
                path,
            )
        )
    if classification == "missing" and outcome not in {
        "unsupported",
        "not_run",
    }:
        failures.append(
            _failure(
                "specification-coverage-stage-coverage",
                "missing concept outcome is dishonest",
                path,
            )
        )
    if concept.get("load_bearing") is True and outcome != "passed":
        failures.append(
            _failure(
                "specification-coverage-load-bearing-stages",
                f"load-bearing concept {concept_id!r} has non-passing stage {stage_id!r}",
                path,
            )
        )


def _stage_results_failures(
    context: _SnapshotContext,
    result: dict[str, object],
    concept: dict[str, object],
    result_index: int,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    concept_id = result.get("concept_id")
    classification = result.get("classification")
    stages = _bounded_list(
        result.get("stage_results"),
        failures,
        rule_id="specification-coverage-stage-coverage",
        label=f"concept_results[{result_index}].stage_results",
        path=path,
    )
    stage_ids: list[object] = []
    for stage_index, stage in enumerate(stages):
        if not _exact_keys(
            stage,
            _STAGE_RESULT_KEYS,
            failures,
            rule_id="specification-coverage-stage-coverage",
            label=f"concept_results[{result_index}].stage_results[{stage_index}]",
            path=path,
        ):
            continue
        stage_ids.append(stage.get("stage_id"))
        _stage_entry_failures(context, stage, concept, classification, concept_id, failures, path)
    expected_stages = concept.get("artifact_stage_ids")
    if (
        not isinstance(expected_stages, list)
        or len(stage_ids) != len(set(stage_ids))
        or set(stage_ids) != set(expected_stages)
    ):
        failures.append(
            _failure(
                "specification-coverage-stage-coverage",
                f"{concept_id!r} does not have rectangular preregistered stage coverage",
                path,
            )
        )


def _occurrence_failures(
    context: _SnapshotContext,
    result: dict[str, object],
    result_index: int,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    concept_id = result.get("concept_id")
    classification = result.get("classification")
    occurrences = _bounded_list(
        result.get("backend_vocabulary_occurrences"),
        failures,
        rule_id="specification-coverage-backend-leakage",
        label=f"concept_results[{result_index}].backend_vocabulary_occurrences",
        path=path,
    )
    for occurrence_index, occurrence in enumerate(occurrences):
        if _exact_keys(
            occurrence,
            _BACKEND_OCCURRENCE_KEYS,
            failures,
            rule_id="specification-coverage-backend-leakage",
            label=f"backend occurrence {occurrence_index}",
            path=path,
        ):
            _occurrence_entry_failures(context, occurrence, classification, concept_id, failures, path)


def _occurrence_entry_failures(
    context: _SnapshotContext,
    occurrence: dict[str, object],
    classification: object,
    concept_id: object,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    if occurrence.get("allowed") is not True or classification == "directly-expressible":
        failures.append(
            _failure(
                "specification-coverage-backend-leakage",
                f"{concept_id!r} contains unallowed backend vocabulary",
                path,
            )
        )
    occurrence_path = occurrence.get("artifact_path")
    if isinstance(occurrence_path, str) and not occurrence_path.startswith("source:"):
        resolved = safe_repo_path(context.repo_root, occurrence_path)
        if resolved is None:
            failures.append(
                _failure(
                    "specification-coverage-artifact-path",
                    "backend occurrence path is unsafe",
                    path,
                )
            )


def _validate_snapshot(
    repo_root: Path,
    protocol: dict[str, object],
    snapshot: dict[str, object],
    catalogs: dict[str, object],
    failures: list[PolicyFailure],
    *,
    replay_current: bool = True,
) -> None:
    path = _EXECUTION_SNAPSHOT_PATH
    if not _exact_keys(
        snapshot,
        (_SNAPSHOT_KEYS - {_HISTORICAL_REVISION_FIELD}) | {"raes_revision", "source_state", "baseline"}
        if replay_current
        else _SNAPSHOT_KEYS,
        failures,
        rule_id="specification-coverage-snapshot-shape",
        label="snapshot",
        path=path,
    ):
        return
    _snapshot_join_failures(repo_root, protocol, snapshot, failures, path)
    if replay_current:
        failures.extend(validate_current_deviations(repo_root, snapshot))
        failures.extend(source_state_failures(repo_root, snapshot.get("source_state"), path, current=True))
        state = snapshot.get("source_state")
        if not isinstance(state, dict) or state.get("base_revision") != snapshot.get("raes_revision"):
            failures.append(_failure("research-evidence-source-state", "base revision must join source identity", path))
    _validate_implementation_surfaces(repo_root, snapshot, failures, replay_current=replay_current)

    artifacts_by_id, executed = _validate_artifacts(repo_root, snapshot, failures, replay_current=replay_current)
    carrier_artifacts = {
        item.get("artifact_id")
        for item in protocol.get("carriers", [])
        if isinstance(item, dict) and item.get("artifact_id") is not None
    }
    if not carrier_artifacts.issubset(artifacts_by_id):
        failures.append(
            _failure(
                "specification-coverage-carriers",
                "carrier artifact is absent from snapshot",
                path,
            )
        )

    _concept_results_failures(
        repo_root, protocol, snapshot, catalogs, executed, failures, path, replay_current=replay_current
    )


def _concept_results_failures(
    repo_root: Path,
    protocol: dict[str, object],
    snapshot: dict[str, object],
    catalogs: dict[str, object],
    executed: dict[str, dict[str, object]],
    failures: list[PolicyFailure],
    path: str,
    *,
    replay_current: bool = True,
) -> None:
    results = _bounded_list(
        snapshot.get("concept_results"),
        failures,
        rule_id="specification-coverage-concept-results",
        label="concept_results",
        path=path,
    )
    result_ids = _record_ids(
        results,
        "concept_id",
        failures,
        rule_id="specification-coverage-concept-results",
        label="concept_results",
        path=path,
    )
    if result_ids != catalogs.get("concept_ids", set()):
        failures.append(
            _failure(
                "specification-coverage-concept-results",
                "concept results must join every protocol concept exactly once",
                path,
            )
        )
    concepts = catalogs.get("concepts", {})
    rules = protocol.get("execution_rules") if isinstance(protocol.get("execution_rules"), dict) else {}
    context = _SnapshotContext(
        repo_root=repo_root,
        executed=executed,
        valid_outcomes=set(rules.get("stage_outcomes", [])),
        valid_strengths=set(rules.get("validation_strength_values", [])),
        replay_current=replay_current,
    )
    for index, result in enumerate(results):
        if not _exact_keys(
            result,
            _CONCEPT_RESULT_KEYS,
            failures,
            rule_id="specification-coverage-concept-results",
            label=f"concept_results[{index}]",
            path=path,
        ):
            continue
        concept = concepts.get(result.get("concept_id")) if isinstance(concepts, dict) else None
        if not isinstance(concept, dict):
            continue
        _result_classification_failures(result, concept, failures, path)
        _stage_results_failures(context, result, concept, index, failures, path)
        _occurrence_failures(context, result, index, failures, path)
