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


def _write_adr(repo: Path, name: str, body: str, *, amended: bool = False) -> None:
    """Write ADR-001 at ``name`` and pin it in the manifest at that path."""
    text = _adr_text(body, amended=amended)
    (repo / ADR_DIR).mkdir(parents=True, exist_ok=True)
    (repo / ADR_DIR / name).write_text(text, encoding="utf-8")
    entry: dict[str, object] = {"id": "ADR-001", "path": (ADR_DIR / name).as_posix(), "pin": content_hash(text)}
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
    "base_rev", ["no-such-rev", "0" * 40, "--all"], ids=["unknown-name", "all-zero-sha", "option-like"]
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
    ],
    ids=["absent", "invalid-yaml", "not-a-mapping", "adrs-not-a-list", "no-usable-entry"],
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
