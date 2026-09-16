"""Content-backed evidence validation for archival experiment runs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, BinaryIO

from ..evidence_proof import ValidatedRunEvidence, _mint_validated_run_evidence
from .experiment_apparatus import ExperimentTaskModel
from .experiment_capture import ExperimentCaptureSpecModel
from .experiment_evidence import ExperimentEvidenceRecordModel
from .experiment_evidence_refinement import validate_evidence_requirement_relations_against_artifacts
from .experiment_run import ExperimentRunModel, validate_experiment_run_structure_against_task


@dataclass(frozen=True)
class ExperimentRunEvidenceInputs:
    """Immutable-reader inputs needed to prove one run's evidence claims."""

    capture_specs: Mapping[str, ExperimentCaptureSpecModel]
    evidence_records: Mapping[str, ExperimentEvidenceRecordModel]
    artifact_readers: Mapping[str, BinaryIO]
    scenarios: Mapping[str, Any] = field(default_factory=dict)


def _task_claims_required_evidence(task: ExperimentTaskModel) -> bool:
    return bool(task.evaluation_protocol.observation_requirements) or any(
        metric.evidence_requirements for metric in task.evaluation_protocol.metric_definitions.values()
    )


def validate_experiment_run_against_task(
    task: ExperimentTaskModel,
    run: ExperimentRunModel,
    *,
    evidence: ExperimentRunEvidenceInputs | None = None,
) -> ValidatedRunEvidence:
    """Validate a task/run pair, including content-backed evidence when claimed."""

    validate_experiment_run_structure_against_task(task, run)
    relations = (*task.evidence_requirement_relations, *run.evidence_requirement_relations)
    if relations:
        if evidence is None:
            raise ValueError("task/run evidence relation validation requires resolved evidence inputs")
        validate_evidence_requirement_relations_against_artifacts(
            relations,
            scenarios=evidence.scenarios,
            capture_specs=evidence.capture_specs,
        )
    if not _task_claims_required_evidence(task) and evidence is None:
        return _mint_validated_run_evidence(task, run, ())
    if evidence is None:
        raise ValueError("task/run validation requires content-backed evidence inputs")
    from ..evidence_satisfaction import validate_experiment_run_evidence

    return validate_experiment_run_evidence(
        task,
        run,
        capture_specs=evidence.capture_specs,
        evidence_records=evidence.evidence_records,
        artifact_readers=evidence.artifact_readers,
    )


__all__ = ["ExperimentRunEvidenceInputs", "validate_experiment_run_against_task"]
