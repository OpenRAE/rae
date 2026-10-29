"""Public core behavior against an executing fixture, distinct from OCI evidence."""

import pytest
from inject_execution_fixtures import ExecutingFixture, fixture_plan, fixture_target, trigger_request
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole


def configured_plane(tmp_path, **options):
    backend = ExecutingFixture(tmp_path / "world")
    selected = fixture_target(backend)
    backend.plan, backend.scenario = fixture_plan(selected)
    plane = RuntimeControlPlane(selected, inject_execution=backend, operation_evidence=backend, **options)
    plane.register_planner_produced_plan(backend.plan)
    return plane, backend, trigger_request(backend.plan)


def test_authored_world_effect_without_participants_has_its_own_durable_outcome(tmp_path):
    plane, backend, request = configured_plane(tmp_path)
    try:
        receipt = plane.submit_inject(request)
        assert receipt.accepted
        assert backend.path.read_bytes() == backend.content
        assert plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
        assert plane.get_inject_occurrence(receipt.operation_id).request == request
        assert plane.get_inject_outcome(receipt.operation_id).effect == "effect-applied"
        correlation = plane.get_inject_correlation(receipt.operation_id)
        assert correlation.occurrence.artifact_id == request.occurrence_id
        assert not plane.snapshot.participant_episode_results
        assert plane._store.load_snapshot_state().revision == 0
        assert plane.submit_inject(request) == receipt
        assert backend.starts == 1
    finally:
        plane.close()


def test_an_auditor_cannot_trigger_and_other_actors_cannot_read_the_occurrence(tmp_path):
    plane, backend, request = configured_plane(tmp_path)
    operator = ControlPlaneIdentity("operator", frozenset({ControlPlaneRole.OPERATOR}), "stub")
    auditor = ControlPlaneIdentity("auditor", frozenset({ControlPlaneRole.AUDITOR}), "stub")
    try:
        with pytest.raises(PermissionError):
            plane.submit_inject(request, identity=auditor)
        assert backend.starts == 0
        assert plane._store.load_records() == {}
        receipt = plane.submit_inject(request, identity=operator)
        for reader in (plane.get_inject_occurrence, plane.get_inject_outcome, plane.get_inject_correlation):
            assert reader(receipt.operation_id, identity=operator) is not None
            assert reader(receipt.operation_id, identity=auditor) is None
            assert reader("unknown", identity=auditor) is None
    finally:
        plane.close()


def test_unverified_readback_never_becomes_success_or_a_participant_result(tmp_path):
    plane, backend, request = configured_plane(tmp_path)
    backend.bad_readback = True
    try:
        receipt = plane.submit_inject(request)
        assert backend.path.read_bytes() == backend.content
        assert plane.get_operation(receipt.operation_id).state is OperationState.INDETERMINATE
        assert plane.get_inject_correlation(receipt.operation_id) is None
        assert plane._store.load_records()[receipt.operation_id].invocation.reserved
        assert plane.submit_inject(request) == receipt
        assert backend.starts == 1
    finally:
        plane.close()


def test_artifact_resolution_cannot_bypass_native_snapshot_validation(tmp_path):
    from raes_contracts.contracts import OperationArtifactReferenceModel

    plane, backend, request = configured_plane(tmp_path)
    original = backend.observe_operation

    def fabricated_native_result(control):
        response = original(control)
        reference = OperationArtifactReferenceModel.model_validate(
            {**backend.readback, "contract_id": "runtime-snapshot-v1"}
        )
        return response.model_copy(update={"message": response.message.model_copy(update={"result": reference})})

    backend.observe_operation = fabricated_native_result
    backend.validate_effects = lambda *args: True
    try:
        receipt = plane.submit_inject(request)
        assert plane.get_operation(receipt.operation_id).state is OperationState.INDETERMINATE
        assert plane.get_inject_correlation(receipt.operation_id) is None
    finally:
        plane.close()


def test_persisted_outcome_models_are_contextually_revalidated_before_use(tmp_path):
    from dataclasses import replace

    plane, backend, request = configured_plane(tmp_path)
    try:
        receipt = plane.submit_inject(request)
        record = plane._store.load_records()[receipt.operation_id]
        copied_model_1 = record.inject_outcome.model_copy(update={"effect": "effect-absent"})
        with pytest.raises(ValueError):
            replace(record, inject_outcome=copied_model_1)
        with pytest.raises(ValueError):
            replace(record, inject_outcome=None)
    finally:
        plane.close()


def test_reading_artifact_metadata_cannot_mutate_the_authoritative_evidence(tmp_path):
    plane, backend, request = configured_plane(tmp_path)
    try:
        receipt = plane.submit_inject(request)
        result = plane.get_inject_result(receipt.operation_id)
        result.artifacts.clear()
        assert plane.get_inject_result(receipt.operation_id).artifacts
    finally:
        plane.close()


