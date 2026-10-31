"""SDL parser — canonical YAML loading and typed normalization.

Provides ``parse_sdl()`` as the primary entry point. Handles:
- Exact canonical structural fields by default
- Explicitly requested migration of legacy field spellings
- Shorthand expansion (``source: "pkg"`` → ``{name: "pkg", version: "*"}``)
"""

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Unpack, cast

from pydantic import ValidationError

from ._base import contains_variable_token, is_variable_ref
from ._composition_budget import CompositionTraversal, ParsePrivateOptions
from ._declaration_sources import attach_declaration_sources, semantic_source_diagnostics
from ._errors import (
    SDLImportError,
    SDLImportErrorCode,
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
    DEFAULT_SOURCE_PARSE_OPTIONS,
    SDL_SOURCE_FORMAT,
    SDLMigrationPolicy,
    SDLParserLimits,
    SDLSourceParseOptions,
)
from ._source_validation import _raise_source_limit
from ._supplied_sources import SuppliedSources
from ._yaml_loader import SDLSourceLocations, load_sdl_yaml
from .materialization import MaterializedScenario
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
    return decode_sdl_source(raw_bytes, path=path, limits=limits)


def decode_sdl_source(
    raw_bytes: bytes,
    *,
    path: Path,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
) -> SDLSourceDocument:
    """Decode already-captured source bytes with the byte limit and the canonical diagnostics."""

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


def _normalize_child(value: object, key: object, is_hashmap: bool, child_is_hashmap: bool) -> object:
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


def _names_mapping(names: list[Any], *, node: object, field: str, path: Path | None) -> dict[Any, str]:
    """Expand a node list shorthand: [a, b] → {a: '', b: ''}; a nested list or mapping is not a name."""
    if not all(isinstance(name, Hashable) for name in names):
        raise SDLParseError(f"Node '{node}' {field} list must contain only names", path=path)
    return dict.fromkeys(names, "")


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


# Scopes where "source" is a plain string reference, NOT a Source package.
_SOURCE_SKIP_SECTIONS = frozenset({"relationships", "agents", "imports", "runtime"})


def _expand_sources_scoped(obj: object, *, is_hashmap: bool = False, skip: bool = False) -> object:
    """Expand ``source`` shorthands outside the scopes where ``source`` is a plain reference."""
    if isinstance(obj, list):
        return [_expand_sources_scoped(item, is_hashmap=is_hashmap, skip=skip) for item in obj]
    if not isinstance(obj, dict):
        return obj
    result = {}
    for k, v in obj.items():
        if is_hashmap:
            result[k] = _expand_sources_scoped(v, skip=skip)
        elif k == "source" and not skip:
            result[k] = _expand_source(v)
        else:
            child_skip = skip or k in _SOURCE_SKIP_SECTIONS
            result[k] = _expand_sources_scoped(v, is_hashmap=_child_is_hashmap_field(k, v), skip=child_skip)
    return result


def _expand_node_shorthands(node_name: object, node_data: dict[str, Any], *, path: Path | None) -> None:
    """Expand the roles and the feature, condition and inject list shorthands of one node."""
    if isinstance(node_data.get("roles"), dict):
        node_data["roles"] = _expand_roles(node_data["roles"])
    # G6: features/conditions/injects as list -> dict with empty role
    for field in ("features", "conditions", "injects"):
        if isinstance(node_data.get(field), list):
            node_data[field] = _names_mapping(node_data[field], node=node_name, field=field, path=path)


def _expand_shorthands(data: dict[str, Any], *, path: Path | None = None) -> dict[str, Any]:
    """Apply all shorthand expansions to normalized data."""
    data = _expand_sources_scoped(data)
    if isinstance(data.get("infrastructure"), dict):
        data["infrastructure"] = _expand_infrastructure(data["infrastructure"])
    nodes = data.get("nodes")
    if isinstance(nodes, dict):
        for node_name, node_data in nodes.items():
            if isinstance(node_data, dict):
                _expand_node_shorthands(node_name, node_data, path=path)
    return data


