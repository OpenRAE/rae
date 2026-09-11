"""Artifact, profile, manifest, and dependency validation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tools.policy.common import PolicyFailure, safe_repo_path
from tools.tooling_artifact_policy_common import (
    ADMISSION_POLICY_PATH,
    ARTIFACT_LOCK_PATH,
    MAX_SCANNED_FILE_BYTES,
    MUTABLE_SELECTORS,
    PROFILES_PATH,
    as_list,
    as_mapping,
    failure,
    has_secret_bearing_locator,
    is_portable_relative_manifest_path,
    is_regular_repo_file,
    normalize_platform_id,
    policy_join_failures,
    string_set,
    walk_forbidden_keys,
)


def _profiles(
    document: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], list[PolicyFailure]]:
    profiles: dict[str, Mapping[str, Any]] = {}
    failures: list[PolicyFailure] = []
    for profile in as_list(document.get("profiles")):
        if not isinstance(profile, Mapping) or not isinstance(profile.get("profile_id"), str):
            continue
        profile_id = profile["profile_id"]
        if profile_id in profiles:
            failures.append(failure("tooling-profile-duplicate", "duplicate development profile", PROFILES_PATH))
        profiles[profile_id] = profile
        canonical = as_mapping(profile.get("platform")).get("canonical_id")
        aliases = string_set(as_mapping(profile.get("platform")).get("aliases"))
        if isinstance(canonical, str) and any(
            normalize_platform_id(alias) != normalize_platform_id(canonical) for alias in aliases
        ):
            failures.append(
                failure(
                    "tooling-profile-alias",
                    f"{profile_id} contains an alias for another platform",
                    PROFILES_PATH,
                )
            )
    return profiles, failures


def _policies(
    document: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], list[PolicyFailure]]:
    policies: dict[str, Mapping[str, Any]] = {}
    failures: list[PolicyFailure] = []
    for policy in as_list(document.get("policies")):
        if not isinstance(policy, Mapping) or not isinstance(policy.get("policy_id"), str):
            continue
        policy_id = policy["policy_id"]
        if policy_id in policies:
            failures.append(failure("tooling-policy-duplicate", "duplicate admission policy id", ADMISSION_POLICY_PATH))
        policies[policy_id] = policy
    return policies, failures


def _is_mutable(value: object) -> bool:
    return isinstance(value, str) and (value.lower() in MUTABLE_SELECTORS or value.lower().startswith("refs/heads/"))


def _artifact_metadata_failures(artifact_id: str, artifact: Mapping[str, Any]) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    source = as_mapping(artifact.get("source"))
    if _is_mutable(artifact.get("version")):
        failures.append(
            failure("tooling-mutable-selector", f"{artifact_id} uses a mutable version", ARTIFACT_LOCK_PATH)
        )
    if _is_mutable(source.get("release")):
        failures.append(
            failure(
                "tooling-mutable-selector",
                f"{artifact_id} uses a mutable release selector",
                ARTIFACT_LOCK_PATH,
            )
        )
    repository = source.get("repository")
    if isinstance(repository, str) and has_secret_bearing_locator(repository):
        failures.append(
            failure(
                "tooling-secret-bearing-locator",
                f"{artifact_id} source locator contains credentials, secret interpolation, or a secret query key",
                ARTIFACT_LOCK_PATH,
            )
        )
    authenticity = as_mapping(artifact.get("authenticity"))
    if authenticity.get("status") not in {"verified", "absent-reviewed"}:
        failures.append(
            failure(
                "tooling-authenticity-unreviewed",
                f"{artifact_id} authenticity is not reviewed",
                ARTIFACT_LOCK_PATH,
            )
        )
    return failures


def _artifact_policy_failures(
    artifact_id: str,
    artifact: Mapping[str, Any],
    policies: Mapping[str, Mapping[str, Any]],
) -> list[PolicyFailure]:
    artifact_class = artifact.get("artifact_class")
    subjects = {"artifact"}
    evidence = {"raw-sha256", "installed-sha256", "exact-size"}
    if artifact_class == "source-snapshot":
        subjects = {"source-snapshot"}
        evidence.update({"checked-in-byte-sha256", "incumbent-source-digest"})
    elif artifact_class == "oci-image":
        subjects = {"oci-image"}
        evidence = {"oci-index-digest", "reviewed-consumer-reference"}
    if as_mapping(artifact.get("authenticity")).get("status") == "absent-reviewed":
        evidence.add("absent-signature-review")
    return policy_join_failures(
        policy_refs=string_set(artifact.get("policy_refs")),
        expected_subjects=subjects,
        provided_evidence=evidence,
        policies=policies,
        path=ARTIFACT_LOCK_PATH,
        context=f"{artifact_id} artifact",
        require_all_evidence_per_policy=True,
    )


def _source_url_failures(artifact_id: str, platform: Mapping[str, Any]) -> list[PolicyFailure]:
    return [
        failure(
            "tooling-secret-bearing-locator",
            f"{artifact_id} source URL contains credentials, secret interpolation, or a secret query key",
            ARTIFACT_LOCK_PATH,
        )
        for source_url in as_list(platform.get("source_urls"))
        if isinstance(source_url, str) and has_secret_bearing_locator(source_url)
    ]


def _profile_link_failures(
    artifact_id: str,
    canonical_platform: str,
    locator_refs: set[str],
    profile_id: str,
    profiles: Mapping[str, Mapping[str, Any]],
) -> list[PolicyFailure]:
    profile = profiles.get(profile_id)
    if profile is None:
        return [failure("tooling-profile-missing", f"{artifact_id} names an unknown profile", ARTIFACT_LOCK_PATH)]
    failures: list[PolicyFailure] = []
    canonical = as_mapping(profile.get("platform")).get("canonical_id")
    if not isinstance(canonical, str) or normalize_platform_id(canonical) != canonical_platform:
        failures.append(
            failure("tooling-profile-platform", f"{artifact_id} profile platform does not match", ARTIFACT_LOCK_PATH)
        )
    if artifact_id not in string_set(profile.get("supported_artifact_ids")):
        failures.append(
            failure("tooling-profile-support", f"{artifact_id} is not admitted by its profile", ARTIFACT_LOCK_PATH)
        )
    locator_ids = {
        locator.get("locator_id")
        for locator in as_list(profile.get("locator_classes"))
        if isinstance(locator, Mapping) and isinstance(locator.get("locator_id"), str)
    }
    if not locator_refs <= locator_ids:
        failures.append(
            failure(
                "tooling-locator-profile",
                f"{artifact_id} source locator is not admitted by {profile_id}",
                ARTIFACT_LOCK_PATH,
            )
        )
    return failures


def _snapshot_manifest_failures(
    repo_root: Path,
    relative_path: object,
    digest: object,
    expected_size: object,
) -> list[PolicyFailure]:
    if not isinstance(relative_path, str) or not isinstance(expected_size, int):
        return []
    failures: list[PolicyFailure] = []
    source_path = safe_repo_path(repo_root, relative_path)
    if (
        source_path is None
        or not is_regular_repo_file(repo_root, relative_path)
        or source_path.stat().st_size > MAX_SCANNED_FILE_BYTES
    ):
        failures.append(
            failure(
                "tooling-source-snapshot-missing",
                "locked source snapshot is missing",
                relative_path,
            )
        )
    else:
        try:
            source_bytes = source_path.read_bytes()
        except OSError:
            failures.append(
                failure(
                    "tooling-source-snapshot-missing",
                    "locked source snapshot cannot be read",
                    relative_path,
                )
            )
        else:
            matches = len(source_bytes) == expected_size and hashlib.sha256(source_bytes).hexdigest() == digest
            if not matches:
                failures.append(
                    failure(
                        "tooling-source-snapshot-drift",
                        "locked source snapshot bytes differ",
                        relative_path,
                    )
                )
    return failures


def _manifest_entry_failures(
    repo_root: Path,
    artifact_id: str,
    artifact_class: object,
    manifest_name: str,
    entry: Mapping[str, Any],
    denied_digests: set[str],
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    digest = entry.get("sha256")
    relative_path = entry.get("path")
    if isinstance(relative_path, str) and not is_portable_relative_manifest_path(relative_path):
        failures.append(
            failure(
                "tooling-manifest-path",
                f"{artifact_id} manifest path is not a normalized portable relative path",
                ARTIFACT_LOCK_PATH,
            )
        )
    if isinstance(digest, str) and digest in denied_digests:
        failures.append(failure("tooling-digest-denied", f"{artifact_id} uses a denied digest", ARTIFACT_LOCK_PATH))
    if artifact_class == "source-snapshot" and manifest_name == "installed_manifest":
        failures.extend(_snapshot_manifest_failures(repo_root, relative_path, digest, entry.get("size")))
    return failures


def _manifest_failures(
    repo_root: Path,
    artifact_id: str,
    artifact_class: object,
    platform: Mapping[str, Any],
    denied_digests: set[str],
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for manifest_name in ("raw_manifest", "installed_manifest"):
        for entry in as_list(platform.get(manifest_name)):
            failures.extend(
                _manifest_entry_failures(
                    repo_root,
                    artifact_id,
                    artifact_class,
                    manifest_name,
                    as_mapping(entry),
                    denied_digests,
                )
            )
    return failures


def _platform_failures(
    repo_root: Path,
    artifact_id: str,
    artifact: Mapping[str, Any],
    platform: Mapping[str, Any],
    profiles: Mapping[str, Mapping[str, Any]],
    denied_digests: set[str],
) -> list[PolicyFailure]:
    failures = _source_url_failures(artifact_id, platform)
    platform_id = platform.get("platform_id")
    if not isinstance(platform_id, str):
        return failures
    canonical_platform = normalize_platform_id(platform_id)
    source = as_mapping(artifact.get("source"))
    for profile_id in string_set(platform.get("profile_ids")):
        failures.extend(
            _profile_link_failures(
                artifact_id,
                canonical_platform,
                string_set(source.get("locator_refs")),
                profile_id,
                profiles,
            )
        )
    failures.extend(
        _manifest_failures(
            repo_root,
            artifact_id,
            artifact.get("artifact_class"),
            platform,
            denied_digests,
        )
    )
    return failures


def _graph_failures(
    known_artifacts: set[str],
    dependency_graph: Mapping[str, set[str]],
    profiles: Mapping[str, Mapping[str, Any]],
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for profile_id, profile in profiles.items():
        unknown = string_set(profile.get("supported_artifact_ids")) - known_artifacts
        if unknown:
            failures.append(
                failure(
                    "tooling-profile-artifact",
                    f"{profile_id} admits {len(unknown)} unknown artifacts",
                    PROFILES_PATH,
                )
            )
    for artifact_id, dependencies in dependency_graph.items():
        failures.extend(
            failure(
                "tooling-dependency-missing",
                f"{artifact_id} depends on unknown artifact {dependency}",
                ARTIFACT_LOCK_PATH,
            )
            for dependency in dependencies - known_artifacts
        )
    if _has_dependency_cycle(known_artifacts, dependency_graph):
        failures.append(
            failure(
                "tooling-dependency-cycle",
                "artifact dependency graph contains a cycle",
                ARTIFACT_LOCK_PATH,
            )
        )
    return failures


def _has_dependency_cycle(known_artifacts: set[str], dependency_graph: Mapping[str, set[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(artifact_id: str) -> bool:
        cyclic = artifact_id in visiting
        if not cyclic and artifact_id not in visited:
            visiting.add(artifact_id)
            cyclic = any(
                visit(dependency)
                for dependency in dependency_graph.get(artifact_id, set())
                if dependency in known_artifacts
            )
            visiting.remove(artifact_id)
            visited.add(artifact_id)
        return cyclic

    return any(visit(artifact_id) for artifact_id in sorted(known_artifacts))


def _artifact_platform_failures(
    repo_root: Path,
    artifact_id: str,
    artifact: Mapping[str, Any],
    profiles: Mapping[str, Mapping[str, Any]],
    denied_digests: set[str],
    identities: set[tuple[str, str]],
    dependency_graph: dict[str, set[str]],
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for platform_value in as_list(artifact.get("platforms")):
        platform = as_mapping(platform_value)
        platform_id = platform.get("platform_id")
        if not isinstance(platform_id, str):
            continue
        identity = (artifact_id, normalize_platform_id(platform_id))
        if identity in identities:
            failures.append(
                failure(
                    "tooling-artifact-identity-duplicate",
                    f"duplicate canonical artifact/platform identity for {artifact_id}",
                    ARTIFACT_LOCK_PATH,
                )
            )
        identities.add(identity)
        dependency_graph[artifact_id].update(string_set(platform.get("dependencies")))
        failures.extend(_platform_failures(repo_root, artifact_id, artifact, platform, profiles, denied_digests))
    return failures


def artifact_failures(repo_root: Path, documents: Mapping[str, dict[str, Any]]) -> list[PolicyFailure]:
    """Validate artifact identities, profiles, manifests, policies, and dependencies."""

    lock = documents.get(ARTIFACT_LOCK_PATH)
    if lock is None:
        return []
    profiles, profile_failures = _profiles(documents.get(PROFILES_PATH) or {})
    policies, admission_failures = _policies(documents.get(ADMISSION_POLICY_PATH) or {})
    failures = [*walk_forbidden_keys(lock), *profile_failures, *admission_failures]
    denied_digests = string_set((documents.get(ADMISSION_POLICY_PATH) or {}).get("denied_digests"))
    artifact_ids: list[str] = []
    dependency_graph: dict[str, set[str]] = {}
    identities: set[tuple[str, str]] = set()
    for artifact_value in as_list(lock.get("artifacts")):
        artifact = as_mapping(artifact_value)
        artifact_id = artifact.get("artifact_id")
        if not isinstance(artifact_id, str):
            continue
        if artifact_id in artifact_ids:
            failures.append(failure("tooling-artifact-duplicate", "duplicate artifact id", ARTIFACT_LOCK_PATH))
        artifact_ids.append(artifact_id)
        dependency_graph.setdefault(artifact_id, set())
        failures.extend(_artifact_metadata_failures(artifact_id, artifact))
        failures.extend(_artifact_policy_failures(artifact_id, artifact, policies))
        failures.extend(
            _artifact_platform_failures(
                repo_root,
                artifact_id,
                artifact,
                profiles,
                denied_digests,
                identities,
                dependency_graph,
            )
        )
    known_artifacts = set(artifact_ids)
    failures.extend(_graph_failures(known_artifacts, dependency_graph, profiles))
    return failures
