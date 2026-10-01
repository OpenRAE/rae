"""Portable provenance transformations for SDL module composition."""

from __future__ import annotations

from collections.abc import Mapping

from ._errors import SDLParseError
from ._module_symbols import HASHMAP_SECTIONS
from .instantiate import _BoundScenarioResult
from .module_registry import ResolvedModule
from .phase_contracts import (
    CapabilityConstraint,
    ExplicitnessProvenanceRecord,
    ResolvedImportProvenance,
)
from .realization_designation import RealizationConstraintRecord, RealizationDesignationRecord
from .scenario import ImportDecl, ScenarioContent


def _normalized_digest(value: str) -> str:
    return f"sha256:{value.removeprefix('sha256:')}" if value else ""


def prefixed_import_record(
    record: ResolvedImportProvenance,
    namespace: str,
) -> ResolvedImportProvenance:
    payload = record.model_dump(mode="python")
    payload["namespace"] = (namespace, *record.namespace)
    return ResolvedImportProvenance.model_validate(payload)


def resolved_import_record(
    resolved: ResolvedModule,
    *,
    requested: ImportDecl,
    bindings: _BoundScenarioResult,
) -> ResolvedImportProvenance:
    return ResolvedImportProvenance(
        namespace=(requested.namespace,),
        requested_source=requested.normalized_source,
        requested_version=requested.version,
        requested_digest=_normalized_digest(requested.digest),
        module_id=resolved.module_descriptor.id,
        module_version=resolved.module_descriptor.version,
        resolved_source=resolved.resolved_source,
        manifest_digest=_normalized_digest(resolved.manifest_digest),
        content_digest=_normalized_digest(resolved.content_digest),
        export_hash=_normalized_digest(resolved.export_hash),
        signer_id=resolved.signer_id,
        bindings=bindings.bindings,
    )


def prefixed_constraint(
    constraint: CapabilityConstraint,
    *,
    namespace: str,
    symbols: dict[str, dict[str, str] | set[str]],
) -> CapabilityConstraint:
    parts = constraint.field_pointer.split("/")
    if len(parts) < 3:
        raise SDLParseError("Capability constraint does not address a namespaced declaration")
    section_name = parts[1]
    declaration_name = _decode_pointer_segment(parts[2])
    section_symbols = symbols.get(section_name)
    if not isinstance(section_symbols, Mapping) or declaration_name not in section_symbols:
        raise SDLParseError("Capability constraint does not resolve to an imported declaration")
    parts[2] = _encode_pointer_segment(section_symbols[declaration_name])
    payload = constraint.model_dump(mode="python")
    payload.update(
        {
            "field_pointer": "/".join(parts),
            "parameter": (namespace, *constraint.parameter),
        }
    )
    return CapabilityConstraint.model_validate(payload)


def prefixed_explicitness(
    record: ExplicitnessProvenanceRecord,
    *,
    namespace: str,
    imported: ScenarioContent,
    symbols: dict[str, dict[str, str] | set[str]],
) -> ExplicitnessProvenanceRecord:
    payload = record.model_dump(mode="python")
    payload.update(
        {
            "model_path": _prefixed_model_path(record.model_path, imported=imported, symbols=symbols),
            "parameters": tuple((namespace, *parameter) for parameter in record.parameters),
        }
    )
    return ExplicitnessProvenanceRecord.model_validate(payload)


def prefixed_realization_designation(
    record: RealizationDesignationRecord,
    *,
    namespace: str,
    symbols: dict[str, dict[str, str] | set[str]],
) -> RealizationDesignationRecord:
    """Qualify one imported lexical scope through the composition symbol map."""

    return RealizationDesignationRecord(
        namespace=(namespace, *record.namespace),
        field_pointer=prefixed_scope_pointer(record.field_pointer, symbols=symbols),
        posture=record.posture,
    )


def prefixed_scope_pointer(field_pointer: str, *, symbols: dict[str, dict[str, str] | set[str]]) -> str:
    """Qualify a semantic location through the existing composition symbol map."""
    parts = field_pointer.split("/")
    if len(parts) >= 3:
        section_symbols = symbols.get(_decode_pointer_segment(parts[1]))
        declaration_name = _decode_pointer_segment(parts[2])
        if isinstance(section_symbols, Mapping) and declaration_name in section_symbols:
            parts[2] = _encode_pointer_segment(section_symbols[declaration_name])
    return "/".join(parts)


def prefixed_realization_constraint(
    record: RealizationConstraintRecord,
    *,
    namespace: str,
    symbols: dict[str, dict[str, str] | set[str]],
) -> RealizationConstraintRecord:
    """Qualify one imported addressed realization constraint."""

    parts = record.field_pointer.split("/")
    if len(parts) >= 3:
        section_symbols = symbols.get(_decode_pointer_segment(parts[1]))
        declaration_name = _decode_pointer_segment(parts[2])
        if isinstance(section_symbols, Mapping) and declaration_name in section_symbols:
            parts[2] = _encode_pointer_segment(section_symbols[declaration_name])
    return RealizationConstraintRecord(
        namespace=(namespace, *record.namespace),
        field_pointer="/".join(parts),
        concern=record.concern,
        posture=record.posture,
        domain=record.domain,
        provenance=record.provenance,
    )


def _decode_pointer_segment(segment: str) -> str:
    return segment.replace("~1", "/").replace("~0", "~")


def _encode_pointer_segment(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")


def _prefixed_model_path(
    path: str,
    *,
    imported: ScenarioContent,
    symbols: dict[str, dict[str, str] | set[str]],
) -> str:
    prefixed_path = path
    for section_name in HASHMAP_SECTIONS:
        prefix = f"{section_name}."
        if not path.startswith(prefix):
            continue
        section = getattr(imported, section_name, {})
        section_symbols = symbols.get(section_name)
        if isinstance(section, Mapping) and isinstance(section_symbols, Mapping):
            for declaration_name in sorted(section, key=len, reverse=True):
                declaration_path = f"{prefix}{declaration_name}"
                if (
                    path == declaration_path
                    or path.startswith(f"{declaration_path}.")
                    or path.startswith(f"{declaration_path}[")
                ):
                    suffix = path[len(declaration_path) :]
                    prefixed_path = f"{prefix}{section_symbols[declaration_name]}{suffix}"
                    break
        break
    return prefixed_path
