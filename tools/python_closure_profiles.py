#!/usr/bin/env python3
"""Reviewed Python closure profiles and the environments they authorize."""

from __future__ import annotations

import os
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.tooling_artifact_policy_common import (
    is_regular_repo_file,
    read_tooling_document,
    validate_tooling_record,
)
from tools.tooling_artifact_policy_python_profiles import (
    _closure_binding_failures,
    _closure_projection_failures,
    _context_failures,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILES_PATH = "implementations/tooling/profiles/development-profiles.json"
TOOL_PROJECT = REPO_ROOT / "implementations" / "tooling" / "python"
_ALLOWED_TOOLS = frozenset(
    {
        "check-added-large-files",
        "check-json",
        "check-merge-conflict",
        "check-yaml",
        "check-jsonschema",
        "detect-private-key",
        "end-of-file-fixer",
        "nox",
        "pre-commit",
        "python",
        "ruff",
        "trailing-whitespace-fixer",
    }
)


@dataclass(frozen=True)
class PythonClosureProfile:
    profile_id: str
    host_profile_id: str
    python_version: str
    abi: str
    platform: str
    purposes: tuple[str, ...]
    project_extras: tuple[str, ...]
    tool_groups: tuple[str, ...]
    acquisition_context_ids: tuple[str, ...]
    project_lock: Path
    tool_lock: Path
    build_constraints: Path
    smoke_requirements: Path
    wheelhouse_manifest: Path
    test_case_ids: tuple[str, ...]
    contexts: Mapping[str, Mapping[str, Any]]


def _repo_file(repo_root: Path, relative_path: object) -> Path:
    if not isinstance(relative_path, str):
        raise ValueError("Python closure authority path must be a string")
    if not is_regular_repo_file(repo_root, relative_path):
        raise ValueError("Python closure authority must be a regular repository file")
    root = repo_root.resolve()
    path = root / relative_path
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Python closure authority is missing") from exc
    if not resolved.is_relative_to(root):
        raise ValueError("Python closure authority must stay inside the repository")
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ValueError("Python closure authority is missing") from exc
    if not stat.S_ISREG(mode) or path.is_symlink():
        raise ValueError("Python closure authority must be a regular file")
    return resolved


def _load_bounded_json_object(repo_root: Path, relative_path: object) -> dict[str, Any]:
    path = _repo_file(repo_root, relative_path)
    return read_tooling_document(repo_root, str(path.relative_to(repo_root.resolve())))


def _selected_closure_profile(repo_root: Path, document: dict[str, Any], profile_id: str) -> Mapping[str, Any]:
    matches = [
        value
        for value in document.get("python_closure_profiles", [])
        if isinstance(value, Mapping) and value.get("python_closure_profile_id") == profile_id
    ]
    if len(matches) != 1:
        raise ValueError("Python closure profile must resolve to exactly one reviewed entry")
    value = matches[0]
    validate_tooling_record(repo_root, value, PROFILES_PATH, definition="pythonClosureProfile")
    return value


def _selected_closure_contexts(
    repo_root: Path, document: dict[str, Any], context_ids: list[str]
) -> dict[str, Mapping[str, Any]]:
    contexts = {}
    for context_id in context_ids:
        matches = [
            context
            for context in document.get("python_package_contexts", [])
            if isinstance(context, Mapping) and context.get("context_id") == context_id
        ]
        if len(matches) != 1:
            raise ValueError("Python acquisition context must resolve to exactly one entry")
        validate_tooling_record(repo_root, matches[0], PROFILES_PATH, definition="pythonPackageContext")
        contexts[context_id] = matches[0]
    return contexts


def load_python_closure_profile(repo_root: Path, profile_id: str) -> PythonClosureProfile:
    """Validate one Python environment without inspecting unrelated repository policy."""
    document = _load_bounded_json_object(repo_root, PROFILES_PATH)
    value = _selected_closure_profile(repo_root, document, profile_id)
    python = value["python"]
    contexts = _selected_closure_contexts(repo_root, document, value["acquisition_context_ids"])
    project_scoped = bool(set(value["purposes"]) & {"wheel-smoke", "sdist-smoke", "compatibility", "docs"})
    failures = _closure_binding_failures(
        value,
        host_ids={
            str(host.get("host_profile_id")) for host in document.get("host_profiles", []) if isinstance(host, Mapping)
        },
        context_ids=list(contexts),
        project_scoped=project_scoped,
    )
    failures.extend(_context_failures(list(contexts.values())))
    # Resolve all authority paths before reading a projection or lock.
    for key in (
        "project_lock",
        "tool_lock",
        "build_constraints",
        "smoke_requirements",
        "wheelhouse_manifest",
    ):
        _repo_file(repo_root, value[key])
    failures.extend(
        _closure_projection_failures(repo_root, value, profile_id=profile_id, project_scoped=project_scoped)
    )
    if failures:
        raise ValueError("Python closure binding or projection is invalid")
    return PythonClosureProfile(
        profile_id=profile_id,
        host_profile_id=str(value["host_profile_id"]),
        python_version=str(python["version"]),
        abi=str(python["abi"]),
        platform=str(python["platform"]),
        purposes=tuple(value["purposes"]),
        project_extras=tuple(value["project_extras"]),
        tool_groups=tuple(value["tool_groups"]),
        acquisition_context_ids=tuple(value["acquisition_context_ids"]),
        project_lock=_repo_file(repo_root, value["project_lock"]),
        tool_lock=_repo_file(repo_root, value["tool_lock"]),
        build_constraints=_repo_file(repo_root, value["build_constraints"]),
        smoke_requirements=_repo_file(repo_root, value["smoke_requirements"]),
        wheelhouse_manifest=_repo_file(repo_root, value["wheelhouse_manifest"]),
        test_case_ids=tuple(value["test_case_ids"]),
        contexts=contexts,
    )


def load_wheelhouse_manifest(profile: PythonClosureProfile) -> dict[str, Any]:
    return _load_bounded_json_object(
        profile.wheelhouse_manifest.parent,
        profile.wheelhouse_manifest.name,
    )


def closure_environment(
    profile: PythonClosureProfile,
    *,
    context_id: str,
    home: Path,
    cache_dir: Path,
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Construct the profile-owned minimal environment for a uv invocation."""

    if context_id not in profile.acquisition_context_ids or context_id not in profile.contexts:
        raise ValueError("acquisition context is not admitted by the Python closure profile")
    context = profile.contexts[context_id]
    source = os.environ if source is None else source
    environment = {
        "HOME": str(home),
        "PATH": source.get("PATH", os.defpath),
        "UV_CACHE_DIR": str(cache_dir),
        "UV_KEYRING_PROVIDER": "disabled",
        "UV_PYTHON_DOWNLOADS": "never",
    }
    if context.get("mode") != "public":
        raise ValueError("unsupported Python acquisition context")
    environment.update(UV_DEFAULT_INDEX="https://pypi.org/simple", UV_INDEX_STRATEGY="first-index")
    return environment


def frozen_tool_command(repo_root: Path, tool: str, *args: str) -> list[str]:
    if tool not in _ALLOWED_TOOLS:
        raise ValueError("tool is not present in the reviewed Python tool closure")
    return [
        "uv",
        "run",
        "--project",
        str(repo_root / "implementations" / "tooling" / "python"),
        "--frozen",
        "--no-default-groups",
        tool,
        *args,
    ]


def assert_runtime_matches_profile(profile: PythonClosureProfile) -> None:
    """Refuse to act when the executing interpreter is not the reviewed one."""

    selected = f"{sys.version_info.major}.{sys.version_info.minor}"
    if sys.implementation.name != "cpython" or selected != profile.python_version:
        raise ValueError("executing Python runtime does not match the reviewed closure profile")


__all__ = (
    "PROFILES_PATH",
    "REPO_ROOT",
    "TOOL_PROJECT",
    "PythonClosureProfile",
    "assert_runtime_matches_profile",
    "closure_environment",
    "frozen_tool_command",
    "load_python_closure_profile",
    "load_wheelhouse_manifest",
)
