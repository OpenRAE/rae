"""Behavioral agreement checks for participant control-context assets."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest
from pydantic import ValidationError
from raes import parse_sdl
from raes_contracts.associated_artifacts import associated_artifact_set_digest
from raes_contracts.contracts import AssociatedArtifactManifestModel, ParticipantDecisionSurfaceSequenceCutModel

PAYLOAD = b"Do not disclose customer records.\n"


def _asset(version="one", content=PAYLOAD):
    from raes_contracts.contracts.participant_control_context import ParticipantControlContextAssetModel

    return ParticipantControlContextAssetModel.model_validate(
        {
            "schema_version": "participant-control-context-asset/v1",
            "asset_id": "privacy-instruction",
            "asset_version": version,
            "kind": "instruction",
            "content": {
                "artifact_id": "instruction-" + version,
                "role": "documentation",
                "media_type": "text/plain",
                "uri": "urn:sha256:" + sha256(content).hexdigest(),
                "checksum": {"algorithm": "sha256", "value": sha256(content).hexdigest()},
                "size_bytes": len(content),
                "created_at": "2026-10-26T00:00:00Z",
                "source": "publisher-reference",
                "sensitivity": "restricted",
            },
            "participant_addresses": [],
            "role_refs": ["roles.analyst"],
            "publication_authority_ref": "authorities.publisher",
            "retention_policy_ref": "retention.governed",
            "provenance_refs": ["provenance.authoring"],
        }
    )


def _cut(index=0):
    return ParticipantDecisionSurfaceSequenceCutModel(
        cut_kind="sequence_prefix",
        cut_ref=f"cuts.{index}",
        history_domain="participant_episode_lifecycle",
        order_model="control_plane_order",
        anchor_event_ref=f"events.{index}",
        anchor_order=index,
        history_prefix_length=index + 1,
    )


def _context(asset=None, participant="participants.red", cut=None):
    from raes_contracts.participant_control_context import ParticipantControlContextValidationContext

    asset = asset or _asset()
    cut = cut or _cut()
    return ParticipantControlContextValidationContext(
        scope_ref="catalog.training",
        run_id="run-1",
        participant_address=participant,
        episode_id="episode-1",
        episode_generation=0,
        audience_scope_ref="audiences.red",
        record_cut=cut,
        assets={(asset.asset_id, asset.asset_version): asset},
        lifecycle={(asset.asset_id, asset.asset_version, cut.cut_ref): "active"},
        roles={cut.cut_ref: frozenset({"roles.analyst"})},
        authorize=lambda request: (
            request.authority_ref.startswith("authorities.")
            or request.authority_ref in {"authority.participant", "delivery-authorizations.red.episode-1.epoch-0"}
        ),
    )


def _record(asset=None, **overrides):
    from raes_contracts.contracts.participant_control_context import ParticipantControlContextRecordModel
    from raes_contracts.participant_control_context import control_context_asset_reference

    asset = asset or _asset()
    payload = {
        "schema_version": "participant-control-context-record/v1",
        "record_id": "record.selected",
        "selection_ref": "selections.red",
        "scope_ref": "catalog.training",
        "run_id": "run-1",
        "participant_address": "participants.red",
        "episode_id": "episode-1",
        "episode_generation": 0,
        "audience_scope_ref": "audiences.red",
        "asset_ref": control_context_asset_reference(asset).model_dump(),
        "selected_by_ref": "actors.director",
        "selection_authority_ref": "authorities.select",
        "selection_cut": _cut().model_dump(),
        "record_cut": _cut().model_dump(),
        "disposition": "selected",
        "evidence_refs": ["evidence.selection"],
        "provenance_refs": ["provenance.selection"],
    }
    payload.update(overrides)
    if "record_id" not in overrides:
        payload["record_id"] = "record." + payload["disposition"]
    return ParticipantControlContextRecordModel.model_validate(payload)


def _manifest(asset):
    manifest = AssociatedArtifactManifestModel(
        schema_version="associated-artifact-manifest/v1",
        manifest_id="instruction-set",
        manifest_version="one",
        canonicalization_profile="associated-artifact-set/v1",
        scope="scenario",
        parent_ref={"ref_kind": "scenario", "ref_id": "training"},
        artifacts={asset.content.artifact_id: asset.content},
        set_digest="sha256:" + "0" * 64,
    )
    return manifest.model_copy(update={"set_digest": associated_artifact_set_digest(manifest)})


def test_exact_asset_reuses_full_manifest_parent_and_byte_validation():
    from raes_contracts.participant_control_context import validate_control_context_asset

    asset = _asset()
    assert (
        validate_control_context_asset(
            asset,
            context=_context(asset),
            manifest=_manifest(asset),
            parent=parse_sdl("name: training\nversion: 1.0.0\n"),
            artifact_readers={asset.content.artifact_id: BytesIO(PAYLOAD)},
        )
        == ()
    )


@pytest.mark.parametrize("bad_parent", [False, True])
def test_stale_content_or_wrong_parent_is_rejected(bad_parent):
    from raes_contracts.participant_control_context import validate_control_context_asset

    asset = _asset()
    diagnostics = validate_control_context_asset(
        asset,
        context=_context(asset),
        manifest=_manifest(asset),
        parent=parse_sdl(f"name: {'wrong' if bad_parent else 'training'}\nversion: 1.0.0\n"),
        artifact_readers={asset.content.artifact_id: BytesIO(PAYLOAD if bad_parent else b"x" * len(PAYLOAD))},
    )
    assert diagnostics
    assert not any(PAYLOAD.decode().strip() in diagnostic.message for diagnostic in diagnostics)


def test_one_immutable_instruction_is_selected_for_two_participants():
    from raes_contracts.participant_control_context import validate_control_context_record

    for participant in ("participants.red", "participants.blue"):
        record = _record(participant_address=participant)
        assert validate_control_context_record(record, _context(participant=participant)) == ()


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "other-run"),
        ("participant_address", "participants.wrong"),
        ("episode_id", "other-episode"),
        ("episode_generation", 1),
        ("audience_scope_ref", "audiences.operator"),
        ("scope_ref", "other-catalog"),
        ("record_cut", _cut(1).model_dump()),
        ("selection_authority_ref", "forged"),
    ],
)
def test_selection_rejects_wrong_scope_recipient_or_authority(field, value):
    from raes_contracts.participant_control_context import validate_control_context_record

    assert validate_control_context_record(_record(**{field: value}), _context())


def test_unknown_version_conflicting_descriptor_and_wrong_role_are_rejected():
    from raes_contracts.participant_control_context import validate_control_context_record

    assert validate_control_context_record(_record(_asset("unknown")), _context())
    assert validate_control_context_record(_record(_asset(content=b"forged")), _context())
    assert validate_control_context_record(_record(), replace(_context(), roles={"cuts.0": frozenset({"roles.other"})}))


def test_withholding_preserves_selection_without_fabricating_delivery():
    from raes_contracts.participant_control_context import validate_control_context_record

    selected = _record()
    withheld = _record(disposition="withheld", withholding_authority_ref="authorities.withhold")
    context = replace(_context(), selections={selected.selection_ref: selected})
    assert validate_control_context_record(withheld, context) == ()
    assert withheld.delivery_ref is None
    assert withheld.asset_ref == selected.asset_ref
    assert validate_control_context_record(
        withheld, replace(context, authorize=lambda request: request.operation != "withhold")
    )


@pytest.mark.parametrize("field,value", [("content_text", "private instruction"), ("kind", "executable")])
def test_private_content_and_unknown_kinds_are_not_portable_fields(field, value):
    from raes_contracts.contracts.participant_control_context import ParticipantControlContextAssetModel

    payload = {**_asset().model_dump(), field: value}
    with pytest.raises(ValidationError):
        ParticipantControlContextAssetModel.model_validate(payload)


def _change(operation="withdraw", **overrides):
    from raes_contracts.contracts.participant_control_context import ParticipantControlContextChangeModel
    from raes_contracts.participant_control_context import control_context_asset_reference

    payload = {
        "schema_version": "participant-control-context-change/v1",
        "change_id": "changes.1",
        "scope_ref": "catalog.training",
        "asset_ref": control_context_asset_reference(_asset()).model_dump(),
        "operation": operation,
        "actor_ref": "actors.director",
        "authority_ref": "authorities.publisher" if operation == "publish" else "authorities.change",
        "effective_cut": _cut().model_dump(),
        "reason_ref": "reasons.reviewed",
        "evidence_refs": ["evidence.change"],
        "provenance_refs": ["provenance.change"],
    }
    payload.update(overrides)
    return ParticipantControlContextChangeModel.model_validate(payload)


@pytest.mark.parametrize("operation,state", [("publish", "unpublished"), ("withdraw", "active"), ("replace", "active")])
def test_lifecycle_changes_require_exact_operation_authority(operation, state):
    from raes_contracts.participant_control_context import (
        control_context_asset_reference,
        validate_control_context_change,
    )

    successor = _asset("two", b"Revised instruction.\n")
    changes = (
        {"successor_ref": control_context_asset_reference(successor).model_dump()} if operation == "replace" else {}
    )
    change = _change(operation, **changes)
    context = replace(
        _context(),
        assets={**_context().assets, (successor.asset_id, successor.asset_version): successor},
        lifecycle={("privacy-instruction", "one", "cuts.0"): state, ("privacy-instruction", "two", "cuts.0"): "active"},
    )
    assert validate_control_context_change(change, context) == ()
    assert validate_control_context_change(change, replace(context, authorize=lambda request: False))
    assert validate_control_context_change(change, replace(context, lifecycle={}))
    assert validate_control_context_change(change, replace(context, record_cut=_cut(1)))


def test_mid_episode_revision_retains_prior_selection_and_withdrawal_history():
    from raes_contracts.participant_control_context import validate_control_context_record

    old = _record()
    revised_asset = _asset("two", b"Revised instruction.\n")
    current = _record(revised_asset, selection_cut=_cut(1).model_dump(), record_cut=_cut(1).model_dump())
    context = _context(revised_asset, cut=_cut(1))
    assert validate_control_context_record(current, context) == ()
    assert validate_control_context_record(old, _context()) == ()
    assert old.asset_ref.asset_version == "one"
    assert current.asset_ref.asset_version == "two"
    assert validate_control_context_record(
        _record(selection_cut=_cut(1).model_dump(), record_cut=_cut(1).model_dump()),
        replace(_context(cut=_cut(1)), lifecycle={("privacy-instruction", "one", "cuts.1"): "withdrawn"}),
    )


def _surface():
    from raes_contracts.contracts import ParticipantDecisionSurfaceV2Model
    from raes_contracts.participant_control_context import control_context_asset_reference

    fixture = (
        Path(__file__).resolve().parents[3]
        / "contracts/fixtures/control-plane/participant-decision-surface-v2/valid/delivered-initial.json"
    )
    payload = json.loads(fixture.read_text())
    binding = payload["assurance"]["exposure_bindings"][0]
    binding["source_ref"] = "urn:" + control_context_asset_reference(_asset()).asset_digest
    binding["transformation_rule_ref"] = "transformations.redacted-instruction"
    binding["source_layer_ref"] = "source.instruction"
    payload["delivery"]["delivery_cut_ref"] = "cuts.2"
    return ParticipantDecisionSurfaceV2Model.model_validate(payload)


def _delivered_context():
    surface = _surface()
    context = _context()
    asset = _asset()
    return replace(
        context,
        record_cut=_cut(2),
        cut_precedes=lambda earlier, later: (
            (earlier.cut_ref, later.cut_ref)
            in {
                ("cuts.0", "cuts.2"),
                ("cuts.0", surface.assurance.derivation_anchor.state_cut.cut_ref),
                (surface.assurance.derivation_anchor.state_cut.cut_ref, "cuts.2"),
            }
        ),
        selections={"selections.red": _record()},
        surfaces={surface.participant_view.surface_id: surface},
        context_views={surface.participant_view.context_view_ref: _context_view()},
        lifecycle={
            **context.lifecycle,
            (asset.asset_id, asset.asset_version, "cuts.2"): "active",
            (asset.asset_id, asset.asset_version, surface.assurance.derivation_anchor.state_cut.cut_ref): "active",
        },
    )


def _context_view():
    from raes_contracts.contracts import ParticipantContextViewModel

    fixture = (
        Path(__file__).resolve().parents[3]
        / "contracts/fixtures/control-plane/participant-context-view-v1/valid/network-posture-context.json"
    )
    payload = json.loads(fixture.read_text())
    surface = _surface()
    binding = surface.assurance.exposure_bindings[0]
    payload.update(
        participant_address="participants.red",
        episode_id="episode-1",
        view_ref=surface.participant_view.context_view_ref,
        payload_ref=binding.item_ref,
        visibility_projection_ref=surface.assurance.visibility_projection_ref,
        redaction_policy_ref=surface.participant_view.redaction_policy_ref,
        marking_definition_refs=surface.participant_view.marking_definition_refs,
        derived_from_refs=[binding.source_ref],
        source_layers=[
            {
                "source_id": "source.instruction",
                "source_layer": "participant_control_context_asset",
                "ref": binding.source_ref,
                "temporal_relation": "same_observation_point",
                "evidence_refs": ["evidence.asset"],
                "provenance_refs": ["provenance.asset"],
            }
        ],
    )
    payload["transformation"].update(
        input_source_ids=["source.instruction"],
        transformation_rule_ref=binding.transformation_rule_ref,
    )
    return ParticipantContextViewModel.model_validate(payload)


def _exposed(disposition="delivered", **overrides):
    surface = _surface()
    fields = {
        "disposition": disposition,
        "record_cut": _cut(2).model_dump(),
        "surface_id": surface.participant_view.surface_id,
        "item_ref": surface.participant_view.visible_context_refs[0],
    }
    if disposition == "delivered":
        fields["delivery_ref"] = surface.delivery.delivery_ref
    fields.update(overrides)
    return _record(**fields)


def test_delivery_uses_existing_trusted_surface_and_preserves_source_transform():
    from raes_contracts.participant_control_context import validate_control_context_record

    context = _delivered_context()
    assert validate_control_context_record(_exposed("disclosed"), context) == ()
    assert validate_control_context_record(_exposed(), context) == ()
    assert _record().delivery_ref is None
    assert _exposed("disclosed").delivery_ref is None
    assert _surface().assurance.exposure_bindings[0].source_ref.startswith("urn:sha256:")
    assert _exposed().item_ref != _asset().content.uri


@pytest.mark.parametrize(
    "defect",
    [
        "withdrawn",
        "unauthorized",
        "wrong-surface",
        "undelivered",
        "wrong-item",
        "forged-delivery",
        "changed-selection",
        "wrong-context",
    ],
)
def test_delivery_rechecks_exact_scope_authority_lifecycle_and_occurrence(defect):
    from raes_contracts.participant_control_context import validate_control_context_record

    context = _delivered_context()
    record = _exposed()
    surface = _surface()
    if defect == "withdrawn":
        context = replace(
            context, lifecycle={**context.lifecycle, ("privacy-instruction", "one", "cuts.2"): "withdrawn"}
        )
    elif defect == "unauthorized":
        context = replace(context, authorize=lambda request: request.operation == "select")
    elif defect == "wrong-surface":
        context = replace(context, surfaces={})
    elif defect == "undelivered":
        payload = surface.model_dump()
        payload.update(surface_state="projected", delivery=None)
        projected = type(surface).model_validate(payload)
        context = replace(context, surfaces={projected.participant_view.surface_id: projected})
    elif defect == "wrong-item":
        record = _exposed(item_ref="actions.scan")
    elif defect == "forged-delivery":
        record = _exposed(delivery_ref="forged")
    elif defect == "changed-selection":
        record = _exposed(selected_by_ref="actors.forged")
    else:
        context = replace(context, context_views={})
    assert validate_control_context_record(record, context)


def test_bounded_ingress_rejects_ambiguous_and_oversized_inputs():
    from raes_contracts.participant_control_context import load_control_context_json

    model = type(_asset())
    for source in (
        '{"kind":"instruction","kind":"policy"}',
        '{"value":NaN}',
        "[" * 40 + "0" + "]" * 40,
        " " * (1024 * 1024 + 1),
    ):
        with pytest.raises(ValueError):
            load_control_context_json(source, model)


def test_missing_authority_context_never_claims_semantic_conformance():
    from raes_conformance.conformance.validators import contract_validation_strength, validate_contract_payload

    assert contract_validation_strength("participant-control-context-record-v1") == "structural-context-required"
    assert validate_contract_payload("participant-control-context-record-v1", _record().model_dump())


def test_context_view_has_an_explicit_asset_source_layer():
    from raes_contracts.contracts.participant_context import ParticipantContextSourceLayerModel

    source = ParticipantContextSourceLayerModel(
        source_id="source.instruction",
        source_layer="participant_control_context_asset",
        ref="urn:sha256:" + "a" * 64,
        temporal_relation="same_observation_point",
        evidence_refs=["evidence.asset"],
        provenance_refs=["provenance.asset"],
    )
    assert source.source_layer == "participant_control_context_asset"
