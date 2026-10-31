"""Regression tests for #1567: the ADR-059 pin gate's base comparison.

Each test builds a throwaway git repository with one accepted, pinned ADR
committed as the base, makes a change on top, and runs the gate. Before #1567
the gate read the base copy at the ADR's current path, so a renamed ADR was
treated as newly added, and a ``--base-rev`` that named no commit skipped every
ADR; both passed with no ``## Amendments`` record.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import tools.check_adr_immutability as adr_gate
import yaml
from tools.check_adr_immutability import content_hash, evaluate_adr_immutability
from tools.policy.common import PolicyFailure

ADR_DIR = Path("docs/decisions/adrs")
ORIGINAL_NAME = "adr-001-example.md"
RENAMED_NAME = "adr-001-renamed-example.md"
ORIGINAL_BODY = "The decision body."
EDITED_BODY = "A materially rewritten decision body."
AMENDMENT_REF = "abc1234"


AMENDMENTS_SECTION = (
    "\n## Amendments\n\n| Date | Commit/PR | Summary |\n|------|-----------|---------|\n"
    f"| 2026-10-12 | {AMENDMENT_REF} | rewrote the body |\n"
)


def _adr_text(body: str, *, amended: bool = False) -> str:
    text = f"# ADR-001: Example\n\n## Status\n\naccepted\n\n## Date\n\n2026-04-05\n\n## Context\n\n{body}\n"
    return text + AMENDMENTS_SECTION if amended else text


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _write_adr(repo: Path, name: str, body: str, *, amended: bool = False, recorded_path: str | None = None) -> None:
    """Write ADR-001 at ``name`` and pin it in the manifest at ``recorded_path``
    (default: that path)."""
    text = _adr_text(body, amended=amended)
    (repo / ADR_DIR).mkdir(parents=True, exist_ok=True)
    (repo / ADR_DIR / name).write_text(text, encoding="utf-8")
    entry: dict[str, object] = {
        "id": "ADR-001",
        "path": recorded_path or (ADR_DIR / name).as_posix(),
        "pin": content_hash(text),
    }
    if amended:
        entry["amendments"] = [{"date": "2026-10-12", "ref": AMENDMENT_REF, "summary": "rewrote the body"}]
    manifest = {"hash_algorithm": "sha256", "adrs": [entry]}
    (repo / ADR_DIR / "adr-index.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _write_adr(tmp_path, ORIGINAL_NAME, ORIGINAL_BODY)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _rename(repo: Path, body: str, *, amended: bool = False) -> None:
    """Rename ADR-001's file, then rewrite it and its manifest entry (path and pin)."""
    _git(repo, "mv", (ADR_DIR / ORIGINAL_NAME).as_posix(), (ADR_DIR / RENAMED_NAME).as_posix())
    _write_adr(repo, RENAMED_NAME, body, amended=amended)


def _evaluate(repo: Path, mode: str) -> list[PolicyFailure]:
    if mode == "staged":
        _git(repo, "add", "-A")
        return evaluate_adr_immutability(repo, staged=True)
    return evaluate_adr_immutability(repo, base_rev="HEAD")


@pytest.mark.parametrize("mode", ["base-rev", "staged"])
def test_renamed_accepted_adr_edit_without_amendment_is_unrecorded(repo: Path, mode: str) -> None:
    _rename(repo, EDITED_BODY)

    failures = _evaluate(repo, mode)

    assert [(failure.rule_id, failure.path) for failure in failures] == [
        (adr_gate.RULE_AMENDMENT_UNRECORDED, (ADR_DIR / RENAMED_NAME).as_posix())
    ]


@pytest.mark.parametrize("mode", ["base-rev", "staged"])
@pytest.mark.parametrize(
    ("body", "amended"),
    [(ORIGINAL_BODY, False), (EDITED_BODY, True)],
    ids=["content-unchanged", "amendment-recorded"],
)
def test_renamed_accepted_adr_passes_when_unchanged_or_amended(repo: Path, mode: str, body: str, amended: bool) -> None:
    _rename(repo, body, amended=amended)

    assert _evaluate(repo, mode) == []


