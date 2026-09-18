"""Selected input validation, independent of repository-wide policy checks."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tools.tooling_artifact_policy_artifacts import artifact_failures
from tools.tooling_artifact_policy_common import (
    ADMISSION_POLICY_PATH,
    ARTIFACT_LOCK_PATH,
    PROFILES_PATH,
    as_list,
    normalize_platform_id,
    read_tooling_document,
    string_set,
    validate_tooling_record,
)


def _selected_artifact(
    lock: dict[str, Any], artifact_id: str, platform_id: str, host_profile_id: str | None
) -> dict[str, Any]:
    matches = [item for item in lock["artifacts"] if item["artifact_id"] == artifact_id]
    if len(matches) != 1:
        raise ValueError("selected artifact or dependency must resolve to exactly one lock entry")
    artifact = matches[0]
    platforms = [
        item
        for item in artifact["platforms"]
        if normalize_platform_id(item["platform_id"]) == normalize_platform_id(platform_id)
        and (host_profile_id is None or not item.get("host_profile_ids") or host_profile_id in item["host_profile_ids"])
    ]
    if len(platforms) != 1:
        raise ValueError("selected artifact platform must resolve to exactly one lock entry")
    return {**artifact, "platforms": platforms}


def _selected_profiles(
    repo_root: Path, profiles: dict[str, Any], selected: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    profile_ids = {
        profile_id
        for artifact in selected.values()
        for platform in artifact["platforms"]
        for profile_id in platform["profile_ids"]
    }
    selected_profiles = []
    for profile_id in sorted(profile_ids):
        matches = [
            item
            for item in as_list(profiles.get("profiles"))
            if isinstance(item, Mapping) and item.get("profile_id") == profile_id
        ]
        if len(matches) != 1:
            raise ValueError("selected artifact profile must resolve to exactly one entry")
        profile = matches[0]
        validate_tooling_record(repo_root, profile, PROFILES_PATH, definition="artifactProfile")
        selected_profiles.append(
            {
                **profile,
                "supported_artifact_ids": sorted(string_set(profile.get("supported_artifact_ids")) & selected.keys()),
            }
        )
    return selected_profiles


def selected_artifact_documents(
    repo_root: Path,
    artifact_ids: set[str],
    platform_id: str,
    *,
    host_profile_id: str | None = None,
    profiles: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Validate the selected platform's inputs and transitive dependencies.

    The lock is read once. Its shape is checked before projection, while the
    existing semantic validator operates on only the selected dependency set.
    Qualification records and other repository configuration are not inputs.
    """

    lock = read_tooling_document(repo_root, ARTIFACT_LOCK_PATH)
    validate_tooling_record(repo_root, lock, ARTIFACT_LOCK_PATH)
    admission = read_tooling_document(repo_root, ADMISSION_POLICY_PATH)
    validate_tooling_record(repo_root, admission, ADMISSION_POLICY_PATH)
    profiles = profiles if profiles is not None else read_tooling_document(repo_root, PROFILES_PATH)
    selected: dict[str, dict[str, Any]] = {}
    pending = set(artifact_ids)
    while pending:
        artifact_id = pending.pop()
        artifact = _selected_artifact(lock, artifact_id, platform_id, host_profile_id)
        selected[artifact_id] = artifact
        pending.update(string_set(artifact["platforms"][0].get("dependencies")) - selected.keys())
    documents = {
        ARTIFACT_LOCK_PATH: {**lock, "artifacts": list(selected.values())},
        PROFILES_PATH: {"profiles": _selected_profiles(repo_root, profiles, selected)},
        ADMISSION_POLICY_PATH: admission,
    }
    failures = artifact_failures(repo_root, documents)
    if failures:
        raise ValueError(
            "selected artifact integrity policy is invalid: " + ", ".join(sorted({f.rule_id for f in failures}))
        )
    return documents
