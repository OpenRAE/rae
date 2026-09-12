"""Semantic policy for reviewed Python closure profiles and their projections."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import (
    PROFILES_PATH,
    failure,
    is_regular_repo_file,
)

PYTHON_PROJECT_LOCK_PATH = "implementations/python/uv.lock"
PYTHON_TOOL_LOCK_PATH = "implementations/tooling/python/uv.lock"
_EXPECTED_CONTEXT_IDS = frozenset(
    {
        "python-public",
        "python-enterprise-mirror-only",
        "python-offline",
    }
)
_PROJECT_SCOPED_PURPOSES = frozenset({"wheel-smoke", "sdist-smoke", "compatibility", "docs"})
_PROJECTION_SIZE_LIMIT = 2 * 1024 * 1024


def _context_set_failures(context_ids: Sequence[str]) -> list[PolicyFailure]:
    """Require the acquisition-context set to be exactly the reviewed one."""

    if set(context_ids) == _EXPECTED_CONTEXT_IDS and len(context_ids) == len(set(context_ids)):
        return []
    return [
        failure(
            "tooling-python-contexts",
            "Python package contexts must be exact and unique",
            PROFILES_PATH,
        )
    ]


def _maps_complete_namespace(context: Mapping[str, Any]) -> bool:
    """Report whether a mirror-only context maps everything to one credentialed mirror."""

    mappings = context.get("namespace_mapping", [])
    return bool(
        context.get("credential_refs", [])
        and len(mappings) == 1
        and isinstance(mappings[0], Mapping)
        and mappings[0].get("namespace") == "*"
        and mappings[0].get("locator_ref") == context.get("locator_ref")
    )


def _context_failures(contexts: Sequence[Mapping[str, Any]]) -> list[PolicyFailure]:
    """Validate credential, mirror, and fallback policy for each context."""

    failures: list[PolicyFailure] = []
    for context in contexts:
        mode = context.get("mode")
        if mode in {"public", "offline"} and context.get("credential_refs", []):
            failures.append(
                failure(
                    "tooling-python-credentials",
                    "public and offline Python contexts must be credential-free",
                    PROFILES_PATH,
                )
            )
        if mode == "mirror-only" and not _maps_complete_namespace(context):
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
    return failures


def _closure_binding_failures(
    value: Mapping[str, Any],
    *,
    host_ids: set[str],
    context_ids: Sequence[str],
    project_scoped: bool,
) -> list[PolicyFailure]:
    """Validate the host, runtime, purpose, and context bindings of one closure."""

    failures: list[PolicyFailure] = []
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
    if not project_scoped and set(value.get("purposes", [])) != {"tool", "build"}:
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
    return failures


def _projection_read_failure(
    repo_root: Path,
    manifest_path: str,
    requirements_path: str,
) -> PolicyFailure | None:
    """Report why a closure projection cannot be read, or None when it can."""

    if not is_regular_repo_file(repo_root, manifest_path) or not is_regular_repo_file(repo_root, requirements_path):
        return failure(
            "tooling-python-projection",
            "Python closure projection is missing or non-regular",
            manifest_path,
        )
    oversized = (repo_root / manifest_path).stat().st_size > _PROJECTION_SIZE_LIMIT or (
        repo_root / requirements_path
    ).stat().st_size > _PROJECTION_SIZE_LIMIT
    if oversized:
        return failure(
            "tooling-python-projection",
            "Python closure projection exceeds the size limit",
            manifest_path,
        )
    return None


def _projection_drift_failures(
    repo_root: Path,
    *,
    manifest_path: str,
    requirements_path: str,
    profile_id: str,
    project_scoped: bool,
) -> list[PolicyFailure]:
    """Require one readable projection to be bound to its profile and lock."""

    try:
        manifest = json.loads((repo_root / manifest_path).read_text(encoding="utf-8"))
        requirements = (repo_root / requirements_path).read_bytes()
    except (OSError, ValueError):
        return [
            failure(
                "tooling-python-projection",
                "Python closure projection could not be parsed",
                manifest_path,
            )
        ]
    selected_lock_path = PYTHON_PROJECT_LOCK_PATH if project_scoped else PYTHON_TOOL_LOCK_PATH
    selected_lock_digest = hashlib.sha256((repo_root / selected_lock_path).read_bytes()).hexdigest()
    bound = (
        manifest.get("python_closure_profile_id") == profile_id
        and manifest.get("lock_path") == selected_lock_path
        and manifest.get("lock_sha256") == selected_lock_digest
        and manifest.get("requirements_sha256") == hashlib.sha256(requirements).hexdigest()
    )
    if bound:
        return []
    return [
        failure(
            "tooling-python-projection-drift",
            "Python closure projection is not bound to its profile and project lock",
            manifest_path,
        )
    ]


def _closure_projection_failures(
    repo_root: Path,
    value: Mapping[str, Any],
    *,
    profile_id: str,
    project_scoped: bool,
) -> list[PolicyFailure]:
    """Validate the checked-in projection one closure profile points at."""

    manifest_path = value.get("wheelhouse_manifest")
    requirements_path = value.get("smoke_requirements")
    if not isinstance(manifest_path, str) or not isinstance(requirements_path, str):
        return []
    read_failure = _projection_read_failure(repo_root, manifest_path, requirements_path)
    if read_failure is not None:
        return [read_failure]
    return _projection_drift_failures(
        repo_root,
        manifest_path=manifest_path,
        requirements_path=requirements_path,
        profile_id=profile_id,
        project_scoped=project_scoped,
    )


def _closure_profile_failures(
    repo_root: Path,
    profiles: Mapping[str, Any],
    context_ids: Sequence[str],
) -> list[PolicyFailure]:
    """Validate every reviewed Python closure profile and its projection."""

    host_ids = {
        str(value.get("host_profile_id")) for value in profiles.get("host_profiles", []) if isinstance(value, Mapping)
    }
    failures: list[PolicyFailure] = []
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
        project_scoped = bool(set(value.get("purposes", [])) & _PROJECT_SCOPED_PURPOSES)
        failures.extend(
            _closure_binding_failures(
                value,
                host_ids=host_ids,
                context_ids=context_ids,
                project_scoped=project_scoped,
            )
        )
        failures.extend(
            _closure_projection_failures(
                repo_root,
                value,
                profile_id=profile_id,
                project_scoped=project_scoped,
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


def profile_semantic_failures(repo_root: Path, profiles: Mapping[str, Any]) -> list[PolicyFailure]:
    """Validate acquisition contexts and closure profiles against reviewed policy."""

    contexts = [value for value in profiles.get("python_package_contexts", []) if isinstance(value, Mapping)]
    context_ids = [str(value.get("context_id", "")) for value in contexts]
    return [
        *_context_set_failures(context_ids),
        *_context_failures(contexts),
        *_closure_profile_failures(repo_root, profiles, context_ids),
    ]


__all__ = ("profile_semantic_failures",)
