#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Validate and replay the issue-168 semantic-validation evidence bundle.

The closed key sets, shape primitives, replay engine, and per-surface
validators live in the ``tools/formal_semantic_validation`` support package;
this entry point evaluates every indexed release and keeps the import surface
the test suite and nox lanes rely on.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_PACKAGES = REPO_ROOT / "implementations" / "python" / "packages"
for import_root in (REPO_ROOT, PYTHON_PACKAGES):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from tools.evidence_bundle_index import revision_key
from tools.policy.common import PolicyFailure, load_bounded_json_object
from tools.formal_semantic_validation._bundle import validate_bundle
from tools.formal_semantic_validation._claims import recompute_claim_results
from tools.formal_semantic_validation._loading import load_release_bundles, load_retest_bundle
from tools.formal_semantic_validation._releases import validate_release_bundle, validate_retest_bundle
from tools.formal_semantic_validation._replay import (
    _participant_test_refs,
    _replay_participant_tests,
    replay_case,
)
from tools.formal_semantic_validation._satisfiability import validate_satisfiability_analysis
from tools.formal_semantic_validation._supplement_loading import (
    load_bundle,
    load_satisfiability_analysis,
)
from tools.formal_semantic_validation._shape import _failure
from tools.formal_semantic_validation._types import (
    EVIDENCE_STATUSES,
    MANIFEST_PATH,
    REQUIRED_CLAIM_CLASS_IDS,
    REQUIRED_PARTICIPANT_OBLIGATION_IDS,
    EvidenceRelease,
    ParticipantTestRunner,
)

__all__ = [
    "EVIDENCE_STATUSES",
    "EvidenceRelease",
    "MANIFEST_PATH",
    "ParticipantTestRunner",
    "REQUIRED_CLAIM_CLASS_IDS",
    "REQUIRED_PARTICIPANT_OBLIGATION_IDS",
    "evaluate",
    "load_bounded_json_object",
    "load_bundle",
    "load_release_bundles",
    "load_retest_bundle",
    "load_satisfiability_analysis",
    "main",
    "recompute_claim_results",
    "replay_case",
    "validate_bundle",
    "validate_release_bundle",
    "validate_retest_bundle",
    "validate_satisfiability_analysis",
]


def _participant_replay_failures(
    repo_root: Path,
    releases: list[EvidenceRelease],
    participant_test_runner: ParticipantTestRunner,
) -> list[PolicyFailure]:
    latest = max(releases, key=lambda item: revision_key(item.manifest.get("revision")))
    test_refs = _participant_test_refs(latest.protocol)
    replayed, detail = participant_test_runner(repo_root, test_refs)
    if replayed:
        return []
    return [
        _failure(
            "formal-validation-participant-replay",
            detail,
            str(latest.manifest.get("snapshot_path")),
        )
    ]


def evaluate(
    repo_root: Path = REPO_ROOT,
    *,
    participant_test_runner: ParticipantTestRunner = _replay_participant_tests,
) -> list[PolicyFailure]:
    try:
        releases = load_release_bundles(repo_root)
        load_retest_bundle(repo_root)
    except (OSError, ValueError) as exc:
        return [_failure("formal-validation-bundle-load", str(exc), MANIFEST_PATH)]
    failures: list[PolicyFailure] = []
    for release in releases:
        failures.extend(validate_release_bundle(repo_root, release))
    if not failures:
        failures = _participant_replay_failures(repo_root, releases, participant_test_runner)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    failures = evaluate(args.repo_root.resolve())
    if failures:
        for failure in failures:
            print(failure.render(), file=sys.stderr)
        return 1
    print("Formal semantic-validation evidence bundle passed integrity and replay checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
