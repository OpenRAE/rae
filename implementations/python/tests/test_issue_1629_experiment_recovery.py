"""Authored attempt limits, retry obligations and restart evidence."""

from dataclasses import replace

import pytest
from issue_1629_trial_fixture import TrialServices, factorial_inputs
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import BackendManifestV2Model, TrialExecutionAuthorityModel
from raes_contracts.versions import BACKEND_OPERATION_CONTRACT_IDS
from raes_runtime import RuntimeControlPlane
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.runtime_trial_decisions import TrialAttemptDecision, TrialTerminalDecision


def retry_request(request, policy):
    authority = request.execution_authority.model_dump(mode="json")
    authority["cleanup"]["retry_policy"] = {"max_attempts": 2, "after_effect_policy": policy}
    if policy == "reset":
        authority["cleanup"]["retry_policy"]["reset_obligation_refs"] = ["reset"]
        authority["cleanup"]["cleanup_obligations"]["reset"] = {
            **authority["cleanup"]["cleanup_obligations"]["destroy"],
            "obligation_id": "reset",
            "action_kind": "reset",
            "triggers": ["retry"],
        }
    if policy == "compensate":
        authority["cleanup"]["retry_policy"]["compensation_refs"] = ["restore-state"]
        authority["cleanup"]["cleanup_obligations"]["destroy"]["compensation_refs"] = ["restore-state"]
    key = next(key for key in request.apparatus_manifests if key[0] == "backend")
    payload = request.apparatus_manifests[key].model_dump(mode="json")
    payload["capabilities"]["operation_supervision"] = {
        "name": "installed-test-supervision",
        "guarantees": ["cessation-evidence", "effect-observation"],
    }
    payload["supported_contract_versions"] = sorted(
        set(payload["supported_contract_versions"]) | set(BACKEND_OPERATION_CONTRACT_IDS)
    )
    payload["capabilities"]["cleanup"]["supported_action_kinds"] = ["destroy", "reset"]
    manifest = BackendManifestV2Model.model_validate(payload)
    refs = [
        ref.model_copy(update={"ref_digest": canonical_json_digest(manifest.model_dump(mode="json"))})
        if ref.subject_ref.ref_kind == "backend"
        else ref
        for ref in request.apparatus.manifest_refs
    ]
    return replace(
        request,
        execution_authority=TrialExecutionAuthorityModel.model_validate(authority),
        apparatus=request.apparatus.model_copy(update={"manifest_refs": refs}),
        apparatus_manifests={**request.apparatus_manifests, key: manifest},
    )


@pytest.mark.parametrize("policy", ["disallow", "idempotent", "reset", "compensate"])
def test_author_retry_choice_controls_new_attempts(policy, monkeypatch):
    _, inputs, target = factorial_inputs(lambda request: retry_request(request, policy))
    services = TrialServices(target)
    services.execution_fails = True
    services.idempotent_effects = True
    from issue_1629_provider_fixture import install_command_owner

    install_command_owner(monkeypatch, target.operation_provider)
    with RuntimeControlPlane(target, operation_evidence=target.operation_provider) as engine:
        experiment = engine.admit_experiment(inputs, services=services)
        for _ in range(30):
            progress = engine.advance_experiment(experiment)
            assert progress.state == "progress", progress
            if len(services.observed) >= 2:
                break
        assert len(services.observed) == 2
        first, second = [run_id for run_id, _, _ in services.observed]
        assert (first == second) == (policy != "disallow")
        attempts = [
            item
            for item in engine._store.load_runtime_decisions()
            if isinstance(item, TrialAttemptDecision) and item.run_id == first
        ]
        assert [item.attempt for item in sorted(attempts, key=lambda item: item.attempt)] == (
            [1] if policy == "disallow" else [1, 2]
        )
        assert len({item.execution_attempt_id for item in attempts}) == len(attempts)
        if policy in {"reset", "compensate"}:
            assert [phase for owner, phase in services.events if owner == first][:4] == [
                "configure",
                "capture",
                "cleanup",
                "retry-reset",
            ]
        # Finish the second attempt; a third attempt must not be allocated for
        # this entry even though the backend continues to report failure.
        for _ in range(8):
            engine.advance_experiment(experiment)
            if len(services.observed) > 2:
                break
        assert not any(
            item.attempt > 2
            for item in engine._store.load_runtime_decisions()
            if isinstance(item, TrialAttemptDecision)
        )


def test_restart_reuses_recorded_attempt_and_capture_precedes_cleanup(tmp_path):
    _, inputs, target = factorial_inputs()
    services = TrialServices(target)

    def factory(run_id):
        return LocalControlPlaneStore(tmp_path / "runs" / run_id)

    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path / "engine")) as engine:
        experiment = engine.admit_experiment(inputs, services=services, store_factory=factory)
        first = engine.advance_experiment(experiment)
        assert first.state == "progress"
        assert services.live
        assert len(services.events) == 1
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path / "engine")) as engine:
        assert engine.admit_experiment(inputs, services=services, store_factory=factory) == experiment
        for _ in range(15):
            progress = engine.advance_experiment(experiment)
            terminals = [
                item for item in engine._store.load_runtime_decisions() if isinstance(item, TrialTerminalDecision)
            ]
            if terminals:
                break
        assert len(terminals) == 1
        assert terminals[0].execution_attempt_id == first.execution_attempt_id
        assert terminals[0].receipt.trial_outcome == "succeeded"
        assert [phase for _, phase in services.events] == ["configure", "capture", "cleanup"]
        (result,) = engine.experiment_results(experiment)
        assert result.execution_snapshot.entries
        assert result.cleanup_receipt.cleanup_status == "succeeded"


def test_authored_attempt_allowance_caps_operation_budget_without_limiting_cleanup(monkeypatch):
    from raes_contracts.planning import ProvisioningPlan
    from raes_runtime import operation_policy_admission as policy
    from raes_runtime.operation_supervision_configuration import OperationSupervisionConfiguration

    now = [100.0]
    monkeypatch.setattr(policy, "monotonic", lambda: now[0])
    configuration = OperationSupervisionConfiguration(execution_ms=10000)
    with policy.authored_attempt_budget(102.0):
        assert policy.execution_budget_ms(ProvisioningPlan(), configuration) == 2000
        now[0] = 103.0
        with pytest.raises(ValueError, match="exhausted"):
            policy.execution_budget_ms(ProvisioningPlan(), configuration)
    assert policy.execution_budget_ms(ProvisioningPlan(), configuration) == 10000
