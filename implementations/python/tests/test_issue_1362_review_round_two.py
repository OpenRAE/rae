"""Execution boundaries repaired after the additional review."""

from dataclasses import replace
from threading import Event, Thread

import pytest
from raes_backend_stubs.stubs import StubProvisioner, create_stub_target
from raes_contracts.errors import OperationalError
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.errors import RuntimeBudgetExhaustedError
from raes_runtime.operation_supervision_configuration import OperationSupervisionConfiguration


def test_native_capacity_refusal_does_not_leave_an_unsettled_acceptance():
    entered, release = Event(), Event()

    class BlockedValidation(StubProvisioner):
        def validate(self, plan):
            entered.set()
            assert release.wait(3)
            return []

    plane = RuntimeControlPlane(
        replace(create_stub_target(), provisioner=BlockedValidation()),
        supervision=OperationSupervisionConfiguration(execution_ms=100),
    )
    try:
        first = plane.submit_provisioning(ProvisioningPlan())
        assert entered.is_set()
        assert plane.get_operation(first.operation_id).state is OperationState.CANCELLED
        second = plane.submit_provisioning(ProvisioningPlan())
        assert plane.get_operation(second.operation_id).state is OperationState.CANCELLED
        assert not plane._store.load_records()[second.operation_id].invocation.reserved
        release.set()
        assert plane._execution_adapter.drain(timeout_ms=1000)
    finally:
        release.set()
        plane.close()


def test_outer_activity_admission_wait_consumes_the_original_allowance():
    import asyncio

    from raes_runtime.operation_temporal_worker import TemporalOperationActivities
    from test_issue_1362_provider_execution import Provider

    calls = []
    activities = TemporalOperationActivities(
        provider=Provider(), effect_authority=None, control_authority=None, worker_identity="worker-1"
    )

    async def exercise():
        held, release = asyncio.Event(), asyncio.Event()

        async def holder():
            async with activities._offload_limiters["effect"]:
                held.set()
                await release.wait()

        task = asyncio.create_task(holder())
        await held.wait()
        try:
            rejected_effect_job = activities._job(
                activities._effect_jobs, "effect", lambda: calls.append(True), budget_ms=50
            )
            with pytest.raises(OperationalError):
                await asyncio.wait_for(rejected_effect_job, 0.3)
            assert not calls
        finally:
            release.set()
            await task

    try:
        asyncio.run(exercise())
    finally:
        assert activities.close()


@pytest.mark.parametrize("distributed", [False, True])
def test_protocol_result_finalization_is_bounded_while_an_archive_remains_blocked(distributed, tmp_path):
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_contracts.versions import BACKEND_OPERATION_CONTRACT_IDS
    from raes_operations.run_artifacts import RunMaterializationArchive
    from raes_runtime.control_plane_store_snapshots import _snapshot_payload
    from raes_runtime.registry import RuntimeTarget
    from test_issue_1241_materialization_context import attesting_plan
    from test_issue_1241_materialization_runtime import ReportingProvisioner
    from test_issue_1362_distributed_authority import Dispatcher, worker
    from test_issue_1362_provider_execution import Provider

    entered, release = Event(), Event()
    execution, _ = attesting_plan()
    execution = replace(execution, provisioning=replace(execution.provisioning, operation_id="archive-bound"))
    provider = Provider()
    manifest = replace(
        execution.manifest,
        supported_contract_versions=execution.manifest.supported_contract_versions
        | frozenset(BACKEND_OPERATION_CONTRACT_IDS),
    )
    configured = RuntimeTarget(
        name="stub", manifest=manifest, provisioner=ReportingProvisioner(manifest), operation_provider=provider
    )
    raw = ReportingProvisioner(configured.manifest).apply(execution.provisioning, RuntimeSnapshot())
    reference = {
        "contract_id": "runtime-snapshot-v1",
        "artifact_id": "native-result",
        "digest": canonical_json_digest(_snapshot_payload(raw.snapshot)),
    }

    def outcome(control):
        return provider.report(
            provider.request,
            {
                "kind": "outcome",
                "proposed_state": "succeeded",
                "effects": {
                    "effect": "complete",
                    "cessation_established": True,
                    "evidence_refs": [reference],
                    "residual_scope": list(raw.snapshot.entries),
                    "residual_state": reference,
                },
                "satisfaction": "satisfied",
                "release_gates_satisfied": True,
                "cancellation_established": False,
                "result": reference,
            },
        )

    provider.observe_operation = outcome
    archive = RunMaterializationArchive(tmp_path / "archive")

    class BlockedArchive:
        def publish(self, content):
            entered.set()
            assert release.wait(5)
            return archive.publish(content)

    class Evidence:
        def validate_effects(self, request, response):
            return request.binding == response.binding

        def resolve_result(self, *args):
            return raw

    dispatcher = Dispatcher() if distributed else None
    plane = RuntimeControlPlane(
        configured,
        operation_evidence=Evidence(),
        distributed_execution=dispatcher,
        materialization_archive=BlockedArchive(),
        run_scope="run:run-1",
        supervision=OperationSupervisionConfiguration(observation_ms=800, execution_ms=5000, drain_ms=50),
    )
    receipts, errors = [], []

    def complete():
        try:
            if distributed:
                plane.publish_backend_response(outcome(None), identity=worker())
            else:
                receipts.append(plane.submit_provisioning(execution.provisioning))
        except Exception as error:  # noqa: BLE001 - the worker hands the exception to the test thread, which asserts it.
            errors.append(error)

    running = None
    try:
        plane.register_planner_produced_plan(
            replace(execution, target_name=configured.name, manifest=configured.manifest)
        )
        if distributed:
            receipts.append(plane.submit_provisioning(execution.provisioning))
            request = dispatcher.commands[0]
            plane.claim_backend_invocation(
                request.binding, provider.operation_capabilities(), provider.check_operation(request), identity=worker()
            )
            plane.publish_backend_response(provider.start_operation(request), identity=worker())
        running = Thread(target=complete)
        running.start()
        assert entered.wait(2), errors
        running.join(1.5)
        assert not running.is_alive(), "native finalization escaped its time allowance"
        assert not errors
        assert plane.get_operation(receipts[0].operation_id).state is OperationState.INDETERMINATE
        assert plane._store.load_records()[receipts[0].operation_id].invocation.reserved
        with pytest.raises(RuntimeBudgetExhaustedError):
            plane.close()
    finally:
        release.set()
        if running is not None:
            running.join(2)
        assert plane._execution_adapter.drain(timeout_ms=2000)
        assert plane.get_operation(receipts[0].operation_id).state is OperationState.INDETERMINATE
        plane.close()


