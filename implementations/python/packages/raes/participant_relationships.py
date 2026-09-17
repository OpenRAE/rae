"""Explicit participant intent within the canonical SDL relationship graph."""

from enum import Enum
from typing import Annotated

from pydantic import ConfigDict, Field, field_validator, model_validator

from ._base import SDLModel

RelationshipReference = Annotated[str, Field(min_length=1, pattern=r"\S")]

PARTICIPANT_RELATIONSHIP_REFERENCE_SECTIONS = {
    "source_action_refs": "action_contracts",
    "target_action_refs": "action_contracts",
    "objective_refs": "objectives",
    "behavior_specification_refs": "behavior_specifications",
    "authority_basis_refs": "named",
    "scope_refs": "named",
    "observation_boundary_refs": "observation_boundaries",
}


class ParticipantRelationshipKind(str, Enum):
    """Portable relation meanings, independent of backend mechanisms."""

    COORDINATION = "coordination"
    DELEGATION = "delegation"
    COOPERATION = "cooperation"
    COMPETITION = "competition"
    SUPERVISION = "supervision"


class ParticipantRelationship(SDLModel):
    """Directed authored intent; a declaration never grants operational rights."""

    model_config = ConfigDict(
        json_schema_extra={
            "if": {
                "required": ["control_specification_ref"],
                "properties": {"control_specification_ref": {"type": "string"}},
            },
            "then": {"properties": {"kind": {"enum": ["delegation", "supervision"]}}},
        }
    )

    kind: ParticipantRelationshipKind
    source_action_refs: list[RelationshipReference] = Field(
        default_factory=list, json_schema_extra={"uniqueItems": True}
    )
    target_action_refs: list[RelationshipReference] = Field(
        default_factory=list, json_schema_extra={"uniqueItems": True}
    )
    objective_refs: list[RelationshipReference] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    behavior_specification_refs: list[RelationshipReference] = Field(
        default_factory=list, json_schema_extra={"uniqueItems": True}
    )
    authority_basis_refs: list[RelationshipReference] = Field(
        default_factory=list, json_schema_extra={"uniqueItems": True}
    )
    scope_refs: list[RelationshipReference] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    observation_boundary_refs: list[RelationshipReference] = Field(
        default_factory=list, json_schema_extra={"uniqueItems": True}
    )
    control_specification_ref: str | None = Field(default=None, min_length=1, pattern=r"\S")

    @field_validator(*PARTICIPANT_RELATIONSHIP_REFERENCE_SECTIONS)
    @classmethod
    def validate_refs(cls, refs: list[str]) -> list[str]:
        if any(not ref.strip() for ref in refs) or len(refs) != len(set(refs)):
            raise ValueError("participant relationship references must be non-empty and unique")
        return refs

    @model_validator(mode="after")
    def validate_control_kind(self) -> "ParticipantRelationship":
        if self.control_specification_ref is not None and self.kind not in {
            ParticipantRelationshipKind.DELEGATION,
            ParticipantRelationshipKind.SUPERVISION,
        }:
            raise ValueError("control_specification_ref requires delegation or supervision")
        return self
