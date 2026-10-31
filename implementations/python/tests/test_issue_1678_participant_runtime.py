"""Issue 1678 regressions for the participant and mixed runtime (ADR-116).

Each test fails without its fix: an isolation or boundary handler logs one
value-free record, a defect is not reported as a domain refusal, and a
diagnostic does not disclose a value from a rejected backend result. A record
of a failure in untrusted foreign code keeps only the RAES frames.
"""

from __future__ import annotations

import logging
import threading
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
import raes_runtime.participant_control_action_admission as action_admission
import raes_runtime.participant_control_effects as control_effects
import raes_runtime.participant_control_replay as control_replay
import raes_runtime.participant_scheduler_operations as scheduler_operations
import yaml
from raes.parser import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts.participant_crossing_prefix import CrossingPrefix
from raes_contracts.errors import ConflictError, EvidenceIntegrityError, InvalidInputError, OperationalError
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.compiler import compile_runtime_model
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import IndeterminateClaimBlocked, NewClaimRejected
from raes_runtime.mixed_runtime_phase import _evaluate
from raes_runtime.participant_action_validation import _history_structure_violation
from raes_runtime.participant_clock_driver import ParticipantClockDriver
from raes_runtime.participant_control_intents import ParticipantProposalControlIntent
from raes_runtime.participant_control_orchestration import _provider_results, _resolve
from raes_runtime.participant_control_targets import _intent_target
from raes_runtime.participant_crossing_records import _next_crossing_snapshot
from raes_runtime.participant_flow_sink import _resolve_flow_sink_relation
from raes_runtime.participant_inject_application import _resolve_delivery
from raes_runtime.participant_scheduler import ParticipantScheduler
from raes_runtime.participant_scheduler_concurrent_dispatch import _execute_concurrent_batch
from raes_runtime.time_coordinator import TimeCoordinator
from test_dsl_437_benign_participant_execution import (
    _await_driver_outcome,
    _NativeParticipantRuntime,
    _scenario_yaml,
)
from test_participant_concurrent_batch_reservations import _batch

_SENTINEL = "value-sentinel-1678-participant"


def _single_error_record(caplog: pytest.LogCaptureFixture, logger: str) -> logging.LogRecord:
    records = [record for record in caplog.records if record.name == logger]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.ERROR
    assert _SENTINEL not in record.getMessage()
    assert record.exc_text is not None
    assert _SENTINEL not in record.exc_text
    return record


def _raise_secret(*_args: object, **_kwargs: object) -> object:
    raise RuntimeError(_SENTINEL)


_ForeignSecretError = type("ForeignOnlyError1678", (RuntimeError,), {})


def _foreign_only_raiser_1678(*_args: object, **_kwargs: object) -> object:
    try:
        raise OSError(_SENTINEL)
    except OSError as cause:
        raise _ForeignSecretError(_SENTINEL) from cause


def _single_foreign_record(caplog: pytest.LogCaptureFixture, logger: str) -> logging.LogRecord:
    record = _single_error_record(caplog, logger)
    assert "ForeignCodeFailure" in record.exc_text
    # The foreign type, its frames and its chain stay out of the record.
    for foreign in ("ForeignOnlyError1678", "_foreign_only_raiser_1678", "OSError"):
        assert foreign not in record.exc_text
    return record


def test_clock_driver_boundary_logs_one_value_free_record(caplog: pytest.LogCaptureFixture) -> None:
    payload = yaml.safe_load(_scenario_yaml())
    payload["time_domains"]["scenario"]["tick_period_seconds"] = {"numerator": 1, "denominator": 100}
    progression = payload["time_progression_policies"]["scenario-progression"]
    progression["advancement_mode"] = "real_time"
    progression.pop("step_ticks")
    payload["temporal_constraints"]["green-cadence"]["cadence_ticks"] = 1
    runtime_model = compile_runtime_model(parse_sdl(yaml.safe_dump(payload, sort_keys=False)))
    policy = next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )
    participant_runtime = _NativeParticipantRuntime()
    scheduler = ParticipantScheduler()
    snapshot = scheduler.initialize(
        [policy], runtime_model.time_model, participant_runtime, TimeCoordinator(runtime_model.time_model).initialize()
    ).snapshot
    snapshot = scheduler.run_due([policy], runtime_model.time_model, participant_runtime, snapshot).snapshot
    driver = ParticipantClockDriver(
        [policy],
        runtime_model.time_model,
        snapshot=lambda: snapshot,
        advance=_foreign_only_raiser_1678,
        service_due=lambda: ApplyResult(success=True, snapshot=snapshot),
        lock=threading.RLock(),
    )

    driver.start()
    _await_driver_outcome(lambda: driver.failure is not None)
    driver.stop(timeout=1.0)

    record = _single_foreign_record(caplog, "raes_runtime.participant_clock_driver")
    assert "participant_clock_driver" in record.exc_text