@pytest.mark.parametrize("distributed", [False, True])
@pytest.mark.parametrize("collection_fails", [False, True])
def test_protocol_success_runs_and_retains_the_native_observation_lifecycle(distributed, collection_fails):
    from raes_contracts.observation_demand import ObservationDemandRule, ObservationLifecycleStage
    from raes_contracts.observation_demand_resolution import normalize_observation_demands
    from raes_runtime.observation_execution import ConfiguredObservationRuntime
    from test_issue_1212_observation_demand import _document, _runtime_capability, _runtime_capability_id, _selector
    from test_issue_1362_distributed_authority import Dispatcher, worker
    from test_issue_1362_provider_execution import Evidence, Provider, target

    selector = _selector("/nodes/fixture", "filesystem-trace")
    demands = normalize_observation_demands(
        _document(
            ObservationDemandRule(
                rule_id="collected",
                scope=selector.semantic_scope,
                purpose="experimental",
                mode="selected",
                selector=selector,
                collection="require",
                retention="require",
                export="disable",
                redaction="none",
                integrity="none",
                required=False,
            )
        ),
        target_scopes=(selector.semantic_scope,),
    )
    collected = []

    def collect(*args):
        collected.append(selector.key)
        if collection_fails:
            raise RuntimeError("synthetic observation unavailable")
        return ("protected-value",)

    runtime = ConfiguredObservationRuntime(
        capabilities=(
            _runtime_capability(
                selector, stages=frozenset({ObservationLifecycleStage.COLLECTION, ObservationLifecycleStage.RETENTION})
            ),
        ),
        producers={_runtime_capability_id(selector): collect},
    )
    provider, dispatcher = Provider(), Dispatcher() if distributed else None
    plane = RuntimeControlPlane(
        replace(target(provider), observation_runtime=runtime),
        operation_evidence=Evidence(),
        distributed_execution=dispatcher,
    )
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan(observation_demands=demands.effective))
        assert receipt.accepted, receipt.diagnostics
        if distributed:
            request = dispatcher.commands[0]
            plane.claim_backend_invocation(
                request.binding, provider.operation_capabilities(), provider.check_operation(request), identity=worker()
            )
            plane.publish_backend_response(provider.start_operation(request), identity=worker())
            plane.publish_backend_response(provider.observe_operation(None), identity=worker())
        record = plane._store.load_records()[receipt.operation_id]
        assert collected == [selector.key]
        assert record.status.state is (OperationState.INDETERMINATE if collection_fails else OperationState.SUCCEEDED)
        if not collection_fails:
            assert record.result_payload["operation_id"] == receipt.operation_id
            assert record.result_payload["retained"][0]["values"] == ["protected-value"]
            assert plane.observation_execution(receipt.operation_id) is not None
        else:
            assert record.invocation.reserved
    finally:
        plane.close()
