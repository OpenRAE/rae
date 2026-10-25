"""Git path listings that feed the gates return every name exactly as git stores it (#1473)."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from tools import check_requirement_governance, check_schema_publication
from tools.policy.common import REPO_ROOT, changed_paths
from tools.policy.repo_policy import evaluate_repo_policy

# Without -z, git quotes a name with a byte above 0x80 (under the default core.quotePath=true), a control character
# or a double quote. Read in text mode, a carriage return or CRLF in a name becomes LF, and the old line split
# stripped spaces at either end of a path. Each stem names one schema publication record and one 501-line module.
_STEMS = ("plain", "naïve", "tab\tname", "new\nline", "carriage\rreturn", "crlf\r\nname", '"quoted"')
_RECORDS_DIR = "contracts/schema-publication/entries"
_RECORDS = sorted(f"{_RECORDS_DIR}/{stem}.json" for stem in _STEMS)
_MODULES = sorted(f"implementations/python/packages/raes/{stem}.py" for stem in _STEMS)
_NAMES = sorted((*_RECORDS, *_MODULES, " leading space.md", "trailing space.md "))
_BASE_FILES = (
    "README.md",
    "contracts/schema-publication-manifest.json",
    "tools/policy/adr_policy.yaml",
    "tools/policy/oversized_allowlist.yaml",
)
_SINCE_BASE = ["--base-rev", "HEAD~1"]
# Each mode's options for the listing helpers and the hygiene stages' arguments that select it.
_CHANGE_MODES: dict[str, tuple[dict[str, object], list[str]]] = {
    "staged": ({"staged": True}, ["--staged"]),
    "base revision": ({"base_rev": "HEAD~1"}, _SINCE_BASE),
    "working tree": ({}, []),
}
# A Latin-1 e acute, which is not UTF-8. An index entry needs no file, so filesystems that refuse the name run it too.
_NOT_UTF8_RECORD = _RECORDS_DIR.encode() + b"/caf\xe9.json"


def _git(repo: Path, *args: str | bytes, stdin: bytes | None = None) -> bytes:
    return subprocess.run(["git", *args], cwd=repo, input=stdin, check=True, capture_output=True).stdout


def _write(repo: Path, name: str, text: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real repository: the gates' configuration in one commit, and every name staged on top of it."""

    # Use git's built-in defaults, as CI runners do, whatever the developer's global or system configuration says.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "tests@example.invalid")
    _git(tmp_path, "config", "user.name", "Tests")
    _write(tmp_path, "README.md", "base\n")
    manifest = {"schema_version": check_schema_publication.SCHEMA_VERSION, "entries_directory": _RECORDS_DIR}
    _write(tmp_path, "contracts/schema-publication-manifest.json", json.dumps(manifest))
    _write(tmp_path, "tools/policy/adr_policy.yaml", (REPO_ROOT / "tools/policy/adr_policy.yaml").read_text("utf-8"))
    _write(tmp_path, "tools/policy/oversized_allowlist.yaml", "files: []\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    for stem, record, module in zip(_STEMS, _RECORDS, _MODULES, strict=True):
        _write(tmp_path, record, json.dumps({"contract_id": stem}))
        _write(tmp_path, module, "value = 0\n" * 501)
    for name in set(_NAMES) - {*_RECORDS, *_MODULES}:
        _write(tmp_path, name, "text\n")
    _git(tmp_path, "add", ".")
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


def _oversized_paths(repo: Path, listed: list[str]) -> list[str | None]:
    """The paths the repository policy's 500-line cap rejects; the scratch repository holds no other package roots."""

    failures = evaluate_repo_policy(repo, listed, check_set="file-local", structural_runner=lambda _: [])
    return sorted(failure.path for failure in failures if failure.rule_id == "oversized-source-file")


@pytest.mark.parametrize("mode", list(_CHANGE_MODES))
def test_changed_path_listings_keep_every_name(repo: Path, runner: ModuleType, mode: str) -> None:
    if mode == "base revision":
        _git(repo, "commit", "-q", "-m", "names")
    options, hygiene_args = _CHANGE_MODES[mode]
    listed = changed_paths(repo, **options)

    assert sorted(listed) == _NAMES
    assert sorted(runner._changed_paths(**options)) == _NAMES
    assert sorted(runner._parse_hygiene_posargs(hygiene_args, default_all_files=False).paths) == _NAMES
    assert _oversized_paths(repo, listed) == _MODULES


def test_repository_listings_keep_every_name(repo: Path, runner: ModuleType) -> None:
    _git(repo, "commit", "-q", "-m", "names")
    tracked = sorted((*_BASE_FILES, *_NAMES))

    assert sorted(runner._tracked_repo_paths()) == tracked
    assert sorted(runner._parse_hygiene_posargs(["--all-files"], default_all_files=False).paths) == tracked
    assert check_schema_publication._git_paths(repo, "HEAD", _RECORDS_DIR) == _RECORDS
    entries, error = check_schema_publication._load_base_manifest(repo, "HEAD")
    assert error is None
    assert entries is not None
    assert sorted(entries) == sorted(_STEMS)


@pytest.mark.parametrize("staged", [True, False])
def test_merge_listing_keeps_every_name(repo: Path, monkeypatch: pytest.MonkeyPatch, staged: bool) -> None:
    """While dev is merged in, the requirement gate lists the delivery diff against the merge parent."""

    _git(repo, "commit", "-q", "-m", "names")
    _git(repo, "checkout", "-q", "-b", "integration", "HEAD~1")
    _write(repo, "upstream.md", "integration\n")
    _git(repo, "add", "upstream.md")
    _git(repo, "commit", "-q", "-m", "integration")
    _git(repo, "update-ref", "refs/remotes/origin/dev", "HEAD")
    _git(repo, "checkout", "-q", "-")
    _git(repo, "merge", "-q", "--no-ff", "--no-commit", "integration")
    monkeypatch.setattr(check_requirement_governance, "REPO_ROOT", repo)

    assert sorted(check_requirement_governance.requirement_changed_paths(staged=staged, base_rev=None)) == _NAMES


_LISTINGS: dict[str, Callable[[Path, ModuleType], object]] = {
    "policy changes": lambda repo, _runner: changed_paths(repo, base_rev="HEAD~1"),
    "hygiene changes": lambda _repo, runner: runner._parse_hygiene_posargs(_SINCE_BASE, default_all_files=False),
    "hygiene all files": lambda _repo, runner: runner._parse_hygiene_posargs(["--all-files"], default_all_files=False),
    "schema publication records": lambda repo, _runner: check_schema_publication._load_base_manifest(repo, "HEAD"),
}


@pytest.mark.parametrize("listing", list(_LISTINGS))
def test_a_name_that_is_not_utf8_stops_the_listing(repo: Path, runner: ModuleType, listing: str) -> None:
    """Names decode as strict UTF-8, like the repository's other -z listings, so the gate fails instead of skipping."""

    blob = _git(repo, "hash-object", "-w", "--stdin", stdin=b"{}\n").strip()
    _git(repo, "update-index", "--add", "--cacheinfo", b"100644," + blob + b"," + _NOT_UTF8_RECORD)
    _git(repo, "commit", "-q", "-m", "names")

    with pytest.raises(UnicodeDecodeError):
        _LISTINGS[listing](repo, runner)