def test_rejected_history_event_diagnostic_omits_the_event_values() -> None:
    participant = "participant.behavior.green"
    request = SimpleNamespace(participant_address=participant)
    predecessor = SimpleNamespace(participant_behavior_history={participant: []})
    result = SimpleNamespace(
        snapshot=SimpleNamespace(participant_behavior_history={participant: [{"event_type": _SENTINEL}]})
    )

    violation, appended = _history_structure_violation(request, result, predecessor)

    assert violation == "participant runtime appended an invalid behavior history event"
    assert appended == []


def test_flow_sink_resolver_failure_is_logged_and_denied(caplog: pytest.LogCaptureFixture) -> None:
    plane = SimpleNamespace(_snapshot=RuntimeSnapshot())
    crossing = SimpleNamespace(intent=SimpleNamespace())

    decision = _resolve_flow_sink_relation(plane, crossing, _raise_secret, "participant-output", ())

    assert decision.permitted is False
    _single_error_record(caplog, "raes_runtime.participant_flow_sink")


def test_control_resolver_failure_is_logged_and_unresolved(caplog: pytest.LogCaptureFixture) -> None:
    plane = SimpleNamespace(_snapshot=RuntimeSnapshot())
    binding = SimpleNamespace(resolver=SimpleNamespace(resolve=_raise_secret))

    outcome = _resolve(plane, binding, SimpleNamespace(intent=None), "participant-output", ())

    assert outcome.disposition == "unresolved"
    _single_error_record(caplog, "raes_runtime.participant_control_orchestration")


def test_control_provider_failure_is_logged_and_contributes_nothing(caplog: pytest.LogCaptureFixture) -> None:
    provider = SimpleNamespace(resolve=_foreign_only_raiser_1678)

    assert _provider_results(SimpleNamespace(), provider, object(), {"slot"}) is None
    _single_foreign_record(caplog, "raes_runtime.participant_control_orchestration")


def test_mixed_phase_evaluator_failure_is_logged_and_denied(caplog: pytest.LogCaptureFixture) -> None:
    plane = SimpleNamespace(
        _mixed_runtime=SimpleNamespace(transition_evaluators={"evaluator": _raise_secret}),
        _snapshot=RuntimeSnapshot(),
    )
    transition = SimpleNamespace(evaluator_ref="evaluator", evidence_bindings=(), progress_bound=1)

    evaluation = _evaluate(plane, transition, object())

    assert evaluation.permitted is False
    assert evaluation.order_ref == "order:evaluator-failed"
    _single_error_record(caplog, "raes_runtime.mixed_runtime_phase")


def test_concurrent_backend_failure_is_logged_and_settled(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scheduler_operations,
        "_bound_action_request",
        lambda context, working, state: SimpleNamespace(
            participant_address=context.participant_address,
            execution_scope_ref=None,
            temporal_contexts=(),
            action_instance_id=f"{context.participant_address}:attempt-{state.attempted_actions}",
        ),
    )
    batch = _batch(SimpleNamespace(admit_actions_concurrently=_foreign_only_raiser_1678))

    _execute_concurrent_batch(batch)

    assert batch.run.failure is not None
    assert batch.run.failure.diagnostics[0].code == "runtime.participant-concurrent-batch-failed"
    _single_foreign_record(caplog, "raes_runtime.participant_scheduler_concurrent_dispatch")


def test_inject_resolver_failure_is_logged_before_the_hidden_refusal(caplog: pytest.LogCaptureFixture) -> None:
    plane = SimpleNamespace(
        _mutation_authority=SimpleNamespace(external_call=nullcontext),
        _execution_adapter=SimpleNamespace(call=_raise_secret),
        _inject_delivery=SimpleNamespace(resolver=SimpleNamespace(resolve_delivery=_raise_secret)),
        _snapshot=RuntimeSnapshot(),
        _supervision=SimpleNamespace(admission_ms=1000),
    )

    with pytest.raises(ConflictError, match="projection is unavailable") as raised:
        _resolve_delivery(plane, object(), object(), object())

    assert raised.value.__cause__ is None
    assert _SENTINEL not in str(raised.value)
    _single_error_record(caplog, "raes_runtime.participant_inject_application")


def test_crossing_extension_refusal_is_a_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(_prefix: object, _records: object, _context: object) -> None:
        raise ValueError("typed subject identity was reused with different semantics")

    monkeypatch.setattr(CrossingPrefix, "validate_extension", refuse)
    plane = SimpleNamespace(
        _snapshot=RuntimeSnapshot(),
        _crossing_policy_resolver=SimpleNamespace(validation_context=lambda _snapshot, _participant: object()),
    )

    intent = SimpleNamespace(participant_address="participant.behavior.green")
    with pytest.raises(ConflictError, match="conflicts with its retained history") as raised:
        _next_crossing_snapshot(plane, intent, [])

    assert isinstance(raised.value.__cause__, ValueError)


