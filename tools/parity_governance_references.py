#!/usr/bin/env python3
"""Re-record the Go governance references whose catalogs no longer store derived digests.

The schema publication, identity cutover and ADR catalogs stopped recording
content digests (#1949, #1929). Each reference keeps its authored repository
inputs. The recorder removes the retired keys from those inputs, keeps a
retired key only where a case deliberately mutates it, and records the
findings of the Python checks.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "implementations/python/packages")]

from raes_contracts.errors import RaesError  # noqa: E402

from tools.check_adr_immutability import evaluate_adr_immutability  # noqa: E402
from tools.check_deprecation_lifecycle import evaluate_deprecation_records  # noqa: E402
from tools.check_identity_cutover import evaluate_identity_cutover  # noqa: E402
from tools.check_schema_coverage import build_coverage_report, evaluate_schema_coverage  # noqa: E402
from tools.check_schema_publication import validate_schema_publication_manifest  # noqa: E402

TESTDATA = ROOT / "implementations/tooling/go/governance/testdata"
PART_SIZE = 400_000
MISSING = object()

PUBLICATION_MANIFEST = "contracts/schema-publication-manifest.json"
PUBLICATION_ENTRIES = "contracts/schema-publication/entries/"
IDENTITY_MANIFEST = "tools/policy/historical_identity_records.json"
ADR_MANIFEST = "docs/decisions/adrs/adr-index.yaml"
IDENTITY_COLLECTIONS = ("records", "operational_bindings", "generated_history_records")
# Case names that deliberately mutate a retired key.
IDENTITY_TARGETS = re.compile(r"hash_algorithm|content_sha256")
PUBLICATION_TARGETS = re.compile(r"hash_algorithm|content_hash|^digest-|^last-change-")
ADR_TARGETS = re.compile(r"^(bad-algorithm|bad-pin)$")
# Cases whose only subject was a removed rule: the stale ADR pin and the schema change ledger.
REMOVED_RULE_CASES = {"stale", "null-schema-ledger-quirk"}
DEPTH_CASE_PREFIX = "yaml-depth-"


def _load(name: str) -> Any:
    single = TESTDATA / f"{name}.hex"
    if single.exists():
        encoded = single.read_text(encoding="ascii").strip()
    else:
        encoded = "".join(path.read_text(encoding="ascii").strip() for path in sorted((TESTDATA / name).glob("*.hex")))
    return json.loads(bytes.fromhex(encoded))


def _encoded(value: Any, separators: tuple[str, str]) -> str:
    return json.dumps(value, separators=separators, ensure_ascii=True).encode().hex()


def _store(name: str, value: Any, separators: tuple[str, str]) -> None:
    encoded = _encoded(value, separators)
    single, directory = TESTDATA / f"{name}.hex", TESTDATA / name
    if not directory.is_dir():
        single.write_text(encoded + "\n", encoding="ascii")
        return
    for part in directory.glob("*.hex"):
        part.unlink()
    for index in range(0, len(encoded), PART_SIZE):
        (directory / f"{index // PART_SIZE:03d}.hex").write_text(encoded[index : index + PART_SIZE] + "\n", "ascii")


def _json_style(text: str, value: Any) -> dict[str, Any] | None:
    for indent in (None, 2):
        for separators in ((", ", ": "), (",", ":")):
            for ensure_ascii in (True, False):
                for tail in ("", "\n"):
                    style = {"indent": indent, "separators": separators, "ensure_ascii": ensure_ascii, "tail": tail}
                    if _dumps(value, style) == text:
                        return style
    return None


def _dumps(value: Any, style: dict[str, Any]) -> str:
    separators = style["separators"]
    if style["indent"] is not None:
        separators = (separators[0].rstrip(), separators[1])
    text = json.dumps(value, indent=style["indent"], separators=separators, ensure_ascii=style["ensure_ascii"])
    return text + style["tail"]


def _strip(container: Any, keys: tuple[str, ...], base: Any, keep_mutations: bool) -> None:
    """Remove retired keys; a deliberate mutation keeps a key whose value differs from the base."""
    if not isinstance(container, dict):
        return
    for key in keys:
        if key not in container:
            continue
        reference = base.get(key, MISSING) if isinstance(base, dict) else MISSING
        if keep_mutations and container[key] != reference:
            continue
        del container[key]


def _retired(path: str, value: Any, base: Any, keep_mutations: bool) -> None:
    def at(index: int, field: str) -> Any:
        rows = base.get(field) if isinstance(base, dict) else None
        return rows[index] if isinstance(rows, list) and index < len(rows) else None

    if path == PUBLICATION_MANIFEST:
        _strip(value, ("hash_algorithm",), base, keep_mutations)
        rows = value.get("schemas") if isinstance(value, dict) else None
        for index, row in enumerate(rows if isinstance(rows, list) else []):
            _strip(row, ("content_hash", "last_change"), at(index, "schemas"), keep_mutations)
    elif path.startswith(PUBLICATION_ENTRIES):
        _strip(value, ("content_hash", "last_change"), base, keep_mutations)
    elif path == IDENTITY_MANIFEST:
        _strip(value, ("hash_algorithm",), base, keep_mutations)
        for field in IDENTITY_COLLECTIONS:
            rows = value.get(field) if isinstance(value, dict) else None
            for index, row in enumerate(rows if isinstance(rows, list) else []):
                _strip(row, ("content_sha256",), at(index, field), keep_mutations)
    elif path == ADR_MANIFEST:
        _strip(value, ("hash_algorithm",), base, keep_mutations)
        rows = value.get("adrs") if isinstance(value, dict) else None
        for index, row in enumerate(rows if isinstance(rows, list) else []):
            _strip(row, ("pin",), at(index, "adrs"), keep_mutations)


# YAML manifests that are not JSON lose the retired keys only at their recorded values.
ADR_YAML_RETIRED = (
    (re.compile(r'"hash_algorithm": "sha256", '), ""),
    (re.compile(r"^hash_algorithm: sha256\n", re.MULTILINE), ""),
    (re.compile(r"hash_algorithm: sha256, "), ""),
    (re.compile(r', "pin": "[0-9a-f]{64}"'), ""),
    (re.compile(r"^ +pin: [0-9a-f]{64}\n", re.MULTILINE), ""),
)


def _yaml_text(path: str, text: str) -> str:
    if path != ADR_MANIFEST:
        return text
    for pattern, replacement in ADR_YAML_RETIRED:
        text = pattern.sub(replacement, text)
    return text


def migrate_text(path: str, text: str | None, base_text: str | None, *, keep_mutations: bool) -> str | None:
    """Return one authored file without the keys that its catalog retired."""
    if text is None or not (
        path in {PUBLICATION_MANIFEST, IDENTITY_MANIFEST, ADR_MANIFEST} or path.startswith(PUBLICATION_ENTRIES)
    ):
        return text
    try:
        value = json.loads(text)
    except ValueError:
        return _yaml_text(path, text) if not keep_mutations else text
    style = _json_style(text, value)
    if style is None:
        return text
    try:
        base = json.loads(base_text) if base_text is not None else None
    except ValueError:
        base = None
    migrated = copy.deepcopy(value)
    _retired(path, migrated, base, keep_mutations)
    return text if migrated == value else _dumps(migrated, style)


def migrate_files(
    files: dict[str, str | None], base: dict[str, str] | None, *, keep_mutations: bool
) -> dict[str, str | None]:
    return {
        path: migrate_text(path, text, (base or {}).get(path), keep_mutations=keep_mutations)
        for path, text in files.items()
    }


@contextlib.contextmanager
def repository(files: dict[str, str], tracked: list[str] | None = None) -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        if tracked is not None:
            _git(root, "init", "-q")
        for name, text in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode("utf-8", "surrogateescape"))
        if tracked:
            _git(root, "add", "--", *tracked)
        yield root


def _git(root: Path, *args: str) -> None:
    environment = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=environment)


def _findings(values: list[Any]) -> list[dict[str, Any]]:
    return [
        {"rule_id": item.rule_id, "message": item.message, "path": item.path, "waivable": item.waivable}
        for item in values
    ]


def _delta_files(base: dict[str, str], changes: dict[str, str | None]) -> dict[str, str]:
    files = dict(base)
    for name, text in changes.items():
        if text is None:
            files.pop(name, None)
        else:
            files[name] = text
    return files


def delta_reference(evaluate: Callable[[Path], list[Any]], targets: re.Pattern[str]) -> Callable[[Any], Any]:
    """Re-record a base-plus-changes catalog of repository findings."""

    def record(reference: dict[str, Any]) -> dict[str, Any]:
        old_base = reference["Base"]
        base = migrate_files(old_base, None, keep_mutations=False)
        cases = []
        for case in reference["Cases"]:
            targeted = bool(targets.search(case["Name"]))
            changes = migrate_files(case.get("Changes") or {}, old_base, keep_mutations=targeted)
            files = _delta_files(base, changes)
            if targeted and files == base:
                continue  # Without the retired key, the case is the valid catalog.
            changes = {name: text for name, text in changes.items() if base.get(name) != text or text is None}
            with repository(files, case.get("Tracked")) as root:
                findings = _findings(evaluate(root))
            recorded = {**case, "Changes": changes, "Findings": findings}
            cases.append(recorded)
        return {**reference, "Base": base, "Cases": cases}

    return record


def _error_type(call: Callable[[], Any]) -> tuple[Any, str]:
    try:
        return call(), ""
    except (RaesError, OSError, ValueError, TypeError) as exc:  # The reference records the failing exception type.
        return None, type(exc).__name__


def publication_reference(reference: dict[str, Any]) -> dict[str, Any]:
    old_base = reference["Base"]
    base = migrate_files(old_base, None, keep_mutations=False)
    cases = []
    for case in reference["Cases"]:
        targeted = bool(PUBLICATION_TARGETS.search(case["Name"]))
        changes = migrate_files(case.get("Changes") or {}, old_base, keep_mutations=targeted)
        files = _delta_files(base, changes)
        if targeted and files == base:
            continue
        with repository(files) as root:
            messages, error = _error_type(lambda root=root: validate_schema_publication_manifest(root))
        recorded = {key: value for key, value in case.items() if key not in {"Messages", "ErrorType"}}
        recorded["Changes"] = changes
        if error:
            recorded["ErrorType"] = error
        else:
            recorded["Messages"] = messages
        cases.append(recorded)
    return {**reference, "Base": base, "Cases": cases}


def publication_history_reference(reference: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases, seen = [], set()
    for case in reference:
        if case["Name"] in REMOVED_RULE_CASES:
            continue
        base = migrate_files(case["Base"], None, keep_mutations=False)
        changes = migrate_files(case.get("Changes") or {}, case["Base"], keep_mutations=False)
        key = json.dumps([base, changes, case.get("Revision")], sort_keys=True)
        if key in seen:
            continue  # The retired ledger was the only difference from an earlier case.
        seen.add(key)
        with repository(base, []) as root:
            _git(root, "add", ".")
            _git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "base")
            for name, text in changes.items():
                target = root / name
                if text is None:
                    target.unlink()
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(text, encoding="utf-8")
            revision = case.get("Revision")
            messages, error = _error_type(
                lambda root=root, revision=revision: validate_schema_publication_manifest(root, base_rev=revision)
            )
        recorded = {key: value for key, value in case.items() if key not in {"Messages", "ErrorType"}}
        recorded.update(Base=base, Changes=changes)
        if error:
            recorded["ErrorType"] = error
        else:
            recorded["Messages"] = messages
        cases.append(recorded)
    return cases


def listed_reference(
    evaluate: Callable[[Path], list[Any]],
    targets: re.Pattern[str] | None = None,
    text: Callable[[Path], str] | None = None,
) -> Callable[[Any], Any]:
    """Re-record a list of independent repository cases."""

    def record(reference: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cases = []
        for case in reference:
            if case["Name"] in REMOVED_RULE_CASES:
                continue
            targeted = bool(targets and targets.search(case["Name"]))
            files = migrate_files(case["Files"], None, keep_mutations=False)
            if targeted:
                valid = next((item for item in reference if item["Name"] == "valid"), None)
                original = migrate_files(case["Files"], valid and valid["Files"], keep_mutations=True)
                if valid is not None and original == migrate_files(valid["Files"], None, keep_mutations=False):
                    continue
                files = original
            recorded = {**case, "Files": files}
            if case.get("NativeRefusal") or case.get("ErrorType"):
                cases.append(recorded)
                continue
            if case["Name"].startswith(DEPTH_CASE_PREFIX):
                # The parser-depth boundary belongs to the retained recording stack, not to the
                # catalog keys; removing a top-level scalar line leaves the nesting unchanged.
                cases.append(recorded)
                continue
            with repository(files, case.get("Tracked")) as root:
                if case.get("Padding"):
                    for name, size in case["Padding"].items():
                        data = (root / name).read_bytes()
                        (root / name).write_bytes(data + b" " * (size - len(data)))
                recorded["Findings"] = _findings(evaluate(root))
                if text is not None:
                    recorded["Text"] = text(root)
            cases.append(recorded)
        return cases

    return record


RECORDS: dict[str, tuple[Callable[[Any], Any], tuple[str, str]]] = {
    "identity-reference": (delta_reference(evaluate_identity_cutover, IDENTITY_TARGETS), (",", ":")),
    "deprecation-reference": (delta_reference(evaluate_deprecation_records, re.compile("(?!)")), (",", ":")),
    "publication-reference": (publication_reference, (",", ":")),
    "publication-history-reference": (publication_history_reference, (",", ":")),
    "adr-reference": (listed_reference(evaluate_adr_immutability, ADR_TARGETS), (", ", ": ")),
    "coverage-reference": (listed_reference(evaluate_schema_coverage, text=build_coverage_report), (",", ":")),
}


def _findings_of(reference: Any) -> list[dict[str, Any]]:
    cases = reference["Cases"] if isinstance(reference, dict) else reference
    return [item for case in cases for item in case.get("Findings") or []]


def _match_waivable(before: Any, after: Any) -> Any:
    """Keep the finding fields of the retained catalog; some catalogs never recorded waivability."""
    if any("waivable" in item for item in _findings_of(before)):
        return after
    for item in _findings_of(after):
        item.pop("waivable", None)
    return after


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("names", nargs="*")
    args = parser.parse_args()
    failed = False
    for name, (record, separators) in RECORDS.items():
        if args.names and name not in args.names:
            continue
        before = _load(name)
        after = _match_waivable(before, record(copy.deepcopy(before)))
        if args.check:
            if after != before:
                print(f"{name} differs from the Python governance checks", file=sys.stderr)
                failed = True
        elif after != before:
            _store(name, after, separators)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
