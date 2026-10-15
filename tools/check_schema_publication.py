#!/usr/bin/env python3
"""Verify the authoritative schema publication manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path("contracts/schema-publication-manifest.json")
SCHEMAS_PREFIX = "contracts/schemas/"
SCHEMA_VERSION = "schema-publication-manifest/v2"
LEGACY_SCHEMA_VERSION = "schema-publication-manifest/v1"
ENTRIES_DIRECTORY = "contracts/schema-publication/entries"
TOMBSTONES_DIRECTORY = "contracts/schema-publication/tombstones"
HASH_ALGORITHM = "sha256"
STABILITY_VALUES = {"draft", "stable"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

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


LAST_CHANGE_KEY = "last_change"
REMOVED_SCHEMAS_KEY = "removed_schemas"


@dataclass(frozen=True)
class ManifestEntry:
    contract_id: str
    schema_path: str
    stability: str
    content_hash: str
    schema: Any
    last_change: dict[str, Any] | None = None


def _published_schema_paths(repo_root: Path) -> set[str]:
    schemas_root = repo_root / "contracts" / "schemas"
    return {path.relative_to(repo_root).as_posix() for path in sorted(schemas_root.rglob("*.json"))}


def _load_manifest(repo_root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    manifest_file = repo_root / MANIFEST_PATH
    if not manifest_file.exists():
        return None, [f"schema publication manifest is missing: {MANIFEST_PATH.as_posix()}"]
    try:
        payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"schema publication manifest is not valid JSON: {exc.msg}"]
    if not isinstance(payload, dict):
        return None, ["schema publication manifest must be a JSON object"]
    if payload.get("schema_version") == LEGACY_SCHEMA_VERSION:
        return payload, []
    expected = {"schema_version", "hash_algorithm", "entries_directory", "tombstones_directory"}
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
        "hash_algorithm": payload.get("hash_algorithm"),
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
        relative = path.relative_to(repo_root).as_posix()
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"schema publication {record_kind} is not valid JSON: {relative}: {exc.msg}")
            continue
        if not isinstance(record, dict):
            failures.append(f"schema publication {record_kind} must be a JSON object: {relative}")
            continue
        identity = record.get("contract_id" if record_kind == "entry" else "schema_path")
        if not isinstance(identity, str) or path.stem != Path(identity).stem:
            failures.append(f"schema publication {record_kind} filename does not match its identity: {relative}")
            continue
        records.append(record)
    return records, failures


def load_schema_publication_catalog(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Load the normalized publication catalog from legacy or sharded storage."""

    payload, failures = _load_manifest(repo_root)
    if payload is None:
        raise ValueError("; ".join(failures))
    return payload


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _schema_content_digest(schema: Any) -> str:
    return hashlib.sha256(_canonical_json(schema).encode("utf-8")).hexdigest()


def schema_content_hash(path: Path) -> str:
    """Return the canonical JSON sha256 for a published schema file."""

    return _schema_content_digest(json.loads(path.read_text(encoding="utf-8")))


def _load_schema(path: Path, schema_path: str) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, f"schema manifest path is not valid JSON: {schema_path}: {exc.msg}"


def _validate_last_change(
    contract_id: str, value: Any, entry_content_hash: str
) -> tuple[list[str], dict[str, Any] | None]:
    """Validate a manifest entry's optional ``last_change`` ledger block.

    The block records the contract-facing rationale for the schema's current
    content (ADR-009 section 7: schema changes are governed contract edits, not
    regeneration side-effects). It must carry a non-empty ``summary`` and a
    ``content_hash`` equal to the entry's canonical schema hash, so a stale
    ledger (rationale left pointing at an older schema) cannot satisfy the gate.
    """
    if not isinstance(value, dict):
        return [f"schema manifest entry {contract_id} last_change must be a JSON object"], None
    failures: list[str] = []
    summary = value.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        failures.append(f"schema manifest entry {contract_id} last_change.summary must be a non-empty string")
    change_hash = value.get("content_hash")
    if not isinstance(change_hash, str) or not SHA256_RE.match(change_hash):
        failures.append(
            f"schema manifest entry {contract_id} last_change.content_hash must be a 64-character sha256 hex digest"
        )
    elif change_hash != entry_content_hash:
        failures.append(
            f"schema manifest entry {contract_id} last_change.content_hash {change_hash} does not match the schema "
            f"content_hash {entry_content_hash}; record the ledger entry against the current schema content"
        )
    if failures:
        return failures, None
    return [], {"summary": summary, "content_hash": change_hash}


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
        ["git", "ls-tree", "-r", "--name-only", "-z", revision, "--", directory],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return sorted(path for path in proc.stdout.split("\0") if path.endswith(".json"))


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
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None, f"base schema publication manifest at {base_rev} is not valid JSON"
    if not isinstance(payload, dict):
        return None, f"base schema publication manifest at {base_rev} must be a JSON object"
    if payload.get("schema_version") == SCHEMA_VERSION:
        directory = payload.get("entries_directory")
        if not isinstance(directory, str):
            return None, f"base schema publication manifest at {base_rev} has no entries directory"
        paths = _git_paths(repo_root, base_rev, directory)
        if paths is None:
            return None, f"base schema publication records at {base_rev} could not be listed"
        entries: list[dict[str, Any]] = []
        for path in paths:
            record_text = _git_show(repo_root, f"{base_rev}:{path}")
            try:
                record = json.loads(record_text) if record_text is not None else None
            except json.JSONDecodeError:
                record = None
            if not isinstance(record, dict):
                return None, f"base schema publication record at {base_rev}:{path} is invalid"
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
            base_schema = json.loads(base_text)
        except json.JSONDecodeError:
            failures.append(f"base schema for {entry.contract_id} at {base_rev}:{base_path} is not valid JSON")
            continue
        if _schema_content_digest(base_schema) == entry.content_hash:
            continue
        breaking_changes = _schema_breaking_changes(base_schema, entry.schema)
        if breaking_changes:
            failures.append(
                f"stable schema {entry.contract_id} changed incompatibly without a version bump: "
                f"{'; '.join(breaking_changes)}"
            )
    return failures


