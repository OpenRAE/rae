"""Native execution-policy capability and exact-context admission regressions."""

import pytest
from raes import parse_sdl
from raes_backend_stubs.manifest import create_stub_manifest
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan


def test_capability_manifest_and_native_operation_checks_preserve_policy():
    from dataclasses import replace

    from raes_backend_protocols.manifest import backend_manifest_from_v2_model, backend_manifest_v2_model
    from raes_contracts.execution_policy import ExecutionPolicyCapabilities
    from raes_contracts.planning import ChangeAction, ProvisionOp

    capabilities = ExecutionPolicyCapabilities(responses=["terminate"])
    manifest = replace(create_stub_manifest(), execution_policy=capabilities)
    assert backend_manifest_from_v2_model(backend_manifest_v2_model(manifest)).execution_policy == capabilities
    with pytest.raises(TypeError, match="execution policy"):
        ProvisionOp(
            action=ChangeAction.CREATE,
            address="provision.node.host",
            resource_type="node",
            payload={},
            execution_policy={"response": "terminate"},
        )


def test_exact_native_policy_and_contextual_willingness_are_both_required():
    from dataclasses import replace

    from raes_contracts import contracts
    from raes_contracts.contracts.backend_operation_validation import require_backend_execution_policy_admission
    from raes_contracts.execution_policy import ExecutionPolicyCapabilities
    from raes_contracts.plan_projection import runtime_plan_digest
    from test_issue_1360_backend_operations import capabilities, request_payload, response

    scenario = parse_sdl("""
name: recovery
nodes: {host: {type: compute, os: linux}}
execution_policy: {default: {policy_id: once, response: terminate}}
""")
    support = ExecutionPolicyCapabilities(responses=["terminate"])
    manifest = replace(create_stub_manifest(), execution_policy=support)
    native = replace(plan(compile_runtime_model(scenario), manifest).provisioning, operation_id="operation-1")
    payload = request_payload()
    payload["command"] = {
        "contract_id": "provisioning-plan-v1",
        "artifact_id": "operation-1",
        "digest": runtime_plan_digest(native),
    }
    request = contracts.BackendOperationRequestModel.model_validate(payload)
    declared = contracts.BackendOperationCapabilitiesModel.model_validate(
        {**capabilities().model_dump(), "execution_policy": support}
    )
    willing = response(
        {
            "kind": "admission",
            "disposition": "willing",
            "capability_digest": contracts.canonical_backend_operation_capabilities_digest(declared),
        },
        operation=request,
    )
    require_backend_execution_policy_admission(request, declared, willing, native)
    refused = response(
        {
            "kind": "admission",
            "disposition": "refused",
            "reason": "context-refused",
            "capability_digest": contracts.canonical_backend_operation_capabilities_digest(declared),
        },
        operation=request,
    )
    with pytest.raises(ValueError, match="refused"):
        require_backend_execution_policy_admission(request, declared, refused, native)
    changed = replace(
        native,
        operations=[
            replace(
                native.operations[0],
                execution_policy=native.operations[0].execution_policy.model_copy(
                    update={"policy": native.operations[0].execution_policy.policy.model_copy(update={"revision": "2"})}
                ),
            )
        ],
    )
    with pytest.raises(ValueError, match="commitment"):
        require_backend_execution_policy_admission(request, declared, willing, changed)
    foreign_run = replace(native, run_id="foreign")
    foreign_request = contracts.BackendOperationRequestModel.model_validate(
        {
            **payload,
            "command": {**payload["command"], "digest": runtime_plan_digest(foreign_run)},
        }
    )
    foreign_willing = response(willing.message, operation=foreign_request)
    with pytest.raises(ValueError, match="run scope"):
        require_backend_execution_policy_admission(foreign_request, declared, foreign_willing, foreign_run)


def test_preparation_admission_preserves_primary_and_scoped_policies():
    from dataclasses import replace

    from raes_backend_protocols.manifest import backend_manifest_v2_model
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.execution_policy import EffectiveExecutionPolicy, ExecutionPolicyCapabilities
    from raes_contracts.realization_preparation import RealizationPreparationAuthority
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
    from test_issue_1204_backend_preparation import _PreparingBackend, _request

    native, manifest = _request()
    manifest = replace(manifest, execution_policy=ExecutionPolicyCapabilities(responses=["terminate"]))
    primary = EffectiveExecutionPolicy(
        scope="/nodes/host", governing_scope="#/", policy={"policy_id": "once", "response": "terminate"}
    )
    scoped = EffectiveExecutionPolicy(
        scope="/nodes/host/features",
        governing_scope="#/nodes/host",
        policy={"policy_id": "child", "response": "terminate"},
    )
    native = replace(
        native,
        operations=[replace(native.operations[0], execution_policy=primary, execution_policy_scopes=(scoped,))],
        preparation=RealizationPreparationAuthority(
            manifest_digest=canonical_json_digest(backend_manifest_v2_model(manifest).model_dump(mode="json"))
        ),
    )
    seen = []

    class PolicyBackend(_PreparingBackend):
        def apply(self, selected, snapshot):
            seen.append((selected.operations[0].execution_policy, selected.operations[0].execution_policy_scopes))
            return super().apply(selected, snapshot)

    backend = PolicyBackend()
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        backend.apply,
        native,
        previous,
        snapshot=previous,
        address="runtime.policy-preparation",
        realization=_RealizationApplyContext(plan=native, manifest=manifest),
    )
    assert result.success, result.diagnostics
    assert (backend.prepares, backend.applies) == (1, 1)
    assert seen == [(primary, (scoped,))]
