"""Planner tests for the SDL-native runtime layer."""

from __future__ import annotations

import textwrap
from dataclasses import replace

import pytest
from paths import EXAMPLES_DIR
from raes import SDLInstantiationError, parse_sdl
from raes_backend_protocols.capabilities import (
    BackendManifest,
    EvaluatorCapabilities,
    ObservationCaptureOffer,
    OperatingSystemCompatibility,
    OrchestratorCapabilities,
    ProvisionerCapabilities,
    WorkflowFeature,
    WorkflowStatePredicateFeature,
)
from raes_backend_stubs.stubs import create_stub_manifest
from raes_contracts.apparatus import (
    ConceptBinding,
    RealizationObservationCapability,
    RealizationSupportDeclaration,
)
from raes_contracts.vocabulary import (
    ObservationStrength,
    RealizationSupportMode,
    RealizationVerificationScope,
)
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import RuntimeDomain, RuntimeSnapshot, SnapshotEntry
from raes_processor.planner import plan


def _scenario(yaml_str: str):
    return parse_sdl(textwrap.dedent(yaml_str))


def _snapshot_from_plan(execution_plan) -> RuntimeSnapshot:
    entries: dict[str, SnapshotEntry] = {}
    for domain, operations in (
        (RuntimeDomain.PROVISIONING, execution_plan.provisioning.operations),
        (RuntimeDomain.ORCHESTRATION, execution_plan.orchestration.operations),
        (RuntimeDomain.EVALUATION, execution_plan.evaluation.operations),
    ):
        for op in operations:
            if op.action.value == "delete":
                continue
            entries[op.address] = SnapshotEntry(
                address=op.address,
                domain=domain,
                resource_type=op.resource_type,
                payload=op.payload,
                ordering_dependencies=op.ordering_dependencies,
                refresh_dependencies=op.refresh_dependencies,
                status="snapshot",
            )
    return RuntimeSnapshot(entries=entries)


def _plan_with_snapshot(yaml_str: str, snapshot: RuntimeSnapshot):
    return plan(compile_runtime_model(_scenario(yaml_str)), create_stub_manifest(), snapshot)


def _limited_backend_manifest(
    *,
    name: str = "limited",
    provisioner: ProvisionerCapabilities,
    orchestrator: OrchestratorCapabilities | None = None,
    evaluator: EvaluatorCapabilities | None = None,
) -> BackendManifest:
    return BackendManifest(
        name=name,
        version="0.0.1",
        supported_contract_versions=frozenset({"backend-manifest-v2"}),
        compatible_processors=frozenset({"raes-reference-processor"}),
        # The manifest is limited in provisioner capability, not realization
        # support: it declares full SEM-218 realization support so the
        # realization gate is a no-op and these tests isolate the provisioner
        # capability checks they target.
        realization_support=(
            RealizationSupportDeclaration(
                domain="runtime-realization",
                support_mode=RealizationSupportMode.CONSTRAINED,
                supported_constraint_kinds=frozenset(
                    {
                        "node-type",
                        "os-family",
                        "content-type",
                        "account-feature",
                        "workflow-feature",
                        "workflow-state-predicate",
                    }
                ),
                supported_exact_requirement_kinds=frozenset({"declared-capability-match"}),
                disclosure_kinds=frozenset({"runtime-snapshot-v1"}),
                observation_capabilities={
                    "operating-system": RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.PRESENCE,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                    )
                },
            ),
        ),
        concept_bindings=(ConceptBinding(scope="capabilities.provisioner.supported_node_types", family="assets"),),
        provisioner=replace(
            provisioner,
            operating_systems=tuple(
                OperatingSystemCompatibility(family, distribution, frozenset({version}))
                for family, distribution, version in (
                    ("linux", "ubuntu", "22.04"),
                    ("windows", "windows-server", "2022"),
                    ("other", "solaris", "11.4"),
                )
                if family in provisioner.supported_os_families
            ),
        ),
        orchestrator=orchestrator,
        evaluator=evaluator,
    )


def _os_capable_stub_manifest() -> BackendManifest:
    base = create_stub_manifest()
    assert base.observation is not None
    observation = replace(
        base.observation,
        capture_offers=(
            ObservationCaptureOffer(
                offer_id="satcom-objective-truth-evidence",
                offer_version="1.0.0",
                output_contract="experiment-evidence-record-v1",
                field_selectors=("",),
                artifact_roles=frozenset({"proposition_truth_evidence"}),
                media_types=frozenset({"application/json"}),
                capture_kind="log",
                source_classes=frozenset({"sdl-evidence-requirement"}),
                source_refs=frozenset(
                    {
                        "nodes.customer-portal",
                        "nodes.ci-runner",
                        "nodes.telemetry-broker",
                        "nodes.artifact-registry",
                        "nodes.edge-gateway-east",
                    }
                ),
                scopes=frozenset({"authored objective, event, workflow, and participant assertion evaluation"}),
                channel_kinds=frozenset({"backend-log"}),
                channel_refs=frozenset(),
                window_kinds=frozenset({"assertion_evaluation"}),
                integrity_modes=frozenset({"checksum"}),
                sensitivity="plain",
                availability="available",
                fidelity="complete",
                disclosure="redacted",
                redaction_policy="redact_secrets",
                retention_policy_refs=frozenset({"study_lifetime"}),
                export_policy="not-required",
            ),
        ),
    )
    limited = _limited_backend_manifest(
        name="os-capable-stub",
        provisioner=base.provisioner,
        orchestrator=base.orchestrator,
        evaluator=base.evaluator,
    )
    return replace(
        limited,
        supported_contract_versions=(
            limited.supported_contract_versions
            | observation.supported_evidence_contracts
            | frozenset(offer.output_contract for offer in observation.capture_offers)
        ),
        capabilities=replace(limited.capabilities, observation=observation),
    )


