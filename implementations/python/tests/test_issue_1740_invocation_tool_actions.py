"""Issue #1740: participant tool actions hosted inside an active autonomous invocation."""

from __future__ import annotations

import threading
from dataclasses import replace

import pytest
import yaml
from raes.parser import parse_sdl
from raes_backend_protocols.manifest import backend_manifest_from_v2_model, backend_manifest_payload
from raes_backend_protocols.participant_capabilities import ParticipantFeatureSupport
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts import (
    BackendManifestV2Model,
    ParticipantActionResultModel,
    ParticipantAutonomousExecutionStateModel,
    ParticipantBehaviorHistoryEventModel,
)
from raes_contracts.contracts.participant_invocation_tools import ParticipantInvocationToolActionCapabilitiesModel
from raes_contracts.contracts.participant_tool_support import ParticipantToolProfilesModel
from raes_contracts.participant_binding import ParticipantNativeActionExecution
from raes_contracts.participant_tool_actions import (
    INVOCATION_TOOL_ACTIONS_SEMANTICS,
    ParticipantToolActionRefusal,
    ParticipantToolActionRequest,
    ParticipantToolActionSettlement,
)
from raes_contracts.runtime_state import ApplyResult
from raes_processor.compiler import compile_runtime_model
from raes_runtime.manager import RuntimeManager
from raes_runtime.participant_invocation_tool_actions import ParticipantInvocationToolActions
from raes_runtime.participant_invocation_tool_settlement import InvocationToolActionConfiguration
from test_dsl_437_benign_participant_execution import (
    _autonomous_manifest,
    _NativeParticipantRuntime,
    _scenario_yaml,
)
from test_runtime_manager import close_runtime_owners as close_runtime_owners

AFFORDANCE = "participant.behavior-specification.participant-behavior.tool-affordance.portal-client"
ACTION = "participant.action-contract.probe-customer-portal-login"
BOUNDARY = "participant.observation-boundary.participant-view"
TARGET = "provision.node.customer-portal.service.http"
POLICY = "participant.autonomous-execution.participant-behavior"
CLOCK = "time.clock.scenario-clock"
FIRST = "participant.behavior.participant-agent"
SECOND = "participant.behavior.second-agent"
_WAIT_SECONDS = 10.0


def _tool_scenario_yaml(*, participants: int = 1, max_in_flight: int = 2, conflicting: bool = False) -> str:
    payload = yaml.safe_load(_scenario_yaml())
    if conflicting:
        payload["action_contracts"]["probe-customer-portal-login"]["interactions"] = [
            {
                "interaction_class": "shared_state_change",
                "target": "nodes.customer-portal.services.http",
                "rationale": "Concurrent login probes update one governed service state.",
                "shared_state_refs": ["nodes.customer-portal.services.http"],
            }
        ]
    reference = "behavior_specifications.participant-behavior.tool_affordances.portal-client"
    specification = payload["behavior_specifications"]["participant-behavior"]
    specification["tool_affordances"] = {
        "portal-client": {
            "action_contract_refs": ["probe-customer-portal-login"],
            "observation_boundary_refs": ["participant-view"],
        }
    }
    view = payload["observation_boundaries"]["participant-view"]
    view["observable_refs"].append(reference)
    view["view_rules"].append(
        {
            "information_ref": reference,
            "boundary_class": "observable_resource",
            "disposition": "observable",
            "visibility_basis": "authored participant-local affordance",
        }
    )
    if participants == 2:
        payload["agents"]["second-agent"] = dict(payload["agents"]["participant-agent"])
        specification["participant_refs"] = ["participant-agent", "second-agent"]
        specification["autonomous_execution"]["max_in_flight"] = max_in_flight
    return yaml.safe_dump(payload, sort_keys=False)


def _tool_manifest(
    runtime_model: object,
    *,
    claim: bool = True,
    offers: int = 1,
    max_actions: int = 4,
    max_concurrent: int = 2,
    with_realization_envelope: bool = True,
) -> object:
    manifest = _autonomous_manifest(runtime_model, with_realization_envelope=with_realization_envelope)
    runtime = manifest.capabilities.participant_runtime
    bindings = runtime.execution_bindings
    if offers == 0:
        bindings = tuple(
            replace(binding, participant_implementation_ref="other-implementation") for binding in bindings
        )
    elif offers == 2:
        bindings = (*bindings, replace(bindings[0], binding_id=bindings[0].binding_id + ".duplicate"))
    runtime = replace(
        runtime,
        supported_behavior_features=runtime.supported_behavior_features | {"tool_affordances"},
        feature_support=(
            *(entry for entry in runtime.feature_support if entry.feature != "tool_affordances"),
            ParticipantFeatureSupport(
                feature="tool_affordances",
                support_level="exact",
                evidence_refs=("evidence.synthetic.tool-probe",),
            ),
        ),
        tool_profiles=ParticipantToolProfilesModel(semantic_versions=["participant-tool-profile/v1"]),
        execution_bindings=bindings,
        invocation_tool_actions=(
            ParticipantInvocationToolActionCapabilitiesModel(
                semantic_versions=[INVOCATION_TOOL_ACTIONS_SEMANTICS],
                max_tool_actions_per_invocation=max_actions,
                max_concurrent_tool_actions_per_invocation=max_concurrent,
            )
            if claim
            else None
        ),
    )
    return replace(manifest, capabilities=replace(manifest.capabilities, participant_runtime=runtime))


def _ledger(store=None):
    from raes_contracts.operation_lifecycle import OperationAdmissionContext
    from raes_contracts.planning import RuntimeDomain
    from raes_contracts.runtime_state import OperationKind, OperationReceipt, OperationState, OperationStatus
    from raes_runtime.control_plane_store import ControlPlaneOperationRecord, InMemoryControlPlaneStore
    from raes_runtime.participant_execution_control import InvocationToolActionLedger

    store = store if store is not None else InMemoryControlPlaneStore()
    context = OperationAdmissionContext(
        actor_id="actor:test",
        authorization_scope=("scope:test",),
        target_scope="target:test",
        run_scope="run:test",
        operation_kind=OperationKind.COMPOSITION_PHASE,
        request_commitment="sha256:" + "0" * 64,
    )
    submitted = "2026-10-30T00:00:00Z"
    store.claim_record(
        ControlPlaneOperationRecord(
            receipt=OperationReceipt(
                operation_id="parent-due-operation",
                domain=RuntimeDomain.PARTICIPANT,
                submitted_at=submitted,
                accepted=True,
                context=context,
            ),
            status=OperationStatus(
                operation_id="parent-due-operation",
                domain=RuntimeDomain.PARTICIPANT,
                state=OperationState.ACCEPTED,
                submitted_at=submitted,
                updated_at=submitted,
                context=context,
            ),
        )
    )
    return InvocationToolActionLedger(store=store, parent_operation_id="parent-due-operation", parent_context=context)


class _ToolRuntime(_NativeParticipantRuntime):
    """Participant runtime whose harness calls tools through the attached port."""

    def __init__(self, script=None) -> None:
        super().__init__()
        self.script = script
        self.ports: dict[str, object] = {}
        self.attached: list[object] = []
        self.script_errors: list[BaseException] = []
        self._lock = threading.Lock()

    def attach_invocation_tool_actions(self, port) -> None:
        self.ports[port.invocation_action_instance_id] = port
        self.attached.append(port)

    def _model_action(self, request, snapshot, *, episode_id):
        port = self.ports.get(request.action_instance_id)
        if self.script is not None and port is not None:
            try:
                self.script(port, request)
            except Exception as exc:
                self.script_errors.append(exc)
                raise
        with self._lock:
            self.native_actions.append(request.action_instance_id)
        # Peers run concurrently, so the outer action writes no shared snapshot state.
        return ParticipantNativeActionExecution(
            apply_result=ApplyResult(success=True, snapshot=snapshot),
            action_result=ParticipantActionResultModel(
                status="succeeded",
                participant_address=request.participant_address,
                episode_id=episode_id,
                action_instance_id=request.action_instance_id,
                action_contract_address=request.action_contract_address,
                observation_point=request.temporal_contexts[0].observation_point,
            ),
        )


