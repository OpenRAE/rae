"""Deny-first, exact-state-cut SEM-226 participant exposure selection."""

from __future__ import annotations

from collections.abc import Mapping

from raes_contracts.contracts import ParticipantExposurePolicyModel

from .behavior_resources import _PARTICIPANT_VISIBLE_VIEW_DISPOSITIONS
from .participant_exposure_authority_v2 import (
    ParticipantExposureAuthorizationRecordV2,
    ParticipantExposurePolicyDecisionV2,
    ParticipantExposureProjectionV2,
    ParticipantExposureResolversV2,
)
from .participant_exposure_policy import _policy_permits_item, resolve_from_host


def _serialized_surface_refs(
    projection: ParticipantExposureProjectionV2,
    entries: list[dict[str, object]],
    surface_affordances: list[str],
) -> set[str]:
    return {
        *projection.visible_context_refs,
        *(str(entry["action_contract_address"]) for entry in entries),
        *surface_affordances,
    }


def _resolve_policy_decision(
    projection: ParticipantExposureProjectionV2,
    resolvers: ParticipantExposureResolversV2,
) -> ParticipantExposurePolicyDecisionV2:
    decision = resolve_from_host(
        "projection-policy",
        "participant exposure exact-cut projection-policy resolution failed",
        lambda: resolvers.projection_policy(
            projection_policy_ref=projection.projection_policy_ref,
            participant_address=projection.participant_address,
            audience_scope_ref=projection.audience_scope_ref,
            decision_cut_ref=projection.decision_cut_ref,
        ),
    )
    if decision is None:
        raise ValueError("participant exposure requires an authoritative policy decision at the exact state cut")
    expected = {
        "policy_ref": projection.projection_policy_ref,
        "revision": projection.projection_policy_revision,
        "decision_ref": projection.projection_policy_decision_ref,
        "decision_cut_ref": projection.decision_cut_ref,
    }
    mismatches = sorted(name for name, value in expected.items() if getattr(decision, name) != value)
    if mismatches:
        raise ValueError("projection policy decision has mismatched exact-cut coordinates: " + ", ".join(mismatches))
    for field_name in ("evidence_refs", "provenance_refs", "limitations"):
        values = getattr(decision, field_name)
        if not values or len(values) != len(set(values)) or any(not value for value in values):
            raise ValueError(f"projection policy decision requires unique non-empty {field_name}")
    if not set(decision.evidence_refs).issubset(projection.evidence_refs):
        raise ValueError("projection policy decision evidence must be carried by assurance")
    if not set(decision.provenance_refs).issubset(projection.provenance_refs):
        raise ValueError("projection policy decision provenance must be carried by assurance")
    return decision


def _selected_exposure_policy(
    projection: ParticipantExposureProjectionV2,
    resolvers: ParticipantExposureResolversV2,
) -> ParticipantExposurePolicyModel:
    selection = resolve_from_host(
        "apparatus",
        "participant exposure exact-cut apparatus resolution failed",
        lambda: resolvers.apparatus(
            implementation_selection_ref=projection.implementation_selection_ref,
            exposure_policy_ref=projection.exposure_policy_ref,
            decision_cut_ref=projection.decision_cut_ref,
        ),
    )
    if selection is None:
        raise ValueError("participant exposure apparatus refs did not resolve at the exact state cut")
    if selection.participant_address != projection.participant_address:
        raise ValueError("implementation selection participant_address must match the exposure projection")
    if selection.selected_decision_surface_mode != projection.decision_control_mode:
        raise ValueError("implementation selection decision-surface mode must match the exposure projection")
    policy = selection.exposure_policy
    if policy.policy_id != projection.exposure_policy_ref:
        raise ValueError("selected exposure policy identity must match exposure_policy_ref")
    if policy.policy_version is None or policy.policy_digest is None:
        raise ValueError("selected exposure policy requires an explicit version and digest")
    return policy


def _resolve_authorization(
    projection: ParticipantExposureProjectionV2,
    *,
    item_ref: str,
    authorization_record_ref: str,
    resolvers: ParticipantExposureResolversV2,
) -> ParticipantExposureAuthorizationRecordV2:
    authorization = resolve_from_host(
        "authorization",
        "participant exposure exact-cut authorization resolution failed",
        lambda: resolvers.authorization(
            authorization_record_ref=authorization_record_ref,
            item_ref=item_ref,
            decision_cut_ref=projection.decision_cut_ref,
        ),
    )
    if authorization is None:
        raise ValueError(f"exposure item {item_ref!r} has no authorization at the exact state cut")
    if authorization.authorization_record_ref != authorization_record_ref or authorization.item_ref != item_ref:
        raise ValueError("exposure authorization resolver returned a different record or item")
    return authorization


