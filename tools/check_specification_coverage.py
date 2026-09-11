#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Validate the standardized specification-coverage evidence bundle.

The closed key sets, shape primitives, and per-section validators live in the
``tools/specification_coverage`` support package; this entry point loads the
revisioned bundles, wires the validators together, and keeps the import
surface the test suite and nox lanes rely on.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.evidence_bundle_index import load_index_records, revision_key
from tools.policy.common import (
    PolicyFailure,
    load_bounded_json_object,
    safe_repo_path,
)
from tools.specification_coverage._analysis import _validate_analysis, recompute_analysis
from tools.specification_coverage._keys import (
    _MANIFEST_KEYS,
    _MAX_FILE_BYTES,
    _SHA256_RE,
    EXPECTED_CLASSIFICATIONS,
    EXPECTED_STRATA,
    MANIFEST_PATH,
    MANIFEST_SCHEMA_VERSION,
)
from tools.specification_coverage._primitives import _failure, _sha256
from tools.specification_coverage._protocol import _validate_protocol
from tools.specification_coverage._snapshot import _validate_snapshot
from tools.research_evidence import current_release_path

__all__ = [
    "EXPECTED_CLASSIFICATIONS",
    "EXPECTED_STRATA",
    "evaluate",
    "load_bundle",
    "load_bundles",
    "main",
    "recompute_analysis",
    "validate_bundle",
]


def validate_bundle(
    repo_root: Path,
    protocol: dict[str, object],
    snapshot: dict[str, object],
    analysis: dict[str, object],
) -> list[PolicyFailure]:
    """Validate bundle shape, execution evidence, joins, and claim honesty."""

    failures: list[PolicyFailure] = []
    catalogs = _validate_protocol(repo_root, protocol, failures)
    _validate_snapshot(repo_root, protocol, snapshot, catalogs, failures)
    _validate_analysis(protocol, snapshot, analysis, failures)
    return failures


def load_bundle(
    repo_root: Path = REPO_ROOT,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    bundles = load_bundles(repo_root)
    return max(
        bundles,
        key=lambda item: (
            revision_key(item[0].get("revision")),
            item[0]["snapshot_path"],
        ),
    )


def load_bundles(
    repo_root: Path = REPO_ROOT,
) -> list[tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]]:
    records = load_index_records(
        repo_root,
        index_path=MANIFEST_PATH,
        schema_version=MANIFEST_SCHEMA_VERSION,
        directory_key="bundles_directory",
        max_bytes=_MAX_FILE_BYTES,
    )
    current_path = current_release_path(records)
    if dict(records)[current_path].get("revision") != "3.0.0" or {record.get("revision") for _, record in records} != {
        "1.0.0",
        "1.1.0",
        "2.0.0",
        "3.0.0",
    }:
        raise ValueError("coverage evidence requires the explicit current 3.0.0 release and supported history")
    bundles = []
    for manifest_path, manifest in records:
        bundles.append(_load_bundle_record(repo_root, manifest_path, manifest))
    return bundles


def _load_bundle_record(
    repo_root: Path,
    manifest_path: str,
    manifest: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    if set(manifest) != _MANIFEST_KEYS:
        raise ValueError(
            f"{manifest_path!r} fields must exactly match {sorted(_MANIFEST_KEYS)}; got {sorted(manifest)}"
        )
    revision_key(manifest.get("revision"))
    loaded: list[dict[str, object]] = []
    for label in ("protocol", "snapshot", "analysis"):
        path_value = manifest[f"{label}_path"]
        sha_value = manifest[f"{label}_sha256"]
        resolved = safe_repo_path(repo_root, path_value) if isinstance(path_value, str) else None
        if resolved is None or not resolved.is_file():
            raise ValueError(f"{manifest_path!r} contains unsafe or missing {label}_path")
        if not isinstance(sha_value, str) or not _SHA256_RE.fullmatch(sha_value):
            raise ValueError(f"{manifest_path!r} contains invalid {label}_sha256")
        if _sha256(resolved) != sha_value:
            raise ValueError(f"{manifest_path!r} contains stale {label}_sha256")
        loaded.append(load_bounded_json_object(repo_root, path_value, max_bytes=_MAX_FILE_BYTES))
    return manifest, loaded[0], loaded[1], loaded[2]


def evaluate(repo_root: Path = REPO_ROOT) -> list[PolicyFailure]:
    try:
        bundles = load_bundles(repo_root)
    except (OSError, ValueError) as exc:
        return [_failure("specification-coverage-bundle-invalid", str(exc), MANIFEST_PATH)]
    failures: list[PolicyFailure] = []
    for manifest, protocol, snapshot, analysis in bundles:
        validator = validate_bundle if manifest.get("revision") == "3.0.0" else validate_historical_bundle
        failures.extend(validator(repo_root, protocol, snapshot, analysis))
    return failures


def validate_historical_bundle(
    repo_root: Path, protocol: dict[str, object], snapshot: dict[str, object], analysis: dict[str, object]
) -> list[PolicyFailure]:
    """Validate frozen archive integrity and recorded joins, not current replay."""
    failures: list[PolicyFailure] = []
    catalogs = _validate_protocol(repo_root, protocol, failures)
    _validate_snapshot(repo_root, protocol, snapshot, catalogs, failures, replay_current=False)
    _validate_analysis(protocol, snapshot, analysis, failures)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit failures as JSON")
    args = parser.parse_args()
    failures = evaluate(REPO_ROOT)
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
    raise SystemExit(main())