def _request(port, *, tool_call_id: str = "call-1", **overrides: object) -> ParticipantToolActionRequest:
    fields = {
        "tool_call_id": tool_call_id,
        "invocation_action_instance_id": port.invocation_action_instance_id,
        "participant_address": port.participant_address,
        "episode_id": port.episode_id,
        "participant_implementation_ref": port.participant_implementation_ref,
        "tool_affordance_address": AFFORDANCE,
        "action_contract_address": ACTION,
        "observation_boundary_address": BOUNDARY,
        "target_addresses": (TARGET,),
        "execution_scope_ref": port.execution_scope_ref,
        "execution_generation": port.execution_generation,
    }
    fields.update(overrides)
    return ParticipantToolActionRequest(**fields)


def _outcome(port, action_instance_id: str, *, status: str = "succeeded", **overrides: object):
    fields = {
        "status": status,
        "participant_address": port.participant_address,
        "episode_id": port.episode_id,
        "action_instance_id": action_instance_id,
        "action_contract_address": ACTION,
        "observation_point": port.observation_point,
        "observations": ["portal answered the tool call"],
    }
    fields.update(overrides)
    return ParticipantActionResultModel(**fields)


def _call_tool(port, tool_call_id: str = "call-1") -> str:
    decision = port.admit(_request(port, tool_call_id=tool_call_id))
    assert decision.admitted, decision.refusal
    assert port.dispatch(decision.action_instance_id).accepted
    assert port.complete(decision.action_instance_id, _outcome(port, decision.action_instance_id)).accepted
    return decision.action_instance_id


def _manager(
    runtime: _ToolRuntime,
    *,
    participants: int = 1,
    max_in_flight: int = 2,
    conflicting: bool = False,
    **manifest_options: object,
):
    scenario = parse_sdl(
        _tool_scenario_yaml(participants=participants, max_in_flight=max_in_flight, conflicting=conflicting)
    )
    runtime_model = compile_runtime_model(scenario)
    target = replace(
        create_stub_target(),
        manifest=_tool_manifest(runtime_model, **manifest_options),
        participant_runtime=runtime,
    )
    manager = RuntimeManager(target)
    return manager, scenario


def _events(snapshot, participant: str) -> list[ParticipantBehaviorHistoryEventModel]:
    return [
        ParticipantBehaviorHistoryEventModel.model_validate(event)
        for event in snapshot.participant_behavior_history.get(participant, ())
    ]


def _scheduler_state(snapshot, participant: str) -> ParticipantAutonomousExecutionStateModel:
    return ParticipantAutonomousExecutionStateModel.model_validate(
        snapshot.participant_autonomous_execution_states[f"{POLICY}.state.{participant}"]
    )


# Compilation and capability contracts.


def test_policy_compiles_exact_invocation_tool_relation_and_digest_covers_it() -> None:
    from raes_runtime.participant_scheduler_policy import _policy_digest

    runtime_model = compile_runtime_model(parse_sdl(_tool_scenario_yaml()))
    policy = runtime_model.behavior_specifications[
        "participant.behavior-specification.participant-behavior"
    ].autonomous_execution

    (binding,) = policy.invocation_tool_bindings
    assert binding.tool_affordance_address == AFFORDANCE
    assert binding.action_contract_address == ACTION
    assert binding.observation_boundary_addresses == (BOUNDARY,)
    assert binding.participant_addresses == (FIRST,)
    assert TARGET in binding.target_addresses
    assert binding.shared_time_bound is False
    assert _policy_digest(policy, runtime_model.time_model) != _policy_digest(
        replace(policy, invocation_tool_bindings=()), runtime_model.time_model
    )


def test_policy_without_affordances_keeps_its_digest_and_has_no_tool_relation() -> None:
    from raes_runtime.participant_scheduler_policy import _policy_digest

    plain = compile_runtime_model(parse_sdl(_scenario_yaml()))
    policy = plain.behavior_specifications[
        "participant.behavior-specification.participant-behavior"
    ].autonomous_execution
    assert policy.invocation_tool_bindings == ()
    assert _policy_digest(policy, plain.time_model) == _policy_digest(
        replace(policy, invocation_tool_bindings=()), plain.time_model
    )


def test_capability_claim_requires_autonomous_execution_and_tool_affordance_support() -> None:
    runtime_model = compile_runtime_model(parse_sdl(_tool_scenario_yaml()))
    payload = backend_manifest_payload(_tool_manifest(runtime_model, with_realization_envelope=False))
    claimed = payload["capabilities"]["participant_runtime"]["invocation_tool_actions"]
    assert claimed["semantic_versions"] == [INVOCATION_TOOL_ACTIONS_SEMANTICS]
    restored = backend_manifest_from_v2_model(BackendManifestV2Model.model_validate(payload))
    assert restored.participant_runtime.invocation_tool_actions.max_tool_actions_per_invocation == 4

    without_tools = backend_manifest_payload(_autonomous_manifest(runtime_model, with_realization_envelope=False))
    without_tools["capabilities"]["participant_runtime"]["invocation_tool_actions"] = claimed
    with pytest.raises(ValueError, match="tool_affordances"):
        BackendManifestV2Model.model_validate(without_tools)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"semantic_versions": ["participant-invocation-tool-actions/v9"]}, "semantic_versions"),
        ({"semantic_versions": []}, "semantic_versions"),
        ({"max_tool_actions_per_invocation": 0}, "max_tool_actions_per_invocation"),
        ({"max_concurrent_tool_actions_per_invocation": 5}, "cannot exceed"),
    ],
)
def test_capability_limits_are_finite_and_versioned(update: dict[str, object], message: str) -> None:
    payload = {
        "semantic_versions": [INVOCATION_TOOL_ACTIONS_SEMANTICS],
        "max_tool_actions_per_invocation": 4,
        "max_concurrent_tool_actions_per_invocation": 2,
    }
    payload.update(update)
    with pytest.raises(ValueError, match=message):
        ParticipantInvocationToolActionCapabilitiesModel.model_validate(payload)


def test_registration_refuses_claim_without_attach_method() -> None:
    runtime_model = compile_runtime_model(parse_sdl(_tool_scenario_yaml()))
    with pytest.raises(ValueError, match="attach_invocation_tool_actions"):
        replace(
            create_stub_target(),
            manifest=_tool_manifest(runtime_model),
            participant_runtime=_NativeParticipantRuntime(),
        )


@pytest.mark.parametrize(
    "fields",
    [
        {"tool_call_id": ""},
        {"tool_call_id": "has space"},
        {"tool_call_id": "x" * 129},
        {"target_addresses": ()},
        {"target_addresses": (TARGET, TARGET)},
        {"execution_generation": -1},
        {"execution_generation": True},
        {"participant_address": ""},
    ],
)
def test_request_shape_is_closed_and_bounded(fields: dict[str, object]) -> None:
    base = {
        "tool_call_id": "call-1",
        "invocation_action_instance_id": "outer",
        "participant_address": FIRST,
        "episode_id": "episode",
        "participant_implementation_ref": "implementation",
        "tool_affordance_address": AFFORDANCE,
        "action_contract_address": ACTION,
        "observation_boundary_address": BOUNDARY,
        "target_addresses": (TARGET,),
        "execution_scope_ref": POLICY,
        "execution_generation": 0,
    }
    base.update(fields)
    with pytest.raises((TypeError, ValueError)):
        ParticipantToolActionRequest(**base)


# Runtime admission, settlement and history.


def test_tool_action_commits_its_own_triple_before_the_outer_triple() -> None:
    issued: list[str] = []
    runtime = _ToolRuntime(lambda port, _outer: issued.append(_call_tool(port)))
    manager, scenario = _manager(runtime)

    applied = manager.apply(manager.plan(scenario))

    assert applied.success, applied.diagnostics
    (tool_id,) = issued
    events = _events(applied.snapshot, FIRST)
    assert [event.action_instance_id for event in events[:3]] == [tool_id] * 3
    outer_id = events[3].action_instance_id
    assert outer_id != tool_id
    assert [event.event_type.value for event in events] == [
        "action_attempted",
        "state_transition_recorded",
        "observation_emitted",
    ] * 2
    assert all(event.invocation_tool_context is None for event in events[3:])
    for event in events[:3]:
        context = event.invocation_tool_context
        assert context.semantics == INVOCATION_TOOL_ACTIONS_SEMANTICS
        assert context.invocation_action_instance_id == outer_id
        assert context.invocation_action_contract_address == ACTION
        assert context.tool_affordance_address == AFFORDANCE
        assert context.tool_call_id == "call-1"
        assert context.admission_ordinal == 0
        assert context.settlement == "completed"
        assert context.execution_scope_ref == POLICY
    assert events[2].action_result.status == "succeeded"
    assert events[2].observation_status.value == "terminal"
    assert runtime.native_actions == [outer_id]
    assert runtime.attached[0].closed


