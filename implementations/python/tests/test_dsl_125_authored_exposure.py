"""Authored selections cross the actual compiler, projection and delivery seams."""

import json
from dataclasses import replace

import pytest
import yaml
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts import ParticipantContextViewModel
from raes_contracts.participant_control_context import control_context_asset_reference
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import (
    project_participant_decision_surface_v2,
    resolve_participant_episode_readiness_anchor_v2,
)
from raes_runtime.control_plane import RuntimeControlPlane
from test_act_620_control_context_assets import _asset, _context, _context_view, _record
from test_dsl_118_control_context import ROOT, selection
from test_sem_220_participant_decision_surface import BOUNDARY, PARTICIPANT, SCAN
from test_sem_220_participant_decision_surface_v2_runtime import _delivery, _exposure_resolvers, _projection

ITEM = "control_context_assets.shared"


def case(*, disposition="selected", hidden=False, reusable=False, later=False):
    asset = _asset().model_copy(update={"role_refs": ["red"]})
    payload = yaml.safe_load((ROOT / "examples/scenarios/participant-tools/tool-kit.sdl.yaml").read_text())
    payload.pop("module")
    behavior = payload["behavior_specifications"].pop("red-scan-behavior")
    payload["behavior_specifications"]["red-surface"] = behavior
    behavior["tool_affordances"]["scanner"] = behavior["tool_affordances"].pop("network-scanner")
    payload["agents"]["red-agent"]["role"] = "red"
    binding = selection(asset.model_dump(mode="json"), disposition=disposition)
    if reusable:
        behavior["control_context"] = {"briefing": binding}
    else:
        payload["agents"]["red-agent"]["control_context"] = {"briefing": binding}
    payload["control_context_assets"] = {"shared": asset.model_dump(mode="json")}
    boundary = payload["observation_boundaries"]["red-view"]
    boundary["observable_refs"] = [
        "action_contracts.scan",
        "behavior_specifications.red-surface.tool_affordances.scanner",
    ] + ([] if hidden else [ITEM])
    boundary["hidden_refs"] = [ITEM] if hidden else []
    boundary["view_rules"] = [
        {
            "information_ref": ref,
            "boundary_class": "observable_resource",
            "disposition": "observable",
            "visibility_basis": "authored",
        }
        for ref in boundary["observable_refs"]
    ]
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(payload)))
    assert not model.diagnostics
    control = RuntimeControlPlane(create_stub_target())
    control.initialize_participant_episode(PARTICIPANT, episode_id="episode-1")
    snapshot = control.get_snapshot().snapshot
    anchor = resolve_participant_episode_readiness_anchor_v2(
        snapshot,
        participant_address=PARTICIPANT,
        decision_epoch=0,
        evidence_refs=("evidence.episode-running",),
        provenance_refs=("provenance.runtime",),
    )
    if later:
        from raes_processor.models import (
            ParticipantBehaviorProjectionAnchorRequestV2,
            resolve_participant_behavior_projection_anchor_v2,
        )
        from test_sem_220_participant_decision_surface import _admission_request
        from test_sem_220_participant_decision_surface_v2_runtime import _compiled_participant_behavior

        _, apparatus = _exposure_resolvers(_projection(anchor))
        from raes_contracts.contracts import ParticipantActionResultModel

        result = ParticipantActionResultModel(
            status="succeeded",
            participant_address=PARTICIPANT,
            episode_id="episode-1",
            action_instance_id="scan-1",
            action_contract_address=SCAN,
            observation_point="scan-1:terminal",
            preconditions=[
                {
                    "precondition_id": "authority-in-scope",
                    "precondition_class": "authority",
                    "status": "satisfied",
                    "participant_address": PARTICIPANT,
                    "episode_id": "episode-1",
                    "action_contract_address": SCAN,
                    "observation_point": "scan-1:attempt",
                }
            ],
            effects=[
                {
                    "effect_id": "terminal-scan-observation",
                    "effect_class": "observation_effect",
                    "description": "terminal scan observation",
                    "evidence_refs": ["evidence.scan-output"],
                }
            ],
        )
        control.admit_participant_action(
            _compiled_participant_behavior(),
            replace(
                _admission_request(),
                implementation_selection=apparatus,
                action_result=result,
                observation_boundary_evidence_refs=("evidence.scan-output",),
            ),
        )
        snapshot = control.get_snapshot().snapshot
        anchor = resolve_participant_behavior_projection_anchor_v2(
            snapshot,
            runtime_model=model,
            request=ParticipantBehaviorProjectionAnchorRequestV2(
                participant_address=PARTICIPANT,
                episode_id="episode-1",
                decision_epoch=1,
                behavior_history_order=2,
                evidence_refs=("evidence.scan",),
                provenance_refs=("provenance.runtime",),
            ),
        )
    projection = _projection(anchor)
    assessments = dict(projection.exposure_assessments)
    assessments[ITEM] = replace(
        assessments.pop("context.public"),
        item_ref=ITEM,
        authorization_record_ref=f"exposure-authorizations.v2.{ITEM}.epoch-{anchor.decision_epoch}",
    )
    projection = replace(
        projection,
        visible_context_refs=(ITEM,),
        exposure_assessments=assessments,
        action_assessments={
            SCAN: replace(
                projection.action_assessments[SCAN], selection_shape_ref=model.action_contracts[SCAN].argument_shape_ref
            )
        },
    )
    resolvers, _ = _exposure_resolvers(projection)
    original = resolvers.authorization
    pin = control_context_asset_reference(asset)

    def authorization(**kwargs):
        result = original(**kwargs)
        return (
            replace(
                result,
                source_ref="urn:" + pin.asset_digest,
                source_layer_ref="source.instruction",
                transformation_rule_ref="transformations.redacted-instruction",
            )
            if kwargs["item_ref"] == ITEM
            else result
        )

    resolvers = replace(resolvers, authorization=authorization)
    record = _record(
        asset,
        participant_address=PARTICIPANT,
        audience_scope_ref=projection.audience_scope_ref,
        selection_cut=anchor.state_cut.model_dump(),
        record_cut=anchor.state_cut.model_dump(),
    )
    exposed = record.model_copy(
        update={
            "record_id": "record.disclosed",
            "disposition": "disclosed",
            "surface_id": projection.surface_id,
            "item_ref": ITEM,
        }
    )
    view_payload = _context_view().model_dump(mode="json")
    view_payload.update(
        participant_address=PARTICIPANT,
        episode_id="episode-1",
        view_ref=projection.context_view_ref,
        payload_ref=ITEM,
        visibility_projection_ref=projection.visibility_projection_ref,
        redaction_policy_ref=projection.redaction_policy_ref,
        marking_definition_refs=list(projection.marking_definition_refs),
        derived_from_refs=["urn:" + pin.asset_digest],
    )
    view_payload["source_layers"][0]["ref"] = "urn:" + pin.asset_digest
    view = ParticipantContextViewModel.model_validate(view_payload)
    context = replace(
        _context(asset, participant=PARTICIPANT, cut=anchor.state_cut),
        audience_scope_ref=projection.audience_scope_ref,
        selections={record.selection_ref: record},
        roles={anchor.state_cut.cut_ref: frozenset({"red"})},
        context_views={view.view_ref: view},
        authorize=lambda request: True,
    )
    from raes_processor.models.authored_participant_exposure_v2 import AuthoredParticipantExposureV2

    return model, snapshot, projection, resolvers, AuthoredParticipantExposureV2({"briefing": exposed}, context)


