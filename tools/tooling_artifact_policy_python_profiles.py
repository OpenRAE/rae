"""Semantic policy for reviewed Python closure profiles and their projections."""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from raes_contracts.errors import InvalidInputError  # noqa: E402

from tools.policy.common import PolicyFailure  # noqa: E402
from tools.tooling_artifact_policy_common import (  # noqa: E402
    PROFILES_PATH,
    as_list,
    failure,
    is_regular_repo_file,
    read_tooling_document,
)

PYTHON_PROJECT_LOCK_PATH = "implementations/python/uv.lock"
PYTHON_TOOL_LOCK_PATH = "implementations/tooling/python/uv.lock"
_EXPECTED_CONTEXT_IDS = frozenset({"python-public"})
_PROJECT_SCOPED_PURPOSES = frozenset({"wheel-smoke", "sdist-smoke", "compatibility", "docs"})
_PROJECTION_SIZE_LIMIT = 2 * 1024 * 1024


def _value_set(value: object) -> set[object] | None:
    """Return the set of one authored collection, or None when the value has no set form."""

    try:
        return set(value)
    except TypeError:
        # A scalar is not iterable, and a list of lists or objects cannot be hashed.
        return None


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


def _context_failures(contexts: Sequence[Mapping[str, Any]]) -> list[PolicyFailure]:
    """Validate credential, mirror, and fallback policy for each context."""

    failures: list[PolicyFailure] = []
    for context in contexts:
        mode = context.get("mode")
        if mode != "public" or context.get("credential_refs", []):
            failures.append(
                failure(
                    "tooling-python-credentials",
                    "Python acquisition must use the credential-free public context",
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
    host_profile_id = value.get("host_profile_id")
    # The known host ids are text, so an id of another type, also one that cannot be hashed, is unknown.
    if not isinstance(host_profile_id, str) or host_profile_id not in host_ids:
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
    if not project_scoped and _value_set(value.get("purposes", [])) != {"tool", "build"}:
        failures.append(
            failure(
                "tooling-python-purposes",
                "non-project Python closures must bind both tool and build purposes",
                PROFILES_PATH,
            )
        )
    expected_extras = {"dev", "docs", "distributed"} if project_scoped else set()
    for field, expected, rule_id, message in (
        (
            "project_extras",
            expected_extras,
            "tooling-python-extras",
            "project smoke closures must include all extras and tool/build closures must include none",
        ),
        (
            "tool_groups",
            {"default", "build"},
            "tooling-python-groups",
            "every Python closure must bind tool and build groups",
        ),
        (
            "acquisition_context_ids",
            set(context_ids),
            "tooling-python-context-binding",
            "Python closure profile must bind every acquisition context",
        ),
    ):
        if _value_set(value.get(field, [])) != expected:
            failures.append(failure(rule_id, message, PROFILES_PATH))
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
        manifest = read_tooling_document(repo_root, manifest_path)
        requirements = (repo_root / requirements_path).read_bytes()
    except (OSError, InvalidInputError):
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
        str(value.get("host_profile_id"))
        for value in as_list(profiles.get("host_profiles"))
        if isinstance(value, Mapping)
    }
    failures: list[PolicyFailure] = []
    seen: set[str] = set()
    for value in as_list(profiles.get("python_closure_profiles")):
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
        project_scoped = bool((_value_set(value.get("purposes", [])) or set()) & _PROJECT_SCOPED_PURPOSES)
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

    contexts = [value for value in as_list(profiles.get("python_package_contexts")) if isinstance(value, Mapping)]
    context_ids = [str(value.get("context_id", "")) for value in contexts]
    return [
        *_context_set_failures(context_ids),
        *_context_failures(contexts),
        *_closure_profile_failures(repo_root, profiles, context_ids),
    ]


__all__ = ("profile_semantic_failures",)