def test_tool_admission_progresses_from_another_thread_while_outer_waits() -> None:
    finished = threading.Event()

    def harness(port, _outer) -> None:
        worker = threading.Thread(target=lambda: (_call_tool(port), finished.set()))
        worker.start()
        worker.join(timeout=_WAIT_SECONDS)

    runtime = _ToolRuntime(harness)
    manager, scenario = _manager(runtime)

    applied = manager.apply(manager.plan(scenario))

    assert finished.is_set()
    assert applied.success, applied.diagnostics
    assert len(_events(applied.snapshot, FIRST)) == 6


def test_overlapping_tool_actions_finish_in_reverse_order_and_keep_peer_and_predecessor_history() -> None:
    both_dispatched = threading.Barrier(2, timeout=_WAIT_SECONDS)
    second_completed = threading.Event()
    completion_order: list[str] = []

    def harness(port, _outer) -> None:
        decision = port.admit(_request(port, tool_call_id=f"call-{port.participant_address[-5:]}"))
        assert port.dispatch(decision.action_instance_id).accepted
        both_dispatched.wait()
        if port.participant_address == FIRST:
            assert second_completed.wait(timeout=_WAIT_SECONDS)
        assert port.complete(decision.action_instance_id, _outcome(port, decision.action_instance_id)).accepted
        completion_order.append(port.participant_address)
        if port.participant_address == SECOND:
            second_completed.set()

    runtime = _ToolRuntime(harness)
    manager, scenario = _manager(runtime, participants=2)

    applied = manager.apply(manager.plan(scenario))

    assert applied.success, applied.diagnostics
    assert completion_order == [SECOND, FIRST]
    first_invocation = {participant: _events(applied.snapshot, participant) for participant in (FIRST, SECOND)}
    for events in first_invocation.values():
        assert len(events) == 6
        assert events[0].invocation_tool_context is not None
        assert events[3].invocation_tool_context is None

    runtime.script = lambda port, _outer: _call_tool(port, "call-next")
    advanced = manager.advance_time(CLOCK, ticks=10)

    assert advanced.success, advanced.diagnostics
    for participant, prior in first_invocation.items():
        events = _events(advanced.snapshot, participant)
        assert events[:6] == prior
        assert len(events) == 12


def test_undispatched_tool_is_withheld_and_dispatched_tool_without_outcome_is_indeterminate() -> None:
    def harness(port, _outer) -> None:
        port.admit(_request(port, tool_call_id="never-dispatched"))
        started = port.admit(_request(port, tool_call_id="never-completed"))
        assert port.dispatch(started.action_instance_id).accepted

    runtime = _ToolRuntime(harness)
    manager, scenario = _manager(runtime)

    applied = manager.apply(manager.plan(scenario))

    assert not applied.success
    assert any(d.code == "runtime.participant-invocation-tool-action-indeterminate" for d in applied.diagnostics)
    events = _events(applied.snapshot, FIRST)
    withheld, indeterminate, outer = events[0:3], events[3:6], events[6:9]
    assert withheld[2].action_result.status == "withheld"
    assert withheld[2].invocation_tool_context.settlement == "withheld"
    assert indeterminate[2].action_result.status == "unknown"
    assert indeterminate[2].observation_status.value == "orphaned_action"
    assert indeterminate[2].invocation_tool_context.settlement == "indeterminate"
    assert [event.invocation_tool_context for event in outer] == [None] * 3
    assert _scheduler_state(applied.snapshot, FIRST).lifecycle_state == "failed"


def test_reported_unknown_effects_are_retained_and_never_replayed() -> None:
    def harness(port, _outer) -> None:
        decision = port.admit(_request(port))
        assert port.dispatch(decision.action_instance_id).accepted
        receipt = port.report_unknown(decision.action_instance_id, "timeout")
        assert receipt.accepted
        assert receipt.settlement is ParticipantToolActionSettlement.INDETERMINATE
        assert port.report_unknown(decision.action_instance_id, "timeout").accepted
        assert port.complete(decision.action_instance_id, _outcome(port, decision.action_instance_id)).refusal is (
            ParticipantToolActionRefusal.OUTCOME_CONFLICT
        )

    runtime = _ToolRuntime(harness)
    manager, scenario = _manager(runtime)

    applied = manager.apply(manager.plan(scenario))

    assert not applied.success
    result = _events(applied.snapshot, FIRST)[2].action_result
    assert (result.status, result.failure_class.value) == ("unknown", "timeout")
    assert len(runtime.native_actions) == 1
    state = _scheduler_state(applied.snapshot, FIRST)
    assert (state.attempted_actions, state.lifecycle_state) == (1, "failed")


def test_outer_protocol_failure_keeps_tool_history_and_consumes_the_attempt() -> None:
    class _InvalidOuterRuntime(_ToolRuntime):
        def admit_action(self, request, snapshot):
            result = super().admit_action(request, snapshot)
            return replace(result, action_result=None)

    runtime = _InvalidOuterRuntime(lambda port, _outer: _call_tool(port))
    manager, scenario = _manager(runtime)

    applied = manager.apply(manager.plan(scenario))

    assert not applied.success
    assert any(d.code == "runtime.participant-autonomous-action-protocol-invalid" for d in applied.diagnostics)
    events = _events(applied.snapshot, FIRST)
    assert len(events) == 3
    assert events[2].invocation_tool_context.settlement == "completed"
    state = _scheduler_state(applied.snapshot, FIRST)
    assert (state.attempted_actions, state.lifecycle_state) == (1, "failed")


def test_raised_outer_invocation_keeps_tool_history_and_cannot_be_replayed() -> None:
    class _RaisingOuterRuntime(_ToolRuntime):
        def _model_action(self, request, snapshot, *, episode_id):
            super()._model_action(request, snapshot, episode_id=episode_id)
            raise RuntimeError("harness crashed")

    runtime = _RaisingOuterRuntime(lambda port, _outer: _call_tool(port))
    manager, scenario = _manager(runtime)

    applied = manager.apply(manager.plan(scenario))

    assert not applied.success
    assert any(d.code == "runtime.participant-invocation-indeterminate" for d in applied.diagnostics)
    assert len(_events(applied.snapshot, FIRST)) == 3
    state = _scheduler_state(applied.snapshot, FIRST)
    assert (state.attempted_actions, state.lifecycle_state) == (1, "failed")


def test_tool_events_returned_inside_the_outer_snapshot_stay_protocol_invalid() -> None:
    class _MergingOuterRuntime(_ToolRuntime):
        def admit_action(self, request, snapshot):
            result = super().admit_action(request, snapshot)
            history = {key: list(value) for key, value in result.snapshot.participant_behavior_history.items()}
            history[request.participant_address] = [
                *history[request.participant_address][:3],
                *history[request.participant_address],
            ]
            return replace(
                result,
                snapshot=result.snapshot.with_entries(
                    dict(result.snapshot.entries), participant_behavior_history=history
                ),
            )

    runtime = _MergingOuterRuntime()
    manager, scenario = _manager(runtime)

    applied = manager.apply(manager.plan(scenario))

    assert not applied.success
    assert any(d.code == "runtime.participant-autonomous-action-protocol-invalid" for d in applied.diagnostics)
    assert _events(applied.snapshot, FIRST) == []


