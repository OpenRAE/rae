"""Structural checks for public-project security and enrollment metadata."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_scorecard_workflow_is_pinned_least_privilege_and_publishes_sarif() -> None:
    workflow_path = REPO_ROOT / ".github" / "workflows" / "scorecard.yml"
    source = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    triggers = workflow.get("on", workflow.get(True))

    assert workflow["permissions"] == "read-all"
    assert "pull_request_target" not in triggers
    analysis = workflow["jobs"]["analysis"]
    assert analysis["permissions"] == {
        "contents": "read",
        "security-events": "write",
        "id-token": "write",
    }
    scorecard_step = next(
        step for step in analysis["steps"] if step.get("uses", "").startswith("ossf/scorecard-action@")
    )
    assert scorecard_step["uses"] == ("ossf/scorecard-action@2d1146689b8cda280b9bc96326124645441f03bc")
    assert scorecard_step["with"] == {
        "results_file": "results.sarif",
        "results_format": "sarif",
        "publish_results": "true",
    }
    assert "SCORECARD_TOKEN" not in source
    for match in re.finditer(r"^\s*uses:\s*([^#\s]+)", source, re.MULTILINE):
        assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", match.group(1))


def test_best_practices_proposal_is_factual_about_single_maintainer_limits() -> None:
    proposal = json.loads((REPO_ROOT / ".bestpractices.json").read_text(encoding="utf-8"))

    assert proposal["repo_url"] == "https://github.com/OpenRAE/rae"
    assert proposal["license"] == "MIT"
    assert proposal["bus_factor_status"] == "Unmet"
    assert proposal["two_person_review_status"] == "Unmet"
    assert "one maintainer" in proposal["bus_factor_justification"].casefold()
    assert "badge" not in proposal


def test_live_repository_identity_uses_openrae_owner() -> None:
    ground_control = yaml.safe_load((REPO_ROOT / ".ground-control.yaml").read_text(encoding="utf-8"))
    mcp = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    previous_owner = "RAE" + "System"

    assert ground_control["github_repo"] == "OpenRAE/rae"
    assert mcp["mcpServers"]["ground-control"]["env"]["GH_REPO"] == "OpenRAE/rae"

    for relative_path in (
        ".bestpractices.json",
        ".github/ISSUE_TEMPLATE/config.yml",
        "CONTRIBUTING.md",
        "README.md",
    ):
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert f"github.com/{previous_owner}" not in source, relative_path
        assert f"{previous_owner}/rae" not in source, relative_path


def test_requirement_issue_links_use_current_repository_identity() -> None:
    previous_repository = ("RAE" + "System") + "/rae"
    requirement_files = sorted((REPO_ROOT / "docs/requirements").glob("*/requirement.md"))

    assert requirement_files
    for requirement_file in requirement_files:
        source = requirement_file.read_text(encoding="utf-8")
        assert previous_repository not in source, requirement_file.relative_to(REPO_ROOT)


def test_publishers_build_only_the_curated_public_source() -> None:
    rtd = yaml.safe_load((REPO_ROOT / ".readthedocs.yaml").read_text(encoding="utf-8"))
    assert rtd["sphinx"] == {
        "configuration": "docs/public/conf.py",
        "fail_on_warning": True,
    }
    assert rtd["python"]["install"][0]["command"] == "sync --frozen"

    docs_workflow = (REPO_ROOT / ".github" / "workflows" / "docs.yml").read_text(encoding="utf-8")
    assert "nox[uv]==2026.4.10" in docs_workflow
    assert "-s docs" in docs_workflow
    assert "sphinx-build" not in docs_workflow
    assert "path: docs/_build/html" in docs_workflow

    makefile = (REPO_ROOT / "docs" / "Makefile").read_text(encoding="utf-8")
    assert "SOURCEDIR     = public" in makefile
    assert "BUILDDIR      = _build" in makefile


def test_python_support_metadata_and_blocking_matrix_are_aligned() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "implementations" / "python" / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    supported = ["3.11", "3.12", "3.13", "3.14"]

    assert project["requires-python"] == ">=3.11,<3.15"
    assert {
        classifier.removeprefix("Programming Language :: Python :: ")
        for classifier in project["classifiers"]
        if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", classifier)
    } == set(supported)

    ci = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    interpreter_job = ci["jobs"]["interpreters"]
    assert interpreter_job["strategy"]["fail-fast"] is False
    assert interpreter_job["strategy"]["matrix"]["python"] == [
        {"feature": "3.11", "payload": "3.11.16"},
        {"feature": "3.12", "payload": "3.12.14"},
        {"feature": "3.13", "payload": "3.13.15"},
        {"feature": "3.14", "payload": "3.14.7"},
    ]
    assert interpreter_job["env"] == {
        "UV_PYTHON": "${{ matrix.python.payload }}",
        "RAES_EXPECTED_PYTHON": "${{ matrix.python.feature }}",
    }

    preview = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "python-free-threaded-preview.yml").read_text(encoding="utf-8")
    )
    preview_job = preview["jobs"]["python-314t"]
    assert preview_job["continue-on-error"] is True
    assert preview_job["env"] == {
        "UV_PYTHON": "3.14.7t",
        "RAES_EXPECTED_PYTHON": "3.14",
        "RAES_EXPECT_FREE_THREADED": "1",
    }

    compatibility_lane = (REPO_ROOT / "tools" / "nox_support" / "test_lanes.py").read_text(encoding="utf-8")
    assert 'assert is_gil_enabled() is False, "interpreter is not free-threaded"' in compatibility_lane
    assert 'assert is_gil_enabled() is True, "standard lane selected a free-threaded interpreter"' in compatibility_lane
