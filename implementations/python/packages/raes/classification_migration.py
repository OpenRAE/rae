"""Explicit, offline migration of legacy SDL classifications to #986 artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

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
    ExternalConceptBindingAssertionModel,
    ExternalConceptBindingDocumentModel,
    PreservationOutcome,
    TransformationCheckOutcome,
)
from raes_contracts.diagnostics import Severity
from raes_contracts.external_concept_bindings import ExternalConceptSchemeSnapshotModel, admit_external_concept_bindings

from ._errors import SDLError
from ._legacy_classification_source import (
    LegacyClassification,
    LegacyClassificationSource,
    legacy_classification_source_digest,
    read_legacy_classification_source,
)
from ._source_profile import DEFAULT_PARSER_LIMITS, SDLParserLimits
from ._transformation_bindings import _retarget_binding_document
from ._transformation_support import check, diagnostic, transformation_policy_digest
from ._transformation_types import ArtifactTransformationPolicy, SDLAuthoringArtifact, SDLTransformationResult
from .canonical import canonical_sdl_digest
from .external_concept_subjects import external_concept_subjects
from .parser import parse_sdl

CLASSIFICATION_MIGRATION_PROFILE = "externalize-sdl-classifications/v1"
_CONTEXT_INVALID = "classification-migration.context-invalid"
_BINDING_ADMISSION_FAILED = "classification-migration.binding-admission-failed"


@dataclass
class _ReportContext:
    source_digest: str
    policy: ArtifactTransformationPolicy
    context_digest: str
    canonicalization_profile: str = "raes-sdl-semantic/v1"


class _MigrationRefusal(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _report(
    context: _ReportContext,
    *,
    code: str | None = None,
    target_digest: str | None = None,
    losses: tuple[ArtifactTransformationLossModel, ...] = (),
    affected: tuple[str, ...] = (),
    binding_digests: tuple[str, ...] = (),
) -> ArtifactTransformationReportModel:
    succeeded = code is None
    source_digest = context.source_digest
    policy_digest = transformation_policy_digest(context.policy)
    return ArtifactTransformationReportModel(
        operation_profile=CLASSIFICATION_MIGRATION_PROFILE,
        status=ArtifactTransformationStatus.SUCCESS if succeeded else ArtifactTransformationStatus.REFUSED,
        artifact_kind=ArtifactTransformationKind.SDL_AUTHORING,
        source_profile="sdl-legacy-classifications/v1",
        target_profile="sdl-authoring-input/v1",
        canonicalization_profile=context.canonicalization_profile,
        source_digest=source_digest,
        target_digest=target_digest,
        policy_digest=policy_digest,
        derivation_digest=canonical_json_digest(
            {
                "operation_profile": CLASSIFICATION_MIGRATION_PROFILE,
                "source_digest": source_digest,
                "policy_digest": policy_digest,
                "context_digest": context.context_digest,
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
    "classification-migration.source-invalid": (
        "Legacy source is invalid or unsupported; migrate uncomposed authoring sources with concrete "
        "classification values. See docs/migration/external-classifications.md."
    ),
    "classification-migration.context-required": (
        "Supply one complete external concept assertion per legacy association, with exact source-pointer "
        "provenance and pinned local scheme snapshots."
    ),
    _CONTEXT_INVALID: (
        "Assertion context must preserve each exact source subject and source pointer without missing, "
        "duplicate, stale, or extra mappings."
    ),
    "classification-migration.loss-not-authorized": (
        "Vulnerability declaration removal requires declaration-removed authorization; an unreferenced "
        "declaration also requires semantic-omission authorization."
    ),
    "classification-migration.target-invalid": (
        "The native SDL must independently pass structural and semantic validation; migrate references "
        "to removed declarations explicitly."
    ),
    "classification-migration.native-projection-changed": (
        "Normalize legacy native fields with the source-version formatter before migration; migration "
        "must preserve the native projection exactly."
    ),
    _BINDING_ADMISSION_FAILED: (
        "Supply exact current scheme snapshots and complete valid assertions; unavailable, stale, ambiguous, "
        "superseded, or unknown concepts cannot complete migration."
    ),
}


def _losses(
    source: LegacyClassificationSource, policy: ArtifactTransformationPolicy
) -> tuple[ArtifactTransformationLossModel, ...] | None:
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
    used: set[str] = set()
    return len(document.bindings) == len(source.classifications) and all(
        _record_matches(record, source.source_digest.value, document, used) for record in source.classifications
    )


def _provenance_matches(binding: ExternalConceptBindingAssertionModel, digest: str, pointer: str) -> bool:
    return any(
        ref.ref_kind == "authoring-input" and ref.ref_digest == digest and ref.ref_path == pointer
        for ref in binding.provenance.source_refs
    )


def _record_matches(
    record: LegacyClassification, digest: str, document: ExternalConceptBindingDocumentModel, used: set[str]
) -> bool:
    candidates = [
        binding for binding in document.bindings.values() if _provenance_matches(binding, digest, record.pointer)
    ]
    if len(candidates) != 1:
        return False
    binding = candidates[0]
    matches = (
        binding.binding_id not in used
        and binding.subject.canonical_ref == record.subject_ref
        and binding.subject.artifact_digest == digest
        and (record.declaration_ref is None or binding.scheme.concept_id == record.identifier)
    )
    used.add(binding.binding_id)
    return matches


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
    context = _ReportContext(
        "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest(),
        resolved_policy,
        context_digest,
        "raw-utf8/v1",
    )
    try:
        source = _migration_source(content, limits)
        context.source_digest = source.source_digest.value
        context.canonicalization_profile = source.source_digest.profile
        losses = _migration_losses(source, bindings, resolved_policy)
        target = _migration_target(source, limits)
        output_documents = _migration_bindings(source, target, bindings, existing_binding_documents, scheme_snapshots)
    except _MigrationRefusal as exc:
        return SDLTransformationResult(None, (), _report(context, code=exc.code))
    # Successful output uses the current canonical profile, as before migration refactoring.
    context.canonicalization_profile = "raes-sdl-semantic/v1"
    report = _report(
        context,
        target_digest=canonical_sdl_digest(target).value,
        losses=losses,
        affected=(*source.declarations, *(record.subject_ref for record in source.classifications)),
        binding_digests=tuple(canonical_json_digest(document.model_dump(mode="json")) for document in output_documents),
    )
    return SDLTransformationResult(target, output_documents, report)


def _migration_source(content: str, limits: SDLParserLimits) -> LegacyClassificationSource:
    try:
        return read_legacy_classification_source(content, limits=limits)
    except (SDLError, ValueError, TypeError) as exc:
        raise _MigrationRefusal("classification-migration.source-invalid") from exc


def _migration_losses(
    source: LegacyClassificationSource,
    bindings: ExternalConceptBindingDocumentModel | None,
    policy: ArtifactTransformationPolicy,
) -> tuple[ArtifactTransformationLossModel, ...]:
    if source.classifications and bindings is None:
        raise _MigrationRefusal("classification-migration.context-required")
    if not _context_matches(source, bindings):
        raise _MigrationRefusal(_CONTEXT_INVALID)
    losses = _losses(source, policy)
    if losses is None:
        raise _MigrationRefusal("classification-migration.loss-not-authorized")
    return losses


def _migration_target(source: LegacyClassificationSource, limits: SDLParserLimits) -> SDLAuthoringArtifact:
    try:
        target = parse_sdl(yaml.safe_dump(source.native, sort_keys=False), limits=limits)
    except (SDLError, ValueError, TypeError) as exc:
        raise _MigrationRefusal("classification-migration.target-invalid") from exc
    if target.model_dump(mode="json", by_alias=True, exclude_unset=True) != source.native:
        raise _MigrationRefusal("classification-migration.native-projection-changed")
    return target


def _migration_bindings(
    source: LegacyClassificationSource,
    target: SDLAuthoringArtifact,
    bindings: ExternalConceptBindingDocumentModel | None,
    existing_binding_documents: tuple[ExternalConceptBindingDocumentModel, ...],
    scheme_snapshots: tuple[ExternalConceptSchemeSnapshotModel, ...],
) -> tuple[ExternalConceptBindingDocumentModel, ...]:
    source_digest = source.source_digest.value
    target_digest = canonical_sdl_digest(target).value
    subject_candidates = external_concept_subjects(target)
    target_subjects = {subject.canonical_ref: subject for subject in subject_candidates}
    if len(target_subjects) != len(subject_candidates):
        raise _MigrationRefusal(_CONTEXT_INVALID)
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
            raise _MigrationRefusal(_BINDING_ADMISSION_FAILED)
    except (ValidationError, ValueError, TypeError) as exc:
        raise _MigrationRefusal(_BINDING_ADMISSION_FAILED) from exc
    return output_documents


__all__ = ["CLASSIFICATION_MIGRATION_PROFILE", "legacy_classification_source_digest", "migrate_sdl_classifications"]
