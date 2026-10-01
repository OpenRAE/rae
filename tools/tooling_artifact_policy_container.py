"""Focused base identity and privilege checks for the native development image.

Docker and dev-container clients interpret their native configuration. This
checker does not model package commands, shell syntax, account creation, editor
settings, or native package repository snapshots.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import (
    ARTIFACT_LOCK_PATH,
    PROFILES_PATH,
    as_list,
    as_mapping,
    failure,
    normalize_platform_id,
    safe_text,
)
from tools.tooling_artifact_policy_devcontainer import (
    devcontainer_failures,
    load_devcontainer_config,
)

CONTAINER_DOCKERFILE_PATH = ".devcontainer/Dockerfile"
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_OCI_PLATFORMS = {"linux-x86_64": "linux/amd64"}


def _container_host_profiles(
    documents: Mapping[str, dict[str, Any]],
) -> list[Mapping[str, Any]]:
    return [
        host
        for host in as_list((documents.get(PROFILES_PATH) or {}).get("host_profiles"))
        if isinstance(host, Mapping) and isinstance(host.get("base_image_artifact_ref"), str)
    ]


def _locked_platform_manifest(
    documents: Mapping[str, dict[str, Any]], artifact_ref: object, platform_id: str
) -> tuple[str, str] | None:
    """Return the locked OCI repository and the one manifest digest for a platform, or None."""

    for artifact_value in as_list((documents.get(ARTIFACT_LOCK_PATH) or {}).get("artifacts")):
        artifact = as_mapping(artifact_value)
        if artifact.get("artifact_id") != artifact_ref or artifact.get("artifact_class") != "oci-image":
            continue
        repository = as_mapping(artifact.get("source")).get("asset")
        digests = [
            as_mapping(entry).get("sha256")
            for value in as_list(artifact.get("platforms"))
            if normalize_platform_id(str((platform := as_mapping(value)).get("platform_id", ""))) == platform_id
            for entry in as_list(platform.get("raw_manifest"))
        ]
        if isinstance(repository, str) and len(digests) == 1 and _DIGEST_RE.fullmatch(str(digests[0])):
            return repository, str(digests[0])
    return None


def container_failures(
    repo_root: Path,
    documents: Mapping[str, dict[str, Any]],
    tracked_paths: Sequence[str] | None = None,
) -> list[PolicyFailure]:
    """Check the locked image projection and explicit non-root boundary."""
    del tracked_paths
    hosts = _container_host_profiles(documents)
    dockerfile = safe_text(repo_root, CONTAINER_DOCKERFILE_PATH)
    if len(hosts) != 1 or dockerfile is None:
        failures = [
            failure(
                "tooling-container-profile",
                "one reviewed container profile and Dockerfile are required",
                PROFILES_PATH,
            )
        ]
        return [] if not hosts and dockerfile is None else failures
    host = hosts[0]
    platform_id = normalize_platform_id(str(host.get("platform_id", "")))
    locked = _locked_platform_manifest(documents, host.get("base_image_artifact_ref"), platform_id)
    if (
        locked is None
        or platform_id not in _OCI_PLATFORMS
        or not str(host.get("base_image_identity", "")).startswith(locked[0] + ":")
    ):
        return [
            failure(
                "tooling-container-profile",
                "container base must bind a supported locked platform",
                PROFILES_PATH,
            )
        ]
    return [
        *_container_base_failures(dockerfile, platform_id, locked),
        *_container_user_failures(repo_root, dockerfile),
    ]


def _dockerfile_instructions(dockerfile: str, instruction: str) -> list[list[str]]:
    return [line.split() for line in dockerfile.splitlines() if line.strip().upper().startswith(instruction + " ")]


def _container_base_failures(dockerfile: str, platform_id: str, locked: tuple[str, str]) -> list[PolicyFailure]:
    failures = []
    stages = _dockerfile_instructions(dockerfile, "FROM")
    reference = f"{locked[0]}@sha256:{locked[1]}"
    if not stages or any(len(tokens) < 3 or tokens[2] != reference for tokens in stages):
        failures.append(
            failure(
                "tooling-container-base-drift",
                "every base must use the locked digest",
                CONTAINER_DOCKERFILE_PATH,
            )
        )
    if any(len(tokens) < 2 or tokens[1] != "--platform=" + _OCI_PLATFORMS[platform_id] for tokens in stages):
        failures.append(
            failure(
                "tooling-container-platform",
                "base platform must match the selected manifest",
                CONTAINER_DOCKERFILE_PATH,
            )
        )
    return failures


def _container_user_failures(repo_root: Path, dockerfile: str) -> list[PolicyFailure]:
    document, config_failure = load_devcontainer_config(repo_root)
    if document is None:
        return [config_failure]
    failures = []
    user = document.get("containerUser")
    users = _dockerfile_instructions(dockerfile, "USER")
    if not isinstance(user, str) or user in {"", "root", "0"} or not users or users[-1][1:] != [user]:
        failures.append(
            failure(
                "tooling-container-user",
                "the final image must run as the non-root development user",
                CONTAINER_DOCKERFILE_PATH,
            )
        )
    if "UV_PYTHON_DOWNLOADS=never" not in dockerfile:
        failures.append(
            failure(
                "tooling-container-unsafe-build",
                "uv must use the verified interpreter",
                CONTAINER_DOCKERFILE_PATH,
            )
        )
    failures.extend(devcontainer_failures(document, str(user)))
    return failures
