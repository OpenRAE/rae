"""Portable mixed services execute under the shared runtime's original authority."""

import pytest
from participant_crossing_fixtures import admission_request, behavior, evidence, identity
from raes_contracts.contracts.mixed_backend_transcript import established_mixed_backend_state
from raes_contracts.runtime_state import OperationState
from test_issue_1371_mixed_backend_contracts import _binding, _scenario, _stage_context


def execute(plane):
    return plane.admit_participant_action(
        behavior(), admission_request(), identity=identity(), crossing_evidence=evidence(), idempotency_key="portable"
    )


@pytest.mark.parametrize(
    "fault, expected",
    [(None, "succeeded"), ("partial", "indeterminate"), ("missing-delivery", "indeterminate"), ("time", "failed")],
)
def test_portable_services_drive_the_shared_runtime(fault, expected):
    from mixed_execution_fixtures import portable_plane

    plane, state, roles, calls, runtimes = portable_plane()
    if fault == "partial":
        roles["bridge"].execution_status = "partial"
    if fault == "missing-delivery":
        state.missing_delivery = True
    if fault == "time":
        roles["coordinator"].fail = True
    try:
        receipt = execute(plane)
        record = plane._store.load_records()[receipt.operation_id]
        assert record.status.state.value == expected
        assert record.invocation is not None
        assert record.invocation.request.command.contract_id == "mixed-backend-execution-binding-v1"
        assert record.invocation.request.binding.context == receipt.context
        if fault is None:
            assert record.invocation.mixed_post_time_state is not None
        assert roles["bridge"].starts == (0 if fault == "time" else 1)
        assert runtimes["sim"].admission_count == 0
        if fault != "time":
            assert roles["bridge"].native_targets == ["native:contain-host"]
            assert calls.index("coordinate") < calls.index("bridge") < calls.index("execution-readback")
        if fault == "partial":
            assert record.invocation.responses[-1].message.effects.residual_state is not None
            assert plane.snapshot.participant_behavior_history
        history = plane.snapshot.mixed_composition_history[state.run_id]
        observations = [e for e in history if e["event_kind"] == "observation"]
        assert bool(observations) == (fault in {None, "partial"})
        assert execute(plane).operation_id == receipt.operation_id
        assert roles["bridge"].starts == (0 if fault == "time" else 1)
    finally:
        plane.close()


def test_contextual_refusal_is_audit_only_before_claim():
    from mixed_execution_fixtures import portable_plane

    plane, _, roles, _, _ = portable_plane()
    roles["bridge"].refuse = True
    try:
        receipt = execute(plane)
        assert not receipt.accepted
        assert roles["bridge"].starts == 0
    finally:
        plane.close()


@pytest.mark.parametrize("stale, expected", [(False, "succeeded"), (True, "failed")])
def test_portable_handoff_requires_correlated_native_owner_readback(stale, expected):
    from mixed_execution_fixtures import portable_plane

    plane, state, roles, calls, _ = portable_plane(handoff=True)
    if stale:
        roles["bridge"].handoff_status = "stale"
    try:
        receipt = plane.advance_mixed_composition(
            transition_id="transition.sim-to-emu", identity=identity(), idempotency_key="handoff"
        )
        assert plane.get_operation(receipt.operation_id, identity=identity()).state.value == expected
        cut = plane.snapshot.mixed_composition_states[state.run_id]
        assert cut["phase_revision"] == (0 if stale else 1)
        assert calls == ["coordinate", "bridge", "execution-readback", "owner-readback"]
    finally:
        plane.close()


def test_invalid_native_result_cannot_publish_delivery_or_observation():
    from dataclasses import replace

    from mixed_execution_fixtures import portable_plane

    plane, state, roles, _, _ = portable_plane()
    original = roles["bridge"].start_operation

    def corrupt(request):
        response = original(request)
        result = roles["bridge"].result
        roles["bridge"].result = replace(
            result,
            snapshot=result.snapshot.with_entries(
                dict(result.snapshot.entries), evaluation_results={"evaluation.foreign": {"success": True}}
            ),
        )
        return response

    roles["bridge"].start_operation = corrupt
    try:
        receipt = execute(plane)
        record = plane._store.load_records()[receipt.operation_id]
        assert record.status.state is OperationState.INDETERMINATE
        assert record.invocation.reserved
        assert [report.stage.stage for report in record.invocation.mixed_reports] == [
            "time-grant",
            "execution",
            "delivery",
            "observation",
        ]
        assert not any(
            event["event_kind"] in {"delivery", "observation"}
            for event in plane.snapshot.mixed_composition_history[state.run_id]
        )
    finally:
        plane.close()


