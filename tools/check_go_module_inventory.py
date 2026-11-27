"""Reconcile Go verification consumers with the architecture module authority.

Run after archcheck, which owns architecture validation and module discovery.
This adapter checks consumer inventories without loading or compiling Go code.
The ADR-123 workflow tests own the gate commands. This check owns their reach:
each declared module must receive every module gate in a required job.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
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
CI_WORKFLOW = ".github/workflows/ci.yml"
SONAR_PROPERTIES = "sonar-project.properties"
RULE = "go-module-inventory"
MODULE_DIRECTORY = "${{ matrix.path }}"
GO_ENV = {"GOTOOLCHAIN": "local", "GOFLAGS": "-mod=readonly", "GOWORK": "off"}
GO_JOBS = ("go", "go-test", "go-architecture")
# archcheck reads the model with the same limit (implementations/tooling/go/arch/model.go).
ARCHITECTURE_MODEL_LIMIT = 4 * 1024 * 1024
# The compiler-cycle proof runs exactly this command, so each module must run it.
COMPILER_COMMAND = "go build ./..."
_UNIFORM_CONDITION = re.compile(r"\$\{\{\s*inputs\.[a-z0-9-]+\s*\}\}")
_SAFE_NAME = re.compile(r"[a-z0-9-]+")


def _require(condition: bool, message: str, path: str = WORKFLOW) -> list[PolicyFailure]:
    return [] if condition else [PolicyFailure(RULE, message, path)]


def _equal(actual: list[str], expected: list[str], consumer: str, path: str = WORKFLOW) -> list[PolicyFailure]:
    return _require(
        sorted(actual) == sorted(expected) and len(set(actual)) == len(actual),
        f"{consumer} must cover each architecture module exactly once",
        path,
    )


def _get[T](value: object, dotted: str, kind: type[T], source: str = WORKFLOW) -> T:
    """Return a nested value, or name the missing or mistyped entry."""
    for key in dotted.split("."):
        if not isinstance(value, Mapping) or key not in value:
            raise InvalidInputError(f"{source} lacks {dotted}")
        value = value[key]
    if not isinstance(value, kind):
        raise InvalidInputError(f"{source} has an invalid {dotted}")
    return value


def _mappings(values: list[Any], dotted: str, source: str = WORKFLOW) -> list[Mapping[str, Any]]:
    if not all(isinstance(value, Mapping) for value in values):
        raise InvalidInputError(f"{source} has an invalid entry in {dotted}")
    return values


def _module_directories(root: Path) -> list[str]:
    model = load_bounded_json_object(root, "implementations/architecture.json", max_bytes=ARCHITECTURE_MODEL_LIMIT)
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


def _rows(job: Mapping[str, Any], job_name: str) -> list[Mapping[str, Any]]:
    dotted = f"jobs.{job_name}.strategy.matrix.include"
    return _mappings(_get(job, "strategy.matrix.include", list), dotted)


def _steps(job: Mapping[str, Any], job_name: str) -> list[Mapping[str, Any]]:
    return _mappings(_get(job, "steps", list), f"jobs.{job_name}.steps")


def _selected_modules(condition: object, key: str, modules: set[str]) -> set[str] | None:
    """Return the modules that a step condition admits, or None when unsupported."""
    text = "" if condition is None else str(condition).strip()
    # No condition, or a workflow input, gates the lane for every module alike.
    selected: set[str] | None = set(modules) if not text or _UNIFORM_CONDITION.fullmatch(text) else None
    match = re.fullmatch(rf"(?:\$\{{\{{\s*)?matrix\.{key}\s*(==|!=)\s*'([a-z0-9-]+)'(?:\s*\}}\}})?", text)
    if match is not None:
        operator, name = match.groups()
        selected = {name} & modules if operator == "==" else modules - {name}
    return selected


def _required_jobs(workflow: Mapping[str, Any]) -> list[PolicyFailure]:
    jobs = _get(workflow, "jobs", Mapping)
    needs = _get(workflow, "jobs.gate.needs", list)
    failures: list[PolicyFailure] = []
    for name in GO_JOBS:
        job = _get(jobs, name, Mapping, WORKFLOW)
        failures += _require(
            name in needs and "if" not in job and not job.get("continue-on-error"),
            f"{name} must be a required job of the aggregate gate",
        )
        env = _get(job, "env", Mapping)
        failures += _require(
            all(env.get(key) == value for key, value in GO_ENV.items()),
            f"{name} must use the admitted readonly toolchain without a workspace",
        )
    return failures


def _check_matrix(go: Mapping[str, Any], dirs: list[str]) -> list[PolicyFailure]:
    rows = _rows(go, "go")
    failures = _equal([str(row.get("path")) for row in rows], dirs, "Go matrix")
    names = [row.get("name") for row in rows]
    failures += _require(
        len(set(names)) == len(names) and all(isinstance(n, str) and _SAFE_NAME.fullmatch(n) for n in names),
        "Go matrix names must be unique safe artifact identifiers",
    )
    failures += _require(
        all(type(row.get("shards")) is int and row["shards"] >= 1 for row in rows),
        "Go matrix rows must declare at least one test group",
    )
    return failures


def _check_test_groups(go: Mapping[str, Any], tests: Mapping[str, Any]) -> list[PolicyFailure]:
    """Require each module's declared test groups, and only those groups."""
    modules = {row.get("name"): row for row in _rows(go, "go")}
    groups = _rows(tests, "go-test")
    group_names = [row.get("group") for row in groups]
    failures = _require(
        len(set(group_names)) == len(group_names)
        and set(group_names) == set(_get(tests, "strategy.matrix.group", list)),
        "Go test groups must match the group axis exactly once",
    )
    failures += _require(
        all(row.get("module") in modules and row.get("path") == modules[row["module"]].get("path") for row in groups),
        "Go test groups must name a matrix module and its path",
    )
    counts = Counter(row.get("module") for row in groups)
    for name, row in modules.items():
        failures += _require(
            counts[name] == row.get("shards"),
            f"Go test groups must cover module {row.get('path')} with its declared group count",
        )
    return failures


