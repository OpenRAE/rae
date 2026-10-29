#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Prove that the normative SDL catalogs cover the live language surface.

The published schema and normative prose remain independently governed
authorities. This read-only check compares both with the reference
implementation registries so drift is reported instead of silently generated
away. The comparison tables and check implementations live in the
``tools/sdl_catalog_parity`` support package; this entry point wires them to
the repository authorities and keeps the import surface the test suite and
nox lanes rely on.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_PACKAGES = REPO_ROOT / "implementations" / "python" / "packages"
for import_root in (REPO_ROOT, PYTHON_PACKAGES):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from raes_contracts.errors import InvalidInputError
from raes_contracts.operational_logging import run_application

from tools.policy.common import (
    PolicyFailure,
    apply_exceptions,
    failures_to_json,
    load_exceptions,
)
from tools.sdl_catalog_parity._checks import (
    _check_phase_members,
    _check_references,
    _check_runtime,
    _check_top_level,
)
from tools.sdl_catalog_parity._prose_checks import (
    _check_diagnostic_normative_layer,
    _check_internal_links,
)
from tools.sdl_catalog_parity._expected import _failure
from tools.sdl_catalog_parity._paths import (
    DIAGNOSTICS_PATH,
    DOCUMENT_MODEL_PATH,
    PHASES_PATH,
    REFERENCES_PATH,
    RUNTIME_PATH,
    SCHEMA_PATH,
    SECTIONS_PATH,
    VARIABLES_PATH,
)
from tools.sdl_catalog_parity._rows import (
    CatalogParseError,
    parse_reference_catalog,
    parse_top_level_catalog,
)

__all__ = [
    "CatalogParseError",
    "evaluate_sdl_catalog_parity",
    "main",
    "parse_args",
    "parse_reference_catalog",
    "parse_top_level_catalog",
]


def evaluate_sdl_catalog_parity(repo_root: Path) -> list[PolicyFailure]:
    """Return deterministic parity failures for the normative SDL catalogs."""
    prose_paths = (
        SECTIONS_PATH,
        REFERENCES_PATH,
        RUNTIME_PATH,
        DOCUMENT_MODEL_PATH,
        VARIABLES_PATH,
        DIAGNOSTICS_PATH,
        PHASES_PATH,
    )
    required_paths = (*prose_paths, SCHEMA_PATH)
    missing = [relative for relative in required_paths if not (repo_root / relative).is_file()]
    if missing:
        return [
            _failure(
                "sdl-catalog-missing",
                f"required catalog authority is missing: {relative}",
                relative,
            )
            for relative in missing
        ]
    try:
        schema = json.loads((repo_root / SCHEMA_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [_failure("sdl-catalog-schema-parse", str(exc), SCHEMA_PATH)]
    except ValueError, RecursionError:
        # The schema is not UTF-8, has an integer beyond the interpreter digit limit or nests beyond the decoder.
        return [_failure("sdl-catalog-schema-parse", "schema is not UTF-8 JSON within the decoder limits", SCHEMA_PATH)]
    sections_text = (repo_root / SECTIONS_PATH).read_text(encoding="utf-8")
    top_failures, top_rows = _check_top_level(sections_text, schema)
    failures = list(top_failures)
    failures.extend(
        _check_references(
            (repo_root / REFERENCES_PATH).read_text(encoding="utf-8"),
            top_rows,
            repo_root,
        )
    )
    failures.extend(_check_runtime((repo_root / RUNTIME_PATH).read_text(encoding="utf-8")))
    failures.extend(_check_phase_members((repo_root / PHASES_PATH).read_text(encoding="utf-8")))
    failures.extend(_check_diagnostic_normative_layer((repo_root / DIAGNOSTICS_PATH).read_text(encoding="utf-8")))
    failures.extend(_check_internal_links(repo_root, prose_paths))
    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate normative SDL catalog parity.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--json", action="store_true", help="Emit JSON failures.")
    return parser.parse_args(argv)


def _evaluate(repo_root: Path) -> list[PolicyFailure]:
    failures = evaluate_sdl_catalog_parity(repo_root)
    exceptions_path = repo_root / "tools" / "policy" / "exceptions.yaml"
    if exceptions_path.is_file():
        failures = apply_exceptions(failures, load_exceptions(repo_root))
    return failures


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        failures = _evaluate(args.repo_root)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, InvalidInputError) as exc:
        print(f"sdl-catalog-parity: {exc}", file=sys.stderr)
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
