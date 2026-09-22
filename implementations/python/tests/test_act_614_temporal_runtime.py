"""ACT-614 temporal runtime."""

from __future__ import annotations

from dataclasses import replace

import pytest
from implementations.python.tests._act_614_temporal_fixtures import (
    _activity_temporal_payload,
    _bound_deadline_payload,
    _bound_dwell_payload,
    _DwellEvidenceRuntime,
    _temporal_target,
    _TemporalEvidenceRuntime,
)
from implementations.python.tests.test_dsl_437_benign_participant_execution import (
    _activity_policy_yaml,
    _NativeParticipantRuntime,
)
from implementations.python.tests.test_issue_899_participant_resource_budgets import _budget_policy_yaml
from raes_processor.compiler import compile_runtime_model
from raes_runtime.manager import RuntimeManager


def test_deadline_five_prevents_native_dispatch_at_tick_ten() -> None:
    payload = _bound_deadline_payload()
    payload["temporal_constraints"]["green-cadence"]["start"] = {"tick": 10}
    scenario, target = _temporal_target(payload)
    manager = RuntimeManager(target)
    try:
        applied = manager.apply(manager.plan(scenario))
        assert applied.success, applied.diagnostics
        result = manager.advance_time("time.clock.scenario-clock", ticks=10)
        assert target.participant_runtime.native_actions == []
        assert not result.success
        assert any(d.code == "runtime.participant-temporal-guarantee-unsatisfied" for d in result.diagnostics)
        history = next(iter(result.snapshot.participant_behavior_history.values()))
        observation = history[-1]
        assert observation["action_result"]["status"] == "rejected"
        assert observation["temporal_assessments"][0]["status"] == "missed"
        assert observation["temporal_assessments"][0]["native_execution"] == "not_dispatched"
    finally:
        manager._stop_participant_clock_driver()


def test_missing_deadline_evidence_does_not_turn_native_success_into_temporal_success() -> None:
    scenario, target = _temporal_target(_bound_deadline_payload())
    manager = RuntimeManager(target)
    result = manager.apply(manager.plan(scenario))
    assert not result.success
    assert len(target.participant_runtime.native_actions) == 1
    history = next(iter(result.snapshot.participant_behavior_history.values()))
    assert history[-1]["action_result"]["status"] == "succeeded"
    assert history[-1]["temporal_assessments"][0]["status"] == "indeterminate"
    assert history[-1]["temporal_assessments"][0]["native_execution"] == "reported"


@pytest.mark.parametrize("event", ["start", "end", "observed", "effective"])
def test_exact_bound_event_evidence_satisfies_deadline(event: str) -> None:
    scenario, target = _temporal_target(_bound_deadline_payload(event), _TemporalEvidenceRuntime())
    manager = RuntimeManager(target)
    result = manager.apply(manager.plan(scenario))
    assert result.success, result.diagnostics
    history = next(iter(result.snapshot.participant_behavior_history.values()))
    assert history[-1]["action_result"]["status"] == "succeeded"
    assert history[-1]["temporal_assessments"][0]["status"] == "met"


@pytest.mark.parametrize(
    "mutation", ["future", "event", "boundary", "episode_id", "action_instance_id", "execution_generation", "segment"]
)
def test_deadline_evidence_cannot_escape_its_bound_context(mutation: str) -> None:
    scenario, target = _temporal_target(_bound_deadline_payload(), _TemporalEvidenceRuntime(mutation=mutation))
    manager = RuntimeManager(target)
    result = manager.apply(manager.plan(scenario))
    assert not result.success
    if mutation in {"boundary", "episode_id", "action_instance_id", "execution_generation"}:
        assert not result.snapshot.participant_behavior_history
        assert any(d.code == "runtime.participant-autonomous-action-protocol-invalid" for d in result.diagnostics)
        return
    history = next(iter(result.snapshot.participant_behavior_history.values()))
    assert history[-1]["action_result"]["status"] == "succeeded"
    assert history[-1]["temporal_assessments"][0]["status"] == "indeterminate"


