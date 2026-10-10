"""Authored participant episode structure and termination intent (DSL-120).

An episode policy is participant *intent* attached to one behavior
specification. It names the closed SDL declarations that define episode
initialization, the turn order authority, terminal and truncation conditions,
and reset-related policy. It is never an execution record: realized episode
identity, lifecycle state, terminal reasons, history and decision epochs stay on
the ADR-013 participant episode contracts and the ADR-095 decision surface.
"""

from __future__ import annotations

from dataclasses import fields
from enum import Enum
from typing import Annotated, Any, ClassVar, Literal, TypeVar

from pydantic import AfterValidator, Field, GetJsonSchemaHandler, model_validator
from pydantic_core import CoreSchema
from raes_contracts.participant_episode import (
    ParticipantEpisodeControlAction,
    ParticipantEpisodeExecutionState,
    ParticipantEpisodeHistoryEvent,
)

from ._base import SDLModel
from ._identifiers import PortableIdentifier

# Realized coordinates owned by the ADR-013 episode state and history contracts,
# plus the ADR-095 decision epoch that callers never author. A policy record that
# carries one of them would be asserting execution rather than declaring intent.
REALIZED_EPISODE_STATE_FIELDS = frozenset(
    {item.name for item in fields(ParticipantEpisodeExecutionState)}
    | {item.name for item in fields(ParticipantEpisodeHistoryEvent)}
    | {"decision_epoch"}
)
# A policy must declare at least one of these elements.
_STRUCTURE_RECORDS = ("initialization", "interaction_structure", "reset_policy")
_STRUCTURE_MAPS = ("terminal_conditions", "truncation_conditions")

_Item = TypeVar("_Item")


def _unique_items(values: list[_Item]) -> list[_Item]:
    if len(values) != len(set(values)):
        raise ValueError("participant episode policy lists must not repeat an item")
    return values


EpisodePolicyRef = Annotated[str, Field(min_length=1, pattern=r"\S")]
EpisodePolicyRefs = Annotated[
    list[EpisodePolicyRef],
    Field(min_length=1, json_schema_extra={"uniqueItems": True}),
    AfterValidator(_unique_items),
]


class ParticipantEpisodeTurnOrderBasis(str, Enum):
    """Authority that orders a participant's turns."""

    DECISION_EPOCH = "decision-epoch"


class ParticipantEpisodeResetAction(str, Enum):
    """ADR-013 control actions that start a later episode."""

    RESET = ParticipantEpisodeControlAction.RESET.value
    RESTART = ParticipantEpisodeControlAction.RESTART.value


class ParticipantEpisodeMemoryScope(str, Enum):
    """ADR-095 participant-memory scope across a reset."""

    EPISODE_LOCAL_RESET = "episode_local_reset"
    PERSISTENT_ACROSS_EPISODES = "persistent_across_episodes"


