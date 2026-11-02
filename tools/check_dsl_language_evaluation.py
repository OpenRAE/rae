#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Validate the preregistered RAES SDL language-evaluation evidence bundle.

The closed key sets, shape primitives, claim-scope machinery, measure
recomputation, and per-surface validators live in the
``tools/dsl_language_evaluation`` support package; this entry point loads the
revisioned claim bundles, wires the validators together, and keeps the import
surface the test suite and nox lanes rely on.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from raes_contracts.errors import InvalidInputError
from raes_contracts.operational_logging import run_application

from tools.policy.common import (
    PolicyFailure,
    load_bounded_json_object,
    safe_repo_path,
)
from tools.dsl_language_evaluation._analysis import _AnalysisContext, _validate_analysis
from tools.dsl_language_evaluation._claims import (
    _validate_claim_binding,
    _validate_claim_scope,
    resolve_claim_strata,
)
from tools.dsl_language_evaluation._keys import (
    _BUNDLE_ENTRY_KEYS,
    _MANIFEST_KEYS,
    _MAX_FILE_BYTES,
    MANIFEST_PATH,
    REQUIRED_DIMENSION_IDS,
    REQUIRED_PERSONA_IDS,
    REQUIRED_TASK_KINDS,
)
from tools.dsl_language_evaluation._measures import (
    recompute_dimension_results,
    recompute_measure_results,
    recompute_stratum_results,
)
from tools.dsl_language_evaluation._protocol import _validate_protocol
from tools.dsl_language_evaluation._shape import _failure, _valid_id
from tools.dsl_language_evaluation._snapshot import _validate_snapshot

__all__ = [
    "MANIFEST_PATH",
    "REQUIRED_DIMENSION_IDS",
    "REQUIRED_PERSONA_IDS",
    "REQUIRED_TASK_KINDS",
    "evaluate",
    "load_bundle",
    "load_bundles",
    "main",
    "recompute_dimension_results",
    "recompute_measure_results",
    "recompute_stratum_results",
    "resolve_claim_strata",
    "validate_bundle",
]


_ANALYSIS_ARTIFACT_PATH = "docs/research/dsl-language-evaluation/analysis-v1.json"


def _artifact_path(paths: Mapping[str, object], key: str, default: str) -> str:
    value = paths.get(key)
    return value if isinstance(value, str) else default


def _manifest_claim_binding(repo_root: Path, analysis: dict[str, object]) -> object:
    claim = analysis.get("claim")
    claim_id = claim.get("claim_id") if isinstance(claim, Mapping) else None
    try:
        return next(
            entry[0]["claim_binding"]
            for entry in load_bundles(repo_root)
            if isinstance(entry[0].get("claim_binding"), Mapping)
            and entry[0]["claim_binding"].get("claim_id") == claim_id
        )
    except OSError, InvalidInputError, StopIteration:
        return None


def validate_bundle(
    repo_root: Path,
    protocol: dict[str, object],
    snapshot: dict[str, object],
    analysis: dict[str, object],
    *,
    artifact_paths: Mapping[str, object] | None = None,
) -> list[PolicyFailure]:
    """Validate closed shapes, preregistration, joins, and evidence-status honesty."""

    failures: list[PolicyFailure] = []
    paths = artifact_paths or {}
    claim_binding = paths.get("claim_binding")
    if claim_binding is None:
        claim_binding = _manifest_claim_binding(repo_root, analysis)
    protocol_path = _artifact_path(paths, "protocol_path", "docs/research/dsl-language-evaluation/protocol-v1.json")
    snapshot_path = _artifact_path(
        paths, "snapshot_path", "docs/research/dsl-language-evaluation/execution-snapshot-v1.json"
    )
    analysis_path = _artifact_path(paths, "analysis_path", _ANALYSIS_ARTIFACT_PATH)
    catalogs = _validate_protocol(repo_root, protocol, failures, path=protocol_path)
    scope = _validate_claim_scope(protocol, analysis, catalogs, failures, path=analysis_path)
    strata = _validate_claim_binding(protocol, analysis, claim_binding, scope, failures, path=analysis_path)
    observation_ids = _validate_snapshot(repo_root, protocol, snapshot, catalogs, scope, failures, path=snapshot_path)
    _validate_analysis(
        _AnalysisContext(
            repo_root=repo_root,
            protocol=protocol,
            snapshot=snapshot,
            scope=scope,
            strata=strata,
            observation_ids=observation_ids,
        ),
        analysis,
        failures,
        path=analysis_path,
    )
    return failures