@pytest.mark.parametrize("late", [False, True])
def test_concurrent_dispatch_obeys_the_same_temporal_gate(late: bool) -> None:
    payload = _bound_deadline_payload()
    payload["entities"]["second"] = dict(payload["entities"]["enterprise-participant"])
    payload["agents"]["second"] = {**payload["agents"]["participant-agent"], "affiliations": ["second"]}
    spec = payload["behavior_specifications"]["participant-behavior"]
    spec["participant_refs"].append("second")
    spec["autonomous_execution"]["max_in_flight"] = 2
    if late:
        payload["temporal_constraints"]["green-cadence"]["start"] = {"tick": 10}
    scenario, target = _temporal_target(payload, _TemporalEvidenceRuntime())
    manager = RuntimeManager(target)
    result = manager.apply(manager.plan(scenario))
    if late:
        assert result.success
        result = manager.advance_time("time.clock.scenario-clock", ticks=10)
        assert not result.success
        assert target.participant_runtime.native_actions == []
    else:
        assert result.success, result.diagnostics
        assert len(target.participant_runtime.native_actions) == 2
        assert len(result.snapshot.participant_behavior_history) == 2
        assert all(
            history[-1]["temporal_assessments"][0]["status"] == "met"
            for history in result.snapshot.participant_behavior_history.values()
        )


@pytest.mark.parametrize("mutation", [None, "missing", "gap", "false", "endpoints", "wrong_condition"])
def test_dwell_requires_condition_coverage_before_native_dispatch(mutation: str | None) -> None:
    scenario, target = _temporal_target(_bound_dwell_payload(), _DwellEvidenceRuntime(mutation=mutation))
    manager = RuntimeManager(target)
    assert manager.apply(manager.plan(scenario)).success
    result = manager.advance_time("time.clock.scenario-clock", ticks=10)
    assert result.success is (mutation is None), result.diagnostics
    assert len(target.participant_runtime.native_actions) == (1 if mutation is None else 0)
    history = next(iter(result.snapshot.participant_behavior_history.values()))
    assessment = history[-1]["temporal_assessments"][0]
    assert (assessment["status"] == "met") is (mutation is None)
    assert assessment["context"]["binding"]["condition_precondition_id"] == "portal-present"


def test_pause_does_not_certify_a_dwell_condition_during_frozen_time() -> None:
    scenario, target = _temporal_target(_bound_dwell_payload(), _DwellEvidenceRuntime())
    manager = RuntimeManager(target)
    assert manager.apply(manager.plan(scenario)).success
    assert manager.pause_time("time.clock.scenario-clock").success
    assert manager.resume_time("time.clock.scenario-clock").success
    result = manager.advance_time("time.clock.scenario-clock", ticks=10)
    assert not result.success
    assert target.participant_runtime.native_actions == []


@pytest.mark.parametrize("replay", [False, True])
@pytest.mark.parametrize("reuse", [False, True])
def test_reset_and_replay_require_fresh_action_evidence(replay: bool, reuse: bool) -> None:
    scenario, target = _temporal_target(
        _bound_deadline_payload(), _TemporalEvidenceRuntime(mutation="reused" if reuse else None)
    )
    manager = RuntimeManager(target)
    first = manager.apply(manager.plan(scenario))
    assert first.success
    assert manager.reset_time("time.clock.scenario-clock", replay=replay).success
    result = manager.run_due_participant_actions()
    assert result.success is (not reuse)
    history = next(iter(result.snapshot.participant_behavior_history.values()))
    observations = [event for event in history if event["event_type"] == "observation_emitted"]
    if reuse:
        assert len(observations) == 1
        assert observations[0] == next(iter(first.snapshot.participant_behavior_history.values()))[-1]
    else:
        old, new = observations[-2:]
        assert old["action_instance_id"] != new["action_instance_id"]
        scope = new["temporal_assessments"][0]["context"]
        assert scope["submitted_at"]["segment"] == scope["bound_end"]["segment"] == 1
        assert scope["execution_generation"] == 1
        assert scope["episode_id"] != old["episode_id"]
    from raes_runtime.control_plane_store_snapshots import _snapshot_from_payload, _snapshot_payload

    assert (
        _snapshot_from_payload(_snapshot_payload(result.snapshot)).participant_behavior_history
        == result.snapshot.participant_behavior_history
    )


