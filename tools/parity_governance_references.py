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
import itertools
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


def _load(name: str) -> object:
    single = TESTDATA / f"{name}.hex"
    if single.exists():
        encoded = single.read_text(encoding="ascii").strip()
    else:
        encoded = "".join(path.read_text(encoding="ascii").strip() for path in sorted((TESTDATA / name).glob("*.hex")))
    return json.loads(bytes.fromhex(encoded))


def _encoded(value: object, separators: tuple[str, str]) -> str:
    return json.dumps(value, separators=separators, ensure_ascii=True).encode().hex()


def _store(name: str, value: object, separators: tuple[str, str]) -> None:
    encoded = _encoded(value, separators)
    single, directory = TESTDATA / f"{name}.hex", TESTDATA / name
    if not directory.is_dir():
        single.write_text(encoded + "\n", encoding="ascii")
        return
    for part in directory.glob("*.hex"):
        part.unlink()
    for index in range(0, len(encoded), PART_SIZE):
        (directory / f"{index // PART_SIZE:03d}.hex").write_text(encoded[index : index + PART_SIZE] + "\n", "ascii")


def _json_style(text: str, value: object) -> dict[str, object] | None:
    styles = itertools.product((None, 2), ((", ", ": "), (",", ":")), (True, False), ("", "\n"))
    for indent, separators, ensure_ascii, tail in styles:
        style = {"indent": indent, "separators": separators, "ensure_ascii": ensure_ascii, "tail": tail}
        if _dumps(value, style) == text:
            return style
    return None


def _dumps(value: object, style: dict[str, object]) -> str:
    separators = style["separators"]
    if style["indent"] is not None:
        separators = (separators[0].rstrip(), separators[1])
    text = json.dumps(value, indent=style["indent"], separators=separators, ensure_ascii=style["ensure_ascii"])
    return text + style["tail"]


def _strip(container: object, keys: tuple[str, ...], base: object, keep_mutations: bool) -> None:
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


def _rows(value: object, field: str) -> list[object]:
    rows = value.get(field) if isinstance(value, dict) else None
    return rows if isinstance(rows, list) else []


def _strip_rows(value: object, field: str, keys: tuple[str, ...], base: object, keep_mutations: bool) -> None:
    """Strip the retired keys of each row; a row compares with the base row at its index."""
    base_rows = _rows(base, field)
    for index, row in enumerate(_rows(value, field)):
        _strip(row, keys, base_rows[index] if index < len(base_rows) else None, keep_mutations)


# Each catalog: its retired top-level keys and its row collections with their retired keys.
CATALOG_RETIRED: dict[str, tuple[tuple[str, ...], tuple[tuple[str, tuple[str, ...]], ...]]] = {
    PUBLICATION_MANIFEST: (("hash_algorithm",), (("schemas", ("content_hash", "last_change")),)),
    IDENTITY_MANIFEST: (("hash_algorithm",), tuple((field, ("content_sha256",)) for field in IDENTITY_COLLECTIONS)),
    ADR_MANIFEST: (("hash_algorithm",), (("adrs", ("pin",)),)),
}


def _retired(path: str, value: object, base: object, keep_mutations: bool) -> None:
    if path.startswith(PUBLICATION_ENTRIES):
        _strip(value, ("content_hash", "last_change"), base, keep_mutations)
        return
    keys, collections = CATALOG_RETIRED.get(path, ((), ()))
    _strip(value, keys, base, keep_mutations)
    for field, row_keys in collections:
        _strip_rows(value, field, row_keys, base, keep_mutations)


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


def _json_or_none(text: str | None) -> object:
    try:
        return json.loads(text) if text is not None else None
    except ValueError:
        return None


def _migrate_json(path: str, text: str, base_text: str | None, keep_mutations: bool) -> str:
    """Rewrite one JSON catalog in its own style; a non-JSON catalog loses only recorded YAML keys."""
    try:
        value = json.loads(text)
    except ValueError:
        return text if keep_mutations else _yaml_text(path, text)
    style = _json_style(text, value)
    migrated = copy.deepcopy(value)
    _retired(path, migrated, _json_or_none(base_text), keep_mutations)
    return text if style is None or migrated == value else _dumps(migrated, style)


def migrate_text(path: str, text: str | None, base_text: str | None, *, keep_mutations: bool) -> str | None:
    """Return one authored file without the keys that its catalog retired."""
    catalog = path in CATALOG_RETIRED or path.startswith(PUBLICATION_ENTRIES)
    return _migrate_json(path, text, base_text, keep_mutations) if catalog and text is not None else text


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


def _findings(values: list[object]) -> list[dict[str, object]]:
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


