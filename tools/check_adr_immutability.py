#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Acceptance-content pin gate for accepted ADRs (ADR-059).

``docs/decisions/adrs/README.md`` claims the ADR corpus is citable — an
accepted ADR's content does not silently change under you. ADR-059 makes that
claim enforceable instead of aspirational: ``docs/decisions/adrs/adr-index.yaml``
pins every *accepted* ADR to the ``sha256`` of its **canonical content** (the
file with its ``## Amendments`` section removed), and a substantive change to an
accepted ADR is only legitimate when it is recorded — as a new ``## Amendments``
row plus an updated pin, or by superseding the ADR with a new one.

What this gate enforces, filesystem-only and deterministically (it never calls
Ground Control, so it cannot become flaky in CI):

* the manifest is well-formed: a mapping with ``hash_algorithm: sha256`` and an
  ``adrs`` list of ``{id, path, pin, amendments?}`` entries, unique ids, repo-
  relative non-escaping paths (via the shared ``safe_repo_path``);
* every ADR whose on-disk status is ``accepted`` has exactly one manifest entry
  (``adr-pin-missing``), and every manifest entry names an ADR that is
  ``accepted`` on disk (``adr-pin-orphan``) — only ``accepted`` ADRs are pinned;
  ``proposed`` stay mutable and ``superseded``/``deprecated`` leave the pin set;
* each pinned ADR's current canonical hash equals its pin (``adr-pin-stale``) —
  the unrecorded-edit detector;
* the manifest ``amendments[]`` refs match the ADR's ``## Amendments`` table rows
  1:1 (``adr-amendment-record-mismatch``);
* with ``--base-rev``/``--staged``: an accepted ADR whose canonical content
  changed versus the base must also have gained a ``## Amendments`` record in the
  same change (``adr-amendment-unrecorded``) — this is what stops a bare pin bump
  from blessing an undocumented edit. (Status transitions to
  superseded/deprecated and superseding ADRs naturally leave the accepted set, so
  they are not flagged.) The base copy is read at the path the base revision's
  manifest records for the same ADR id, so renaming the file does not hide an
  edit, and a ``--base-rev`` that names no commit fails
  (``adr-base-rev-unresolved``) instead of comparing nothing.

Failures use ``tools.policy.common.PolicyFailure``; the CLI honours ``--json`` and
the shared ``tools/policy/exceptions.yaml`` waiver mechanism like the other
``policy`` nox-stage entry points.
"""

from __future__ import annotations

import argparse
import hashlib
import posixpath
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

import yaml
from raes_contracts.errors import InvalidInputError
from raes_contracts.operational_logging import run_application

from tools.policy.adr import parse_adr_file
from tools.policy.common import (
    YAML_CONTENT_FAILURES,
    PolicyFailure,
    apply_exceptions,
    failures_to_json,
    load_exceptions,
    load_yaml,
    safe_repo_path,
)

ADR_DIR = "docs/decisions/adrs"
MANIFEST_PATH = f"{ADR_DIR}/adr-index.yaml"
SUPPORTED_HASH_ALGORITHM = "sha256"

ADR_ID_RE = re.compile(r"^ADR-\d{3}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
AMENDMENTS_HEADING_RE = re.compile(r"##\s+Amendments\s*")
SECTION_HEADING_RE = re.compile(r"##\s+")

RULE_MALFORMED = "adr-manifest-malformed"
RULE_PATH_UNSAFE = "adr-manifest-path-unsafe"
RULE_PIN_STALE = "adr-pin-stale"
RULE_PIN_MISSING = "adr-pin-missing"
RULE_PIN_ORPHAN = "adr-pin-orphan"
RULE_AMENDMENT_MISMATCH = "adr-amendment-record-mismatch"
RULE_AMENDMENT_UNRECORDED = "adr-amendment-unrecorded"
RULE_BASE_UNRESOLVED = "adr-base-rev-unresolved"


def _amendments_section_bounds(text: str) -> tuple[int, int] | None:
    """Character bounds ``(start, end)`` of the ``## Amendments`` section — its
    heading through the line before the next ``##`` heading (or end of file).
    Headings inside fenced code blocks are ignored, so an ``## Amendments``
    *example* in an ADR's prose (e.g. ADR-059) is not mistaken for a real
    section. Returns None when the ADR has no Amendments section."""
    lines = text.splitlines(keepends=True)
    starts: list[int] = []
    cursor = 0
    for line in lines:
        starts.append(cursor)
        cursor += len(line)
    total = cursor

    in_fence = False
    heading_line: int | None = None
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        body = line.rstrip("\n")
        if heading_line is None:
            if AMENDMENTS_HEADING_RE.fullmatch(body):
                heading_line = index
        elif SECTION_HEADING_RE.match(body):
            return starts[heading_line], starts[index]
    if heading_line is None:
        return None
    return starts[heading_line], total


def _strip_amendments(text: str) -> str:
    """Return ``text`` with its ``## Amendments`` section removed."""
    bounds = _amendments_section_bounds(text)
    if bounds is None:
        return text
    start, end = bounds
    return text[:start] + text[end:]


def canonical_content(text: str) -> str:
    """The bytes the pin is taken over: the ADR minus its ``## Amendments``
    section, with per-line trailing whitespace removed and exactly one trailing
    newline. Recording an amendment therefore never perturbs the pin, and
    per-line trailing-whitespace churn is not treated as a substantive edit.
    Only the file-final newline run is normalized (a text file with or without a
    final newline hashes the same); leading blank lines and interior blank lines
    are significant, so adding or removing one is a detectable content change."""
    body = _strip_amendments(text)
    lines = [line.rstrip() for line in body.splitlines()]
    return "\n".join(lines).rstrip("\n") + "\n"


def content_hash(text: str) -> str:
    # surrogateescape gives text that was read with it its exact bytes back; other text encodes unchanged.
    return hashlib.sha256(canonical_content(text).encode("utf-8", "surrogateescape")).hexdigest()


def amendment_refs(text: str) -> list[str]:
    """The commit/PR ref column of the ``## Amendments`` markdown table
    (``| Date | Commit/PR | Summary |``), in document order. Header and
    separator rows are skipped."""
    bounds = _amendments_section_bounds(text)
    if bounds is None:
        return []
    start, end = bounds
    section = text[start:end]
    refs: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if cells[0].lower() == "date":  # header row
            continue
        if set("".join(cells)) <= set("-: "):  # separator row
            continue
        refs.append(cells[1])
    return refs


def _coerce_manifest(raw: object, manifest_rel: str) -> tuple[list[dict] | None, list[PolicyFailure]]:
    """Validate the manifest shape. Returns ``(entries, [])`` on success, or
    ``(None, failures)`` when the manifest is malformed — shape errors are
    reported before any hash comparison so a broken manifest fails cleanly."""

    def fail(message: str) -> PolicyFailure:
        return PolicyFailure(RULE_MALFORMED, message, manifest_rel)

    if not isinstance(raw, dict):
        return None, [fail("manifest root must be a mapping")]
    algorithm = raw.get("hash_algorithm")
    if algorithm != SUPPORTED_HASH_ALGORITHM:
        return None, [fail(f"hash_algorithm must be '{SUPPORTED_HASH_ALGORITHM}'; got {algorithm!r}")]
    entries = raw.get("adrs")
    if not isinstance(entries, list):
        return None, [fail("'adrs' must be a list")]

    failures: list[PolicyFailure] = []
    normalized: list[dict] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            failures.append(fail(f"adrs[{index}] must be a mapping"))
            continue
        adr_id = entry.get("id")
        path = entry.get("path")
        pin = entry.get("pin")
        if not isinstance(adr_id, str) or not ADR_ID_RE.match(adr_id):
            failures.append(fail(f"adrs[{index}].id must match ADR-NNN; got {adr_id!r}"))
            continue
        if adr_id in seen_ids:
            failures.append(fail(f"duplicate manifest entry for {adr_id}"))
            continue
        seen_ids.add(adr_id)
        if not isinstance(path, str) or not path:
            failures.append(fail(f"{adr_id}: path must be a non-empty string"))
            continue
        if not isinstance(pin, str) or not SHA256_RE.match(pin):
            failures.append(fail(f"{adr_id}: pin must be a 64-character sha256 hex digest"))
            continue
        amendments = entry.get("amendments") or []
        if not isinstance(amendments, list):
            failures.append(fail(f"{adr_id}: amendments must be a list"))
            continue
        refs: list[str] = []
        malformed_amendment = False
        for aindex, amendment in enumerate(amendments):
            if not isinstance(amendment, dict) or not isinstance(amendment.get("ref"), str):
                failures.append(fail(f"{adr_id}: amendments[{aindex}] must be a mapping with a string 'ref'"))
                malformed_amendment = True
                break
            refs.append(amendment["ref"])
        if malformed_amendment:
            continue
        normalized.append({"id": adr_id, "path": path, "pin": pin, "amendment_refs": refs})

    if failures:
        return None, failures
    return normalized, []


def _rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _accepted_adrs(repo_root: Path) -> dict[str, Path]:
    """Map ``ADR-NNN`` → file for every ADR whose on-disk status is accepted.
    Unparseable ADR files are repo_policy's concern, not this gate's."""
    accepted: dict[str, Path] = {}
    adr_dir = repo_root / ADR_DIR
    for adr_file in sorted(adr_dir.glob("adr-*.md")):
        if adr_file.name == "README.md":
            continue
        try:
            number, _title, status, _date = parse_adr_file(adr_file)
        except InvalidInputError:
            continue
        if status == "accepted":
            accepted[f"ADR-{number}"] = adr_file
    return accepted


def _git_show(repo_root: Path, gitref: str, *, follow_symlinks: bool = False) -> str | None:
    """Content of a path at a git ref (``<rev>:<path>`` or ``:<path>`` for the
    index). Returns None when the path does not exist at that ref.

    Content that is not UTF-8 is read again with surrogate escapes. They keep
    every byte distinct, so content_hash and the amendment check compare the
    exact revision."""
    # Only a revision that starts with a letter, digit or underscore, an optional repository path, or an
    # index path can reach git; git would read a value that starts with "-" as an option.
    if not re.match(r"^(?:\w[\w./@^~{}-]*(?::[\w./-]+)?|:[\w./-]+)\Z", gitref, re.ASCII):
        raise InvalidInputError("a git revision must not start with '-' or contain other characters")
    if follow_symlinks:
        # Git resolves links in the historical tree, never against the checkout.
        # Index reads keep using show: cat-file cannot follow index symlinks.
        proc = subprocess.run(
            ["git", "cat-file", "--batch", "--follow-symlinks"],
            input=f"{gitref}\n".encode(),
            cwd=repo_root,
            capture_output=True,
        )
        if proc.returncode != 0:
            return None
        header, _, payload = proc.stdout.partition(b"\n")
        fields = header.split()
        # Missing/dangling/looping links, directories and links outside the tree
        # have no blob response. In particular, an outside link is never read.
        if len(fields) != 3 or fields[1] != b"blob":
            return None
        return payload[: int(fields[2])].decode("utf-8", errors="surrogateescape")
    command = ["git", "show", "--end-of-options", gitref]
    try:
        proc = subprocess.run(command, cwd=repo_root, capture_output=True, text=True)
    except UnicodeDecodeError:
        proc = subprocess.run(command, cwd=repo_root, capture_output=True, text=True, errors="surrogateescape")
    if proc.returncode != 0:
        return None
    return proc.stdout


def _resolve_commit(repo_root: Path, rev: str) -> str | None:
    """Full SHA of the commit ``rev`` names, or None when it names no commit.
    ``--end-of-options`` keeps a ``rev`` that starts with ``-`` from being read
    as a git option."""
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "--end-of-options", f"{rev}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _base_manifest_paths(repo_root: Path, base: str) -> dict[str, str]:
    """``ADR-NNN`` → path recorded in the base revision's manifest, normalized
    (``./`` and ``//`` segments removed) because ``git show`` needs the literal
    tree path. Empty when the base has no readable manifest (for example a
    revision before ADR-059)."""
    text = _git_show(repo_root, f"{base}:{MANIFEST_PATH}", follow_symlinks=True)
    try:
        raw = yaml.safe_load(text) if text is not None else None
    except (yaml.YAMLError, *YAML_CONTENT_FAILURES):
        raw = None
    entries = raw.get("adrs") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        return {}
    return {
        entry["id"]: posixpath.normpath(entry["path"])
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("id"), str) and isinstance(entry.get("path"), str)
    }


