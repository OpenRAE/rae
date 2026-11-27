"""Operational validation for the versioned SDL YAML source profile."""

from __future__ import annotations

import math
from pathlib import Path
from typing import cast

import yaml
from yaml.error import Mark
from yaml.nodes import MappingNode, Node, SequenceNode
from yaml.tokens import (
    AliasToken,
    BlockEndToken,
    BlockMappingStartToken,
    BlockSequenceStartToken,
    DirectiveToken,
    FlowMappingEndToken,
    FlowMappingStartToken,
    FlowSequenceEndToken,
    FlowSequenceStartToken,
    ScalarToken,
    TagToken,
    Token,
)

from ._errors import SDLParseDiagnostic, SDLParseError, SDLSourcePosition, SDLSourceRange
from ._source_profile import SDL_SOURCE_FORMAT, SDLMigrationPolicy, SDLParserLimits

EMPTY_CONTENT_MESSAGE = "SDL content is empty"
_UTF8_MESSAGE = "SDL source must be valid UTF-8 without unpaired surrogate code points."
_COLLECTION_START_TOKENS = (
    BlockMappingStartToken,
    BlockSequenceStartToken,
    FlowMappingStartToken,
    FlowSequenceStartToken,
)
_COLLECTION_END_TOKENS = (BlockEndToken, FlowMappingEndToken, FlowSequenceEndToken)


def prepare_content(content: str, *, path: Path | None) -> str:
    """Reject empty or non-UTF-8-compatible source without rewriting it."""
    if not content.strip():
        raise SDLParseError(EMPTY_CONTENT_MESSAGE, path=path)
    try:
        content.encode("utf-8")
    except UnicodeEncodeError as exc:
        diagnostic = _diagnostic_at_start(code="sdl.utf8", message=_UTF8_MESSAGE, path=path)
        raise SDLParseError(diagnostic.message, path=path, diagnostics=(diagnostic,)) from exc
    return content


def validate_source_format(source_format: str, *, path: Path | None) -> None:
    """Require the one implemented versioned source profile."""
    if source_format == SDL_SOURCE_FORMAT:
        return
    diagnostic = _diagnostic_at_start(
        code="sdl.source_format",
        message=f"Unsupported SDL source format '{source_format}'; expected '{SDL_SOURCE_FORMAT}'.",
        path=path,
    )
    raise SDLParseError(diagnostic.message, path=path, diagnostics=(diagnostic,))


def coerce_migration_policy(
    migration_policy: SDLMigrationPolicy | str,
    *,
    path: Path | None,
) -> SDLMigrationPolicy:
    """Validate the explicit migration-policy selector."""
    try:
        return SDLMigrationPolicy(migration_policy)
    except ValueError as exc:
        allowed = ", ".join(policy.value for policy in SDLMigrationPolicy)
        diagnostic = _diagnostic_at_start(
            code="sdl.migration_policy",
            message=f"Unsupported SDL migration policy '{migration_policy}'; expected one of: {allowed}.",
            path=path,
        )
        raise SDLParseError(diagnostic.message, path=path, diagnostics=(diagnostic,)) from exc


def validate_source_tokens(content: str, *, path: Path | None, limits: SDLParserLimits) -> None:
    """Enforce byte/scalar/alias limits and forbidden presentation tokens."""
    input_bytes = len(content.encode("utf-8"))
    if input_bytes > limits.max_input_bytes:
        _raise_source_limit(
            f"SDL source is {input_bytes} bytes; limit is {limits.max_input_bytes} bytes.",
            path=path,
        )

    aliases = 0
    depth = 0
    try:
        for token in yaml.scan(content, Loader=yaml.SafeLoader):
            depth = _nesting_depth(token, depth, path=path, limits=limits)
            if isinstance(token, AliasToken):
                aliases += 1
                if aliases > limits.max_aliases:
                    _raise_source_limit(
                        f"SDL source has more than {limits.max_aliases} alias occurrences.",
                        path=path,
                        token=token,
                    )
            elif isinstance(token, ScalarToken):
                scalar_bytes = _scalar_bytes(token, path=path)
                if scalar_bytes > limits.max_scalar_bytes:
                    _raise_source_limit(
                        f"SDL scalar is {scalar_bytes} bytes; limit is {limits.max_scalar_bytes} bytes.",
                        path=path,
                        token=token,
                    )
            elif isinstance(token, TagToken):
                _raise_token_diagnostic(
                    code="sdl.explicit_tag",
                    message="Explicit YAML tags are not valid sdl-yaml/v1 authoring syntax.",
                    path=path,
                    token=token,
                )
            elif isinstance(token, DirectiveToken):
                _raise_token_diagnostic(
                    code="sdl.directive",
                    message="YAML directives are not valid sdl-yaml/v1 authoring syntax.",
                    path=path,
                    token=token,
                )
    except SDLParseError:
        raise
    except yaml.YAMLError as exc:
        raise yaml_parse_error(exc, path=path) from exc


