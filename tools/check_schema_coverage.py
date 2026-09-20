#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Structural gate: every published schema carries concrete coverage evidence.

A contract can be published, hashed, ledgered and metaschema-valid while nothing
in the repository ever exercises it. ``check_schema_publication.py`` proves the
inventory, hashes, stability and evolution of the published set; it does not ask
whether anything supports a contract's claims. This gate asks exactly that, by
schema path, over the whole published inventory.

A published schema is **covered** when at least one of these holds:

1. **Corpus coverage.** At least one checked-in artifact that the canonical
   corpus router (``check_json_artifacts.covered_schema_paths``) routes to that
   exact schema path. The set is non-empty by construction, so an empty
   ``valid/`` directory, an ``invalid/``-only family and a bare directory are
   not coverage. Alternate routes are inherited from the router, never copied.
2. **Formal coverage.** The schema path is a ``delivered_artifacts`` entry of a
   classified subsystem in ``specs/formal/assurance-fulfillment.yaml``. A
   ``waived_artifacts`` entry never counts: a dated, tracked waiver is an
   unresolved obligation, not delivered evidence.
3. **Declared alternate coverage.** The contract's publication record carries a
   validated ``coverage`` association naming the concrete evidence that
   exercises it where neither canonical route reaches.

**A formal model is never required.** Leg 2 is one alternative among three. This
gate never reads an FM level, never infers FM applicability, and never turns a
missing formal association into "not applicable" — FM applicability belongs to
``assurance-policy.yaml`` / ``assurance-fulfillment.yaml`` under
``check_assurance_policy.py``. A structural contract passes on leg 1 alone.

``check_schema_publication.py`` does not validate unknown publication-record
keys, so this module owns the ``coverage`` shape end to end. A malformed
association is reported as ``schema-coverage-declaration-invalid``, separately
from the ``schema-coverage-missing`` outcome, and never counts as coverage.

``--report`` prints a read-only inventory naming the covering leg per schema and
never gates. Failures use ``tools.policy.common.PolicyFailure`` and the CLI
honours ``--json`` and the shared ``tools/policy/exceptions.yaml`` waiver
mechanism, like the other ``policy`` nox-stage entry points.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.check_json_artifacts import covered_schema_paths
from tools.check_schema_publication import load_schema_publication_catalog
from tools.policy.common import (
    PolicyFailure,
    apply_exceptions,
    failures_to_json,
    load_bounded_json_object,
    load_yaml,
    safe_repo_path,
)
from tools.tooling_artifact_policy_common import is_regular_repo_file

__all__ = [
    "COVERAGE_KEY",
    "CATALOG_RULE_ID",
    "DECLARATION_RULE_ID",
    "MAX_SOURCES",
    "MISSING_RULE_ID",
    "build_coverage_report",
    "evaluate_schema_coverage",
    "main",
]

ASSURANCE_FULFILLMENT_RELATIVE_PATH = "specs/formal/assurance-fulfillment.yaml"

COVERAGE_KEY = "coverage"
CATALOG_RULE_ID = "schema-coverage-catalog-unreadable"
DECLARATION_RULE_ID = "schema-coverage-declaration-invalid"
MISSING_RULE_ID = "schema-coverage-missing"

MAX_SOURCES = 8
_RATIONALE_BOUNDS = (20, 500)
_SUPPORTS_BOUNDS = (10, 200)
_MAX_SOURCE_BYTES = 1_000_000

_COVERAGE_KEYS = frozenset({"rationale", "sources"})
_SOURCE_KEYS = frozenset({"kind", "path", "pointer", "schema_pointer", "supports"})
_SOURCE_KINDS = frozenset({"fixture", "embedded"})
_FIXTURE_ROOT = "contracts/"
_DEFS_PREFIX = "#/$defs/"
_METASCHEMA = "https://json-schema.org/draft/2020-12/schema"
_MAX_SCHEMA_BYTES = 4_000_000
_MAX_POINTER_LENGTH = 256
_VERSION_SUFFIX = re.compile(r"^(?P<base>.+)-(?P<version>v\d+)$")

