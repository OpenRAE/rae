#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Structural gate for the ASR-517 normative-artifact authority boundary.

ADR-009 ("Normative Artifact Authority and Repository Structure") decides
where ecosystem authority lives: normative prose under ``specs/``, published
JSON Schemas under ``contracts/schemas/``, conformance fixtures under
``contracts/fixtures/``, capability profiles under ``contracts/profiles/``,
and concept-authority artifacts under ``contracts/concept-authority/``.
Reference implementations consume those artifacts; they do not define them.

ASR-517 says the ecosystem **shall** define this authority boundary
explicitly. The canonical machine-readable surface lives in
``specs/authority/authority-boundary.yaml`` (per ADR-009, normative prose
lives under ``specs/``); this checker pins the YAML's structural invariants
and guards against drift between the YAML, ADR-009, ``contracts/README.md``,
and ``specs/README.md``. Failures use ``tools.policy.common.PolicyFailure``
and the CLI honours ``--json`` and the shared
``tools/policy/exceptions.yaml`` waiver mechanism, matching the other
policy gates (``check_repo_policy.py``, ``check_requirement_governance.py``,
``check_semantic_coverage.py``, ``check_assurance_policy.py``).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml

from tools.policy.common import (
    PolicyFailure,
    apply_exceptions,
    failures_to_json,
    load_exceptions,
)

# --------------------------------------------------------------------------- #
# Canonical paths and baseline invariants. Test code imports these directly   #
# so a rename here surfaces in the test suite, not silently in production.    #
# The validator otherwise derives its expectations from the YAML itself —     #
# adding a future normative family is a single YAML edit + a brief mention   #
# in ADR-009 (which the drift guard will require).                            #
# --------------------------------------------------------------------------- #

AUTHORITY_BOUNDARY_RELATIVE_PATH = "specs/authority/authority-boundary.yaml"
ADR_AUTHORITY_RELATIVE_PATH = "docs/decisions/adrs/adr-009-normative-artifact-authority-and-repository-structure.md"
ADR_SEAM_RELATIVE_PATH = "docs/decisions/adrs/adr-019-normative-authority-boundary-manifest.md"
CONTRACTS_README_RELATIVE_PATH = "contracts/README.md"
SPECS_README_RELATIVE_PATH = "specs/README.md"

REQUIREMENT_REF = "ASR-517"
ADR_SOURCE_REF = "ADR-009"  # the authority decision (immutable)
ADR_SEAM_REF = "ADR-019"  # the canonical-seam decision that governs THIS file
ADR_REFS: tuple[str, ...] = (ADR_SOURCE_REF, ADR_SEAM_REF)
POLICY_VALUE = "normative-artifact-authority"

# The canonical normative-artifact families ADR-009 and ADR-019 name, pinned to
# their expected root path AND family token. The YAML may not swap a
# canonical id onto a different root or relabel its family without failing
# the gate — otherwise `normative_schemas` and `normative_fixtures` could be
# silently transposed while the id set still looks complete.
CANONICAL_AUTHORITY_ROOT_BINDING: dict[str, tuple[str, str]] = {
    "normative_prose": ("specs/", "prose"),
    "normative_schemas": ("contracts/schemas/", "schemas"),
    "normative_fixtures": ("contracts/fixtures/", "fixtures"),
    "normative_profiles": ("contracts/profiles/", "profiles"),
    "normative_realization_envelopes": (
        "contracts/realization-envelopes/",
        "realization-envelopes",
    ),
    "normative_concept_authority": (
        "contracts/concept-authority/",
        "concept-authority",
    ),
    "normative_provenance": (
        "contracts/provenance/",
        "provenance",
    ),
}
CANONICAL_AUTHORITY_ROOT_IDS: tuple[str, ...] = tuple(CANONICAL_AUTHORITY_ROOT_BINDING)

# The non-normative root ids that the YAML MUST cover, each pinned to its
# expected root path. ADR-019 names every entry below as part of the
# canonical authority boundary; the YAML may not relabel any of these onto a
# different root without failing the gate (e.g. swapping `explanatory_docs`
# with `tooling`, or pointing `worked_examples` at `research/`).
CANONICAL_NON_NORMATIVE_ROOT_BINDING: dict[str, str] = {
    "reference_implementations": "implementations/",
    "explanatory_docs": "docs/",
    "worked_examples": "examples/",
    "research_notes": "research/",
    "process_notes": "notes/",
    "tooling": "tools/",
}
CANONICAL_NON_NORMATIVE_ROOT_IDS: tuple[str, ...] = tuple(CANONICAL_NON_NORMATIVE_ROOT_BINDING)

# ADR-009 names schemas/, conformance/, src/ as transitional. The gate fails
# if any reappears at the repo root, AND the YAML's `legacy_top_level_dirs`
# list must be a superset of this floor — otherwise a contributor could
# silently drop `schemas` from the list to allow it back as a non-normative
# bucket.
CANONICAL_LEGACY_TOP_LEVEL_DIRS: tuple[str, ...] = ("schemas", "conformance", "src")

# Canonical artifact-family bindings (CA-4): non-prose artifacts that live
# inside a normative authority root but bear a distinct authority family —
# a "surface" in the concept-authority sense (specs/concept-authority/
# concept-authority.md). The `specs/` root's default family is `prose`; an
# explicit `normative_artifact_families` entry classifies one exact file more
# specifically, so the artifact's authority class is decidable from the
# manifest alone. Pinned here the same way CANONICAL_AUTHORITY_ROOT_BINDING
# pins roots, so the classification cannot be silently dropped or relabelled.
CANONICAL_ARTIFACT_FAMILY_BINDING: dict[str, str] = {
    "specs/agent-guidance/agent-guidance.yaml": "governance-guidance",
    "specs/evolution/deprecation-records.yaml": "deprecation-records",
}

# Required top-level fields and per-entry fields. Used by both the YAML shape
# check and the test fixture parametrisation.
_REQUIRED_TOP_LEVEL_FIELDS: tuple[str, ...] = (
    "policy",
    "requirement_refs",
    "adr_refs",
    "authority_roots",
    "non_normative_roots",
    "legacy_top_level_dirs",
    "schema_authority",
    "normative_artifact_families",
)
_REQUIRED_AUTHORITY_ROOT_FIELDS: tuple[str, ...] = ("id", "root", "authority", "family")
_REQUIRED_NON_NORMATIVE_ROOT_FIELDS: tuple[str, ...] = ("id", "root", "note")
_REQUIRED_ARTIFACT_FAMILY_FIELDS: tuple[str, ...] = (
    "id",
    "artifact",
    "authority",
    "family",
)
_REQUIRED_SCHEMA_AUTHORITY_FIELDS: tuple[str, ...] = (
    "normative_root",
    "publication_manifest",
    "forbidden_authority_roots",
    "forbidden_schema_filename_suffixes",
)

