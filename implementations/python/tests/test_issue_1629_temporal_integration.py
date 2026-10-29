"""CI-only shared run/experiment delivery through real Temporal, HTTP and PostgreSQL."""

import asyncio
import os
import socket
from contextlib import ExitStack
from pathlib import Path
from threading import Thread

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["run", "experiment"])
def test_real_sequence_delivery_retains_runtime_authority(kind, tmp_path):
    if os.environ.get("RAES_EXECUTION_INTEGRATION") != "1":
        pytest.skip("requires the hosted runtime-execution integration composition")
    from postgresql_ledger_fixtures import disposable_ledger_database

    with ExitStack() as databases:
        owned = [databases.enter_context(disposable_ledger_database()) for _ in range(3 if kind == "experiment" else 1)]
        asyncio.run(exercise(kind, tmp_path, owned))


async def exercise(kind, tmp_path, databases):
    import uvicorn
    from issue_1629_trial_fixture import TrialServices, factorial_inputs
    from postgresql_ledger_fixtures import ledger_configuration
    from pydantic import SecretStr
    from raes_backend_stubs.stubs import create_stub_target
    from raes_runtime import RuntimeControlPlane
    from raes_runtime.control_plane_api import create_control_plane_app
    from raes_runtime.control_plane_security import ControlPlaneSecurityConfig
    from raes_runtime.control_plane_store_postgresql import PostgreSQLControlPlaneStore
    from raes_runtime.operation_remote_authority import RemoteAuthorityConfiguration, RemoteOperationAuthority
    from raes_runtime.operation_temporal import TemporalExecutionAdapter, TemporalExecutionConfiguration
    from raes_runtime.operation_temporal_worker import workflow_sandbox_runner
    from raes_runtime.runtime_temporal_worker import TemporalRuntimeActivities, create_runtime_state_worker
    from raes_runtime.runtime_temporal_workflow import RaeExperimentWorkflow, RaeRunWorkflow
    from temporalio.client import Client
    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Worker
    from test_issue_1362_distributed_integration import _until
    from test_issue_1629_temporal_runtime import worker
    from test_runtime_manager import _full_scenario

    store = PostgreSQLControlPlaneStore(ledger_configuration(databases[0]))
    await asyncio.to_thread(store.initialize_schema)
    services = None
    if kind == "run":
        target = create_stub_target()
    else:
        from test_issue_1666_factorial_compilation import _with_design

        def two_entries(request):
            payload = request.experiment.model_dump(mode="json")
            payload["factors"] = {"terrain-x": payload["factors"]["terrain-x"]}
            design = payload["factorial_design"]
            design.update(
                factor_ids=["terrain-x"],
                target_runs_per_condition=1,
                level_effects={"terrain-x": design["level_effects"]["terrain-x"]},
            )
            return _with_design(request, payload)

        _, inputs, target = factorial_inputs(two_entries)
    plane = RuntimeControlPlane(target, store=store)
    calls = []
    original = target.provisioner.apply

    def apply(plan, snapshot):
        calls.append(plan)
        return original(plan, snapshot)

    target.provisioner.apply = apply
    if kind == "run":
        reference = plane.bind_workflow(
            kind=kind,
            scope_id="run:default",
            execution_id="ci-run",
            worker_id="state-worker",
            state_queue="state",
            plan=plane.plan(_full_scenario()),
        )
        expected = "succeeded"
    else:
        services = TrialServices(target)
        services.pending = True
        run_stores = {}
        for entry, database in zip(inputs.plan.entries.values(), databases[1:], strict=True):
            run_store = PostgreSQLControlPlaneStore(ledger_configuration(database))
            await asyncio.to_thread(run_store.initialize_schema)
            run_stores[entry.run_id] = run_store
        experiment = plane.admit_experiment(inputs, services=services, store_factory=run_stores.__getitem__)
        reference = plane.bind_workflow(
            kind=kind, scope_id=experiment, execution_id="ci-experiment", worker_id="state-worker", state_queue="state"
        )
        expected = "completed"
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    principal = worker(target.name)
    app = create_control_plane_app(plane, security=ControlPlaneSecurityConfig(bearer_tokens={"test-state": principal}))
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", lifespan="on"))
    thread = Thread(target=lambda: server.run(sockets=[listener]))
    thread.start()
    authority = RemoteOperationAuthority(
        RemoteAuthorityConfiguration(
            base_url=f"http://127.0.0.1:{listener.getsockname()[1]}",
            identity=principal,
            bearer_token=SecretStr("test-state"),
            rpc_budget_ms=45000,
            allow_insecure_loopback=True,
        )
    )
    delivery = None
    try:
        await _until(lambda: server.started)
        cli = Path(os.environ["RAES_TEMPORAL_CLI"]).resolve(strict=True)
        async with await WorkflowEnvironment.start_local(
            dev_server_existing_path=str(cli), dev_server_database_filename=str(tmp_path / "history.sqlite3")
        ) as environment:
            address = environment.client.service_client.config.target_host

            async def connected():
                return await Client.connect(address, namespace="default")

            delivery = TemporalExecutionAdapter(
                TemporalExecutionConfiguration(worker_identity="state-worker", rpc_budget_ms=10000),
                client_factory=connected,
            )
            async with Worker(
                environment.client,
                task_queue=delivery.configuration.workflow_queue,
                workflows=[RaeRunWorkflow, RaeExperimentWorkflow],
                workflow_runner=workflow_sandbox_runner(),
            ):
                activities = TemporalRuntimeActivities(authority)
                async with create_runtime_state_worker(environment.client, state_queue="state", activities=activities):
                    workflow_id = await asyncio.to_thread(delivery.submit_runtime, reference)
                    if services is not None:
                        await _until(lambda: bool(services.live))
                    else:
                        assert (
                            await asyncio.wait_for(environment.client.get_workflow_handle(workflow_id).result(), 45)
                            == expected
                        )
                # Replacing the state worker must continue the same engine-owned
                # attempt. The operation witness and RAE ledger remain intact.
                if services is not None:
                    services.pending = False
                async with create_runtime_state_worker(environment.client, state_queue="state", activities=activities):
                    assert (
                        await asyncio.wait_for(environment.client.get_workflow_handle(workflow_id).result(), 90)
                        == expected
                    )
                    assert await asyncio.to_thread(delivery.submit_runtime, reference) == workflow_id
                    assert await asyncio.to_thread(plane.advance_workflow, reference, identity=principal) == expected
                    assert len(calls) == (1 if kind == "run" else 4)  # provision and native teardown per trial
                    if services is not None:
                        assert len(services.observed) == 2
                        assert [phase for _, phase in services.events].count("configure") == 2
                    retained = plane._store.load_runtime_decisions()
                    assert retained
    finally:
        if delivery is not None:
            await asyncio.to_thread(delivery.close)
        authority.close()
        server.should_exit = True
        await asyncio.to_thread(thread.join, 10)
        listener.close()
        plane.close()
    # The owner process can reopen the committed decisions; engine history is
    # never used as a substitute for the RAE ledger.
    with RuntimeControlPlane(target, store=PostgreSQLControlPlaneStore(ledger_configuration(databases[0]))) as reopened:
        assert reopened._store.load_runtime_decisions() == retained
