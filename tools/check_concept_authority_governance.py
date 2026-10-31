#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Structural gate for concept-authority catalog governance (ADR-062).

ADR-012 ("Shared Concept Authority and RAES Extension Discipline") §3 demands
that RAES-native concept families be explicit, disciplined extensions over the
shared concept authority. The JSON Schema for ``concept-families-v1.json``
validates field *presence* (a native family must declare ``extension_scope``,
``relation_rules``, and ``non_ambiguity_constraints``), but nothing structural
prevents a family being added to the catalog with no governing ADR, or a
relation rule that names a family or vocabulary that does not exist. The
discipline is otherwise process-gated, not enforced.

This gate (ADR-062, operationalising GOV-918 / GOV-919) closes that gap with
filesystem-only, deterministic checks around the existing catalog — it does
not introduce a new concept schema, registry, runtime validator, or vocabulary:

* **ADR linkage.** Every family id in
  ``contracts/concept-authority/concept-families-v1.json`` must be matched as a
  whole token in at least one ADR under ``docs/decisions/adrs/``. ADR linkage
  is governance proof; specs, explanatory docs, the preflight note, and tests
  do not satisfy it. The word-boundary match mirrors
  ``check_authority_boundary.py`` so ``prosecution`` cannot satisfy ``prose``.
* **Reference resolution.** Cross-references from a family's ``relation_rules``
  to another concept family or to a controlled vocabulary use an explicit
  inline-code (Markdown backtick) token convention; the gate validates only
  those explicit tokens — never bare prose words — and each must resolve to a
  known concept family (``concept-families-v1.json``) or controlled vocabulary
  (``controlled-vocabularies-v1.json``). A backtick token shaped like an id but
  resolving to neither is a dangling reference.

Family and vocabulary identity derive from the authoritative catalogs and their
existing Pydantic models (``ConceptFamilyCatalogModel`` /
``ControlledVocabularyCatalogModel``); the gate hard-codes no family or
vocabulary id list. Failures use ``tools.policy.common.PolicyFailure`` and the
CLI honours ``--json`` and the shared ``tools/policy/exceptions.yaml`` waiver
mechanism, matching the other ``policy`` nox-stage gates.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from pydantic import ValidationError

from raes_contracts.contracts import (
    ConceptFamilyCatalogModel,
    ControlledVocabularyCatalogModel,
)
from raes_contracts.errors import InvalidInputError
from raes_contracts.operational_logging import run_application

from tools.policy.common import PolicyFailure, apply_exceptions, failures_to_json, load_exceptions

# --------------------------------------------------------------------------- #
# Canonical paths and references. Test code imports these directly so a rename #
# surfaces in the test suite rather than silently in production.              #
# --------------------------------------------------------------------------- #

CONCEPT_FAMILIES_RELATIVE_PATH = "contracts/concept-authority/concept-families-v1.json"
CONTROLLED_VOCABULARIES_RELATIVE_PATH = "contracts/concept-authority/controlled-vocabularies-v1.json"
ADR_DIR_RELATIVE_PATH = "docs/decisions/adrs"

# ADR-012 establishes the extension discipline this gate enforces; ADR-062 is
# the decision record that governs THIS file and enumerates the governed set.
EXTENSION_DISCIPLINE_ADR_REF = "ADR-012"
GOVERNANCE_ADR_REF = "ADR-062"
# The requirements this gate operationalises (cross-artifact concept binding and
# extension discipline). Pinned for the module-invariant tests.
REQUIREMENT_REFS: tuple[str, ...] = ("GOV-918", "GOV-919")

# The shared concept-family / controlled-vocabulary identifier grammar — the
# same pattern as raes_contracts.vocabulary.ConceptFamilyId and the keys of
# controlled-vocabularies-v1.json. Only inline-code spans whose full content
# matches this grammar are treated as catalog references.
_ID_TOKEN_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
# A Markdown inline-code span with no embedded backtick or newline. This is the
# explicit reference-token convention: a family/vocabulary cross-reference in
# free-text prose is written as `the-id`, never inferred from bare words.
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")

