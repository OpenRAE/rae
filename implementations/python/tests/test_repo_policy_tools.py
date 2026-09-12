from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
import threading
import tomllib
import types
from contextlib import nullcontext
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class _FakeNoxOptions:
    default_venv_backend = ""
    reuse_existing_virtualenvs = False
    sessions: list[str] = []


def _fake_nox_session(*args: object, **_kwargs: object) -> object:
    if args and callable(args[0]):
        return args[0]

    def decorate(function: object) -> object:
        return function

    return decorate


sys.modules.setdefault(
    "nox",
    types.SimpleNamespace(options=_FakeNoxOptions(), Session=object, session=_fake_nox_session),
)

import pytest
import tools.check_generated_schemas as check_generated_schemas
import tools.check_json_artifacts as check_json_artifacts
import tools.nox_support.compatibility_lanes as nox_compatibility_lanes
import tools.nox_support.config as nox_config
import tools.nox_support.graph as nox_graph
import tools.nox_support.policy_lanes as nox_policy_lanes
import tools.nox_support.runner as nox_runner
import tools.nox_support.test_lanes as nox_test_lanes
import tools.osv_scanner_tool as osv_scanner_tool
import tools.policy.conftest_tool as conftest_tool
import yaml
from packaging.requirements import Requirement
from packaging.version import Version
from tools.check_adr_immutability import (
    amendment_refs,
    canonical_content,
    content_hash,
    evaluate_adr_immutability,
)
from tools.check_generated_schemas import _extra_published_schema_paths
from tools.check_json_artifacts import ValidationTarget, collect_validation_targets, should_run_full_validation
from tools.check_schema_publication import schema_content_hash, validate_schema_publication_manifest
from tools.gitleaks_tool import gitleaks_binary_path
from tools.parallel_verification import VerificationLane, run_verification_lanes
from tools.policy.common import PolicyFailure
from tools.policy.conftest_tool import run_conftest_policy
from tools.policy.repo_policy import evaluate_repo_policy

NOX_SUPPORT_MODULES = (
    "config",
    "runner",
    "policy_lanes",
    "test_lanes",
    "compatibility_lanes",
    "graph",
)


def test_sonar_project_binding_matches_scanner_configuration() -> None:
    ground_control = yaml.safe_load((REPO_ROOT / ".ground-control.yaml").read_text(encoding="utf-8"))
    sonar_properties = dict(
        line.split("=", maxsplit=1)
        for line in (REPO_ROOT / "sonar-project.properties").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )

    assert ground_control["sonarcloud"]["project_key"] == sonar_properties["sonar.projectKey"]
    assert ground_control["sonarcloud"]["organization"] == sonar_properties["sonar.organization"]
    assert set(sonar_properties["sonar.sources"].split(",")) == {
        "implementations/python/packages",
        "noxfile.py",
        "tools",
    }


