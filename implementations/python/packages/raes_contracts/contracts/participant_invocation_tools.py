"""Issue #1740 capability claim for tool actions hosted by an autonomous invocation."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from .base import ContractModel

INVOCATION_TOOL_ACTIONS_SEMANTICS = "participant-invocation-tool-actions/v1"
Limit = Annotated[int, Field(strict=True, ge=1)]


class ParticipantInvocationToolActionCapabilitiesModel(ContractModel):
    """Exact composition version and finite per-invocation limits."""

    model_config = ConfigDict(revalidate_instances="always")

    semantic_versions: list[Literal["participant-invocation-tool-actions/v1"]] = Field(
        min_length=1, json_schema_extra={"uniqueItems": True}
    )
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
    if not supports_autonomous_execution:
        raise ValueError("invocation_tool_actions requires autonomous execution support")
    if not supports_tool_affordances:
        raise ValueError("invocation_tool_actions requires positive tool_affordances support")


__all__ = (
    "INVOCATION_TOOL_ACTIONS_SEMANTICS",
    "ParticipantInvocationToolActionCapabilitiesModel",
    "validate_invocation_tool_action_claim",
)