def test_completion_after_outer_settlement_is_refused_as_stale() -> None:
    kept: list[tuple[object, str]] = []

    def harness(port, _outer) -> None:
        decision = port.admit(_request(port))
        port.dispatch(decision.action_instance_id)
        kept.append((port, decision.action_instance_id))

    runtime = _ToolRuntime(harness)
    manager, scenario = _manager(runtime)
    applied = manager.apply(manager.plan(scenario))
    port, action_instance_id = kept[0]

    late = port.complete(action_instance_id, _outcome(port, action_instance_id))
    late_admission = port.admit(_request(port, tool_call_id="late"))

    assert late.refusal is ParticipantToolActionRefusal.INVOCATION_CLOSED
    assert late_admission.refusal is ParticipantToolActionRefusal.INVOCATION_CLOSED
    assert _events(manager.snapshot, FIRST) == _events(applied.snapshot, FIRST)


def test_backend_without_claim_receives_no_port_and_runs_ordinary_actions() -> None:
    runtime = _ToolRuntime()
    manager, scenario = _manager(runtime, claim=False)

    applied = manager.apply(manager.plan(scenario))

    assert applied.success, applied.diagnostics
    assert runtime.attached == []
    assert len(_events(applied.snapshot, FIRST)) == 3


def test_authority_refusals_cause_no_effect_and_no_history() -> None:
    decisions: dict[str, object] = {}

    def harness(port, _outer) -> None:
        cases = {
            "participant": {"participant_address": SECOND},
            "episode": {"episode_id": "other-episode"},
            "implementation": {"participant_implementation_ref": "other-implementation"},
            "invocation": {"invocation_action_instance_id": "other-invocation"},
            "scope": {"execution_scope_ref": "participant.autonomous-execution.other"},
            "generation": {"execution_generation": port.execution_generation + 1},
            "affordance": {"tool_affordance_address": AFFORDANCE + "-other"},
            "action": {"action_contract_address": "participant.action-contract.other"},
            "boundary": {"observation_boundary_address": "participant.observation-boundary.other"},
            "target": {"target_addresses": ("provision.node.customer-db.service.postgres",)},
        }
        for name, overrides in cases.items():
            decisions[name] = port.admit(_request(port, tool_call_id=f"call-{name}", **overrides))

    runtime = _ToolRuntime(harness)
    manager, scenario = _manager(runtime)

    applied = manager.apply(manager.plan(scenario))

    assert applied.success, applied.diagnostics
    expected = {
        "participant": ParticipantToolActionRefusal.INVOCATION_MISMATCH,
        "episode": ParticipantToolActionRefusal.INVOCATION_MISMATCH,
        "implementation": ParticipantToolActionRefusal.INVOCATION_MISMATCH,
        "invocation": ParticipantToolActionRefusal.INVOCATION_MISMATCH,
        "scope": ParticipantToolActionRefusal.INVOCATION_MISMATCH,
        "generation": ParticipantToolActionRefusal.INVOCATION_MISMATCH,
        "affordance": ParticipantToolActionRefusal.BINDING_UNKNOWN,
        "action": ParticipantToolActionRefusal.BINDING_UNKNOWN,
        "boundary": ParticipantToolActionRefusal.OBSERVATION_BOUNDARY_UNBOUND,
        "target": ParticipantToolActionRefusal.TARGET_UNBOUND,
    }
    assert {name: decision.refusal for name, decision in decisions.items()} == expected
    assert not any(decision.admitted for decision in decisions.values())
    assert all(decision.action_instance_id is None for decision in decisions.values())
    assert len(_events(applied.snapshot, FIRST)) == 3


@pytest.mark.parametrize(
    ("offers", "refusal"),
    [
        (0, ParticipantToolActionRefusal.EXECUTION_OFFER_MISSING),
        (2, ParticipantToolActionRefusal.EXECUTION_OFFER_AMBIGUOUS),
    ],
)
def test_tool_action_requires_one_exact_manifest_execution_offer(
    offers: int, refusal: ParticipantToolActionRefusal
) -> None:
    scenario = parse_sdl(_tool_scenario_yaml())
    runtime_model = compile_runtime_model(scenario)
    manifest = _tool_manifest(runtime_model, offers=offers)
    configuration = InvocationToolActionConfiguration.from_manifest(manifest.participant_runtime, ledger=_ledger())
    assert configuration is not None
    port = _direct_port(runtime_model, configuration)

    assert port.admit(_request(port)).refusal is refusal


def test_replay_conflict_limits_and_state_refusals() -> None:
    observed: dict[str, object] = {}

    def harness(port, _outer) -> None:
        first = port.admit(_request(port, tool_call_id="call-a"))
        observed["replay"] = port.admit(_request(port, tool_call_id="call-a"))
        observed["conflict"] = port.admit(
            _request(port, tool_call_id="call-a", target_addresses=(TARGET, "provision.node.wazuh-manager"))
        )
        second = port.admit(_request(port, tool_call_id="call-b"))
        observed["limit"] = port.admit(_request(port, tool_call_id="call-c"))
        observed["complete_before_dispatch"] = port.complete(
            first.action_instance_id, _outcome(port, first.action_instance_id)
        )
        observed["dispatch"] = port.dispatch(first.action_instance_id)
        observed["dispatch_again"] = port.dispatch(first.action_instance_id)
        observed["concurrency"] = port.dispatch(second.action_instance_id)
        observed["cancel_after_dispatch"] = port.cancel(first.action_instance_id)
        observed["nonterminal"] = port.complete(
            first.action_instance_id, _outcome(port, first.action_instance_id, status="accepted")
        )
        observed["foreign_outcome"] = port.complete(first.action_instance_id, _outcome(port, second.action_instance_id))
        observed["complete"] = port.complete(first.action_instance_id, _outcome(port, first.action_instance_id))
        observed["complete_replay"] = port.complete(first.action_instance_id, _outcome(port, first.action_instance_id))
        observed["complete_conflict"] = port.complete(
            first.action_instance_id, _outcome(port, first.action_instance_id, status="failed")
        )
        observed["cancel_before_dispatch"] = port.cancel(second.action_instance_id)
        observed["unknown_action"] = port.dispatch("participant-tool-action-unknown")
        observed["first"] = first

    runtime = _ToolRuntime(harness)
    manager, scenario = _manager(runtime, max_actions=2, max_concurrent=1)

    applied = manager.apply(manager.plan(scenario))

    assert applied.success, applied.diagnostics
    first = observed["first"]
    assert observed["replay"] == first
    refusals = {name: getattr(value, "refusal", None) for name, value in observed.items()}
    assert refusals["conflict"] is ParticipantToolActionRefusal.REQUEST_CONFLICT
    assert refusals["limit"] is ParticipantToolActionRefusal.ADMISSION_LIMIT_EXHAUSTED
    assert refusals["complete_before_dispatch"] is ParticipantToolActionRefusal.STATE_CONFLICT
    assert observed["dispatch"].accepted
    assert refusals["dispatch_again"] is ParticipantToolActionRefusal.STATE_CONFLICT
    assert refusals["concurrency"] is ParticipantToolActionRefusal.CONCURRENCY_LIMIT_EXHAUSTED
    assert refusals["cancel_after_dispatch"] is ParticipantToolActionRefusal.STATE_CONFLICT
    assert refusals["nonterminal"] is ParticipantToolActionRefusal.OUTCOME_INVALID
    assert refusals["foreign_outcome"] is ParticipantToolActionRefusal.OUTCOME_INVALID
    assert observed["complete"].accepted
    assert observed["complete_replay"].accepted
    assert refusals["complete_conflict"] is ParticipantToolActionRefusal.OUTCOME_CONFLICT
    assert observed["cancel_before_dispatch"].settlement is ParticipantToolActionSettlement.WITHHELD
    assert refusals["unknown_action"] is ParticipantToolActionRefusal.ACTION_UNKNOWN
    events = _events(applied.snapshot, FIRST)
    assert [event.invocation_tool_context.tool_call_id for event in events[:6:3]] == ["call-a", "call-b"]
    assert [event.action_result.status for event in events[2:6:3]] == ["succeeded", "withheld"]


# Direct port checks for unsupported compositions.


