"""Task/run evidence validation used by experiment-study analysis."""

from __future__ import annotations

from collections.abc import Mapping

from .experiment_apparatus import ExperimentTaskModel
from .experiment_manifest_references import ExperimentEvidenceReferenceModel
from .experiment_run import (
    ExperimentRunEvidenceInputs,
    ExperimentRunModel,
    validate_experiment_run_against_task,
    validate_experiment_run_structure_against_task,
)


def validate_study_run_task_membership(
    matched_tasks: list[ExperimentTaskModel],
    matched_runs: list[ExperimentRunModel],
    evidence_by_run: Mapping[str, ExperimentRunEvidenceInputs] | None,
    *,
    structural_only: bool,
) -> dict[tuple[str, str | None], tuple[ExperimentEvidenceReferenceModel, ...]]:
    """Validate task membership and return only content-proven evidence refs."""

    task_by_key = {(task.task_id, task.task_version): task for task in matched_tasks}
    validated_evidence: dict[tuple[str, str | None], tuple[ExperimentEvidenceReferenceModel, ...]] = {}
    for run in matched_runs:
        task = task_by_key.get((run.task_ref.ref_id, run.task_ref.ref_version))
        if task is None:
            raise ValueError("study run members must reference a supplied study task artifact")
        if structural_only:
            validate_experiment_run_structure_against_task(task, run)
            validated_evidence[(run.run_id, run.run_version)] = ()
        else:
            validated_evidence[(run.run_id, run.run_version)] = validate_experiment_run_against_task(
                task,
                run,
                evidence=None if evidence_by_run is None else evidence_by_run.get(run.run_id),
            )
    return validated_evidence


__all__ = ["validate_study_run_task_membership"]
