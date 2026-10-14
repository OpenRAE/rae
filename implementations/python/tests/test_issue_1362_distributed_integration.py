"""CI-only real Temporal delivery, P2 worker authority and PostgreSQL ledger."""

import asyncio
import os
import socket
from contextlib import AsyncExitStack
from pathlib import Path
from threading import Thread
from time import monotonic

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("phase", ["before-grant", "after-grant", "after-dispatch", "after-terminal"])
def test_actual_process_loss_never_reissues_a_consumed_grant(phase, tmp_path):
    if os.environ.get("RAES_EXECUTION_INTEGRATION") != "1":
        pytest.skip("requires the hosted runtime-execution integration composition")
    import subprocess
    import sys

    import psycopg
    from pydantic import SecretStr
    from raes_backend_stubs.stubs import create_stub_target
    from raes_contracts.planning import ProvisioningPlan
    from raes_contracts.runtime_state import OperationState
    from raes_runtime.control_plane import RuntimeControlPlane
    from raes_runtime.control_plane_store_postgresql import PostgreSQLControlPlaneStore, PostgreSQLStoreConfiguration

    config = PostgreSQLStoreConfiguration(
        host=os.environ["RAES_TEST_PG_HOST"],
        database="rae_ledger",
        user="rae_ledger",
        password=SecretStr("integration-only"),
        sslmode="disable",
    )
    with psycopg.connect(
        host=config.host,
        dbname=config.database,
        user=config.user,
        password=config.password.get_secret_value(),
        autocommit=True,
    ) as cleanup:
        cleanup.execute(
            "DROP TABLE IF EXISTS raes_ledger_audit, raes_ledger_operations, raes_ledger_state, raes_ledger_metadata"
        )
    PostgreSQLControlPlaneStore(config).initialize_schema()
    marker = tmp_path / "effect-witness"
    fixture = Path(__file__).with_name("control_plane_supervision_crash_fixture.py")
    stopped = subprocess.run([sys.executable, str(fixture), phase, str(marker)], timeout=25, capture_output=True)
    assert stopped.returncode == 86
    reopened_target = create_stub_target()
    calls = []
    original_apply = reopened_target.provisioner.apply

    def apply(plan, snapshot):
        calls.append(plan)
        return original_apply(plan, snapshot)

    reopened_target.provisioner.apply = apply
    plane = RuntimeControlPlane(reopened_target, store=PostgreSQLControlPlaneStore(config))
    try:
        (record,) = plane._store.load_records().values()
        expected = (
            OperationState.CANCELLED
            if phase == "before-grant"
            else (OperationState.SUCCEEDED if phase == "after-terminal" else OperationState.INDETERMINATE)
        )
        assert record.status.state is expected
        assert record.invocation.consumed == (phase != "before-grant")
        assert marker.exists() == (phase in {"after-dispatch", "after-terminal"})
        receipt = plane.submit_provisioning(ProvisioningPlan(operation_id="crash-case"), idempotency_key="crash-retry")
        assert receipt == record.receipt
        if record.invocation.reserved:
            with pytest.raises(RuntimeError, match="indeterminate operation requires resolution"):
                plane.submit_provisioning(ProvisioningPlan())
        assert calls == []
        assert plane._store.load_records()[record.receipt.operation_id].invocation == record.invocation
        assert len([event for event in plane._store.read_audit() if event.action.endswith("_terminal")]) == 1
    finally:
        plane.close()


async def _until(predicate, *, timeout=15):
    deadline = monotonic() + timeout
    while not await asyncio.to_thread(predicate):
        if monotonic() >= deadline:
            raise TimeoutError("integration witness did not arrive")
        await asyncio.sleep(0.02)


@pytest.mark.parametrize("blocked", [False, True])
def test_real_delivery_control_and_reopening_preserve_the_consumed_fence(blocked, tmp_path):
    if os.environ.get("RAES_EXECUTION_INTEGRATION") != "1":
        pytest.skip("requires the hosted runtime-execution integration composition")
    asyncio.run(_exercise(blocked, tmp_path))


