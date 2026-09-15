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
    "SDLInstantiationError",
    "SDLMigrationPolicy",
    "SDLParserLimits",
    "SDL_SOURCE_FORMAT",
    "SDLParseDiagnostic",
    "SDLParseError",
    "SDLSourcePosition",
    "SDLSourceRange",
    "SDLValidationError",
    "validate_experiment_selection_against_family",
    "VARIABLE_TOKEN_PATTERN",
]


def __getattr__(name: str):
    if name in {
        "SDLError",
        "SDLInstantiationError",
        "SDLParseDiagnostic",
        "SDLParseError",
        "SDLSourcePosition",
        "SDLSourceRange",
        "SDLValidationError",
    }:
        module = import_module("raes._errors")
    elif name in {
        "canonical_materialized_sdl_bytes",
        "canonical_materialized_sdl_digest",
        "MATERIALIZED_SDL_PROFILE",
        "canonical_instantiated_sdl_bytes",
        "canonical_instantiated_sdl_digest",
        "canonical_sdl_bytes",
        "canonical_sdl_digest",
        "INSTANTIATED_SNAPSHOT_PROFILE",
        "InstantiatedScenarioSnapshot",
        "SDLCanonicalDigest",
    }:
        module = import_module("raes.canonical")
    elif name in {"format_sdl_source", "SDLFormatResult", "render_sdl_source", "SDLRenderResult"}:
        module = import_module("raes.formatting")
    elif name in {"SDLCandidateSynthesisResult", "synthesize_sdl_candidate"}:
        module = import_module("raes.candidate_synthesis")
    elif name in {
        "SDL_CANONICAL_PROFILE",
        "SDLMigrationPolicy",
        "SDLParserLimits",
        "SDL_SOURCE_FORMAT",
    }:
        module = import_module("raes._source_profile")
    elif name == "VARIABLE_TOKEN_PATTERN":
        module = import_module("raes._base")
    elif name == "build_declaration_index":
        module = import_module("raes._declarations")
    elif name in {"admit_instantiated_scenario", "instantiate_scenario"}:
        module = import_module("raes.instantiate")
    elif name in {"admit_materialized_scenario", "MaterializedScenario"}:
        module = import_module("raes.materialization")
    elif name == "validate_experiment_selection_against_family":
        module = import_module("raes.experiment_selection")
    elif name in {"ExpandedScenarioBindingTargetResolver", "select_scenario_family"}:
        module = import_module("raes.selected_scenario")
    elif name in {"load_sdl_fragment", "parse_sdl", "parse_sdl_file"}:
        module = import_module("raes.parser")
    elif name in {
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
    }:
        module = import_module("raes.transformations")
    elif name in {"InstantiatedScenario", "Scenario"}:
        module = import_module("raes.scenario")
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