@pytest.mark.parametrize("source", [_activity_policy_yaml, _budget_policy_yaml])
def test_activity_deadline_rejection_does_not_consume_native_resources(source) -> None:
    from implementations.python.tests.test_dsl_437_benign_participant_execution import _activity_control

    scenario, target = _temporal_target(_activity_temporal_payload(source))
    manager = RuntimeManager(target, stochastic_controls=[_activity_control()])
    initial = manager.apply(manager.plan(scenario))
    assert initial.success, initial.diagnostics
    state = next(iter(initial.snapshot.participant_autonomous_execution_states.values()))
    for _tick in range(10, state["next_tick"] + 1, 10):
        result = manager.advance_time("time.clock.scenario-clock", ticks=10)
    assert not result.success
    assert target.participant_runtime.native_actions == []
    assert result.snapshot.participant_resource_budget_events == initial.snapshot.participant_resource_budget_events
    assert not any("measurement" in diagnostic.code for diagnostic in result.diagnostics)


def test_temporal_indeterminacy_never_triggers_native_retry() -> None:
    from implementations.python.tests.test_dsl_437_benign_participant_execution import _activity_control
    from raes.participant_behavior import ParticipantFailureClass

    class FailedWithoutTiming(_NativeParticipantRuntime):
        def _model_action(self, request, snapshot, *, episode_id):
            native = super()._model_action(request, snapshot, episode_id=episode_id)
            return replace(
                native,
                action_result=native.action_result.model_copy(
                    update={"status": "failed", "failure_class": ParticipantFailureClass.TIMEOUT}
                ),
            )

    payload = _activity_temporal_payload(_activity_policy_yaml)
    payload["temporal_constraints"]["finish-by-five"]["end"]["tick"] = 200
    scenario, target = _temporal_target(payload, FailedWithoutTiming())
    manager = RuntimeManager(target, stochastic_controls=[_activity_control()])
    initial = manager.apply(manager.plan(scenario))
    assert initial.success
    state = next(iter(initial.snapshot.participant_autonomous_execution_states.values()))
    for _tick in range(10, state["next_tick"] + 1, 10):
        result = manager.advance_time("time.clock.scenario-clock", ticks=10)
    assert not result.success
    assert len(target.participant_runtime.native_actions) == 1


@pytest.mark.parametrize("event", ["start", "end", "observed", "effective"])
def test_temporal_assessment_uses_selected_event_not_submission_time(event: str) -> None:
    from raes_contracts.contracts.participant_temporal import ParticipantTemporalEvidenceModel
    from raes_contracts.participant_temporal import assess_temporal_guarantee
    from raes_runtime.time_coordinator import TimeCoordinator

    scenario, target = _temporal_target(_bound_deadline_payload(event), _TemporalEvidenceRuntime())
    manager = RuntimeManager(target)
    initial = manager.apply(manager.plan(scenario))
    observed = next(iter(initial.snapshot.participant_behavior_history.values()))[-1]
    proof = ParticipantTemporalEvidenceModel.model_validate(observed["action_result"]["temporal_evidence"][0])
    coordinator = TimeCoordinator(compile_runtime_model(scenario).time_model)
    advanced = coordinator.advance(initial.snapshot, "time.clock.scenario-clock", ticks=10)
    clock = advanced.time_model_state.clocks["time.clock.scenario-clock"]
    late = proof.model_copy(update={"coordinate": clock.coordinate})
    assessment = assess_temporal_guarantee(
        proof.context, (late,), observed["observation_boundary_address"], clock, native_execution="reported"
    )
    assert proof.context.submitted_at.tick == 0
    assert assessment.status == "missed"
    assert assessment.native_execution == "reported"