def delta_reference(
    evaluate: Callable[[Path], list[object]], targets: re.Pattern[str] | None
) -> Callable[[object], object]:
    """Re-record a base-plus-changes catalog of repository findings."""

    def record(reference: dict[str, object]) -> dict[str, object]:
        old_base = reference["Base"]
        base = migrate_files(old_base, None, keep_mutations=False)
        cases = []
        for case in reference["Cases"]:
            targeted = bool(targets and targets.search(case["Name"]))
            changes = migrate_files(case.get("Changes") or {}, old_base, keep_mutations=targeted)
            files = _delta_files(base, changes)
            # Without the retired key, the case is the valid catalog.
            if targeted and files == base:
                continue
            changes = {name: text for name, text in changes.items() if base.get(name) != text or text is None}
            with repository(files, case.get("Tracked")) as root:
                findings = _findings(evaluate(root))
            recorded = {**case, "Changes": changes, "Findings": findings}
            cases.append(recorded)
        return {**reference, "Base": base, "Cases": cases}

    return record


def _error_type(call: Callable[[], object]) -> tuple[object, str]:
    try:
        return call(), ""
    except (RaesError, OSError, ValueError, TypeError) as exc:
        # The reference records the failing exception type.
        return None, type(exc).__name__


def publication_reference(reference: dict[str, object]) -> dict[str, object]:
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


def publication_history_reference(reference: list[dict[str, object]]) -> list[dict[str, object]]:
    cases, seen = [], set()
    for case in reference:
        if case["Name"] in REMOVED_RULE_CASES:
            continue
        base = migrate_files(case["Base"], None, keep_mutations=False)
        changes = migrate_files(case.get("Changes") or {}, case["Base"], keep_mutations=False)
        key = json.dumps([base, changes, case.get("Revision")], sort_keys=True)
        # The retired ledger was the only difference from an earlier case.
        if key in seen:
            continue
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


class _ListedReference:
    """Re-record a list of independent repository cases."""

    def __init__(
        self,
        evaluate: Callable[[Path], list[object]],
        targets: re.Pattern[str] | None,
        text: Callable[[Path], str] | None,
    ) -> None:
        self.evaluate, self.targets, self.text = evaluate, targets, text

    def evaluated(self, case: dict[str, Any], files: dict[str, str]) -> dict[str, Any]:
        recorded = {**case, "Files": files}
        # A native refusal or error keeps its recording. The parser-depth boundary belongs to the
        # retained recording stack: removing a top-level scalar line leaves the nesting unchanged.
        if case.get("NativeRefusal") or case.get("ErrorType") or case["Name"].startswith(DEPTH_CASE_PREFIX):
            return recorded
        with repository(files, case.get("Tracked")) as root:
            for name, size in (case.get("Padding") or {}).items():
                data = (root / name).read_bytes()
                (root / name).write_bytes(data + b" " * (size - len(data)))
            recorded["Findings"] = _findings(self.evaluate(root))
            if self.text is not None:
                recorded["Text"] = self.text(root)
        return recorded

    def __call__(self, reference: list[dict[str, Any]]) -> list[dict[str, Any]]:
        valid = next((item for item in reference if item["Name"] == "valid"), None)
        valid_files = migrate_files(valid["Files"], None, keep_mutations=False) if valid is not None else None
        cases = []
        for case in reference:
            if case["Name"] in REMOVED_RULE_CASES:
                continue
            files = migrate_files(case["Files"], None, keep_mutations=False)
            if self.targets and self.targets.search(case["Name"]):
                files = migrate_files(case["Files"], valid and valid["Files"], keep_mutations=True)
                # Without the retired key, the case is the valid catalog.
                if files == valid_files:
                    continue
            cases.append(self.evaluated(case, files))
        return cases


def listed_reference(
    evaluate: Callable[[Path], list[object]],
    targets: re.Pattern[str] | None = None,
    text: Callable[[Path], str] | None = None,
) -> Callable[[list[dict[str, Any]]], list[dict[str, Any]]]:
    """Re-record a list of independent repository cases."""
    return _ListedReference(evaluate, targets, text)


RECORDS: dict[str, tuple[Callable[[object], object], tuple[str, str]]] = {
    "identity-reference": (delta_reference(evaluate_identity_cutover, IDENTITY_TARGETS), (",", ":")),
    "deprecation-reference": (delta_reference(evaluate_deprecation_records, None), (",", ":")),
    "publication-reference": (publication_reference, (",", ":")),
    "publication-history-reference": (publication_history_reference, (",", ":")),
    "adr-reference": (listed_reference(evaluate_adr_immutability, ADR_TARGETS), (", ", ": ")),
    "coverage-reference": (listed_reference(evaluate_schema_coverage, text=build_coverage_report), (",", ":")),
}


def _findings_of(reference: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases = reference["Cases"] if isinstance(reference, dict) else reference
    return [item for case in cases for item in case.get("Findings") or []]


def _match_waivable(before: object, after: object) -> object:
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
