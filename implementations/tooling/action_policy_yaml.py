"""Closed GitHub workflow YAML parsing."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError, SafeConstructor
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
    if not isinstance(node, yaml.MappingNode):
        # An explicit !!map tag can name a scalar or a sequence node.
        raise ConstructorError(
            None,
            None,
            f"expected a mapping node, but found {node.id}",
            node.start_mark,
        )
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

# The safe scalar constructors raise these built-in exceptions, not a YAMLError, for a
# value that they cannot build: an integer beyond the interpreter digit limit, an
# impossible date or time, an empty tagged number, an unknown !!bool word or a
# !!timestamp value that is not a timestamp.
_SCALAR_CONSTRUCTION_FAILURES: tuple[tuple[str, Callable[..., object], tuple[type[Exception], ...]], ...] = (
    ("tag:yaml.org,2002:int", SafeConstructor.construct_yaml_int, (ValueError, IndexError)),
    ("tag:yaml.org,2002:float", SafeConstructor.construct_yaml_float, (ValueError, IndexError)),
    ("tag:yaml.org,2002:bool", SafeConstructor.construct_yaml_bool, (KeyError,)),
    ("tag:yaml.org,2002:timestamp", SafeConstructor.construct_yaml_timestamp, (ValueError, AttributeError)),
)


def _refusing_scalar_constructor(
    constructor: Callable[..., object],
    construction_failures: tuple[type[Exception], ...],
) -> Callable[[_ClosedWorkflowLoader, yaml.Node], object]:
    """Report a scalar that the safe constructor cannot build as a constructor error."""

    def construct(loader: _ClosedWorkflowLoader, node: yaml.Node) -> object:
        try:
            return constructor(loader, node)
        except construction_failures as exc:
            raise ConstructorError(None, None, "scalar value cannot be constructed", node.start_mark) from exc

    return construct


for _tag, _constructor, _construction_failures in _SCALAR_CONSTRUCTION_FAILURES:
    _ClosedWorkflowLoader.add_constructor(_tag, _refusing_scalar_constructor(_constructor, _construction_failures))


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
    except (yaml.YAMLError, RecursionError):
        # Without a depth limit, the recursive composer stops at the interpreter recursion limit.
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
