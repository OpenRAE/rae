"""Configured reference provider with a substituted daemon; CI owns real-container evidence."""

import hashlib
from dataclasses import replace
from time import monotonic

import pytest
from raes import canonical_instantiated_sdl_digest, instantiate_scenario, parse_sdl
from raes_contracts.associated_artifacts import associated_artifact_set_digest
from raes_contracts.canonical import canonical_json_bytes, canonical_json_digest
from raes_contracts.contracts import (
    AssociatedArtifactManifestModel,
    InjectOrderModel,
    InjectTriggerRequestModel,
    OperationArtifactReferenceModel,
)
from raes_contracts.plan_projection import runtime_plan_digest
from raes_contracts.runtime_state import OperationState
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_reference_backend import create_reference_backend_target
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_profiles import ControlPlaneProfile
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from test_issue_1367_oci_inject_driver import BINDING, CONFIG_DIGEST, IMAGE, NODE, configured
from test_issue_1367_oci_inject_driver import mock_oci_runtime as mock_oci_runtime
from test_issue_1423_inject_occurrence_contracts import ENVIRONMENT_SDL


def source_manifest(scenario, descriptor):
    artifact = {
        "artifact_id": "fixture-source",
        "role": "configuration",
        "media_type": "application/json",
        "uri": "urn:raes:test:source",
        "checksum": {"algorithm": "sha256", "value": hashlib.sha256(descriptor).hexdigest()},
        "size_bytes": len(descriptor),
        "created_at": "2026-10-15T00:00:00Z",
        "source": "operator-admitted-test-source",
        "sensitivity": "public",
    }
    result = AssociatedArtifactManifestModel(
        schema_version="associated-artifact-manifest/v1",
        manifest_id="inject-source",
        manifest_version="1",
        canonicalization_profile="associated-artifact-set/v1",
        scope="scenario",
        parent_ref={"ref_kind": "scenario", "ref_id": scenario.name},
        artifacts={"fixture-source": artifact},
        set_digest="sha256:" + "0" * 64,
    )
    return result.model_copy(update={"set_digest": associated_artifact_set_digest(result)})


def reference_program(native, *, image=IMAGE, image_digest=CONFIG_DIGEST):
    from raes_reference_backend.inject_bindings import OciInjectPermit, OciInjectProbe, OciInjectProgram

    scenario = parse_sdl(
        ENVIRONMENT_SDL.replace(
            "description: Release the staged maintenance notice.", "source: {name: fixture-source, version: '1'}"
        )
    )
    execution_plan = plan(
        compile_runtime_model(scenario), create_reference_backend_target(driver=native.deployment).manifest
    )
    binding = native.binding(BINDING, NODE, deadline=monotonic() + 2)
    request = InjectTriggerRequestModel(
        request_key="oci-trigger-1",
        occurrence_id="oci-occurrence-1",
        target_scope="target:reference-emulation",
        run_scope="run:default",
        plan={
            "contract_id": "orchestration-plan-v1",
            "artifact_id": "oci-plan",
            "digest": runtime_plan_digest(execution_plan.orchestration),
        },
        inject="orchestration.inject.release",
        bindings=(binding,),
        placement={"kind": "independent"},
        expected_head="inject-order:genesis",
    )
    evidence = OperationArtifactReferenceModel(
        contract_id="associated-artifact-manifest-v1",
        artifact_id="ordered-permit",
        digest=canonical_json_digest(request.model_dump(mode="json")),
    )
    descriptor = canonical_json_bytes(
        {"profile": "reference-oci-entrypoint/v1", "image": image, "image_config_digest": image_digest}
    )
    program = OciInjectProgram(
        scenario=scenario,
        scenario_reference=OperationArtifactReferenceModel(
            contract_id="instantiated-scenario-v1",
            artifact_id=scenario.name,
            digest=canonical_instantiated_sdl_digest(instantiate_scenario(scenario)).value,
        ),
        plan=execution_plan.orchestration,
        source_manifest=source_manifest(scenario, descriptor),
        source_descriptor=descriptor,
        probes=(OciInjectProbe(binding=binding, path="/tmp/world-state", before=b"before", after=b"after"),),
        permits=(
            OciInjectPermit(
                request,
                InjectOrderModel(scope=request.run_scope, predecessor=request.expected_head, position=1),
                (evidence,),
            ),
        ),
    )
    return program, execution_plan, request