def load_noxfile_with_fake_nox(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    fake_nox = types.SimpleNamespace(options=_FakeNoxOptions(), Session=object, session=_fake_nox_session)
    monkeypatch.setitem(sys.modules, "nox", fake_nox)

    spec = importlib.util.spec_from_file_location("_raes_test_noxfile", REPO_ROOT / "noxfile.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "_raes_test_noxfile", module)
    spec.loader.exec_module(module)
    return module


def test_nox_support_has_one_authoritative_definition_per_symbol() -> None:
    definitions: dict[str, list[str]] = {}
    for module_name in NOX_SUPPORT_MODULES:
        relative_path = f"tools/nox_support/{module_name}.py"
        tree = ast.parse((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            definitions.setdefault(node.name, []).append(relative_path)
    duplicates = {name: paths for name, paths in definitions.items() if len(paths) > 1}
    assert duplicates == {}


def test_noxfile_owns_session_registration_and_nox_configuration() -> None:
    noxfile_source = (REPO_ROOT / "noxfile.py").read_text(encoding="utf-8")
    noxfile_tree = ast.parse(noxfile_source)
    assert 'nox.options.default_venv_backend = "none"' in noxfile_source
    assert "nox.options.reuse_existing_virtualenvs = True" in noxfile_source
    assert 'nox.options.sessions = ["verify"]' in noxfile_source
    for module_name in NOX_SUPPORT_MODULES:
        support_source = (REPO_ROOT / "tools" / "nox_support" / f"{module_name}.py").read_text(encoding="utf-8")
        assert "@nox.session" not in support_source
        assert "nox.options." not in support_source

    loaded_names = {node.id for node in ast.walk(noxfile_tree) if isinstance(node, ast.Name)}
    support_imports = {
        alias.asname or alias.name
        for node in noxfile_tree.body
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("tools.nox_support")
        for alias in node.names
    }
    assert support_imports <= loaded_names


def test_noxfile_registers_the_exact_public_session_inventory() -> None:
    tree = ast.parse((REPO_ROOT / "noxfile.py").read_text(encoding="utf-8"))
    sessions: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Attribute) and decorator.attr == "session":
                sessions.add(node.name)
            elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                name_keyword = next((keyword.value for keyword in decorator.keywords if keyword.arg == "name"), None)
                if decorator.func.attr == "session" and isinstance(name_keyword, ast.Constant):
                    sessions.add(name_keyword.value)
    assert sessions == {
        "contracts",
        "docs",
        "docs-links",
        "docs-local",
        "fuzz",
        "hook-pre-commit",
        "hook-pre-push",
        "hygiene",
        "integration",
        "integration_docker",
        "lint",
        "osv_scan",
        "participant-opacity-proof",
        "policy",
        "python-compatibility",
        "tests",
        "verify",
        "verify-changed",
        "verify-completion",
        "verify-integration-lane",
        "verify-static-lane",
        "verify-tests-lane",
    }


def test_nox_support_dependency_graph_is_acyclic() -> None:
    dependencies = {module_name: set() for module_name in NOX_SUPPORT_MODULES}
    for module_name in NOX_SUPPORT_MODULES:
        source = (REPO_ROOT / "tools" / "nox_support" / f"{module_name}.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert "noxfile" not in imported_modules
        dependencies[module_name].update(
            imported.removeprefix("tools.nox_support.")
            for imported in imported_modules
            if imported.startswith("tools.nox_support.")
        )

    remaining = {module_name: set(imports) for module_name, imports in dependencies.items()}
    while remaining:
        leaves = {module_name for module_name, imports in remaining.items() if not imports.intersection(remaining)}
        assert leaves, f"cyclic nox support imports: {remaining}"
        for module_name in leaves:
            del remaining[module_name]


def test_parallel_coverage_command_is_capped_and_worker_safe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.commands: list[tuple[tuple[str, ...], dict[str, Any]]] = []

        def run(self, *args: str, **kwargs: Any) -> None:
            self.commands.append((args, kwargs))

        def chdir(self, _path: Path):
            return nullcontext()

    session = FakeSession()
    coverage_file = tmp_path / ".coverage"
    nox_runner._run_pytest(
        session,
        "-q",
        coverage_file=coverage_file,
        parallel=True,
    )

    pytest_command, kwargs = next(
        (command, options)
        for command, options in session.commands
        if command[:6] == ("uv", "run", "--frozen", "python", "-m", "pytest")
    )
    assert pytest_command[6:] == (
        "-n",
        "auto",
        "--maxprocesses=8",
        "--dist=worksteal",
        "--cov",
        "--cov-config=pyproject.toml",
        "--cov-report=",
        "-q",
    )
    assert kwargs["env"] == {"COVERAGE_FILE": str(coverage_file)}

    session.commands.clear()
    monkeypatch.setattr(nox_runner, "_enforce_line_coverage", lambda _path: 90.0)
    nox_runner._run_pytest(
        session,
        "-m",
        "integration",
        coverage_file=coverage_file,
        append_coverage=True,
        finalize_coverage=True,
    )
    pytest_command = next(
        command
        for command, _options in session.commands
        if command[:6] == ("uv", "run", "--frozen", "python", "-m", "pytest")
    )
    assert "--cov-append" in pytest_command
    coverage_commands = [
        (command, options)
        for command, options in session.commands
        if command[:4] == ("uv", "run", "--frozen", "coverage")
    ]
    assert [command[4] for command, _options in coverage_commands] == ["xml", "json", "report"]
    assert coverage_commands[-1][0][-1:] == ("--format=total",)
    assert all(options["env"] == {"COVERAGE_FILE": str(coverage_file)} for _, options in coverage_commands)


def test_verification_lanes_run_concurrently_and_preserve_declared_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    barrier = threading.Barrier(2, timeout=2)
    commands: list[tuple[str, ...]] = []
    commands_lock = threading.Lock()

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        with commands_lock:
            commands.append(tuple(command))
        barrier.wait()
        return subprocess.CompletedProcess(command, 0, stdout=f"{command[-1]} passed\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    lanes = (
        VerificationLane(name="static", nox_session="verify-static-lane"),
        VerificationLane(name="contracts", nox_session="contracts", posargs=("--base-rev", "base")),
    )

    results = run_verification_lanes(
        lanes,
        nox_python=Path("/tools/python"),
        noxfile=tmp_path / "noxfile.py",
        repo_root=tmp_path,
        base_env={"RAES_VERIFY_PROJECT_SYNCED": "1"},
    )

    assert [result.name for result in results] == ["static", "contracts"]
    assert all(result.returncode == 0 for result in results)
    assert sorted(commands) == sorted(
        [
            (
                "/tools/python",
                "-m",
                "nox",
                "-f",
                str(tmp_path / "noxfile.py"),
                "-s",
                "verify-static-lane",
            ),
            (
                "/tools/python",
                "-m",
                "nox",
                "-f",
                str(tmp_path / "noxfile.py"),
                "-s",
                "contracts",
                "--",
                "--base-rev",
                "base",
            ),
        ]
    )


def test_parallel_verification_reports_every_failed_lane(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        session_name = command[command.index("-s") + 1]
        return subprocess.CompletedProcess(command, 3 if session_name != "contracts" else 4, stdout=session_name)

    monkeypatch.setattr(subprocess, "run", fake_run)
    results = run_verification_lanes(
        (
            VerificationLane(name="static", nox_session="verify-static-lane"),
            VerificationLane(name="contracts", nox_session="contracts"),
        ),
        nox_python=Path("/tools/python"),
        noxfile=tmp_path / "noxfile.py",
        repo_root=tmp_path,
    )

    assert [(result.name, result.returncode) for result in results] == [("static", 3), ("contracts", 4)]


class ImmediateReporter:
    def __init__(self) -> None:
        self.runs: list[tuple[str, str]] = []
        self.skips: list[tuple[str, str]] = []

    def run(self, name: str, func: object, *, detail: str = "") -> None:
        self.runs.append((name, detail))
        assert callable(func)
        func()

    def skip(self, name: str, reason: str) -> None:
        self.skips.append((name, reason))


def test_policy_lanes_route_commands_and_report_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    session = types.SimpleNamespace()
    reporter = ImmediateReporter()
    commands: list[tuple[str, ...]] = []

    monkeypatch.setattr(nox_policy_lanes, "_sync_project", lambda _session: commands.append(("sync",)))
    monkeypatch.setattr(
        nox_policy_lanes,
        "_run",
        lambda _session, *args, **_kwargs: commands.append(tuple(args)),
    )
    monkeypatch.setattr(
        nox_policy_lanes,
        "_run_project_python",
        lambda _session, *args: commands.append(tuple(args)),
    )
    monkeypatch.setattr(
        nox_policy_lanes,
        "_run_pre_commit_hook",
        lambda _session, command, *args, paths: commands.append((command, *args, *paths)),
    )
    monkeypatch.setattr(
        nox_policy_lanes,
        "_run_gitleaks_dir_scan",
        lambda _session, paths: commands.append(("gitleaks", *paths)),
    )
    monkeypatch.setattr(
        nox_policy_lanes,
        "_run_ruff",
        lambda _session, *args, **_kwargs: commands.append(("ruff", *args)),
    )

    selection = nox_runner.HygieneSelection(
        paths=["README.md", "config.yaml", "data.json"],
        source="test selection",
    )
    monkeypatch.setattr(nox_policy_lanes, "_parse_hygiene_posargs", lambda *_args, **_kwargs: selection)
    monkeypatch.setattr(nox_policy_lanes, "_text_paths", lambda paths: paths[:1])
    nox_policy_lanes._run_hygiene(session, reporter, posargs=[], default_all_files=False)

    nox_policy_lanes._run_policy(session, reporter, "--base-rev", "base", "--requirement-uid", "ASR-1")
    nox_policy_lanes._run_policy(session, reporter, "--staged", "--skip-requirement")
    nox_policy_lanes._run_contracts(
        session,
        reporter,
        "--staged",
        "--base-rev",
        "base",
        "--requirement-uid",
        "ASR-1",
        "--skip-requirement",
        "--unknown",
        "artifact.json",
    )
    nox_policy_lanes._run_lint(session, reporter)
    nox_policy_lanes._run_changed_lint(
        session,
        reporter,
        ["implementations/python/tests/test_example.py", "tools/check_example.py", "noxfile.py"],
    )
    nox_policy_lanes._run_changed_lint(session, reporter, [])
    nox_policy_lanes._run_participant_opacity_proof(session, reporter)

    assert ("tools/check_schema_publication.py", "--base-rev", "base") in commands
    assert ("tools/check_json_artifacts.py", "--staged", "--base-rev", "base", "artifact.json") in commands
    assert ("tools/check_requirement_governance.py", "--base-rev", "base", "--requirement-uid", "ASR-1") in commands
    assert any(name == "policy / semantic coverage ADR" for name, _detail in reporter.runs)
    assert any(name == "policy / semantic coverage ADR" for name, _reason in reporter.skips)
    assert any(name == "lint / ruff check (changed tooling files)" for name, _detail in reporter.runs)
    assert any(name == "lint / ruff check (changed tooling files)" for name, _reason in reporter.skips)


def test_hygiene_lane_handles_empty_and_non_text_selections(monkeypatch: pytest.MonkeyPatch) -> None:
    reporter = ImmediateReporter()

    selections = iter(
        [
            nox_runner.HygieneSelection(paths=[], source="empty"),
            nox_runner.HygieneSelection(paths=["binary.dat"], source="binary"),
        ]
    )
    monkeypatch.setattr(nox_policy_lanes, "_parse_hygiene_posargs", lambda *_args, **_kwargs: next(selections))
    monkeypatch.setattr(nox_policy_lanes, "_text_paths", lambda _paths: [])
    monkeypatch.setattr(nox_policy_lanes, "_run_pre_commit_hook", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(nox_policy_lanes, "_run_gitleaks_dir_scan", lambda *_args, **_kwargs: None)

    nox_policy_lanes._run_hygiene(types.SimpleNamespace(), reporter, posargs=[], default_all_files=False)
    nox_policy_lanes._run_hygiene(types.SimpleNamespace(), reporter, posargs=[], default_all_files=False)

    assert ("hygiene / candidate path resolution", "no files selected from empty") in reporter.skips
    skipped_stages = {name for name, _reason in reporter.skips}
    assert "hygiene / trailing whitespace" in skipped_stages
    assert "hygiene / yaml syntax" in skipped_stages
    assert "hygiene / json syntax" in skipped_stages


def test_parallel_graph_executes_success_and_reports_all_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSession:
        posargs = ["--base-rev", "base"]

        def __init__(self) -> None:
            self.messages: list[str] = []

        def log(self, message: str) -> None:
            self.messages.append(message)

    session = FakeSession()
    reporter = ImmediateReporter()
    calls: list[str] = []
    monkeypatch.setattr(nox_graph, "_sync_project", lambda _session: calls.append("sync"))
    monkeypatch.setattr(
        nox_graph,
        "_run_project_python",
        lambda _session, *_args: calls.append("toolchain"),
    )
    monkeypatch.setattr(
        nox_graph,
        "_finalize_parallel_coverage",
        lambda _session, _path: calls.append("coverage"),
    )
    monkeypatch.setattr(nox_graph, "_available_cpu_count", lambda: 8)

    results = [
        types.SimpleNamespace(name="unit-tests", returncode=0, output="passed\n", duration_s=0.01),
        types.SimpleNamespace(name="contracts", returncode=0, output="", duration_s=0.02),
    ]
    monkeypatch.setattr(nox_graph, "run_verification_lanes", lambda *_args, **_kwargs: results)
    nox_graph._run_parallel_verification(session, reporter, include_policy=True)

    assert calls == ["sync", "toolchain", "coverage"]
    assert any("lane unit-tests: PASS" in message for message in session.messages)

    monkeypatch.setattr(
        nox_graph,
        "run_verification_lanes",
        lambda *_args, **_kwargs: [
            types.SimpleNamespace(
                name="unit-tests",
                returncode=2,
                output="FAILED tests/test_runtime.py::test_atomic_commit - AssertionError\n",
                duration_s=0.01,
            ),
            types.SimpleNamespace(name="contracts", returncode=3, output="", duration_s=0.02),
        ],
    )
    failure_reporter = ImmediateReporter()
    with pytest.raises(RuntimeError, match=r"unit-tests \(exit 2\), contracts \(exit 3\)"):
        nox_graph._run_parallel_verification(session, failure_reporter, include_policy=False)
    assert any(
        "failure summary unit-tests: FAILED tests/test_runtime.py::test_atomic_commit" in message
        for message in session.messages
    )


def test_change_selected_graph_routes_plans_and_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def log(self, message: str) -> None:
            self.messages.append(message)

    session = FakeSession()
    reporter = ImmediateReporter()
    calls: list[str] = []
    plan = types.SimpleNamespace(contracts=False, regression=False, fuzz=False, docs=False, reason="prose")
    monkeypatch.setattr(nox_graph, "collect_git_changes", lambda *_args: [types.SimpleNamespace(path="README.md")])
    monkeypatch.setattr(nox_graph, "plan_for_changes", lambda _changes: plan)
    monkeypatch.setattr(nox_graph, "_requirement_aware_policy_args", lambda *args: list(args))
    for name in ("_run_hygiene", "_run_policy", "_run_lint", "_run_contracts", "_run_tests", "_run_fuzz", "_run_docs"):
        monkeypatch.setattr(nox_graph, name, lambda *_args, _name=name, **_kwargs: calls.append(_name))

    nox_graph._run_changed_verification(session, reporter, ["--base-rev", "base"])
    assert calls == ["_run_hygiene", "_run_policy", "_run_lint"]
    assert {name for name, _reason in reporter.skips} == {
        "contracts / governed artifact graph",
        "tests / pytest",
        "tests / pytest fuzz",
        "docs / sphinx-build",
    }

    plan.contracts = plan.regression = plan.fuzz = plan.docs = True
    calls.clear()
    monkeypatch.setattr(
        nox_graph,
        "_changed_base_rev",
        lambda _posargs: (_ for _ in ()).throw(RuntimeError("no upstream")),
    )
    nox_graph._run_changed_verification(session, ImmediateReporter(), [])
    assert calls == [
        "_run_hygiene",
        "_run_policy",
        "_run_lint",
        "_run_contracts",
        "_run_tests",
        "_run_fuzz",
        "_run_docs",
    ]
    assert any("failed closed" in message for message in session.messages)


def test_graph_base_revision_and_cpu_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    assert nox_graph._changed_base_rev(["--base-rev", "base"]) == "base"
    with pytest.raises(ValueError, match="requires a revision"):
        nox_graph._changed_base_rev(["--base-rev"])
    monkeypatch.setattr(nox_graph, "resolve_upstream", lambda _root: "origin/dev")
    assert nox_graph._changed_base_rev([]) == "origin/dev"

    monkeypatch.setattr(nox_graph.os, "sched_getaffinity", lambda _pid: {0, 1}, raising=False)
    assert nox_graph._available_cpu_count() == 2

    def unavailable(_pid: int) -> set[int]:
        raise OSError("unsupported")

    monkeypatch.setattr(nox_graph.os, "sched_getaffinity", unavailable, raising=False)
    monkeypatch.setattr(nox_graph.os, "cpu_count", lambda: None)
    assert nox_graph._available_cpu_count() == 1


def test_canonical_verify_does_not_use_change_aware_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    noxfile = load_noxfile_with_fake_nox(monkeypatch)
    source = inspect.getsource(noxfile.verify)

    assert "_run_changed_verification" not in source
    assert "_run_parallel_verification" in source

    lanes = nox_graph._verification_lanes(
        posargs=["--base-rev", "base"],
        coverage_dir=Path("/coverage"),
        include_policy=True,
    )
    assert [(lane.name, lane.nox_session) for lane in lanes] == [
        ("unit-tests", "verify-tests-lane"),
        ("integration-tests", "verify-integration-lane"),
        ("contracts", "contracts"),
        ("static", "verify-static-lane"),
        ("participant-opacity-proof", "participant-opacity-proof"),
        ("docs-local", "docs-local"),
    ]
    lanes_by_name = {lane.name: lane for lane in lanes}
    assert lanes_by_name["static"].posargs == ("--include-policy", "--base-rev", "base")
    assert lanes_by_name["contracts"].posargs == ("--base-rev", "base")
    assert lanes_by_name["unit-tests"].env["RAES_VERIFY_COVERAGE_FILE"] == "/coverage/.coverage.unit"
    assert lanes_by_name["integration-tests"].env["RAES_VERIFY_COVERAGE_FILE"] == "/coverage/.coverage.integration"


def test_completion_verification_omits_policy_only_from_static_lane() -> None:
    lanes = nox_graph._verification_lanes(
        posargs=["--requirement-uid", "ASR-535"],
        coverage_dir=Path("/coverage"),
        include_policy=False,
        cpu_count=4,
    )

    lanes_by_name = {lane.name: lane for lane in lanes}
    assert lanes_by_name["static"].posargs == ("--requirement-uid", "ASR-535")
    assert [lane.name for lane in lanes] == [
        "unit-tests",
        "integration-tests",
        "contracts",
        "static",
        "participant-opacity-proof",
        "docs-local",
    ]
    assert lanes_by_name["contracts"].env["RAES_JSON_SCHEMA_WORKERS"] == "1"
    assert lanes_by_name["unit-tests"].env["PYTEST_XDIST_AUTO_NUM_WORKERS"] == "2"
    assert nox_graph._verification_lane_workers(cpu_count=4, lane_count=len(lanes)) == 2
    assert nox_graph._verification_lane_workers(cpu_count=16, lane_count=len(lanes)) == 4


def test_parallel_coverage_is_combined_before_reporting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.commands: list[tuple[tuple[str, ...], dict[str, Any]]] = []

        def run(self, *args: str, **kwargs: Any) -> None:
            self.commands.append((args, kwargs))

        def chdir(self, _path: Path):
            return nullcontext()

    session = FakeSession()
    monkeypatch.setattr(nox_runner, "_enforce_line_coverage", lambda _path: 90.0)
    nox_test_lanes._finalize_parallel_coverage(session, tmp_path)

    coverage_commands = [
        (command, options)
        for command, options in session.commands
        if command[:4] == ("uv", "run", "--frozen", "coverage")
    ]
    assert [command[4] for command, _options in coverage_commands] == ["combine", "xml", "json", "report"]
    assert coverage_commands[0][0][5:] == ("--keep", str(tmp_path))
    assert coverage_commands[-1][0][-1:] == ("--format=total",)
    assert all(
        options["env"] == {"COVERAGE_FILE": str(tmp_path / ".coverage")} for _command, options in coverage_commands
    )


def test_policy_session_split_routes_base_revision_to_both_policy_layers() -> None:
    repo_args, requirement_args, skip_requirement = nox_runner._split_policy_session_args(
        ["--base-rev", "origin/dev", "--requirement-uid", "API-404"]
    )

    assert repo_args == ["--base-rev", "origin/dev"]
    assert requirement_args == ["--base-rev", "origin/dev", "--requirement-uid", "API-404"]
    assert skip_requirement is False


def _exercise_python_compatibility(
    monkeypatch: pytest.MonkeyPatch,
    *,
    build_artifacts: bool,
    smoke_only: bool = False,
    configured_wheelhouse: bool = False,
) -> tuple[
    list[tuple[str, ...]],
    list[tuple[str, ...]],
    list[nox_runner.StageResult],
    list[object],
]:
    commands: list[tuple[str, ...]] = []
    pytest_calls: list[tuple[str, ...]] = []
    logs: list[str] = []
    sync_calls: list[object] = []

    class FakeSession:
        def __init__(self) -> None:
            self.env: dict[str, str] = {}

        def log(self, message: str) -> None:
            logs.append(message)

    def fake_run(session: FakeSession, *command: str, **_kwargs: object) -> None:
        assert session.env["UV_PYTHON"] == "cpython-3.14"
        commands.append(command)
        if command[:2] != ("uv", "build"):
            return
        output_dir = Path(command[command.index("--out-dir") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        if build_artifacts:
            (output_dir / "raes-3.3.0-py3-none-any.whl").write_bytes(b"wheel")
            (output_dir / "raes-3.3.0.tar.gz").write_bytes(b"sdist")

    monkeypatch.setenv(nox_config.EXPECTED_PYTHON_ENV, "3.14")
    monkeypatch.setenv("UV_PYTHON", "cpython-3.14")
    monkeypatch.setenv(nox_config.EXPECT_FREE_THREADED_ENV, "0")
    monkeypatch.setenv(nox_config.PYTHON_COMPATIBILITY_SMOKE_ONLY_ENV, "1" if smoke_only else "0")
    monkeypatch.setenv(nox_config.PYTHON_CLOSURE_PROFILE_ENV, "public-linux-x86_64-cp314-all-extras")
    if configured_wheelhouse:
        monkeypatch.setenv(nox_config.PYTHON_CLOSURE_WHEELHOUSE_ENV, "/verified-wheelhouse")
    else:
        monkeypatch.delenv(nox_config.PYTHON_CLOSURE_WHEELHOUSE_ENV, raising=False)
    monkeypatch.setattr(nox_compatibility_lanes, "_run", fake_run)
    monkeypatch.setattr(nox_compatibility_lanes, "_sync_project", sync_calls.append)
    monkeypatch.setattr(
        nox_compatibility_lanes,
        "_run_pytest",
        lambda _session, *args, **_kwargs: pytest_calls.append(tuple(args)),
    )
    reporter = nox_runner.SessionReporter(FakeSession(), "python-compatibility")
    nox_compatibility_lanes._run_python_compatibility(reporter.session, reporter)
    return commands, pytest_calls, reporter.results, sync_calls


def test_python_compatibility_graph_builds_and_checks_clean_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands, pytest_calls, results, sync_calls = _exercise_python_compatibility(
        monkeypatch,
        build_artifacts=True,
    )
    stages = [result.name for result in results]

    assert stages == [
        "python compatibility / frozen sync",
        "python compatibility / exact runtime",
        "python compatibility / hermetic tests",
        "python compatibility / build distributions",
        "python compatibility / build wheel from sdist",
        "python compatibility / materialize dependency wheelhouse",
        "python compatibility / install direct wheel",
        "python compatibility / direct wheel metadata and imports",
        "python compatibility / direct wheel CLI version",
        "python compatibility / direct wheel CLI help",
        "python compatibility / install sdist-built wheel",
        "python compatibility / sdist-built wheel metadata and imports",
        "python compatibility / sdist-built wheel CLI version",
        "python compatibility / sdist-built wheel CLI help",
    ]
    assert len(sync_calls) == 1
    assert pytest_calls == [("-q",)]
    runtime_command = next(command for command in commands if command[:2] == ("uv", "run"))
    assert runtime_command[-2:] == ("3.14", "0")
    build_command = next(command for command in commands if command[:2] == ("uv", "build"))
    assert build_command[build_command.index("--python") :][:2] == ("--python", "cpython-3.14")
    assert "--build-constraints" in build_command
    assert "--require-hashes" in build_command
    installed_python = next(
        command
        for command in commands
        if command and "/installed-" in command[0] and command[0].endswith("/bin/python")
    )
    assert installed_python[-1] == "3.14"
    assert any(command and command[0].endswith("/bin/raes") and command[-1] == "--version" for command in commands)
    assert nox_config.PROJECT_ROOT.as_posix() in build_command
    install_command = next(command for command in commands if "tools.python_closure" in command and "smoke" in command)
    assert "--offline" in install_command
    assert "--wheelhouse" in install_command


def test_python_compatibility_smoke_omits_redundant_hermetic_suite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _commands, pytest_calls, results, _sync_calls = _exercise_python_compatibility(
        monkeypatch,
        build_artifacts=True,
        smoke_only=True,
    )
    stages = [result.name for result in results]

    assert "python compatibility / hermetic tests" not in stages
    assert "python compatibility / direct wheel metadata and imports" in stages
    assert pytest_calls == []


def test_offline_python_compatibility_reuses_only_a_verified_raw_wheelhouse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands, _pytest_calls, results, sync_calls = _exercise_python_compatibility(
        monkeypatch,
        build_artifacts=True,
        smoke_only=True,
        configured_wheelhouse=True,
    )
    stages = [result.name for result in results]

    assert "python compatibility / wheelhouse-verify dependency wheelhouse" in stages
    frozen_sync = next(result for result in results if result.name == "python compatibility / frozen sync")
    assert frozen_sync.status == "SKIP"
    assert sync_calls == []
    runtime_command = next(command for command in commands if command and command[0] == "cpython-3.14")
    assert runtime_command[-2:] == ("3.14", "0")
    assert all(command[:2] != ("uv", "run") for command in commands)
    closure_commands = [command for command in commands if "tools.python_closure" in command]
    assert any("wheelhouse-verify" in command for command in closure_commands)
    assert all("materialize" not in command for command in closure_commands)
    assert all("/verified-wheelhouse" in command for command in closure_commands)


def test_python_compatibility_rejects_restored_wheelhouse_outside_smoke_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(nox_config.PYTHON_CLOSURE_WHEELHOUSE_ENV, "/verified-wheelhouse")
    reporter = nox_runner.SessionReporter(types.SimpleNamespace(log=lambda _message: None), "python-compatibility")

    with pytest.raises(RuntimeError, match="valid only for compatibility smoke execution"):
        nox_compatibility_lanes._compatibility_runtime_stages(
            reporter.session,
            reporter,
            selector="cpython-3.14",
            expected="3.14",
            expect_free_threaded=False,
            smoke_only=False,
        )


def test_python_compatibility_distribution_requires_reviewed_closure_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(nox_config.PYTHON_CLOSURE_PROFILE_ENV, raising=False)
    reporter = nox_runner.SessionReporter(types.SimpleNamespace(log=lambda _message: None), "python-compatibility")

    with pytest.raises(RuntimeError, match="must select a reviewed closure profile"):
        nox_compatibility_lanes._compatibility_distribution_stages(
            reporter.session,
            reporter,
            selector="cpython-3.14",
            expected="3.14",
        )


@pytest.mark.parametrize(
    ("expected", "selector", "message"),
    [
        ("3.15", "cpython-3.15", "must select a supported feature release"),
        ("3.14", "", "UV_PYTHON must select the interpreter under test"),
    ],
)
def test_python_compatibility_rejects_unsupported_or_missing_interpreter_selection(
    monkeypatch: pytest.MonkeyPatch,
    expected: str,
    selector: str,
    message: str,
) -> None:
    monkeypatch.setenv(nox_config.EXPECTED_PYTHON_ENV, expected)
    monkeypatch.setenv("UV_PYTHON", selector)
    reporter = nox_runner.SessionReporter(types.SimpleNamespace(log=lambda _message: None), "python-compatibility")

    with pytest.raises(RuntimeError, match=message):
        nox_compatibility_lanes._run_python_compatibility(reporter.session, reporter)


def test_python_compatibility_rejects_profile_for_another_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(nox_config.EXPECTED_PYTHON_ENV, "3.14")
    monkeypatch.setenv("UV_PYTHON", "cpython-3.14")
    monkeypatch.setenv(nox_config.EXPECT_FREE_THREADED_ENV, "0")
    monkeypatch.setenv(nox_config.PYTHON_CLOSURE_PROFILE_ENV, "public-linux-x86_64-cp313-all-extras")
    reporter = nox_runner.SessionReporter(types.SimpleNamespace(log=lambda _message: None), "python-compatibility")

    with pytest.raises(RuntimeError, match="must match the selected interpreter"):
        nox_compatibility_lanes._run_python_compatibility(reporter.session, reporter)


def test_python_compatibility_rejects_incomplete_distribution_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="must produce exactly one wheel and one source distribution"):
        _exercise_python_compatibility(monkeypatch, build_artifacts=False)


def test_python_compatibility_and_osv_session_wrappers_always_summarize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    logs: list[str] = []
    session = types.SimpleNamespace(log=logs.append, posargs=[])
    monkeypatch.setattr(
        nox_compatibility_lanes,
        "_run_python_compatibility",
        lambda _session, _reporter: calls.append("python"),
    )
    monkeypatch.setattr(
        nox_test_lanes,
        "_run_osv_scan",
        lambda _session, _reporter, **_kwargs: calls.append("osv"),
    )
    noxfile = load_noxfile_with_fake_nox(monkeypatch)

    noxfile.python_compatibility(session)
    noxfile.osv_scan(session)

    assert calls == ["python", "osv"]
    assert any("[python-compatibility] stage summary" in message for message in logs)
    assert any("[osv_scan] stage summary" in message for message in logs)


def test_coverage_configuration_measures_branches_and_repository_python() -> None:
    config = tomllib.loads((REPO_ROOT / "implementations" / "python" / "pyproject.toml").read_text(encoding="utf-8"))
    run = config["tool"]["coverage"]["run"]
    report = config["tool"]["coverage"]["report"]

    assert run["branch"] is True
    assert run["source"] == ["../.."]
    assert set(run["omit"]) == {
        "*/.cache/*",
        "*/docs/*",
        "*/implementations/python/.venv/*",
        "*/implementations/tooling/python/.venv/*",
        "*/implementations/python/tests/*",
    }
    assert report["include_namespace_packages"] is True


def test_line_coverage_threshold_is_fixed_at_ninety_percent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "coverage.json"
    report_path.write_text(
        json.dumps({"totals": {"covered_lines": 90, "num_statements": 100}}),
        encoding="utf-8",
    )

    assert nox_runner._enforce_line_coverage(report_path) == 90.0

    report_path.write_text(
        json.dumps({"totals": {"covered_lines": 899, "num_statements": 1000}}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="89.900% is below required 90.000%"):
        nox_runner._enforce_line_coverage(report_path)


def test_make_policy_skips_only_requirement_governance_without_a_uid() -> None:
    environment = os.environ.copy()
    environment.pop("RAES_REQUIREMENT_UID", None)
    requirement_free = subprocess.run(
        ("make", "--dry-run", "policy"),
        cwd=REPO_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    environment["RAES_REQUIREMENT_UID"] = "ASR-505"
    requirement_scoped = subprocess.run(
        ("make", "--dry-run", "policy"),
        cwd=REPO_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert requirement_free.rstrip().endswith("-- --skip-requirement")
    assert "--skip-requirement" not in requirement_scoped


def test_hook_policy_context_skips_only_requirement_free_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAES_REQUIREMENT_UID", raising=False)
    monkeypatch.setattr(nox_runner, "_git_lines", lambda *_args: ["1104-minimal-coverage-policy"])
    assert nox_runner._requirement_aware_policy_args("--staged") == ["--staged", "--skip-requirement"]

    monkeypatch.setattr(nox_runner, "_git_lines", lambda *_args: ["1104-ASR-505-coverage-policy"])
    assert nox_runner._requirement_aware_policy_args("--staged") == ["--staged"]

    monkeypatch.setenv("RAES_REQUIREMENT_UID", "ASR-505")
    monkeypatch.setattr(nox_runner, "_git_lines", lambda *_args: ["1104-minimal-coverage-policy"])
    assert nox_runner._requirement_aware_policy_args("--staged") == ["--staged"]


def test_docs_graph_uses_curated_root_and_reader_style_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[tuple[str, ...]] = []

    class FakeSession:
        def log(self, _message: str) -> None:
            pass

        def run(self, *args: str, **_kwargs: Any) -> None:
            commands.append(args)

    fake_vale = tmp_path / "vale"
    fake_vale.write_text("", encoding="utf-8")
    monkeypatch.setattr(nox_test_lanes, "ensure_vale", lambda _repo_root: fake_vale)
    monkeypatch.setattr(nox_test_lanes, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(nox_test_lanes, "PROJECT_ROOT", tmp_path / "implementations" / "python")
    public_root = tmp_path / "docs" / "public"
    monkeypatch.setattr(nox_test_lanes, "PUBLIC_DOCS_ROOT", public_root)
    monkeypatch.setattr(nox_test_lanes, "DOCS_BUILD_ROOT", tmp_path / "docs" / "_build")
    reporter = nox_runner.SessionReporter(FakeSession(), "docs")

    nox_test_lanes._run_docs(reporter.session, reporter)

    assert [result.name for result in reporter.results] == [
        "docs / public source boundary",
        "docs / Vale reader style",
        "docs / executable quickstart",
        "docs / Sphinx HTML",
        "docs / public output inventory",
        "docs / Sphinx link check",
    ]
    sphinx_commands = [command for command in commands if "sphinx-build" in command]
    assert len(sphinx_commands) == 2
    assert all(str(public_root) in command for command in sphinx_commands)
    assert all("-W" in command and "--keep-going" in command for command in sphinx_commands)
    vale_command = next(command for command in commands if command and command[0] == str(fake_vale))
    assert "--config=.vale.ini" in vale_command
    assert "README.md" in vale_command
    assert str(public_root) in vale_command
    pytest_command = next(command for command in commands if "pytest" in command)
    assert (
        "implementations/python/tests/test_public_docs_policy.py::test_checked_in_quickstart_scenario_parses"
        in pytest_command
    )
    assert (
        "implementations/python/tests/test_public_docs_policy.py::test_readme_quickstart_matches_checked_in_scenario"
        in pytest_command
    )


def test_local_docs_graph_excludes_external_link_check(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[tuple[str, ...]] = []

    class FakeSession:
        def log(self, _message: str) -> None:
            pass

        def run(self, *args: str, **_kwargs: Any) -> None:
            commands.append(args)

    fake_vale = tmp_path / "vale"
    fake_vale.write_text("", encoding="utf-8")
    monkeypatch.setattr(nox_test_lanes, "ensure_vale", lambda _repo_root: fake_vale)
    monkeypatch.setattr(nox_test_lanes, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(nox_test_lanes, "PROJECT_ROOT", tmp_path / "implementations" / "python")
    monkeypatch.setattr(nox_test_lanes, "PUBLIC_DOCS_ROOT", tmp_path / "docs" / "public")
    monkeypatch.setattr(nox_test_lanes, "DOCS_BUILD_ROOT", tmp_path / "docs" / "_build")
    reporter = nox_runner.SessionReporter(FakeSession(), "docs-local")

    nox_test_lanes._run_docs(reporter.session, reporter, include_external_links=False)

    assert "docs / Sphinx link check" not in [result.name for result in reporter.results]
    sphinx_commands = [command for command in commands if "sphinx-build" in command]
    assert len(sphinx_commands) == 1
    assert "html" in sphinx_commands[0]


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def setup_policy_repo(tmp_path: Path) -> Path:
    policy_dir = tmp_path / "tools" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO_ROOT / "tools" / "policy" / "adr_policy.yaml", policy_dir / "adr_policy.yaml")
    # The ADR-015 size-cap gate reads tools/policy/oversized_allowlist.yaml;
    # seed an empty allowlist by default so tests that don't exercise the
    # allowlist don't trip the missing-config failure. Tests that target
    # allowlist behavior overwrite this file.
    write_text(policy_dir / "oversized_allowlist.yaml", "files: []\n")

    adr_dir = tmp_path / "docs" / "decisions" / "adrs"
    adr_dir.mkdir(parents=True, exist_ok=True)
    write_text(
        adr_dir / "adr-001-example.md",
        "# ADR-001: Example ADR\n\n## Status\nAccepted\n\n## Date\n2026-04-05\n",
    )
    write_text(
        adr_dir / "README.md",
        "| Number | Title | Status | Date |\n"
        "| --- | --- | --- | --- |\n"
        "| [001](adr-001-example.md) | Example ADR | Accepted | 2026-04-05 |\n",
    )
    write_text(
        adr_dir / "TEMPLATE.md",
        "# ADR-NNN: Title\n\n"
        "## Status\n\n"
        "proposed\n\n"
        "## Date\n\n"
        "YYYY-MM-DD\n\n"
        "## Context\n\n"
        "What problem or situation is driving this decision?\n\n"
        "## Decision\n\n"
        "What did we choose, and why?\n\n"
        "## Alternatives Considered\n\n"
        "Which credible options were rejected, and why?\n\n"
        "## Consequences\n\n"
        "What are the positive, negative, and risk trade-offs?\n",
    )
    for package in (
        "raes",
        "raes_processor",
        "raes_runtime",
        "raes_backend_protocols",
        "raes_backend_stubs",
        "raes_backend_libvirt",
        "raes_operations",
        "raes_reference_backend",
        "raes_conformance",
        "raes_cli",
        "raes_mcp",
        "raes_contracts",
    ):
        write_text(
            tmp_path / "implementations" / "python" / "packages" / package / "__init__.py",
            "",
        )
    return tmp_path


def structural_runner_stub(_: dict) -> list[PolicyFailure]:
    return []


def _load_test_policy(repo_root: Path) -> dict[str, Any]:
    with (repo_root / "tools" / "policy" / "adr_policy.yaml").open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    assert isinstance(data, dict)
    return data


def _write_test_policy(repo_root: Path, policy: dict[str, Any]) -> None:
    (repo_root / "tools" / "policy" / "adr_policy.yaml").write_text(
        yaml.safe_dump(policy, sort_keys=False),
        encoding="utf-8",
    )


def test_hygiene_parser_ignores_policy_only_verify_args(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_changed_paths(*, staged: bool = False, base_rev: str | None = None) -> list[str]:
        calls.append({"staged": staged, "base_rev": base_rev})
        return ["noxfile.py"]

    monkeypatch.setattr(nox_runner, "_changed_paths", fake_changed_paths)

    skip_selection = nox_runner._parse_hygiene_posargs(
        ["--base-rev", "origin/dev", "--skip-requirement"],
        default_all_files=False,
    )
    uid_selection = nox_runner._parse_hygiene_posargs(
        ["--base-rev", "origin/dev", "--requirement-uid", "GOV-918"],
        default_all_files=False,
    )

    assert skip_selection.paths == ["noxfile.py"]
    assert skip_selection.source == "changes since origin/dev"
    assert uid_selection.paths == ["noxfile.py"]
    assert uid_selection.source == "changes since origin/dev"
    assert calls == [
        {"staged": False, "base_rev": "origin/dev"},
        {"staged": False, "base_rev": "origin/dev"},
    ]


@pytest.mark.parametrize("option", ["--base-rev", "--requirement-uid"])
@pytest.mark.parametrize("trailing", [[], [""], ["--skip-requirement"]])
def test_policy_arg_parsers_reject_missing_option_values(
    monkeypatch: pytest.MonkeyPatch,
    option: str,
    trailing: list[str],
) -> None:
    args = [option, *trailing]

    with pytest.raises(ValueError, match=rf"^{option} requires a value$"):
        nox_runner._split_policy_session_args(args)
    with pytest.raises(ValueError, match=rf"^{option} requires a value$"):
        nox_runner._parse_hygiene_posargs(args, default_all_files=False)


def test_structural_policy_runner_receives_policy_input(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    captured: dict = {}

    def runner(input_document: dict) -> list[PolicyFailure]:
        captured.update(input_document)
        return [PolicyFailure("structural-check", "blocked", "contracts/schemas/backend-manifest/schema.json")]

    failures = evaluate_repo_policy(
        repo_root,
        ["contracts/schemas/backend-manifest/schema.json"],
        structural_runner=runner,
    )

    assert captured["changed"] == ["contracts/schemas/backend-manifest/schema.json"]
    assert captured["check_set"] == "full"
    assert "generated_contracts" in captured["policy"]
    assert [failure.rule_id for failure in failures] == ["structural-check"]


@pytest.mark.integration
def test_default_structural_policy_runner_executes_rego(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = setup_policy_repo(tmp_path)
    binary = conftest_tool.conftest_binary_path(REPO_ROOT)
    assert binary.is_file()
    monkeypatch.setattr(conftest_tool, "ensure_conftest", lambda *_args, **_kwargs: binary)

    failures = evaluate_repo_policy(
        repo_root,
        ["schemas/legacy-contract.json"],
        check_set="file-local",
        structural_runner=None,
    )

    assert [failure.rule_id for failure in failures] == ["legacy-top-level-root"]


def test_conftest_policy_runner_parses_and_sorts_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(conftest_tool, "ensure_conftest", lambda *_args, **_kwargs: tmp_path / "conftest")
    payload = [
        {
            "failures": [
                {"msg": "second", "metadata": {"rule_id": "rule-b", "path": "z.py"}},
                {"msg": "first", "metadata": {"rule_id": "rule-a", "path": "a.py"}},
            ]
        }
    ]
    monkeypatch.setattr(
        conftest_tool.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout=json.dumps(payload),
            stderr="",
        ),
    )

    failures = run_conftest_policy({}, repo_root=tmp_path, policy_dir=tmp_path / "policy")

    assert [(failure.path, failure.rule_id, failure.message) for failure in failures] == [
        ("a.py", "rule-a", "first"),
        ("z.py", "rule-b", "second"),
    ]


def test_adr_readme_must_match_adr_documents(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    write_text(
        repo_root / "docs" / "decisions" / "adrs" / "README.md",
        "| Number | Title | Status | Date |\n"
        "| --- | --- | --- | --- |\n"
        "| [001](adr-001-example.md) | Wrong Title | Accepted | 2026-04-05 |\n",
    )

    failures = evaluate_repo_policy(
        repo_root,
        ["docs/decisions/adrs/adr-001-example.md"],
        structural_runner=structural_runner_stub,
    )

    assert [failure.rule_id for failure in failures] == ["adr-index-sync"]


def test_adr_index_accepts_legacy_inline_status_and_date_fields(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    write_text(
        repo_root / "docs" / "decisions" / "adrs" / "adr-001-example.md",
        "# ADR-001: Example ADR\n\n**Status:** Accepted\n**Date:** 2026-04-05\n",
    )

    failures = evaluate_repo_policy(
        repo_root,
        ["docs/decisions/adrs/adr-001-example.md"],
        structural_runner=structural_runner_stub,
    )

    assert failures == []


def test_adr_template_requires_alternatives_considered(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    write_text(
        repo_root / "docs" / "decisions" / "adrs" / "TEMPLATE.md",
        "# ADR-NNN: Title\n\n"
        "## Status\n\n"
        "proposed\n\n"
        "## Date\n\n"
        "YYYY-MM-DD\n\n"
        "## Context\n\n"
        "Context.\n\n"
        "## Decision\n\n"
        "Decision.\n\n"
        "## Consequences\n\n"
        "Consequences.\n",
    )

    failures = evaluate_repo_policy(
        repo_root,
        ["docs/decisions/adrs/TEMPLATE.md"],
        structural_runner=structural_runner_stub,
    )

    assert [failure.rule_id for failure in failures] == ["adr-template-section-missing"]


# ── ADR-015: SDL→processor layering rule ────────────────────────────────


def _raes_file(repo_root: Path, name: str, content: str) -> str:
    """Write a synthetic file under raes/ and return its repo-relative path."""
    rel = f"implementations/python/packages/raes/{name}"
    write_text(repo_root / rel, content)
    return rel


@pytest.mark.parametrize(
    "import_line",
    [
        "import raes_processor",
        "import raes_processor.compiler",
        "from raes_processor import compiler",
        "from raes_processor.compiler import compile_runtime_model",
    ],
)
def test_layering_rule_rejects_raes_processor_imports(tmp_path: Path, import_line: str) -> None:
    repo_root = setup_policy_repo(tmp_path)
    rel = _raes_file(repo_root, "_uses_processor.py", import_line + "\n")

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert "layering-rule-violation" in [f.rule_id for f in failures], (
        f"import line {import_line!r} should fire layering-rule-violation; got {[f.rule_id for f in failures]}"
    )


def test_layering_rule_does_not_match_prefix_only_package(tmp_path: Path) -> None:
    """A package merely starting with `raes_processor` (e.g. a
    hypothetical `raes_processor_extra`) is not the forbidden package."""
    repo_root = setup_policy_repo(tmp_path)
    rel = _raes_file(repo_root, "_uses_other.py", "from raes_processor_extra import thing\n")

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert failures == []


def test_layering_rule_allows_raes_importing_other_packages(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    rel = _raes_file(
        repo_root,
        "_normal.py",
        "from raes_contracts.contracts import Scenario\nfrom raes.semantics.objectives import analyze_objective_window\n",
    )

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert failures == []


def test_layering_rule_does_not_check_files_outside_scope(tmp_path: Path) -> None:
    """An `import raes_processor` inside raes_processor itself (or any
    package other than raes) is not a layering violation."""
    repo_root = setup_policy_repo(tmp_path)
    rel = "implementations/python/packages/raes_processor/internal.py"
    write_text(repo_root / rel, "import raes_processor.models\n")

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert failures == []


# ── ADR-036: module ownership boundaries ────────────────────────────────


def install_module_boundary_policy(repo_root: Path) -> None:
    del repo_root


def test_module_boundaries_reject_processor_importing_runtime(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    install_module_boundary_policy(repo_root)
    rel = "implementations/python/packages/raes_processor/uses_runtime.py"
    write_text(repo_root / rel, "from raes_runtime.manager import RuntimeManager\n")

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert [f.rule_id for f in failures] == ["module-boundary-import"]


def test_module_boundaries_reject_runtime_importing_processor_private_modules(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    install_module_boundary_policy(repo_root)
    rel = "implementations/python/packages/raes_runtime/uses_private_processor.py"
    write_text(repo_root / rel, "from raes_processor._private import helper\n")

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert [f.rule_id for f in failures] == ["module-boundary-private-import"]


def test_module_boundaries_allow_runtime_using_processor_public_api(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    install_module_boundary_policy(repo_root)
    rel = "implementations/python/packages/raes_runtime/uses_processor.py"
    write_text(
        repo_root / rel,
        "from raes_processor.compiler import compile_runtime_model\n"
        "from raes_processor.models import RuntimeSnapshot\n"
        "from raes_processor.planner import plan\n",
    )

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert failures == []


def test_module_boundaries_allow_cli_using_processor_compiler_public_api(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    install_module_boundary_policy(repo_root)
    rel = "implementations/python/packages/raes_cli/semantic.py"
    write_text(repo_root / rel, "from raes_processor.compiler import compile_scenario_runtime_model\n")

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert failures == []


def test_module_boundaries_reject_runtime_using_non_public_processor_module(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    install_module_boundary_policy(repo_root)
    rel = "implementations/python/packages/raes_runtime/uses_processor_semantics.py"
    write_text(repo_root / rel, "from raes_processor.semantics.planner import reverse_delete_order\n")

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert [f.rule_id for f in failures] == ["module-boundary-public-api"]


def test_module_boundaries_reject_sdl_importing_runtime(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    install_module_boundary_policy(repo_root)
    rel = "implementations/python/packages/raes/uses_runtime.py"
    write_text(repo_root / rel, "import raes_runtime\n")

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert [f.rule_id for f in failures] == ["module-boundary-import"]


def test_module_boundaries_reject_authoring_importing_runtime_internals(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    install_module_boundary_policy(repo_root)
    rel = "implementations/python/packages/raes_mcp/tools/authoring_runtime.py"
    write_text(repo_root / rel, "from raes_runtime.control_plane import RuntimeControlPlane\n")

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert [f.rule_id for f in failures] == ["module-boundary-import"]


def test_module_boundaries_reject_backend_stub_importing_processor(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    rel = "implementations/python/packages/raes_backend_stubs/uses_processor.py"
    write_text(repo_root / rel, "from raes_processor.models import ApplyResult\n")

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert [f.rule_id for f in failures] == ["module-boundary-import"]


def test_module_boundaries_reject_backend_protocol_any_signatures(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    rel = "implementations/python/packages/raes_backend_protocols/protocols.py"
    write_text(
        repo_root / rel,
        "from typing import Any, Protocol\n\n"
        "class Provisioner(Protocol):\n"
        "    def apply(self, plan: Any) -> Any: ...\n",
    )

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert [f.rule_id for f in failures] == ["backend-protocol-untyped-contract"]


def test_module_boundaries_reject_backend_protocol_any_signatures_outside_protocols_module(
    tmp_path: Path,
) -> None:
    # ADR-036 requires the Any-signature ban package-wide, not only in protocols.py.
    repo_root = setup_policy_repo(tmp_path)
    rel = "implementations/python/packages/raes_backend_protocols/participant_reset.py"
    write_text(
        repo_root / rel,
        "from typing import Any, Protocol\n\n"
        "class ParticipantReset(Protocol):\n"
        "    def reset(self, request: Any) -> Any: ...\n",
    )

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert [f.rule_id for f in failures] == ["backend-protocol-untyped-contract"]


def test_module_boundaries_allow_typed_backend_protocol_outside_protocols_module(
    tmp_path: Path,
) -> None:
    repo_root = setup_policy_repo(tmp_path)
    rel = "implementations/python/packages/raes_backend_protocols/participant_reset.py"
    write_text(
        repo_root / rel,
        "from typing import Protocol\n\n"
        "class ParticipantReset(Protocol):\n"
        "    def reset(self, request: str) -> bool: ...\n",
    )

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert failures == []


def test_module_boundaries_allow_structural_backend_protocol_attributes_outside_protocols_module(
    tmp_path: Path,
) -> None:
    # Non-method structural protocol attributes are not signatures and must not be flagged.
    repo_root = setup_policy_repo(tmp_path)
    rel = "implementations/python/packages/raes_backend_protocols/participant_resource_admission.py"
    write_text(
        repo_root / rel,
        "from typing import Any, Protocol\n\nclass ParticipantResourceAdmission(Protocol):\n    limit: Any\n",
    )

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert failures == []


def test_module_boundaries_config_is_required(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    policy = _load_test_policy(repo_root)
    policy.pop("module_boundaries")
    _write_test_policy(repo_root, policy)

    failures = evaluate_repo_policy(
        repo_root,
        ["tools/policy/adr_policy.yaml"],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert [f.rule_id for f in failures] == ["policy-config-malformed"]
    assert "module_boundaries block is required" in failures[0].message


def test_module_boundaries_config_is_required_even_without_changed_paths(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    policy = _load_test_policy(repo_root)
    policy.pop("module_boundaries")
    _write_test_policy(repo_root, policy)

    failures = evaluate_repo_policy(
        repo_root,
        [],
        check_set="full",
        structural_runner=structural_runner_stub,
    )

    assert [f.rule_id for f in failures] == ["policy-config-malformed"]
    assert "module_boundaries block is required" in failures[0].message


def test_module_boundaries_reject_missing_module_root(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    policy = _load_test_policy(repo_root)
    policy["module_boundaries"]["modules"][0]["root"] = "implementations/python/packages/raes_typo"
    _write_test_policy(repo_root, policy)

    failures = evaluate_repo_policy(
        repo_root,
        ["tools/policy/adr_policy.yaml"],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert [f.rule_id for f in failures] == ["policy-config-malformed"]
    assert "must resolve to an existing directory" in failures[0].message


def test_module_boundaries_reject_uncovered_package_root(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    write_text(repo_root / "implementations/python/packages/raes_new_package/__init__.py", "")

    failures = evaluate_repo_policy(
        repo_root,
        ["tools/policy/adr_policy.yaml"],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert [f.rule_id for f in failures] == ["policy-config-malformed"]
    assert "raes_new_package" in failures[0].message
    assert "missing from module_boundaries.modules" in failures[0].message


def test_module_boundaries_full_check_scans_all_module_sources(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    rel = "implementations/python/packages/raes_processor/latent_runtime_import.py"
    write_text(repo_root / rel, "from raes_runtime.manager import RuntimeManager\n")

    failures = evaluate_repo_policy(
        repo_root,
        ["tools/policy/adr_policy.yaml"],
        check_set="full",
        structural_runner=structural_runner_stub,
    )

    assert [f.rule_id for f in failures] == ["module-boundary-import"]
    assert failures[0].path == rel


def test_module_boundaries_reject_runtime_importing_sdl_semantics(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    rel = "implementations/python/packages/raes_runtime/uses_sdl_workflow_semantics.py"
    write_text(repo_root / rel, "from raes.semantics.workflow import validate_workflow_step_result\n")

    failures = evaluate_repo_policy(
        repo_root,
        [rel],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert [f.rule_id for f in failures] == ["module-boundary-import"]


# ── ADR-015: 500-line source-file cap ───────────────────────────────────

# A path that is in _ADR015_INITIAL_OVERSIZED_FILES (the code constant in
# tools/policy/repo_policy.py), so the allowlist-subset (drain) check passes
# when we put it in the allowlist.
_LOCKED_PATH = "implementations/python/packages/raes_processor/models.py"


def test_oversized_source_file_over_cap_is_rejected(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    rel = "implementations/python/packages/raes_processor/big_new_file.py"
    write_text(repo_root / rel, "x = 1\n" * 700)

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert [f.rule_id for f in failures] == ["oversized-source-file"]


def test_oversized_source_file_in_allowlist_passes(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    write_text(repo_root / "tools" / "policy" / "oversized_allowlist.yaml", f"files:\n  - {_LOCKED_PATH}\n")
    write_text(repo_root / _LOCKED_PATH, "x = 1\n" * 700)

    failures = evaluate_repo_policy(
        repo_root, [_LOCKED_PATH], check_set="file-local", structural_runner=structural_runner_stub
    )

    assert failures == []


def test_oversized_source_file_under_cap_passes(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    rel = "implementations/python/packages/raes_processor/small.py"
    write_text(repo_root / rel, "x = 1\n" * 100)

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert failures == []


def test_oversized_cap_excludes_test_files(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    rel = "implementations/python/tests/test_huge.py"
    write_text(repo_root / rel, "x = 1\n" * 700)

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert failures == []


def test_oversized_cap_only_checks_python_files(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    rel = "implementations/python/packages/raes_processor/data.txt"
    write_text(repo_root / rel, "line\n" * 700)

    failures = evaluate_repo_policy(repo_root, [rel], check_set="file-local", structural_runner=structural_runner_stub)

    assert failures == []


# ── ADR-015: allowlist drain (must be a subset of the code constant) ────


def test_allowlist_entry_not_in_locked_set_is_rejected(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    bogus = "implementations/python/packages/raes_processor/not_a_locked_file.py"
    write_text(repo_root / "tools" / "policy" / "oversized_allowlist.yaml", f"files:\n  - {bogus}\n")

    failures = evaluate_repo_policy(
        repo_root,
        ["tools/policy/oversized_allowlist.yaml"],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert [f.rule_id for f in failures] == ["oversized-allowlist-locked"]


def test_allowlist_subset_of_locked_set_passes(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    # A strict subset of the initial oversized entries — the drained state.
    write_text(repo_root / "tools" / "policy" / "oversized_allowlist.yaml", f"files:\n  - {_LOCKED_PATH}\n")
    write_text(repo_root / _LOCKED_PATH, "x = 1\n" * 700)

    failures = evaluate_repo_policy(
        repo_root,
        ["tools/policy/oversized_allowlist.yaml"],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert failures == []


def test_growing_locked_set_via_config_does_not_relax_drain_check(tmp_path: Path) -> None:
    """The drain check diffs against the *code* constant, not config. Adding
    a new oversized file to the allowlist (and even re-introducing a
    `locked_initial_files` block in adr_policy.yaml) must not make it pass —
    the locked reference set is not config the same PR can edit."""
    repo_root = setup_policy_repo(tmp_path)
    sneaky = "implementations/python/packages/raes_processor/sneaky_new_big_file.py"
    write_text(repo_root / "tools" / "policy" / "oversized_allowlist.yaml", f"files:\n  - {sneaky}\n")
    write_text(repo_root / sneaky, "x = 1\n" * 700)
    # Re-add a config-level locked_initial_files block listing the sneaky file.
    config = (repo_root / "tools" / "policy" / "adr_policy.yaml").read_text()
    config += f"  locked_initial_files:\n    - {sneaky}\n"
    write_text(repo_root / "tools" / "policy" / "adr_policy.yaml", config)

    failures = evaluate_repo_policy(
        repo_root,
        ["tools/policy/oversized_allowlist.yaml", sneaky],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert "oversized-allowlist-locked" in [f.rule_id for f in failures], [f.message for f in failures]


def test_unsafe_locked_allowlist_entry_is_rejected(tmp_path: Path) -> None:
    """An allowlisted (and locked) path that has been replaced by a symlink
    pointing out of the tree is reported as policy-path-unsafe rather than
    silently accepted as still-over-cap debt."""
    repo_root = setup_policy_repo(tmp_path)
    write_text(repo_root / "tools" / "policy" / "oversized_allowlist.yaml", f"files:\n  - {_LOCKED_PATH}\n")
    outside = tmp_path.parent / "outside_big.py"
    write_text(outside, "x = 1\n" * 700)
    target = repo_root / _LOCKED_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(outside)

    failures = evaluate_repo_policy(
        repo_root,
        ["docs/decisions/adrs/adr-001-example.md"],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert "policy-path-unsafe" in [f.rule_id for f in failures], [f.message for f in failures]


# ── ADR-015: schema validation (malformed config → structured failure) ──


@pytest.mark.parametrize(
    ("mutation", "marker"),
    [
        ('oversized_source_files:\n  line_cap: "nope"\n', "line_cap"),
        ("oversized_source_files: notamapping\n", "must be a mapping"),
        ("layering_rules: notalist\n", "layering_rules must be a list"),
        ("layering_rules:\n  - {}\n", "layering_rules[0].id"),
    ],
)
def test_malformed_policy_config_produces_structured_failure(tmp_path: Path, mutation: str, marker: str) -> None:
    repo_root = setup_policy_repo(tmp_path)
    # Replace the whole adr_policy.yaml with a minimal-but-malformed config.
    # Keep the keys other parts of the policy need (adr_index, source_roots,
    # generated_contracts, concept_authority) by
    # appending the mutation onto the real config.
    base = (REPO_ROOT / "tools" / "policy" / "adr_policy.yaml").read_text()
    # Drop the real layering_rules / oversized_source_files blocks so the
    # mutation is what gets validated. Cheap approach: only the mutation
    # blocks matter; strip from the first occurrence of "layering_rules:".
    cut = base.split("\nlayering_rules:", 1)[0]
    write_text(repo_root / "tools" / "policy" / "adr_policy.yaml", cut + "\n" + mutation)

    failures = evaluate_repo_policy(
        repo_root,
        ["tools/policy/adr_policy.yaml"],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    rule_ids = [f.rule_id for f in failures]
    assert "policy-config-malformed" in rule_ids, f"expected policy-config-malformed, got {rule_ids}"
    assert any(marker in f.message for f in failures if f.rule_id == "policy-config-malformed"), (
        f"expected a failure mentioning {marker!r}; got {[f.message for f in failures]}"
    )


def test_missing_allowlist_file_produces_structured_failure(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    (repo_root / "tools" / "policy" / "oversized_allowlist.yaml").unlink()

    failures = evaluate_repo_policy(
        repo_root,
        ["docs/decisions/adrs/adr-001-example.md"],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    rule_ids = [f.rule_id for f in failures]
    assert "policy-config-malformed" in rule_ids, f"expected policy-config-malformed, got {rule_ids}"


# ── ADR-015: stale allowlist entry (file no longer over the cap) ─────────


def test_stale_allowlist_entry_below_cap_is_rejected(tmp_path: Path) -> None:
    """An allowlist entry that was split (so the file is now small) but
    whose entry the split PR forgot to drain is flagged on the next run,
    even though the file's deletion/shrink isn't in the changed set."""
    repo_root = setup_policy_repo(tmp_path)
    write_text(repo_root / "tools" / "policy" / "oversized_allowlist.yaml", f"files:\n  - {_LOCKED_PATH}\n")
    write_text(repo_root / _LOCKED_PATH, "x = 1\n" * 100)  # well under the 500-line cap

    failures = evaluate_repo_policy(
        repo_root,
        ["docs/decisions/adrs/adr-001-example.md"],  # unrelated change
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert [f.rule_id for f in failures] == ["oversized-allowlist-stale-entry"]
    assert "100 lines" in failures[0].message


def test_stale_allowlist_entry_missing_file_is_rejected(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    write_text(repo_root / "tools" / "policy" / "oversized_allowlist.yaml", f"files:\n  - {_LOCKED_PATH}\n")
    # _LOCKED_PATH file is never created.

    failures = evaluate_repo_policy(
        repo_root,
        ["docs/decisions/adrs/adr-001-example.md"],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert [f.rule_id for f in failures] == ["oversized-allowlist-stale-entry"]
    assert "no regular file exists" in failures[0].message


def test_allowlist_entry_still_over_cap_passes(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    write_text(repo_root / "tools" / "policy" / "oversized_allowlist.yaml", f"files:\n  - {_LOCKED_PATH}\n")
    write_text(repo_root / _LOCKED_PATH, "x = 1\n" * 700)  # still over the cap → legitimate debt

    failures = evaluate_repo_policy(
        repo_root,
        ["docs/decisions/adrs/adr-001-example.md"],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert failures == []


# ── ADR-015: required blocks + unsafe paths ─────────────────────────────


def _write_policy_without_adr015_blocks(repo_root: Path, *, extra: str = "") -> None:
    """Rewrite adr_policy.yaml dropping the layering_rules and
    oversized_source_files blocks, optionally appending `extra`."""
    base = (REPO_ROOT / "tools" / "policy" / "adr_policy.yaml").read_text()
    cut = base.split("\nlayering_rules:", 1)[0]
    write_text(repo_root / "tools" / "policy" / "adr_policy.yaml", cut + "\n" + extra)


def test_absent_layering_rules_block_is_malformed(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    # Re-add a valid oversized_source_files block so only layering_rules is absent.
    real = (REPO_ROOT / "tools" / "policy" / "adr_policy.yaml").read_text()
    oversized_block = "oversized_source_files:" + real.split("\noversized_source_files:", 1)[1]
    _write_policy_without_adr015_blocks(repo_root, extra=oversized_block)

    failures = evaluate_repo_policy(
        repo_root,
        ["tools/policy/adr_policy.yaml"],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert any(
        f.rule_id == "policy-config-malformed" and "layering_rules is required" in f.message for f in failures
    ), [f.message for f in failures]


def test_absent_oversized_block_is_malformed(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    # Re-add a valid layering_rules block so only oversized_source_files is absent.
    real = (REPO_ROOT / "tools" / "policy" / "adr_policy.yaml").read_text()
    layering_block = "layering_rules:" + real.split("\nlayering_rules:", 1)[1].split("\noversized_source_files:", 1)[0]
    _write_policy_without_adr015_blocks(repo_root, extra=layering_block)

    failures = evaluate_repo_policy(
        repo_root,
        ["tools/policy/adr_policy.yaml"],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert any(
        f.rule_id == "policy-config-malformed" and "oversized_source_files block is required" in f.message
        for f in failures
    ), [f.message for f in failures]


@pytest.mark.parametrize(
    "bad_content",
    [
        "[unclosed flow sequence\n",  # parse error (never-closed flow sequence)
        "- just\n- a\n- list\n",  # parses, but root is a list not a mapping
        "42\n",  # parses to a scalar
    ],
)
def test_unparseable_or_non_mapping_adr_policy_is_malformed(tmp_path: Path, bad_content: str) -> None:
    repo_root = setup_policy_repo(tmp_path)
    write_text(repo_root / "tools" / "policy" / "adr_policy.yaml", bad_content)

    failures = evaluate_repo_policy(
        repo_root,
        ["docs/decisions/adrs/adr-001-example.md"],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert [f.rule_id for f in failures] == ["policy-config-malformed"], [f.message for f in failures]


@pytest.mark.parametrize("bad_path", ["/etc/passwd", "../../../etc/passwd"])
def test_unsafe_allowlist_path_is_rejected(tmp_path: Path, bad_path: str) -> None:
    repo_root = setup_policy_repo(tmp_path)
    config = (repo_root / "tools" / "policy" / "adr_policy.yaml").read_text()
    config = config.replace("allowlist_path: tools/policy/oversized_allowlist.yaml", f"allowlist_path: {bad_path}")
    write_text(repo_root / "tools" / "policy" / "adr_policy.yaml", config)

    failures = evaluate_repo_policy(
        repo_root,
        ["tools/policy/adr_policy.yaml"],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert [f.rule_id for f in failures] == ["policy-path-unsafe"], [f.message for f in failures]


def test_unsafe_changed_path_is_rejected(tmp_path: Path) -> None:
    """A changed path that escapes the repo root (e.g. via a planted
    symlink) is reported as policy-path-unsafe rather than being read."""
    repo_root = setup_policy_repo(tmp_path)
    outside = tmp_path.parent / "outside_secret.py"
    write_text(outside, "import raes_processor\n")
    link_rel = "implementations/python/packages/raes/_link.py"
    (repo_root / "implementations" / "python" / "packages" / "raes").mkdir(parents=True, exist_ok=True)
    (repo_root / link_rel).symlink_to(outside)

    failures = evaluate_repo_policy(
        repo_root, [link_rel], check_set="file-local", structural_runner=structural_runner_stub
    )

    assert "policy-path-unsafe" in [f.rule_id for f in failures], [f.message for f in failures]
    assert "layering-rule-violation" not in [f.rule_id for f in failures]


# ── ADR-015: drain requires the file to actually have been split ────────


def test_premature_drain_is_rejected(tmp_path: Path) -> None:
    """Removing an initial oversized file from the allowlist while the file
    itself is unchanged (still over the cap) is a premature drain — the
    debt list shrank without the work being done. Caught config-wide even
    though the (unchanged, undeleted) file is not in the changed set."""
    repo_root = setup_policy_repo(tmp_path)
    # Default allowlist is empty -> _LOCKED_PATH is "claimed drained".
    write_text(repo_root / _LOCKED_PATH, "x = 1\n" * 700)  # but the file is still over cap

    failures = evaluate_repo_policy(
        repo_root,
        ["docs/decisions/adrs/adr-001-example.md"],  # unrelated change
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert [f.rule_id for f in failures] == ["oversized-source-file"], [f.message for f in failures]
    assert "removed from" in failures[0].message and "700" in failures[0].message


def test_legitimate_drain_passes(tmp_path: Path) -> None:
    """An initial oversized file that has been removed from the allowlist
    AND actually split below the cap passes."""
    repo_root = setup_policy_repo(tmp_path)
    write_text(repo_root / _LOCKED_PATH, "x = 1\n" * 120)  # genuinely split below the cap

    failures = evaluate_repo_policy(
        repo_root,
        ["docs/decisions/adrs/adr-001-example.md"],
        check_set="file-local",
        structural_runner=structural_runner_stub,
    )

    assert failures == []


# ── ADR-015: config-wide checks run even when nothing changed ────────────


def test_empty_changed_still_runs_config_wide_adr015_checks(tmp_path: Path) -> None:
    """A deletion-only PR (the repo's changed-paths helper excludes
    deletions) can hand an empty changed list to the policy. The ADR-015
    config-wide invariants must still be evaluated — here, a stale allowlist
    entry is flagged with no changed files at all."""
    repo_root = setup_policy_repo(tmp_path)
    write_text(repo_root / "tools" / "policy" / "oversized_allowlist.yaml", f"files:\n  - {_LOCKED_PATH}\n")
    write_text(repo_root / _LOCKED_PATH, "x = 1\n" * 100)

    failures = evaluate_repo_policy(repo_root, [], check_set="file-local", structural_runner=structural_runner_stub)

    assert [f.rule_id for f in failures] == ["oversized-allowlist-stale-entry"], [f.message for f in failures]


def test_empty_changed_detects_deleted_allowlist_file(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    (repo_root / "tools" / "policy" / "oversized_allowlist.yaml").unlink()

    failures = evaluate_repo_policy(repo_root, [], check_set="file-local", structural_runner=structural_runner_stub)

    assert "policy-config-malformed" in [f.rule_id for f in failures], [f.message for f in failures]


def setup_json_validation_repo(tmp_path: Path) -> Path:
    write_text(
        tmp_path / "contracts" / "schemas" / "concept-authority" / "concept-families-v1.json",
        "{}\n",
    )
    write_text(
        tmp_path / "contracts" / "schemas" / "profiles" / "semantic-profile-v1.json",
        "{}\n",
    )
    write_text(
        tmp_path / "contracts" / "schemas" / "backend-manifest" / "backend-manifest-v2.json",
        "{}\n",
    )
    write_text(
        tmp_path / "contracts" / "concept-authority" / "concept-families-v1.json",
        '{"schema_version": "concept-families-v1"}\n',
    )
    write_text(
        tmp_path / "contracts" / "profiles" / "semantic" / "reference-stack-v1.json",
        '{"schema_version": "semantic-profile-v1"}\n',
    )
    write_text(
        tmp_path / "contracts" / "fixtures" / "backend-manifest" / "backend-manifest-v2" / "valid" / "stub.json",
        "{}\n",
    )
    write_text(
        tmp_path / "contracts" / "fixtures" / "backend-manifest" / "backend-manifest-v2" / "invalid" / "broken.json",
        "{}\n",
    )
    return tmp_path


def write_schema_publication_manifest(
    repo_root: Path,
    entries: list[dict[str, Any]],
    *,
    fill_defaults: bool = True,
    removed_schemas: list[dict[str, Any]] | None = None,
) -> None:
    import json

    normalized: list[dict[str, Any]] = []
    for entry in entries:
        normalized_entry = dict(entry)
        if fill_defaults:
            normalized_entry.setdefault("stability", "draft")
            schema_path = normalized_entry.get("schema_path")
            if "content_hash" not in normalized_entry and isinstance(schema_path, str):
                path = repo_root / schema_path
                normalized_entry["content_hash"] = schema_content_hash(path) if path.is_file() else "0" * 64
        normalized.append(normalized_entry)

    document: dict[str, Any] = {
        "schema_version": "schema-publication-manifest/v1",
        "hash_algorithm": "sha256",
        "schemas": normalized,
    }
    if removed_schemas is not None:
        document["removed_schemas"] = removed_schemas

    write_text(
        repo_root / "contracts" / "schema-publication-manifest.json",
        json.dumps(document, indent=2) + "\n",
    )


def _published_schema(properties: dict[str, Any], *, required: list[str] | None = None) -> str:
    import json

    payload = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required or [],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def test_should_run_full_validation_for_schema_driver_paths() -> None:
    assert should_run_full_validation(["tools/generate_contract_schemas.py"]) is True
    assert should_run_full_validation(["implementations/python/packages/raes_contracts/contracts.py"]) is True
    # raes supplies the Scenario Pydantic model exposed by schema_bundle();
    # a change there must trigger full schema validation just like raes_contracts.
    assert should_run_full_validation(["implementations/python/packages/raes/agents.py"]) is True
    assert should_run_full_validation(["contracts/concept-authority/concept-families-v1.json"]) is False


def test_schema_publication_manifest_accepts_complete_current_schema_inventory(tmp_path: Path) -> None:
    repo_root = tmp_path
    write_text(repo_root / "contracts" / "schemas" / "sdl" / "sdl-authoring-input-v1.json", "{}\n")
    write_text(repo_root / "contracts" / "schemas" / "control-plane" / "operation-status-v1.json", "{}\n")
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "operation-status-v1",
                "schema_path": "contracts/schemas/control-plane/operation-status-v1.json",
            },
            {
                "contract_id": "sdl-authoring-input-v1",
                "schema_path": "contracts/schemas/sdl/sdl-authoring-input-v1.json",
            },
        ],
    )

    assert validate_schema_publication_manifest(repo_root) == []


def test_schema_publication_manifest_requires_stability_and_content_hash(tmp_path: Path) -> None:
    repo_root = tmp_path
    write_text(repo_root / "contracts" / "schemas" / "sdl" / "sdl-authoring-input-v1.json", "{}\n")
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "sdl-authoring-input-v1",
                "schema_path": "contracts/schemas/sdl/sdl-authoring-input-v1.json",
            },
        ],
        fill_defaults=False,
    )

    assert validate_schema_publication_manifest(repo_root) == [
        "schema manifest entry sdl-authoring-input-v1 stability must be one of: draft, stable",
        "schema manifest entry sdl-authoring-input-v1 content_hash must be a 64-character sha256 hex digest",
    ]


def test_schema_publication_manifest_rejects_missing_published_schema_entry(tmp_path: Path) -> None:
    repo_root = tmp_path
    write_text(repo_root / "contracts" / "schemas" / "sdl" / "sdl-authoring-input-v1.json", "{}\n")
    write_text(repo_root / "contracts" / "schemas" / "control-plane" / "operation-status-v1.json", "{}\n")
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "sdl-authoring-input-v1",
                "schema_path": "contracts/schemas/sdl/sdl-authoring-input-v1.json",
            },
        ],
    )

    assert validate_schema_publication_manifest(repo_root) == [
        "schema manifest is missing published schema: contracts/schemas/control-plane/operation-status-v1.json"
    ]


def test_schema_publication_manifest_rejects_paths_outside_contract_schemas(tmp_path: Path) -> None:
    repo_root = tmp_path
    write_text(repo_root / "schemas" / "legacy.json", "{}\n")
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "legacy",
                "schema_path": "schemas/legacy.json",
            },
        ],
    )

    assert validate_schema_publication_manifest(repo_root) == [
        "schema manifest path must be under contracts/schemas/: schemas/legacy.json"
    ]


def test_schema_publication_manifest_rejects_resolved_schema_path_escape(tmp_path: Path) -> None:
    repo_root = tmp_path
    write_text(repo_root / "contracts" / "secret-v1.json", "{}\n")
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "secret-v1",
                "schema_path": "contracts/schemas/../secret-v1.json",
            },
        ],
    )

    assert validate_schema_publication_manifest(repo_root) == [
        "schema manifest path resolves outside contracts/schemas/: contracts/schemas/../secret-v1.json"
    ]


def test_schema_publication_manifest_allows_recorded_draft_schema_churn(tmp_path: Path) -> None:
    repo_root = tmp_path
    schema_path = repo_root / "contracts" / "schemas" / "sdl" / "draft-contract-v1.json"
    write_text(schema_path, _published_schema({"name": {"type": "string"}}))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "draft-contract-v1",
                "schema_path": "contracts/schemas/sdl/draft-contract-v1.json",
                "stability": "draft",
            },
        ],
    )
    _init_git_repo(repo_root)
    _git_commit_all(repo_root, "base")

    write_text(schema_path, _published_schema({"name": {"type": "integer"}}))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "draft-contract-v1",
                "schema_path": "contracts/schemas/sdl/draft-contract-v1.json",
                "stability": "draft",
                "last_change": {
                    "summary": "Retype name to integer for the draft contract.",
                    "content_hash": schema_content_hash(schema_path),
                },
            },
        ],
    )

    assert validate_schema_publication_manifest(repo_root, base_rev="HEAD") == []


def test_schema_publication_manifest_allows_stable_additive_schema_change(tmp_path: Path) -> None:
    repo_root = tmp_path
    schema_path = repo_root / "contracts" / "schemas" / "sdl" / "stable-contract-v1.json"
    write_text(schema_path, _published_schema({"name": {"type": "string"}}, required=["name"]))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "stable-contract-v1",
                "schema_path": "contracts/schemas/sdl/stable-contract-v1.json",
                "stability": "stable",
            },
        ],
    )
    _init_git_repo(repo_root)
    _git_commit_all(repo_root, "base")

    write_text(
        schema_path,
        _published_schema({"name": {"type": "string"}, "display_name": {"type": "string"}}, required=["name"]),
    )
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "stable-contract-v1",
                "schema_path": "contracts/schemas/sdl/stable-contract-v1.json",
                "stability": "stable",
                "last_change": {
                    "summary": "Add optional display_name property.",
                    "content_hash": schema_content_hash(schema_path),
                },
            },
        ],
    )

    assert validate_schema_publication_manifest(repo_root, base_rev="HEAD") == []


def test_schema_publication_manifest_allows_stable_enum_addition(tmp_path: Path) -> None:
    repo_root = tmp_path
    schema_path = repo_root / "contracts" / "schemas" / "sdl" / "stable-contract-v1.json"
    write_text(schema_path, _published_schema({"kind": {"enum": ["alpha"], "type": "string"}}, required=["kind"]))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "stable-contract-v1",
                "schema_path": "contracts/schemas/sdl/stable-contract-v1.json",
                "stability": "stable",
            },
        ],
    )
    _init_git_repo(repo_root)
    _git_commit_all(repo_root, "base")

    write_text(
        schema_path,
        _published_schema({"kind": {"enum": ["alpha", "beta"], "type": "string"}}, required=["kind"]),
    )
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "stable-contract-v1",
                "schema_path": "contracts/schemas/sdl/stable-contract-v1.json",
                "stability": "stable",
                "last_change": {
                    "summary": "Add enum value beta to kind.",
                    "content_hash": schema_content_hash(schema_path),
                },
            },
        ],
    )

    assert validate_schema_publication_manifest(repo_root, base_rev="HEAD") == []


def test_schema_publication_manifest_rejects_stable_default_change_without_version_bump(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    schema_path = repo_root / "contracts" / "schemas" / "sdl" / "stable-contract-v1.json"
    write_text(
        schema_path,
        _published_schema({"name": {"default": "alpha", "type": "string"}}, required=["name"]),
    )
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "stable-contract-v1",
                "schema_path": "contracts/schemas/sdl/stable-contract-v1.json",
                "stability": "stable",
            },
        ],
    )
    _init_git_repo(repo_root)
    _git_commit_all(repo_root, "base")

    write_text(
        schema_path,
        _published_schema({"name": {"default": "beta", "type": "string"}}, required=["name"]),
    )
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "stable-contract-v1",
                "schema_path": "contracts/schemas/sdl/stable-contract-v1.json",
                "stability": "stable",
                "last_change": {
                    "summary": "Change default value of name.",
                    "content_hash": schema_content_hash(schema_path),
                },
            },
        ],
    )

    assert validate_schema_publication_manifest(repo_root, base_rev="HEAD") == [
        "stable schema stable-contract-v1 changed incompatibly without a version bump: properties/name default changed"
    ]


def test_schema_publication_manifest_rejects_stable_breaking_schema_change_without_version_bump(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    schema_path = repo_root / "contracts" / "schemas" / "sdl" / "stable-contract-v1.json"
    write_text(schema_path, _published_schema({"name": {"type": "string"}}, required=["name"]))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "stable-contract-v1",
                "schema_path": "contracts/schemas/sdl/stable-contract-v1.json",
                "stability": "stable",
            },
        ],
    )
    _init_git_repo(repo_root)
    _git_commit_all(repo_root, "base")

    write_text(schema_path, _published_schema({"name": {"type": "integer"}}, required=["name"]))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "stable-contract-v1",
                "schema_path": "contracts/schemas/sdl/stable-contract-v1.json",
                "stability": "stable",
                "last_change": {
                    "summary": "Retype name to integer.",
                    "content_hash": schema_content_hash(schema_path),
                },
            },
        ],
    )

    assert validate_schema_publication_manifest(repo_root, base_rev="HEAD") == [
        "stable schema stable-contract-v1 changed incompatibly without a version bump: properties/name schema changed"
    ]


def test_schema_publication_manifest_rejects_unreadable_base_manifest_for_stable_schema(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    schema_path = repo_root / "contracts" / "schemas" / "sdl" / "stable-contract-v1.json"
    write_text(schema_path, _published_schema({"name": {"type": "string"}}, required=["name"]))
    write_text(repo_root / "contracts" / "schema-publication-manifest.json", "{not-json\n")
    _init_git_repo(repo_root)
    _git_commit_all(repo_root, "base")

    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "stable-contract-v1",
                "schema_path": "contracts/schemas/sdl/stable-contract-v1.json",
                "stability": "stable",
            },
        ],
    )

    assert validate_schema_publication_manifest(repo_root, base_rev="HEAD") == [
        "base schema publication manifest at HEAD is not valid JSON"
    ]


def test_schema_publication_manifest_rejects_missing_base_schema_for_stable_schema(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "stable-contract-v1",
                "schema_path": "contracts/schemas/sdl/stable-contract-v1.json",
                "stability": "stable",
                "content_hash": "0" * 64,
            },
        ],
        fill_defaults=False,
    )
    _init_git_repo(repo_root)
    _git_commit_all(repo_root, "base")

    schema_path = repo_root / "contracts" / "schemas" / "sdl" / "stable-contract-v1.json"
    write_text(schema_path, _published_schema({"name": {"type": "string"}}, required=["name"]))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "stable-contract-v1",
                "schema_path": "contracts/schemas/sdl/stable-contract-v1.json",
                "stability": "stable",
                "last_change": {
                    "summary": "Publish the stable contract.",
                    "content_hash": schema_content_hash(schema_path),
                },
            },
        ],
    )

    assert validate_schema_publication_manifest(repo_root, base_rev="HEAD") == [
        "base schema for stable-contract-v1 is missing at HEAD: contracts/schemas/sdl/stable-contract-v1.json"
    ]


def test_schema_publication_manifest_accepts_valid_last_change_ledger(tmp_path: Path) -> None:
    repo_root = tmp_path
    schema_path = repo_root / "contracts" / "schemas" / "sdl" / "draft-contract-v1.json"
    write_text(schema_path, _published_schema({"name": {"type": "string"}}))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "draft-contract-v1",
                "schema_path": "contracts/schemas/sdl/draft-contract-v1.json",
                "stability": "draft",
                "last_change": {
                    "summary": "Initial draft of the authoring contract.",
                    "content_hash": schema_content_hash(schema_path),
                },
            },
        ],
    )

    assert validate_schema_publication_manifest(repo_root) == []


def test_schema_publication_manifest_accepts_independent_v2_records(tmp_path: Path) -> None:
    import json

    repo_root = tmp_path
    schema_path = repo_root / "contracts" / "schemas" / "sdl" / "draft-contract-v1.json"
    write_text(schema_path, _published_schema({"name": {"type": "string"}}))
    digest = schema_content_hash(schema_path)
    write_text(
        repo_root / "contracts" / "schema-publication-manifest.json",
        json.dumps(
            {
                "schema_version": "schema-publication-manifest/v2",
                "hash_algorithm": "sha256",
                "entries_directory": "contracts/schema-publication/entries",
                "tombstones_directory": "contracts/schema-publication/tombstones",
            }
        )
        + "\n",
    )
    write_text(
        repo_root / "contracts" / "schema-publication" / "entries" / "draft-contract-v1.json",
        json.dumps(
            {
                "contract_id": "draft-contract-v1",
                "schema_path": "contracts/schemas/sdl/draft-contract-v1.json",
                "stability": "draft",
                "content_hash": digest,
                "last_change": {"summary": "Initial publication.", "content_hash": digest},
            }
        )
        + "\n",
    )
    write_text(repo_root / "contracts" / "schema-publication" / "tombstones" / "README.md", "# Empty\n")

    assert validate_schema_publication_manifest(repo_root) == []


def test_schema_publication_manifest_rejects_last_change_without_summary(tmp_path: Path) -> None:
    repo_root = tmp_path
    schema_path = repo_root / "contracts" / "schemas" / "sdl" / "draft-contract-v1.json"
    write_text(schema_path, _published_schema({"name": {"type": "string"}}))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "draft-contract-v1",
                "schema_path": "contracts/schemas/sdl/draft-contract-v1.json",
                "stability": "draft",
                "last_change": {"content_hash": schema_content_hash(schema_path)},
            },
        ],
    )

    failures = validate_schema_publication_manifest(repo_root)
    assert any("last_change.summary" in failure for failure in failures)


def test_schema_publication_manifest_rejects_last_change_hash_mismatch(tmp_path: Path) -> None:
    repo_root = tmp_path
    schema_path = repo_root / "contracts" / "schemas" / "sdl" / "draft-contract-v1.json"
    write_text(schema_path, _published_schema({"name": {"type": "string"}}))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "draft-contract-v1",
                "schema_path": "contracts/schemas/sdl/draft-contract-v1.json",
                "stability": "draft",
                "last_change": {"summary": "stale ledger entry", "content_hash": "0" * 64},
            },
        ],
    )

    failures = validate_schema_publication_manifest(repo_root)
    assert any("last_change.content_hash" in failure and "does not match" in failure for failure in failures)


def test_schema_publication_manifest_requires_ledger_when_schema_changes(tmp_path: Path) -> None:
    repo_root = tmp_path
    schema_path = repo_root / "contracts" / "schemas" / "sdl" / "draft-contract-v1.json"
    write_text(schema_path, _published_schema({"name": {"type": "string"}}))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "draft-contract-v1",
                "schema_path": "contracts/schemas/sdl/draft-contract-v1.json",
                "stability": "draft",
            },
        ],
    )
    _init_git_repo(repo_root)
    _git_commit_all(repo_root, "base")

    # Schema content changes vs base, manifest hash bumps, but no contract-facing
    # ledger entry records why — the process gate must reject this.
    write_text(schema_path, _published_schema({"name": {"type": "integer"}}))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "draft-contract-v1",
                "schema_path": "contracts/schemas/sdl/draft-contract-v1.json",
                "stability": "draft",
            },
        ],
    )

    failures = validate_schema_publication_manifest(repo_root, base_rev="HEAD")
    assert any("contract-facing change description" in failure for failure in failures)


