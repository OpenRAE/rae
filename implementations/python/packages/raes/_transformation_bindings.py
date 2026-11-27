"""External concept-binding retargeting for SDL transformations."""

from __future__ import annotations

from raes_contracts.contracts import (
    ExternalConceptBindingDocumentModel,
    ExternalConceptSubjectModel,
)

from ._transformation_types import SDLAuthoringArtifact, _TransformationRefusal
from .external_concept_subjects import external_concept_subjects


def _binding_subject_payload(binding: object) -> dict[str, object]:
    if not isinstance(binding, dict) or not isinstance(binding.get("subject"), dict):
        raise ValueError("external concept binding document has an invalid subject")
    return binding["subject"]


def _same_subject_coordinate(
    source_subject: ExternalConceptSubjectModel | None,
    subject: dict[str, object],
) -> bool:
    return source_subject is not None and (
        source_subject.subject_kind == subject.get("subject_kind")
        and source_subject.owning_contract_id == subject.get("owning_contract_id")
        and source_subject.lifecycle_phase.value == subject.get("lifecycle_phase")
    )


def _retarget_binding_subject(
    subject: dict[str, object],
    *,
    source_subjects: dict[str, ExternalConceptSubjectModel],
    target_subjects: dict[str, ExternalConceptSubjectModel],
    source_digest: str,
    target_digest: str,
    before: str,
    after: str,
) -> None:
    canonical_ref = str(subject.get("canonical_ref", ""))
    source_subject = source_subjects.get(canonical_ref)
    same_source_coordinate = _same_subject_coordinate(source_subject, subject)
    supplied_digest = str(subject.get("artifact_digest", ""))
    source_digest_matches = supplied_digest.casefold() == source_digest.casefold()
    if same_source_coordinate and not source_digest_matches:
        raise _TransformationRefusal("external concept subject is stale for the source artifact")
    if not source_digest_matches:
        return
    if not same_source_coordinate or source_subject is None:
        raise _TransformationRefusal("external concept subject does not resolve in the source artifact")
    rewritten_ref = after if canonical_ref == before else canonical_ref
    target_subject = target_subjects.get(rewritten_ref)
    if target_subject is None or target_subject.subject_kind != source_subject.subject_kind:
        raise _TransformationRefusal("external concept subject does not resolve in the target artifact")
    subject["canonical_ref"] = rewritten_ref
    subject["artifact_digest"] = target_digest


def _retarget_binding_document(
    document: ExternalConceptBindingDocumentModel,
    *,
    source_subjects: dict[str, ExternalConceptSubjectModel],
    target_subjects: dict[str, ExternalConceptSubjectModel],
    source_digest: str,
    target_digest: str,
    before: str,
    after: str,
) -> ExternalConceptBindingDocumentModel:
    payload = document.model_dump(mode="json")
    bindings = payload.get("bindings")
    if not isinstance(bindings, dict):
        raise ValueError("external concept binding document has an invalid binding map")
    for binding in bindings.values():
        _retarget_binding_subject(
            _binding_subject_payload(binding),
            source_subjects=source_subjects,
            target_subjects=target_subjects,
            source_digest=source_digest,
            target_digest=target_digest,
            before=before,
            after=after,
        )
    return ExternalConceptBindingDocumentModel.model_validate(payload)


def _retarget_binding_documents(
    documents: tuple[ExternalConceptBindingDocumentModel, ...],
    *,
    source: SDLAuthoringArtifact,
    target: SDLAuthoringArtifact,
    source_digest: str,
    target_digest: str,
    before: str,
    after: str,
) -> tuple[ExternalConceptBindingDocumentModel, ...]:
    source_subjects = {subject.canonical_ref: subject for subject in external_concept_subjects(source)}
    target_subjects = {subject.canonical_ref: subject for subject in external_concept_subjects(target)}
    return tuple(
        _retarget_binding_document(
            document,
            source_subjects=source_subjects,
            target_subjects=target_subjects,
            source_digest=source_digest,
            target_digest=target_digest,
            before=before,
            after=after,
        )
        for document in documents
    )


__all__ = []
