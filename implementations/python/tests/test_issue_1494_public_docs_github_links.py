"""In-repository GitHub links on public pages must resolve (issue 1494).

``docs/public/conf.py`` keeps links into this repository out of the Sphinx link check.
``tools/check_public_docs.py`` checks their ``blob`` and ``tree`` links on ``main``,
``dev`` and ``HEAD`` against the files git tracks instead.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from tools import check_public_docs
from tools.check_public_docs import REQUIRED_PUBLIC_PAGES, REQUIRED_PUBLIC_REDIRECTS
from tools.public_docs_links import RULE_ID, evaluate_repository_links, repository_link_failures

PAGE = "docs/public/page.md"
REPO = "https://github.com/OpenRAE/rae"
TRACKED = ("README.md", "docs/guide.md", "docs/two words.md", "specs/formal/model.md")
MISSING_FILE = f"{REPO}/blob/main/docs/missing.md"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _failures(line: str) -> list[tuple[str, str | None, str]]:
    return [
        (failure.rule_id, failure.path, failure.message) for failure in repository_link_failures({PAGE: line}, TRACKED)
    ]


@pytest.mark.parametrize(
    "line",
    [
        f"See {REPO}/blob/main/README.md.",
        f"Read the [guide]({REPO}/blob/dev/docs/guide.md).",
        f"<{REPO}/tree/main/specs/formal>",
        f"`Model <{REPO}/blob/HEAD/specs/formal/model.md>`_",
        f'<a href="{REPO}/blob/main/README.md">README</a>',
        f"[specs]({REPO}/tree/main/specs/)",
        f"[repository root]({REPO}/tree/main)",
        f"[install]({REPO}/blob/main/docs/guide.md#install)",
        f"[source]({REPO}/blob/main/README.md?plain=1#L3)",
        f"[spaced]({REPO}/blob/main/docs/two%20words.md)",
        "[former owner](https://github.com/RAESystem/rae/blob/main/README.md)",
    ],
)
def test_links_to_tracked_paths_pass(line: str) -> None:
    assert _failures(line) == []


@pytest.mark.parametrize(
    ("line", "message"),
    [
        (
            f"[missing]({MISSING_FILE})",
            f"{MISSING_FILE} does not resolve: this checkout tracks no file at docs/missing.md",
        ),
        (
            f"[missing]({REPO}/tree/dev/docs/missing)",
            f"{REPO}/tree/dev/docs/missing does not resolve: this checkout tracks no directory at docs/missing",
        ),
        (
            f"[case]({REPO}/blob/HEAD/readme.md)",
            f"{REPO}/blob/HEAD/readme.md does not resolve: this checkout tracks no file at readme.md",
        ),
        (
            "[former owner](https://github.com/RAESystem/rae/blob/main/docs/missing.md)",
            "https://github.com/RAESystem/rae/blob/main/docs/missing.md does not resolve: "
            "this checkout tracks no file at docs/missing.md",
        ),
        (
            f"[spaced]({REPO}/blob/main/docs/two%20word.md)",
            f"{REPO}/blob/main/docs/two%20word.md does not resolve: this checkout tracks no file at docs/two word.md",
        ),
        (
            f"`git show {MISSING_FILE}`",
            f"{MISSING_FILE} does not resolve: this checkout tracks no file at docs/missing.md",
        ),
        (
            f"[{MISSING_FILE}]({MISSING_FILE})",
            f"{MISSING_FILE} does not resolve: this checkout tracks no file at docs/missing.md",
        ),
        (
            f"[specs]({REPO}/blob/main/specs)",
            f"{REPO}/blob/main/specs names a directory: link specs with /tree/, not /blob/",
        ),
        (
            f"[README]({REPO}/tree/main/README.md)",
            f"{REPO}/tree/main/README.md names a file: link README.md with /blob/, not /tree/",
        ),
    ],
)
def test_links_that_do_not_resolve_fail_once_with_the_url(line: str, message: str) -> None:
    assert _failures(line) == [(RULE_ID, f"{PAGE}:1", message)]


@pytest.mark.parametrize(
    "line",
    [
        f"[tag]({REPO}/blob/v6.0.1/docs/missing.md)",
        f"[commit]({REPO}/blob/3011197c/docs/missing.md)",
        f"[branch]({REPO}/tree/release/docs/missing)",
        "[other repository](https://github.com/OpenRAE/env-packs/blob/main/docs/missing.md)",
        f"[issue]({REPO}/issues/813)",
        f"[template]({REPO}/issues/new?template=missing.md)",
        "[plain HTTP](http://github.com/OpenRAE/rae/blob/main/docs/missing.md)",
        "[other host](https://example.com/OpenRAE/rae/blob/main/docs/missing.md)",
        "[relative](../missing.md)",
    ],
)
def test_links_outside_the_checked_scope_are_ignored(line: str) -> None:
    assert _failures(line) == []


@pytest.mark.integration
def test_only_files_that_git_tracks_resolve(tmp_path: Path) -> None:
    _write(tmp_path / "README.md", "# Tracked\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "README.md")
    _write(tmp_path / "docs" / "draft.md", "# On disk, never added\n")
    page = f"[README]({REPO}/blob/main/README.md)\n[draft]({REPO}/blob/main/docs/draft.md)\n"

    failures = evaluate_repository_links(tmp_path, {PAGE: page})

    assert [(failure.path, failure.message) for failure in failures] == [
        (
            f"{PAGE}:2",
            f"{REPO}/blob/main/docs/draft.md does not resolve: this checkout tracks no file at docs/draft.md",
        )
    ]


@pytest.mark.integration
def test_a_checkout_that_git_cannot_list_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))

    failures = evaluate_repository_links(tmp_path, {PAGE: "No links here.\n"})

    assert [(failure.rule_id, failure.path) for failure in failures] == [(RULE_ID, None)]
    assert failures[0].message.startswith("cannot list the files git tracks: ")


@pytest.mark.integration
@pytest.mark.parametrize(
    ("dead_link", "status", "output"),
    [
        ("", 0, []),
        (
            f"See the [missing page]({MISSING_FILE}).\n",
            1,
            [
                f"[{RULE_ID}] docs/public/quickstart.md:4: {MISSING_FILE} does not resolve: "
                "this checkout tracks no file at docs/missing.md"
            ],
        ),
    ],
    ids=["live-link", "dead-link"],
)
def test_checker_reports_dead_links_by_page_line_and_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    dead_link: str,
    status: int,
    output: list[str],
) -> None:
    public_root = tmp_path / "docs" / "public"
    for relative_path in REQUIRED_PUBLIC_PAGES:
        _write(public_root / relative_path, f"# {Path(relative_path).stem.title()}\n")
    _write(public_root / "redirects.json", json.dumps(REQUIRED_PUBLIC_REDIRECTS))
    _write(tmp_path / "README.md", "# RAES\n")
    quickstart = f"# Quickstart\n\nRead the [README]({REPO}/blob/main/README.md).\n{dead_link}"
    _write(public_root / "quickstart.md", quickstart)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    monkeypatch.setattr(check_public_docs, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_public_docs.py"])

    assert check_public_docs.main() == status
    assert capsys.readouterr().out.splitlines() == output


def test_checker_skips_the_link_check_when_the_public_root_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Without a git repository, a link check that ran would add a "cannot list" failure.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    monkeypatch.setattr(check_public_docs, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_public_docs.py"])

    assert check_public_docs.main() == 1
    assert capsys.readouterr().out.splitlines() == [
        "[public-docs-root] docs/public: the curated public documentation root is missing or unsafe"
    ]
