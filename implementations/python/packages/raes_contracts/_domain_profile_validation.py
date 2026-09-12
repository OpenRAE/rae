"""Bounded inert structural validation for domain-profile data."""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from jsonschema.protocols import Validator
from referencing.exceptions import Unresolvable

from ._domain_profile_contracts import (
    DomainProfileAdmissionOutcome,
    DomainProfileBindingModel,
    DomainProfileDefinitionModel,
    DomainProfileLimitsModel,
    DomainProfileSupportDeclarationModel,
)
from ._domain_profile_schema_registry import profile_schema_registry
from .json_ingress import parse_bounded_json_object

SAFE_DOMAIN_PROFILE_SCHEMA_KEYWORDS = tuple(
    sorted(
        {
            "$anchor",
            "$comment",
            "$defs",
            "$id",
            "$ref",
            "$schema",
            "$vocabulary",
            "additionalProperties",
            "allOf",
            "anyOf",
            "const",
            "contains",
            "default",
            "dependentRequired",
            "dependentSchemas",
            "deprecated",
            "description",
            "else",
            "enum",
            "examples",
            "exclusiveMaximum",
            "exclusiveMinimum",
            "if",
            "items",
            "maxContains",
            "maxItems",
            "maxLength",
            "maxProperties",
            "maximum",
            "minContains",
            "minItems",
            "minLength",
            "minProperties",
            "minimum",
            "multipleOf",
            "not",
            "oneOf",
            "prefixItems",
            "properties",
            "propertyNames",
            "readOnly",
            "required",
            "then",
            "title",
            "type",
            "writeOnly",
        }
    )
)

_SCHEMA_MAP_CHILDREN = frozenset({"$defs", "dependentSchemas", "properties"})
_SCHEMA_SINGLE_CHILDREN = frozenset(
    {"additionalProperties", "contains", "else", "if", "items", "not", "propertyNames", "then"}
)
_SCHEMA_SEQUENCE_CHILDREN = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})


class _ProfileAdmissionError(ValueError):
    def __init__(self, outcome: DomainProfileAdmissionOutcome, message: str) -> None:
        self.outcome = outcome
        super().__init__(message)


