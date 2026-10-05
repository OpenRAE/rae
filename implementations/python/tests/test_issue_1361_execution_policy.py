"""Authored recovery choices survive the language and public plan boundaries."""

import pytest
from raes import parse_sdl
from raes_backend_stubs.manifest import create_stub_manifest
from raes_contracts.plan_projection import provisioning_plan_model
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan


def test_explicit_never_repeat_survives_plan_projection():
    scenario = parse_sdl("""
name: recovery
nodes:
  host: {type: compute, os: linux}
execution_policy:
  default:
    policy_id: once
    response: terminate
""")
    compiled = compile_runtime_model(scenario)
    execution = plan(compiled, create_stub_manifest())
    operation = provisioning_plan_model(execution.provisioning).operations[0]
    assert operation.execution_policy.policy.policy_id == "once"
    assert operation.execution_policy.policy.retry.max_attempts == 1
    assert operation.execution_policy.governing_scope == "#/"


@pytest.mark.parametrize("response", ["resume", "new-trial", "hold", "reconcile", "continue"])
def test_unsupported_recovery_is_preserved_and_rejected(response):
    trial_limit = "    fresh_trial_limit: 2" if response == "new-trial" else ""
    scenario = parse_sdl(f"""
name: recovery
nodes:
  host: {{type: compute, os: linux}}
evidence_requirements:
  continuity:
    source_class: apparatus
    scope: whole-scenario
    window: execution
    channel: log
    sensitivity: plain
    redaction: none
    integrity: checksum
    retention: run_lifetime
    loss_disclosure: required
execution_policy:
  default:
    policy_id: selected
    response: {response}
    evidence_refs: [continuity]
{trial_limit}
""")
    execution = plan(compile_runtime_model(scenario), create_stub_manifest())
    assert not execution.is_valid
    assert any(d.code.startswith("execution-policy.") for d in execution.diagnostics)
    assert execution.provisioning.operations[0].execution_policy.policy.response == response
    if response in {"hold", "reconcile", "continue"}:
        from dataclasses import replace

        from raes_contracts.execution_policy import ExecutionPolicyCapabilities

        compatible = replace(create_stub_manifest(), execution_policy=ExecutionPolicyCapabilities(responses=[response]))
        supported = plan(compile_runtime_model(scenario), compatible)
        assert not any(d.code.startswith("execution-policy.") for d in supported.diagnostics)


def test_nested_complete_override_and_sibling_isolation():
    from raes_contracts.execution_policy import ExecutionPolicyCapabilities

    manifest = create_stub_manifest()
    from dataclasses import replace

    manifest = replace(manifest, execution_policy=ExecutionPolicyCapabilities(responses=("terminate",)))
    scenario = parse_sdl("""
name: recovery
nodes:
  first: {type: compute, os: linux}
  second: {type: compute, os: linux}
execution_policy:
  default: {policy_id: parent, revision: original, response: terminate, validity: invalidate}
  scopes:
    - scope: /nodes/first
      policy: {policy_id: child, response: terminate}
""")
    execution = plan(compile_runtime_model(scenario), manifest)
    policies = {op.address: op.execution_policy for op in execution.provisioning.operations}
    first = policies["provision.node.first"]
    second = policies["provision.node.second"]
    assert first.policy.policy_id == "child"
    assert first.policy.revision == "1"
    assert first.policy.validity == "preserve"
    assert second.policy.validity == "invalidate"
    assert first.governing_scope == "#/nodes/first"
    assert not any(d.code.startswith("execution-policy.") for d in execution.diagnostics)


def test_policy_round_trip_and_digest_preserve_original_admission():
    from raes_cli.processor import _execution_plan_payload
    from raes_contracts.contracts import ProvisioningPlanModel
    from raes_contracts.plan_projection import provisioning_plan_digest
    from raes_runtime.control_plane_api_models import _provisioning_plan

    scenario = parse_sdl("""
name: recovery
nodes: {host: {type: compute, os: linux}}
execution_policy: {default: {policy_id: once, response: terminate}}
""")
    original = plan(compile_runtime_model(scenario), create_stub_manifest())
    dto = provisioning_plan_model(original.provisioning)
    restored = _provisioning_plan(ProvisioningPlanModel.model_validate_json(dto.model_dump_json()))
    assert provisioning_plan_digest(original.provisioning) == provisioning_plan_digest(restored)
    assert (
        _execution_plan_payload(original)["provisioning"]["operations"][0]["execution_policy"]["policy"]["policy_id"]
        == "once"
    )
    scenario.execution_policy = scenario.execution_policy.model_copy(
        update={"default": scenario.execution_policy.default.model_copy(update={"revision": "2"})}
    )
    changed = plan(compile_runtime_model(scenario), create_stub_manifest())
    assert provisioning_plan_digest(changed.provisioning) != provisioning_plan_digest(restored)
    assert restored.operations[0].execution_policy.policy.revision == "1"