def project(args, **kwargs):
    model, snapshot, projection, resolvers, authored = args
    from raes_processor.models import ParticipantBehaviorHistoryEvent

    history = tuple(
        ParticipantBehaviorHistoryEvent.from_payload(p)
        for p in snapshot.participant_behavior_history.get(PARTICIPANT, [])
    )
    return project_participant_decision_surface_v2(
        model,
        snapshot,
        history_events=history,
        projection=projection,
        exposure_resolvers=resolvers,
        authored_exposure=authored,
        **kwargs,
    )


@pytest.mark.parametrize("reusable", [False, True])
@pytest.mark.parametrize("later", [False, True])
def test_compiled_declaration_projects_and_delivers_with_exact_provenance(reusable, later):
    from raes_processor.models.authored_participant_exposure_v2 import deliver_authored_participant_decision_surface_v2

    args = case(reusable=reusable, later=later)
    model, _, projection, _, authored = args
    surface = project(args)
    binding = next(b for b in surface.assurance.exposure_bindings if b.item_ref == ITEM)
    assert binding.source_ref == "urn:" + authored.records["briefing"].asset_ref.asset_digest
    assert binding.transformation_rule_ref == "transformations.redacted-instruction"
    delivery = _delivery(surface)
    delivered_record = authored.records["briefing"].model_copy(
        update={"record_id": "record.delivered", "disposition": "delivered", "delivery_ref": delivery.delivery_ref}
    )
    delivered = deliver_authored_participant_decision_surface_v2(
        model,
        surface,
        delivery_ref=delivery.delivery_ref,
        resolver=lambda **_: delivery,
        relation={ITEM: "observable"},
        authored=replace(authored, records={"briefing": delivered_record}),
    )
    assert delivered.surface_state == "delivered"
    assert delivered.participant_view.visible_context_refs == [ITEM]
    participant_bytes = json.dumps(delivered.participant_view.model_dump(mode="json"))
    assert "authorization_record_ref" not in participant_bytes
    assert "provenance_refs" not in participant_bytes
    assert "derivation_anchor" not in participant_bytes


