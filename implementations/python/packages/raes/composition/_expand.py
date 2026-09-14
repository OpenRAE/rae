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
from .._composition_provenance import (
    prefixed_constraint as _prefixed_constraint,
)
from .._composition_provenance import (
    prefixed_explicitness as _prefixed_explicitness,
)
from .._composition_provenance import (
    prefixed_import_record as _prefixed_import_record,
)
from .._composition_provenance import (
    prefixed_realization_constraint as _prefixed_realization_constraint,
)
from .._composition_provenance import (
    prefixed_realization_designation as _prefixed_realization_designation,
)
from .._composition_provenance import (
    resolved_import_record as _resolved_import_record,
)
from .._errors import SDLInstantiationError, SDLParseDiagnostic, SDLParseError
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
from ..instantiate import _bind_scenario_content, _BoundScenarioResult
from ..module_registry import (
    Lockfile,
    ResolvedModule,
    TrustPolicy,
    _VerifiedSourceBundle,
    load_lockfile,
    load_trust_policy,
    resolve_import,
)
from ..parser import _load_normalized_data
from ..phase_contracts import (
    CapabilityConstraint,
    ExpansionProvenance,
    ExplicitnessProvenanceRecord,
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
from ._behavior import _behavior_reference_maps, _rewrite_agent_sections, _rewrite_behavior_sections
from ._profiles import rewrite_profile_selections
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

    rewritten = _rewrite_variable_tokens(namespaced, symbols["variables"])
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


def _import_decl(value: object) -> ImportDecl:
    if isinstance(value, ImportDecl):
        return value
    return ImportDecl.model_validate(value)


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


@dataclass(frozen=True)
class _ExpansionContext:
    """Private traversal and trust state carried across recursive expansion."""

    traversal: CompositionTraversal | None = None
    verified_sources: _VerifiedSourceBundle | None = None
    inherited_lockfile: Lockfile | None = None
    inherited_trust_policy: TrustPolicy | None = None
    registry_base_dir: Path | None = None


class _ExpansionPrivateOptions(TypedDict, total=False):
    """Typed compatibility keywords for private recursive expansion state."""

    _context: _ExpansionContext
    _traversal: CompositionTraversal | None
    _verified_sources: _VerifiedSourceBundle | None
    _inherited_lockfile: Lockfile | None
    _inherited_trust_policy: TrustPolicy | None
    _registry_base_dir: Path | None


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
    )


def _expand_one_import(
    raw_import: object,
    merged: dict[str, Any],
    context: _ImportContext,
) -> tuple[
    dict[str, Any],
    list[ResolvedImportProvenance],
    list[CapabilityConstraint],
    list[ExplicitnessProvenanceRecord],
    list[RealizationDesignationRecord],
    list[RealizationConstraintRecord],
]:
    """Resolve, expand, namespace, and merge a single import; return provenance additions."""

    context.budget.add_import(path=context.path)
    import_decl = _import_decl(raw_import)
    if "__private." in import_decl.namespace:
        raise SDLParseError(
            "Import namespaces may not contain the reserved '__private' segment",
            path=context.path,
        )
    resolved_import = resolve_import(
        import_decl,
        base_dir=context.resolved_path.parent,
        lockfile=context.lockfile,
        trust_policy=context.trust_policy,
        source_options=SDLSourceParseOptions(
            source_format=context.source_format,
            migration_policy=context.migration_policy,
            limits=context.limits,
            required_semantic_revision=context.semantic_revision,
        ),
        source_diagnostics=context.source_diagnostics,
        verified_sources=context.verified_sources,
        _registry_base_dir=context.registry_base_dir,
    )
    import_path = resolved_import.root_file
    imported_raw = _load_normalized_data(
        resolved_import.source_document.text,
        path=import_path,
        source_format=context.source_format,
        migration_policy=context.migration_policy,
        limits=context.limits,
        source_diagnostics=context.source_diagnostics,
        required_semantic_revision=context.semantic_revision,
    )
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
        raise SDLParseError("Imported SDL unit is structurally invalid", path=import_path) from exc
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

    namespaced_payload = _namespace_payload(
        bound.content.model_dump(mode="python", by_alias=True),
        bound.content,
        namespace,
        descriptor,
    )
    context.budget.check_namespaces(namespaced_payload, path=import_path)
    merged = _merge_sections(merged, namespaced_payload, path=import_path)

    return (merged, *_import_provenance_additions(resolved_import, import_decl, bound, inner_provenance, symbols))


def _import_provenance_additions(
    resolved_import: ResolvedModule,
    import_decl: ImportDecl,
    bound: _BoundScenarioResult,
    inner_provenance: ExpansionProvenance,
    symbols: dict[str, dict[str, str] | set[str]],
) -> tuple[
    list[ResolvedImportProvenance],
    list[CapabilityConstraint],
    list[ExplicitnessProvenanceRecord],
    list[RealizationDesignationRecord],
    list[RealizationConstraintRecord],
]:
    """Build the namespaced provenance additions contributed by one import."""

    namespace = import_decl.namespace
    import_records: list[ResolvedImportProvenance] = [
        _resolved_import_record(resolved_import, requested=import_decl, bindings=bound)
    ]
    import_records.extend(_prefixed_import_record(record, namespace) for record in inner_provenance.imports)
    capability_constraints = [
        _prefixed_constraint(constraint, namespace=namespace, symbols=symbols)
        for constraint in bound.capability_constraints
    ]
    explicitness_records = [
        _prefixed_explicitness(record, namespace=namespace, imported=bound.content, symbols=symbols)
        for record in bound.explicitness
        if any(record.model_path.startswith(f"{section_name}.") for section_name in _HASHMAP_SECTIONS)
    ]
    realization_records = [
        _prefixed_realization_designation(record, namespace=namespace, symbols=symbols)
        for record in inner_provenance.realization_designations
    ]
    realization_constraints = [
        _prefixed_realization_constraint(record, namespace=namespace, symbols=symbols)
        for record in inner_provenance.realization_constraints
    ]
    return (
        import_records,
        capability_constraints,
        explicitness_records,
        realization_records,
        realization_constraints,
    )


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
    if expansion_context.verified_sources is None:
        lockfile = load_lockfile(resolved_path.parent)
        trust_policy = load_trust_policy(resolved_path.parent)
    else:
        lockfile = expansion_context.inherited_lockfile
        trust_policy = (
            expansion_context.inherited_trust_policy
            if expansion_context.inherited_trust_policy is not None
            else TrustPolicy()
        )
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
    )

    for raw_import in merged.get("imports", []):
        merged, import_add, capability_add, explicitness_add, realization_add, constraint_add = _expand_one_import(
            raw_import, merged, context
        )
        import_records.extend(import_add)
        capability_constraints.extend(capability_add)
        explicitness_records.extend(explicitness_add)
        realization_records.extend(realization_add)
        realization_constraints.extend(constraint_add)

    provenance = ExpansionProvenance(
        imports=tuple(import_records),
        capability_constraints=tuple(capability_constraints),
        explicitness=tuple(explicitness_records),
        realization_designations=tuple(realization_records),
        realization_constraints=tuple(realization_constraints),
    )
    merged.pop("imports", None)
    merged.pop("module", None)
    merged.pop("realization", None)
    merged["expansion_provenance"] = provenance.model_dump(mode="python")
    return merged, provenance
