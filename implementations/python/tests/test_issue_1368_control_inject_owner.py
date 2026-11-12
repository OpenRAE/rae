"""API-424 joins resolve canonical coordinates independently of provider claims."""

from types import SimpleNamespace

import pytest
from participant_inject_runtime_fixtures import apply_control, caller, configured_plane
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_control_effects import ControlInjectEffectModel
from raes_contracts.contracts.participant_control_resolution import _validate_inject
from raes_contracts.participant_inject_delivery import ParticipantInjectDelivery


def selected_application(plane, request):
    target = apply_control(plane, "handoff", revision=0, head=0, order=1)
    event = apply_control(plane, "external-direction", revision=1, head=1, order=2, target=target)
    return type(request).model_validate(
        {
            **request.model_dump(mode="json"),
            "expected_snapshot_revision": plane._snapshot_state.revision,
            "control": {
                "event_id": event["event_id"],
                "occurrence_revision": 2,
                "digest": canonical_json_digest(event),
            },
        }
    )


def effect_target(plane, request):
    binding = plane._inject_delivery.model.participant_inject_deliveries[request.delivery_address]
    return ControlInjectEffectModel(
        kind="inject",
        delivery_ref={
            "kind": "inject-delivery",
            "ref": binding.address,
            "revision": "1",
            "digest": request.delivery_digest,
        },
        inject_ref=binding.inject_address,
        event_ref=binding.event_address,
        script_ref=binding.script_address,
        story_ref=binding.story_address,
        source_item_ref=binding.source_item_address,
        result_item_ref=binding.result_item_address,
        participant_address=request.participant_address,
        episode_id=request.episode_id,
        disclosure_ref={
            "kind": "disclosure",
            "ref": binding.disclosure_basis_ref,
            "revision": "1",
            "digest": canonical_json_digest(binding.disclosure_basis_ref),
        },
    )


def test_context_requires_exact_owner_application_and_canonical_coordinates(tmp_path):
    plane, backend, _, request = configured_plane(tmp_path, controlled="external-direction", fresh_result=True)
    with plane:
        request = selected_application(plane, request)
        target = effect_target(plane, request)
        content = plane.deliver_participant_inject(request, identity=caller()).delivery
        binding = plane._inject_delivery.model.participant_inject_deliveries[request.delivery_address]
        context = SimpleNamespace(
            inject_deliveries={binding.address: ParticipantInjectDelivery.model_validate(binding.spec)},
            inject_applications={binding.address: content},
            inject_coordinates={binding.address: target},
        )
        cut = SimpleNamespace(episode_id=request.episode_id)
        _validate_inject(target, cut, context)
        wrong_target = target.model_copy(update={"inject_ref": "orchestration.inject.wrong"})
        with pytest.raises(ValueError):
            _validate_inject(wrong_target, cut, context)
        context.inject_applications = {}
        with pytest.raises(ValueError):
            _validate_inject(target, cut, context)
        assert backend.starts == 1


def test_effect_owner_submits_through_the_real_world_result_delivery_boundary(tmp_path):
    from raes_runtime.participant_control_effects import ParticipantControlEffectOperation, _submit

    plane, backend, _, request = configured_plane(tmp_path, controlled="external-direction", fresh_result=True)
    with plane:
        request = selected_application(plane, request)
        target = effect_target(plane, request)
        claim = SimpleNamespace(receipt=SimpleNamespace(operation_id="effect-claim-1"))
        _submit(
            plane,
            claim,
            SimpleNamespace(target=target),
            ParticipantControlEffectOperation(kind="inject", inject_application=request),
            principal=caller(),
        )
        deliveries = [record for record in plane._store.load_records().values() if record.inject_delivery]
        assert len(deliveries) == 1
        assert deliveries[0].idempotency_key == "control-effect-owner:effect-claim-1"
        assert backend.starts == 1


def test_planning_rejects_unknown_owner_context_keywords(tmp_path):
    from raes_processor.planner import plan

    plane, _, _, _ = configured_plane(tmp_path)
    with plane, pytest.raises(TypeError, match="unsupported planning owner context"):
        plan(plane._inject_delivery.model, plane._target.manifest, unsupported_owner_context=True)