# Schema-authority invariants the gate pins to known-good repo state.
_SCHEMA_NORMATIVE_ROOT = "contracts/schemas/"
_SCHEMA_PUBLICATION_MANIFEST = "contracts/schema-publication-manifest.json"
_SCHEMA_FORBIDDEN_ROOTS_FLOOR: frozenset[str] = frozenset({"implementations/"})
# Closed schemas used only to validate repository-internal tooling policy are
# implementation data, not published ecosystem contracts. This exact root is
# the sole exception to the filename heuristic below; the publication manifest
# remains authoritative for public schemas.
_INTERNAL_TOOLING_SCHEMA_ROOT = "implementations/tooling/schemas/"


# --------------------------------------------------------------------------- #
# Failure factory.                                                            #
# --------------------------------------------------------------------------- #


def _fail(rule_id: str, message: str, path: str | None = None) -> PolicyFailure:
    return PolicyFailure(rule_id, message, path)


# --------------------------------------------------------------------------- #
# Shape checks.                                                               #
# --------------------------------------------------------------------------- #


def _is_str(value: object) -> bool:
    return isinstance(value, str)


def _str_list(value: object) -> list[str] | None:
    """Return ``value`` as a list of strings, or None if it isn't one.

    A list with a non-string element is rejected (returns None) so the gate
    doesn't silently coerce ``[ASR-517, 17]`` into ``["ASR-517", "17"]`` and
    keep passing. Empty lists are accepted at the shape layer; per-field
    semantic checks reject them where required.
    """
    if not isinstance(value, list):
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return list(value)


def _check_top_level_fields(raw: dict, source_path: str) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for field in _REQUIRED_TOP_LEVEL_FIELDS:
        if field not in raw:
            failures.append(
                _fail(
                    "authority-boundary-field",
                    f"required top-level field is missing: {field}",
                    source_path,
                )
            )
    # Type-strict checks on the present fields. A missing field is reported
    # above; a present-but-wrong-type field is reported here.
    if "policy" in raw and not _is_str(raw["policy"]):
        failures.append(
            _fail(
                "authority-boundary-field-type",
                f"policy must be a string; got {type(raw['policy']).__name__}",
                source_path,
            )
        )
    if "requirement_refs" in raw and _str_list(raw["requirement_refs"]) is None:
        failures.append(
            _fail(
                "authority-boundary-field-type",
                "requirement_refs must be a list of strings",
                source_path,
            )
        )
    if "adr_refs" in raw and _str_list(raw["adr_refs"]) is None:
        failures.append(
            _fail(
                "authority-boundary-field-type",
                "adr_refs must be a list of strings",
                source_path,
            )
        )
    if "authority_roots" in raw and not isinstance(raw["authority_roots"], list):
        failures.append(
            _fail(
                "authority-boundary-field-type",
                f"authority_roots must be a list; got {type(raw['authority_roots']).__name__}",
                source_path,
            )
        )
    if "non_normative_roots" in raw and not isinstance(raw["non_normative_roots"], list):
        failures.append(
            _fail(
                "authority-boundary-field-type",
                f"non_normative_roots must be a list; got {type(raw['non_normative_roots']).__name__}",
                source_path,
            )
        )
    if "legacy_top_level_dirs" in raw and _str_list(raw["legacy_top_level_dirs"]) is None:
        failures.append(
            _fail(
                "authority-boundary-field-type",
                "legacy_top_level_dirs must be a list of strings",
                source_path,
            )
        )
    if "schema_authority" in raw and not isinstance(raw["schema_authority"], dict):
        failures.append(
            _fail(
                "authority-boundary-field-type",
                f"schema_authority must be a mapping; got {type(raw['schema_authority']).__name__}",
                source_path,
            )
        )
    if "normative_artifact_families" in raw and not isinstance(raw["normative_artifact_families"], list):
        failures.append(
            _fail(
                "authority-boundary-field-type",
                f"normative_artifact_families must be a list; got {type(raw['normative_artifact_families']).__name__}",
                source_path,
            )
        )
    return failures


def _check_refs(raw: dict, source_path: str) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []

    requirement_refs = _str_list(raw.get("requirement_refs"))
    if requirement_refs is not None and REQUIREMENT_REF not in requirement_refs:
        failures.append(
            _fail(
                "authority-boundary-requirement-ref",
                f"requirement_refs must include {REQUIREMENT_REF}; got {requirement_refs!r}",
                source_path,
            )
        )

    adr_refs = _str_list(raw.get("adr_refs"))
    if adr_refs is not None:
        for ref in ADR_REFS:
            if ref not in adr_refs:
                failures.append(
                    _fail(
                        "authority-boundary-adr-ref",
                        f"adr_refs must include {ref}; got {adr_refs!r}",
                        source_path,
                    )
                )

    if "policy" in raw and _is_str(raw["policy"]) and raw["policy"] != POLICY_VALUE:
        failures.append(
            _fail(
                "authority-boundary-value",
                f"policy must equal {POLICY_VALUE!r}; got {raw['policy']!r}",
                source_path,
            )
        )
    return failures


def _check_root_path_shape(root: str) -> str | None:
    """Return the reason ``root`` is malformed, or None if it is well-formed."""
    if not root:
        return "must be a non-empty string"
    if root.startswith("/"):
        return f"must be a repo-relative path; got {root!r}"
    if ".." in Path(root).parts:
        return f"must not traverse parent directories; got {root!r}"
    if not root.endswith("/"):
        return f"must end with '/'; got {root!r}"
    return None


