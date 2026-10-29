#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Structural gate for the ASR-505 classification-based assurance policy.

ADR-007 ("Lightweight Formal Methods Policy") and the contributor-facing
``docs/explain/reference/coding-standards.md`` define the FM0/FM1/FM2/FM3
ladder. ASR-505 says the ecosystem shall *define* a classification-based
assurance policy that maps structural, semantic, graph, and stateful changes to
proportionate verification artifacts. The canonical mapping lives in
``specs/formal/assurance-policy.yaml`` -- one machine-readable artifact under
the normative ``specs/`` tree (per ADR-009) that every downstream doc and tool
references.

This checker pins the YAML's structural invariants and guards against drift
between the YAML and the three docs that name the levels (the immutable
ADR-007, the contributor-facing coding standards, and the formal-specs
overview). Failures use ``tools.policy.common.PolicyFailure`` and the CLI honours
``--json`` and the shared ``tools/policy/exceptions.yaml`` waiver mechanism,
matching the other policy gates (``check_repo_policy.py``,
``check_requirement_governance.py``, ``check_semantic_coverage.py``).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from datetime import date as date_cls
from datetime import datetime as datetime_cls
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

import yaml
from raes_contracts.errors import InvalidInputError
from raes_contracts.operational_logging import run_application

from tools.policy.common import (
    YAML_CONTENT_FAILURES,
    PolicyFailure,
    apply_exceptions,
    failures_to_json,
    load_exceptions,
    safe_repo_path,
)

# --------------------------------------------------------------------------- #
# Canonical paths and baseline policy invariants. Test code imports these     #
# directly so a rename here surfaces in the test suite, not silently in       #
# production. The validator otherwise derives its expectations from the YAML  #
# itself, so adding FM4 only requires editing the YAML plus mentioning FM4 in #
# each downstream doc; this baseline only encodes the floor the policy may    #
# not drop below.                                                             #
# --------------------------------------------------------------------------- #

ASSURANCE_POLICY_RELATIVE_PATH = "specs/formal/assurance-policy.yaml"
ADR_POLICY_RELATIVE_PATH = "docs/decisions/adrs/adr-007-lightweight-formal-methods-policy.md"
CODING_STANDARDS_RELATIVE_PATH = "docs/explain/reference/coding-standards.md"
FORMAL_OVERVIEW_RELATIVE_PATH = "docs/specs/formal.md"
ADR_TEMPLATE_RELATIVE_PATH = "docs/decisions/adrs/TEMPLATE.md"
ADR_DIRECTORY_RELATIVE_PATH = "docs/decisions/adrs"
FM_CLASSIFICATION_LEDGER_RELATIVE_PATH = "docs/explain/reference/fm-classification-ledger.yaml"
# Per-classified-formal-subsystem fulfillment map (issue #485). Distinct from the
# per-change ADR ledger above: this records, for each classified subsystem under
# `specs/formal/<domain>/`, whether the required artifact kinds for its FM level
# are delivered (a concrete non-empty repo path) or explicitly waived (ISO date +
# tracking reference).
ASSURANCE_FULFILLMENT_RELATIVE_PATH = "specs/formal/assurance-fulfillment.yaml"
FORMAL_DOMAINS_RELATIVE_PATH = "specs/formal"

# The baseline canonical level ids. The YAML MAY add more levels (e.g. FM4),
# but these four are the floor and must always be present.
CANONICAL_LEVEL_IDS: tuple[str, ...] = ("FM0", "FM1", "FM2", "FM3")

# ADR-060 existed before this gate. ADR-061 and later ADRs must carry the
# explicit per-change FM classification record.
ADR_CLASSIFICATION_REQUIRED_FROM = 61
FM_LEDGER_RUNTIME_ADR_RANGE = range(23, 59)

# The four words in the ASR-505 statement -- the validator pins each to a
# specific level so reordering does not silently keep passing.
REQUIRED_CHANGE_CATEGORIES: tuple[str, ...] = ("structural", "semantic", "graph", "stateful")

# Which level owns which canonical change category. This is the category-to-
# level binding the requirement statement implies.
_LEVEL_PRIMARY_CATEGORY: dict[str, str] = {
    "FM0": "structural",
    "FM1": "semantic",
    "FM2": "graph",
    "FM3": "stateful",
}

REQUIREMENT_REF = "ASR-505"
# ADR-007 is the policy decision; ADR-018 is the canonical-seam decision that
# governs THIS file. Both must be named in the YAML so a future edit cannot
# silently sever the governance link without failing the gate.
ADR_REFS: tuple[str, ...] = ("ADR-007", "ADR-018")
# Kept for backwards compatibility / external imports — equals the first ADR ref.
ADR_REF = ADR_REFS[0]
POLICY_VALUE = "classification-based-assurance"

# Floor required-artifact obligations per level, sourced from ADR-007. The
# YAML may add MORE required artifacts to any level; it may not drop these.
# This is independent of the proportionality (superset) check.
_LEVEL_REQUIRED_FLOOR: dict[str, frozenset[str]] = {
    "FM0": frozenset({"unit_tests"}),
    "FM1": frozenset({"invariant_list", "unit_tests"}),
    "FM2": frozenset(
        {"invariant_list", "unit_tests", "typed_ir_or_contract_coverage", "property_based_or_differential_tests"}
    ),
    "FM3": frozenset(
        {
            "invariant_list",
            "unit_tests",
            "typed_ir_or_contract_coverage",
            "property_based_or_differential_tests",
            "abstract_state_machine_model",
        }
    ),
}

_REQUIRED_TOP_LEVEL_FIELDS: tuple[str, ...] = ("policy", "requirement_refs", "adr_refs", "levels")
_REQUIRED_LEVEL_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "scope",
    "change_categories",
    "required_artifacts",
)
_LEVEL_SEQUENCE_FIELDS: tuple[str, ...] = (
    "change_categories",
    "required_artifacts",
    "recommended_artifacts",
    "prohibited_artifacts",
)
_FM0_PROHIBITED_ARTIFACTS: frozenset[str] = frozenset({"TLA+", "Alloy"})
_ADR_FILE_RE = re.compile(r"^adr-(\d{3})-.+\.md$")
_ADR_CLASSIFICATION_RE = re.compile(r"^Classification:\s*(FM\d+)\s*$", re.MULTILINE)
_ADR_REQUIRED_ARTIFACTS_RE = re.compile(r"^Required artifacts:\s*(.+?)\s*$", re.MULTILINE)
_ADR_WAIVERS_RE = re.compile(r"^Waivers:\s*(.+?)\s*$", re.MULTILINE)
_LEDGER_VALUE = "per-change-fm-classification"
_FULFILLMENT_VALUE = "classification-based-assurance-fulfillment"
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_iso_date_waiver(value: Any) -> bool:
    """Return True only when ``value`` is a date-only ``YYYY-MM-DD`` value.

    Two shapes are accepted, mirroring how ``yaml.safe_load`` parses a waiver's
    ``date`` field:

    * A native YAML *date* scalar (``date: 2026-06-13``), which parses to a
      ``datetime.date``. A native YAML *timestamp* scalar
      (``date: 2026-06-13 10:30:00``) parses to a ``datetime.datetime`` -- which
      is a *subclass* of ``date`` -- and must be rejected, because the contract
      requires a date-only ``YYYY-MM-DD`` value, not a wall-clock timestamp.
    * A quoted string, which must parse as a real ``YYYY-MM-DD`` calendar date.
      The regex pins the textual shape (rejecting the broader forms that
      ``date.fromisoformat`` accepts on Python >= 3.11, e.g. ``20250101`` or
      ``2025-W01-1``); ``date.fromisoformat`` then enforces calendar validity, so
      impossible dates such as ``2025-13-45`` or ``2025-02-30`` are rejected
      rather than merely shape-matched.
    """
    if isinstance(value, datetime_cls):
        # datetime is a date subclass; a timestamp scalar is not a date-only value.
        return False
    if isinstance(value, date_cls):
        return True
    if not isinstance(value, str):
        return False
    if not _ISO_DATE_RE.match(value):
        return False
    try:
        date_cls.fromisoformat(value)
    except ValueError:
        return False
    return True


