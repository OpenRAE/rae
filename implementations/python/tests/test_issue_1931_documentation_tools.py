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
from tools.vale_tool import ensure_vale

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.integration


@pytest.fixture
def prose_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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

    def run(path: str, text: str, *, base_rev: str | None = None, posargs: list[str] | None = None):
        page = tmp_path / path
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(text)
        git("add", "--", path)
        git("commit", "-qm", "Update fixture", "--allow-empty")
        state.update(result=None, logs=[], calls=[])
        session = SimpleNamespace(
            posargs=posargs if posargs is not None else ["--base-rev", base_rev or base], log=state["logs"].append
        )
        reporter = lanes.SessionReporter(session, "docs-prose")
        try:
            lanes._run_docs_prose(session, reporter)
        except subprocess.CalledProcessError:
            pass
        except (InvalidInputError, OperationalError) as exc:
            return subprocess.CompletedProcess([], 2, "", str(exc))
        return state["result"] or subprocess.CompletedProcess([], 0, "\n".join(state["logs"]), "")

    return SimpleNamespace(run=run, root=tmp_path, lanes=lanes, state=state)


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
def test_changed_prose_check_catches_and_clears_style_violations(prose_check, path: str) -> None:
    heading = "Check a file\n============\n" if path.endswith(".rst") else "# Check a file\n"
    bad = prose_check.run(path, heading + "\nUtilize the tool to check a file.\n")
    assert bad.returncode != 0, bad.stdout + bad.stderr
    assert "RAES.PlainWords" in bad.stdout, bad.stdout + bad.stderr
    good = prose_check.run(path, heading + "\nUse the tool to check a file.\n")
    assert good.returncode == 0, good.stdout + good.stderr


def test_changed_prose_check_runs_without_personal_skills(prose_check) -> None:
    result = prose_check.run("docs/explain/task.md", "# Check a file\n\nCheck the file.\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "unchanged.md" not in result.stdout


def test_changed_prose_check_preserves_literal_content(prose_check) -> None:
    result = prose_check.run(
        "docs/explain/task.md", "# Check a file\n\nCheck the file.\n\n```text\nSimply utilize this tool.\n```\n"
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_changed_prose_check_leaves_build_and_hooks_unchanged(prose_check) -> None:
    result = prose_check.run("implementations/data.json", "{}\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not prose_check.state["calls"]


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
def test_changed_prose_check_preserves_release_and_legal_records(prose_check, path: str) -> None:
    result = prose_check.run(path, "# Exact Record\n\nSimply utilize this tool.\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not prose_check.state["calls"]
    assert path in result.stdout
    assert "manual" in result.stdout.lower()


@pytest.mark.parametrize(
    "catalog", ["docs/decisions/adrs/adr-index.yaml", "tools/policy/historical_identity_records.json"]
)
def test_changed_prose_check_rejects_malformed_protection_catalog(prose_check, catalog: str) -> None:
    (prose_check.root / catalog).write_text("{}")
    result = prose_check.run("docs/task.md", "# Check a file\n\nCheck the file.\n")
    assert result.returncode != 0
    assert "catalog" in result.stderr
    assert not prose_check.state["calls"]


def test_changed_prose_check_accepts_explicit_paths(prose_check) -> None:
    result = prose_check.run("docs/task.md", "# Check a file\n\nUtilize the tool.\n", posargs=["docs/task.md"])
    assert result.returncode != 0
    assert "RAES.PlainWords" in result.stdout


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


def test_changed_prose_check_refuses_paths_outside_repository(prose_check) -> None:
    outside = prose_check.root.parent / "outside.md"
    outside.write_text("# Check a file\n\nUtilize the tool.\n")
    result = prose_check.run("docs/task.md", "# Check a file\n\nCheck the file.\n", posargs=["../outside.md"])
    assert result.returncode != 0
    assert "unsafe" in result.stderr
    assert not prose_check.state["calls"]


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
