"""One engine retains fixed state and resource authority across runs."""

import pytest
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.errors import ConflictError, OperationalError
from raes_contracts.planning import PlanScope
from raes_runtime import RuntimeControlPlane


def _plan(run, run_id):
    return run.plan(
        parse_sdl("name: run-context\nnodes:\n  server:\n    type: compute\n"),
        run_scope=PlanScope(run_id=run_id),
    )


def test_runs_share_engine_capacity_but_keep_state_and_operations_separate():
    target = create_stub_target()
    with RuntimeControlPlane(target) as engine:
        first = engine.open_run(run_scope="run:first")
        second = engine.open_run(run_scope="run:second")
        first_plan, second_plan = _plan(first, "first"), _plan(second, "second")
        assert first._execution_adapter is second._execution_adapter is engine._execution_adapter
        assert first.apply(first_plan).success
        assert first.snapshot.entries
        assert not second.snapshot.entries
        assert not engine.snapshot.entries
        with pytest.raises(ConflictError, match="reserved"):
            second.apply(second_plan)
        assert first.destroy().success
        engine.retire_run("run:first")
        assert second.apply(second_plan).success
        assert not first.snapshot.entries
        assert second.snapshot.entries
        with pytest.raises(ConflictError, match="retired"):
            first.apply(first_plan)
        assert second.destroy().success
        engine.retire_run("run:second")
        assert not engine._closed


def test_run_scope_and_backend_owner_cannot_be_replaced():
    target = create_stub_target()
    with RuntimeControlPlane(target) as engine:
        first = engine.open_run(run_scope="run:first")
        with pytest.raises(ConflictError, match="already"):
            engine.open_run(run_scope="run:first")
        with pytest.raises(ConflictError, match="runtime owner"):
            RuntimeControlPlane(target)
        assert first.apply(_plan(first, "first")).success
        with pytest.raises(ConflictError, match="cleanup"):
            engine.retire_run("run:first")
        assert first.destroy().success
        engine.retire_run("run:first")
        assert engine.snapshot.entries == {}


def test_child_provider_close_failure_retains_every_lease_and_poisons_all_contexts():
    from test_issue_1183_store_ownership_leases import _OrderedCloseStore

    root_store = _OrderedCloseStore([])
    child_store = _OrderedCloseStore([], fail_close=True)
    engine = RuntimeControlPlane(create_stub_target(), store=root_store)
    child = engine.open_run(run_scope="run:child", store=child_store)
    try:
        with pytest.raises(RuntimeError, match="provider close failed"):
            engine.close()
        assert not root_store.lease.closed
        assert not child_store.lease.closed
        for context in (engine, child):
            with pytest.raises(OperationalError, match="requires restart"):
                context.get_snapshot()
    finally:
        child_store.fail_close = False
        engine.close()


def test_fixed_run_stores_reopen_without_retargeting_the_default_scope(tmp_path):
    from raes_runtime.control_plane_store_local import LocalControlPlaneStore

    target = create_stub_target()
    with RuntimeControlPlane(target) as engine:
        first = engine.open_run(run_scope="run:first", store=LocalControlPlaneStore(tmp_path / "first"))
        assert first.apply(_plan(first, "first")).success
        recorded = first.snapshot
    with RuntimeControlPlane(target) as engine:
        first = engine.open_run(run_scope="run:first", store=LocalControlPlaneStore(tmp_path / "first"))
        assert first.snapshot == recorded
        second = engine.open_run(run_scope="run:second", store=LocalControlPlaneStore(tmp_path / "second"))
        second_plan = _plan(second, "second")
        with pytest.raises(ConflictError, match="reserved"):
            second.apply(second_plan)
        assert first.destroy().success
        engine.retire_run("run:first")
        assert second.apply(_plan(second, "second")).success
        assert second.destroy().success


def test_restoring_a_durable_run_cannot_drop_its_required_operation_guarantees(tmp_path):
    from raes_runtime.control_plane_store_local import LocalControlPlaneStore
    from test_issue_1362_provider_execution import Evidence, Provider
    from test_issue_1362_provider_execution import target as provider_target

    target = provider_target(Provider())
    required = ("cessation-evidence", "effect-observation")
    with RuntimeControlPlane(
        target, store=LocalControlPlaneStore(tmp_path / "engine"), operation_evidence=Evidence()
    ) as engine:
        engine.open_run(
            run_scope="run:guarantees",
            store=LocalControlPlaneStore(tmp_path / "run"),
            required_operation_guarantees=required,
        )
    with RuntimeControlPlane(
        target, store=LocalControlPlaneStore(tmp_path / "engine"), operation_evidence=Evidence()
    ) as engine:
        conflicting_store = LocalControlPlaneStore(tmp_path / "run")
        with pytest.raises(ConflictError, match="conflicts"):
            engine.open_run(run_scope="run:guarantees", store=conflicting_store)
        run = engine.open_run(
            run_scope="run:guarantees",
            store=LocalControlPlaneStore(tmp_path / "run"),
            required_operation_guarantees=required,
        )
        from raes_contracts.planning import ProvisioningPlan

        receipt = run.submit_provisioning(ProvisioningPlan())
        assert run._store.load_records()[receipt.operation_id].invocation.request.required_guarantees == required