RULE_FAMILIES_MISSING = "concept-authority-families-catalog-missing"
RULE_FAMILIES_INVALID = "concept-authority-families-catalog-invalid"
RULE_VOCAB_MISSING = "concept-authority-vocabularies-catalog-missing"
RULE_VOCAB_INVALID = "concept-authority-vocabularies-catalog-invalid"
RULE_ADR_DIR_MISSING = "concept-authority-adr-dir-missing"
RULE_FAMILY_ADR_MISSING = "concept-authority-family-adr-missing"
RULE_DANGLING_REFERENCE = "concept-authority-dangling-reference"
# Besides the JSONDecodeError handled first, read_text() and json.loads() raise these for a catalog
# that is not UTF-8, has an integer beyond the interpreter digit limit or nests beyond the decoder.
_JSON_CONTENT_FAILURES = (ValueError, RecursionError)
_UNREADABLE_JSON = "catalog is not UTF-8 JSON within the decoder limits"


def _fail(rule_id: str, message: str, path: str | None = None) -> PolicyFailure:
    return PolicyFailure(rule_id, message, path)


def _read_text_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return None


# --------------------------------------------------------------------------- #
# Catalog loading. The authoritative catalogs are read from disk and validated #
# through the existing Pydantic models; a malformed catalog is surfaced as a   #
# clean failure rather than coerced to an empty structure.                     #
# --------------------------------------------------------------------------- #


def _load_families(repo_root: Path) -> tuple[ConceptFamilyCatalogModel | None, list[PolicyFailure]]:
    path = repo_root / CONCEPT_FAMILIES_RELATIVE_PATH
    if not path.is_file():
        return None, [
            _fail(
                RULE_FAMILIES_MISSING,
                f"concept-family catalog not found: {CONCEPT_FAMILIES_RELATIVE_PATH}",
                CONCEPT_FAMILIES_RELATIVE_PATH,
            )
        ]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [
            _fail(
                RULE_FAMILIES_INVALID,
                f"{CONCEPT_FAMILIES_RELATIVE_PATH} is not valid JSON: {exc}",
                CONCEPT_FAMILIES_RELATIVE_PATH,
            )
        ]
    except _JSON_CONTENT_FAILURES:
        return None, [_fail(RULE_FAMILIES_INVALID, _UNREADABLE_JSON, CONCEPT_FAMILIES_RELATIVE_PATH)]
    try:
        catalog = ConceptFamilyCatalogModel.model_validate(payload)
    except ValidationError as exc:
        return None, [
            _fail(
                RULE_FAMILIES_INVALID,
                f"{CONCEPT_FAMILIES_RELATIVE_PATH} failed concept-family catalog validation "
                f"({exc.error_count()} error(s))",
                CONCEPT_FAMILIES_RELATIVE_PATH,
            )
        ]
    return catalog, []


def _load_vocabularies(repo_root: Path) -> tuple[ControlledVocabularyCatalogModel | None, list[PolicyFailure]]:
    path = repo_root / CONTROLLED_VOCABULARIES_RELATIVE_PATH
    if not path.is_file():
        return None, [
            _fail(
                RULE_VOCAB_MISSING,
                f"controlled-vocabulary catalog not found: {CONTROLLED_VOCABULARIES_RELATIVE_PATH}",
                CONTROLLED_VOCABULARIES_RELATIVE_PATH,
            )
        ]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [
            _fail(
                RULE_VOCAB_INVALID,
                f"{CONTROLLED_VOCABULARIES_RELATIVE_PATH} is not valid JSON: {exc}",
                CONTROLLED_VOCABULARIES_RELATIVE_PATH,
            )
        ]
    except _JSON_CONTENT_FAILURES:
        return None, [_fail(RULE_VOCAB_INVALID, _UNREADABLE_JSON, CONTROLLED_VOCABULARIES_RELATIVE_PATH)]
    try:
        catalog = ControlledVocabularyCatalogModel.model_validate(payload)
    except ValidationError as exc:
        return None, [
            _fail(
                RULE_VOCAB_INVALID,
                f"{CONTROLLED_VOCABULARIES_RELATIVE_PATH} failed controlled-vocabulary catalog validation "
                f"({exc.error_count()} error(s))",
                CONTROLLED_VOCABULARIES_RELATIVE_PATH,
            )
        ]
    return catalog, []


# --------------------------------------------------------------------------- #
# Check 1: every family id is ADR-linked.                                     #
# --------------------------------------------------------------------------- #


