"""Scoped observation and reporting-demand contracts.

The models in this module select data lifecycle work.  They deliberately do
not describe realization constraints, backend capability, or proof that an
observation occurred.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ._base import ContractModel, NonEmptyString
from .diagnostics import Diagnostic
from .observation_reporting import AchievedObservationValue, realization_description_report
from .realization_structure import (
    DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
    RealizationConstraintLimits,
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
        if len(self.prohibited_stages) != len(set(self.prohibited_stages)):
            raise ValueError("observation demand prohibited_stages must be unique")
        if (
            not any(
                value is not None
                for value in (
                    self.mode,
                    self.selector,
                    self.collection,
                    self.retention,
                    self.export,
                    self.basis,
                    self.redaction,
                    self.integrity,
                )
            )
            and not self.prohibited_stages
        ):
            raise ValueError("observation demand rule must declare at least one policy axis")
        if self.mode in {ObservationDemandMode.SELECTED, ObservationDemandMode.EXHAUSTIVE} and self.selector is None:
            raise ValueError("selected and exhaustive observation demand require a selector")
        if self.mode is ObservationDemandMode.EXHAUSTIVE and (
            self.selector is None or self.selector.coverage_profile is None
        ):
            raise ValueError("exhaustive observation demand requires named finite coverage")
        if (
            self.purpose is ObservationPurpose.EXPERIMENTAL
            and self.mode in {ObservationDemandMode.SELECTED, ObservationDemandMode.EXHAUSTIVE}
            and (self.redaction is None or self.integrity is None)
        ):
            raise ValueError("selected experimental demand requires redaction and integrity policy")
        return self

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
        if self.mode is ObservationDemandMode.INHERIT:
            raise ValueError("effective observation demand cannot retain inherited mode")
        decisions = (self.collection, self.retention, self.export)
        if any(
            value in {ObservationLifecycleDecision.INHERIT, ObservationLifecycleDecision.FORBID} for value in decisions
        ):
            raise ValueError("effective observation demand must contain concrete lifecycle decisions")
        if self.mode is ObservationDemandMode.NONE and (
            self.selectors or any(value is ObservationLifecycleDecision.REQUIRE for value in decisions)
        ):
            raise ValueError("none observation demand cannot select or process data")
        if self.mode in {ObservationDemandMode.SELECTED, ObservationDemandMode.EXHAUSTIVE} and not self.selectors:
            raise ValueError("selecting observation demand requires selectors")
        if self.mode is ObservationDemandMode.EXHAUSTIVE and any(
            selector.coverage_profile is None or selector.max_items is None for selector in self.selectors
        ):
            raise ValueError("exhaustive observation demand requires named finite coverage")
        if any(value is ObservationLifecycleDecision.REQUIRE for value in (self.retention, self.export)) and (
            self.collection is not ObservationLifecycleDecision.REQUIRE
        ):
            raise ValueError("retention and export require collection")
        if self.mode is ObservationDemandMode.OPERATIONAL_ONLY and (
            self.purpose is not ObservationPurpose.OPERATIONAL
            or self.retention is ObservationLifecycleDecision.REQUIRE
            or self.export is ObservationLifecycleDecision.REQUIRE
        ):
            raise ValueError("operational-only demand cannot become retained or exported study data")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        from .observation_demand_schema import effective_observation_schema

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


def normalize_observation_demands(
    document: ObservationDemandDocument | None,
    *,
    target_scopes: Sequence[str],
    limits: RealizationConstraintLimits = DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
) -> ObservationDemandResolution:
    """Resolve scoped demand without reading data or invoking backend code."""

    from .observation_demand_resolution import resolve_observation_demands

    return resolve_observation_demands(document, target_scopes=target_scopes, limits=limits)


def _validate_lifecycle_plan(
    resolution: ObservationDemandResolution,
    supported: frozenset[str],
) -> None:
    if not resolution.is_valid:
        raise ValueError("invalid-observation-demand")
    for demand in resolution.effective:
        stages = set(demand.prohibited_stages)
        decisions = {
            ObservationLifecycleStage.COLLECTION: demand.collection,
            ObservationLifecycleStage.RETENTION: demand.retention,
            ObservationLifecycleStage.EXPORT: demand.export,
        }
        if any(
            decision is ObservationLifecycleDecision.REQUIRE and stage in stages
            for stage, decision in decisions.items()
        ):
            raise ValueError("required-prohibited-conflict")
        if demand.collection is ObservationLifecycleDecision.REQUIRE:
            for selector in demand.selectors:
                if selector.key not in supported and demand.required:
                    raise ValueError("unsupported-required-observation")
                if demand.required and observation_selector_has_more_specific_policy(
                    resolution.effective,
                    demand,
                    selector,
                ):
                    raise ValueError("required-observation-overlaps-more-specific-policy")


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


def execute_observation_lifecycle(
    resolution: ObservationDemandResolution,
    *,
    producers: Mapping[str, Callable[[], tuple[object, ...]]],
    supported: frozenset[str],
    protector: Callable[[ObservationLifecycleItem, EffectiveObservationDemand], ObservationLifecycleItem] | None = None,
) -> ObservationLifecycleResult:
    """Execute the admitted lifecycle through the canonical contract owner."""

    from .observation_lifecycle import execute_observation_lifecycle as execute

    return execute(resolution, producers=producers, supported=supported, protector=protector)


__all__ = [
    "AchievedObservationValue",
    "EffectiveObservationDemand",
    "ObservationBasis",
    "OBSERVATION_SCOPE_PROFILE",
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
    "execute_observation_lifecycle",
    "normalize_observation_demands",
    "observation_selector_has_more_specific_policy",
    "realization_description_report",
]
