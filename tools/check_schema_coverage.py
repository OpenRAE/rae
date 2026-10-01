#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Structural gate: every published schema carries concrete coverage evidence.

A contract can be published, hashed, ledgered and metaschema-valid while nothing
in the repository ever exercises it. ``check_schema_publication.py`` proves the
inventory, hashes, stability and evolution of the published set; it does not ask
whether anything supports a contract's claims. This gate asks exactly that, by
schema path, over the whole published inventory.

A published schema is **covered** when at least one of these holds:

1. **Corpus coverage.** At least one checked-in artifact that the canonical
   corpus router (``check_json_artifacts.covered_schema_paths``) routes to that
   exact schema path. The set is non-empty by construction, so an empty
   ``valid/`` directory, an ``invalid/``-only family and a bare directory are
   not coverage. Alternate routes are inherited from the router, never copied.
2. **Formal coverage.** The schema path is a ``delivered_artifacts`` entry of a
   classified subsystem in ``specs/formal/assurance-fulfillment.yaml``. A
   ``waived_artifacts`` entry never counts: a dated, tracked waiver is an
   unresolved obligation, not delivered evidence.
3. **Declared alternate coverage.** The contract's publication record carries a
   validated ``coverage`` association naming the concrete evidence that
   exercises it where neither canonical route reaches.

**A formal model is never required.** Leg 2 is one alternative among three. This
gate never reads an FM level, never infers FM applicability, and never turns a
missing formal association into "not applicable" — FM applicability belongs to
``assurance-policy.yaml`` / ``assurance-fulfillment.yaml`` under
``check_assurance_policy.py``. A structural contract passes on leg 1 alone.

Every accepted leg is computed, never trusted: a declared source is resolved and
run through the published schema on each invocation, so evidence the gate cannot
falsify is not accepted at all. The closed key sets, evidence checks, and
declaration validator live in ``tools/schema_coverage``; this entry point wires
them together and owns the CLI.

``--report`` prints a read-only inventory naming the covering leg per schema and
never gates. Failures use ``tools.policy.common.PolicyFailure`` and the CLI
honours ``--json`` and the shared ``tools/policy/exceptions.yaml`` waiver
mechanism, like the other ``policy`` nox-stage entry points.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.policy.common import PolicyFailure, apply_exceptions, failures_to_json, load_exceptions
from tools.schema_coverage._classify import classify
from tools.schema_coverage._keys import (
    CATALOG_RULE_ID,
    CORPUS,
    COVERAGE_KEY,
    DECLARATION_RULE_ID,
    DECLARED,
    FORMAL,
    MAX_SOURCES,
    MISSING_RULE_ID,
    UNCOVERED,
)

__all__ = [
    "CATALOG_RULE_ID",
    "COVERAGE_KEY",
    "DECLARATION_RULE_ID",
    "MAX_SOURCES",
    "MISSING_RULE_ID",
    "build_coverage_report",
    "evaluate_schema_coverage",
    "main",
]

_REPORT_LEGS = (CORPUS, FORMAL, DECLARED, UNCOVERED)


def evaluate_schema_coverage(repo_root: Path = REPO_ROOT) -> list[PolicyFailure]:
    """Return every published schema that carries no concrete coverage evidence."""

    rows, failures = classify(repo_root)
    failures.extend(
        PolicyFailure(
            MISSING_RULE_ID,
            f"published schema {contract_id} has no fixture, formal, or declared coverage evidence",
            schema_path,
        )
        for contract_id, schema_path, leg in rows
        if leg == UNCOVERED
    )
    return sorted(failures, key=lambda item: (item.path or "", item.rule_id, item.message))


def build_coverage_report(repo_root: Path = REPO_ROOT) -> str:
    """Render a read-only inventory naming the covering leg per schema. Never gates."""

    rows, failures = classify(repo_root)
    lines = ["Published-schema coverage report (ASR-501)", ""]
    for leg in _REPORT_LEGS:
        group = [row for row in rows if row[2] == leg]
        lines.append(f"## {leg} ({len(group)})")
        lines.extend(f"  - {contract_id}: {schema_path}" for contract_id, schema_path, _ in group)
        lines.append("")
    if failures:
        lines.append(f"## malformed associations ({len(failures)})")
        lines.extend(f"  - {failure.render()}" for failure in failures)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _waivers(repo_root: Path) -> list[dict[str, object]]:
    if not (repo_root / "tools" / "policy" / "exceptions.yaml").is_file():
        return []
    return load_exceptions(repo_root)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate published-schema coverage evidence (ASR-501).")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (defaults to the repo containing this file).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON failures.")
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print a read-only coverage inventory (covering leg per schema) and exit 0.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.report:
        print(build_coverage_report(args.repo_root))
        return 0
    failures = apply_exceptions(evaluate_schema_coverage(args.repo_root), _waivers(args.repo_root))
    if not failures:
        return 0
    if args.json:
        print(failures_to_json(failures))
    else:
        for failure in failures:
            print(failure.render(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
