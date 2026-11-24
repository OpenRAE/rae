"""Property-based and differential coverage for workflow control semantics (FM3).

Delivers the ``property_based_or_differential_tests`` artifact kind for the
``workflows`` formal-spec subsystem (``specs/formal/workflows``, FM3) recorded in
``specs/formal/assurance-fulfillment.yaml`` (issue #521). It exercises the pure
workflow state-machine / result-envelope rules in ``raes.semantics.workflow``
that validation, compilation, and runtime all share:

* ``branch_closure`` -- the join-ownership / branch-convergence graph semantics
  (only the owning parallel's branch closure, up to but excluding the join),
  checked *differentially* against an independent fix-point reachability oracle
  plus the structural invariants the closure must satisfy for any graph.
* ``validate_workflow_step_result`` -- the per-step lifecycle/outcome/attempt
  contract, checked over a generated legal-state space (must accept) and
  targeted illegal mutations (must reject), and cross-checked against the
  compiled ``raes_contracts`` wrapper surface.

These are FM2/FM3 semantic properties, not example fixtures: the assertions hold
across the generated space rather than for a hand-picked case.
"""

from __future__ import annotations

from collections.abc import Mapping

from hypothesis import given, settings
from hypothesis import strategies as st
from raes_contracts.workflow import validate_workflow_step_result_contract
from raes_contracts.workflow.semantics import (
    branch_closure,
    validate_workflow_step_result,
    workflow_step_semantic_contract,
)

# --------------------------------------------------------------------------- #
# branch_closure: workflow-graph state-machine semantics                      #
# --------------------------------------------------------------------------- #

_NODE_NAMES = tuple(f"s{index}" for index in range(6))


@st.composite
def _graph_with_join(draw):
    """Draw an arbitrary directed step graph plus a join step and branch entries."""
    nodes = draw(st.lists(st.sampled_from(_NODE_NAMES), min_size=1, max_size=6, unique=True))
    graph: dict[str, tuple[str, ...]] = {}
    for node in nodes:
        successors = draw(st.lists(st.sampled_from(nodes), max_size=3, unique=True))
        graph[node] = tuple(successors)
    join_step = draw(st.sampled_from(nodes))
    branches = draw(st.lists(st.sampled_from(nodes), min_size=1, max_size=len(nodes), unique=True))
    return graph, tuple(branches), join_step


def _reference_branch_closure(
    graph: Mapping[str, tuple[str, ...]],
    branches: tuple[str, ...],
    join_step: str,
) -> frozenset[str]:
    """Independent fix-point reachability oracle for :func:`branch_closure`.

    Deliberately formulated as a monotone fix-point rather than the production
    DFS so agreement between the two is a genuine differential signal, not a
    restatement of the same traversal.
    """
    reachable = {node for node in branches if node != join_step}
    changed = True
    while changed:
        changed = False
        for node in list(reachable):
            for successor in graph.get(node, ()):
                if successor != join_step and successor not in reachable:
                    reachable.add(successor)
                    changed = True
    return frozenset(reachable)


class TestBranchClosureSemantics:
    @given(_graph_with_join())
    @settings(deadline=None)
    def test_matches_independent_reachability_oracle(self, payload):
        graph, branches, join_step = payload
        assert branch_closure(graph, branches=branches, join_step=join_step) == _reference_branch_closure(
            graph, branches, join_step
        )

    @given(_graph_with_join())
    @settings(deadline=None)
    def test_join_is_never_in_the_closure(self, payload):
        graph, branches, join_step = payload
        assert join_step not in branch_closure(graph, branches=branches, join_step=join_step)

    @given(_graph_with_join())
    @settings(deadline=None)
    def test_closure_is_closed_under_successors_except_join(self, payload):
        # Branch convergence: every successor of a closure node either is the
        # join (the single convergence point) or is itself inside the closure.
        graph, branches, join_step = payload
        closure = branch_closure(graph, branches=branches, join_step=join_step)
        for node in closure:
            for successor in graph.get(node, ()):
                assert successor == join_step or successor in closure

    @given(_graph_with_join(), st.lists(st.sampled_from(_NODE_NAMES), max_size=6, unique=True))
    @settings(deadline=None)
    def test_widening_branch_entries_grows_closure_monotonically(self, payload, extra):
        graph, branches, join_step = payload
        base = branch_closure(graph, branches=branches, join_step=join_step)
        widened = branch_closure(graph, branches=tuple({*branches, *extra}), join_step=join_step)
        assert base <= widened


# --------------------------------------------------------------------------- #
# validate_workflow_step_result: per-step result-envelope contract            #
# --------------------------------------------------------------------------- #

_OBSERVABLE_STEP_TYPES = ("objective", "retry", "parallel", "call")
_NON_OBSERVABLE_STEP_TYPES = ("end", "decision", "join", "start", "scaffold")
_ALL_STEP_TYPES = _OBSERVABLE_STEP_TYPES + _NON_OBSERVABLE_STEP_TYPES
_LIFECYCLES = ("pending", "running", "completed")