# Report labels, strongest evidence first.
_CORPUS = "corpus"
_FORMAL = "formal"
_DECLARED = "declared"
_UNCOVERED = "uncovered"


def _failure(rule_id: str, message: str, path: str | None = None) -> PolicyFailure:
    return PolicyFailure(rule_id, message, path)


def _contract_version_forms(contract_id: str) -> frozenset[str]:
    """Return the ``schema_version`` spellings that identify ``contract_id``.

    Published schemas spell their own version with a slash
    (``operation-status/v1``) while the publication record and schema filename
    use a hyphen (``operation-status-v1``). Both identify one contract.
    """

    match = _VERSION_SUFFIX.match(contract_id)
    if match is None:
        return frozenset({contract_id})
    return frozenset({contract_id, f"{match['base']}/{match['version']}"})


def _declares_contract(payload: Any, forms: frozenset[str]) -> bool:
    """Whether the document as a whole claims to be a payload of the contract.

    The claim must be the document's own ``schema_version``. A contract id found
    deeper — an element of a declared-contract list, a member of a carrier, a
    prose mention — is not this document claiming to be that contract. A payload
    that genuinely lives inside a carrier is named by its node with an
    ``embedded`` source instead, so it is validated as the thing it is rather
    than dragging its carrier through the wrong schema.
    """

    return isinstance(payload, dict) and payload.get("schema_version") in forms


def _formal_artifact_paths(repo_root: Path) -> tuple[frozenset[str], list[PolicyFailure]]:
    """Delivered assurance-artifact paths, keyed by repo-relative path.

    Waived artifacts are deliberately excluded: a dated, tracked waiver records
    an unresolved obligation. A missing fulfillment map is not an error here —
    this gate never requires a formal model.
    """

    path = repo_root / ASSURANCE_FULFILLMENT_RELATIVE_PATH
    if not path.is_file():
        return frozenset(), []
    try:
        document = load_yaml(path)
    except yaml.YAMLError:
        return frozenset(), [
            _failure(
                CATALOG_RULE_ID,
                "assurance fulfillment map is not valid YAML",
                ASSURANCE_FULFILLMENT_RELATIVE_PATH,
            )
        ]
    entries = document.get("entries")
    if not isinstance(entries, list):
        return frozenset(), []
    delivered = {
        artifact["path"]
        for entry in entries
        if isinstance(entry, dict)
        for artifact in (entry.get("delivered_artifacts") or [])
        if isinstance(artifact, dict) and isinstance(artifact.get("path"), str)
    }
    return frozenset(delivered), []


def _check_source_path(repo_root: Path, relative_path: object) -> str | None:
    """Return a stable reason the source path is unusable, or None when it is safe."""

    if not isinstance(relative_path, str) or not relative_path:
        return "source path must be a non-empty string"
    if relative_path != Path(relative_path).as_posix() or relative_path.startswith("/"):
        return f"source path must be a normalized repo-relative path: {relative_path}"
    if safe_repo_path(repo_root, relative_path) is None:
        return f"source path escapes the repository: {relative_path}"
    if not is_regular_repo_file(repo_root, relative_path):
        return f"source path is not a regular in-repository file: {relative_path}"
    return None


def _published_validator(
    repo_root: Path, schema_path: str, schema_pointer: str | None
) -> tuple[object | None, str | None]:
    """Build a validator for the published schema, or for one of its published ``$defs``.

    Resolution is local: the wrapper copies the root ``$defs`` so a ``$ref`` in the
    named sub-schema resolves without any network or registry lookup.
    """

    try:
        root = load_bounded_json_object(repo_root, schema_path, max_bytes=_MAX_SCHEMA_BYTES)
    except (ValueError, json.JSONDecodeError):
        return None, f"published schema is not a readable bounded JSON object: {schema_path}"
    if schema_pointer is None:
        return Draft202012Validator(root), None
    definitions = root.get("$defs")
    name = schema_pointer[len(_DEFS_PREFIX) :]
    if not isinstance(definitions, dict) or name not in definitions:
        return None, f"schema pointer names no published definition: {schema_pointer}"
    wrapper = {"$schema": root.get("$schema", _METASCHEMA), "$defs": definitions, "$ref": schema_pointer}
    return Draft202012Validator(wrapper), None