def _check_authority_roots(raw: dict, source_path: str) -> tuple[list[dict], list[PolicyFailure]]:
    """Validate the authority_roots list and return the validated entries."""
    failures: list[PolicyFailure] = []
    raw_entries = raw.get("authority_roots")
    if not isinstance(raw_entries, list):
        return [], failures  # type-level failure already reported

    validated: list[dict] = []
    seen_ids: set[str] = set()
    seen_roots: set[str] = set()
    for index, entry in enumerate(raw_entries):
        if not isinstance(entry, dict):
            failures.append(
                _fail(
                    "authority-boundary-entry-field",
                    f"authority_roots[{index}] must be a mapping; got {type(entry).__name__}",
                    source_path,
                )
            )
            continue

        entry_ok = True
        for field in _REQUIRED_AUTHORITY_ROOT_FIELDS:
            if field not in entry:
                failures.append(
                    _fail(
                        "authority-boundary-entry-field",
                        f"authority_roots[{index}] is missing required field: {field}",
                        source_path,
                    )
                )
                entry_ok = False
            elif not _is_str(entry[field]) or not entry[field]:
                failures.append(
                    _fail(
                        "authority-boundary-entry-field",
                        f"authority_roots[{index}].{field} must be a non-empty string",
                        source_path,
                    )
                )
                entry_ok = False
        if not entry_ok:
            continue

        root_id = entry["id"]
        root_path = entry["root"]

        path_problem = _check_root_path_shape(root_path)
        if path_problem is not None:
            failures.append(
                _fail(
                    "authority-boundary-root-shape",
                    f"authority_roots[{index}].root {path_problem}",
                    source_path,
                )
            )
            continue

        if root_id in seen_ids:
            failures.append(
                _fail(
                    "authority-boundary-entry-duplicate",
                    f"authority_roots[{index}].id '{root_id}' is duplicated",
                    source_path,
                )
            )
            continue
        if root_path in seen_roots:
            failures.append(
                _fail(
                    "authority-boundary-entry-duplicate",
                    f"authority_roots[{index}].root '{root_path}' is duplicated",
                    source_path,
                )
            )
            continue

        seen_ids.add(root_id)
        seen_roots.add(root_path)
        validated.append(
            {
                "id": root_id,
                "root": root_path,
                "authority": entry["authority"],
                "family": entry["family"],
            }
        )

    validated_by_id = {entry["id"]: entry for entry in validated}
    for canonical_id, (
        expected_root,
        expected_family,
    ) in CANONICAL_AUTHORITY_ROOT_BINDING.items():
        if canonical_id not in seen_ids:
            failures.append(
                _fail(
                    "authority-boundary-canonical-root-missing",
                    f"authority_roots is missing canonical entry: {canonical_id}",
                    source_path,
                )
            )
            continue
        entry = validated_by_id[canonical_id]
        if entry["root"] != expected_root:
            failures.append(
                _fail(
                    "authority-boundary-canonical-root-binding",
                    (
                        f"authority_roots entry '{canonical_id}' must declare root={expected_root!r}; "
                        f"got {entry['root']!r}"
                    ),
                    source_path,
                )
            )
        if entry["family"] != expected_family:
            failures.append(
                _fail(
                    "authority-boundary-canonical-root-binding",
                    (
                        f"authority_roots entry '{canonical_id}' must declare family={expected_family!r}; "
                        f"got {entry['family']!r}"
                    ),
                    source_path,
                )
            )

    return validated, failures


def _check_non_normative_roots(raw: dict, source_path: str) -> tuple[list[dict], list[PolicyFailure]]:
    failures: list[PolicyFailure] = []
    raw_entries = raw.get("non_normative_roots")
    if not isinstance(raw_entries, list):
        return [], failures

    validated: list[dict] = []
    seen_ids: set[str] = set()
    seen_roots: set[str] = set()
    for index, entry in enumerate(raw_entries):
        if not isinstance(entry, dict):
            failures.append(
                _fail(
                    "authority-boundary-entry-field",
                    f"non_normative_roots[{index}] must be a mapping; got {type(entry).__name__}",
                    source_path,
                )
            )
            continue

        entry_ok = True
        for field in _REQUIRED_NON_NORMATIVE_ROOT_FIELDS:
            if field not in entry:
                failures.append(
                    _fail(
                        "authority-boundary-entry-field",
                        f"non_normative_roots[{index}] is missing required field: {field}",
                        source_path,
                    )
                )
                entry_ok = False
            elif not _is_str(entry[field]) or not entry[field]:
                failures.append(
                    _fail(
                        "authority-boundary-entry-field",
                        f"non_normative_roots[{index}].{field} must be a non-empty string",
                        source_path,
                    )
                )
                entry_ok = False
        if not entry_ok:
            continue

        root_id = entry["id"]
        root_path = entry["root"]
        path_problem = _check_root_path_shape(root_path)
        if path_problem is not None:
            failures.append(
                _fail(
                    "authority-boundary-root-shape",
                    f"non_normative_roots[{index}].root {path_problem}",
                    source_path,
                )
            )
            continue

        if root_id in seen_ids:
            failures.append(
                _fail(
                    "authority-boundary-entry-duplicate",
                    f"non_normative_roots[{index}].id '{root_id}' is duplicated",
                    source_path,
                )
            )
            continue
        if root_path in seen_roots:
            failures.append(
                _fail(
                    "authority-boundary-entry-duplicate",
                    f"non_normative_roots[{index}].root '{root_path}' is duplicated",
                    source_path,
                )
            )
            continue

        seen_ids.add(root_id)
        seen_roots.add(root_path)
        validated.append({"id": root_id, "root": root_path, "note": entry["note"]})

    validated_by_id = {entry["id"]: entry for entry in validated}
    for canonical_id, expected_root in CANONICAL_NON_NORMATIVE_ROOT_BINDING.items():
        if canonical_id not in seen_ids:
            failures.append(
                _fail(
                    "authority-boundary-canonical-root-missing",
                    f"non_normative_roots is missing canonical entry: {canonical_id}",
                    source_path,
                )
            )
            continue
        entry = validated_by_id[canonical_id]
        if entry["root"] != expected_root:
            failures.append(
                _fail(
                    "authority-boundary-canonical-root-binding",
                    (
                        f"non_normative_roots entry '{canonical_id}' must declare root={expected_root!r}; "
                        f"got {entry['root']!r}"
                    ),
                    source_path,
                )
            )

    return validated, failures


