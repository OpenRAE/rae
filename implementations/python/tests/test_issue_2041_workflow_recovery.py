"""Interruption preserves the original workflow dispatch and outcome facts."""

from __future__ import annotations

from dataclasses import replace

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.manager import RuntimeManager
from test_issue_2041_runtime_step_dispatch import StepBackend, scenario


@pytest.mark.parametrize("boundary", ["install-commit", "before-effect", "after-response"])
def test_restart_resumes_the_original_step_without_repeating_effects(tmp_path, monkeypatch, boundary):
    backend = StepBackend()
    target = replace(create_stub_target(), orchestrator=backend)
    path = tmp_path / "ledger"
    with RuntimeManager(target, store=LocalControlPlaneStore(path)) as first:
        original = first._workflow_ports
        interrupted = False

        def ports(identity):
            bound = original(identity)

            def commit(snapshot, record):
                nonlocal interrupted
                if boundary == "install-commit" and not interrupted:
                    interrupted = True
                    raise RuntimeError("interrupted before checkpoint commit")
                return bound.commit(snapshot, record)

            def execute(request):
                nonlocal interrupted
                if boundary == "before-effect" and not interrupted:
                    interrupted = True
                    raise RuntimeError("interrupted before effect")
                result = bound.execute(request)
                if boundary == "after-response" and not interrupted:
                    interrupted = True
                    raise RuntimeError("interrupted after response commit")
                return result

            return replace(bound, commit=commit, execute=execute)

        monkeypatch.setattr(first, "_workflow_ports", ports)
        execution = first.plan(
            scenario("      run: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n")
        )
        with pytest.raises(RuntimeError, match="interrupted"):
            first.apply(execution)
        roots = [
            record
            for record in first._store.load_records().values()
            if record.workflow is not None and record.workflow.kind == "root"
        ]
        assert len(roots) == 1
        root_id = roots[0].receipt.operation_id
        before = len(backend.dispatches)
        assert before == (1 if boundary == "after-response" else 0)

    with RuntimeManager(target, store=LocalControlPlaneStore(path)) as restored:
        restored.advance_orchestration(root_id)
        assert restored.get_operation(root_id).state is OperationState.SUCCEEDED
        assert [request.step_name for request in backend.dispatches] == ["run", "finish"]
        events = restored.snapshot.orchestration_history["orchestration.workflow.response"]
        assert len([event for event in events if event["event_type"] == "step_started"]) == 2
        assert len([event for event in events if event["event_type"] == "step_reported"]) == 2


def test_restart_does_not_redispatch_an_uncertain_effect(tmp_path):
    class LostResponse(StepBackend):
        def dispatch_step(self, request):
            super().dispatch_step(request)
            raise RuntimeError("native response was lost")

    backend = LostResponse()
    target = replace(create_stub_target(), orchestrator=backend)
    path = tmp_path / "uncertain"
    with RuntimeManager(target, store=LocalControlPlaneStore(path)) as first:
        result = first.apply(
            first.plan(
                scenario(
                    "      run: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n"
                )
            )
        )
        assert not result.success
        root_id = next(
            record.receipt.operation_id
            for record in first._store.load_records().values()
            if record.workflow is not None and record.workflow.kind == "root"
        )

    with RuntimeManager(target, store=LocalControlPlaneStore(path)) as restored:
        restored.advance_orchestration(root_id)
        assert [request.step_name for request in backend.dispatches] == ["run"]
        effects = [
            record
            for record in restored._store.load_records().values()
            if record.invocation is not None and record.invocation.request.workflow_step is not None
        ]
        assert len(effects) == 1
        assert effects[0].status.state is OperationState.INDETERMINATE
        assert effects[0].invocation.reserved
        from raes_runtime.runtime_module_step import phase_states

        root = restored._store.load_records()[root_id]
        assert phase_states(restored, (root,)) == {OperationState.INDETERMINATE}


def test_checkpoint_cannot_overwrite_cancellation_at_a_new_revision(monkeypatch):
    from raes_contracts.errors import ConflictError

    backend = StepBackend()
    with RuntimeManager(replace(create_stub_target(), orchestrator=backend)) as owner:
        original = owner._workflow_ports
        cancelled = False

        def ports(identity):
            bound = original(identity)

            def claim(record):
                nonlocal cancelled
                claimed = bound.claim(record)
                if (
                    not cancelled
                    and record.workflow is not None
                    and record.workflow.kind == "checkpoint"
                    and record.workflow.continuation.outstanding is not None
                ):
                    cancelled = True
                    owner.cancel_workflow("orchestration.workflow.response", idempotency_key="checkpoint-race")
                return claimed

            return replace(bound, claim=claim)

        monkeypatch.setattr(owner, "_workflow_ports", ports)
        source = scenario(
            "      run: {type: objective, objective: check, on_success: finish}\n      finish: {type: end}\n"
        )
        with pytest.raises(ConflictError, match="predecessor changed"):
            owner.apply(owner.plan(source))
        assert backend.dispatches == []
        assert owner.snapshot.orchestration_results["orchestration.workflow.response"]["workflow_status"] == "cancelled"
        root = next(
            record
            for record in owner._store.load_records().values()
            if record.workflow is not None and record.workflow.kind == "root"
        )
        owner.advance_orchestration(root.receipt.operation_id)
        assert owner.get_operation(root.receipt.operation_id).state is OperationState.CANCELLED
        assert backend.dispatches == []
