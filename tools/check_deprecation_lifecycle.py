#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Structural gate for the GOV-902 ecosystem deprecation and lifecycle rules.

ADR-075 ("Ecosystem Versioning, Deprecation, and Migration Governance") and
its normative spec ``specs/evolution/versioning-deprecation-and-migration.md``
decide that deprecations must be explicit, complete records so that
supersession and removal are predictable and reviewable. GOV-902 says the
ecosystem **shall** define those deprecation and lifecycle rules.

The canonical, reviewable record surface lives in
``specs/evolution/deprecation-records.yaml`` (per ADR-009, normative prose and
its data live under ``specs/``). This checker pins the record contract: every
record must name the seven fields the spec requires -- exact surface and
identifier, first-notice version, replacement or explicit no-replacement
rationale, migration reference, notice window / removal-eligibility rule, and
verification evidence that the old surface stays supported (plus a reviewed
security exception if the ordinary window is shortened). Removal
(``status: removed``) is allowed only with a removal record, and for a
published JSON Schema surface the removal must reference an existing
schema-publication tombstone record (ADR-061),
not a duplicate mechanism.

This is a CI-time governance gate over static data, not a runtime lifecycle
registry, migration service, persistence layer, or endpoint (ADR-075 forbids
those). Failures use ``tools.policy.common.PolicyFailure`` and the CLI honours
``--json`` and the shared ``tools/policy/exceptions.yaml`` waiver mechanism,
matching the other policy gates (``check_authority_boundary.py``,
``check_adr_immutability.py``, ``check_assurance_policy.py``).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml

from tools.check_schema_publication import load_schema_publication_catalog
from tools.policy.common import (
    PolicyFailure,
    apply_exceptions,
    failures_to_json,
    load_exceptions,
)

# --------------------------------------------------------------------------- #
# Canonical paths and pinned invariants. Test code imports these directly so   #
# a rename here surfaces in the test suite rather than silently in production. #
# --------------------------------------------------------------------------- #

DEPRECATION_RECORDS_RELATIVE_PATH = "specs/evolution/deprecation-records.yaml"
SPEC_RELATIVE_PATH = "specs/evolution/versioning-deprecation-and-migration.md"
SCHEMA_PUBLICATION_MANIFEST = "contracts/schema-publication-manifest.json"

REQUIREMENT_REF = "GOV-902"
ADR_REF = "ADR-075"
POLICY_VALUE = "ecosystem-deprecation-records"

# Surface-class keys, bound to the rows of the surface-class matrix in
# specs/evolution/versioning-deprecation-and-migration.md. A record may not
# name a surface the policy does not recognise; extending the matrix with a new
# family adds a key here (and a row + owner in the spec), which is the
# documented extension seam.
SURFACE_CLASSES: frozenset[str] = frozenset(
    {
        "python-distribution",
        "published-json-schema",
        "closed-contract-dto",
        "processor-backend-support",
        "apparatus-identity",
        "sdl-scenario-module",
        "experiment-artifact",
        "adr",
        "ground-control-requirement",
    }
)

STATUSES: frozenset[str] = frozenset({"deprecated", "removed"})

# The retention floor: record ids that MUST remain present in the ledger. A
# deprecation record is lifecycle history, so it may not silently disappear --
# once a construct is deprecated, that fact is permanent (its `status` may
# later advance to `removed`, but its identity is retained). Pinning the known
# ids here means an empty or truncated ledger fails the gate, mirroring the
# canonical-floor pattern the authority-boundary gate uses for its roots and
# artifact families. Retiring a record id is a deliberate, reviewable edit to
# this floor -- exactly the predictability GOV-902 requires.
CANONICAL_DEPRECATION_RECORD_IDS: frozenset[str] = frozenset(
    {
        "legacy-python-distribution",
        "sdl-import-path-field",
        "sdl-domain-classification-fields",
    }
)

# The published-schema surface is the only one whose removal is governed by a
# machine-readable tombstone (ADR-061). A `removed` record on this surface must
# point at an existing tombstone rather than asserting removal in prose.
_PUBLISHED_SCHEMA_SURFACE = "published-json-schema"

_REQUIRED_TOP_LEVEL_FIELDS: tuple[str, ...] = (
    "policy",
    "requirement_refs",
    "adr_refs",
    "spec",
    "records",
)