def load_bundle(
    repo_root: Path = REPO_ROOT,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    """Load the primary compatibility bundle selected by the manifest."""

    return load_bundles(repo_root)[0]


def _load_bundle_entry(
    repo_root: Path,
    entry: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    if set(entry) != _BUNDLE_ENTRY_KEYS:
        raise InvalidInputError(
            f"bundle entry fields must exactly match {sorted(_BUNDLE_ENTRY_KEYS)}; got {sorted(entry)}"
        )
    paths: list[str] = []
    for field in ("protocol_path", "snapshot_path", "analysis_path"):
        value = entry[field]
        if not isinstance(value, str) or safe_repo_path(repo_root, value) is None:
            raise InvalidInputError(f"bundle entry contains unsafe {field}")
        paths.append(value)
    protocol, snapshot, analysis = (
        load_bounded_json_object(repo_root, path, max_bytes=_MAX_FILE_BYTES) for path in paths
    )
    return entry, protocol, snapshot, analysis


def load_bundles(
    repo_root: Path = REPO_ROOT,
) -> list[tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]]:
    """Load every independently revisioned claim bundle named by the manifest."""

    manifest = load_bounded_json_object(repo_root, MANIFEST_PATH, max_bytes=_MAX_FILE_BYTES)
    if set(manifest) != _MANIFEST_KEYS:
        raise InvalidInputError(
            f"{MANIFEST_PATH!r} fields must exactly match {sorted(_MANIFEST_KEYS)}; got {sorted(manifest)}"
        )
    supplemental = manifest["supplemental_bundles"]
    if not isinstance(supplemental, list) or len(supplemental) > 32:
        raise InvalidInputError(f"{MANIFEST_PATH!r} supplemental_bundles must be a list with at most 32 entries")
    primary = {field: manifest[field] for field in _BUNDLE_ENTRY_KEYS}
    entries = [primary]
    for index, entry in enumerate(supplemental):
        if not isinstance(entry, dict):
            raise InvalidInputError(f"{MANIFEST_PATH!r} supplemental_bundles[{index}] must be an object")
        entries.append(entry)
    bundle_ids = [entry.get("bundle_id") for entry in entries]
    if any(not _valid_id(bundle_id) for bundle_id in bundle_ids) or len(bundle_ids) != len(set(bundle_ids)):
        raise InvalidInputError(f"{MANIFEST_PATH!r} bundle ids must be unique stable ids")
    return [_load_bundle_entry(repo_root, entry) for entry in entries]


def evaluate(repo_root: Path = REPO_ROOT) -> list[PolicyFailure]:
    try:
        bundles = load_bundles(repo_root)
    except (OSError, InvalidInputError) as exc:
        return [_failure("dsl-evaluation-bundle-invalid", str(exc), MANIFEST_PATH)]
    failures: list[PolicyFailure] = []
    for entry, protocol, snapshot, analysis in bundles:
        failures.extend(validate_bundle(repo_root, protocol, snapshot, analysis, artifact_paths=entry))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit failures as JSON")
    args = parser.parse_args()
    try:
        failures = evaluate(REPO_ROOT)
    except (OSError, InvalidInputError) as exc:
        print(f"dsl-language-evaluation: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "rule_id": failure.rule_id,
                        "message": failure.message,
                        "path": failure.path,
                    }
                    for failure in failures
                ],
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for failure in failures:
            print(failure.render())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
