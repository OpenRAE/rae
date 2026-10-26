"""Trusted-context agreement for ACT-620; no acquisition, release or execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import BinaryIO, Literal

from .associated_artifacts import AssociatedArtifactValidationLimits, validate_associated_artifact_manifest
from .contracts.associated_artifacts import AssociatedArtifactManifestModel
from .contracts.participant_context import ParticipantContextViewModel
from .contracts.participant_control_context import (
    ParticipantControlContextAssetModel,
    ParticipantControlContextAssetReferenceModel,
    ParticipantControlContextChangeModel,
    ParticipantControlContextRecordModel,
)
from .contracts.participant_decision_state_cut import ParticipantDecisionSurfaceStateCutModel
from .contracts.participant_decision_surface_v2 import ParticipantDecisionSurfaceV2Model
from .diagnostics import Diagnostic, Severity
from .json_ingress import parse_bounded_json_object

AssetKey = tuple[str, str]
LifecycleKey = tuple[str, str, str]
LifecycleState = Literal["unpublished", "active", "replaced", "withdrawn"]


@dataclass(frozen=True)
class ParticipantControlContextContentBinding:
    manifest: AssociatedArtifactManifestModel
    parent: object
    artifact_readers: Mapping[str, BinaryIO]
    limits: AssociatedArtifactValidationLimits | None = None


@dataclass(frozen=True)
class ParticipantControlContextAuthorityRequest:
    """All coordinates a trusted host must authorize together."""

    operation: str
    authority_ref: str
    actor_ref: str
    asset_ref: ParticipantControlContextAssetReferenceModel
    scope_ref: str
    run_id: str
    participant_address: str
    episode_id: str
    episode_generation: int
    audience_scope_ref: str
    state_cut: ParticipantDecisionSurfaceStateCutModel


@dataclass(frozen=True)
class ParticipantControlContextValidationContext:
    """Host-owned snapshot; portable records cannot establish these facts."""

    scope_ref: str
    run_id: str
    participant_address: str
    episode_id: str
    episode_generation: int
    audience_scope_ref: str
    record_cut: ParticipantDecisionSurfaceStateCutModel
    assets: Mapping[AssetKey, ParticipantControlContextAssetModel]
    lifecycle: Mapping[LifecycleKey, LifecycleState]
    roles: Mapping[str, frozenset[str]]
    authorize: Callable[[ParticipantControlContextAuthorityRequest], bool]
    selections: Mapping[str, ParticipantControlContextRecordModel] = field(default_factory=dict)
    surfaces: Mapping[str, ParticipantDecisionSurfaceV2Model] = field(default_factory=dict)
    context_views: Mapping[str, ParticipantContextViewModel] = field(default_factory=dict)
    content_binding: ParticipantControlContextContentBinding | None = None
    cut_precedes: (
        Callable[[ParticipantDecisionSurfaceStateCutModel, ParticipantDecisionSurfaceStateCutModel], bool] | None
    ) = None


def control_context_asset_reference(
    asset: ParticipantControlContextAssetModel,
) -> ParticipantControlContextAssetReferenceModel:
    from .satisfiability import canonical_contract_digest

    return ParticipantControlContextAssetReferenceModel(
        asset_id=asset.asset_id, asset_version=asset.asset_version, asset_digest=canonical_contract_digest(asset)
    )


def load_control_context_json(source: str | bytes | bytearray, model: type):
    """Use shared duplicate-rejecting, depth- and byte-bounded JSON ingress."""
    if model not in (
        ParticipantControlContextAssetModel,
        ParticipantControlContextRecordModel,
        ParticipantControlContextChangeModel,
    ):
        raise ValueError("unsupported control-context contract")
    return model.model_validate(parse_bounded_json_object(source, max_bytes=1024 * 1024, max_depth=32))


def _failure(code: str) -> tuple[Diagnostic, ...]:
    return (
        Diagnostic(
            code="control-context." + code,
            domain="participant-control-context",
            address="#",
            message="Participant control-context agreement failed: " + code,
            severity=Severity.ERROR,
        ),
    )


def _resolve(reference, context):
    asset = context.assets.get((reference.asset_id, reference.asset_version))
    if asset is None or control_context_asset_reference(asset) != reference:
        return None
    return asset


def _active(reference, context, cut):
    return context.lifecycle.get((reference.asset_id, reference.asset_version, cut.cut_ref)) == "active"


def _ordered(context, earlier, later):
    return earlier == later or (context.cut_precedes is not None and context.cut_precedes(earlier, later) is True)


def _authorized(context, operation, authority_ref, actor_ref, asset_ref, cut):
    request = ParticipantControlContextAuthorityRequest(
        operation,
        authority_ref,
        actor_ref,
        asset_ref,
        context.scope_ref,
        context.run_id,
        context.participant_address,
        context.episode_id,
        context.episode_generation,
        context.audience_scope_ref,
        cut,
    )
    # Resolver failures are infrastructure failures, never permission or safe refusal.
    return context.authorize(request) is True


def validate_control_context_asset(
    asset: ParticipantControlContextAssetModel,
    *,
    context: ParticipantControlContextValidationContext,
    manifest: AssociatedArtifactManifestModel,
    parent: object,
    artifact_readers: Mapping[str, BinaryIO],
    limits: AssociatedArtifactValidationLimits | None = None,
) -> tuple[Diagnostic, ...]:
    """Bind the exact registered descriptor to its supported parent and actual bytes."""
    if _resolve(control_context_asset_reference(asset), context) != asset:
        return _failure("version-conflict")
    if manifest.artifacts.get(asset.content.artifact_id) != asset.content:
        return _failure("content-descriptor-mismatch")
    return validate_associated_artifact_manifest(
        manifest, parent=parent, artifact_readers=artifact_readers, limits=limits
    )


_SELECTION_FIELDS = (
    "selection_ref",
    "scope_ref",
    "run_id",
    "participant_address",
    "episode_id",
    "episode_generation",
    "audience_scope_ref",
    "asset_ref",
    "selected_by_ref",
    "selection_authority_ref",
    "selection_cut",
)


def validate_control_context_record(
    record: ParticipantControlContextRecordModel,
    context: ParticipantControlContextValidationContext,
) -> tuple[Diagnostic, ...]:
    """Check a selection claim; it never delivers content or grants action authority."""
    for name in (
        "scope_ref",
        "run_id",
        "participant_address",
        "episode_id",
        "episode_generation",
        "audience_scope_ref",
        "record_cut",
    ):
        if getattr(record, name) != getattr(context, name):
            return _failure("scope-mismatch")
    asset = _resolve(record.asset_ref, context)
    if asset is None:
        return _failure("version-conflict")
    roles = context.roles.get(record.selection_cut.cut_ref, frozenset())
    if record.participant_address not in asset.participant_addresses and not roles.intersection(asset.role_refs):
        return _failure("not-applicable")
    if not _active(record.asset_ref, context, record.selection_cut):
        return _failure("inactive-version")
    if not _authorized(
        context,
        "select",
        record.selection_authority_ref,
        record.selected_by_ref,
        record.asset_ref,
        record.selection_cut,
    ):
        return _failure("unauthorized-selection")
    original = context.selections.get(record.selection_ref)
    if record.disposition != "selected" and original is None:
        return _failure("selection-unresolved")
    if (
        original is not None
        and record.disposition != "selected"
        and (original.disposition != "selected" or original.record_id == record.record_id)
    ):
        return _failure("selection-overwrite")
    if original is not None and any(getattr(record, name) != getattr(original, name) for name in _SELECTION_FIELDS):
        return _failure("selection-conflict")
    if not _ordered(context, record.selection_cut, record.record_cut):
        return _failure("incomparable-cuts")
    if record.disposition == "selected":
        if record.record_cut != record.selection_cut:
            return _failure("selection-cut-mismatch")
        return ()
    if record.disposition == "withheld":
        if not _authorized(
            context,
            "withhold",
            record.withholding_authority_ref,
            record.selected_by_ref,
            record.asset_ref,
            record.record_cut,
        ):
            return _failure("unauthorized-withholding")
        return ()
    return _validate_exposure(record, context)


def _validate_exposure(record, context):
    surface = context.surfaces.get(record.surface_id)
    if surface is None:
        return _failure("exposure-unresolved")
    # Revalidate the resolved carrier rather than trusting unchecked model_copy updates.
    surface = ParticipantDecisionSurfaceV2Model.model_validate(surface.model_dump())
    view, assurance = surface.participant_view, surface.assurance
    if (
        (view.participant_address, view.episode_id, assurance.audience_scope_ref)
        != (record.participant_address, record.episode_id, record.audience_scope_ref)
        or view.surface_id != record.surface_id
        or record.item_ref not in view.visible_context_refs
    ):
        return _failure("exposure-scope-mismatch")
    bindings = [binding for binding in assurance.exposure_bindings if binding.item_ref == record.item_ref]
    if len(bindings) != 1 or bindings[0].source_ref != "urn:" + record.asset_ref.asset_digest:
        return _failure("exposure-source-mismatch")
    binding = bindings[0]
    context_view = context.context_views.get(view.context_view_ref)
    if context_view is None:
        return _failure("context-view-unresolved")
    context_view = ParticipantContextViewModel.model_validate(context_view.model_dump())
    if (
        context_view.participant_address != record.participant_address
        or context_view.episode_id != record.episode_id
        or context_view.audience_scope != "participant_visible"
        or context_view.view_ref != view.context_view_ref
        or context_view.payload_ref != record.item_ref
        or context_view.visibility_projection_ref != assurance.visibility_projection_ref
        or context_view.redaction_policy_ref != view.redaction_policy_ref
        or not set(context_view.marking_definition_refs).issubset(view.marking_definition_refs)
    ):
        return _failure("context-view-mismatch")
    sources = [
        source
        for source in context_view.source_layers
        if (
            source.source_layer == "participant_control_context_asset"
            and source.ref == binding.source_ref
            and source.source_id == binding.source_layer_ref
            and source.source_id in context_view.transformation.input_source_ids
        )
    ]
    if len(sources) != 1 or context_view.transformation.transformation_rule_ref != binding.transformation_rule_ref:
        return _failure("context-source-mismatch")
    derivation_cut = assurance.derivation_anchor.state_cut
    if not _ordered(context, record.selection_cut, derivation_cut) or not _ordered(
        context, derivation_cut, record.record_cut
    ):
        return _failure("incomparable-cuts")
    if not _active(record.asset_ref, context, derivation_cut) or not _active(
        record.asset_ref, context, record.record_cut
    ):
        return _failure("inactive-version")
    if not _authorized(
        context, "disclose", binding.authority_basis_ref, binding.actor_ref, record.asset_ref, derivation_cut
    ):
        return _failure("unauthorized-disclosure")
    if not _authorized(
        context, "disclose", binding.authority_basis_ref, binding.actor_ref, record.asset_ref, record.record_cut
    ):
        return _failure("unauthorized-disclosure")
    if record.disposition == "delivered":
        delivery = surface.delivery
        if (
            surface.surface_state != "delivered"
            or delivery is None
            or (delivery.delivery_ref != record.delivery_ref or delivery.delivery_cut_ref != record.record_cut.cut_ref)
        ):
            return _failure("delivery-mismatch")
        if not _authorized(
            context,
            "deliver",
            delivery.delivery_authorization_ref,
            binding.actor_ref,
            record.asset_ref,
            record.record_cut,
        ):
            return _failure("unauthorized-delivery")
    return ()


def validate_control_context_change(
    change: ParticipantControlContextChangeModel,
    context: ParticipantControlContextValidationContext,
) -> tuple[Diagnostic, ...]:
    """Check a lifecycle transition without mutating a catalog or its history."""
    if change.scope_ref != context.scope_ref or change.effective_cut != context.record_cut:
        return _failure("scope-mismatch")
    asset = _resolve(change.asset_ref, context)
    if asset is None:
        return _failure("version-conflict")
    state = context.lifecycle.get((asset.asset_id, asset.asset_version, change.effective_cut.cut_ref))
    expected = "unpublished" if change.operation == "publish" else "active"
    if state != expected:
        return _failure("invalid-lifecycle")
    if change.operation == "publish" and change.authority_ref != asset.publication_authority_ref:
        return _failure("publication-authority-mismatch")
    if change.successor_ref is not None:
        if _resolve(change.successor_ref, context) is None or not _active(
            change.successor_ref, context, change.effective_cut
        ):
            return _failure("successor-unresolved")
    if not _authorized(
        context, change.operation, change.authority_ref, change.actor_ref, change.asset_ref, change.effective_cut
    ):
        return _failure("unauthorized-change")
    return ()
