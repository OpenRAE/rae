#!/usr/bin/env python3
# ruff: noqa: E402
"""Validate the closed, deterministic development artifact policy."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.policy.common import PolicyFailure, failures_to_json, load_bounded_json_object
from tools.tooling_artifact_policy_actions import action_failures
from tools.tooling_artifact_policy_artifacts import artifact_failures
from tools.tooling_artifact_policy_common import (
    ACTIONS_POLICY_PATH,
    ARTIFACT_LOCK_PATH,
    INVENTORY_COVERAGE_PATH,
    MAX_JSON_BYTES,
    POLICY_SCHEMAS,
    PROFILES_PATH,
    SELECTOR_BINDINGS_PATH,
    as_list,
    failure,
    load_documents,
    normalize_platform_id,
    string_set,
)
from tools.tooling_artifact_policy_discovery import tracked_python_scans
from tools.tooling_artifact_policy_inventory import inventory_failures
from tools.tooling_artifact_policy_selectors import selector_failures

__all__ = [
    "ACTIONS_POLICY_PATH",
    "ARTIFACT_LOCK_PATH",
    "INVENTORY_COVERAGE_PATH",
    "PROFILES_PATH",
    "SELECTOR_BINDINGS_PATH",
    "evaluate_tooling_artifact_policy",
    "normalize_platform_id",
    "select_tooling_artifact",
    "select_tooling_host_profile",
    "tooling_policy_sha256",
]


def _tracked_paths(repo_root: Path) -> list[str]:
    """Return repository paths from the staged/index view only."""

    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return sorted(path for path in result.stdout.decode("utf-8").split("\0") if path)


def _resolved_paths(
    repo_root: Path,
    tracked_paths: Sequence[str] | None,
) -> tuple[list[str], list[PolicyFailure]]:
    if tracked_paths is not None:
        return sorted(set(tracked_paths)), []
    try:
        return _tracked_paths(repo_root), []
    except (OSError, UnicodeError, subprocess.SubprocessError):
        return [], [
            failure(
                "tooling-git-scan",
                "tracked repository paths could not be enumerated",
            )
        ]


def evaluate_tooling_artifact_policy(
    repo_root: Path = REPO_ROOT,
    *,
    tracked_paths: Sequence[str] | None = None,
) -> list[PolicyFailure]:
    """Return deterministic policy failures without performing acquisition."""

    documents, failures = load_documents(repo_root)
    paths, path_failures = _resolved_paths(repo_root, tracked_paths)
    failures.extend(path_failures)
    python_scans = tracked_python_scans(repo_root, paths)
    failures.extend(artifact_failures(repo_root, documents))
    failures.extend(action_failures(repo_root, documents, paths))
    failures.extend(selector_failures(repo_root, documents, paths, python_scans))
    failures.extend(inventory_failures(repo_root, documents, paths, python_scans))
    if all(path in documents for path in POLICY_SCHEMAS):
        expected_policy_sha256 = tooling_policy_sha256(repo_root)
        profiles = documents[PROFILES_PATH]
        failures.extend(
            failure(
                "tooling-host-evidence-policy",
                "qualification evidence is not bound to the complete current tooling policy",
                PROFILES_PATH,
            )
            for record in as_list(profiles.get("qualification_records"))
            if not isinstance(record, Mapping) or record.get("policy_sha256") != expected_policy_sha256
        )
    return sorted(set(failures), key=lambda item: (item.path or "", item.rule_id, item.message))


def tooling_policy_sha256(repo_root: Path) -> str:
    """Hash every canonical policy authority without hashing result records."""

    digest = hashlib.sha256()
    authority_paths = sorted({*POLICY_SCHEMAS, *POLICY_SCHEMAS.values()})
    for relative_path in authority_paths:
        value = load_bounded_json_object(repo_root, relative_path, max_bytes=MAX_JSON_BYTES)
        if relative_path == PROFILES_PATH:
            value = {key: child for key, child in value.items() if key != "qualification_records"}
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        path_bytes = relative_path.encode()
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _selection_matches(
    lock: Mapping[str, Any],
    *,
    artifact_id: str,
    version: str,
    platform_id: str,
    profile_id: str,
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    matches: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    canonical_platform = normalize_platform_id(platform_id)
    for artifact in as_list(lock.get("artifacts")):
        if not isinstance(artifact, Mapping):
            continue
        if artifact.get("artifact_id") != artifact_id or artifact.get("version") != version:
            continue
        matches.extend(
            (artifact, platform)
            for platform in as_list(artifact.get("platforms"))
            if isinstance(platform, Mapping)
            and isinstance(platform.get("platform_id"), str)
            and normalize_platform_id(platform["platform_id"]) == canonical_platform
            and profile_id in string_set(platform.get("profile_ids"))
        )
    return matches


def select_tooling_artifact(
    repo_root: Path,
    *,
    artifact_id: str,
    version: str,
    platform_id: str,
    profile_id: str,
) -> dict[str, Any]:
    """Return one fully validated artifact/platform selection from the lock."""

    failures = evaluate_tooling_artifact_policy(repo_root)
    if failures:
        rendered = "\n".join(item.render() for item in failures)
        raise ValueError(f"development artifact policy is invalid:\n{rendered}")
    lock = load_bounded_json_object(repo_root, ARTIFACT_LOCK_PATH, max_bytes=MAX_JSON_BYTES)
    matches = _selection_matches(
        lock,
        artifact_id=artifact_id,
        version=version,
        platform_id=platform_id,
        profile_id=profile_id,
    )
    if len(matches) != 1:
        raise ValueError(
            "requested artifact version, platform, and profile must resolve to exactly one reviewed lock entry"
        )
    artifact, platform = matches[0]
    return {
        "artifact_id": artifact["artifact_id"],
        "artifact_class": artifact["artifact_class"],
        "version": artifact["version"],
        "source": artifact["source"],
        "platform": platform,
    }


def select_tooling_host_profile(repo_root: Path, *, host_profile_id: str) -> dict[str, Any]:
    """Return one fully validated host profile and its exact bootstrap selections."""

    failures = evaluate_tooling_artifact_policy(repo_root)
    if failures:
        rendered = "\n".join(item.render() for item in failures)
        raise ValueError(f"development artifact policy is invalid:\n{rendered}")
    profiles = load_bounded_json_object(repo_root, PROFILES_PATH, max_bytes=MAX_JSON_BYTES)
    lock = load_bounded_json_object(repo_root, ARTIFACT_LOCK_PATH, max_bytes=MAX_JSON_BYTES)
    hosts = [
        item
        for item in as_list(profiles.get("host_profiles"))
        if isinstance(item, Mapping) and item.get("host_profile_id") == host_profile_id
    ]
    if len(hosts) != 1:
        raise ValueError("requested host profile must resolve to exactly one reviewed entry")
    host = hosts[0]
    artifacts: list[dict[str, Any]] = []
    for artifact_id in sorted(string_set(host.get("bootstrap_payload_ids"))):
        artifact_matches = [
            item
            for item in as_list(lock.get("artifacts"))
            if isinstance(item, Mapping) and item.get("artifact_id") == artifact_id
        ]
        platform_matches = [
            (artifact, platform)
            for artifact in artifact_matches
            for platform in as_list(artifact.get("platforms"))
            if isinstance(platform, Mapping)
            and normalize_platform_id(str(platform.get("platform_id", "")))
            == normalize_platform_id(str(host.get("platform_id", "")))
            and (
                not string_set(platform.get("host_profile_ids"))
                or host_profile_id in string_set(platform.get("host_profile_ids"))
            )
        ]
        if len(platform_matches) != 1:
            raise ValueError(f"host profile must resolve exactly one reviewed {artifact_id} payload")
        artifact, platform = platform_matches[0]
        artifacts.append(
            {
                "artifact_id": artifact["artifact_id"],
                "artifact_class": artifact["artifact_class"],
                "version": artifact["version"],
                "support_level": artifact.get("support_level", "blocking"),
                "source": artifact["source"],
                "platform": platform,
            }
        )
    return {
        "host_profile": host,
        "artifacts": artifacts,
        "policy_sha256": tooling_policy_sha256(repo_root),
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--json", action="store_true", help="emit structured failures")
    parser.add_argument("--select-artifact")
    parser.add_argument("--version")
    parser.add_argument("--platform-id")
    parser.add_argument("--profile-id")
    parser.add_argument("--select-host-profile")
    return parser.parse_args(list(argv) if argv is not None else None)


def _selection_args(args: argparse.Namespace) -> tuple[object, object, object, object]:
    return args.select_artifact, args.version, args.platform_id, args.profile_id


def _run_selection(args: argparse.Namespace) -> int:
    selection_args = _selection_args(args)
    if not all(selection_args):
        print(
            "artifact selection requires artifact, version, platform, and profile",
            file=sys.stderr,
        )
        return 2
    try:
        selection = select_tooling_artifact(
            args.repo_root,
            artifact_id=args.select_artifact,
            version=args.version,
            platform_id=args.platform_id,
            profile_id=args.profile_id,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(selection, sort_keys=True, separators=(",", ":")))
    return 0


def _run_validation(args: argparse.Namespace) -> int:
    failures = evaluate_tooling_artifact_policy(args.repo_root)
    if not failures:
        return 0
    if args.json:
        print(failures_to_json(failures))
    else:
        for item in failures:
            print(item.render(), file=sys.stderr)
    return 1


def _run_host_selection(args: argparse.Namespace) -> int:
    try:
        selection = select_tooling_host_profile(args.repo_root, host_profile_id=args.select_host_profile)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(selection, sort_keys=True, separators=(",", ":")))
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.select_host_profile and any(_selection_args(args)):
        print("host and artifact selection modes cannot be combined", file=sys.stderr)
        return 2
    if args.select_host_profile:
        return _run_host_selection(args)
    return _run_selection(args) if any(_selection_args(args)) else _run_validation(args)


if __name__ == "__main__":
    raise SystemExit(main())