def _direct_port(runtime_model, configuration, *, policy_update: dict[str, object] | None = None):
    from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
    from test_dsl_437_benign_participant_execution import _implementation_manifest, _selection

    policy = runtime_model.behavior_specifications[
        "participant.behavior-specification.participant-behavior"
    ].autonomous_execution
    policy = replace(policy, **(policy_update or {}))
    outer = ParticipantActionAdmissionRequest(
        participant_address=FIRST,
        action_contract_address=ACTION,
        observation_boundary_address=BOUNDARY,
        action_instance_id="outer-action",
        implementation_manifest=_implementation_manifest(),
        implementation_selection=_selection(FIRST),
        requires_terminal_outcome=True,
        target_addresses=policy.execution_bindings[0].target_addresses,
        execution_scope_ref=POLICY,
        execution_generation=0,
    )
    port = ParticipantInvocationToolActions(
        outer=outer,
        episode_id="episode-1",
        policy=policy,
        configuration=configuration,
        scheduler_state_key=f"{POLICY}.state.{FIRST}",
        prior_history_length=0,
    )
    port.activate()
    return port


@pytest.mark.parametrize(
    ("policy_update", "crossing", "refusal"),
    [
        (
            {"profile": "participant-autonomous-execution/v3"},
            False,
            ParticipantToolActionRefusal.RESOURCE_GOVERNANCE_UNSUPPORTED,
        ),
        (None, True, ParticipantToolActionRefusal.CROSSING_MEDIATION_UNSUPPORTED),
        ("shared-time", False, ParticipantToolActionRefusal.TEMPORAL_BINDING_UNSUPPORTED),
    ],
)
def test_unsupported_compositions_refuse_before_effects(policy_update, crossing: bool, refusal) -> None:
    runtime_model = compile_runtime_model(parse_sdl(_tool_scenario_yaml()))
    configuration = InvocationToolActionConfiguration.from_manifest(
        _tool_manifest(runtime_model).participant_runtime, ledger=_ledger(), crossing_installed=crossing
    )
    if policy_update == "shared-time":
        policy = runtime_model.behavior_specifications[
            "participant.behavior-specification.participant-behavior"
        ].autonomous_execution
        policy_update = {
            "invocation_tool_bindings": tuple(
                replace(binding, shared_time_bound=True) for binding in policy.invocation_tool_bindings
            )
        }
    port = _direct_port(runtime_model, configuration, policy_update=policy_update)

    decision = port.admit(_request(port))

    assert decision.refusal is refusal
    assert port.close() == ()


# Attachment, cancellation and settlement failure paths.


class _AttachFailsRuntime(_ToolRuntime):
    def attach_invocation_tool_actions(self, port) -> None:
        raise RuntimeError("attach failed")


@pytest.mark.parametrize("participants", [1, 2])
def test_failed_attachment_dispatches_nothing(participants: int) -> None:
    runtime = _AttachFailsRuntime(lambda port, _outer: _call_tool(port))
    manager, scenario = _manager(runtime, participants=participants)

    applied = manager.apply(manager.plan(scenario))

    assert not applied.success
    assert any(d.code == "runtime.participant-invocation-tool-attach-failed" for d in applied.diagnostics)
    assert runtime.native_actions == []
    assert _events(applied.snapshot, FIRST) == []


def test_raised_concurrent_batch_keeps_every_peer_tool_history() -> None:
    def harness(port, _outer) -> None:
        _call_tool(port)
        if port.participant_address == SECOND:
            raise RuntimeError("second harness crashed")

    runtime = _ToolRuntime(harness)
    manager, scenario = _manager(runtime, participants=2)

    applied = manager.apply(manager.plan(scenario))

    assert not applied.success
    for participant in (FIRST, SECOND):
        events = _events(applied.snapshot, participant)
        assert [event.invocation_tool_context.settlement for event in events] == ["completed"] * 3
        assert _scheduler_state(applied.snapshot, participant).attempted_actions == 1


def _session_run(port, snapshot):
    from raes_runtime.participant_scheduler_types import SchedulerRunState

    run = SchedulerRunState(working=snapshot, diagnostics=[], changed=[])
    run.tool_sessions.append(port)
    return run


def _applied_snapshot_and_port():
    kept: list[object] = []

    def harness(port, _outer) -> None:
        kept.append(port)

    runtime = _ToolRuntime(harness)
    manager, scenario = _manager(runtime)
    applied = manager.apply(manager.plan(scenario))
    assert applied.success, applied.diagnostics
    configuration = InvocationToolActionConfiguration.from_manifest(
        _tool_manifest(compile_runtime_model(scenario)).participant_runtime, ledger=_ledger()
    )
    return configuration, applied.snapshot, kept[0]


def _fresh_port_like(port, configuration):
    fresh = ParticipantInvocationToolActions(
        outer=port.outer,
        episode_id=port.episode_id,
        policy=port.policy,
        configuration=configuration,
        scheduler_state_key=port.scheduler_state_key,
        prior_history_length=0,
    )
    fresh.activate()
    return fresh


def test_settlement_after_generation_change_commits_no_tool_history() -> None:
    from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel
    from raes_runtime.participant_invocation_tool_settlement import settle_invocation_tool_sessions

    configuration, snapshot, closed_port = _applied_snapshot_and_port()
    port = _fresh_port_like(closed_port, configuration)
    _call_tool(port)
    services = dict(snapshot.participant_execution_services)
    service = ParticipantExecutionServiceStateModel.model_validate(services[POLICY])
    services[POLICY] = service.model_copy(
        update={"generation": service.generation + 1, "observed_generation": service.generation + 1}
    ).model_dump(mode="json")
    stale = snapshot.with_entries(dict(snapshot.entries), participant_execution_services=services)
    run = _session_run(port, stale)

    settle_invocation_tool_sessions(run)

    assert run.failure is not None
    assert [d.code for d in run.diagnostics] == ["runtime.participant-invocation-tool-settlement-stale"]
    assert _events(run.working, FIRST) == _events(snapshot, FIRST)


def test_settlement_merges_into_a_distinct_failure_snapshot() -> None:
    from raes_runtime.participant_invocation_tool_settlement import settle_invocation_tool_sessions

    configuration, snapshot, closed_port = _applied_snapshot_and_port()
    port = _fresh_port_like(closed_port, configuration)
    _call_tool(port)
    run = _session_run(port, snapshot)
    failed_snapshot = snapshot.with_entries(dict(snapshot.entries))
    run.failure = ApplyResult(success=False, snapshot=failed_snapshot, diagnostics=[])

    settle_invocation_tool_sessions(run)

    assert len(_events(run.working, FIRST)) == 6
    assert len(_events(run.failure.snapshot, FIRST)) == 6
    assert FIRST in run.failure.changed_addresses


def test_cancelled_outer_invocation_settles_tool_history_before_the_cancellation_sink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from asyncio import CancelledError

    import raes_runtime.participant_scheduler as scheduler_module
    from raes_runtime.participant_invocation_tool_settlement import admit_outer_action
    from raes_runtime.participant_scheduler import ParticipantScheduler

    configuration, snapshot, closed_port = _applied_snapshot_and_port()
    port = _fresh_port_like(closed_port, configuration)

    class _CancellingRuntime:
        def admit_action(self, request, predecessor):
            _call_tool(port)
            raise CancelledError

    class _Context:
        policy = port.policy
        participant_runtime = _CancellingRuntime()
        participant_address = FIRST
        key = port.scheduler_state_key

    def due_policy(policy, time_model, participant_runtime, controls, run) -> None:
        run.tool_sessions.append(port)
        result = admit_outer_action(_Context(), port.outer, run.working, port, run)
        assert result is not None
        run.failure = ApplyResult(success=False, snapshot=run.working, diagnostics=run.diagnostics)

    monkeypatch.setattr(scheduler_module, "_run_due_policy", due_policy)
    settled: list[ApplyResult] = []

    with pytest.raises(CancelledError):
        ParticipantScheduler.run_due([object()], object(), object(), snapshot, cancellation_sink=settled.append)

    assert port.closed
    (result,) = settled
    assert any(d.code == "runtime.participant-invocation-indeterminate" for d in result.diagnostics)
    assert len(_events(result.snapshot, FIRST)) == 6


