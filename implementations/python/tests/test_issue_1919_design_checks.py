"""Issue #1919: Ground Control design check commands.

The acceptance adapter runs as a subprocess, because it starts its own pytest
session. The cases that it observes are in tests/fixtures/design_acceptance.
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from tools import design_acceptance, design_wiring
from tools.policy.common import PolicyFailure
from tools.policy.import_graph import ImportAnalysis
from tools.policy.repo_policy import evaluate_repo_policy

REPO_ROOT = Path(__file__).resolve().parents[3]
ADAPTER = REPO_ROOT / "tools" / "design_acceptance.py"
CASES = "implementations/python/tests/fixtures/design_acceptance/cases.py"
COLLECTION_ERROR = "implementations/python/tests/fixtures/design_acceptance/collection_error.py"


def _run_adapter(stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed interpreter and repository script.
        [sys.executable, str(ADAPTER)],
        input=stdin,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _observe(test_file: str, test_name: str) -> dict[str, object]:
    completed = _run_adapter(json.dumps({"test_file": test_file, "test_name": test_name}))
    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.splitlines()
    assert len(lines) == 1, completed.stdout
    observation = json.loads(lines[0])
    assert set(observation) == {"test_name", "status", "matches", "message"}
    assert observation["test_name"] == test_name
    return observation


def _design() -> dict[str, str]:
    return _configuration()["workflow"]["design"]


def _configuration() -> dict:
    return yaml.safe_load((REPO_ROOT / ".ground-control.yaml").read_text(encoding="utf-8"))


def _adr_status(path: str) -> str:
    lines = [line.strip() for line in (REPO_ROOT / path).read_text(encoding="utf-8").splitlines()]
    for index, line in enumerate(lines):
        if line.lower().startswith("**status:**"):
            return line.split(":**", 1)[1].strip().lower()
        if line == "## Status":
            return next(item for item in lines[index + 1 :] if item).lower()
    raise AssertionError(f"{path} has no status")


def test_configuration_names_real_commands_and_existing_references() -> None:
    configuration = _configuration()
    design = configuration["workflow"]["design"]

    assert configuration["schema_version"] == 2
    assert set(design) == {"compile_command", "structural_command", "wiring_command", "acceptance_command"}
    for script in ("tools/check_repo_policy.py", "tools/design_wiring.py", "tools/design_acceptance.py"):
        assert script in " ".join(design.values())
        assert (REPO_ROOT / script).is_file()
    for test_path in re.findall(r"tests/test_\w+\.py", design["structural_command"]):
        assert (REPO_ROOT / "implementations" / "python" / test_path).is_file()
    paths = [module["path"] for module in configuration["architecture"]["modules"]]
    assert len(paths) == len(set(paths))
    for module in configuration["architecture"]["modules"]:
        assert module["path"] == "." or (REPO_ROOT / module["path"]).exists(), module["path"]
        for reference in module["implementations"]:
            assert (REPO_ROOT / reference).is_file(), reference
        for reference in module["adrs"]:
            assert reference.startswith("docs/decisions/adrs/adr-"), reference
            assert _adr_status(reference) == "accepted", reference


def test_design_commands_run_from_locked_environments_without_credentials() -> None:
    for name, command in _design().items():
        uv_runs = command.count("uv run")
        assert uv_runs >= 1, name
        assert command.count("--frozen --no-sync") == uv_runs, name
        assert not re.search(r"(?i)token|secret|password|\.env\b|curl|wget|pip install|uv sync", command), name
    assert "-p no:cacheprovider" in _design()["structural_command"]
    assert 'PYTHONPYCACHEPREFIX="$d"' in _design()["compile_command"]
    assert "trap 'rm -rf \"$d\"' EXIT" in _design()["compile_command"]


def test_adapter_distinguishes_every_observation_status() -> None:
    expected = [
        ("test_failing_assertion", "failed", 1),
        ("test_passing", "passed", 1),
        ("test_absent", "missing", 0),
        ("test_skipped", "skipped", 1),
        ("test_expected_failure", "skipped", 1),
        ("test_integration_marked", "skipped", 0),
        ("test_name_error", "broken", 1),
        ("test_setup_error", "broken", 1),
        ("test_duplicate", "missing", 2),
        ("TestFirst::test_duplicate", "passed", 1),
        ("test_parametrized[1]", "passed", 1),
        ("test_parametrized", "missing", 0),
    ]

    observed = [(name, *_status(_observe(CASES, name))) for name, _, _ in expected]

    assert observed == expected


def _status(observation: dict[str, object]) -> tuple[object, object]:
    return observation["status"], observation["matches"]


def test_module_map_covers_every_tracked_area() -> None:
    modules = {module["path"] for module in _configuration()["architecture"]["modules"]}
    tracked = subprocess.run(  # noqa: S603 -- fixed git command.
        ["git", "ls-files"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    packages = REPO_ROOT / "implementations" / "python" / "packages"

    assert "." in modules
    for package in sorted(path.name for path in packages.iterdir() if (path / "__init__.py").is_file()):
        assert f"implementations/python/packages/{package}" in modules, package
    for area in ("contracts", "specs", "docs", "examples", "tools", ".github", "implementations/python/tests"):
        assert area in modules, area
        assert any(path.startswith(f"{area}/") for path in tracked), area


def test_existing_workflow_gates_remain_configured() -> None:
    configuration = _configuration()
    workflow = configuration["workflow"]

    assert "pre-commit run" in workflow["precommit_command"]
    assert "make policy" in workflow["policy_command"]
    assert "verify-fast-feedback" in workflow["test_command"]
    assert workflow["codex_review"] == {"pre_push_cap": 1}
    sonar = dict(
        line.split("=", 1)
        for line in (REPO_ROOT / "sonar-project.properties").read_text(encoding="utf-8").splitlines()
        if line.startswith(("sonar.projectKey=", "sonar.organization="))
    )
    assert configuration["sonarcloud"] == {
        "project_key": sonar["sonar.projectKey"],
        "organization": sonar["sonar.organization"],
    }
    assert configuration["rules"] == {"plan_rules": ".gc/plan-rules.md"}


def test_readme_links_the_design_check_instructions() -> None:
    page = "docs/develop/ground-control-design-checks.md"
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert f"https://github.com/OpenRAE/rae/blob/main/{page}" in readme
    assert "(develop/ground-control-design-checks.md)" in (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    instructions = (REPO_ROOT / page).read_text(encoding="utf-8")
    for name in _design():
        assert f"`{name}`" in instructions, name


def test_adapter_keeps_the_assertion_message_of_a_failing_case() -> None:
    observation = _observe(CASES, "test_failing_assertion")

    assert "the acceptance behavior is missing" in str(observation["message"])


def test_adapter_reports_a_file_that_does_not_collect_as_broken() -> None:
    observation = _observe(COLLECTION_ERROR, "test_unreachable")

    assert observation["status"] == "broken"
    assert "raes_missing_design_acceptance_module" in str(observation["message"])


INVALID_REQUESTS = [
    "not json",
    "[]",
    json.dumps({"test_file": CASES}),
    json.dumps({"test_file": CASES, "test_name": "test_passing", "extra": 1}),
    json.dumps({"test_file": str(REPO_ROOT / CASES), "test_name": "test_passing"}),
    json.dumps({"test_file": "implementations/python/../../" + CASES, "test_name": "test_passing"}),
    json.dumps({"test_file": "tools/design_acceptance.py", "test_name": "test_passing"}),
    json.dumps({"test_file": "implementations/python/tests/absent.py", "test_name": "test_passing"}),
    json.dumps({"test_file": "implementations/python/pyproject.toml", "test_name": "test_passing"}),
    json.dumps({"test_file": CASES, "test_name": ""}),
    json.dumps({"test_file": CASES, "test_name": 1}),
    json.dumps({"test_file": CASES, "test_name": "x" * (design_acceptance.MAX_INPUT_BYTES + 1)}),
]


def test_adapter_refuses_an_invalid_request_with_a_nonzero_exit() -> None:
    completed = _run_adapter(INVALID_REQUESTS[0])

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr.startswith("design-acceptance: ")


@pytest.mark.parametrize("stdin", INVALID_REQUESTS)
def test_request_reader_refuses_an_invalid_request(stdin: str) -> None:
    with pytest.raises(design_acceptance.InvalidInputError):
        design_acceptance.read_request(stdin)


def test_request_reader_returns_the_resolved_file_and_exact_name() -> None:
    request = json.dumps({"test_file": CASES, "test_name": "TestFirst::test_duplicate"})

    assert design_acceptance.read_request(request) == (REPO_ROOT / CASES, "TestFirst::test_duplicate")


@pytest.fixture
def isolated_import_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep a nested pytest session from leaving modules or import paths behind."""

    monkeypatch.setattr(sys, "path", list(sys.path))
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        del sys.modules[name]


