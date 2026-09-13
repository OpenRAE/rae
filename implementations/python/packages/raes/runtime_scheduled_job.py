"""Scheduled-job runtime inventory models (shared cadence primitive)."""

from enum import Enum

from pydantic import field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel
from .runtime_values import (
    parse_optional_bool_or_var,
    parse_runtime_enum_or_var,
    require_symbol,
)

__all__ = [
    "RuntimeScheduledJob",
    "RuntimeScheduledJobLastResult",
    "RuntimeScheduledJobRunState",
    "RuntimeScheduledJobSchedule",
    "RuntimeScheduledJobScheduleKind",
]


class RuntimeScheduledJobScheduleKind(str, Enum):
    """Closed structural recurrence vocabulary for a scheduled-job schedule.

    This is a fixed structural vocabulary (POSIX crontab / RFC 5545 RRULE /
    fixed-interval), so per the DSL-139 enum-sentinel rule it carries neither
    ``unknown`` nor ``other``.
    """

    INTERVAL = "interval"
    CRON = "cron"
    CALENDAR = "calendar"


class RuntimeScheduledJobLastResult(str, Enum):
    """Open run-outcome taxonomy for the most recent scheduled-job execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeScheduledJobSchedule(SDLModel):
    """The recurrence cadence for a scheduled job."""

    kind: GovernedVocabulary[RuntimeScheduledJobScheduleKind] = RuntimeScheduledJobScheduleKind.INTERVAL
    spec: str = ""
    enabled: bool | str | None = None

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeScheduledJobScheduleKind | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeScheduledJobScheduleKind, field_name="kind")

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_enabled(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="enabled")


class RuntimeScheduledJobRunState(SDLModel):
    """Observed run-state for a scheduled job."""

    last_run: str = ""
    next_run: str = ""
    last_result: GovernedVocabulary[RuntimeScheduledJobLastResult] = RuntimeScheduledJobLastResult.UNKNOWN

    @field_validator("last_result", mode="before")
    @classmethod
    def normalize_last_result(cls, v: RuntimeScheduledJobLastResult | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeScheduledJobLastResult, field_name="last_result")


class RuntimeScheduledJob(SDLModel):
    """Node-scoped runtime inventory for a recurring scheduled job (cadence + run-state)."""

    scheduled_job_id: str
    name: str = ""
    command_ref: str = ""
    enabled: bool | str | None = None
    schedule: RuntimeScheduledJobSchedule | None = None
    run_state: RuntimeScheduledJobRunState | None = None
    description: str = ""

    @field_validator("scheduled_job_id")
    @classmethod
    def validate_scheduled_job_id(cls, v: str) -> str:
        return require_symbol(v, field_name="scheduled_job_id")

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_enabled(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="enabled")

    @model_validator(mode="after")
    def validate_scheduled_job(self) -> "RuntimeScheduledJob":
        return self
