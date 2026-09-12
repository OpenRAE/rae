"""Closed GitHub workflow YAML parsing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.events import AliasEvent

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import YAML_SUFFIXES, failure, safe_text


class _ClosedWorkflowLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects aliases and duplicate mapping keys."""

    def compose_node(self, parent: object, index: object) -> yaml.Node:
        if self.check_event(AliasEvent):
            raise ConstructorError(
                None,
                None,
                "workflow aliases are not admitted",
                self.peek_event().start_mark,
            )
        return super().compose_node(parent, index)


def _construct_unique_mapping(
    loader: _ClosedWorkflowLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    loader.flatten_mapping(node)
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "unhashable key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_ClosedWorkflowLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def parse_yaml_mapping(repo_root: Path, path: str) -> tuple[Mapping[str, Any] | None, list[PolicyFailure]]:
    text = safe_text(repo_root, path)
    if text is None:
        return None, [
            failure(
                "tooling-action-scan",
                "workflow policy input could not be read safely",
                path,
            )
        ]
    try:
        document = yaml.load(text, Loader=_ClosedWorkflowLoader)  # noqa: S506
    except yaml.YAMLError:
        parse_failure = failure(
            "tooling-action-scan",
            "workflow policy input could not be parsed safely",
            path,
        )
    else:
        if isinstance(document, Mapping):
            return document, []
        parse_failure = failure(
            "tooling-action-scan",
            "workflow policy input must be a mapping",
            path,
        )
    return None, [parse_failure]


def workflow_documents(
    repo_root: Path,
    tracked_paths: Sequence[str],
) -> tuple[dict[str, Mapping[str, Any]], list[PolicyFailure]]:
    documents: dict[str, Mapping[str, Any]] = {}
    failures: list[PolicyFailure] = []
    paths = [
        path for path in tracked_paths if path.startswith(".github/workflows/") and Path(path).suffix in YAML_SUFFIXES
    ]
    for path in paths:
        document, parse_failures = parse_yaml_mapping(repo_root, path)
        failures.extend(parse_failures)
        if document is not None:
            documents[path] = document
    return documents, failures


__all__ = ("parse_yaml_mapping", "workflow_documents")
