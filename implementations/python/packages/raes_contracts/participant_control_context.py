"""Trusted-context agreement for ACT-620; no acquisition, release or execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import BinaryIO, Literal, TypeVar

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
from .contracts.participant_decision_surface_exposure_v2 import ParticipantDecisionSurfaceExposureBindingV2Model
from .contracts.participant_decision_surface_v2 import ParticipantDecisionSurfaceV2Model
from .diagnostics import Diagnostic, Severity
from .json_ingress import parse_bounded_json_object

AssetKey = tuple[str, str]
LifecycleKey = tuple[str, str, str]
LifecycleState = Literal["unpublished", "active", "replaced", "withdrawn"]
_ControlContextContract = TypeVar(
    "_ControlContextContract",
    ParticipantControlContextAssetModel,
    ParticipantControlContextRecordModel,
    ParticipantControlContextChangeModel,
)


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


def load_control_context_json(
    source: str | bytes | bytearray, model: type[_ControlContextContract]
) -> _ControlContextContract:
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


def _resolve(
    reference: ParticipantControlContextAssetReferenceModel,
    context: ParticipantControlContextValidationContext,
) -> ParticipantControlContextAssetModel | None:
    asset = context.assets.get((reference.asset_id, reference.asset_version))
    if asset is None or control_context_asset_reference(asset) != reference:
        return None
    return asset


def _active(
    reference: ParticipantControlContextAssetReferenceModel,
    context: ParticipantControlContextValidationContext,
    cut: ParticipantDecisionSurfaceStateCutModel,
) -> bool:
    return context.lifecycle.get((reference.asset_id, reference.asset_version, cut.cut_ref)) == "active"


def _ordered(
    context: ParticipantControlContextValidationContext,
    earlier: ParticipantDecisionSurfaceStateCutModel,
    later: ParticipantDecisionSurfaceStateCutModel,
) -> bool:
    return earlier == later or (context.cut_precedes is not None and context.cut_precedes(earlier, later) is True)


def _authorized(
    context: ParticipantControlContextValidationContext,
    operation: str,
    authority_ref: str,
    actor_ref: str,
    asset_ref: ParticipantControlContextAssetReferenceModel,
    cut: ParticipantDecisionSurfaceStateCutModel,
) -> bool:
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


class _AgreementFailure(ValueError):
    """A refused agreement; host resolver exceptions remain distinct."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise _AgreementFailure(code)


def validate_control_context_record(
    record: ParticipantControlContextRecordModel,
    context: ParticipantControlContextValidationContext,
) -> tuple[Diagnostic, ...]:
    """Check a selection claim; it never delivers content or grants action authority."""
    try:
        _validate_selection(record, context)
        _validate_selection_history(record, context)
        _validate_disposition(record, context)
    except _AgreementFailure as exc:
        return _failure(str(exc))
    return ()


def _validate_selection(
    record: ParticipantControlContextRecordModel,
    context: ParticipantControlContextValidationContext,
) -> None:
    scope_fields = (
        "scope_ref",
        "run_id",
        "participant_address",
        "episode_id",
        "episode_generation",
        "audience_scope_ref",
        "record_cut",
    )
    _require(all(getattr(record, name) == getattr(context, name) for name in scope_fields), "scope-mismatch")
    asset = _resolve(record.asset_ref, context)
    if asset is None:
        raise _AgreementFailure("version-conflict")
    roles = context.roles.get(record.selection_cut.cut_ref, frozenset())
    _require(
        record.participant_address in asset.participant_addresses or bool(roles.intersection(asset.role_refs)),
        "not-applicable",
    )
    _require(_active(record.asset_ref, context, record.selection_cut), "inactive-version")
    _require(
        _authorized(
            context,
            "select",
            record.selection_authority_ref,
            record.selected_by_ref,
            record.asset_ref,
            record.selection_cut,
        ),
        "unauthorized-selection",
    )


def _validate_selection_history(
    record: ParticipantControlContextRecordModel,
    context: ParticipantControlContextValidationContext,
) -> None:
    original = context.selections.get(record.selection_ref)
    if original is None:
        _require(record.disposition == "selected", "selection-unresolved")
    else:
        _require(
            record.disposition == "selected"
            or (original.disposition == "selected" and original.record_id != record.record_id),
            "selection-overwrite",
        )
        _require(
            all(getattr(record, name) == getattr(original, name) for name in _SELECTION_FIELDS),
            "selection-conflict",
        )
    _require(_ordered(context, record.selection_cut, record.record_cut), "incomparable-cuts")


def _validate_disposition(
    record: ParticipantControlContextRecordModel,
    context: ParticipantControlContextValidationContext,
) -> None:
    if record.disposition == "selected":
        _require(record.record_cut == record.selection_cut, "selection-cut-mismatch")
    elif record.disposition == "withheld":
        _require(
            record.withholding_authority_ref is not None
            and _authorized(
                context,
                "withhold",
                record.withholding_authority_ref,
                record.selected_by_ref,
                record.asset_ref,
                record.record_cut,
            ),
            "unauthorized-withholding",
        )
    else:
        _validate_exposure(record, context)


