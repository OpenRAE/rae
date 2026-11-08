#!/usr/bin/env python3
"""Refresh independent formatter, import and version results for frozen inputs.

Add inputs to the JSON vectors, then run this tool with the reference Python
interpreter. --check compares results without changing files. This command
records targeted vectors; it does not run the complete parity corpus.
"""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "implementations/python/packages")]

from packaging.specifiers import InvalidSpecifier
from pydantic import ValidationError
from raes._composition_budget import CompositionTraversal
from raes._declaration_sources import (
    attach_declaration_sources,
    semantic_source_diagnostics,
)
from raes._errors import SDLError, SDLValidationError
from raes._source_profile import SDLParserLimits, SDLSourceParseOptions
from raes._supplied_sources import SuppliedSources
from raes.canonical import (
    canonical_materialized_sdl_bytes,
    canonical_materialized_sdl_digest,
    canonical_sdl_bytes,
    canonical_sdl_digest,
)
from raes.formatting import SDLFormatResult, format_sdl_source
from raes.materialization import MaterializedScenario
from raes.module_registry._digests import _normalize_exact_or_range, _satisfies_version
from raes.parser import _load_normalized_data, parse_sdl
from raes.scenario import ScenarioContent
from raes.validator import SemanticValidator
from raes.validator._variation_satisfiability import (
    _SelectionBudgetExceeded,
    _SelectionGroup,
    _SelectionSatisfiability,
)
from raes_contracts.realization_structure import validate_realization_value
from raes_contracts.runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS

from tools.parity_storage import read_blob, read_document

MAIN_SOURCE = "main.yaml"
ROOT_MARKER = "$ROOT"

VECTORS = ROOT / "implementations/go/internal/sdl/authoring/testdata"
SEMANTIC_SHARD_BYTES = 450 * 1024
SEMANTIC_SCHEMA = "raes-sdl-semantic-vectors/v1"