def _nesting_depth(token: Token, depth: int, *, path: Path | None, limits: SDLParserLimits) -> int:
    """Bound collection nesting before the recursive composer builds nodes.

    Each counted collection is a node at that depth or deeper, so this check refuses
    only source that the graph depth check refuses after composition.
    """
    if isinstance(token, _COLLECTION_END_TOKENS):
        return depth - 1
    if not isinstance(token, _COLLECTION_START_TOKENS):
        return depth
    if depth >= limits.max_depth:
        _raise_source_limit(f"SDL node depth exceeds {limits.max_depth}.", path=path, token=token)
    return depth + 1


def _scalar_bytes(token: ScalarToken, *, path: Path | None) -> int:
    try:
        return len(token.value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        # A double-quoted escape can produce an unpaired surrogate, which has no UTF-8 form.
        raise _token_error(code="sdl.utf8", message=_UTF8_MESSAGE, path=path, token=token) from exc


def validate_source_graph(root: Node, *, path: Path | None, limits: SDLParserLimits) -> None:
    """Bound unique nodes, expanded alias work, and effective depth."""
    _GraphMetrics(path=path, limits=limits).calculate(root, 1)


class _GraphMetrics:
    def __init__(self, *, path: Path | None, limits: SDLParserLimits) -> None:
        self.path = path
        self.limits = limits
        self.unique: set[int] = set()
        self.active: set[int] = set()
        self.memoized: dict[int, tuple[int, int]] = {}

    def calculate(self, node: Node, depth: int) -> tuple[int, int]:
        self._check_depth(node, depth)
        identity = id(node)
        if identity in self.active:
            return 0, 0
        self._track_unique(node, identity)
        cached = self.memoized.get(identity)
        if cached is not None:
            self._check_cached_depth(node, depth, cached)
            return cached
        self.active.add(identity)
        try:
            metrics = self._calculate_children(node, depth)
        finally:
            self.active.remove(identity)
        self.memoized[identity] = metrics
        return metrics

    def _calculate_children(self, node: Node, depth: int) -> tuple[int, int]:
        cost = 1
        height = 1
        for child in self._children(node):
            child_cost, child_height = self.calculate(child, depth + 1)
            cost += child_cost
            height = max(height, child_height + 1)
            _check_expanded_cost(cost, node=node, path=self.path, limits=self.limits)
        return cost, height

    @staticmethod
    def _children(node: Node) -> tuple[Node, ...]:
        if isinstance(node, MappingNode):
            return tuple(child for pair in node.value for child in pair)
        if isinstance(node, SequenceNode):
            return tuple(node.value)
        return ()

    def _track_unique(self, node: Node, identity: int) -> None:
        if identity in self.unique:
            return
        self.unique.add(identity)
        if len(self.unique) > self.limits.max_nodes:
            _raise_source_limit(
                f"SDL node graph has more than {self.limits.max_nodes} unique nodes.",
                path=self.path,
                node=node,
            )

    def _check_depth(self, node: Node, depth: int) -> None:
        if depth > self.limits.max_depth:
            _raise_source_limit(f"SDL node depth exceeds {self.limits.max_depth}.", path=self.path, node=node)

    def _check_cached_depth(self, node: Node, depth: int, metrics: tuple[int, int]) -> None:
        _cost, height = metrics
        if depth + height - 1 > self.limits.max_depth:
            _raise_source_limit(f"SDL node depth exceeds {self.limits.max_depth}.", path=self.path, node=node)


def _check_expanded_cost(
    cost: int,
    *,
    node: Node,
    path: Path | None,
    limits: SDLParserLimits,
) -> None:
    if cost > limits.max_expanded_nodes:
        _raise_source_limit(
            f"SDL alias-expanded work exceeds {limits.max_expanded_nodes} nodes.",
            path=path,
            node=node,
        )


def validate_constructed_domain(value: object, *, path: Path | None) -> None:
    """Reject values outside the string-keyed JSON data domain."""
    _ConstructedDomainValidator(path=path).visit(value)


class _ConstructedDomainValidator:
    _SCALAR_TYPES = frozenset({str, bool, int})

    def __init__(self, *, path: Path | None) -> None:
        self.path = path
        self.active: set[int] = set()
        self.visited: set[int] = set()

    def visit(self, item: object) -> None:
        item_type = type(item)
        if item is None or item_type in self._SCALAR_TYPES:
            return
        if item_type is float:
            self._visit_float(cast(float, item))
        elif item_type is list:
            self._visit_list(cast(list[object], item))
        elif item_type is dict:
            self._visit_dict(cast(dict[object, object], item))
        else:
            _raise_domain_error(
                f"YAML value type '{item_type.__name__}' is outside the SDL JSON domain.", path=self.path
            )

    def _visit_float(self, item: float) -> None:
        if not math.isfinite(item):
            _raise_domain_error("Non-finite numbers are not valid SDL values.", path=self.path)

    def _visit_list(self, item: list[object]) -> None:
        if not self._begin_container(item):
            return
        try:
            for child in item:
                self.visit(child)
        finally:
            self._finish_container(item)

    def _visit_dict(self, item: dict[object, object]) -> None:
        if not self._begin_container(item):
            return
        try:
            for key, child in item.items():
                if not isinstance(key, str):
                    _raise_domain_error("SDL mapping keys must construct as strings.", path=self.path)
                self.visit(child)
        finally:
            self._finish_container(item)

    def _begin_container(self, item: object) -> bool:
        identity = id(item)
        if identity in self.active or identity in self.visited:
            return False
        self.active.add(identity)
        return True

    def _finish_container(self, item: object) -> None:
        identity = id(item)
        self.active.remove(identity)
        self.visited.add(identity)


def _raise_domain_error(message: str, *, path: Path | None) -> None:
    diagnostic = _diagnostic_at_start(code="sdl.non_json_value", message=message, path=path)
    raise SDLParseError(message, path=path, diagnostics=(diagnostic,))


def _raise_source_limit(
    message: str,
    *,
    path: Path | None,
    token: Token | None = None,
    node: Node | None = None,
) -> None:
    if token is not None:
        primary_range = _range_from_marks(token.start_mark, token.end_mark)
    elif node is not None:
        primary_range = _range_from_node(node)
    else:
        primary_range = _start_range()
    diagnostic = SDLParseDiagnostic(
        code="sdl.source_limit",
        message=message,
        pointer="",
        primary_range=primary_range,
        source=str(path) if path is not None else None,
    )
    raise SDLParseError(message, path=path, diagnostics=(diagnostic,))


def _raise_token_diagnostic(*, code: str, message: str, path: Path | None, token: Token) -> None:
    raise _token_error(code=code, message=message, path=path, token=token)


def _token_error(*, code: str, message: str, path: Path | None, token: Token) -> SDLParseError:
    diagnostic = SDLParseDiagnostic(
        code=code,
        message=message,
        pointer="",
        primary_range=_range_from_marks(token.start_mark, token.end_mark),
        source=str(path) if path is not None else None,
    )
    return SDLParseError(message, path=path, diagnostics=(diagnostic,))


def _diagnostic_at_start(*, code: str, message: str, path: Path | None) -> SDLParseDiagnostic:
    return SDLParseDiagnostic(
        code=code,
        message=message,
        pointer="",
        primary_range=_start_range(),
        source=str(path) if path is not None else None,
    )


def _start_range() -> SDLSourceRange:
    position = SDLSourcePosition(1, 1)
    return SDLSourceRange(start=position, end=position)


def _range_from_marks(start: Mark, end: Mark) -> SDLSourceRange:
    return SDLSourceRange(
        start=SDLSourcePosition(start.line + 1, start.column + 1),
        end=SDLSourcePosition(end.line + 1, end.column + 1),
    )


def _range_from_node(node: Node) -> SDLSourceRange:
    return _range_from_marks(node.start_mark, node.end_mark)


def yaml_parse_error(error: yaml.YAMLError, *, path: Path | None) -> SDLParseError:
    """Translate a PyYAML error into the stable SDL parse envelope."""
    mark = getattr(error, "problem_mark", None)
    problem = getattr(error, "problem", None)
    if mark is None:
        return SDLParseError(f"Invalid YAML: {error}", path=path)
    position = SDLSourcePosition(mark.line + 1, mark.column + 1)
    diagnostic = SDLParseDiagnostic(
        code="sdl.parse",
        message=str(problem or error),
        pointer="",
        primary_range=SDLSourceRange(start=position, end=position),
        source=str(path) if path is not None else None,
    )
    return SDLParseError(f"Invalid YAML: {error}", path=path, diagnostics=(diagnostic,))
