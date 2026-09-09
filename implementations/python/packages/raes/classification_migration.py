"""Explicit, offline migration of legacy SDL classifications to #986 artifacts."""

from __future__ import annotations

import hashlib

import yaml
from pydantic import ValidationError
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    ArtifactTransformationKind,
    ArtifactTransformationLossKind,
    ArtifactTransformationLossModel,
    ArtifactTransformationPreservationModel,
    ArtifactTransformationReportModel,
    ArtifactTransformationStatus,
    ExternalConceptBindingDocumentModel,
    PreservationOutcome,
    TransformationCheckOutcome,
)
from raes_contracts.diagnostics import Severity
from raes_contracts.external_concept_bindings import ExternalConceptSchemeSnapshotModel, admit_external_concept_bindings

from ._errors import SDLError
from ._legacy_classification_source import (
    LegacyClassificationSource,
    legacy_classification_source_digest,
    read_legacy_classification_source,
)
from ._source_profile import DEFAULT_PARSER_LIMITS, SDLParserLimits
from ._transformation_bindings import _retarget_binding_document
from ._transformation_support import check, diagnostic, transformation_policy_digest
from ._transformation_types import ArtifactTransformationPolicy, SDLTransformationResult
from .canonical import canonical_sdl_digest
from .external_concept_subjects import external_concept_subjects
from .parser import parse_sdl

CLASSIFICATION_MIGRATION_PROFILE = "externalize-sdl-classifications/v1"


def _report(
    *,
    source_digest: str,
    policy: ArtifactTransformationPolicy,
    context_digest: str,
    code: str | None = None,
    target_digest: str | None = None,
    losses: tuple[ArtifactTransformationLossModel, ...] = (),
    affected: tuple[str, ...] = (),
    binding_digests: tuple[str, ...] = (),
    canonicalization_profile: str = "raes-sdl-semantic/v1",
) -> ArtifactTransformationReportModel:
    succeeded = code is None
    policy_digest = transformation_policy_digest(policy)
    return ArtifactTransformationReportModel(
        operation_profile=CLASSIFICATION_MIGRATION_PROFILE,
        status=ArtifactTransformationStatus.SUCCESS if succeeded else ArtifactTransformationStatus.REFUSED,
        artifact_kind=ArtifactTransformationKind.SDL_AUTHORING,
        source_profile="sdl-legacy-classifications/v1",
        target_profile="sdl-authoring-input/v1",
        canonicalization_profile=canonicalization_profile,
        source_digest=source_digest,
        target_digest=target_digest,
        policy_digest=policy_digest,
        derivation_digest=canonical_json_digest(
            {
                "operation_profile": CLASSIFICATION_MIGRATION_PROFILE,
                "source_digest": source_digest,
                "policy_digest": policy_digest,
                "context_digest": context_digest,
            }
        ),
        preconditions=(
            check(
                "migration-context",
                TransformationCheckOutcome.PASSED if succeeded else TransformationCheckOutcome.FAILED,
                *((code,) if code else ()),
            ),
        ),
        postconditions=(check("target-and-bindings-admitted", TransformationCheckOutcome.PASSED),) if succeeded else (),
        affected_identities=tuple(sorted(set(affected))),
        losses=losses,
        preservation=ArtifactTransformationPreservationModel(
            profile="native-configuration-and-explicit-assertions/v1",
            outcome=PreservationOutcome.VERIFIED if succeeded else PreservationOutcome.FAILED,
            evidence_digests=tuple(
                sorted({source_digest, *(binding_digests), *((target_digest,) if target_digest else ())})
            ),
            limitations=(
                "Native projection equality and binding admission do not prove realization or participant disclosure.",
            ),
        ),
        diagnostics=() if succeeded else (diagnostic(code, _MESSAGES[code]),),
    )


_MESSAGES = {
    "classification-migration.source-invalid": "Legacy source is invalid or unsupported; migrate uncomposed authoring sources with concrete classification values. See docs/migration/external-classifications.md.",
    "classification-migration.context-required": "Supply one complete external concept assertion per legacy association, with exact source-pointer provenance and pinned local scheme snapshots.",
    "classification-migration.context-invalid": "Assertion context must preserve each exact source subject and source pointer without missing, duplicate, stale, or extra mappings.",
    "classification-migration.loss-not-authorized": "Vulnerability declaration removal requires declaration-removed authorization; an unreferenced declaration also requires semantic-omission authorization.",
    "classification-migration.target-invalid": "The native SDL must independently pass structural and semantic validation; migrate references to removed declarations explicitly.",
    "classification-migration.native-projection-changed": "Normalize legacy native fields with the source-version formatter before migration; migration must preserve the native projection exactly.",
    "classification-migration.binding-admission-failed": "Supply exact current scheme snapshots and complete valid assertions; unavailable, stale, ambiguous, superseded, or unknown concepts cannot complete migration.",
}


def _losses(source: LegacyClassificationSource, policy: ArtifactTransformationPolicy):
    referenced = {record.declaration_ref for record in source.classifications}
    allowed = set(policy.allowed_loss_kinds)
    if source.declarations and ArtifactTransformationLossKind.DECLARATION_REMOVED not in allowed:
        return None
    unreferenced = set(source.declarations) - referenced
    if unreferenced and ArtifactTransformationLossKind.SEMANTIC_OMISSION not in allowed:
        return None
    losses = [
        ArtifactTransformationLossModel(
            kind=ArtifactTransformationLossKind.DECLARATION_REMOVED,
            affected_identity=identity,
            diagnostic=diagnostic(
                "classification-migration.declaration-removed",
                "The historical classification declaration is retained only in the source artifact.",
                severity=Severity.WARNING,
            ),
        )
        for identity in source.declarations
    ]
    losses.extend(
        ArtifactTransformationLossModel(
            kind=ArtifactTransformationLossKind.SEMANTIC_OMISSION,
            affected_identity=identity,
            diagnostic=diagnostic(
                "classification-migration.unreferenced-classification",
                "An unreferenced classification was omitted under explicit loss authorization.",
                severity=Severity.WARNING,
            ),
        )
        for identity in sorted(unreferenced)
    )
    return tuple(losses)