# Fields every record must carry regardless of status. `replacement` is handled
# separately (exactly one of replacement / no_replacement_rationale).
_REQUIRED_RECORD_FIELDS: tuple[str, ...] = (
    "id",
    "surface_class",
    "identifier",
    "status",
    "first_notice",
    "migration_reference",
    "notice_window",
    "verification_evidence",
)

_SECURITY_EXCEPTION_FIELDS: tuple[str, ...] = (
    "affected_versions",
    "impact",
    "mitigation",
    "migration",
    "review_authority",
)


# --------------------------------------------------------------------------- #
# Helpers.                                                                     #
# --------------------------------------------------------------------------- #


def _fail(rule_id: str, message: str, path: str | None = None) -> PolicyFailure:
    return PolicyFailure(rule_id, message, path)


def _is_str(value: object) -> bool:
    return isinstance(value, str)


def _nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _str_list(value: object) -> list[str] | None:
    """Return ``value`` as a list of strings, or None if it is not one.

    A list with a non-string element is rejected so the gate does not silently
    coerce ``[GOV-902, 17]`` into strings and keep passing.
    """
    if not isinstance(value, list):
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return list(value)


# --------------------------------------------------------------------------- #
# Top-level shape and references.                                             #
# --------------------------------------------------------------------------- #


def _check_top_level(raw: dict, source_path: str) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for field in _REQUIRED_TOP_LEVEL_FIELDS:
        if field not in raw:
            failures.append(
                _fail(
                    "deprecation-records-field",
                    f"required top-level field is missing: {field}",
                    source_path,
                )
            )

    if "policy" in raw and not _is_str(raw["policy"]):
        failures.append(
            _fail(
                "deprecation-records-field-type",
                f"policy must be a string; got {type(raw['policy']).__name__}",
                source_path,
            )
        )
    elif "policy" in raw and raw["policy"] != POLICY_VALUE:
        failures.append(
            _fail(
                "deprecation-records-policy-value",
                f"policy must equal {POLICY_VALUE!r}; got {raw['policy']!r}",
                source_path,
            )
        )

    requirement_refs = raw.get("requirement_refs")
    if "requirement_refs" in raw and _str_list(requirement_refs) is None:
        failures.append(
            _fail(
                "deprecation-records-field-type",
                "requirement_refs must be a list of strings",
                source_path,
            )
        )
    elif _str_list(requirement_refs) is not None and REQUIREMENT_REF not in requirement_refs:
        failures.append(
            _fail(
                "deprecation-records-requirement-ref",
                f"requirement_refs must include {REQUIREMENT_REF}; got {requirement_refs!r}",
                source_path,
            )
        )

    adr_refs = raw.get("adr_refs")
    if "adr_refs" in raw and _str_list(adr_refs) is None:
        failures.append(
            _fail(
                "deprecation-records-field-type",
                "adr_refs must be a list of strings",
                source_path,
            )
        )
    elif _str_list(adr_refs) is not None and ADR_REF not in adr_refs:
        failures.append(
            _fail(
                "deprecation-records-adr-ref",
                f"adr_refs must include {ADR_REF}; got {adr_refs!r}",
                source_path,
            )
        )

    if "spec" in raw and not _nonempty_str(raw["spec"]):
        failures.append(
            _fail(
                "deprecation-records-field-type",
                "spec must be a non-empty string path",
                source_path,
            )
        )

    if "records" in raw and not isinstance(raw["records"], list):
        failures.append(
            _fail(
                "deprecation-records-field-type",
                f"records must be a list; got {type(raw['records']).__name__}",
                source_path,
            )
        )
    return failures


def _check_spec_present(repo_root: Path, raw: dict, source_path: str) -> list[PolicyFailure]:
    spec = raw.get("spec")
    if not _nonempty_str(spec):
        return []  # type/shape failure already reported
    if not (repo_root / spec).is_file():
        return [
            _fail(
                "deprecation-records-spec-missing",
                f"spec path {spec!r} does not exist on disk",
                source_path,
            )
        ]
    return []


# --------------------------------------------------------------------------- #
# Per-record checks.                                                          #
# --------------------------------------------------------------------------- #


def _load_removed_schema_paths(repo_root: Path) -> set[str]:
    """Return the schema paths in normalized publication tombstone records."""
    try:
        manifest = load_schema_publication_catalog(repo_root)
    except (OSError, ValueError):
        return set()
    removed = manifest.get("removed_schemas")
    if not isinstance(removed, list):
        return set()
    paths: set[str] = set()
    for entry in removed:
        if isinstance(entry, dict) and _nonempty_str(entry.get("schema_path")):
            paths.add(entry["schema_path"])
    return paths


