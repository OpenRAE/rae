"""Typed portable resource state and its explicit provisioning profile host."""

from typing import Any

from pydantic import Field, model_validator

from ..addressing import CompiledAddress
from ..domain_profiles import DomainProfileBindingModel
from ..realization_profiles import profile_binding_tree, profile_resource_address
from .base import ContractModel


class SnapshotEntryModel(ContractModel):
    address: CompiledAddress
    domain: str
    resource_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    ordering_dependencies: list[CompiledAddress] = Field(default_factory=list)
    refresh_dependencies: list[CompiledAddress] = Field(default_factory=list)
    status: str = "ready"
    profile_bindings: tuple[DomainProfileBindingModel, ...] = Field(
        default=(), max_length=256, exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def _validate_profile_owners(self) -> "SnapshotEntryModel":
        if self.profile_bindings and (
            self.domain != "provisioning"
            or any(
                profile_resource_address(binding) != self.address
                for binding in profile_binding_tree(self.profile_bindings).values()
            )
        ):
            raise ValueError("Snapshot profile bindings must belong to their provisioning resource")
        return self