def _check_schema_authority_block(raw: dict, source_path: str) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    block = raw.get("schema_authority")
    if not isinstance(block, dict):
        return failures  # type-level failure already reported

    for field in _REQUIRED_SCHEMA_AUTHORITY_FIELDS:
        if field not in block:
            failures.append(
                _fail(
                    "authority-boundary-entry-field",
                    f"schema_authority is missing required field: {field}",
                    source_path,
                )
            )

    # normative_root and publication_manifest must each be a non-empty
    # string AND match the canonical value. A non-string value used to be
    # ignored by these two checks; surface it as a field-type failure so a
    # malformed value can't sneak through "the mismatch check was skipped".
    if "normative_root" in block:
        normative_root = block["normative_root"]
        if not _is_str(normative_root) or not normative_root:
            failures.append(
                _fail(
                    "authority-boundary-field-type",
                    f"schema_authority.normative_root must be a non-empty string; got {normative_root!r}",
                    source_path,
                )
            )
        elif normative_root != _SCHEMA_NORMATIVE_ROOT:
            failures.append(
                _fail(
                    "authority-boundary-schema-authority-mismatch",
                    f"schema_authority.normative_root must equal {_SCHEMA_NORMATIVE_ROOT!r}; got {normative_root!r}",
                    source_path,
                )
            )

    if "publication_manifest" in block:
        manifest = block["publication_manifest"]
        if not _is_str(manifest) or not manifest:
            failures.append(
                _fail(
                    "authority-boundary-field-type",
                    f"schema_authority.publication_manifest must be a non-empty string; got {manifest!r}",
                    source_path,
                )
            )
        elif manifest != _SCHEMA_PUBLICATION_MANIFEST:
            failures.append(
                _fail(
                    "authority-boundary-schema-authority-mismatch",
                    (
                        f"schema_authority.publication_manifest must equal "
                        f"{_SCHEMA_PUBLICATION_MANIFEST!r}; got {manifest!r}"
                    ),
                    source_path,
                )
            )

    forbidden = _str_list(block.get("forbidden_authority_roots"))
    if forbidden is None:
        # Either missing (already reported above) or wrong type — surface
        # a separate failure for the type case so the operator sees the
        # right corrective action.
        if "forbidden_authority_roots" in block:
            failures.append(
                _fail(
                    "authority-boundary-field-type",
                    "schema_authority.forbidden_authority_roots must be a list of strings",
                    source_path,
                )
            )
    else:
        for index, root_value in enumerate(forbidden):
            problem = _check_root_path_shape(root_value)
            if problem is not None:
                failures.append(
                    _fail(
                        "authority-boundary-root-shape",
                        f"schema_authority.forbidden_authority_roots[{index}] {problem}",
                        source_path,
                    )
                )
        missing_floor = _SCHEMA_FORBIDDEN_ROOTS_FLOOR - set(forbidden)
        if missing_floor:
            failures.append(
                _fail(
                    "authority-boundary-schema-authority-forbidden-roots",
                    (
                        "schema_authority.forbidden_authority_roots must include the baseline floor "
                        f"{sorted(_SCHEMA_FORBIDDEN_ROOTS_FLOOR)}; missing {sorted(missing_floor)}"
                    ),
                    source_path,
                )
            )

    suffixes = _str_list(block.get("forbidden_schema_filename_suffixes"))
    if suffixes is None and "forbidden_schema_filename_suffixes" in block:
        failures.append(
            _fail(
                "authority-boundary-field-type",
                "schema_authority.forbidden_schema_filename_suffixes must be a list of strings",
                source_path,
            )
        )
    elif suffixes is not None:
        if not suffixes:
            failures.append(
                _fail(
                    "authority-boundary-field-type",
                    "schema_authority.forbidden_schema_filename_suffixes must be a non-empty list",
                    source_path,
                )
            )
        for index, suffix in enumerate(suffixes):
            # A suffix must be a non-empty string that begins with `.` so it
            # can be safely passed to `str.endswith`. An empty suffix would
            # match every file and turn the schema-misplaced check into a
            # blanket reject; a suffix that doesn't begin with `.` is
            # almost certainly a malformed entry.
            if not suffix or not suffix.startswith(".") or len(suffix) < 2:
                failures.append(
                    _fail(
                        "authority-boundary-field-type",
                        (
                            f"schema_authority.forbidden_schema_filename_suffixes[{index}] must be a "
                            f"non-empty extension starting with '.'; got {suffix!r}"
                        ),
                        source_path,
                    )
                )

    return failures


# --------------------------------------------------------------------------- #
# Normative artifact-family classification (CA-4).                            #
# --------------------------------------------------------------------------- #


def _check_artifact_path_shape(artifact: str) -> str | None:
    """Return why ``artifact`` is a malformed repo-relative file path, or None.

    Mirrors ``_check_root_path_shape`` but for files: a classified artifact is a
    concrete file, so it must NOT end with ``/`` (the root rule is inverted).
    """
    if not artifact:
        return "must be a non-empty string"
    if artifact.startswith("/"):
        return f"must be a repo-relative path; got {artifact!r}"
    if ".." in Path(artifact).parts:
        return f"must not traverse parent directories; got {artifact!r}"
    if artifact.endswith("/"):
        return f"must be a file path, not a directory; got {artifact!r}"
    return None


