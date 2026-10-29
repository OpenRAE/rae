"""Pure admission of normalized, import-free SDL scenario families."""

from pydantic import BaseModel, ValidationError

from ._declaration_sources import semantic_source_diagnostics
from ._errors import SDLParseError, SDLValidationError
from ._model_diagnostics import _model_parse_error
from .phase_contracts import ExpansionProvenance
from .realization_designation import (
    RealizationConstraintDesignation,
    RealizationDesignation,
    constraint_records,
    designation_records,
)
from .scenario import ExpandedScenario, Scenario
from .validator import SemanticValidator


def _check_omitted_defaults(value: object) -> None:
    """Refuse mutations that an exclude-unset reconstruction would discard."""
    if isinstance(value, BaseModel):
        for name, field in type(value).model_fields.items():
            current = getattr(value, name)
            if name not in value.model_fields_set and current != field.get_default(call_default_factory=True):
                raise SDLParseError("Scenario has a modified omitted default; reparse SDL before family admission")
            _check_omitted_defaults(current)
    elif isinstance(value, dict):
        for current in value.values():
            _check_omitted_defaults(current)
    elif isinstance(value, (list, tuple)):
        for current in value:
            _check_omitted_defaults(current)


def admit_scenario_family(scenario: Scenario) -> ExpandedScenario:
    """Reconstruct and semantically admit an import-free normalized family.

    Parse SDL with ``parse_sdl`` or ``parse_sdl_file`` first. Unresolved imports
    and other document phases are rejected. The returned independent family
    retains source diagnostics, field presence and realization intent. No file,
    network or workspace-policy access occurs.

    Current content is revalidated even if its previous admission flag is set.
    Changes to omitted default fields require reparsing, so serialization cannot
    silently discard them. Re-admit after editing; the result is not immutable.

    Raises:
        SDLParseError: If the phase, imports or current structure are invalid.
        SDLValidationError: If the resulting family has invalid semantics.
    """
    if not isinstance(scenario, Scenario):
        raise SDLParseError("Scenario family admission requires a normalized Scenario")
    if scenario.imports:
        raise SDLParseError("Scenario family admission requires resolved imports; use parse_sdl_file")
    _check_omitted_defaults(scenario)
    sources = scenario.declaration_sources
    ranges = {source.pointer: source.source_range for source in sources.values()}
    try:
        # A model instance or copied admission flag is not structural evidence.
        current = scenario.model_dump(mode="python", by_alias=True, exclude_unset=True, warnings="none")
        original = scenario.realization
        if isinstance(original, RealizationDesignation) and isinstance(original.constraints, (tuple, list)):
            # Preserve excluded migration origins as data, then validate them too.
            for raw, constraint in zip(
                current.get("realization", {}).get("constraints", ()), original.constraints, strict=False
            ):
                if isinstance(raw, dict) and isinstance(constraint, RealizationConstraintDesignation):
                    raw["provenance"] = constraint.provenance
        authored = Scenario.model_validate(current)
        provenance = ExpansionProvenance()
        if authored.realization is not None:
            provenance = ExpansionProvenance(
                realization_designations=designation_records(authored.realization),
                realization_constraints=constraint_records(authored.realization),
            )
        payload = authored.model_dump(
            mode="python", by_alias=True, exclude_unset=True, exclude={"module", "imports", "realization"}
        )
        payload["expansion_provenance"] = provenance.model_dump(mode="python")
        admitted = ExpandedScenario.model_validate(payload)
    except ValidationError as exc:
        raise _model_parse_error(exc, path=None, source_ranges=ranges) from exc
    admitted._set_declaration_sources(sources)
    admitted._set_source_diagnostics(list(scenario.source_diagnostics))
    validator = SemanticValidator(admitted)
    try:
        validator.validate()
    except SDLValidationError as exc:
        semantic_source_diagnostics(exc, admitted)
        raise
    admitted._set_advisories(validator.warnings)
    admitted._set_semantic_validated(True)
    return admitted
