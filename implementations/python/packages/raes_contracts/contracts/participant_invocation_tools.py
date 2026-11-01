"""Explicit capability versions for tools hosted by participant invocations."""

from collections.abc import Iterable
from typing import Annotated, Literal, Protocol

from pydantic import ConfigDict, Field, model_validator

from .base import ContractModel

INVOCATION_TOOL_ACTIONS_SEMANTICS = "participant-invocation-tool-actions/v1"
DELIVERY_TOOL_ACTIONS_SEMANTICS = "participant-invocation-tool-actions/v2"
Limit = Annotated[int, Field(strict=True, ge=1)]


class ParticipantInvocationToolActionCapabilitiesModel(ContractModel):
    """Exact composition version and finite per-invocation limits."""

    model_config = ConfigDict(revalidate_instances="always")

    semantic_versions: list[
        Literal["participant-invocation-tool-actions/v1", "participant-invocation-tool-actions/v2"]
    ] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    max_tool_actions_per_invocation: Limit
    max_concurrent_tool_actions_per_invocation: Limit

    @model_validator(mode="after")
    def _bounded(self) -> ParticipantInvocationToolActionCapabilitiesModel:
        if len(set(self.semantic_versions)) != len(self.semantic_versions):
            raise ValueError("semantic_versions must contain unique values")
        if self.max_concurrent_tool_actions_per_invocation > self.max_tool_actions_per_invocation:
            raise ValueError("max_concurrent_tool_actions_per_invocation cannot exceed max_tool_actions_per_invocation")
        return self


def validate_invocation_tool_action_claim(
    claim: ParticipantInvocationToolActionCapabilitiesModel | None,
    *,
    supports_autonomous_execution: bool,
    supports_tool_affordances: bool,
) -> None:
    """Join the composition claim to the two capabilities it composes."""

    if claim is None:
        return
    if INVOCATION_TOOL_ACTIONS_SEMANTICS in claim.semantic_versions and not supports_autonomous_execution:
        raise ValueError("invocation_tool_actions requires autonomous execution support")
    if not supports_tool_affordances:
        raise ValueError("invocation_tool_actions requires positive tool_affordances support")


def delivery_tool_actions_enabled(claim: ParticipantInvocationToolActionCapabilitiesModel | None) -> bool:
    return claim is not None and DELIVERY_TOOL_ACTIONS_SEMANTICS in claim.semantic_versions


class _ExecutionBindingIdentity(Protocol):
    binding_id: str


def validate_delivery_tool_bindings(
    claim: ParticipantInvocationToolActionCapabilitiesModel | None, bindings: Iterable[_ExecutionBindingIdentity]
) -> None:
    if not delivery_tool_actions_enabled(claim):
        return
    identities = [binding.binding_id for binding in bindings]
    if len(identities) != len(set(identities)):
        raise ValueError("delivery tool execution bindings must have unique identities")


__all__ = (
    "INVOCATION_TOOL_ACTIONS_SEMANTICS",
    "DELIVERY_TOOL_ACTIONS_SEMANTICS",
    "delivery_tool_actions_enabled",
    "validate_delivery_tool_bindings",
    "ParticipantInvocationToolActionCapabilitiesModel",
    "validate_invocation_tool_action_claim",
)