def test_foreign_producer_keeps_prior_execution_without_inventing_delivery():
    from mixed_execution_fixtures import portable_plane

    plane, state, roles, _, _ = portable_plane()
    roles["delivery"].foreign = True
    try:
        receipt = execute(plane)
        record = plane._store.load_records()[receipt.operation_id]
        assert record.status.state is OperationState.INDETERMINATE
        assert [report.stage.stage for report in record.invocation.mixed_reports] == ["time-grant", "execution"]
        assert not any(
            event["event_kind"] in {"delivery", "observation"}
            for event in plane.snapshot.mixed_composition_history[state.run_id]
        )
    finally:
        plane.close()


def test_blocked_bridge_has_responsive_controls_and_no_late_completion():
    from threading import Thread
    from time import monotonic

    from mixed_execution_fixtures import portable_plane
    from raes_runtime.operation_supervision_configuration import OperationSupervisionConfiguration

    plane, state, roles, _, _ = portable_plane(supervision=OperationSupervisionConfiguration(execution_ms=700))
    bridge = roles["bridge"]
    bridge.release.clear()
    receipts, failures = [], []

    def invoke():
        try:
            receipts.append(execute(plane))
        except Exception as error:
            failures.append(error)

    thread = Thread(target=invoke)
    thread.start()
    try:
        assert bridge.started.wait(2)
        operation_id = bridge.request.binding.operation_id
        started = monotonic()
        plane.stop_admission(identity=identity())
        plane.cancel_operation(operation_id, control_id="cancel:blocked", identity=identity())
        assert monotonic() - started < 0.6
        assert bridge.cancels == 1
        thread.join(2)
        assert not thread.is_alive()
        assert not failures
        assert plane.get_operation(operation_id, identity=identity()).state is OperationState.INDETERMINATE
        bridge.release.set()
        assert not any(
            event["event_kind"] == "observation" for event in plane.snapshot.mixed_composition_history[state.run_id]
        )
    finally:
        bridge.release.set()
        thread.join(3)
        plane.close()


@pytest.mark.parametrize(
    "destination, expected, calls", [(4, OperationState.SUCCEEDED, 1), (3, OperationState.FAILED, 0)]
)
def test_nonidentity_affine_mapping_controls_actual_dispatch(destination, expected, calls):
    from mixed_execution_fixtures import portable_plane

    plane, _, roles, _, _ = portable_plane(affine_destination=destination)
    try:
        receipt = execute(plane)
        record = plane._store.load_records()[receipt.operation_id]
        assert record.status.state is expected
        assert roles["bridge"].starts == calls
        grant = record.invocation.mixed_reports[0].stage
        assert (grant.source_coordinate.tick, grant.destination_coordinate.tick) == (2, destination)
    finally:
        plane.close()


@pytest.mark.parametrize("partial", [False, True])
def test_local_reopen_retains_stages_and_never_reissues_a_consumed_effect(tmp_path, partial):
    from mixed_execution_fixtures import portable_plane
    from raes_runtime.control_plane_store_local import LocalControlPlaneStore

    plane, state, roles, _, _ = portable_plane(store=LocalControlPlaneStore(tmp_path / "mixed"))
    if partial:
        roles["bridge"].execution_status = "partial"
    receipt = execute(plane)
    original = plane._store.load_records()[receipt.operation_id].invocation
    plane.close()
    reopened, _, roles, _, _ = portable_plane(store=LocalControlPlaneStore(tmp_path / "mixed"), resolver=state.resolver)
    roles["bridge"].refuse = True
    try:
        assert execute(reopened).operation_id == receipt.operation_id
        restored = reopened._store.load_records()[receipt.operation_id].invocation
        assert restored == original
        assert roles["bridge"].starts == 0
        assert restored.reserved == partial
    finally:
        reopened.close()


def test_retained_mixed_stages_and_cut_cannot_be_rewritten():
    from mixed_execution_fixtures import portable_plane
    from raes_runtime.operation_invocation_ledger import require_invocation_transition

    plane, _, _, _, _ = portable_plane()
    try:
        receipt = execute(plane)
        ledger = plane._store.load_records()[receipt.operation_id].invocation
        truncated = ledger.model_copy(update={"mixed_reports": ledger.mixed_reports[:-1]})
        with pytest.raises(ValueError, match="append-only"):
            require_invocation_transition(ledger, truncated)
        replaced_time = ledger.model_copy(update={"mixed_time_state": None})
        with pytest.raises(ValueError, match="immutable"):
            require_invocation_transition(ledger, replaced_time)
        replaced_post_time = ledger.model_copy(update={"mixed_post_time_state": None})
        with pytest.raises(ValueError, match="immutable"):
            require_invocation_transition(ledger, replaced_post_time)
        report = ledger.mixed_reports[-1]
        changed = report.model_copy(update={"stage": report.stage.model_copy(update={"evidence_refs": ("forged",)})})
        replaced_report = ledger.model_copy(update={"mixed_reports": (*ledger.mixed_reports, changed)})
        payload = replaced_report.model_dump(mode="json")
        model = type(ledger)
        with pytest.raises(ValueError, match="duplicate"):
            model.model_validate(payload)
    finally:
        plane.close()