def test_schema_publication_manifest_accepts_changed_schema_with_current_ledger(tmp_path: Path) -> None:
    repo_root = tmp_path
    schema_path = repo_root / "contracts" / "schemas" / "sdl" / "draft-contract-v1.json"
    write_text(schema_path, _published_schema({"name": {"type": "string"}}))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "draft-contract-v1",
                "schema_path": "contracts/schemas/sdl/draft-contract-v1.json",
                "stability": "draft",
            },
        ],
    )
    _init_git_repo(repo_root)
    _git_commit_all(repo_root, "base")

    write_text(schema_path, _published_schema({"name": {"type": "integer"}}))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "draft-contract-v1",
                "schema_path": "contracts/schemas/sdl/draft-contract-v1.json",
                "stability": "draft",
                "last_change": {
                    "summary": "Retype name to integer per contract review.",
                    "content_hash": schema_content_hash(schema_path),
                },
            },
        ],
    )

    assert validate_schema_publication_manifest(repo_root, base_rev="HEAD") == []


def test_schema_publication_manifest_requires_ledger_for_new_schema(tmp_path: Path) -> None:
    repo_root = tmp_path
    existing = repo_root / "contracts" / "schemas" / "sdl" / "existing-contract-v1.json"
    write_text(existing, _published_schema({"name": {"type": "string"}}))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "existing-contract-v1",
                "schema_path": "contracts/schemas/sdl/existing-contract-v1.json",
                "stability": "draft",
            },
        ],
    )
    _init_git_repo(repo_root)
    _git_commit_all(repo_root, "base")

    new_schema = repo_root / "contracts" / "schemas" / "sdl" / "new-contract-v1.json"
    write_text(new_schema, _published_schema({"id": {"type": "string"}}))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "existing-contract-v1",
                "schema_path": "contracts/schemas/sdl/existing-contract-v1.json",
                "stability": "draft",
            },
            {
                "contract_id": "new-contract-v1",
                "schema_path": "contracts/schemas/sdl/new-contract-v1.json",
                "stability": "draft",
            },
        ],
    )

    failures = validate_schema_publication_manifest(repo_root, base_rev="HEAD")
    assert any("new-contract-v1" in failure and "contract-facing change description" in failure for failure in failures)