def _check_family_adr_linkage(repo_root: Path, family_ids: Iterable[str]) -> list[PolicyFailure]:
    adr_dir = repo_root / ADR_DIR_RELATIVE_PATH
    if not adr_dir.is_dir():
        return [
            _fail(
                RULE_ADR_DIR_MISSING,
                f"ADR directory not found: {ADR_DIR_RELATIVE_PATH}",
                ADR_DIR_RELATIVE_PATH,
            )
        ]

    # The README in the ADR directory is not an ADR; the `adr-*.md` glob already
    # excludes it. Treat each ADR's bytes as inert text — no Markdown parsing.
    texts = [text for adr_file in sorted(adr_dir.glob("adr-*.md")) if (text := _read_text_or_none(adr_file))]
    union_text = "\n".join(texts)

    failures: list[PolicyFailure] = []
    for family_id in sorted(family_ids):
        # Whole-token match: a substring like `subepisodes` AND a hyphen-
        # delimited superset like `pre-episodes` / `actions-and-events-post`
        # must not satisfy the family id. Concept ids use `-` as an identifier
        # character (the `ConceptFamilyId` grammar), so the boundary excludes
        # word characters AND `-` on both sides — `check_authority_boundary`
        # excludes only `\w`, which suffices there but would let a hyphen-
        # extended superset satisfy a hyphenated concept-family id here.
        pattern = rf"(?<![\w-]){re.escape(family_id)}(?![\w-])"
        if not re.search(pattern, union_text):
            failures.append(
                _fail(
                    RULE_FAMILY_ADR_MISSING,
                    f"concept family '{family_id}' is not mentioned as a whole token in any ADR under "
                    f"{ADR_DIR_RELATIVE_PATH}; add ADR linkage (specs, docs, and tests do not satisfy it)",
                    CONCEPT_FAMILIES_RELATIVE_PATH,
                )
            )
    return failures


# --------------------------------------------------------------------------- #
# Check 2: relation-rule references resolve to a known family or vocabulary.  #
# --------------------------------------------------------------------------- #


def _inline_code_id_tokens(text: str) -> Iterator[str]:
    """Yield inline-code spans whose full content is a concept-id-shaped token.

    Backtick spans that are not id-shaped — a field name like ``concept_bindings``
    (underscore), a model like ``RuntimeConfiguration`` (caps), or an instance
    path like ``nodes.*.runtime`` (dots) — are not catalog references and are
    skipped, so the gate never flags them.
    """
    for match in _INLINE_CODE_RE.finditer(text):
        token = match.group(1)
        if _ID_TOKEN_RE.match(token):
            yield token


def _check_reference_resolution(
    catalog: ConceptFamilyCatalogModel,
    family_ids: frozenset[str],
    vocabulary_ids: frozenset[str],
) -> list[PolicyFailure]:
    known = family_ids | vocabulary_ids
    failures: list[PolicyFailure] = []
    for family_id, definition in sorted(catalog.families.items()):
        seen: set[str] = set()
        for rule in definition.relation_rules:
            for token in _inline_code_id_tokens(rule):
                if token in known or token in seen:
                    continue
                seen.add(token)
                failures.append(
                    _fail(
                        RULE_DANGLING_REFERENCE,
                        f"concept family '{family_id}' relation_rules reference '{token}', which is not a known "
                        "concept family or controlled vocabulary",
                        CONCEPT_FAMILIES_RELATIVE_PATH,
                    )
                )
    return failures


# --------------------------------------------------------------------------- #
# Top-level entry point.                                                      #
# --------------------------------------------------------------------------- #


def evaluate_concept_authority_governance(repo_root: Path) -> list[PolicyFailure]:
    """Return the list of concept-authority governance failures (empty = OK)."""
    failures: list[PolicyFailure] = []

    catalog, families_failures = _load_families(repo_root)
    failures.extend(families_failures)
    if catalog is None:
        return failures

    family_ids = frozenset(catalog.families)
    failures.extend(_check_family_adr_linkage(repo_root, family_ids))

    vocabulary_catalog, vocab_failures = _load_vocabularies(repo_root)
    failures.extend(vocab_failures)
    if vocabulary_catalog is not None:
        vocabulary_ids = frozenset(vocabulary_catalog.vocabularies)
        failures.extend(_check_reference_resolution(catalog, family_ids, vocabulary_ids))

    return failures


# --------------------------------------------------------------------------- #
# CLI.                                                                        #
# --------------------------------------------------------------------------- #


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate concept-authority catalog governance (ADR-012 extension discipline / ADR-062)."
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
    failures = evaluate_concept_authority_governance(args.repo_root)
    exceptions_file = args.repo_root / "tools" / "policy" / "exceptions.yaml"
    if exceptions_file.is_file():
        try:
            failures = apply_exceptions(failures, load_exceptions(args.repo_root))
        except InvalidInputError as exc:
            print(f"concept-authority-governance: {exc}", file=sys.stderr)
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
