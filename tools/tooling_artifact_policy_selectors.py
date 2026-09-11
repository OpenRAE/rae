"""Literal and runtime selector binding validation."""

from __future__ import annotations

import re
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
from tools.tooling_artifact_policy_discovery import PythonScan


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


def _runtime_declarations(bindings: Mapping[str, Any]) -> tuple[dict[str, set[str]], list[PolicyFailure]]:
    declared: dict[str, set[str]] = {}
    failures: list[PolicyFailure] = []
    for selection_value in as_list(bindings.get("runtime_selections")):
        selection = as_mapping(selection_value)
        artifact_id = selection.get("artifact_id")
        if not isinstance(artifact_id, str):
            continue
        if artifact_id in declared:
            failures.append(
                failure(
                    "tooling-runtime-selection-duplicate",
                    "artifact has more than one runtime selection binding",
                    SELECTOR_BINDINGS_PATH,
                )
            )
        declared.setdefault(artifact_id, set()).update(
            path for path in as_list(selection.get("consumers")) if isinstance(path, str)
        )
    return declared, failures


def _runtime_observations(
    tracked_paths: Sequence[str],
    python_scans: Mapping[str, PythonScan | None],
) -> tuple[dict[str, set[str]], list[PolicyFailure]]:
    observed: dict[str, set[str]] = {}
    failures: list[PolicyFailure] = []
    for path in tracked_paths:
        if Path(path).suffix != ".py":
            continue
        scan = python_scans.get(path)
        if scan is None:
            failures.append(
                failure(
                    "tooling-runtime-selection-scan",
                    "tracked Python source could not be read safely",
                    path,
                )
            )
            continue
        if not scan.selection_calls_valid:
            failures.append(
                failure(
                    "tooling-runtime-selection-drift",
                    "selection call must use a literal artifact id and all reviewed dimensions",
                    path,
                )
            )
        for artifact_id in scan.selected_artifact_ids:
            observed.setdefault(artifact_id, set()).add(path)
    return observed, failures


def _runtime_selection_failures(
    lock: Mapping[str, Any],
    bindings: Mapping[str, Any],
    tracked_paths: Sequence[str],
    python_scans: Mapping[str, PythonScan | None],
) -> list[PolicyFailure]:
    locked_ids = {
        artifact.get("artifact_id")
        for artifact in as_list(lock.get("artifacts"))
        if isinstance(artifact, Mapping) and isinstance(artifact.get("artifact_id"), str)
    }
    declared, failures = _runtime_declarations(bindings)
    observed, observation_failures = _runtime_observations(tracked_paths, python_scans)
    failures.extend(observation_failures)
    failures.extend(
        failure(
            "tooling-runtime-selection-drift",
            f"{artifact_id} runtime selection consumers differ from tracked calls",
            SELECTOR_BINDINGS_PATH,
        )
        for artifact_id in sorted(set(declared) | set(observed))
        if declared.get(artifact_id, set()) != observed.get(artifact_id, set())
    )
    if set(declared) != locked_ids or set(observed) != locked_ids:
        failures.append(
            failure(
                "tooling-runtime-selection-coverage",
                "every locked artifact must have exactly one runtime selection binding",
                SELECTOR_BINDINGS_PATH,
            )
        )
    return failures


def _tracked_literal_failure(
    repo_root: Path,
    tracked_paths: Sequence[str],
    tracked_literal: Mapping[str, Any],
) -> list[PolicyFailure]:
    values = (
        tracked_literal.get("selector_id"),
        tracked_literal.get("authority_path"),
        tracked_literal.get("authority_template"),
        tracked_literal.get("consumer_prefix"),
    )
    if not all(isinstance(value, str) for value in values):
        return []
    selector_id, authority_path, authority_template, consumer_prefix = values
    assert isinstance(selector_id, str)
    assert isinstance(authority_path, str)
    assert isinstance(authority_template, str)
    assert isinstance(consumer_prefix, str)
    prefix, marker, suffix = authority_template.partition("{selector}")
    authority_text = safe_text(repo_root, authority_path)
    authority_failure = None
    if authority_text is None or not marker:
        authority_failure = failure(
            "tooling-selector-authority",
            f"{selector_id} authority cannot be read",
            authority_path,
        )
        selectors: set[str] = set()
    else:
        selectors = set(re.findall(re.escape(prefix) + r"([^\r\n]+?)" + re.escape(suffix), authority_text))
        if len(selectors) != 1:
            authority_failure = failure(
                "tooling-selector-authority",
                f"{selector_id} authority must resolve to exactly one selector",
                authority_path,
            )
    if authority_failure is not None:
        return [authority_failure]
    return _literal_consumer_failures(repo_root, tracked_paths, selector_id, selectors.pop(), consumer_prefix)


def _literal_consumer_failures(
    repo_root: Path,
    tracked_paths: Sequence[str],
    selector_id: str,
    selector: str,
    consumer_prefix: str,
) -> list[PolicyFailure]:
    consumer_pattern = re.compile(re.escape(consumer_prefix) + r"([A-Za-z0-9._+-]+)")
    suffixes = {".bash", ".md", ".py", ".sh", ".toml", ".yaml", ".yml"}
    failures: list[PolicyFailure] = []
    for path in tracked_paths:
        if Path(path).suffix not in suffixes and Path(path).name != "Makefile":
            continue
        text = safe_text(repo_root, path)
        if text is not None and any(value != selector for value in consumer_pattern.findall(text)):
            failures.append(
                failure(
                    "tooling-selector-drift",
                    f"{selector_id} literal differs from its authority",
                    path,
                )
            )
    return failures


def _tracked_literal_failures(
    repo_root: Path,
    bindings: Mapping[str, Any],
    tracked_paths: Sequence[str],
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    seen_ids: set[str] = set()
    for literal_value in as_list(bindings.get("tracked_literals")):
        literal = as_mapping(literal_value)
        selector_id = literal.get("selector_id")
        if isinstance(selector_id, str) and selector_id in seen_ids:
            failures.append(
                failure(
                    "tooling-selector-binding-duplicate",
                    "duplicate tracked literal binding",
                    SELECTOR_BINDINGS_PATH,
                )
            )
        if isinstance(selector_id, str):
            seen_ids.add(selector_id)
        failures.extend(_tracked_literal_failure(repo_root, tracked_paths, literal))
    return failures


def selector_failures(
    repo_root: Path,
    documents: Mapping[str, dict[str, Any]],
    tracked_paths: Sequence[str],
    python_scans: Mapping[str, PythonScan | None],
) -> list[PolicyFailure]:
    """Validate fixed literals and every tracked runtime lock-selection call."""

    lock = documents.get(ARTIFACT_LOCK_PATH)
    bindings = documents.get(SELECTOR_BINDINGS_PATH)
    if lock is None or bindings is None:
        return []
    failures = _binding_failures(repo_root, bindings, _locked_versions(lock))
    failures.extend(_runtime_selection_failures(lock, bindings, tracked_paths, python_scans))
    failures.extend(_tracked_literal_failures(repo_root, bindings, tracked_paths))
    return failures
