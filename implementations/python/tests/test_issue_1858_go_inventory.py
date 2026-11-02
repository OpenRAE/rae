"""A modeled Go module cannot escape a required verification consumer."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from tools.nox_support.config import OSV_SCAN_TARGETS, REPO_ROOT


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for name in (
        "implementations/architecture.json",
        ".github/workflows/canonical-verification.yml",
        ".github/workflows/ci.yml",
        "sonar-project.properties",
    ):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / name, target)
    return tmp_path


def targets(root: Path) -> tuple:
    return tuple(
        (label, root / path.relative_to(REPO_ROOT), root / report.relative_to(REPO_ROOT))
        for label, path, report in OSV_SCAN_TARGETS
    )


def check(root: Path) -> list:
    from tools.check_go_module_inventory import check_inventory

    return check_inventory(root, targets(root))


def test_current_consumers_agree(repo: Path) -> None:
    assert check(repo) == []


def test_next_declared_module_cannot_escape_ci_and_scanning(repo: Path) -> None:
    path = repo / "implementations/architecture.json"
    model = json.loads(path.read_text())
    model["modules"].append({"dir": "implementations/next/go", "path": "example.com/next"})
    path.write_text(json.dumps(model))
    failures = "\n".join(f.render() for f in check(repo))
    assert "matrix" in failures
    assert "OSV" in failures
    assert "coverage" in failures


@pytest.mark.parametrize("consumer", ["matrix", "scan", "download", "reports", "sources", "tests", "scan-report"])
def test_consumer_omission_fails(repo: Path, consumer: str) -> None:
    scan = targets(repo)
    if consumer == "scan":
        scan = scan[:-1]
    elif consumer in {"reports", "sources", "tests"}:
        path = repo / "sonar-project.properties"
        key = {"reports": "sonar.go.coverage.reportPaths", "sources": "sonar.sources", "tests": "sonar.tests"}[consumer]
        lines = path.read_text().splitlines()
        path.write_text(
            "\n".join(
                line.replace(",implementations/go/cover.out", "").replace(",implementations/go", "")
                if line.startswith(key + "=")
                else line
                for line in lines
            )
        )
    else:
        path = repo / ".github/workflows" / ("ci.yml" if consumer == "scan-report" else "canonical-verification.yml")
        workflow = yaml.safe_load(path.read_text())
        if consumer == "matrix":
            workflow["jobs"]["go"]["strategy"]["matrix"]["include"].pop()
        elif consumer == "download":
            steps = workflow["jobs"]["sonar"]["steps"]
            steps[:] = [s for s in steps if s.get("with", {}).get("path") != "implementations/go/"]
        else:
            steps = workflow["jobs"]["supply-chain"]["steps"]
            step = next(s for s in steps if s.get("name") == "Upload OSV-scanner report")
            step["with"]["path"] = step["with"]["path"].replace("implementations/python/osv-scanner-go-report.json", "")
        path.write_text(yaml.safe_dump(workflow))
    from tools.check_go_module_inventory import check_inventory

    assert check_inventory(repo, scan)


@pytest.mark.parametrize("change", ["duplicate", "extra", "skip", "compiler", "coverage", "toolchain"])
def test_required_matrix_lane_cannot_be_weakened(repo: Path, change: str) -> None:
    path = repo / ".github/workflows/canonical-verification.yml"
    workflow = yaml.safe_load(path.read_text())
    go = workflow["jobs"]["go"]
    if change in {"duplicate", "extra"}:
        row = dict(go["strategy"]["matrix"]["include"][0])
        if change == "extra":
            row = {"name": "extra", "path": "extra"}
        go["strategy"]["matrix"]["include"].append(row)
    elif change == "skip":
        go["if"] = "false"
    elif change == "toolchain":
        go["env"]["GOTOOLCHAIN"] = "auto"
    else:
        token = "go build ./..." if change == "compiler" else "-coverprofile=cover.out"
        for step in go["steps"]:
            if "run" in step:
                step["run"] = step["run"].replace(token, "")
    path.write_text(yaml.safe_dump(workflow))
    assert check(repo)


def test_declared_cycle_fails_the_compiler_gate(tmp_path: Path) -> None:
    """Use exactly the compiler command required of every matrix module."""
    go = shutil.which("go")
    if go is None:
        pytest.skip("The required go-architecture job supplies the admitted toolchain")
    version = subprocess.run([go, "version"], capture_output=True, text=True, check=True)
    if "go1.27.3 " not in version.stdout:
        pytest.skip("The required go-architecture job supplies Go 1.27.3")
    module_root = tmp_path / "m"
    module_root.mkdir()
    (module_root / "go.mod").write_text("module example.com/cycle\n\ngo 1.27.3\n")
    for name, other in (("a", "b"), ("b", "a")):
        (module_root / name).mkdir()
        (module_root / name / "code.go").write_text(f'package {name}\nimport _ "example.com/cycle/{other}"\n')
    model_dir = tmp_path / "implementations"
    model_dir.mkdir()
    (model_dir / "architecture.json").write_text(
        json.dumps(
            {
                "schema": "raes-go-architecture/v1",
                "modules": [{"dir": "m", "path": "example.com/cycle"}],
                "layers": [{"name": "cycle", "dir": "m", "doc": "Cycle fixture.", "uses": [], "external": []}],
                "packages": [
                    {
                        "dir": "m/" + name,
                        "layer": "cycle",
                        "public": False,
                        "doc": "Fixture package.",
                        "imports": ["m/" + other],
                    }
                    for name, other in (("a", "b"), ("b", "a"))
                ],
            }
        )
    )
    adr = tmp_path / "docs/decisions/adrs/adr-122-go-architecture-model.md"
    adr.parent.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / "docs/decisions/adrs/adr-122-go-architecture-model.md", adr)
    binary = tmp_path / "archcheck"
    env = {**os.environ, "GOTOOLCHAIN": "local", "GOFLAGS": "-mod=readonly", "GOWORK": "off"}
    subprocess.run(
        [go, "-C", str(REPO_ROOT / "implementations/tooling/go"), "build", "-o", str(binary), "./cmd/archcheck"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run([str(binary)], cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    result = subprocess.run(
        [go, "build", "./..."],
        cwd=module_root,
        capture_output=True,
        text=True,
        env={**os.environ, "GOTOOLCHAIN": "local", "GOFLAGS": "-mod=readonly", "GOWORK": "off"},
        check=False,
    )
    assert result.returncode != 0
    assert "import cycle not allowed" in result.stderr


def test_required_jobs_run_inventory_after_architecture_check() -> None:
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/canonical-verification.yml").read_text())
    job = workflow["jobs"]["go-architecture"]
    steps = job["steps"]
    architecture = next(
        i for i, step in enumerate(steps) if '"${RUNNER_TEMP}/go-tools/archcheck"' in step.get("run", "")
    )
    inventory = next(i for i, step in enumerate(steps) if "-m tools.check_go_module_inventory" in step.get("run", ""))
    assert inventory > architecture
    assert not steps[inventory].get("if")
    assert not steps[inventory].get("continue-on-error")
    assert not job.get("if")
    assert "go-architecture" in workflow["jobs"]["gate"]["needs"]
    assert "go" in workflow["jobs"]["gate"]["needs"]


def test_missing_scan_report_is_an_error(repo: Path) -> None:
    from raes_contracts.errors import InvalidInputError
    from tools.check_go_module_inventory import check_scan_reports

    scan = targets(repo)
    for _, _, report in scan:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text('{"results": []}')
    check_scan_reports(repo, scan)
    scan[-1][2].unlink()
    with pytest.raises(InvalidInputError):
        check_scan_reports(repo, scan)


def test_unsafe_module_directory_is_rejected(repo: Path) -> None:
    from raes_contracts.errors import InvalidInputError

    path = repo / "implementations/architecture.json"
    model = json.loads(path.read_text())
    model["modules"][0]["dir"] = "../outside"
    path.write_text(json.dumps(model))
    with pytest.raises(InvalidInputError):
        check(repo)


def test_duplicate_yaml_keys_fail_closed(repo: Path) -> None:
    path = repo / ".github/workflows/canonical-verification.yml"
    path.write_text("jobs: {}\njobs: {}\n")
    assert check(repo)


@pytest.mark.parametrize("args,expected", [([], [0]), (["--scan-reports"], [0, 1])])
def test_checker_starts_in_a_clean_tooling_process(args: list[str], expected: list[int]) -> None:
    import sys

    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "-m", "tools.check_go_module_inventory", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in expected, result.stderr
    assert "Traceback" not in result.stderr
    if args and result.returncode == 1:
        assert "invalid or incomplete inventory configuration" in result.stdout
