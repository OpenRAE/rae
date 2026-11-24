"""Exercise shared nox prose selection with the real pinned Vale."""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from raes_contracts.errors import InvalidInputError, OperationalError

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def prose_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from tools.vale_tool import ensure_vale

    monkeypatch.setitem(sys.modules, "nox", SimpleNamespace(Session=object))
    for name in ("tools.nox_support.runner", "tools.nox_support.test_lanes"):
        monkeypatch.setitem(sys.modules, name, None)
        monkeypatch.delitem(sys.modules, name)
    lanes = importlib.import_module("tools.nox_support.test_lanes")
    binary = ensure_vale(ROOT)
    monkeypatch.setattr(lanes, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(lanes, "ensure_vale", lambda _root: binary)
    shutil.copy(ROOT / ".vale.ini", tmp_path)
    shutil.copytree(ROOT / "styles", tmp_path / "styles")
    for catalog in ("docs/decisions/adrs/adr-index.yaml", "tools/policy/historical_identity_records.json"):
        target = tmp_path / catalog
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / catalog, target)
    (tmp_path / "home").mkdir()
    env = {**os.environ, "HOME": str(tmp_path / "home"), "GIT_CONFIG_NOSYSTEM": "1"}
    state = {"result": None, "logs": [], "calls": []}

    def invoke(_session, *args, **kwargs):
        result = subprocess.run(
            args, cwd=tmp_path, env={**env, **kwargs.get("env", {})}, text=True, capture_output=True
        )
        state["calls"].append(args)
        state["result"] = result
        if result.returncode:
            raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)

    monkeypatch.setattr(lanes, "_run", invoke)

    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=tmp_path, env=env, text=True).strip()

    git("init", "-q")
    git("config", "user.name", "Documentation tests")
    git("config", "user.email", "tests@example.invalid")
    git("config", "commit.gpgsign", "false")
    (tmp_path / "unchanged.md").write_text("# Legacy Page\n\nSimply utilize this tool.\n")
    git("add", ".")
    git("commit", "-qm", "Initial fixture")
    base = git("rev-parse", "HEAD")

    def check(posargs: list[str]):
        state.update(result=None, logs=[], calls=[])
        session = SimpleNamespace(posargs=posargs, log=state["logs"].append)
        reporter = lanes.SessionReporter(session, "docs-prose")
        try:
            lanes._run_docs_prose(session, reporter)
        except subprocess.CalledProcessError:
            pass
        except (InvalidInputError, OperationalError) as exc:
            return subprocess.CompletedProcess([], 2, "", str(exc))
        return state["result"] or subprocess.CompletedProcess([], 0, "\n".join(state["logs"]), "")

    def run(
        path: str,
        text: str,
        *,
        base_rev: str | None = None,
        posargs: list[str] | None = None,
        commit: bool = True,
        stage: bool = True,
    ):
        page = tmp_path / path
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(text)
        if stage:
            git("add", "--", path)
        if commit:
            git("commit", "-qm", "Update fixture", "--allow-empty")
        return check(posargs if posargs is not None else ["--base-rev", base_rev or base])

    return SimpleNamespace(run=run, check=check, git=git, root=tmp_path, lanes=lanes, state=state)


@pytest.mark.parametrize(
    "path",
    [
        "docs/public/guide.md",
        "docs/public/api/index.rst",
        "examples/a guide.md",
        "-guide.md",
        "docs/CHANGELOG.md",
        "docs/a\npage.md",
    ],
)
@pytest.mark.integration
def test_changed_prose_check_catches_and_clears_style_violations(prose_check, path: str) -> None:
    heading = "Check a file\n============\n" if path.endswith(".rst") else "# Check a file\n"
    bad = prose_check.run(path, heading + "\nUtilize the tool to check a file.\n")
    assert bad.returncode != 0, bad.stdout + bad.stderr
    assert "RAES.PlainWords" in bad.stdout, bad.stdout + bad.stderr
    good = prose_check.run(path, heading + "\nUse the tool to check a file.\n")
    assert good.returncode == 0, good.stdout + good.stderr


