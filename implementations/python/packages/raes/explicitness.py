"""SEM-218 explicitness classification for authored SDL declarations."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel

from ._base import VARIABLE_TOKEN_RE, extract_variable_name
from .variables import Variable

__all__ = [
    "ExplicitnessClass",
    "ExplicitnessProvenance",
    "ExplicitnessRecord",
    "ExplicitnessResult",
    "classify_authoring_specificity",
    "classify_model_explicitness",
    "classify_scenario_explicitness",
    "derive_instantiated_explicitness",
]

_OPEN_ENUM_SENTINELS = frozenset({"unknown", "other"})
_EXPLICITNESS_ORDER: dict[ExplicitnessClass, int] = {}
_PATH_TOKEN_RE = re.compile(r"[^.\[\]]+|\[\d+\]")


class ExplicitnessClass(str, Enum):
    """SEM-218 author-intent class for a declaration."""

    EXACT = "exact"
    CONSTRAINED = "constrained"
    OPEN = "open"


class ExplicitnessProvenance(str, Enum):
    """Where the classified value came from in the SDL lifecycle."""

    AUTHOR_DECLARED = "author-declared"
    PROCESSOR_DERIVED = "processor-derived"
    BACKEND_REALIZED = "backend-realized"


_EXPLICITNESS_ORDER.update(
    {
        ExplicitnessClass.OPEN: 0,
        ExplicitnessClass.CONSTRAINED: 1,
        ExplicitnessClass.EXACT: 2,
    }
)


@dataclass(frozen=True)
class ExplicitnessRecord:
    """Classification metadata for one SDL model path."""

    path: str
    classification: ExplicitnessClass
    provenance: ExplicitnessProvenance = ExplicitnessProvenance.AUTHOR_DECLARED
    reason: str = ""
    variables: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExplicitnessResult:
    """Classifier result plus non-fatal diagnostics for validation."""

    records: dict[str, ExplicitnessRecord]
    errors: tuple[str, ...] = ()


def classify_scenario_explicitness(scenario: BaseModel) -> ExplicitnessResult:
    """Classify authored SDL declarations on ``scenario``."""

    return classify_model_explicitness(scenario)


def classify_model_explicitness(
    model: BaseModel,
    *,
    variables: dict[str, Variable] | None = None,
) -> ExplicitnessResult:
    """Classify authored declarations on any closed RAES Pydantic model."""

    variables = variables if variables is not None else getattr(model, "variables", {})
    classifier = _ExplicitnessClassifier(variables)
    classifier.visit(model, "")
    return ExplicitnessResult(records=dict(classifier.records), errors=tuple(classifier.errors))


def classify_authoring_specificity(
    model: BaseModel,
    *,
    admitted_open_paths: Iterable[str] = (),
    variables: dict[str, Variable] | None = None,
) -> ExplicitnessResult:
    """Classify DSL-115 specificity with opt-in open/underspecified paths.

    Missing fields are not open by default. A caller must supply the exact
    owning-surface path for any concern whose owning rule explicitly admits an
    open or underspecified form. This records authoring review metadata only;
    it is not backend-realization permission.
    """

    result = classify_model_explicitness(model, variables=variables)
    records = dict(result.records)
    errors = list(result.errors)
    for path in admitted_open_paths:
        normalized_path = path.strip() if isinstance(path, str) else ""
        if not normalized_path:
            errors.append("Cannot classify open specificity for an empty path")
            continue
        if not _path_addresses_model_surface(model, normalized_path):
            errors.append(
                f"Cannot classify open specificity for '{normalized_path}': path does not resolve to a model surface"
            )
            continue
        records.setdefault(
            normalized_path,
            ExplicitnessRecord(
                path=normalized_path,
                classification=ExplicitnessClass.OPEN,
                reason="explicitly admitted open/underspecified concern; not backend-realization permission",
            ),
        )
    return ExplicitnessResult(records=records, errors=tuple(errors))


def derive_instantiated_explicitness(
    raw_scenario: BaseModel,
    instantiated_scenario: BaseModel,
) -> ExplicitnessResult:
    """Derive instantiated explicitness without promoting substitutions to exact."""

    raw_result = classify_scenario_explicitness(raw_scenario)
    instantiated_paths = _authored_paths(instantiated_scenario)
    records: dict[str, ExplicitnessRecord] = {}
    for path, record in raw_result.records.items():
        if path not in instantiated_paths:
            continue
        provenance = (
            ExplicitnessProvenance.PROCESSOR_DERIVED if record.variables else ExplicitnessProvenance.AUTHOR_DECLARED
        )
        reason = record.reason
        if record.variables:
            reason = "parameter/default substitution preserved authored explicitness class"
        records[path] = ExplicitnessRecord(
            path=record.path,
            classification=record.classification,
            provenance=provenance,
            reason=reason,
            variables=record.variables,
        )
    return ExplicitnessResult(records=records, errors=raw_result.errors)


class _ExplicitnessClassifier:
    def __init__(self, variables: dict[str, Variable]) -> None:
        self._variables = variables
        self.records: dict[str, ExplicitnessRecord] = {}
        self.errors: list[str] = []

    def visit(self, value: object, path: str) -> ExplicitnessRecord | None:
        record: ExplicitnessRecord | None = None
        if isinstance(value, BaseModel):
            record = self._visit_model(value, path)
        elif isinstance(value, dict):
            record = self._visit_mapping(value, path)
        elif isinstance(value, list):
            record = self._visit_sequence(value, path)
        elif path:
            record = self._record_scalar(value, path)
        return record

    def _visit_model(self, model: BaseModel, path: str) -> ExplicitnessRecord | None:
        child_records: list[ExplicitnessRecord] = []
        fields_set = set(model.model_fields_set)
        exact_fields_hook = getattr(model, "explicitness_exact_fields", None)
        exact_fields = exact_fields_hook() if callable(exact_fields_hook) else frozenset()
        for field_name in model.__class__.model_fields:
            if field_name not in fields_set:
                continue
            child_path = f"{path}.{field_name}" if path else field_name
            child_record = self.visit(getattr(model, field_name), child_path)
            if field_name in exact_fields and child_record is not None and not child_record.variables:
                child_record = ExplicitnessRecord(
                    path=child_path,
                    classification=ExplicitnessClass.EXACT,
                    reason="owning model supplies exact extension identity",
                )
                self.records[child_path] = child_record
            if child_record is not None:
                child_records.append(child_record)
        return self._record_container(path, child_records)

    def _visit_mapping(self, value: dict[object, object], path: str) -> ExplicitnessRecord | None:
        child_records: list[ExplicitnessRecord] = []
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            child_record = self.visit(child, child_path)
            if child_record is not None:
                child_records.append(child_record)
        return self._record_container(path, child_records)

    def _visit_sequence(self, value: list[object], path: str) -> ExplicitnessRecord | None:
        child_records: list[ExplicitnessRecord] = []
        for index, child in enumerate(value):
            child_record = self.visit(child, f"{path}[{index}]")
            if child_record is not None:
                child_records.append(child_record)
        return self._record_container(path, child_records)

    def _record_container(
        self,
        path: str,
        child_records: list[ExplicitnessRecord],
    ) -> ExplicitnessRecord | None:
        if not path:
            return None
        classification = _weakest_class(record.classification for record in child_records)
        variables = tuple(sorted({name for record in child_records for name in record.variables}))
        record = ExplicitnessRecord(
            path=path,
            classification=classification,
            reason="derived from child declarations" if child_records else "authored empty structure",
            variables=variables,
        )
        self.records[path] = record
        return record

    def _record_scalar(self, value: object, path: str) -> ExplicitnessRecord:
        variable_names = _variable_names(value)
        if variable_names:
            missing = tuple(name for name in variable_names if name not in self._variables)
            if missing:
                self.errors.append(
                    f"Cannot classify explicitness for '{path}': undefined variable(s) {', '.join(missing)}"
                )
            record = ExplicitnessRecord(
                path=path,
                classification=ExplicitnessClass.CONSTRAINED,
                reason=_variable_constraint_reason(variable_names, self._variables),
                variables=variable_names,
            )
            self.records[path] = record
            return record

        classification = ExplicitnessClass.OPEN if _is_open_enum_sentinel(value) else ExplicitnessClass.EXACT
        reason = "open taxonomy sentinel" if classification is ExplicitnessClass.OPEN else "authored concrete value"
        record = ExplicitnessRecord(path=path, classification=classification, reason=reason)
        self.records[path] = record
        return record


def _variable_names(value: object) -> tuple[str, ...]:
    names: list[str] = []
    if isinstance(value, str):
        full_name = extract_variable_name(value)
        if full_name is not None:
            names.append(full_name)
        else:
            names.extend(dict.fromkeys(VARIABLE_TOKEN_RE.findall(value)))
    return tuple(names)


def _variable_constraint_reason(variable_names: tuple[str, ...], variables: dict[str, Variable]) -> str:
    parts: list[str] = []
    for variable_name in variable_names:
        variable = variables.get(variable_name)
        if variable is None:
            parts.append(f"{variable_name}: undefined")
            continue
        if variable.allowed_values:
            parts.append(f"{variable_name}: allowed_values")
        else:
            parts.append(f"{variable_name}: type {variable.type.value}")
    return "; ".join(parts)


def _is_open_enum_sentinel(value: object) -> bool:
    return isinstance(value, Enum) and isinstance(value.value, str) and value.value in _OPEN_ENUM_SENTINELS


def _weakest_class(classes: Iterable[ExplicitnessClass]) -> ExplicitnessClass:
    weakest = ExplicitnessClass.EXACT
    for classification in classes:
        if _EXPLICITNESS_ORDER[classification] < _EXPLICITNESS_ORDER[weakest]:
            weakest = classification
    return weakest


def _authored_paths(value: object) -> set[str]:
    collector = _AuthoredPathCollector()
    collector.visit(value, "")
    return collector.paths


def _path_addresses_model_surface(root: object, path: str) -> bool:
    tokens = _path_tokens(path)
    if not tokens:
        return False

    current = root
    for index, token in enumerate(tokens):
        is_final = index == len(tokens) - 1
        found, current = _resolve_path_token(current, token, allow_unset_model_field=is_final)
        if not found:
            return False
    return True


def _path_tokens(path: str) -> tuple[str | int, ...]:
    tokens: list[str | int] = []
    for raw in _PATH_TOKEN_RE.findall(path):
        tokens.append(int(raw[1:-1]) if raw.startswith("[") else raw)
    return tuple(tokens)


def _resolve_path_token(
    current: object,
    token: str | int,
    *,
    allow_unset_model_field: bool,
) -> tuple[bool, object]:
    resolved: tuple[bool, object] = (False, None)
    if isinstance(token, int):
        resolved = _resolve_sequence_path_token(current, token)
    elif isinstance(current, BaseModel):
        resolved = _resolve_model_path_token(
            current,
            token,
            allow_unset_model_field=allow_unset_model_field,
        )
    elif isinstance(current, Mapping):
        resolved = _resolve_mapping_path_token(current, token)
    return resolved


def _resolve_sequence_path_token(current: object, token: int) -> tuple[bool, object]:
    resolved: tuple[bool, object] = (False, None)
    if isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)) and 0 <= token < len(current):
        resolved = (True, current[token])
    return resolved


def _resolve_model_path_token(
    current: BaseModel,
    token: str,
    *,
    allow_unset_model_field: bool,
) -> tuple[bool, object]:
    resolved: tuple[bool, object] = (False, None)
    if token in type(current).model_fields:
        value = getattr(current, token)
        missing_unset_optional = value is None and token not in current.model_fields_set
        if not missing_unset_optional or allow_unset_model_field:
            resolved = (True, value)
    return resolved


def _resolve_mapping_path_token(current: Mapping[object, object], token: str) -> tuple[bool, object]:
    resolved: tuple[bool, object] = (False, None)
    if token in current:
        resolved = (True, current[token])
    return resolved


class _AuthoredPathCollector:
    def __init__(self) -> None:
        self.paths: set[str] = set()

    def visit(self, value: object, path: str) -> None:
        if path:
            self.paths.add(path)
        if isinstance(value, BaseModel):
            self._visit_model(value, path)
        elif isinstance(value, dict):
            self._visit_mapping(value, path)
        elif isinstance(value, list):
            self._visit_sequence(value, path)

    def _visit_model(self, model: BaseModel, path: str) -> None:
        for field_name in model.__class__.model_fields:
            if field_name not in model.model_fields_set:
                continue
            child_path = f"{path}.{field_name}" if path else field_name
            self.visit(getattr(model, field_name), child_path)

    def _visit_mapping(self, value: dict[object, object], path: str) -> None:
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            self.visit(child, child_path)

    def _visit_sequence(self, value: list[object], path: str) -> None:
        for index, child in enumerate(value):
            self.visit(child, f"{path}[{index}]")