def _equivalent_step_elsewhere(
    workflow: Mapping[str, Any],
    source_job: str,
    step: Mapping[str, Any],
    directory: str,
) -> bool:
    """Find the same gate script run unconditionally for one module in another required job."""
    needs = _get(workflow, "jobs.gate.needs", list)
    required = [
        (name, job)
        for name, job in _get(workflow, "jobs", Mapping).items()
        if name != source_job and name in needs and isinstance(job, Mapping) and "if" not in job
    ]
    return any(
        _same_unconditional_step(other, step, directory) for name, job in required for other in _steps(job, name)
    )


def _same_unconditional_step(other: Mapping[str, Any], step: Mapping[str, Any], directory: str) -> bool:
    return (
        other.get("working-directory") == directory
        and other.get("run") == step.get("run")
        and "if" not in other
        and not other.get("continue-on-error")
    )


def _check_module_lanes(workflow: Mapping[str, Any], job_name: str, key: str) -> list[PolicyFailure]:
    """Require every module-directory step to reach every module in a required job."""
    job = _get(workflow, f"jobs.{job_name}", Mapping)
    paths = {row.get(key): row.get("path") for row in _rows(job, job_name)}
    failures: list[PolicyFailure] = []
    for step in _steps(job, job_name):
        if step.get("working-directory") != MODULE_DIRECTORY:
            continue
        label = f"{job_name} step {step.get('name', '(unnamed)')!r}"
        failures += _require(not step.get("continue-on-error"), f"{label} must fail the job")
        selected = _selected_modules(step.get("if"), key, set(paths))
        if selected is None:
            failures += _require(
                False,
                f"{label} has a condition that the module inventory cannot evaluate",
            )
            continue
        for name in sorted(set(paths) - selected):
            failures += _require(
                _equivalent_step_elsewhere(workflow, job_name, step, str(paths[name])),
                f"{label} skips module {paths[name]} without the same required step elsewhere",
            )
    return failures


def _check_compiler(go: Mapping[str, Any]) -> list[PolicyFailure]:
    return _require(
        any(
            step.get("working-directory") == MODULE_DIRECTORY
            and "if" not in step
            and COMPILER_COMMAND in str(step.get("run", "")).splitlines()
            for step in _steps(go, "go")
        ),
        f"Go matrix must run {COMPILER_COMMAND!r} in every module directory",
    )


def _check_coverage_upload(go: Mapping[str, Any]) -> list[PolicyFailure]:
    upload = [
        step
        for step in _steps(go, "go")
        if isinstance(step.get("with"), Mapping) and step["with"].get("path") == f"{MODULE_DIRECTORY}/cover.out"
    ]
    return _require(
        len(upload) == 1
        and upload[0]["with"].get("if-no-files-found") == "error"
        and upload[0]["with"].get("name") == "go-coverage-${{ matrix.name }}-${{ inputs.ref }}"
        and "if" not in upload[0]
        and not upload[0].get("continue-on-error"),
        "Go coverage artifact upload must be required for every module",
    )