def _conformance_reason(validator: object, payload: object, relative_path: str) -> str | None:
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if not errors:
        return None
    # Bounded, path-only diagnostics: never echo the payload or the validator message body.
    location = "/".join(str(part) for part in errors[0].path) or "<root>"
    return f"source does not conform to the published schema at {location}: {relative_path}"


def _check_fixture_source(
    repo_root: Path,
    relative_path: str,
    forms: frozenset[str],
    schema_path: str,
) -> str | None:
    """A fixture source is evidence only if it is a payload of the contract that validates.

    Carrying the contract id is an identity claim, not evidence. The gate proves
    the claim here by validating the document against the checked-in published
    schema, so a deliberately invalid document can never stand in as coverage.
    """

    if not relative_path.startswith(_FIXTURE_ROOT) or not relative_path.endswith(".json"):
        return f"fixture source must be a JSON artifact under {_FIXTURE_ROOT}: {relative_path}"
    try:
        payload = load_bounded_json_object(repo_root, relative_path, max_bytes=_MAX_SOURCE_BYTES)
    except (ValueError, json.JSONDecodeError):
        return f"fixture source is not a readable bounded JSON object: {relative_path}"
    if not _declares_contract(payload, forms):
        return f"fixture source does not carry a payload of this contract: {relative_path}"
    validator, reason = _published_validator(repo_root, schema_path, None)
    if reason is not None:
        return reason
    return _conformance_reason(validator, payload, relative_path)


def _resolve_pointer(payload: object, pointer: str) -> tuple[object, bool]:
    """Resolve an RFC 6901 pointer against a loaded document."""

    node = payload
    for raw_token in pointer.split("/")[1:]:
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            if token not in node:
                return None, False
            node = node[token]
        elif isinstance(node, list):
            if not token.isdigit() or int(token) >= len(node):
                return None, False
            node = node[int(token)]
        else:
            return None, False
    return node, True


def _check_embedded_source(
    repo_root: Path,
    relative_path: str,
    schema_path: str,
    pointer: object,
    schema_pointer: object,
) -> str | None:
    """An embedded source is evidence only if the pointed-to node validates.

    Some contracts are realized as a node inside a carrier rather than as a
    standalone document — the ``x-raes-invariants`` entries published inside other
    schemas, for example. The carrier and the exact node are named here and the
    gate validates that node against the published shape, so breaking or deleting
    the annotation turns the gate red.
    """

    if not relative_path.startswith(_FIXTURE_ROOT) or not relative_path.endswith(".json"):
        return f"embedded source must be a JSON artifact under {_FIXTURE_ROOT}: {relative_path}"
    if not isinstance(pointer, str) or not pointer.startswith("/") or len(pointer) > _MAX_POINTER_LENGTH:
        return f"embedded source needs an RFC 6901 pointer into the carrier: {relative_path}"
    if schema_pointer is not None and (
        not isinstance(schema_pointer, str)
        or not schema_pointer.startswith(_DEFS_PREFIX)
        or len(schema_pointer) > _MAX_POINTER_LENGTH
    ):
        return f"embedded schema pointer must name a published definition: {relative_path}"
    try:
        carrier = load_bounded_json_object(repo_root, relative_path, max_bytes=_MAX_SCHEMA_BYTES)
    except (ValueError, json.JSONDecodeError):
        return f"embedded source is not a readable bounded JSON object: {relative_path}"
    node, found = _resolve_pointer(carrier, pointer)
    if not found:
        return f"embedded pointer {pointer} resolves to nothing in {relative_path}"
    validator, reason = _published_validator(repo_root, schema_path, schema_pointer)
    if reason is not None:
        return reason
    return _conformance_reason(validator, node, relative_path)