def _main_in_process(
    request: dict[str, str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str, str]:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))
    status = design_acceptance.main()
    captured = capsys.readouterr()
    return status, captured.out, captured.err


@pytest.mark.usefixtures("isolated_import_state")
def test_adapter_main_reports_observations_in_process(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    expected = {
        "test_failing_assertion": ("failed", 1),
        "test_passing": ("passed", 1),
        "test_skipped": ("skipped", 1),
        "test_expected_failure": ("skipped", 1),
        "test_integration_marked": ("skipped", 0),
        "test_setup_error": ("broken", 1),
        "test_duplicate": ("missing", 2),
        "test_absent": ("missing", 0),
    }
    observed = {}
    for name in expected:
        status, out, _ = _main_in_process({"test_file": CASES, "test_name": name}, monkeypatch, capsys)
        assert status == 0
        observed[name] = _status(json.loads(out))
    broken_status, broken_out, _ = _main_in_process(
        {"test_file": COLLECTION_ERROR, "test_name": "test_unreachable"}, monkeypatch, capsys
    )

    assert observed == expected
    assert broken_status == 0
    assert _status(json.loads(broken_out)) == ("broken", 0)


def test_adapter_main_exits_nonzero_when_pytest_cannot_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(design_acceptance.pytest, "main", lambda args, plugins: pytest.ExitCode.USAGE_ERROR)

    status, out, err = _main_in_process({"test_file": CASES, "test_name": "test_passing"}, monkeypatch, capsys)

    assert status == 1
    assert out == ""
    assert "pytest stopped with exit code 4" in err


def test_adapter_main_exits_nonzero_for_an_invalid_request(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    status, out, err = _main_in_process({"test_file": CASES}, monkeypatch, capsys)

    assert status == 1
    assert out == ""
    assert err.startswith("design-acceptance: ")


def test_adapter_refuses_a_symlinked_test_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "implementations" / "python"
    project.mkdir(parents=True)
    (project / "real.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    (project / "link.py").symlink_to(project / "real.py")
    monkeypatch.setattr(design_acceptance, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(design_acceptance, "PROJECT_ROOT", project)

    with pytest.raises(design_acceptance.InvalidInputError, match="regular Python file"):
        design_acceptance.resolve_test_file("implementations/python/link.py")
    assert design_acceptance.resolve_test_file("implementations/python/real.py") == project / "real.py"


def test_adapter_bounds_a_long_message_to_its_head_and_tail() -> None:
    text = "h" * 5000 + "t" * 5000

    bounded = design_acceptance.bounded(text)

    assert len(bounded) <= design_acceptance.MAX_MESSAGE_CHARS
    assert bounded.startswith("h")
    assert bounded.endswith("t")
    assert design_acceptance.bounded("short") == "short"


@pytest.mark.parametrize(
    ("when", "exception_type", "status"),
    [
        ("call", AssertionError, "failed"),
        ("call", ValueError, "failed"),
        ("call", ImportError, "broken"),
        ("call", ModuleNotFoundError, "broken"),
        ("call", NameError, "broken"),
        ("call", None, "broken"),
        ("setup", AssertionError, "broken"),
        ("teardown", AssertionError, "broken"),
    ],
)
def test_failure_classification(when: str, exception_type: type[BaseException] | None, status: str) -> None:
    assert design_acceptance.classify_failure(when, exception_type) == status


def test_wiring_counts_edges_between_distinct_components() -> None:
    imports = [
        ("raes_runtime.a", "raes_contracts.b"),
        ("raes_runtime.c", "raes_contracts.d"),
        ("raes_runtime.a", "raes_runtime.c"),
        ("raes.x.y", "raes_contracts.b"),
    ]

    assert design_wiring.component_edges(imports, 1) == Counter(
        {("raes_runtime", "raes_contracts"): 2, ("raes", "raes_contracts"): 1}
    )
    assert design_wiring.component_edges(imports, 2)[("raes_runtime.a", "raes_runtime.c")] == 1
    with pytest.raises(design_wiring.InvalidInputError):
        design_wiring.component_edges(imports, 0)


def test_wiring_renders_a_sorted_mermaid_flowchart() -> None:
    rendered = design_wiring.render_mermaid(
        {"raes_runtime", "raes_contracts", "raes_cli"}, Counter({("raes_runtime", "raes_contracts"): 3})
    )

    assert rendered.splitlines() == [
        "graph TD",
        '    n0["raes_cli"]',
        '    n1["raes_contracts"]',
        '    n2["raes_runtime"]',
        "    n2 -->|3| n1",
    ]


def test_structural_check_set_runs_only_the_structural_ratchet(tmp_path: Path) -> None:
    from test_repo_policy_tools import setup_policy_repo

    repo_root = setup_policy_repo(tmp_path)
    ratchet = PolicyFailure("structural-ratchet", "cycle", "tools/policy/import_contracts.toml")

    def by_file_runner(input_document: dict) -> list[PolicyFailure]:
        raise AssertionError("the structural check set must not run the by-file checks")

    failures = evaluate_repo_policy(
        repo_root,
        ["contracts/schemas/backend-manifest/schema.json"],
        check_set="structural",
        structural_runner=by_file_runner,
        ratchet_runner=lambda policy: [ratchet],
    )

    assert failures == [ratchet]


def test_wiring_main_prints_the_package_graph(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured_roots: list[tuple[str, ...]] = []

    def analyzer(packages_roots, config_path, *, root_packages, exclude_type_checking_imports):
        captured_roots.append(tuple(root_packages))
        assert config_path == REPO_ROOT / "tools" / "policy" / "import_contracts.toml"
        assert exclude_type_checking_imports is True
        return ImportAnalysis(
            modules=frozenset({"raes_runtime.a", "raes_contracts.b"}),
            imports=frozenset({("raes_runtime.a", "raes_contracts.b")}),
            contracts=(),
            versions={},
        )

    monkeypatch.setattr(design_wiring, "analyze_imports", analyzer)

    assert design_wiring.main(["--depth", "1"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "graph TD",
        '    n0["raes_contracts"]',
        '    n1["raes_runtime"]',
        "    n1 -->|1| n0",
    ]
    assert "raes_contracts" in captured_roots[0]