# Human-readable phrasings for each YAML artifact slug. The drift guard
# requires the union of required artifacts (across all levels in the YAML) to
# appear in each MUTABLE downstream doc (coding-standards.md, formal.md). A
# stale doc that drops one of these phrases entirely fails the gate. ADR-007
# is immutable, so it is exempt from this check.
_ARTIFACT_DOC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "unit_tests": ("unit tests",),
    "invariant_list": ("invariant",),  # matches "invariants", "invariant list", etc.
    "typed_ir_or_contract_coverage": ("typed IR", "contract coverage", "typed IR/contract"),
    "property_based_or_differential_tests": (
        "property-based",
        "differential test",
    ),
    "abstract_state_machine_model": ("abstract state-machine", "state-machine model"),
}


def _fail(rule_id: str, message: str, path: str | None) -> PolicyFailure:
    return PolicyFailure(rule_id, message, path)


def _check_top_level_fields(data: dict, path: str) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for field in _REQUIRED_TOP_LEVEL_FIELDS:
        if field not in data:
            failures.append(_fail("assurance-policy-field", f"missing required top-level field: {field}", path))
    if "policy" in data and data["policy"] != POLICY_VALUE:
        failures.append(
            _fail(
                "assurance-policy-value",
                f"policy field must be '{POLICY_VALUE}', got '{data['policy']}'",
                path,
            )
        )
    # Reject non-list sequence fields rather than silently coercing them to [].
    for field in ("requirement_refs", "adr_refs"):
        if field in data and not isinstance(data[field], list):
            failures.append(
                _fail(
                    "assurance-policy-field-type",
                    f"top-level field '{field}' must be a YAML list; got {type(data[field]).__name__}",
                    path,
                )
            )
    if "levels" in data and not isinstance(data["levels"], list):
        failures.append(
            _fail(
                "assurance-policy-field-type",
                f"top-level field 'levels' must be a YAML list; got {type(data['levels']).__name__}",
                path,
            )
        )
    return failures


def _check_refs(data: dict, path: str) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    requirement_refs = data.get("requirement_refs")
    adr_refs = data.get("adr_refs")
    # Top-level ref lists must contain only strings. Non-string entries are
    # surfaced as type failures rather than silently stringified.
    for field_name, value in (("requirement_refs", requirement_refs), ("adr_refs", adr_refs)):
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, str):
                    failures.append(
                        _fail(
                            "assurance-policy-field-type",
                            f"top-level field '{field_name}' must contain only strings; "
                            f"got non-string element {item!r}",
                            path,
                        )
                    )
    requirement_strs = _refs_sequence(requirement_refs)
    adr_strs = _refs_sequence(adr_refs)
    if isinstance(requirement_refs, list) and REQUIREMENT_REF not in requirement_strs:
        failures.append(
            _fail(
                "assurance-policy-requirement-ref",
                f"requirement_refs must include {REQUIREMENT_REF}",
                path,
            )
        )
    if isinstance(adr_refs, list):
        for required_adr in ADR_REFS:
            if required_adr not in adr_strs:
                failures.append(
                    _fail(
                        "assurance-policy-adr-ref",
                        f"adr_refs must include {required_adr}",
                        path,
                    )
                )
    return failures


