"""Pure, author-authorized adoption of progressive SDL semantics."""

from __future__ import annotations

import yaml
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    ArtifactTransformationPreservationModel,
    ArtifactTransformationReportModel,
    ExternalConceptBindingDocumentModel,
)
from raes_contracts.external_concept_bindings import ExternalConceptSchemeSnapshotModel, admit_external_concept_bindings
from raes_contracts.sdl_semantic_migration import SDLSemanticMigrationContext

from ._errors import SDLError
from ._semantic_migration_decisions import apply_sentinel_decisions
from ._source_profile import DEFAULT_PARSER_LIMITS, SDLParserLimits, SDLSourceParseOptions
from ._transformation_bindings import _retarget_binding_documents
from ._transformation_support import check, diagnostic
from ._transformation_types import SDLTransformationResult
from ._yaml_loader import load_sdl_yaml
from .canonical import canonical_sdl_digest
from .external_concept_subjects import external_concept_subjects
from .formatting import format_sdl_source
from .parser import parse_sdl
from .scenario import Scenario
from .semantic_revisions import (
    LEGACY_SDL_REVISION,
    PROGRESSIVE_SDL_REVISION,
    read_versioned_sdl,
    source_byte_digest,
)

SEMANTIC_MIGRATION_PROFILE = "adopt-progressive-sdl-semantics/v1"


def _report(
    source_digest: str,
    context: SDLSemanticMigrationContext | None,
    *,
    output: Scenario | None = None,
    code: str | None = None,
    source_profile: str = LEGACY_SDL_REVISION,
    linked_context_digest: str | None = None,
) -> ArtifactTransformationReportModel:
    policy_digest = canonical_json_digest(context.model_dump(mode="json") if context is not None else None)
    return ArtifactTransformationReportModel(
        operation_profile=SEMANTIC_MIGRATION_PROFILE,
        status="success" if output is not None else "refused",
        artifact_kind="sdl-authoring",
        source_profile=source_profile,
        target_profile=PROGRESSIVE_SDL_REVISION,
        canonicalization_profile="sdl-progressive-migration-digest-pair/v1",
        source_digest=source_digest,
        target_digest=canonical_sdl_digest(output).value if output is not None else None,
        policy_digest=policy_digest,
        derivation_digest=canonical_json_digest(
            {
                "operation": SEMANTIC_MIGRATION_PROFILE,
                "source": source_digest,
                "policy": policy_digest,
                "linked_context": linked_context_digest,
            }
        ),
        preconditions=(check("source-and-author-context", "passed" if output is not None else "failed"),),
        postconditions=(check("current-target-admission", "passed"),) if output is not None else (),
        affected_identities=tuple(sorted(decision.pointer for decision in context.sentinel_decisions))
        if context
        else (),
        preservation=ArtifactTransformationPreservationModel(
            profile="explicit-semantic-revision-adoption/v1",
            outcome="not-applicable",
            limitations=(
                "Author adoption changes recursive, admission and observation semantics; "
                "no cross-version equivalence or current execution claim is made.",
            ),
        ),
        diagnostics=(
            diagnostic(
                code, "Explicit semantic migration was refused; review the source-bound decisions and migration guide."
            ),
        )
        if code
        else (),
    )


