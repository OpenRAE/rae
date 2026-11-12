"""Closed ACT-620 asset versions and reference-only participant evidence."""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import Field, GetJsonSchemaHandler, StrictInt, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..uri_safety import validate_safe_absolute_uri
from .base import ContractModel, Sha256DigestString
from .experiment_artifacts import ExperimentArtifactRefModel
from .participant_decision_state_cut import ParticipantDecisionSurfaceStateCutModel
from .schema_invariants import add_raes_invariant

__all__ = [
    "ParticipantControlContextAssetModel",
    "ParticipantControlContextAssetReferenceModel",
    "ParticipantControlContextChangeModel",
    "ParticipantControlContextRecordModel",
]

ContextReference = Annotated[str, Field(min_length=1, max_length=1024)]
ContextReferences = Annotated[list[ContextReference], Field(max_length=256, json_schema_extra={"uniqueItems": True})]


class _ControlContextModel(ContractModel):
    _CONTRACT_ID: ClassVar[str]

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        add_raes_invariant(
            schema,
            "control-context-trusted-agreement",
            "Full conformance requires trusted exact version, lifecycle, authority, recipient, "
            "cut and content agreement.",
            validator="raes_contracts.participant_control_context.validate_control_context_" + cls._CONTRACT_ID,
            inputs=[{"contract_id": "participant-control-context-" + cls._CONTRACT_ID + "-v1", "instance_path": "#"}],
        )
        return schema


class ParticipantControlContextAssetReferenceModel(ContractModel):
    asset_id: ContextReference
    asset_version: ContextReference
    asset_digest: Sha256DigestString


class ParticipantControlContextAssetModel(_ControlContextModel):
    """An immutable descriptor; its content remains in consumer-controlled storage."""

    _CONTRACT_ID = "asset"
    schema_version: Literal["participant-control-context-asset/v1"]
    asset_id: ContextReference
    asset_version: ContextReference
    kind: Literal["instruction", "directive", "policy", "guidance"]
    content: ExperimentArtifactRefModel
    participant_addresses: ContextReferences = Field(default_factory=list)
    role_refs: ContextReferences = Field(default_factory=list)
    publication_authority_ref: ContextReference
    retention_policy_ref: ContextReference
    provenance_refs: ContextReferences = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_asset(self) -> ParticipantControlContextAssetModel:
        if not self.participant_addresses and not self.role_refs:
            raise ValueError("control-context applicability is required")
        for values in (self.participant_addresses, self.role_refs, self.provenance_refs):
            if len(values) != len(set(values)):
                raise ValueError("control-context references must be unique")
        validate_safe_absolute_uri(self.content.uri, field_name="control-context content locator")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = super().__get_pydantic_json_schema__(core_schema, handler)
        schema["anyOf"] = [
            {"required": [name], "properties": {name: {"minItems": 1}}}
            for name in ("participant_addresses", "role_refs")
        ]
        return schema


class ParticipantControlContextRecordModel(_ControlContextModel):
    """One version selection, with disclosure and actual delivery kept separate."""

    _CONTRACT_ID = "record"
    schema_version: Literal["participant-control-context-record/v1"]
    record_id: ContextReference
    selection_ref: ContextReference
    scope_ref: ContextReference
    run_id: ContextReference
    participant_address: ContextReference
    episode_id: ContextReference
    episode_generation: StrictInt = Field(ge=0)
    audience_scope_ref: ContextReference
    asset_ref: ParticipantControlContextAssetReferenceModel
    selected_by_ref: ContextReference
    selection_authority_ref: ContextReference
    selection_cut: ParticipantDecisionSurfaceStateCutModel
    record_cut: ParticipantDecisionSurfaceStateCutModel
    disposition: Literal["selected", "withheld", "disclosed", "delivered"]
    withholding_authority_ref: ContextReference | None = None
    surface_id: ContextReference | None = None
    item_ref: ContextReference | None = None
    delivery_ref: ContextReference | None = None
    evidence_refs: ContextReferences = Field(min_length=1)
    provenance_refs: ContextReferences = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_disposition(self) -> ParticipantControlContextRecordModel:
        for name in ("withholding_authority_ref", "surface_id", "item_ref", "delivery_ref"):
            if (getattr(self, name) is not None) != (name in self._required_disposition_fields(self.disposition)):
                raise ValueError("control-context disposition and evidence fields disagree")
        for values in (self.evidence_refs, self.provenance_refs):
            if len(values) != len(set(values)):
                raise ValueError("control-context evidence references must be unique")
        return self

    @staticmethod
    def _required_disposition_fields(disposition: str) -> set[str]:
        return {
            "selected": set(),
            "withheld": {"withholding_authority_ref"},
            "disclosed": {"surface_id", "item_ref"},
            "delivered": {"surface_id", "item_ref", "delivery_ref"},
        }[disposition]

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = super().__get_pydantic_json_schema__(core_schema, handler)
        schema["allOf"] = [
            {
                "if": {"properties": {"disposition": {"const": state}}, "required": ["disposition"]},
                "then": {
                    "required": sorted(cls._required_disposition_fields(state)),
                    "properties": {
                        name: {"not": {"type": "null"}}
                        if name in cls._required_disposition_fields(state)
                        else {"type": "null"}
                        for name in ("withholding_authority_ref", "surface_id", "item_ref", "delivery_ref")
                    },
                },
            }
            for state in ("selected", "withheld", "disclosed", "delivered")
        ]
        return schema


class ParticipantControlContextChangeModel(_ControlContextModel):
    """An authorized lifecycle claim, independent of per-participant selection."""

    _CONTRACT_ID = "change"
    schema_version: Literal["participant-control-context-change/v1"]
    change_id: ContextReference
    scope_ref: ContextReference
    asset_ref: ParticipantControlContextAssetReferenceModel
    operation: Literal["publish", "replace", "withdraw"]
    successor_ref: ParticipantControlContextAssetReferenceModel | None = None
    actor_ref: ContextReference
    authority_ref: ContextReference
    effective_cut: ParticipantDecisionSurfaceStateCutModel
    reason_ref: ContextReference
    evidence_refs: ContextReferences = Field(min_length=1)
    provenance_refs: ContextReferences = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_change(self) -> ParticipantControlContextChangeModel:
        if (self.successor_ref is not None) != (self.operation == "replace"):
            raise ValueError("only replacement requires a successor")
        if self.successor_ref is not None and (
            self.successor_ref.asset_id != self.asset_ref.asset_id
            or self.successor_ref.asset_version == self.asset_ref.asset_version
        ):
            raise ValueError("replacement requires a distinct version of the same asset")
        for values in (self.evidence_refs, self.provenance_refs):
            if len(values) != len(set(values)):
                raise ValueError("control-context change references must be unique")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = super().__get_pydantic_json_schema__(core_schema, handler)
        schema["allOf"] = [
            {
                "if": {"properties": {"operation": {"const": "replace"}}, "required": ["operation"]},
                "then": {"required": ["successor_ref"], "properties": {"successor_ref": {"not": {"type": "null"}}}},
                "else": {"properties": {"successor_ref": {"type": "null"}}},
            }
        ]
        return schema