def test_program_scenario_pin_must_resolve_to_the_admitted_instantiated_content():
    native, _ = configured()
    program, _, _ = reference_program(native)
    with pytest.raises(ValueError, match="scenario"):
        replace(
            program, scenario_reference=program.scenario_reference.model_copy(update={"digest": "sha256:" + "0" * 64})
        )


def test_configured_provider_executes_the_authored_image_and_validates_world_artifact():
    from raes_reference_backend.inject_execution import ReferenceOciInjectExecutor

    native, daemon = configured()
    program, execution_plan, request = reference_program(native)
    executor = ReferenceOciInjectExecutor(native.deployment, programs=(program,), runner=daemon)
    selected = create_reference_backend_target(driver=native.deployment, inject_execution=executor)
    assert selected.operation_provider is executor
    with RuntimeControlPlane(selected, inject_execution=executor, operation_evidence=executor) as plane:
        executor.bind_record_reader(lambda operation_id: plane._store.load_records().get(operation_id))
        plane.register_planner_produced_plan(execution_plan)
        receipt = plane.submit_inject(request)
        assert receipt.accepted
        assert plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
        assert daemon.probe == b"after"
        assert plane.get_inject_outcome(receipt.operation_id).effect == "effect-applied"
        assert (
            plane.get_inject_correlation(receipt.operation_id).result.contract_id == "associated-artifact-manifest-v1"
        )
        assert plane.submit_inject(request) == receipt
        assert len([argv for argv, _ in daemon.calls if argv[1] == "start"]) == 1


def test_failed_entrypoint_retains_the_applied_world_outcome_without_successful_correlation():
    from raes_reference_backend.inject_execution import ReferenceOciInjectExecutor

    native, daemon = configured()
    program, execution_plan, request = reference_program(native)
    daemon.exit_code = 7
    executor = ReferenceOciInjectExecutor(native.deployment, programs=(program,), runner=daemon)
    selected = create_reference_backend_target(driver=native.deployment, inject_execution=executor)
    with RuntimeControlPlane(selected, inject_execution=executor, operation_evidence=executor) as plane:
        executor.bind_record_reader(lambda operation_id: plane._store.load_records().get(operation_id))
        plane.register_planner_produced_plan(execution_plan)
        receipt = plane.submit_inject(request)
        assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED
        assert plane.get_inject_outcome(receipt.operation_id).effect == "effect-applied"
        assert plane.get_inject_correlation(receipt.operation_id) is None
        assert not plane._store.load_records()[receipt.operation_id].invocation.reserved


def test_backend_dispatch_cannot_renew_the_budget_after_admission_wait(monkeypatch):
    import raes_reference_backend.inject_execution as execution

    native, daemon = configured()
    program, execution_plan, request = reference_program(native)
    executor = execution.ReferenceOciInjectExecutor(native.deployment, programs=(program,), runner=daemon)
    selected = create_reference_backend_target(driver=native.deployment, inject_execution=executor)
    start = executor.start_operation
    real_clock = monotonic

    def delayed_dispatch(command):
        monkeypatch.setattr(execution, "monotonic", lambda: real_clock() + 120)
        return start(command)

    executor.start_operation = delayed_dispatch
    with RuntimeControlPlane(selected, inject_execution=executor, operation_evidence=executor) as plane:
        executor.bind_record_reader(lambda operation_id: plane._store.load_records().get(operation_id))
        plane.register_planner_produced_plan(execution_plan)
        receipt = plane.submit_inject(request)
        assert receipt.accepted
        assert plane.get_operation(receipt.operation_id).state is OperationState.INDETERMINATE
        assert daemon.probe == b"before"
        assert not [argv for argv, _ in daemon.calls if argv[1] == "start"]


