"""The runtime SBOM describes the distribution, not the all-extras smoke venv.

`tools/python_closure.py:202` installs the full projected requirements and then
the candidate with `--no-deps`, so the smoke environment also holds every
published `dev` and `docs` extra. Dumping it would file Sphinx and pytest as
runtime dependencies of `raes`. These cases pin the reconciliation that avoids
that: declared wheel metadata, the locked selection, and the observed
installation must agree, and disagreement must fail rather than silently omit an
edge.
"""

from __future__ import annotations

import tomllib
import zipfile
from pathlib import Path
from typing import Any

import pytest
from packaging.metadata import Metadata
from tools.generate_python_closures_locks import locked_closure, target_environment
from tools.release_evidence_sbom import (
    RuntimeClosureError,
    reconcile_runtime_closure,
    wheel_metadata,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECT_LOCK = REPO_ROOT / "implementations" / "python" / "uv.lock"

_ENVIRONMENT = target_environment("3.12", "x86_64-unknown-linux-gnu", full_version="3.12.14")

_METADATA = """Metadata-Version: 2.3
Name: raes
Version: 1.2.3
Requires-Python: >=3.11,<3.15
Requires-Dist: typer>=0.12.0
Requires-Dist: tomli; python_full_version < '3.11'
Requires-Dist: pytest>=9.0.3; extra == 'dev'
Requires-Dist: sphinx>=7.3.0; extra == 'docs'
Provides-Extra: dev
Provides-Extra: docs
"""


def _wheel(tmp_path: Path, metadata: str = _METADATA) -> Path:
    path = tmp_path / "raes-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("raes/__init__.py", "")
        archive.writestr("raes-1.2.3.dist-info/METADATA", metadata)
    return path


def _package(name: str, version: str, *dependencies: str) -> dict[str, Any]:
    return {
        "name": name,
        "version": version,
        "dependencies": [{"name": item} for item in dependencies],
    }


# A minimal lock shaped like uv.lock: `typer` pulls `click`, the extras pull
# their own trees, and nothing else is reachable from the declared roots.
_LOCK: dict[str, Any] = {
    "package": [
        _package("raes", "1.2.3"),
        _package("typer", "0.24.1", "click"),
        _package("click", "8.4.2"),
        _package("pytest", "9.0.3", "pluggy"),
        _package("pluggy", "1.6.0"),
        _package("sphinx", "8.2.3"),
        _package("tomli", "2.4.1"),
    ]
}

_INSTALLED = {
    "typer": "0.24.1",
    "click": "8.4.2",
    "pytest": "9.0.3",
    "pluggy": "1.6.0",
    "sphinx": "8.2.3",
    "tomli": "2.4.1",
}


def _reconcile(tmp_path: Path, **overrides: Any):
    kwargs: dict[str, Any] = {
        "lock": _LOCK,
        "installed_versions": _INSTALLED,
        "environment": _ENVIRONMENT,
        "extras": (),
    }
    kwargs.update(overrides)
    return reconcile_runtime_closure(wheel_metadata(_wheel(tmp_path)), **kwargs)


def test_wheel_metadata_is_read_without_installing_or_importing_the_candidate(
    tmp_path: Path,
) -> None:
    metadata = wheel_metadata(_wheel(tmp_path))
    assert metadata.name == "raes"
    assert str(metadata.version) == "1.2.3"


def test_base_closure_excludes_published_dev_and_docs_extras(tmp_path: Path) -> None:
    """The failure mode acceptance criterion 1 names, asserted directly."""

    closure = _reconcile(tmp_path)
    assert {component.name for component in closure.components} == {"typer", "click"}
    assert all(component.scope == "required" for component in closure.components)


def test_transitive_dependencies_are_included_not_just_declared_roots(
    tmp_path: Path,
) -> None:
    """`click` is reached through `typer`, never declared by the wheel itself."""

    closure = _reconcile(tmp_path)
    assert "click" in {component.name for component in closure.components}


def test_dependency_edges_are_preserved(tmp_path: Path) -> None:
    closure = _reconcile(tmp_path)
    assert closure.edges["typer"] == ["click"]
    assert closure.edges["click"] == []


def test_extras_qualifier_on_a_declared_root_pulls_its_extra_tree(
    tmp_path: Path,
) -> None:
    """`uvicorn[standard]` shape: the qualifier must not be dropped when seeding.

    Dropping it resolves a closure that is silently four packages short against
    the real project lock, which is an omitted dependency rather than a visible
    failure.
    """

    metadata = """Metadata-Version: 2.3
Name: raes
Version: 1.2.3
Requires-Dist: server[fast]
"""
    lock = {
        "package": [
            _package("raes", "1.2.3"),
            {
                "name": "server",
                "version": "1.0.0",
                "dependencies": [{"name": "base"}],
                "optional-dependencies": {"fast": [{"name": "turbo"}]},
            },
            _package("base", "2.0.0"),
            _package("turbo", "3.0.0"),
        ]
    }
    path = tmp_path / "raes-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("raes-1.2.3.dist-info/METADATA", metadata)
    closure = reconcile_runtime_closure(
        wheel_metadata(path),
        lock=lock,
        installed_versions={"server": "1.0.0", "base": "2.0.0", "turbo": "3.0.0"},
        environment=_ENVIRONMENT,
        extras=(),
    )
    assert {component.name for component in closure.components} == {
        "server",
        "base",
        "turbo",
    }


def test_reconciled_closure_agrees_with_the_incumbent_walker() -> None:
    """Seeding from declared roots must not resolve a different set."""

    lock = tomllib.loads(PROJECT_LOCK.read_text(encoding="utf-8"))
    raes = next(item for item in lock["package"] if item["name"] == "raes")
    installed = {str(item["name"]): str(item["version"]) for item in lock["package"] if item.get("version")}
    lines = ["Metadata-Version: 2.3", "Name: raes", "Version: 9.9.9"]
    for dependency in raes.get("dependencies", []):
        extras = dependency.get("extra") or []
        suffix = f"[{','.join(extras)}]" if extras else ""
        lines.append(f"Requires-Dist: {dependency['name']}{suffix}")
    closure = reconcile_runtime_closure(
        Metadata.from_email("\n".join(lines) + "\n", validate=False),
        lock=lock,
        installed_versions=installed,
        environment=_ENVIRONMENT,
        extras=(),
    )
    expected = {
        str(package["name"])
        for package in locked_closure(lock, _ENVIRONMENT, root_name="raes", include_root_optional=False)
    }
    assert {component.name for component in closure.components} == expected


def test_extras_are_labelled_rather_than_unconditional_runtime(
    tmp_path: Path,
) -> None:
    closure = _reconcile(tmp_path, extras=("docs",))
    by_name = {component.name: component for component in closure.components}
    assert set(by_name) == {"typer", "click", "sphinx"}
    assert by_name["sphinx"].scope == "optional"
    assert by_name["sphinx"].extra == "docs"
    assert by_name["typer"].scope == "required"


def test_markers_are_evaluated_against_the_selected_target(tmp_path: Path) -> None:
    """`tomli` is gated on <3.11 and must not appear for a 3.12 target."""

    closure = _reconcile(tmp_path)
    assert "tomli" not in {component.name for component in closure.components}


def test_dependency_missing_from_the_lock_fails_rather_than_being_omitted(
    tmp_path: Path,
) -> None:
    lock = {"package": [_package("raes", "1.2.3"), _package("click", "8.4.2")]}
    with pytest.raises(RuntimeClosureError) as excinfo:
        _reconcile(tmp_path, lock=lock)
    assert excinfo.value.code == "runtime-closure-unlocked-dependency"


def test_dependency_missing_from_the_installation_fails(tmp_path: Path) -> None:
    with pytest.raises(RuntimeClosureError) as excinfo:
        _reconcile(tmp_path, installed_versions={"typer": "0.24.1"})
    assert excinfo.value.code == "runtime-closure-uninstalled-dependency"


def test_locked_version_disagreeing_with_the_installation_fails(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeClosureError) as excinfo:
        _reconcile(tmp_path, installed_versions={**_INSTALLED, "click": "9.9.9"})
    assert excinfo.value.code == "runtime-closure-version-disagreement"


def test_locked_version_violating_the_declared_specifier_fails(
    tmp_path: Path,
) -> None:
    lock = {
        "package": [
            _package("raes", "1.2.3"),
            _package("typer", "0.1.0", "click"),
            _package("click", "8.4.2"),
        ]
    }
    with pytest.raises(RuntimeClosureError) as excinfo:
        _reconcile(tmp_path, lock=lock, installed_versions={"typer": "0.1.0", "click": "8.4.2"})
    assert excinfo.value.code == "runtime-closure-specifier-violation"


def test_unknown_extra_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RuntimeClosureError) as excinfo:
        _reconcile(tmp_path, extras=("nonexistent",))
    assert excinfo.value.code == "runtime-closure-unknown-extra"