async def _exercise(blocked, tmp_path):
    import psycopg
    import uvicorn
    from pydantic import SecretStr
    from raes_contracts.planning import ProvisioningPlan
    from raes_contracts.runtime_state import OperationState
    from raes_runtime.control_plane import RuntimeControlPlane
    from raes_runtime.control_plane_api import create_control_plane_app
    from raes_runtime.control_plane_security import ControlPlaneSecurityConfig
    from raes_runtime.control_plane_store_postgresql import PostgreSQLControlPlaneStore, PostgreSQLStoreConfiguration
    from raes_runtime.operation_remote_authority import RemoteAuthorityConfiguration, RemoteOperationAuthority
    from raes_runtime.operation_supervision_configuration import OperationSupervisionConfiguration
    from raes_runtime.operation_temporal import TemporalExecutionAdapter, TemporalExecutionConfiguration
    from raes_runtime.operation_temporal_worker import TemporalOperationActivities, create_temporal_workers
    from temporalio.client import Client
    from temporalio.testing import WorkflowEnvironment
    from test_issue_1362_distributed_authority import worker
    from test_issue_1362_provider_execution import Evidence, Provider, target
    from test_issue_1362_runtime_supervision import supervisor

    config = PostgreSQLStoreConfiguration(
        host=os.environ["RAES_TEST_PG_HOST"],
        database="rae_ledger",
        user="rae_ledger",
        password=SecretStr("integration-only"),
        sslmode="disable",
    )
    # The disposable CI database is reused by these two parametrized cases.
    with psycopg.connect(
        host=config.host,
        dbname=config.database,
        user=config.user,
        password=config.password.get_secret_value(),
        autocommit=True,
    ) as cleanup:
        cleanup.execute(
            "DROP TABLE IF EXISTS raes_ledger_audit, raes_ledger_operations, raes_ledger_state, raes_ledger_metadata"
        )
    store = PostgreSQLControlPlaneStore(config)
    await asyncio.to_thread(store.initialize_schema)
    provider = Provider()
    if blocked:
        provider.release.clear()
    cli = Path(os.environ["RAES_TEMPORAL_CLI"]).resolve(strict=True)
    async with await WorkflowEnvironment.start_local(
        dev_server_existing_path=str(cli), dev_server_database_filename=str(tmp_path / "engine-history.sqlite3")
    ) as engine:
        address = engine.client.service_client.config.target_host

        async def connected():
            return await Client.connect(address, namespace="default")

        delivery = TemporalExecutionAdapter(
            TemporalExecutionConfiguration(worker_identity="worker-1362"), client_factory=connected
        )
        plane = RuntimeControlPlane(
            target(provider),
            store=store,
            operation_evidence=Evidence(),
            distributed_execution=delivery,
            supervision=OperationSupervisionConfiguration(execution_ms=2000 if blocked else 15000),
        )
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        app = create_control_plane_app(
            plane, security=ControlPlaneSecurityConfig(bearer_tokens={"integration-worker": worker()})
        )
        server = uvicorn.Server(uvicorn.Config(app, log_level="critical", lifespan="on"))
        thread = Thread(target=lambda: server.run(sockets=[listener]))
        thread.start()
        authorities = []
        activities = None
        try:
            await _until(lambda: server.started)
            rpc = RemoteAuthorityConfiguration(
                base_url=f"http://127.0.0.1:{listener.getsockname()[1]}",
                identity=worker(),
                bearer_token=SecretStr("integration-worker"),
                allow_insecure_loopback=True,
            )
            authorities = [RemoteOperationAuthority(rpc), RemoteOperationAuthority(rpc)]
            activities = TemporalOperationActivities(
                provider=provider,
                effect_authority=authorities[0],
                control_authority=authorities[1],
                worker_identity="worker-1362",
            )
            async with AsyncExitStack() as workers:
                for installed in create_temporal_workers(engine.client, delivery.configuration, activities):
                    await workers.enter_async_context(installed)
                receipt = await asyncio.to_thread(
                    plane.submit_provisioning, ProvisioningPlan(), idempotency_key="distributed-case"
                )
                assert receipt.accepted
                await _until(provider.started.is_set)
                record = await asyncio.to_thread(lambda: store.load_records()[receipt.operation_id])
                assert record.invocation.consumed and record.invocation.delivery is not None
                if blocked:
                    await asyncio.to_thread(
                        plane.cancel_operation, receipt.operation_id, control_id="cancel-ci", identity=supervisor()
                    )
                    await _until(lambda: provider.cancels == 1)
                    await _until(
                        lambda: plane.get_operation(receipt.operation_id).state is OperationState.INDETERMINATE
                    )
                    assert store.load_records()[receipt.operation_id].invocation.reserved
                    provider.release.set()
                else:
                    await _until(lambda: plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED)
                original = plane.get_operation(receipt.operation_id)
                # Real SDK duplicate workflow delivery retains the original reference.
                assert (
                    await asyncio.to_thread(delivery.submit, record.invocation.request)
                    == record.invocation.delivery.workflow_id
                )
                await activities.invoke(record.invocation.delivery.reference.model_dump(mode="json"))
                assert provider.starts == 1
                assert plane.get_operation(receipt.operation_id) == original
                assert sum(event.action.endswith("_terminal") for event in store.read_audit()) == 1
        finally:
            provider.release.set()
            if activities is not None:
                assert await asyncio.to_thread(activities.close, timeout_ms=3000)
            for authority in authorities:
                assert await asyncio.to_thread(authority.close, timeout_ms=3000)
            server.should_exit = True
            await asyncio.to_thread(thread.join, 5)
            assert not thread.is_alive()
            listener.close()
            await asyncio.to_thread(plane.close)
        # A fresh owner sees retained records, never a recreated dispatch grant.
        reopened = RuntimeControlPlane(
            plane._target,
            store=PostgreSQLControlPlaneStore(config),
            operation_evidence=Evidence(),
            distributed_execution=TemporalExecutionAdapter(delivery.configuration, client_factory=connected),
        )
        try:
            retained = reopened._store.load_records()[receipt.operation_id]
            assert retained.invocation.consumed
            assert retained.status == original
            with pytest.raises(ValueError):
                reopened.claim_backend_invocation(
                    retained.invocation.request.binding,
                    provider.operation_capabilities(),
                    provider.check_operation(retained.invocation.request),
                    identity=worker(),
                )
            assert provider.starts == 1
        finally:
            await asyncio.to_thread(reopened.close)
