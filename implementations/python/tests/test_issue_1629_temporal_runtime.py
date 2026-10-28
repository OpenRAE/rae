"""Reference-only delivery drives the same admitted runtime decisions."""

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_runtime import RuntimeControlPlane
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from test_runtime_manager import _full_scenario


def worker(target, name="state-worker"):
    return ControlPlaneIdentity(identity=name, roles=frozenset({ControlPlaneRole.BACKEND}), target_name=target)


def test_state_worker_is_scoped_and_repeated_delivery_does_not_repeat_effects():
    target = create_stub_target()
    calls = []
    apply = target.provisioner.apply

    def record(plan, snapshot):
        calls.append(plan)
        return apply(plan, snapshot)

    target.provisioner.apply = record
    with RuntimeControlPlane(target) as engine:
        plan = engine.plan(_full_scenario())
        reference = engine.bind_workflow(
            kind="run",
            scope_id="run:default",
            execution_id="one",
            plan=plan,
            worker_id="state-worker",
            state_queue="runtime-state",
        )
        payload = reference.model_dump_json()
        assert "provisioning" not in payload
        assert "participant_configurations" not in payload
        foreign_worker = worker(target.name, "foreign")
        with pytest.raises(PermissionError):
            engine.advance_workflow(reference, identity=foreign_worker)
        assert not calls
        for _ in range(10):
            state = engine.advance_workflow(reference, identity=worker(target.name))
            if state != "progress":
                break
        assert state == "succeeded"
        assert engine.advance_workflow(reference, identity=worker(target.name)) == "succeeded"
        assert len(calls) == 1
        foreign_reference = reference.model_copy(update={"scope_id": "run:foreign"})
        admitted_worker = worker(target.name)
        with pytest.raises(PermissionError):
            engine.advance_workflow(foreign_reference, identity=admitted_worker)


def test_temporal_workflow_has_single_delivery_attempt_and_preserves_rollover_reference(monkeypatch):
    pytest.importorskip("temporalio")
    import asyncio

    from raes_runtime import runtime_temporal_workflow as module
    from raes_runtime.runtime_sequence_reference import RuntimeSequenceReference

    reference = RuntimeSequenceReference(
        engine_id="sha256:" + "a" * 64,
        kind="run",
        execution_id="one",
        scope_id="run:default",
        request_digest="sha256:" + "b" * 64,
        worker_id="state-worker",
        state_queue="state",
    )
    calls = []

    async def execute(name, payload, **kwargs):
        calls.append((name, payload, kwargs["retry_policy"].maximum_attempts))
        return "progress"

    class RolledOver(Exception):
        pass

    def rollover(payload):
        assert payload == reference.model_dump(mode="json")
        raise RolledOver

    monkeypatch.setattr(module.workflow, "execute_activity", execute)
    monkeypatch.setattr(module.workflow, "continue_as_new", rollover)
    progress = module._drive(reference.model_dump(mode="json"))
    with pytest.raises(RolledOver):
        asyncio.run(progress)
    assert len(calls) == 128
    assert all(name == "raes.runtime.advance" and attempts == 1 for name, _, attempts in calls)


def test_runtime_workflows_are_accepted_by_installed_sdk_sandbox():
    import asyncio

    from raes_runtime.operation_temporal_worker import workflow_sandbox_runner
    from raes_runtime.runtime_temporal_workflow import RaeExperimentWorkflow, RaeRunWorkflow
    from temporalio import workflow

    async def exercise():
        for definition in (RaeRunWorkflow, RaeExperimentWorkflow):
            workflow_sandbox_runner().prepare_workflow(workflow._Definition.must_from_class(definition))

    asyncio.run(exercise())


def test_state_endpoint_requires_the_bound_worker_and_exposes_only_progress():
    from fastapi.testclient import TestClient
    from raes_runtime.control_plane_api import create_control_plane_app
    from raes_runtime.control_plane_security import ControlPlaneSecurityConfig

    target = create_stub_target()
    with RuntimeControlPlane(target) as engine:
        run = engine.open_run(run_scope="run:http")
        reference = engine.bind_workflow(
            kind="run",
            scope_id="run:http",
            execution_id="http",
            plan=run.plan(_full_scenario()),
            worker_id="state-worker",
            state_queue="state",
        )
        security = ControlPlaneSecurityConfig(
            bearer_tokens={"worker": worker(target.name), "foreign": worker(target.name, "foreign")}
        )
        with TestClient(create_control_plane_app(engine, security=security)) as client:
            payload = reference.model_dump(mode="json")
            assert client.post("/runtime/progress", json=payload).status_code == 401
            denied = client.post("/runtime/progress", json=payload, headers={"Authorization": "Bearer foreign"})
            assert denied.status_code == 404
            assert not run.snapshot.entries
            for _ in range(10):
                response = client.post("/runtime/progress", json=payload, headers={"Authorization": "Bearer worker"})
                assert response.status_code == 200, response.text
                if response.json() != "progress":
                    break
            assert response.json() == "succeeded"
            assert run.snapshot.entries
            assert not engine.snapshot.entries