def test_schema_publication_manifest_unchanged_schema_needs_no_ledger(tmp_path: Path) -> None:
    repo_root = tmp_path
    schema_path = repo_root / "contracts" / "schemas" / "sdl" / "draft-contract-v1.json"
    write_text(schema_path, _published_schema({"name": {"type": "string"}}))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "draft-contract-v1",
                "schema_path": "contracts/schemas/sdl/draft-contract-v1.json",
                "stability": "draft",
            },
        ],
    )
    _init_git_repo(repo_root)
    _git_commit_all(repo_root, "base")

    # No schema change vs base: an existing entry without a ledger stays valid,
    # so the gate never forces backfilling ledgers onto unchanged schemas.
    assert validate_schema_publication_manifest(repo_root, base_rev="HEAD") == []


def _seed_two_schema_repo(repo_root: Path) -> None:
    keep = repo_root / "contracts" / "schemas" / "sdl" / "keep-contract-v1.json"
    drop = repo_root / "contracts" / "schemas" / "sdl" / "drop-contract-v1.json"
    write_text(keep, _published_schema({"name": {"type": "string"}}))
    write_text(drop, _published_schema({"id": {"type": "string"}}))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "drop-contract-v1",
                "schema_path": "contracts/schemas/sdl/drop-contract-v1.json",
                "stability": "draft",
            },
            {
                "contract_id": "keep-contract-v1",
                "schema_path": "contracts/schemas/sdl/keep-contract-v1.json",
                "stability": "draft",
            },
        ],
    )
    _init_git_repo(repo_root)
    _git_commit_all(repo_root, "base")
    # Delete the published schema and drop its manifest entry.
    drop.unlink()
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "keep-contract-v1",
                "schema_path": "contracts/schemas/sdl/keep-contract-v1.json",
                "stability": "draft",
            },
        ],
    )