def test_context_view_request_reference_refusal_is_invalid_input() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    try:
        control_plane.initialize_participant_episode("participant.alice")

        with pytest.raises(InvalidInputError, match="context view request is invalid"):
            control_plane.get_participant_context_view("participant.alice", view_ref="")
    finally:
        control_plane.close()


def test_proposal_source_reference_without_revision_is_invalid_input() -> None:
    intent = ParticipantProposalControlIntent.model_construct(
        source_proposal_ref="proposal:source", source_proposal_revision=None
    )

    with pytest.raises(InvalidInputError, match="requires its revision"):
        _intent_target(intent)


def test_effect_owner_claim_block_propagates_and_owner_refusal_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    claim = SimpleNamespace(receipt=SimpleNamespace(operation_id="claim-1"))
    monkeypatch.setattr(control_effects, "owner_record", lambda *_args: None)

    def blocked(*_args: object, **_kwargs: object) -> None:
        raise NewClaimRejected

    monkeypatch.setattr(control_effects, "_submit", blocked)
    with pytest.raises(NewClaimRejected):
        control_effects._submitted_outcome(object(), claim, object(), object(), principal=object())

    # Regression: an indeterminate-operation block and lost runtime ownership were RuntimeError
    # and left recovery open; as categories they must still propagate, not fail the effect.
    for interruption in (
        IndeterminateClaimBlocked("indeterminate operation requires resolution before effectful mutation"),
        OperationalError("in-memory control-plane runtime ownership has ended"),
    ):

        def interrupted(*_args: object, error: Exception = interruption, **_kwargs: object) -> None:
            raise error

        monkeypatch.setattr(control_effects, "_submit", interrupted)
        with pytest.raises(type(interruption)):
            control_effects._submitted_outcome(object(), claim, object(), object(), principal=object())

    def refused(*_args: object, **_kwargs: object) -> None:
        raise ConflictError("participant control intent refused")

    monkeypatch.setattr(control_effects, "_submit", refused)
    assert control_effects._submitted_outcome(object(), claim, object(), object(), principal=object()) == "failed"


def test_linked_action_refusal_does_not_report_a_defect_as_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    plane = SimpleNamespace(_snapshot=RuntimeSnapshot())
    request = SimpleNamespace(participant_address="participant.behavior.green")

    def defect(*_args: object) -> None:
        raise ValueError("internal defect")

    monkeypatch.setattr(action_admission, "require_live_control_proposal", defect)
    with pytest.raises(ValueError, match="internal defect"):
        action_admission.linked_action_refusal(plane, request)

    def stale(*_args: object) -> None:
        raise ConflictError("linked control proposal is no longer eligible")

    monkeypatch.setattr(action_admission, "require_live_control_proposal", stale)
    refusal = action_admission.linked_action_refusal(plane, request)
    assert refusal is not None
    assert refusal.diagnostics[0].code == "runtime.participant-control.action-not-authorized"


def test_scheduler_binding_defect_is_not_a_binding_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    context = SimpleNamespace(participant_address="participant.behavior.green")
    run = SimpleNamespace(working=RuntimeSnapshot(), diagnostics=[], failure=None)

    def defect(*_args: object) -> ParticipantActionAdmissionRequest:
        raise TypeError("internal defect")

    monkeypatch.setattr(scheduler_operations, "_bound_action_request", defect)
    with pytest.raises(TypeError, match="internal defect"):
        scheduler_operations._try_bound_action_request(context, object(), run)

    def refused(*_args: object) -> ParticipantActionAdmissionRequest:
        raise InvalidInputError("backend autonomous action binding does not satisfy its contract")

    monkeypatch.setattr(scheduler_operations, "_bound_action_request", refused)
    assert scheduler_operations._try_bound_action_request(context, object(), run) is None
    assert run.diagnostics[-1].code == "runtime.participant-autonomous-binding-invalid"


def test_restored_control_archive_refusal_is_an_integrity_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(_payload: object) -> object:
        raise ValueError("participant control occurrence lineage is unsupported")

    monkeypatch.setattr(control_replay, "parse_participant_control_occurrence", refuse)
    history = {"participant.behavior.green": [{"schema_version": "2.0.0"}]}
    plane = SimpleNamespace(
        _snapshot=SimpleNamespace(participant_control_history=history),
        _mixed_control=SimpleNamespace(legacy_declarations=()),
    )

    with pytest.raises(EvidenceIntegrityError, match="archive does not validate") as raised:
        control_replay.validate_restored_control_archive(plane)

    assert isinstance(raised.value.__cause__, ValueError)
