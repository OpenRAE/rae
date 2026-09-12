"""Package-artifact inventory coverage and acquisition-site validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import (
    ADMISSION_POLICY_PATH,
    INVENTORY_COVERAGE_PATH,
    as_list,
    as_mapping,
    failure,
    policy_join_failures,
    safe_text,
    string_set,
)
from tools.tooling_artifact_policy_discovery import (
    PythonScan,
    is_acquisition_scan_candidate,
    structured_acquisition,
)

EXPECTED_INVENTORY_IDS = frozenset(
    {
        *(f"I{index:02d}" for index in range(1, 17)),
        *(f"A{index:02d}" for index in range(1, 8)),
        *(f"O{index:02d}" for index in range(1, 5)),
        *(f"C{index:02d}" for index in range(1, 5)),
        "S01",
        "S02",
        "D01",
    }
)


@dataclass(frozen=True)
class _AcquisitionObservation:
    acquisition_count: int
    unknown_count: int
    failure: PolicyFailure | None = None

    @property
    def total(self) -> int:
        return self.acquisition_count + self.unknown_count


def _admission_policies(documents: Mapping[str, dict[str, Any]]) -> dict[str, Mapping[str, Any]]:
    admission = documents.get(ADMISSION_POLICY_PATH) or {}
    return {
        item["policy_id"]: item
        for item in as_list(admission.get("policies"))
        if isinstance(item, Mapping) and isinstance(item.get("policy_id"), str)
    }


def _inventory_ids(rows: Sequence[Any]) -> tuple[set[str], list[PolicyFailure]]:
    seen: set[str] = set()
    failures: list[PolicyFailure] = []
    for row_value in rows:
        inventory_id = as_mapping(row_value).get("inventory_id")
        if not isinstance(inventory_id, str):
            continue
        if inventory_id in seen:
            failures.append(
                failure(
                    "tooling-inventory-duplicate",
                    "inventory row is covered more than once",
                    INVENTORY_COVERAGE_PATH,
                )
            )
        seen.add(inventory_id)
    missing = EXPECTED_INVENTORY_IDS - seen
    extra = seen - EXPECTED_INVENTORY_IDS
    if missing:
        failures.append(
            failure(
                "tooling-inventory-missing",
                f"{len(missing)} package-artifact inventory rows lack coverage",
                INVENTORY_COVERAGE_PATH,
            )
        )
    if extra:
        failures.append(
            failure(
                "tooling-inventory-extra",
                f"{len(extra)} unknown package-artifact inventory rows are present",
                INVENTORY_COVERAGE_PATH,
            )
        )
    return seen, failures


def _row_policy_failures(
    rows: Sequence[Any],
    policies: Mapping[str, Mapping[str, Any]],
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for row_value in rows:
        row = as_mapping(row_value)
        inventory_id = row.get("inventory_id")
        if not isinstance(inventory_id, str):
            continue
        failures.extend(
            policy_join_failures(
                policy_refs=string_set(row.get("policy_refs")),
                expected_subjects=string_set(row.get("subjects")),
                provided_evidence=string_set(row.get("evidence_refs")),
                policies=policies,
                path=INVENTORY_COVERAGE_PATH,
                context=f"inventory row {inventory_id}",
                require_all_evidence_per_policy=False,
            )
        )
    return failures


def _owned_paths(coverage: Mapping[str, Any], inventory_ids: set[str]) -> tuple[dict[str, int], list[PolicyFailure]]:
    owned: dict[str, int] = {}
    failures: list[PolicyFailure] = []
    for acquisition_value in as_list(coverage.get("acquisition_paths")):
        acquisition = as_mapping(acquisition_value)
        path = acquisition.get("path")
        inventory_id = acquisition.get("inventory_id")
        site_count = acquisition.get("site_count")
        if not isinstance(path, str) or not isinstance(inventory_id, str) or inventory_id not in inventory_ids:
            continue
        if path in owned:
            failures.append(
                failure(
                    "tooling-acquisition-duplicate",
                    "acquisition path has more than one disposition",
                    path,
                )
            )
        if isinstance(site_count, int) and not isinstance(site_count, bool):
            owned[path] = site_count
    return owned, failures


def _python_observation(path: str, scan: PythonScan | None) -> _AcquisitionObservation:
    if scan is None:
        return _AcquisitionObservation(
            0,
            0,
            failure(
                "tooling-acquisition-scan",
                "possible acquisition surface could not be read safely",
                path,
            ),
        )
    if not scan.parsed:
        return _AcquisitionObservation(
            0,
            0,
            failure(
                "tooling-acquisition-scan",
                "possible acquisition surface could not be parsed safely",
                path,
            ),
        )
    return _AcquisitionObservation(scan.acquisition_count, scan.unknown_executable_count)


def _nonpython_observation(repo_root: Path, path: str) -> _AcquisitionObservation:
    text = safe_text(repo_root, path)
    if text is None:
        return _AcquisitionObservation(
            0,
            0,
            failure(
                "tooling-acquisition-scan",
                "possible acquisition surface could not be read safely",
                path,
            ),
        )
    acquisition_count, parsed, unknown_count = structured_acquisition(text, path)
    if not parsed:
        return _AcquisitionObservation(
            0,
            0,
            failure(
                "tooling-acquisition-scan",
                "possible acquisition surface could not be parsed safely",
                path,
            ),
        )
    return _AcquisitionObservation(acquisition_count, unknown_count)


def _observe_path(
    repo_root: Path,
    path: str,
    python_scans: Mapping[str, PythonScan | None],
) -> _AcquisitionObservation:
    if Path(path).suffix == ".py":
        return _python_observation(path, python_scans.get(path))
    return _nonpython_observation(repo_root, path)


def _unowned_failures(path: str, observation: _AcquisitionObservation, owned: Mapping[str, int]) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    if observation.acquisition_count and path not in owned:
        failures.append(
            failure(
                "tooling-acquisition-unowned",
                "artifact acquisition path lacks an inventory disposition",
                path,
            )
        )
    if observation.unknown_count and path not in owned:
        failures.append(
            failure(
                "tooling-acquisition-unknown",
                "dynamic executable form lacks an explicit inventory disposition",
                path,
            )
        )
    return failures


def _acquisition_failures(
    repo_root: Path,
    tracked_paths: Sequence[str],
    python_scans: Mapping[str, PythonScan | None],
    owned: Mapping[str, int],
) -> list[PolicyFailure]:
    observed: dict[str, int] = {}
    failures: list[PolicyFailure] = []
    for path in tracked_paths:
        if not is_acquisition_scan_candidate(path):
            continue
        observation = _observe_path(repo_root, path, python_scans)
        if observation.failure is not None:
            failures.append(observation.failure)
            continue
        if observation.total:
            observed[path] = observation.total
        failures.extend(_unowned_failures(path, observation, owned))
    failures.extend(
        failure(
            "tooling-acquisition-stale",
            "inventory disposition does not match a discovered acquisition surface",
            path,
        )
        for path in sorted(set(owned) - set(observed))
    )
    failures.extend(
        failure(
            "tooling-acquisition-drift",
            "discovered acquisition-site count differs from its explicit disposition",
            path,
        )
        for path in sorted(set(owned) & set(observed))
        if owned[path] != observed[path]
    )
    return failures


def inventory_failures(
    repo_root: Path,
    documents: Mapping[str, dict[str, Any]],
    tracked_paths: Sequence[str],
    python_scans: Mapping[str, PythonScan | None],
) -> list[PolicyFailure]:
    """Validate complete inventory ownership and discovered acquisition sites."""

    coverage = documents.get(INVENTORY_COVERAGE_PATH)
    if coverage is None:
        return []
    rows = as_list(coverage.get("rows"))
    inventory_ids, failures = _inventory_ids(rows)
    failures.extend(_row_policy_failures(rows, _admission_policies(documents)))
    owned, ownership_failures = _owned_paths(coverage, inventory_ids)
    failures.extend(ownership_failures)
    failures.extend(_acquisition_failures(repo_root, tracked_paths, python_scans, owned))
    return failures