def test_imported_default_is_definition_scoped(tmp_path):
    from raes import parse_sdl_file

    module = tmp_path / "module.yaml"
    module.write_text("""
name: shared
module:
  id: acme/shared
  version: 1.0.0
  exports: {nodes: [host]}
nodes: {host: {type: compute, os: linux}}
execution_policy: {default: {policy_id: imported, response: terminate}}
""")
    root = tmp_path / "root.yaml"
    root.write_text("""
name: recovery
imports: [{source: 'local:module.yaml', namespace: imported}]
nodes: {host: {type: compute, os: linux}}
execution_policy: {default: {policy_id: root, response: terminate}}
""")
    execution = plan(compile_runtime_model(parse_sdl_file(root)), create_stub_manifest())
    policies = {op.address: op.execution_policy for op in execution.provisioning.operations}
    assert policies["provision.node.host"].policy.policy_id == "root"
    imported = policies["provision.node.imported.host"]
    assert imported.policy.policy_id == "imported"
    assert imported.governing_scope == "imported#/"


@pytest.mark.parametrize(
    "policy",
    [
        {"response": "retry"},
        {"response": "terminate", "retry": {"max_attempts": 2, "after_effect_policy": "disallow"}},
        {"response": "resume"},
        {"response": "new-trial", "evidence_refs": ["clean"]},
        {"response": "terminate", "fresh_trial_limit": 2},
        {"response": "terminate", "schema_version": "execution-policy/v9"},
        {
            "response": "retry",
            "retry": {"max_attempts": True, "after_effect_policy": "disallow"},
            "budget_ms": 1000,
            "effect_classes": ["absent"],
            "evidence_refs": ["clean"],
        },
    ],
)
def test_invalid_policy_cannot_enter_sdl(policy):
    import yaml
    from raes import SDLParseError

    payload = {"name": "recovery", "execution_policy": {"default": {"policy_id": "invalid", **policy}}}
    source = yaml.safe_dump(payload)
    with pytest.raises(SDLParseError):
        parse_sdl(source)


def test_dangling_scope_is_rejected_safely():
    from raes import SDLValidationError

    with pytest.raises(SDLValidationError, match="scope does not resolve") as failure:
        parse_sdl("""
name: recovery
execution_policy:
  scopes:
    - scope: /nodes/secret-canary
      policy: {policy_id: once, response: terminate}
""")
    assert "secret-canary" not in str(failure.value)


def test_existing_workflow_retry_is_not_another_workflow_invocation():
    scenario = parse_sdl("""
name: recovery
nodes: {host: {type: compute, os: linux}}
entities: {blue: {role: blue}}
propositions:
  health:
    description: Declared host runtime exists.
    subjects: [nodes.host]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: 'urn:raes:declared-property:runtime', operator: exists}
assertions: {health: {proposition: health, role: postcondition, polarity: positive}}
objectives: {check: {owner: blue, success: {assertions: [health]}}}
workflows:
  check:
    start: try
    steps:
      try: {type: retry, objective: check, max_attempts: 3, on_success: finish}
      finish: {type: end}
execution_policy: {default: {policy_id: one-workflow-invocation, response: terminate}}
""")
    compiled = compile_runtime_model(scenario)
    workflow = compiled.workflows["orchestration.workflow.check"]
    assert workflow.control_steps["try"].max_attempts == 3
    assert compiled.execution_policies[workflow.address][0].policy.retry.max_attempts == 1
    from raes import SDLValidationError
    from raes.evidence_requirements import EvidenceRequirement
    from raes.validator import SemanticValidator
    from raes_contracts.execution_policy import ExecutionPolicyDocument

    scenario.evidence_requirements["clean"] = EvidenceRequirement(
        source_class="apparatus",
        scope="whole-scenario",
        window="execution",
        channel="log",
        sensitivity="plain",
        redaction="none",
        integrity="checksum",
        retention="run_lifetime",
        loss_disclosure="required",
    )
    policy = {
        "policy_id": "repeat",
        "response": "retry",
        "retry": {"max_attempts": 3, "after_effect_policy": "disallow"},
        "budget_ms": 1000,
        "effect_classes": ["absent"],
        "evidence_refs": ["clean"],
    }
    scenario.execution_policy = ExecutionPolicyDocument(default=policy)
    validator = SemanticValidator(scenario)
    with pytest.raises(SDLValidationError, match="cannot multiply"):
        validator.validate()
    scenario.execution_policy = ExecutionPolicyDocument(
        scopes=[{"scope": "/workflows/check/steps/try", "policy": policy}]
    )
    SemanticValidator(scenario).validate()
    scoped = compile_runtime_model(scenario).execution_policies[workflow.address][0]
    assert scoped.retry_unit == "workflow-step"
    assert scoped.policy.retry.max_attempts == 3


