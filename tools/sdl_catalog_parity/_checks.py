"""Parity checks comparing the normative catalogs with the live SDL surface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from raes._language_metadata import REFERENCE_COMPLETION_TARGETS
from raes._mapping_scopes import HASHMAP_SECTIONS
from raes._module_symbols import HASHMAP_SECTIONS as MODULE_HASHMAP_SECTIONS
from raes._runtime_service_families import RUNTIME_SERVICE_FAMILIES
from raes.materialization import MaterializedScenario
from raes.phase_contracts import ExpansionProvenance, InstantiationProvenance
from raes.scenario import (
    ExpandedScenario,
    InstantiatedScenario,
    Scenario,
    ScenarioContent,
)

from tools.policy.common import PolicyFailure
from tools.sdl_catalog_parity._expected import (
    _expected_identity,
    _expected_kind,
    _expected_lifecycle,
    _expected_presence,
    _failure,
    _flatten_children,
    _schema_shape,
)
from tools.sdl_catalog_parity._model_paths import (
    _is_normative_reference_owner,
    _reference_source_path_exists,
)
from tools.sdl_catalog_parity._paths import (
    _SUMMARY_RE,
    _VALID_KINDS,
    _VALID_LIFECYCLE,
    _VALID_SHAPES,
    PHASES_PATH,
    REFERENCES_PATH,
    RUNTIME_PATH,
    SCHEMA_PATH,
    SECTIONS_PATH,
)
from tools.sdl_catalog_parity._registry import REFERENCE_EDGE_EXPECTATIONS
from tools.sdl_catalog_parity._rows import (
    CatalogParseError,
    PhaseMemberRow,
    ReferenceRow,
    TopLevelRow,
    parse_phase_member_catalog,
    parse_reference_catalog,
    parse_runtime_catalog,
    parse_top_level_catalog,
)


def _field_set_failures(
    catalog_fields: set[str],
    model_fields: set[str],
    schema_fields: set[str],
) -> list[PolicyFailure]:
    if model_fields == schema_fields and catalog_fields == model_fields:
        return []
    return [
        _failure(
            "sdl-catalog-field-set",
            f"field sets differ: catalog-only={sorted(catalog_fields - model_fields)}, "
            f"model-only={sorted(model_fields - catalog_fields)}, "
            f"schema-only={sorted(schema_fields - model_fields)}, "
            f"model-only-vs-schema={sorted(model_fields - schema_fields)}",
            SECTIONS_PATH,
        )
    ]


def _field_row_failures(field: str, row: TopLevelRow, field_schema: dict[str, Any]) -> list[PolicyFailure]:
    """Return the classification failures for one catalogued top-level field."""

    failures: list[PolicyFailure] = []
    expected_shape = _schema_shape(field_schema)
    if field in HASHMAP_SECTIONS:
        expected_shape = "map"
    if row.shape != expected_shape:
        failures.append(
            _failure(
                "sdl-catalog-field-shape",
                f"{field!r} is {expected_shape}, catalog says {row.shape}",
                SECTIONS_PATH,
            )
        )
    expected_presence = _expected_presence(field)
    if row.presence != expected_presence:
        failures.append(
            _failure(
                "sdl-catalog-field-default",
                f"{field!r} is {expected_presence}, catalog says {row.presence}",
                SECTIONS_PATH,
            )
        )
    expected_identity = _expected_identity(field, expected_shape)
    if row.identity != expected_identity:
        failures.append(
            _failure(
                "sdl-catalog-field-identity",
                f"{field!r} identity is {expected_identity!r}, catalog says {row.identity!r}",
                SECTIONS_PATH,
            )
        )
    if row.kind != _expected_kind(field) or row.kind not in _VALID_KINDS:
        failures.append(
            _failure(
                "sdl-catalog-field-kind",
                f"{field!r} has invalid kind {row.kind!r}",
                SECTIONS_PATH,
            )
        )
    failures.extend(_field_classification_failures(field, row))
    return failures


def _field_classification_failures(field: str, row: TopLevelRow) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    expected_lifecycle = _expected_lifecycle(field)
    if row.lifecycle != expected_lifecycle or not set(row.lifecycle) <= _VALID_LIFECYCLE:
        failures.append(
            _failure(
                "sdl-catalog-lifecycle",
                f"{field!r} lifecycle is {expected_lifecycle!r}, catalog says {row.lifecycle!r}",
                SECTIONS_PATH,
            )
        )
    if row.shape not in _VALID_SHAPES or not row.identity or not row.owner:
        failures.append(
            _failure(
                "sdl-catalog-row-incomplete",
                f"{field!r} has an incomplete classification",
                SECTIONS_PATH,
            )
        )
    return failures


def _map_set_failures(rows: list[TopLevelRow]) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    map_fields = {row.field for row in rows if row.shape == "map"}
    if map_fields != set(HASHMAP_SECTIONS):
        failures.append(
            _failure(
                "sdl-catalog-map-set",
                f"map fields differ from mapping registry: {sorted(map_fields ^ set(HASHMAP_SECTIONS))}",
                SECTIONS_PATH,
            )
        )
    if not set(MODULE_HASHMAP_SECTIONS) <= map_fields:
        failures.append(
            _failure(
                "sdl-catalog-module-map-set",
                "module export maps are not a subset of catalogued maps",
                SECTIONS_PATH,
            )
        )
    return failures


def _summary_failures(text: str, rows: list[TopLevelRow]) -> list[PolicyFailure]:
    summary = _SUMMARY_RE.search(text)
    actual = {
        "top": len(rows),
        "meta": sum(row.kind != "section" for row in rows),
        "sections": sum(row.kind == "section" for row in rows),
        "maps": sum(row.shape == "map" for row in rows),
        "lists": sum(row.shape == "list" and row.kind == "section" for row in rows),
    }
    if summary is not None and all(int(summary.group(key)) == value for key, value in actual.items()):
        return []
    return [
        _failure(
            "sdl-catalog-summary",
            f"checked summary is absent or stale; expected {actual}",
            SECTIONS_PATH,
        )
    ]


def _schema_required_failures(schema: dict[str, Any]) -> list[PolicyFailure]:
    required = set(schema.get("required", []))
    model_required = {name for name, field in Scenario.model_fields.items() if field.is_required()}
    if required == model_required:
        return []
    return [
        _failure(
            "sdl-catalog-schema-required",
            f"published schema required set differs from model: {sorted(required ^ model_required)}",
            SCHEMA_PATH,
        )
    ]


def _check_top_level(text: str, schema: dict[str, Any]) -> tuple[list[PolicyFailure], list[TopLevelRow]]:
    try:
        rows = parse_top_level_catalog(text)
    except CatalogParseError as exc:
        return [_failure("sdl-catalog-parse", str(exc), SECTIONS_PATH)], []
    by_field = {row.field: row for row in rows}
    model_fields = set(Scenario.model_fields)
    schema_fields = set(schema.get("properties", {}))
    catalog_fields = set(by_field)
    failures = _field_set_failures(catalog_fields, model_fields, schema_fields)
    for field in sorted(catalog_fields & model_fields & schema_fields):
        failures.extend(_field_row_failures(field, by_field[field], schema["properties"][field]))
    failures.extend(_map_set_failures(rows))
    failures.extend(_summary_failures(text, rows))
    failures.extend(_schema_required_failures(schema))
    return failures, rows


def _reference_contract_failures(
    by_source: dict[str, tuple[str, str, str, str]],
) -> list[PolicyFailure]:
    if by_source == REFERENCE_EDGE_EXPECTATIONS:
        return []
    differing = sorted(
        source
        for source in by_source.keys() | REFERENCE_EDGE_EXPECTATIONS.keys()
        if by_source.get(source) != REFERENCE_EDGE_EXPECTATIONS.get(source)
    )
    return [
        _failure(
            "sdl-catalog-reference-row",
            f"reference-edge contract differs for: {differing}",
            REFERENCES_PATH,
        )
    ]


def _completion_target_failures(rows: list[ReferenceRow]) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for key, domain in sorted(REFERENCE_COMPLETION_TARGETS.items()):
        matching = [row for row in rows if row.key == key and row.domain == domain]
        if not matching:
            actual = sorted({row.domain for row in rows if row.key == key}) or None
            failures.append(
                _failure(
                    "sdl-catalog-reference-domain",
                    f"{key!r} expects domain {domain!r}, catalog says {actual!r}",
                    REFERENCES_PATH,
                )
            )
    return failures


def _row_validity_failures(rows: list[ReferenceRow], repo_root: Path) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for row in rows:
        if not _reference_source_path_exists(row.source_path):
            failures.append(
                _failure(
                    "sdl-catalog-reference-path",
                    f"{row.source_path!r} does not traverse the typed SDL model",
                    REFERENCES_PATH,
                )
            )
        if not _is_normative_reference_owner(row.normative_owner, repo_root):
            failures.append(
                _failure(
                    "sdl-catalog-reference-owner",
                    f"{row.source_path!r} has no normative prose/ADR owner",
                    REFERENCES_PATH,
                )
            )
    return failures


def _behavior_edge_failures(
    by_source: dict[str, tuple[str, str, str, str]],
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    behavior_expectations = {
        source: expected
        for source, expected in REFERENCE_EDGE_EXPECTATIONS.items()
        if source.startswith("behavior_specifications.*.")
    }
    for source, expected in behavior_expectations.items():
        if by_source.get(source) != expected:
            failures.append(
                _failure(
                    "sdl-catalog-behavior-edge",
                    f"{source} must match its behavior reference contract",
                    REFERENCES_PATH,
                )
            )
    return failures


def _reference_coverage_failures(rows: list[ReferenceRow], top_rows: list[TopLevelRow]) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    source_sections = {row.key[0] for row in rows}
    top_by_field = {row.field: row for row in top_rows}
    for section in source_sections:
        top = top_by_field.get(section)
        if top is None or top.references != "catalogued":
            failures.append(
                _failure(
                    "sdl-catalog-reference-coverage",
                    f"reference source section {section!r} is not marked catalogued",
                    SECTIONS_PATH,
                )
            )
    for row in top_rows:
        if row.references == "catalogued" and row.field not in source_sections:
            failures.append(
                _failure(
                    "sdl-catalog-reference-coverage",
                    f"{row.field!r} is marked catalogued but has no edge row",
                    REFERENCES_PATH,
                )
            )
    return failures


def _check_references(text: str, top_rows: list[TopLevelRow], repo_root: Path) -> list[PolicyFailure]:
    try:
        rows = parse_reference_catalog(text)
    except CatalogParseError as exc:
        return [_failure("sdl-catalog-reference-parse", str(exc), REFERENCES_PATH)]
    by_source = {row.source_path: (row.domain, row.phase, row.failure, row.evidence) for row in rows}
    failures = _reference_contract_failures(by_source)
    failures.extend(_completion_target_failures(rows))
    failures.extend(_row_validity_failures(rows, repo_root))
    failures.extend(_behavior_edge_failures(by_source))
    failures.extend(_reference_coverage_failures(rows, top_rows))
    return failures


def _check_runtime(text: str) -> list[PolicyFailure]:
    try:
        rows = parse_runtime_catalog(text)
    except CatalogParseError as exc:
        return [_failure("sdl-catalog-runtime-parse", str(exc), RUNTIME_PATH)]
    actual = {row.key: (row.collection, row.primary_id, row.child_paths) for row in rows}
    expected = {
        family.key: (
            family.collection_name,
            family.id_field,
            _flatten_children(family.child_refs),
        )
        for family in RUNTIME_SERVICE_FAMILIES
    }
    if actual != expected:
        differing = sorted(key for key in actual.keys() | expected.keys() if actual.get(key) != expected.get(key))
        return [
            _failure(
                "sdl-catalog-runtime-family",
                f"runtime-family catalog differs for: {differing}",
                RUNTIME_PATH,
            )
        ]
    return []


def _phase_status(model: type[ScenarioContent], member: str) -> str:
    field = model.model_fields.get(member)
    if field is None:
        return "forbidden"
    return "required" if field.is_required() else "optional"


_PHASE_MODELS: tuple[tuple[str, type[ScenarioContent]], ...] = (
    ("normalized", Scenario),
    ("expanded", ExpandedScenario),
    ("instantiated", InstantiatedScenario),
    ("materialized", MaterializedScenario),
)


def _phase_membership_failures(
    by_member: dict[str, PhaseMemberRow],
    expected_members: set[str],
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for member in sorted(set(by_member) & expected_members):
        row = by_member[member]
        actual = tuple(getattr(row, phase) for phase, _model in _PHASE_MODELS)
        expected = tuple(_phase_status(model, member) for _phase, model in _PHASE_MODELS)
        if actual != expected:
            failures.append(
                _failure(
                    "sdl-catalog-phase-membership",
                    f"{member!r} phase membership is {expected!r}, catalog says {actual!r}",
                    PHASES_PATH,
                )
            )
        if not row.transfer:
            failures.append(
                _failure(
                    "sdl-catalog-phase-transfer",
                    f"{member!r} has no phase-transfer disposition",
                    PHASES_PATH,
                )
            )
    return failures


def _realization_transfer_failures(
    by_member: dict[str, PhaseMemberRow],
) -> list[PolicyFailure]:
    realization = by_member.get("realization")
    if realization is None:
        return []
    designation_fields = (
        ("expansion_provenance", ExpansionProvenance),
        ("instantiation_provenance", InstantiationProvenance),
    )
    required_paths = {
        f"{provenance_field}.{field_name}"
        for provenance_field, model in designation_fields
        for field_name in model.model_fields
        if field_name == "realization_designations"
    }
    missing = sorted(path for path in required_paths if f"`{path}`" not in realization.transfer)
    if not missing:
        return []
    return [
        _failure(
            "sdl-catalog-phase-transfer",
            f"realization transfer omits portable designation paths: {missing}",
            PHASES_PATH,
        )
    ]


def _check_phase_members(text: str) -> list[PolicyFailure]:
    try:
        rows = parse_phase_member_catalog(text)
    except CatalogParseError as exc:
        return [_failure("sdl-catalog-phase-parse", str(exc), PHASES_PATH)]

    shared = set(ScenarioContent.model_fields)
    expected_members = set().union(*(set(model.model_fields) - shared for _phase, model in _PHASE_MODELS))
    by_member = {row.member: row for row in rows}
    failures: list[PolicyFailure] = []
    if set(by_member) != expected_members:
        failures.append(
            _failure(
                "sdl-catalog-phase-members",
                "phase-specific member set differs: "
                f"catalog-only={sorted(set(by_member) - expected_members)}, "
                f"model-only={sorted(expected_members - set(by_member))}",
                PHASES_PATH,
            )
        )
    failures.extend(_phase_membership_failures(by_member, expected_members))
    failures.extend(_realization_transfer_failures(by_member))
    return failures
