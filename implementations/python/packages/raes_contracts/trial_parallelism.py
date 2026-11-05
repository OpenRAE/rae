"""Authored experiment capacity, independent of isolation and live leases."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from ._base import ContractModel
from .realization_posture import Posture

TrialCount = Annotated[int, Field(strict=True, ge=1)]


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


def parallelism_bounds(intent: TrialParallelismModel | None, ceiling: int) -> tuple[int, int]:
    """Intersect author intent with independently admitted isolation capacity."""

    lower = 1
    if isinstance(intent, ExactTrialParallelismModel):
        lower, ceiling = intent.count, min(ceiling, intent.count)
    elif isinstance(intent, ConstrainedTrialParallelismModel):
        lower = intent.minimum or 1
        if intent.maximum is not None:
            ceiling = min(ceiling, intent.maximum)
    if lower > ceiling:
        raise ValueError("trial parallelism cannot be met by the admitted isolation capacity")
    return lower, ceiling


__all__ = ["TrialParallelismModel", "parallelism_bounds"]