def _validate_exposure(
    record: ParticipantControlContextRecordModel,
    context: ParticipantControlContextValidationContext,
) -> None:
    surface = context.surfaces.get(record.surface_id) if record.surface_id is not None else None
    if surface is None:
        raise _AgreementFailure("exposure-unresolved")
    # Revalidate the resolved carrier rather than trusting unchecked model_copy updates.
    surface = ParticipantDecisionSurfaceV2Model.model_validate(surface.model_dump())
    view, assurance = surface.participant_view, surface.assurance
    _require(
        (view.participant_address, view.episode_id, assurance.audience_scope_ref)
        == (record.participant_address, record.episode_id, record.audience_scope_ref)
        and view.surface_id == record.surface_id
        and record.item_ref in view.visible_context_refs,
        "exposure-scope-mismatch",
    )
    bindings = [binding for binding in assurance.exposure_bindings if binding.item_ref == record.item_ref]
    _require(
        len(bindings) == 1 and bindings[0].source_ref == "urn:" + record.asset_ref.asset_digest,
        "exposure-source-mismatch",
    )
    binding = bindings[0]
    _validate_context_view(record, context, surface, binding)
    _validate_exposure_authority(record, context, surface, binding)
    if record.disposition == "delivered":
        _validate_delivery(record, context, surface, binding)


def _validate_context_view(
    record: ParticipantControlContextRecordModel,
    context: ParticipantControlContextValidationContext,
    surface: ParticipantDecisionSurfaceV2Model,
    binding: ParticipantDecisionSurfaceExposureBindingV2Model,
) -> None:
    view, assurance = surface.participant_view, surface.assurance
    context_view = context.context_views.get(view.context_view_ref)
    if context_view is None:
        raise _AgreementFailure("context-view-unresolved")
    context_view = ParticipantContextViewModel.model_validate(context_view.model_dump())
    _require(
        (
            context_view.participant_address,
            context_view.episode_id,
            context_view.audience_scope,
            context_view.view_ref,
            context_view.payload_ref,
            context_view.visibility_projection_ref,
            context_view.redaction_policy_ref,
        )
        == (
            record.participant_address,
            record.episode_id,
            "participant_visible",
            view.context_view_ref,
            record.item_ref,
            assurance.visibility_projection_ref,
            view.redaction_policy_ref,
        )
        and set(context_view.marking_definition_refs).issubset(view.marking_definition_refs),
        "context-view-mismatch",
    )
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
    _require(
        len(sources) == 1 and context_view.transformation.transformation_rule_ref == binding.transformation_rule_ref,
        "context-source-mismatch",
    )


def _validate_exposure_authority(
    record: ParticipantControlContextRecordModel,
    context: ParticipantControlContextValidationContext,
    surface: ParticipantDecisionSurfaceV2Model,
    binding: ParticipantDecisionSurfaceExposureBindingV2Model,
) -> None:
    derivation_cut = surface.assurance.derivation_anchor.state_cut
    _require(
        _ordered(context, record.selection_cut, derivation_cut)
        and _ordered(context, derivation_cut, record.record_cut),
        "incomparable-cuts",
    )
    cuts = (derivation_cut, record.record_cut)
    _require(all(_active(record.asset_ref, context, cut) for cut in cuts), "inactive-version")
    _require(
        all(
            _authorized(context, "disclose", binding.authority_basis_ref, binding.actor_ref, record.asset_ref, cut)
            for cut in cuts
        ),
        "unauthorized-disclosure",
    )


def _validate_delivery(
    record: ParticipantControlContextRecordModel,
    context: ParticipantControlContextValidationContext,
    surface: ParticipantDecisionSurfaceV2Model,
    binding: ParticipantDecisionSurfaceExposureBindingV2Model,
) -> None:
    delivery = surface.delivery
    if surface.surface_state != "delivered" or delivery is None:
        raise _AgreementFailure("delivery-mismatch")
    _require(
        (delivery.delivery_ref, delivery.delivery_cut_ref) == (record.delivery_ref, record.record_cut.cut_ref),
        "delivery-mismatch",
    )
    _require(
        _authorized(
            context,
            "deliver",
            delivery.delivery_authorization_ref,
            binding.actor_ref,
            record.asset_ref,
            record.record_cut,
        ),
        "unauthorized-delivery",
    )


def validate_control_context_change(
    change: ParticipantControlContextChangeModel,
    context: ParticipantControlContextValidationContext,
) -> tuple[Diagnostic, ...]:
    """Check a lifecycle transition without mutating a catalog or its history."""
    try:
        _require(change.scope_ref == context.scope_ref and change.effective_cut == context.record_cut, "scope-mismatch")
        asset = _resolve(change.asset_ref, context)
        if asset is None:
            raise _AgreementFailure("version-conflict")
        state = context.lifecycle.get((asset.asset_id, asset.asset_version, change.effective_cut.cut_ref))
        expected = "unpublished" if change.operation == "publish" else "active"
        _require(state == expected, "invalid-lifecycle")
        _require(
            change.operation != "publish" or change.authority_ref == asset.publication_authority_ref,
            "publication-authority-mismatch",
        )
        if change.successor_ref is not None:
            _require(
                _resolve(change.successor_ref, context) is not None
                and _active(change.successor_ref, context, change.effective_cut),
                "successor-unresolved",
            )
        _require(
            _authorized(
                context,
                change.operation,
                change.authority_ref,
                change.actor_ref,
                change.asset_ref,
                change.effective_cut,
            ),
            "unauthorized-change",
        )
    except _AgreementFailure as exc:
        return _failure(str(exc))
    return ()
