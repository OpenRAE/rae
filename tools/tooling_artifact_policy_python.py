"""Semantic policy for reviewed Python tool, build, and smoke closures."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement

from tools.generate_python_closures import generate as generate_python_closures
from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import (
    PROFILES_PATH,
    failure,
    is_regular_repo_file,
)

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


def _toml(repo_root: Path, relative_path: str) -> Mapping[str, Any] | None:
    if not is_regular_repo_file(repo_root, relative_path):
        return None
    try:
        payload = (repo_root / relative_path).read_bytes()
        if len(payload) > 4 * 1024 * 1024:
            return None
        value = tomllib.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return None
    return value


def _direct_pins(requirements: object) -> dict[str, str] | None:
    if not isinstance(requirements, list):
        return None
    pins: dict[str, str] = {}
    try:
        for value in requirements:
            if not isinstance(value, str):
                return None
            requirement = Requirement(value)
            specifiers = list(requirement.specifier)
            if len(specifiers) != 1 or specifiers[0].operator != "==" or requirement.name.lower() in pins:
                return None
            pins[requirement.name.lower()] = specifiers[0].version
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


def _constraint_records(text: str) -> dict[str, tuple[str, set[str]]] | None:
    records: dict[str, tuple[str, set[str]]] = {}
    logical = text.replace("\\\n", " ").splitlines()
    try:
        for line in logical:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            requirement = Requirement(stripped.split("--hash", 1)[0].strip())
            specifiers = list(requirement.specifier)
            hashes = set(_HASH_RE.findall(stripped))
            if len(specifiers) != 1 or specifiers[0].operator != "==" or not hashes:
                return None
            name = requirement.name.lower()
            if name in records:
                return None
            records[name] = (specifiers[0].version, hashes)
    except InvalidRequirement:
        return None
    return records


def _profile_semantic_failures(
    repo_root: Path,
    profiles: Mapping[str, Any],
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    contexts = [value for value in profiles.get("python_package_contexts", []) if isinstance(value, Mapping)]
    context_ids = [str(value.get("context_id", "")) for value in contexts]
    if set(context_ids) != {
        "python-public",
        "python-enterprise-mirror-only",
        "python-offline",
    } or len(context_ids) != len(set(context_ids)):
        failures.append(
            failure(
                "tooling-python-contexts",
                "Python package contexts must be exact and unique",
                PROFILES_PATH,
            )
        )
    for context in contexts:
        mode = context.get("mode")
        credentials = context.get("credential_refs", [])
        mappings = context.get("namespace_mapping", [])
        if mode in {"public", "offline"} and credentials:
            failures.append(
                failure(
                    "tooling-python-credentials",
                    "public and offline Python contexts must be credential-free",
                    PROFILES_PATH,
                )
            )
        if mode == "mirror-only" and (
            not credentials
            or len(mappings) != 1
            or not isinstance(mappings[0], Mapping)
            or mappings[0].get("namespace") != "*"
            or mappings[0].get("locator_ref") != context.get("locator_ref")
        ):
            failures.append(
                failure(
                    "tooling-python-mirror",
                    "mirror-only Python context must map the complete namespace to one credential-referenced mirror",
                    PROFILES_PATH,
                )
            )
        if context.get("public_fallback") != "prohibited":
            failures.append(
                failure(
                    "tooling-python-fallback",
                    "Python package contexts must prohibit fallback",
                    PROFILES_PATH,
                )
            )

    host_ids = {
        str(value.get("host_profile_id")) for value in profiles.get("host_profiles", []) if isinstance(value, Mapping)
    }
    seen: set[str] = set()
    for value in profiles.get("python_closure_profiles", []):
        if not isinstance(value, Mapping):
            continue
        profile_id = str(value.get("python_closure_profile_id", ""))
        if profile_id in seen:
            failures.append(
                failure(
                    "tooling-python-profile-duplicate",
                    "Python closure profile ids must be unique",
                    PROFILES_PATH,
                )
            )
        seen.add(profile_id)
        if value.get("host_profile_id") not in host_ids:
            failures.append(
                failure(
                    "tooling-python-host",
                    "Python closure profile references an unknown host",
                    PROFILES_PATH,
                )
            )
        python = value.get("python", {})
        if isinstance(python, Mapping) and str(python.get("abi", "")) != "cp" + str(python.get("version", "")).replace(
            ".", ""
        ):
            failures.append(
                failure(
                    "tooling-python-abi",
                    "Python ABI must match the selected CPython feature release",
                    PROFILES_PATH,
                )
            )
        purposes = set(value.get("purposes", []))
        project_scoped = bool(purposes & {"wheel-smoke", "sdist-smoke", "compatibility", "docs"})
        if not project_scoped and purposes != {"tool", "build"}:
            failures.append(
                failure(
                    "tooling-python-purposes",
                    "non-project Python closures must bind both tool and build purposes",
                    PROFILES_PATH,
                )
            )
        expected_extras = {"dev", "docs"} if project_scoped else set()
        if set(value.get("project_extras", [])) != expected_extras:
            failures.append(
                failure(
                    "tooling-python-extras",
                    "project smoke closures must include all extras and tool/build closures must include none",
                    PROFILES_PATH,
                )
            )
        if set(value.get("tool_groups", [])) != {"default", "build"}:
            failures.append(
                failure(
                    "tooling-python-groups",
                    "every Python closure must bind tool and build groups",
                    PROFILES_PATH,
                )
            )
        if set(value.get("acquisition_context_ids", [])) != set(context_ids):
            failures.append(
                failure(
                    "tooling-python-context-binding",
                    "Python closure profile must bind every acquisition context",
                    PROFILES_PATH,
                )
            )
        manifest_path = value.get("wheelhouse_manifest")
        requirements_path = value.get("smoke_requirements")
        if not isinstance(manifest_path, str) or not isinstance(requirements_path, str):
            continue
        if not is_regular_repo_file(repo_root, manifest_path) or not is_regular_repo_file(repo_root, requirements_path):
            failures.append(
                failure(
                    "tooling-python-projection",
                    "Python closure projection is missing or non-regular",
                    manifest_path,
                )
            )
            continue
        if (repo_root / manifest_path).stat().st_size > 2 * 1024 * 1024 or (
            repo_root / requirements_path
        ).stat().st_size > 2 * 1024 * 1024:
            failures.append(
                failure(
                    "tooling-python-projection",
                    "Python closure projection exceeds the size limit",
                    manifest_path,
                )
            )
            continue
        try:
            manifest = json.loads((repo_root / manifest_path).read_text(encoding="utf-8"))
            requirements = (repo_root / requirements_path).read_bytes()
        except (OSError, UnicodeError, json.JSONDecodeError):
            failures.append(
                failure(
                    "tooling-python-projection",
                    "Python closure projection could not be parsed",
                    manifest_path,
                )
            )
            continue
        selected_lock_path = PYTHON_PROJECT_LOCK_PATH if project_scoped else PYTHON_TOOL_LOCK_PATH
        selected_lock_digest = hashlib.sha256((repo_root / selected_lock_path).read_bytes()).hexdigest()
        if (
            manifest.get("python_closure_profile_id") != profile_id
            or manifest.get("lock_path") != selected_lock_path
            or manifest.get("lock_sha256") != selected_lock_digest
            or manifest.get("requirements_sha256") != hashlib.sha256(requirements).hexdigest()
        ):
            failures.append(
                failure(
                    "tooling-python-projection-drift",
                    "Python closure projection is not bound to its profile and project lock",
                    manifest_path,
                )
            )
    if not seen:
        failures.append(
            failure(
                "tooling-python-profiles",
                "repository Python project requires reviewed closure profiles",
                PROFILES_PATH,
            )
        )
    return failures


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


def python_closure_failures(
    repo_root: Path,
    documents: Mapping[str, Mapping[str, Any]],
    tracked_paths: Sequence[str],
) -> list[PolicyFailure]:
    """Validate the internal Python closure authorities without acquisition."""

    if not (repo_root / PYTHON_PROJECT_PATH).exists():
        return []
    failures: list[PolicyFailure] = []
    missing = [path for path in PYTHON_AUTHORITY_PATHS if not is_regular_repo_file(repo_root, path)]
    failures.extend(
        failure(
            "tooling-python-authority",
            "Python closure authority must be a repository regular file",
            path,
        )
        for path in missing
    )
    if missing:
        return failures
    project = _toml(repo_root, PYTHON_PROJECT_PATH)
    project_lock = _toml(repo_root, PYTHON_PROJECT_LOCK_PATH)
    tool_project = _toml(repo_root, PYTHON_TOOL_PROJECT_PATH)
    tool_lock = _toml(repo_root, PYTHON_TOOL_LOCK_PATH)
    if any(value is None for value in (project, project_lock, tool_project, tool_lock)):
        return [
            *failures,
            failure(
                "tooling-python-toml",
                "Python closure TOML authority could not be parsed safely",
            ),
        ]
    assert project is not None and project_lock is not None and tool_project is not None and tool_lock is not None

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
    for name, version in {**_EXPECTED_TOOLS, **_EXPECTED_BUILD}.items():
        if versions.get(name) != {version}:
            failures.append(
                failure(
                    "tooling-python-lock",
                    "reviewed Python direct dependency is absent or drifted in the tool lock",
                    PYTHON_TOOL_LOCK_PATH,
                )
            )
    build_requires = _direct_pins(project.get("build-system", {}).get("requires"))
    if build_requires != _EXPECTED_BUILD:
        failures.append(
            failure(
                "tooling-python-build-system",
                "project build-system requirements must match the reviewed build group",
                PYTHON_PROJECT_PATH,
            )
        )
    project_requirements = project.get("project", {}).get("dependencies", [])
    z3_requirements = [
        Requirement(value)
        for value in project_requirements
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
    if (
        constraints is None
        or not _EXPECTED_BUILD.items() <= {name: record[0] for name, record in (constraints or {}).items()}.items()
    ):
        failures.append(
            failure(
                "tooling-python-build-constraints",
                "build constraints must be exact and hash-complete",
                PYTHON_BUILD_CONSTRAINTS_PATH,
            )
        )

    profiles = documents.get(PROFILES_PATH)
    if isinstance(profiles, Mapping):
        failures.extend(_profile_semantic_failures(repo_root, profiles))
    try:
        projections_current = generate_python_closures(check=True, repo_root=repo_root)
    except (OSError, UnicodeError, ValueError, tomllib.TOMLDecodeError):
        projections_current = False
    if not projections_current:
        failures.append(
            failure(
                "tooling-python-projection-generation",
                "Python closure projections must exactly match the reviewed lock authorities",
                "implementations/tooling/python/smoke",
            )
        )
    failures.extend(_legacy_surface_failures(repo_root, tracked_paths))
    return failures
