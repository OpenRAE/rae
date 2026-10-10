"""Git path listings that feed the gates keep the names git quotes (#1473)."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from tools import check_schema_publication
from tools.policy.common import changed_paths

# Without -z, git quotes a name with a byte above 0x80 (under the default core.quotePath=true), a control character
# or a double quote, so the gates drop it or receive the quoted text. Git lists the plain name verbatim either way.
_SCHEMAS = "contracts/schemas"
_NAMES = sorted(f"{_SCHEMAS}/{name}" for name in ("naïve.json", "tab\tname.json", '"quoted".json', "plain.json"))
_CHANGE_MODES: dict[str, dict[str, object]] = {
    "staged": {"staged": True},
    "base revision": {"base_rev": "HEAD~1"},
    "working tree": {},
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real repository with one base commit and the four names staged on top of it."""

    # Use git's built-in defaults, as CI runners do, whatever the developer's global or system configuration says.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "tests@example.invalid")
    _git(tmp_path, "config", "user.name", "Tests")
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-q", "-m", "base")
    (tmp_path / _SCHEMAS).mkdir(parents=True)
    for name in _NAMES:
        (tmp_path / name).write_text("{}\n", encoding="utf-8")
    _git(tmp_path, "add", _SCHEMAS)
    return tmp_path


@pytest.fixture
def runner(repo: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import the nox runner against a stand-in nox (the project env has no nox), rooted at ``repo``."""

    monkeypatch.setitem(sys.modules, "nox", SimpleNamespace(Session=object))
    # Registering the key makes monkeypatch remove the stand-in import afterward.
    monkeypatch.setitem(sys.modules, "tools.nox_support.runner", None)
    monkeypatch.delitem(sys.modules, "tools.nox_support.runner")
    module = importlib.import_module("tools.nox_support.runner")
    monkeypatch.setattr(module, "REPO_ROOT", repo)
    return module


@pytest.mark.parametrize("mode", list(_CHANGE_MODES))
def test_changed_path_listings_keep_names_git_quotes(repo: Path, runner: ModuleType, mode: str) -> None:
    if mode == "base revision":
        _git(repo, "commit", "-q", "-m", "names")
    options = _CHANGE_MODES[mode]

    assert sorted(changed_paths(repo, **options)) == _NAMES
    assert sorted(runner._changed_paths(**options)) == _NAMES


def test_repository_listings_keep_names_git_quotes(repo: Path, runner: ModuleType) -> None:
    _git(repo, "commit", "-q", "-m", "names")

    assert sorted(runner._tracked_repo_paths()) == ["README.md", *_NAMES]
    assert check_schema_publication._git_paths(repo, "HEAD", _SCHEMAS) == _NAMES