@st.composite
def _legal_step_state(draw):
    """Draw a (contract, lifecycle, outcome, attempts) tuple guaranteed legal."""
    step_type = draw(st.sampled_from(_ALL_STEP_TYPES))
    contract = workflow_step_semantic_contract(step_type)
    lifecycle = draw(st.sampled_from(_LIFECYCLES))
    outcome: str | None = None
    if lifecycle == "pending":
        attempts = 0
    elif lifecycle == "running":
        lower = 1 if contract.state_observable else 0
        upper = contract.fixed_attempts if contract.fixed_attempts is not None else 5
        attempts = draw(st.integers(min_value=lower, max_value=upper))
    else:  # completed
        if contract.state_observable:
            outcome = draw(st.sampled_from(contract.observable_outcomes))
        if contract.fixed_attempts is not None:
            attempts = contract.fixed_attempts
        else:
            attempts = draw(st.integers(min_value=0, max_value=5))
    return contract, lifecycle, outcome, attempts


@st.composite
def _arbitrary_step_state(draw):
    """Draw an unconstrained step state -- most are illegal in some way."""
    step_type = draw(st.sampled_from(_ALL_STEP_TYPES))
    contract = workflow_step_semantic_contract(step_type)
    lifecycle = draw(st.sampled_from((*_LIFECYCLES, "bogus")))
    outcome = draw(st.sampled_from((None, "succeeded", "failed", "exhausted", "weird")))
    attempts = draw(st.integers(min_value=-2, max_value=6))
    return contract, lifecycle, outcome, attempts


class TestStepResultContract:
    @given(_legal_step_state())
    @settings(deadline=None)
    def test_legal_states_report_no_violations(self, payload):
        contract, lifecycle, outcome, attempts = payload
        assert validate_workflow_step_result(contract, lifecycle=lifecycle, outcome=outcome, attempts=attempts) == ()

    @given(_arbitrary_step_state())
    @settings(deadline=None)
    def test_validation_is_deterministic(self, payload):
        contract, lifecycle, outcome, attempts = payload
        first = validate_workflow_step_result(contract, lifecycle=lifecycle, outcome=outcome, attempts=attempts)
        second = validate_workflow_step_result(contract, lifecycle=lifecycle, outcome=outcome, attempts=attempts)
        assert first == second

    @given(_arbitrary_step_state())
    @settings(deadline=None)
    def test_semantics_and_compiled_contract_wrapper_agree(self, payload):
        # Differential: the raes.semantics rule and the raes_contracts compiled
        # wrapper are two public surfaces that must stay in lock-step.
        contract, lifecycle, outcome, attempts = payload
        assert validate_workflow_step_result(
            contract, lifecycle=lifecycle, outcome=outcome, attempts=attempts
        ) == validate_workflow_step_result_contract(contract, lifecycle=lifecycle, outcome=outcome, attempts=attempts)

    @given(st.sampled_from(_NON_OBSERVABLE_STEP_TYPES), st.integers(max_value=-1))
    @settings(deadline=None)
    def test_negative_attempts_are_rejected(self, step_type, attempts):
        contract = workflow_step_semantic_contract(step_type)
        errors = validate_workflow_step_result(contract, lifecycle="completed", outcome=None, attempts=attempts)
        assert any("attempts must be >= 0" in error for error in errors)

    @given(st.sampled_from(_ALL_STEP_TYPES), st.integers(min_value=1, max_value=9))
    @settings(deadline=None)
    def test_pending_steps_must_report_zero_attempts(self, step_type, attempts):
        contract = workflow_step_semantic_contract(step_type)
        errors = validate_workflow_step_result(contract, lifecycle="pending", outcome=None, attempts=attempts)
        assert any("pending steps must report 0 attempts" in error for error in errors)

    @given(
        st.sampled_from(("pending", "running")),
        st.sampled_from(("succeeded", "failed", "exhausted")),
    )
    @settings(deadline=None)
    def test_non_completed_steps_may_not_report_an_outcome(self, lifecycle, outcome):
        contract = workflow_step_semantic_contract("retry")
        errors = validate_workflow_step_result(contract, lifecycle=lifecycle, outcome=outcome, attempts=1)
        assert any("non-completed steps may not report an outcome" in error for error in errors)

    def test_invalid_outcome_for_step_type_is_rejected(self):
        # 'exhausted' is legal for 'retry' but not for 'objective'.
        contract = workflow_step_semantic_contract("objective")
        errors = validate_workflow_step_result(contract, lifecycle="completed", outcome="exhausted", attempts=1)
        assert any("is invalid for step type 'objective'" in error for error in errors)

    def test_unknown_lifecycle_is_rejected(self):
        contract = workflow_step_semantic_contract("objective")
        errors = validate_workflow_step_result(contract, lifecycle="paused", outcome=None, attempts=0)
        assert any("lifecycle 'paused' is invalid" in error for error in errors)
