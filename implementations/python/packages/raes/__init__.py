"""RAES Scenario Description Language (SDL).

A backend-agnostic scenario specification language with revision-pinned syntax
and translated-model ancestry in Open Cyber Range SDL plus RAES-native
extensions. The normative derivation boundary is recorded in
``contracts/provenance/sdl-lineage-ledger-v2.json``; this module does not claim
drop-in compatibility.
"""

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("raes")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = [
    "admit_instantiated_scenario",
    "admit_materialized_scenario",
    "admit_scenario_family",
    "MaterializedScenario",
    "MATERIALIZED_SDL_PROFILE",
    "canonical_materialized_sdl_bytes",
    "canonical_materialized_sdl_digest",
    "__version__",
    "canonical_instantiated_sdl_bytes",
    "canonical_instantiated_sdl_digest",
    "canonical_sdl_bytes",
    "canonical_sdl_digest",
    "ExpandedScenarioBindingTargetResolver",
    "build_declaration_index",
    "ReferencePurpose",
    "operating_scope_aliases",
    "INSTANTIATED_SNAPSHOT_PROFILE",
    "instantiate_scenario",
    "InstantiatedScenario",
    "InstantiatedScenarioSnapshot",
    "SDLCanonicalDigest",
    "SDL_CANONICAL_PROFILE",
    "SDLFormatResult",
    "format_sdl_source",
    "SDLRenderResult",
    "render_sdl_source",
    "load_sdl_fragment",
    "parse_sdl",
    "parse_sdl_file",
    "parse_sdl_sources",
    "ArtifactTransformationPolicy",
    "CanonicalArtifactComparison",
    "PortableContractTransformationResult",
    "RemoveSDLDeclarationRequest",
    "RenameSDLDeclarationRequest",
    "canonicalize_portable_contract",
    "compare_canonical_artifacts",
    "remove_sdl_declaration",
    "rename_sdl_declaration",
    "SDLTransformationResult",
    "SDLCandidateSynthesisResult",
    "synthesize_sdl_candidate",
    "select_scenario_family",
    "Scenario",
    "SDLError",
    "SDLImportError",
    "SDLImportErrorCode",
    "SDLInstantiationError",
    "SDLMigrationPolicy",
    "SDLParserLimits",
    "SDL_SOURCE_FORMAT",
    "SDLParseDiagnostic",
    "SDLParseError",
    "SDLSelectionError",
    "SDLSourcePosition",
    "SDLSourceRange",
    "SDLValidationError",
    "SDLValidationFinding",
    "validate_experiment_selection_against_family",
    "VARIABLE_TOKEN_PATTERN",
]


_LAZY_EXPORTS = {
    "raes._errors": (
        "SDLError",
        "SDLImportError",
        "SDLImportErrorCode",
        "SDLInstantiationError",
        "SDLParseDiagnostic",
        "SDLParseError",
        "SDLSelectionError",
        "SDLSourcePosition",
        "SDLSourceRange",
        "SDLValidationError",
        "SDLValidationFinding",
    ),
    "raes.canonical": (
        "INSTANTIATED_SNAPSHOT_PROFILE",
        "InstantiatedScenarioSnapshot",
        "MATERIALIZED_SDL_PROFILE",
        "SDLCanonicalDigest",
        "canonical_instantiated_sdl_bytes",
        "canonical_instantiated_sdl_digest",
        "canonical_materialized_sdl_bytes",
        "canonical_materialized_sdl_digest",
        "canonical_sdl_bytes",
        "canonical_sdl_digest",
    ),
    "raes.formatting": (
        "SDLFormatResult",
        "SDLRenderResult",
        "format_sdl_source",
        "render_sdl_source",
    ),
    "raes.candidate_synthesis": (
        "SDLCandidateSynthesisResult",
        "synthesize_sdl_candidate",
    ),
    "raes._source_profile": (
        "SDLMigrationPolicy",
        "SDLParserLimits",
        "SDL_CANONICAL_PROFILE",
        "SDL_SOURCE_FORMAT",
    ),
    "raes._base": ("VARIABLE_TOKEN_PATTERN",),
    "raes._declarations": ("build_declaration_index",),
    "raes._reference_targetability": ("ReferencePurpose",),
    "raes._operating_scope_index": ("operating_scope_aliases",),
    "raes.instantiate": (
        "admit_instantiated_scenario",
        "instantiate_scenario",
    ),
    "raes.materialization": (
        "MaterializedScenario",
        "admit_materialized_scenario",
    ),
    "raes.experiment_selection": ("validate_experiment_selection_against_family",),
    "raes.family_admission": ("admit_scenario_family",),
    "raes.selected_scenario": (
        "ExpandedScenarioBindingTargetResolver",
        "select_scenario_family",
    ),
    "raes.parser": (
        "load_sdl_fragment",
        "parse_sdl",
        "parse_sdl_file",
        "parse_sdl_sources",
    ),
    "raes.transformations": (
        "ArtifactTransformationPolicy",
        "CanonicalArtifactComparison",
        "PortableContractTransformationResult",
        "RemoveSDLDeclarationRequest",
        "RenameSDLDeclarationRequest",
        "SDLTransformationResult",
        "canonicalize_portable_contract",
        "compare_canonical_artifacts",
        "remove_sdl_declaration",
        "rename_sdl_declaration",
    ),
    "raes.scenario": (
        "InstantiatedScenario",
        "Scenario",
    ),
}
_EXPORT_MODULES = {name: module for module, names in _LAZY_EXPORTS.items() for name in names}


def __getattr__(name: str):
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(module_name), name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