def _check_security_exception(entry: dict, index: int, source_path: str) -> list[PolicyFailure]:
    exception = entry.get("security_exception")
    if exception is None:
        return []
    if not isinstance(exception, dict):
        return [
            _fail(
                "deprecation-records-security-exception",
                f"records[{index}].security_exception must be a mapping when present",
                source_path,
            )
        ]
    failures: list[PolicyFailure] = []
    for field in _SECURITY_EXCEPTION_FIELDS:
        if not _nonempty_str(exception.get(field)):
            failures.append(
                _fail(
                    "deprecation-records-security-exception",
                    (
                        f"records[{index}].security_exception must name a non-empty {field!r} "
                        "(affected versions, impact, mitigation, migration, and review authority)"
                    ),
                    source_path,
                )
            )
    return failures


def _check_removal(
    entry: dict,
    index: int,
    removed_schema_paths: set[str],
    source_path: str,
) -> list[PolicyFailure]:
    """Validate the extra invariants for a ``status: removed`` record."""
    failures: list[PolicyFailure] = []
    if not _nonempty_str(entry.get("removal_record")):
        failures.append(
            _fail(
                "deprecation-records-removal-record",
                (
                    f"records[{index}] has status 'removed' but no non-empty 'removal_record' "
                    "(removal is allowed only after a complete deprecation record reaches its "
                    "removal-eligibility rule)"
                ),
                source_path,
            )
        )
    if entry.get("surface_class") == _PUBLISHED_SCHEMA_SURFACE:
        tombstone = entry.get("removal_tombstone")
        if not _nonempty_str(tombstone):
            failures.append(
                _fail(
                    "deprecation-records-removal-tombstone",
                    (
                        f"records[{index}] removes a {_PUBLISHED_SCHEMA_SURFACE} surface and must name a "
                        "'removal_tombstone' schema_path recorded in the schema publication manifest"
                    ),
                    source_path,
                )
            )
        elif tombstone not in removed_schema_paths:
            failures.append(
                _fail(
                    "deprecation-records-removal-tombstone",
                    (
                        f"records[{index}].removal_tombstone {tombstone!r} is not a removed_schemas "
                        f"tombstone in {SCHEMA_PUBLICATION_MANIFEST} (ADR-061 governs published-schema removal)"
                    ),
                    source_path,
                )
            )
    return failures


def _check_records(repo_root: Path, raw: dict, source_path: str) -> list[PolicyFailure]:
    raw_records = raw.get("records")
    if not isinstance(raw_records, list):
        return []  # type-level failure already reported

    removed_schema_paths = _load_removed_schema_paths(repo_root)
    failures: list[PolicyFailure] = []
    seen_ids: set[str] = set()

    for index, entry in enumerate(raw_records):
        if not isinstance(entry, dict):
            failures.append(
                _fail(
                    "deprecation-records-entry-field",
                    f"records[{index}] must be a mapping; got {type(entry).__name__}",
                    source_path,
                )
            )
            continue

        entry_ok = True
        for field in _REQUIRED_RECORD_FIELDS:
            if field not in entry:
                failures.append(
                    _fail(
                        "deprecation-records-entry-field",
                        f"records[{index}] is missing required field: {field}",
                        source_path,
                    )
                )
                entry_ok = False
            elif not _nonempty_str(entry[field]):
                failures.append(
                    _fail(
                        "deprecation-records-entry-field",
                        f"records[{index}].{field} must be a non-empty string",
                        source_path,
                    )
                )
                entry_ok = False

        # Exactly one of replacement / no_replacement_rationale. The spec allows
        # a no-replacement deprecation, but it must carry an explicit rationale.
        has_replacement = _nonempty_str(entry.get("replacement"))
        has_no_replacement = _nonempty_str(entry.get("no_replacement_rationale"))
        if has_replacement == has_no_replacement:
            failures.append(
                _fail(
                    "deprecation-records-replacement",
                    (f"records[{index}] must name exactly one of 'replacement' or 'no_replacement_rationale'"),
                    source_path,
                )
            )

        # id uniqueness (only meaningful once the id itself is a valid string).
        entry_id = entry.get("id")
        if _nonempty_str(entry_id):
            if entry_id in seen_ids:
                failures.append(
                    _fail(
                        "deprecation-records-entry-duplicate",
                        f"records[{index}].id {entry_id!r} is duplicated",
                        source_path,
                    )
                )
            seen_ids.add(entry_id)

        surface = entry.get("surface_class")
        if _nonempty_str(surface) and surface not in SURFACE_CLASSES:
            failures.append(
                _fail(
                    "deprecation-records-surface-class",
                    (
                        f"records[{index}].surface_class {surface!r} is not a recognised surface "
                        f"class; expected one of {sorted(SURFACE_CLASSES)}"
                    ),
                    source_path,
                )
            )

        status = entry.get("status")
        if _nonempty_str(status) and status not in STATUSES:
            failures.append(
                _fail(
                    "deprecation-records-status",
                    f"records[{index}].status {status!r} must be one of {sorted(STATUSES)}",
                    source_path,
                )
            )

        failures.extend(_check_security_exception(entry, index, source_path))

        if status == "removed":
            failures.extend(_check_removal(entry, index, removed_schema_paths, source_path))

        _ = entry_ok  # per-field failures already recorded; kept for readability
    return failures