def _removal_ledger(payload: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Parse and validate the normalized ``removed_schemas`` tombstone list.

    A removed schema has no current ``schemas`` entry to carry a ``last_change``
    block, so its contract-facing rationale is recorded as a tombstone keyed by
    ``schema_path`` (ADR-009 section 7: a contract removal is a governed edit,
    not a silent regeneration side-effect). Each tombstone must carry a
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


def _check_change_ledger(
    repo_root: Path,
    current_entries: Iterable[ManifestEntry],
    *,
    base_rev: str,
    base_entries: dict[str, dict[str, Any]] | None,
    removal_tombstones: dict[str, dict[str, Any]],
) -> list[str]:
    """Require a contract-facing change-ledger entry whenever a published schema's
    content changed relative to ``base_rev`` (or is newly published or removed).

    The manifest ``last_change`` block is what turns a schema change into a
    reviewed contract edit rather than a silent regeneration side-effect
    (ADR-009 section 7). The per-entry shape check already rejects a stale or
    malformed ledger; this gate adds the "a change must carry one at all" rule,
    keyed by the same ``schema_path`` identity used elsewhere. Removals have no
    current entry to inspect, so they are gated separately against the base
    publication catalog and must carry an independent tombstone record.
    """
    failures: list[str] = []
    for entry in current_entries:
        base_text = _git_show(repo_root, f"{base_rev}:{entry.schema_path}")
        if base_text is not None:
            try:
                base_schema = json.loads(base_text)
            except json.JSONDecodeError:
                base_schema = None
            if base_schema is not None and _schema_content_digest(base_schema) == entry.content_hash:
                continue
        if entry.last_change is None:
            failures.append(
                f"published schema {entry.contract_id} changed without a contract-facing change description; "
                f"add a '{LAST_CHANGE_KEY}' entry (summary + current content_hash) to its record under "
                f"{ENTRIES_DIRECTORY} "
                "recording why the contract changed"
            )

    failures.extend(
        _check_removal_ledger(
            current_entries,
            base_entries=base_entries,
            removal_tombstones=removal_tombstones,
        )
    )
    return failures


def _check_removal_ledger(
    current_entries: Iterable[ManifestEntry],
    *,
    base_entries: dict[str, dict[str, Any]] | None,
    removal_tombstones: dict[str, dict[str, Any]],
) -> list[str]:
    """Require a ``removed_schemas`` tombstone for every published schema that
    existed at ``base_rev`` and is gone from the current manifest.

    Without this, a PR can delete ``contracts/schemas/foo.json`` and drop its
    manifest entry: the file-level Rego rule is satisfied because the manifest
    was touched, and ``_check_change_ledger`` has no current entry to inspect,
    so the removal lands without the contract-facing ledger this gate requires
    for every other schema change (ADR-009 section 7).
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
    except (OSError, ValueError):
        return None, f"schema manifest path resolves outside contracts/schemas/: {schema_path}"
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
    if payload.get("hash_algorithm") != HASH_ALGORITHM:
        failures.append(f"schema manifest hash_algorithm must be {HASH_ALGORITHM!r}")

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
        content_hash = entry.get("content_hash")
        if not isinstance(contract_id, str) or not contract_id:
            failures.append(f"schema manifest entry {index} contract_id must be a non-empty string")
            continue
        if not isinstance(schema_path, str) or not schema_path:
            failures.append(f"schema manifest entry {contract_id} schema_path must be a non-empty string")
            continue
        if stability not in STABILITY_VALUES:
            failures.append(f"schema manifest entry {contract_id} stability must be one of: draft, stable")
        if not isinstance(content_hash, str) or not SHA256_RE.match(content_hash):
            failures.append(
                f"schema manifest entry {contract_id} content_hash must be a 64-character sha256 hex digest"
            )

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
        if isinstance(content_hash, str) and SHA256_RE.match(content_hash):
            actual_hash = _schema_content_digest(schema)
            if actual_hash != content_hash:
                failures.append(
                    f"schema manifest entry {contract_id} content_hash {content_hash} does not match "
                    f"canonical schema hash {actual_hash}"
                )
        parsed_last_change: dict[str, Any] | None = None
        if isinstance(content_hash, str) and SHA256_RE.match(content_hash) and LAST_CHANGE_KEY in entry:
            last_change_failures, parsed_last_change = _validate_last_change(
                contract_id, entry[LAST_CHANGE_KEY], content_hash
            )
            failures.extend(last_change_failures)
        if stability in STABILITY_VALUES and isinstance(content_hash, str) and SHA256_RE.match(content_hash):
            validated_entries.append(
                ManifestEntry(
                    contract_id=contract_id,
                    schema_path=schema_path,
                    stability=stability,
                    content_hash=content_hash,
                    schema=schema,
                    last_change=parsed_last_change,
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
            _check_change_ledger(
                repo_root,
                validated_entries,
                base_rev=base_rev,
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
    failures = validate_schema_publication_manifest(REPO_ROOT, base_rev=args.base_rev)
    if failures:
        for failure in failures:
            print(f"[schema-publication] {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
