"""The portable suite joins real owner operations to independent readback."""

from dataclasses import replace

import pytest
from governed_effect_runtime_fixtures import EffectResolver
from participant_control_v2_fixtures import binding
from participant_crossing_fixtures import PARTICIPANT, control_specification, identity
from raes_conformance.conformance import run_modular_control_conformance
from raes_conformance.conformance.modular_control_types import (
    ModularControlCase,
    ModularControlOperation,
    ModularControlStep,
    ModularOwnerObservation,
)
from sem233_flow_sink_fixtures import permit_resolver
from test_issue_1069_participant_control_effects import _target
from test_issue_1071_modular_conformance import Harness, action_step


def handoff_case(*, phase="independent", parent="none", decision="permit", observation="applied"):
    owner = EffectResolver(phase=phase, parent_outcome=parent, decision=decision)
    specification = control_specification()
    specification = replace(
        specification,
        controller_states=(
            specification.controller_states[0],
            replace(
                specification.controller_states[1],
                controller_address="participant.behavior.next-supervisor",
                controller_ref="next-supervisor",
            ),
        ),
    )

    def readback(plane):
        # Observe the real controller transition, independently of effect claims.
        history = plane.snapshot.participant_control_history[PARTICIPANT]
        assert history[-1]["occurrence"]["disposition"] == "accepted"
        assert history[-1]["occurrence"]["resulting_state_revision"] == 1
        event = next(event for event in reversed(plane.audit_log()) if event.action == "record_participant_control")
        return (ModularOwnerObservation("effect-1", event.operation_id, observation, ("controller-readback",)),)

    dispatch = ModularControlStep(
        ModularControlOperation.DISPATCH, dict(participant_address=PARTICIPANT, identity=identity(audience_bound=True))
    )
    return ModularControlCase(
        name="handoff-" + phase,
        obligation="effect:handoff",
        participant_address=PARTICIPANT,
        episode_id="episode-1",
        options=dict(
            participant_control=binding(owner),
            crossing_policy_resolver=permit_resolver(),
            behavior_specifications={specification.address: specification},
        ),
        steps=(action_step(), dispatch, dispatch),
        expected_compositions=(
            "withhold" if phase == "required-predecessor" else "eligible" if decision == "permit" else decision,
        ),
        expected_calls={
            "participant_runtime.admit_action": 1 if decision == "permit" and phase != "required-predecessor" else 0
        },
        expected_effects={"effect-1": "applied"},
        observe=readback,
    )


@pytest.mark.parametrize(
    "phase,parent,decision",
    [
        ("independent", "none", "permit"),
        ("independent", "none", "deny"),
        ("required-predecessor", "none", "permit"),
        ("success-dependent", "admitted", "permit"),
        ("success-dependent", "applied", "permit"),
    ],
)
def test_real_handoff_owner_and_phase_prerequisites(phase, parent, decision):
    selected = handoff_case(phase=phase, parent=parent, decision=decision)
    report = run_modular_control_conformance(
        _target(), harness=Harness(selected), obligations=(), effect_kinds=("handoff",)
    )
    assert report.passed, report.cases[0].diagnostics


@pytest.mark.parametrize("observed", [None, "failed"])
def test_missing_or_contradictory_owner_readback_fails(observed):
    selected = handoff_case(observation=observed)
    if observed is None:
        selected = replace(selected, observe=None)
    report = run_modular_control_conformance(
        _target(), harness=Harness(selected), obligations=(), effect_kinds=("handoff",)
    )
    assert not report.passed


def test_effect_reopen_retains_exact_claim_and_owner(tmp_path):
    selected = handoff_case()
    selected = replace(
        selected,
        steps=(*selected.steps[:2], ModularControlStep(ModularControlOperation.REOPEN, {}), selected.steps[-1]),
    )
    report = run_modular_control_conformance(
        _target(), harness=Harness(selected), obligations=(), effect_kinds=("handoff",), store_root=tmp_path
    )
    assert report.passed, report.cases[0].diagnostics
    assert report.cases[0].modular_control.reopened


