#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Structural gate: every published contract traces to a live governing requirement.

``ADR-009`` §7 makes ``contracts/schemas/`` the normative contract authority, and
``check_schema_publication.py`` and ``check_schema_coverage.py`` prove that each
published schema is inventoried and exercised. Neither asks which requirement
governs it, so a schema could be published, and stay published, with no
requirement owning it (issue #712). This gate asks that question over the whole
published inventory on every run, not over the changed-file set.

A published contract is **traced** when at least one requirement record under
``docs/requirements/<UID>/requirement.md`` whose status is ACTIVE or DRAFT
carries an ``IMPLEMENTS → SPEC`` link to the contract's exact schema path.

- ``CODE_FILE`` links never count. A module such as
  ``raes_contracts/contracts/bundle.py`` generates every contract, so a module
  link cannot say which contract a requirement governs.
- Other link types never count. ``CONSTRAINS``, ``DOCUMENTS``, ``TESTS``, and
  ``VERIFIES`` record a relation other than ownership, and an ``IMPLEMENTS``
  link typed as anything but ``SPEC`` is a classification error to correct.
- DRAFT owners qualify and DEPRECATED or ARCHIVED owners never do. That is the
  status rule ``requirement_governance.py`` applies to implementation work.

The inventory is every ``contracts/schemas/**/*.json`` file. The contracts lane
already fails when that tree disagrees with ``schema_bundle()``
(``check_generated_schemas.py``) or with the publication manifest
(``check_schema_publication.py``), so this gate reads the tree and does not
regenerate the bundle. Requirement records are read offline through
``RepositoryRequirementClient``, the authority ``requirement_order.yaml``
selects. An unreadable record fails closed rather than counting as untraced.

``--report`` prints the owners of each published contract and never gates.
Failures use ``tools.policy.common.PolicyFailure``. The CLI honours ``--json``
and the shared ``tools/policy/exceptions.yaml`` waiver mechanism, like the other
``policy`` nox-stage entry points.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.policy.common import PolicyFailure, apply_exceptions, failures_to_json, load_exceptions
from tools.policy.repository_requirements import RepositoryRequirementClient, RepositoryRequirementError

__all__ = [
    "GOVERNING_LINK",
    "MISSING_RULE_ID",
    "RETIRED_STATUSES",
    "UNREADABLE_RULE_ID",
    "build_tracing_report",
    "evaluate_contract_tracing",
    "governing_owners",
    "main",
    "published_schema_paths",
]

SCHEMAS_ROOT = "contracts/schemas"
REQUIREMENTS_ROOT = "docs/requirements"
GOVERNING_LINK = ("IMPLEMENTS", "SPEC")
RETIRED_STATUSES = frozenset({"ARCHIVED", "DEPRECATED"})
MISSING_RULE_ID = "contract-requirement-trace-missing"
UNREADABLE_RULE_ID = "contract-requirement-record-unreadable"


def published_schema_paths(repo_root: Path = REPO_ROOT) -> list[str]:
    """Return every published schema as a sorted repository-relative path."""

    schemas_root = repo_root / SCHEMAS_ROOT
    return sorted(path.relative_to(repo_root).as_posix() for path in schemas_root.rglob("*.json"))


def _requirement_uids(repo_root: Path) -> list[str]:
    requirements_root = repo_root / REQUIREMENTS_ROOT
    if not requirements_root.is_dir():
        return []
    return sorted(path.name for path in requirements_root.iterdir() if path.is_dir())


def _governing_identifiers(client: RepositoryRequirementClient, uid: str) -> list[str]:
    """Return the ``IMPLEMENTS → SPEC`` identifiers one requirement can own."""

    if client.get_requirement("", uid)["status"] in RETIRED_STATUSES:
        return []
    return [
        link["artifact_identifier"]
        for link in client.get_traceability(uid)
        if (link["link_type"], link["artifact_type"]) == GOVERNING_LINK
    ]


def governing_owners(repo_root: Path = REPO_ROOT) -> tuple[dict[str, set[str]], list[PolicyFailure]]:
    """Map each governed artifact to its live owners, failing closed on unreadable records."""

    client = RepositoryRequirementClient(repo_root)
    owners: dict[str, set[str]] = defaultdict(set)
    failures: list[PolicyFailure] = []
    for uid in _requirement_uids(repo_root):
        try:
            identifiers = _governing_identifiers(client, uid)
        except RepositoryRequirementError as exc:
            failures.append(PolicyFailure(UNREADABLE_RULE_ID, str(exc), f"{REQUIREMENTS_ROOT}/{uid}/requirement.md"))
            continue
        for identifier in identifiers:
            owners[identifier].add(uid)
    return dict(owners), failures


def evaluate_contract_tracing(repo_root: Path = REPO_ROOT) -> list[PolicyFailure]:
    """Return every published contract with no live ``IMPLEMENTS → SPEC`` owner."""

    owners, failures = governing_owners(repo_root)
    failures.extend(
        PolicyFailure(
            MISSING_RULE_ID,
            f"published contract {Path(schema_path).stem} has no IMPLEMENTS → SPEC link "
            "from an ACTIVE or DRAFT requirement",
            schema_path,
        )
        for schema_path in published_schema_paths(repo_root)
        if schema_path not in owners
    )
    return failures


def build_tracing_report(repo_root: Path = REPO_ROOT) -> str:
    """Render the owners of every published contract. Never gates."""

    owners, failures = governing_owners(repo_root)
    lines = ["Published-contract requirement tracing report (issue #712)", ""]
    for schema_path in published_schema_paths(repo_root):
        lines.append(f"  - {schema_path}: {', '.join(sorted(owners.get(schema_path, ()))) or 'UNTRACED'}")
    lines.extend(f"  - {failure.render()}" for failure in failures)
    return "\n".join(lines) + "\n"


def _active_waivers(repo_root: Path) -> list[dict[str, object]]:
    exceptions_file = repo_root / "tools" / "policy" / "exceptions.yaml"
    return load_exceptions(repo_root) if exceptions_file.is_file() else []


def _print_failures(failures: list[PolicyFailure], *, as_json: bool) -> None:
    if as_json:
        print(failures_to_json(failures))
        return
    for failure in failures:
        print(failure.render(), file=sys.stderr)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Require every published contract to trace to a live governing requirement (issue #712)."
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root to check.")
    parser.add_argument("--json", action="store_true", help="Emit failures as JSON on stdout.")
    parser.add_argument("--report", action="store_true", help="Print each contract's owners and exit 0.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.report:
        print(build_tracing_report(args.repo_root), end="")
        return 0
    failures = apply_exceptions(evaluate_contract_tracing(args.repo_root), _active_waivers(args.repo_root))
    if failures:
        _print_failures(failures, as_json=args.json)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