def test_schema_publication_manifest_requires_tombstone_for_removed_schema(tmp_path: Path) -> None:
    repo_root = tmp_path
    _seed_two_schema_repo(repo_root)

    # Removing the file and its manifest entry without a tombstone bypasses the
    # contract-facing ledger the gate requires for every other schema change.
    failures = validate_schema_publication_manifest(repo_root, base_rev="HEAD")
    assert any(
        "drop-contract-v1.json" in failure and "removed without a contract-facing removal description" in failure
        for failure in failures
    )


def test_schema_publication_manifest_accepts_removed_schema_with_tombstone(tmp_path: Path) -> None:
    repo_root = tmp_path
    _seed_two_schema_repo(repo_root)

    # The tombstone records why the contract was removed; the gate is satisfied.
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "keep-contract-v1",
                "schema_path": "contracts/schemas/sdl/keep-contract-v1.json",
                "stability": "draft",
            },
        ],
        removed_schemas=[
            {
                "schema_path": "contracts/schemas/sdl/drop-contract-v1.json",
                "summary": "Retired per contract review; superseded by keep-contract-v1.",
            },
        ],
    )

    assert validate_schema_publication_manifest(repo_root, base_rev="HEAD") == []


def test_schema_publication_manifest_rejects_tombstone_without_summary(tmp_path: Path) -> None:
    repo_root = tmp_path
    _seed_two_schema_repo(repo_root)

    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "keep-contract-v1",
                "schema_path": "contracts/schemas/sdl/keep-contract-v1.json",
                "stability": "draft",
            },
        ],
        removed_schemas=[{"schema_path": "contracts/schemas/sdl/drop-contract-v1.json"}],
    )

    failures = validate_schema_publication_manifest(repo_root, base_rev="HEAD")
    assert any("removed_schemas" in failure and "summary must be a non-empty string" in failure for failure in failures)