def _validate_authorization_coordinates(
    authorization: ParticipantExposureAuthorizationRecordV2,
    projection: ParticipantExposureProjectionV2,
    policy: ParticipantExposurePolicyModel,
) -> None:
    exact_coordinates = {
        "participant_address": projection.participant_address,
        "episode_id": projection.episode_id,
        "audience_scope_ref": projection.audience_scope_ref,
        "decision_epoch": projection.decision_epoch,
        "decision_cut_ref": projection.decision_cut_ref,
        "implementation_selection_ref": projection.implementation_selection_ref,
        "projection_policy_ref": projection.projection_policy_ref,
        "projection_policy_revision": projection.projection_policy_revision,
        "projection_policy_decision_ref": projection.projection_policy_decision_ref,
        "exposure_policy_ref": projection.exposure_policy_ref,
        "exposure_policy_version": policy.policy_version,
        "exposure_policy_digest": policy.policy_digest,
    }
    mismatches = sorted(
        name for name, expected in exact_coordinates.items() if getattr(authorization, name) != expected
    )
    if mismatches:
        raise ValueError(
            f"exposure authorization {authorization.item_ref!r} has mismatched exact-cut coordinates: "
            + ", ".join(mismatches)
        )


def _validate_authorization_visibility_and_policy(
    authorization: ParticipantExposureAuthorizationRecordV2,
    relation: Mapping[str, str],
    policy: ParticipantExposurePolicyModel,
) -> None:
    if relation.get(authorization.item_ref) not in _PARTICIPANT_VISIBLE_VIEW_DISPOSITIONS:
        raise ValueError(f"exposure item {authorization.item_ref!r} is not participant-visible at the state cut")
    if not _policy_permits_item(policy, authorization.item_ref):
        raise ValueError(f"selected exposure policy does not permit item {authorization.item_ref!r}")


def _validate_authorization_authority_refs(
    authorization: ParticipantExposureAuthorizationRecordV2,
) -> None:
    required_strings = (
        authorization.source_ref,
        authorization.source_layer_ref,
        authorization.visibility_basis_ref,
        authorization.operation_basis_ref,
        authorization.actor_ref,
        authorization.controller_ref,
        authorization.authority_basis_ref,
        authorization.backend_support_ref,
    )
    if any(not value for value in required_strings):
        raise ValueError("participant exposure authorization requires non-empty authority refs")


def _validate_authorization_ref_collections(
    authorization: ParticipantExposureAuthorizationRecordV2,
) -> None:
    for field_name in (
        "source_marking_definition_refs",
        "result_marking_definition_refs",
        "source_provenance_refs",
        "result_provenance_refs",
        "evidence_refs",
        "provenance_refs",
        "loss_and_limitations",
    ):
        values = getattr(authorization, field_name)
        if field_name in {"evidence_refs", "provenance_refs", "loss_and_limitations"} and not values:
            raise ValueError(f"exposure authorization {authorization.item_ref!r} requires {field_name}")
        if len(values) != len(set(values)) or any(not value for value in values):
            raise ValueError(f"exposure authorization {authorization.item_ref!r} has invalid {field_name}")


def _validate_authorization_transformation(
    authorization: ParticipantExposureAuthorizationRecordV2,
) -> None:
    if authorization.source_ref != authorization.item_ref and authorization.transformation_rule_ref is None:
        raise ValueError("derived exposure items require a transformation rule")
    if authorization.operation in {"masking", "redaction", "transformation"} and (
        authorization.transformation_rule_ref is None
    ):
        raise ValueError(f"{authorization.operation} exposure operations require a transformation rule")
    if authorization.operation == "redaction" and authorization.redaction_policy_ref is None:
        raise ValueError("redaction exposure operations require a redaction policy")
    if authorization.operation == "declassification" and authorization.declassification_basis_ref is None:
        raise ValueError("declassification exposure operations require a declassification basis")


def _validate_authorization_inheritance(
    authorization: ParticipantExposureAuthorizationRecordV2,
) -> None:
    if authorization.declassification_basis_ref is None and not set(
        authorization.source_marking_definition_refs
    ).issubset(authorization.result_marking_definition_refs):
        raise ValueError("derived exposure results must inherit source markings unless declassification is explicit")
    if authorization.declassification_basis_ref is None and not set(authorization.source_provenance_refs).issubset(
        authorization.result_provenance_refs
    ):
        raise ValueError("derived exposure results must inherit source provenance unless declassification is explicit")


def _validate_authorization_provenance_carriage(
    authorization: ParticipantExposureAuthorizationRecordV2,
) -> None:
    if not {*authorization.source_provenance_refs, *authorization.result_provenance_refs}.issubset(
        authorization.provenance_refs
    ):
        raise ValueError("source and result exposure provenance must be carried by provenance_refs")


def _validate_authorization_assurance_carriage(
    authorization: ParticipantExposureAuthorizationRecordV2,
    projection: ParticipantExposureProjectionV2,
) -> None:
    carried = (
        ("evidence", authorization.evidence_refs, projection.evidence_refs),
        ("provenance", authorization.provenance_refs, projection.provenance_refs),
        ("result markings", authorization.result_marking_definition_refs, projection.marking_definition_refs),
    )
    for label, refs, carrier in carried:
        if not set(refs).issubset(carrier):
            raise ValueError(f"exposure authorization {authorization.item_ref!r} {label} must be carried by assurance")