def test_default_context_also_retains_required_guarantees_across_restart(tmp_path):
    from raes_runtime.control_plane_store_local import LocalControlPlaneStore
    from test_issue_1362_provider_execution import Evidence, Provider
    from test_issue_1362_provider_execution import target as provider_target

    target = provider_target(Provider())
    with RuntimeControlPlane(
        target,
        store=LocalControlPlaneStore(tmp_path),
        required_operation_guarantees=("cessation-evidence",),
        operation_evidence=Evidence(),
    ):
        pass
    with (
        pytest.raises(ConflictError, match="conflicts"),
        RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path), operation_evidence=Evidence()),
    ):
        pass


def test_legacy_default_run_can_finish_before_a_new_run():
    with RuntimeControlPlane(create_stub_target(), run_scope="run:first") as engine:
        assert engine.apply(_plan(engine, "first")).success
        assert engine.destroy().success
        engine.retire_run("run:first")
        second = engine.open_run(run_scope="run:second")
        assert second.apply(_plan(second, "second")).success
        assert engine.snapshot.entries == {}
        assert second.destroy().success


def test_reopened_engine_cannot_skip_a_retained_run_reservation(tmp_path):
    from raes_runtime.control_plane_store_local import LocalControlPlaneStore

    target = create_stub_target()
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path / "engine")) as engine:
        first = engine.open_run(run_scope="run:first", store=LocalControlPlaneStore(tmp_path / "first"))
        assert first.apply(_plan(first, "first")).success
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path / "engine")) as engine:
        default_plan = _plan(engine, "default")
        with pytest.raises(ConflictError, match="restored|reserved"):
            engine.apply(default_plan)
        first = engine.open_run(run_scope="run:first", store=LocalControlPlaneStore(tmp_path / "first"))
        assert first.destroy().success
        engine.retire_run("run:first")
        assert engine.apply(_plan(engine, "default")).success
        assert engine.destroy().success


def test_delayed_result_stays_with_original_run_and_unknown_effects_block_reuse():
    from dataclasses import replace
    from threading import Event, Thread

    from raes_backend_stubs.stubs import StubProvisioner
    from raes_contracts.planning import ProvisioningPlan
    from raes_contracts.runtime_state import OperationState
    from raes_runtime.operation_supervision_configuration import OperationSupervisionConfiguration

    entered, release = Event(), Event()
    receipts = []

    class Blocked(StubProvisioner):
        def apply(self, plan, snapshot):
            entered.set()
            assert release.wait(4)
            return super().apply(plan, snapshot)

    target = replace(create_stub_target(), provisioner=Blocked())
    engine = RuntimeControlPlane(target, supervision=OperationSupervisionConfiguration(execution_ms=200, drain_ms=1000))
    first = engine.open_run(run_scope="run:first")
    worker = Thread(target=lambda: receipts.append(first.submit_provisioning(ProvisioningPlan(run_id="first"))))
    worker.start()
    try:
        assert entered.wait(1)
        second = engine.open_run(run_scope="run:second")
        before = second.get_snapshot()
        worker.join(2)
        assert not worker.is_alive()
        assert first.get_operation(receipts[0].operation_id).state is OperationState.INDETERMINATE
        with pytest.raises(ConflictError, match="active|unresolved"):
            engine.retire_run("run:first")
        second_request = ProvisioningPlan(run_id="second")
        with pytest.raises(ConflictError, match="reserved"):
            second.submit_provisioning(second_request)
        release.set()
        assert second.get_snapshot() == before
        assert second.get_operation(receipts[0].operation_id) is None
        assert first.get_operation(receipts[0].operation_id).state is OperationState.INDETERMINATE
    finally:
        release.set()
        worker.join(2)
        engine.close()


def test_engine_stop_admission_covers_existing_and_future_run_contexts():
    from raes_contracts.planning import ProvisioningPlan

    with RuntimeControlPlane(create_stub_target()) as engine:
        existing = engine.open_run(run_scope="run:existing")
        engine.stop_admission()
        future = engine.open_run(run_scope="run:future")
        for run in (engine, existing, future):
            receipt = run.submit_provisioning(ProvisioningPlan())
            assert not receipt.accepted
            assert any(item.code == "runtime.control-plane.effect-admission-closed" for item in receipt.diagnostics)
            assert not run.snapshot.entries


def test_retired_run_receipt_replay_does_not_acquire_the_next_runs_resources():
    from raes_contracts.planning import ProvisioningPlan

    with RuntimeControlPlane(create_stub_target()) as engine:
        first = engine.open_run(run_scope="run:first")
        receipt = first.submit_provisioning(ProvisioningPlan(), idempotency_key="original")
        engine.retire_run(first._run_scope)
        second = engine.open_run(run_scope="run:second")
        second.submit_provisioning(ProvisioningPlan())
        assert first.submit_provisioning(ProvisioningPlan(), idempotency_key="original") == receipt
        assert engine._engine._reserved_run is second
        fresh_request = ProvisioningPlan()
        with pytest.raises(ConflictError, match="retired"):
            first.submit_provisioning(fresh_request)


def test_durable_engine_refuses_ephemeral_children_before_recording_an_open(tmp_path):
    from raes_runtime.control_plane_store_local import LocalControlPlaneStore

    with RuntimeControlPlane(create_stub_target(), store=LocalControlPlaneStore(tmp_path)) as engine:
        with pytest.raises(ValueError, match="durable store for each run"):
            engine.open_run(run_scope="run:ephemeral")
        assert not engine._store.load_runtime_decisions()
