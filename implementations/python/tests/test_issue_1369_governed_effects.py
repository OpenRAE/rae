"""Public-provider regressions for phase-independent decisions and owned effects."""

from copy import deepcopy

import pytest
from participant_control_contract_fixtures import evaluation_payload
from participant_control_runtime_fixtures import SyntheticControlResolver, control_binding
from participant_crossing_fixtures import PARTICIPANT, admit, identity
from raes_contracts.runtime_state import OperationState
from test_issue_1069_participant_control_orchestration import _instrument_backend, _plane, control_target


class ParentDecisionResolver(SyntheticControlResolver):
    def resolve(self, **coordinates):
        resolution = super().resolve(**coordinates)
        effect = self.live["results"][1]["payload"]
        context = self.live["request"]["context"]
        effect["target"] = dict(
            kind=self.payload["parent_decision"], crossing_decision=context["crossing"], subject=context["subject"]
        )
        for provider in self.providers:
            provider.bind(self.live)
        return resolution


@pytest.mark.parametrize("decision", ["deny", "withhold"])
@pytest.mark.parametrize("phase", ["subsequent", "required-predecessor"])
def test_parent_refusal_blocks_public_ingress_in_every_legacy_phase(decision, phase):
    payload = evaluation_payload()
    payload["results"][1]["payload"]["phase"] = phase
    resolver = ParentDecisionResolver(payload=deepcopy(payload))
    resolver.payload["parent_decision"] = decision
    binding = control_binding(payload, resolver=resolver)
    # The resolver's selection must be the operator-admitted live selection.
    resolver.payload = deepcopy(control_binding(payload).resolver.payload) | {"parent_decision": decision}
    target = control_target()
    calls = _instrument_backend(target)
    plane = _plane(binding, target=target)
    receipt = admit(plane, control_identity=identity(audience_bound=True), idempotency_key="late-refusal")
    assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED
    assert calls["calls"] == 0
    assert plane.audit_log()[-1].details["control_disposition"] == decision


def test_v2_commit_receipt_is_retained_at_the_actual_crossing_transaction():
    from participant_control_v2_fixtures import binding

    plane = _plane(binding())
    receipt = admit(plane, idempotency_key="commit-v2")
    evaluation = plane.snapshot.participant_control_evaluation_history[PARTICIPANT][0]
    assert evaluation["commit"]["status"] == "committed"
    assert evaluation["commit"]["receipt"]["ref"] == receipt.operation_id
    assert plane._store.load_records()[receipt.operation_id].result_history_heads


def test_independent_handoff_survives_a_complete_parent_denial():
    from governed_effect_runtime_fixtures import EffectResolver, effect_plane

    plane, owner = effect_plane(EffectResolver(decision="deny"))
    caller = identity(audience_bound=True)
    receipt = admit(plane, control_identity=caller)
    assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED
    before = deepcopy(plane.snapshot.participant_control_evaluation_history)
    outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
    assert [item.disposition for item in outcomes] == ["applied"]
    assert len(plane.snapshot.participant_control_history[PARTICIPANT]) == 1
    assert (
        plane.snapshot.participant_control_evaluation_history[PARTICIPANT][: len(before[PARTICIPANT])]
        == before[PARTICIPANT]
    )
    claims = [
        record
        for record in plane._store.load_records().values()
        if record.idempotency_key.startswith("control-effect:")
    ]
    assert len(claims) == 1
    assert claims[0].receipt.context.parent_operation_id == receipt.operation_id
    assert claims[0].result_payload["effect_id"] == outcomes[0].effect_id
    assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller) == outcomes
    assert len(plane.snapshot.participant_control_history[PARTICIPANT]) == 1


def test_missing_required_owner_refuses_the_parent_during_admission():
    from governed_effect_runtime_fixtures import EffectResolver, effect_plane

    owner = EffectResolver()
    owner.available = False
    plane, _ = effect_plane(owner)
    calls = _instrument_backend(plane._target)
    receipt = admit(plane, control_identity=identity(audience_bound=True))
    assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED
    assert calls["calls"] == 0
    evaluation = plane.snapshot.participant_control_evaluation_history[PARTICIPANT][-1]
    assert evaluation["composition"]["disposition"] == "unsupported"
    assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity(audience_bound=True)) == ()