def _context_matches(source: LegacyClassificationSource, document: ExternalConceptBindingDocumentModel | None) -> bool:
    if document is None:
        return not source.classifications
    if len(document.bindings) != len(source.classifications):
        return False
    used: set[str] = set()
    for record in source.classifications:
        candidates = [
            binding
            for binding in document.bindings.values()
            if any(
                ref.ref_kind == "authoring-input"
                and ref.ref_digest == source.source_digest.value
                and ref.ref_path == record.pointer
                for ref in binding.provenance.source_refs
            )
        ]
        if len(candidates) != 1:
            return False
        binding = candidates[0]
        if binding.binding_id in used or binding.subject.canonical_ref != record.subject_ref:
            return False
        if binding.subject.artifact_digest != source.source_digest.value:
            return False
        if record.declaration_ref is not None and binding.scheme.concept_id != record.identifier:
            return False
        used.add(binding.binding_id)
    return True


def migrate_sdl_classifications(
    content: str,
    *,
    bindings: ExternalConceptBindingDocumentModel | None = None,
    scheme_snapshots: tuple[ExternalConceptSchemeSnapshotModel, ...] = (),
    existing_binding_documents: tuple[ExternalConceptBindingDocumentModel, ...] = (),
    policy: ArtifactTransformationPolicy | None = None,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
) -> SDLTransformationResult:
    """Return admitted native SDL, binding sidecars and a report, or only a refusal.

    New assertions explicitly name their historical source digest and association
    JSON pointer in an authoring-input provenance reference. Every assertion
    dimension is supplied by the caller. Source bytes are never changed.
    """
    resolved_policy = policy if policy is not None else ArtifactTransformationPolicy()
    context_digest = canonical_json_digest(
        {
            "bindings": bindings.model_dump(mode="json") if bindings else None,
            "existing": [document.model_dump(mode="json") for document in existing_binding_documents],
            "snapshots": [snapshot.model_dump(mode="json") for snapshot in scheme_snapshots],
        }
    )
    source_digest = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    source_profile = "raw-utf8/v1"

    def refuse(code: str) -> SDLTransformationResult:
        return SDLTransformationResult(
            None,
            (),
            _report(
                source_digest=source_digest,
                policy=resolved_policy,
                context_digest=context_digest,
                code=code,
                canonicalization_profile=source_profile,
            ),
        )

    try:
        source = read_legacy_classification_source(content, limits=limits)
    except (SDLError, ValueError, TypeError):
        return refuse("classification-migration.source-invalid")
    source_digest = source.source_digest.value
    source_profile = source.source_digest.profile
    if source.classifications and bindings is None:
        return refuse("classification-migration.context-required")
    if not _context_matches(source, bindings):
        return refuse("classification-migration.context-invalid")
    losses = _losses(source, resolved_policy)
    if losses is None:
        return refuse("classification-migration.loss-not-authorized")
    try:
        target = parse_sdl(yaml.safe_dump(source.native, sort_keys=False), limits=limits)
    except (SDLError, ValueError, TypeError):
        return refuse("classification-migration.target-invalid")
    if target.model_dump(mode="json", by_alias=True, exclude_unset=True) != source.native:
        return refuse("classification-migration.native-projection-changed")
    target_digest = canonical_sdl_digest(target).value
    subject_candidates = external_concept_subjects(target)
    target_subjects = {subject.canonical_ref: subject for subject in subject_candidates}
    if len(target_subjects) != len(subject_candidates):
        return refuse("classification-migration.context-invalid")
    source_subjects = {
        ref: subject.model_copy(update={"artifact_digest": source_digest}) for ref, subject in target_subjects.items()
    }
    documents = (*((bindings,) if bindings else ()), *existing_binding_documents)
    try:
        output_documents = tuple(
            _retarget_binding_document(
                ExternalConceptBindingDocumentModel.model_validate(document.model_dump(mode="json")),
                source_subjects=source_subjects,
                target_subjects=target_subjects,
                source_digest=source_digest,
                target_digest=target_digest,
                before="",
                after="",
            )
            for document in documents
        )
        if any(
            not admit_external_concept_bindings(
                document, subjects=tuple(target_subjects.values()), scheme_snapshots=scheme_snapshots
            ).admitted
            for document in output_documents
        ):
            return refuse("classification-migration.binding-admission-failed")
    except (ValidationError, ValueError, TypeError):
        return refuse("classification-migration.binding-admission-failed")
    binding_digests = tuple(canonical_json_digest(document.model_dump(mode="json")) for document in output_documents)
    report = _report(
        source_digest=source_digest,
        policy=resolved_policy,
        context_digest=context_digest,
        target_digest=target_digest,
        losses=losses,
        affected=(*source.declarations, *(record.subject_ref for record in source.classifications)),
        binding_digests=binding_digests,
    )
    return SDLTransformationResult(target, output_documents, report)


__all__ = ["CLASSIFICATION_MIGRATION_PROFILE", "legacy_classification_source_digest", "migrate_sdl_classifications"]
