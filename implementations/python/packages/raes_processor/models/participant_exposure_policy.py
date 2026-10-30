"""Trusted policy and authorization validation for SEM-226 exposure."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from raes_contracts.contracts import ParticipantExposurePolicyModel
from raes_contracts.errors import OperationalError
from raes_contracts.operational_logging import foreign_failure_record, get_logger

from .participant_exposure_authority import (
    ParticipantExposureApparatusResolver,
    ParticipantExposureAuthorizationRecord,
    ParticipantExposureAuthorizationResolver,
    ParticipantExposurePolicyRevision,
    ParticipantExposureProjection,
    ParticipantExposureProjectionPolicyResolver,
)

_LOGGER = get_logger(__name__)


def resolve_from_host[T](resolver: str, message: str, call: Callable[[], T]) -> T:
    """Call a host resolver and return its value (H2 isolation).

    A resolver failure is logged one time with only the RAES frames. Then this
    function raises the value-free ``OperationalError(message)`` after the
    handler, so the error carries no host exception as its context.
    """

    try:
        return call()
    except Exception as exc:
        _LOGGER.exception("participant exposure %s resolver failed", resolver, exc_info=foreign_failure_record(exc))
    raise OperationalError(message)


def _resolved_projection_policy_revisions(
    projection: ParticipantExposureProjection,
    resolver: ParticipantExposureProjectionPolicyResolver,
) -> tuple[ParticipantExposurePolicyRevision, ...]:
    revisions = resolve_from_host(
        "projection-policy",
        "participant exposure projection-policy resolution failed",
        lambda: tuple(
            resolver(
                projection_policy_ref=projection.projection_policy_ref,
                participant_address=projection.participant_address,
                audience_scope_ref=projection.audience_scope_ref,
            )
        ),
    )
    if not revisions:
        raise ValueError("participant exposure requires an authoritative projection policy sequence")
    if any(revision.policy_ref != projection.projection_policy_ref for revision in revisions):
        raise ValueError("projection policy resolver returned a revision for a different policy")
    orders = [revision.effective_order for revision in revisions]
    if len(orders) != len(set(orders)):
        raise ValueError("projection policy revisions must have unique effective_order values")
    return revisions


def _effective_projection_policy(
    revisions: Sequence[ParticipantExposurePolicyRevision],
    *,
    observation_order: int,
    expected_revision: str,
) -> ParticipantExposurePolicyRevision:
    eligible = [revision for revision in revisions if revision.effective_order <= observation_order]
    if not eligible:
        raise ValueError("no projection policy revision is effective at observation_order")
    effective = max(eligible, key=lambda revision: revision.effective_order)
    if effective.revision != expected_revision:
        raise ValueError("surface projection policy must match the revision effective at observation_order")
    return effective


def _selected_exposure_policy(
    projection: ParticipantExposureProjection,
    resolver: ParticipantExposureApparatusResolver,
    *,
    observation_order: int,
) -> ParticipantExposurePolicyModel:
    selection = resolve_from_host(
        "apparatus",
        "participant exposure apparatus resolution failed",
        lambda: resolver(
            implementation_selection_ref=projection.implementation_selection_ref,
            exposure_policy_ref=projection.exposure_policy_ref,
            observation_order=observation_order,
        ),
    )
    if selection is None:
        raise ValueError("participant exposure apparatus refs did not resolve")
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
    *,
    authorization_record_ref: str,
    item_ref: str,
    resolver: ParticipantExposureAuthorizationResolver,
) -> ParticipantExposureAuthorizationRecord:
    if not item_ref or not authorization_record_ref:
        raise ValueError("participant exposure assessment requires item and authorization record refs")
    authorization = resolve_from_host(
        "authorization",
        "participant exposure authorization resolution failed",
        lambda: resolver(authorization_record_ref=authorization_record_ref, item_ref=item_ref),
    )
    if authorization is None:
        raise ValueError(f"exposure item {item_ref!r} has no authoritative authorization")
    if authorization.authorization_record_ref != authorization_record_ref:
        raise ValueError("exposure authorization resolver returned a different record")
    if authorization.item_ref != item_ref:
        raise ValueError("exposure authorization record item_ref does not match the requested item")
    return authorization


def _validate_authorization_scope(
    authorization: ParticipantExposureAuthorizationRecord,
    projection: ParticipantExposureProjection,
    policy: ParticipantExposurePolicyModel,
    *,
    observation_order: int,
    projection_policy_revision: str,
) -> None:
    exact_coordinates = {
        "participant_address": projection.participant_address,
        "episode_id": projection.episode_id,
        "audience_scope_ref": projection.audience_scope_ref,
        "implementation_selection_ref": projection.implementation_selection_ref,
        "projection_policy_ref": projection.projection_policy_ref,
        "projection_policy_revision": projection_policy_revision,
        "exposure_policy_ref": projection.exposure_policy_ref,
        "exposure_policy_version": policy.policy_version,
        "exposure_policy_digest": policy.policy_digest,
    }
    mismatches = sorted(
        field_name
        for field_name, expected in exact_coordinates.items()
        if getattr(authorization, field_name) != expected
    )
    if mismatches:
        raise ValueError(
            f"exposure authorization {authorization.item_ref!r} has mismatched coordinates: " + ", ".join(mismatches)
        )
    if authorization.effective_from_order > observation_order or (
        authorization.effective_through_order is not None and observation_order > authorization.effective_through_order
    ):
        raise ValueError(f"exposure authorization {authorization.item_ref!r} is not effective at observation_order")


def _validate_authorization_shape(authorization: ParticipantExposureAuthorizationRecord) -> None:
    required_strings = {
        "authorization_record_ref": authorization.authorization_record_ref,
        "item_ref": authorization.item_ref,
        "source_ref": authorization.source_ref,
        "source_layer_ref": authorization.source_layer_ref,
        "visibility_basis_ref": authorization.visibility_basis_ref,
        "operation_basis_ref": authorization.operation_basis_ref,
        "actor_ref": authorization.actor_ref,
        "controller_ref": authorization.controller_ref,
        "authority_basis_ref": authorization.authority_basis_ref,
        "backend_support_ref": authorization.backend_support_ref,
        "exposure_policy_version": authorization.exposure_policy_version,
        "exposure_policy_digest": authorization.exposure_policy_digest,
    }
    missing = sorted(name for name, value in required_strings.items() if not isinstance(value, str) or not value)
    if missing:
        raise ValueError("participant exposure authorization requires non-empty refs: " + ", ".join(missing))
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
        if len(values) != len(set(values)) or any(not isinstance(value, str) or not value for value in values):
            raise ValueError(f"exposure authorization {authorization.item_ref!r} has invalid {field_name}")


def _validate_exposure_operation(authorization: ParticipantExposureAuthorizationRecord) -> None:
    emitted_operations = {"projection", "masking", "redaction", "declassification", "disclosure", "transformation"}
    if authorization.operation not in emitted_operations:
        raise ValueError(f"exposure authorization {authorization.item_ref!r} operation cannot emit a surface item")
    _validate_transformation_requirements(authorization)
    _validate_exposure_inheritance(authorization)


def _validate_transformation_requirements(authorization: ParticipantExposureAuthorizationRecord) -> None:
    if authorization.source_ref != authorization.item_ref and authorization.transformation_rule_ref is None:
        raise ValueError(f"derived exposure item {authorization.item_ref!r} requires a transformation rule")
    transformed_operations = {"masking", "redaction", "transformation"}
    if authorization.operation in transformed_operations and authorization.transformation_rule_ref is None:
        raise ValueError(f"{authorization.operation} exposure operation requires a transformation rule")
    if authorization.operation == "redaction" and authorization.redaction_policy_ref is None:
        raise ValueError("redaction exposure operation requires a redaction policy")
    if authorization.operation == "declassification" and authorization.declassification_basis_ref is None:
        raise ValueError("declassification exposure operation requires a declassification basis")


def _validate_exposure_inheritance(authorization: ParticipantExposureAuthorizationRecord) -> None:
    if authorization.declassification_basis_ref is None and not set(
        authorization.source_marking_definition_refs
    ).issubset(authorization.result_marking_definition_refs):
        raise ValueError("derived exposure results must inherit source markings unless declassification is explicit")
    if authorization.declassification_basis_ref is None and not set(authorization.source_provenance_refs).issubset(
        authorization.result_provenance_refs
    ):
        raise ValueError("derived exposure results must inherit source provenance unless declassification is explicit")
    if not {*authorization.source_provenance_refs, *authorization.result_provenance_refs}.issubset(
        authorization.provenance_refs
    ):
        raise ValueError("source and result exposure provenance must be carried by provenance_refs")


def _policy_permits_item(policy: ParticipantExposurePolicyModel, item_ref: str) -> bool:
    allowed_refs = {*policy.disclosed_refs, *policy.tool_affordance_refs, *policy.visibility_scope_refs}
    return item_ref not in policy.withheld_refs and item_ref in allowed_refs