def test_crash_after_world_effect_before_terminal_commit_reopens_without_redispatch(tmp_path, monkeypatch):
    from raes_reference_backend.inject_execution import ReferenceOciInjectExecutor

    native, daemon = configured()
    program, execution_plan, request = reference_program(native)
    path = tmp_path / "durable-inject-ledger"

    def reopen():
        executor = ReferenceOciInjectExecutor(native.deployment, programs=(program,), runner=daemon)
        selected = create_reference_backend_target(driver=native.deployment, inject_execution=executor)
        plane = RuntimeControlPlane(
            selected,
            inject_execution=executor,
            operation_evidence=executor,
            store=LocalControlPlaneStore(path),
            profile=ControlPlaneProfile.P1,
        )
        executor.bind_record_reader(lambda operation_id: plane._store.load_records().get(operation_id))
        return plane

    plane = reopen()
    plane.register_planner_produced_plan(execution_plan)

    def crash(*args, **kwargs):
        raise KeyboardInterrupt("simulated process loss at the terminal-commit boundary")

    monkeypatch.setattr(plane, "_commit_terminal_operation", crash)
    try:
        with pytest.raises(KeyboardInterrupt):
            plane.submit_inject(request)
        assert daemon.probe == b"after"
        parent = next(iter(plane._store.load_records().values()))
        assert parent.status.state is OperationState.RUNNING
        assert parent.invocation.consumed and parent.invocation.reserved
    finally:
        plane.close()
    with reopen() as recovered:
        assert recovered.get_operation(parent.receipt.operation_id).state is OperationState.INDETERMINATE
        assert recovered.submit_inject(request) == parent.receipt
        assert len([argv for argv, _ in daemon.calls if argv[1] == "start"]) == 1
        control = recovered.supervise_operation(
            parent.receipt.operation_id, action="reconcile", control_id="recover-world"
        )
        response = recovered.get_control_response(parent.receipt.operation_id, control.control_id)
        assert response.message.effects.effect == "complete"
        assert response.message.effects.cessation_established
        assert recovered.get_operation(parent.receipt.operation_id).state is OperationState.INDETERMINATE
        assert recovered.get_inject_correlation(parent.receipt.operation_id) is None


def test_produced_artifact_content_survives_reopen_and_later_world_changes(tmp_path):
    from raes_reference_backend.inject_execution import ReferenceOciInjectExecutor

    native, daemon = configured()
    program, execution_plan, request = reference_program(native)
    path = tmp_path / "artifact-ledger"

    def reopen():
        executor = ReferenceOciInjectExecutor(native.deployment, programs=(program,), runner=daemon)
        selected = create_reference_backend_target(driver=native.deployment, inject_execution=executor)
        plane = RuntimeControlPlane(
            selected,
            inject_execution=executor,
            operation_evidence=executor,
            store=LocalControlPlaneStore(path),
            profile=ControlPlaneProfile.P1,
        )
        executor.bind_record_reader(lambda operation_id: plane._store.load_records().get(operation_id))
        return plane

    with reopen() as plane:
        plane.register_planner_produced_plan(execution_plan)
        receipt = plane.submit_inject(request)
        assert plane.get_inject_artifact(receipt.operation_id, "binding-0-result") == b"after"
        result = plane.get_inject_result(receipt.operation_id)
        assert (
            canonical_json_digest(result.model_dump(mode="json"))
            == plane.get_inject_correlation(receipt.operation_id).result.digest
        )
    daemon.probe = b"a different later world state"
    daemon.effects.clear()
    native_calls = len(daemon.calls)
    with reopen() as restored:
        assert restored.submit_inject(request) == receipt
        assert restored.get_inject_result(receipt.operation_id) == result
        assert restored.get_inject_artifact(receipt.operation_id, "binding-0-result") == b"after"
        assert len(daemon.calls) == native_calls
