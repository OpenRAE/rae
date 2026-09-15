"""Safe, source-marked YAML composition for the SDL authoring boundary."""

from __future__ import annotations

from pathlib import Path

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode

from ._errors import (
    SDLParseDiagnostic,
    SDLParseError,
    SDLSourceRange,
)
from ._mapping_key_analyzer import _MappingAnalyzer
from ._mapping_scopes import MappingScope
from ._source_profile import (
    DEFAULT_SOURCE_PARSE_OPTIONS,
    SDLMigrationPolicy,
    SDLSourceParseOptions,
    install_yaml_12_core_resolvers,
)
from ._source_validation import (
    EMPTY_CONTENT_MESSAGE,
    coerce_migration_policy,
    prepare_content,
    validate_constructed_domain,
    validate_source_format,
    validate_source_graph,
    validate_source_tokens,
    yaml_parse_error,
)


class _SDLSafeLoader(yaml.SafeLoader):
    """SafeLoader with an isolated YAML 1.2 Core implicit resolver table."""


install_yaml_12_core_resolvers(_SDLSafeLoader)


def load_sdl_yaml(
    content: str,
    *,
    path: Path | None = None,
    scope: MappingScope = MappingScope.STRUCTURAL,
    base_pointer: str = "",
    source_options: SDLSourceParseOptions = DEFAULT_SOURCE_PARSE_OPTIONS,
    source_diagnostics: list[SDLParseDiagnostic] | None = None,
    source_ranges: dict[str, SDLSourceRange] | None = None,
) -> object:
    """Validate and safely construct one SDL YAML document or fragment."""
    prepared = prepare_content(content, path=path)
    policy = coerce_migration_policy(source_options.migration_policy, path=path)
    validate_source_format(source_options.source_format, path=path)
    validate_source_tokens(prepared, path=path, limits=source_options.limits)
    loader: _SDLSafeLoader | None = None
    try:
        loader = _SDLSafeLoader(prepared)
        root = loader.get_single_node()
        if root is None:
            raise SDLParseError(EMPTY_CONTENT_MESSAGE, path=path)
        validate_source_graph(root, path=path, limits=source_options.limits)
        _validate_mapping_keys(
            root,
            path=path,
            scope=scope,
            base_pointer=base_pointer,
            migration_policy=policy,
            source_diagnostics=source_diagnostics,
            source_ranges=source_ranges,
        )
        constructed = loader.construct_document(root)
        validate_constructed_domain(constructed, path=path)
        if source_options.required_semantic_revision is not None and (
            not isinstance(constructed, dict)
            or constructed.get("semantic_revision") != source_options.required_semantic_revision
        ):
            raise SDLParseError("Imported source must carry the selected semantic revision.", path=path)
        return constructed
    except SDLParseError:
        raise
    except yaml.YAMLError as exc:
        raise yaml_parse_error(exc, path=path) from exc
    finally:
        if loader is not None:
            loader.dispose()


def compose_sdl_yaml(
    content: str,
    *,
    path: Path | None = None,
    scope: MappingScope = MappingScope.STRUCTURAL,
    base_pointer: str = "",
    source_options: SDLSourceParseOptions = DEFAULT_SOURCE_PARSE_OPTIONS,
    source_diagnostics: list[SDLParseDiagnostic] | None = None,
    source_ranges: dict[str, SDLSourceRange] | None = None,
) -> Node:
    """Compose and key-validate SDL YAML while retaining source nodes."""
    prepared = prepare_content(content, path=path)
    policy = coerce_migration_policy(source_options.migration_policy, path=path)
    validate_source_format(source_options.source_format, path=path)
    validate_source_tokens(prepared, path=path, limits=source_options.limits)
    loader: _SDLSafeLoader | None = None
    try:
        loader = _SDLSafeLoader(prepared)
        root = loader.get_single_node()
        if root is None:
            raise SDLParseError(EMPTY_CONTENT_MESSAGE, path=path)
        validate_source_graph(root, path=path, limits=source_options.limits)
        _validate_mapping_keys(
            root,
            path=path,
            scope=scope,
            base_pointer=base_pointer,
            migration_policy=policy,
            source_diagnostics=source_diagnostics,
            source_ranges=source_ranges,
        )
        return root
    except SDLParseError:
        raise
    except yaml.YAMLError as exc:
        raise yaml_parse_error(exc, path=path) from exc
    finally:
        if loader is not None:
            loader.dispose()


def _is_materialized_mapping(root: Node, scope: MappingScope, base_pointer: str) -> bool:
    return (
        not base_pointer
        and scope is MappingScope.STRUCTURAL
        and isinstance(root, MappingNode)
        and any(isinstance(key, ScalarNode) and key.value == "materialization_provenance" for key, _value in root.value)
    )


def _validate_mapping_keys(
    root: Node,
    *,
    path: Path | None,
    scope: MappingScope,
    base_pointer: str,
    migration_policy: SDLMigrationPolicy,
    source_diagnostics: list[SDLParseDiagnostic] | None,
    source_ranges: dict[str, SDLSourceRange] | None,
) -> None:
    diagnostics = _MappingAnalyzer(
        migration_policy=migration_policy,
        path=path,
        source_ranges=source_ranges,
        materialized=_is_materialized_mapping(root, scope, base_pointer),
    ).analyze(
        root,
        scope=scope,
        base_tokens=_decode_pointer(base_pointer),
    )
    warnings = tuple(item for item in diagnostics if item.severity == "warning")
    errors = tuple(item for item in diagnostics if item.severity != "warning")
    if source_diagnostics is not None:
        source_diagnostics.extend(warnings)
    if not errors:
        return
    rendered: list[str] = []
    for item in errors:
        location = item.primary_range.start
        detail = (
            f"[{item.code}] {item.pointer or '/'} at line {location.line}, column {location.column}: {item.message}"
        )
        if item.related_range is not None:
            related = item.related_range.start
            detail += f" First declaration at line {related.line}, column {related.column}."
        rendered.append(detail)
    details = "SDL mapping-key validation failed:\n  " + "\n  ".join(rendered)
    raise SDLParseError(details, path=path, diagnostics=errors)


def _decode_pointer(pointer: str) -> list[str]:
    if not pointer:
        return []
    if not pointer.startswith("/"):
        raise ValueError("base_pointer must be an RFC 6901 pointer")
    return [token.replace("~1", "/").replace("~0", "~") for token in pointer[1:].split("/")]