def _base_copy(repo_root: Path, base: str, recorded: str | None, rel: str) -> str | None:
    """The ADR's text at ``base``: at the base manifest's ``recorded`` path, else
    at its current path ``rel``. Resolve symlinks in that revision so a renamed
    file remains comparable even when its old manifest path used a link.
    None only when neither path resolves to a blob at ``base``."""
    for path in dict.fromkeys((recorded or rel, rel)):
        text = _git_show(repo_root, f"{base}:{path}", follow_symlinks=True)
        if text is not None:
            return text
    return None


def _check_unrecorded_edits(
    repo_root: Path,
    accepted: dict[str, Path],
    *,
    base_rev: str | None,
    staged: bool,
) -> list[PolicyFailure]:
    """A pin bump alone must not bless an edit: when an accepted ADR's canonical
    content changed versus the base, the same change must also have added a
    ``## Amendments`` record. The base copy is the file at the path the base
    manifest records for the same ADR id, or at the current path when the base
    manifest has none or git stores nothing there, so a rename cannot hide an
    edit."""
    if staged:
        base = "HEAD"
    else:
        resolved = _resolve_commit(repo_root, str(base_rev))
        if resolved is None:
            return [
                PolicyFailure(
                    RULE_BASE_UNRESOLVED,
                    f"--base-rev {base_rev!r} does not name a commit in this repository, so no "
                    "accepted ADR can be compared against its base; fetch the base or pass a valid revision",
                )
            ]
        base = resolved
    base_paths = _base_manifest_paths(repo_root, base)
    failures: list[PolicyFailure] = []
    for adr_id, disk_path in accepted.items():
        rel = _rel(repo_root, disk_path)
        base_text = _base_copy(repo_root, base, base_paths.get(adr_id), rel)
        if base_text is None:
            continue  # not present at base (newly added) — nothing to compare
        head_text = _git_show(repo_root, f":{rel}") if staged else disk_path.read_text(encoding="utf-8")
        if head_text is None or content_hash(base_text) == content_hash(head_text):
            continue
        new_refs = set(amendment_refs(head_text)) - set(amendment_refs(base_text))
        if new_refs:
            continue
        failures.append(
            PolicyFailure(
                RULE_AMENDMENT_UNRECORDED,
                f"{adr_id}: accepted ADR content changed without a new ## Amendments record; "
                "add an amendment (and update its pin) or supersede it with a new ADR",
                rel,
            )
        )
    return failures