@pytest.mark.parametrize("prerequisite", ["admitted", "applied"])
def test_success_dependent_effect_requires_the_actual_parent_receipt(prerequisite):
    from governed_effect_runtime_fixtures import EffectResolver, effect_plane

    plane, _ = effect_plane(EffectResolver(phase="success-dependent", parent_outcome=prerequisite))
    caller = identity(audience_bound=True)
    with plane:
        receipt = admit(plane, control_identity=caller)
        assert plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
        outcome = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert [item.disposition for item in outcome] == ["applied"]
        assert len(plane.snapshot.participant_control_history[PARTICIPANT]) == 1


def test_pending_consequence_cannot_bypass_trusted_effect_authority():
    from dataclasses import replace

    from governed_effect_runtime_fixtures import EffectResolver, effect_plane

    owner = EffectResolver(phase="success-dependent", parent_outcome="applied")
    trusted = owner.validation_context
    owner.validation_context = lambda evaluation: replace(trusted(evaluation), authorized_effects={})
    plane, _ = effect_plane(owner)
    caller = identity(audience_bound=True)
    with plane:
        receipt = admit(plane, control_identity=caller)
        assert plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
        assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller) == ()
        assert not plane.snapshot.participant_control_history.get(PARTICIPANT)
        assert not any(r.idempotency_key.startswith("control-effect:") for r in plane._store.load_records().values())


def test_required_predecessor_is_applied_without_releasing_the_withheld_parent():
    from governed_effect_runtime_fixtures import EffectResolver, effect_plane

    plane, _ = effect_plane(EffectResolver(phase="required-predecessor"))
    calls = _instrument_backend(plane._target)
    caller = identity(audience_bound=True)
    with plane:
        receipt = admit(plane, control_identity=caller)
        assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED
        outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert [item.disposition for item in outcomes] == ["applied"]
        assert calls["calls"] == 0
        assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED


def test_fresh_cut_can_release_parent_only_after_exact_predecessor_application():

    from governed_effect_runtime_fixtures import EffectResolver, effect_plane
    from participant_crossing_fixtures import admission_request

    plane, _ = effect_plane(EffectResolver(phase="required-predecessor"))
    caller = identity(audience_bound=True)
    with plane:
        refused = admit(plane, control_identity=caller, idempotency_key="before-predecessor")
        plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        resumed = admit(
            plane, request=admission_request(), control_identity=caller, idempotency_key="after-predecessor"
        )
        assert plane.get_operation(refused.operation_id).state is OperationState.FAILED
        assert plane.get_operation(resumed.operation_id).state is OperationState.SUCCEEDED
        assert len(plane.snapshot.participant_control_history[PARTICIPANT]) == 1


def test_effect_claim_outcome_is_validated_before_store_admission():
    from dataclasses import replace

    from governed_effect_runtime_fixtures import effect_plane
    from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
    from raes_contracts.runtime_state import OperationKind
    from raes_runtime.control_plane_mutation import control_plane_mutation
    from raes_runtime.participant_control_receipts import claim_effect

    plane, _ = effect_plane()
    with plane:
        receipt = admit(plane, control_identity=identity(audience_bound=True))
        evaluation = ParticipantControlEvaluationV2Model.model_validate(
            plane.snapshot.participant_control_evaluation_history[PARTICIPANT][0]
        )
        with control_plane_mutation(plane, OperationKind.PARTICIPANT_CONTROL):
            claim = claim_effect(
                plane, plane._store.load_records()[receipt.operation_id], evaluation.effect_plan.effects[0]
            )
            with pytest.raises(ValueError):
                replace(claim.record, result_payload={"effect_id": "forged", "disposition": "applied"})


