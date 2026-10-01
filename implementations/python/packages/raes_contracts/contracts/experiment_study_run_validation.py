"""Task/run evidence validation used by experiment-study analysis."""

from __future__ import annotations

from collections.abc import Mapping

from ..evidence_proof import ValidatedRunEvidence
from .experiment_apparatus import ExperimentTaskModel
from .experiment_run import ExperimentRunModel, validate_experiment_run_structure_against_task
from .experiment_run_evidence_validation import (
    ExperimentRunEvidenceInputs,
    validate_experiment_run_against_task,
)


def validate_study_run_task_membership(
    matched_tasks: list[ExperimentTaskModel],
    matched_runs: list[ExperimentRunModel],
    evidence_by_run: Mapping[str, ExperimentRunEvidenceInputs] | None,
    *,
    structural_only: bool,
) -> dict[tuple[str, str | None], ValidatedRunEvidence]:
    """Validate task membership and preserve the content proof for each run."""

    task_by_key = {(task.task_id, task.task_version): task for task in matched_tasks}
    validated_evidence: dict[tuple[str, str | None], ValidatedRunEvidence] = {}
    for run in matched_runs:
        task = task_by_key.get((run.task_ref.ref_id, run.task_ref.ref_version))
        if task is None:
            raise ValueError("study run members must reference a supplied study task artifact")
        if structural_only:
            validate_experiment_run_structure_against_task(task, run)
        else:
            validated_evidence[(run.run_id, run.run_version)] = validate_experiment_run_against_task(
                task,
                run,
                evidence=None if evidence_by_run is None else evidence_by_run.get(run.run_id),
            )
    return validated_evidence


__all__ = ["validate_study_run_task_membership"]