def test_deadline_is_inclusive_at_the_exact_superdense_coordinate() -> None:
    from raes_contracts.contracts.participant_temporal import ParticipantTemporalEvidenceModel
    from raes_contracts.contracts.time_model import TimeCoordinateModel
    from raes_contracts.participant_temporal import assess_temporal_guarantee
    from raes_runtime.time_coordinator import TimeCoordinator

    scenario, target = _temporal_target(_bound_deadline_payload(), _TemporalEvidenceRuntime())
    manager = RuntimeManager(target)
    initial = manager.apply(manager.plan(scenario))
    observed = next(iter(initial.snapshot.participant_behavior_history.values()))[-1]
    proof = ParticipantTemporalEvidenceModel.model_validate(observed["action_result"]["temporal_evidence"][0])
    advanced = TimeCoordinator(compile_runtime_model(scenario).time_model).advance(
        initial.snapshot, "time.clock.scenario-clock", ticks=10
    )
    clock = advanced.time_model_state.clocks["time.clock.scenario-clock"]
    for microstep, expected in ((0, "met"), (1, "missed")):
        candidate = proof.model_copy(update={"coordinate": TimeCoordinateModel(tick=5, microstep=microstep)})
        result = assess_temporal_guarantee(
            proof.context, (candidate,), observed["observation_boundary_address"], clock, native_execution="reported"
        )
        assert result.status == expected


def test_activity_commit_fences_completion_against_the_authoritative_generation() -> None:
    from implementations.python.tests.test_dsl_437_benign_participant_execution import _activity_control
    from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
    from raes_runtime.participant_activity import resolve_participant_activity_controls
    from raes_runtime.participant_scheduler_operations import _run_one_activity_action, participant_due_context
    from raes_runtime.participant_scheduler_types import SchedulerRunState
    from raes_runtime.time_coordinator import TimeCoordinator

    class ResetDuringCommit(_TemporalEvidenceRuntime):
        def admit_action(self, request, snapshot):
            result = super().admit_action(request, snapshot)
            services = dict(run.working.participant_execution_services)
            services[request.execution_scope_ref] = {
                **services[request.execution_scope_ref],
                "generation": 1,
                "observed_generation": 1,
            }
            run.working = run.working.with_entries(dict(run.working.entries), participant_execution_services=services)
            return result

    payload = _activity_temporal_payload(_activity_policy_yaml)
    payload["temporal_constraints"]["finish-by-five"]["end"]["tick"] = 200
    scenario, target = _temporal_target(payload, ResetDuringCommit())
    manager = RuntimeManager(target, stochastic_controls=[_activity_control()])
    initialized = manager.apply(manager.plan(scenario))
    assert initialized.success
    model = compile_runtime_model(scenario)
    policy = next(iter(model.behavior_specifications.values())).autonomous_execution
    state = ParticipantAutonomousExecutionStateModel.model_validate(
        next(iter(initialized.snapshot.participant_autonomous_execution_states.values()))
    )
    snapshot = initialized.snapshot
    coordinator = TimeCoordinator(model.time_model)
    for _tick in range(10, state.next_tick + 1, 10):
        snapshot = coordinator.advance(snapshot, policy.clock_address, ticks=10)
    run = SchedulerRunState(working=snapshot, diagnostics=[], changed=[])
    context = participant_due_context(
        policy,
        model.time_model,
        target.participant_runtime,
        state.participant_address,
        state.next_tick,
        0,
        resolve_participant_activity_controls([_activity_control()]),
    )
    _run_one_activity_action(context, state, run)
    assert any(d.code == "runtime.participant-execution-stale-completion" for d in run.diagnostics)
    assert run.working.participant_execution_services[policy.address]["generation"] == 1
    assert run.working.participant_behavior_history == snapshot.participant_behavior_history


def test_native_action_cannot_change_the_shared_clock_to_certify_its_own_deadline() -> None:
    from raes_runtime.time_coordinator import TimeCoordinator

    class SelfCertifyingClock(_TemporalEvidenceRuntime):
        def admit_action(self, request, snapshot):
            result = super().admit_action(request, snapshot)
            advanced = TimeCoordinator(model.time_model).advance(result.snapshot, "time.clock.scenario-clock", ticks=10)
            return replace(result, snapshot=advanced)

    scenario, target = _temporal_target(_bound_deadline_payload(), SelfCertifyingClock())
    model = compile_runtime_model(scenario)
    manager = RuntimeManager(target)
    result = manager.apply(manager.plan(scenario))
    assert not result.success
    assert any(d.code == "runtime.participant-autonomous-action-protocol-invalid" for d in result.diagnostics)
    assert result.snapshot.time_model_state.clocks["time.clock.scenario-clock"].coordinate.tick == 0
