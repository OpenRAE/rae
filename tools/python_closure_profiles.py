#!/usr/bin/env python3
"""Reviewed Python closure profiles and the environments they authorize."""

from __future__ import annotations

import json
import os
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILES_PATH = "implementations/tooling/profiles/development-profiles.json"
TOOL_PROJECT = REPO_ROOT / "implementations" / "tooling" / "python"
_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_CLOSURE_MODULE_PATHS = ("tools/python_closure.py", "tools/python_closure_profiles.py")
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
    try:
        if path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise ValueError("Python closure authority exceeds the size limit")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Python closure authority is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("Python closure authority must be a JSON object")
    return value


def load_python_closure_profile(repo_root: Path, profile_id: str) -> PythonClosureProfile:
    """Load one exact closed profile after the canonical static policy passes."""

    from tools.check_tooling_artifact_policy import (
        _tracked_paths,
        evaluate_tooling_artifact_policy,
    )

    tracked_paths = _tracked_paths(repo_root)
    tracked_paths.extend(
        module_path
        for module_path in _CLOSURE_MODULE_PATHS
        if module_path not in tracked_paths and (repo_root / module_path).is_file()
    )
    failures = evaluate_tooling_artifact_policy(repo_root, tracked_paths=tracked_paths)
    if failures:
        rendered = "\n".join(item.render() for item in failures[:20])
        raise ValueError(f"development artifact policy is invalid:\n{rendered}")
    document = _load_bounded_json_object(repo_root, PROFILES_PATH)
    matches = [
        value
        for value in document.get("python_closure_profiles", [])
        if isinstance(value, Mapping) and value.get("python_closure_profile_id") == profile_id
    ]
    if len(matches) != 1:
        raise ValueError("Python closure profile must resolve to exactly one reviewed entry")
    value = matches[0]
    python = value["python"]
    contexts = {
        str(context["context_id"]): context
        for context in document.get("python_package_contexts", [])
        if isinstance(context, Mapping) and isinstance(context.get("context_id"), str)
    }
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


def _reviewed_mirror_url(source: Mapping[str, str]) -> str:
    """Require a credential-free HTTPS locator before a mirror-only acquisition."""

    mirror_url = source.get("RAES_PYTHON_MIRROR_URL", "")
    parsed = urlsplit(mirror_url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("mirror-only context requires a credential-free HTTPS mirror locator")
    return mirror_url


def _acquisition_mode_environment(mode: object, source: Mapping[str, str]) -> dict[str, str]:
    """Derive index and offline policy from one reviewed acquisition mode."""

    if mode == "offline":
        return {"UV_OFFLINE": "1"}
    if mode not in {"public", "mirror-only"}:
        raise ValueError("unsupported Python acquisition context")
    index = "https://pypi.org/simple" if mode == "public" else _reviewed_mirror_url(source)
    return {"UV_DEFAULT_INDEX": index, "UV_INDEX_STRATEGY": "first-index"}


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
    environment.update(_acquisition_mode_environment(context.get("mode"), source))
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