class _EpisodePolicyIntent(SDLModel):
    """Closed policy record that rejects realized episode state by name."""

    # Set by a condition whose map already fixes its terminal reason.
    implied_terminal_reason: ClassVar[str | None] = None

    @model_validator(mode="before")
    @classmethod
    def _reject_realized_episode_state(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if cls.implied_terminal_reason is not None and "terminal_reason" in data:
            raise ValueError(
                f"these conditions always end the episode as {cls.implied_terminal_reason} and carry no terminal_reason"
            )
        realized = sorted(REALIZED_EPISODE_STATE_FIELDS.intersection(data) - set(cls.model_fields))
        if realized:
            raise ValueError(
                "participant episode policies declare intent only; realized episode state belongs to "
                "the ADR-013 participant episode state and history contracts: " + ", ".join(realized)
            )
        return data


class ParticipantEpisodeInitialization(_EpisodePolicyIntent):
    """Preconditions of every new episode generation."""

    assertion_refs: EpisodePolicyRefs


class ParticipantEpisodeInteractionStructure(_EpisodePolicyIntent):
    """Turn order authority and the actions a turn offers."""

    order_basis: ParticipantEpisodeTurnOrderBasis
    action_contract_refs: EpisodePolicyRefs


class ParticipantEpisodeCompletionCondition(_EpisodePolicyIntent):
    """Evidenced assertions that end the episode as completed."""

    terminal_reason: Literal["completed"]
    assertion_refs: EpisodePolicyRefs
    evidence_requirement_refs: EpisodePolicyRefs


class ParticipantEpisodeTimeoutCondition(_EpisodePolicyIntent):
    """Evidenced clock limit that ends the episode as timed out."""

    terminal_reason: Literal["timed_out"]
    temporal_constraint_ref: EpisodePolicyRef
    evidence_requirement_refs: EpisodePolicyRefs


ParticipantEpisodeTerminalCondition = Annotated[
    ParticipantEpisodeCompletionCondition | ParticipantEpisodeTimeoutCondition,
    Field(discriminator="terminal_reason"),
]


class ParticipantEpisodeTruncationCondition(_EpisodePolicyIntent):
    """Evidenced assertions that end the episode as truncated."""

    implied_terminal_reason: ClassVar[str | None] = "truncated"

    assertion_refs: EpisodePolicyRefs
    evidence_requirement_refs: EpisodePolicyRefs


class ParticipantEpisodeResetPolicy(_EpisodePolicyIntent):
    """Admitted reset actions, memory scope, reset authority, and evidence."""

    # The ADR-095 assurance and information-state contracts require the same pairing: an
    # episode_local_reset scope names the authority that resets the participant
    # implementation and every participant-visible memory channel, and a
    # persistent_across_episodes scope claims no reset authority. Semantic
    # validation resolves the authority to exactly one declared targetable element.

    control_actions: Annotated[
        list[ParticipantEpisodeResetAction],
        Field(min_length=1, json_schema_extra={"uniqueItems": True}),
        AfterValidator(_unique_items),
    ]
    participant_memory_scope: ParticipantEpisodeMemoryScope
    memory_reset_authority_ref: EpisodePolicyRef | None = None
    evidence_requirement_refs: EpisodePolicyRefs

    @model_validator(mode="after")
    def _validate_reset_authority(self) -> ParticipantEpisodeResetPolicy:
        local = self.participant_memory_scope is ParticipantEpisodeMemoryScope.EPISODE_LOCAL_RESET
        if local and self.memory_reset_authority_ref is None:
            raise ValueError("episode_local_reset memory scope requires memory_reset_authority_ref")
        if not local and self.memory_reset_authority_ref is not None:
            raise ValueError("persistent_across_episodes memory scope must not claim a reset authority")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> dict[str, Any]:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema["allOf"] = [
            {
                "if": {"properties": {"participant_memory_scope": {"const": "episode_local_reset"}}},
                "then": {
                    "required": ["memory_reset_authority_ref"],
                    "properties": {"memory_reset_authority_ref": {"type": "string"}},
                },
                "else": {"properties": {"memory_reset_authority_ref": {"type": "null"}}},
            }
        ]
        return json_schema


class ParticipantEpisodePolicy(_EpisodePolicyIntent):
    """Versioned episode structure intent of a behavior specification."""

    profile: Literal["participant-episode-policy/v1"]
    initialization: ParticipantEpisodeInitialization | None = None
    interaction_structure: ParticipantEpisodeInteractionStructure | None = None
    terminal_conditions: dict[PortableIdentifier, ParticipantEpisodeTerminalCondition] = Field(
        default_factory=dict,
        json_schema_extra={"additionalProperties": False},
    )
    truncation_conditions: dict[PortableIdentifier, ParticipantEpisodeTruncationCondition] = Field(
        default_factory=dict,
        json_schema_extra={"additionalProperties": False},
    )
    reset_policy: ParticipantEpisodeResetPolicy | None = None

    @model_validator(mode="after")
    def _validate_policy_shape(self) -> ParticipantEpisodePolicy:
        if not any(getattr(self, name) for name in (*_STRUCTURE_RECORDS, *_STRUCTURE_MAPS)):
            raise ValueError("participant episode policies must declare at least one episode structure element")
        shared = sorted(set(self.terminal_conditions).intersection(self.truncation_conditions))
        if shared:
            raise ValueError(
                "participant episode condition ids must be unique across terminal and truncation conditions: "
                + ", ".join(shared)
            )
        # One evidenced set of assertions cannot end an episode as both completed and truncated.
        completions = {
            frozenset(condition.assertion_refs)
            for condition in self.terminal_conditions.values()
            if isinstance(condition, ParticipantEpisodeCompletionCondition)
        }
        aliases = sorted(
            condition_id
            for condition_id, condition in self.truncation_conditions.items()
            if frozenset(condition.assertion_refs) in completions
        )
        if aliases:
            raise ValueError(
                "participant episode truncation conditions must not reuse the assertions of a completion condition: "
                + ", ".join(aliases)
            )
        return self


__all__ = [
    "REALIZED_EPISODE_STATE_FIELDS",
    "ParticipantEpisodeCompletionCondition",
    "ParticipantEpisodeInitialization",
    "ParticipantEpisodeInteractionStructure",
    "ParticipantEpisodeMemoryScope",
    "ParticipantEpisodePolicy",
    "ParticipantEpisodeResetAction",
    "ParticipantEpisodeResetPolicy",
    "ParticipantEpisodeTerminalCondition",
    "ParticipantEpisodeTimeoutCondition",
    "ParticipantEpisodeTruncationCondition",
    "ParticipantEpisodeTurnOrderBasis",
]
