"""The closed operation member shared by every published native phase plan."""

from typing import Any, Self

from pydantic import ConfigDict, Field, model_validator

from ..addressing import CompiledAddress
from ..domain_profiles import DomainProfileBindingModel
from ..execution_policy import EffectiveExecutionPolicy, validate_effective_execution_policies
from ..execution_policy_schema import execution_policy_schema
from .base import ContractModel


class PlanOperationModel(ContractModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=execution_policy_schema)
    execution_policy: EffectiveExecutionPolicy | None = Field(default=None, exclude_if=lambda value: value is None)
    execution_policy_scopes: tuple[EffectiveExecutionPolicy, ...] = Field(
        default=(), max_length=256, exclude_if=lambda value: not value
    )
    action: str
    address: CompiledAddress
    resource_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    ordering_dependencies: list[CompiledAddress] = Field(default_factory=list)
    refresh_dependencies: list[CompiledAddress] = Field(default_factory=list)
    profile_bindings: tuple[DomainProfileBindingModel, ...] = Field(
        default=(), max_length=256, exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def _execution_policy_consistency(self) -> Self:
        validate_effective_execution_policies(self.execution_policy, self.execution_policy_scopes)
        return self