@pytest.mark.parametrize(
    "disclosure,tamper",
    [
        ("none", None),
        ("delivered", None),
        ("withheld", None),
        ("uncertain-world", None),
        ("none", "slot"),
        ("none", "plan"),
        ("none", "bindings"),
        ("none", "input"),
        ("none", "head"),
        ("none", "request-key"),
        ("none", "occurrence"),
        ("none", "target-scope"),
        ("none", "run-scope"),
        ("none", "authority"),
        ("none", "inject-authority"),
        ("delivered", "episode"),
        ("delivered", "participant"),
        ("delivered", "delivery"),
        ("delivered", "digest"),
    ],
)
def test_inject_effect_creates_a_fresh_real_world_occurrence(tmp_path, disclosure, tamper):

    from governed_effect_runtime_fixtures import EffectResolver
    from participant_control_v2_fixtures import binding
    from participant_crossing_fixtures import admission_request, behavior, evidence
    from participant_inject_runtime_fixtures import configured_plane
    from raes_backend_protocols.inject_execution import InjectAdmission
    from raes_contracts.participant_inject_delivery import ParticipantInjectDelivery
    from raes_runtime.inject_claims import inject_order_head
    from raes_runtime.participant_control_effects import ParticipantControlEffectOperation
    from test_issue_1368_control_inject_owner import effect_target

    owner = EffectResolver()
    plane, backend, disclosure_owner, application = configured_plane(
        tmp_path, participant_control=binding(owner), fresh_result=True
    )
    disclosure_owner.fail = disclosure == "withheld"
    owner.target = effect_target(plane, application).model_dump(mode="json")
    delivery = plane._inject_delivery.model.participant_inject_deliveries[application.delivery_address]
    owner.inject_deliveries = {delivery.address: ParticipantInjectDelivery.model_validate(delivery.spec)}
    owner.inject_coordinates = {delivery.address: effect_target(plane, application)}

    def operation(effect, context):
        prior = next(record for record in plane._store.load_records().values() if record.inject_occurrence)
        return ParticipantControlEffectOperation(
            kind="inject",
            inject_application=application if disclosure in {"delivered", "withheld"} else None,
            inject_request=backend.world_request.model_copy(
                update={
                    "request_key": "effect-world-key-1",
                    "occurrence_id": "effect-world-occurrence-1",
                    "expected_head": inject_order_head(prior.inject_occurrence),
                    "placement": backend.world_request.placement.model_copy(update={"slot": "effect-slot-1"}),
                }
            ),
        )

    owner.operation = operation
    owner.target["world_request"] = operation(None, None).inject_request.model_dump(mode="json")
    from raes_contracts.contracts.participant_control_effects import ControlInjectEffectModel

    owner.inject_coordinates = {delivery.address: ControlInjectEffectModel.model_validate(owner.target)}
    original_admit = backend.admit

    def issue_order(*args):
        backend.sequence = 0
        admitted = original_admit(*args)
        count = sum(record.inject_occurrence is not None for record in plane._store.load_records().values())
        backend.claim = admitted.occurrence.model_copy(
            update={"order": admitted.occurrence.order.model_copy(update={"position": count + 1})}
        )
        return InjectAdmission(admitted.plan, backend.claim)

    if disclosure == "uncertain-world":
        from raes_backend_protocols.inject_execution import ResolvedInjectOutcome
        from raes_contracts.contracts import (
            BackendOperationResponseModel,
            InjectOccurrenceOutcomeModel,
            inject_occurrence_reference,
        )

        observe = backend.observe_operation

        def uncertain(control):
            response = observe(control).model_dump(mode="json")
            response["message"].update(
                proposed_state="indeterminate", satisfaction="unsatisfied", release_gates_satisfied=False
            )
            response["message"]["effects"].update(effect="unknown", cessation_established=False)
            return BackendOperationResponseModel.model_validate(response)

        backend.observe_operation = uncertain

        def outcome(occurrence, request, response):
            return ResolvedInjectOutcome(
                InjectOccurrenceOutcomeModel(
                    occurrence=inject_occurrence_reference(occurrence),
                    response=response,
                    effect="indeterminate",
                    bindings=tuple(
                        {"binding": item, "effects": response.message.effects, "readback": response.message.result}
                        for item in occurrence.request.bindings
                    ),
                ),
                backend.evidence,
            )

        backend.resolve_outcome = outcome
    backend.admit = issue_order
    caller = identity(audience_bound=True, audience_scope_ref=delivery.audience_scope_ref)
    with plane:
        assert backend.starts == 1
        plane.admit_participant_action(
            behavior(),
            admission_request(),
            identity=caller,
            crossing_evidence=evidence().model_copy(update={"audience_scope_ref": delivery.audience_scope_ref}),
            idempotency_key="world-effect-parent",
        )
        if tamper in {"authority", "inject-authority"}:
            from dataclasses import replace

            trusted = owner.validation_context
            if tamper == "authority":
                owner.validation_context = lambda evaluation: replace(trusted(evaluation), authorized_effects={})
            else:
                owner.inject_coordinates = {}
        elif tamper:
            from dataclasses import replace

            original_operation = owner.operation

            def changed(effect, context):
                operation = original_operation(effect, context)
                if tamper == "slot":
                    return replace(
                        operation,
                        inject_request=operation.inject_request.model_copy(
                            update={
                                "placement": operation.inject_request.placement.model_copy(
                                    update={"slot": "different-slot"}
                                )
                            }
                        ),
                    )
                world = operation.inject_request
                world_changes = {
                    "plan": {"plan": world.plan.model_copy(update={"artifact_id": "different-plan"})},
                    "bindings": {
                        "bindings": (world.bindings[0].model_copy(update={"instance": "different-instance"}),)
                    },
                    "input": {"input_ref": world.plan.model_copy(update={"artifact_id": "different-input"})},
                    "head": {"expected_head": "different-head"},
                    "request-key": {"request_key": "different-key"},
                    "occurrence": {"occurrence_id": "different-occurrence"},
                    "target-scope": {"target_scope": "target:other"},
                    "run-scope": {"run_scope": "run:other"},
                }
                if tamper in world_changes:
                    return replace(operation, inject_request=world.model_copy(update=world_changes[tamper]))
                changes = {
                    "episode": {"episode_id": "different-episode"},
                    "participant": {"participant_address": "participant.behavior.other"},
                    "delivery": {"delivery_address": "participant.behavior-specification.other.inject-delivery.other"},
                    "digest": {"delivery_digest": "sha256:" + "0" * 64},
                }
                return replace(operation, inject_application=application.model_copy(update=changes[tamper]))

            owner.operation = changed
        outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        if tamper:
            assert [item.disposition for item in outcomes] == [
                "withheld" if tamper in {"authority", "inject-authority"} else "unsupported"
            ]
            assert backend.starts == 1
            assert not any(record.inject_delivery for record in plane._store.load_records().values())
            return
        expected = "indeterminate" if disclosure == "uncertain-world" else "applied"
        assert [item.disposition for item in outcomes] == [expected]
        assert backend.starts == 2
        worlds = [record for record in plane._store.load_records().values() if record.inject_occurrence]
        assert len({record.inject_occurrence.request.occurrence_id for record in worlds}) == 2
        assert len({record.receipt.operation_id for record in worlds}) == 2
        deliveries = [record for record in plane._store.load_records().values() if record.inject_delivery]
        assert len(deliveries) == (1 if disclosure == "delivered" else 0)
        if deliveries:
            assert deliveries[0].inject_delivery.application.world_operation_id != application.world_operation_id
            assert deliveries[0].receipt.operation_id != outcomes[0].receipt_ref
        assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller) == outcomes
        assert backend.starts == 2


def test_a_resolver_input_cannot_substitute_for_an_installed_owner():
    from governed_effect_runtime_fixtures import EffectResolver
    from participant_control_v2_fixtures import binding

    plane = _plane(binding(EffectResolver()))
    with plane:
        receipt = admit(plane, control_identity=identity(audience_bound=True))
        assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED
        assert (
            plane.snapshot.participant_control_evaluation_history[PARTICIPANT][-1]["composition"]["disposition"]
            == "unsupported"
        )
