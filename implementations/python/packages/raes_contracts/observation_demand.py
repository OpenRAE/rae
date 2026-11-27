"""Scoped observation and reporting-demand contracts.

The models in this module select data lifecycle work.  They deliberately do
not describe realization constraints, backend capability, or proof that an
observation occurred.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ._base import ContractModel, NonEmptyString
from .diagnostics import Diagnostic
from .observation_demand_schema import effective_observation_schema
from .realization_structure import (
    semantic_address_contains,
)

OBSERVATION_SCOPE_PROFILE = "recursive-realization-constraint/v1"
SemanticScope = Annotated[str, Field(pattern=r"^(?:/(?:[^~/]|~[01])*)*$", max_length=4096)]


class ObservationPurpose(str, Enum):
    """Authority plane for requested data use."""

    EXPERIMENTAL = "experimental"
    REALIZATION_DESCRIPTION = "realization-description"
    OPERATIONAL = "operational"


class ObservationDemandMode(str, Enum):
    """Selection posture at a named semantic scope."""

    INHERIT = "inherit"
    NONE = "none"
    OPERATIONAL_ONLY = "operational-only"
    SELECTED = "selected"
    EXHAUSTIVE = "exhaustive"


class ObservationLifecycleStage(str, Enum):
    """Independently governed data-lifecycle stages."""

    COLLECTION = "collection"
    RETENTION = "retention"
    EXPORT = "export"


class ObservationLifecycleDecision(str, Enum):
    """One local lifecycle preference or monotone prohibition."""

    INHERIT = "inherit"
    FORBID = "forbid"
    DISABLE = "disable"
    REQUIRE = "require"


class ObservationBasis(str, Enum):
    """Truthful basis requested for a reportable value."""

    BACKEND_SELECTED = "backend-selected"
    OBSERVED = "observed"
    INDEPENDENTLY_VERIFIED = "independently-verified"
    OPERATIONAL = "operational"


class ObservationSelector(ContractModel):
    """Bounded selector over a semantic scope and one data surface."""

    semantic_scope: SemanticScope
    excluded_scopes: tuple[SemanticScope, ...] = Field(default=(), max_length=256)
    component_refs: tuple[NonEmptyString, ...] = Field(default=(), max_length=256)
    data_kind: Literal["field", "stream", "artifact"]
    names: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=256)
    window_refs: tuple[NonEmptyString, ...] = Field(default=(), max_length=256)
    coverage_profile: NonEmptyString | None = None
    max_items: int | None = Field(default=None, ge=1, le=1_000_000)

    @model_validator(mode="after")
    def _validate_unique_values(self) -> ObservationSelector:
        for field_name in ("excluded_scopes", "component_refs", "names", "window_refs"):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"observation selector {field_name} must be unique")
        if any(
            scope == self.semantic_scope or not semantic_address_contains(self.semantic_scope, scope)
            for scope in self.excluded_scopes
        ):
            raise ValueError("observation selector exclusions must be strict descendants of its semantic scope")
        if (self.coverage_profile is None) != (self.max_items is None):
            raise ValueError("observation selector coverage_profile and max_items must be supplied together")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler(core_schema)
        schema = handler.resolve_ref_schema(schema)
        schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {"coverage_profile": {"not": {"type": "null"}}},
                        "required": ["coverage_profile"],
                    },
                    "then": {
                        "properties": {"max_items": {"not": {"type": "null"}}},
                        "required": ["max_items"],
                    },
                },
                {
                    "if": {
                        "properties": {"max_items": {"not": {"type": "null"}}},
                        "required": ["max_items"],
                    },
                    "then": {
                        "properties": {"coverage_profile": {"not": {"type": "null"}}},
                        "required": ["coverage_profile"],
                    },
                },
            ]
        )
        return schema

    @property
    def key(self) -> str:
        """Return a stable credential-free key for collection-boundary lookup."""

        return self.model_dump_json(exclude_none=True)


class ObservationDemandRule(ContractModel):
    """One local scoped preference or independent mandatory requirement."""

    rule_id: NonEmptyString
    scope: SemanticScope
    purpose: ObservationPurpose
    mode: ObservationDemandMode | None = None
    selector: ObservationSelector | None = None
    collection: ObservationLifecycleDecision | None = None
    retention: ObservationLifecycleDecision | None = None
    export: ObservationLifecycleDecision | None = None
    basis: ObservationBasis | None = None
    prohibited_stages: tuple[ObservationLifecycleStage, ...] = Field(default=(), max_length=3)
    redaction: NonEmptyString | None = None
    integrity: NonEmptyString | None = None
    required: bool = False
    authority_ref: NonEmptyString = "author"

    @model_validator(mode="after")
    def _validate_rule(self) -> ObservationDemandRule:
        return validate_observation_demand_rule(self)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler(core_schema)
        schema = handler.resolve_ref_schema(schema)
        schema.setdefault("allOf", []).append(
            {
                "anyOf": [
                    {
                        "required": [field_name],
                        "properties": {field_name: {"not": {"type": "null"}}},
                    }
                    for field_name in (
                        "mode",
                        "selector",
                        "collection",
                        "retention",
                        "export",
                        "basis",
                        "redaction",
                        "integrity",
                    )
                ]
                + [
                    {
                        "required": ["prohibited_stages"],
                        "properties": {"prohibited_stages": {"minItems": 1}},
                    }
                ]
            }
        )
        schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {"properties": {"mode": {"enum": ["selected", "exhaustive"]}}, "required": ["mode"]},
                    "then": {"required": ["selector"], "properties": {"selector": {"not": {"type": "null"}}}},
                },
                {
                    "if": {"properties": {"mode": {"const": "exhaustive"}}, "required": ["mode"]},
                    "then": {
                        "required": ["selector"],
                        "properties": {
                            "selector": {
                                "required": ["coverage_profile", "max_items"],
                                "properties": {
                                    "coverage_profile": {"type": "string", "minLength": 1},
                                    "max_items": {"type": "integer", "minimum": 1},
                                },
                            }
                        },
                    },
                },
                {
                    "if": {
                        "properties": {
                            "purpose": {"const": "experimental"},
                            "mode": {"enum": ["selected", "exhaustive"]},
                        },
                        "required": ["purpose", "mode"],
                    },
                    "then": {
                        "required": ["redaction", "integrity"],
                        "properties": {
                            "redaction": {"type": "string", "minLength": 1},
                            "integrity": {"type": "string", "minLength": 1},
                        },
                    },
                },
            ]
        )
        return schema


class ObservationDemandDocument(ContractModel):
    """Versioned scoped demand policy exchanged across authoring and runtime."""

    contract_id: Literal["observation-demand-v1"] = "observation-demand-v1"
    schema_version: Literal["observation-demand/v1"]
    document_id: NonEmptyString
    scope_profile: Literal["recursive-realization-constraint/v1"]
    rules: tuple[ObservationDemandRule, ...] = Field(default=(), max_length=4096)

    @model_validator(mode="after")
    def _validate_unique_rules(self) -> ObservationDemandDocument:
        ids = [rule.rule_id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("observation demand rule ids must be unique")
        return self


class EffectiveObservationDemand(ContractModel):
    """Normalized configuration-bound demand at one semantic scope."""

    scope: SemanticScope
    purpose: ObservationPurpose
    mode: ObservationDemandMode
    selectors: tuple[ObservationSelector, ...] = Field(default=(), max_length=256)
    collection: ObservationLifecycleDecision
    retention: ObservationLifecycleDecision
    export: ObservationLifecycleDecision
    basis: ObservationBasis
    prohibited_stages: tuple[ObservationLifecycleStage, ...] = Field(default=(), max_length=3)
    redaction: NonEmptyString | None = None
    integrity: NonEmptyString | None = None
    required: bool = False
    origins: dict[str, NonEmptyString] = Field(default_factory=dict, max_length=16)

    @model_validator(mode="after")
    def _validate_normal_form(self) -> EffectiveObservationDemand:
        return validate_effective_observation_demand(self)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:

        return effective_observation_schema(handler.resolve_ref_schema(handler(core_schema)))


@dataclass(frozen=True)
class ObservationDemandResolution:
    """Normalized effective demands plus bounded portable diagnostics."""

    effective: tuple[EffectiveObservationDemand, ...]
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not any(diagnostic.is_error for diagnostic in self.diagnostics)


@dataclass(frozen=True)
class ObservationLifecycleItem:
    selector_key: str
    values: tuple[object, ...]
    integrity_ref: str | None = None


@dataclass(frozen=True)
class ObservationLifecycleResult:
    collected: tuple[ObservationLifecycleItem, ...]
    retained: tuple[ObservationLifecycleItem, ...]
    exported: tuple[ObservationLifecycleItem, ...]
    operational_count: int


def observation_selector_has_more_specific_policy(
    demands: Sequence[EffectiveObservationDemand],
    demand: EffectiveObservationDemand,
    selector: ObservationSelector,
) -> bool:
    """Return whether a descendant effective policy partitions a broad selector."""

    selector_depth = selector.semantic_scope.count("/")
    return any(
        candidate is not demand
        and candidate.purpose is demand.purpose
        and candidate.scope.count("/") > selector_depth
        and semantic_address_contains(selector.semantic_scope, candidate.scope)
        and not any(
            excluded == candidate.scope or semantic_address_contains(excluded, candidate.scope)
            for excluded in selector.excluded_scopes
        )
        for candidate in demands
    )


def validate_observation_demand_rule(rule: ObservationDemandRule) -> ObservationDemandRule:
    _require_unique_prohibited_stages(rule)
    _require_declared_policy_axis(rule)
    _require_selector_for_selection(rule)
    _require_bounded_exhaustive_selector(rule)
    _require_experimental_protection(rule)
    return rule


def validate_effective_observation_demand(demand: EffectiveObservationDemand) -> EffectiveObservationDemand:
    _require_effective_mode(demand)
    _require_concrete_lifecycle(demand)
    _require_effective_selection(demand)
    _require_collection_for_later_stages(demand)
    _require_operational_only_lifecycle(demand)
    return demand


def validate_observation_lifecycle_plan(
    resolution: ObservationDemandResolution,
    supported: frozenset[str],
) -> None:
    if not resolution.is_valid:
        raise ValueError("invalid-observation-demand")
    for demand in resolution.effective:
        _validate_effective_lifecycle_plan(demand, resolution.effective, supported)


def _require_unique_prohibited_stages(rule: ObservationDemandRule) -> None:
    if len(rule.prohibited_stages) != len(set(rule.prohibited_stages)):
        raise ValueError("observation demand prohibited_stages must be unique")


def _require_declared_policy_axis(rule: ObservationDemandRule) -> None:
    axes = (
        rule.mode,
        rule.selector,
        rule.collection,
        rule.retention,
        rule.export,
        rule.basis,
        rule.redaction,
        rule.integrity,
    )
    if not any(value is not None for value in axes) and not rule.prohibited_stages:
        raise ValueError("observation demand rule must declare at least one policy axis")


def _require_selector_for_selection(rule: ObservationDemandRule) -> None:
    if rule.mode in {ObservationDemandMode.SELECTED, ObservationDemandMode.EXHAUSTIVE} and rule.selector is None:
        raise ValueError("selected and exhaustive observation demand require a selector")


def _require_bounded_exhaustive_selector(rule: ObservationDemandRule) -> None:
    selector = rule.selector
    if rule.mode is ObservationDemandMode.EXHAUSTIVE and (selector is None or selector.coverage_profile is None):
        raise ValueError("exhaustive observation demand requires named finite coverage")


def _require_experimental_protection(rule: ObservationDemandRule) -> None:
    selecting = rule.mode in {ObservationDemandMode.SELECTED, ObservationDemandMode.EXHAUSTIVE}
    if (
        rule.purpose is ObservationPurpose.EXPERIMENTAL
        and selecting
        and (rule.redaction is None or rule.integrity is None)
    ):
        raise ValueError("selected experimental demand requires redaction and integrity policy")


def _effective_decisions(demand: EffectiveObservationDemand) -> tuple[ObservationLifecycleDecision, ...]:
    return demand.collection, demand.retention, demand.export


def _require_effective_mode(demand: EffectiveObservationDemand) -> None:
    if demand.mode is ObservationDemandMode.INHERIT:
        raise ValueError("effective observation demand cannot retain inherited mode")


def _require_concrete_lifecycle(demand: EffectiveObservationDemand) -> None:
    invalid = {ObservationLifecycleDecision.INHERIT, ObservationLifecycleDecision.FORBID}
    if any(value in invalid for value in _effective_decisions(demand)):
        raise ValueError("effective observation demand must contain concrete lifecycle decisions")


def _require_effective_selection(demand: EffectiveObservationDemand) -> None:
    decisions = _effective_decisions(demand)
    if demand.mode is ObservationDemandMode.NONE and (
        demand.selectors or any(value is ObservationLifecycleDecision.REQUIRE for value in decisions)
    ):
        raise ValueError("none observation demand cannot select or process data")
    selecting = demand.mode in {ObservationDemandMode.SELECTED, ObservationDemandMode.EXHAUSTIVE}
    if selecting and not demand.selectors:
        raise ValueError("selecting observation demand requires selectors")
    if demand.mode is ObservationDemandMode.EXHAUSTIVE and any(
        selector.coverage_profile is None or selector.max_items is None for selector in demand.selectors
    ):
        raise ValueError("exhaustive observation demand requires named finite coverage")


def _require_collection_for_later_stages(demand: EffectiveObservationDemand) -> None:
    later_required = ObservationLifecycleDecision.REQUIRE in (demand.retention, demand.export)
    if later_required and demand.collection is not ObservationLifecycleDecision.REQUIRE:
        raise ValueError("retention and export require collection")


def _require_operational_only_lifecycle(demand: EffectiveObservationDemand) -> None:
    invalid = (
        demand.purpose is not ObservationPurpose.OPERATIONAL
        or demand.retention is ObservationLifecycleDecision.REQUIRE
        or demand.export is ObservationLifecycleDecision.REQUIRE
    )
    if demand.mode is ObservationDemandMode.OPERATIONAL_ONLY and invalid:
        raise ValueError("operational-only demand cannot become retained or exported study data")


def _required_stage_is_prohibited(demand: EffectiveObservationDemand) -> bool:
    decisions = {
        ObservationLifecycleStage.COLLECTION: demand.collection,
        ObservationLifecycleStage.RETENTION: demand.retention,
        ObservationLifecycleStage.EXPORT: demand.export,
    }
    return any(
        decision is ObservationLifecycleDecision.REQUIRE and stage in demand.prohibited_stages
        for stage, decision in decisions.items()
    )


def _validate_effective_lifecycle_plan(
    demand: EffectiveObservationDemand,
    demands: Sequence[EffectiveObservationDemand],
    supported: frozenset[str],
) -> None:
    if _required_stage_is_prohibited(demand):
        raise ValueError("required-prohibited-conflict")
    if demand.collection is not ObservationLifecycleDecision.REQUIRE:
        return
    for selector in demand.selectors:
        if selector.key not in supported and demand.required:
            raise ValueError("unsupported-required-observation")
        if demand.required and observation_selector_has_more_specific_policy(demands, demand, selector):
            raise ValueError("required-observation-overlaps-more-specific-policy")


__all__ = [
    "EffectiveObservationDemand",
    "OBSERVATION_SCOPE_PROFILE",
    "ObservationBasis",
    "ObservationDemandDocument",
    "ObservationDemandMode",
    "ObservationDemandResolution",
    "ObservationDemandRule",
    "ObservationLifecycleDecision",
    "ObservationLifecycleItem",
    "ObservationLifecycleResult",
    "ObservationLifecycleStage",
    "ObservationPurpose",
    "ObservationSelector",
    "observation_selector_has_more_specific_policy",
    "validate_effective_observation_demand",
    "validate_observation_demand_rule",
    "validate_observation_lifecycle_plan",
]
