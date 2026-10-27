"""Durable retry, failure publication, and value-free dispatch regressions."""

from copy import deepcopy
from dataclasses import replace

import pytest
import yaml
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel
from raes_contracts.planning import PlanScope
from raes_contracts.runtime_state import OperationState
from raes_contracts.vocabulary import Closure
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.manager import RuntimeManager
from raes_runtime.operation_command_commitment import native_command_commitment
from test_dsl_437_benign_participant_execution import (
    _autonomous_manifest,
    _NativeParticipantRuntime,
    _scenario_yaml,
)
from test_issue_673_account_credential_bindings import _account_payload, _credential_plan
from test_issue_1067_resolved_realization_authority import _manifest
from test_runtime_manager import _full_scenario


def test_owner_commits_clock_driver_failure_and_reopens_degraded(tmp_path):
    scenario = parse_sdl(_scenario_yaml())
    model = compile_runtime_model(scenario)
    target = replace(
        create_stub_target(), manifest=_autonomous_manifest(model), participant_runtime=_NativeParticipantRuntime()
    )
    path = tmp_path / "ledger"
    with RuntimeManager(target, store=LocalControlPlaneStore(path)) as runtime:
        assert runtime.apply(runtime.plan(scenario)).success
        predecessor = runtime.get_snapshot()
        runtime._participant_clock_driver._record_unexpected_failure(RuntimeError("private backend detail"))
        committed = runtime.get_snapshot()
        services = [
            ParticipantExecutionServiceStateModel.model_validate(payload)
            for payload in committed.snapshot.participant_execution_services.values()
        ]
        assert services
        assert all(service.health == "degraded" and service.readiness == "not_ready" for service in services)
        assert all(not service.accepting_new_work and service.pacing_deviation_refs for service in services)
        assert committed.snapshot.entries == predecessor.snapshot.entries
        assert runtime._store.effect_admission_stopped()
        assert any(
            diagnostic.code == "runtime.participant-clock-driver-failed"
            for record in runtime._store.load_records().values()
            for diagnostic in record.status.diagnostics
        )
    with RuntimeManager(target, store=LocalControlPlaneStore(path)) as runtime:
        assert runtime.get_snapshot() == committed
        assert runtime._store.effect_admission_stopped()


def test_inventory_dispatch_commitment_omits_credentials_but_keeps_private_command_proof():
    commitments = []
    command_proofs = []
    for value in ("first-fixture-input", "second-fixture-input"):
        account = deepcopy(_account_payload())
        account["credential_bindings"][0]["material"]["value"] = value
        request = replace(_credential_plan(account), inventory_refresh=True)
        with RuntimeManager(create_stub_target()) as runtime:
            runtime._interaction_backend_call(
                runtime._target.provisioner.apply,
                request,
                runtime.snapshot,
                address="runtime.inventory-refresh",
                snapshot=runtime.snapshot,
            )
            (record,) = runtime._store.load_records().values()
            commitments.append(record.request_fingerprint)
            command_proofs.append(record.invocation.request.command.digest)
            assert record.request_fingerprint == record.receipt.context.request_commitment
            changed_account = deepcopy(account)
            changed_account["credential_bindings"][0]["material"]["value"] += "-changed"
            changed_request = replace(_credential_plan(changed_account), inventory_refresh=True)
            assert native_command_commitment(runtime, request) == record.invocation.request.command.digest
            assert native_command_commitment(runtime, changed_request) != record.invocation.request.command.digest
    assert commitments[0] == commitments[1]
    assert command_proofs[0] != command_proofs[1]


@pytest.mark.parametrize("closure", [Closure.CLOSED_WORLD, Closure.OPEN_WORLD])
def test_fresh_evaluation_preserves_original_delegated_resolution(tmp_path, closure):
    payload = _full_scenario().model_dump(mode="json", exclude_none=True, exclude_unset=True)
    payload["realization"] = {"default": "unspecified"}
    scenario = parse_sdl(yaml.safe_dump(payload))
    target = create_stub_target()
    authority = _manifest()
    target = replace(
        target,
        manifest=replace(
            target.manifest,
            realization_support=authority.realization_support,
            capabilities=replace(
                target.manifest.capabilities,
                provisioner=replace(
                    target.manifest.provisioner,
                    operating_systems=authority.provisioner.operating_systems,
                    supported_os_families=authority.provisioner.supported_os_families,
                ),
            ),
        ),
    )
    calls = []

    def resolve(requirement, manifest):
        key = (requirement.address, requirement.field_path, requirement.requirement_kind)
        assert key not in calls
        calls.append(key)
        return closure if requirement.requirement_kind == "node-architecture" else Closure.CLOSED_WORLD

    execution = plan(
        compile_runtime_model(scenario),
        target.manifest,
        scope=PlanScope(target_name=target.name),
        apparatus_realization_default=resolve,
    )
    assert execution.is_valid, execution.diagnostics
    original_calls = list(calls)
    path = tmp_path / "ledger"
    with RuntimeManager(target, store=LocalControlPlaneStore(path)) as runtime:
        applied = runtime.apply(execution)
        assert applied.success, [(item.code, item.message) for item in applied.diagnostics]
        receipt = runtime.evaluate(execution, idempotency_key="delegated-evaluation")
        assert runtime.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
        assert runtime.evaluate(idempotency_key="new-evaluation").accepted
    with RuntimeManager(target, store=LocalControlPlaneStore(path)) as runtime:
        assert runtime.evaluate(execution, idempotency_key="delegated-evaluation") == receipt
    assert calls == original_calls
