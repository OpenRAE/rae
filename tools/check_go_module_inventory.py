"""Reconcile Go verification consumers with the architecture module authority.

Run after archcheck, which owns architecture validation and module discovery.
This adapter checks consumer inventories without loading or compiling Go code.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from raes_contracts.errors import InvalidInputError  # noqa: E402
from raes_contracts.operational_logging import run_application  # noqa: E402

from implementations.tooling.action_policy_yaml import parse_yaml_mapping  # noqa: E402
from tools.policy.common import PolicyFailure, load_bounded_json_object, safe_repo_path  # noqa: E402

WORKFLOW = ".github/workflows/canonical-verification.yml"
RULE = "go-module-inventory"


def _require(condition: bool, message: str) -> list[PolicyFailure]:
    return [] if condition else [PolicyFailure(RULE, message, WORKFLOW)]


def _equal(actual: list[str], expected: list[str], consumer: str) -> list[PolicyFailure]:
    return _require(
        sorted(actual) == sorted(expected) and len(set(actual)) == len(actual),
        f"{consumer} must cover each architecture module exactly once",
    )


def _module_directories(root: Path) -> list[str]:
    model = load_bounded_json_object(root, "implementations/architecture.json", max_bytes=2_000_000)
    # archcheck validates the model before this adapter in the required job.
    modules = model.get("modules")
    if not isinstance(modules, list) or not modules:
        raise InvalidInputError("Go module inventory must not be empty")
    dirs = []
    for module in modules:
        directory = module.get("dir") if isinstance(module, dict) else None
        if not isinstance(directory, str) or not directory or safe_repo_path(root, directory) is None:
            raise InvalidInputError("Go module inventory contains an unsafe directory")
        dirs.append(directory)
    return dirs


def _check_matrix(go: dict[str, Any], dirs: list[str]) -> list[PolicyFailure]:
    rows = go["strategy"]["matrix"]["include"]
    failures = _equal([row["path"] for row in rows], dirs, "Go matrix")
    names = [row["name"] for row in rows]
    failures += _require(
        len(set(names)) == len(names) and all(re.fullmatch(r"[a-z0-9-]+", name) for name in names),
        "Go matrix names must be unique safe artifact identifiers",
    )
    failures += _require(
        not go.get("if") and not go.get("continue-on-error"),
        "Go matrix must be required",
    )
    failures += _require(
        go["env"].get("GOTOOLCHAIN") == "local"
        and go["env"].get("GOFLAGS") == "-mod=readonly"
        and go["env"].get("GOWORK") == "off",
        "Go matrix must use the admitted readonly toolchain without a workspace",
    )
    return failures


def _check_go_lanes(go: dict[str, Any]) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    scripts = "\n".join(
        step.get("run", "") for step in go["steps"] if not step.get("if") and not step.get("continue-on-error")
    )
    for command in (
        "install-go public-ubuntu-24.04-x86_64",
        "go build ./...",
        "go mod tidy -diff",
        "go mod verify",
        'golangci-lint run --config "${GITHUB_WORKSPACE}/implementations/.golangci.yml" ./...',
        'go vet -vettool="$(command -v raesvet)" ./...',
        "go test -v -race -covermode=atomic -coverprofile=cover.out ./...",
        "exit !(total >= 90)",
        "-fuzztime 20s",
        "gremlins unleash",
        "regressiontest -base",
    ):
        failures += _require(command in scripts, f"Go matrix lacks required lane: {command}")
    return failures


def _check_coverage_upload(go: dict[str, Any]) -> list[PolicyFailure]:
    upload = [step for step in go["steps"] if step.get("with", {}).get("path") == "${{ matrix.path }}/cover.out"]
    return _require(
        len(upload) == 1
        and upload[0]["with"].get("if-no-files-found") == "error"
        and upload[0]["with"].get("name") == "go-coverage-${{ matrix.name }}-${{ inputs.ref }}"
        and not upload[0].get("if")
        and not upload[0].get("continue-on-error"),
        "Go coverage artifact upload must be required for every module",
    )


def _sonar_properties(root: Path) -> dict[str, str]:
    path = safe_repo_path(root, "sonar-project.properties")
    if path is None:
        raise InvalidInputError("unsafe Sonar configuration")
    return {
        key: value
        for line in path.read_text().splitlines()
        if line and not line.startswith("#") and "=" in line
        for key, value in [line.split("=", 1)]
    }


def _check_sonar(
    root: Path, workflow: dict[str, Any], dirs: list[str], rows: list[dict[str, Any]]
) -> list[PolicyFailure]:
    downloads = [
        step["with"]
        for step in workflow["jobs"]["sonar"]["steps"]
        if step.get("with", {}).get("name", "").startswith("go-coverage-")
    ]
    failures = _equal([d["path"].rstrip("/") for d in downloads], dirs, "Go coverage downloads")
    failures += _require(
        {(d["name"], d["path"].rstrip("/")) for d in downloads}
        == {(f"go-coverage-{row['name']}-${{{{ inputs.ref }}}}", row["path"]) for row in rows},
        "Go coverage downloads must match producer identities",
    )
    properties = _sonar_properties(root)
    failures += _equal(
        properties.get("sonar.go.coverage.reportPaths", "").split(","),
        [f"{d}/cover.out" for d in dirs],
        "Go coverage reports",
    )
    for key in ("sonar.sources", "sonar.tests"):
        roots = properties.get(key, "").split(",")
        failures += _require(all(d in roots for d in dirs), f"{key} must analyze each Go module")
    return failures


def _check_scans(
    root: Path, ci: dict[str, Any], dirs: list[str], scan_targets: Sequence[tuple[str, Path, Path]]
) -> list[PolicyFailure]:
    scan_modules = [path.parent.relative_to(root).as_posix() for _, path, _ in scan_targets if path.name == "go.mod"]
    failures = _equal(scan_modules, dirs, "OSV Go targets")
    scan_upload = next(
        step["with"] for step in ci["jobs"]["supply-chain"]["steps"] if step.get("name") == "Upload OSV-scanner report"
    )
    failures += _equal(
        scan_upload["path"].split(),
        [report.relative_to(root).as_posix() for _, _, report in scan_targets],
        "OSV reports",
    )
    return failures


def check_inventory(root: Path, scan_targets: Sequence[tuple[str, Path, Path]]) -> list[PolicyFailure]:
    """Require all consumers to cover each module once, with common gates."""
    dirs = _module_directories(root)
    failures = _equal(dirs, list(set(dirs)), "declared modules")
    workflow, errors = parse_yaml_mapping(root, WORKFLOW)
    failures.extend(errors)
    ci, errors = parse_yaml_mapping(root, ".github/workflows/ci.yml")
    failures.extend(errors)
    if workflow is None or ci is None:
        return failures
    go = workflow["jobs"]["go"]
    failures.extend(_check_matrix(go, dirs))
    failures.extend(_check_go_lanes(go))
    failures.extend(_check_coverage_upload(go))
    failures.extend(_check_sonar(root, workflow, dirs, go["strategy"]["matrix"]["include"]))
    failures.extend(_check_scans(root, ci, dirs, scan_targets))
    return failures


def check_scan_reports(root: Path, targets: Sequence[tuple[str, Path, Path]]) -> None:
    """Require a nonempty JSON report for every scanned closure on success."""
    for _, _, report in targets:
        load_bounded_json_object(root, report.relative_to(root).as_posix(), max_bytes=50_000_000)


def main() -> int:
    from tools.nox_support.config import OSV_SCAN_TARGETS, REPO_ROOT

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan-reports",
        action="store_true",
        help="Check scan outputs after successful scanning",
    )
    args = parser.parse_args()
    try:
        if args.scan_reports:
            check_scan_reports(REPO_ROOT, OSV_SCAN_TARGETS)
            return 0
        failures = check_inventory(REPO_ROOT, OSV_SCAN_TARGETS)
    except InvalidInputError, KeyError, TypeError, ValueError, OSError:
        print("go-module-inventory: invalid or incomplete inventory configuration")
        return 1
    for failure in failures:
        print(failure.render())
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(run_application(main))
