"""Semantic policy for reviewed Python tool, build, and smoke closures."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from packaging.requirements import InvalidRequirement, Requirement

from tools.generate_python_closures import generate as generate_python_closures
from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import (
    PROFILES_PATH,
    failure,
    is_regular_repo_file,
)
from tools.tooling_artifact_policy_python_profiles import profile_semantic_failures

PYTHON_PROJECT_PATH = "implementations/python/pyproject.toml"
PYTHON_PROJECT_LOCK_PATH = "implementations/python/uv.lock"
PYTHON_TOOL_PROJECT_PATH = "implementations/tooling/python/pyproject.toml"
PYTHON_TOOL_LOCK_PATH = "implementations/tooling/python/uv.lock"
PYTHON_BUILD_CONSTRAINTS_PATH = "implementations/tooling/python/build-constraints.txt"
PYTHON_AUTHORITY_PATHS = (
    PYTHON_PROJECT_PATH,
    PYTHON_PROJECT_LOCK_PATH,
    PYTHON_TOOL_PROJECT_PATH,
    PYTHON_TOOL_LOCK_PATH,
    PYTHON_BUILD_CONSTRAINTS_PATH,
)
_EXPECTED_TOOLS = {
    "check-jsonschema": "0.37.1",
    "cryptography": "46.0.3",
    "nox": "2026.4.10",
    "pip": "26.0.1",
    "pre-commit": "4.3.0",
    "pre-commit-hooks": "6.0.0",
    "pytest": "9.0.3",
    "pytest-timeout": "2.4.0",
    "ruff": "0.15.9",
    "uv": "0.12.4",
}
_EXPECTED_BUILD = {"hatchling": "1.27.0"}
_HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})")
_TOML_SIZE_LIMIT = 4 * 1024 * 1024


def _bounded_repo_bytes(repo_root: Path, relative_path: str, *, limit: int) -> bytes | None:
    """Read a tracked regular file, refusing anything missing or oversized."""

    if not is_regular_repo_file(repo_root, relative_path):
        return None
    try:
        payload = (repo_root / relative_path).read_bytes()
    except OSError:
        return None
    return None if len(payload) > limit else payload


def _toml(repo_root: Path, relative_path: str) -> Mapping[str, Any] | None:
    """Parse one tracked TOML authority, or None when it cannot be trusted."""

    payload = _bounded_repo_bytes(repo_root, relative_path, limit=_TOML_SIZE_LIMIT)
    if payload is None:
        return None
    try:
        return tomllib.loads(payload.decode("utf-8"))
    except ValueError:
        return None


def _exact_pin(value: object, seen: Mapping[str, str]) -> tuple[str, str]:
    """Return one exact name/version pin, rejecting anything inexact or duplicated."""

    if not isinstance(value, str):
        raise InvalidRequirement("direct dependency must be a requirement string")
    requirement = Requirement(value)
    specifiers = list(requirement.specifier)
    name = requirement.name.lower()
    if len(specifiers) != 1 or specifiers[0].operator != "==" or name in seen:
        raise InvalidRequirement("direct dependency must carry one unique exact pin")
    return name, specifiers[0].version


def _direct_pins(requirements: object) -> dict[str, str] | None:
    """Index exact ``==`` direct pins, or None when any requirement is not exact."""

    if not isinstance(requirements, list):
        return None
    pins: dict[str, str] = {}
    try:
        for value in requirements:
            name, version = _exact_pin(value, pins)
            pins[name] = version
    except InvalidRequirement:
        return None
    return pins


def _lock_versions(lock: Mapping[str, Any]) -> dict[str, set[str]]:
    versions: dict[str, set[str]] = {}
    for package in lock.get("package", []):
        if not isinstance(package, Mapping) or not isinstance(package.get("name"), str):
            continue
        versions.setdefault(package["name"].lower(), set()).add(str(package.get("version", "")))
    return versions


def _constraint_record(line: str, seen: Mapping[str, tuple[str, set[str]]]) -> tuple[str, tuple[str, set[str]]]:
    """Return one exact hash-complete constraint, rejecting anything else."""

    requirement = Requirement(line.split("--hash", 1)[0].strip())
    specifiers = list(requirement.specifier)
    hashes = set(_HASH_RE.findall(line))
    name = requirement.name.lower()
    if len(specifiers) != 1 or specifiers[0].operator != "==" or not hashes or name in seen:
        raise InvalidRequirement("build constraint must carry one unique exact hash-pinned version")
    return name, (specifiers[0].version, hashes)


def _constraint_records(text: str) -> dict[str, tuple[str, set[str]]] | None:
    """Index exact hash-pinned build constraints, or None when any line is not."""

    records: dict[str, tuple[str, set[str]]] = {}
    try:
        for line in text.replace("\\\n", " ").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            name, record = _constraint_record(stripped, records)
            records[name] = record
    except InvalidRequirement:
        return None
    return records


def _legacy_surface_failures(repo_root: Path, tracked_paths: Sequence[str]) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    excluded_prefixes = ("docs/decisions/adrs/", "docs/decisions/issue-")
    excluded_paths = {
        "implementations/python/tests/test_public_project_readiness.py",
        "implementations/python/tests/test_tooling_artifact_policy.py",
        "tools/tooling_artifact_policy_python.py",
    }
    for relative_path in tracked_paths:
        if relative_path in excluded_paths or relative_path.startswith(excluded_prefixes):
            continue
        if Path(relative_path).suffix not in {
            ".md",
            ".py",
            ".toml",
            ".yaml",
            ".yml",
        } and Path(relative_path).name not in {
            "Makefile",
        }:
            continue
        path = repo_root / relative_path
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if "uv tool run" in text:
            failures.append(
                failure(
                    "tooling-python-ad-hoc-tool",
                    "tracked consumer still creates an ad hoc isolated Python tool environment",
                    relative_path,
                )
            )
    return failures


def _python_authorities(
    repo_root: Path,
) -> tuple[tuple[Mapping[str, Any], ...] | None, list[PolicyFailure]]:
    """Parse the reviewed Python authorities, or report why they cannot be read."""

    missing = [path for path in PYTHON_AUTHORITY_PATHS if not is_regular_repo_file(repo_root, path)]
    if missing:
        return None, [
            failure(
                "tooling-python-authority",
                "Python closure authority must be a repository regular file",
                path,
            )
            for path in missing
        ]
    parsed = tuple(
        _toml(repo_root, path)
        for path in (
            PYTHON_PROJECT_PATH,
            PYTHON_PROJECT_LOCK_PATH,
            PYTHON_TOOL_PROJECT_PATH,
            PYTHON_TOOL_LOCK_PATH,
        )
    )
    if any(value is None for value in parsed):
        return None, [
            failure(
                "tooling-python-toml",
                "Python closure TOML authority could not be parsed safely",
            )
        ]
    return cast("tuple[Mapping[str, Any], ...]", parsed), []


def _dependency_pin_failures(
    project: Mapping[str, Any],
    tool_project: Mapping[str, Any],
    tool_lock: Mapping[str, Any],
) -> list[PolicyFailure]:
    """Require the reviewed exact tool, build, and build-system pin sets."""

    failures: list[PolicyFailure] = []
    tool_pins = _direct_pins(tool_project.get("project", {}).get("dependencies"))
    build_pins = _direct_pins(tool_project.get("dependency-groups", {}).get("build"))
    if tool_pins != _EXPECTED_TOOLS or build_pins != _EXPECTED_BUILD:
        failures.append(
            failure(
                "tooling-python-direct-pins",
                "Python tool and build direct dependencies must match the reviewed exact set",
                PYTHON_TOOL_PROJECT_PATH,
            )
        )
    versions = _lock_versions(tool_lock)
    failures.extend(
        failure(
            "tooling-python-lock",
            "reviewed Python direct dependency is absent or drifted in the tool lock",
            PYTHON_TOOL_LOCK_PATH,
        )
        for name, version in {**_EXPECTED_TOOLS, **_EXPECTED_BUILD}.items()
        if versions.get(name) != {version}
    )
    if _direct_pins(project.get("build-system", {}).get("requires")) != _EXPECTED_BUILD:
        failures.append(
            failure(
                "tooling-python-build-system",
                "project build-system requirements must match the reviewed build group",
                PYTHON_PROJECT_PATH,
            )
        )
    return failures


def _governed_pin_failures(repo_root: Path, project: Mapping[str, Any]) -> list[PolicyFailure]:
    """Require the governed solver pin and hash-complete build constraints."""

    failures: list[PolicyFailure] = []
    z3_requirements = [
        Requirement(value)
        for value in project.get("project", {}).get("dependencies", [])
        if isinstance(value, str) and Requirement(value).name.lower() == "z3-solver"
    ]
    if len(z3_requirements) != 1 or str(z3_requirements[0].specifier) != "==4.16.0.0":
        failures.append(
            failure(
                "tooling-python-z3",
                "the governed Z3 dependency pin must remain exact",
                PYTHON_PROJECT_PATH,
            )
        )
    constraints = _constraint_records((repo_root / PYTHON_BUILD_CONSTRAINTS_PATH).read_text(encoding="utf-8"))
    recorded = {name: record[0] for name, record in (constraints or {}).items()}
    hash_complete = constraints is not None and _EXPECTED_BUILD.items() <= recorded.items()
    if not hash_complete:
        failures.append(
            failure(
                "tooling-python-build-constraints",
                "build constraints must be exact and hash-complete",
                PYTHON_BUILD_CONSTRAINTS_PATH,
            )
        )
    return failures


def _projection_generation_failures(repo_root: Path) -> list[PolicyFailure]:
    """Require the checked-in projections to match a fresh generation exactly."""

    try:
        projections_current = generate_python_closures(check=True, repo_root=repo_root)
    except (OSError, ValueError):
        projections_current = False
    if projections_current:
        return []
    return [
        failure(
            "tooling-python-projection-generation",
            "Python closure projections must exactly match the reviewed lock authorities",
            "implementations/tooling/python/smoke",
        )
    ]


def python_closure_failures(
    repo_root: Path,
    documents: Mapping[str, Mapping[str, Any]],
    tracked_paths: Sequence[str],
) -> list[PolicyFailure]:
    """Validate the internal Python closure authorities without acquisition."""

    if not (repo_root / PYTHON_PROJECT_PATH).exists():
        return []
    authorities, blocking = _python_authorities(repo_root)
    if authorities is None:
        return blocking
    project, _project_lock, tool_project, tool_lock = authorities
    profiles = documents.get(PROFILES_PATH)
    return [
        *_dependency_pin_failures(project, tool_project, tool_lock),
        *_governed_pin_failures(repo_root, project),
        *(profile_semantic_failures(repo_root, profiles) if isinstance(profiles, Mapping) else []),
        *_projection_generation_failures(repo_root),
        *_legacy_surface_failures(repo_root, tracked_paths),
    ]