def migrate_sdl_semantics(
    content: str,
    *,
    context: SDLSemanticMigrationContext | None = None,
    binding_documents: tuple[ExternalConceptBindingDocumentModel, ...] = (),
    scheme_snapshots: tuple[ExternalConceptSchemeSnapshotModel, ...] = (),
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
) -> SDLTransformationResult:
    """Return a separately identified current artifact or an atomic refusal.

    Conversion does not certify or execute old semantics. The author context names the
    change from historical implicit floors to independently selected demand,
    and permits the negotiated preparation protocol without asserting support.
    #989's classification migration must be performed at its existing owner.
    """
    digest = source_byte_digest(content)
    linked_digest = canonical_json_digest(
        {
            "bindings": [document.model_dump(mode="json") for document in binding_documents],
            "schemes": [snapshot.model_dump(mode="json") for snapshot in scheme_snapshots],
        }
    )
    code = None
    output = None
    documents = ()
    source_profile = LEGACY_SDL_REVISION
    try:
        raw = load_sdl_yaml(content, source_options=SDLSourceParseOptions(limits=limits))
        if isinstance(raw, dict) and raw.get("semantic_revision") == PROGRESSIVE_SDL_REVISION:
            if context is not None:
                code = "semantic-migration.source-mismatch"
            else:
                output = read_versioned_sdl(content, limits=limits).scenario
                documents = _bindings(binding_documents, scheme_snapshots, output, output)
                source_profile = PROGRESSIVE_SDL_REVISION
        else:
            output, documents, code = _adopt_source(raw, digest, context, binding_documents, scheme_snapshots, limits)
    except (SDLError, ValueError, TypeError):
        code = "semantic-migration.source-or-target-invalid"
        output = None
        documents = ()
    return SDLTransformationResult(
        output,
        documents,
        _report(
            digest,
            context,
            output=output,
            code=code,
            source_profile=source_profile,
            linked_context_digest=linked_digest,
        ),
    )


def _adopt_source(
    raw: object,
    digest: str,
    context: SDLSemanticMigrationContext | None,
    binding_documents: tuple[ExternalConceptBindingDocumentModel, ...],
    scheme_snapshots: tuple[ExternalConceptSchemeSnapshotModel, ...],
    limits: SDLParserLimits,
) -> tuple[Scenario | None, tuple[ExternalConceptBindingDocumentModel, ...], str | None]:
    if context is None:
        return None, (), "semantic-migration.context-required"
    if digest != context.source_digest:
        return None, (), "semantic-migration.source-mismatch"
    return _adopt_legacy_source(raw, context, binding_documents, scheme_snapshots, limits)


def _adopt_legacy_source(
    raw: object,
    context: SDLSemanticMigrationContext,
    binding_documents: tuple[ExternalConceptBindingDocumentModel, ...],
    scheme_snapshots: tuple[ExternalConceptSchemeSnapshotModel, ...],
    limits: SDLParserLimits,
) -> tuple[Scenario | None, tuple[ExternalConceptBindingDocumentModel, ...], str | None]:
    if not isinstance(raw, dict) or raw.get("semantic_revision") not in {None, LEGACY_SDL_REVISION}:
        raise ValueError("unsupported source revision")
    if raw.get("imports"):
        return None, (), "semantic-migration.migrate-modules-independently"
    source_payload = {key: value for key, value in raw.items() if key != "semantic_revision"}
    normalized = format_sdl_source(yaml.safe_dump(source_payload, sort_keys=False), limits=limits)
    source = parse_sdl(normalized.content, limits=limits)
    payload, code = apply_sentinel_decisions(source, context.sentinel_decisions)
    if payload is None:
        return None, (), code
    payload["semantic_revision"] = PROGRESSIVE_SDL_REVISION
    output = parse_sdl(yaml.safe_dump(payload, sort_keys=False), limits=limits)
    documents = _bindings(binding_documents, scheme_snapshots, source, output)
    return output, documents, code


def _bindings(
    documents: tuple[ExternalConceptBindingDocumentModel, ...],
    snapshots: tuple[ExternalConceptSchemeSnapshotModel, ...],
    source: Scenario,
    target: Scenario,
) -> tuple[ExternalConceptBindingDocumentModel, ...]:
    """Reuse #989's exact-subject transport and existing binding admission."""
    if not documents:
        return ()
    transformed = _retarget_binding_documents(
        documents,
        source=source,
        target=target,
        source_digest=canonical_sdl_digest(source).value,
        target_digest=canonical_sdl_digest(target).value,
        before="",
        after="",
    )
    subjects = external_concept_subjects(target)
    if any(
        not admit_external_concept_bindings(document, subjects=subjects, scheme_snapshots=snapshots).admitted
        for document in transformed
    ):
        raise ValueError("linked classification binding admission failed")
    return transformed


__all__ = ["SDLSemanticMigrationContext", "SEMANTIC_MIGRATION_PROFILE", "migrate_sdl_semantics"]
