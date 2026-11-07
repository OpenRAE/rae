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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from packaging.specifiers import InvalidSpecifier
from pydantic import ValidationError
from raes._composition_budget import CompositionTraversal
from raes._errors import SDLError
from raes._source_profile import SDLParserLimits
from raes._supplied_sources import SuppliedSources
from raes.formatting import format_sdl_source
from raes.module_registry._digests import _normalize_exact_or_range, _satisfies_version

VECTORS = ROOT / "implementations/go/internal/sdl/authoring/testdata"


def formatter(rows: list[dict]) -> list[dict]:
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


def import_result(row: dict):
    files = row["files"]
    limits = SDLParserLimits(**row.get("limits", {}))
    if row["supplied"]:
        sources = SuppliedSources.capture({key: value.encode() for key, value in files.items()})
        path, _ = sources.root("main.yaml")
        return format_sdl_source(
            files["main.yaml"],
            path=path,
            limits=limits,
            _traversal=CompositionTraversal.supplied_root(limits, sources),
        )
    with tempfile.TemporaryDirectory(prefix="sdl-import-reference-") as directory:
        for name, content in files.items():
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("unsafe reference file name")
            path = Path(directory) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content.replace("$ROOT", directory) if row.get("rooted") else content)
        for name, target in row.get("links", {}).items():
            path = Path(directory) / name
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("unsafe reference link name")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(target.replace("$ROOT", directory) if row.get("rooted") else target)
        result = format_sdl_source(
            files["main.yaml"].replace("$ROOT", directory) if row.get("rooted") else files["main.yaml"],
            path=Path(directory) / "main.yaml",
            limits=limits,
        )
        if row.get("rooted"):
            return type(result)(
                content=result.content.replace(directory, "$ROOT"),
                diagnostics=result.diagnostics,
            )
        return result


def imports(rows: list[dict]) -> list[dict]:
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


def versions(rows: list[dict]) -> list[dict]:
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


def provenance() -> dict:
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
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