def parse_sdl(
    content: str,
    path: Path | None = None,
    *,
    skip_semantic_validation: bool = False,
    source_format: str = SDL_SOURCE_FORMAT,
    migration_policy: SDLMigrationPolicy | str = SDLMigrationPolicy.REJECT,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
    **private_options: Unpack[ParsePrivateOptions],
) -> Scenario | ExpandedScenario | MaterializedScenario:
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
    source_key_ranges: dict[str, SDLSourceRange] = {}
    declaration_sources = {}
    data = _load_normalized_data(
        content,
        path=path,
        source_options=SDLSourceParseOptions(
            source_format=source_format, migration_policy=migration_policy, limits=limits
        ),
        source_diagnostics=source_diagnostics,
        source_ranges=source_ranges,
        source_key_ranges=source_key_ranges,
    )
    _reject_removed_scoring_sections(data, path=path)
    traversal = private_options.get("_traversal")
    if "materialization_provenance" in data and traversal is not None and traversal.sources is not None:
        raise SDLImportError(
            SDLImportErrorCode.PHASE_REFUSED, "A supplied root must be an authored scenario.", path=path
        )
    if "materialization_provenance" in data:
        scenario_cls = MaterializedScenario
    elif data.get("imports"):
        if path is None:
            raise SDLParseError(
                "SDL imports require file-backed parsing via parse_sdl_file()",
                path=path,
            )
        from .composition import expand_sdl_modules

        # Public authoring checks must run before expansion introduces generated
        # identities, including legitimate private references owned by modules.
        try:
            Scenario.model_validate(data)
        except ValidationError as exc:
            raise _model_parse_error(exc, path=path, source_ranges=source_ranges) from exc

        data, _expansion_provenance = expand_sdl_modules(
            data,
            path=path,
            source_format=source_format,
            migration_policy=migration_policy,
            limits=limits,
            source_diagnostics=source_diagnostics,
            _traversal=traversal,
            _declaration_sources=declaration_sources,
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
    attach_declaration_sources(scenario, content, path, source_ranges, source_key_ranges, declaration_sources)

    # Semantic validation
    if not skip_semantic_validation or isinstance(scenario, MaterializedScenario):
        validator = SemanticValidator(scenario)
        try:
            validator.validate()
        except SDLValidationError as e:
            e.path = path
            semantic_source_diagnostics(e, scenario)
            raise
        scenario._set_advisories(validator.warnings)
        scenario._set_semantic_validated(True)
    else:
        scenario._set_advisories([])
        scenario._set_semantic_validated(False)
    return scenario


def parse_sdl_sources(
    sources: Mapping[str, bytes],
    root: str,
    *,
    source_format: str = SDL_SOURCE_FORMAT,
    migration_policy: SDLMigrationPolicy | str = SDLMigrationPolicy.REJECT,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
) -> Scenario | ExpandedScenario:
    """Parse untrusted SDL from caller-supplied bytes (ADR-119).

    The operation reads only ``sources``. It never reads a file, the
    environment or the network, and it never reads ``raes-trust.yaml``. Each
    import at each depth must be ``local:``, must have a ``sha256:`` digest pin
    and must match exactly one record in the ``raes.lock.json`` entry beside its
    importing document.

    Args:
        sources: Canonical POSIX relative paths mapped to exact source bytes.
            The operation copies each value one time.
        root: The path of the root SDL document in ``sources``.
        source_format: Versioned concrete-syntax profile identifier.
        migration_policy: Strict rejection or explicit acceptance of recognized
            legacy field/merge syntax.
        limits: Source, lock and composition resource limits.

    Returns:
        A semantically validated ``Scenario``, or ``ExpandedScenario`` when the
        root has imports.

    Raises:
        SDLImportError: An import or a supplied path was refused; ``code`` names why.
        SDLParseError: The YAML or the structure of a document is not valid.
        SDLValidationError: Semantic validation found errors.
    """
    supplied = SuppliedSources.capture(sources)
    root_path, root_bytes = supplied.root(root)
    document = decode_sdl_source(root_bytes, path=root_path, limits=limits)
    # parse_sdl refuses a materialized root when the traversal carries supplied sources.
    return cast(
        Scenario | ExpandedScenario,
        parse_sdl(
            document.text,
            path=root_path,
            source_format=source_format,
            migration_policy=migration_policy,
            limits=limits,
            _traversal=CompositionTraversal.supplied_root(limits, supplied),
        ),
    )


def parse_sdl_file(path: Path, **kwargs: Any) -> Scenario | ExpandedScenario | MaterializedScenario:
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
    source_options: SDLSourceParseOptions = DEFAULT_SOURCE_PARSE_OPTIONS,
    source_diagnostics: list[SDLParseDiagnostic] | None = None,
    source_ranges: dict[str, SDLSourceRange] | None = None,
    source_key_ranges: dict[str, SDLSourceRange] | None = None,
) -> dict[str, Any]:
    raw = load_sdl_yaml(
        content,
        path=path,
        source_options=source_options,
        source_diagnostics=source_diagnostics,
        source_locations=SDLSourceLocations(source_ranges, source_key_ranges),
    )

    if not isinstance(raw, dict):
        raise SDLParseError("SDL must be a YAML mapping (not a scalar or list)", path=path)

    from ._source_profile import PROGRESSIVE_SDL_REVISION

    if "semantic_revision" in raw and raw["semantic_revision"] != PROGRESSIVE_SDL_REVISION:
        raise SDLParseError(
            "This parser requires the current semantic revision; explicitly migrate older source.", path=path
        )

    data = _normalize_keys(raw)
    if any(not isinstance(key, str) for key in data):
        raise SDLParseError("SDL top-level mapping keys must be strings", path=path)
    _reject_variable_mapping_keys(data)
    data = _expand_shorthands(data, path=path)
    migrate_legacy_vm_nodes(
        data,
        path=path,
        migration_policy=source_options.migration_policy,
        source_diagnostics=source_diagnostics,
        source_ranges=source_ranges,
    )
    return data