def test_committed_tool_history_round_trips_through_the_local_store(tmp_path) -> None:
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    runtime = _ToolRuntime(lambda port, _outer: _call_tool(port))
    manager, scenario = _manager(runtime)
    applied = manager.apply(manager.plan(scenario))
    assert applied.success, applied.diagnostics
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    store.admit_runtime(target_scope="target:stub", run_scope="run:test")

    store.save_snapshot(applied.snapshot, expected_revision=store.load_snapshot_state().revision)
    loaded = store.load_snapshot()

    assert _events(loaded, FIRST) == _events(applied.snapshot, FIRST)
    assert _events(loaded, FIRST)[0].invocation_tool_context.settlement == "completed"


# Review cycle 1 regressions.


def test_port_is_inactive_while_the_backend_attaches_it() -> None:
    attach_decisions: list[object] = []

    class _EagerAttachRuntime(_ToolRuntime):
        def attach_invocation_tool_actions(self, port) -> None:
            super().attach_invocation_tool_actions(port)
            attach_decisions.append(port.admit(_request(port, tool_call_id="during-attach")))
            attach_decisions.append(port.dispatch("participant-tool-action-guess"))

    runtime = _EagerAttachRuntime(lambda port, _outer: _call_tool(port))
    manager, scenario = _manager(runtime)

    applied = manager.apply(manager.plan(scenario))

    assert applied.success, applied.diagnostics
    assert [decision.refusal for decision in attach_decisions] == [
        ParticipantToolActionRefusal.INVOCATION_INACTIVE,
        ParticipantToolActionRefusal.INVOCATION_INACTIVE,
    ]
    tool_call_ids = [event.invocation_tool_context.tool_call_id for event in _events(applied.snapshot, FIRST)[:3]]
    assert tool_call_ids == ["call-1"] * 3


def test_cancelled_attachment_leaves_a_registered_closed_port() -> None:
    from asyncio import CancelledError

    from raes_runtime.participant_invocation_tool_settlement import open_invocation_tool_session
    from raes_runtime.participant_scheduler_types import SchedulerRunState

    configuration, snapshot, closed_port = _applied_snapshot_and_port()

    class _CancellingAttach:
        def attach_invocation_tool_actions(self, port) -> None:
            assert port.admit(_request(port)).refusal is ParticipantToolActionRefusal.INVOCATION_INACTIVE
            raise CancelledError

    class _Context:
        policy = closed_port.policy
        participant_runtime = _CancellingAttach()
        participant_address = FIRST
        key = closed_port.scheduler_state_key

    run = SchedulerRunState(working=snapshot, diagnostics=[], changed=[], invocation_tools=configuration)

    with pytest.raises(CancelledError):
        open_invocation_tool_session(
            _Context(), closed_port.outer, episode_id=closed_port.episode_id, predecessor=snapshot, run=run
        )

    (registered,) = run.tool_sessions
    assert registered.closed
    assert registered.close() == ()


def test_tool_outcome_must_pass_canonical_exposure_and_observation_binding() -> None:
    receipts: dict[str, object] = {}

    def harness(port, _outer) -> None:
        for name, overrides in {
            "withheld": {"evidence_refs": ["content.evaluator-notes"]},
            "undeclared": {"evidence_refs": ["content.not-in-boundary"]},
            "observation_point": {"observation_point": "somewhere-else"},
            "declared": {"evidence_refs": ["content.participant-observation"]},
        }.items():
            decision = port.admit(_request(port, tool_call_id=f"call-{name}"))
            assert port.dispatch(decision.action_instance_id).accepted
            receipts[name] = port.complete(
                decision.action_instance_id, _outcome(port, decision.action_instance_id, **overrides)
            )
            if not receipts[name].accepted:
                assert port.complete(
                    decision.action_instance_id, _outcome(port, decision.action_instance_id, status="failed")
                ).accepted

    runtime = _ToolRuntime(harness)
    manager, scenario = _manager(runtime)

    applied = manager.apply(manager.plan(scenario))

    refusals = {name: receipt.refusal for name, receipt in receipts.items()}
    assert refusals == {
        "withheld": ParticipantToolActionRefusal.OUTCOME_INVALID,
        "undeclared": ParticipantToolActionRefusal.OUTCOME_INVALID,
        "observation_point": ParticipantToolActionRefusal.OUTCOME_INVALID,
        "declared": None,
    }
    events = _events(applied.snapshot, FIRST)
    assert "content.evaluator-notes" not in str([event.model_dump() for event in events])
    declared = next(event for event in events if event.invocation_tool_context.tool_call_id == "call-declared")
    assert declared.invocation_tool_context.settlement == "completed"


def _child_records(store) -> dict[str, object]:
    return {
        operation_id: record
        for operation_id, record in store.load_records().items()
        if (record.result_payload or {}).get("kind") == "participant-invocation-tool-action/v1"
    }


def test_durable_store_retains_claims_before_decisions_and_grants(tmp_path) -> None:
    from raes_contracts.runtime_state import OperationState
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    store = LocalControlPlaneStore(tmp_path / "control-plane")
    observed: dict[str, object] = {}

    def harness(port, _outer) -> None:
        decision = port.admit(_request(port))
        observed["after_admit"] = _child_records(store)[decision.action_instance_id].status.state
        assert port.dispatch(decision.action_instance_id).accepted
        observed["after_dispatch"] = _child_records(store)[decision.action_instance_id].status.state
        assert port.complete(decision.action_instance_id, _outcome(port, decision.action_instance_id)).accepted
        observed["after_complete"] = _child_records(store)[decision.action_instance_id]
        observed["action_instance_id"] = decision.action_instance_id

    runtime = _ToolRuntime(harness)
    scenario = parse_sdl(_tool_scenario_yaml())
    target = replace(
        create_stub_target(),
        manifest=_tool_manifest(compile_runtime_model(scenario)),
        participant_runtime=runtime,
    )
    manager = RuntimeManager(target, store=store)

    applied = manager.apply(manager.plan(scenario))

    assert applied.success, applied.diagnostics
    assert observed["after_admit"] is OperationState.ACCEPTED
    assert observed["after_dispatch"] is OperationState.RUNNING
    terminal = observed["after_complete"]
    assert terminal.status.state is OperationState.SUCCEEDED
    assert terminal.receipt.context.parent_operation_id is not None
    assert terminal.result_payload["settlement"] == "completed"
    assert terminal.result_payload["action_result"]["status"] == "succeeded"
    assert manager.get_operation(observed["action_instance_id"]).state is OperationState.SUCCEEDED
    assert len(_events(applied.snapshot, FIRST)) == 6


def test_restart_classifies_interrupted_tool_claims_without_replay(tmp_path) -> None:
    import shutil

    from raes_contracts.runtime_state import OperationState
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    store_path = tmp_path / "control-plane"
    crashed_path = tmp_path / "crashed"
    claims: dict[str, str] = {}

    def harness(port, _outer) -> None:
        admitted = port.admit(_request(port, tool_call_id="admitted-only"))
        dispatched = port.admit(_request(port, tool_call_id="dispatched"))
        assert port.dispatch(dispatched.action_instance_id).accepted
        claims["admitted"] = admitted.action_instance_id
        claims["dispatched"] = dispatched.action_instance_id
        # The copy is the durable state that a process loss at this point would leave.
        shutil.copytree(store_path, crashed_path)

    runtime = _ToolRuntime(harness)
    scenario = parse_sdl(_tool_scenario_yaml())
    target = replace(
        create_stub_target(),
        manifest=_tool_manifest(compile_runtime_model(scenario)),
        participant_runtime=runtime,
    )
    manager = RuntimeManager(target, store=LocalControlPlaneStore(store_path))
    manager.apply(manager.plan(scenario))
    manager.close()

    restarted_target = replace(
        create_stub_target(),
        manifest=_tool_manifest(compile_runtime_model(scenario)),
        participant_runtime=_ToolRuntime(),
    )
    restarted = RuntimeManager(restarted_target, store=LocalControlPlaneStore(crashed_path))

    assert restarted.get_operation(claims["admitted"]).state is OperationState.CANCELLED
    assert restarted.get_operation(claims["dispatched"]).state is OperationState.INDETERMINATE
    assert len(runtime.native_actions) == 1