def test_inject_evidence_resolution_shares_the_bounded_observation_budget(tmp_path):
    from threading import Event, Thread

    from raes_runtime.operation_supervision_configuration import OperationSupervisionConfiguration

    plane, backend, request = configured_plane(
        tmp_path, supervision=OperationSupervisionConfiguration(observation_ms=1000, execution_ms=10000)
    )
    entered, release, finished = Event(), Event(), Event()
    receipts = []

    def evidence(*args):
        entered.set()
        release.wait(10)
        return True

    backend.validate_effects = evidence

    def submit():
        receipts.append(plane.submit_inject(request))
        finished.set()

    thread = Thread(target=submit)
    thread.start()
    try:
        # Parallel coverage runs need scheduling room before evidence starts.
        # The caller must still finish while evidence remains blocked, well
        # before the execution deadline or the callback's own fallback wait.
        assert entered.wait(5)
        assert finished.wait(3)
        assert plane.get_operation(receipts[0].operation_id).state is OperationState.INDETERMINATE
    finally:
        release.set()
        thread.join(5)
        plane.close()


@pytest.mark.parametrize("after_claim", [False, True])
def test_provider_refusal_before_or_after_claim_never_dispatches(tmp_path, after_claim):
    plane, backend, request = configured_plane(tmp_path)
    original = backend.check_operation
    calls = 0

    def admission(command):
        nonlocal calls
        calls += 1
        backend.refuse = not after_claim or calls >= 2
        return original(command)

    backend.check_operation = admission
    try:
        receipt = plane.submit_inject(request)
        assert backend.starts == 0
        assert not backend.path.exists()
        assert receipt.accepted is after_claim
        if after_claim:
            assert plane.get_operation(receipt.operation_id).state is OperationState.CANCELLED
            assert plane.get_inject_outcome(receipt.operation_id) is None
            assert plane.submit_inject(request) == receipt
        else:
            assert plane._store.load_records() == {}
    finally:
        plane.close()


def test_selected_binding_must_resolve_in_the_exact_pinned_plan(tmp_path):
    plane, backend, request = configured_plane(tmp_path)
    binding = request.bindings[0].model_copy(
        update={"node": "provision.node.other", "binding": "orchestration.inject-binding.other.release"}
    )
    try:
        receipt = plane.submit_inject(request.model_copy(update={"bindings": (binding,)}))
        assert not receipt.accepted
        assert plane._store.load_records() == {}
        assert backend.starts == 0
    finally:
        plane.close()


def test_artifact_only_inject_cannot_omit_native_augmentation_obligations(tmp_path):
    from dataclasses import replace

    from raes_contracts.plan_projection import runtime_plan_digest

    plane, backend, request = configured_plane(tmp_path)
    backend.plan = replace(
        backend.plan, orchestration=replace(backend.plan.orchestration, augmentation_scope_required=True)
    )
    plane.register_planner_produced_plan(backend.plan)
    changed = request.model_copy(
        update={"plan": request.plan.model_copy(update={"digest": runtime_plan_digest(backend.plan.orchestration)})}
    )
    try:
        assert not plane.submit_inject(changed).accepted
        assert backend.starts == 0
    finally:
        plane.close()


def test_settlement_checks_state_authority_before_evaluating_diagnostics(tmp_path):
    from raes_runtime.control_plane_supervised_execution import settle

    plane, _, request = configured_plane(tmp_path)
    evaluated = []

    def diagnostics():
        evaluated.append(True)
        yield from ()

    try:
        receipt = plane.submit_inject(request)
        record = plane._store.load_records()[receipt.operation_id]
        pending = diagnostics()
        with pytest.raises(RuntimeError):
            settle(plane, record, OperationState.FAILED, diagnostics=pending)
        assert not evaluated
    finally:
        plane.close()


class _DurableFixture(ExecutingFixture):
    """Reads its retained invocation from the store, so controls survive a reopen."""

    def __init__(self, path):
        super().__init__(path)
        self.reader = None
        self.fail = False

    def _retained_request(self, control):
        return self.reader(control.binding.operation_id).invocation.request

    def observe_operation(self, control):
        self.request = getattr(self, "request", None) or self._retained_request(control)
        response = super().observe_operation(control)
        if not self.fail:
            return response
        failed = response.message.model_copy(
            update={"proposed_state": "failed", "satisfaction": "unsatisfied", "release_gates_satisfied": False}
        )
        self.failed_message = failed
        return self.report(self.request, failed.model_dump(mode="json"))

    def validate_effects(self, request, response):
        if response.message.kind == "reconciliation":
            return self.path.read_bytes() == self.content
        if self.fail:
            return self.path.read_bytes() == self.content and response.message == self.failed_message
        return super().validate_effects(request, response)

    def reconcile_operation(self, control):
        from raes_contracts.contracts import backend_operation_control_digest

        request = self._retained_request(control)
        self.request = request
        super().observe_operation(control)  # independent readback of the retained world artifact
        return self.report(
            request,
            {
                "kind": "reconciliation",
                "control_id": control.control_id,
                "control_digest": backend_operation_control_digest(control),
                "effects": {"effect": "complete", "cessation_established": True, "evidence_refs": [self.readback]},
            },
        )


