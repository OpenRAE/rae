"""Meaning-preserving migration for historical node-kind syntax."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from raes_contracts.json_pointer import escape_token

from ._errors import (
    SDLParseDiagnostic,
    SDLParseError,
    SDLSourcePosition,
    SDLSourceRange,
)
from ._source_profile import SDLMigrationPolicy


def _source_range(pointer: str, source_ranges: dict[str, SDLSourceRange] | None) -> SDLSourceRange:
    if source_ranges is not None and pointer in source_ranges:
        return source_ranges[pointer]
    position = SDLSourcePosition(1, 1)
    return SDLSourceRange(start=position, end=position)


def _legacy_vm_diagnostic(
    *,
    pointer: str,
    path: Path | None,
    source_ranges: dict[str, SDLSourceRange] | None,
    severity: str,
) -> SDLParseDiagnostic:
    return SDLParseDiagnostic(
        code="sdl.legacy_node_type_vm",
        message=(
            "Legacy node type 'vm' is exact virtual-machine intent; migrate to type 'compute' "
            "with an exact compute-substrate realization constraint."
        ),
        pointer=pointer,
        primary_range=_source_range(pointer, source_ranges),
        severity=severity,
        source=str(path) if path is not None else None,
    )


def _reject_processor_owned_constraint_provenance(
    data: dict[str, Any],
    *,
    path: Path | None,
) -> None:
    realization = data.get("realization")
    if not isinstance(realization, dict):
        return
    constraints = realization.get("constraints")
    if isinstance(constraints, list) and any(
        isinstance(constraint, dict) and "provenance" in constraint for constraint in constraints
    ):
        raise SDLParseError("Realization constraint provenance is processor-owned.", path=path)


def _legacy_vm_nodes(data: dict[str, Any]) -> list[tuple[object, dict[str, Any]]]:
    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        return []
    return [
        (name, node)
        for name, node in nodes.items()
        if isinstance(node, dict) and isinstance(node.get("type"), str) and node["type"].casefold() == "vm"
    ]


def _realization_constraints(data: dict[str, Any], *, path: Path | None) -> list[object]:
    realization = data.setdefault("realization", {})
    if not isinstance(realization, dict):
        raise SDLParseError("Legacy vm migration requires realization to be a mapping.", path=path)
    constraints = realization.setdefault("constraints", [])
    if not isinstance(constraints, list):
        raise SDLParseError("Legacy vm migration requires realization.constraints to be a sequence.", path=path)
    return constraints


def _migrate_legacy_vm_node(
    name: object,
    node: dict[str, Any],
    constraints: list[object],
    *,
    path: Path | None,
) -> None:
    field_pointer = f"/nodes/{escape_token(str(name))}"
    collision = any(
        isinstance(authored, dict)
        and authored.get("field_pointer") == field_pointer
        and authored.get("concern") == "compute-substrate"
        and not authored.get("namespace")
        for authored in constraints
    )
    if collision:
        raise SDLParseError(
            f"Legacy vm constraint for '{field_pointer}' collides with an authored compute-substrate constraint.",
            path=path,
        )
    node["type"] = "compute"
    constraints.append(
        {
            "field_pointer": field_pointer,
            "concern": "compute-substrate",
            "posture": "exact",
            "domain": {"kind": "exact", "value": "virtual-machine"},
            "provenance": "legacy-node-type-vm",
        }
    )


def migrate_legacy_vm_nodes(
    data: dict[str, Any],
    *,
    path: Path | None,
    migration_policy: SDLMigrationPolicy | str,
    source_diagnostics: list[SDLParseDiagnostic] | None,
    source_ranges: dict[str, SDLSourceRange] | None,
) -> None:
    """Normalize legacy VM syntax once without weakening its exact meaning."""

    _reject_processor_owned_constraint_provenance(data, path=path)
    policy = SDLMigrationPolicy(migration_policy)
    legacy = _legacy_vm_nodes(data)
    if not legacy:
        return
    diagnostics = [
        _legacy_vm_diagnostic(
            pointer=f"/nodes/{escape_token(str(name))}/type",
            path=path,
            source_ranges=source_ranges,
            severity="warning" if policy is SDLMigrationPolicy.ACCEPT else "error",
        )
        for name, _node in legacy
    ]
    if policy is SDLMigrationPolicy.REJECT:
        raise SDLParseError(
            "Legacy node type 'vm' requires explicit migration acceptance.",
            path=path,
            diagnostics=diagnostics,
        )

    constraints = _realization_constraints(data, path=path)
    for name, node in legacy:
        _migrate_legacy_vm_node(name, node, constraints, path=path)
    if source_diagnostics is not None:
        source_diagnostics.extend(diagnostics)


__all__ = ["migrate_legacy_vm_nodes"]
