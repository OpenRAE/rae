#!/usr/bin/env python3
# ruff: noqa: E402
"""Validate behavioral-relation bindings and unstructured positive claims.

The gate is semantic rather than a keyword ban. Relation terminology is
allowed in definitions, explicit nonclaims, and revisioned claim bindings. A
positive claim must identify the governed relation and state its evidence
boundary; finite evidence therefore cannot silently become an equivalence,
simulation, refinement, or bisimulation claim.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from pydantic import ValidationError  # noqa: E402
from raes_contracts.behavioral_relations import (
    BehavioralRelationCatalogModel,
    validate_behavioral_claim_binding,
)  # noqa: E402
from raes_contracts.contracts import BehavioralClaimBindingModel  # noqa: E402
from raes_contracts.errors import InvalidInputError
from raes_contracts.operational_logging import run_application

from tools.policy.common import (
    PolicyFailure,
    apply_exceptions,
    failures_to_json,
    load_exceptions,
)  # noqa: E402

CATALOG_RELATIVE_PATH = "contracts/concept-authority/behavioral-relations-v1.json"
RULE_CATALOG_INVALID = "behavioral-relation-catalog-invalid"
RULE_BINDING_INVALID = "behavioral-relation-binding-invalid"
RULE_UNBOUND_CLAIM = "behavioral-relation-unbound-positive-claim"

_CLAIM_BINDING_KEYS = frozenset({"taxonomy_id", "taxonomy_revision", "relation_id"})
_CLAIM_CONTAINER_SCHEMA_VERSIONS = frozenset(
    {
        "behavioral-relation-profile/v1",
        "participant-opacity-analysis-evidence/v1",
        "participant-opacity-model-check-evidence/v1",
    }
)
_TEXT_SUFFIXES = frozenset({".json", ".md", ".py", ".toml", ".yaml", ".yml"})
_SCAN_ROOTS = (
    "docs",
    "specs",
    "examples",
    "contracts/profiles",
    "contracts/fixtures",
    "implementations/python/packages",
)
_EXCLUDED_PREFIXES = (
    "contracts/schemas/",
    "docs/_build/",
    "implementations/python/tests/",
)

_CLAIM_PATTERNS: tuple[tuple[re.Pattern[str], frozenset[str]], ...] = (
    (
        re.compile(
            r"\b(?:are|is|was|were|remain|remains|establish|establishes|prove|proves|"
            r"guarantee|guarantees|claim|claims|satisfy|satisfies)\b"
            r"(?:\s+[a-z-]+){0,5}\s+(?:universal\s+)?(?:policy[- ]?)?noninterference\b",
            re.IGNORECASE,
        ),
        frozenset({"policy-noninterference"}),
    ),
    (
        re.compile(r"\bbehavior(?:al(?:ly)?)?[- ]history[- ]equivalent\b", re.IGNORECASE),
        frozenset({"participant-projected-history-equivalence"}),
    ),
    (
        re.compile(
            r"\b(?:are|is|was|were|remain|remains|establish|establishes|prove|proves|"
            r"guarantee|guarantees|claim|claims)\b(?:\s+[a-z-]+){0,5}\s+"
            r"(?:behaviorally equivalent|behavioral equivalence)\b",
            re.IGNORECASE,
        ),
        frozenset(
            {
                "trace-equivalence",
                "strong-bisimulation",
                "weak-bisimulation",
                "divergence-preserving-branching-bisimulation",
                "participant-projected-history-equivalence",
                "probabilistic-bisimulation",
            }
        ),
    ),
    (
        re.compile(
            r"\b(?:are|is|was|were|establish|establishes|prove|proves|claim|claims)\b"
            r"(?:\s+[a-z-]+){0,5}\s+trace equivalen(?:ce|t)\b",
            re.IGNORECASE,
        ),
        frozenset({"trace-equivalence"}),
    ),
    (
        re.compile(
            r"\b(?:are|is|was|were|establish|establishes|prove|proves|claim|claims)\b"
            r"(?:\s+[a-z-]+){0,5}\s+strong (?:bisimulation|bisimilar)\b",
            re.IGNORECASE,
        ),
        frozenset({"strong-bisimulation"}),
    ),
    (
        re.compile(
            r"\b(?:are|is|was|were|establish|establishes|prove|proves|claim|claims)\b"
            r"(?:\s+[a-z-]+){0,5}\s+weak (?:bisimulation|bisimilar)\b",
            re.IGNORECASE,
        ),
        frozenset({"weak-bisimulation"}),
    ),
    (
        re.compile(
            r"\b(?:are|is|was|were|establish|establishes|prove|proves|claim|claims)\b"
            r"(?:\s+[a-z-]+){0,5}\s+probabilistic (?:bisimulation|bisimilar)\b",
            re.IGNORECASE,
        ),
        frozenset({"probabilistic-bisimulation"}),
    ),
    (
        re.compile(
            r"\b(?:are|is|was|were|establish|establishes|prove|proves|claim|claims)\b"
            r"(?:\s+[a-z-]+){0,5}\s+(?:bisimulation|bisimilar(?:ity)?)\b",
            re.IGNORECASE,
        ),
        frozenset(
            {
                "strong-bisimulation",
                "weak-bisimulation",
                "divergence-preserving-branching-bisimulation",
                "probabilistic-bisimulation",
            }
        ),
    ),
    (
        re.compile(
            r"\b(?:are|is|was|were|establish|establishes|prove|proves|claim|claims)\b"
            r"(?:\s+[a-z-]+){0,5}\s+strategic(?:ally)? equivalen(?:ce|t)\b",
            re.IGNORECASE,
        ),
        frozenset({"alternating-strategic-equivalence"}),
    ),
    (
        re.compile(
            r"\b(?:are|is|was|were|establish|establishes|prove|proves|claim|claims)\b"
            r"(?:\s+[a-z-]+){0,5}\s+epistemic(?:ally)? indistinguish(?:ability|able)\b",
            re.IGNORECASE,
        ),
        frozenset({"epistemic-indistinguishability"}),
    ),
    (
        re.compile(
            r"\b(?:are|is|was|were|establish|establishes|prove|proves|claim|claims)\b"
            r"(?:\s+[a-z-]+){0,5}\s+statistical(?:ly)? equivalen(?:ce|t)\b",
            re.IGNORECASE,
        ),
        frozenset({"statistical-equivalence"}),
    ),
    (
        re.compile(
            r"\bimplementation refines? (?:this|the) (?:design|model|specification)\b",
            re.IGNORECASE,
        ),
        frozenset(
            {
                "trace-inclusion",
                "forward-simulation",
                "backward-simulation",
                "data-refinement",
            }
        ),
    ),
)

_NONCLAIM_RE = re.compile(
    r"\b(?:does not|do not|is not|are not|was not|were not|neither|cannot|can not|must not|"
    r"not evidence|not establish|not imply|"
    r"not\s+(?:a|an)\s+[^.]{0,80}claim|no [^.]{0,80}claim|deliberately unproved|"
    r"remains? unproved|future work)\b",
    re.IGNORECASE,
)
_BOUNDARY_RE = re.compile(
    r"\b(?:evidence boundary|bounded by|bounded to|only (?:the|these|named|under)|"
    r"finite (?:case|probe|trace|observation)|quantifier.scope|evidence.scope|"
    r"observation projection|projection revision|proof obligation)\b",
    re.IGNORECASE,
)


def _iter_objects(value: Any) -> Iterator[dict[str, Any]]:
    """Yield every object in document order (depth first, parents first).

    The walk keeps its own stack, so a document that the JSON decoder accepts
    cannot exceed the interpreter recursion limit here.
    """

    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            yield current
            pending.extend(reversed(list(current.values())))
        elif isinstance(current, list):
            pending.extend(reversed(current))


def _validate_structured_bindings(
    payload: Any,
    catalog: BehavioralRelationCatalogModel,
    path: str,
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for candidate in _iter_objects(payload):
        if not _CLAIM_BINDING_KEYS.issubset(candidate):
            continue
        if candidate.get("schema_version") in _CLAIM_CONTAINER_SCHEMA_VERSIONS:
            continue
        try:
            binding = BehavioralClaimBindingModel.model_validate(candidate)
            validate_behavioral_claim_binding(binding)
        except (ValidationError, ValueError) as exc:
            failures.append(
                PolicyFailure(
                    RULE_BINDING_INVALID,
                    f"behavioral claim binding is invalid: {exc}",
                    path,
                )
            )
    return failures


def _should_validate_structured_bindings(path: str) -> bool:
    """Invalid contract fixtures are negative validator inputs, not claims."""

    return not (path.startswith("contracts/fixtures/") and "/invalid/" in path)


def _sentence_around(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n\n", 0, start), start - 500)
    right_candidates = [position for position in (text.find(".", end), text.find("\n\n", end)) if position >= 0]
    right = min(right_candidates) + 1 if right_candidates else min(len(text), end + 500)
    return text[left + 1 : right]


def _window_around(text: str, start: int, end: int) -> str:
    return text[max(0, start - 700) : min(len(text), end + 700)]


def _relation_id_present(window: str, relation_ids: frozenset[str]) -> bool:
    return any(
        re.search(
            rf"(?<![a-z0-9-]){re.escape(relation_id)}(?![a-z0-9-])",
            window,
            re.IGNORECASE,
        )
        for relation_id in relation_ids
    )


def _validate_claim_text(text: str, path: str) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    seen: set[tuple[int, str]] = set()
    for pattern, expected_relation_ids in _CLAIM_PATTERNS:
        for match in pattern.finditer(text):
            key = (match.start(), match.group(0).lower())
            if key in seen:
                continue
            seen.add(key)
            sentence = _sentence_around(text, match.start(), match.end())
            if _NONCLAIM_RE.search(sentence):
                continue
            window = _window_around(text, match.start(), match.end())
            if _relation_id_present(window, expected_relation_ids) and _BOUNDARY_RE.search(window):
                continue
            expected = ", ".join(sorted(expected_relation_ids))
            failures.append(
                PolicyFailure(
                    RULE_UNBOUND_CLAIM,
                    f"positive phrase {match.group(0)!r} must bind relation identity ({expected}) and an "
                    "evidence boundary, or be stated as an explicit weaker nonclaim",
                    path,
                )
            )
    return failures


def _iter_scan_paths(repo_root: Path) -> Iterator[Path]:
    root_readme = repo_root / "README.md"
    if root_readme.is_file():
        yield root_readme
    for relative_root in _SCAN_ROOTS:
        scan_root = repo_root / relative_root
        if not scan_root.is_dir():
            continue
        for path in sorted(scan_root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
                continue
            relative = path.relative_to(repo_root).as_posix()
            is_preflight_record = relative.startswith("docs/decisions/issue-") and relative.endswith("-preflight.md")
            if (
                relative == CATALOG_RELATIVE_PATH
                or is_preflight_record
                or any(relative.startswith(prefix) for prefix in _EXCLUDED_PREFIXES)
            ):
                continue
            yield path


def evaluate(repo_root: Path) -> list[PolicyFailure]:
    catalog_path = repo_root / CATALOG_RELATIVE_PATH
    try:
        catalog = BehavioralRelationCatalogModel.model_validate_json(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        return [
            PolicyFailure(
                RULE_CATALOG_INVALID,
                f"cannot load governed catalog: {exc}",
                CATALOG_RELATIVE_PATH,
            )
        ]

    failures: list[PolicyFailure] = []
    for path in _iter_scan_paths(repo_root):
        relative = path.relative_to(repo_root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            failures.append(PolicyFailure(RULE_UNBOUND_CLAIM, f"cannot inspect claim surface: {exc}", relative))
            continue
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(text)
            # json.loads reports invalid syntax and an integer beyond the interpreter digit limit with
            # ValueError, and nesting beyond the decoder with RecursionError; all three are not JSON here.
            except ValueError, RecursionError:
                payload = None
            if payload is not None and _should_validate_structured_bindings(relative):
                failures.extend(_validate_structured_bindings(payload, catalog, relative))
        failures.extend(_validate_claim_text(text, relative))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit failures as JSON.")
    args = parser.parse_args()

    try:
        failures = apply_exceptions(evaluate(REPO_ROOT), load_exceptions(REPO_ROOT))
    except InvalidInputError as exc:
        print(f"behavioral-relation-claims: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(failures_to_json(failures))
    else:
        for failure in failures:
            print(failure.render())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