@pytest.mark.integration
def test_changed_prose_check_runs_without_personal_skills(prose_check) -> None:
    result = prose_check.run("docs/explain/task.md", "# Check a file\n\nCheck the file.\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "unchanged.md" not in result.stdout


@pytest.mark.integration
def test_changed_prose_check_preserves_literal_content(prose_check) -> None:
    result = prose_check.run(
        "docs/explain/task.md", "# Check a file\n\nCheck the file.\n\n```text\nSimply utilize this tool.\n```\n"
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration
def test_changed_prose_check_leaves_build_and_hooks_unchanged(prose_check) -> None:
    result = prose_check.run("implementations/data.json", "{}\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not prose_check.state["calls"]


@pytest.mark.integration
def test_changed_prose_check_propagates_git_failure(prose_check) -> None:
    result = prose_check.run("docs/task.md", "# Check a file\n\nCheck the file.\n", base_rev="missing-revision")
    assert result.returncode != 0
    assert "git diff failed" in result.stderr


@pytest.mark.parametrize(
    "path",
    [
        "CHANGELOG.md",
        "THIRD_PARTY_NOTICES.md",
        "docs/decisions/adrs/adr-014-nox-as-canonical-verification-graph.md",
        "docs/research/experiment-core/issue-233-exp-707-capture-spec-preflight-guardrails.md",
    ],
)
@pytest.mark.integration
def test_changed_prose_check_preserves_release_and_legal_records(prose_check, path: str) -> None:
    result = prose_check.run(path, "# Exact Record\n\nSimply utilize this tool.\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not prose_check.state["calls"]
    assert path in result.stdout
    assert "manual" in result.stdout.lower()


@pytest.mark.parametrize(
    "catalog", ["docs/decisions/adrs/adr-index.yaml", "tools/policy/historical_identity_records.json"]
)
@pytest.mark.integration
def test_changed_prose_check_rejects_malformed_protection_catalog(prose_check, catalog: str) -> None:
    (prose_check.root / catalog).write_text("{}")
    result = prose_check.run("docs/task.md", "# Check a file\n\nCheck the file.\n")
    assert result.returncode != 0
    assert "catalog" in result.stderr
    assert not prose_check.state["calls"]


@pytest.mark.integration
def test_changed_prose_check_accepts_explicit_paths(prose_check) -> None:
    result = prose_check.run("docs/task.md", "# Check a file\n\nUtilize the tool.\n", posargs=["docs/task.md"])
    assert result.returncode != 0
    assert "RAES.PlainWords" in result.stdout


@pytest.mark.integration
def test_shared_docs_lane_runs_prose_check(prose_check, monkeypatch: pytest.MonkeyPatch) -> None:
    lanes = prose_check.lanes
    calls = []
    monkeypatch.setattr(lanes, "DOCS_BUILD_ROOT", prose_check.root / "build")
    monkeypatch.setattr(lanes, "PUBLIC_DOCS_ROOT", prose_check.root / "docs/public")
    monkeypatch.setattr(lanes, "_sync_project", lambda _session: None)
    monkeypatch.setattr(lanes, "_run_project_python", lambda *_a, **_k: None)
    monkeypatch.setattr(lanes, "_run", lambda *_a, **_k: None)
    monkeypatch.setattr(lanes, "_run_docs_prose", lambda session, _reporter: calls.append(session.posargs))
    session = SimpleNamespace(posargs=["--base-rev", "verified-base"], log=lambda _text: None)
    lanes._run_docs(session, lanes.SessionReporter(session, "docs-local"), include_external_links=False)
    assert calls == [["--base-rev", "verified-base"]]


@pytest.mark.integration
def test_changed_prose_check_refuses_paths_outside_repository(prose_check) -> None:
    outside = prose_check.root.parent / "outside.md"
    outside.write_text("# Check a file\n\nUtilize the tool.\n")
    result = prose_check.run("docs/task.md", "# Check a file\n\nCheck the file.\n", posargs=["../outside.md"])
    assert result.returncode != 0
    assert "unsafe" in result.stderr
    assert not prose_check.state["calls"]


@pytest.mark.parametrize(("posargs", "stage"), [(["--staged"], True), ([], True), ([], False)])
@pytest.mark.integration
def test_changed_prose_check_selects_staged_working_and_untracked(prose_check, posargs: list[str], stage: bool) -> None:
    result = prose_check.run(
        "docs/task.md", "# Check a file\n\nUtilize the tool.\n", posargs=posargs, commit=False, stage=stage
    )
    assert result.returncode != 0
    assert "RAES.PlainWords" in result.stdout


@pytest.mark.integration
def test_changed_prose_check_lints_rename_destination(prose_check) -> None:
    prose_check.run("docs/old.md", "# Check a file\n\nUtilize the tool.\n")
    before = prose_check.git("rev-parse", "HEAD")
    prose_check.git("mv", "docs/old.md", "docs/new.md")
    prose_check.git("commit", "-qm", "Rename fixture")
    result = prose_check.check(["--base-rev", before])
    assert result.returncode != 0
    assert "RAES.PlainWords" in result.stdout
    assert "new.md" in result.stdout


@pytest.mark.integration
def test_changed_prose_check_ignores_deleted_paths(prose_check) -> None:
    prose_check.run("docs/old.md", "# Check a file\n\nUtilize the tool.\n")
    before = prose_check.git("rev-parse", "HEAD")
    prose_check.git("rm", "docs/old.md")
    prose_check.git("commit", "-qm", "Delete fixture")
    result = prose_check.check(["--base-rev", before])
    assert result.returncode == 0, result.stdout + result.stderr
    assert not prose_check.state["calls"]


@pytest.mark.integration
def test_changed_prose_check_does_not_exempt_operational_bindings(prose_check) -> None:
    catalog = prose_check.root / "tools/policy/historical_identity_records.json"
    data = json.loads(catalog.read_text())
    data["operational_bindings"].append(
        {
            "path": "docs/current.md",
            "binding_class": "external-service-project-key",
            "rationale": "Fixture binding",
            "occurrences": 1,
            "content_sha256": "0" * 64,
        }
    )
    catalog.write_text(json.dumps(data))
    result = prose_check.run("docs/current.md", "# Check a file\n\nUtilize the tool.\n")
    assert result.returncode != 0
    assert "RAES.PlainWords" in result.stdout


@pytest.mark.integration
def test_changed_prose_check_refuses_external_symlinks(prose_check) -> None:
    outside = prose_check.root.parent / "outside.md"
    outside.write_text("# Check a file\n\nUtilize the tool.\n")
    link = prose_check.root / "docs/link.md"
    link.parent.mkdir(exist_ok=True)
    link.symlink_to(outside)
    result = prose_check.run("docs/link.md", outside.read_text())
    assert result.returncode != 0
    assert "unsafe" in result.stderr
    assert not prose_check.state["calls"]


@pytest.mark.integration
def test_changed_prose_check_rejects_unsafe_adr_catalog_paths(prose_check) -> None:
    catalog = prose_check.root / "docs/decisions/adrs/adr-index.yaml"
    data = yaml.safe_load(catalog.read_text())
    data["adrs"][0]["path"] = "../outside.md"
    catalog.write_text(yaml.safe_dump(data))
    result = prose_check.run("docs/task.md", "# Check a file\n\nCheck the file.\n")
    assert result.returncode != 0
    assert "catalog" in result.stderr
    assert not prose_check.state["calls"]


@pytest.mark.parametrize("content", [b"adrs: [", b"\xff", None])
@pytest.mark.integration
def test_changed_prose_check_reports_unreadable_adr_catalog(prose_check, content: bytes | None) -> None:
    catalog = prose_check.root / "docs/decisions/adrs/adr-index.yaml"
    if content is None:
        catalog.unlink()
    else:
        catalog.write_bytes(content)
    result = prose_check.run("docs/task.md", "# Check a file\n\nCheck the file.\n")
    assert result.returncode != 0
    assert "catalog" in result.stderr
    assert not prose_check.state["calls"]


@pytest.mark.integration
def test_changed_prose_check_uses_selected_docs_environment(prose_check, monkeypatch: pytest.MonkeyPatch) -> None:
    environment = prose_check.root / "isolated"
    (environment / "bin").mkdir(parents=True)
    marker = prose_check.root / "parser-used"
    actual = str(ROOT / "implementations/python/.venv/bin/rst2html")
    parser = environment / "bin/rst2html"
    parser.write_text(
        f"#!{sys.executable}\nimport os,sys\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('used')\n"
        f"os.execv({actual!r}, [{actual!r}, *sys.argv[1:]])\n"
    )
    parser.chmod(0o755)
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(environment))
    result = prose_check.run("docs/task.rst", "Check a file\n============\n\nCheck the file.\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert marker.is_file(), "Vale must use docutils from the selected frozen docs environment"


def test_canonical_ci_passes_verified_base_to_shared_docs_lane(tmp_path: Path) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/canonical-verification.yml").read_text())
    step = next(
        s for s in workflow["jobs"]["checks"]["steps"] if s.get("name") == "Run deterministic documentation checks"
    )
    assert step["env"]["BASE_REV"] == "${{ steps.commit.outputs.base_rev }}"
    binary = tmp_path / "uv"
    binary.write_text("#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n")
    binary.chmod(0o755)
    result = subprocess.run(
        ["bash", "-c", step["run"]],
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "BASE_REV": "verified-base"},
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout)[-7:] == [
        "-f",
        "noxfile.py",
        "-s",
        "docs-local",
        "--",
        "--base-rev",
        "verified-base",
    ]


@pytest.mark.integration
def test_full_verification_forwards_selection_to_docs_lane(prose_check) -> None:
    graph = importlib.import_module("tools.nox_support.graph")
    lanes = graph._verification_lanes(
        posargs=["--base-rev", "verified-base"], coverage_dir=prose_check.root / "coverage", include_policy=False
    )
    docs = next(lane for lane in lanes if lane.nox_session == "docs-local")
    assert docs.posargs == ("--base-rev", "verified-base")