def test_world_inject_executes_a_fresh_occurrence_and_matches_file_readback(tmp_path):
    from participant_inject_runtime_fixtures import configured_plane
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.contracts.participant_control_effects import ControlInjectEffectModel
    from raes_contracts.participant_inject_delivery import ParticipantInjectDelivery
    from raes_runtime.participant_control_effects import ParticipantControlEffectOperation
    from raes_runtime.time_coordinator import TimeCoordinator
    from test_issue_1368_control_inject_owner import effect_target

    owner = EffectResolver()
    seed, backend, _, application = configured_plane(tmp_path, participant_control=binding(owner), fresh_result=True)
    model, selected, delivery_binding, crossing = (
        seed._inject_delivery.model,
        seed._target,
        seed._inject_delivery,
        seed._crossing_policy_resolver,
    )
    target = effect_target(seed, application)
    seed.close()
    backend.path.unlink()
    backend.starts, backend.sequence = 0, 0
    request = backend.world_request.model_copy(
        update={
            "request_key": "portable-world-key",
            "occurrence_id": "portable-world-occurrence",
            "expected_head": "inject-order:genesis",
        }
    )
    owner.target = target.model_dump(mode="json") | {"world_request": request.model_dump(mode="json")}
    delivery = model.participant_inject_deliveries[application.delivery_address]
    owner.inject_deliveries = {delivery.address: ParticipantInjectDelivery.model_validate(delivery.spec)}
    owner.inject_coordinates = {delivery.address: ControlInjectEffectModel.model_validate(owner.target)}
    owner.operation = lambda effect, context: ParticipantControlEffectOperation(kind="inject", inject_request=request)
    clock = TimeCoordinator(model.time_model)
    initial = clock.advance(clock.initialize(), "time.clock.exercise-clock", ticks=5)

    def observe(plane):
        assert backend.path.read_bytes() == backend.content
        return (
            ModularOwnerObservation(
                "effect-1", backend.claim.operation_id, "applied", (canonical_json_digest(backend.content.decode()),)
            ),
        )

    source = action_step()
    source = replace(
        source,
        arguments={
            **source.arguments,
            "crossing_evidence": source.arguments["crossing_evidence"].model_copy(
                update={"audience_scope_ref": delivery.audience_scope_ref}
            ),
            "identity": identity(audience_bound=True, audience_scope_ref=delivery.audience_scope_ref),
        },
    )
    dispatch = ModularControlStep(
        ModularControlOperation.DISPATCH, dict(participant_address=PARTICIPANT, identity=source.arguments["identity"])
    )
    case = ModularControlCase(
        name="world-inject",
        obligation="effect:inject",
        participant_address=PARTICIPANT,
        episode_id="episode-1",
        options=dict(
            participant_control=binding(owner),
            crossing_policy_resolver=crossing,
            behavior_specifications=model.behavior_specifications,
            inject_execution=backend,
            operation_evidence=backend,
            inject_delivery=delivery_binding,
            initial_snapshot=initial,
        ),
        steps=(
            ModularControlStep(ModularControlOperation.REGISTER_PLAN, {"plan": backend.plan}),
            source,
            dispatch,
            dispatch,
        ),
        expected_compositions=("eligible",),
        expected_calls={"participant_runtime.admit_action": 1, "operation_provider.start_operation": 1},
        expected_effects={"effect-1": "applied"},
        observe=observe,
    )
    report = run_modular_control_conformance(selected, harness=Harness(case), obligations=(), effect_kinds=("inject",))
    assert report.passed, report.cases[0].diagnostics
    assert backend.starts == 1


def test_cancellation_effect_prevents_the_exact_pending_attempt():
    from participant_control_contract_fixtures import ref
    from participant_crossing_fixtures import evidence
    from raes_runtime.participant_control_effects import ParticipantControlEffectOperation
    from reusable_control_runtime_fixtures import configured_plane
    from reusable_control_runtime_fixtures import identity as controller
    from test_issue_1364_cancellation import admitted_attempt, cancellation

    owner = EffectResolver()
    owner.principal, owner.trigger_key = "operator", "trigger-cancel"
    seed, cuts = configured_plane(
        target=_target(), participant_control=binding(owner), crossing_policy_resolver=permit_resolver()
    )
    selected, mixed = seed._target, seed._mixed_control
    seed.close()

    def source(plane, outputs):
        target = admitted_attempt(plane)
        first = cancellation(
            plane, cuts, target.receipt.operation_id, target_kind="attempt", revision=0, head=0, order=1, key="source"
        )
        effect = cancellation(
            plane, cuts, target.receipt.operation_id, target_kind="attempt", revision=1, head=1, order=2, key="effect"
        )
        owner.target = dict(
            kind="interrupt",
            target_kind="execution",
            target_ref=target.receipt.operation_id,
            operation="cancel",
            lifecycle_authority=ref(effect.application.policy_ref, "authority"),
            expected_revision="1",
        )
        owner.operation = lambda request, context: ParticipantControlEffectOperation(
            kind="interrupt", intent=effect, participant_address=PARTICIPANT, crossing_evidence=evidence()
        )
        return dict(
            participant_address=PARTICIPANT,
            intent=first,
            identity=controller(),
            idempotency_key="trigger-cancel",
            crossing_evidence=evidence(),
        )

    def readback(plane):
        event = next(event for event in reversed(plane.audit_log()) if event.action == "record_participant_control")
        status = plane.participant_cancellation_status(event.operation_id, identity=controller())
        assert status.cancellation_effect.value == "prevented"
        assert plane.get_operation(status.target_operation_id).state.value == "cancelled"
        return (ModularOwnerObservation("effect-1", event.operation_id, "applied", tuple(status.evidence_refs)),)

    dispatch = ModularControlStep(
        ModularControlOperation.DISPATCH, dict(participant_address=PARTICIPANT, identity=controller())
    )
    case = ModularControlCase(
        name="cancel-attempt",
        obligation="effect:interrupt",
        participant_address=PARTICIPANT,
        episode_id="episode-1",
        identity=controller(),
        options=dict(
            participant_control=binding(owner),
            crossing_policy_resolver=permit_resolver(),
            behavior_specifications=mixed.model.behavior_specifications,
            mixed_control=mixed,
        ),
        steps=(ModularControlStep(ModularControlOperation.CONTROL, source), dispatch, dispatch),
        expected_compositions=("eligible",),
        expected_calls={},
        expected_effects={"effect-1": "applied"},
        observe=readback,
    )
    report = run_modular_control_conformance(
        selected, harness=Harness(case), obligations=(), effect_kinds=("interrupt",)
    )
    assert report.passed, report.cases[0].diagnostics
