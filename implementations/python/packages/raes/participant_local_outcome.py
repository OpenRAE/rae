"""Versioned ACT-618 local meaning within the SEM-215 rule family."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ._base import SDLModel

OutcomeCategory = Literal["task_completion", "effect_realization"]
OutcomeAttainment = Literal["undetermined", "not_attained", "partial", "attained"]
OutcomeKnowledge = Literal["unknown", "supported", "conflicting", "withheld"]
_Text = Annotated[str, Field(min_length=1, pattern=r"\S")]


class LocalOutcomeCriterion(SDLModel):
    """An explicitly declared realized effect, never an action status shortcut."""

    criterion_id: _Text
    source_id: _Text
    effect_id: _Text


class LocalOutcomeDefinition(SDLModel):
    """All criteria must be evidenced; contradictory observations need correction."""

    model_version: Literal["1.0.0"]
    category: OutcomeCategory
    criterion_basis: _Text
    criteria: list[LocalOutcomeCriterion] = Field(min_length=1)
    conflict_policy: Literal["retain_until_explicit_correction"]
    freshness_policy: Literal["exact_observation_cut"]
    episode_policy: Literal["reset_without_transfer"]

    @model_validator(mode="after")
    def _unique_criteria(self) -> "LocalOutcomeDefinition":
        identities = [criterion.criterion_id for criterion in self.criteria]
        bindings = [(criterion.source_id, criterion.effect_id) for criterion in self.criteria]
        if len(set(identities)) != len(identities) or len(set(bindings)) != len(bindings):
            raise ValueError("local outcome criteria and effect bindings must be unique")
        return self