def test_scope_order_cannot_change_effective_policy():
    from raes_contracts.execution_policy import ExecutionPolicyDocument, resolve_execution_policy

    rules = [
        {"scope": "/nodes", "policy": {"policy_id": "parent", "response": "terminate"}},
        {"scope": "/nodes/host", "policy": {"policy_id": "child", "response": "terminate"}},
    ]
    first = resolve_execution_policy(ExecutionPolicyDocument(scopes=rules), "/nodes/host")
    second = resolve_execution_policy(ExecutionPolicyDocument(scopes=list(reversed(rules))), "/nodes/host")
    assert first == second


def test_root_semantic_rewrite_preserves_and_rebinds_default_references():
    from raes.composition._execution_policy import rewrite_execution_policy

    payload = {
        "execution_policy": {
            "default": {
                "policy_id": "held",
                "response": "hold",
                "clock_basis": "semantic",
                "clock_ref": "old",
                "evidence_refs": ["proof"],
            }
        }
    }
    rewrite_execution_policy(payload, {"clocks": {"old": "new"}, "evidence_requirements": {"proof": "new-proof"}}, "")
    assert payload["execution_policy"]["default"]["clock_ref"] == "new"
    assert payload["execution_policy"]["default"]["evidence_refs"] == ("new-proof",)


def test_retry_evidence_is_materialized_in_the_native_requirement():
    from dataclasses import replace

    from raes_contracts.execution_policy import ExecutionPolicyCapabilities

    scenario = parse_sdl("""
name: recovery
nodes: {host: {type: compute, os: linux}}
evidence_requirements:
  clean:
    source_class: apparatus
    scope: whole-scenario
    window: execution
    channel: log
    sensitivity: plain
    redaction: none
    integrity: checksum
    retention: run_lifetime
    loss_disclosure: required
execution_policy:
  default:
    policy_id: retry-absent
    response: retry
    retry: {max_attempts: 3, after_effect_policy: disallow}
    budget_ms: 1000
    effect_classes: [absent]
    evidence_refs: [clean]
""")
    manifest = replace(
        create_stub_manifest(), execution_policy=ExecutionPolicyCapabilities(responses=["retry"], max_attempts=3)
    )
    native = plan(compile_runtime_model(scenario), manifest).provisioning
    policy = provisioning_plan_model(native).operations[0].execution_policy
    assert policy.evidence_requirements["clean"].integrity.value == "checksum"
    assert policy.policy.retry.max_attempts == 3
    scenario.execution_policy.default.retry.max_attempts = 100
    assert policy.policy.retry.max_attempts == 3


@pytest.mark.parametrize("scope", ["/nodes/host/os", "/description"])
def test_scope_without_native_execution_owner_is_rejected(scope):
    from raes import SDLValidationError

    with pytest.raises(SDLValidationError, match="no native execution owner"):
        parse_sdl(f"""
name: recovery
nodes: {{host: {{type: compute, os: linux}}}}
execution_policy:
  scopes:
    - scope: {scope}
      policy: {{policy_id: once, response: terminate}}
""")


def test_nonexistent_lexical_namespace_is_rejected():
    from raes import SDLValidationError

    with pytest.raises(SDLValidationError, match="namespace does not resolve"):
        parse_sdl("""
name: recovery
execution_policy:
  scopes:
    - namespace: [missing]
      policy: {policy_id: once, response: terminate}
""")