def test_willingness_withdrawn_during_coordination_never_starts_the_bridge():
    from mixed_execution_fixtures import portable_plane

    plane, _, roles, _, _ = portable_plane()
    original = roles["coordinator"].grant

    def withdraw(request, time_state):
        roles["bridge"].refuse = True
        return original(request, time_state)

    roles["coordinator"].grant = withdraw
    try:
        receipt = execute(plane)
        record = plane._store.load_records()[receipt.operation_id]
        assert record.status.state is OperationState.CANCELLED
        assert roles["bridge"].starts == 0
        assert not record.invocation.reserved
    finally:
        plane.close()


def test_handoff_replay_returns_the_original_without_new_backend_admission():
    from mixed_execution_fixtures import portable_plane

    plane, _, roles, _, _ = portable_plane(handoff=True)
    try:
        receipt = plane.advance_mixed_composition(
            transition_id="transition.sim-to-emu", identity=identity(), idempotency_key="handoff"
        )
        roles["bridge"].refuse = True
        replay = plane.advance_mixed_composition(
            transition_id="transition.sim-to-emu", identity=identity(), idempotency_key="handoff"
        )
        assert replay.operation_id == receipt.operation_id
        assert roles["bridge"].starts == 1
    finally:
        plane.close()


def test_mixed_distributed_installation_refuses_without_worker_authority():
    from mixed_execution_fixtures import portable_plane
    from raes_runtime.control_plane_configuration import ControlPlaneConfiguration

    class Dispatcher:
        worker_identity = "worker:unbound"

        def submit(self, request):
            pass

        def binding(self, request):
            pass

        def deliver_control(self, request, control):
            pass

        def close(self):
            pass

    plane, _, _, _, _ = portable_plane()
    try:
        dispatcher = Dispatcher()
        with pytest.raises(ValueError, match="mixed.*worker"):
            ControlPlaneConfiguration(
                mixed_runtime=plane._mixed_runtime,
                run_scope=plane._run_scope,
                crossing_policy_resolver=plane._crossing_policy_resolver,
                distributed_execution=dispatcher,
            )
    finally:
        plane.close()


def test_shared_provider_progress_does_not_settle_the_mixed_operation_early():
    from mixed_execution_fixtures import portable_plane

    plane, _, roles, _, _ = portable_plane()
    bridge = roles["bridge"]
    observe = bridge.observe_operation
    observations = []

    def progress(control):
        observations.append(control)
        if len(observations) == 1:
            return bridge.report(bridge.request, {"kind": "progress", "phase": "executing"})
        return observe(control)

    bridge.observe_operation = progress
    try:
        receipt = execute(plane)
        assert plane.get_operation(receipt.operation_id, identity=identity()).state is OperationState.SUCCEEDED
        assert len(observations) == 2
    finally:
        plane.close()


def test_unavailable_optional_observation_does_not_erase_confirmed_delivery():
    from mixed_execution_fixtures import portable_plane

    plane, state, roles, _, _ = portable_plane()

    def unavailable(control):
        raise RuntimeError("private reader unavailable")

    roles["observation"].read_stage = unavailable
    try:
        receipt = execute(plane)
        assert plane.get_operation(receipt.operation_id, identity=identity()).state is OperationState.SUCCEEDED
        kinds = [event["event_kind"] for event in plane.snapshot.mixed_composition_history[state.run_id]]
        assert "delivery" in kinds
        assert "observation" not in kinds
    finally:
        plane.close()


def test_known_execution_failure_needs_no_delivery_or_observation():
    from mixed_execution_fixtures import portable_plane

    plane, state, roles, calls, _ = portable_plane()
    roles["bridge"].execution_status = "failed"
    try:
        receipt = execute(plane)
        record = plane._store.load_records()[receipt.operation_id]
        assert record.status.state is OperationState.FAILED
        assert not record.invocation.reserved
        assert "delivery" not in calls
        assert "observation" not in calls
    finally:
        plane.close()


