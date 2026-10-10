#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Structural, SDL, and experiment authoring-input validation gate for the AUT-806 example library."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml

from tools.example_library_checks import (
    check_entry_metadata,
    check_example_refs,
    check_template_body,
    check_template_validation,
    check_worked_example_file,
)
from tools.policy.common import PolicyFailure, apply_exceptions, failures_to_json, load_exceptions

CATALOG_RELATIVE_PATH = "examples/library/catalog.yaml"
LIBRARY_VALUE = "raes-example-pattern-library"
TEMPLATE_VALUE = "raes-library-template"
PATTERN_VALUE = "raes-library-pattern"
REQUIREMENT_REF = "AUT-806"
REQUIRED_SURFACES: tuple[str, ...] = (
    "scenario",
    "workflow",
    "participant_behavior",
    "task",
    "run",
    "study",
)
REQUIRED_TOP_LEVEL_FIELDS: tuple[str, ...] = (
    "library",
    "version",
    "requirement_refs",
    "source_refs",
    "surfaces",
)
REQUIRED_SURFACE_FIELDS: tuple[str, ...] = (
    "summary",
    "worked_examples",
    "templates",
    "patterns",
)
REQUIRED_REFERENCE_ENTRY_FIELDS: tuple[str, ...] = (
    "id",
    "path",
)
REQUIRED_TEMPLATE_FIELDS: tuple[str, ...] = (
    "template",
    "version",
    "id",
    "surface",
    "requirement_refs",
    "source_refs",
    "summary",
    "validation",
    "body",
)
REQUIRED_PATTERN_FIELDS: tuple[str, ...] = (
    "pattern",
    "version",
    "id",
    "surface",
    "requirement_refs",
    "source_refs",
    "summary",
    "intent",
    "authoring_steps",
    "validation",
)


def _fail(rule_id: str, message: str, path: str | None = CATALOG_RELATIVE_PATH) -> PolicyFailure:
    return PolicyFailure(rule_id, message, path)


def _str_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    if not all(isinstance(item, str) and item for item in value):
        return None
    return list(value)


def _load_yaml_file(path: Path, relative_path: str) -> tuple[dict[str, Any] | None, list[PolicyFailure]]:
    if not path.is_file():
        return None, [_fail("example-library-missing", f"missing {relative_path}", relative_path)]
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return None, [_fail("example-library-parse", f"failed to parse {relative_path}: {exc}", relative_path)]
    if not isinstance(raw, dict):
        return None, [
            _fail(
                "example-library-shape",
                f"{relative_path} must be a YAML mapping at the top level",
                relative_path,
            )
        ]
    return raw, []


def _repo_relative_path(
    value: Any, *, repo_root: Path, owner: str
) -> tuple[Path | None, str | None, PolicyFailure | None]:
    if not isinstance(value, str) or not value:
        return None, None, _fail("example-library-path", f"{owner} path must be a non-empty string")
    raw_path = Path(value)
    if raw_path.is_absolute() or ".." in raw_path.parts:
        return None, value, _fail("example-library-path", f"{owner} path must be repo-relative: {value}", value)
    return repo_root / raw_path, value, None


def _check_top_level(raw: dict[str, Any]) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in raw:
            failures.append(_fail("example-library-field", f"missing required top-level field: {field}"))

    if "library" in raw and raw["library"] != LIBRARY_VALUE:
        failures.append(_fail("example-library-name", f"library must be {LIBRARY_VALUE!r}; got {raw['library']!r}"))
    if "version" in raw and (not isinstance(raw["version"], int) or raw["version"] < 1):
        failures.append(_fail("example-library-version", "version must be a positive integer"))

    for field in ("requirement_refs", "source_refs"):
        if field in raw and _str_list(raw[field]) is None:
            failures.append(_fail("example-library-field-type", f"{field} must be a list of non-empty strings"))

    requirement_refs = _str_list(raw.get("requirement_refs"))
    if requirement_refs is not None and REQUIREMENT_REF not in requirement_refs:
        failures.append(_fail("example-library-requirement-ref", f"requirement_refs must include {REQUIREMENT_REF}"))

    if "surfaces" in raw and not isinstance(raw["surfaces"], dict):
        failures.append(_fail("example-library-field-type", "surfaces must be a mapping"))
    return failures


def _check_surfaces(raw: dict[str, Any], *, repo_root: Path) -> list[PolicyFailure]:
    surfaces = raw.get("surfaces")
    if not isinstance(surfaces, dict):
        return []

    failures: list[PolicyFailure] = []
    seen_ids: set[str] = set()
    for surface in REQUIRED_SURFACES:
        value = surfaces.get(surface)
        if not isinstance(value, dict):
            failures.append(_fail("example-library-surface", f"surfaces.{surface} must be a mapping"))
            continue
        failures.extend(_check_surface(surface, value, repo_root=repo_root, seen_ids=seen_ids))
    failures.extend(check_example_refs(surfaces))

    extras = sorted(set(surfaces) - set(REQUIRED_SURFACES))
    for surface in extras:
        failures.append(_fail("example-library-surface-extra", f"unexpected surface: {surface}"))
    return failures


