"""Tests for the fail-closed local verification classifier."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from defusedxml import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raes_contracts.errors import OperationalError  # noqa: E402
from tools import verification_plan  # noqa: E402
from tools.verification_plan import (  # noqa: E402
    ChangeRecord,
    collect_git_changes,
    plan_for_changes,
    select_changed_python_tests,
)


def _plan(*paths: str):
    return plan_for_changes([ChangeRecord(status="M", path=path) for path in paths])


def test_non_authoritative_prose_selects_docs_only() -> None:
    plan = _plan("README.md", "docs/explain/sdl/sections.md")

    assert not plan.contracts
    assert not plan.regression
    assert not plan.fuzz
    assert plan.docs


def test_research_evidence_and_formal_specs_select_contract_replay() -> None:
    plan = _plan(
        "docs/research/formal-semantic-validation/analysis-v1.json",
        "specs/formal/participant-semantics/README.md",
    )

    assert plan.contracts
    assert not plan.regression
    assert not plan.fuzz
    assert plan.docs


@pytest.mark.parametrize(
    "path",
    [
        "contracts/schemas/sdl/sdl-authoring-input-v1.json",
        "implementations/python/packages/raes/scenario.py",
        "implementations/python/tests/test_sdl_models.py",
        "implementations/python/pyproject.toml",
        "noxfile.py",
        ".github/workflows/ci.yml",
        "tools/check_formal_semantic_validation.py",
        "unclassified/new-surface.txt",
    ],
)
def test_executable_contract_configuration_and_unknown_paths_fail_closed(path: str) -> None:
    plan = _plan(path)

    assert plan.contracts
    assert plan.regression
    assert plan.fuzz
    assert plan.docs


@pytest.mark.parametrize(
    "path",
    [
        ".vale.ini",
        "styles/RAES/PlainWords.yml",
        "tools/check_public_docs.py",
        "tools/vale_tool.py",
        ".github/workflows/docs.yml",
        ".readthedocs.yaml",
        "noxfile.py",
    ],
)
def test_documentation_tooling_changes_select_docs_graph(path: str) -> None:
    assert _plan(path).docs


@pytest.mark.parametrize("status", ["D", "R", "C", "T"])
def test_destructive_or_structural_changes_fail_closed(status: str) -> None:
    plan = plan_for_changes([ChangeRecord(status=status, old_path="docs/old.md", path="docs/new.md")])

    assert plan.contracts
    assert plan.regression
    assert plan.fuzz


def test_mixed_prose_and_source_changes_take_the_highest_risk_plan() -> None:
    plan = _plan("docs/explain/sdl/sections.md", "implementations/python/packages/raes/scenario.py")

    assert plan.contracts
    assert plan.regression


def test_precommit_selects_only_directly_changed_pytest_modules() -> None:
    selected = select_changed_python_tests(
        [
            "tools/isabelle_tool.py",
            "implementations/python/tests/helpers.py",
            "implementations/python/tests/test_issue_963_participant_opacity_proof.py",
            "implementations/python/tests/test_issue_963_participant_opacity_proof.py",
            "implementations/python/tests/test_contract.json",
        ]
    )

    assert selected == ["implementations/python/tests/test_issue_963_participant_opacity_proof.py"]


def test_evidence_prefix_matching_respects_directory_boundaries() -> None:
    plan = _plan("docs/researcher/notes.md")

    assert not plan.contracts
    assert not plan.regression
    assert plan.docs


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.mark.integration
def test_git_collection_preserves_deletions_renames_and_untracked_paths(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "tests@example.invalid")
    _git(tmp_path, "config", "user.name", "Tests")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "rename-me.md").write_text("rename\n", encoding="utf-8")
    (tmp_path / "docs" / "delete-me.md").write_text("delete\n", encoding="utf-8")
    _git(tmp_path, "add", "docs")
    _git(tmp_path, "commit", "-q", "-m", "base")

    _git(tmp_path, "mv", "docs/rename-me.md", "docs/renamed.md")
    (tmp_path / "docs" / "delete-me.md").unlink()
    (tmp_path / "docs" / "untracked.md").write_text("new\n", encoding="utf-8")

    changes = collect_git_changes(tmp_path, "HEAD")

    assert ChangeRecord(status="R", old_path="docs/rename-me.md", path="docs/renamed.md") in changes
    assert ChangeRecord(status="D", path="docs/delete-me.md") in changes
    assert ChangeRecord(status="A", path="docs/untracked.md") in changes


@pytest.mark.integration
def test_git_collection_fails_closed_when_base_revision_is_invalid(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")

    with pytest.raises(OperationalError, match="git diff") as raised:
        collect_git_changes(tmp_path, "does-not-exist")
    assert "does-not-exist" not in str(raised.value)


def _git_result(*, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["git"], returncode, stdout=stdout, stderr=stderr)


def test_git_failure_message_omits_git_output_and_command_line(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = b"fatal: unable to access https://user:secret-sentinel@example.invalid/repo"
    monkeypatch.setattr(
        verification_plan.subprocess, "run", lambda *_args, **_kwargs: _git_result(returncode=128, stderr=sentinel)
    )

    with pytest.raises(OperationalError) as raised:
        collect_git_changes(Path("."), "base-sentinel")

    assert str(raised.value) == "git diff failed with exit code 128"


@pytest.mark.parametrize(
    ("stdout", "message"),
    [
        (b"R100\x00only-one-path\x00", "incomplete change record"),
        (b"M\x00\xff\xfe\x00", "not UTF-8"),
    ],
)
def test_malformed_git_output_is_an_operational_failure(
    monkeypatch: pytest.MonkeyPatch, stdout: bytes, message: str
) -> None:
    monkeypatch.setattr(verification_plan.subprocess, "run", lambda *_args, **_kwargs: _git_result(stdout=stdout))

    with pytest.raises(OperationalError, match=message):
        collect_git_changes(Path("."), "HEAD")


@pytest.mark.integration
def test_xdist_workers_are_combined_into_one_coverage_report(tmp_path: Path) -> None:
    (tmp_path / "covered.py").write_text(
        "def left():\n    return 'left'\n\ndef right():\n    return 'right'\n",
        encoding="utf-8",
    )
    (tmp_path / "test_covered.py").write_text(
        "from covered import left, right\n\ndef test_left():\n    assert left() == 'left'\n"
        "\ndef test_right():\n    assert right() == 'right'\n",
        encoding="utf-8",
    )
    report = tmp_path / "coverage.xml"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COV_CORE_") and key not in {"COVERAGE_FILE", "COVERAGE_PROCESS_START"}
    }

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-n",
            "2",
            "--dist=worksteal",
            "--cov=covered",
            f"--cov-report=xml:{report}",
        ],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    covered_class = ET.parse(report).find(".//class[@filename='covered.py']")
    assert covered_class is not None
    assert covered_class.attrib["line-rate"] == "1"