@dataclass(slots=True)
class _InspectionBudget:
    limits: DomainProfileLimitsModel
    nodes: int = 0
    scalar_bytes: int = 0
    references: int = 0

    def node(self, depth: int) -> None:
        self.nodes += 1
        if self.nodes > self.limits.max_nodes or depth > self.limits.max_depth:
            raise _ProfileAdmissionError(
                DomainProfileAdmissionOutcome.LIMIT_EXCEEDED,
                "domain profile input exceeds the configured node or depth limit",
            )

    def scalar(self, value: object) -> None:
        if isinstance(value, str):
            self.scalar_bytes += len(value.encode("utf-8"))
        elif isinstance(value, int) and not isinstance(value, bool):
            self.scalar_bytes += max(1, (value.bit_length() + 7) // 8)
        else:
            self.scalar_bytes += 1
        if self.scalar_bytes > self.limits.max_scalar_bytes:
            raise _ProfileAdmissionError(
                DomainProfileAdmissionOutcome.LIMIT_EXCEEDED,
                "domain profile input exceeds the configured scalar limit",
            )

    def reference(self) -> None:
        self.references += 1
        if self.references > self.limits.max_references:
            raise _ProfileAdmissionError(
                DomainProfileAdmissionOutcome.LIMIT_EXCEEDED,
                "domain profile schema exceeds the configured reference limit",
            )


@dataclass(slots=True)
class _EvaluationBudget:
    limit: int
    evaluations: int = 0

    def consume(self, amount: int = 1) -> None:
        self.evaluations += amount
        if self.evaluations > self.limit:
            raise _ProfileAdmissionError(
                DomainProfileAdmissionOutcome.LIMIT_EXCEEDED,
                "domain profile validation exceeds the configured evaluation limit",
            )


class _KeywordValidator(Protocol):
    def __call__(
        self,
        validator: Validator,
        keyword_value: object,
        instance: object,
        schema: object,
    ) -> Iterable[object]: ...


def _json_comparison_size(value: object) -> int:
    if isinstance(value, dict):
        return 1 + len(value) + sum(_json_comparison_size(item) for item in value.values())
    if isinstance(value, list | tuple):
        return 1 + sum(_json_comparison_size(item) for item in value)
    return 1


def _enum_evaluation_cost(candidates: list[object], instance: object) -> int:
    instance_size = _json_comparison_size(instance)
    return max(
        1,
        len(candidates) * instance_size + sum(_json_comparison_size(candidate) for candidate in candidates),
    )


def _unique_items_evaluation_cost(instance: list[object]) -> int:
    largest_item = max((_json_comparison_size(item) for item in instance), default=1)
    pair_count = len(instance) * (len(instance) - 1) // 2
    return max(1, pair_count * largest_item * 2)


def _keyword_evaluation_cost(keyword: str, keyword_value: object, instance: object) -> int:
    cost = 1
    if keyword == "enum" and isinstance(keyword_value, list):
        cost = _enum_evaluation_cost(keyword_value, instance)
    elif keyword == "const":
        cost = _json_comparison_size(instance) + _json_comparison_size(keyword_value)
    elif keyword == "uniqueItems" and keyword_value is True and isinstance(instance, list):
        cost = _unique_items_evaluation_cost(instance)
    return cost


def _wrap_keyword_validator(
    keyword: str,
    validate: _KeywordValidator,
    budget: _EvaluationBudget,
) -> _KeywordValidator:
    def budgeted_validator(
        validator: Validator,
        keyword_value: object,
        instance: object,
        schema: object,
    ) -> Iterator[object]:
        budget.consume(_keyword_evaluation_cost(keyword, keyword_value, instance))
        yield from validate(validator, keyword_value, instance, schema)

    return budgeted_validator


def _budgeted_validator_class(base_validator: type[Validator], budget: _EvaluationBudget) -> type[Validator]:
    from jsonschema import validators

    keyword_validators = cast(Mapping[str, _KeywordValidator], base_validator.VALIDATORS)
    extended = validators.extend(
        base_validator,
        {
            keyword: _wrap_keyword_validator(keyword, validate, budget)
            for keyword, validate in keyword_validators.items()
        },
    )
    return cast(type[Validator], extended)


def _inspect_json_value(value: object, budget: _InspectionBudget, depth: int = 0) -> None:
    budget.node(depth)
    if value is None or isinstance(value, (str, bool, int)):
        budget.scalar(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise _ProfileAdmissionError(
                DomainProfileAdmissionOutcome.VALUE_INVALID,
                "domain profile data contains a non-finite number",
            )
        budget.scalar(value)
    elif isinstance(value, list | tuple):
        for item in value:
            _inspect_json_value(item, budget, depth + 1)
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise _ProfileAdmissionError(
                    DomainProfileAdmissionOutcome.VALUE_INVALID,
                    "domain profile data contains a non-string member name",
                )
            budget.scalar(key)
            _inspect_json_value(item, budget, depth + 1)
    else:
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.VALUE_INVALID,
            "domain profile data contains a non-JSON value",
        )


def _resolve_local_schema_reference(root: dict[str, object], reference: str) -> object:
    if not reference.startswith("#/"):
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.SCHEMA_INVALID,
            "domain profile schemas may use only local JSON Pointer references",
        )
    try:
        return profile_schema_registry(root).resolver(str(root["$id"])).lookup(reference).contents
    except Unresolvable as exc:
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.SCHEMA_INVALID,
            "domain profile schema contains an unresolved local reference",
        ) from exc


@dataclass(slots=True)
class _SchemaInspection:
    root: dict[str, object]
    budget: _InspectionBudget
    used_keywords: set[str]


def _validate_schema_keyword(keyword: str, value: object) -> None:
    if keyword not in SAFE_DOMAIN_PROFILE_SCHEMA_KEYWORDS:
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.UNSUPPORTED_KEYWORD,
            "domain profile schema uses a keyword outside the admitted safe subset",
        )
    if keyword == "enum" and isinstance(value, list) and any(isinstance(candidate, dict | list) for candidate in value):
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.UNSUPPORTED_KEYWORD,
            "domain profile schemas may use enum only with scalar values",
        )
    if keyword == "const" and isinstance(value, dict | list):
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.UNSUPPORTED_KEYWORD,
            "domain profile schemas may use const only with a scalar value",
        )


def _inspect_schema_reference(
    value: object,
    inspection: _SchemaInspection,
    depth: int,
    active_references: frozenset[str],
) -> None:
    if not isinstance(value, str):
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.SCHEMA_INVALID,
            "domain profile schema reference must be a string",
        )
    inspection.budget.reference()
    if value in active_references:
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.SCHEMA_INVALID,
            "recursive domain profile schemas are not admitted",
        )
    target = _resolve_local_schema_reference(inspection.root, value)
    _inspect_schema(
        target,
        inspection=inspection,
        depth=depth + 1,
        active_references=active_references | {value},
    )


def _inspect_schema_map(
    value: object,
    inspection: _SchemaInspection,
    depth: int,
    active_references: frozenset[str],
) -> None:
    if not isinstance(value, dict):
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.SCHEMA_INVALID,
            "domain profile schema map keyword must contain an object",
        )
    for child in value.values():
        _inspect_schema(
            child,
            inspection=inspection,
            depth=depth + 1,
            active_references=active_references,
        )