def _check_bounded_string(value: object, label: str, bounds: tuple[int, int]) -> str | None:
    minimum, maximum = bounds
    if not isinstance(value, str):
        return f"{label} must be a string"
    if not minimum <= len(value.strip()) <= maximum:
        return f"{label} must be between {minimum} and {maximum} characters"
    return None


def _evaluate_declaration(
    repo_root: Path,
    declaration: object,
    contract_id: str,
    schema_path: str,
) -> tuple[bool, list[PolicyFailure]]:
    """Validate one ``coverage`` association.

    Returns whether the association qualifies as evidence, plus every reason it
    is malformed. An association that produces any reason provides no coverage:
    an unknown key, a dead or duplicated reference, or a stale source cannot
    silently pass on the strength of a sibling that still resolves.
    """

    reasons: list[str] = []
    if not isinstance(declaration, dict):
        return False, [_failure(DECLARATION_RULE_ID, "coverage must be a JSON object", schema_path)]

    unknown = sorted(set(declaration) - _COVERAGE_KEYS)
    if unknown:
        reasons.append(f"coverage has unsupported keys: {', '.join(unknown)}")
    reason = _check_bounded_string(declaration.get("rationale"), "coverage rationale", _RATIONALE_BOUNDS)
    if reason is not None:
        reasons.append(reason)

    sources = declaration.get("sources")
    if not isinstance(sources, list) or not sources:
        reasons.append("coverage sources must be a non-empty array")
        sources = []
    elif len(sources) > MAX_SOURCES:
        reasons.append(f"coverage sources must name at most {MAX_SOURCES} artifacts")
        sources = []

    forms = _contract_version_forms(contract_id)
    seen: set[tuple[str, object]] = set()
    qualified = False
    for source in sources:
        if not isinstance(source, dict):
            reasons.append("each coverage source must be a JSON object")
            continue
        source_unknown = sorted(set(source) - _SOURCE_KEYS)
        if source_unknown:
            reasons.append(f"coverage source has unsupported keys: {', '.join(source_unknown)}")
            continue
        supports_reason = _check_bounded_string(source.get("supports"), "coverage source supports", _SUPPORTS_BOUNDS)
        if supports_reason is not None:
            reasons.append(supports_reason)
            continue
        path_reason = _check_source_path(repo_root, source.get("path"))
        if path_reason is not None:
            reasons.append(path_reason)
            continue
        relative_path = str(source["path"])
        # Two embedded sources may legitimately share a carrier at different nodes,
        # so identity is the (artifact, node) pair rather than the artifact alone.
        identity = (relative_path, source.get("pointer"))
        if identity in seen:
            reasons.append(f"coverage sources must be unique: {relative_path}")
            continue
        seen.add(identity)
        kind = source.get("kind")
        if kind == "fixture":
            evidence_reason = _check_fixture_source(repo_root, relative_path, forms, schema_path)
        elif kind == "embedded":
            evidence_reason = _check_embedded_source(
                repo_root,
                relative_path,
                schema_path,
                source.get("pointer"),
                source.get("schema_pointer"),
            )
        else:
            evidence_reason = f"coverage source kind must be one of {sorted(_SOURCE_KINDS)}: {relative_path}"
        if evidence_reason is None:
            qualified = True
        else:
            reasons.append(evidence_reason)

    return qualified and not reasons, [_failure(DECLARATION_RULE_ID, reason, schema_path) for reason in reasons]