def _sonar_properties(root: Path) -> dict[str, str]:
    path = safe_repo_path(root, SONAR_PROPERTIES)
    if path is None or not path.is_file():
        raise InvalidInputError("missing or unsafe Sonar configuration")
    return {
        key.strip(): value.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
        for key, value in [line.split("=", 1)]
    }


def _check_sonar(root: Path, workflow: Mapping[str, Any], dirs: list[str]) -> list[PolicyFailure]:
    rows = _rows(_get(workflow, "jobs.go", Mapping), "go")
    downloads = [
        step["with"]
        for step in _steps(_get(workflow, "jobs.sonar", Mapping), "sonar")
        if isinstance(step.get("with"), Mapping) and str(step["with"].get("name", "")).startswith("go-coverage-")
    ]
    failures = _equal(
        [str(d.get("path", "")).rstrip("/") for d in downloads],
        dirs,
        "Go coverage downloads",
    )
    failures += _require(
        {(d.get("name"), str(d.get("path", "")).rstrip("/")) for d in downloads}
        == {(f"go-coverage-{row.get('name')}-${{{{ inputs.ref }}}}", row.get("path")) for row in rows},
        "Go coverage downloads must match producer identities",
    )
    properties = _sonar_properties(root)
    failures += _equal(
        properties.get("sonar.go.coverage.reportPaths", "").split(","),
        [f"{d}/cover.out" for d in dirs],
        "Go coverage reports",
        SONAR_PROPERTIES,
    )
    for key in ("sonar.sources", "sonar.tests"):
        roots = properties.get(key, "").split(",")
        failures += _require(
            all(d in roots for d in dirs),
            f"{key} must analyze each Go module",
            SONAR_PROPERTIES,
        )
    return failures


def _check_scans(
    root: Path,
    ci: Mapping[str, Any],
    dirs: list[str],
    scan_targets: Sequence[tuple[str, Path, Path]],
) -> list[PolicyFailure]:
    scan_modules = [path.parent.relative_to(root).as_posix() for _, path, _ in scan_targets if path.name == "go.mod"]
    failures = _equal(scan_modules, dirs, "OSV Go targets", CI_WORKFLOW)
    uploads = [
        step.get("with")
        for step in _steps(_get(ci, "jobs.supply-chain", Mapping, CI_WORKFLOW), "supply-chain")
        if step.get("name") == "Upload OSV-scanner report"
    ]
    if len(uploads) != 1 or not isinstance(uploads[0], Mapping):
        raise InvalidInputError(f"{CI_WORKFLOW} lacks one OSV report upload")
    failures += _equal(
        str(uploads[0].get("path", "")).split(),
        [report.relative_to(root).as_posix() for _, _, report in scan_targets],
        "OSV reports",
        CI_WORKFLOW,
    )
    return failures


def check_inventory(root: Path, scan_targets: Sequence[tuple[str, Path, Path]]) -> list[PolicyFailure]:
    """Require all consumers to cover each module once, with common gates."""
    dirs = _module_directories(root)
    failures = _equal(dirs, list(set(dirs)), "declared modules", "implementations/architecture.json")
    workflow, errors = parse_yaml_mapping(root, WORKFLOW)
    failures.extend(errors)
    ci, errors = parse_yaml_mapping(root, CI_WORKFLOW)
    failures.extend(errors)
    if workflow is None or ci is None:
        return failures
    go = _get(workflow, "jobs.go", Mapping)
    tests = _get(workflow, "jobs.go-test", Mapping)
    failures.extend(_required_jobs(workflow))
    failures.extend(_check_matrix(go, dirs))
    failures.extend(_check_test_groups(go, tests))
    failures.extend(_check_module_lanes(workflow, "go", "name"))
    failures.extend(_check_module_lanes(workflow, "go-test", "module"))
    failures.extend(_check_compiler(go))
    failures.extend(_check_coverage_upload(go))
    failures.extend(_check_sonar(root, workflow, dirs))
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
    except (InvalidInputError, OSError) as error:
        print(f"go-module-inventory: invalid or incomplete inventory configuration: {error}")
        return 1
    for failure in failures:
        print(failure.render())
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(run_application(main))
