"""Literal and runtime selector binding validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import (
    ARTIFACT_LOCK_PATH,
    SELECTOR_BINDINGS_PATH,
    as_list,
    as_mapping,
    failure,
    safe_text,
)


def _locked_versions(lock: Mapping[str, Any]) -> dict[object, object]:
    return {
        artifact.get("artifact_id"): artifact.get("version")
        for artifact in as_list(lock.get("artifacts"))
        if isinstance(artifact, Mapping)
        and isinstance(artifact.get("artifact_id"), str)
        and isinstance(artifact.get("version"), str)
    }


def _binding_failures(
    repo_root: Path,
    bindings: Mapping[str, Any],
    versions: Mapping[object, object],
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    seen_bindings: set[str] = set()
    for binding_value in as_list(bindings.get("bindings")):
        binding = as_mapping(binding_value)
        binding_id = binding.get("binding_id")
        if isinstance(binding_id, str) and binding_id in seen_bindings:
            failures.append(
                failure(
                    "tooling-selector-binding-duplicate",
                    "duplicate selector binding",
                    SELECTOR_BINDINGS_PATH,
                )
            )
        if isinstance(binding_id, str):
            seen_bindings.add(binding_id)
        selector = versions.get(binding.get("artifact_id"))
        if not isinstance(selector, str):
            failures.append(
                failure(
                    "tooling-selector-authority",
                    "selector binding names an unknown artifact",
                    SELECTOR_BINDINGS_PATH,
                )
            )
            continue
        failures.extend(_binding_consumer_failures(repo_root, binding, selector))
    return failures


def _binding_consumer_failures(
    repo_root: Path,
    binding: Mapping[str, Any],
    selector: str,
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for consumer_value in as_list(binding.get("consumers")):
        consumer = as_mapping(consumer_value)
        path = consumer.get("path")
        template = consumer.get("template")
        if not isinstance(path, str) or not isinstance(template, str):
            continue
        text = safe_text(repo_root, path)
        if text is None or template.replace("{selector}", selector) not in text:
            failures.append(
                failure(
                    "tooling-selector-drift",
                    "consumer selector differs from lock authority",
                    path,
                )
            )
    return failures


def selector_failures(
    repo_root: Path,
    documents: Mapping[str, dict[str, Any]],
    tracked_paths: Sequence[str],
) -> list[PolicyFailure]:
    """Check the retained literal projections of reviewed tool versions."""

    del tracked_paths
    lock = documents.get(ARTIFACT_LOCK_PATH)
    bindings = documents.get(SELECTOR_BINDINGS_PATH)
    if lock is None or bindings is None:
        return []
    return _binding_failures(repo_root, bindings, _locked_versions(lock))