def _check_normative_artifact_families(
    repo_root: Path,
    raw: dict,
    authority_roots: list[dict],
    non_normative_roots: list[dict],
    source_path: str,
) -> list[PolicyFailure]:
    """Validate the ``normative_artifact_families`` block (CA-4).

    Each entry classifies one non-prose artifact that lives inside a normative
    authority root but bears a distinct authority family (a governed
    "surface", per specs/concept-authority/concept-authority.md). The block is
    the most-specific classification seam: because an artifact path is strictly
    more specific than any root prefix, an explicit entry classifies that exact
    file and the containing root supplies the default for everything else, so
    there is no parent/child ambiguity. The canonical bindings are pinned so
    the classification cannot be silently dropped or relabelled.
    """
    failures: list[PolicyFailure] = []
    raw_entries = raw.get("normative_artifact_families")
    if not isinstance(raw_entries, list):
        return failures  # missing-field / type-level failure already reported

    authority_prefixes = [entry["root"] for entry in authority_roots]
    non_normative_prefixes = [entry["root"] for entry in non_normative_roots]

    validated: list[dict] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(raw_entries):
        if not isinstance(entry, dict):
            failures.append(
                _fail(
                    "authority-boundary-artifact-family-entry-field",
                    f"normative_artifact_families[{index}] must be a mapping; got {type(entry).__name__}",
                    source_path,
                )
            )
            continue

        entry_ok = True
        for field in _REQUIRED_ARTIFACT_FAMILY_FIELDS:
            if field not in entry:
                failures.append(
                    _fail(
                        "authority-boundary-artifact-family-entry-field",
                        f"normative_artifact_families[{index}] is missing required field: {field}",
                        source_path,
                    )
                )
                entry_ok = False
            elif not (_is_str(entry[field]) and entry[field]):
                failures.append(
                    _fail(
                        "authority-boundary-artifact-family-entry-field",
                        f"normative_artifact_families[{index}].{field} must be a non-empty string",
                        source_path,
                    )
                )
                entry_ok = False

        # requirement_refs is optional, but when present it carries the same
        # list-of-strings strictness as the top-level refs.
        if "requirement_refs" in entry and _str_list(entry["requirement_refs"]) is None:
            failures.append(
                _fail(
                    "authority-boundary-artifact-family-entry-field",
                    f"normative_artifact_families[{index}].requirement_refs must be a list of strings",
                    source_path,
                )
            )
            entry_ok = False

        if not entry_ok:
            continue

        entry_id = entry["id"]
        if entry_id in seen_ids:
            failures.append(
                _fail(
                    "authority-boundary-artifact-family-duplicate",
                    f"normative_artifact_families[{index}].id '{entry_id}' is duplicated",
                    source_path,
                )
            )
        seen_ids.add(entry_id)

        artifact = entry["artifact"]
        shape_problem = _check_artifact_path_shape(artifact)
        if shape_problem is not None:
            failures.append(
                _fail(
                    "authority-boundary-artifact-family-path-shape",
                    f"normative_artifact_families[{index}].artifact {shape_problem}",
                    source_path,
                )
            )
            continue

        # A governed surface must live under a NORMATIVE authority root — it
        # cannot be classified into a tree that only consumes authority.
        if not any(artifact.startswith(prefix) for prefix in authority_prefixes):
            under_non_normative = any(artifact.startswith(prefix) for prefix in non_normative_prefixes)
            detail = (
                "is under a non-normative root"
                if under_non_normative
                else "is not under any declared normative authority root"
            )
            failures.append(
                _fail(
                    "authority-boundary-artifact-family-non-normative",
                    f"normative_artifact_families[{index}].artifact '{artifact}' {detail}",
                    source_path,
                )
            )
            continue

        if not (repo_root / artifact).is_file():
            failures.append(
                _fail(
                    "authority-boundary-artifact-family-missing",
                    f"normative_artifact_families[{index}].artifact '{artifact}' does not exist on disk",
                    source_path,
                )
            )
            continue

        validated.append({"id": entry_id, "artifact": artifact, "family": entry["family"]})

    # Pin the canonical artifact-family bindings, mirroring the canonical-root
    # binding floor: each must be present with its expected family.
    by_artifact = {entry["artifact"]: entry for entry in validated}
    for canon_artifact, canon_family in CANONICAL_ARTIFACT_FAMILY_BINDING.items():
        entry = by_artifact.get(canon_artifact)
        if entry is None:
            failures.append(
                _fail(
                    "authority-boundary-artifact-family-canonical-missing",
                    (
                        f"normative_artifact_families is missing the canonical classification for "
                        f"{canon_artifact} (expected family {canon_family!r})"
                    ),
                    source_path,
                )
            )
            continue
        if entry["family"] != canon_family:
            failures.append(
                _fail(
                    "authority-boundary-artifact-family-canonical-binding",
                    (
                        f"normative_artifact_families entry for {canon_artifact} must declare "
                        f"family={canon_family!r}; got {entry['family']!r}"
                    ),
                    source_path,
                )
            )

    return failures


# --------------------------------------------------------------------------- #
# Filesystem invariants.                                                      #
# --------------------------------------------------------------------------- #


def _dir_has_content(directory: Path) -> bool:
    """Return True if ``directory`` exists and contains at least one entry
    other than `.keep` placeholder files.

    A directory whose only contents are `.keep` files counts as empty —
    those are placeholder markers, not real artifacts. This catches the
    "I created the root but never put anything in it" failure mode."""
    if not directory.is_dir():
        return False
    for child in directory.iterdir():
        if child.name == ".keep":
            continue
        return True
    return False


def _check_root_exists(
    repo_root: Path, authority_roots: list[dict], non_normative_roots: list[dict]
) -> list[PolicyFailure]:
    """Authority roots MUST exist with real content (they are the contract).
    Non-normative roots are CLASSIFIED but not required to exist on disk —
    `research/` and `notes/` are gitignored in this repo, so requiring them
    to exist would fail CI checkouts while passing local dev. The YAML is
    the boundary classifier; presence-on-disk is a separate concern enforced
    only for normative artifacts."""
    failures: list[PolicyFailure] = []
    for entry in authority_roots:
        root_path = entry["root"]
        directory = repo_root / root_path
        if not directory.is_dir():
            failures.append(
                _fail(
                    "authority-boundary-root-missing",
                    f"authority root '{root_path}' (id={entry['id']!r}) does not exist on disk",
                    root_path,
                )
            )
        elif not _dir_has_content(directory):
            failures.append(
                _fail(
                    "authority-boundary-root-empty",
                    f"authority root '{root_path}' (id={entry['id']!r}) exists but contains no artifacts",
                    root_path,
                )
            )
    # Non-normative roots are not required to exist on disk. The classified
    # set still feeds into _check_unclassified_top_level so a non-normative
    # dir that DOES exist on disk is accepted rather than flagged.
    return failures


def _check_legacy_dirs_absent(repo_root: Path, legacy_dirs: list[str]) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for legacy in legacy_dirs:
        directory = repo_root / legacy
        if directory.is_dir():
            failures.append(
                _fail(
                    "authority-boundary-legacy-dir-present",
                    (
                        f"legacy top-level directory '{legacy}' must not exist (ADR-009: transitional paths "
                        "have been migrated and may not reappear)"
                    ),
                    legacy,
                )
            )
    return failures


