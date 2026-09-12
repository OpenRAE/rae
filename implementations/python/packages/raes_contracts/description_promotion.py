"""Explicit pure promotion; callers retain ownership of author mutation admission."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_json_digest
from .contracts.artifact_transformations import (
    ArtifactTransformationCheckModel,
    ArtifactTransformationPreservationModel,
    ArtifactTransformationReportModel,
)
from .contracts.base import _parse_rfc3339_datetime
from .contracts.experiment_references import ExperimentReferenceModel
from .contracts.realization_descriptions import TypedRealizationDescriptionModel
from .description_projection import (
    _bind_author,
    description_conflict,
    description_values,
    known_fact_violation,
    readmit_description,
)
from .realization_structure import (
    RealizationConstraintDocument,
    RealizationLiteral,
    compose_realization_constraints,
    normalize_realization_literal,
    realization_constraint_refines,
    semantic_address_contains,
    validate_realization_value,
)


@dataclass(frozen=True)
class DescriptionPromotion:
    constraints: RealizationConstraintDocument
    selected_fact_ids: tuple[str, ...]
    source_ref: ExperimentReferenceModel
    target_ref: ExperimentReferenceModel
    actor: str
    decision_id: str
    decided_at: str
    transformation: ArtifactTransformationReportModel


def promote_description(
    description: TypedRealizationDescriptionModel,
    authored: RealizationConstraintDocument,
    *,
    fact_ids: tuple[str, ...],
    actor: str,
    decision_id: str,
    decided_at: str,
    target_id: str,
    target_version: str,
) -> DescriptionPromotion:
    """Conjoin selected known scalar facts with an isolated original constraint.

    This returns a new artifact and decision record. It grants no storage,
    execution, or authoring permission and performs no external operation.
    """
    decision = {
        "fact_ids": fact_ids,
        "actor": actor,
        "decision_id": decision_id,
        "decided_at": decided_at,
        "target_id": target_id,
        "target_version": target_version,
    }
    if not validate_realization_value(decision, python_carriers=True).conformant:
        raise ValueError("promotion decision exceeds the supported bounds")
    if any(
        not isinstance(value, str) or not value.strip() for value in (actor, decision_id, target_id, target_version)
    ):
        raise ValueError("promotion requires explicit actor, decision and target identities")
    _parse_rfc3339_datetime("decided_at", decided_at)
    description = readmit_description(description)
    if _bind_author(description, authored) is not None:
        raise ValueError("promotion requires the matching original author artifact")
    if (target_id, target_version) == (description.authored_ref.ref_id, description.authored_ref.ref_version):
        raise ValueError("promotion must create a new authored artifact identity")
    if not fact_ids or len(set(fact_ids)) != len(fact_ids):
        raise ValueError("promotion requires a nonempty unique selection of fact ids")
    selected = tuple(fact for fact in description.facts if fact.fact_id in fact_ids)
    if len(selected) != len(fact_ids) or any(
        fact.state != "known"
        or not isinstance(fact.value, RealizationLiteral)
        or fact.profile_bindings
        or fact.limitations
        for fact in selected
    ):
        raise ValueError("promotion requires selected known supported scalar facts without limitations")
    selected_subjects = {fact.subject for fact in selected}
    competing = description.model_copy(
        update={
            "facts": tuple(
                fact
                for fact in description.facts
                if any(
                    semantic_address_contains(subject, fact.subject) or semantic_address_contains(fact.subject, subject)
                    for subject in selected_subjects
                )
            )
        }
    )
    if description_conflict(competing) is not None or known_fact_violation(competing, authored) is not None:
        raise ValueError("promotion cannot resolve conflicting assertions or weaken author constraints")
    values = description_values(selected)
    normalized = normalize_realization_literal(values, semantic_profile=authored.semantic_profile)
    if normalized.document is None:
        raise ValueError("promotion selection could not be normalized within supported bounds")
    original = RealizationConstraintDocument.model_validate(authored.model_dump(mode="json"))
    additional = original.model_copy(update={"root": normalized.document.root})
    composed = compose_realization_constraints(original, additional)
    if composed.document is None or not realization_constraint_refines(composed.document, original).conformant:
        raise ValueError("promotion could not establish a conforming refinement")
    target = composed.document
    source_digest = canonical_json_digest(description.model_dump(mode="json"))
    target_digest = canonical_json_digest(target.model_dump(mode="json"))
    selected_ids = tuple(sorted(fact_ids))
    policy_digest = canonical_json_digest({**decision, "fact_ids": list(selected_ids)})
    transformation = ArtifactTransformationReportModel(
        operation_profile="description-promotion/v1",
        status="success",
        artifact_kind="portable-contract",
        source_profile=description.schema_version,
        target_profile=target.contract_id,
        canonicalization_profile="rfc8785-jcs-sha256/v1",
        source_digest=source_digest,
        target_digest=target_digest,
        policy_digest=policy_digest,
        derivation_digest=canonical_json_digest(
            {"source": source_digest, "target": target_digest, "decision": policy_digest}
        ),
        preconditions=(ArtifactTransformationCheckModel(check_id="selected-facts-admitted", outcome="passed"),),
        postconditions=(ArtifactTransformationCheckModel(check_id="author-refinement", outcome="passed"),),
        affected_identities=tuple(sorted(selected_subjects)),
        preservation=ArtifactTransformationPreservationModel(
            profile="author-constraint-refinement/v1",
            outcome="verified",
            evidence_digests=tuple(sorted({description.authored_ref.ref_digest, target_digest})),
            limitations=("Only selected scalar facts gain authority; coverage does not close collections.",),
        ),
    )
    return DescriptionPromotion(
        target,
        selected_ids,
        ExperimentReferenceModel(
            ref_kind="other",
            ref_id=description.description_id,
            ref_version=description.description_version,
            ref_digest=source_digest,
        ),
        ExperimentReferenceModel(
            ref_kind="authoring-input", ref_id=target_id, ref_version=target_version, ref_digest=target_digest
        ),
        actor,
        decision_id,
        decided_at,
        transformation,
    )


__all__ = ["DescriptionPromotion", "promote_description"]
