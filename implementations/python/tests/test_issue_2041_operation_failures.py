"""Conclusive operation failures and uncertain setup retain distinct workflow outcomes."""

from dataclasses import replace

import pytest
from raes.orchestration import Event
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.runtime_state import ApplyResult, OperationState
from raes_runtime.manager import RuntimeManager
from raes_runtime.runtime_module_step import phase_states
from test_issue_1362_provider_execution import Provider, target
from test_issue_2041_runtime_step_dispatch import StepBackend, scenario


class TerminalProvider(Provider):
    def __init__(self, outcome):
        super().__init__()
        self.outcome = outcome

    def operation_capabilities(self):
        original = super().operation_capabilities()
        return type(original).model_validate({**original.model_dump(), "supported_operation_kinds": ["orchestration"]})

    def observe_operation(self, control):
        return self.report(
            self.request,
            {
                "kind": "outcome",
                "proposed_state": self.outcome,
                "effects": {
                    "effect": "absent",
                    "cessation_established": True,
                    "evidence_refs": [
                        {
                            "contract_id": "runtime-snapshot-v1",
                            "artifact_id": "no-effect",
                            "digest": "sha256:" + "a" * 64,
                        }
                    ],
                },
                "satisfaction": "unsatisfied",
                "release_gates_satisfied": True,
                "cancellation_established": self.outcome == "cancelled",
            },
        )


class AbsenceEvidence:
    def validate_effects(self, request, response):
        return (
            response.binding == request.binding
            and response.message.effects.effect == "absent"
            and response.message.effects.cessation_established
        )

    def resolve_result(self, request, response, predecessor):
        raise AssertionError("a conclusive absent failure has no result artifact")


@pytest.mark.parametrize("role", ["step", "resources"])
@pytest.mark.parametrize("outcome", ["failed", "cancelled"])
def test_conclusive_child_operation_without_result_terminates_workflow(role, outcome):
    provider = TerminalProvider(outcome)
    source = scenario("      run: {type: end}\n")
    if role == "resources":
        source.events = {"setup": Event(description="An admitted setup event.")}
    with RuntimeManager(target(provider), operation_evidence=AbsenceEvidence()) as owner:
        plan = owner.plan(source)
        assert plan.is_valid, plan.diagnostics
        owner.register_planner_produced_plan(plan)
        receipt = owner.submit_orchestration(plan.orchestration, idempotency_key="terminal-child")
        assert owner.get_operation(receipt.operation_id).state.value == outcome
        children = [item for item in owner._store.load_records().values() if item.invocation is not None]
        assert len(children) == 1
        assert children[0].status.state.value == outcome
        assert children[0].invocation.consumed and not children[0].invocation.reserved
        assert children[0].workflow is None
        assert owner.get_operation(receipt.operation_id).diagnostics
        assert provider.starts == 1


def test_refused_setup_admission_terminates_before_any_step():
    provider = TerminalProvider("failed")
    provider.refuse = True
    source = scenario("      run: {type: end}\n")
    source.events = {"setup": Event(description="A refused setup event.")}
    with RuntimeManager(target(provider), operation_evidence=AbsenceEvidence()) as owner:
        plan = owner.plan(source)
        owner.register_planner_produced_plan(plan)
        receipt = owner.submit_orchestration(plan.orchestration, idempotency_key="refused-setup")
        assert owner.get_operation(receipt.operation_id).state is OperationState.FAILED
        assert provider.starts == 0
        provider.refuse = False
        replay = owner.submit_orchestration(plan.orchestration, idempotency_key="refused-setup")
        assert replay == receipt
        assert provider.starts == 0


def test_uncertain_resource_setup_is_visible_in_run_progress():
    class UnknownSetup(StepBackend):
        def start(self, plan, snapshot):
            return ApplyResult(False, snapshot)

    backend = UnknownSetup()
    source = scenario("      run: {type: end}\n")
    source.events = {"setup": Event(description="An uncertain setup event.")}
    with RuntimeManager(replace(create_stub_target(), orchestrator=backend)) as owner:
        assert not owner.apply(owner.plan(source)).success
        records = owner._store.load_records()
        root = next(item for item in records.values() if item.workflow is not None and item.workflow.kind == "root")
        assert phase_states(owner, (root,)) == {OperationState.INDETERMINATE}
        assert backend.dispatches == []