def _inspect_schema_sequence(
    value: object,
    inspection: _SchemaInspection,
    depth: int,
    active_references: frozenset[str],
) -> None:
    if not isinstance(value, list):
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.SCHEMA_INVALID,
            "domain profile schema sequence keyword must contain an array",
        )
    for child in value:
        _inspect_schema(
            child,
            inspection=inspection,
            depth=depth + 1,
            active_references=active_references,
        )


def _inspect_schema_child(
    keyword: str,
    value: object,
    inspection: _SchemaInspection,
    depth: int,
    active_references: frozenset[str],
) -> None:
    if keyword == "$ref":
        _inspect_schema_reference(value, inspection, depth, active_references)
    elif keyword in _SCHEMA_MAP_CHILDREN:
        _inspect_schema_map(value, inspection, depth, active_references)
    elif keyword in _SCHEMA_SINGLE_CHILDREN:
        _inspect_schema(
            value,
            inspection=inspection,
            depth=depth + 1,
            active_references=active_references,
        )
    elif keyword in _SCHEMA_SEQUENCE_CHILDREN:
        _inspect_schema_sequence(value, inspection, depth, active_references)


def _inspect_schema(
    schema: object,
    *,
    inspection: _SchemaInspection,
    depth: int = 0,
    active_references: frozenset[str] = frozenset(),
) -> None:
    inspection.budget.node(depth)
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.SCHEMA_INVALID,
            "domain profile schema contains a non-schema child",
        )
    if schema is not inspection.root and ("$id" in schema or "$schema" in schema):
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.SCHEMA_INVALID,
            "domain profile resource identities and dialects are root-only",
        )
    for keyword, value in schema.items():
        _validate_schema_keyword(keyword, value)
        inspection.used_keywords.add(keyword)
        _inspect_schema_child(keyword, value, inspection, depth, active_references)


def _has_validation_error(validator: Validator, value: object) -> bool:
    try:
        return next(validator.iter_errors(value), None) is not None
    except Unresolvable as exc:
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.SCHEMA_INVALID,
            "domain profile schema reference cannot be resolved locally",
        ) from exc


def _validate_structural_value(
    binding: DomainProfileBindingModel,
    definition: DomainProfileDefinitionModel,
    support: DomainProfileSupportDeclarationModel,
    limits: DomainProfileLimitsModel,
) -> None:
    from jsonschema import Draft202012Validator

    profile_schema = definition.profile_schema
    if profile_schema.dialect not in support.supported_schema_dialects:
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.UNSUPPORTED_VOCABULARY,
            "the selected schema dialect is unsupported",
        )
    if not set(profile_schema.required_vocabularies) <= set(support.supported_vocabularies):
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.UNSUPPORTED_VOCABULARY,
            "a required schema vocabulary is unsupported",
        )

    schema_budget = _InspectionBudget(limits)
    _inspect_json_value(profile_schema.schema_document, schema_budget)
    used_keywords: set[str] = set()
    schema_walk_budget = _InspectionBudget(limits)
    _inspect_schema(
        profile_schema.schema_document,
        inspection=_SchemaInspection(
            root=profile_schema.schema_document,
            budget=schema_walk_budget,
            used_keywords=used_keywords,
        ),
    )
    if not used_keywords <= set(support.supported_schema_keywords):
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.UNSUPPORTED_KEYWORD,
            "the local validator support declaration omits a used schema keyword",
        )

    value_budget = _InspectionBudget(limits)
    _inspect_json_value(binding.value, value_budget)
    if schema_walk_budget.nodes * value_budget.nodes > limits.max_evaluations:
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.LIMIT_EXCEEDED,
            "domain profile validation exceeds the configured evaluation limit",
        )
    evaluation_budget = _EvaluationBudget(limits.max_evaluations)
    budgeted_validator = _budgeted_validator_class(Draft202012Validator, evaluation_budget)
    schema_validator = budgeted_validator(
        schema=Draft202012Validator.META_SCHEMA,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
        registry=profile_schema_registry(),
    )
    if _has_validation_error(schema_validator, profile_schema.schema_document):
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.SCHEMA_INVALID,
            "domain profile schema failed Draft 2020-12 validation",
        )
    validator = budgeted_validator(
        profile_schema.schema_document, registry=profile_schema_registry(profile_schema.schema_document)
    )
    if _has_validation_error(validator, binding.value):
        raise _ProfileAdmissionError(
            DomainProfileAdmissionOutcome.VALUE_INVALID,
            "domain profile value failed structural validation",
        )


def parse_domain_profile_binding(
    source: str | bytes | bytearray,
    *,
    max_bytes: int = 1_048_576,
    limits: DomainProfileLimitsModel | None = None,
) -> DomainProfileBindingModel:
    """Parse one bounded binding without duplicate members or implicit I/O."""

    selected_limits = limits or DomainProfileLimitsModel()
    payload = parse_bounded_json_object(source, max_bytes=max_bytes)
    _inspect_json_value(payload, _InspectionBudget(selected_limits))
    return DomainProfileBindingModel.model_validate(payload)
