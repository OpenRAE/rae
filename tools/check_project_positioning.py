#!/usr/bin/env python3
"""Validate the domain-neutral, evidence-bounded RAES positioning surfaces."""

from __future__ import annotations

import argparse
import ast
import re
import sys
import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.policy.common import (  # noqa: E402
    PolicyFailure,
    apply_exceptions,
    failures_to_json,
    load_exceptions,
    safe_repo_path,
)

MAX_SURFACE_BYTES = 512_000
RULE_SURFACE = "project-positioning-surface"
RULE_FRAMING = "project-positioning-framing"
RULE_DOMAINS = "project-positioning-domains"
RULE_CLAIM_BOUNDARY = "project-positioning-claim-boundary"
RULE_METADATA = "project-positioning-metadata"

PRIMARY_ENTRYPOINTS = (
    "README.md",
    "docs/public/index.md",
)
SUPPORTING_DOCS = (
    "docs/public/quickstart.md",
    "docs/public/concepts.md",
    "docs/public/sdl/index.md",
    "docs/public/backends.md",
    "docs/public/research.md",
    "examples/README.md",
)
APPLICATION_AREAS = (
    "cyber",
    "ai security",
    "ai safety",
    "testing",
    "research",
    "evaluation",
)


def _read_text(repo_root: Path, relative_path: str) -> tuple[str | None, PolicyFailure | None]:
    path = safe_repo_path(repo_root, relative_path)
    if path is None or not path.is_file():
        return None, PolicyFailure(RULE_SURFACE, "required positioning surface is missing", relative_path)
    try:
        if path.stat().st_size > MAX_SURFACE_BYTES:
            return None, PolicyFailure(
                RULE_SURFACE,
                f"positioning surface exceeds the {MAX_SURFACE_BYTES}-byte inspection limit",
                relative_path,
            )
        return path.read_text(encoding="utf-8"), None
    except OSError, UnicodeDecodeError:
        return None, PolicyFailure(
            RULE_SURFACE,
            "positioning surface is not readable UTF-8 text",
            relative_path,
        )


def _read_required(repo_root: Path, relative_path: str, failures: list[PolicyFailure]) -> str:
    text, failure = _read_text(repo_root, relative_path)
    if failure is not None:
        failures.append(failure)
        return ""
    return text or ""


def _literal_assignment(source: str, name: str) -> str | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return None


def _missing_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    normalized = re.sub(r"[\s-]+", " ", text.casefold())
    return [term for term in terms if re.sub(r"[\s-]+", " ", term.casefold()) not in normalized]


def _validate_entrypoints(
    surfaces: dict[str, str],
    failures: list[PolicyFailure],
) -> None:
    full_name = "reproducible agentic environments system"
    for relative_path in PRIMARY_ENTRYPOINTS:
        text = surfaces[relative_path]
        missing = _missing_terms(text, (full_name, "agentic environment"))
        if missing:
            failures.append(
                PolicyFailure(
                    RULE_FRAMING,
                    "primary entrypoint must introduce RAES and agentic environments",
                    relative_path,
                )
            )

    for relative_path in SUPPORTING_DOCS:
        if _missing_terms(surfaces[relative_path], ("RAES",)):
            failures.append(
                PolicyFailure(
                    RULE_FRAMING,
                    "supporting entrypoint must connect its subject to RAES",
                    relative_path,
                )
            )

    readme = surfaces["README.md"]
    missing_areas = _missing_terms(readme, APPLICATION_AREAS)
    if missing_areas or len(_missing_terms(readme, ("additional domains", "other domains"))) == 2:
        failures.append(
            PolicyFailure(
                RULE_DOMAINS,
                "README must present the named application areas as non-exhaustive",
                "README.md",
            )
        )

    concepts = surfaces["docs/public/concepts.md"]
    required_boundaries = (
        "authored scenario",
        "realized environment",
        "bounded reproduction",
        "does not",
        "exact replay",
    )
    if _missing_terms(concepts, required_boundaries):
        failures.append(
            PolicyFailure(
                RULE_CLAIM_BOUNDARY,
                "concept guidance must retain the bounded reproduction and nonclaim boundary",
                "docs/public/concepts.md",
            )
        )


def _validate_structured_metadata(repo_root: Path, failures: list[PolicyFailure]) -> None:
    pyproject_path = "implementations/python/pyproject.toml"
    pyproject_text = _read_required(repo_root, pyproject_path, failures)
    if pyproject_text:
        try:
            project = tomllib.loads(pyproject_text).get("project", {})
            description = project.get("description", "") if isinstance(project, dict) else ""
        except tomllib.TOMLDecodeError, TypeError:
            description = ""
        if not isinstance(description, str) or "reproducible agentic environments" not in description.casefold():
            failures.append(
                PolicyFailure(
                    RULE_METADATA,
                    "package description must identify reproducible agentic environments",
                    pyproject_path,
                )
            )

    conf_path = "docs/public/conf.py"
    conf_text = _read_required(repo_root, conf_path, failures)
    project_name = _literal_assignment(conf_text, "project")
    html_title = _literal_assignment(conf_text, "html_title")
    if project_name != "Reproducible Agentic Environments System" or html_title != "RAES Documentation":
        failures.append(
            PolicyFailure(
                RULE_METADATA,
                "Sphinx metadata must identify the RAES system and documentation surface",
                conf_path,
            )
        )

    catalog_path = "examples/library/catalog.yaml"
    catalog_text = _read_required(repo_root, catalog_path, failures)
    try:
        catalog = yaml.safe_load(catalog_text)
        description = catalog.get("description", "") if isinstance(catalog, dict) else ""
    except yaml.YAMLError:
        description = ""
    if not isinstance(description, str) or _missing_terms(description, ("domain-neutral", "agentic environment")):
        failures.append(
            PolicyFailure(
                RULE_METADATA,
                "example catalog description must identify its domain-neutral agentic-environment role",
                catalog_path,
            )
        )


def _validate_mcp_metadata(repo_root: Path, failures: list[PolicyFailure]) -> None:
    assignments = (
        ("implementations/python/packages/raes_mcp/server.py", "_INSTRUCTIONS"),
        (
            "implementations/python/packages/raes_mcp/tools/reference.py",
            "_OVERVIEW_TEXT",
        ),
    )
    for relative_path, assignment in assignments:
        source = _read_required(repo_root, relative_path, failures)
        value = _literal_assignment(source, assignment)
        if not value or _missing_terms(value, ("agentic environment", "RAES SDL", "authored scenario")):
            failures.append(
                PolicyFailure(
                    RULE_METADATA,
                    "MCP positioning must distinguish RAES agentic environments from authored RAES SDL scenarios",
                    relative_path,
                )
            )


def validate_project_positioning(repo_root: Path) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    surfaces = {
        relative_path: _read_required(repo_root, relative_path, failures)
        for relative_path in (*PRIMARY_ENTRYPOINTS, *SUPPORTING_DOCS)
    }
    _validate_entrypoints(surfaces, failures)
    _validate_structured_metadata(repo_root, failures)
    _validate_mcp_metadata(repo_root, failures)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit failures as JSON.")
    args = parser.parse_args()

    failures = apply_exceptions(validate_project_positioning(REPO_ROOT), load_exceptions(REPO_ROOT))
    if args.json:
        print(failures_to_json(failures))
    else:
        for failure in failures:
            print(failure.render())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