def _check_root_categorisation_overlap(
    authority_roots: list[dict],
    non_normative_roots: list[dict],
    legacy_dirs: list[str],
) -> list[PolicyFailure]:
    """Reject any root that is classified into more than one category.

    A root may be normative, non-normative, or legacy — but not two of those
    at once. ASR-517 turns on the predicate that reference implementations
    *consume* authority rather than bearing it; without this check, a
    manifest could declare ``implementations/`` as both ``authority_roots``
    and ``non_normative_roots`` and pass the existing per-list shape checks.

    Ancestor/descendant overlaps across categories also fail: an authority
    root ``implementations/python/foo/`` cannot coexist with a non-normative
    root ``implementations/`` because the former would force the latter to
    bear partial authority.
    """
    failures: list[PolicyFailure] = []

    authority_by_root = {entry["root"]: entry for entry in authority_roots}
    non_normative_by_root = {entry["root"]: entry for entry in non_normative_roots}

    # Exact-root collisions across the three categories.
    for root_path, entry in authority_by_root.items():
        if root_path in non_normative_by_root:
            failures.append(
                _fail(
                    "authority-boundary-categorisation-overlap",
                    (
                        f"root '{root_path}' is classified as both authority "
                        f"(id={entry['id']!r}) and non-normative "
                        f"(id={non_normative_by_root[root_path]['id']!r}); each root must have exactly one "
                        "classification"
                    ),
                    AUTHORITY_BOUNDARY_RELATIVE_PATH,
                )
            )

    # Legacy-vs-classified overlap: the legacy floor names top-level dirs
    # (no trailing slash). If any authority or non-normative root has the
    # same first path segment as a legacy entry, the legacy floor is
    # contradicted (the dir is both "must not exist" and "is classified
    # somewhere").
    legacy_set = set(legacy_dirs)
    for entry in authority_roots + non_normative_roots:
        root_path = entry["root"]
        first_segment = Path(root_path).parts[0] if Path(root_path).parts else ""
        if first_segment and first_segment in legacy_set:
            category = "authority" if entry in authority_roots else "non-normative"
            failures.append(
                _fail(
                    "authority-boundary-categorisation-overlap",
                    (
                        f"{category} root '{root_path}' (id={entry['id']!r}) shares its top-level segment "
                        f"'{first_segment}' with legacy_top_level_dirs; legacy dirs must remain absent and "
                        "may not host a classified root"
                    ),
                    AUTHORITY_BOUNDARY_RELATIVE_PATH,
                )
            )

    # Ancestor/descendant overlaps across the authority vs non-normative
    # lists. e.g. authority `implementations/python/foo/` would force the
    # non-normative `implementations/` to bear partial authority.
    def _is_strict_ancestor(parent: str, child: str) -> bool:
        return child != parent and child.startswith(parent)

    cross_pairs = [
        ("authority", entry, "non-normative", other) for entry in authority_roots for other in non_normative_roots
    ]
    for parent_label, parent_entry, child_label, child_entry in cross_pairs:
        a_root = parent_entry["root"]
        b_root = child_entry["root"]
        if _is_strict_ancestor(a_root, b_root):
            failures.append(
                _fail(
                    "authority-boundary-categorisation-overlap",
                    (
                        f"{parent_label} root '{a_root}' (id={parent_entry['id']!r}) is an ancestor of "
                        f"{child_label} root '{b_root}' (id={child_entry['id']!r}); a child of a "
                        "normative root cannot be non-normative"
                    ),
                    AUTHORITY_BOUNDARY_RELATIVE_PATH,
                )
            )
        elif _is_strict_ancestor(b_root, a_root):
            failures.append(
                _fail(
                    "authority-boundary-categorisation-overlap",
                    (
                        f"{child_label} root '{b_root}' (id={child_entry['id']!r}) is an ancestor of "
                        f"{parent_label} root '{a_root}' (id={parent_entry['id']!r}); a child of a "
                        "non-normative root cannot be authority"
                    ),
                    AUTHORITY_BOUNDARY_RELATIVE_PATH,
                )
            )

    return failures


def _classify_top_level_dir_names(
    authority_roots: list[dict],
    non_normative_roots: list[dict],
    legacy_dirs: list[str],
) -> set[str]:
    """Return the set of top-level directory names that the YAML classifies.

    A YAML entry whose root is ``contracts/schemas/`` covers the top-level
    ``contracts`` directory — sub-roots count their parent as classified. This
    is what lets the gate accept the canonical layout where one top-level
    directory hosts several authority families.
    """
    classified: set[str] = set()
    for entry in authority_roots + non_normative_roots:
        root_path = entry["root"]
        first = Path(root_path).parts[0] if Path(root_path).parts else ""
        if first:
            classified.add(first)
    classified.update(legacy_dirs)
    return classified


def _check_unclassified_top_level(
    repo_root: Path,
    authority_roots: list[dict],
    non_normative_roots: list[dict],
    legacy_dirs: list[str],
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    classified = _classify_top_level_dir_names(authority_roots, non_normative_roots, legacy_dirs)
    for child in sorted(repo_root.iterdir()):
        if not child.is_dir():
            continue
        if child.is_symlink():
            # Symlinks at the root are operational infrastructure, not
            # authority artifacts; don't fail the gate on them.
            continue
        name = child.name
        if name.startswith(".") or name in _PRUNE_DIR_NAMES:
            # Hidden directories (.github, .codex, .gc, ...) and operational
            # build/cache artifacts (build/, dist/, node_modules/, venv/,
            # __pycache__/, ...) are git-ignored and never authority-bearing.
            # The schema-misplaced scan prunes this same set, so a
            # developer-local build artifact does not trip a gate that CI's
            # clean checkout would never see.
            continue
        if name in classified:
            continue
        failures.append(
            _fail(
                "authority-boundary-unclassified-top-level",
                (
                    f"top-level directory '{name}' is not classified in authority_roots, "
                    "non_normative_roots, or legacy_top_level_dirs"
                ),
                name,
            )
        )
    return failures


import os

# Directory names that are operational/build artifacts (developer-local
# virtualenvs, caches, dependency caches, test caches, VCS metadata, etc.).
# Both the schema-misplaced scan and the unclassified-top-level scan prune
# these so the gate is deterministic over tracked repository contents rather
# than over whichever third-party packages or local build artifacts happen to
# be present in a developer's checkout.
_PRUNE_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        ".tox",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        "build",
        "dist",
        ".eggs",
        ".cache",
        ".coverage",
        "site-packages",
        "_build",
    }
)


