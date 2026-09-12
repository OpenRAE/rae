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
from .contracts.realization_descriptions import DescriptionFactModel, TypedRealizationDescriptionModel
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
class DescriptionPromotionDecision:
    actor: str
    decision_id: str
    decided_at: str
    target_id: str
    target_version: str


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
    decision: DescriptionPromotionDecision,
) -> DescriptionPromotion:
    """Conjoin selected known scalar facts with an isolated original constraint.

    This returns a new artifact and decision record. It grants no storage,
    execution, or authoring permission and performs no external operation.
    """
    _validate_decision(decision, fact_ids)
    description = readmit_description(description)
    if _bind_author(description, authored) is not None:
        raise ValueError("promotion requires the matching original author artifact")
    if (decision.target_id, decision.target_version) == (
        description.authored_ref.ref_id,
        description.authored_ref.ref_version,
    ):
        raise ValueError("promotion must create a new authored artifact identity")
    selected = _promotion_selection(description, fact_ids)
    selected_subjects = {fact.subject for fact in selected}
    _validate_competing_facts(description, authored, selected_subjects)
    target = _compose_promotion(selected, authored)
    source_digest = canonical_json_digest(description.model_dump(mode="json"))
    target_digest = canonical_json_digest(target.model_dump(mode="json"))
    selected_ids = tuple(sorted(fact_ids))
    policy_digest = canonical_json_digest({**_decision_values(decision), "fact_ids": list(selected_ids)})
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
            ref_kind="authoring-input",
            ref_id=decision.target_id,
            ref_version=decision.target_version,
            ref_digest=target_digest,
        ),
        decision.actor,
        decision.decision_id,
        decision.decided_at,
        transformation,
    )


def _decision_values(decision: DescriptionPromotionDecision) -> dict[str, object]:
    return {
        "actor": decision.actor,
        "decision_id": decision.decision_id,
        "decided_at": decision.decided_at,
        "target_id": decision.target_id,
        "target_version": decision.target_version,
    }


def _validate_decision(decision: DescriptionPromotionDecision, fact_ids: tuple[str, ...]) -> None:
    if not validate_realization_value(
        {**_decision_values(decision), "fact_ids": fact_ids}, python_carriers=True
    ).conformant:
        raise ValueError("promotion decision exceeds the supported bounds")
    identities = (decision.actor, decision.decision_id, decision.target_id, decision.target_version)
    if any(not isinstance(value, str) or not value.strip() for value in identities):
        raise ValueError("promotion requires explicit actor, decision and target identities")
    _parse_rfc3339_datetime("decided_at", decision.decided_at)


def _promotion_selection(
    description: TypedRealizationDescriptionModel, fact_ids: tuple[str, ...]
) -> tuple[DescriptionFactModel, ...]:
    if not fact_ids or len(set(fact_ids)) != len(fact_ids):
        raise ValueError("promotion requires a nonempty unique selection of fact ids")
    selected = tuple(fact for fact in description.facts if fact.fact_id in fact_ids)
    if len(selected) != len(fact_ids) or any(not _promotable_fact(fact) for fact in selected):
        raise ValueError("promotion requires selected known supported scalar facts without limitations")
    return selected


def _promotable_fact(fact: DescriptionFactModel) -> bool:
    return (
        fact.state == "known"
        and isinstance(fact.value, RealizationLiteral)
        and not fact.profile_bindings
        and not fact.limitations
    )


def _validate_competing_facts(
    description: TypedRealizationDescriptionModel, authored: RealizationConstraintDocument, selected_subjects: set[str]
) -> None:
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


def _compose_promotion(
    selected: tuple[DescriptionFactModel, ...], authored: RealizationConstraintDocument
) -> RealizationConstraintDocument:
    values = description_values(selected)
    normalized = normalize_realization_literal(values, semantic_profile=authored.semantic_profile)
    if normalized.document is None:
        raise ValueError("promotion selection could not be normalized within supported bounds")
    original = RealizationConstraintDocument.model_validate(authored.model_dump(mode="json"))
    additional = original.model_copy(update={"root": normalized.document.root})
    composed = compose_realization_constraints(original, additional)
    if composed.document is None or not realization_constraint_refines(composed.document, original).conformant:
        raise ValueError("promotion could not establish a conforming refinement")
    return composed.document


__all__ = ["DescriptionPromotion", "DescriptionPromotionDecision", "promote_description"]
