#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Structural gate for the AUT-811 agent guidance profile."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

import yaml
from raes_contracts.errors import InvalidInputError
from raes_contracts.operational_logging import run_application

from tools.policy.common import PolicyFailure, apply_exceptions, failures_to_json, load_exceptions

AGENT_GUIDANCE_RELATIVE_PATH = "specs/agent-guidance/agent-guidance.yaml"
POLICY_VALUE = "raes-agent-guidance"
REQUIREMENT_REF = "AUT-811"
REQUIRED_CATEGORIES: tuple[str, ...] = (
    "scope_boundaries",
    "invariants",
    "review_priorities",
    "safe_operating_expectations",
)
ALLOWED_AUDIENCES: frozenset[str] = frozenset({"contributor", "operator"})
REQUIRED_TOP_LEVEL_FIELDS: tuple[str, ...] = (
    "profile",
    "version",
    "requirement_refs",
    "source_refs",
    "recommended_workflow",
    "guidance",
)
REQUIRED_ENTRY_FIELDS: tuple[str, ...] = (
    "id",
    "audience",
    "surfaces",
    "statement",
    "source_refs",
)


def _fail(rule_id: str, message: str, path: str | None = AGENT_GUIDANCE_RELATIVE_PATH) -> PolicyFailure:
    return PolicyFailure(rule_id, message, path)


def _str_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    if not all(isinstance(item, str) and item for item in value):
        return None
    return list(value)


def _load_yaml(path: Path) -> tuple[dict[str, Any] | None, list[PolicyFailure]]:
    if not path.is_file():
        return None, [_fail("agent-guidance-missing", f"missing {AGENT_GUIDANCE_RELATIVE_PATH}")]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return None, [
            _fail(
                "agent-guidance-parse",
                f"failed to parse {AGENT_GUIDANCE_RELATIVE_PATH}: the file cannot be read as UTF-8 text",
            )
        ]
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, [_fail("agent-guidance-parse", f"failed to parse {AGENT_GUIDANCE_RELATIVE_PATH}: {exc}")]
    except ValueError, KeyError, AttributeError, IndexError, RecursionError:
        # The safe constructor raises these, not a YAMLError, for a scalar such as an impossible date,
        # an empty tagged number or an unknown !!bool value; the composer stops at the recursion limit.
        return None, [
            _fail(
                "agent-guidance-parse",
                f"failed to parse {AGENT_GUIDANCE_RELATIVE_PATH}: the YAML document cannot be constructed",
            )
        ]
    if not isinstance(raw, dict):
        return None, [
            _fail(
                "agent-guidance-shape",
                f"{AGENT_GUIDANCE_RELATIVE_PATH} must be a YAML mapping at the top level",
            )
        ]
    return raw, []


def _check_top_level(raw: dict[str, Any]) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in raw:
            failures.append(_fail("agent-guidance-field", f"missing required top-level field: {field}"))

    if "profile" in raw and raw["profile"] != POLICY_VALUE:
        failures.append(_fail("agent-guidance-profile", f"profile must be {POLICY_VALUE!r}; got {raw['profile']!r}"))
    if "version" in raw and (not isinstance(raw["version"], int) or raw["version"] < 1):
        failures.append(_fail("agent-guidance-version", "version must be a positive integer"))

    for field in ("requirement_refs", "source_refs", "recommended_workflow"):
        if field in raw and _str_list(raw[field]) is None:
            failures.append(_fail("agent-guidance-field-type", f"{field} must be a list of non-empty strings"))

    requirement_refs = _str_list(raw.get("requirement_refs"))
    if requirement_refs is not None and REQUIREMENT_REF not in requirement_refs:
        failures.append(_fail("agent-guidance-requirement-ref", f"requirement_refs must include {REQUIREMENT_REF}"))

    if "guidance" in raw and not isinstance(raw["guidance"], dict):
        failures.append(_fail("agent-guidance-field-type", "guidance must be a mapping"))
    return failures


def _check_guidance(raw: dict[str, Any]) -> list[PolicyFailure]:
    guidance = raw.get("guidance")
    if not isinstance(guidance, dict):
        return []

    failures: list[PolicyFailure] = []
    seen_ids: set[str] = set()
    for category in REQUIRED_CATEGORIES:
        entries = guidance.get(category)
        if not isinstance(entries, list) or not entries:
            failures.append(_fail("agent-guidance-category", f"guidance.{category} must be a non-empty list"))
            continue
        for index, entry in enumerate(entries):
            failures.extend(_check_entry(category, index, entry, seen_ids))
    return failures


def _check_entry(category: str, index: int, entry: Any, seen_ids: set[str]) -> list[PolicyFailure]:
    if not isinstance(entry, dict):
        return [
            _fail(
                "agent-guidance-entry-shape",
                f"guidance.{category}[{index}] must be a mapping; got {type(entry).__name__}",
            )
        ]

    failures: list[PolicyFailure] = []
    for field in REQUIRED_ENTRY_FIELDS:
        if field not in entry:
            failures.append(_fail("agent-guidance-entry-field", f"guidance.{category}[{index}] missing {field}"))

    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not entry_id:
        failures.append(_fail("agent-guidance-entry-id", f"guidance.{category}[{index}].id must be a non-empty string"))
    elif entry_id in seen_ids:
        failures.append(_fail("agent-guidance-entry-duplicate", f"duplicate guidance id: {entry_id}"))
    else:
        seen_ids.add(entry_id)

    audience = _str_list(entry.get("audience"))
    if audience is None:
        failures.append(
            _fail("agent-guidance-entry-audience", f"{entry_id or category} audience must be a string list")
        )
    elif not set(audience) <= ALLOWED_AUDIENCES:
        failures.append(
            _fail(
                "agent-guidance-entry-audience",
                f"{entry_id or category} audience must be within {sorted(ALLOWED_AUDIENCES)}; got {audience}",
            )
        )

    for field in ("surfaces", "source_refs"):
        if _str_list(entry.get(field)) is None:
            failures.append(
                _fail("agent-guidance-entry-field-type", f"{entry_id or category} {field} must be a string list")
            )

    statement = entry.get("statement")
    if not isinstance(statement, str) or len(statement.strip()) < 20:
        failures.append(
            _fail("agent-guidance-entry-statement", f"{entry_id or category} statement must be a substantive string")
        )
    return failures


def evaluate_agent_guidance(repo_root: Path = REPO_ROOT) -> list[PolicyFailure]:
    raw, failures = _load_yaml(repo_root / AGENT_GUIDANCE_RELATIVE_PATH)
    if raw is None:
        return failures
    failures.extend(_check_top_level(raw))
    failures.extend(_check_guidance(raw))
    return failures


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the AUT-811 agent guidance profile.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (defaults to the repo containing this file).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON failures.")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    failures = evaluate_agent_guidance(args.repo_root)
    exceptions_file = args.repo_root / "tools" / "policy" / "exceptions.yaml"
    if exceptions_file.is_file():
        try:
            failures = apply_exceptions(failures, load_exceptions(args.repo_root))
        except InvalidInputError as exc:
            print(f"agent-guidance: {exc}", file=sys.stderr)
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
