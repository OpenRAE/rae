"""Versioned canonical semantic identity for validated SDL authoring scenarios."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

import rfc8785
from pydantic import ConfigDict, model_validator
from raes_contracts.canonical import canonical_json_bytes, canonical_json_digest
from raes_contracts.digests import sha256_digest
from raes_contracts.json_pointer import escape_token

from ._base import SDLModel
from ._errors import SDLError, SDLParseError
from ._source_profile import DEFAULT_PARSER_LIMITS, SDL_CANONICAL_PROFILE
from .materialization import MaterializedScenario, admit_materialized_scenario
from .scenario import ExpandedScenario, InstantiatedScenario, Scenario

INSTANTIATED_SNAPSHOT_PROFILE = "raes-sdl-instantiated-snapshot/v2"
MATERIALIZED_SDL_PROFILE = "raes-sdl-materialized/v1"
_LEGACY_SNAPSHOT_PROJECTION_REVISION = "instantiated-snapshot-v1/node-architecture-default"
# Twice the authoring depth limit leaves room for the snapshot envelope and provenance, and it
# keeps the recursive copy and canonicalization far below the interpreter recursion limit.
_SNAPSHOT_MAX_DEPTH = 2 * DEFAULT_PARSER_LIMITS.max_depth


@dataclass(frozen=True)
class SDLCanonicalDigest:
    """Profile-labelled digest of canonical SDL semantic bytes."""

    profile: str
    algorithm: str
    value: str

    def as_dict(self) -> dict[str, str]:
        return {"profile": self.profile, "algorithm": self.algorithm, "value": self.value}


def canonical_sdl_bytes(scenario: Scenario | ExpandedScenario) -> bytes:
    """Return RFC 8785 bytes for one validated, post-expansion authoring scenario."""
    if not isinstance(scenario, (Scenario, ExpandedScenario)):
        raise SDLParseError("Canonical SDL semantic identity requires an authoring scenario")
    if not scenario.semantic_validated:
        raise SDLParseError("Canonical SDL semantic identity requires successful semantic validation")

    excluded_fields = {"expansion_provenance"}
    if not scenario.variation_points:
        excluded_fields.add("variation_points")
    payload = {
        "profile": SDL_CANONICAL_PROFILE,
        "scenario": scenario.model_dump(
            mode="json",
            by_alias=True,
            exclude_unset=True,
            exclude=excluded_fields,
        ),
        "module_variable_specs": scenario.module_variable_specs,
        "module_node_variable_refs": scenario.module_node_variable_refs,
    }
    try:
        return canonical_json_bytes(payload)
    except rfc8785.CanonicalizationError as exc:
        raise SDLParseError("SDL canonicalization failed") from exc


def canonical_sdl_digest(scenario: Scenario | ExpandedScenario) -> SDLCanonicalDigest:
    """Return the profile-labelled SHA-256 digest of canonical SDL semantic bytes."""
    return SDLCanonicalDigest(
        profile=SDL_CANONICAL_PROFILE,
        algorithm="sha256",
        value=sha256_digest(canonical_sdl_bytes(scenario)),
    )


def canonical_materialized_sdl_bytes(scenario: MaterializedScenario) -> bytes:
    """Return a descriptive identity without reusing an input snapshot profile."""
    if not isinstance(scenario, MaterializedScenario) or not scenario.semantic_validated:
        raise SDLParseError("Materialized SDL identity requires a validated materialization description")
    scenario = admit_materialized_scenario(scenario)
    try:
        return canonical_json_bytes(
            {
                "profile": MATERIALIZED_SDL_PROFILE,
                "scenario": scenario.model_dump(mode="json", by_alias=True, exclude_unset=True),
            }
        )
    except rfc8785.CanonicalizationError as exc:
        raise SDLParseError("Materialized SDL canonicalization failed") from exc


def canonical_materialized_sdl_digest(scenario: MaterializedScenario) -> SDLCanonicalDigest:
    """Return the separately profiled identity of a materialization description."""
    return SDLCanonicalDigest(
        profile=MATERIALIZED_SDL_PROFILE,
        algorithm="sha256",
        value=sha256_digest(canonical_materialized_sdl_bytes(scenario)),
    )


class InstantiatedScenarioSnapshot(SDLModel):
    """Sealed canonical envelope for one portable instantiated artifact."""

    model_config = ConfigDict(
        title="SDL Instantiated Scenario Snapshot v1",
        extra="forbid",
        frozen=True,
        json_schema_extra={"x-raes-document-phase": "canonical-instantiated-snapshot"},
    )

    profile: Literal["raes-sdl-instantiated-snapshot/v2"]
    scenario: InstantiatedScenario

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_vm_snapshot(cls, value: object) -> object:
        migrated, _changed = migrate_legacy_instantiated_snapshot_payload(value)
        return migrated


def migrate_legacy_instantiated_snapshot_payload(value: object) -> tuple[object, bool]:
    """Upgrade v1 snapshot defaults and legacy node kinds independently.

    Authoring input remains strict by default.  This compatibility boundary is
    limited to already-instantiated ``v1`` artifacts, whose historical ``vm``
    resource kind meant both compute and an exact virtual-machine substrate.
    Empty retired classification containers assert nothing, regardless of the
    node kinds present. Nonempty classifications still require explicit migration.
    """

    if (
        not isinstance(value, Mapping)
        or value.get("profile") != INSTANTIATED_SNAPSHOT_PROFILE
        or not isinstance(value.get("scenario"), dict)
    ):
        return value, False

    _require_bounded_snapshot_depth(value)
    legacy_names = _legacy_snapshot_vm_names(value)
    migrated: dict[str, Any] = deepcopy(dict(value))
    if legacy_names:
        nodes, existing = _legacy_snapshot_migration_surfaces(migrated)
        for name in legacy_names:
            _migrate_legacy_snapshot_vm(name, nodes, existing)
    from ._legacy_snapshot_classifications import remove_empty_legacy_snapshot_classifications

    changed = remove_empty_legacy_snapshot_classifications(migrated["scenario"])
    return (migrated, True) if legacy_names or changed else (value, False)


def _require_bounded_snapshot_depth(value: object) -> None:
    """Refuse nesting that the recursive copy and walks below cannot process.

    Model validators call this migration, so the refusal is a ValueError (ADR-116 rule E3).
    """
    pending: list[tuple[object, int]] = [(value, 1)]
    while pending:
        item, depth = pending.pop()
        if isinstance(item, Mapping):
            children: Iterable[object] = item.values()
        elif isinstance(item, (list, tuple)):
            children = item
        else:
            continue
        if depth > _SNAPSHOT_MAX_DEPTH:
            raise ValueError("instantiated snapshot nesting exceeds the depth limit")
        pending.extend((child, depth + 1) for child in children)


def _legacy_snapshot_vm_names(value: object) -> list[str]:
    if not isinstance(value, Mapping) or value.get("profile") != INSTANTIATED_SNAPSHOT_PROFILE:
        return []
    scenario = value.get("scenario")
    nodes = scenario.get("nodes") if isinstance(scenario, Mapping) else None
    if not isinstance(nodes, Mapping):
        return []
    return sorted(str(name) for name, node in nodes.items() if isinstance(node, Mapping) and node.get("type") == "vm")


def _legacy_snapshot_migration_surfaces(
    migrated: dict[str, Any],
) -> tuple[dict[str, Any], list[object]]:
    scenario = migrated["scenario"]
    nodes = scenario["nodes"]
    provenance = scenario.get("instantiation_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("legacy instantiated VM migration requires instantiation provenance")
    existing = provenance.setdefault("realization_constraints", [])
    if not isinstance(existing, list):
        raise ValueError("legacy instantiated VM migration requires a realization constraint list")
    return nodes, existing


def _migrate_legacy_snapshot_vm(
    name: str,
    nodes: dict[str, Any],
    existing: list[object],
) -> None:
    pointer = f"/nodes/{escape_token(name)}"
    collision = any(
        isinstance(record, Mapping)
        and not record.get("namespace")
        and record.get("field_pointer") == pointer
        and record.get("concern") == "compute-substrate"
        for record in existing
    )
    if collision:
        raise ValueError("legacy instantiated VM migration collides with a compute-substrate constraint")
    nodes[name]["type"] = "compute"
    existing.append(
        {
            "namespace": [],
            "field_pointer": pointer,
            "concern": "compute-substrate",
            "posture": "exact",
            "domain": {"kind": "exact", "value": "virtual-machine"},
            "provenance": "legacy-node-type-vm",
        }
    )


def migrate_legacy_instantiated_snapshot_join(
    value: object,
    submitted_digest: object,
) -> tuple[object, object, bool]:
    """Authenticate a historical snapshot join before migrating its payload.

    The historical v1 canonical projection materialized the then-new nullable
    node ``architecture`` field before hashing. Reproduce that versioned
    projection for every structurally valid legacy snapshot instead of pinning
    compatibility to a single published artifact.
    """

    migrated, changed = migrate_legacy_instantiated_snapshot_payload(value)
    if not changed:
        return value, submitted_digest, False
    try:
        raw_digest = canonical_json_digest(value)
    except rfc8785.CanonicalizationError as exc:
        raise ValueError("legacy instantiated snapshot canonicalization failed") from exc
    if not isinstance(value, Mapping):
        raise ValueError("legacy snapshot migration requires a mapping")
    historical_digest = _legacy_instantiated_snapshot_projection_digest(value)
    if submitted_digest not in {raw_digest, historical_digest}:
        raise ValueError("legacy snapshot_digest must bind the submitted immutable snapshot")
    snapshot = InstantiatedScenarioSnapshot.model_validate(migrated)
    # Model validators call this function, so an SDL refusal becomes a ValueError (ADR-116 rule E3).
    try:
        current_digest = canonical_instantiated_sdl_digest(snapshot.scenario).value
    except SDLError as exc:
        raise ValueError("migrated legacy snapshot failed instantiated SDL admission") from exc
    return migrated, current_digest, True


def _legacy_instantiated_snapshot_projection_digest(value: Mapping[str, object]) -> str:
    """Reproduce the named historical v1 projection without current models."""

    projected: dict[str, Any] = deepcopy(dict(value))
    scenario = projected.get("scenario")
    nodes = scenario.get("nodes") if isinstance(scenario, dict) else None
    if isinstance(nodes, dict):
        for node in nodes.values():
            if isinstance(node, dict):
                node.setdefault("architecture", None)
    try:
        payload = canonical_json_bytes(projected)
    except rfc8785.CanonicalizationError as exc:
        raise ValueError(f"legacy snapshot projection {_LEGACY_SNAPSHOT_PROJECTION_REVISION} failed") from exc
    return sha256_digest(payload)


def canonical_instantiated_sdl_bytes(scenario: InstantiatedScenario) -> bytes:
    """Return RFC 8785 bytes for one admitted instantiated artifact."""

    # Keep canonicalization pure with respect to the caller's private validation
    # flags while applying the same structural and semantic admission boundary
    # used by the compiler.
    from .instantiate import admit_instantiated_scenario

    admitted = admit_instantiated_scenario(
        InstantiatedScenario.model_validate(scenario.model_dump(mode="python", by_alias=True))
    )
    snapshot = InstantiatedScenarioSnapshot(
        profile=INSTANTIATED_SNAPSHOT_PROFILE,
        scenario=admitted,
    )
    try:
        return canonical_json_bytes(snapshot.model_dump(mode="json"))
    except rfc8785.CanonicalizationError as exc:
        raise SDLParseError("Instantiated SDL canonicalization failed") from exc


def canonical_instantiated_sdl_digest(scenario: InstantiatedScenario) -> SDLCanonicalDigest:
    """Return the profile-labelled digest of an instantiated snapshot."""

    return SDLCanonicalDigest(
        profile=INSTANTIATED_SNAPSHOT_PROFILE,
        algorithm="sha256",
        value=sha256_digest(canonical_instantiated_sdl_bytes(scenario)),
    )