def test_wheel_without_metadata_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "raes-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("raes/__init__.py", "")
    with pytest.raises(RuntimeClosureError) as excinfo:
        wheel_metadata(path)
    assert excinfo.value.code == "wheel-metadata-absent"


def test_oversized_metadata_member_is_refused(tmp_path: Path) -> None:
    """Evidence inputs are untrusted: a declared member cannot be read unbounded."""

    oversized = _wheel(tmp_path, _METADATA + "# padding\n" * 200_000)
    with pytest.raises(RuntimeClosureError) as excinfo:
        wheel_metadata(oversized)
    assert excinfo.value.code == "wheel-metadata-oversized"


def test_real_project_lock_separates_runtime_from_the_developer_closure() -> None:
    """The reconciled closure is materially smaller than the smoke environment.

    The all-extras smoke requirements pin 91 packages; the distribution's actual
    runtime closure is far smaller and contains none of the published developer
    or documentation tooling.
    """

    lock = tomllib.loads(PROJECT_LOCK.read_text(encoding="utf-8"))
    raes = next(item for item in lock["package"] if item["name"] == "raes")
    installed = {str(item["name"]): str(item["version"]) for item in lock["package"] if item.get("version")}
    metadata_lines = ["Metadata-Version: 2.3", "Name: raes", "Version: 9.9.9"]
    metadata_lines += [f"Requires-Dist: {item['name']}" for item in raes.get("dependencies", [])]
    metadata = Metadata.from_email("\n".join(metadata_lines) + "\n", validate=False)
    closure = reconcile_runtime_closure(
        metadata,
        lock=lock,
        installed_versions=installed,
        environment=_ENVIRONMENT,
        extras=(),
    )
    names = {component.name for component in closure.components}
    assert not names & {"sphinx", "pytest", "furo", "coverage", "hypothesis"}
    assert len(names) < 91
    assert "pydantic" in names