@pytest.mark.parametrize(
    "defect",
    ["withheld", "no-record", "unknown-slot", "stale-pin", "wrong-episode", "wrong-participant", "denied", "hidden"],
)
def test_projection_fails_closed_at_authored_join(defect):
    args = list(case(disposition="withheld" if defect == "withheld" else "selected", hidden=defect == "hidden"))
    authored = args[-1]
    record = authored.records["briefing"]
    if defect == "no-record":
        authored = replace(authored, records={})
    elif defect == "unknown-slot":
        authored = replace(authored, records={"unknown": record})
    elif defect == "stale-pin":
        authored = replace(
            authored,
            records={
                "briefing": record.model_copy(update={"asset_ref": control_context_asset_reference(_asset("two"))})
            },
        )
    elif defect in {"wrong-episode", "wrong-participant"}:
        field = "episode_id" if defect == "wrong-episode" else "participant_address"
        authored = replace(authored, records={"briefing": record.model_copy(update={field: "other"})})
    elif defect == "denied":
        authored = replace(authored, context=replace(authored.context, authorize=lambda request: False))
    args[-1] = authored
    with pytest.raises(ValueError):
        project(args)


def test_delivery_rechecks_authority_after_projection():
    from raes_processor.models.authored_participant_exposure_v2 import deliver_authored_participant_decision_surface_v2

    args = case()
    model, _, _, _, authored = args
    surface = project(args)
    delivery = _delivery(surface)
    record = authored.records["briefing"].model_copy(
        update={"record_id": "record.delivered", "disposition": "delivered", "delivery_ref": delivery.delivery_ref}
    )
    authored = replace(
        authored, records={"briefing": record}, context=replace(authored.context, authorize=lambda request: False)
    )
    with pytest.raises(ValueError, match="authored-exposure.authority-mismatch"):
        deliver_authored_participant_decision_surface_v2(
            model,
            surface,
            delivery_ref=delivery.delivery_ref,
            resolver=lambda **_: delivery,
            relation={ITEM: "observable"},
            authored=authored,
        )


def test_unknown_declared_asset_cannot_pass_as_ordinary_context():
    args = list(case())
    projection = args[2]
    unknown = "control_context_assets.unknown"
    args[0].observation_boundaries[BOUNDARY].view_relation_timeline[0]["view_relation"][unknown] = "observable"
    assessments = dict(projection.exposure_assessments)
    assessments[unknown] = replace(
        assessments.pop(ITEM),
        item_ref=unknown,
        authorization_record_ref=f"exposure-authorizations.v2.{unknown}.epoch-0",
    )
    args[2] = replace(projection, visible_context_refs=(unknown,), exposure_assessments=assessments)
    args[3], _ = _exposure_resolvers(args[2])
    args[4] = None
    with pytest.raises(ValueError, match="authored-exposure"):
        project(args)


@pytest.mark.parametrize("defect", ["stale-cut", "stale-policy", "role-revoked", "assurance-source", "missing-context"])
def test_live_authority_and_hidden_sources_remain_independent(defect):
    args = list(case())
    authored = args[-1]
    if defect == "stale-cut":
        from test_act_620_control_context_assets import _cut

        authored = replace(authored, context=replace(authored.context, record_cut=_cut(8)))
    elif defect == "role-revoked":
        authored = replace(authored, context=replace(authored.context, roles={}))
    elif defect == "missing-context":
        authored = None
    elif defect == "stale-policy":
        resolver = args[3].projection_policy
        args[3] = replace(args[3], projection_policy=lambda **kw: replace(resolver(**kw), revision="stale"))
    else:
        resolver = args[3].authorization
        args[3] = replace(args[3], authorization=lambda **kw: replace(resolver(**kw), source_ref="assurance.private"))
    args[-1] = authored
    with pytest.raises(ValueError):
        project(args)