def _level_sequence(level: dict, field: str) -> list[str]:
    """Return the level's sequence field as a list of strings.

    Non-string elements are silently dropped here so downstream set operations
    (proportionality, floor, category-binding) are not corrupted. The shape
    check in `_check_levels` separately reports any non-string element as a
    `assurance-policy-level-field-type` failure, so dropping them here does
    not mask the regression.
    """
    value = level.get(field)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _refs_sequence(value: Any) -> list[str]:
    """Same shape as `_level_sequence` but for top-level refs."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _check_levels(levels: list[Any], path: str) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []

    if not levels:
        failures.append(
            _fail(
                "assurance-policy-levels-empty",
                "levels list is empty; the policy must enumerate every canonical FM level",
                path,
            )
        )

    present_ids = [level.get("id") if isinstance(level, dict) else None for level in levels]

    # Every baseline canonical level must be present (FM0..FM3 is the floor).
    for expected in CANONICAL_LEVEL_IDS:
        if expected not in present_ids:
            failures.append(
                _fail(
                    "assurance-policy-level-missing",
                    f"levels list is missing canonical level {expected}",
                    path,
                )
            )

    # Level ids must be unique. `by_id` would otherwise silently keep only the
    # last entry, leaving a non-canonical mapping with ambiguous semantics.
    seen: set[str] = set()
    duplicates: list[str] = []
    for level_id in present_ids:
        if not isinstance(level_id, str):
            continue
        if level_id in seen:
            duplicates.append(level_id)
        else:
            seen.add(level_id)
    if duplicates:
        failures.append(
            _fail(
                "assurance-policy-level-duplicate",
                f"level ids must be unique; duplicates: {sorted(set(duplicates))}",
                path,
            )
        )

    # Every FM-numbered level must appear in ascending numeric order. This
    # covers the baseline canonical levels AND any future FM4+ -- inserting
    # FM4 before FM2 or between FM0 and FM1 is a failure.
    fm_numbered_ids = [lid for lid in present_ids if isinstance(lid, str) and _fm_index(lid) is not None]
    expected_fm_order = sorted(fm_numbered_ids, key=_fm_index)
    if fm_numbered_ids != expected_fm_order:
        failures.append(
            _fail(
                "assurance-policy-level-order",
                f"FM-numbered levels must appear in ascending numeric order; got {fm_numbered_ids}, "
                f"expected {expected_fm_order}",
                path,
            )
        )

    # Per-level shape: an FM level id, required keys, sequence fields actually lists.
    for index, level in enumerate(levels):
        if not isinstance(level, dict):
            failures.append(_fail("assurance-policy-level-field", f"level entry is not a mapping: {level!r}", path))
            continue
        # ADR-018 enumerates FM levels, so an id that is not FM-numbered would escape the order and
        # proportionality checks.
        if "id" in level and _fm_index(level["id"]) is None:
            failures.append(
                _fail("assurance-policy-level-id", f"level {index} id must be FM followed by ASCII digits", path)
            )
        for field in _REQUIRED_LEVEL_FIELDS:
            if field not in level:
                failures.append(
                    _fail(
                        "assurance-policy-level-field",
                        f"level '{level.get('id', '?')}' missing required field: {field}",
                        path,
                    )
                )
        for field in _LEVEL_SEQUENCE_FIELDS:
            value = level.get(field) if field in level else None
            if field in level and not isinstance(value, list):
                failures.append(
                    _fail(
                        "assurance-policy-level-field-type",
                        f"level '{level.get('id', '?')}' field '{field}' must be a YAML list; "
                        f"got {type(value).__name__}",
                        path,
                    )
                )
                continue
            if isinstance(value, list):
                for item in value:
                    if not isinstance(item, str):
                        failures.append(
                            _fail(
                                "assurance-policy-level-field-type",
                                f"level '{level.get('id', '?')}' field '{field}' must contain only "
                                f"strings; got non-string element {item!r}",
                                path,
                            )
                        )

    # Each level must claim its primary canonical category. This pins the
    # category-to-level binding, not just the union (the ASR-505 statement
    # guard).
    # Only a text id can name a canonical level; an unhashable id cannot be a dictionary key.
    by_id = {lv["id"]: lv for lv in levels if isinstance(lv, dict) and isinstance(lv.get("id"), str)}
    for level_id, expected_category in _LEVEL_PRIMARY_CATEGORY.items():
        level = by_id.get(level_id)
        if level is None:
            continue
        categories = _level_sequence(level, "change_categories")
        if expected_category not in categories:
            failures.append(
                _fail(
                    "assurance-policy-categories",
                    f"level {level_id} must claim canonical change category '{expected_category}' "
                    f"(per the ASR-505 statement); got {categories}",
                    path,
                )
            )

    # Belt-and-suspenders: the union of every level's change_categories must
    # still cover every word in the ASR-505 statement. This catches a future
    # level that drops one of the canonical words without triggering the
    # binding check above.
    category_union = {
        cat for level in levels if isinstance(level, dict) for cat in _level_sequence(level, "change_categories")
    }
    missing_categories = [cat for cat in REQUIRED_CHANGE_CATEGORIES if cat not in category_union]
    if missing_categories:
        failures.append(
            _fail(
                "assurance-policy-categories",
                f"change_categories union must include every word in the ASR-505 statement "
                f"({REQUIRED_CHANGE_CATEGORIES}); missing: {missing_categories}",
                path,
            )
        )

    # FM0 must prohibit TLA+ and Alloy explicitly.
    fm0 = by_id.get("FM0")
    if fm0 is not None:
        prohibited = set(_level_sequence(fm0, "prohibited_artifacts"))
        missing = sorted(_FM0_PROHIBITED_ARTIFACTS - prohibited)
        if missing:
            failures.append(
                _fail(
                    "assurance-policy-fm0-prohibited",
                    f"FM0 must list {sorted(_FM0_PROHIBITED_ARTIFACTS)} in prohibited_artifacts; missing: {missing}",
                    path,
                )
            )

    # Per-level required-artifact floor (from ADR-007). The YAML may require
    # MORE; it may not require less.
    for level_id, floor in _LEVEL_REQUIRED_FLOOR.items():
        level = by_id.get(level_id)
        if level is None:
            continue
        required = set(_level_sequence(level, "required_artifacts"))
        missing = sorted(floor - required)
        if missing:
            failures.append(
                _fail(
                    "assurance-policy-required-floor",
                    f"{level_id}'s required_artifacts must include the ADR-007 floor; missing: {missing}",
                    path,
                )
            )

    # Required and prohibited sets must be disjoint per level.
    for level in levels:
        if not isinstance(level, dict):
            continue
        required = set(_level_sequence(level, "required_artifacts"))
        prohibited = set(_level_sequence(level, "prohibited_artifacts"))
        overlap = sorted(required & prohibited)
        if overlap:
            failures.append(
                _fail(
                    "assurance-policy-required-prohibited-overlap",
                    f"level '{level.get('id', '?')}' has artifacts in both required_artifacts and "
                    f"prohibited_artifacts: {overlap}",
                    path,
                )
            )

    # Consecutive-pair proportionality across every FM-numbered level, not
    # just FM2/FM3. FM4 (if present) must be a superset of FM3, and so on.
    fm_levels_ordered = sorted(
        (lv for lv in levels if isinstance(lv, dict) and _fm_index(lv.get("id")) is not None),
        key=lambda lv: _fm_index(lv.get("id")),
    )
    for parent, child in zip(fm_levels_ordered, fm_levels_ordered[1:], strict=False):
        child_id = child.get("id", "?")
        parent_id = parent.get("id", "?")
        child_set = set(_level_sequence(child, "required_artifacts"))
        parent_set = set(_level_sequence(parent, "required_artifacts"))
        missing = sorted(parent_set - child_set)
        if missing:
            failures.append(
                _fail(
                    "assurance-policy-proportionality",
                    f"{child_id}'s required_artifacts must be a superset of {parent_id}'s; "
                    f"missing from {child_id}: {missing}",
                    path,
                )
            )

    return failures


def _fm_index(level_id: object) -> tuple[int, str] | None:
    """Return the numeric order key of an FM-numbered level id, else None.

    The key compares the significant digits by count and then by value, so FM10
    follows FM9 without int(), which refuses a string beyond the interpreter
    digit limit.
    """
    if not isinstance(level_id, str) or not level_id.startswith("FM"):
        return None
    suffix = level_id[2:]
    # str.isdigit() also accepts digits that int() refuses, such as "²".
    if not (suffix.isascii() and suffix.isdigit()):
        return None
    digits = suffix.lstrip("0") or "0"
    return len(digits), digits


def _drift_targets(levels: list[Any]) -> list[tuple[str, str]]:
    """Return (level_id, level_name) pairs that mutable downstream docs must mention.

    Names are derived from the YAML so a future FM4 (or a name change to an
    existing level) flows through to every drift check without editing this
    file. The id is checked AS-IS; the name is checked after collapsing runs
    of whitespace, since Markdown sometimes wraps long names.
    """
    targets: list[tuple[str, str]] = []
    for level in levels:
        if not isinstance(level, dict):
            continue
        level_id = level.get("id")
        name = level.get("name")
        if isinstance(level_id, str) and isinstance(name, str):
            targets.append((level_id, name))
    return targets


def _baseline_drift_targets(levels: list[Any]) -> list[tuple[str, str]]:
    """Return drift targets restricted to the BASELINE canonical levels.

    Used for ADR-007, which is immutable per the ADR README and therefore
    cannot be required to mention a future FM4. The baseline floor (FM0..FM3)
    is fixed at policy adoption time; ADR-007 is required to mention it, and
    nothing more. Extending the ladder requires a superseding or
    complementary ADR (e.g. ADR-018, which governs the canonical YAML).
    """
    # Only a text id can name a canonical level; an unhashable id cannot be a dictionary key.
    by_id = {lv["id"]: lv for lv in levels if isinstance(lv, dict) and isinstance(lv.get("id"), str)}
    targets: list[tuple[str, str]] = []
    for canonical_id in CANONICAL_LEVEL_IDS:
        level = by_id.get(canonical_id)
        if not isinstance(level, dict):
            # Level missing — _check_levels reports it separately. Fall back
            # to id-only so the drift guard still runs.
            targets.append((canonical_id, ""))
            continue
        name = level.get("name")
        targets.append((canonical_id, name if isinstance(name, str) else ""))
    return targets


def _required_artifact_union(levels: list[Any]) -> set[str]:
    """Return the union of YAML required_artifacts across every level."""
    union: set[str] = set()
    for level in levels:
        if isinstance(level, dict):
            union.update(_level_sequence(level, "required_artifacts"))
    return union


def _level_ids(levels: list[Any]) -> set[str]:
    """Return valid FM level ids from the canonical YAML."""
    return {level["id"] for level in levels if isinstance(level, dict) and isinstance(level.get("id"), str)}


def _required_artifacts_by_level(levels: list[Any]) -> dict[str, set[str]]:
    """Return YAML-required artifact kinds per FM level."""
    by_level: dict[str, set[str]] = {}
    for level in levels:
        if isinstance(level, dict) and isinstance(level.get("id"), str):
            by_level[level["id"]] = set(_level_sequence(level, "required_artifacts"))
    return by_level


def _is_filled_field(value: str | None) -> bool:
    """Return true when a template field has been replaced with a real value."""
    if value is None:
        return False
    normalized = value.strip().lower()
    if not normalized:
        return False
    if normalized in {"tbd", "todo", "none yet", "n/a"}:
        return False
    return "<" not in value and "..." not in value


def _adr_number(path: Path) -> int | None:
    match = _ADR_FILE_RE.match(path.name)
    if not match:
        return None
    return int(match.group(1))


def _adr_id_from_number(number: int) -> str:
    return f"ADR-{number:03d}"


def _find_adr_path(repo_root: Path, adr_id: str) -> Path | None:
    suffix = adr_id.removeprefix("ADR-")
    if not suffix.isdigit():
        return None
    adr_dir = repo_root / ADR_DIRECTORY_RELATIVE_PATH
    matches = sorted(adr_dir.glob(f"adr-{suffix}-*.md"))
    return matches[0] if matches else None


def _resolve_repo_path(repo_root: Path, relative_path: str) -> Path | None:
    root = repo_root.resolve()
    candidate = (root / relative_path).resolve()
    if candidate == root or root in candidate.parents:
        return candidate
    return None


def _check_adr_template_classification(repo_root: Path) -> list[PolicyFailure]:
    template_path = repo_root / ADR_TEMPLATE_RELATIVE_PATH
    if not template_path.is_file():
        return [_fail("adr-template-classification", "ADR template is missing", ADR_TEMPLATE_RELATIVE_PATH)]
    text = template_path.read_text(encoding="utf-8")
    required_snippets = (
        "## Classification",
        "Classification: FM<n>",
        "Required artifacts:",
        "Waivers:",
    )
    missing = [snippet for snippet in required_snippets if snippet not in text]
    if missing:
        return [
            _fail(
                "adr-template-classification",
                "ADR template is missing FM classification field(s): " + ", ".join(missing),
                ADR_TEMPLATE_RELATIVE_PATH,
            )
        ]
    return []


def _check_new_adr_classifications(repo_root: Path, level_ids: set[str]) -> list[PolicyFailure]:
    adr_dir = repo_root / ADR_DIRECTORY_RELATIVE_PATH
    if not adr_dir.is_dir():
        return []
    failures: list[PolicyFailure] = []
    for adr_path in sorted(adr_dir.glob("adr-*.md")):
        number = _adr_number(adr_path)
        if number is None or number < ADR_CLASSIFICATION_REQUIRED_FROM:
            continue
        rel_path = adr_path.relative_to(repo_root).as_posix()
        text = adr_path.read_text(encoding="utf-8")
        classification_matches = _ADR_CLASSIFICATION_RE.findall(text)
        if len(classification_matches) != 1:
            failures.append(
                _fail(
                    "adr-classification-missing",
                    f"{_adr_id_from_number(number)} must contain exactly one 'Classification: FM<n>' field",
                    rel_path,
                )
            )
            continue
        level_id = classification_matches[0]
        if level_id not in level_ids:
            failures.append(
                _fail(
                    "adr-classification-level",
                    f"{_adr_id_from_number(number)} classification level {level_id} "
                    f"is not defined in {ASSURANCE_POLICY_RELATIVE_PATH}",
                    rel_path,
                )
            )
        artifacts_match = _ADR_REQUIRED_ARTIFACTS_RE.search(text)
        if not _is_filled_field(artifacts_match.group(1) if artifacts_match else None):
            failures.append(
                _fail(
                    "adr-classification-artifacts",
                    f"{_adr_id_from_number(number)} must name required artifacts delivered or waived",
                    rel_path,
                )
            )
        waivers_match = _ADR_WAIVERS_RE.search(text)
        if not _is_filled_field(waivers_match.group(1) if waivers_match else None):
            failures.append(
                _fail(
                    "adr-classification-waivers",
                    f"{_adr_id_from_number(number)} must name waivers or explicitly say none",
                    rel_path,
                )
            )
    return failures


def _runtime_adr_ids_present(repo_root: Path) -> set[str]:
    adr_dir = repo_root / ADR_DIRECTORY_RELATIVE_PATH
    if not adr_dir.is_dir():
        return set()
    present: set[str] = set()
    for path in adr_dir.glob("adr-*.md"):
        number = _adr_number(path)
        if number in FM_LEDGER_RUNTIME_ADR_RANGE:
            present.add(_adr_id_from_number(number))
    return present


def _check_ledger_artifact(
    repo_root: Path,
    entry_id: str,
    artifact: Any,
    valid_artifact_kinds: set[str],
    index: int,
) -> tuple[str | None, list[PolicyFailure]]:
    path = FM_CLASSIFICATION_LEDGER_RELATIVE_PATH
    if not isinstance(artifact, dict):
        return None, [
            _fail(
                "fm-classification-ledger-artifact",
                f"{entry_id} delivered_artifacts[{index}] must be a mapping",
                path,
            )
        ]
    kind = artifact.get("kind")
    artifact_path = artifact.get("path")
    failures: list[PolicyFailure] = []
    if not isinstance(kind, str) or kind not in valid_artifact_kinds:
        failures.append(
            _fail(
                "fm-classification-ledger-artifact",
                f"{entry_id} delivered_artifacts[{index}].kind must be one of "
                f"{sorted(valid_artifact_kinds)}; got {kind!r}",
                path,
            )
        )
    if not isinstance(artifact_path, str) or not artifact_path.strip():
        failures.append(
            _fail(
                "fm-classification-ledger-artifact",
                f"{entry_id} delivered_artifacts[{index}].path must be a non-empty repo-relative path",
                path,
            )
        )
    else:
        resolved = _resolve_repo_path(repo_root, artifact_path)
        if resolved is None:
            failures.append(
                _fail(
                    "fm-classification-ledger-artifact",
                    f"{entry_id} delivered artifact path escapes the repo root: {artifact_path}",
                    path,
                )
            )
        elif not resolved.exists():
            failures.append(
                _fail(
                    "fm-classification-ledger-artifact",
                    f"{entry_id} delivered artifact path does not exist: {artifact_path}",
                    path,
                )
            )
    return kind if isinstance(kind, str) else None, failures


def _check_ledger_waiver(
    entry_id: str,
    waiver: Any,
    valid_artifact_kinds: set[str],
    index: int,
) -> tuple[str | None, list[PolicyFailure]]:
    path = FM_CLASSIFICATION_LEDGER_RELATIVE_PATH
    if not isinstance(waiver, dict):
        return None, [
            _fail(
                "fm-classification-ledger-waiver",
                f"{entry_id} waived_artifacts[{index}] must be a mapping",
                path,
            )
        ]
    kind = waiver.get("kind")
    rationale = waiver.get("rationale")
    failures: list[PolicyFailure] = []
    if not isinstance(kind, str) or kind not in valid_artifact_kinds:
        failures.append(
            _fail(
                "fm-classification-ledger-waiver",
                f"{entry_id} waived_artifacts[{index}].kind must be one of "
                f"{sorted(valid_artifact_kinds)}; got {kind!r}",
                path,
            )
        )
    if not isinstance(rationale, str) or not rationale.strip():
        failures.append(
            _fail(
                "fm-classification-ledger-waiver",
                f"{entry_id} waived_artifacts[{index}].rationale must be non-empty",
                path,
            )
        )
    return kind if isinstance(kind, str) else None, failures


def _check_fm_classification_ledger(repo_root: Path, levels: list[Any]) -> list[PolicyFailure]:
    ledger_path = repo_root / FM_CLASSIFICATION_LEDGER_RELATIVE_PATH
    if not ledger_path.is_file():
        return [
            _fail(
                "fm-classification-ledger-missing",
                f"FM classification ledger not found: {FM_CLASSIFICATION_LEDGER_RELATIVE_PATH}",
                FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
            )
        ]
    try:
        raw = yaml.safe_load(ledger_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [
            _fail(
                "fm-classification-ledger-parse",
                f"failed to parse {FM_CLASSIFICATION_LEDGER_RELATIVE_PATH}: {exc}",
                FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
            )
        ]
    except YAML_CONTENT_FAILURES:
        return [
            _fail(
                "fm-classification-ledger-parse",
                f"failed to parse {FM_CLASSIFICATION_LEDGER_RELATIVE_PATH}",
                FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
            )
        ]
    if not isinstance(raw, dict):
        return [
            _fail(
                "fm-classification-ledger-shape",
                f"{FM_CLASSIFICATION_LEDGER_RELATIVE_PATH} must be a YAML mapping at the top level",
                FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
            )
        ]

    failures: list[PolicyFailure] = []
    if raw.get("ledger") != _LEDGER_VALUE:
        failures.append(
            _fail(
                "fm-classification-ledger-field",
                f"ledger field must be {_LEDGER_VALUE!r}",
                FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
            )
        )
    if raw.get("policy_ref") != ASSURANCE_POLICY_RELATIVE_PATH:
        failures.append(
            _fail(
                "fm-classification-ledger-policy-ref",
                f"policy_ref must be {ASSURANCE_POLICY_RELATIVE_PATH}",
                FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
            )
        )

    entries = raw.get("entries")
    if not isinstance(entries, list):
        return failures + [
            _fail(
                "fm-classification-ledger-field",
                "entries must be a YAML list",
                FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
            )
        ]

    level_ids = _level_ids(levels)
    required_by_level = _required_artifacts_by_level(levels)
    valid_artifact_kinds = _required_artifact_union(levels)
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            failures.append(
                _fail(
                    "fm-classification-ledger-entry",
                    f"entries[{index}] must be a mapping",
                    FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
                )
            )
            continue
        adr = entry.get("adr")
        entry_id = adr if isinstance(adr, str) else f"entries[{index}]"
        if not isinstance(adr, str) or not re.fullmatch(r"ADR-\d{3}", adr):
            failures.append(
                _fail(
                    "fm-classification-ledger-entry",
                    f"entries[{index}].adr must be an ADR-NNN id",
                    FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
                )
            )
        elif adr in seen:
            failures.append(
                _fail(
                    "fm-classification-ledger-duplicate",
                    f"ledger contains duplicate entry for {adr}",
                    FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
                )
            )
        else:
            seen.add(adr)
            if _find_adr_path(repo_root, adr) is None:
                failures.append(
                    _fail(
                        "fm-classification-ledger-entry",
                        f"{adr} does not resolve to an ADR file under {ADR_DIRECTORY_RELATIVE_PATH}",
                        FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
                    )
                )
        surface = entry.get("surface")
        if not isinstance(surface, str) or not surface.strip():
            failures.append(
                _fail(
                    "fm-classification-ledger-entry",
                    f"{entry_id}.surface must be non-empty",
                    FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
                )
            )
        fm_level = entry.get("fm_level")
        if not isinstance(fm_level, str) or fm_level not in level_ids:
            failures.append(
                _fail(
                    "fm-classification-ledger-level",
                    f"{entry_id}.fm_level {fm_level!r} is not defined in {ASSURANCE_POLICY_RELATIVE_PATH}",
                    FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
                )
            )
            required = set()
        else:
            required = required_by_level.get(fm_level, set())

        delivered = entry.get("delivered_artifacts")
        if not isinstance(delivered, list):
            failures.append(
                _fail(
                    "fm-classification-ledger-artifact",
                    f"{entry_id}.delivered_artifacts must be a YAML list",
                    FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
                )
            )
            delivered = []
        delivered_kinds: set[str] = set()
        for artifact_index, artifact in enumerate(delivered):
            kind, artifact_failures = _check_ledger_artifact(
                repo_root,
                entry_id,
                artifact,
                valid_artifact_kinds,
                artifact_index,
            )
            if kind is not None:
                delivered_kinds.add(kind)
            failures.extend(artifact_failures)

        waived = entry.get("waived_artifacts", [])
        if not isinstance(waived, list):
            failures.append(
                _fail(
                    "fm-classification-ledger-waiver",
                    f"{entry_id}.waived_artifacts must be a YAML list when present",
                    FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
                )
            )
            waived = []
        waived_kinds: set[str] = set()
        for waiver_index, waiver in enumerate(waived):
            kind, waiver_failures = _check_ledger_waiver(
                entry_id,
                waiver,
                valid_artifact_kinds,
                waiver_index,
            )
            if kind is not None:
                waived_kinds.add(kind)
            failures.extend(waiver_failures)

        missing_required = sorted(required - delivered_kinds - waived_kinds)
        if missing_required:
            failures.append(
                _fail(
                    "fm-classification-ledger-artifacts",
                    f"{entry_id} ({fm_level}) must deliver or waive required artifact kind(s): {missing_required}",
                    FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
                )
            )

    missing = sorted(_runtime_adr_ids_present(repo_root) - seen)
    if missing:
        failures.append(
            _fail(
                "fm-classification-ledger-coverage",
                f"ledger must cover existing runtime-surface ADRs {FM_LEDGER_RUNTIME_ADR_RANGE.start:03d}-"
                f"{FM_LEDGER_RUNTIME_ADR_RANGE.stop - 1:03d}; missing: {missing}",
                FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
            )
        )
    return failures


def _classified_formal_domains(repo_root: Path) -> list[str]:
    """Return repo-relative paths of classified formal-spec subsystems.

    A classified subsystem is an immediate subdirectory of ``specs/formal/`` that
    carries a ``README.md`` -- the domain-marker convention documented in
    ``specs/formal/README.md`` ("Each domain directory should include a short
    README"). This is the independent source of truth the fulfillment registry is
    checked against, so a new ``specs/formal/<domain>/`` that forgets a registry
    entry fails the gate instead of being silently un-tracked.
    """
    formal_dir = repo_root / FORMAL_DOMAINS_RELATIVE_PATH
    if not formal_dir.is_dir():
        return []
    domains: list[str] = []
    for child in sorted(formal_dir.iterdir()):
        if child.is_dir() and (child / "README.md").is_file():
            domains.append(child.relative_to(repo_root).as_posix())
    return domains


def _check_fulfillment_delivered(
    repo_root: Path,
    entry_id: str,
    delivered: Any,
    valid_artifact_kinds: set[str],
) -> tuple[set[str], list[PolicyFailure]]:
    """Validate an entry's ``delivered_artifacts`` and return the satisfied kinds.

    A kind counts as delivered only when its kind is valid AND its path resolves
    inside the repo to an existing, non-empty file.
    """
    path = ASSURANCE_FULFILLMENT_RELATIVE_PATH
    failures: list[PolicyFailure] = []
    kinds: set[str] = set()
    if delivered is None:
        return kinds, failures  # absent list is fine -- required kinds may all be waived.
    if not isinstance(delivered, list):
        return kinds, [
            _fail("assurance-fulfillment-artifact", f"{entry_id}.delivered_artifacts must be a YAML list", path)
        ]
    for index, artifact in enumerate(delivered):
        if not isinstance(artifact, dict):
            failures.append(
                _fail(
                    "assurance-fulfillment-artifact", f"{entry_id}.delivered_artifacts[{index}] must be a mapping", path
                )
            )
            continue
        kind = artifact.get("kind")
        artifact_path = artifact.get("path")
        kind_ok = isinstance(kind, str) and kind in valid_artifact_kinds
        if not kind_ok:
            failures.append(
                _fail(
                    "assurance-fulfillment-artifact",
                    f"{entry_id}.delivered_artifacts[{index}].kind must be one of "
                    f"{sorted(valid_artifact_kinds)}; got {kind!r}",
                    path,
                )
            )
        path_ok = False
        if not isinstance(artifact_path, str) or not artifact_path.strip():
            failures.append(
                _fail(
                    "assurance-fulfillment-artifact",
                    f"{entry_id}.delivered_artifacts[{index}].path must be a non-empty repo-relative path",
                    path,
                )
            )
        else:
            resolved = safe_repo_path(repo_root, artifact_path)
            if resolved is None:
                failures.append(
                    _fail(
                        "assurance-fulfillment-artifact",
                        f"{entry_id} delivered artifact path escapes the repo root: {artifact_path}",
                        path,
                    )
                )
            elif not resolved.is_file():
                failures.append(
                    _fail(
                        "assurance-fulfillment-artifact",
                        f"{entry_id} delivered artifact path does not exist: {artifact_path}",
                        path,
                    )
                )
            elif resolved.stat().st_size == 0:
                failures.append(
                    _fail(
                        "assurance-fulfillment-artifact",
                        f"{entry_id} delivered artifact path is empty: {artifact_path}",
                        path,
                    )
                )
            else:
                path_ok = True
        if kind_ok and path_ok:
            kinds.add(kind)
    return kinds, failures


def _check_fulfillment_waived(
    entry_id: str,
    waived: Any,
    valid_artifact_kinds: set[str],
) -> tuple[set[str], list[PolicyFailure]]:
    """Validate an entry's ``waived_artifacts`` and return the waived kinds.

    A waiver counts only when it names a valid kind, an ISO ``date``, at least one
    ``tracking`` reference, and a non-empty ``rationale``.
    """
    path = ASSURANCE_FULFILLMENT_RELATIVE_PATH
    failures: list[PolicyFailure] = []
    kinds: set[str] = set()
    if waived is None:
        return kinds, failures
    if not isinstance(waived, list):
        return kinds, [
            _fail("assurance-fulfillment-waiver", f"{entry_id}.waived_artifacts must be a YAML list when present", path)
        ]
    for index, waiver in enumerate(waived):
        if not isinstance(waiver, dict):
            failures.append(
                _fail("assurance-fulfillment-waiver", f"{entry_id}.waived_artifacts[{index}] must be a mapping", path)
            )
            continue
        kind = waiver.get("kind")
        waiver_date = waiver.get("date")
        tracking = waiver.get("tracking")
        rationale = waiver.get("rationale")
        kind_ok = isinstance(kind, str) and kind in valid_artifact_kinds
        if not kind_ok:
            failures.append(
                _fail(
                    "assurance-fulfillment-waiver",
                    f"{entry_id}.waived_artifacts[{index}].kind must be one of "
                    f"{sorted(valid_artifact_kinds)}; got {kind!r}",
                    path,
                )
            )
        date_ok = _is_iso_date_waiver(waiver_date)
        if not date_ok:
            failures.append(
                _fail(
                    "assurance-fulfillment-waiver",
                    f"{entry_id} waiver for {kind!r} must carry an ISO date (YYYY-MM-DD); got {waiver_date!r}",
                    path,
                )
            )
        tracking_ok = isinstance(tracking, list) and any(isinstance(ref, str) and ref.strip() for ref in tracking)
        if not tracking_ok:
            failures.append(
                _fail(
                    "assurance-fulfillment-waiver",
                    f"{entry_id} waiver for {kind!r} must name at least one tracking reference",
                    path,
                )
            )
        rationale_ok = isinstance(rationale, str) and bool(rationale.strip())
        if not rationale_ok:
            failures.append(
                _fail(
                    "assurance-fulfillment-waiver",
                    f"{entry_id} waiver for {kind!r} must carry a non-empty rationale",
                    path,
                )
            )
        if kind_ok and date_ok and tracking_ok and rationale_ok:
            kinds.add(kind)
    return kinds, failures


def _check_assurance_fulfillment(repo_root: Path, levels: list[Any]) -> list[PolicyFailure]:
    """Validate the per-subsystem assurance fulfillment map (issue #485).

    Every classified formal-spec subsystem must appear in the registry; every
    registry subsystem must have a fulfillment entry (and vice-versa); and every
    required artifact kind for the subsystem's FM level -- derived from
    ``assurance-policy.yaml`` -- must be delivered (non-empty repo path) or waived
    (ISO date + tracking reference).
    """
    path = ASSURANCE_FULFILLMENT_RELATIVE_PATH
    fulfillment_path = repo_root / path
    if not fulfillment_path.is_file():
        return [_fail("assurance-fulfillment-missing", f"assurance fulfillment map not found: {path}", path)]
    try:
        raw = yaml.safe_load(fulfillment_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [_fail("assurance-fulfillment-parse", f"failed to parse {path}: {exc}", path)]
    except YAML_CONTENT_FAILURES:
        return [_fail("assurance-fulfillment-parse", f"failed to parse {path}", path)]
    if not isinstance(raw, dict):
        return [_fail("assurance-fulfillment-shape", f"{path} must be a YAML mapping at the top level", path)]

    failures: list[PolicyFailure] = []
    if raw.get("fulfillment") != _FULFILLMENT_VALUE:
        failures.append(_fail("assurance-fulfillment-field", f"fulfillment field must be {_FULFILLMENT_VALUE!r}", path))
    if raw.get("policy_ref") != ASSURANCE_POLICY_RELATIVE_PATH:
        failures.append(
            _fail("assurance-fulfillment-field", f"policy_ref must be {ASSURANCE_POLICY_RELATIVE_PATH}", path)
        )
    adr_refs = raw.get("adr_refs")
    if not isinstance(adr_refs, list):
        failures.append(_fail("assurance-fulfillment-field", "adr_refs must be a YAML list", path))
    else:
        adr_strs = _refs_sequence(adr_refs)
        for required_adr in ADR_REFS:
            if required_adr not in adr_strs:
                failures.append(_fail("assurance-fulfillment-field", f"adr_refs must include {required_adr}", path))

    level_ids = _level_ids(levels)
    required_by_level = _required_artifacts_by_level(levels)
    valid_artifact_kinds = _required_artifact_union(levels)

    # --- subsystem registry: {id, path, fm_level} ---
    # The registry's path boundary is the classified formal-domain set itself --
    # immediate `specs/formal/<domain>/` subdirectories carrying a README.md (per
    # the issue #485 preflight and the specs/formal/README.md domain-marker
    # convention). A registry entry pointing anywhere else
    # (some other repo dir that merely happens to hold a README) is rejected, so
    # the fulfillment surface cannot drift outside the declared ownership
    # boundary.
    formal_domain_paths = set(_classified_formal_domains(repo_root))
    subsystems = raw.get("subsystems")
    if not isinstance(subsystems, list):
        failures.append(_fail("assurance-fulfillment-field", "subsystems must be a YAML list", path))
        subsystems = []
    registry: dict[str, dict] = {}
    registered_paths: set[str] = set()
    seen_ids: set[str] = set()
    for index, sub in enumerate(subsystems):
        if not isinstance(sub, dict):
            failures.append(_fail("assurance-fulfillment-subsystem", f"subsystems[{index}] must be a mapping", path))
            continue
        sub_id = sub.get("id")
        sub_path = sub.get("path")
        fm_level = sub.get("fm_level")
        ident = sub_id if isinstance(sub_id, str) and sub_id.strip() else f"subsystems[{index}]"
        if not isinstance(sub_id, str) or not sub_id.strip():
            failures.append(
                _fail("assurance-fulfillment-subsystem", f"subsystems[{index}].id must be a non-empty string", path)
            )
            sub_id = None
        elif sub_id in seen_ids:
            failures.append(_fail("assurance-fulfillment-subsystem", f"duplicate subsystem id: {sub_id}", path))
        else:
            seen_ids.add(sub_id)
        resolved_rel: str | None = None
        if not isinstance(sub_path, str) or not sub_path.strip():
            failures.append(
                _fail("assurance-fulfillment-subsystem", f"{ident}.path must be a non-empty repo-relative path", path)
            )
        else:
            resolved = safe_repo_path(repo_root, sub_path)
            if resolved is None:
                failures.append(
                    _fail("assurance-fulfillment-subsystem", f"{ident}.path escapes the repo root: {sub_path}", path)
                )
            else:
                candidate_rel = resolved.relative_to(repo_root.resolve()).as_posix()
                if candidate_rel not in formal_domain_paths:
                    failures.append(
                        _fail(
                            "assurance-fulfillment-subsystem",
                            f"{ident}.path is not a classified formal-spec domain "
                            f"(must be an immediate specs/formal/<domain>/ directory containing README.md): {sub_path}",
                            path,
                        )
                    )
                elif candidate_rel in registered_paths:
                    failures.append(
                        _fail(
                            "assurance-fulfillment-subsystem",
                            f"{ident}.path duplicates another registry entry's path: {sub_path}",
                            path,
                        )
                    )
                else:
                    resolved_rel = candidate_rel
                    registered_paths.add(resolved_rel)
        if not isinstance(fm_level, str) or fm_level not in level_ids:
            failures.append(
                _fail(
                    "assurance-fulfillment-level",
                    f"{ident}.fm_level {fm_level!r} is not defined in {ASSURANCE_POLICY_RELATIVE_PATH}",
                    path,
                )
            )
            fm_level = None
        if isinstance(sub_id, str) and sub_id.strip() and sub_id not in registry:
            registry[sub_id] = {"path": resolved_rel, "fm_level": fm_level}

    # --- coverage: every classified domain dir must be registered ---
    for domain_rel in _classified_formal_domains(repo_root):
        if domain_rel not in registered_paths:
            failures.append(
                _fail(
                    "assurance-fulfillment-coverage",
                    f"classified formal subsystem is absent from the fulfillment registry: {domain_rel}",
                    path,
                )
            )

    # --- fulfillment entries keyed by subsystem id ---
    entries = raw.get("entries")
    if not isinstance(entries, list):
        failures.append(_fail("assurance-fulfillment-field", "entries must be a YAML list", path))
        entries = []
    entry_subsystems: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            failures.append(_fail("assurance-fulfillment-entry", f"entries[{index}] must be a mapping", path))
            continue
        sub_id = entry.get("subsystem")
        if not isinstance(sub_id, str) or not sub_id.strip():
            failures.append(
                _fail("assurance-fulfillment-entry", f"entries[{index}].subsystem must be a non-empty string", path)
            )
            continue
        if sub_id in entry_subsystems:
            failures.append(
                _fail("assurance-fulfillment-entry", f"duplicate fulfillment entry for subsystem: {sub_id}", path)
            )
            continue
        entry_subsystems.add(sub_id)
        if sub_id not in registry:
            failures.append(
                _fail(
                    "assurance-fulfillment-entry-unknown",
                    f"fulfillment entry references subsystem {sub_id!r} not in the registry",
                    path,
                )
            )
            continue
        fm_level = registry[sub_id]["fm_level"]
        required = required_by_level.get(fm_level, set()) if fm_level else set()
        delivered_kinds, deliver_failures = _check_fulfillment_delivered(
            repo_root, sub_id, entry.get("delivered_artifacts"), valid_artifact_kinds
        )
        failures.extend(deliver_failures)
        waived_kinds, waiver_failures = _check_fulfillment_waived(
            sub_id, entry.get("waived_artifacts"), valid_artifact_kinds
        )
        failures.extend(waiver_failures)
        missing_required = sorted(required - delivered_kinds - waived_kinds)
        if missing_required:
            failures.append(
                _fail(
                    "assurance-fulfillment-artifacts",
                    f"{sub_id} ({fm_level}) must deliver or waive required artifact kind(s): {missing_required}",
                    path,
                )
            )

    # --- every registry subsystem must have a fulfillment entry ---
    for sub_id in registry:
        if sub_id not in entry_subsystems:
            failures.append(
                _fail(
                    "assurance-fulfillment-entry-missing",
                    f"classified subsystem {sub_id!r} is in the registry but has no fulfillment entry",
                    path,
                )
            )

    return failures


def _check_artifact_keyword_drift(
    repo_root: Path,
    doc_rel: str,
    drift_rule_id: str,
    required_artifacts: set[str],
) -> list[PolicyFailure]:
    """Verify each YAML-required artifact has at least one keyword variant in the doc.

    Applied only to MUTABLE downstream docs. ADR-007 is exempt because it is
    immutable; that boundary is the same one `_baseline_drift_targets` enforces.
    """
    doc_path = repo_root / doc_rel
    if not doc_path.is_file():
        return []  # missing-doc failure already raised by `_check_doc_drift`.
    text = doc_path.read_text(encoding="utf-8").lower()
    missing_slugs: list[str] = []
    for slug in sorted(required_artifacts):
        keywords = _ARTIFACT_DOC_KEYWORDS.get(slug)
        if not keywords:
            # Slug not in the keyword map yet — silently pass rather than
            # bake an implicit "every new artifact slug must update the
            # keyword map AND the doc". The keyword map is the
            # contributor-facing surface; new slugs should be added
            # alongside the YAML edit.
            continue
        # Case-insensitive match: docs may use "Invariants" or "invariant
        # list" or "INVARIANT LIST" -- the keyword "invariant" should match
        # all of them.
        if not any(keyword.lower() in text for keyword in keywords):
            missing_slugs.append(slug)
    if missing_slugs:
        return [
            _fail(
                drift_rule_id,
                f"{doc_rel} no longer mentions every required artifact; missing keywords for: {missing_slugs}",
                doc_rel,
            )
        ]
    return []


def _check_doc_drift(
    repo_root: Path,
    doc_rel: str,
    missing_rule_id: str,
    drift_rule_id: str,
    targets: list[tuple[str, str]],
) -> list[PolicyFailure]:
    doc_path = repo_root / doc_rel
    if not doc_path.is_file():
        return [_fail(missing_rule_id, f"{doc_rel} is missing — the policy references it", doc_rel)]
    text = doc_path.read_text(encoding="utf-8")
    normalized = " ".join(text.split())
    missing_ids: list[str] = []
    missing_names: list[str] = []
    unpaired: list[tuple[str, str]] = []
    for level_id, level_name in targets:
        if level_id not in text:
            missing_ids.append(level_id)
        canonical_name = " ".join(level_name.split()) if level_name else ""
        if canonical_name and canonical_name not in normalized:
            missing_names.append(level_name)
        # Pair check: the id and its canonical name must co-occur within a
        # narrow window somewhere in the doc, so it is not enough that the
        # doc mentions every id AND every name -- they must be bound
        # together. This catches the exact "FM2 | Dynamic Semantic Rules"
        # drift mode where the wrong name is paired with the right id.
        # Well-formed bindings sit within ~10 chars ("### FM2 Semantic
        # Graph / Constraint", "FM2 (Semantic Graph / Constraint)"); a
        # Markdown table that mis-pairs across adjacent rows leaves ~50+
        # chars between the id and the wrong-row name.
        if canonical_name and level_id in text and canonical_name in normalized:
            if not _id_name_paired(normalized, level_id, canonical_name):
                unpaired.append((level_id, level_name))
    failures: list[PolicyFailure] = []
    if missing_ids:
        failures.append(
            _fail(
                drift_rule_id,
                f"{doc_rel} no longer mentions every canonical level id; missing: {missing_ids}",
                doc_rel,
            )
        )
    if missing_names:
        failures.append(
            _fail(
                drift_rule_id,
                f"{doc_rel} no longer mentions every canonical level name; missing: {missing_names}",
                doc_rel,
            )
        )
    if unpaired:
        rendered = ", ".join(f"{lid}↔{name!r}" for lid, name in unpaired)
        failures.append(
            _fail(
                drift_rule_id,
                f"{doc_rel} mentions every canonical id and name, but at least one (id, name) pair is "
                f"not co-located within a 200-character window — likely id/name drift: {rendered}",
                doc_rel,
            )
        )
    return failures


def _id_name_paired(normalized_text: str, level_id: str, level_name: str, window: int = 40) -> bool:
    """Return True if `level_id` and `level_name` co-occur within `window` chars in `normalized_text`."""
    start = 0
    while True:
        idx = normalized_text.find(level_id, start)
        if idx == -1:
            return False
        window_start = max(0, idx - window)
        window_end = idx + len(level_id) + window
        if level_name in normalized_text[window_start:window_end]:
            return True
        start = idx + 1


def evaluate_assurance_policy(repo_root: Path) -> list[PolicyFailure]:
    """Return the list of structural failures for the ASR-505 assurance policy (empty = OK)."""
    policy_path = repo_root / ASSURANCE_POLICY_RELATIVE_PATH
    if not policy_path.is_file():
        return [
            _fail(
                "assurance-policy-missing",
                f"assurance policy not found: {ASSURANCE_POLICY_RELATIVE_PATH}",
                ASSURANCE_POLICY_RELATIVE_PATH,
            )
        ]

    try:
        raw = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [
            _fail(
                "assurance-policy-parse",
                f"failed to parse {ASSURANCE_POLICY_RELATIVE_PATH}: {exc}",
                ASSURANCE_POLICY_RELATIVE_PATH,
            )
        ]
    except YAML_CONTENT_FAILURES:
        return [
            _fail(
                "assurance-policy-parse",
                f"failed to parse {ASSURANCE_POLICY_RELATIVE_PATH}",
                ASSURANCE_POLICY_RELATIVE_PATH,
            )
        ]

    if not isinstance(raw, dict):
        return [
            _fail(
                "assurance-policy-shape",
                f"{ASSURANCE_POLICY_RELATIVE_PATH} must be a YAML mapping at the top level",
                ASSURANCE_POLICY_RELATIVE_PATH,
            )
        ]

    failures: list[PolicyFailure] = []
    failures.extend(_check_top_level_fields(raw, ASSURANCE_POLICY_RELATIVE_PATH))
    failures.extend(_check_refs(raw, ASSURANCE_POLICY_RELATIVE_PATH))

    raw_levels = raw.get("levels")
    levels: list[Any] = raw_levels if isinstance(raw_levels, list) else []
    # _check_levels runs even when levels is empty or missing, so the
    # missing-canonical-level failures fire instead of getting silently
    # skipped.
    failures.extend(_check_levels(levels, ASSURANCE_POLICY_RELATIVE_PATH))

    # ADR-007 is IMMUTABLE per the ADR README; it must mention the baseline
    # FM0..FM3 ladder it codifies, and nothing more. Future FM4+ levels flow
    # through to the mutable docs only.
    baseline_targets = _baseline_drift_targets(levels)
    extended_targets = _drift_targets(levels) if levels else baseline_targets
    if not extended_targets or not any(name for _id, name in extended_targets):
        extended_targets = baseline_targets

    failures.extend(
        _check_doc_drift(
            repo_root,
            ADR_POLICY_RELATIVE_PATH,
            "assurance-policy-adr-missing",
            "assurance-policy-adr-drift",
            baseline_targets,
        )
    )
    failures.extend(
        _check_doc_drift(
            repo_root,
            CODING_STANDARDS_RELATIVE_PATH,
            "assurance-policy-coding-standards-missing",
            "assurance-policy-coding-standards-drift",
            extended_targets,
        )
    )
    failures.extend(
        _check_doc_drift(
            repo_root,
            FORMAL_OVERVIEW_RELATIVE_PATH,
            "assurance-policy-formal-overview-missing",
            "assurance-policy-formal-overview-drift",
            extended_targets,
        )
    )

    # Artifact-keyword drift -- applies only to MUTABLE docs. A doc that drops
    # mention of an artifact category that the YAML still requires fails the
    # gate; readers cannot be told a stale story.
    required_artifacts = _required_artifact_union(levels)
    failures.extend(
        _check_artifact_keyword_drift(
            repo_root,
            CODING_STANDARDS_RELATIVE_PATH,
            "assurance-policy-coding-standards-drift",
            required_artifacts,
        )
    )
    failures.extend(
        _check_artifact_keyword_drift(
            repo_root,
            FORMAL_OVERVIEW_RELATIVE_PATH,
            "assurance-policy-formal-overview-drift",
            required_artifacts,
        )
    )

    failures.extend(_check_adr_template_classification(repo_root))
    failures.extend(_check_new_adr_classifications(repo_root, _level_ids(levels)))
    failures.extend(_check_fm_classification_ledger(repo_root, levels))
    failures.extend(_check_assurance_fulfillment(repo_root, levels))

    return failures


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the ASR-505 classification-based assurance policy (ADR-007 / ADR-018)."
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
    failures = evaluate_assurance_policy(args.repo_root)
    exceptions_file = args.repo_root / "tools" / "policy" / "exceptions.yaml"
    if exceptions_file.is_file():
        try:
            failures = apply_exceptions(failures, load_exceptions(args.repo_root))
        except InvalidInputError as exc:
            print(f"assurance-policy: {exc}", file=sys.stderr)
            return 1
    if failures:
        if args.json:
            print(failures_to_json(failures))
        else:
            for failure in failures:
                print(failure.render(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
