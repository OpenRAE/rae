"""Namespaced derivation and realization evidence contributed by one import."""

from __future__ import annotations

from .._composition_provenance import (
    prefixed_constraint as _prefixed_constraint,
)
from .._composition_provenance import (
    prefixed_explicitness as _prefixed_explicitness,
)
from .._composition_provenance import (
    prefixed_import_record as _prefixed_import_record,
)
from .._composition_provenance import prefixed_parameter_derivation
from .._composition_provenance import (
    prefixed_realization_constraint as _prefixed_realization_constraint,
)
from .._composition_provenance import (
    prefixed_realization_designation as _prefixed_realization_designation,
)
from .._composition_provenance import (
    resolved_import_record as _resolved_import_record,
)
from .._module_symbols import HASHMAP_SECTIONS as _HASHMAP_SECTIONS
from ..instantiate import _BoundScenarioResult
from ..module_registry import ResolvedModule
from ..phase_contracts import (
    CapabilityConstraint,
    ExpansionProvenance,
    ExplicitnessProvenanceRecord,
    ParameterDerivation,
    ResolvedImportProvenance,
)
from ..realization_designation import RealizationConstraintRecord, RealizationDesignationRecord
from ..scenario import ImportDecl


def import_provenance_additions(
    resolved_import: ResolvedModule,
    import_decl: ImportDecl,
    bound: _BoundScenarioResult,
    inner_provenance: ExpansionProvenance,
    symbols: dict[str, dict[str, str] | set[str]],
) -> tuple[
    list[ResolvedImportProvenance],
    list[CapabilityConstraint],
    list[ParameterDerivation],
    list[ExplicitnessProvenanceRecord],
    list[RealizationDesignationRecord],
    list[RealizationConstraintRecord],
]:
    """Build the namespaced provenance additions contributed by one import."""

    namespace = import_decl.namespace
    import_records: list[ResolvedImportProvenance] = [
        _resolved_import_record(resolved_import, requested=import_decl, bindings=bound)
    ]
    import_records.extend(_prefixed_import_record(record, namespace) for record in inner_provenance.imports)
    capability_constraints = [
        _prefixed_constraint(constraint, namespace=namespace, symbols=symbols)
        for constraint in bound.capability_constraints
    ]
    parameter_derivations = [
        prefixed_parameter_derivation(derivation, namespace=namespace, symbols=symbols)
        for derivation in bound.parameter_derivations
    ]
    explicitness_records = [
        _prefixed_explicitness(record, namespace=namespace, imported=bound.content, symbols=symbols)
        for record in bound.explicitness
        if any(record.model_path.startswith(f"{section_name}.") for section_name in _HASHMAP_SECTIONS)
    ]
    realization_records = [
        _prefixed_realization_designation(record, namespace=namespace, symbols=symbols)
        for record in inner_provenance.realization_designations
    ]
    realization_constraints = [
        _prefixed_realization_constraint(record, namespace=namespace, symbols=symbols)
        for record in inner_provenance.realization_constraints
    ]
    return (
        import_records,
        capability_constraints,
        parameter_derivations,
        explicitness_records,
        realization_records,
        realization_constraints,
    )