def _validate_authorization_redaction_policy(
    authorization: ParticipantExposureAuthorizationRecordV2,
    projection: ParticipantExposureProjectionV2,
) -> None:
    if (
        authorization.redaction_policy_ref is not None
        and authorization.redaction_policy_ref != projection.redaction_policy_ref
    ):
        raise ValueError("exposure authorization redaction policy must match the participant view")


def _validate_authorization(
    authorization: ParticipantExposureAuthorizationRecordV2,
    projection: ParticipantExposureProjectionV2,
    policy: ParticipantExposurePolicyModel,
    relation: Mapping[str, str],
) -> None:
    _validate_authorization_coordinates(authorization, projection, policy)
    _validate_authorization_visibility_and_policy(authorization, relation, policy)
    _validate_authorization_authority_refs(authorization)
    _validate_authorization_ref_collections(authorization)
    _validate_authorization_transformation(authorization)
    _validate_authorization_inheritance(authorization)
    _validate_authorization_provenance_carriage(authorization)
    _validate_authorization_assurance_carriage(authorization, projection)
    _validate_authorization_redaction_policy(authorization, projection)


def _binding_payload(
    authorization: ParticipantExposureAuthorizationRecordV2,
    projection: ParticipantExposureProjectionV2,
    policy: ParticipantExposurePolicyModel,
) -> dict[str, object]:
    return {
        "item_ref": authorization.item_ref,
        "authorization_record_ref": authorization.authorization_record_ref,
        "source_ref": authorization.source_ref,
        "source_layer_ref": authorization.source_layer_ref,
        "participant_address": projection.participant_address,
        "episode_id": projection.episode_id,
        "audience_scope_ref": authorization.audience_scope_ref,
        "decision_epoch": projection.decision_epoch,
        "decision_cut_ref": projection.decision_cut_ref,
        "visibility_basis_ref": authorization.visibility_basis_ref,
        "projection_policy_ref": projection.projection_policy_ref,
        "projection_policy_revision": projection.projection_policy_revision,
        "projection_policy_decision_ref": projection.projection_policy_decision_ref,
        "exposure_policy_ref": projection.exposure_policy_ref,
        "exposure_policy_version": policy.policy_version,
        "exposure_policy_digest": policy.policy_digest,
        "operation": authorization.operation,
        "operation_basis_ref": authorization.operation_basis_ref,
        "actor_ref": authorization.actor_ref,
        "controller_ref": authorization.controller_ref,
        "authority_basis_ref": authorization.authority_basis_ref,
        "source_marking_definition_refs": list(authorization.source_marking_definition_refs),
        "result_marking_definition_refs": list(authorization.result_marking_definition_refs),
        "source_provenance_refs": list(authorization.source_provenance_refs),
        "result_provenance_refs": list(authorization.result_provenance_refs),
        "declassification_basis_ref": authorization.declassification_basis_ref,
        "redaction_policy_ref": authorization.redaction_policy_ref,
        "transformation_rule_ref": authorization.transformation_rule_ref,
        "evidence_refs": list(authorization.evidence_refs),
        "provenance_refs": list(authorization.provenance_refs),
        "loss_and_limitations": list(authorization.loss_and_limitations),
    }


def project_participant_exposure_bindings_v2(
    relation: Mapping[str, str],
    projection: ParticipantExposureProjectionV2,
    entries: list[dict[str, object]],
    surface_affordances: list[str],
    resolvers: ParticipantExposureResolversV2,
) -> tuple[list[dict[str, object]], ParticipantExposurePolicyDecisionV2]:
    """Resolve every visible item against policy and authority at one exact cut."""

    policy_decision = _resolve_policy_decision(projection, resolvers)
    policy = _selected_exposure_policy(projection, resolvers)
    expected = _serialized_surface_refs(projection, entries, surface_affordances)
    if set(projection.exposure_assessments) != expected:
        raise ValueError("exposure_assessments must exactly cover every serialized participant-view ref")
    bindings = []
    for item_ref in sorted(expected):
        assessment = projection.exposure_assessments[item_ref]
        if assessment.item_ref != item_ref:
            raise ValueError(f"exposure assessment key {item_ref!r} must match its item_ref")
        if assessment.realization is not None:
            raise ValueError("v2 item exposure authorization must not be used as a surface delivery occurrence")
        authorization = _resolve_authorization(
            projection,
            item_ref=item_ref,
            authorization_record_ref=assessment.authorization_record_ref,
            resolvers=resolvers,
        )
        _validate_authorization(authorization, projection, policy, relation)
        bindings.append(_binding_payload(authorization, projection, policy))
    return bindings, policy_decision
