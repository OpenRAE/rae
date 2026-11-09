#!/usr/bin/env python3
"""Verify the authoritative schema publication manifest."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from raes_contracts.errors import InvalidInputError  # noqa: E402
from raes_contracts.operational_logging import run_application  # noqa: E402

MANIFEST_PATH = Path("contracts/schema-publication-manifest.json")
SCHEMAS_PREFIX = "contracts/schemas/"
SCHEMA_VERSION = "schema-publication-manifest/v2"
LEGACY_SCHEMA_VERSION = "schema-publication-manifest/v1"
ENTRIES_DIRECTORY = "contracts/schema-publication/entries"
TOMBSTONES_DIRECTORY = "contracts/schema-publication/tombstones"
STABILITY_VALUES = {"draft", "stable"}
RETIRED_MANIFEST_KEYS = ("hash_algorithm",)
RETIRED_ENTRY_KEYS = ("content_hash", "last_change")

JSON_SCHEMA_ANNOTATION_KEYS = {
    "$comment",
    "$id",
    "$schema",
    "deprecated",
    "description",
    "examples",
    "readOnly",
    "title",
    "writeOnly",
}
OBJECT_COMPATIBILITY_CHILD_KEYS = {
    "additionalProperties",
    "patternProperties",
    "properties",
    "required",
}
PROPERTY_SPECIAL_COMPATIBILITY_KEYS = {"default", "enum"}
_MISSING = object()


REMOVED_SCHEMAS_KEY = "removed_schemas"


@dataclass(frozen=True)
class ManifestEntry:
    contract_id: str
    schema_path: str
    stability: str
    schema: Any


def _published_schema_paths(repo_root: Path) -> set[str]:
    schemas_root = repo_root / "contracts" / "schemas"
    return {path.relative_to(repo_root).as_posix() for path in sorted(schemas_root.rglob("*.json"))}


def _json_integer(literal: str) -> int:
    # The decoder passes only JSON integer literals, so int() fails only beyond the interpreter digit limit.
    try:
        return int(literal)
    except ValueError as exc:
        raise InvalidInputError("schema publication JSON contains an integer beyond the digit limit") from exc


def _parse_json(text: str) -> object:
    """Decode JSON text; raise ``InvalidInputError`` for a value the decoder cannot build."""

    try:
        return json.loads(text, parse_int=_json_integer)
    except RecursionError as exc:
        # Without a depth limit, the recursive decoder stops at the interpreter recursion limit.
        raise InvalidInputError("schema publication JSON nests beyond the decoder depth") from exc


def _load_manifest(repo_root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    manifest_file = repo_root / MANIFEST_PATH
    if not manifest_file.exists():
        return None, [f"schema publication manifest is missing: {MANIFEST_PATH.as_posix()}"]
    try:
        payload = _parse_json(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"schema publication manifest is not valid JSON: {exc.msg}"]
    except InvalidInputError as exc:
        return None, [f"schema publication manifest is not valid JSON: {exc}"]
    if not isinstance(payload, dict):
        return None, ["schema publication manifest must be a JSON object"]
    if payload.get("schema_version") == LEGACY_SCHEMA_VERSION:
        return payload, []
    expected = {"schema_version", "entries_directory", "tombstones_directory"}
    if set(payload) != expected:
        return None, [f"schema publication manifest fields must exactly match: {sorted(expected)}"]
    records, record_failures = _load_record_directory(
        repo_root,
        payload.get("entries_directory"),
        expected_directory=ENTRIES_DIRECTORY,
        record_kind="entry",
    )
    tombstones, tombstone_failures = _load_record_directory(
        repo_root,
        payload.get("tombstones_directory"),
        expected_directory=TOMBSTONES_DIRECTORY,
        record_kind="tombstone",
        allow_empty=True,
    )
    failures = [*record_failures, *tombstone_failures]
    if failures:
        return None, failures
    return {
        "schema_version": payload.get("schema_version"),
        "schemas": records,
        REMOVED_SCHEMAS_KEY: tombstones,
    }, []


def _load_record_directory(
    repo_root: Path,
    value: object,
    *,
    expected_directory: str,
    record_kind: str,
    allow_empty: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    if value != expected_directory:
        return [], [f"schema publication {record_kind} directory must be {expected_directory!r}"]
    root = (repo_root / expected_directory).resolve()
    try:
        root.relative_to(repo_root.resolve())
    except ValueError:
        return [], [f"schema publication {record_kind} directory resolves outside the repository"]
    if not root.is_dir():
        return [], [f"schema publication {record_kind} directory is missing: {expected_directory}"]
    paths = sorted(root.glob("*.json"))
    if not paths and not allow_empty:
        return [], [f"schema publication {record_kind} directory is empty: {expected_directory}"]
    records: list[dict[str, Any]] = []
    failures: list[str] = []
    for path in paths:
        record, failure = _load_record(path, path.relative_to(repo_root).as_posix(), record_kind)
        if failure is not None:
            failures.append(failure)
        else:
            records.append(record)
    return records, failures


def _load_record(path: Path, relative: str, record_kind: str) -> tuple[dict[str, Any], str | None]:
    """Return one publication record, or a failure that names why it cannot be used."""
    try:
        record = _parse_json(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, InvalidInputError) as exc:
        detail = exc.msg if isinstance(exc, json.JSONDecodeError) else exc
        return (
            {},
            f"schema publication {record_kind} is not valid JSON: {relative}: {detail}",
        )
    if not isinstance(record, dict):
        return {}, f"schema publication {record_kind} must be a JSON object: {relative}"
    identity = record.get("contract_id" if record_kind == "entry" else "schema_path")
    matches = isinstance(identity, str) and path.stem == Path(identity).stem
    return (
        record,
        None if matches else f"schema publication {record_kind} filename does not match its identity: {relative}",
    )


def load_schema_publication_catalog(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Load the normalized publication catalog from legacy or sharded storage.

    Raise ``InvalidInputError`` when the manifest or one of its records is
    missing or malformed.
    """

    payload, failures = _load_manifest(repo_root)
    if payload is None:
        raise InvalidInputError("; ".join(failures))
    return payload


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load_schema(path: Path, schema_path: str) -> tuple[Any | None, str | None]:
    try:
        return _parse_json(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, f"schema manifest path is not valid JSON: {schema_path}: {exc.msg}"
    except InvalidInputError as exc:
        return None, f"schema manifest path is not valid JSON: {schema_path}: {exc}"


def _git_show(repo_root: Path, gitref: str) -> str | None:
    proc = subprocess.run(
        ["git", "show", gitref],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def _git_paths(repo_root: Path, revision: str, directory: str) -> list[str] | None:
    proc = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", revision, "--", directory],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return sorted(path for path in proc.stdout.splitlines() if path.endswith(".json"))


def _manifest_entries(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = payload.get("schemas")
    if not isinstance(entries, list):
        return {}
    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        contract_id = entry.get("contract_id")
        if isinstance(contract_id, str):
            by_id[contract_id] = entry
    return by_id


def _json_path(base: str, *parts: str) -> str:
    escaped = [part.replace("~", "~0").replace("/", "~1") for part in parts]
    return "/".join([part for part in (base, *escaped) if part])


def _object_schema_nodes(schema: Any, path: str = "") -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    if isinstance(schema, dict):
        if any(key in schema for key in OBJECT_COMPATIBILITY_CHILD_KEYS):
            nodes[path] = schema
        for key, value in schema.items():
            if isinstance(value, dict):
                nodes.update(_object_schema_nodes(value, _json_path(path, key)))
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    nodes.update(_object_schema_nodes(item, _json_path(path, key, str(index))))
    return nodes


def _without_annotations(value: Any) -> Any:
    if isinstance(value, dict):
        ignored = set(JSON_SCHEMA_ANNOTATION_KEYS)
        return {key: _without_annotations(item) for key, item in sorted(value.items()) if key not in ignored}
    if isinstance(value, list):
        return [_without_annotations(item) for item in value]
    return value


def _property_core(value: Any) -> Any:
    if not isinstance(value, dict):
        return _without_annotations(value)
    ignored = set(JSON_SCHEMA_ANNOTATION_KEYS)
    ignored.update(OBJECT_COMPATIBILITY_CHILD_KEYS)
    ignored.update(PROPERTY_SPECIAL_COMPATIBILITY_KEYS)
    return {key: _without_annotations(item) for key, item in sorted(value.items()) if key not in ignored}


def _enum_values(value: Any) -> list[Any] | None:
    if not isinstance(value, dict):
        return None
    enum = value.get("enum")
    if not isinstance(enum, list):
        return None
    return enum


def _enum_missing_values(old_enum: list[Any], new_enum: list[Any]) -> list[Any]:
    new_keys = {_canonical_json(value) for value in new_enum}
    return [value for value in old_enum if _canonical_json(value) not in new_keys]


def _render_enum_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return _canonical_json(value)


def _property_breaking_changes(pointer: str, old_property: Any, new_property: Any) -> list[str]:
    changes: list[str] = []
    if not isinstance(old_property, dict) or not isinstance(new_property, dict):
        if _without_annotations(old_property) != _without_annotations(new_property):
            changes.append(f"{pointer} schema changed")
        return changes

    old_default = old_property.get("default", _MISSING)
    new_default = new_property.get("default", _MISSING)
    if old_default != new_default:
        changes.append(f"{pointer} default changed")

    old_enum = _enum_values(old_property)
    new_enum = _enum_values(new_property)
    if old_enum is None and new_enum is not None:
        changes.append(f"{pointer} enum constraint added")
    elif old_enum is not None and new_enum is None:
        changes.append(f"{pointer} enum constraint removed")
    elif old_enum is not None and new_enum is not None:
        missing_values = _enum_missing_values(old_enum, new_enum)
        if missing_values:
            rendered = ", ".join(_render_enum_value(value) for value in missing_values)
            changes.append(f"{pointer} enum values removed: {rendered}")

    if _property_core(old_property) != _property_core(new_property):
        changes.append(f"{pointer} schema changed")
    return changes


def _required_values(schema: dict[str, Any]) -> set[str]:
    values = schema.get("required")
    if not isinstance(values, list):
        return set()
    return {value for value in values if isinstance(value, str)}


def _properties(schema: dict[str, Any]) -> dict[str, Any]:
    values = schema.get("properties")
    if not isinstance(values, dict):
        return {}
    return values


def _schema_breaking_changes(old_schema: Any, new_schema: Any) -> list[str]:
    changes: list[str] = []
    old_nodes = _object_schema_nodes(old_schema)
    new_nodes = _object_schema_nodes(new_schema)

    for pointer in sorted(old_nodes):
        old_node = old_nodes[pointer]
        new_node = new_nodes.get(pointer)
        if new_node is None:
            changes.append(f"{pointer or '<root>'} object schema removed")
            continue

        old_properties = _properties(old_node)
        new_properties = _properties(new_node)
        for name in sorted(set(old_properties) - set(new_properties)):
            changes.append(f"{_json_path(pointer, 'properties', name)} removed")
        for name in sorted(set(old_properties) & set(new_properties)):
            changes.extend(
                _property_breaking_changes(
                    _json_path(pointer, "properties", name),
                    old_properties[name],
                    new_properties[name],
                )
            )

        old_required = _required_values(old_node)
        new_required = _required_values(new_node)
        for name in sorted(new_required - old_required):
            changes.append(f"{_json_path(pointer, 'required', name)} newly required")

        old_additional = old_node.get("additionalProperties")
        new_additional = new_node.get("additionalProperties")
        if old_additional is not False and new_additional is False:
            changes.append(f"{pointer or '<root>'} additionalProperties tightened")

    return changes


def _load_base_manifest(repo_root: Path, base_rev: str) -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    text = _git_show(repo_root, f"{base_rev}:{MANIFEST_PATH.as_posix()}")
    if text is None:
        return None, f"base schema publication manifest is missing at {base_rev}"
    try:
        payload = _parse_json(text)
    except json.JSONDecodeError, InvalidInputError:
        return None, f"base schema publication manifest at {base_rev} is not valid JSON"
    if not isinstance(payload, dict):
        return (
            None,
            f"base schema publication manifest at {base_rev} must be a JSON object",
        )
    if payload.get("schema_version") == SCHEMA_VERSION:
        directory = payload.get("entries_directory")
        if not isinstance(directory, str):
            return (
                None,
                f"base schema publication manifest at {base_rev} has no entries directory",
            )
        paths = _git_paths(repo_root, base_rev, directory)
        if paths is None:
            return (
                None,
                f"base schema publication records at {base_rev} could not be listed",
            )
        entries: list[dict[str, Any]] = []
        for path in paths:
            record_text = _git_show(repo_root, f"{base_rev}:{path}")
            try:
                record = _parse_json(record_text) if record_text is not None else None
            except json.JSONDecodeError, InvalidInputError:
                record = None
            if not isinstance(record, dict):
                return (
                    None,
                    f"base schema publication record at {base_rev}:{path} is invalid",
                )
            entries.append(record)
        payload = {"schemas": entries}
    return _manifest_entries(payload), None


def _check_stable_schema_changes(
    repo_root: Path,
    current_entries: Iterable[ManifestEntry],
    *,
    base_rev: str,
) -> list[str]:
    failures: list[str] = []
    stable_entries = [entry for entry in current_entries if entry.stability == "stable"]
    if not stable_entries:
        return failures
    base_entries, base_error = _load_base_manifest(repo_root, base_rev)
    if base_error is not None or base_entries is None:
        return [base_error or f"base schema publication manifest at {base_rev} could not be read"]
    for entry in stable_entries:
        base_entry = base_entries.get(entry.contract_id)
        if not base_entry or base_entry.get("stability") != "stable":
            continue
        base_path = base_entry.get("schema_path")
        if not isinstance(base_path, str):
            continue
        if base_path != entry.schema_path:
            failures.append(
                f"stable schema {entry.contract_id} changed schema_path without a version bump: "
                f"{base_path} -> {entry.schema_path}"
            )
            continue
        base_text = _git_show(repo_root, f"{base_rev}:{base_path}")
        if base_text is None:
            failures.append(f"base schema for {entry.contract_id} is missing at {base_rev}: {base_path}")
            continue
        try:
            base_schema = _parse_json(base_text)
        except json.JSONDecodeError, InvalidInputError:
            failures.append(f"base schema for {entry.contract_id} at {base_rev}:{base_path} is not valid JSON")
            continue
        try:
            if base_schema == entry.schema:
                continue
            breaking_changes = _schema_breaking_changes(base_schema, entry.schema)
        except RecursionError:
            # The comparison walks the schemas recursively; the JSON decoder accepts deeper documents.
            failures.append(
                f"stable schema {entry.contract_id} nests beyond the depth that the compatibility check can compare"
            )
            continue
        if breaking_changes:
            failures.append(
                f"stable schema {entry.contract_id} changed incompatibly without a version bump: "
                f"{'; '.join(breaking_changes)}"
            )
    return failures


def _removal_ledger(
    payload: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Parse and validate the normalized ``removed_schemas`` tombstone list.

    A removed schema has no current ``schemas`` entry, so its contract-facing
    rationale is recorded as a tombstone keyed by ``schema_path`` (ADR-009
    section 7: a contract removal is a governed edit, not a silent
    regeneration side-effect). Each tombstone must carry a
    non-empty ``summary``; the ``schema_path`` is what links the tombstone back
    to the schema that existed at ``base_rev``.
    """
    value = payload.get(REMOVED_SCHEMAS_KEY)
    if value is None:
        return {}, []
    if not isinstance(value, list):
        return {}, [f"schema manifest {REMOVED_SCHEMAS_KEY} must be a JSON array"]
    failures: list[str] = []
    tombstones: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            failures.append(f"schema manifest {REMOVED_SCHEMAS_KEY} entry {index} must be a JSON object")
            continue
        schema_path = item.get("schema_path")
        if not isinstance(schema_path, str) or not schema_path:
            failures.append(
                f"schema manifest {REMOVED_SCHEMAS_KEY} entry {index} schema_path must be a non-empty string"
            )
            continue
        summary = item.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            failures.append(
                f"schema manifest {REMOVED_SCHEMAS_KEY} entry {schema_path} summary must be a non-empty string"
            )
            continue
        tombstones[schema_path] = item
    return tombstones, failures


def _check_removal_ledger(
    current_entries: Iterable[ManifestEntry],
    *,
    base_entries: dict[str, dict[str, Any]] | None,
    removal_tombstones: dict[str, dict[str, Any]],
) -> list[str]:
    """Require a ``removed_schemas`` tombstone for every published schema that
    existed at ``base_rev`` and is gone from the current manifest.

    Without this, a PR can delete ``contracts/schemas/foo.json`` and drop its
    manifest entry, and the removal lands without a recorded reason
    (ADR-061).
    """
    if not base_entries:
        return []
    base_paths = {
        base_path
        for base_entry in base_entries.values()
        if isinstance(base_path := base_entry.get("schema_path"), str) and base_path.startswith(SCHEMAS_PREFIX)
    }
    current_paths = {entry.schema_path for entry in current_entries}
    failures: list[str] = []
    for removed_path in sorted(base_paths - current_paths):
        if removed_path not in removal_tombstones:
            failures.append(
                f"published schema {removed_path} was removed without a contract-facing removal description; "
                f"add a tombstone record (schema_path + summary) under {TOMBSTONES_DIRECTORY} "
                "recording why the contract was removed"
            )
    return failures


def _safe_schema_path(repo_root: Path, schema_path: str) -> tuple[Path | None, str | None]:
    schemas_root = (repo_root / SCHEMAS_PREFIX).resolve()
    candidate = repo_root / schema_path
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(schemas_root)
    except OSError, ValueError:
        return (
            None,
            f"schema manifest path resolves outside contracts/schemas/: {schema_path}",
        )
    return resolved, None


def validate_schema_publication_manifest(
    repo_root: Path = REPO_ROOT,
    *,
    base_rev: str | None = None,
) -> list[str]:
    """Return validation failures for the checked-in schema publication manifest."""

    payload, failures = _load_manifest(repo_root)
    if payload is None:
        return failures

    if payload.get("schema_version") not in {SCHEMA_VERSION, LEGACY_SCHEMA_VERSION}:
        failures.append(f"schema manifest schema_version must be {SCHEMA_VERSION!r} or {LEGACY_SCHEMA_VERSION!r}")
    for key in RETIRED_MANIFEST_KEYS:
        if key in payload:
            failures.append(f"schema manifest must not record {key}; git holds schema history")

    entries = payload.get("schemas")
    if not isinstance(entries, list) or not entries:
        failures.append("schema manifest must define a non-empty schemas array")
        return failures

    manifest_paths: set[str] = set()
    seen_manifest_paths: set[str] = set()
    manifest_ids: set[str] = set()
    validated_entries: list[ManifestEntry] = []
    previous_id = ""
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            failures.append(f"schema manifest entry {index} must be an object")
            continue

        contract_id = entry.get("contract_id")
        schema_path = entry.get("schema_path")
        stability = entry.get("stability")
        if not isinstance(contract_id, str) or not contract_id:
            failures.append(f"schema manifest entry {index} contract_id must be a non-empty string")
            continue
        if not isinstance(schema_path, str) or not schema_path:
            failures.append(f"schema manifest entry {contract_id} schema_path must be a non-empty string")
            continue
        if stability not in STABILITY_VALUES:
            failures.append(f"schema manifest entry {contract_id} stability must be one of: draft, stable")
        for key in RETIRED_ENTRY_KEYS:
            if key in entry:
                failures.append(f"schema manifest entry {contract_id} must not record {key}; git holds schema history")

        if contract_id <= previous_id:
            failures.append("schema manifest entries must be sorted by contract_id")
        previous_id = contract_id

        if contract_id in manifest_ids:
            failures.append(f"schema manifest contains duplicate contract_id: {contract_id}")
        manifest_ids.add(contract_id)

        if schema_path in seen_manifest_paths:
            failures.append(f"schema manifest contains duplicate schema_path: {schema_path}")
        seen_manifest_paths.add(schema_path)

        if schema_path != Path(schema_path).as_posix() or schema_path.startswith(("/", "../")):
            failures.append(f"schema manifest path must be a normalized repo-relative path: {schema_path}")
            continue
        if not schema_path.startswith(SCHEMAS_PREFIX):
            failures.append(f"schema manifest path must be under contracts/schemas/: {schema_path}")
            continue
        if not schema_path.endswith(".json"):
            failures.append(f"schema manifest path must point to a JSON schema file: {schema_path}")
            continue

        path, path_error = _safe_schema_path(repo_root, schema_path)
        if path_error is not None or path is None:
            failures.append(path_error or f"schema manifest path is unsafe: {schema_path}")
            continue
        manifest_paths.add(schema_path)
        if not path.is_file():
            failures.append(f"schema manifest path does not exist: {schema_path}")
            continue
        if path.stem != contract_id:
            failures.append(f"schema manifest contract_id {contract_id!r} must match schema filename {path.stem!r}")
        schema, schema_error = _load_schema(path, schema_path)
        if schema_error is not None:
            failures.append(schema_error)
            continue
        if stability in STABILITY_VALUES:
            validated_entries.append(
                ManifestEntry(
                    contract_id=contract_id,
                    schema_path=schema_path,
                    stability=stability,
                    schema=schema,
                )
            )

    published_paths = _published_schema_paths(repo_root)
    for path in sorted(published_paths - manifest_paths):
        failures.append(f"schema manifest is missing published schema: {path}")
    for path in sorted(manifest_paths - published_paths):
        if path.startswith(SCHEMAS_PREFIX):
            failures.append(f"schema manifest references unpublished schema: {path}")

    removal_tombstones, tombstone_failures = _removal_ledger(payload)
    failures.extend(tombstone_failures)
    for removed_path in sorted(removal_tombstones):
        if removed_path in manifest_paths:
            failures.append(
                f"schema manifest {REMOVED_SCHEMAS_KEY} tombstone {removed_path} refers to a still-published schema"
            )

    if not failures and base_rev:
        failures.extend(_check_stable_schema_changes(repo_root, validated_entries, base_rev=base_rev))
        base_entries, _ = _load_base_manifest(repo_root, base_rev)
        failures.extend(
            _check_removal_ledger(
                validated_entries,
                base_entries=base_entries,
                removal_tombstones=removal_tombstones,
            )
        )

    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the authoritative schema publication manifest.")
    parser.add_argument("--base-rev", help="Compare stable schemas against a base git revision.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        failures = validate_schema_publication_manifest(REPO_ROOT, base_rev=args.base_rev)
    except (OSError, UnicodeDecodeError, InvalidInputError) as exc:
        print(f"[schema-publication] {exc}", file=sys.stderr)
        return 1
    if failures:
        for failure in failures:
            print(f"[schema-publication] {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