def _parent_reservation(child, **overrides):
    from types import SimpleNamespace

    from raes_contracts.runtime_state import OperationKind, OperationState

    context = child.status.context.model_copy(
        update={"operation_kind": OperationKind.COMPOSITION_PHASE, "parent_operation_id": None}
    )
    values = {"state": OperationState.RUNNING, "context": context, "operation_id": "parent-due-operation"}
    values.update(overrides)
    return SimpleNamespace(
        invocation=SimpleNamespace(reserved=True),
        reconciliation=None,
        receipt=SimpleNamespace(operation_id=values["operation_id"]),
        status=SimpleNamespace(state=values["state"], context=values["context"]),
    )


def _claimed_child():
    from raes_contracts.participant_tool_actions import tool_action_instance_id

    request = ParticipantToolActionRequest(
        tool_call_id="call-1",
        invocation_action_instance_id="outer",
        participant_address=FIRST,
        episode_id="episode",
        participant_implementation_ref="implementation",
        tool_affordance_address=AFFORDANCE,
        action_contract_address=ACTION,
        observation_boundary_address=BOUNDARY,
        target_addresses=(TARGET,),
        execution_scope_ref=POLICY,
        execution_generation=0,
    )
    action_instance_id = tool_action_instance_id(
        "outer", episode_id="episode", execution_generation=0, tool_call_id="call-1"
    )
    return _ledger().record_admission(action_instance_id, request, "2026-10-30T00:00:00Z")


def test_only_a_validated_tool_child_is_compatible_with_its_parent_reservation() -> None:
    from raes_contracts.runtime_state import OperationKind, OperationState
    from raes_runtime.operation_invocation_ledger import supervised_claim_conflicts
    from raes_runtime.participant_invocation_tool_claims import invocation_tool_child_of

    child = _claimed_child()
    parent = _parent_reservation(child)
    assert invocation_tool_child_of(parent, child)
    assert not supervised_claim_conflicts(child, [parent])

    context = child.status.context
    tampered = {
        "other parent": _parent_reservation(child, operation_id="another-operation"),
        "parent not running": _parent_reservation(child, state=OperationState.INDETERMINATE),
        "parent not a due pass": _parent_reservation(
            child, context=context.model_copy(update={"operation_kind": OperationKind.PARTICIPANT_ACTION})
        ),
        "other actor": _parent_reservation(
            child,
            context=context.model_copy(
                update={"operation_kind": OperationKind.COMPOSITION_PHASE, "actor_id": "actor:other"}
            ),
        ),
    }
    for name, other_parent in tampered.items():
        assert not invocation_tool_child_of(other_parent, child), name
        assert supervised_claim_conflicts(child, [other_parent]), name

    forged_payload = replace(child, result_payload={**child.result_payload, "target_addresses": ["provision.other"]})
    forged_key = replace(child, idempotency_key="invocation-tool-action:other")
    from types import SimpleNamespace

    with_invocation = SimpleNamespace(
        invocation=object(),
        receipt=child.receipt,
        status=child.status,
        idempotency_key=child.idempotency_key,
        result_payload=child.result_payload,
    )
    for name, forged in {"payload": forged_payload, "key": forged_key, "invocation": with_invocation}.items():
        assert not invocation_tool_child_of(parent, forged), name


class _FailingStore:
    """In-memory store whose selected writes fail like an unavailable durable store."""

    def __init__(self, failing: set[str], error: type[Exception] | None = None) -> None:
        from raes_contracts.errors import OperationalError
        from raes_runtime.control_plane_store import InMemoryControlPlaneStore

        self._store = InMemoryControlPlaneStore()
        self.failing = failing
        self.error = error or OperationalError

    def __getattr__(self, name: str):
        method = getattr(self._store, name)
        if name not in self.failing:
            return method

        def fail(*_args, **_kwargs):
            raise self.error("store unavailable")

        return fail


def test_store_write_failure_refuses_decisions_and_grants_and_fails_closure() -> None:
    from raes_runtime.participant_invocation_tool_settlement import settle_invocation_tool_sessions

    configuration, snapshot, closed_port = _applied_snapshot_and_port()
    store = _FailingStore(set())
    port = _fresh_port_like(closed_port, replace(configuration, ledger=_ledger(store)))
    store.failing = {"claim_record"}

    assert port.admit(_request(port)).refusal is ParticipantToolActionRefusal.LEDGER_UNAVAILABLE

    store.failing = {"save_record"}
    decision = port.admit(_request(port, tool_call_id="call-2"))
    assert decision.admitted
    assert port.dispatch(decision.action_instance_id).refusal is ParticipantToolActionRefusal.LEDGER_UNAVAILABLE

    store.failing = {"commit_terminal_operation"}
    assert port.cancel(decision.action_instance_id).refusal is ParticipantToolActionRefusal.LEDGER_UNAVAILABLE
    run = _session_run(port, snapshot)

    settle_invocation_tool_sessions(run)

    assert port.ledger_failures == 1
    assert run.failure is not None
    assert "runtime.participant-invocation-tool-ledger-failed" in [d.code for d in run.diagnostics]
    assert _events(run.working, FIRST)[2].action_result.status == "withheld"


# Review cycle 2 regressions.


def test_outer_backend_returning_none_consumes_the_attempt_without_redispatch() -> None:
    class _NoneOuterRuntime(_ToolRuntime):
        def __init__(self) -> None:
            super().__init__()
            self.admit_calls = 0

        def admit_action(self, request, snapshot):
            self.admit_calls += 1
            return None

    runtime = _NoneOuterRuntime()
    manager, scenario = _manager(runtime, claim=False)

    applied = manager.apply(manager.plan(scenario))

    assert not applied.success
    assert any(d.code == "runtime.participant-autonomous-action-protocol-invalid" for d in applied.diagnostics)
    assert runtime.admit_calls == 1
    state = _scheduler_state(applied.snapshot, FIRST)
    assert (state.attempted_actions, state.lifecycle_state) == (1, "failed")


def test_cancelled_concurrent_attachment_restores_the_reserved_batch() -> None:
    from asyncio import CancelledError

    from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel

    class _CancelSecondAttach(_ToolRuntime):
        def attach_invocation_tool_actions(self, port) -> None:
            if port.participant_address == SECOND:
                raise CancelledError
            super().attach_invocation_tool_actions(port)

    runtime = _CancelSecondAttach(lambda port, _outer: _call_tool(port))
    manager, scenario = _manager(runtime, participants=2)

    try:
        manager.apply(manager.plan(scenario))
    except CancelledError:
        pass

    snapshot = manager.snapshot
    assert runtime.native_actions == []
    for participant in (FIRST, SECOND):
        state = _scheduler_state(snapshot, participant)
        assert (state.attempted_actions, state.in_flight) == (0, 0)
    service = ParticipantExecutionServiceStateModel.model_validate(snapshot.participant_execution_services[POLICY])
    assert (service.reserved, service.in_flight) == (0, 0)


def test_tool_action_identity_is_unique_across_episodes_and_generations() -> None:
    from raes_contracts.participant_tool_actions import tool_action_instance_id

    identities = {
        tool_action_instance_id("outer", episode_id=episode, execution_generation=generation, tool_call_id="call-1")
        for episode in ("episode-1", "episode-2")
        for generation in (0, 1)
    }
    assert len(identities) == 4


def test_reused_call_id_is_admitted_again_after_a_clock_reset() -> None:
    decisions: list[object] = []

    def harness(port, _outer) -> None:
        decision = port.admit(_request(port, tool_call_id="call-1"))
        decisions.append(decision)
        if decision.admitted:
            port.cancel(decision.action_instance_id)

    runtime = _ToolRuntime(harness)
    manager, scenario = _manager(runtime)
    assert manager.apply(manager.plan(scenario)).success

    reset = manager.reset_time(CLOCK)
    assert reset.success, reset.diagnostics
    due = manager.run_due_participant_actions()

    assert due.success, due.diagnostics
    assert [decision.admitted for decision in decisions] == [True, True]
    assert decisions[0].action_instance_id != decisions[1].action_instance_id


# Review cycle 3 regressions.