def test_feature_definition_policy_and_explicit_application_override():
    scenario = parse_sdl("""
name: recovery
features: {setup: {type: configuration}}
nodes:
  host: {type: compute, os: linux, roles: {setup-role: {username: root}}, features: {setup: setup-role}}
execution_policy:
  default: {policy_id: ambient, response: terminate}
  scopes:
    - scope: /features/setup
      policy: {policy_id: definition, response: terminate, validity: invalidate}
""")
    native = plan(compile_runtime_model(scenario), create_stub_manifest()).provisioning
    binding = next(op for op in native.operations if op.resource_type == "feature-binding")
    assert binding.execution_policy.policy.policy_id == "definition"
    from raes_contracts.execution_policy import ExecutionPolicyDocument

    scenario.execution_policy = ExecutionPolicyDocument.model_validate(
        {
            **scenario.execution_policy.model_dump(),
            "scopes": [
                *scenario.execution_policy.scopes,
                {
                    "scope": "/nodes/host/features/setup",
                    "policy": {"policy_id": "application", "response": "terminate"},
                },
            ],
        }
    )
    native = plan(compile_runtime_model(scenario), create_stub_manifest()).provisioning
    binding = next(op for op in native.operations if op.resource_type == "feature-binding")
    assert binding.execution_policy.policy.policy_id == "application"
    assert binding.execution_policy.policy.validity == "preserve"


@pytest.mark.parametrize(
    "posture,refs,expected",
    [
        ("idempotent", {}, ()),
        ("reset", {"reset_obligation_refs": ["cleanup-1"]}, ("cleanup-authority-required",)),
        ("compensate", {"compensation_refs": ["compensation-1"]}, ("cleanup-authority-required",)),
    ],
)
def test_after_effect_retry_requires_installed_support_and_owning_authority(posture, refs, expected):
    from raes_contracts.execution_policy import (
        ExecutionPolicy,
        ExecutionPolicyCapabilities,
        execution_policy_capability_gaps,
    )

    policy = ExecutionPolicy(
        policy_id="repeat",
        response="retry",
        retry={"max_attempts": 3, "after_effect_policy": posture, **refs},
        budget_ms=1000,
        effect_classes=["partial"],
        evidence_refs=["clean"],
    )
    support = ExecutionPolicyCapabilities(responses=["retry"], max_attempts=3, after_effect_policies=[posture])
    assert execution_policy_capability_gaps(policy, support) == expected
    if not expected:
        assert execution_policy_capability_gaps(policy, support.model_copy(update={"max_attempts": 2})) == (
            "retry-unsupported",
        )


def test_policy_does_not_erase_an_intentional_fault_or_allocate_a_trial():
    from raes_contracts.execution_policy import (
        ExecutionPolicy,
        ExecutionPolicyCapabilities,
        execution_policy_capability_gaps,
    )

    policy = ExecutionPolicy(
        policy_id="fresh",
        response="retry",
        failure_classes=["intentional-fault"],
        validity="invalidate",
        retry={"max_attempts": 2, "after_effect_policy": "disallow"},
        budget_ms=1000,
        effect_classes=["absent"],
        evidence_refs=["clean"],
        on_exhausted="new-trial",
        fresh_trial_limit=4,
    )
    assert policy.retry.max_attempts == 2
    assert policy.fresh_trial_limit == 4
    assert policy.failure_classes == ("intentional-fault",)
    assert policy.validity == "invalidate"
    assert execution_policy_capability_gaps(
        policy, ExecutionPolicyCapabilities(responses=["retry", "new-trial"], max_attempts=2)
    ) == ("trial-allocation-authority-required",)


def test_effective_scope_provenance_and_native_duplicate_scopes_fail_closed():
    from pydantic import ValidationError
    from raes_contracts.contracts import PlanOperationModel
    from raes_contracts.execution_policy import EffectiveExecutionPolicy

    effective = EffectiveExecutionPolicy(
        scope="/nodes/host", governing_scope="#/nodes", policy={"policy_id": "once", "response": "terminate"}
    )
    foreign = {**effective.model_dump(), "governing_scope": "#/workflows"}
    with pytest.raises(ValidationError, match="governing scope"):
        EffectiveExecutionPolicy.model_validate(foreign)
    with pytest.raises(ValidationError, match="scopes must be unique"):
        PlanOperationModel(
            action="create",
            address="provision.node.host",
            resource_type="node",
            execution_policy=effective,
            execution_policy_scopes=[effective],
        )