def test_blocked_transition_evaluator_uses_the_same_finite_invocation_budget():
    from dataclasses import replace
    from threading import Event, Thread

    from mixed_execution_fixtures import portable_plane
    from raes_runtime.operation_supervision_configuration import OperationSupervisionConfiguration

    plane, _, roles, _, _ = portable_plane(
        handoff=True, supervision=OperationSupervisionConfiguration(execution_ms=700)
    )
    entered, release = Event(), Event()
    original = next(iter(plane._mixed_runtime.transition_evaluators.values()))

    def blocked(*args):
        entered.set()
        release.wait(3)
        return original(*args)

    plane._mixed_runtime = replace(
        plane._mixed_runtime, transition_evaluators={key: blocked for key in plane._mixed_runtime.transition_evaluators}
    )
    receipts = []
    thread = Thread(
        target=lambda: receipts.append(
            plane.advance_mixed_composition(
                transition_id="transition.sim-to-emu", identity=identity(), idempotency_key="blocked-evaluator"
            )
        )
    )
    thread.start()
    try:
        assert entered.wait(2)
        thread.join(1.5)
        assert not thread.is_alive()
        assert roles["bridge"].starts == 0
        assert plane.get_operation(receipts[0].operation_id, identity=identity()).state is OperationState.INDETERMINATE
    finally:
        release.set()
        thread.join(3)
        plane.close()


@pytest.mark.parametrize("changed", [False, True])
def test_stage_retransmission_is_idempotent_and_changed_duplicates_are_refused(changed):
    from mixed_execution_fixtures import portable_plane

    plane, _, roles, _, _ = portable_plane()
    original = roles["bridge"].stage_reports

    def retransmit(control):
        report = original(control)[0]
        duplicate = (
            report.model_copy(
                update={"stage": report.stage.model_copy(update={"evidence_refs": ("evidence:changed",)})}
            )
            if changed
            else report
        )
        return report, duplicate

    roles["bridge"].stage_reports = retransmit
    try:
        receipt = execute(plane)
        record = plane._store.load_records()[receipt.operation_id]
        assert record.status.state is (OperationState.INDETERMINATE if changed else OperationState.SUCCEEDED)
        executions = [report for report in record.invocation.mixed_reports if report.stage.stage == "execution"]
        assert len(executions) == 1
    finally:
        plane.close()


def test_runtime_settlement_uses_the_contract_stage_model():
    request, responses, reports = _scenario("mixed-edge")
    assert (
        established_mixed_backend_state(_binding(), request, responses, reports, context=_stage_context("mixed-edge"))
        is OperationState.SUCCEEDED
    )


def test_missing_delivery_establishes_no_success_from_a_backend_boolean():
    request, responses, reports = _scenario("mixed-edge")
    assert (
        established_mixed_backend_state(
            _binding(), request, responses[:-1], reports[:2], context=_stage_context("mixed-edge")
        )
        is OperationState.INDETERMINATE
    )


@pytest.mark.parametrize("fault", ["pin", "missing", "aliased-readers", "undeclared", "reader-shape"])
def test_unauthorized_service_installation_is_refused_before_effect(fault):
    from dataclasses import replace

    from mixed_execution_fixtures import portable_plane

    plane, _, roles, _, _ = portable_plane()
    installation = next(iter(plane._mixed_runtime.backend_installations.values()))
    services = dict(installation.services)
    pin = installation.binding.subject.delivery_reader
    original = services[pin.service_ref]
    if fault == "pin":
        services[pin.service_ref] = replace(original, identity=pin.model_copy(update={"digest": "sha256:" + "f" * 64}))
    elif fault == "missing":
        del services[pin.service_ref]
    elif fault == "aliased-readers":
        services[pin.service_ref] = replace(original, implementation=roles["observation"])
    elif fault == "undeclared":
        services[pin.service_ref] = replace(original, declared_contracts=())
    else:
        services[pin.service_ref] = replace(original, implementation=object())
    try:
        with pytest.raises(ValueError):
            replace(installation, services=services)
        assert roles["bridge"].starts == 0
    finally:
        plane.close()


def test_native_artifact_digest_is_verified_before_publishing_its_state():
    from mixed_execution_fixtures import portable_plane

    plane, _, roles, _, _ = portable_plane()
    bridge = roles["bridge"]
    original = bridge.observe_operation

    def mismatched(control):
        response = original(control)
        reference = response.message.result.model_copy(update={"digest": "sha256:" + "0" * 64})
        return response.model_copy(update={"message": response.message.model_copy(update={"result": reference})})

    bridge.observe_operation = mismatched
    try:
        receipt = execute(plane)
        record = plane._store.load_records()[receipt.operation_id]
        assert record.status.state is OperationState.INDETERMINATE
        assert record.invocation.reserved
        assert not plane.snapshot.participant_behavior_history
    finally:
        plane.close()