def evaluate_adr_immutability(
    repo_root: Path,
    *,
    base_rev: str | None = None,
    staged: bool = False,
) -> list[PolicyFailure]:
    manifest_rel = MANIFEST_PATH
    manifest_file = repo_root / manifest_rel
    if not manifest_file.is_file():
        return [PolicyFailure(RULE_MALFORMED, "ADR pin manifest is missing", manifest_rel)]
    try:
        raw = load_yaml(manifest_file)
    except OSError, UnicodeDecodeError, yaml.YAMLError, RecursionError, InvalidInputError:
        # An unreadable or malformed manifest, including a scalar that the safe
        # constructor cannot build, is a clean failure, not a traceback.
        return [PolicyFailure(RULE_MALFORMED, "ADR pin manifest is not valid YAML", manifest_rel)]

    entries, failures = _coerce_manifest(raw, manifest_rel)
    if entries is None:
        return failures

    # Path safety before any file read.
    resolved: dict[str, Path] = {}
    for entry in entries:
        safe = safe_repo_path(repo_root, entry["path"])
        if safe is None:
            failures.append(
                PolicyFailure(RULE_PATH_UNSAFE, f"{entry['id']}: path escapes the repository", entry["path"])
            )
            continue
        resolved[entry["id"]] = safe
    if failures:
        return failures

    accepted = _accepted_adrs(repo_root)
    manifest_ids = {entry["id"] for entry in entries}

    # Coverage both ways.
    for adr_id, disk_path in accepted.items():
        if adr_id not in manifest_ids:
            failures.append(
                PolicyFailure(
                    RULE_PIN_MISSING,
                    f"{adr_id} is accepted but not pinned in the manifest",
                    _rel(repo_root, disk_path),
                )
            )
    for entry in entries:
        if entry["id"] not in accepted:
            failures.append(
                PolicyFailure(
                    RULE_PIN_ORPHAN,
                    f"manifest pins {entry['id']} but it is missing or not 'accepted' on disk",
                    entry["path"],
                )
            )

    # Pin + amendment-record checks for entries that are accepted on disk.
    for entry in entries:
        adr_id = entry["id"]
        disk_path = accepted.get(adr_id)
        if disk_path is None:
            continue  # already reported as orphan
        if resolved[adr_id] != disk_path.resolve():
            failures.append(
                PolicyFailure(
                    RULE_MALFORMED,
                    f"{adr_id}: manifest path does not resolve to the ADR file on disk",
                    entry["path"],
                )
            )
            continue
        text = disk_path.read_text(encoding="utf-8")
        if content_hash(text) != entry["pin"]:
            failures.append(
                PolicyFailure(
                    RULE_PIN_STALE,
                    f"{adr_id} content differs from its pinned hash; record an amendment "
                    "(and update the pin) or supersede it with a new ADR",
                    entry["path"],
                )
            )
        document_refs = amendment_refs(text)
        if sorted(document_refs) != sorted(entry["amendment_refs"]):
            failures.append(
                PolicyFailure(
                    RULE_AMENDMENT_MISMATCH,
                    f"{adr_id}: manifest amendment refs {sorted(entry['amendment_refs'])} do not match "
                    f"the ADR ## Amendments rows {sorted(document_refs)}",
                    entry["path"],
                )
            )

    if failures:
        return failures

    if base_rev or staged:
        failures.extend(_check_unrecorded_edits(repo_root, accepted, base_rev=base_rev, staged=staged))
    return failures


