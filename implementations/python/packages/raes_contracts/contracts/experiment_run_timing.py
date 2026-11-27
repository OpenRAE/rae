"""Core timing and status validation for archival experiment runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..timestamps import parse_rfc3339_datetime

if TYPE_CHECKING:
    from .experiment_run import ExperimentRunModel


def validate_run_timing(run: ExperimentRunModel) -> None:
    """Require a non-negative archival run interval."""

    started_at = parse_rfc3339_datetime("started_at", run.started_at)
    if run.ended_at is None:
        return
    ended_at = parse_rfc3339_datetime("ended_at", run.ended_at)
    if ended_at < started_at:
        raise ValueError("ended_at must be greater than or equal to started_at")


def validate_run_invalidation_status(run: ExperimentRunModel) -> None:
    """Require details whenever the archival status is invalidated."""

    if run.run_status == "invalidated" and run.invalidation is None:
        raise ValueError("invalidated experiment runs must include invalidation details")


__all__ = ["validate_run_invalidation_status", "validate_run_timing"]
