"""Participant-directed inject delivery authoring models (DSL-142)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import ConfigDict, Field, StrictInt, field_validator, model_validator

from ._base import SDLModel
from ._identifiers import PortableIdentifier
from .participant_mixed_control_vocabulary import omit_property_titles


class ParticipantInjectDeliveryKind(str, Enum):
    """Participant-bound meaning kept distinct from orchestration identity."""

    DISCLOSURE = "disclosure"
    EXTERNAL_DIRECTION = "external-direction"
    INTERVENTION = "intervention"


class ParticipantInjectDeliveryOrderBasis(str, Enum):
    """The only admitted ordering basis for participant inject delivery."""

    ORCHESTRATION_OCCURRENCE_AND_SHARED_TIME = "orchestration-occurrence-and-shared-time"


class ParticipantInjectDeliveryFailureDisposition(str, Enum):
    """Fail-closed behavior when a declared delivery cannot be admitted."""

    REJECT_NO_DELIVERY = "reject-no-delivery"


class ParticipantInjectOccurrenceAnchor(SDLModel):
    """Exact inject occurrence in the existing event/script/story chain."""

    event_ref: str = Field(min_length=1)
    script_ref: str = Field(min_length=1)
    story_ref: str = Field(min_length=1)


class ParticipantInjectDeliveryPolicy(SDLModel):
    """Closed, reference-led participant disclosure policy coordinates."""

    policy_ref: str = Field(min_length=1)
    policy_revision: str = Field(min_length=1)
    exposure_policy_ref: str = Field(min_length=1)
    audience_scope_ref: str = Field(min_length=1)
    visibility_basis_ref: str = Field(min_length=1)
    disclosure_basis_ref: str = Field(min_length=1)

    @field_validator(
        "policy_ref",
        "policy_revision",
        "exposure_policy_ref",
        "audience_scope_ref",
        "visibility_basis_ref",
        "disclosure_basis_ref",
    )
    @classmethod
    def _require_non_empty_policy_refs(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("participant inject delivery policy refs must be non-empty")
        return value


_UNIQUE_ITEMS = {"uniqueItems": True}
_CONTROL_REF_LIST = {**_UNIQUE_ITEMS, "items": {"type": "string", "pattern": r"\S"}}


class ParticipantInjectDeliveryControl(SDLModel):
    """Rev1 binding to one permitted transition (MC-09)."""

    # It names a permission, never an occurrence: each realized delivery must join one
    # exact accepted API-409 control occurrence of that permission.

    model_config = ConfigDict(json_schema_extra=omit_property_titles)

    semantics: Literal["mixed-control-policy-occurrence/rev1"]
    policy_revision: str = Field(min_length=1, pattern=r"\S")
    permitted_transition_ref: PortableIdentifier
    controller_ref: str = Field(min_length=1, pattern=r"\S")
    authority_scope_refs: list[str] = Field(min_length=1, json_schema_extra=_CONTROL_REF_LIST)
    evidence_refs: list[str] = Field(min_length=1, json_schema_extra=_CONTROL_REF_LIST)

    @field_validator("authority_scope_refs", "evidence_refs")
    @classmethod
    def _require_unique_non_empty_refs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("participant inject delivery control refs must be non-empty")
        if len(values) != len(set(values)):
            raise ValueError("participant inject delivery control refs must be unique within each field")
        return values


_FLAT_CONTROL_LISTS = ("control_authority_scope_refs", "control_evidence_refs")
_FLAT_CONTROL_FIELDS = (
    "control_transition_ref",
    "controller_ref",
    _FLAT_CONTROL_LISTS[0],
    "control_effective_order",
    "control_valid_from_order",
    "control_valid_until_order",
    _FLAT_CONTROL_LISTS[1],
)
_FLAT_CONTROL_SCALARS = tuple(name for name in _FLAT_CONTROL_FIELDS if name not in _FLAT_CONTROL_LISTS)


def _control_block_exclusivity_schema(schema: dict[str, Any]) -> None:
    absent = {name: {"type": "null"} for name in _FLAT_CONTROL_SCALARS}
    absent.update({name: {"maxItems": 0} for name in _FLAT_CONTROL_LISTS})
    schema.setdefault("allOf", []).append(
        {"if": {"properties": {"control": {"type": "object"}}, "required": ["control"]}, "then": {"properties": absent}}
    )
    schema["allOf"].append(
        {
            "if": {"properties": {"delivery_kind": {"const": "disclosure"}}, "required": ["delivery_kind"]},
            "then": {"properties": {"control": {"type": "null"}, **absent}},
        }
    )
    flat = {name: {"not": {"type": "null"}} for name in _FLAT_CONTROL_SCALARS}
    flat.update({name: {"minItems": 1} for name in _FLAT_CONTROL_LISTS})
    schema["allOf"].append(
        {
            "if": {
                "properties": {"delivery_kind": {"enum": ["external-direction", "intervention"]}},
                "required": ["delivery_kind"],
            },
            "then": {
                "oneOf": [
                    {"properties": {"control": {"type": "object"}}, "required": ["control"]},
                    {"properties": flat, "required": list(_FLAT_CONTROL_FIELDS)},
                ]
            },
        }
    )


class ParticipantInjectDelivery(SDLModel):
    """Authored participant-local relation to one orchestration inject occurrence."""

    model_config = ConfigDict(json_schema_extra=_control_block_exclusivity_schema)

    participant_ref: str = Field(min_length=1)
    inject_ref: str = Field(min_length=1)
    occurrence: ParticipantInjectOccurrenceAnchor
    source_item_ref: str = Field(min_length=1)
    result_item_ref: str = Field(min_length=1)
    observation_boundary_ref: str = Field(min_length=1)
    delivery_kind: ParticipantInjectDeliveryKind
    delivery_policy: ParticipantInjectDeliveryPolicy
    order_basis: ParticipantInjectDeliveryOrderBasis
    temporal_constraint_refs: list[str] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    evidence_requirement_refs: list[str] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    failure_disposition: ParticipantInjectDeliveryFailureDisposition
    control_transition_ref: PortableIdentifier | None = None
    controller_ref: str | None = Field(default=None, min_length=1)
    control_authority_scope_refs: list[str] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    control_effective_order: StrictInt | None = Field(default=None, ge=0)
    control_valid_from_order: StrictInt | None = Field(default=None, ge=0)
    control_valid_until_order: StrictInt | None = Field(default=None, ge=0)
    control_evidence_refs: list[str] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    control: ParticipantInjectDeliveryControl | None = None

    @field_validator(
        "participant_ref",
        "inject_ref",
        "source_item_ref",
        "result_item_ref",
        "observation_boundary_ref",
    )
    @classmethod
    def _require_non_empty_refs(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("participant inject delivery refs must be non-empty")
        return value

    @field_validator(
        "temporal_constraint_refs",
        "evidence_requirement_refs",
        *_FLAT_CONTROL_LISTS,
    )
    @classmethod
    def _require_unique_non_empty_ref_lists(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("participant inject delivery ref lists must be non-empty")
        if len(values) != len(set(values)):
            raise ValueError("participant inject delivery refs must be unique within each field")
        return values

    @model_validator(mode="after")
    def _validate_control_binding_shape(self) -> ParticipantInjectDelivery:
        directs_control = self.delivery_kind in {
            ParticipantInjectDeliveryKind.EXTERNAL_DIRECTION,
            ParticipantInjectDeliveryKind.INTERVENTION,
        }
        if self.control is not None:
            self._validate_control_block(directs_control)
            return self
        control_fields = {name: getattr(self, name) for name in _FLAT_CONTROL_FIELDS}
        if directs_control:
            self._validate_flat_control_agreement(control_fields)
        else:
            present = [field_name for field_name, value in control_fields.items() if value is not None and value != []]
            if present:
                raise ValueError("disclosure delivery cannot carry control agreement fields: " + ", ".join(present))
        return self

    def _validate_flat_control_agreement(self, control_fields: dict[str, object]) -> None:
        missing = [field_name for field_name, value in control_fields.items() if value is None or value == []]
        if missing:
            raise ValueError(
                f"{self.delivery_kind.value} delivery requires complete control agreement fields: " + ", ".join(missing)
            )
        if self.control_valid_until_order < self.control_valid_from_order:
            raise ValueError("participant inject delivery control validity interval must not be inverted")
        if not self.control_valid_from_order <= self.control_effective_order <= self.control_valid_until_order:
            raise ValueError("participant inject delivery control effective order must fall within its interval")

    def _validate_control_block(self, directs_control: bool) -> None:
        flat = [name for name in _FLAT_CONTROL_FIELDS if getattr(self, name) not in (None, [])]
        if flat:
            raise ValueError(
                "participant inject delivery control block excludes flat control fields: " + ", ".join(flat)
            )
        if not directs_control:
            raise ValueError("disclosure delivery cannot carry a control block")


def participant_inject_delivery_reference(spec_name: str, binding_id: str) -> str:
    """Return the stable authored reference for one participant inject delivery."""

    return f"behavior_specifications.{spec_name}.participant_inject_deliveries.{binding_id}"
