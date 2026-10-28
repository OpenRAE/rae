"""Existing worker authority routes immutable operations to their run context."""

import pytest
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import OperationState
from raes_runtime import RuntimeControlPlane
from test_issue_1362_distributed_authority import Dispatcher, worker
from test_issue_1362_provider_execution import Evidence, Provider, target


def test_engine_routes_child_worker_grants_without_retargeting_default_state():
    provider, dispatcher = Provider(), Dispatcher()
    with RuntimeControlPlane(
        target(provider), operation_evidence=Evidence(), distributed_execution=dispatcher
    ) as engine:
        run = engine.open_run(run_scope="run:first")
        receipt = run.submit_provisioning(ProvisioningPlan(run_id="first"))
        request = dispatcher.commands[0]
        assert engine.get_backend_invocation(receipt.operation_id, identity=worker()) == request
        with pytest.raises(PermissionError):
            engine.get_backend_invocation(receipt.operation_id, identity=worker("foreign"))
        grant = engine.claim_backend_invocation(
            request.binding, provider.operation_capabilities(), provider.check_operation(request), identity=worker()
        )
        assert grant.request.binding.context.run_scope == "run:first"
        assert run.get_operation(receipt.operation_id).state is OperationState.RUNNING
        assert engine.get_operation(receipt.operation_id) == run.get_operation(receipt.operation_id)
        changed = request.binding.model_copy(
            update={"context": request.binding.context.model_copy(update={"run_scope": "run:other"})}
        )
        with pytest.raises((ValueError, PermissionError)):
            engine.claim_backend_invocation(
                changed, provider.operation_capabilities(), provider.check_operation(request), identity=worker()
            )
        assert not engine.snapshot.entries


@pytest.mark.parametrize("child", [False, True])
def test_public_operation_routing_preserves_keyword_arguments(child):
    provider, dispatcher = Provider(), Dispatcher()
    with RuntimeControlPlane(
        target(provider), operation_evidence=Evidence(), distributed_execution=dispatcher
    ) as engine:
        run = engine.open_run(run_scope="run:keywords") if child else engine
        receipt = run.submit_provisioning(ProvisioningPlan())
        request = engine.get_backend_invocation(operation_id=receipt.operation_id, identity=worker())
        grant = engine.claim_backend_invocation(
            binding=request.binding,
            capabilities=provider.operation_capabilities(),
            admission=provider.check_operation(request),
            identity=worker(),
        )
        assert grant.request == request
        assert engine.get_operation(operation_id=receipt.operation_id).state is OperationState.RUNNING
        response = provider.report(request, {"kind": "acknowledgement", "disposition": "accepted"})
        engine.publish_backend_response(response=response, identity=worker())
        control = engine.cancel_operation(operation_id=receipt.operation_id, control_id="keyword-cancel")
        assert control.binding == request.binding
        assert run._store.load_records()[receipt.operation_id].invocation.responses[-1] == response
