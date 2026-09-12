"""SDL parser — canonical YAML loading and typed normalization.

Provides ``parse_sdl()`` as the primary entry point. Handles:
- Exact canonical structural fields by default
- Explicitly requested migration of legacy field spellings
- Shorthand expansion (``source: "pkg"`` → ``{name: "pkg", version: "*"}``)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from ._base import contains_variable_token, is_variable_ref
from ._errors import (
    SDLParseDiagnostic,
    SDLParseError,
    SDLSourcePosition,
    SDLSourceRange,
    SDLValidationError,
)
from ._legacy_node_migration import migrate_legacy_vm_nodes
from ._mapping_scopes import (
    HASHMAP_SECTIONS,
    NESTED_HASHMAP_FIELDS,
    PROFILE_JSON_FIELDS,
    MappingScope,
    is_literal_map_field,
    normalize_field_key,
)
from ._model_diagnostics import (
    _dedupe_source_diagnostics,
    _model_parse_error,
)
from ._source_profile import (
    DEFAULT_PARSER_LIMITS,
    SDL_SOURCE_FORMAT,
    SDLMigrationPolicy,
    SDLParserLimits,
    SDLSourceParseOptions,
)
from ._source_validation import _raise_source_limit
from ._yaml_loader import load_sdl_yaml
from .scenario import ExpandedScenario, Scenario
from .validator import SemanticValidator

# Top-level sections that are HashMaps of user-defined identifiers.
# Keys inside these are scenario-author names (e.g., "web-server")
# and must NOT be transformed.
_HASHMAP_SECTIONS = HASHMAP_SECTIONS

# Fields within struct models that are also HashMaps of user-defined keys.
_NESTED_HASHMAP_FIELDS = NESTED_HASHMAP_FIELDS


@dataclass(frozen=True)
class SDLSourceDocument:
    """Exact bounded bytes and decoded text for one SDL source document."""

    raw_bytes: bytes
    text: str


def read_sdl_source(
    path: Path,
    *,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
) -> SDLSourceDocument:
    """Read one SDL source with the byte limit enforced before decoding."""

    if not path.exists():
        raise FileNotFoundError(f"SDL file not found: {path}")
    with path.open("rb") as source:
        raw_bytes = source.read(limits.max_input_bytes + 1)
    return _source_document_from_bytes(raw_bytes, path=path, limits=limits)


def _source_document_from_bytes(
    raw_bytes: bytes,
    *,
    path: Path,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
) -> SDLSourceDocument:
    """Decode already-captured source bytes with the canonical diagnostics."""

    if len(raw_bytes) > limits.max_input_bytes:
        _raise_source_limit(
            f"SDL source exceeds the byte limit of {limits.max_input_bytes} bytes.",
            path=path,
        )
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        position = SDLSourcePosition(1, 1)
        diagnostic = SDLParseDiagnostic(
            code="sdl.utf8",
            message="SDL source must be valid UTF-8.",
            pointer="",
            primary_range=SDLSourceRange(start=position, end=position),
            source=str(path),
        )
        raise SDLParseError(diagnostic.message, path=path, diagnostics=(diagnostic,)) from exc
    return SDLSourceDocument(raw_bytes=raw_bytes, text=text)


def _child_is_hashmap_field(key: str, value: Any) -> bool:
    """Return whether the children of ``key`` are user-defined hashmap keys."""
    return is_literal_map_field(
        key,
        value_is_mapping=isinstance(value, dict),
        value_is_sequence=isinstance(value, list),
    )


def _normalize_field_key(k: Any) -> Any:
    """Return the normalized representation of a structural field key."""
    if isinstance(k, str):
        return normalize_field_key(k)
    return k


def _normalize_keys(data: Any, is_hashmap: bool = False) -> Any:
    """Normalize dict keys for Pydantic field matching.

    Pydantic struct field keys are lowercased with hyphens converted to
    underscores. User-defined HashMap keys (node names, feature names,
    entity names, etc.) are preserved as-is so cross-references remain
    consistent.
    """
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if is_hashmap:
                # This key is a user-defined identifier — preserve it
                norm_k = k
                child_is_hashmap = False
            else:
                norm_k = _normalize_field_key(k)
                # Check if this field's children are user-defined HashMap keys
                child_key = norm_k if isinstance(norm_k, str) else str(norm_k)
                child_is_hashmap = _child_is_hashmap_field(child_key, v)
            result[norm_k] = _normalize_child(v, norm_k, is_hashmap, child_is_hashmap)
        return result
    if isinstance(data, list):
        # List items inherit the hashmap flag — if the parent dict had
        # user-defined keys, list items within it do too.
        return [_normalize_keys(item, is_hashmap=is_hashmap) for item in data]
    return data


def _normalize_child(value: Any, key: Any, is_hashmap: bool, child_is_hashmap: bool) -> Any:
    if not is_hashmap and key in PROFILE_JSON_FIELDS:
        return value
    return _normalize_keys(value, is_hashmap=child_is_hashmap)


def load_sdl_fragment(
    content: str,
    *,
    mapping_keys: Literal["structural", "literal"] = "structural",
    base_pointer: str = "",
    source_format: str = SDL_SOURCE_FORMAT,
    migration_policy: SDLMigrationPolicy | str = SDLMigrationPolicy.REJECT,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
    source_diagnostics: list[SDLParseDiagnostic] | None = None,
) -> object:
    """Safely load an SDL YAML fragment with the canonical key preflight."""
    return load_sdl_yaml(
        content,
        scope=MappingScope(mapping_keys),
        base_pointer=base_pointer,
        source_options=SDLSourceParseOptions(
            source_format=source_format,
            migration_policy=migration_policy,
            limits=limits,
        ),
        source_diagnostics=source_diagnostics,
    )


def _reject_variable_mapping_keys(
    data: Any,
    *,
    path: str = "",
    is_hashmap: bool = False,
) -> None:
    """Reject ``${var}`` placeholders in symbol-defining mapping keys."""
    if isinstance(data, dict):
        for k, v in data.items():
            if is_hashmap and contains_variable_token(k):
                key_path = f"{path}.{k}" if path else str(k)
                raise SDLParseError(f"Variable placeholders are not allowed in user-defined mapping keys: '{key_path}'")

            child_key = k if isinstance(k, str) else str(k)
            child_path = f"{path}.{child_key}" if path else child_key
            child_is_hashmap = False if is_hashmap else _child_is_hashmap_field(child_key, v)
            _reject_variable_mapping_keys(
                v,
                path=child_path,
                is_hashmap=child_is_hashmap,
            )
        return

    if isinstance(data, list):
        for index, item in enumerate(data):
            child_path = f"{path}[{index}]"
            _reject_variable_mapping_keys(
                item,
                path=child_path,
                is_hashmap=is_hashmap,
            )


def _expand_source(value: Any) -> Any:
    """Expand shorthand source: 'pkg-name' → {name: 'pkg-name', version: '*'}."""
    if isinstance(value, str):
        return {"name": value, "version": "*"}
    return value


def _expand_infrastructure(infra: dict[str, Any]) -> dict[str, Any]:
    """Expand infrastructure shorthand: {node: 3} → {node: {count: 3}}."""
    result = {}
    for name, value in infra.items():
        if isinstance(value, int) or is_variable_ref(value):
            result[name] = {"count": value}
        else:
            result[name] = value
    return result


def _expand_roles(roles: dict[str, Any]) -> dict[str, Any]:
    """Expand role shorthand: {admin: 'username'} → {admin: {username: 'username'}}."""
    result = {}
    for name, value in roles.items():
        if isinstance(value, str):
            result[name] = {"username": value}
        else:
            result[name] = value
    return result


# OCR scoring sections removed from the SDL by ADR-073. Detected up front so
# authors get a migration pointer instead of a raw "extra fields" error.
_REMOVED_SCORING_SECTIONS = ("metrics", "evaluations", "tlos", "goals")


def _reject_removed_scoring_sections(data: dict[str, Any], *, path: Path | None) -> None:
    """Raise a migration-pointing error when a removed scoring section is used."""
    present = [section for section in _REMOVED_SCORING_SECTIONS if section in data]
    if not present:
        return
    raise SDLParseError(
        "SDL scoring sections "
        f"{', '.join(present)} were removed from the language by ADR-073. "
        "Express objective success through backend-neutral propositions and "
        "'objectives.*.success.assertions', and route graded scoring, reward, "
        "and evaluation outputs to the experiment/evaluator plane "
        "(ADR-055/064/069). The CybORG 'agents.*.reward_calculator' label was "
        "removed for the same reason.",
        path=path,
    )


def _expand_shorthands(data: dict[str, Any]) -> dict[str, Any]:
    """Apply all shorthand expansions to normalized data."""
    # Scopes where "source" is a plain string reference, NOT a Source package.
    _SOURCE_SKIP_SECTIONS = frozenset({"relationships", "agents", "imports", "runtime"})

    def expand_sources_scoped(
        obj: Any,
        *,
        is_hashmap: bool = False,
        skip: bool = False,
    ) -> Any:
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                if is_hashmap:
                    result[k] = expand_sources_scoped(
                        v,
                        is_hashmap=False,
                        skip=skip,
                    )
                    continue

                child_skip = skip or k in _SOURCE_SKIP_SECTIONS
                child_is_hashmap = _child_is_hashmap_field(k, v)

                if k == "source" and not skip:
                    result[k] = _expand_source(v)
                else:
                    result[k] = expand_sources_scoped(
                        v,
                        is_hashmap=child_is_hashmap,
                        skip=child_skip,
                    )
            return result
        if isinstance(obj, list):
            return [
                expand_sources_scoped(
                    item,
                    is_hashmap=is_hashmap,
                    skip=skip,
                )
                for item in obj
            ]
        return obj

    data = expand_sources_scoped(data)

    # Expand infrastructure shorthand
    if "infrastructure" in data and isinstance(data["infrastructure"], dict):
        data["infrastructure"] = _expand_infrastructure(data["infrastructure"])

    # Expand roles and feature/condition/inject list shorthands within nodes
    if "nodes" in data and isinstance(data["nodes"], dict):
        for node_data in data["nodes"].values():
            if isinstance(node_data, dict):
                if "roles" in node_data:
                    node_data["roles"] = _expand_roles(node_data["roles"])
                # G6: features/conditions/injects as list -> dict with empty role
                for field in ("features", "conditions", "injects"):
                    if field in node_data and isinstance(node_data[field], list):
                        node_data[field] = {name: "" for name in node_data[field]}

    return data


def parse_sdl(
    content: str,
    path: Path | None = None,
    *,
    skip_semantic_validation: bool = False,
    source_format: str = SDL_SOURCE_FORMAT,
    migration_policy: SDLMigrationPolicy | str = SDLMigrationPolicy.REJECT,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
) -> Scenario | ExpandedScenario:
    """Parse SDL YAML into a normalized or expanded authoring object.

    Handles SDL documents with ``name`` at the top level. Runs
    structural validation (Pydantic) and semantic validation
    (cross-references, cycles, etc.).

    Args:
        content: Raw YAML string.
        path: Optional file path for error messages.
        skip_semantic_validation: If True, only run Pydantic structural
            validation (useful for partial scenarios during development).
        source_format: Versioned concrete-syntax profile identifier.
        migration_policy: Strict rejection or explicit acceptance of recognized
            legacy field/merge syntax with retained diagnostics.
        limits: Source and alias-processing resource limits.

    Returns:
        A ``Scenario``, or ``ExpandedScenario`` when file-backed module imports
        are present. Unless explicitly skipped, semantic validation has run.

    Raises:
        SDLParseError: If YAML parsing fails or the data isn't a dict.
        SDLValidationError: If semantic validation finds errors.
    """
    source_diagnostics: list[SDLParseDiagnostic] = []
    source_ranges: dict[str, SDLSourceRange] = {}
    data = _load_normalized_data(
        content,
        path=path,
        source_format=source_format,
        migration_policy=migration_policy,
        limits=limits,
        source_diagnostics=source_diagnostics,
        source_ranges=source_ranges,
    )
    _reject_removed_scoring_sections(data, path=path)
    if data.get("imports"):
        if path is None:
            raise SDLParseError(
                "SDL imports require file-backed parsing via parse_sdl_file()",
                path=path,
            )
        from .composition import expand_sdl_modules

        data, _expansion_provenance = expand_sdl_modules(
            data,
            path=path,
            source_format=source_format,
            migration_policy=migration_policy,
            limits=limits,
            source_diagnostics=source_diagnostics,
        )
        scenario_cls = ExpandedScenario
    else:
        scenario_cls = Scenario

    # Construct the Pydantic model (structural validation)
    try:
        scenario = scenario_cls(**data)
    except ValidationError as e:
        raise _model_parse_error(e, path=path, source_ranges=source_ranges) from e

    source_diagnostics = _dedupe_source_diagnostics(source_diagnostics)

    scenario._set_source_diagnostics(source_diagnostics)

    # Semantic validation
    if not skip_semantic_validation:
        validator = SemanticValidator(scenario)
        try:
            validator.validate()
        except SDLValidationError as e:
            e.path = path
            raise
        scenario._set_advisories(validator.warnings)
        scenario._set_semantic_validated(True)
    else:
        scenario._set_advisories([])
        scenario._set_semantic_validated(False)
    return scenario


def parse_sdl_file(path: Path, **kwargs: Any) -> Scenario | ExpandedScenario:
    """Parse an SDL file into a normalized or expanded authoring object.

    Convenience wrapper around ``parse_sdl()`` that reads from a file.
    """
    limits = kwargs.get("limits", DEFAULT_PARSER_LIMITS)
    document = read_sdl_source(path, limits=limits)
    return parse_sdl(document.text, path=path, **kwargs)


def _load_normalized_data(
    content: str,
    *,
    path: Path | None = None,
    source_format: str = SDL_SOURCE_FORMAT,
    migration_policy: SDLMigrationPolicy | str = SDLMigrationPolicy.REJECT,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
    source_diagnostics: list[SDLParseDiagnostic] | None = None,
    source_ranges: dict[str, SDLSourceRange] | None = None,
) -> dict[str, Any]:
    raw = load_sdl_yaml(
        content,
        path=path,
        source_options=SDLSourceParseOptions(
            source_format=source_format,
            migration_policy=migration_policy,
            limits=limits,
        ),
        source_diagnostics=source_diagnostics,
        source_ranges=source_ranges,
    )

    if not isinstance(raw, dict):
        raise SDLParseError("SDL must be a YAML mapping (not a scalar or list)", path=path)

    data = _normalize_keys(raw)
    if any(not isinstance(key, str) for key in data):
        raise SDLParseError("SDL top-level mapping keys must be strings", path=path)
    _reject_variable_mapping_keys(data)
    data = _expand_shorthands(data)
    migrate_legacy_vm_nodes(
        data,
        path=path,
        migration_policy=migration_policy,
        source_diagnostics=source_diagnostics,
        source_ranges=source_ranges,
    )
    return data
