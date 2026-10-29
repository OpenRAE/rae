"""Import-expansion orchestration and the canonical payload rewrite coordinator.

``expand_sdl_modules`` is the single import-expansion coordinator;
``_rewrite_payload_with_symbols`` is the one pure rewrite seam shared by module
composition and semantic transformations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict, Unpack

from pydantic import ValidationError

from .._composition_budget import CompositionBudget, CompositionTraversal
from .._declaration_sources import (
    DeclarationSource,
    namespace_declaration_sources,
)
from .._errors import SDLInstantiationError, SDLParseDiagnostic, SDLParseError
from .._model_diagnostics import _import_declarations, _model_parse_error
from .._module_symbols import FORWARDING_AGENTS_SECTION
from .._module_symbols import HASHMAP_SECTIONS as _HASHMAP_SECTIONS
from .._module_symbols import (
    symbol_index as _symbol_index,
)
from .._source_profile import (
    DEFAULT_PARSER_LIMITS,
    SDL_SOURCE_FORMAT,
    SDLMigrationPolicy,
    SDLParserLimits,
    SDLSourceParseOptions,
)
from ..instantiate import _bind_scenario_content
from ..module_registry import (
    Lockfile,
    TrustPolicy,
    _VerifiedSourceBundle,
    load_lockfile,
    load_trust_policy,
    resolve_import,
)
from ..phase_contracts import (
    CapabilityConstraint,
    ExpansionProvenance,
    ExplicitnessProvenanceRecord,
    ParameterDerivation,
    ResolvedImportProvenance,
)
from ..realization_designation import (
    RealizationConstraintRecord,
    RealizationDesignation,
    RealizationDesignationRecord,
    constraint_records,
    designation_records,
)
from ..scenario import ExpandedScenario, ImportDecl, ModuleDescriptor, ScenarioContent
from ._augmentation import merge_augmentation_scope, rewrite_augmentation_scope
from ._behavior import (
    _behavior_reference_maps,
    _reject_ambiguous_unit_behavior_refs,
    _rewrite_agent_sections,
    _rewrite_behavior_sections,
)
from ._execution_policy import merge_execution_policy, rewrite_execution_policy
from ._import_admission import admit_import_source
from ._profiles import rewrite_profile_selections
from ._provenance import import_provenance_additions as _import_provenance_additions
from ._references import _rewrite_variable_tokens
from ._sections import (
    _rewrite_account_and_domain_sections,
    _rewrite_content_sections,
    _rewrite_deployment_sections,
    _rewrite_foundational_sections,
    _rewrite_narrative_sections,
    _rewrite_observation_boundaries,
    _rewrite_proposition_sections,
    _rewrite_relationship_sections,
    _rewrite_stateful_resources,
    _validate_descriptor_exports,
)
from ._terminal import (
    _namespace_declaration_keys,
    _namespace_forwarding_agents,
    _rewrite_terminal_sections,
    _strip_composition_fields,
)


def _rewrite_payload_with_symbols(
    payload: dict[str, Any],
    *,
    symbols: dict[str, dict[str, str] | set[str]],
    namespace: str = "",
    strip_composition_fields: bool = False,
) -> dict[str, Any]:
    """Rewrite declarations and references through one canonical symbol map.

    Module composition and semantic transformations share this implementation
    so new reference-bearing SDL fields cannot drift between the two surfaces.
    The caller supplies an isolated ``model_dump`` payload; this function never
    receives or mutates a caller-owned scenario model.
    """

    namespaced = dict(payload)
    tool_affordance_refs, _ = _behavior_reference_maps(namespaced, symbols, namespace)
    rewrite_profile_selections(namespaced, symbols)
    _rewrite_foundational_sections(namespaced, symbols)
    _rewrite_proposition_sections(namespaced, symbols)
    _rewrite_narrative_sections(namespaced, symbols)
    _rewrite_observation_boundaries(namespaced, symbols, tool_affordance_refs)
    _rewrite_content_sections(namespaced, symbols)
    _rewrite_stateful_resources(namespaced, symbols)
    _rewrite_account_and_domain_sections(namespaced, symbols)
    _rewrite_deployment_sections(namespaced, symbols)
    _rewrite_relationship_sections(namespaced, symbols)
    _rewrite_agent_sections(namespaced, symbols)
    _rewrite_behavior_sections(namespaced, symbols)
    _rewrite_terminal_sections(namespaced, symbols, tool_affordance_refs)
    rewrite_augmentation_scope(namespaced, symbols, namespace)
    rewrite_execution_policy(namespaced, symbols, namespace)

    pinned_assets = namespaced.pop("control_context_assets", None)
    rewritten = _rewrite_variable_tokens(namespaced, symbols["variables"])
    if pinned_assets is not None:
        rewritten["control_context_assets"] = pinned_assets
    if not isinstance(rewritten, dict):
        raise TypeError("variable rewriting returned a non-object payload")
    namespaced = rewritten
    _namespace_declaration_keys(namespaced, symbols, namespace)
    _namespace_forwarding_agents(namespaced, symbols, namespace)
    if strip_composition_fields:
        _strip_composition_fields(namespaced)
    return namespaced


def _namespace_payload(
    payload: dict[str, Any],
    imported: ScenarioContent,
    namespace: str,
    descriptor: ModuleDescriptor,
) -> dict[str, Any]:
    _validate_descriptor_exports(imported, descriptor)
    symbols = _symbol_index(
        imported,
        namespace=namespace,
        descriptor=descriptor,
        restrict_to_descriptor=True,
    )
    return _rewrite_payload_with_symbols(
        payload,
        symbols=symbols,
        namespace=namespace,
        strip_composition_fields=True,
    )


def _merge_sections(
    root: dict[str, Any],
    incoming: dict[str, Any],
    *,
    path: Path,
) -> dict[str, Any]:
    merged = dict(root)
    merge_augmentation_scope(merged, incoming)
    merge_execution_policy(merged, incoming)
    for section_name in _HASHMAP_SECTIONS:
        current = dict(merged.get(section_name, {}))
        additions = dict(incoming.get(section_name, {}))
        collisions = sorted(set(current).intersection(additions))
        if collisions:
            raise SDLParseError(f"Import from {path} collides on {section_name}: {', '.join(collisions)}")
        current.update(additions)
        merged[section_name] = current
    current_agents = list(merged.get(FORWARDING_AGENTS_SECTION, []))
    incoming_agents = list(incoming.get(FORWARDING_AGENTS_SECTION, []))
    current_ids = {agent.get("forwarding_agent_id") for agent in current_agents if isinstance(agent, dict)}
    incoming_ids = {agent.get("forwarding_agent_id") for agent in incoming_agents if isinstance(agent, dict)}
    collisions = sorted(identifier for identifier in current_ids.intersection(incoming_ids) if identifier)
    if collisions:
        raise SDLParseError(f"Import from {path} collides on {FORWARDING_AGENTS_SECTION}: {', '.join(collisions)}")
    merged[FORWARDING_AGENTS_SECTION] = [*current_agents, *incoming_agents]
    merged["imports"] = []
    return merged


@dataclass(frozen=True)
class _ImportContext:
    """Invariant per-document context threaded through each import expansion."""

    path: Path
    resolved_path: Path
    child_traversal: CompositionTraversal
    budget: CompositionBudget
    lockfile: Lockfile | None
    trust_policy: TrustPolicy
    source_format: str
    migration_policy: SDLMigrationPolicy | str
    limits: SDLParserLimits
    source_diagnostics: list[SDLParseDiagnostic] | None
    verified_sources: _VerifiedSourceBundle | None
    registry_base_dir: Path
    semantic_revision: str | None
    declaration_sources: dict[str, DeclarationSource]


@dataclass(frozen=True)
class _ExpansionContext:
    """Private traversal and trust state carried across recursive expansion."""

    traversal: CompositionTraversal | None = None
    verified_sources: _VerifiedSourceBundle | None = None
    inherited_lockfile: Lockfile | None = None
    inherited_trust_policy: TrustPolicy | None = None
    registry_base_dir: Path | None = None
    declaration_sources: dict[str, DeclarationSource] | None = None


class _ExpansionPrivateOptions(TypedDict, total=False):
    """Typed compatibility keywords for private recursive expansion state."""

    _context: _ExpansionContext
    _traversal: CompositionTraversal | None
    _verified_sources: _VerifiedSourceBundle | None
    _inherited_lockfile: Lockfile | None
    _inherited_trust_policy: TrustPolicy | None
    _registry_base_dir: Path | None
    _declaration_sources: dict[str, DeclarationSource]


def _expansion_context(options: _ExpansionPrivateOptions) -> _ExpansionContext:
    current = options.get("_context")
    if current is not None:
        return current
    return _ExpansionContext(
        traversal=options.get("_traversal"),
        verified_sources=options.get("_verified_sources"),
        inherited_lockfile=options.get("_inherited_lockfile"),
        inherited_trust_policy=options.get("_inherited_trust_policy"),
        registry_base_dir=options.get("_registry_base_dir"),
        declaration_sources=options.get("_declaration_sources"),
    )


def _expand_one_import(
    import_decl: ImportDecl,
    merged: dict[str, Any],
    context: _ImportContext,
) -> tuple[
    dict[str, Any],
    list[ResolvedImportProvenance],
    list[CapabilityConstraint],
    list[ParameterDerivation],
    list[ExplicitnessProvenanceRecord],
    list[RealizationDesignationRecord],
    list[RealizationConstraintRecord],
]:
    """Resolve, expand, namespace, and merge a single import; return provenance additions."""

    context.budget.add_import(path=context.path)
    if "__private." in import_decl.namespace:
        raise SDLParseError(
            "Import namespaces may not contain the reserved '__private' segment",
            path=context.path,
        )
    source_options = SDLSourceParseOptions(
        source_format=context.source_format,
        migration_policy=context.migration_policy,
        limits=context.limits,
        required_semantic_revision=context.semantic_revision,
    )
    resolved_import = resolve_import(
        import_decl,
        base_dir=context.resolved_path.parent,
        lockfile=context.lockfile,
        trust_policy=context.trust_policy,
        source_options=source_options,
        source_diagnostics=context.source_diagnostics,
        verified_sources=context.verified_sources,
        _registry_base_dir=context.registry_base_dir,
        _local_sources_only=context.child_traversal.local_sources_only,
    )
    import_path = resolved_import.root_file
    imported_raw, source_ranges, local_sources = admit_import_source(
        resolved_import, source_options, context.source_diagnostics
    )
    inner_sources: dict[str, DeclarationSource] = {}
    if imported_raw.get("semantic_revision") != context.semantic_revision:
        raise SDLParseError("Imported SDL semantic revision must match the root revision.", path=import_path)
    imported_expanded, inner_provenance = expand_sdl_modules(
        imported_raw,
        path=import_path,
        source_format=context.source_format,
        migration_policy=context.migration_policy,
        limits=context.limits,
        source_diagnostics=context.source_diagnostics,
        _context=_ExpansionContext(
            traversal=context.child_traversal,
            verified_sources=resolved_import.verified_sources,
            inherited_lockfile=context.lockfile,
            inherited_trust_policy=context.trust_policy,
            registry_base_dir=context.registry_base_dir if resolved_import.verified_sources is not None else None,
            declaration_sources=inner_sources,
        ),
    )
    try:
        imported_scenario = ExpandedScenario.model_validate(imported_expanded)
        bound = _bind_scenario_content(
            imported_scenario,
            import_decl.parameters,
            preserve_variation_variables=True,
        )
    except ValidationError as exc:
        raise _model_parse_error(exc, path=import_path, source_ranges=source_ranges) from exc
    except SDLInstantiationError as exc:
        raise SDLParseError(str(exc), path=import_path) from exc
    namespace = import_decl.namespace
    descriptor = resolved_import.module_descriptor
    symbols = _symbol_index(
        bound.content,
        namespace=namespace,
        descriptor=descriptor,
        restrict_to_descriptor=True,
    )

    _reject_ambiguous_unit_behavior_refs(bound.content, path=import_path)
    namespaced_payload = _namespace_payload(
        bound.content.model_dump(mode="python", by_alias=True),
        bound.content,
        namespace,
        descriptor,
    )
    context.budget.check_namespaces(namespaced_payload, path=import_path)
    context.declaration_sources.update(
        namespace_declaration_sources(
            {**inner_sources, **local_sources},
            bound.content,
            ExpandedScenario.model_validate(namespaced_payload),
            symbols,
            namespace,
        )
    )
    merged = _merge_sections(merged, namespaced_payload, path=import_path)

    additions = _import_provenance_additions(
        resolved_import, import_decl, bound, inner_provenance, symbols, path=context.path
    )
    return (merged, *additions)


def _workspace_policy(
    resolved_path: Path, context: _ExpansionContext, traversal: CompositionTraversal
) -> tuple[Lockfile | None, TrustPolicy]:
    if context.verified_sources is not None:
        return context.inherited_lockfile, context.inherited_trust_policy or TrustPolicy()
    lockfile = load_lockfile(resolved_path.parent)
    trust_policy = load_trust_policy(resolved_path.parent)
    if traversal.local_sources_only:
        # Editor path mode never fetches, so trust cannot authorize a registry request.
        trust_policy = trust_policy.model_copy(update={"registries": {}})
    return lockfile, trust_policy


def expand_sdl_modules(
    data: dict[str, Any],
    *,
    path: Path,
    source_format: str = SDL_SOURCE_FORMAT,
    migration_policy: SDLMigrationPolicy | str = SDLMigrationPolicy.REJECT,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
    source_diagnostics: list[SDLParseDiagnostic] | None = None,
    **private_options: Unpack[_ExpansionPrivateOptions],
) -> tuple[dict[str, Any], ExpansionProvenance]:
    """Expand trusted imports into executable content and portable evidence."""

    expansion_context = _expansion_context(private_options)
    traversal = expansion_context.traversal or CompositionTraversal(
        seen=frozenset(),
        budget=CompositionBudget(limits),
        depth=0,
    )
    budget = traversal.budget
    budget.check_depth(traversal.depth, path=path)
    budget.add_document(data, path=path)
    resolved_path = (
        expansion_context.verified_sources.identity_path(path)
        if expansion_context.verified_sources is not None
        else path.resolve()
    )
    if resolved_path in traversal.seen:
        raise SDLParseError(f"Import cycle detected at {resolved_path}", path=path)
    child_traversal = traversal.descend_from(resolved_path)
    registry_base_dir = (
        resolved_path.parent if expansion_context.registry_base_dir is None else expansion_context.registry_base_dir
    )

    merged = dict(data)
    merged.setdefault("imports", [])
    merged.setdefault("version", "*")
    import_records: list[ResolvedImportProvenance] = []
    capability_constraints: list[CapabilityConstraint] = []
    parameter_derivations: list[ParameterDerivation] = []
    explicitness_records: list[ExplicitnessProvenanceRecord] = []
    realization_records: list[RealizationDesignationRecord] = []
    realization_constraints: list[RealizationConstraintRecord] = []
    raw_designation = merged.get("realization")
    if raw_designation is not None:
        try:
            typed_designation = RealizationDesignation.model_validate(raw_designation)
            realization_records.extend(designation_records(typed_designation))
            realization_constraints.extend(constraint_records(typed_designation))
        except ValidationError as exc:
            raise SDLParseError("Realization designation is structurally invalid", path=path) from exc
    lockfile, trust_policy = _workspace_policy(resolved_path, expansion_context, traversal)
    context = _ImportContext(
        path=path,
        resolved_path=resolved_path,
        child_traversal=child_traversal,
        budget=budget,
        lockfile=lockfile,
        trust_policy=trust_policy,
        source_format=source_format,
        migration_policy=migration_policy,
        limits=limits,
        source_diagnostics=source_diagnostics,
        verified_sources=expansion_context.verified_sources,
        registry_base_dir=registry_base_dir,
        semantic_revision=data.get("semantic_revision"),
        declaration_sources=expansion_context.declaration_sources
        if expansion_context.declaration_sources is not None
        else {},
    )

    # ADR-053 steps 1, 3 and 4: the policy files are loaded, then every declaration
    # is validated as the typed field before the first import resolves.
    for import_decl in _import_declarations(merged, path=path, source_ranges={}):
        merged, import_add, capability_add, derivation_add, explicitness_add, realization_add, constraint_add = (
            _expand_one_import(import_decl, merged, context)
        )
        import_records.extend(import_add)
        capability_constraints.extend(capability_add)
        parameter_derivations.extend(derivation_add)
        explicitness_records.extend(explicitness_add)
        realization_records.extend(realization_add)
        realization_constraints.extend(constraint_add)

    provenance = ExpansionProvenance(
        imports=tuple(import_records),
        capability_constraints=tuple(capability_constraints),
        parameter_derivations=tuple(parameter_derivations),
        explicitness=tuple(explicitness_records),
        realization_designations=tuple(realization_records),
        realization_constraints=tuple(realization_constraints),
    )
    merged.pop("imports", None)
    merged.pop("module", None)
    merged.pop("realization", None)
    merged["expansion_provenance"] = provenance.model_dump(mode="python")
    return merged, provenance