def formatter(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        recorded = {key: row[key] for key in ("name", "source")}
        if "limits" in row:
            recorded["limits"] = row["limits"]
        try:
            value = format_sdl_source(row["source"], limits=SDLParserLimits(**row.get("limits", {})))
            recorded.update(
                accepted=True,
                content=value.content,
                diagnostics=[item.code for item in value.diagnostics],
            )
        except (SDLError, ValidationError) as exc:
            recorded.update(accepted=False, error=type(exc).__name__)
        result.append(recorded)
    return result


def import_result(row: dict[str, Any]) -> SDLFormatResult:
    files = row["files"]
    limits = SDLParserLimits(**row.get("limits", {}))
    if row["supplied"]:
        sources = SuppliedSources.capture({key: value.encode() for key, value in files.items()})
        path, _ = sources.root(MAIN_SOURCE)
        return format_sdl_source(
            files[MAIN_SOURCE],
            path=path,
            limits=limits,
            _traversal=CompositionTraversal.supplied_root(limits, sources),
        )
    with tempfile.TemporaryDirectory(prefix="sdl-import-reference-") as directory:
        write_import_files(row, directory)
        result = format_sdl_source(
            files[MAIN_SOURCE].replace(ROOT_MARKER, directory) if row.get("rooted") else files[MAIN_SOURCE],
            path=Path(directory) / MAIN_SOURCE,
            limits=limits,
        )
        if row.get("rooted"):
            return type(result)(
                content=result.content.replace(directory, ROOT_MARKER),
                diagnostics=result.diagnostics,
            )
        return result


def reference_path(directory: str, name: str) -> Path:
    if Path(name).is_absolute() or ".." in Path(name).parts:
        raise ValueError("unsafe reference file name")
    path = Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_import_files(row: dict[str, Any], directory: str) -> None:
    for name, content in row["files"].items():
        path = reference_path(directory, name)
        path.write_text(content.replace(ROOT_MARKER, directory) if row.get("rooted") else content)
    for name, target in row.get("links", {}).items():
        path = reference_path(directory, name)
        path.symlink_to(target.replace(ROOT_MARKER, directory) if row.get("rooted") else target)


def imports(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        recorded = {key: row[key] for key in ("name", "files", "supplied")}
        for key in ("limits", "rooted", "links"):
            if key in row:
                recorded[key] = row[key]
        try:
            value = import_result(row)
            recorded.update(accepted=True, content=value.content)
        except (SDLError, ValidationError) as exc:
            recorded.update(accepted=False, error=type(exc).__name__)
            if code := getattr(exc, "code", None):
                recorded["code"] = str(code)
        result.append(recorded)
    return result


def versions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        request = row["requested"]
        recorded = {"requested": request, "actuals": {}}
        try:
            _normalize_exact_or_range(request)
            recorded["valid"] = True
        except InvalidSpecifier:
            recorded["valid"] = False
        if recorded["valid"]:
            for actual in row["actuals"]:
                try:
                    recorded["actuals"][actual] = _satisfies_version(actual, request)
                except InvalidSpecifier:
                    recorded["actuals"][actual] = None
        result.append(recorded)
    return result


def provenance() -> dict[str, Any]:
    package = ROOT / "implementations/python/packages/raes"
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        digest.update(str(path.relative_to(package)).encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    commit = subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", str(package)], cwd=ROOT, text=True
    ).strip()
    return {
        "reference_commit": commit,
        "reference_package_sha256": digest.hexdigest(),
        "dependencies": {name: importlib.metadata.version(name) for name in ("PyYAML", "pydantic", "packaging")},
    }


def write_or_check(name: str, value: object, check: bool) -> bool:
    path = VECTORS / name
    encoded = json.dumps(value, indent=2, ensure_ascii=True) + "\n"
    if check:
        if not path.exists() or path.read_text() != encoded:
            print(f"{name}: reference results differ", file=sys.stderr)
            return False
    else:
        path.write_text(encoded)
    return True


def read_semantic_vectors() -> list[dict[str, Any]]:
    manifest = json.loads((VECTORS / "semantics.json").read_bytes())
    if isinstance(manifest, list):
        return manifest
    if manifest["schema"] != SEMANTIC_SCHEMA:
        raise ValueError("unknown semantic vector manifest")
    rows = []
    for index, shard in enumerate(manifest["shards"]):
        if shard["name"] != f"semantics-{index:03d}.json":
            raise ValueError("noncanonical semantic shard name")
        rows.extend(json.loads((VECTORS / shard["name"]).read_bytes()))
    if len(rows) != manifest["case_count"] or len({row["name"] for row in rows}) != len(rows):
        raise ValueError("incomplete or duplicate semantic cases")
    return rows


def write_semantic_vectors(rows: list[dict[str, Any]], check: bool) -> bool:
    chunks, current = [], []
    for row in rows:
        candidate = current + [row]
        encoded = json.dumps(candidate, indent=2, ensure_ascii=True) + "\n"
        if len(encoded.encode()) > SEMANTIC_SHARD_BYTES:
            if not current:
                raise ValueError("one semantic vector exceeds the shard ceiling")
            chunks.append(current)
            current = [row]
        else:
            current = candidate
    if current:
        chunks.append(current)
    manifest = {"schema": SEMANTIC_SCHEMA, "case_count": len(rows), "shards": []}
    valid = True
    for index, chunk in enumerate(chunks):
        name = f"semantics-{index:03d}.json"
        encoded = (json.dumps(chunk, indent=2, ensure_ascii=True) + "\n").encode()
        if len(encoded) > SEMANTIC_SHARD_BYTES:
            raise ValueError("one semantic vector exceeds the shard ceiling")
        manifest["shards"].append(
            {
                "name": name,
                "case_count": len(chunk),
                "sha256": hashlib.sha256(encoded).hexdigest(),
            }
        )
        valid = write_or_check(name, chunk, check) and valid
    valid = write_or_check("semantics.json", manifest, check) and valid
    return valid


def semantic_input(row: dict[str, Any], limits: SDLParserLimits) -> Any:
    path = row.get("_path", Path(MAIN_SOURCE))
    policy = "accept" if row.get("accept_migration") else "reject"
    if not row.get("materialized") and not row.get("_corpus"):
        return semantic_parse(row, limits, skip=True)
    # parse_sdl deliberately admits materialized descriptions even when asked
    # to skip semantics. Use its same construction and location owners here
    # so the recorder can observe all errors and advisories before admission.
    ranges, keys = {}, {}
    data = _load_normalized_data(
        row["source"],
        path=path,
        source_options=SDLSourceParseOptions(limits=limits, migration_policy=policy),
        source_diagnostics=[],
        source_ranges=ranges,
        source_key_ranges=keys,
    )
    if "materialization_provenance" not in data:
        return semantic_parse(row, limits, skip=True)
    document = MaterializedScenario(**data)
    attach_declaration_sources(document, row["source"], path, ranges, keys, {})
    return document


def semantic_parse(row: dict[str, Any], limits: SDLParserLimits, *, skip: bool = False) -> Any:
    return parse_sdl(
        row["source"],
        path=row.get("_path", Path(MAIN_SOURCE)),
        skip_semantic_validation=skip,
        migration_policy="accept" if row.get("accept_migration") else "reject",
        limits=limits,
        _traversal=row.get("_traversal"),
    )


def semantic(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Record the actual rule findings before command adapters summarize them."""
    if len({row["name"] for row in rows}) != len(rows):
        raise ValueError("semantic case names must be unique")
    result = []
    for row in rows:
        recorded = {key: row[key] for key in ("name", "source")}
        if "limits" in row:
            recorded["limits"] = row["limits"]
        if row.get("materialized"):
            recorded["materialized"] = True
        if row.get("record_explicitness"):
            recorded["record_explicitness"] = True
        limits = SDLParserLimits(**row.get("limits", {}))
        document = semantic_input(row, limits)
        if isinstance(document, MaterializedScenario):
            content = {name: getattr(document, name) for name in ScenarioContent.model_fields}
            if not validate_realization_value(
                content, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS, python_carriers=True
            ).conformant:
                recorded.update(
                    accepted=False,
                    admission_error="materialized SDL exceeds portable bounds",
                    findings=[],
                    locations=[],
                    advisories=[],
                )
                result.append(recorded)
                continue
        validator = SemanticValidator(document)
        try:
            validator.validate()
        except SDLValidationError as exc:
            semantic_source_diagnostics(exc, document)
            recorded.update(
                accepted=False,
                findings=[{"message": f.message, "owner": f.owner, "pointer": f.pointer} for f in exc.findings],
                locations=[d.as_dict() if d else None for d in exc.diagnostics],
            )
        else:
            admitted = semantic_parse(row, limits)
            recorded.update(accepted=True, findings=[], locations=[])
            try:
                if isinstance(admitted, MaterializedScenario):
                    canonical = canonical_materialized_sdl_bytes(admitted)
                    digest = canonical_materialized_sdl_digest(admitted).value
                else:
                    canonical = canonical_sdl_bytes(admitted)
                    digest = canonical_sdl_digest(admitted).value
                recorded.update(canonical=canonical.decode(), digest=digest)
            except (SDLError, ValueError) as exc:
                recorded["canonical_error"] = type(exc).__name__
        recorded["advisories"] = validator.warnings
        if row.get("record_explicitness"):
            recorded["explicitness"] = {path: asdict(record) for path, record in document.explicitness.items()}
        result.append(recorded)
    return result


def corpus_semantic(case: dict[str, Any], corpus: Path) -> dict[str, Any]:
    """Admit a retained source with no authority to read host source files."""
    identity = case["files"]["arguments.json"].removeprefix("sha256:")
    arguments = json.loads(read_blob(corpus, identity))
    row = {
        "name": case["name"],
        "source": arguments.get("sdl_content"),
        "record_explicitness": True,
        "accept_migration": arguments.get("accept_migration_syntax", False),
        "_corpus": True,
    }
    if not isinstance(row["source"], str):
        return {
            "name": row["name"],
            "source": row["source"],
            "constructed": False,
            "input_error": "non-text-source",
            "accept_migration": row["accept_migration"],
        }
    with tempfile.TemporaryDirectory(prefix="sdl-semantic-oracle-") as directory:
        row["_path"] = Path(directory) / MAIN_SOURCE
        try:
            recorded = semantic([row])[0]
        except (SDLError, ValidationError) as exc:
            recorded = {key: row[key] for key in ("name", "source")}
            recorded.update(constructed=False, construction_error=type(exc).__name__)
        else:
            recorded["constructed"] = True
            for location in recorded["locations"]:
                if location and location.get("source") == str(row["_path"]):
                    location["source"] = MAIN_SOURCE
    recorded["accept_migration"] = row["accept_migration"]
    return recorded


def semantic_imports(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        with tempfile.TemporaryDirectory(prefix="sdl-import-semantic-") as directory:
            request = {
                "name": row["name"],
                "source": row["files"][MAIN_SOURCE],
                "record_explicitness": True,
            }
            request["_path"] = Path(directory) / MAIN_SOURCE
            if row["supplied"]:
                sources = SuppliedSources.capture({name: content.encode() for name, content in row["files"].items()})
                request["_path"], _ = sources.root(MAIN_SOURCE)
                request["_traversal"] = CompositionTraversal.supplied_root(SDLParserLimits(), sources)
            else:
                write_import_files(row, directory)
            recorded = semantic([request])[0]
            for location in recorded["locations"]:
                if location:
                    source = Path(location["source"])
                    location["source"] = str(source.relative_to("/" if row["supplied"] else directory))
            recorded.update(files=row["files"], supplied=row["supplied"])
            result.append(recorded)
    return result


def record_corpus(output: Path, selected: list[str]) -> None:
    corpus = ROOT / "implementations/go/internal/parity/testdata"
    rows = []
    for path in sorted((corpus / "cases/mcp/sdl_parse").glob("*.json")):
        case = read_document(corpus, path.relative_to(corpus))
        if not selected or case["name"] in selected:
            rows.append(corpus_semantic(case, corpus))
    if not rows or (selected and {row["name"] for row in rows} != set(selected)):
        raise ValueError("requested semantic corpus cases were not found")
    if len({row["name"] for row in rows}) != len(rows):
        raise ValueError("semantic corpus case names must be unique")
    result = {
        "schema": "raes-sdl-semantic-oracle/v1",
        "complete": not selected,
        "cases": rows,
    }
    output.write_text(json.dumps(result, ensure_ascii=True) + "\n")
    print(f"recorded semantic admission for {len(rows)} retained corpus inputs")


def selection(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Record finite solver witnesses and the shared deterministic state cost."""
    result = []
    for row in rows:
        recorded = {key: row[key] for key in ("name", "variables", "groups", "clauses", "budget", "required")}
        variables = [tuple(value) for value in row["variables"]]
        groups = [
            _SelectionGroup(
                tuple(variables[index] for index in group["members"]),
                group["minimum"],
                group["maximum"],
            )
            for group in row["groups"]
        ]
        clauses = [tuple((variables[index], value) for index, value in clause) for clause in row["clauses"]]
        solver = _SelectionSatisfiability(groups, clauses)
        solver._remaining_states = row["budget"]
        calls = []
        for required in row["required"]:
            try:
                witness = solver.has_witness({variables[required]: True} if required >= 0 else None)
                exhausted = False
            except _SelectionBudgetExceeded:
                witness, exhausted = False, True
            calls.append(
                {
                    "witness": witness,
                    "exhausted": exhausted,
                    "remaining": solver._remaining_states,
                }
            )
        recorded["calls"] = calls
        result.append(recorded)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--semantic",
        action="store_true",
        help="Record only the targeted semantic and selection vectors.",
    )
    mode.add_argument(
        "--selection",
        action="store_true",
        help="Record only the targeted selection solver vectors.",
    )
    mode.add_argument(
        "--semantic-imports",
        action="store_true",
        help="Record imported semantic identities.",
    )
    mode.add_argument(
        "--corpus",
        action="store_true",
        help="Record retained MCP source inputs for CI.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    if args.corpus:
        if args.check or args.output is None:
            parser.error("--corpus requires --output and does not support --check")
        record_corpus(args.output, args.case)
        return 0
    if args.output is not None or args.case:
        parser.error("--output and --case require --corpus")
    if args.semantic_imports:
        rows = json.loads((VECTORS / "semantic-imports.json").read_bytes())
        return 0 if write_or_check("semantic-imports.json", semantic_imports(rows), args.check) else 1
    if args.selection:
        rows = json.loads((VECTORS / "selection.json").read_bytes())
        return 0 if write_or_check("selection.json", selection(rows), args.check) else 1
    if args.semantic:
        rows = read_semantic_vectors()
        valid = write_semantic_vectors(semantic(rows), args.check)
        valid = write_or_check("semantics-provenance.json", provenance(), args.check) and valid
        rows = json.loads((VECTORS / "selection.json").read_bytes())
        valid = write_or_check("selection.json", selection(rows), args.check) and valid
        return 0 if valid else 1
    source = json.loads((VECTORS / "reference.json").read_bytes())
    source["cases"] = formatter(source["cases"])
    valid = write_or_check("reference.json", source, args.check)
    for name, record in (("imports.json", imports), ("versions.json", versions)):
        rows = json.loads((VECTORS / name).read_bytes())
        valid = write_or_check(name, record(rows), args.check) and valid
    valid = write_or_check("provenance.json", provenance(), args.check) and valid
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