def test_schema_publication_manifest_rejects_tombstone_for_published_schema(tmp_path: Path) -> None:
    repo_root = tmp_path
    schema_path = repo_root / "contracts" / "schemas" / "sdl" / "draft-contract-v1.json"
    write_text(schema_path, _published_schema({"name": {"type": "string"}}))
    write_schema_publication_manifest(
        repo_root,
        [
            {
                "contract_id": "draft-contract-v1",
                "schema_path": "contracts/schemas/sdl/draft-contract-v1.json",
                "stability": "draft",
            },
        ],
        removed_schemas=[
            {
                "schema_path": "contracts/schemas/sdl/draft-contract-v1.json",
                "summary": "Tombstone contradicts a still-published schema.",
            },
        ],
    )
    _init_git_repo(repo_root)
    _git_commit_all(repo_root, "base")

    failures = validate_schema_publication_manifest(repo_root, base_rev="HEAD")
    assert any("removed_schemas tombstone" in failure and "still-published schema" in failure for failure in failures)


def test_collect_validation_targets_includes_only_schema_governed_artifacts(tmp_path: Path) -> None:
    repo_root = setup_json_validation_repo(tmp_path)

    targets = collect_validation_targets(repo_root)

    observed = {(target.path, target.schema_path, target.mode) for target in targets}

    assert ("contracts/schemas/backend-manifest/backend-manifest-v2.json", None, "metaschema") in observed
    assert (
        "contracts/concept-authority/concept-families-v1.json",
        "contracts/schemas/concept-authority/concept-families-v1.json",
        "schema",
    ) in observed
    assert (
        "contracts/profiles/semantic/reference-stack-v1.json",
        "contracts/schemas/profiles/semantic-profile-v1.json",
        "schema",
    ) in observed
    assert (
        "contracts/fixtures/backend-manifest/backend-manifest-v2/valid/stub.json",
        "contracts/schemas/backend-manifest/backend-manifest-v2.json",
        "schema",
    ) in observed
    assert all("/invalid/" not in target.path for target in targets)


def test_collect_validation_targets_runs_full_scan_when_schema_drivers_change(tmp_path: Path) -> None:
    repo_root = setup_json_validation_repo(tmp_path)

    targets = collect_validation_targets(
        repo_root,
        paths=["implementations/python/packages/raes_contracts/contracts.py"],
    )

    assert any(target.path == "contracts/concept-authority/concept-families-v1.json" for target in targets)


def test_json_validation_batches_by_schema_and_runs_batches_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAES_JSON_SCHEMA_WORKERS", raising=False)
    barrier = threading.Barrier(3, timeout=2)
    calls: list[tuple[str, ...]] = []
    calls_lock = threading.Lock()

    def fake_run(*args: str) -> subprocess.CompletedProcess[str]:
        with calls_lock:
            calls.append(args)
        barrier.wait()
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(check_json_artifacts, "_run_check_jsonschema", fake_run)
    targets = [
        ValidationTarget("contracts/schemas/one.json", None, "metaschema"),
        ValidationTarget("contracts/schemas/two.json", None, "metaschema"),
        ValidationTarget("contracts/fixtures/one-a.json", "contracts/schemas/one.json", "schema"),
        ValidationTarget("contracts/fixtures/one-b.json", "contracts/schemas/one.json", "schema"),
        ValidationTarget("contracts/fixtures/two.json", "contracts/schemas/two.json", "schema"),
    ]

    assert check_json_artifacts.validate_targets(targets) == []
    assert sorted(calls) == sorted(
        [
            ("--check-metaschema", "contracts/schemas/one.json", "contracts/schemas/two.json"),
            (
                "--schemafile",
                "contracts/schemas/one.json",
                "contracts/fixtures/one-a.json",
                "contracts/fixtures/one-b.json",
            ),
            (
                "--schemafile",
                "contracts/schemas/two.json",
                "contracts/fixtures/two.json",
            ),
        ]
    )


def test_gitleaks_binary_path_uses_repo_local_cache(tmp_path: Path) -> None:
    assert gitleaks_binary_path(tmp_path, version="8.30.1") == (
        tmp_path / ".cache" / "raes-sdl" / "tooling" / "gitleaks" / "8.30.1" / "gitleaks"
    )


def test_osv_scanner_binary_path_uses_repo_local_cache(tmp_path: Path) -> None:
    assert osv_scanner_tool.osv_scanner_binary_path(tmp_path, version="2.4.0") == (
        tmp_path / ".cache" / "raes-sdl" / "tooling" / "osv-scanner" / "2.4.0" / "osv-scanner"
    )


def _pin_fake_osv_download(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    digest = osv_scanner_tool.sha256(payload).hexdigest()

    def selection(**kwargs: object) -> object:
        if kwargs.get("version") != "2.4.0":
            raise RuntimeError("no reviewed lock selection")
        return types.SimpleNamespace(
            artifact_id="osv-scanner",
            version="2.4.0",
            platform_id="macos-arm64",
            profile_id="public-macos-arm64",
            repository="https://github.com/google/osv-scanner",
            release="v2.4.0",
            source_urls=("https://github.com/google/osv-scanner/releases/download/v2.4.0/osv-scanner_darwin_arm64",),
            raw_manifest=(types.SimpleNamespace(path="osv-scanner_darwin_arm64", sha256=digest, size=len(payload)),),
            installed_manifest=(types.SimpleNamespace(path="osv-scanner", sha256=digest, size=len(payload)),),
        )

    monkeypatch.setattr("tools.tooling_policy_gate.host_platform_id", lambda: "macos-arm64")
    monkeypatch.setattr("tools.tooling_policy_gate.load_tooling_artifact_selection", selection)


def test_osv_scanner_valid_cache_hit_rehashes_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"reviewed-scanner"
    _pin_fake_osv_download(monkeypatch, payload)
    binary = osv_scanner_tool.osv_scanner_binary_path(tmp_path)
    binary.parent.mkdir(parents=True)
    binary.write_bytes(payload)
    binary.chmod(0o755)
    monkeypatch.setattr(
        osv_scanner_tool,
        "acquire_locked_bytes",
        lambda **_kwargs: pytest.fail("acquisition used for valid cache"),
    )

    assert osv_scanner_tool.ensure_osv_scanner(tmp_path) == binary


@pytest.mark.parametrize("cache_kind", ["tampered", "non-executable", "symlink"])
def test_osv_scanner_invalid_file_cache_is_reacquired_atomically(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cache_kind: str,
) -> None:
    payload = b"reviewed-scanner"
    _pin_fake_osv_download(monkeypatch, payload)
    binary = osv_scanner_tool.osv_scanner_binary_path(tmp_path)
    binary.parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_bytes(b"must-remain")
    if cache_kind == "symlink":
        binary.symlink_to(outside)
    else:
        binary.write_bytes(payload if cache_kind == "non-executable" else b"tampered")
        binary.chmod(0o644 if cache_kind == "non-executable" else 0o755)
    monkeypatch.setattr(osv_scanner_tool, "acquire_locked_bytes", lambda **_kwargs: payload)

    installed = osv_scanner_tool.ensure_osv_scanner(tmp_path)

    assert installed == binary
    assert installed.read_bytes() == payload
    assert installed.stat().st_mode & 0o100
    assert outside.read_bytes() == b"must-remain"


def test_osv_scanner_unsafe_cache_shapes_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = b"reviewed-scanner"
    _pin_fake_osv_download(monkeypatch, payload)
    binary = osv_scanner_tool.osv_scanner_binary_path(tmp_path)
    binary.mkdir(parents=True)

    with pytest.raises(RuntimeError, match="not a regular file"):
        osv_scanner_tool.ensure_osv_scanner(tmp_path)

    shutil.rmtree(tmp_path / ".cache")
    outside = tmp_path / "outside-cache"
    outside.mkdir()
    (tmp_path / ".cache").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="unsafe osv-scanner cache directory"):
        osv_scanner_tool.ensure_osv_scanner(tmp_path)

    with pytest.raises(RuntimeError, match="cache path escapes"):
        osv_scanner_tool._safe_cache_parent(tmp_path, tmp_path.parent / "outside" / "osv-scanner")