def test_sealed_trial_configuration_uses_the_same_slot_join():
    from raes import instantiate_scenario
    from raes_contracts.contracts import ParticipantDecisionSurfaceV2Model
    from raes_processor.models import AuthoredParticipantExposureV2, validate_authored_participant_exposure_v2
    from raes_processor.trial_compiler import compile_admitted_trial_plan
    from test_act_620_control_context_assets import _context_view, _delivered_context, _exposed, _surface
    from test_dsl_118_trial_control_context import context_request

    request = context_request()
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None
    configuration = next(iter(result.plan.entries.values())).participant_configurations[0]
    selected = configuration.configuration.values[0].control_context_selection
    asset = request.family.control_context_assets[selected.asset_ref.asset_version]
    model = compile_runtime_model(
        instantiate_scenario(
            parse_sdl(
                yaml.safe_dump(
                    {
                        "name": "configured",
                        "agents": {"red": {"role": "red"}},
                        "control_context_assets": {
                            name: asset.model_dump(mode="json")
                            for name, asset in request.family.control_context_assets.items()
                        },
                    }
                )
            )
        )
    )
    participant = next(iter(model.participant_behaviors))
    payload = _surface().model_dump_json().replace("participants.red", participant)
    payload = json.loads(payload)
    payload["assurance"]["exposure_bindings"][0]["source_ref"] = "urn:" + selected.asset_ref.asset_digest
    from raes_contracts.canonical import canonical_json_digest

    payload["assurance"]["participant_view_digest"] = canonical_json_digest(payload["participant_view"])
    payload["delivery"]["participant_view_digest"] = payload["assurance"]["participant_view_digest"]
    surface = ParticipantDecisionSurfaceV2Model.model_validate(payload)
    record = _exposed().model_copy(update={"participant_address": participant, "asset_ref": selected.asset_ref})
    context = _delivered_context()
    view = _context_view().model_copy(
        update={
            "participant_address": participant,
            "derived_from_refs": ["urn:" + selected.asset_ref.asset_digest],
            "source_layers": [
                _context_view().source_layers[0].model_copy(update={"ref": "urn:" + selected.asset_ref.asset_digest})
            ],
        }
    )
    context = replace(
        context,
        participant_address=participant,
        assets={(asset.asset_id, asset.asset_version): asset},
        selections={record.selection_ref: _record(asset, participant_address=participant)},
        context_views={view.view_ref: view},
        roles={record.selection_cut.cut_ref: frozenset({"red"})},
        lifecycle={
            (asset.asset_id, asset.asset_version, cut): "active"
            for cut in [
                record.selection_cut.cut_ref,
                record.record_cut.cut_ref,
                surface.assurance.derivation_anchor.state_cut.cut_ref,
            ]
        },
    )
    authored = AuthoredParticipantExposureV2({selected.slot_id: record}, context, configuration)
    validate_authored_participant_exposure_v2(
        model, surface, relation={selected.declaration_ref: "observable"}, authored=authored
    )
    wrong_participant = replace(
        authored, configuration=configuration.model_copy(update={"participant_address": "agents.other"})
    )
    with pytest.raises(ValueError, match="configuration-participant-mismatch"):
        validate_authored_participant_exposure_v2(
            model,
            surface,
            relation={selected.declaration_ref: "observable"},
            authored=wrong_participant,
        )


@pytest.mark.parametrize("revoked", [False, True])
def test_distinct_delivery_cut_uses_current_policy(revoked):
    from raes_processor.models import deliver_authored_participant_decision_surface_v2
    from test_act_620_control_context_assets import _cut

    args = case()
    model, _, _, _, authored = args
    surface = project(args)
    cut = _cut(9)
    delivery = _delivery(surface).model_copy(update={"delivery_cut_ref": cut.cut_ref})
    original = authored.records["briefing"]
    record = original.model_copy(
        update={
            "record_id": "record.delivered",
            "disposition": "delivered",
            "delivery_ref": delivery.delivery_ref,
            "record_cut": cut,
        }
    )
    context = replace(
        authored.context,
        record_cut=cut,
        cut_precedes=lambda earlier, later: earlier == original.selection_cut and later == cut,
        lifecycle={
            **authored.context.lifecycle,
            (original.asset_ref.asset_id, original.asset_ref.asset_version, cut.cut_ref): "active",
        },
        authorize=lambda request: (
            not (revoked and request.state_cut == cut and request.operation in {"disclose", "deliver"})
        ),
    )

    def deliver():
        return deliver_authored_participant_decision_surface_v2(
            model,
            surface,
            delivery_ref=delivery.delivery_ref,
            resolver=lambda **_: delivery,
            relation={ITEM: "observable"},
            authored=replace(authored, records={"briefing": record}, context=context),
        )

    if revoked:
        with pytest.raises(ValueError, match="authored-exposure.authority-mismatch"):
            deliver()
    else:
        assert deliver().delivery.delivery_cut_ref == cut.cut_ref


def test_malformed_record_has_a_value_free_error():
    args = list(case())
    authored = args[-1]
    bad = authored.records["briefing"].model_copy(update={"disposition": "private-sentinel"})
    args[-1] = replace(authored, records={"briefing": bad})
    with pytest.raises(ValueError) as error:
        project(args)
    assert "private-sentinel" not in str(error.value)