def _catalog_entries(repo_root: Path) -> tuple[list[dict[str, Any]], list[PolicyFailure]]:
    try:
        catalog = load_schema_publication_catalog(repo_root)
    except (ValueError, json.JSONDecodeError, OSError):
        return [], [
            _failure(
                CATALOG_RULE_ID,
                "schema publication catalog could not be read; check_schema_publication.py owns the detail",
                "contracts/schema-publication-manifest.json",
            )
        ]
    entries = catalog.get("schemas")
    if not isinstance(entries, list):
        return [], [
            _failure(
                CATALOG_RULE_ID,
                "schema publication catalog defines no schemas array",
                "contracts/schema-publication-manifest.json",
            )
        ]
    return [entry for entry in entries if isinstance(entry, dict)], []


def _classify(repo_root: Path) -> tuple[list[tuple[str, str, str]], list[PolicyFailure]]:
    """Return ``(contract_id, schema_path, covering leg)`` rows plus association failures."""

    entries, failures = _catalog_entries(repo_root)
    if failures:
        return [], failures
    corpus = covered_schema_paths(repo_root)
    formal, formal_failures = _formal_artifact_paths(repo_root)
    failures.extend(formal_failures)

    rows: list[tuple[str, str, str]] = []
    for entry in entries:
        contract_id = entry.get("contract_id")
        schema_path = entry.get("schema_path")
        if not isinstance(contract_id, str) or not isinstance(schema_path, str):
            # Malformed records are check_schema_publication.py's failure to report.
            continue
        if schema_path in corpus:
            leg = _CORPUS
        elif schema_path in formal:
            leg = _FORMAL
        else:
            leg = _UNCOVERED
        if COVERAGE_KEY in entry:
            qualified, declaration_failures = _evaluate_declaration(
                repo_root, entry[COVERAGE_KEY], contract_id, schema_path
            )
            failures.extend(declaration_failures)
            if leg is _UNCOVERED and qualified:
                leg = _DECLARED
        rows.append((contract_id, schema_path, leg))
    return sorted(rows), failures


def evaluate_schema_coverage(repo_root: Path = REPO_ROOT) -> list[PolicyFailure]:
    """Return every published schema that carries no concrete coverage evidence."""

    rows, failures = _classify(repo_root)
    failures.extend(
        _failure(
            MISSING_RULE_ID,
            f"published schema {contract_id} has no fixture, formal, or declared coverage evidence",
            schema_path,
        )
        for contract_id, schema_path, leg in rows
        if leg == _UNCOVERED
    )
    return sorted(failures, key=lambda item: (item.path or "", item.rule_id, item.message))


def build_coverage_report(repo_root: Path = REPO_ROOT) -> str:
    """Render a read-only inventory naming the covering leg per schema. Never gates."""

    rows, failures = _classify(repo_root)
    lines = ["Published-schema coverage report (ASR-501)", ""]
    for leg in (_CORPUS, _FORMAL, _DECLARED, _UNCOVERED):
        group = [row for row in rows if row[2] == leg]
        lines.append(f"## {leg} ({len(group)})")
        lines.extend(f"  - {contract_id}: {schema_path}" for contract_id, schema_path, _ in group)
        lines.append("")
    if failures:
        lines.append(f"## malformed associations ({len(failures)})")
        lines.extend(f"  - {failure.render()}" for failure in failures)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate published-schema coverage evidence (ASR-501).")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (defaults to the repo containing this file).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON failures.")
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print a read-only coverage inventory (covering leg per schema) and exit 0.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.report:
        print(build_coverage_report(args.repo_root))
        return 0
    failures = evaluate_schema_coverage(args.repo_root)
    failures = apply_exceptions(failures, load_exceptions_for(args.repo_root))
    if failures:
        if args.json:
            print(failures_to_json(failures))
        else:
            for failure in failures:
                print(failure.render(), file=sys.stderr)
        return 1
    return 0


def load_exceptions_for(repo_root: Path) -> list[dict]:
    from tools.policy.common import load_exceptions

    if not (repo_root / "tools" / "policy" / "exceptions.yaml").is_file():
        return []
    return load_exceptions(repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