def test_osv_scanner_cache_read_error_is_sanitized(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    binary = tmp_path / "osv-scanner"
    binary.write_bytes(b"scanner")
    binary.chmod(0o755)
    monkeypatch.setattr(osv_scanner_tool, "_sha256_path", lambda _path: (_ for _ in ()).throw(OSError("secret")))

    with pytest.raises(RuntimeError, match="failed to validate cached osv-scanner") as raised:
        osv_scanner_tool._validated_cache_hit(binary, "0" * 64)
    assert "secret" not in str(raised.value)


def test_osv_scanner_cache_final_identity_read_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"scanner"
    binary = tmp_path / "osv-scanner"
    binary.write_bytes(payload)
    binary.chmod(0o755)
    expected = osv_scanner_tool.sha256(payload).hexdigest()
    monkeypatch.setattr(osv_scanner_tool, "_sha256_path", lambda _path: expected)
    real_lstat = Path.lstat
    calls = 0

    def fail_second_lstat(path: Path) -> os.stat_result:
        nonlocal calls
        if path == binary:
            calls += 1
            if calls == 2:
                raise OSError("changed")
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", fail_second_lstat)

    with pytest.raises(RuntimeError, match="failed to validate cached osv-scanner"):
        osv_scanner_tool._validated_cache_hit(binary, expected)


def test_osv_scanner_cache_hash_rejects_last_component_swap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"reviewed-scanner"
    binary = tmp_path / "osv-scanner"
    outside = tmp_path / "outside-scanner"
    binary.write_bytes(payload)
    binary.chmod(0o755)
    outside.write_bytes(payload)
    real_open = osv_scanner_tool.os.open

    def swap_before_open(path: object, flags: int, *args: object) -> int:
        if Path(path) == binary:
            binary.unlink()
            binary.symlink_to(outside)
        return real_open(path, flags, *args)

    monkeypatch.setattr(osv_scanner_tool.os, "open", swap_before_open)
    expected = osv_scanner_tool.sha256(payload).hexdigest()

    with pytest.raises(RuntimeError, match="failed to validate cached osv-scanner"):
        osv_scanner_tool._validated_cache_hit(binary, expected)
    assert outside.read_bytes() == payload


def test_osv_scanner_cache_hash_rejects_unbounded_or_changed_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binary = tmp_path / "osv-scanner"
    binary.write_bytes(b"abc")
    monkeypatch.setattr(osv_scanner_tool, "_MAX_BINARY_BYTES", 2)
    with pytest.raises(OSError, match="bounded regular file"):
        osv_scanner_tool._sha256_path(binary)

    monkeypatch.setattr(osv_scanner_tool, "_MAX_BINARY_BYTES", 3)
    real_open = osv_scanner_tool.os.open

    def grow_before_open(path: object, flags: int, *args: object) -> int:
        if Path(path) == binary:
            binary.write_bytes(b"abcd")
        return real_open(path, flags, *args)

    monkeypatch.setattr(osv_scanner_tool.os, "open", grow_before_open)
    with pytest.raises(OSError, match="exceeds the size bound"):
        osv_scanner_tool._sha256_path(binary)


def test_osv_scanner_cache_hash_rejects_open_and_post_hash_identity_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binary = tmp_path / "osv-scanner"
    other = tmp_path / "other"
    binary.write_bytes(b"scanner")
    other.write_bytes(b"other")
    real_fstat = osv_scanner_tool.os.fstat
    monkeypatch.setattr(osv_scanner_tool.os, "fstat", lambda _descriptor: other.stat())
    with pytest.raises(OSError, match="changed while it was opened"):
        osv_scanner_tool._sha256_path(binary)

    monkeypatch.setattr(osv_scanner_tool.os, "fstat", real_fstat)
    real_samestat = osv_scanner_tool.os.path.samestat
    calls = 0

    def identity_changes(left: os.stat_result, right: os.stat_result) -> bool:
        nonlocal calls
        calls += 1
        return real_samestat(left, right) if calls == 1 else False

    monkeypatch.setattr(osv_scanner_tool.os.path, "samestat", identity_changes)
    with pytest.raises(OSError, match="changed while it was hashed"):
        osv_scanner_tool._sha256_path(binary)


def test_osv_scanner_uses_the_selected_raw_object_at_the_shared_acquisition_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"reviewed-scanner"
    _pin_fake_osv_download(monkeypatch, payload)
    observed: dict[str, object] = {}

    def acquire_locked_bytes(**kwargs: object) -> bytes:
        observed.update(kwargs)
        return payload

    monkeypatch.setattr(osv_scanner_tool, "acquire_locked_bytes", acquire_locked_bytes)

    assert osv_scanner_tool.ensure_osv_scanner(tmp_path).read_bytes() == payload
    assert observed["artifact_id"] == "osv-scanner"
    assert observed["source_url"] == (
        "https://github.com/google/osv-scanner/releases/download/v2.4.0/osv-scanner_darwin_arm64"
    )
    assert observed["expected"].path == "osv-scanner_darwin_arm64"
    assert observed["local_input"] is None


def test_osv_scanner_policy_rejection_prevents_an_untrusted_release_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def reject_selection(**_kwargs: object) -> object:
        raise RuntimeError("policy rejected unsafe source URL")

    monkeypatch.setattr("tools.tooling_policy_gate.load_tooling_artifact_selection", reject_selection)
    monkeypatch.setattr(
        osv_scanner_tool,
        "acquire_locked_bytes",
        lambda **_kwargs: pytest.fail("unsafe URL reached the acquisition boundary"),
    )

    with pytest.raises(RuntimeError, match="policy rejected unsafe source URL"):
        osv_scanner_tool.ensure_osv_scanner(tmp_path)


def test_osv_scanner_acquisition_failure_is_terminal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = b"reviewed-scanner"
    _pin_fake_osv_download(monkeypatch, payload)

    def timeout(**_kwargs: object) -> bytes:
        raise RuntimeError("osv-scanner acquisition failed: curl-wall-deadline")

    monkeypatch.setattr(osv_scanner_tool, "acquire_locked_bytes", timeout)

    with pytest.raises(RuntimeError, match="curl-wall-deadline"):
        osv_scanner_tool.ensure_osv_scanner(tmp_path)


def test_osv_scanner_unpinned_version_and_download_mismatch_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"reviewed-scanner"
    _pin_fake_osv_download(monkeypatch, payload)
    with pytest.raises(RuntimeError, match="no reviewed lock selection"):
        osv_scanner_tool.ensure_osv_scanner(tmp_path, version="9.9.9")

    monkeypatch.setattr(osv_scanner_tool, "acquire_locked_bytes", lambda **_kwargs: b"different")
    with pytest.raises(RuntimeError, match="installed binary differs"):
        osv_scanner_tool.ensure_osv_scanner(tmp_path)
    assert not osv_scanner_tool.osv_scanner_binary_path(tmp_path).exists()


def test_osv_scanner_concurrent_acquisition_publishes_only_complete_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"reviewed-scanner"
    _pin_fake_osv_download(monkeypatch, payload)
    barrier = threading.Barrier(2, timeout=3)

    def concurrent_acquisition(**_kwargs: object) -> bytes:
        barrier.wait()
        return payload

    monkeypatch.setattr(osv_scanner_tool, "acquire_locked_bytes", concurrent_acquisition)
    results: list[Path] = []
    failures: list[BaseException] = []

    def acquire() -> None:
        try:
            results.append(osv_scanner_tool.ensure_osv_scanner(tmp_path))
        except BaseException as exc:  # noqa: BLE001 - preserve worker failure for the main assertion
            failures.append(exc)

    workers = [threading.Thread(target=acquire) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5)

    assert failures == []
    assert len(results) == 2
    assert results[0] == results[1]
    assert results[0].read_bytes() == payload
    assert list(results[0].parent.glob(".*.download")) == []


def test_osv_scanner_cache_parent_tolerates_directory_creation_race(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binary = osv_scanner_tool.osv_scanner_binary_path(tmp_path)
    real_mkdir = Path.mkdir
    raced = False

    def create_then_report_race(path: Path, *args: object, **kwargs: object) -> None:
        nonlocal raced
        if not raced and path == tmp_path / ".cache":
            raced = True
            real_mkdir(path, *args, **kwargs)
            raise FileExistsError(path)
        real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", create_then_report_race)

    parent = osv_scanner_tool._safe_cache_parent(tmp_path, binary)

    assert raced is True
    assert parent == binary.parent
    assert parent.is_dir()


@pytest.mark.parametrize(
    ("exit_code", "expected"),
    [
        (0, osv_scanner_tool.OSVScanOutcome.CLEAN),
        (1, osv_scanner_tool.OSVScanOutcome.FINDINGS),
        (2, osv_scanner_tool.OSVScanOutcome.SCANNER_ERROR),
        (127, osv_scanner_tool.OSVScanOutcome.SCANNER_ERROR),
        (128, osv_scanner_tool.OSVScanOutcome.SCANNER_ERROR),
        (-9, osv_scanner_tool.OSVScanOutcome.SCANNER_ERROR),
    ],
)
def test_osv_scanner_exit_codes_distinguish_findings_from_scanner_errors(
    exit_code: int, expected: osv_scanner_tool.OSVScanOutcome
) -> None:
    assert osv_scanner_tool.classify_osv_exit_code(exit_code) is expected


def _fake_osv_binary(tmp_path: Path, *, exit_code: int, payload: str = '{"results": []}') -> Path:
    binary = tmp_path / "osv-scanner"
    binary.write_text(
        f"#!/usr/bin/env python3\nimport sys\nsys.stdout.write({payload!r})\nraise SystemExit({exit_code})\n"
    )
    binary.chmod(0o755)
    return binary


def test_run_osv_scanner_captures_stdout_and_returns_exit_code(tmp_path: Path) -> None:
    binary = _fake_osv_binary(tmp_path, exit_code=1, payload='{"results": [1]}')
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text("")
    report = tmp_path / "out" / "osv-scanner-report.json"

    exit_code = osv_scanner_tool.run_osv_scanner(lockfile, report, binary=binary)

    assert exit_code == 1
    assert report.read_text() == '{"results": [1]}'


def _run_nox_osv_scan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    exit_code: int,
) -> nox_runner.SessionReporter:
    class FakeSession:
        def log(self, _message: str) -> None:
            pass

    lockfile = tmp_path / "implementations" / "python" / "uv.lock"
    lockfile.parent.mkdir(parents=True)
    lockfile.write_text("", encoding="utf-8")
    report = lockfile.with_name("osv-scanner-report.json")
    scanner_binary = tmp_path / "osv-scanner"
    monkeypatch.setattr(nox_test_lanes, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(nox_test_lanes, "OSV_LOCKFILE_PATH", lockfile)
    monkeypatch.setattr(nox_test_lanes, "OSV_REPORT_PATH", report)
    monkeypatch.setattr(nox_test_lanes, "ensure_osv_scanner", lambda _repo_root: scanner_binary)

    def fake_run_osv_scanner(actual_lockfile: Path, actual_report: Path, *, binary: Path) -> int:
        assert actual_lockfile == lockfile
        assert actual_report == report
        assert binary == scanner_binary
        return exit_code

    monkeypatch.setattr(nox_test_lanes, "run_osv_scanner", fake_run_osv_scanner)
    session = FakeSession()
    reporter = nox_runner.SessionReporter(session, "osv_scan")
    nox_test_lanes._run_osv_scan(session, reporter)
    return reporter


def test_nox_osv_scan_accepts_only_a_clean_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reporter = _run_nox_osv_scan(monkeypatch, tmp_path, exit_code=0)

    assert [result.name for result in reporter.results] == ["osv-scan / uv.lock"]


def test_nox_osv_scan_gates_vulnerability_findings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match=r"reported vulnerabilities \(exit code 1\)"):
        _run_nox_osv_scan(monkeypatch, tmp_path, exit_code=1)


def test_nox_osv_scan_surfaces_scanner_errors_distinctly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match="scanner/setup error exit code 127"):
        _run_nox_osv_scan(monkeypatch, tmp_path, exit_code=127)


def test_security_dependency_floors_and_frozen_lock_exclude_vulnerable_releases() -> None:
    project = tomllib.loads((REPO_ROOT / "implementations/python/pyproject.toml").read_text(encoding="utf-8"))
    direct_requirements: dict[str, Requirement] = {}
    for value in project["project"]["dependencies"]:
        requirement = Requirement(value)
        direct_requirements[requirement.name.lower()] = requirement
    locked = tomllib.loads((REPO_ROOT / "implementations/python/uv.lock").read_text(encoding="utf-8"))
    locked_versions = {
        package["name"].lower(): Version(package["version"]) for package in locked["package"] if "version" in package
    }

    for name, last_vulnerable, first_fixed in (
        ("click", Version("8.3.2"), Version("8.3.3")),
        ("cryptography", Version("49.0.0"), Version("50.0.0")),
    ):
        requirement = direct_requirements[name]
        assert Version("0") not in requirement.specifier
        assert last_vulnerable not in requirement.specifier
        assert first_fixed in requirement.specifier
        assert locked_versions[name] >= first_fixed


def test_supply_chain_ci_scan_is_gating_and_preserves_failure_report() -> None:
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["supply-chain"]
    assert "continue-on-error" not in job
    assert all("continue-on-error" not in step for step in job["steps"])

    scan_step = next(step for step in job["steps"] if step.get("name") == "Run OSV-scanner (gating)")
    assert "nox -f noxfile.py -s osv_scan" in scan_step["run"]
    upload_step = next(step for step in job["steps"] if step.get("name") == "Upload OSV-scanner report")
    assert upload_step["if"] == "always()"


def test_extra_published_schema_paths_detects_stale_generated_files(tmp_path: Path) -> None:
    schemas_root = tmp_path / "contracts" / "schemas"
    write_text(schemas_root / "backend-manifest" / "backend-manifest-v2.json", "{}\n")
    write_text(schemas_root / "backend-manifest" / "backend-manifest-v1.json", "{}\n")

    assert _extra_published_schema_paths(
        schemas_root,
        expected_relative_paths={"backend-manifest/backend-manifest-v2.json"},
    ) == ["backend-manifest/backend-manifest-v1.json"]


def _install_fake_schema_generator(
    monkeypatch: pytest.MonkeyPatch,
    *,
    repo_root: Path,
    schemas_root: Path,
    generated: dict[str, str],
) -> None:
    """Install a fake ``tools.generate_contract_schemas`` whose
    ``write_schema_bundle`` emits ``generated`` (rel_path -> content) into
    whatever directory it is given, and repoint ``check_generated_schemas`` at a
    temp repo. The reference bundle is written into a throwaway directory so the
    check can prove the implementation matches the published normative schemas
    (ADR-009 §7) without overwriting them."""
    fake_generator = types.ModuleType("tools.generate_contract_schemas")

    def _write_schema_bundle(schemas_dir: Path) -> None:
        for rel_path, content in generated.items():
            target = schemas_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    fake_generator.write_schema_bundle = _write_schema_bundle

    monkeypatch.setattr(check_generated_schemas, "REPO_ROOT", repo_root)
    monkeypatch.setattr(check_generated_schemas, "SCHEMAS_ROOT", schemas_root)
    monkeypatch.setattr(check_generated_schemas, "PYTHON_ROOT", repo_root / "implementations" / "python")
    monkeypatch.setattr(sys, "argv", ["check_generated_schemas.py"])
    monkeypatch.setitem(sys.modules, "tools.generate_contract_schemas", fake_generator)


def test_check_generated_schemas_rejects_stale_extra_schema_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path
    schemas_root = repo_root / "contracts" / "schemas"
    write_text(schemas_root / "backend-manifest" / "backend-manifest-v2.json", "{}\n")
    write_text(schemas_root / "backend-manifest" / "backend-manifest-v1.json", "{}\n")

    # The reference bundle produces only v2; the published v1 is an extra
    # normative schema the reference implementation no longer generates.
    _install_fake_schema_generator(
        monkeypatch,
        repo_root=repo_root,
        schemas_root=schemas_root,
        generated={"backend-manifest/backend-manifest-v2.json": "{}\n"},
    )

    assert check_generated_schemas.main() == 1


