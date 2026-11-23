"""Issue #2020: release autonomous participants only when their starting assertions are true."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from raes.parser import parse_sdl
from raes_backend_stubs.stubs import StubEvaluator, create_stub_target
from raes_contracts.contracts.participant_execution import (
    ParticipantExecutionControlRequestModel,
    ParticipantExecutionServiceStateModel,
)
from raes_contracts.errors import ConflictError
from raes_contracts.planning import PlanScope, RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_processor.compiler import compile_runtime_model
from raes_runtime import RuntimeControlPlane, RuntimeTarget
from raes_runtime.control_plane_store import IndeterminateClaimBlocked
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.manager import RuntimeManager
from raes_runtime.participant_release import (
    ReleaseDisposition,
    participant_disposition,
    participant_release_assertions,
    release_disposition,
    setup_release_assertions,
)
from raes_runtime.participant_scheduler import ParticipantScheduler
from test_dsl_437_benign_participant_execution import (
    SCENARIO_CLOCK_ADDRESS,
    _autonomous_manifest,
    _await_driver_outcome,
    _NativeParticipantRuntime,
    _scenario_yaml,
)

PARTICIPANT = "participant.behavior.participant-agent"
READY_ASSERTION = "evaluation.assertion.range-ready"
READY_PROPOSITION = "evaluation.proposition.range-ready"
WAITING = "runtime.participant-release-waiting"
UNSUPPORTED = "runtime.participant-release-unsupported"


def _gated_scenario_yaml(*, polarity: str = "positive") -> str:
    payload = yaml.safe_load(_scenario_yaml())
    payload["propositions"]["range-ready"] = {
        "description": "The backend finished native preparation of the range.",
        "subjects": ["nodes.redteam-net"],
        "basis": "observed_state",
        "predicate": {
            "kind": "boolean",
            "property": "range-ready",
            "semantic_ref": "urn:raes:observable:range-ready",
            "operator": "equals",
            "expected": True,
        },
        "quantifier": "all",
        "evidence_requirements": ["objective-truth-evidence"],
    }
    payload["assertions"]["range-ready"] = {
        "proposition": "range-ready",
        "role": "precondition",
        "polarity": polarity,
    }
    payload["agents"]["participant-agent"]["starting_assertions"] = ["range-ready"]
    return yaml.safe_dump(payload, sort_keys=False)


def _truth_result(outcome: str, *, polarity: str = "positive") -> dict[str, object]:
    inverted = {"true": "false", "false": "true"}
    assertion_outcome = inverted.get(outcome, outcome) if polarity == "negative" else outcome
    decided = outcome in {"true", "false"}
    return {
        "schema_version": "proposition-truth-result/v1",
        "result_id": f"truth-range-ready-{outcome}",
        "proposition_address": READY_PROPOSITION,
        "assertion_address": READY_ASSERTION,
        "assertion_polarity": polarity,
        "proposition_outcome": outcome,
        "assertion_outcome": assertion_outcome,
        "evaluation_basis": "observed_state",
        "indeterminacy_reason": "missing_evidence" if outcome == "unknown" else None,
        "probe_binding": {
            "binding_id": "range-ready-binding",
            "implementation_id": "example/range-ready-probe",
            "implementation_version": "1.0.0",
            "artifact_digest": "sha256:" + "a" * 64,
            "backend_manifest_ref": "backend-manifest:stub",
            "proposition_address": READY_PROPOSITION,
            "capability_refs": ["predicate.boolean.equals", "evidence.log"],
        }
        if decided
        else None,
        "evidence_refs": ["experiment-evidence:range-ready"] if decided else [],
        "declared_artifact_digest": None,
        "temporal_context": {
            "boundary_ref": "agents.participant-agent:start",
            "time_domain": "scenario_time",
            "clock_authority": "runtime.time-coordinator",
        }
        if decided
        else None,
        "loss_disclosures": [],
        "unsupported_capability_refs": ["predicate.boolean.equals"] if outcome == "unsupported" else [],
    }


class _ReadinessEvaluator(StubEvaluator):
    """Evaluator double that reports the range-ready truth result after native preparation."""

    def __init__(self) -> None:
        super().__init__()
        self.report: dict[str, object] | None = None

    def start(self, plan, snapshot: RuntimeSnapshot) -> ApplyResult:
        started = super().start(plan, snapshot)
        if self.report is None:
            return started
        results = dict(started.snapshot.proposition_truth_results)
        results[READY_ASSERTION] = self.report
        return replace(
            started,
            snapshot=started.snapshot.with_entries(dict(started.snapshot.entries), proposition_truth_results=results),
        )


class _CountingParticipantRuntime(_NativeParticipantRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.initialized: list[str] = []

    def initialize(self, request, snapshot):
        self.initialized.append(request.participant_address)
        return super().initialize(request, snapshot)


def _target(scenario: object) -> tuple[RuntimeTarget, _CountingParticipantRuntime, _ReadinessEvaluator]:
    participants = _CountingParticipantRuntime()
    evaluator = _ReadinessEvaluator()
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(compile_runtime_model(scenario)),
        participant_runtime=participants,
        evaluator=evaluator,
    )
    return target, participants, evaluator


def _manager(scenario_yaml: str) -> tuple[RuntimeManager, object, _CountingParticipantRuntime, _ReadinessEvaluator]:
    scenario = parse_sdl(scenario_yaml)
    target, participants, evaluator = _target(scenario)
    return RuntimeManager(target), scenario, participants, evaluator


def _codes(result: ApplyResult) -> list[str]:
    return [diagnostic.code for diagnostic in result.diagnostics]


def test_participant_waits_until_backend_reports_range_ready() -> None:
    manager, scenario, participants, evaluator = _manager(_gated_scenario_yaml())

    applied = manager.apply(manager.plan(scenario))

    assert applied.success, applied.diagnostics
    assert participants.initialized == []
    assert participants.native_actions == []
    assert WAITING in _codes(applied)
    assert applied.snapshot.participant_autonomous_execution_states == {}

    evaluator.report = _truth_result("true")
    receipt = manager.evaluate(idempotency_key="range-ready")

    assert receipt.accepted, receipt.diagnostics
    assert manager.snapshot.proposition_truth_results[READY_ASSERTION]["assertion_outcome"] == "true"
    assert participants.initialized == [PARTICIPANT]
    assert len(participants.native_actions) == 1
    assert manager.read_time_state().clocks[SCENARIO_CLOCK_ADDRESS].coordinate.tick == 0


def _apply_waiting(scenario_yaml: str) -> tuple[RuntimeManager, _CountingParticipantRuntime, _ReadinessEvaluator]:
    manager, scenario, participants, evaluator = _manager(scenario_yaml)
    applied = manager.apply(manager.plan(scenario))
    assert applied.success, applied.diagnostics
    assert participants.initialized == []
    return manager, participants, evaluator


def _report(manager: RuntimeManager, evaluator: _ReadinessEvaluator, result: dict[str, object], key: str) -> None:
    evaluator.report = result
    assert manager.evaluate(idempotency_key=key).accepted
    assert manager.snapshot.proposition_truth_results[READY_ASSERTION] == result


def _policy_address(manager: RuntimeManager) -> str:
    return next(iter(manager.snapshot.participant_execution_services))


@pytest.mark.parametrize("outcome", ["false", "unknown"])
def test_undecided_or_false_readiness_keeps_participant_waiting(outcome: str) -> None:
    manager, participants, evaluator = _apply_waiting(_gated_scenario_yaml())
    _report(manager, evaluator, _truth_result(outcome), f"range-{outcome}")

    due = manager.run_due_participant_actions()

    assert due.success, due.diagnostics
    assert WAITING in _codes(due)
    assert participants.initialized == []
    assert participants.native_actions == []


def test_unsupported_readiness_refuses_execution_instead_of_waiting_forever() -> None:
    manager, participants, evaluator = _apply_waiting(_gated_scenario_yaml())
    evaluator.report = _truth_result("unsupported")
    receipt = manager.evaluate(idempotency_key="range-unsupported")

    assert receipt.accepted
    unsupported = next(diagnostic for diagnostic in receipt.diagnostics if diagnostic.code == UNSUPPORTED)
    assert unsupported.address.endswith(f"{_policy_address(manager)}.state.{PARTICIPANT}")
    assert participants.initialized == []
    # Like other scheduler refusals, the refused pass needs explicit resolution before more effects.
    with pytest.raises(IndeterminateClaimBlocked):
        manager.run_due_participant_actions()
    assert participants.initialized == []


@pytest.mark.parametrize(("outcome", "released"), [("false", True), ("true", False)])
def test_negative_starting_assertion_releases_only_on_true_assertion_outcome(outcome: str, released: bool) -> None:
    manager, participants, evaluator = _apply_waiting(_gated_scenario_yaml(polarity="negative"))
    _report(manager, evaluator, _truth_result(outcome, polarity="negative"), f"negative-{outcome}")

    assert manager.run_due_participant_actions().success
    assert participants.initialized == ([PARTICIPANT] if released else [])


def test_agent_without_starting_assertions_starts_in_the_apply_handoff() -> None:
    manager, scenario, participants, _ = _manager(_scenario_yaml())

    applied = manager.apply(manager.plan(scenario))

    assert applied.success, applied.diagnostics
    assert WAITING not in _codes(applied)
    assert participants.initialized == [PARTICIPANT]
    assert len(participants.native_actions) == 1


def test_delayed_release_starts_at_the_next_authored_cadence_tick() -> None:
    manager, participants, evaluator = _apply_waiting(_gated_scenario_yaml())
    advanced = manager.advance_time(SCENARIO_CLOCK_ADDRESS, ticks=10)
    assert advanced.success, advanced.diagnostics
    assert participants.initialized == []

    _report(manager, evaluator, _truth_result("true"), "range-ready-late")

    assert participants.initialized == [PARTICIPANT]
    assert len(participants.native_actions) == 1
    state = next(iter(manager.snapshot.participant_autonomous_execution_states.values()))
    assert (state["attempted_actions"], state["next_tick"]) == (1, 20)
    assert manager.advance_time(SCENARIO_CLOCK_ADDRESS, ticks=10).success
    assert len(participants.native_actions) == 2


def test_replayed_report_and_scheduler_passes_start_the_episode_once() -> None:
    manager, participants, evaluator = _apply_waiting(_gated_scenario_yaml())
    _report(manager, evaluator, _truth_result("true"), "range-ready")
    assert manager.run_due_participant_actions().success

    assert manager.evaluate(idempotency_key="range-ready").accepted
    assert manager.run_due_participant_actions().success

    assert participants.initialized == [PARTICIPANT]


def test_clock_reset_does_not_start_or_reset_a_waiting_participant() -> None:
    manager, participants, _ = _apply_waiting(_gated_scenario_yaml())

    reset = manager.reset_time(SCENARIO_CLOCK_ADDRESS)

    assert reset.success, reset.diagnostics
    assert participants.initialized == []
    assert participants.native_actions == []
    assert manager.snapshot.participant_autonomous_execution_states == {}


def _semantic_snapshot(result: dict[str, object], *, polarity: str = "positive") -> RuntimeSnapshot:
    return RuntimeSnapshot(
        entries={
            READY_PROPOSITION: SnapshotEntry(
                address=READY_PROPOSITION,
                domain=RuntimeDomain.EVALUATION,
                resource_type="proposition",
                payload={"name": "range-ready", "evaluation_basis": "observed_state"},
            ),
            READY_ASSERTION: SnapshotEntry(
                address=READY_ASSERTION,
                domain=RuntimeDomain.EVALUATION,
                resource_type="assertion",
                payload={"proposition_address": READY_PROPOSITION, "polarity": polarity},
            ),
        },
        proposition_truth_results={READY_ASSERTION: result},
    )


def test_release_requires_an_admitted_true_result_for_every_assertion() -> None:
    snapshot = _semantic_snapshot(_truth_result("true"))

    assert release_disposition(snapshot, ()) is ReleaseDisposition.RELEASED
    assert release_disposition(snapshot, (READY_ASSERTION,)) is ReleaseDisposition.RELEASED
    assert release_disposition(snapshot, (READY_ASSERTION, "evaluation.assertion.other")) is (
        ReleaseDisposition.WAITING
    )


def test_release_refuses_true_results_that_do_not_match_admitted_entries() -> None:
    changed_meaning = _semantic_snapshot(_truth_result("true"), polarity="negative")
    without_evidence = _semantic_snapshot({**_truth_result("true"), "evidence_refs": []})
    unadmitted = RuntimeSnapshot(proposition_truth_results={READY_ASSERTION: _truth_result("true")})

    for snapshot in (changed_meaning, without_evidence, unadmitted):
        assert release_disposition(snapshot, (READY_ASSERTION,)) is ReleaseDisposition.WAITING


def test_participants_release_independently_by_their_own_assertions() -> None:
    snapshot = _semantic_snapshot(_truth_result("true"))
    release_assertions = {
        "participant.behavior.a": (READY_ASSERTION,),
        "participant.behavior.b": ("evaluation.assertion.x",),
    }

    assert participant_disposition(release_assertions, snapshot, "participant.behavior.a") is (
        ReleaseDisposition.RELEASED
    )
    assert participant_disposition(release_assertions, snapshot, "participant.behavior.b") is (
        ReleaseDisposition.WAITING
    )
    assert participant_disposition(release_assertions, snapshot, "participant.behavior.unknown") is (
        ReleaseDisposition.WAITING
    )


def test_durable_run_stays_pending_across_restart_until_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = parse_sdl(_gated_scenario_yaml())
    target, participants, evaluator = _target(scenario)
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path), run_scope="run:gate") as runtime:
        plan = runtime.plan(scenario, run_scope=PlanScope(run_id="gate"))
        for _ in range(3):
            assert runtime.advance_plan(plan, execution_id="gate").state == "progress"
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path), run_scope="run:gate") as runtime:
        for _ in range(10):
            progress = runtime.advance_plan(plan, execution_id="gate")
            if progress.state != "progress":
                break
        assert progress.state == "pending"
        assert participants.initialized == []
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path), run_scope="run:gate") as runtime:
        assert runtime.advance_plan(plan, execution_id="gate").state == "pending"
        # Isolate durable continuation from the release pass that a report also runs.
        monkeypatch.setattr(runtime, "_release_reported_participants", lambda receipt: receipt)
        _report(runtime, evaluator, _truth_result("true"), "range-ready-durable")
        assert participants.initialized == []

        assert runtime.advance_plan(plan, execution_id="gate").state == "succeeded"
        assert participants.initialized == [PARTICIPANT]
        assert runtime.advance_plan(plan, execution_id="gate").state == "succeeded"
        assert participants.initialized == [PARTICIPANT]


def test_paused_clock_holds_release_until_resume() -> None:
    manager, participants, evaluator = _apply_waiting(_gated_scenario_yaml())
    paused = manager.pause_time(SCENARIO_CLOCK_ADDRESS)
    assert paused.success, paused.diagnostics
    service = next(iter(manager.snapshot.participant_execution_services.values()))
    assert (service["observed_lifecycle"], service["accepting_new_work"]) == ("paused", False)

    _report(manager, evaluator, _truth_result("true"), "range-ready-paused")
    assert manager.run_due_participant_actions().success

    assert participants.initialized == []
    assert participants.native_actions == []
    resumed = manager.resume_time(SCENARIO_CLOCK_ADDRESS)
    assert resumed.success, resumed.diagnostics
    assert participants.initialized == [PARTICIPANT]


def test_direct_episode_initialization_of_a_waiting_participant_is_refused() -> None:
    manager, participants, _ = _apply_waiting(_gated_scenario_yaml())

    receipt = manager.initialize_participant_episode(PARTICIPANT)

    assert not receipt.accepted
    assert participants.initialized == []


def test_report_before_the_durable_start_phase_waits_for_that_phase(tmp_path: Path) -> None:
    scenario = parse_sdl(_gated_scenario_yaml())
    target, participants, evaluator = _target(scenario)
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path), run_scope="run:early") as runtime:
        plan = runtime.plan(scenario, run_scope=PlanScope(run_id="early"))
        # Provisioning, time, participant execution, and evaluation phases.
        for _ in range(4):
            assert runtime.advance_plan(plan, execution_id="early").state == "progress"

        _report(runtime, evaluator, _truth_result("true"), "range-ready-early")
        assert runtime.advance_plan(plan, execution_id="early").state == "progress"

        assert (participants.initialized, participants.native_actions) == ([], [])
        assert runtime.advance_plan(plan, execution_id="early").state == "progress"
        assert participants.initialized == [PARTICIPANT]
        assert len(participants.native_actions) == 1


def test_wall_clock_driver_releases_after_a_deferred_truth_result(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = yaml.safe_load(_gated_scenario_yaml())
    payload["time_domains"]["scenario"]["tick_period_seconds"] = {"numerator": 1, "denominator": 100}
    progression = payload["time_progression_policies"]["scenario-progression"]
    progression["advancement_mode"] = "real_time"
    progression.pop("step_ticks")
    payload["temporal_constraints"]["green-cadence"]["cadence_ticks"] = 1
    manager, participants, evaluator = _apply_waiting(yaml.safe_dump(payload, sort_keys=False))
    # A deferred evaluation commits without the submission-return release pass.
    monkeypatch.setattr(manager, "_release_reported_participants", lambda receipt: receipt)

    _report(manager, evaluator, _truth_result("true"), "range-ready-deferred")
    _await_driver_outcome(lambda: participants.initialized == [PARTICIPANT])

    assert participants.initialized == [PARTICIPANT]
    manager.destroy()


@pytest.mark.parametrize(("actions", "lifecycle"), [(("drain",), "quiescent"), (("drain", "teardown"), "terminated")])
def test_clock_controls_keep_independent_drain_and_teardown_of_waiting_service(
    actions: tuple[str, ...], lifecycle: str
) -> None:
    manager, participants, evaluator = _apply_waiting(_gated_scenario_yaml())
    for action in actions:
        service = ParticipantExecutionServiceStateModel.model_validate(
            next(iter(manager.snapshot.participant_execution_services.values()))
        )
        controlled = manager.control_participant_execution(
            ParticipantExecutionControlRequestModel(
                execution_scope_ref=service.execution_scope_ref,
                action=action,
                expected_generation=service.generation,
                timeout_seconds=30 if action == "drain" else None,
            )
        )
        assert manager.get_operation(controlled.operation_id).state.value == "succeeded"
    assert next(iter(manager.snapshot.participant_execution_services.values()))["observed_lifecycle"] == lifecycle

    assert manager.pause_time(SCENARIO_CLOCK_ADDRESS).success
    assert manager.resume_time(SCENARIO_CLOCK_ADDRESS).success
    _report(manager, evaluator, _truth_result("true"), f"range-ready-{lifecycle}")

    after = next(iter(manager.snapshot.participant_execution_services.values()))
    assert after["observed_lifecycle"] == lifecycle
    assert after["accepting_new_work"] is False
    assert participants.initialized == []


def _control(manager: RuntimeManager, action: str) -> None:
    service = ParticipantExecutionServiceStateModel.model_validate(
        next(iter(manager.snapshot.participant_execution_services.values()))
    )
    controlled = manager.control_participant_execution(
        ParticipantExecutionControlRequestModel(
            execution_scope_ref=service.execution_scope_ref,
            action=action,
            expected_generation=service.generation,
            timeout_seconds=30 if action == "drain" else None,
        )
    )
    assert manager.get_operation(controlled.operation_id).state.value == "succeeded"


def test_report_before_the_evaluation_phase_is_refused(tmp_path: Path) -> None:
    scenario = parse_sdl(_gated_scenario_yaml())
    target, participants, evaluator = _target(scenario)
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path), run_scope="run:setup") as runtime:
        plan = runtime.plan(scenario, run_scope=PlanScope(run_id="setup"))
        # Provisioning and time phases only.
        for _ in range(2):
            assert runtime.advance_plan(plan, execution_id="setup").state == "progress"
        evaluator.report = _truth_result("true")

        with pytest.raises(ConflictError, match="applied evaluation phase"):
            runtime.evaluate(idempotency_key="range-ready-before-setup")

        for _ in range(4):
            assert runtime.advance_plan(plan, execution_id="setup").state == "progress"
        assert runtime.advance_plan(plan, execution_id="setup").state == "succeeded"
        assert participants.initialized == [PARTICIPANT]


def test_setup_starts_only_participants_without_starting_assertions() -> None:
    model = compile_runtime_model(parse_sdl(_gated_scenario_yaml()))

    assert participant_release_assertions(model) == {PARTICIPANT: (READY_ASSERTION,)}
    assert setup_release_assertions(model) == {}
    assert setup_release_assertions(compile_runtime_model(parse_sdl(_scenario_yaml()))) == {PARTICIPANT: ()}


@pytest.mark.parametrize("hold", ["pause", "drain"])
def test_direct_initialization_requires_service_admission_after_a_true_report(hold: str) -> None:
    manager, participants, evaluator = _apply_waiting(_gated_scenario_yaml())
    if hold == "pause":
        assert manager.pause_time(SCENARIO_CLOCK_ADDRESS).success
    else:
        _control(manager, "drain")
    _report(manager, evaluator, _truth_result("true"), f"range-ready-{hold}-direct")

    receipt = manager.initialize_participant_episode(PARTICIPANT)

    assert not receipt.accepted
    assert participants.initialized == []


def test_shared_clock_reset_keeps_a_drained_waiting_service() -> None:
    manager, participants, evaluator = _apply_waiting(_gated_scenario_yaml())
    _control(manager, "drain")

    assert manager.reset_time(SCENARIO_CLOCK_ADDRESS).success
    _report(manager, evaluator, _truth_result("true"), "range-ready-reset-drained")

    service = next(iter(manager.snapshot.participant_execution_services.values()))
    assert (service["observed_lifecycle"], service["accepting_new_work"]) == ("quiescent", False)
    assert participants.initialized == []


def test_clock_lifecycle_keeps_a_drained_service_with_released_participants() -> None:
    manager, scenario, participants, _ = _manager(_scenario_yaml())
    assert manager.apply(manager.plan(scenario)).success
    assert participants.initialized == [PARTICIPANT]
    address, payload = next(iter(manager.snapshot.participant_execution_services.items()))
    drained = ParticipantExecutionServiceStateModel.model_validate(payload).model_copy(
        update={
            "desired_lifecycle": "quiescent",
            "observed_lifecycle": "quiescent",
            "readiness": "not_ready",
            "accepting_new_work": False,
        }
    )
    snapshot = manager.snapshot.with_entries(
        dict(manager.snapshot.entries),
        participant_execution_services={address: drained.model_dump(mode="json")},
    )

    for lifecycle in ("paused", "running"):
        snapshot = ParticipantScheduler.set_clock_lifecycle(
            snapshot, SCENARIO_CLOCK_ADDRESS, lifecycle, policies=manager._participant_execution_policies
        ).snapshot
        service = snapshot.participant_execution_services[address]
        assert (service["observed_lifecycle"], service["accepting_new_work"]) == ("quiescent", False)