def _check_canonical_record_floor(raw: dict, source_path: str) -> list[PolicyFailure]:
    """Enforce the retention floor: every canonical record id must be present.

    Deprecation records are lifecycle history. An empty or truncated ledger --
    ``records: []`` or a diff that drops a checked-in record -- would let that
    history disappear while the gate stays green, because the per-record checks
    pass vacuously over whatever entries remain. Pinning the known ids means the
    authoritative record set cannot be silently emptied; a record's ``status``
    may advance (e.g. deprecated -> removed) but its identity is retained.
    """
    raw_records = raw.get("records")
    present_ids = set()
    if isinstance(raw_records, list):
        present_ids = {
            entry["id"] for entry in raw_records if isinstance(entry, dict) and _nonempty_str(entry.get("id"))
        }
    failures: list[PolicyFailure] = []
    for canonical_id in sorted(CANONICAL_DEPRECATION_RECORD_IDS):
        if canonical_id not in present_ids:
            failures.append(
                _fail(
                    "deprecation-records-canonical-record-missing",
                    (
                        f"the canonical deprecation record {canonical_id!r} is missing; established "
                        "lifecycle records may not be removed from the ledger (retiring one is a "
                        "deliberate edit to CANONICAL_DEPRECATION_RECORD_IDS)"
                    ),
                    source_path,
                )
            )
    return failures


# --------------------------------------------------------------------------- #
# Top-level entry point.                                                      #
# --------------------------------------------------------------------------- #


def evaluate_deprecation_records(repo_root: Path) -> list[PolicyFailure]:
    """Return the list of structural failures for the GOV-902 deprecation-record
    surface (empty list = OK)."""
    records_path = repo_root / DEPRECATION_RECORDS_RELATIVE_PATH
    if not records_path.is_file():
        return [
            _fail(
                "deprecation-records-missing",
                f"deprecation records surface not found: {DEPRECATION_RECORDS_RELATIVE_PATH}",
                DEPRECATION_RECORDS_RELATIVE_PATH,
            )
        ]

    try:
        raw = yaml.safe_load(records_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [
            _fail(
                "deprecation-records-parse",
                f"failed to parse {DEPRECATION_RECORDS_RELATIVE_PATH}: {exc}",
                DEPRECATION_RECORDS_RELATIVE_PATH,
            )
        ]

    if not isinstance(raw, dict):
        return [
            _fail(
                "deprecation-records-shape",
                f"{DEPRECATION_RECORDS_RELATIVE_PATH} must be a YAML mapping at the top level",
                DEPRECATION_RECORDS_RELATIVE_PATH,
            )
        ]

    failures: list[PolicyFailure] = []
    failures.extend(_check_top_level(raw, DEPRECATION_RECORDS_RELATIVE_PATH))
    failures.extend(_check_spec_present(repo_root, raw, DEPRECATION_RECORDS_RELATIVE_PATH))
    failures.extend(_check_records(repo_root, raw, DEPRECATION_RECORDS_RELATIVE_PATH))
    failures.extend(_check_canonical_record_floor(raw, DEPRECATION_RECORDS_RELATIVE_PATH))
    return failures


# --------------------------------------------------------------------------- #
# CLI.                                                                        #
# --------------------------------------------------------------------------- #


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the GOV-902 ecosystem deprecation and lifecycle records (ADR-075)."
    )
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
    failures = evaluate_deprecation_records(args.repo_root)
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