def test_check_generated_schemas_reports_drift_without_mutating_published(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path
    schemas_root = repo_root / "contracts" / "schemas"
    published = schemas_root / "backend-manifest" / "backend-manifest-v2.json"
    published_content = '{\n  "x": 2\n}\n'
    write_text(published, published_content)

    # Reference implementation generates different bytes than the published
    # normative schema: drift must be reported AND the published authority must
    # not be overwritten by the compatibility proof (ADR-009 §7).
    _install_fake_schema_generator(
        monkeypatch,
        repo_root=repo_root,
        schemas_root=schemas_root,
        generated={"backend-manifest/backend-manifest-v2.json": '{\n  "x": 1\n}\n'},
    )

    assert check_generated_schemas.main() == 1
    assert published.read_text(encoding="utf-8") == published_content


def test_check_generated_schemas_passes_when_reference_matches_published(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path
    schemas_root = repo_root / "contracts" / "schemas"
    content = '{\n  "x": 1\n}\n'
    published = schemas_root / "backend-manifest" / "backend-manifest-v2.json"
    write_text(published, content)

    _install_fake_schema_generator(
        monkeypatch,
        repo_root=repo_root,
        schemas_root=schemas_root,
        generated={"backend-manifest/backend-manifest-v2.json": content},
    )

    assert check_generated_schemas.main() == 0
    assert published.read_text(encoding="utf-8") == content


# --- ADR acceptance-content pin gate (ADR-059 / GOV-941) ----------------------

AMENDMENTS_TABLE_HEADER = "## Amendments\n\n| Date | Commit/PR | Summary |\n|------|-----------|---------|\n"


def _adr_dir(tmp_path: Path) -> Path:
    adr_dir = tmp_path / "docs" / "decisions" / "adrs"
    adr_dir.mkdir(parents=True, exist_ok=True)
    return adr_dir


def _make_adr(
    adr_dir: Path,
    number: str,
    *,
    status: str = "accepted",
    body: str = "\n## Context\n\nThe decision body.\n",
    amendment_rows: list[tuple[str, str, str]] | None = None,
) -> str:
    text = _adr_text(number, status=status, body=body)
    if amendment_rows:
        rows = "".join(f"| {date} | {ref} | {summary} |\n" for date, ref, summary in amendment_rows)
        text += "\n" + AMENDMENTS_TABLE_HEADER + rows
    write_text(adr_dir / f"adr-{number}-example.md", text)
    return text


def _write_manifest(adr_dir: Path, entries: list[dict], *, algorithm: str = "sha256") -> None:
    write_text(
        adr_dir / "adr-index.yaml",
        yaml.safe_dump({"hash_algorithm": algorithm, "adrs": entries}, sort_keys=False),
    )


def _entry(number: str, text: str, *, pin_text: str | None = None, amendments: list[dict] | None = None) -> dict:
    # ``pin_text`` lets a caller pin over content that is NOT byte-identical to the
    # on-disk ADR (``text``). Recorded-amendment tests rely on this to pin over the
    # *unamended* body so the gate only stays green if ``canonical_content`` truly
    # strips the ``## Amendments`` section — pinning over the amended text would be
    # tautological (both sides hashed from the same amended bytes).
    entry = {
        "id": f"ADR-{number}",
        "path": f"docs/decisions/adrs/adr-{number}-example.md",
        "pin": content_hash(pin_text if pin_text is not None else text),
    }
    if amendments is not None:
        entry["amendments"] = amendments
    return entry


def _adr_text(number: str, *, status: str = "accepted", body: str = "\n## Context\n\nThe decision body.\n") -> str:
    """The unamended ADR text ``_make_adr`` writes for ``(number, status, body)``,
    without touching disk. Used to compute a pin over body-only content so the
    amendment-stripping invariant is falsifiable."""
    return f"# ADR-{number}: Example {number}\n\n## Status\n\n{status}\n\n## Date\n\n2026-04-05\n{body}"


def _rule_ids(failures: list[PolicyFailure]) -> list[str]:
    return [failure.rule_id for failure in failures]


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_root, check=True, capture_output=True)


def _git_commit_all(repo_root: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo_root, check=True, capture_output=True, text=True)


def _git_add_all(repo_root: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True, capture_output=True, text=True)


def test_adr_pin_gate_passes_on_pinned_accepted_corpus(tmp_path: Path) -> None:
    adr_dir = _adr_dir(tmp_path)
    accepted_one = _make_adr(adr_dir, "001")
    accepted_two = _make_adr(adr_dir, "002")
    _make_adr(adr_dir, "003", status="proposed")  # proposed ADRs are not pinned
    _write_manifest(adr_dir, [_entry("001", accepted_one), _entry("002", accepted_two)])

    assert evaluate_adr_immutability(tmp_path) == []


def test_adr_pin_gate_flags_unrecorded_edit(tmp_path: Path) -> None:
    adr_dir = _adr_dir(tmp_path)
    original = _make_adr(adr_dir, "001")
    _write_manifest(adr_dir, [_entry("001", original)])
    # Edit the ADR body without updating the pin.
    _make_adr(adr_dir, "001", body="\n## Context\n\nA substantively different body.\n")

    failures = evaluate_adr_immutability(tmp_path)
    assert "adr-pin-stale" in _rule_ids(failures)


def test_adr_pin_gate_accepts_recorded_amendment(tmp_path: Path) -> None:
    adr_dir = _adr_dir(tmp_path)
    text = _make_adr(adr_dir, "001", amendment_rows=[("2026-06-07", "abc1234", "added a field")])
    # Pin over the *unamended* body. If canonical_content stops stripping the
    # ## Amendments section, the on-disk (amended) hash diverges from this pin and
    # the gate fires adr-pin-stale — so this assertion genuinely verifies the
    # "amendment records never change the pin" invariant rather than tautologically
    # hashing the same amended bytes on both sides.
    _write_manifest(
        adr_dir,
        [
            _entry(
                "001",
                text,
                pin_text=_adr_text("001"),
                amendments=[{"date": "2026-06-07", "ref": "abc1234", "summary": "added a field"}],
            )
        ],
    )

    # The pin is over canonical content (amendments excluded), so the recorded
    # amendment does not perturb it, and the manifest refs match the table 1:1.
    assert evaluate_adr_immutability(tmp_path) == []


def test_adr_pin_gate_flags_missing_pin(tmp_path: Path) -> None:
    adr_dir = _adr_dir(tmp_path)
    pinned = _make_adr(adr_dir, "001")
    _make_adr(adr_dir, "002")  # accepted but absent from the manifest
    _write_manifest(adr_dir, [_entry("001", pinned)])

    failures = evaluate_adr_immutability(tmp_path)
    assert "adr-pin-missing" in _rule_ids(failures)


def test_adr_pin_gate_flags_orphan_entry(tmp_path: Path) -> None:
    adr_dir = _adr_dir(tmp_path)
    proposed = _make_adr(adr_dir, "001", status="proposed")
    _write_manifest(adr_dir, [_entry("001", proposed)])  # pins a non-accepted ADR

    failures = evaluate_adr_immutability(tmp_path)
    assert "adr-pin-orphan" in _rule_ids(failures)


def test_adr_pin_gate_flags_amendment_record_mismatch(tmp_path: Path) -> None:
    adr_dir = _adr_dir(tmp_path)
    text = _make_adr(adr_dir, "001", amendment_rows=[("2026-06-07", "abc1234", "added a field")])
    _write_manifest(adr_dir, [_entry("001", text, amendments=[])])  # table row not mirrored in manifest

    failures = evaluate_adr_immutability(tmp_path)
    assert "adr-amendment-record-mismatch" in _rule_ids(failures)


def test_adr_pin_gate_rejects_unsupported_algorithm(tmp_path: Path) -> None:
    adr_dir = _adr_dir(tmp_path)
    text = _make_adr(adr_dir, "001")
    _write_manifest(adr_dir, [_entry("001", text)], algorithm="md5")

    failures = evaluate_adr_immutability(tmp_path)
    assert _rule_ids(failures) == ["adr-manifest-malformed"]


def test_adr_pin_gate_rejects_duplicate_id(tmp_path: Path) -> None:
    adr_dir = _adr_dir(tmp_path)
    text = _make_adr(adr_dir, "001")
    _write_manifest(adr_dir, [_entry("001", text), _entry("001", text)])

    failures = evaluate_adr_immutability(tmp_path)
    assert "adr-manifest-malformed" in _rule_ids(failures)


def test_adr_pin_gate_rejects_unsafe_path(tmp_path: Path) -> None:
    adr_dir = _adr_dir(tmp_path)
    _write_manifest(
        adr_dir,
        [{"id": "ADR-001", "path": "../outside-the-repo.md", "pin": "0" * 64}],
    )

    failures = evaluate_adr_immutability(tmp_path)
    assert "adr-manifest-path-unsafe" in _rule_ids(failures)


def test_adr_pin_gate_missing_manifest_fails_cleanly(tmp_path: Path) -> None:
    _adr_dir(tmp_path)
    failures = evaluate_adr_immutability(tmp_path)
    assert _rule_ids(failures) == ["adr-manifest-malformed"]


def test_adr_pin_gate_base_rev_flags_pin_bump_without_amendment(tmp_path: Path) -> None:
    adr_dir = _adr_dir(tmp_path)
    original = _make_adr(adr_dir, "001")
    _write_manifest(adr_dir, [_entry("001", original)])
    _init_git_repo(tmp_path)
    _git_commit_all(tmp_path, "base")

    # Edit the body AND bump the pin, but record no amendment.
    edited = _make_adr(adr_dir, "001", body="\n## Context\n\nA materially changed body.\n")
    _write_manifest(adr_dir, [_entry("001", edited)])

    failures = evaluate_adr_immutability(tmp_path, base_rev="HEAD")
    assert _rule_ids(failures) == ["adr-amendment-unrecorded"]


def test_adr_pin_gate_base_rev_accepts_recorded_amendment(tmp_path: Path) -> None:
    adr_dir = _adr_dir(tmp_path)
    original = _make_adr(adr_dir, "001")
    _write_manifest(adr_dir, [_entry("001", original)])
    _init_git_repo(tmp_path)
    _git_commit_all(tmp_path, "base")

    changed_body = "\n## Context\n\nA materially changed body.\n"
    edited = _make_adr(
        adr_dir,
        "001",
        body=changed_body,
        amendment_rows=[("2026-06-08", "def5678", "changed the body")],
    )
    # Pin over the unamended edited body so the recorded amendment is what makes
    # the change legitimate; a canonical_content regression that stops stripping
    # amendments would diverge this pin from the on-disk hash and fail the test.
    _write_manifest(
        adr_dir,
        [
            _entry(
                "001",
                edited,
                pin_text=_adr_text("001", body=changed_body),
                amendments=[{"date": "2026-06-08", "ref": "def5678", "summary": "changed the body"}],
            )
        ],
    )

    assert evaluate_adr_immutability(tmp_path, base_rev="HEAD") == []


def test_adr_pin_gate_base_rev_allows_supersession(tmp_path: Path) -> None:
    adr_dir = _adr_dir(tmp_path)
    original = _make_adr(adr_dir, "001")
    _write_manifest(adr_dir, [_entry("001", original)])
    _init_git_repo(tmp_path)
    _git_commit_all(tmp_path, "base")

    # Supersede ADR-001: status changes (so it leaves the accepted/pinned set)
    # and a new superseding ADR-002 is added; drop ADR-001 from the manifest.
    _make_adr(adr_dir, "001", status="superseded by ADR-002")
    superseding = _make_adr(adr_dir, "002")
    _write_manifest(adr_dir, [_entry("002", superseding)])

    assert evaluate_adr_immutability(tmp_path, base_rev="HEAD") == []


def test_adr_pin_gate_staged_flags_pin_bump_without_amendment(tmp_path: Path) -> None:
    # The pre-commit invocation: ``staged=True`` compares the git *index*
    # (``git show :<path>``) against HEAD, a distinct code path from ``base_rev``
    # (which reads the working tree from disk). A staged pin bump without an
    # amendment must be flagged just like the base_rev case.
    adr_dir = _adr_dir(tmp_path)
    original = _make_adr(adr_dir, "001")
    _write_manifest(adr_dir, [_entry("001", original)])
    _init_git_repo(tmp_path)
    _git_commit_all(tmp_path, "base")

    edited = _make_adr(adr_dir, "001", body="\n## Context\n\nA materially changed body.\n")
    _write_manifest(adr_dir, [_entry("001", edited)])
    _git_add_all(tmp_path)

    failures = evaluate_adr_immutability(tmp_path, staged=True)
    assert _rule_ids(failures) == ["adr-amendment-unrecorded"]


def test_adr_pin_gate_staged_accepts_recorded_amendment(tmp_path: Path) -> None:
    # A staged edit that records its amendment (and bumps the pin) passes — proving
    # the staged branch does not over-fire on legitimately recorded changes.
    adr_dir = _adr_dir(tmp_path)
    original = _make_adr(adr_dir, "001")
    _write_manifest(adr_dir, [_entry("001", original)])
    _init_git_repo(tmp_path)
    _git_commit_all(tmp_path, "base")

    changed_body = "\n## Context\n\nA materially changed body.\n"
    edited = _make_adr(
        adr_dir,
        "001",
        body=changed_body,
        amendment_rows=[("2026-06-08", "def5678", "changed the body")],
    )
    # Pin over the unamended edited body (see recorded-amendment tests above): the
    # green result must depend on canonical_content actually stripping amendments.
    _write_manifest(
        adr_dir,
        [
            _entry(
                "001",
                edited,
                pin_text=_adr_text("001", body=changed_body),
                amendments=[{"date": "2026-06-08", "ref": "def5678", "summary": "changed the body"}],
            )
        ],
    )
    _git_add_all(tmp_path)

    assert evaluate_adr_immutability(tmp_path, staged=True) == []


def test_adr_pin_gate_staged_sources_head_text_from_index_not_disk(tmp_path: Path) -> None:
    # Pins down that ``head_text`` in the staged branch comes from the git *index*
    # (``git show :<path>``), not the working tree. We stage an unrecorded ADR edit
    # (with a bumped pin) and then restore the working-tree file to the committed
    # original. Now the index holds the edit while disk == HEAD, so:
    #   * the pin-hash check (which reads disk) sees the original and stays green;
    #   * the corpus checks all pass against the staged pin too, so evaluation
    #     reaches the staged unrecorded-edit detector;
    #   * only an index-sourced ``head_text`` can observe the edit and flag it.
    # If the detector read disk instead, head_text would equal base_text and the
    # edit would silently pass — exactly the false exit-0 this test forbids.
    adr_dir = _adr_dir(tmp_path)
    original = _make_adr(adr_dir, "001")
    _write_manifest(adr_dir, [_entry("001", original)])
    _init_git_repo(tmp_path)
    _git_commit_all(tmp_path, "base")

    # Stage the edited ADR. The bumped pin must match the *index* (edited) content
    # so the disk-based pin-hash check will be green once we restore disk below.
    edited = _make_adr(adr_dir, "001", body="\n## Context\n\nA materially changed body.\n")
    _git_add_all(tmp_path)  # index now holds the edited ADR

    # Restore the working tree to the committed original while keeping the index
    # edit. Pin stays over the original content so the disk-read pin-hash is green.
    write_text(adr_dir / "adr-001-example.md", original)
    _write_manifest(adr_dir, [_entry("001", original)])

    failures = evaluate_adr_immutability(tmp_path, staged=True)
    assert _rule_ids(failures) == ["adr-amendment-unrecorded"]


def test_amendment_refs_parses_table_rows() -> None:
    text = (
        "# ADR-001: Example\n\n## Status\n\naccepted\n\n## Date\n\n2026-04-05\n\n"
        + AMENDMENTS_TABLE_HEADER
        + "| 2026-06-07 | abc1234 | first |\n| 2026-06-08 | def5678 | second |\n"
    )
    assert amendment_refs(text) == ["abc1234", "def5678"]


def test_amendment_parsing_ignores_fenced_examples(tmp_path: Path) -> None:
    # An ADR that documents the amendment format (like ADR-059) embeds a
    # ``## Amendments`` example inside a fenced code block. That example must
    # not be read as a real section, or the ADR's pin would truncate and a
    # bogus amendment would be parsed from the example row.
    adr_dir = _adr_dir(tmp_path)
    text = (
        "# ADR-001: Policy\n\n## Status\n\naccepted\n\n## Date\n\n2026-04-05\n\n"
        "## Decision\n\nRecord amendments like:\n\n"
        "```markdown\n## Amendments\n\n| Date | Commit/PR | Summary |\n"
        "|------|-----------|---------|\n| 2026-06-07 | deadbee | example |\n```\n\n"
        "## Consequences\n\nDone.\n"
    )
    write_text(adr_dir / "adr-001-example.md", text)
    assert amendment_refs(text) == []
    _write_manifest(adr_dir, [_entry("001", text)])  # _entry hashes full text; no amendments

    assert evaluate_adr_immutability(tmp_path) == []


def test_canonical_content_detects_boundary_blank_line_edits() -> None:
    # ADR-059 declares only per-line trailing whitespace and the file-final
    # newline as normalized. A leading or interior blank line is significant, so
    # adding one must change the canonical hash; toggling the final newline must
    # not. This keeps the pin from silently absorbing boundary blank-line edits.
    base = "# ADR-001: Example\n\n## Context\n\nThe body.\n"
    leading_blank = "\n" + base
    interior_blank = "# ADR-001: Example\n\n\n## Context\n\nThe body.\n"
    no_final_newline = base.rstrip("\n")
    trailing_blank = base + "\n"

    assert canonical_content(base) != canonical_content(leading_blank)
    assert canonical_content(base) != canonical_content(interior_blank)
    assert canonical_content(base) == canonical_content(no_final_newline)
    assert canonical_content(base) == canonical_content(trailing_blank)


def test_adr_pin_gate_base_rev_flags_boundary_blank_line_edit(tmp_path: Path) -> None:
    adr_dir = _adr_dir(tmp_path)
    original = _make_adr(adr_dir, "001")
    _write_manifest(adr_dir, [_entry("001", original)])
    _init_git_repo(tmp_path)
    _git_commit_all(tmp_path, "base")

    # Prepend a blank line (a boundary-only edit) and bump the pin, no amendment.
    edited = "\n" + original
    write_text(adr_dir / "adr-001-example.md", edited)
    _write_manifest(adr_dir, [_entry("001", edited)])

    failures = evaluate_adr_immutability(tmp_path, base_rev="HEAD")
    assert _rule_ids(failures) == ["adr-amendment-unrecorded"]
