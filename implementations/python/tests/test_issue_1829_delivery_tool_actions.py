"""Delivery invocation tool actions obey core admission and ownership rules."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from raes_contracts.contracts.participant_invocation_tools import (
    ParticipantInvocationToolActionCapabilitiesModel,
    validate_invocation_tool_action_claim,
)
from raes_contracts.errors import ConflictError
from raes_contracts.runtime_state import OperationKind
from raes_runtime.control_plane_mutation import RuntimeMutationAuthority, detached_extension


def test_delivery_composition_does_not_claim_autonomous_execution():
    claim = ParticipantInvocationToolActionCapabilitiesModel(
        semantic_versions=["participant-invocation-tool-actions/v2"],
        max_tool_actions_per_invocation=4,
        max_concurrent_tool_actions_per_invocation=2,
    )
    validate_invocation_tool_action_claim(claim, supports_autonomous_execution=False, supports_tool_affordances=True)
    with pytest.raises(ValueError, match="tool_affordances"):
        validate_invocation_tool_action_claim(
            claim, supports_autonomous_execution=False, supports_tool_affordances=False
        )


def test_v1_still_requires_autonomous_execution():
    claim = ParticipantInvocationToolActionCapabilitiesModel(
        semantic_versions=["participant-invocation-tool-actions/v1"],
        max_tool_actions_per_invocation=4,
        max_concurrent_tool_actions_per_invocation=2,
    )
    with pytest.raises(ValueError, match="autonomous"):
        validate_invocation_tool_action_claim(
            claim, supports_autonomous_execution=False, supports_tool_affordances=True
        )


def test_child_scope_uses_parent_writer_without_general_extension_reentry():
    authority = RuntimeMutationAuthority()
    with authority.mutation(OperationKind.COMPOSITION_PHASE):
        scope = authority.invocation_child_scope()

        def child():
            with detached_extension():
                with (
                    pytest.raises(RuntimeError, match="backend callback"),
                    authority.mutation(OperationKind.PROVISIONING),
                ):
                    pytest.fail("ordinary extension mutation was admitted")
                return scope.run(authority.owns_current_thread)

        with authority.external_call(), ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(child).result(timeout=2)
        assert authority.owns_current_thread()
        scope.close()
    with pytest.raises(ConflictError):
        scope.run(lambda: pytest.fail("closed child scope admitted work"))


def test_child_scope_cannot_mint_or_recursively_acquire_authority():
    authority = RuntimeMutationAuthority()
    with pytest.raises(RuntimeError):
        authority.invocation_child_scope()
    with authority.mutation(OperationKind.COMPOSITION_PHASE):
        scope = authority.invocation_child_scope()
        with authority.external_call():

            def nested():
                with pytest.raises(RuntimeError):
                    authority.invocation_child_scope()
                with pytest.raises(RuntimeError):
                    scope.run(lambda: None)

            scope.run(nested)
        scope.close()


def test_tool_relation_compiles_without_autonomous_policy():
    import yaml
    from raes import parse_sdl
    from raes_processor import compiler
    from test_issue_1740_invocation_tool_actions import ACTION, AFFORDANCE, FIRST, TARGET, _tool_scenario_yaml

    payload = yaml.safe_load(_tool_scenario_yaml())
    del payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    model = compiler.compile_runtime_model(parse_sdl(yaml.safe_dump(payload)))
    specification = model.behavior_specifications["participant.behavior-specification.participant-behavior"]
    assert specification.autonomous_execution is None
    bindings, temporal = compiler.compile_participant_invocation_tools(
        model,
        specification.address,
        participant_implementation_ref="implementations.participant-fixture",
        max_actions=4,
        max_in_flight=2,
    )
    assert len(bindings) == 1
    assert bindings[0].tool_affordance_address == AFFORDANCE
    assert bindings[0].action_contract_address == ACTION
    assert bindings[0].participant_addresses == (FIRST,)
    assert TARGET in bindings[0].target_addresses
    assert temporal == ()


def test_delivery_tool_history_context_does_not_invent_an_outer_action():
    from raes_contracts.contracts import participant_runtime

    context = participant_runtime.ParticipantDeliveryToolContextModel(
        semantics="participant-invocation-tool-actions/v2",
        invocation_id="delivery-invocation-1",
        delivery_operation_ref="delivery-operation-1",
        tool_affordance_address="participant.behavior-specification.tools.tool-affordance.probe",
        tool_call_id="call-1",
        admission_ordinal=0,
        settlement="completed",
        execution_scope_ref="delivery-invocation-1",
        execution_generation=1,
    )
    assert "invocation_action_contract_address" not in context.model_dump()
    invalid = {**context.model_dump(), "invocation_action_contract_address": "fabricated"}
    with pytest.raises(ValueError):
        participant_runtime.ParticipantDeliveryToolContextModel.model_validate(invalid)


def test_public_delivery_invocation_without_autonomous_policy(tmp_path):
    from delivery_invocation_fixtures import caller, delivery_plane, invocation_request

    plane, runtime, _, delivered, model = delivery_plane(tmp_path)
    with plane:
        assert all(item.autonomous_execution is None for item in model.behavior_specifications.values())
        assert not plane._target.manifest.participant_runtime.supports_autonomous_execution
        request = invocation_request(delivered)
        receipt = plane.invoke_participant_delivery(request, identity=caller())
        assert plane.get_operation(receipt.operation_id).state.value == "succeeded"
        assert runtime.calls == 1
        assert runtime.port.closed
        assert plane.invoke_participant_delivery(request, identity=caller()) == receipt
        assert runtime.calls == 1


def test_tool_is_independently_admitted_dispatched_and_recorded(tmp_path):
    from delivery_invocation_fixtures import (
        PARTICIPANT,
        caller,
        delivery_plane,
        invocation_request,
        tool_evidence,
        tool_outcome,
        tool_request,
    )
    from raes_contracts.participant_tool_actions import ParticipantToolActionRefusal

    calls, observations = [], []

    def script(invocation, port):
        request = tool_request(port)
        admitted = port.admit(request, crossing_evidence=tool_evidence())
        observations.append(admitted)
        assert admitted.admitted
        assert port.admit(request, crossing_evidence=tool_evidence()) == admitted
        grant = port.dispatch(admitted.action_instance_id)
        assert grant.accepted
        calls.append(grant.action_instance_id)
        assert port.dispatch(grant.action_instance_id).refusal is ParticipantToolActionRefusal.STATE_CONFLICT
        outcome = tool_outcome(port, grant.binding)
        assert port.complete(grant.action_instance_id, outcome).accepted
        assert port.complete(grant.action_instance_id, outcome).accepted

    plane, runtime, _, delivered, _ = delivery_plane(tmp_path, script)
    with plane:
        receipt = plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
        assert plane.get_operation(receipt.operation_id).state.value == "succeeded", (runtime.errors, observations)
        assert len(calls) == 1
        history = plane.snapshot.participant_behavior_history[PARTICIPANT]
        assert [event["event_type"] for event in history] == [
            "action_attempted",
            "state_transition_recorded",
            "observation_emitted",
        ]
        assert {event["action_instance_id"] for event in history} == set(calls)
        assert history[-1]["invocation_tool_context"]["delivery_operation_ref"] == delivered.operation_id
        assert history[-1]["action_result"]["status"] == "succeeded"
        from raes_runtime.participant_result_contracts import participant_runtime_state_contract_diagnostics

        assert not participant_runtime_state_contract_diagnostics(plane.snapshot)
        assert runtime.port.closed


@pytest.mark.parametrize(
    "changes",
    [
        {"target_addresses": ("provision.node.foreign",)},
        {"observation_boundary_address": "participant.observation-boundary.foreign"},
        {"episode_id": "foreign"},
        {"execution_generation": 9999},
        {"tool_affordance_address": "participant.behavior-specification.foreign.tool-affordance.probe"},
    ],
)
def test_foreign_tool_bindings_receive_no_grant_or_behavior_history(tmp_path, changes):
    from delivery_invocation_fixtures import (
        PARTICIPANT,
        caller,
        delivery_plane,
        invocation_request,
        tool_evidence,
        tool_request,
    )

    decisions = []

    def script(invocation, port):
        decisions.append(port.admit(tool_request(port, **changes), crossing_evidence=tool_evidence()))

    plane, _, _, delivered, _ = delivery_plane(tmp_path, script)
    with plane:
        receipt = plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
        assert plane.get_operation(receipt.operation_id).state.value == "succeeded"
        assert len(decisions) == 1
        assert not decisions[0].admitted
        assert not plane.snapshot.participant_behavior_history.get(PARTICIPANT)


@pytest.mark.parametrize("proof_mode", ["valid", "missing", "foreign"])
def test_child_shared_time_is_bound_and_assessed_by_runtime(tmp_path, proof_mode):
    from delivery_invocation_fixtures import (
        PARTICIPANT,
        caller,
        delivery_plane,
        invocation_request,
        temporal_payload,
        tool_evidence,
        tool_outcome,
        tool_request,
    )
    from raes_contracts.contracts.participant_temporal import ParticipantTemporalEvidenceModel
    from raes_contracts.contracts.participant_temporal_history import require_participant_temporal_history

    def script(invocation, port):
        decision = port.admit(tool_request(port), crossing_evidence=tool_evidence())
        assert decision.admitted
        grant = port.dispatch(decision.action_instance_id)
        assert grant.accepted
        context = grant.binding.temporal_contexts[0].shared_time
        assert context.action_instance_id == grant.action_instance_id
        assert context.execution_scope_ref == invocation.invocation_id
        assert context.execution_generation == invocation.execution_generation
        proofs = (
            []
            if proof_mode == "missing"
            else [
                ParticipantTemporalEvidenceModel(
                    context=context
                    if proof_mode == "valid"
                    else context.model_copy(update={"action_instance_id": "foreign"}),
                    observation_boundary_address=grant.binding.observation_boundary_address,
                    event_point="end",
                    coordinate=context.submitted_at,
                    evidence_refs=(grant.binding.observation_boundary_evidence_refs[0],),
                )
            ]
        )
        receipt = port.complete(grant.action_instance_id, tool_outcome(port, grant.binding, temporal_evidence=proofs))
        assert receipt.accepted is (proof_mode != "foreign")

    plane, runtime, _, delivered, _ = delivery_plane(tmp_path, script, payload_transform=temporal_payload)
    with plane:
        plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
        assert not runtime.errors, runtime.errors
        require_participant_temporal_history(plane.snapshot)
        terminal = plane.snapshot.participant_behavior_history[PARTICIPANT][-1]
        expected = "met" if proof_mode == "valid" else "indeterminate"
        assert terminal["temporal_assessments"][0]["status"] == expected


@pytest.mark.parametrize("phase", ["admit", "dispatch"])
def test_live_authority_revocation_refuses_tool_effect(tmp_path, phase):
    from delivery_invocation_fixtures import (
        PARTICIPANT,
        caller,
        delivery_plane,
        invocation_request,
        tool_evidence,
        tool_request,
    )
    from raes_contracts.participant_tool_actions import ParticipantToolActionRefusal

    owners, grants = {}, []

    def script(invocation, port):
        if phase == "admit":
            owners["owner"].revoked = True
        decision = port.admit(tool_request(port), crossing_evidence=tool_evidence())
        if phase == "admit":
            assert decision.refusal is ParticipantToolActionRefusal.AUTHORITY_DENIED
        else:
            assert decision.admitted
            owners["owner"].revoked = True
            grants.append(port.dispatch(decision.action_instance_id))
            assert grants[-1].refusal is ParticipantToolActionRefusal.AUTHORITY_DENIED

    plane, runtime, owner, delivered, _ = delivery_plane(tmp_path, script)
    owners["owner"] = owner
    with plane:
        plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
        assert not runtime.errors, runtime.errors
        history = plane.snapshot.participant_behavior_history.get(PARTICIPANT, ())
        assert not history if phase == "admit" else history[-1]["action_result"]["status"] == "withheld"


@pytest.mark.parametrize("outer_failure", ["invalid", "failed", "exception", "cancelled"])
def test_settled_child_survives_enclosing_invocation_failure(tmp_path, outer_failure):
    from asyncio import CancelledError

    from delivery_invocation_fixtures import (
        PARTICIPANT,
        caller,
        delivery_plane,
        invocation_request,
        tool_evidence,
        tool_outcome,
        tool_request,
    )
    from raes_contracts.contracts.participant_delivery_invocation import ParticipantDeliveryInvocationOutcomeModel

    def script(invocation, port):
        decision = port.admit(tool_request(port), crossing_evidence=tool_evidence())
        grant = port.dispatch(decision.action_instance_id)
        assert grant.accepted
        assert port.complete(grant.action_instance_id, tool_outcome(port, grant.binding)).accepted
        if outer_failure == "exception":
            raise RuntimeError("synthetic enclosing failure")
        if outer_failure == "cancelled":
            raise CancelledError()
        return object() if outer_failure == "invalid" else ParticipantDeliveryInvocationOutcomeModel(status="failed")

    plane, runtime, _, delivered, _ = delivery_plane(tmp_path, script)
    with plane:
        if outer_failure == "cancelled":
            request, identity = invocation_request(delivered), caller()
            with pytest.raises(CancelledError):
                plane.invoke_participant_delivery(request, identity=identity)
        else:
            plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
        history = plane.snapshot.participant_behavior_history[PARTICIPANT]
        assert len(history) == 3
        assert history[-1]["action_result"]["status"] == "succeeded"
        assert runtime.port.closed
        assert not runtime.port.admit(tool_request(runtime.port), crossing_evidence=tool_evidence()).admitted


def test_restart_settles_interrupted_children_without_repeating_effects(tmp_path):
    import shutil

    from delivery_invocation_fixtures import (
        PARTICIPANT,
        caller,
        delivery_plane,
        invocation_request,
        tool_evidence,
        tool_request,
    )
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    durable, crashed = tmp_path / "durable", tmp_path / "crashed"
    seen = {}

    def script(invocation, port):
        admitted = port.admit(tool_request(port, tool_call_id="pending"), crossing_evidence=tool_evidence())
        dispatched = port.admit(tool_request(port, tool_call_id="running"), crossing_evidence=tool_evidence())
        assert admitted.admitted
        assert dispatched.admitted
        assert port.dispatch(dispatched.action_instance_id).accepted
        seen.update(admitted=admitted.action_instance_id, dispatched=dispatched.action_instance_id)
        shutil.copytree(durable, crashed)

    plane, runtime, _, delivered, _ = delivery_plane(tmp_path / "first", script, store=LocalControlPlaneStore(durable))
    with plane:
        plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
        assert not runtime.errors, runtime.errors
    restored, fresh_runtime, _, _, _ = delivery_plane(
        tmp_path / "second",
        store=LocalControlPlaneStore(crashed),
        resolver=plane._crossing_policy_resolver,
    )
    with restored:
        assert restored.get_operation(seen["admitted"]).state.value == "cancelled"
        assert restored.get_operation(seen["dispatched"]).state.value == "indeterminate"
        history = restored.snapshot.participant_behavior_history[PARTICIPANT]
        assert len(history) == 6
        assert {event["invocation_tool_context"]["settlement"] for event in history} == {"withheld", "indeterminate"}
        assert fresh_runtime.calls == 0
