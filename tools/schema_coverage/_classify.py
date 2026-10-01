"""Join the published inventory to its coverage evidence, one row per contract."""

from __future__ import annotations

from pathlib import Path

from tools.check_json_artifacts import covered_schema_paths
from tools.check_schema_publication import load_schema_publication_catalog
from tools.policy.common import PolicyFailure
from tools.schema_coverage._declaration import evaluate_declaration
from tools.schema_coverage._evidence import formal_artifact_paths
from tools.schema_coverage._keys import (
    CATALOG_RULE_ID,
    CORPUS,
    COVERAGE_KEY,
    DECLARED,
    FORMAL,
    MANIFEST_RELATIVE_PATH,
    UNCOVERED,
)

__all__ = ["CoverageRow", "classify"]

#: ``(contract_id, schema_path, covering leg)``.
CoverageRow = tuple[str, str, str]


def _catalog_entries(repo_root: Path) -> tuple[list[dict[str, object]], list[PolicyFailure]]:
    """Read the published inventory, failing closed rather than covering nothing."""

    try:
        catalog = load_schema_publication_catalog(repo_root)
    except (OSError, ValueError):
        message = "schema publication catalog could not be read; check_schema_publication.py owns the detail"
        return [], [PolicyFailure(CATALOG_RULE_ID, message, MANIFEST_RELATIVE_PATH)]
    entries = catalog.get("schemas")
    if not isinstance(entries, list):
        message = "schema publication catalog defines no schemas array"
        return [], [PolicyFailure(CATALOG_RULE_ID, message, MANIFEST_RELATIVE_PATH)]
    return [entry for entry in entries if isinstance(entry, dict)], []


def _derived_leg(schema_path: str, corpus: frozenset[str] | set[str], formal: frozenset[str]) -> str:
    if schema_path in corpus:
        return CORPUS
    if schema_path in formal:
        return FORMAL
    return UNCOVERED


def classify(repo_root: Path) -> tuple[list[CoverageRow], list[PolicyFailure]]:
    """Return one row per published contract plus every malformed-association failure."""

    entries, failures = _catalog_entries(repo_root)
    if failures:
        return [], failures
    corpus = covered_schema_paths(repo_root)
    formal, formal_failures = formal_artifact_paths(repo_root)
    failures.extend(formal_failures)

    rows: list[CoverageRow] = []
    for entry in entries:
        contract_id = entry.get("contract_id")
        schema_path = entry.get("schema_path")
        if not isinstance(contract_id, str) or not isinstance(schema_path, str):
            # Malformed records are check_schema_publication.py's failure to report.
            continue
        leg = _derived_leg(schema_path, corpus, formal)
        if COVERAGE_KEY in entry:
            qualified, declaration_failures = evaluate_declaration(
                repo_root, entry[COVERAGE_KEY], contract_id, schema_path
            )
            failures.extend(declaration_failures)
            if leg == UNCOVERED and qualified:
                leg = DECLARED
        rows.append((contract_id, schema_path, leg))
    return sorted(rows), failures