@pytest.mark.parametrize(
    "base_rev",
    ["no-such-rev", "0" * 40, "--all", "HEAD^{tree}"],
    ids=["unknown-name", "all-zero-sha", "option-like", "tree-instead-of-commit"],
)
def test_unresolvable_base_rev_fails_with_named_rule(repo: Path, base_rev: str) -> None:
    _write_adr(repo, ORIGINAL_NAME, EDITED_BODY)

    failures = evaluate_adr_immutability(repo, base_rev=base_rev)

    assert [failure.rule_id for failure in failures] == [adr_gate.RULE_BASE_UNRESOLVED]
    assert repr(base_rev) in failures[0].message


def test_cli_reports_unresolvable_base_rev(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(adr_gate, "REPO_ROOT", repo)
    monkeypatch.setattr(adr_gate, "load_exceptions", lambda _root: [])

    assert adr_gate.main(["--base-rev", "no-such-rev"]) == 1
    assert f"[{adr_gate.RULE_BASE_UNRESOLVED}]" in capsys.readouterr().err


@pytest.mark.parametrize(
    "base_manifest",
    [
        None,
        "adrs: [\n",
        "- not a mapping\n",
        "hash_algorithm: sha256\nadrs: {}\n",
        "adrs:\n- not-an-entry\n- {id: ADR-001}\n",
        "date: 2026-99-99\n",
        "value: !!bool unknown\n",
        "value: !!int ''\n",
    ],
    ids=[
        "absent",
        "invalid-yaml",
        "not-a-mapping",
        "adrs-not-a-list",
        "no-usable-entry",
        "invalid-date",
        "invalid-bool",
        "invalid-int",
    ],
)
def test_base_without_usable_manifest_compares_at_current_path(repo: Path, base_manifest: str | None) -> None:
    manifest = repo / ADR_DIR / "adr-index.yaml"
    if base_manifest is None:
        manifest.unlink()
    else:
        manifest.write_text(base_manifest, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base without a usable manifest")
    _write_adr(repo, ORIGINAL_NAME, EDITED_BODY)

    failures = evaluate_adr_immutability(repo, base_rev="HEAD")

    assert [(failure.rule_id, failure.path) for failure in failures] == [
        (adr_gate.RULE_AMENDMENT_UNRECORDED, (ADR_DIR / ORIGINAL_NAME).as_posix())
    ]


@pytest.mark.parametrize("mode", ["base-rev", "staged"])
@pytest.mark.parametrize(
    "recorded_path",
    [
        f"{ADR_DIR.as_posix()}/./{ORIGINAL_NAME}",
        f"./{ADR_DIR.as_posix()}/{ORIGINAL_NAME}",
        f"docs//decisions/adrs/{ORIGINAL_NAME}",
        f"docs/decisions/adrs-link/{ORIGINAL_NAME}",
    ],
    ids=["dot-segment", "leading-dot", "double-slash", "symlinked-dir"],
)
def test_unnormalized_base_manifest_path_still_compares_the_base_copy(
    repo: Path, mode: str, recorded_path: str
) -> None:
    """A manifest path that resolves to the ADR file but is not the literal path
    git stores must not make the edited ADR look newly added."""
    (repo / "docs/decisions/adrs-link").symlink_to("adrs", target_is_directory=True)
    _write_adr(repo, ORIGINAL_NAME, ORIGINAL_BODY, recorded_path=recorded_path)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base pinned at an unnormalized path")
    _write_adr(repo, ORIGINAL_NAME, EDITED_BODY, recorded_path=recorded_path)

    failures = _evaluate(repo, mode)

    assert [(failure.rule_id, failure.path) for failure in failures] == [
        (adr_gate.RULE_AMENDMENT_UNRECORDED, (ADR_DIR / ORIGINAL_NAME).as_posix())
    ]


@pytest.mark.parametrize("mode", ["base-rev", "staged"])
def test_accepted_adr_absent_at_base_is_treated_as_newly_added(repo: Path, mode: str) -> None:
    _git(repo, "rm", "-q", "-r", ADR_DIR.as_posix())
    _git(repo, "commit", "-q", "-m", "base without ADR-001")
    _write_adr(repo, ORIGINAL_NAME, EDITED_BODY)

    assert _evaluate(repo, mode) == []


@pytest.mark.parametrize("mode", ["base-rev", "staged"])
@pytest.mark.parametrize("link_type", ["directory", "file", "chain"])
@pytest.mark.parametrize(
    ("body", "amended", "unrecorded"),
    [(EDITED_BODY, False, True), (ORIGINAL_BODY, False, False), (EDITED_BODY, True, False)],
    ids=["unrecorded-edit", "content-unchanged", "amendment-recorded"],
)
def test_renamed_adr_compares_through_base_symlink_after_link_is_removed(
    repo: Path, mode: str, link_type: str, body: str, amended: bool, unrecorded: bool
) -> None:
    if link_type == "file":
        link = repo / "docs/adr-link.md"
        link.symlink_to(f"decisions/adrs/{ORIGINAL_NAME}")
        recorded_path = link.relative_to(repo).as_posix()
    else:
        link = repo / "docs/decisions/adrs-link"
        link.symlink_to("adrs", target_is_directory=True)
        if link_type == "chain":
            link = repo / "docs/adrs-chain"
            link.symlink_to("decisions/adrs-link", target_is_directory=True)
        recorded_path = f"{link.relative_to(repo).as_posix()}/{ORIGINAL_NAME}"
    _write_adr(repo, ORIGINAL_NAME, ORIGINAL_BODY, recorded_path=recorded_path)
    assert evaluate_adr_immutability(repo) == []  # the base manifest is valid
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "pin ADR through an in-repository symlink")

    _rename(repo, body, amended=amended)
    link.unlink()  # resolution must use the historical tree, not the checkout

    failures = _evaluate(repo, mode)

    assert [(failure.rule_id, failure.path) for failure in failures] == (
        [(adr_gate.RULE_AMENDMENT_UNRECORDED, (ADR_DIR / RENAMED_NAME).as_posix())] if unrecorded else []
    )


@pytest.mark.parametrize("target", ["/outside.md", "../../../outside.md", "missing.md", "link"])
def test_base_blob_read_refuses_outside_dangling_and_looping_symlinks(repo: Path, target: str) -> None:
    link = repo / "docs/decisions/link"
    link.symlink_to(target)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add an unresolvable symlink")

    assert adr_gate._git_show(repo, "HEAD:docs/decisions/link", follow_symlinks=True) is None


@pytest.mark.parametrize("payload", [b"", b"text\r\nwith a final newline\n", b"non-UTF8: \xff\n"])
def test_base_blob_read_preserves_exact_bytes(repo: Path, payload: bytes) -> None:
    (repo / "payload.bin").write_bytes(payload)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add historical blob bytes")

    text = adr_gate._git_show(repo, "HEAD:payload.bin", follow_symlinks=True)

    assert text is not None
    assert text.encode("utf-8", errors="surrogateescape") == payload


@pytest.mark.parametrize("path", ["docs/decisions/adrs", "missing.md"])
def test_base_blob_read_requires_an_existing_blob(repo: Path, path: str) -> None:
    assert adr_gate._git_show(repo, f"HEAD:{path}", follow_symlinks=True) is None


@pytest.mark.parametrize("revision", ["", "--all", "HEAD\n--all", "HEAD:path", "HEAD;whoami"])
def test_invalid_base_revision_never_reaches_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, revision: str
) -> None:
    def unexpected_subprocess(*args: object, **kwargs: object) -> None:
        pytest.fail("invalid revision reached the subprocess boundary")

    monkeypatch.setattr(adr_gate.subprocess, "run", unexpected_subprocess)

    assert adr_gate._resolve_commit(tmp_path, revision) is None
