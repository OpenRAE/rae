"""Authored supervision requirements survive command admission and delivery."""

from dataclasses import replace

import pytest
from issue_1629_provider_fixture import install_command_owner
from issue_1629_trial_fixture import TrialServices, factorial_inputs
from raes_contracts.errors import ConflictError
from raes_runtime import RuntimeControlPlane
from test_issue_1362_distributed_authority import Dispatcher, worker
from test_issue_1629_experiment_recovery import retry_request


def test_run_guarantees_cannot_bypass_a_missing_operation_provider():
    from raes_backend_stubs.stubs import create_stub_target
    from raes_contracts.planning import ProvisioningPlan

    with RuntimeControlPlane(create_stub_target()) as engine:
        run = engine.open_run(run_scope="run:requires-provider", required_operation_guarantees=("cessation-evidence",))
        request = ProvisioningPlan()
        with pytest.raises(ConflictError, match="installed provider"):
            run.submit_provisioning(request)
        assert not run._store.load_records()


def test_mixed_command_admission_also_preserves_run_guarantees(monkeypatch):
    from mixed_execution_fixtures import portable_plane
    from test_issue_1372_mixed_execution import execute

    engine, _, roles, _, _ = portable_plane(required_operation_guarantees=("cancellation",))
    bridge = roles["bridge"]
    original, checked = bridge.check_operation, []

    def check(request):
        checked.append(request)
        bridge.refuse = "cancellation" in request.required_guarantees
        return original(request)

    monkeypatch.setattr(bridge, "check_operation", check)
    with engine:
        receipt = execute(engine)
        assert checked
        assert all(
            set(request.required_guarantees) == {"cancellation", "effect-observation", "cessation-evidence"}
            for request in checked
        )
        assert not receipt.accepted
        assert bridge.starts == 0


@pytest.mark.parametrize("delivery", ["local", "temporal"])
def test_provider_can_refuse_authored_guarantees_for_the_actual_trial_command(monkeypatch, delivery):
    _, inputs, target = factorial_inputs(lambda request: retry_request(request, "disallow"))
    services, provider = TrialServices(target), target.operation_provider
    install_command_owner(monkeypatch, provider)
    original, checked = provider.check_operation, []

    def check(request):
        checked.append(request)
        # Static support does not imply willingness for this exact command.
        provider.refuse = bool(request.required_guarantees)
        return original(request)

    monkeypatch.setattr(provider, "check_operation", check)
    dispatcher = Dispatcher() if delivery == "temporal" else None
    with RuntimeControlPlane(target, operation_evidence=provider, distributed_execution=dispatcher) as engine:
        experiment = engine.admit_experiment(inputs, services=services)
        engine.advance_experiment(experiment)
        assert checked
        assert all(request.required_guarantees == ("cessation-evidence", "effect-observation") for request in checked)
        assert provider.starts == 0
        assert not services.live
        assert dispatcher is None or not dispatcher.commands


def test_temporal_worker_rechecks_the_same_authored_trial_guarantees(monkeypatch):
    _, inputs, target = factorial_inputs(lambda request: retry_request(request, "disallow"))
    services, provider, dispatcher = TrialServices(target), target.operation_provider, Dispatcher()
    install_command_owner(monkeypatch, provider)
    with RuntimeControlPlane(target, operation_evidence=provider, distributed_execution=dispatcher) as engine:
        experiment = engine.admit_experiment(inputs, services=services)
        engine.advance_experiment(experiment)
        (request,) = dispatcher.commands
        assert request.required_guarantees == ("cessation-evidence", "effect-observation")
        identity = replace(worker(), target_name=target.name)
        assert engine.get_backend_invocation(request.binding.operation_id, identity=identity) == request
        provider.refuse = True
        capabilities, admission = provider.operation_capabilities(), provider.check_operation(request)
        with pytest.raises(ConflictError):
            engine.claim_backend_invocation(request.binding, capabilities, admission, identity=identity)
        run = engine.get_run(request.binding.context.run_scope)
        assert not run._store.load_records()[request.binding.operation_id].invocation.consumed
        assert provider.starts == 0
        assert not services.live