def _durable_plane(tmp_path, backend):
    from raes_runtime.control_plane_profiles import ControlPlaneProfile
    from raes_runtime.control_plane_store_local import LocalControlPlaneStore

    selected = fixture_target(backend)
    backend.plan, backend.scenario = fixture_plan(selected)
    plane = RuntimeControlPlane(
        selected,
        inject_execution=backend,
        operation_evidence=backend,
        store=LocalControlPlaneStore(tmp_path / "durable-inject-ledger"),
        profile=ControlPlaneProfile.P1,
    )
    backend.reader = lambda operation_id: plane._store.load_records().get(operation_id)
    return plane


def test_failed_world_effect_retains_the_applied_outcome_without_successful_correlation(tmp_path):
    backend = _DurableFixture(tmp_path / "world")
    backend.fail = True
    with _durable_plane(tmp_path, backend) as plane:
        plane.register_planner_produced_plan(backend.plan)
        receipt = plane.submit_inject(trigger_request(backend.plan))
        assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED
        assert plane.get_inject_outcome(receipt.operation_id).effect == "effect-applied"
        assert plane.get_inject_correlation(receipt.operation_id) is None
        assert not plane._store.load_records()[receipt.operation_id].invocation.reserved


def test_crash_after_world_effect_before_terminal_commit_reopens_without_redispatch(tmp_path, monkeypatch):
    backend = _DurableFixture(tmp_path / "world")
    plane = _durable_plane(tmp_path, backend)
    request = trigger_request(backend.plan)
    plane.register_planner_produced_plan(backend.plan)

    def crash(*args, **kwargs):
        raise KeyboardInterrupt("simulated process loss at the terminal-commit boundary")

    monkeypatch.setattr(plane, "_commit_terminal_operation", crash)
    try:
        with pytest.raises(KeyboardInterrupt):
            plane.submit_inject(request)
        assert backend.path.read_bytes() == backend.content
        parent = next(iter(plane._store.load_records().values()))
        assert parent.status.state is OperationState.RUNNING
        assert parent.invocation.consumed
        assert parent.invocation.reserved
    finally:
        plane.close()
    restarted = _DurableFixture(tmp_path / "world")
    restarted.sequence = backend.sequence  # a backend's response sequence is durable across restart
    with _durable_plane(tmp_path, restarted) as recovered:
        assert recovered.get_operation(parent.receipt.operation_id).state is OperationState.INDETERMINATE
        assert recovered.submit_inject(request) == parent.receipt
        assert backend.starts == 1
        assert restarted.starts == 0
        control = recovered.supervise_operation(
            parent.receipt.operation_id, action="reconcile", control_id="recover-world"
        )
        response = recovered.get_control_response(parent.receipt.operation_id, control.control_id)
        assert response.message.effects.effect == "complete"
        assert response.message.effects.cessation_established
        assert recovered.get_operation(parent.receipt.operation_id).state is OperationState.INDETERMINATE
        assert recovered.get_inject_correlation(parent.receipt.operation_id) is None


def test_produced_artifact_content_survives_reopen_and_later_world_changes(tmp_path):
    from raes_contracts.canonical import canonical_json_digest

    backend = _DurableFixture(tmp_path / "world")
    with _durable_plane(tmp_path, backend) as plane:
        request = trigger_request(backend.plan)
        plane.register_planner_produced_plan(backend.plan)
        receipt = plane.submit_inject(request)
        assert plane.get_inject_artifact(receipt.operation_id, "world-result") == backend.content
        result = plane.get_inject_result(receipt.operation_id)
        assert (
            canonical_json_digest(result.model_dump(mode="json"))
            == plane.get_inject_correlation(receipt.operation_id).result.digest
        )
    (tmp_path / "world").write_bytes(b"a different later world state")
    restarted = _DurableFixture(tmp_path / "world")
    with _durable_plane(tmp_path, restarted) as restored:
        assert restored.submit_inject(request) == receipt
        assert restored.get_inject_result(receipt.operation_id) == result
        assert restored.get_inject_artifact(receipt.operation_id, "world-result") == backend.content
        assert restarted.starts == 0