class TestRuntimePlanner:
    def test_plan_records_provenance(self):
        snapshot = RuntimeSnapshot(metadata={"seed": "planner"})
        manifest = create_stub_manifest()

        execution_plan = plan(
            compile_runtime_model(
                _scenario("""
name: provenance
nodes:
  vm: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
""")
            ),
            manifest,
            snapshot,
            target_name="custom-target",
        )

        assert execution_plan.target_name == "custom-target"
        assert execution_plan.manifest == manifest
        assert execution_plan.base_snapshot == snapshot

    def test_direct_plan_is_unbound_by_default(self):
        execution_plan = plan(
            compile_runtime_model(
                _scenario("""
name: provenance
nodes:
  vm: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
""")
            ),
            create_stub_manifest(),
        )

        assert execution_plan.target_name is None

    def test_planned_payload_excludes_runtime_envelope_fields(self):
        execution_plan = plan(
            compile_runtime_model(
                _scenario("""
name: payload-shape
nodes:
  vm: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
""")
            ),
            create_stub_manifest(),
        )

        payload = execution_plan.provisioning.operations[0].payload

        assert payload["name"] == "vm"
        assert payload["os_family"] == "linux"
        assert "address" not in payload
        assert "ordering_dependencies" not in payload
        assert "refresh_dependencies" not in payload

    def test_delete_operations_emitted_for_removed_resources(self):
        old_model = compile_runtime_model(
            _scenario("""
name: original
nodes:
  vm1: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
  vm2: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
""")
        )
        old_plan = plan(old_model, create_stub_manifest())
        snapshot = _snapshot_from_plan(old_plan)

        new_model = compile_runtime_model(
            _scenario("""
name: original
nodes:
  vm1: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
""")
        )
        new_plan = plan(new_model, create_stub_manifest(), snapshot)

        delete_ops = {
            op.address: op.action.value for op in new_plan.provisioning.operations if op.action.value == "delete"
        }
        assert delete_ops == {"provision.node.vm2": "delete"}

    def test_cyclic_provisioning_dependencies_fail_closed(self):
        execution_plan = plan(
            compile_runtime_model(
                parse_sdl(
                    textwrap.dedent("""
name: provisioning-cycle
nodes:
  a: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
  b: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
infrastructure:
  a: {dependencies: [b]}
  b: {dependencies: [a]}
"""),
                    skip_semantic_validation=True,
                )
            ),
            create_stub_manifest(),
        )

        diagnostics = {(diag.code, diag.address) for diag in execution_plan.diagnostics}

        assert ("provisioning.ordering-cycle", "provision.node.a") in diagnostics
        assert not execution_plan.is_valid

    def test_compiler_admission_rejects_cyclic_objective_dependencies(self):
        scenario = parse_sdl(
            textwrap.dedent("""
name: objective-cycle
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  first:
    entity: blue
    success: {assertions: [health]}
    depends_on: [second]
  second:
    entity: blue
    success: {assertions: [health]}
    depends_on: [first]
"""),
            skip_semantic_validation=True,
        )

        with pytest.raises(SDLInstantiationError, match="Objective dependency graph contains a cycle"):
            compile_runtime_model(scenario)

    def test_dependency_changes_propagate_through_evaluation_graph(self):
        old_model = compile_runtime_model(
            _scenario("""
name: original
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  initial:
    entity: blue
    success: {assertions: [health]}
""")
        )
        old_plan = plan(old_model, create_stub_manifest())
        snapshot = _snapshot_from_plan(old_plan)

        new_plan = _plan_with_snapshot(
            """
name: original
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/false, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime-v2, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  initial:
    entity: blue
    success: {assertions: [health]}
""",
            snapshot,
        )

        eval_actions = {op.address: op.action.value for op in new_plan.evaluation.operations}
        assert eval_actions["evaluation.condition.vm.health"] == "update"
        # The condition and proposition changed independently. The objective
        # refresh follows the proposition/assertion dependency chain.
        assert eval_actions["evaluation.objective.initial"] == "update"

    def test_assertion_refs_remain_unambiguous_with_multiple_condition_bindings(self):
        execution_plan = plan(
            compile_runtime_model(
                _scenario("""
name: ambiguous
nodes:
  a:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
  b:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [nodes.a]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
events:
  kickoff: {assertions: [pre-health]}
""")
            ),
            create_stub_manifest(),
        )

        kickoff = execution_plan.model.events["orchestration.event.kickoff"]
        assert kickoff.assertion_addresses == ("evaluation.assertion.pre-health",)
        assert execution_plan.is_valid

    def test_top_level_inject_refs_resolve_directly(self):
        execution_plan = plan(
            compile_runtime_model(
                _scenario("""
name: injects
nodes:
  web:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
injects:
  mail: {source: inbox}
events:
  kickoff: {injects: [mail]}
""")
            ),
            create_stub_manifest(),
        )

        kickoff = execution_plan.model.events["orchestration.event.kickoff"]
        assert kickoff.inject_addresses == ("orchestration.inject.mail",)
        assert execution_plan.is_valid

    def test_compiler_admission_rejects_unbound_inject_refs(self):
        scenario = _scenario("""
name: unbound
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
injects:
  mail: {source: inbox}
entities:
  blue: {role: blue}
objectives:
  check:
    entity: blue
    success: {assertions: [health]}
events:
  kickoff: {assertions: [pre-health], injects: [mail]}
""")
        scenario.injects = {}

        with pytest.raises(SDLInstantiationError, match="references undefined inject 'mail'"):
            compile_runtime_model(scenario)

    @pytest.mark.parametrize(
        ("orchestrator_kwargs", "scenario_yaml", "expected_code"),
        [
            pytest.param(
                {
                    "supported_sections": frozenset({"workflows"}),
                    "supports_workflows": True,
                    "supports_assertion_refs": False,
                    "supported_workflow_features": frozenset({WorkflowFeature.DECISION}),
                },
                """
name: workflows
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
workflows:
  flow:
    start: branch
    steps:
      branch:
        type: decision
        when: {assertions: [pre-health]}
        then: finish
        else: finish
      finish: {type: end}
""",
                "orchestrator.assertion-refs-unsupported",
                id="assertion-refs-unsupported",
            ),
            pytest.param(
                {
                    "supported_sections": frozenset({"workflows"}),
                    "supports_workflows": True,
                    "supported_workflow_features": frozenset({WorkflowFeature.DECISION}),
                },
                """
name: workflows
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
entities:
  blue: {role: blue}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
objectives:
  defend:
    entity: blue
    success: {assertions: [health]}
workflows:
  flow:
    start: attempt
    steps:
      attempt:
        type: retry
        objective: defend
        on_success: finish
        max_attempts: 3
      finish: {type: end}
""",
                "orchestrator.workflow-feature-unsupported",
                id="workflow-feature-unsupported",
            ),
            pytest.param(
                {
                    "supported_sections": frozenset({"workflows"}),
                    "supports_workflows": True,
                    "supported_workflow_features": frozenset({WorkflowFeature.DECISION}),
                    "supported_workflow_state_predicates": frozenset(),
                },
                """
name: workflows
entities:
  blue: {role: blue}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [entities.blue]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
objectives:
  defend:
    entity: blue
    success: {assertions: [health]}
workflows:
  flow:
    start: validate
    steps:
      validate:
        type: objective
        objective: defend
        on_success: branch
      branch:
        type: decision
        when:
          steps:
            - step: validate
              outcomes: [succeeded]
        then: finish
        else: finish
      finish: {type: end}
""",
                "orchestrator.step-state-predicate-feature-unsupported",
                id="step-state-predicates-unsupported",
            ),
            pytest.param(
                {
                    "supported_sections": frozenset({"workflows"}),
                    "supports_workflows": True,
                    "supported_workflow_features": frozenset({WorkflowFeature.DECISION}),
                    "supported_workflow_state_predicates": frozenset({WorkflowStatePredicateFeature.OUTCOME_MATCHING}),
                },
                """
name: workflows
entities:
  blue: {role: blue}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [entities.blue]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
objectives:
  defend:
    entity: blue
    success: {assertions: [health]}
workflows:
  flow:
    start: validate
    steps:
      validate:
        type: retry
        objective: defend
        on_success: branch
        max_attempts: 3
      branch:
        type: decision
        when:
          steps:
            - step: validate
              outcomes: [succeeded]
              min_attempts: 2
        then: finish
        else: finish
      finish: {type: end}
""",
                "orchestrator.step-state-predicate-feature-unsupported",
                id="attempt-count-predicates-unsupported",
            ),
            pytest.param(
                {
                    "supported_sections": frozenset({"workflows"}),
                    "supports_workflows": True,
                    "supported_workflow_features": frozenset({WorkflowFeature.DECISION}),
                },
                """
name: workflows
entities:
  blue: {role: blue}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [entities.blue]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
objectives:
  left:
    entity: blue
    success: {assertions: [health]}
  right:
    entity: blue
    success: {assertions: [health]}
workflows:
  flow:
    start: fanout
    steps:
      fanout:
        type: parallel
        branches: [left-branch, right-branch]
        join: joined
      left-branch:
        type: objective
        objective: left
        on_success: joined
      right-branch:
        type: objective
        objective: right
        on_success: joined
      joined:
        type: join
        next: finish
      finish: {type: end}
""",
                "orchestrator.workflow-feature-unsupported",
                id="parallel-barrier-unsupported",
            ),
        ],
    )
    def test_workflow_capability_requires_orchestrator_support(self, orchestrator_kwargs, scenario_yaml, expected_code):
        limited = _limited_backend_manifest(
            name="limited",
            provisioner=create_stub_manifest().provisioner,
            orchestrator=OrchestratorCapabilities(name="limited-orchestrator", **orchestrator_kwargs),
            evaluator=create_stub_manifest().evaluator,
        )

        execution_plan = plan(
            compile_runtime_model(_scenario(scenario_yaml)),
            limited,
        )

        codes = {diag.code for diag in execution_plan.diagnostics}
        assert expected_code in codes
        assert not execution_plan.is_valid

    def test_workflow_assertion_changes_force_workflow_refresh(self):
        old_model = compile_runtime_model(
            _scenario("""
name: workflow
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
objectives:
  initial:
    entity: blue
    success: {assertions: [health]}
entities:
  blue: {role: blue}
workflows:
  flow:
    start: branch
    steps:
      branch:
        type: decision
        when: {assertions: [pre-health]}
        then: finish
        else: finish
      finish: {type: end}
""")
        )
        old_plan = plan(old_model, create_stub_manifest())
        snapshot = _snapshot_from_plan(old_plan)

        new_plan = _plan_with_snapshot(
            """
name: workflow
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/false, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime-v2, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
objectives:
  initial:
    entity: blue
    success: {assertions: [health]}
entities:
  blue: {role: blue}
workflows:
  flow:
    start: branch
    steps:
      branch:
        type: decision
        when: {assertions: [pre-health]}
        then: finish
        else: finish
      finish: {type: end}
""",
            snapshot,
        )

        orchestration_actions = {op.address: op.action.value for op in new_plan.orchestration.operations}
        assert orchestration_actions["orchestration.workflow.flow"] == "update"

    def test_cross_domain_refresh_dependencies_do_not_drive_ordering(self):
        base = """
name: cross-domain
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    injects: {mail: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime-v2, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
injects:
  mail: {source: inbox}
events:
  kickoff: {assertions: [pre-health], injects: [mail]}
"""
        old_model = compile_runtime_model(_scenario(base))
        kickoff = old_model.events["orchestration.event.kickoff"]
        assert "evaluation.assertion.pre-health" not in kickoff.ordering_dependencies
        assert "evaluation.assertion.pre-health" in kickoff.refresh_dependencies
        assert "orchestration.inject.mail" in kickoff.ordering_dependencies

        old_plan = plan(old_model, create_stub_manifest())
        snapshot = _snapshot_from_plan(old_plan)
        new_plan = _plan_with_snapshot(
            base.replace(
                "urn:raes:declared-property:runtime",
                "urn:raes:declared-property:runtime-v2",
            ),
            snapshot,
        )

        orchestration_actions = {op.address: op.action.value for op in new_plan.orchestration.operations}
        assert orchestration_actions["orchestration.event.kickoff"] == "update"

    def test_objective_window_refs_are_refresh_only(self):
        model = compile_runtime_model(
            _scenario("""
name: objective-window
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
objectives:
  initial:
    entity: blue
    success: {assertions: [health]}
    window:
      workflows: [flow]
      steps: [flow.branch]
entities:
  blue: {role: blue}
workflows:
  flow:
    start: branch
    steps:
      branch:
        type: decision
        when: {assertions: [pre-health]}
        then: finish
        else: finish
      finish: {type: end}
""")
        )

        objective = model.objectives["evaluation.objective.initial"]
        execution_plan = plan(model, _os_capable_stub_manifest())

        assert "orchestration.workflow.flow" not in objective.ordering_dependencies
        assert "orchestration.workflow.flow" in objective.refresh_dependencies
        assert execution_plan.evaluation.startup_order == [
            "evaluation.condition.vm.health",
            "evaluation.proposition.health",
            "evaluation.assertion.health",
            "evaluation.assertion.pre-health",
            "evaluation.objective.initial",
        ]

    def test_objective_updates_when_window_dependencies_change(self):
        base = """
name: windows
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
objectives:
  initial:
    entity: blue
    success: {assertions: [health]}
    window:
      scripts: [timeline]
      events: [kickoff]
      workflows: [flow]
      steps: [flow.branch]
entities:
  blue: {role: blue}
events:
  kickoff: {assertions: [pre-health], description: kickoff}
scripts:
  timeline: {start_time: 0, end_time: 60, speed: 1, events: {kickoff: 10}}
workflows:
  flow:
    description: primary
    start: branch
    steps:
      branch:
        type: decision
        when: {assertions: [pre-health]}
        then: finish
        else: finish
      finish: {type: end}
"""
        old_plan = plan(compile_runtime_model(_scenario(base)), create_stub_manifest())
        snapshot = _snapshot_from_plan(old_plan)

        changed_variants = [
            base.replace("end_time: 60", "end_time: 120"),
            base.replace("description: kickoff", "description: changed"),
            base.replace("description: primary", "description: updated"),
            base.replace("then: finish", "then: finish\n        description: changed"),
        ]
        for changed in changed_variants:
            new_plan = _plan_with_snapshot(changed, snapshot)
            actions = {op.address: op.action.value for op in new_plan.evaluation.operations}
            assert actions["evaluation.objective.initial"] == "update"

    def test_content_and_account_refresh_only_on_node_changes(self):
        old_model = compile_runtime_model(
            _scenario("""
name: provision
nodes:
  web:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    features: {nginx: web}
    roles: {web: appuser}
features:
  nginx: {type: service, source: nginx}
content:
  flag: {type: file, target: web, path: /tmp/flag.txt}
accounts:
  admin: {username: admin, node: web}
""")
        )
        old_plan = plan(old_model, create_stub_manifest())
        snapshot = _snapshot_from_plan(old_plan)

        feature_change_plan = _plan_with_snapshot(
            """
name: provision
nodes:
  web:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    features: {nginx: web}
    roles: {web: appuser}
features:
  nginx: {type: service, source: nginx-full}
content:
  flag: {type: file, target: web, path: /tmp/flag.txt}
accounts:
  admin: {username: admin, node: web}
""",
            snapshot,
        )
        feature_actions = {op.address: op.action.value for op in feature_change_plan.provisioning.operations}
        assert feature_actions["provision.feature.web.nginx"] == "update"
        assert feature_actions["provision.content.flag"] == "unchanged"
        assert feature_actions["provision.account.admin"] == "unchanged"

        node_change_plan = _plan_with_snapshot(
            """
name: provision
nodes:
  web:
    type: compute
    os: windows
    resources: {ram: 1 gib, cpu: 1}
    features: {nginx: web}
    roles: {web: appuser}
features:
  nginx: {type: service, source: nginx}
content:
  flag: {type: file, target: web, path: /tmp/flag.txt}
accounts:
  admin: {username: admin, node: web}
""",
            snapshot,
        )
        node_actions = {op.address: op.action.value for op in node_change_plan.provisioning.operations}
        assert node_actions["provision.node.web"] == "update"
        assert node_actions["provision.content.flag"] == "update"
        assert node_actions["provision.account.admin"] == "update"

    def test_semantic_capability_validation_catches_real_requirements(self):
        limited = _limited_backend_manifest(
            name="limited",
            provisioner=ProvisionerCapabilities(
                name="limited-provisioner",
                supported_node_types=frozenset({"compute", "switch"}),
                supported_os_families=frozenset({"linux"}),
                supported_content_types=frozenset({"file"}),
                supported_account_features=frozenset({"groups"}),
                max_total_nodes=1,
                supports_acls=False,
                supports_accounts=True,
            ),
            orchestrator=OrchestratorCapabilities(
                name="limited-orchestrator",
                supported_sections=frozenset({"events", "scripts", "stories"}),
                supports_workflows=False,
            ),
            evaluator=EvaluatorCapabilities(
                name="limited-evaluator",
                supported_sections=frozenset({"conditions"}),
                supports_scoring=True,
                supports_objectives=False,
            ),
        )

        model = compile_runtime_model(
            _scenario("""
name: limited
nodes:
  corp: {type: switch}
  stateful: {type: compute, os: linux}
  dc:
    type: compute
    os: windows
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
generated_artifacts:
  dc-config:
    generator: rendered_config
    lifecycle: regenerate_on_change
    provenance: config/dc.yml
    outputs:
      - {name: dc-config, path: dc.yml, sensitivity: restricted}
    consumers:
      - {node: stateful, mount_destination: /etc/raes/dc.yml, access_mode: read_only}
persistent_volumes:
  dc-data:
    lifecycle: retain
    access_mode: read_write_once
    consumers:
      - {node: stateful, mount_destination: /var/lib/raes, access_mode: read_write}
infrastructure:
  corp:
    count: 1
    properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}
    acls:
      - {direction: in, from_net: corp, action: allow}
  dc: {count: 1, links: [corp]}
accounts:
  admin: {username: administrator, node: dc, spn: LDAP/dc.example.local, domain_ref: example}
identity_domains:
  example:
    profile: active_directory
    dns_name: example.local
    netbios_name: EXAMPLE
    authority_account_ref: admin
relationships:
  dc-role:
    type: domain_controller_for
    source: dc
    target: example
    domain_controller: {}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [nodes.dc]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
objectives:
  defend:
    entity: blue
    success: {assertions: [health]}
entities:
  blue: {role: blue}
events:
  kickoff: {assertions: [pre-health]}
scripts:
  timeline: {start_time: 0, end_time: 60, speed: 1, events: {kickoff: 10}}
stories:
  main: {scripts: [timeline]}
workflows:
  flow:
    start: start
    steps:
      start: {type: objective, objective: defend, on_success: end}
      end: {type: end}
""")
        )
        execution_plan = plan(model, limited)
        codes = {diag.code for diag in execution_plan.diagnostics}

        assert "provisioner.unsupported-os-family" in codes
        assert "provisioner.max-total-nodes-exceeded" in codes
        assert "provisioner.acls-unsupported" in codes
        assert "provisioner.unsupported-account-feature" in codes
        assert "provisioner.generated-artifacts-unsupported" in codes
        assert "provisioner.persistent-volumes-unsupported" in codes
        assert "orchestrator.unsupported-section" in codes
        assert "orchestrator.workflows-unsupported" in codes
        assert "evaluator.unsupported-section" in codes
        assert "evaluator.objectives-unsupported" in codes
        assert not execution_plan.is_valid

    def test_evaluator_admission_enforces_compiled_proposition_capabilities(self):
        limited = _limited_backend_manifest(
            provisioner=ProvisionerCapabilities(
                name="limited-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
            ),
            evaluator=EvaluatorCapabilities(
                name="boolean-api-evaluator",
                supported_sections=frozenset({"propositions", "assertions"}),
                supported_predicate_families=frozenset({"boolean"}),
                supported_quantifiers=frozenset({"all"}),
                supported_truth_outcomes=frozenset({"true", "false", "unknown", "unsupported"}),
                supported_evidence_channels=frozenset({"api_response"}),
                supported_time_domains=frozenset({"wall_clock_time"}),
                preserves_binding_provenance=True,
            ),
        )
        model = compile_runtime_model(
            _scenario("""
name: evaluator-capability-mismatch
nodes:
  vm: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
evidence_requirements:
  runtime-log:
    source_refs: [nodes.vm]
    scope: evaluator admission test
    boundary_kind: assertion_evaluation
    channel: log
    sensitivity: plain
    redaction: redact_secrets
    integrity: checksum
    retention: run_lifetime
    loss_disclosure: required
propositions:
  load:
    description: The runtime load equals the expected value.
    subjects: [nodes.vm]
    basis: observed_state
    quantifier: any
    predicate:
      kind: number
      property: runtime.load
      semantic_ref: urn:raes:observed-property:runtime.load
      expected: 1
      unit: count
      unit_semantic_ref: urn:raes:unit:count
    evidence_requirements: [runtime-log]
assertions:
  load: {proposition: load, role: postcondition}
""")
        )

        proposition = model.propositions["evaluation.proposition.load"]
        execution_plan = plan(model, limited)
        codes = {diagnostic.code for diagnostic in execution_plan.diagnostics}

        assert proposition.quantifier == "any"
        assert proposition.evidence_channels == ("log",)
        assert proposition.required_time_domain == "scenario_time"
        assert {
            "evaluator.unsupported-predicate-family",
            "evaluator.unsupported-quantifier",
            "evaluator.unsupported-evidence-channel",
            "evaluator.unsupported-time-domain",
        } <= codes
        assert not execution_plan.is_valid

    def test_evaluator_admission_rejects_opaque_evidence_channel_refs(self):
        evaluator = EvaluatorCapabilities(
            name="complete-evaluator",
            supported_sections=frozenset({"propositions", "assertions"}),
            supported_predicate_families=frozenset({"boolean"}),
            supported_quantifiers=frozenset({"all"}),
            supported_truth_outcomes=frozenset({"true", "false", "unknown", "unsupported"}),
            supported_evidence_channels=frozenset({"log"}),
            supported_time_domains=frozenset({"scenario_time"}),
            preserves_binding_provenance=True,
        )
        manifest = _limited_backend_manifest(
            provisioner=ProvisionerCapabilities(
                name="limited-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
            ),
            evaluator=evaluator,
        )
        model = compile_runtime_model(
            _scenario("""
name: unresolved-evidence-channel
nodes:
  vm: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
evidence_requirements:
  opaque-capture:
    source_refs: [nodes.vm]
    scope: evaluator admission test
    boundary_kind: assertion_evaluation
    channel_refs: [nodes.vm]
    sensitivity: plain
    redaction: redact_secrets
    integrity: checksum
    retention: run_lifetime
    loss_disclosure: required
propositions:
  healthy:
    description: The observed runtime is healthy.
    subjects: [nodes.vm]
    basis: observed_state
    predicate:
      kind: boolean
      property: runtime.healthy
      semantic_ref: urn:raes:observed-property:runtime.healthy
      expected: true
    evidence_requirements: [opaque-capture]
assertions:
  healthy: {proposition: healthy, role: postcondition}
""")
        )

        execution_plan = plan(model, manifest)

        assert model.propositions["evaluation.proposition.healthy"].unresolved_evidence_channel_refs == (
            "opaque-capture",
        )
        assert "evaluator.evidence-channel-unresolved" in {diagnostic.code for diagnostic in execution_plan.diagnostics}
        assert not execution_plan.is_valid

    def test_acl_capability_validation_covers_node_attached_rules(self):
        limited = _limited_backend_manifest(
            name="limited",
            provisioner=ProvisionerCapabilities(
                name="limited-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
                supports_acls=False,
            ),
        )
        model = compile_runtime_model(
            _scenario("""
name: node-acl
nodes:
  web:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
infrastructure:
  web:
    count: 1
    acls:
      - {direction: in, protocol: tcp, ports: [443], action: allow}
""")
        )

        execution_plan = plan(model, limited)

        acl_diagnostics = [
            diagnostic for diagnostic in execution_plan.diagnostics if diagnostic.code == "provisioner.acls-unsupported"
        ]
        assert [diagnostic.address for diagnostic in acl_diagnostics] == ["provision.node.web"]
        assert not execution_plan.is_valid

    def test_variable_backed_os_allowed_values_pass_when_all_supported(self):
        manifest = _limited_backend_manifest(
            name="limited",
            provisioner=ProvisionerCapabilities(
                name="limited-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux", "windows"}),
            ),
        )

        execution_plan = plan(
            compile_runtime_model(
                _scenario("""
name: variable-os
variables:
  os_name:
    type: string
    default: linux
    allowed_values: [linux, windows]
nodes:
  vm: {type: compute, os: '${os_name}', resources: {ram: 1 gib, cpu: 1}}
""")
            ),
            manifest,
        )

        codes = {diag.code for diag in execution_plan.diagnostics}

        assert "provisioner.unsupported-os-family" not in codes
        assert execution_plan.is_valid

    def test_variable_backed_os_allowed_values_pass_with_nonempty_supported_intersection(self):
        manifest = _limited_backend_manifest(
            name="limited",
            provisioner=ProvisionerCapabilities(
                name="limited-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
            ),
        )

        execution_plan = plan(
            compile_runtime_model(
                _scenario("""
name: variable-os
variables:
  os_name:
    type: string
    default: linux
    allowed_values: [linux, windows]
nodes:
  vm: {type: compute, os: '${os_name}', resources: {ram: 1 gib, cpu: 1}}
""")
            ),
            manifest,
        )

        codes = {diag.code for diag in execution_plan.diagnostics}

        assert "provisioner.unsupported-os-family" not in codes
        assert execution_plan.is_valid

    def test_variable_backed_os_defaults_must_be_valid_for_nodes_os(self):
        with pytest.raises(SDLInstantiationError) as exc:
            compile_runtime_model(
                _scenario("""
name: variable-os
variables:
  os_name:
    type: string
    default: banana
    allowed_values: [banana]
nodes:
  vm: {type: compute, os: '${os_name}', resources: {ram: 1 gib, cpu: 1}}
""")
            )
        assert "/nodes/vm/os" in str(exc.value)

    def test_variable_backed_os_without_allowed_values_is_narrowed_to_feasible_authority(self):
        manifest = _limited_backend_manifest(
            name="limited",
            provisioner=ProvisionerCapabilities(
                name="limited-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
            ),
        )

        execution_plan = plan(
            compile_runtime_model(
                _scenario("""
name: variable-os
variables:
  os_name:
    type: string
    default: linux
nodes:
  vm: {type: compute, os: '${os_name}', resources: {ram: 1 gib, cpu: 1}}
""")
            ),
            manifest,
        )

        codes = {diag.code for diag in execution_plan.diagnostics}

        assert "provisioner.os-family-validation-deferred" not in codes
        assert "provisioner.unsupported-os-family" not in codes
        assert "realization.authority-bound-unavailable" not in codes
        assert execution_plan.is_valid
        authority = next(
            entry
            for entry in execution_plan.provisioning.realization_authority
            if entry.requirement_kind == "os-family"
        )
        assert authority.bounds[0].domain.values == ["linux"]

    def test_variable_backed_os_with_undeclared_variable_fails_instantiation(self):
        manifest = _limited_backend_manifest(
            name="limited",
            provisioner=ProvisionerCapabilities(
                name="limited-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
            ),
        )
        scenario = parse_sdl(
            textwrap.dedent("""
name: variable-os
nodes:
  vm: {type: compute, os: '${missing_os}', resources: {ram: 1 gib, cpu: 1}}
"""),
            skip_semantic_validation=True,
        )

        with pytest.raises(SDLInstantiationError) as exc:
            compile_runtime_model(scenario)
        assert "missing_os" in str(exc.value)

    def test_variable_backed_counts_with_allowed_values_enforce_max_nodes(self):
        manifest = _limited_backend_manifest(
            name="limited",
            provisioner=ProvisionerCapabilities(
                name="limited-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
                max_total_nodes=2,
            ),
        )

        execution_plan = plan(
            compile_runtime_model(
                _scenario("""
name: variable-count
variables:
  node_count:
    type: integer
    default: 1
    allowed_values: [1, 3]
nodes:
  vm: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
infrastructure:
  vm: ${node_count}
""")
            ),
            manifest,
        )

        codes = {diag.code for diag in execution_plan.diagnostics}

        assert "provisioner.max-total-nodes-exceeded" in codes
        assert not execution_plan.is_valid

    def test_imported_module_allowed_values_retain_supported_intersection(self, tmp_path):
        # SDL module-import composition strips imported variables from the
        # merged payload, so the side-channel provenance must carry both the
        # imported variable spec AND the imported nodes' captured refs onto
        # the outer scenario. Otherwise the runtime planner's
        # `allowed_values`-vs-`supported_os_families` check is unreachable
        # for parameterized imported modules. This test exercises the path
        # end-to-end via parse_sdl_file.
        from pathlib import Path

        from raes import parse_sdl_file

        imported = tmp_path / "shared.yaml"
        imported.write_text(
            """
name: shared
version: 1.0.0
module:
  id: raes/shared
  version: 1.0.0
  parameters: [os_name]
  exports:
    nodes: [vm]
variables:
  os_name:
    type: string
    default: linux
    allowed_values: [linux, windows]
nodes:
  vm:
    type: compute
    os: '${os_name}'
    resources: {ram: 1 gib, cpu: 1}
""",
            encoding="utf-8",
        )
        root = tmp_path / "root.yaml"
        root.write_text(
            """
name: root
imports:
  - path: shared.yaml
    namespace: shared
    version: 1.0.0
""",
            encoding="utf-8",
        )
        manifest = _limited_backend_manifest(
            name="limited",
            provisioner=ProvisionerCapabilities(
                name="limited-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
            ),
        )

        scenario = parse_sdl_file(Path(root), skip_semantic_validation=True)
        execution_plan = plan(compile_runtime_model(scenario), manifest)

        codes = {diag.code for diag in execution_plan.diagnostics}

        assert "provisioner.unsupported-os-family" not in codes
        assert execution_plan.is_valid

    def test_variable_backed_counts_defaults_must_be_valid_for_infrastructure_count(self):
        manifest = _limited_backend_manifest(
            name="limited",
            provisioner=ProvisionerCapabilities(
                name="limited-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
                max_total_nodes=10,
            ),
        )

        with pytest.raises(SDLInstantiationError) as exc:
            compile_runtime_model(
                _scenario("""
name: variable-count
variables:
  node_count:
    type: integer
    default: 0
    allowed_values: [0]
nodes:
  vm: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
infrastructure:
  vm: ${node_count}
""")
            )
        assert "/infrastructure/vm/count" in str(exc.value)

    def test_variable_backed_os_allowed_values_retain_intersection_when_pre_instantiated(self):
        # Manager-path coverage: when the caller instantiates upstream and
        # passes an InstantiatedScenario to compile_runtime_model, the
        # captured-ref snapshot must still flow through so the
        # allowed_values-vs-supported_os_families intersection remains available.
        manifest = _limited_backend_manifest(
            name="limited",
            provisioner=ProvisionerCapabilities(
                name="limited-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
            ),
        )

        from raes.instantiate import instantiate_scenario

        instantiated = instantiate_scenario(
            _scenario("""
name: variable-os
variables:
  os_name:
    type: string
    default: linux
    allowed_values: [linux, windows]
nodes:
  vm: {type: compute, os: '${os_name}', resources: {ram: 1 gib, cpu: 1}}
"""),
        )
        execution_plan = plan(compile_runtime_model(instantiated), manifest)

        codes = {diag.code for diag in execution_plan.diagnostics}

        assert "provisioner.unsupported-os-family" not in codes
        assert execution_plan.is_valid

    def test_variable_backed_switch_count_enforces_max_nodes(self):
        # Switch (network) resources go through the same max_total_nodes
        # check as VM resources, so their `infrastructure.count` provenance
        # must be captured by the same path. Without that, a switch with
        # `allowed_values: [1, 3]` would slip past `max_total_nodes=2`.
        manifest = _limited_backend_manifest(
            name="limited",
            provisioner=ProvisionerCapabilities(
                name="limited-provisioner",
                supported_node_types=frozenset({"compute", "switch"}),
                supported_os_families=frozenset({"linux"}),
                max_total_nodes=2,
            ),
        )

        execution_plan = plan(
            compile_runtime_model(
                _scenario("""
name: variable-switch-count
variables:
  net_count:
    type: integer
    default: 1
    allowed_values: [1, 3]
nodes:
  net: {type: switch}
infrastructure:
  net: ${net_count}
""")
            ),
            manifest,
        )

        codes = {diag.code for diag in execution_plan.diagnostics}

        assert "provisioner.max-total-nodes-exceeded" in codes
        assert not execution_plan.is_valid

    def test_variable_backed_counts_without_allowed_values_use_instantiated_default(self):
        manifest = _limited_backend_manifest(
            name="limited",
            provisioner=ProvisionerCapabilities(
                name="limited-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
                max_total_nodes=1,
            ),
        )

        execution_plan = plan(
            compile_runtime_model(
                _scenario("""
name: variable-count
variables:
  node_count:
    type: integer
    default: 3
nodes:
  vm: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
infrastructure:
  vm: ${node_count}
""")
            ),
            manifest,
        )

        codes = {diag.code for diag in execution_plan.diagnostics}

        assert "provisioner.max-total-nodes-validation-deferred" not in codes
        assert "provisioner.max-total-nodes-exceeded" in codes
        assert not execution_plan.is_valid

    def test_variable_backed_counts_with_undeclared_variable_fail_instantiation(self):
        manifest = _limited_backend_manifest(
            name="limited",
            provisioner=ProvisionerCapabilities(
                name="limited-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
                max_total_nodes=1,
            ),
        )
        scenario = parse_sdl(
            textwrap.dedent("""
name: variable-count
nodes:
  vm: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
infrastructure:
  vm: ${missing_count}
"""),
            skip_semantic_validation=True,
        )

        with pytest.raises(SDLInstantiationError) as exc:
            compile_runtime_model(scenario)
        assert "missing_count" in str(exc.value)

    def test_dependency_ordering_across_domain_plans(self):
        execution_plan = plan(
            compile_runtime_model(
                _scenario("""
name: ordering
nodes:
  corp: {type: switch}
  web:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    features: {nginx: web}
    conditions: {health: web}
    injects: {mail: web}
    roles: {web: appuser}
infrastructure:
  corp: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  web: {count: 1, links: [corp]}
features:
  nginx: {type: service, source: nginx}
content:
  flag: {type: file, target: web, path: /tmp/flag.txt}
accounts:
  admin: {username: admin, node: web}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [nodes.web]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
injects:
  mail: {source: inbox}
objectives:
  initial:
    entity: blue
    success: {assertions: [health]}
entities:
  blue: {role: blue}
events:
  kickoff: {assertions: [pre-health], injects: [mail]}
scripts:
  timeline: {start_time: 0, end_time: 60, speed: 1, events: {kickoff: 10}}
stories:
  main: {scripts: [timeline]}
workflows:
  flow:
    start: start
    steps:
      start: {type: objective, objective: initial, on_success: end}
      end: {type: end}
""")
            ),
            create_stub_manifest(),
        )

        provision_order = [op.address for op in execution_plan.provisioning.operations if op.action.value != "delete"]
        orchestration_order = execution_plan.orchestration.startup_order
        evaluation_order = execution_plan.evaluation.startup_order

        assert provision_order.index("provision.network.corp") < provision_order.index("provision.node.web")
        assert provision_order.index("provision.node.web") < provision_order.index("provision.feature.web.nginx")
        assert provision_order.index("provision.node.web") < provision_order.index("provision.content.flag")
        assert provision_order.index("provision.node.web") < provision_order.index("provision.account.admin")
        assert orchestration_order.index("orchestration.inject.mail") < orchestration_order.index(
            "orchestration.inject-binding.web.mail"
        )
        assert orchestration_order.index("orchestration.inject-binding.web.mail") < orchestration_order.index(
            "orchestration.event.kickoff"
        )
        assert orchestration_order.index("orchestration.event.kickoff") < orchestration_order.index(
            "orchestration.script.timeline"
        )
        assert orchestration_order.index("orchestration.script.timeline") < orchestration_order.index(
            "orchestration.story.main"
        )
        # Post ADR-073 the evaluation domain orders condition -> objective
        # (the metric -> evaluation -> tlo -> goal chain was removed).
        assert evaluation_order.index("evaluation.condition.web.health") < evaluation_order.index(
            "evaluation.objective.initial"
        )

    def test_satcom_release_poisoning_compiles_to_valid_execution_plan(self):
        scenario_path = EXAMPLES_DIR / "satcom-release-poisoning.sdl.yaml"
        content = scenario_path.read_text(encoding="utf-8")
        model = compile_runtime_model(parse_sdl(content))
        execution_plan = plan(model, _os_capable_stub_manifest())

        # Pinned counts from the satcom example. A partial regression
        # (e.g. half the nodes failing to compile) keeps `> 5` green; exact
        # match catches it. Authors who add or remove SDL elements update
        # this single line, which is preferable to letting the test rot
        # into a no-op.
        assert execution_plan.is_valid
        assert len(model.node_deployments) == 14
        assert len(model.feature_bindings) == 14
        assert len(model.injects) == 3
        assert len(model.objectives) == 6
        assert len(model.workflows) == 1
        assert len(execution_plan.provisioning.operations) > 0
        assert len(execution_plan.orchestration.startup_order) > 0
        assert len(execution_plan.evaluation.startup_order) > 0
