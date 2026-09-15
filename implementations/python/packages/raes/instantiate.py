"""Canonical scenario instantiation.

The SDL parser preserves `${var}` placeholders structurally. This module owns
the repo-level instantiation phase that turns a parsed ``Scenario`` into a
fully concrete ``InstantiatedScenario`` before compilation/runtime planning.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, ValidationError

from ._base import VARIABLE_TOKEN_RE, extract_variable_name
from ._capability_constraints import capture_capability_constraints
from ._errors import SDLInstantiationError, SDLValidationError
from ._identifiers import QualifiedName
from ._mapping_scopes import HASHMAP_SECTIONS
from .canonical import canonical_sdl_digest
from .explicitness import ExplicitnessRecord, derive_instantiated_explicitness
from .phase_contracts import (
    BindingOrigin,
    CapabilityConstraint,
    ExplicitnessProvenanceRecord,
    InstantiationProvenance,
    ParameterBinding,
    SemanticDigest,
    TrialInstantiationProvenance,
)
from .realization_designation import (
    RealizationConstraintRecord,
    RealizationDesignationRecord,
    constraint_records,
    designation_records,
)
from .scenario import ExpandedScenario, InstantiatedScenario, Scenario, ScenarioContent
from .validator import SemanticValidator
from .variables import Variable, VariableType
from .variation import ParameterVariationPoint, VariationPoint

JSONScalar = str | int | float | bool | None
JSONLike = JSONScalar | list["JSONLike"] | dict[str, "JSONLike"]


class _BoundScenarioContent(ScenarioContent):
    """Private structural result of substitution, before public admission."""

    _allows_qualified_declaration_keys: ClassVar[bool] = True
    model_config = ConfigDict(title="SDL Private Bound Content", extra="forbid")
    variables: dict[str, Variable] = Field(default_factory=dict)
    variation_points: dict[str, VariationPoint] = Field(default_factory=dict)


@dataclass(frozen=True)
class _BoundScenarioResult:
    content: _BoundScenarioContent
    bindings: tuple[ParameterBinding, ...]
    capability_constraints: tuple[CapabilityConstraint, ...]
    explicitness: tuple[ExplicitnessProvenanceRecord, ...]
    realization_designations: tuple[RealizationDesignationRecord, ...]
    realization_constraints: tuple[RealizationConstraintRecord, ...]


def _matches_value_type(value: object, variable: Variable) -> bool:
    if variable.type == VariableType.STRING:
        return isinstance(value, str)
    if variable.type == VariableType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if variable.type == VariableType.BOOLEAN:
        return isinstance(value, bool)
    if variable.type == VariableType.NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def _variable_candidate(
    name: str,
    variable: Variable,
    parameters: Mapping[str, JSONLike],
    preserved: set[str],
) -> tuple[JSONLike | None, BindingOrigin | None, str | None]:
    value: JSONLike | None = None
    origin: BindingOrigin | None = None
    error: str | None = None
    if name in preserved:
        if name in parameters:
            error = f"Variable '{name}' is owned by a variation point and cannot be bound during composition."
    elif name in parameters:
        value = parameters[name]
        origin = BindingOrigin.PROVIDED
    elif variable.default is not None:
        value = variable.default
        origin = BindingOrigin.DEFAULT
    elif variable.required:
        error = f"Variable '{name}' is required and has no provided value or default."
    return value, origin, error


def _variable_constraint_error(name: str, value: JSONLike, variable: Variable) -> str | None:
    error: str | None = None
    if not _matches_value_type(value, variable):
        error = f"Variable '{name}' expects type '{variable.type.value}', got {type(value).__name__}."
    elif variable.allowed_values and value not in variable.allowed_values:
        error = f"Variable '{name}' does not satisfy its allowed_values constraint."
    return error


def _resolve_variable_values(
    scenario: Scenario | ExpandedScenario,
    parameters: Mapping[str, JSONLike],
    *,
    preserved: set[str] | None = None,
) -> tuple[dict[str, JSONLike], dict[str, BindingOrigin], list[str]]:
    resolved: dict[str, JSONLike] = {}
    origins: dict[str, BindingOrigin] = {}
    errors: list[str] = []

    preserved = preserved or set()
    for name, variable in scenario.variables.items():
        value, origin, error = _variable_candidate(name, variable, parameters, preserved)
        if error is not None:
            errors.append(error)
            continue
        if origin is None:
            continue
        constraint_error = _variable_constraint_error(name, value, variable)
        if constraint_error is not None:
            errors.append(constraint_error)
            continue
        resolved[name] = value
        origins[name] = origin

    undeclared = sorted(name for name in parameters if name not in scenario.variables)
    for name in undeclared:
        errors.append(f"Instantiation parameter '{name}' is not a declared variable.")

    return resolved, origins, errors


def _substitute_value(
    value: Any,
    *,
    variable_values: Mapping[str, JSONLike],
    unresolved_refs: set[str],
    preserved: set[str] | None = None,
) -> Any:
    preserved = preserved or set()
    if isinstance(value, dict):
        return {
            str(key): _substitute_value(
                nested_value,
                variable_values=variable_values,
                unresolved_refs=unresolved_refs,
                preserved=preserved,
            )
            for key, nested_value in value.items()
        }
    if isinstance(value, list):
        return [
            _substitute_value(
                nested_value,
                variable_values=variable_values,
                unresolved_refs=unresolved_refs,
                preserved=preserved,
            )
            for nested_value in value
        ]
    if not isinstance(value, str):
        return value

    full_variable_name = extract_variable_name(value)
    if full_variable_name is not None:
        if full_variable_name in preserved:
            return value
        if full_variable_name not in variable_values:
            unresolved_refs.add(full_variable_name)
            return value
        return variable_values[full_variable_name]

    def replace_token(match: re.Match[str]) -> str:
        variable_name = match.group(1)
        if variable_name in preserved:
            return match.group(0)
        if variable_name not in variable_values:
            unresolved_refs.add(variable_name)
            return match.group(0)
        return str(variable_values[variable_name])

    return VARIABLE_TOKEN_RE.sub(replace_token, value)


def _portable_explicitness_record(record: ExplicitnessRecord) -> ExplicitnessProvenanceRecord:
    return ExplicitnessProvenanceRecord(
        model_path=record.path,
        classification=record.classification,
        provenance=record.provenance,
        reason=record.reason,
        parameters=tuple((name,) for name in record.variables),
    )


def _safe_model_validation_errors(
    exc: ValidationError,
    *,
    subject: str = "Bound scenario",
) -> list[str]:
    diagnostics: list[str] = []
    for error in exc.errors()[:50]:
        location = "/" + "/".join(str(segment) for segment in error.get("loc", ()))
        error_type = str(error.get("type", "invalid_value"))
        diagnostics.append(f"{subject} is invalid at {location or '/'} ({error_type}).")
    return diagnostics or [f"{subject} failed structural validation."]


def _imported_declaration_prefixes(scenario: ExpandedScenario) -> set[str]:
    imported_namespaces = tuple(record.namespace for record in scenario.expansion_provenance.imports)
    prefixes: set[str] = set()
    for section_name in HASHMAP_SECTIONS:
        for declaration_name in getattr(scenario, section_name):
            parts = QualifiedName.parse(declaration_name).parts
            if any(parts[: len(namespace)] == namespace for namespace in imported_namespaces):
                prefixes.add(f"{section_name}.{declaration_name}")
    return prefixes


def _path_has_prefix(model_path: str, prefixes: set[str]) -> bool:
    return any(
        model_path == prefix or model_path.startswith(prefix + ".") or model_path.startswith(prefix + "[")
        for prefix in prefixes
    )


def _merge_expanded_provenance(
    scenario: ExpandedScenario,
    local_constraints: tuple[CapabilityConstraint, ...],
    explicitness_by_path: dict[str, ExplicitnessProvenanceRecord],
) -> tuple[
    tuple[CapabilityConstraint, ...],
    tuple[RealizationDesignationRecord, ...],
    tuple[RealizationConstraintRecord, ...],
]:
    constraints = (*scenario.expansion_provenance.capability_constraints, *local_constraints)
    imported_prefixes = _imported_declaration_prefixes(scenario)
    portable_paths = {record.model_path for record in scenario.expansion_provenance.explicitness}
    stale_paths = {
        model_path
        for model_path in explicitness_by_path
        if model_path not in portable_paths and _path_has_prefix(model_path, imported_prefixes)
    }
    for model_path in stale_paths:
        del explicitness_by_path[model_path]
    explicitness_by_path.update({record.model_path: record for record in scenario.expansion_provenance.explicitness})
    return (
        constraints,
        scenario.expansion_provenance.realization_designations,
        scenario.expansion_provenance.realization_constraints,
    )


def _bind_scenario_content(
    raw_scenario: Scenario | ExpandedScenario,
    parameters: Mapping[str, JSONLike] | None = None,
    *,
    preserve_variation_variables: bool = False,
) -> _BoundScenarioResult:
    """Bind one already-expanded object without minting a public phase artifact."""

    preserved = (
        {
            point.target.variable
            for point in raw_scenario.variation_points.values()
            if isinstance(point, ParameterVariationPoint)
        }
        if preserve_variation_variables
        else set()
    )
    variable_values, binding_origins, errors = _resolve_variable_values(
        raw_scenario,
        dict(parameters or {}),
        preserved=preserved,
    )
    if errors:
        raise SDLInstantiationError(errors)

    local_constraints = tuple(
        constraint
        for constraint in capture_capability_constraints(raw_scenario)
        if not constraint.parameter or constraint.parameter[0] not in preserved
    )
    raw_payload = raw_scenario.model_dump(mode="python", by_alias=True)
    unresolved_refs: set[str] = set()
    substituted_payload = _substitute_value(
        raw_payload,
        variable_values=variable_values,
        unresolved_refs=unresolved_refs,
        preserved=preserved,
    )
    if unresolved_refs:
        unresolved_list = ", ".join(sorted(unresolved_refs))
        raise SDLInstantiationError(
            [f"Scenario contains unresolved variable references after instantiation: {unresolved_list}."]
        )

    variable_definitions = substituted_payload.get("variables", {})
    substituted_payload["variables"] = {
        name: definition for name, definition in variable_definitions.items() if name in preserved
    }
    for authoring_field in ("imports", "module", "realization", "expansion_provenance"):
        substituted_payload.pop(authoring_field, None)
    try:
        content = _BoundScenarioContent.model_validate(substituted_payload)
    except ValidationError as exc:
        raise SDLInstantiationError(_safe_model_validation_errors(exc)) from exc

    derived = derive_instantiated_explicitness(raw_scenario, content)
    if derived.errors:
        raise SDLInstantiationError(list(derived.errors))
    explicitness_by_path = {
        record.path: _portable_explicitness_record(record)
        for record in derived.records.values()
        if not any(name in preserved for name in record.variables)
    }
    constraints: tuple[CapabilityConstraint, ...] = local_constraints
    realization_designations = (
        designation_records(raw_scenario.realization)
        if isinstance(raw_scenario, Scenario) and raw_scenario.realization is not None
        else ()
    )
    realization_constraints = (
        constraint_records(raw_scenario.realization)
        if isinstance(raw_scenario, Scenario) and raw_scenario.realization is not None
        else ()
    )
    if isinstance(raw_scenario, ExpandedScenario):
        constraints, realization_designations, realization_constraints = _merge_expanded_provenance(
            raw_scenario,
            local_constraints,
            explicitness_by_path,
        )

    return _BoundScenarioResult(
        content=content,
        bindings=tuple(
            ParameterBinding(
                parameter=(name,),
                origin=binding_origins[name],
                value=value,
            )
            for name, value in variable_values.items()
        ),
        capability_constraints=constraints,
        explicitness=tuple(explicitness_by_path.values()),
        realization_designations=realization_designations,
        realization_constraints=realization_constraints,
    )


def _validate_authoring_scenario(scenario: Scenario | ExpandedScenario) -> None:
    if not isinstance(scenario, (Scenario, ExpandedScenario)):
        raise SDLInstantiationError(["Instantiation requires authored SDL; descriptions require explicit derivation."])
    if isinstance(scenario, Scenario) and scenario.imports:
        raise SDLInstantiationError(["Scenario imports must be resolved by file-backed parsing before instantiation."])
    validator = SemanticValidator(scenario)
    try:
        validator.validate()
    except SDLValidationError as exc:
        raise SDLInstantiationError(list(exc.errors)) from exc
    scenario._set_advisories(validator.warnings)
    scenario._set_semantic_validated(True)


def admit_instantiated_scenario(
    artifact: InstantiatedScenario | Mapping[str, object],
) -> InstantiatedScenario:
    """Structurally and semantically admit a portable instantiated artifact."""

    if isinstance(artifact, InstantiatedScenario):
        admitted = artifact
    else:
        try:
            admitted = InstantiatedScenario.model_validate(artifact)
        except ValidationError as exc:
            raise SDLInstantiationError(_safe_model_validation_errors(exc, subject="Instantiated artifact")) from exc
    validator = SemanticValidator(admitted)
    validator.validate()
    admitted._set_advisories(validator.warnings)
    admitted._set_semantic_validated(True)
    return admitted


def instantiate_scenario(
    raw_scenario: Scenario | ExpandedScenario,
    parameters: Mapping[str, JSONLike] | None = None,
    profile: str | None = None,
    *,
    trial_provenance: TrialInstantiationProvenance | None = None,
) -> InstantiatedScenario:
    """Return a fully concrete scenario ready for compilation.

    Instantiation applies parameter values and variable defaults, rejects
    unresolved placeholders, rebuilds the Pydantic model, and reruns semantic
    validation on the concrete result.
    """

    _validate_authoring_scenario(raw_scenario)
    if raw_scenario.variation_points:
        raise SDLInstantiationError(
            [
                "Scenario has unresolved variation points; recorded selection integration is required "
                "before instantiation."
            ]
        )
    authored_digest = canonical_sdl_digest(raw_scenario)
    bound = _bind_scenario_content(raw_scenario, parameters)
    expansion = raw_scenario.expansion_provenance if isinstance(raw_scenario, ExpandedScenario) else None
    provenance = InstantiationProvenance(
        authored_digest=SemanticDigest(**authored_digest.as_dict()),
        selected_profile=profile,
        bindings=bound.bindings,
        imports=expansion.imports if expansion is not None else (),
        capability_constraints=bound.capability_constraints,
        explicitness=bound.explicitness,
        realization_designations=bound.realization_designations,
        realization_constraints=bound.realization_constraints,
        trial=trial_provenance,
    )
    payload = bound.content.model_dump(mode="python", by_alias=True)
    payload.pop("variables", None)
    payload.pop("variation_points", None)
    payload["instantiation_provenance"] = provenance.model_dump(mode="python")

    try:
        instantiated = InstantiatedScenario.model_validate(payload)
    except ValidationError as exc:
        raise SDLInstantiationError(_safe_model_validation_errors(exc)) from exc
    try:
        return admit_instantiated_scenario(instantiated)
    except SDLValidationError as exc:
        raise SDLInstantiationError(list(exc.errors)) from exc
