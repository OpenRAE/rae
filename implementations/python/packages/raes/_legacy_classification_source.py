"""Exact historical classification extraction; never a runtime SDL reader."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from pydantic import TypeAdapter
from raes_contracts.canonical import canonical_json_digest

from ._base import contains_variable_token
from ._errors import SDLParseError
from ._source_profile import DEFAULT_PARSER_LIMITS, SDL_CANONICAL_PROFILE, SDLParserLimits
from .canonical import SDLCanonicalDigest
from .parser import _load_normalized_data
from .participant_behavior import ExternalMappingLoss
from .vulnerabilities import Vulnerability

BEHAVIOR_CLASSIFICATION_FIELDS = (
    "ai_offensive_behavior_refs",
    "defensive_behavior_refs",
    "offensive_behavior_refs",
)
_STRINGS = TypeAdapter(list[str])


@dataclass(frozen=True)
class LegacyClassification:
    pointer: str
    subject_ref: str
    identifier: str
    declaration_ref: str | None = None


@dataclass(frozen=True)
class LegacyClassificationSource:
    native: dict[str, Any]
    original: dict[str, Any]
    classifications: tuple[LegacyClassification, ...]
    declarations: tuple[str, ...]
    source_digest: SDLCanonicalDigest


def _token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _strings(value: object) -> list[str]:
    values = _STRINGS.validate_python(value, strict=True)
    if any(not item.strip() or contains_variable_token(item) for item in values):
        raise ValueError("Legacy classification values must be concrete non-empty strings.")
    if len(values) != len(set(values)):
        raise ValueError("Legacy classification values must be unique.")
    return values


def _extract_fields(
    item: dict[str, Any],
    *,
    pointer: str,
    subject: str,
    fields: tuple[str, ...],
    declarations: dict[str, Vulnerability],
    records: list[LegacyClassification],
) -> None:
    for field in fields:
        if field not in item:
            continue
        for index, identifier in enumerate(_strings(item.pop(field))):
            declaration = None
            if field in {"vulnerabilities", "vulnerability_refs"}:
                if identifier not in declarations:
                    raise ValueError("Legacy vulnerability association has no exact declaration.")
                declaration = f"vulnerabilities.{identifier}"
                identifier = declarations[identifier].vuln_class
            records.append(
                LegacyClassification(
                    pointer=f"{pointer}/{field}/{index}",
                    subject_ref=subject,
                    identifier=identifier,
                    declaration_ref=declaration,
                )
            )


def _extract_entities(
    entities: object,
    *,
    pointer: str,
    subject: str,
    declarations: dict[str, Vulnerability],
    records: list[LegacyClassification],
) -> None:
    if not isinstance(entities, dict):
        return
    for name, item in entities.items():
        if not isinstance(item, dict):
            continue
        path, ref = f"{pointer}/{_token(name)}", f"{subject}.{name}"
        _extract_fields(
            item,
            pointer=path,
            subject=ref,
            fields=("vulnerabilities", "categories"),
            declarations=declarations,
            records=records,
        )
        _extract_entities(
            item.get("entities"), pointer=f"{path}/entities", subject=ref, declarations=declarations, records=records
        )


def _extract_routes(
    node: dict[str, Any], *, node_name: str, declarations: dict[str, Vulnerability], records: list[LegacyClassification]
) -> None:
    runtime = node.get("runtime")
    if not isinstance(runtime, dict):
        return
    applications = runtime.get("applications", [])
    if not isinstance(applications, list):
        return
    for app_index, application in enumerate(applications):
        if not isinstance(application, dict) or not isinstance(application.get("routes", []), list):
            continue
        _extract_application_routes(application, node_name, app_index, declarations, records)


def _extract_application_routes(
    application: dict[str, Any],
    node_name: str,
    app_index: int,
    declarations: dict[str, Vulnerability],
    records: list[LegacyClassification],
) -> None:
    for route_index, route in enumerate(application.get("routes", [])):
        if not isinstance(route, dict) or "vulnerability_refs" not in route:
            continue
        app_id, route_id = application.get("application_id"), route.get("route_id")
        if any(
            not isinstance(value, str) or not value or contains_variable_token(value) for value in (app_id, route_id)
        ):
            raise ValueError("Route classification migration requires exact concrete route identity.")
        _extract_fields(
            route,
            pointer=f"/nodes/{_token(node_name)}/runtime/applications/{app_index}/routes/{route_index}",
            subject=f"nodes.{node_name}.runtime.applications.{app_id}.routes.{route_id}",
            fields=("vulnerability_refs",),
            declarations=declarations,
            records=records,
        )


def read_legacy_classification_source(
    content: str,
    *,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
) -> LegacyClassificationSource:
    """Load bounded canonical-spelling legacy YAML and extract only known fields."""
    original = _load_normalized_data(content, limits=limits)
    if original.get("imports") or "instantiation_provenance" in original:
        raise ValueError("Migrate each authored source before composition or instantiation.")
    native = deepcopy(original)
    raw_declarations = native.pop("vulnerabilities", {})
    if not isinstance(raw_declarations, dict):
        raise ValueError("Legacy vulnerabilities must be a declaration map.")
    declarations = {name: Vulnerability.model_validate(value) for name, value in raw_declarations.items()}
    if any(
        model.model_dump(mode="json", by_alias=True, exclude_unset=True) != raw_declarations[name]
        for name, model in declarations.items()
    ):
        raise ValueError("Normalize historical declaration values with the source-version formatter first.")
    records: list[LegacyClassification] = []
    _extract_sections(native, declarations, records)
    _extract_entities(
        native.get("entities"), pointer="/entities", subject="entities", declarations=declarations, records=records
    )
    _extract_actions(native.get("action_contracts", {}), records)
    digest = canonical_json_digest(
        {
            "profile": SDL_CANONICAL_PROFILE,
            "scenario": original,
            "module_variable_specs": {},
            "module_node_variable_refs": {},
        }
    )
    return LegacyClassificationSource(
        native,
        original,
        tuple(sorted(records, key=lambda item: item.pointer)),
        tuple(sorted(f"vulnerabilities.{name}" for name in declarations)),
        SDLCanonicalDigest(SDL_CANONICAL_PROFILE, "sha256", digest),
    )


def _extract_sections(
    native: dict[str, Any], declarations: dict[str, Vulnerability], records: list[LegacyClassification]
) -> None:
    for section, fields in (
        ("nodes", ("vulnerabilities",)),
        ("features", ("vulnerabilities",)),
        ("behavior_specifications", BEHAVIOR_CLASSIFICATION_FIELDS),
    ):
        values = native.get(section, {})
        if not isinstance(values, dict):
            continue
        for name, item in values.items():
            if not isinstance(item, dict):
                continue
            _extract_fields(
                item,
                pointer=f"/{section}/{_token(name)}",
                subject=f"{section}.{name}",
                fields=fields,
                declarations=declarations,
                records=records,
            )
            if section == "nodes":
                _extract_routes(item, node_name=name, declarations=declarations, records=records)


def _extract_actions(actions: object, records: list[LegacyClassification]) -> None:
    if isinstance(actions, dict):
        for name, action in actions.items():
            if not isinstance(action, dict) or "external_mappings" not in action:
                continue
            raw_mappings = action.pop("external_mappings")
            mappings = TypeAdapter(list[ExternalMappingLoss]).validate_python(raw_mappings)
            if [model.model_dump(mode="json", by_alias=True, exclude_unset=True) for model in mappings] != raw_mappings:
                raise ValueError("Normalize historical action mappings with the source-version formatter first.")
            for index, mapping in enumerate(mappings):
                if contains_variable_token(mapping.identifier):
                    raise ValueError("Legacy action mappings require concrete identifiers.")
                records.append(
                    LegacyClassification(
                        pointer=f"/action_contracts/{_token(name)}/external_mappings/{index}",
                        subject_ref=f"action_contracts.{name}",
                        identifier=mapping.identifier,
                    )
                )


def legacy_classification_source_digest(content: str) -> SDLCanonicalDigest:
    """Digest of the supported, normalized legacy authoring-source projection."""
    try:
        return read_legacy_classification_source(content).source_digest
    except (TypeError, ValueError) as exc:
        raise SDLParseError("Legacy classification source is invalid or needs an explicit subject migration.") from exc