def _check_surface(
    surface: str,
    value: dict[str, Any],
    *,
    repo_root: Path,
    seen_ids: set[str],
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for field in REQUIRED_SURFACE_FIELDS:
        if field not in value:
            failures.append(_fail("example-library-surface-field", f"surfaces.{surface} missing {field}"))

    summary = value.get("summary")
    if not isinstance(summary, str) or len(summary.strip()) < 20:
        failures.append(_fail("example-library-surface-summary", f"surfaces.{surface}.summary must be substantive"))

    failures.extend(
        _check_reference_entries(
            surface,
            "worked_examples",
            value.get("worked_examples"),
            repo_root=repo_root,
            seen_ids=seen_ids,
        )
    )
    failures.extend(
        _check_artifact_entries(
            surface,
            "templates",
            value.get("templates"),
            repo_root=repo_root,
            seen_ids=seen_ids,
            artifact_kind="template",
        )
    )
    failures.extend(
        _check_artifact_entries(
            surface,
            "patterns",
            value.get("patterns"),
            repo_root=repo_root,
            seen_ids=seen_ids,
            artifact_kind="pattern",
        )
    )
    return failures


def _check_reference_entries(
    surface: str,
    field: str,
    entries: Any,
    *,
    repo_root: Path,
    seen_ids: set[str],
) -> list[PolicyFailure]:
    if not isinstance(entries, list) or not entries:
        return [_fail("example-library-surface-entry", f"surfaces.{surface}.{field} must be a non-empty list")]

    failures: list[PolicyFailure] = []
    for index, entry in enumerate(entries):
        failures.extend(
            _check_reference_entry(
                surface,
                field,
                index,
                entry,
                repo_root=repo_root,
                seen_ids=seen_ids,
            )
        )
    return failures


def _check_reference_entry(
    surface: str,
    field: str,
    index: int,
    entry: Any,
    *,
    repo_root: Path,
    seen_ids: set[str],
) -> list[PolicyFailure]:
    if not isinstance(entry, dict):
        return [
            _fail(
                "example-library-entry-shape",
                f"surfaces.{surface}.{field}[{index}] must be a mapping; got {type(entry).__name__}",
            )
        ]

    failures: list[PolicyFailure] = []
    for required_field in REQUIRED_REFERENCE_ENTRY_FIELDS:
        if required_field not in entry:
            failures.append(
                _fail("example-library-entry-field", f"surfaces.{surface}.{field}[{index}] missing {required_field}")
            )

    failures.extend(_check_unique_id(entry.get("id"), f"surfaces.{surface}.{field}[{index}]", seen_ids))
    failures.extend(check_entry_metadata(field, entry, f"surfaces.{surface}.{field}[{index}]", surface=surface))
    absolute, relative, path_failure = _repo_relative_path(
        entry.get("path"),
        repo_root=repo_root,
        owner=f"surfaces.{surface}.{field}[{index}]",
    )
    if path_failure is not None:
        failures.append(path_failure)
    elif absolute is not None and relative is not None:
        failures.extend(check_worked_example_file(absolute, relative, entry))

    if "source_refs" in entry and _str_list(entry["source_refs"]) is None:
        failures.append(
            _fail("example-library-entry-field-type", f"surfaces.{surface}.{field}[{index}].source_refs must be a list")
        )
    return failures


def _check_artifact_entries(
    surface: str,
    field: str,
    entries: Any,
    *,
    repo_root: Path,
    seen_ids: set[str],
    artifact_kind: str,
) -> list[PolicyFailure]:
    if not isinstance(entries, list) or not entries:
        return [_fail("example-library-surface-entry", f"surfaces.{surface}.{field} must be a non-empty list")]

    failures: list[PolicyFailure] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            failures.append(
                _fail(
                    "example-library-entry-shape",
                    f"surfaces.{surface}.{field}[{index}] must be a mapping; got {type(entry).__name__}",
                )
            )
            continue
        for required_field in REQUIRED_REFERENCE_ENTRY_FIELDS:
            if required_field not in entry:
                failures.append(
                    _fail(
                        "example-library-entry-field",
                        f"surfaces.{surface}.{field}[{index}] missing {required_field}",
                    )
                )
        entry_id = entry.get("id")
        failures.extend(_check_unique_id(entry_id, f"surfaces.{surface}.{field}[{index}]", seen_ids))
        failures.extend(check_entry_metadata(field, entry, f"surfaces.{surface}.{field}[{index}]", surface=surface))
        absolute, relative, path_failure = _repo_relative_path(
            entry.get("path"),
            repo_root=repo_root,
            owner=f"surfaces.{surface}.{field}[{index}]",
        )
        if path_failure is not None:
            failures.append(path_failure)
            continue
        if absolute is None or relative is None:
            continue
        if not absolute.is_file():
            failures.append(
                _fail("example-library-path-missing", f"referenced path does not exist: {relative}", relative)
            )
            continue
        if artifact_kind == "template":
            failures.extend(_check_template_file(absolute, relative, surface=surface, entry=entry))
        else:
            failures.extend(_check_pattern_file(absolute, relative, surface=surface, catalog_id=entry_id))
    return failures


def _check_unique_id(value: Any, owner: str, seen_ids: set[str]) -> list[PolicyFailure]:
    if not isinstance(value, str) or not value:
        return [_fail("example-library-entry-id", f"{owner}.id must be a non-empty string")]
    if value in seen_ids:
        return [_fail("example-library-entry-duplicate", f"duplicate library id: {value}")]
    seen_ids.add(value)
    return []


def _check_template_file(path: Path, relative_path: str, *, surface: str, entry: dict[str, Any]) -> list[PolicyFailure]:
    raw, failures = _load_yaml_file(path, relative_path)
    if raw is None:
        return failures
    catalog_id = entry.get("id")
    failures.extend(_check_artifact_common(raw, relative_path, surface=surface, catalog_id=catalog_id, kind="template"))

    if "template" in raw and raw["template"] != TEMPLATE_VALUE:
        failures.append(_fail("example-library-template-kind", f"template must be {TEMPLATE_VALUE!r}", relative_path))
    for field in REQUIRED_TEMPLATE_FIELDS:
        if field not in raw:
            failures.append(
                _fail("example-library-template-field", f"missing required template field: {field}", relative_path)
            )
    failures.extend(check_template_validation(raw, relative_path))

    body = raw.get("body")
    if not isinstance(body, dict):
        failures.append(_fail("example-library-template-body", "template body must be a mapping", relative_path))
        return failures
    failures.extend(check_template_body(entry, body, relative_path))
    return failures


def _check_pattern_file(path: Path, relative_path: str, *, surface: str, catalog_id: Any) -> list[PolicyFailure]:
    raw, failures = _load_yaml_file(path, relative_path)
    if raw is None:
        return failures
    failures.extend(_check_artifact_common(raw, relative_path, surface=surface, catalog_id=catalog_id, kind="pattern"))

    if "pattern" in raw and raw["pattern"] != PATTERN_VALUE:
        failures.append(_fail("example-library-pattern-kind", f"pattern must be {PATTERN_VALUE!r}", relative_path))
    for field in REQUIRED_PATTERN_FIELDS:
        if field not in raw:
            failures.append(
                _fail("example-library-pattern-field", f"missing required pattern field: {field}", relative_path)
            )

    for field in ("use_when", "required_fields", "authoring_steps", "validation"):
        if field in raw and not isinstance(raw[field], list):
            failures.append(_fail("example-library-pattern-field-type", f"{field} must be a list", relative_path))
    return failures


def _check_artifact_common(
    raw: dict[str, Any],
    relative_path: str,
    *,
    surface: str,
    catalog_id: Any,
    kind: str,
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    artifact_id = raw.get("id")
    if artifact_id != catalog_id:
        failures.append(
            _fail(
                f"example-library-{kind}-id",
                f"{kind} id must match catalog id {catalog_id!r}; got {artifact_id!r}",
                relative_path,
            )
        )
    if raw.get("surface") != surface:
        failures.append(
            _fail(
                f"example-library-{kind}-surface",
                f"{kind} surface must match catalog surface {surface!r}; got {raw.get('surface')!r}",
                relative_path,
            )
        )
    if "version" in raw and (not isinstance(raw["version"], int) or raw["version"] < 1):
        failures.append(_fail(f"example-library-{kind}-version", "version must be a positive integer", relative_path))
    for field in ("requirement_refs", "source_refs"):
        if field in raw and _str_list(raw[field]) is None:
            failures.append(
                _fail(f"example-library-{kind}-field-type", f"{field} must be a string list", relative_path)
            )
    requirement_refs = _str_list(raw.get("requirement_refs"))
    if requirement_refs is not None and REQUIREMENT_REF not in requirement_refs:
        failures.append(
            _fail(
                f"example-library-{kind}-requirement-ref",
                f"requirement_refs must include {REQUIREMENT_REF}",
                relative_path,
            )
        )
    summary = raw.get("summary")
    if not isinstance(summary, str) or len(summary.strip()) < 20:
        failures.append(_fail(f"example-library-{kind}-summary", "summary must be substantive", relative_path))
    return failures


def evaluate_example_library(repo_root: Path = REPO_ROOT) -> list[PolicyFailure]:
    raw, failures = _load_yaml_file(repo_root / CATALOG_RELATIVE_PATH, CATALOG_RELATIVE_PATH)
    if raw is None:
        return failures
    failures.extend(_check_top_level(raw))
    failures.extend(_check_surfaces(raw, repo_root=repo_root))
    return failures


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the AUT-806 example template and pattern library.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (defaults to the repo containing this file).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON failures.")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    failures = evaluate_example_library(args.repo_root)
    exceptions_file = args.repo_root / "tools" / "policy" / "exceptions.yaml"
    if exceptions_file.is_file():
        failures = apply_exceptions(failures, load_exceptions(args.repo_root))
    if failures:
        if args.json:
            print(failures_to_json(failures))
        else:
            for failure in failures:
                print(failure.render(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
