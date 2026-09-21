"""RUN-300: end-to-end processing-model lifecycle integrity tests.

RUN-300 ("Processing Model and Lifecycle") requires that the ecosystem
carry a valid scenario through instantiation, compilation, planning,
execution, and live observation while preserving scenario meaning across
those stages.

The existing per-stage tests (``test_fm2_semantics``, ``test_runtime_*``)
each verify a single stage or a single stage pair. The tests in this
module thread one parameterized scenario through all five stages end to
end, and assert that the canonical identity chosen at instantiation time
survives unchanged into the compiled model, the planner provenance tuple,
the applied snapshot, and the live-observation envelope — and that any
drift of that provenance is rejected rather than silently reconciled.
"""

from __future__ import annotations

import json
import textwrap

import pytest
from raes import (
    InstantiatedScenario,
    SDLInstantiationError,
    instantiate_scenario,
    parse_sdl,
)
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.planning import PlanScope
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import (
    ChangeAction,
    ExecutionPlan,
    RuntimeDomain,
    RuntimeSnapshot,
)
from raes_processor.planner import plan as plan_execution
from raes_runtime.manager import RuntimeManager

NODE_NAME = "vm1"
EXPECTED_NODE_ADDRESS = f"provision.node.{NODE_NAME}"
EXPECTED_WORKFLOW_ADDRESS = "orchestration.workflow.response"
DRIFT_DIAGNOSTIC_CODE = "runtime.plan-snapshot-mismatch"
PARAM_NODE_DESCRIPTION = "primary-node"
PARAM_CPU_COUNT = 2


def _enveloped_stub_target():
    return create_stub_target()


def _raw_scenario():
    """Return a parsed, still-parameterized scenario.

    Canonical mapping keys (``nodes.vm1``) are fixed at parse time —
    the parser explicitly rejects ``${var}`` in user-defined mapping
    keys (see ``_reject_variable_mapping_keys`` in the SDL parser).
    The meaning-preservation probe therefore lives in value positions:
    the ``node_description`` and ``cpu_count`` variables must flow through
    instantiation and land, fully substituted, inside the compiled
    model, the planner's operation payload, and the applied snapshot
    entry for ``provision.node.vm1``.

    The scenario exercises all three runtime domains (provisioning,
    orchestration, evaluation) so each downstream plan has non-empty
    operations and the live-observation surface is populated.
    """

    return parse_sdl(
        textwrap.dedent(
            f"""
            name: run-300-lifecycle
            variables:
              node_description:
                type: string
                default: primary-node
                allowed_values: [primary-node]
              cpu_count:
                type: integer
                default: 1
            nodes:
              {NODE_NAME}:
                type: compute
                description: ${{node_description}}
                resources:
                  ram: 1 gib
                  cpu: ${{cpu_count}}
                conditions: {{health: ops}}
                roles: {{ops: operator}}
            conditions:
              health: {{command: /bin/true, interval: 15}}
            propositions:
              health:
                description: The governed VM has declared runtime state.
                subjects: [nodes.{NODE_NAME}]
                basis: declared_state
                predicate: {{kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}}
            assertions:
              health: {{proposition: health, role: postcondition, polarity: positive}}
            entities:
              blue: {{role: blue}}
            objectives:
              validate:
                owner: blue
                success: {{assertions: [health]}}
            workflows:
              response:
                start: run
                steps:
                  run:
                    type: objective
                    objective: validate
                    on_success: finish
                  finish: {{type: end}}
            """
        )
    )


def _no_variable_tokens(obj: object) -> bool:
    """Return ``True`` if ``obj`` contains no ``${...}`` placeholder tokens."""

    serialized = json.dumps(obj, default=str)
    return "${" not in serialized


