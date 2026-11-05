"""Authored experiment capacity: an arbitrary cap on concurrent trials."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from ._base import ContractModel
from .realization_posture import Posture

MAX_TRIAL_PARALLELISM = 4096
TrialCount = Annotated[int, Field(strict=True, ge=1, le=MAX_TRIAL_PARALLELISM)]


class OpenTrialParallelismModel(ContractModel):
    """Leave effective capacity to the allocator."""

    posture: Literal[Posture.OPEN]


class ExactTrialParallelismModel(ContractModel):
    """Require one exact effective capacity."""

    posture: Literal[Posture.EXACT]
    count: TrialCount


class ConstrainedTrialParallelismModel(ContractModel):
    """Require an inclusive lower bound, upper bound, or both."""

    model_config = ConfigDict(
        json_schema_extra={
            "anyOf": [
                {"required": ["minimum"], "properties": {"minimum": {"type": "integer"}}},
                {"required": ["maximum"], "properties": {"maximum": {"type": "integer"}}},
            ]
        }
    )

    posture: Literal[Posture.CONSTRAINED]
    minimum: TrialCount | None = Field(default=None, exclude_if=lambda value: value is None)
    maximum: TrialCount | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def _validate_bounds(self) -> ConstrainedTrialParallelismModel:
        if self.minimum is None and self.maximum is None:
            raise ValueError("constrained trial parallelism requires a minimum or maximum")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("trial parallelism minimum cannot exceed maximum")
        return self


TrialParallelismModel = Annotated[
    OpenTrialParallelismModel | ExactTrialParallelismModel | ConstrainedTrialParallelismModel,
    Field(discriminator="posture"),
]


def parallelism_bounds(intent: TrialParallelismModel | None, entry_count: int) -> tuple[int, int]:
    """Return the inclusive parallel-trial bounds that the author sets.

    The upper bound is the exact count, the maximum, or ``entry_count`` (at most
    ``MAX_TRIAL_PARALLELISM``) when the value is open or has no maximum. Without
    a value, trials run one at a time.
    """

    if intent is None:
        return 1, 1
    if isinstance(intent, ExactTrialParallelismModel):
        return intent.count, intent.count
    available = min(entry_count, MAX_TRIAL_PARALLELISM)
    if isinstance(intent, OpenTrialParallelismModel):
        return 1, available
    lower = intent.minimum or 1
    upper = available if intent.maximum is None else intent.maximum
    if lower > upper:
        raise ValueError("trial parallelism minimum exceeds the trial count")
    return lower, upper


__all__ = ["MAX_TRIAL_PARALLELISM", "TrialParallelismModel", "parallelism_bounds"]