def _git_revision(value: str) -> str:
    """Accept a revision argument that git cannot read as an option."""
    if not re.match(r"^\w[\w./@^~{}-]*\Z", value, re.ASCII):
        raise argparse.ArgumentTypeError("a git revision must not be empty, start with '-' or contain other characters")
    return value


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enforce ADR-059 acceptance-content pins for accepted ADRs.")
    parser.add_argument("--staged", action="store_true", help="Compare staged content against HEAD.")
    parser.add_argument("--base-rev", type=_git_revision, help="Compare against a specific git revision.")
    parser.add_argument("--json", action="store_true", help="Emit JSON failures.")
    # Accepted for CLI parity with the other policy entry points. The pin gate
    # always evaluates the whole accepted-ADR corpus — a partial path list could
    # not prove corpus-wide coverage — so an explicit path list is not consulted.
    parser.add_argument("--paths", nargs="*", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    failures = evaluate_adr_immutability(REPO_ROOT, base_rev=args.base_rev, staged=args.staged)
    try:
        failures = apply_exceptions(failures, load_exceptions(REPO_ROOT))
    except InvalidInputError as exc:
        print(f"adr-immutability: {exc}", file=sys.stderr)
        return 1
    if failures:
        if args.json:
            print(failures_to_json(failures))
        else:
            for failure in failures:
                print(failure.render(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
