"""Experiment-owned permission and immutable lineage for fresh trial allocation."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .base import ContractModel, NonEmptyString, PrefixedDigestString
from .schema_invariants import add_raes_invariant

ReplacementOrdinal = Annotated[int, Field(strict=True, ge=1, le=1000)]


class TrialReplacementPolicyModel(ContractModel):
    """Additional trials per original allocation slot, never an attempt budget."""

    schema_version: Literal["trial-replacement-policy/v1"] = "trial-replacement-policy/v1"
    max_replacements: Annotated[int, Field(strict=True, ge=0, le=1000)]
    replace_on: list[Literal["failed", "invalidated"]] = Field(max_length=2, json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def _validate_policy(self) -> Self:
        if len(self.replace_on) != len(set(self.replace_on)):
            raise ValueError("replacement triggers must be unique")
        if bool(self.max_replacements) != bool(self.replace_on):
            raise ValueError("positive replacement limit requires triggers; zero requires no triggers")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        schema.setdefault("allOf", []).append(
            {
                "if": {"properties": {"max_replacements": {"const": 0}}, "required": ["max_replacements"]},
                "then": {"properties": {"replace_on": {"maxItems": 0}}},
                "else": {"properties": {"replace_on": {"minItems": 1}}},
            }
        )
        add_raes_invariant(
            schema,
            "trial-replacement-policy-explicit-and-bounded",
            "Replacement triggers are unique; a positive additional-trial bound requires selected triggers, "
            "and zero requires none. Omission supplies no allocation permission.",
            validator="raes_contracts.contracts.trial_replacement.TrialReplacementPolicyModel._validate_policy",
            inputs=[
                {"contract_id": "experiment-authoring-input-v1", "instance_path": "#/run_plan/replacement_policy"},
                {"contract_id": "admitted-trial-plan-v1", "instance_path": "#/replacement_policy"},
            ],
        )
        return schema


class TrialReplacementOriginModel(ContractModel):
    """Acyclic child-to-parent linkage; original sealed plans are never edited."""

    root_plan_id: NonEmptyString
    root_plan_digest: PrefixedDigestString
    root_entry_id: NonEmptyString
    ordinal: ReplacementOrdinal
    parent_plan_id: NonEmptyString
    parent_plan_digest: PrefixedDigestString
    parent_entry_id: NonEmptyString
    parent_run_id: NonEmptyString
    parent_run_version: NonEmptyString
    parent_run_digest: PrefixedDigestString
    cleanup_receipt_ref: NonEmptyString


__all__ = ["TrialReplacementOriginModel", "TrialReplacementPolicyModel"]
