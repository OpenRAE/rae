"""Experiment-run validation and schema annotations for adaptive difficulty."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic.json_schema import JsonSchemaValue

from ..timestamps import parse_rfc3339_datetime
from .schema_invariants import _add_raes_invariant

if TYPE_CHECKING:
    from .difficulty_adaptation import DifficultyInterventionRecordModel
    from .experiment_run import ExperimentRunModel


def validate_run_difficulty_provenance(run: ExperimentRunModel) -> None:
    """Validate difficulty records against the archival run scope and time window."""

    provenance = run.difficulty_provenance
    if provenance is None:
        return
    started_at = parse_rfc3339_datetime("started_at", run.started_at)
    ended_at = parse_rfc3339_datetime("ended_at", run.ended_at)
    decisions_by_id = _difficulty_decision_times(run, started_at, ended_at)
    for intervention in provenance.interventions:
        _validate_difficulty_intervention_time(
            run,
            intervention,
            decisions_by_id,
            started_at,
            ended_at,
        )


def _difficulty_decision_times(
    run: ExperimentRunModel,
    started_at: datetime,
    ended_at: datetime,
) -> dict[str, datetime]:
    assert run.difficulty_provenance is not None
    decisions_by_id = {}
    for decision in run.difficulty_provenance.decisions:
        if decision.run_id != run.run_id:
            raise ValueError("difficulty decisions must match the archival run_id")
        decided_at = parse_rfc3339_datetime("difficulty decision decided_at", decision.decided_at)
        if decided_at < started_at or decided_at > ended_at:
            raise ValueError("difficulty decision timing must be within the run")
        decisions_by_id[decision.decision_id] = decided_at
    return decisions_by_id


def _validate_difficulty_intervention_time(
    run: ExperimentRunModel,
    intervention: DifficultyInterventionRecordModel,
    decisions_by_id: dict[str, datetime],
    started_at: datetime,
    ended_at: datetime,
) -> None:
    if intervention.run_id != run.run_id:
        raise ValueError("difficulty interventions must match the archival run_id")
    occurred_at = parse_rfc3339_datetime(
        "difficulty intervention occurred_at",
        intervention.occurred_at,
    )
    if occurred_at < started_at or occurred_at > ended_at:
        raise ValueError("difficulty intervention timing must be within the run")
    if occurred_at < decisions_by_id[intervention.decision_id]:
        raise ValueError("difficulty interventions must not precede their selected decision")


def add_run_difficulty_invariants(json_schema: JsonSchemaValue) -> None:
    """Publish run-local and cross-artifact difficulty invariants."""

    _add_raes_invariant(
        json_schema,
        "adaptive-difficulty-run-provenance-valid",
        "Difficulty decisions and interventions match the archival run id, remain within the run time window, "
        "and preserve fixed/adaptive/scaffolded policy provenance.",
        inputs=[{"contract_id": "experiment-run-v1", "instance_path": "#/difficulty_provenance"}],
    )
    _add_raes_invariant(
        json_schema,
        "adaptive-difficulty-authoring-admission-valid",
        "Difficulty provenance must match the exact digest-bound authoring input, allocated condition, task, "
        "and immutable policy snapshot.",
        inputs=[
            {"contract_id": "experiment-authoring-input-v1", "instance_path": "#"},
            {"contract_id": "experiment-run-v1", "instance_path": "#"},
        ],
    )


__all__ = ["add_run_difficulty_invariants", "validate_run_difficulty_provenance"]