class TestRun300Lifecycle:
    """Five-stage pipeline integrity tests for RUN-300."""

    def test_valid_scenario_flows_through_all_five_stages_preserving_identity(self):
        """One parameterized scenario → instantiate → compile → plan → apply → observe.

        Asserts that the values substituted for ``${node_description}`` and
        ``${cpu_count}`` at instantiation time, and the canonical node
        and workflow addresses, survive unchanged into the downstream
        typed contracts that publish them. Substituted values must remain
        intact in the compiled model, plan operation, and applied
        snapshot entry; canonical addresses must remain intact through
        compilation, planning, apply, and the live-observation envelope.
        No ``${...}`` token is permitted to escape any stage.
        """

        # ----- Stage 1: Instantiation --------------------------------
        raw = _raw_scenario()
        instantiated = instantiate_scenario(
            raw,
            parameters={"node_description": PARAM_NODE_DESCRIPTION, "cpu_count": PARAM_CPU_COUNT},
        )

        assert isinstance(instantiated, InstantiatedScenario), (
            "instantiate_scenario must return a typed InstantiatedScenario, "
            "not a loose dict — typed contracts are how RUN-300 preserves "
            "meaning across stages."
        )
        assert instantiated.instantiation_provenance.root_binding_values == {
            "node_description": PARAM_NODE_DESCRIPTION,
            "cpu_count": PARAM_CPU_COUNT,
        }, (
            "Instantiation parameters must be captured in portable provenance "
            "so downstream stages can trace them to the authoring inputs."
        )
        instantiated_payload = instantiated.model_dump(mode="python", by_alias=True)
        assert _no_variable_tokens(instantiated_payload), (
            "All ${...} tokens must be resolved during instantiation; any "
            "token surviving into compilation would mean a stage is "
            "consuming raw SDL rather than the canonical compiled form."
        )
        assert NODE_NAME in instantiated_payload.get("nodes", {}), (
            "The canonical node identity must appear under its literal key after instantiation."
        )
        instantiated_node = instantiated_payload["nodes"][NODE_NAME]
        assert instantiated_node["description"] == PARAM_NODE_DESCRIPTION, (
            "Instantiation must substitute node_description before compilation begins."
        )
        assert instantiated_node["resources"]["cpu"] == PARAM_CPU_COUNT, (
            "Instantiation must substitute cpu_count before compilation begins."
        )

        # ----- Stage 2: Compilation ----------------------------------
        model = compile_runtime_model(instantiated)
        compile_errors = [diag for diag in model.diagnostics if diag.is_error]
        assert not compile_errors, (
            f"Compilation produced error diagnostics: {compile_errors!r}. A valid scenario must compile cleanly."
        )
        assert EXPECTED_NODE_ADDRESS in model.node_deployments, (
            f"Compiled RuntimeModel must key its node_deployments on the "
            f"canonical address {EXPECTED_NODE_ADDRESS!r}. Any other key "
            f"shape would mean planning has to reparse raw SDL to know "
            f"what a node is called."
        )
        compiled_node = model.node_deployments[EXPECTED_NODE_ADDRESS]
        assert compiled_node.node_name == NODE_NAME
        assert compiled_node.spec["node"]["description"] == PARAM_NODE_DESCRIPTION, (
            f"node_description parameter ({PARAM_NODE_DESCRIPTION!r}) must survive "
            "substitution through into the compiled node specification."
        )
        assert compiled_node.spec["node"]["resources"]["cpu"] == PARAM_CPU_COUNT, (
            f"cpu_count parameter ({PARAM_CPU_COUNT!r}) must survive "
            "compilation into the canonical node resource payload."
        )

        # ----- Stage 3: Planning -------------------------------------
        target = _enveloped_stub_target()
        empty_snapshot = RuntimeSnapshot()
        execution_plan = plan_execution(
            model,
            target.manifest,
            empty_snapshot,
            scope=PlanScope(target_name=target.name),
        )

        assert isinstance(execution_plan, ExecutionPlan)
        assert execution_plan.target_name == target.name, (
            "ExecutionPlan provenance must bind to the target name the manager will apply against."
        )
        assert execution_plan.manifest == target.manifest, (
            "ExecutionPlan provenance must carry the manifest used at planning time so apply can detect manifest drift."
        )
        assert execution_plan.base_snapshot == empty_snapshot, (
            "ExecutionPlan provenance must carry the snapshot used at planning time so apply can detect snapshot drift."
        )
        assert execution_plan.scenario_name == instantiated.name, (
            "The planner must propagate the scenario identity through the "
            "plan so archival layers can correlate plans back to their "
            "originating compiled model."
        )
        assert execution_plan.is_valid, f"Plan must be valid; got diagnostics: {execution_plan.diagnostics!r}"

        provision_addresses = {op.address for op in execution_plan.provisioning.operations}
        assert EXPECTED_NODE_ADDRESS in provision_addresses, (
            f"Planner must emit a provisioning operation addressed "
            f"{EXPECTED_NODE_ADDRESS!r}; got {sorted(provision_addresses)!r}."
        )
        create_ops = [op for op in execution_plan.provisioning.operations if op.address == EXPECTED_NODE_ADDRESS]
        assert create_ops and create_ops[0].action == ChangeAction.CREATE, (
            "Against an empty snapshot the node must reconcile as CREATE; "
            "any other action means planning is conflating base state with "
            "the compiled model."
        )
        create_op = create_ops[0]
        assert create_op.payload["spec"]["node"]["description"] == PARAM_NODE_DESCRIPTION, (
            "Planner payload must preserve the compiled node description without rewriting or reinterpreting it."
        )
        assert create_op.payload["spec"]["node"]["resources"]["cpu"] == PARAM_CPU_COUNT, (
            "Planner payload must preserve the compiled cpu_count without rewriting or reinterpreting it."
        )
        orchestration_addresses = {op.address for op in execution_plan.orchestration.operations}
        assert orchestration_addresses == {EXPECTED_WORKFLOW_ADDRESS}, (
            "Planner must emit the canonical workflow address so live "
            "observation can report the same identity without translation."
        )

        # ----- Stage 4: Execution (apply) ----------------------------
        manager = RuntimeManager(target)
        apply_result = manager.apply(execution_plan)

        error_diagnostics = [diag for diag in apply_result.diagnostics if diag.is_error]
        assert apply_result.success, (
            f"Apply must succeed on a clean scenario against an empty snapshot; diagnostics: {error_diagnostics!r}"
        )
        assert not error_diagnostics, (
            f"Apply must not surface error diagnostics on the happy path; got: {error_diagnostics!r}"
        )

        applied_snapshot = manager.snapshot
        provisioning_state = applied_snapshot.for_domain(RuntimeDomain.PROVISIONING)
        assert EXPECTED_NODE_ADDRESS in provisioning_state, (
            f"Applied provisioning snapshot must contain the canonical "
            f"address {EXPECTED_NODE_ADDRESS!r}. Loss of this address "
            f"would mean execution rewrote the identity between planning "
            f"and apply."
        )
        applied_entry = provisioning_state[EXPECTED_NODE_ADDRESS]
        assert applied_entry.resource_type == "node", (
            "The snapshot entry must carry the canonical resource type from the compiled model."
        )
        assert applied_entry.domain is RuntimeDomain.PROVISIONING
        assert EXPECTED_NODE_ADDRESS in apply_result.changed_addresses, (
            "ApplyResult must report the canonical address as changed so "
            "live-observation consumers can subscribe by canonical identity."
        )
        assert applied_entry.payload["spec"]["node"]["description"] == PARAM_NODE_DESCRIPTION, (
            "Apply must preserve the planned node description in the stored snapshot entry."
        )
        assert applied_entry.payload["spec"]["node"]["resources"]["cpu"] == PARAM_CPU_COUNT, (
            "Apply must preserve the planned cpu_count in the stored snapshot entry."
        )
        assert _no_variable_tokens(applied_entry.payload), (
            "Applied snapshot payload must not contain any ${...} tokens — "
            "meaning has been lost if unsubstituted placeholders reached "
            "the runtime state surface."
        )

        # ----- Stage 5: Live observation -----------------------------
        # The published live-observation surface is the manager snapshot's
        # orchestration_results / orchestration_history (portable envelope
        # defined in specs/formal/runtime-contracts/workflow-results.md).
        # The stub orchestrator produces a running workflow state keyed by
        # the compiled workflow address; that address — like the node
        # address — must derive from the compiled identity, not from raw SDL.
        orchestration_state = applied_snapshot.for_domain(RuntimeDomain.ORCHESTRATION)
        assert orchestration_state, (
            "Orchestration domain must contain at least one runtime entry "
            "after apply for a scenario that declares a workflow."
        )
        assert set(orchestration_state) == {EXPECTED_WORKFLOW_ADDRESS}, (
            "Live observation must expose the exact canonical workflow "
            "address chosen during planning, not merely the right namespace."
        )

        orchestration_results = applied_snapshot.orchestration_results
        assert orchestration_results, (
            "Stub orchestrator must publish at least one workflow "
            "execution state entry on the live-observation surface; an "
            "empty result set would mean stage 5 is not actually exercised."
        )
        assert set(orchestration_results) == orchestration_addresses, (
            "Live observation must publish the same workflow addresses the "
            "planner emitted, with no drift or silent remapping."
        )
        # Portable workflow-execution-state envelope invariants.
        for address, state in orchestration_results.items():
            assert address in orchestration_state, (
                f"Orchestration result {address!r} must correspond to a snapshot entry in the orchestration domain."
            )
            assert state.get("state_schema_version") == "workflow-step-state/v1", (
                f"Workflow execution state must declare the current "
                f"state_schema_version per workflow-results.md; got "
                f"{state.get('state_schema_version')!r}."
            )
            assert state.get("workflow_status") == "running", (
                f"Stub orchestrator must publish workflow_status='running' "
                f"on the live envelope immediately after start; got "
                f"{state.get('workflow_status')!r}."
            )

    def test_reapplying_stale_plan_is_rejected_by_provenance_drift_check(self):
        """Drift rejection test.

        After a successful apply the manager's snapshot advances. Re-applying
        the original plan — whose ``base_snapshot`` is now stale — must
        surface a ``runtime.plan-snapshot-mismatch`` diagnostic and must
        not perform a second (partial) apply against the advanced state.
        This exercises the provenance check in ``raes_processor/manager.py``
        (the base_snapshot comparison in ``_provenance_diagnostics``) and
        is the concrete guarantee that RUN-300's "preserving scenario
        meaning across those stages" clause is enforced even against
        out-of-order or replayed plans.
        """

        raw = _raw_scenario()
        instantiated = instantiate_scenario(
            raw,
            parameters={"node_description": PARAM_NODE_DESCRIPTION, "cpu_count": PARAM_CPU_COUNT},
        )
        model = compile_runtime_model(instantiated)
        target = _enveloped_stub_target()
        empty_snapshot = RuntimeSnapshot()
        stale_plan = plan_execution(
            model,
            target.manifest,
            empty_snapshot,
            scope=PlanScope(target_name=target.name),
        )

        manager = RuntimeManager(target)
        first_apply = manager.apply(stale_plan)
        assert first_apply.success, "First apply must succeed to advance the snapshot."
        assert manager.snapshot != empty_snapshot, (
            "Manager snapshot must advance after a successful apply; otherwise the drift check below is a tautology."
        )
        snapshot_before_reapply = manager.snapshot.with_entries(dict(manager.snapshot.entries))

        # Attempt to apply the original plan a second time. Its base_snapshot
        # is still the empty snapshot, which no longer matches the manager.
        second_apply = manager.apply(stale_plan)

        assert not second_apply.success, (
            "Re-applying a plan whose base_snapshot no longer matches the "
            "manager's current snapshot must fail rather than silently "
            "reconcile against a different base."
        )
        drift_codes = {diag.code for diag in second_apply.diagnostics if diag.is_error}
        assert DRIFT_DIAGNOSTIC_CODE in drift_codes, (
            f"Expected provenance drift diagnostic {DRIFT_DIAGNOSTIC_CODE!r}; got error codes: {sorted(drift_codes)!r}"
        )
        assert second_apply.snapshot == snapshot_before_reapply, (
            "On drift rejection apply must return the pre-existing snapshot "
            "state unchanged — no partial apply is permitted."
        )
        assert manager.snapshot == snapshot_before_reapply, (
            "On drift rejection the manager must retain its pre-existing snapshot state unchanged."
        )

    def test_unresolved_instantiation_parameter_is_rejected_before_compilation(self):
        """Invalid scenarios must not reach compilation.

        RUN-300 requires the processing model to carry *valid* scenarios
        through the pipeline. An unresolved variable reference is an
        instantiation-time error and must be raised before the compiler
        ever sees the scenario, so that no downstream stage can mistake
        an unsubstituted ``${...}`` token for a canonical identity.
        """

        raw = parse_sdl(
            textwrap.dedent(
                """
                name: run-300-unresolved
                variables:
                  node_description:
                    type: string
                nodes:
                  vm1:
                    type: compute
                    description: ${node_description}
                    resources: {ram: 1 gib, cpu: 1}
                """
            )
        )
        with pytest.raises(SDLInstantiationError, match="unresolved variable references"):
            instantiate_scenario(raw, parameters={})
