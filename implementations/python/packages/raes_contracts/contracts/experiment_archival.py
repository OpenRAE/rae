"""Archival timestamp validators for experiment contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .base import _payload_get, _validate_artifact_collection_created_at, _validate_rfc3339_payload_field
from .experiment_apparatus import ExperimentApparatusContextModel, ExperimentTaskModel
from .experiment_run import ExperimentRunModel
from .experiment_spec import ExperimentStudyModel


def validate_experiment_task_archival_datetimes(task: ExperimentTaskModel | Mapping[str, Any]) -> None:
    """Validate task-level archival timestamp semantics not carried by generic JSON Schema."""

    _validate_artifact_collection_created_at("artifact_refs", _payload_get(task, "artifact_refs"))


def validate_experiment_apparatus_context_archival_datetimes(
    apparatus_context: ExperimentApparatusContextModel | Mapping[str, Any],
) -> None:
    """Validate apparatus-context archival timestamp semantics not carried by generic JSON Schema."""

    _validate_rfc3339_payload_field(apparatus_context, "declared_at")
    _validate_artifact_collection_created_at(
        "observed_setup_evidence",
        _payload_get(apparatus_context, "observed_setup_evidence"),
    )


def validate_experiment_run_archival_datetimes(run: ExperimentRunModel | Mapping[str, Any]) -> None:
    """Validate run-level archival timestamp semantics not carried by generic JSON Schema."""

    _validate_rfc3339_payload_field(run, "started_at")
    _validate_rfc3339_payload_field(run, "ended_at")
    invalidation = _payload_get(run, "invalidation")
    if invalidation is not None:
        _validate_rfc3339_payload_field(invalidation, "invalidated_at")
    _validate_artifact_collection_created_at("evidence_artifacts", _payload_get(run, "evidence_artifacts"))


def validate_experiment_study_archival_datetimes(study: ExperimentStudyModel | Mapping[str, Any]) -> None:
    """Validate study-level archival timestamp semantics not carried by generic JSON Schema."""

    _validate_artifact_collection_created_at("report_artifacts", _payload_get(study, "report_artifacts"))
    _validate_artifact_collection_created_at("export_artifacts", _payload_get(study, "export_artifacts"))


__all__ = [
    "validate_experiment_apparatus_context_archival_datetimes",
    "validate_experiment_run_archival_datetimes",
    "validate_experiment_study_archival_datetimes",
    "validate_experiment_task_archival_datetimes",
]
