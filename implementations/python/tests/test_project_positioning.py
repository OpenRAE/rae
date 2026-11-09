from __future__ import annotations

from pathlib import Path

import pytest
from tools.check_project_positioning import MAX_SURFACE_BYTES, validate_project_positioning

REPO_ROOT = Path(__file__).resolve().parents[3]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_positioning_surfaces(repo_root: Path) -> None:
    primary_copy = """
Reproducible Agentic Environments System (RAES) supports reproducible agentic
environments. An agentic environment is a declared and realized setting in
which participants receive observations, take actions, interact, and are
evaluated under stated controls.

Cyber, AI security, AI safety, testing, research, and evaluation are
non-exhaustive application areas. The general model can support additional
domains through domain-specific profiles and catalogs.

RAES preserves authored scenario intent, governed variation, realized
environment details, participant behavior, observations, evidence, provenance,
replay boundaries, and conformance results for a bounded reproduction attempt.
It does not guarantee deterministic runtime behavior, equal outcomes, exact
replay, or reproducibility.
"""
    for relative_path in (
        "README.md",
        "docs/public/index.md",
        "docs/public/quickstart.md",
        "docs/public/concepts.md",
        "docs/public/sdl/index.md",
        "docs/public/backends.md",
        "docs/public/research.md",
        "examples/README.md",
    ):
        _write(repo_root / relative_path, primary_copy)
    _write(
        repo_root / "examples/library/catalog.yaml",
        "description: >\n"
        "  Domain-neutral RAES agentic-environment authoring library for examples,\n"
        "  templates, and reusable patterns.\n",
    )
    _write(
        repo_root / "implementations/python/pyproject.toml",
        '[project]\ndescription = "Contracts and reference tooling for reproducible agentic environments."\n',
    )
    _write(
        repo_root / "docs/public/conf.py",
        'project = "Reproducible Agentic Environments System"\nhtml_title = "RAES Documentation"\n',
    )
    _write(
        repo_root / "implementations/python/packages/raes_mcp/server.py",
        '_INSTRUCTIONS = """Reproducible Agentic Environments System (RAES) '
        "supports agentic environments. RAES SDL is the authored scenario "
        'language."""\n',
    )
    _write(
        repo_root / "implementations/python/packages/raes_mcp/tools/reference.py",
        '_OVERVIEW_TEXT = """RAES supports reproducible agentic environments. '
        "RAES SDL describes authored scenarios; backends produce realized "
        'environments for bounded reproduction attempts."""\n',
    )


def test_current_repository_satisfies_project_positioning_contract() -> None:
    assert validate_project_positioning(REPO_ROOT) == []


def test_positioning_check_reports_missing_domain_neutral_metadata(tmp_path: Path) -> None:
    _seed_positioning_surfaces(tmp_path)
    _write(
        tmp_path / "implementations/python/pyproject.toml",
        '[project]\ndescription = "Backend-agnostic cyber range scenario language."\n',
    )

    failures = validate_project_positioning(tmp_path)

    assert any(
        failure.rule_id == "project-positioning-metadata" and failure.path == "implementations/python/pyproject.toml"
        for failure in failures
    )


def test_positioning_check_reports_missing_claim_boundary(tmp_path: Path) -> None:
    _seed_positioning_surfaces(tmp_path)
    _write(
        tmp_path / "docs/public/concepts.md",
        "Reproducible Agentic Environments System guarantees exact replay.\n",
    )

    failures = validate_project_positioning(tmp_path)

    assert any(
        failure.rule_id == "project-positioning-claim-boundary" and failure.path == "docs/public/concepts.md"
        for failure in failures
    )


@pytest.mark.parametrize(
    ("relative_path", "replacement"),
    (
        ("README.md", None),
        ("docs/public/index.md", "x" * (MAX_SURFACE_BYTES + 1)),
    ),
)
def test_positioning_check_reports_invalid_required_surface(
    tmp_path: Path,
    relative_path: str,
    replacement: str | None,
) -> None:
    _seed_positioning_surfaces(tmp_path)
    surface = tmp_path / relative_path
    if replacement is None:
        surface.unlink()
    else:
        _write(surface, replacement)

    failures = validate_project_positioning(tmp_path)

    assert any(
        failure.rule_id == "project-positioning-surface" and failure.path == relative_path for failure in failures
    )


@pytest.mark.parametrize(
    "relative_path",
    (
        "README.md",
        "docs/public/backends.md",
    ),
)
def test_positioning_check_reports_missing_entrypoint_framing(
    tmp_path: Path,
    relative_path: str,
) -> None:
    _seed_positioning_surfaces(tmp_path)
    _write(tmp_path / relative_path, "This surface no longer identifies its subject.\n")

    failures = validate_project_positioning(tmp_path)

    assert any(
        failure.rule_id == "project-positioning-framing" and failure.path == relative_path for failure in failures
    )


def test_positioning_check_reports_incomplete_application_areas(tmp_path: Path) -> None:
    _seed_positioning_surfaces(tmp_path)
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    _write(tmp_path / "README.md", readme.replace(", and evaluation", ""))

    failures = validate_project_positioning(tmp_path)

    assert any(failure.rule_id == "project-positioning-domains" and failure.path == "README.md" for failure in failures)


@pytest.mark.parametrize(
    ("relative_path", "replacement"),
    (
        (
            "docs/public/conf.py",
            'project = "RAES"\nhtml_title = "Documentation"\n',
        ),
        (
            "examples/library/catalog.yaml",
            "description: Cyber scenario examples.\n",
        ),
    ),
)
def test_positioning_check_reports_invalid_structured_metadata(
    tmp_path: Path,
    relative_path: str,
    replacement: str,
) -> None:
    _seed_positioning_surfaces(tmp_path)
    _write(tmp_path / relative_path, replacement)

    failures = validate_project_positioning(tmp_path)

    assert any(
        failure.rule_id == "project-positioning-metadata" and failure.path == relative_path for failure in failures
    )


@pytest.mark.parametrize(
    ("relative_path", "assignment"),
    (
        ("implementations/python/packages/raes_mcp/server.py", "_INSTRUCTIONS"),
        (
            "implementations/python/packages/raes_mcp/tools/reference.py",
            "_OVERVIEW_TEXT",
        ),
    ),
)
def test_positioning_check_reports_invalid_mcp_metadata(
    tmp_path: Path,
    relative_path: str,
    assignment: str,
) -> None:
    _seed_positioning_surfaces(tmp_path)
    _write(tmp_path / relative_path, f'{assignment} = "Scenario authoring tools."\n')

    failures = validate_project_positioning(tmp_path)

    assert any(
        failure.rule_id == "project-positioning-metadata" and failure.path == relative_path for failure in failures
    )


def test_positioning_check_is_registered_in_canonical_policy_graph() -> None:
    policy_lane_source = (REPO_ROOT / "tools" / "nox_support" / "policy_lanes.py").read_text(encoding="utf-8")
    assert '"tools/check_project_positioning.py"' in policy_lane_source


def test_a_defect_while_reading_package_metadata_is_not_reported_as_a_metadata_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.check_project_positioning as gate

    _seed_positioning_surfaces(tmp_path)

    def defective(_text: str) -> dict[str, object]:
        raise TypeError("toml reader defect")

    monkeypatch.setattr(gate.tomllib, "loads", defective)
    with pytest.raises(TypeError, match="toml reader defect"):
        validate_project_positioning(tmp_path)
