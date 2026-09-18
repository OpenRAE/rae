"""Closed, schedule-independent authority inputs for SCE-002 compilation."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonEmptyString, PositiveInteger
from .trial_cleanup import (
    CleanStateRequirementModel,
    CleanupObligationModel,
    CleanupResourceBoundaryModel,
    ExecutionRetryPolicyModel,
    TrialCleanupPlanModel,
)


class TrialCompilationLimitsModel(ContractModel):
    """Explicit resource ceilings; changing a non-binding ceiling cannot change plan bytes."""

    max_coordinates: PositiveInteger = 10_000
    max_domain_values_per_point: PositiveInteger = 10_000
    max_product_outputs: PositiveInteger = 10_000
    max_bindings_per_entry: PositiveInteger = 256
    max_draws_per_entry: PositiveInteger = 256
    max_diagnostics: PositiveInteger = 128
    max_mixed_profiles: PositiveInteger = 256
    max_mixed_context_work: PositiveInteger = 1_000_000
    max_plan_bytes: PositiveInteger = 32 * 1024 * 1024


class TrialCleanupTemplateModel(ContractModel):
    """Complete cleanup intent before compiler-derived entry/run identities exist."""

    clean_state: CleanStateRequirementModel
    resource_boundaries: dict[NonEmptyString, CleanupResourceBoundaryModel] = Field(min_length=1)
    cleanup_obligations: dict[NonEmptyString, CleanupObligationModel] = Field(min_length=1)
    retry_policy: ExecutionRetryPolicyModel

    @model_validator(mode="after")
    def _validate_template(self) -> TrialCleanupTemplateModel:
        self.bind(
            plan_id="cleanup-template",
            plan_entry_id="entry-template",
            run_id="run-template",
        )
        return self

    def bind(self, *, plan_id: str, plan_entry_id: str, run_id: str) -> TrialCleanupPlanModel:
        """Bind the complete template to deterministic compiler identities."""

        return TrialCleanupPlanModel(
            plan_id=plan_id,
            plan_entry_id=plan_entry_id,
            run_id=run_id,
            clean_state=self.clean_state,
            resource_boundaries=self.resource_boundaries,
            cleanup_obligations=self.cleanup_obligations,
            retry_policy=self.retry_policy,
        )


class TrialExecutionAuthorityModel(ContractModel):
    """Explicit attempt and cleanup authority consumed by the pure compiler."""

    attempt_timeout_seconds: PositiveInteger
    on_timeout: Literal["cancel", "abort", "cleanup-and-fail"]
    on_cancellation: Literal["abort", "cleanup-and-fail"]
    cleanup: TrialCleanupTemplateModel


__all__ = [
    "TrialCleanupTemplateModel",
    "TrialCompilationLimitsModel",
    "TrialExecutionAuthorityModel",
]