def _misplaced_schema_failures(
    repo_root: Path,
    directory: Path,
    forbidden_root: str,
    suffixes: tuple[str, ...],
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for dirpath, dirnames, filenames in os.walk(directory):
        dirnames[:] = [name for name in dirnames if name not in _PRUNE_DIR_NAMES and not name.startswith(".")]
        for filename in filenames:
            rel_path = Path(dirpath, filename).relative_to(repo_root).as_posix()
            if not filename.endswith(suffixes) or rel_path.startswith(_INTERNAL_TOOLING_SCHEMA_ROOT):
                continue
            failures.append(
                _fail(
                    "authority-boundary-schema-misplaced",
                    (
                        f"published schema file '{rel_path}' is under a forbidden authority root "
                        f"('{forbidden_root}'); published schemas must live under '{_SCHEMA_NORMATIVE_ROOT}'"
                    ),
                    rel_path,
                )
            )
    return failures


def _check_schemas_outside_normative_root(
    repo_root: Path,
    suffixes: list[str],
    forbidden_roots: list[str],
) -> list[PolicyFailure]:
    """Reject published schemas under configured non-normative roots."""

    failures: list[PolicyFailure] = []
    suffix_tuple = tuple(suffixes)
    for forbidden in forbidden_roots:
        if _check_root_path_shape(forbidden) is not None:
            continue
        directory = repo_root / forbidden
        if not directory.is_dir():
            continue
        failures.extend(_misplaced_schema_failures(repo_root, directory, forbidden, suffix_tuple))
    return failures


def _check_publication_manifest_present(repo_root: Path) -> list[PolicyFailure]:
    manifest = repo_root / _SCHEMA_PUBLICATION_MANIFEST
    if not manifest.is_file():
        return [
            _fail(
                "authority-boundary-publication-manifest-missing",
                f"schema publication manifest '{_SCHEMA_PUBLICATION_MANIFEST}' is missing",
                _SCHEMA_PUBLICATION_MANIFEST,
            )
        ]
    return []


# --------------------------------------------------------------------------- #
# Drift guards.                                                               #
# --------------------------------------------------------------------------- #


def _read_text_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _check_adr_drift(repo_root: Path, authority_roots: list[dict]) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []

    adr_path = repo_root / ADR_AUTHORITY_RELATIVE_PATH
    adr_text: str | None = None
    if not adr_path.is_file():
        failures.append(
            _fail(
                "authority-boundary-adr-missing",
                f"{ADR_AUTHORITY_RELATIVE_PATH} is missing",
                ADR_AUTHORITY_RELATIVE_PATH,
            )
        )
    else:
        adr_text = _read_text_or_none(adr_path)
        if adr_text is None:
            failures.append(
                _fail(
                    "authority-boundary-adr-missing",
                    f"{ADR_AUTHORITY_RELATIVE_PATH} could not be read",
                    ADR_AUTHORITY_RELATIVE_PATH,
                )
            )

    # ADR-019 (the canonical-seam decision) must exist and be readable. The
    # drift-token union only covers `concept-authority` via ADR-019, and the
    # README references point at ADR-019 as the governing decision; if the
    # file disappears, the manifest's governance link is broken even when
    # adr_refs still names it.
    seam_path = repo_root / ADR_SEAM_RELATIVE_PATH
    seam_text: str | None = None
    if not seam_path.is_file():
        failures.append(
            _fail(
                "authority-boundary-seam-adr-missing",
                f"{ADR_SEAM_RELATIVE_PATH} is missing",
                ADR_SEAM_RELATIVE_PATH,
            )
        )
    else:
        seam_text = _read_text_or_none(seam_path)
        if seam_text is None:
            failures.append(
                _fail(
                    "authority-boundary-seam-adr-missing",
                    f"{ADR_SEAM_RELATIVE_PATH} could not be read",
                    ADR_SEAM_RELATIVE_PATH,
                )
            )

    if adr_text is None and seam_text is None:
        # Nothing to drift-check against.
        return failures

    # The drift guard checks the family token against the UNION of ADR-009
    # (the immutable authority decision) and ADR-019 (the canonical-seam
    # decision that governs THIS file). ADR-009 names the four authority
    # families it introduced (`prose`, `schemas`, `fixtures`, `profiles`);
    # `concept-authority` was added by ADR-012 and is named verbatim in
    # ADR-019 so the gate stays self-contained.
    union_parts = [text for text in (adr_text, seam_text) if text is not None]
    union_text = "\n".join(union_parts)

    for entry in authority_roots:
        family = entry["family"]
        # Word-boundary match on the family token; substring matching would
        # let `prose` falsely satisfy a doc that mentions `prosecution`, or
        # let a short family token match unrelated words. The root path is
        # also accepted (it is path-shaped and effectively self-delimited),
        # but only as an exact occurrence, not as a substring of a longer
        # path like `old/contracts/profiles/`.
        family_pattern = rf"(?<!\w){re.escape(family)}(?!\w)"
        if not re.search(family_pattern, union_text):
            failures.append(
                _fail(
                    "authority-boundary-adr-drift",
                    (
                        f"neither {ADR_AUTHORITY_RELATIVE_PATH} nor {ADR_SEAM_RELATIVE_PATH} "
                        f"mentions authority family '{family}' (root='{entry['root']}', id={entry['id']!r}); "
                        "the immutable ADR pair must reference every authority family or it has drifted"
                    ),
                    ADR_AUTHORITY_RELATIVE_PATH,
                )
            )
    return failures


# Parse Markdown link targets `[text](target)` and inline code spans
# `` `target` ``. The README drift guard checks the accepted manifest paths
# against these tokens rather than against raw substrings, so a stale link
# like `../old/specs/authority/authority-boundary.yaml` cannot satisfy the
# canonical path by sharing its suffix.
_MARKDOWN_LINK_TARGET_RE = re.compile(r"\(([^)]+)\)")
_MARKDOWN_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


# Canonical paths each README may use to reference the manifest. Anything
# else (e.g. `old/authority-boundary.yaml`) is a stale link and must fail the
# drift guard rather than satisfying it. Keys are README paths; values are
# the accepted manifest reference strings (absolute repo-relative + the
# README-relative shorthand).
_README_MANIFEST_REFERENCES: dict[str, tuple[str, ...]] = {
    CONTRACTS_README_RELATIVE_PATH: (
        AUTHORITY_BOUNDARY_RELATIVE_PATH,
        "../specs/authority/authority-boundary.yaml",
    ),
    SPECS_README_RELATIVE_PATH: (
        AUTHORITY_BOUNDARY_RELATIVE_PATH,
        "authority/authority-boundary.yaml",
    ),
}


def _check_readme_drift(
    repo_root: Path,
    readme_relative_path: str,
    missing_rule: str,
    drift_rule: str,
) -> list[PolicyFailure]:
    readme_path = repo_root / readme_relative_path
    if not readme_path.is_file():
        return [
            _fail(
                missing_rule,
                f"{readme_relative_path} is missing",
                readme_relative_path,
            )
        ]
    text = _read_text_or_none(readme_path)
    if text is None:
        return [
            _fail(
                missing_rule,
                f"{readme_relative_path} could not be read",
                readme_relative_path,
            )
        ]

    failures: list[PolicyFailure] = []
    accepted_paths = _README_MANIFEST_REFERENCES.get(readme_relative_path, (AUTHORITY_BOUNDARY_RELATIVE_PATH,))
    # Parse every Markdown link target out of the README and compare against
    # the accepted set as whole tokens. A substring like `../old/authority-
    # boundary.yaml` then no longer satisfies the canonical path
    # `authority-boundary.yaml`, and an inline code fence `code` that names
    # the accepted path still counts as a reference.
    link_targets = set(_MARKDOWN_LINK_TARGET_RE.findall(text))
    code_targets = set(_MARKDOWN_INLINE_CODE_RE.findall(text))
    referenced_tokens = link_targets | code_targets
    if not any(reference in referenced_tokens for reference in accepted_paths):
        failures.append(
            _fail(
                drift_rule,
                (
                    f"{readme_relative_path} must reference the canonical authority manifest at one of "
                    f"{list(accepted_paths)} as a Markdown link target or inline-code token; "
                    "a partial-substring like 'old/authority-boundary.yaml' does not satisfy this check"
                ),
                readme_relative_path,
            )
        )
    # ADR-019 must appear as a word-boundary match (so `ADR-0190` cannot
    # falsely satisfy it).
    if not re.search(rf"(?<!\w){re.escape(ADR_SEAM_REF)}(?!\w)", text):
        failures.append(
            _fail(
                drift_rule,
                f"{readme_relative_path} must reference {ADR_SEAM_REF} (canonical-seam ADR)",
                readme_relative_path,
            )
        )
    return failures


# --------------------------------------------------------------------------- #
# Top-level entry point.                                                      #
# --------------------------------------------------------------------------- #


def evaluate_authority_boundary(repo_root: Path) -> list[PolicyFailure]:
    """Return the list of structural failures for the ASR-517 authority boundary
    (empty list = OK)."""
    policy_path = repo_root / AUTHORITY_BOUNDARY_RELATIVE_PATH
    if not policy_path.is_file():
        return [
            _fail(
                "authority-boundary-missing",
                f"authority boundary policy not found: {AUTHORITY_BOUNDARY_RELATIVE_PATH}",
                AUTHORITY_BOUNDARY_RELATIVE_PATH,
            )
        ]

    try:
        raw = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [
            _fail(
                "authority-boundary-parse",
                f"failed to parse {AUTHORITY_BOUNDARY_RELATIVE_PATH}: {exc}",
                AUTHORITY_BOUNDARY_RELATIVE_PATH,
            )
        ]

    if not isinstance(raw, dict):
        return [
            _fail(
                "authority-boundary-shape",
                f"{AUTHORITY_BOUNDARY_RELATIVE_PATH} must be a YAML mapping at the top level",
                AUTHORITY_BOUNDARY_RELATIVE_PATH,
            )
        ]

    failures: list[PolicyFailure] = []
    failures.extend(_check_top_level_fields(raw, AUTHORITY_BOUNDARY_RELATIVE_PATH))
    failures.extend(_check_refs(raw, AUTHORITY_BOUNDARY_RELATIVE_PATH))

    authority_roots, authority_failures = _check_authority_roots(raw, AUTHORITY_BOUNDARY_RELATIVE_PATH)
    failures.extend(authority_failures)
    non_normative_roots, non_normative_failures = _check_non_normative_roots(raw, AUTHORITY_BOUNDARY_RELATIVE_PATH)
    failures.extend(non_normative_failures)
    failures.extend(_check_schema_authority_block(raw, AUTHORITY_BOUNDARY_RELATIVE_PATH))
    failures.extend(
        _check_normative_artifact_families(
            repo_root,
            raw,
            authority_roots,
            non_normative_roots,
            AUTHORITY_BOUNDARY_RELATIVE_PATH,
        )
    )

    legacy_dirs = _str_list(raw.get("legacy_top_level_dirs")) or []
    # The YAML's legacy list must be a superset of the canonical floor that
    # ADR-009 transitioned out. Without this check, a contributor could
    # silently drop `schemas` from `legacy_top_level_dirs` to allow it back
    # as a non-normative bucket and slip past the gate.
    missing_legacy = set(CANONICAL_LEGACY_TOP_LEVEL_DIRS) - set(legacy_dirs)
    if missing_legacy:
        failures.append(
            _fail(
                "authority-boundary-legacy-floor",
                (
                    f"legacy_top_level_dirs must include the ADR-009 floor "
                    f"{list(CANONICAL_LEGACY_TOP_LEVEL_DIRS)}; missing {sorted(missing_legacy)}"
                ),
                AUTHORITY_BOUNDARY_RELATIVE_PATH,
            )
        )

    # Reject any root that is classified into more than one category before
    # the existence and unclassified-top-level checks run — overlapping
    # classification is a YAML-level error, independent of disk state.
    failures.extend(_check_root_categorisation_overlap(authority_roots, non_normative_roots, legacy_dirs))

    failures.extend(_check_root_exists(repo_root, authority_roots, non_normative_roots))
    failures.extend(_check_legacy_dirs_absent(repo_root, legacy_dirs))
    failures.extend(_check_unclassified_top_level(repo_root, authority_roots, non_normative_roots, legacy_dirs))

    schema_block = raw.get("schema_authority")
    suffixes = (
        _str_list(schema_block.get("forbidden_schema_filename_suffixes")) if isinstance(schema_block, dict) else None
    )
    forbidden_roots = (
        _str_list(schema_block.get("forbidden_authority_roots")) if isinstance(schema_block, dict) else None
    )
    if suffixes and forbidden_roots:
        failures.extend(_check_schemas_outside_normative_root(repo_root, suffixes, forbidden_roots))

    failures.extend(_check_publication_manifest_present(repo_root))

    failures.extend(_check_adr_drift(repo_root, authority_roots))
    failures.extend(
        _check_readme_drift(
            repo_root,
            CONTRACTS_README_RELATIVE_PATH,
            "authority-boundary-contracts-readme-missing",
            "authority-boundary-contracts-readme-drift",
        )
    )
    failures.extend(
        _check_readme_drift(
            repo_root,
            SPECS_README_RELATIVE_PATH,
            "authority-boundary-specs-readme-missing",
            "authority-boundary-specs-readme-drift",
        )
    )

    return failures


# --------------------------------------------------------------------------- #
# CLI.                                                                        #
# --------------------------------------------------------------------------- #


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the ASR-517 normative-artifact authority boundary (ADR-009 / ADR-019)."
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
    failures = evaluate_authority_boundary(args.repo_root)
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
