"""Canonical after-effect retry posture shared by cleanup and authored operation policy."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ._base import ContractModel

RetryAttempts = Annotated[int, Field(ge=1)]
RetryReference = Annotated[str, Field(min_length=1)]


def _require_unique(field_name: str, values: list[str]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")


class ExecutionRetryPolicyModel(ContractModel):
    """Retry posture after an execution attempt may have produced effects."""

    max_attempts: RetryAttempts
    after_effect_policy: Literal["disallow", "idempotent", "reset", "compensate"]
    reset_obligation_refs: list[RetryReference] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    compensation_refs: list[RetryReference] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def _validate_policy(self) -> ExecutionRetryPolicyModel:
        _require_unique("reset_obligation_refs", self.reset_obligation_refs)
        _require_unique("compensation_refs", self.compensation_refs)
        if self.after_effect_policy == "reset" and not self.reset_obligation_refs:
            raise ValueError("reset retry policy requires reset_obligation_refs")
        if self.after_effect_policy == "compensate" and not self.compensation_refs:
            raise ValueError("compensate retry policy requires compensation_refs")
        if self.after_effect_policy != "reset" and self.reset_obligation_refs:
            raise ValueError("reset_obligation_refs are only valid for reset retry policy")
        if self.after_effect_policy != "compensate" and self.compensation_refs:
            raise ValueError("compensation_refs are only valid for compensate retry policy")
        return self