def test_unknown_effects_fence_later_grants_but_let_accepted_work_settle() -> None:
    observed: dict[str, object] = {}

    def harness(port, _outer) -> None:
        first = port.admit(_request(port, tool_call_id="call-a"))
        running = port.admit(_request(port, tool_call_id="call-b"))
        waiting = port.admit(_request(port, tool_call_id="call-c"))
        assert port.dispatch(first.action_instance_id).accepted
        assert port.dispatch(running.action_instance_id).accepted
        assert port.report_unknown(first.action_instance_id, "timeout").accepted
        observed["new_admission"] = port.admit(_request(port, tool_call_id="call-d"))
        observed["waiting_dispatch"] = port.dispatch(waiting.action_instance_id)
        observed["running_complete"] = port.complete(
            running.action_instance_id, _outcome(port, running.action_instance_id)
        )

    runtime = _ToolRuntime(harness)
    manager, scenario = _manager(runtime, max_concurrent=2)

    applied = manager.apply(manager.plan(scenario))

    assert not applied.success
    assert observed["new_admission"].refusal is ParticipantToolActionRefusal.UNRESOLVED_EFFECTS
    assert observed["waiting_dispatch"].refusal is ParticipantToolActionRefusal.UNRESOLVED_EFFECTS
    assert observed["running_complete"].accepted


def test_unknown_effects_stop_later_outer_dispatch_in_the_same_pass() -> None:
    def harness(port, _outer) -> None:
        decision = port.admit(_request(port))
        assert port.dispatch(decision.action_instance_id).accepted
        assert port.report_unknown(decision.action_instance_id, "timeout").accepted

    runtime = _ToolRuntime(harness)
    manager, scenario = _manager(runtime, participants=2, max_in_flight=1)

    applied = manager.apply(manager.plan(scenario))

    assert not applied.success
    assert any(d.code == "runtime.participant-invocation-tool-effects-fenced" for d in applied.diagnostics)
    assert len(runtime.native_actions) == 1
    assert _scheduler_state(applied.snapshot, SECOND).attempted_actions == 0


def test_store_barrier_refuses_a_new_port_after_another_child_is_indeterminate() -> None:
    configuration, _snapshot, closed_port = _applied_snapshot_and_port()
    shared = replace(configuration, ledger=_ledger())
    first = _fresh_port_like(closed_port, shared)
    decision = first.admit(_request(first, tool_call_id="call-a"))
    assert first.dispatch(decision.action_instance_id).accepted
    assert first.report_unknown(decision.action_instance_id, "timeout").accepted

    second = _fresh_port_like(closed_port, shared)

    assert second.admit(_request(second, tool_call_id="call-b")).refusal is (
        ParticipantToolActionRefusal.UNRESOLVED_EFFECTS
    )


def test_grant_requires_a_live_parent_and_open_effect_admission() -> None:
    from raes_runtime.control_plane_store import AuditEvent, TerminalCommitMode

    configuration, _snapshot, closed_port = _applied_snapshot_and_port()
    ledger = _ledger()
    port = _fresh_port_like(closed_port, replace(configuration, ledger=ledger))
    decision = port.admit(_request(port))
    assert decision.admitted
    parent = ledger.store.load_records()["parent-due-operation"]
    from raes_contracts.runtime_state import OperationState

    state = ledger.store.load_snapshot_state()
    ledger.store.commit_terminal_operation(
        state.snapshot,
        replace(
            parent, status=replace(parent.status, state=OperationState.CANCELLED, updated_at="2026-10-30T00:00:01Z")
        ),
        mode=TerminalCommitMode.OPERATION_ONLY,
        expected_revision=state.revision,
    )

    assert port.dispatch(decision.action_instance_id).refusal is ParticipantToolActionRefusal.EFFECT_ADMISSION_CLOSED

    stopped_ledger = _ledger()
    stopped_port = _fresh_port_like(closed_port, replace(configuration, ledger=stopped_ledger))
    stopped_ledger.store.stop_effect_admission(
        AuditEvent(
            timestamp="2026-10-30T00:00:02Z",
            action="effect_admission_stopped",
            identity="actor:test",
            allowed=True,
            target="target:test",
        )
    )

    assert stopped_port.admit(_request(stopped_port)).refusal is (ParticipantToolActionRefusal.EFFECT_ADMISSION_CLOSED)


def test_sqlite_failure_during_closure_keeps_completed_sibling_history() -> None:
    import sqlite3

    from raes_runtime.participant_invocation_tool_settlement import settle_invocation_tool_sessions

    configuration, snapshot, closed_port = _applied_snapshot_and_port()
    store = _FailingStore(set(), sqlite3.OperationalError)
    port = _fresh_port_like(closed_port, replace(configuration, ledger=_ledger(store)))
    _call_tool(port, "call-done")
    port.admit(_request(port, tool_call_id="call-open"))
    store.failing = {"commit_terminal_operation"}
    run = _session_run(port, snapshot)

    settle_invocation_tool_sessions(run)

    assert port.ledger_failures == 1
    events = _events(run.working, FIRST)
    assert [event.invocation_tool_context.tool_call_id for event in events[0:6:3]] == ["call-done", "call-open"]
    assert [event.action_result.status for event in events[2:6:3]] == ["succeeded", "withheld"]
    assert "runtime.participant-invocation-tool-ledger-failed" in [d.code for d in run.diagnostics]


# Review cycle 4 regressions.


def test_conflicting_hosted_actions_are_not_granted_together() -> None:
    observed: dict[str, object] = {}

    def harness(port, _outer) -> None:
        first = port.admit(_request(port, tool_call_id="call-a"))
        second = port.admit(_request(port, tool_call_id="call-b"))
        assert port.dispatch(first.action_instance_id).accepted
        observed["overlap"] = port.dispatch(second.action_instance_id)
        assert port.complete(first.action_instance_id, _outcome(port, first.action_instance_id)).accepted
        observed["after_settlement"] = port.dispatch(second.action_instance_id)
        assert port.complete(second.action_instance_id, _outcome(port, second.action_instance_id)).accepted

    runtime = _ToolRuntime(harness)
    manager, scenario = _manager(runtime, conflicting=True, max_concurrent=2)

    applied = manager.apply(manager.plan(scenario))

    assert applied.success, applied.diagnostics
    assert observed["overlap"].refusal is ParticipantToolActionRefusal.SEMANTIC_CONFLICT
    assert observed["after_settlement"].accepted


def test_unknown_effects_fence_grants_even_when_the_settlement_write_fails() -> None:
    configuration, _snapshot, closed_port = _applied_snapshot_and_port()
    store = _FailingStore(set())
    shared = replace(configuration, ledger=_ledger(store))
    port = _fresh_port_like(closed_port, shared)
    first = port.admit(_request(port, tool_call_id="call-a"))
    second = port.admit(_request(port, tool_call_id="call-b"))
    assert port.dispatch(first.action_instance_id).accepted
    store.failing = {"commit_terminal_operation"}

    unknown = port.report_unknown(first.action_instance_id, "timeout")

    assert unknown.refusal is ParticipantToolActionRefusal.LEDGER_UNAVAILABLE
    assert port.dispatch(second.action_instance_id).refusal is ParticipantToolActionRefusal.UNRESOLVED_EFFECTS
    sibling = _fresh_port_like(closed_port, shared)
    assert sibling.admit(_request(sibling, tool_call_id="call-c")).refusal is (
        ParticipantToolActionRefusal.UNRESOLVED_EFFECTS
    )


def test_engine_stop_refuses_hosted_tool_claims_and_grants() -> None:
    from raes_runtime.control_plane import RuntimeControlPlane
    from raes_runtime.control_plane_store import NewClaimRejected

    configuration, _snapshot, closed_port = _applied_snapshot_and_port()

    def stopped() -> None:
        raise NewClaimRejected("runtime engine effect admission is closed")

    port = _fresh_port_like(closed_port, replace(configuration, ledger=replace(_ledger(), engine_admission=stopped)))
    assert port.admit(_request(port)).refusal is ParticipantToolActionRefusal.EFFECT_ADMISSION_CLOSED

    with RuntimeControlPlane(create_stub_target()) as engine:
        existing = engine.open_run(run_scope="run:existing")
        existing._tool_engine_admission()
        engine.stop_admission()
        with pytest.raises(NewClaimRejected):
            existing._tool_engine_admission()
