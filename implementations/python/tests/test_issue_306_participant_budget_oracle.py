"""Differential oracle for SEM-223 participant budget accounting (issue #306).

Hypothesis drives random reserve, commit, release, and reset-reconcile sequences
through the production accounting functions. A small reference model follows
the FM3 state machine in ``specs/formal/participant-episode-model/README.md``
(T2 reset and T7-T10). It never imports the code under test. After every step
the oracle requires that:

* each dimension's reservation, use, and generation equal the reference model;
* admission is ``exhausted`` exactly when ``rem(d) <= 0`` (EBM-06);
* a reservation that does not fit ``rem(d)`` is a typed rejection with no other
  change, and admission is all-or-nothing across the vector (T7, T10);
* commit and release settle each reservation exactly once inside its own
  generation (T8, T9, EBM-08);
* a reset clears only the dimensions whose reset owner it crosses (T2, EBM-03);
  and
* the event stream passes the SEM-223 stream checks and stays append-only.

``test_traceability_table_covers_the_design_routed_invariants`` keeps the SEM-223
traceability table in ``specs/formal/participant-semantics/autonomous-execution.md``
in step with the issue #122 matrix and with the tests that exist.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from implementations.python.tests.test_issue_899_participant_resource_budgets import (
    _budget_policy_yaml,
    _capabilities,
)
from raes import parse_sdl
from raes_contracts.contracts.participant_resource_budgets import (
    ParticipantResourceBudgetStateModel,
    participant_resource_budget_state_ref,
)
from raes_contracts.participant_resource_exhaustion import (
    iter_participant_resource_budget_event_transition_violations,
    iter_participant_resource_budget_event_violations,
    participant_resource_admission_state,
    participant_resource_used,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.compiler import compile_runtime_model
from raes_runtime.participant_resource_accounting import (
    commit_participant_resource_reservation,
    reconcile_participant_resource_budgets,
    release_participant_resource_reservation,
)
from raes_runtime.participant_resource_budgets import (
    initialize_participant_resource_budgets,
    reserve_participant_resources,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DESIGN = REPO_ROOT / "specs/formal/participant-episode-model/README.md"
SEMANTICS = REPO_ROOT / "specs/formal/participant-semantics/autonomous-execution.md"
TEST_MODULES = (
    Path(__file__),
    Path(__file__).with_name("test_issue_306_participant_budget_exhaustion.py"),
    Path(__file__).with_name("test_issue_899_participant_resource_budgets.py"),
)
RESET_MODES = ("episode", "time_segment", "run", "reconciled")
EXHAUSTED = "runtime.participant-resource-exhausted"
STALE = "runtime.participant-resource-stale-generation"
SETTLED = "runtime.participant-resource-reservation-settled"
MISSING = "runtime.participant-resource-reservation-missing"
_GAUGES = frozenset({"reservable_gauge", "lease"})


def _oracle_policy():
    payload = yaml.safe_load(_budget_policy_yaml())
    dimensions = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]["resource_budget"][
        "dimensions"
    ]
    dimensions["participant-actions"].update(limit=3, reset="episode")
    dimensions["tokens"]["limit"] = 1500
    dimensions["images"]["limit"] = 2
    runtime_model = compile_runtime_model(parse_sdl(yaml.safe_dump(payload, sort_keys=False)))
    return next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )


POLICY = _oracle_policy()


@dataclass
class _Dimension:
    budget_id: str
    limit: int
    reset: str
    gauge: bool
    default: int
    used: int = 0
    reserved: int = 0

    def remaining(self) -> int:
        return self.limit - self.used - self.reserved


@dataclass
class _Reservation:
    quantities: dict[str, int]
    generation: int
    admitted: bool
    settlement: str | None = None


@dataclass
class _Model:
    """Reference accounting state machine, independent of the runtime code."""

    dimensions: dict[str, _Dimension]
    generation: int = 0
    reservations: list[_Reservation] = field(default_factory=list)

    def reserve(self, requested: dict[str, int]) -> list[str]:
        quantities = {
            budget_id: requested.get(budget_id, dimension.default) for budget_id, dimension in self.dimensions.items()
        }
        admitted = all(
            quantities[budget_id] <= dimension.remaining() for budget_id, dimension in self.dimensions.items()
        )
        self.reservations.append(_Reservation(quantities, self.generation, admitted))
        if not admitted:
            return [EXHAUSTED]
        for budget_id, dimension in self.dimensions.items():
            dimension.reserved += quantities[budget_id]
        return []

    def settle(self, index: int, verb: str, numerator: int) -> list[str]:
        reservation = self.reservations[index]
        if not reservation.admitted:
            return [MISSING] if verb == "commit" else []
        if reservation.settlement == verb:
            return []
        if reservation.generation != self.generation:
            return [STALE]
        if reservation.settlement is not None:
            return [SETTLED]
        reservation.settlement = verb
        for budget_id, dimension in self.dimensions.items():
            quantity = reservation.quantities[budget_id]
            dimension.reserved -= quantity
            if verb == "commit" and not dimension.gauge:
                dimension.used += quantity * numerator // 2
        return []

    def reconcile(self, crossed: frozenset[str]) -> list[str]:
        self.generation += 1
        for dimension in self.dimensions.values():
            dimension.reserved = 0
            if dimension.reset in crossed:
                dimension.used = 0
        return []


def _initial() -> tuple[RuntimeSnapshot, _Model]:
    initialized = initialize_participant_resource_budgets(
        RuntimeSnapshot(), (POLICY,), _capabilities(), execution_generation=0
    )
    assert initialized.success
    states = {
        demand.budget_id: ParticipantResourceBudgetStateModel.model_validate(
            initialized.snapshot.participant_resource_budget_states[
                participant_resource_budget_state_ref(POLICY.address, demand.budget_id)
            ]
        )
        for demand in POLICY.resource_demands
    }
    dimensions = {
        demand.budget_id: _Dimension(
            budget_id=demand.budget_id,
            limit=min(demand.limit, states[demand.budget_id].configured_capacity),
            reset=demand.reset,
            gauge=demand.accounting_mode in _GAUGES,
            default=demand.reservation,
        )
        for demand in POLICY.resource_demands
    }
    return initialized.snapshot, _Model(dimensions)


def _operation_id(index: int) -> str:
    return f"oracle-{index}"


def _runtime_settle(snapshot: RuntimeSnapshot, model: _Model, index: int, verb: str, numerator: int) -> ApplyResult:
    operation_id = _operation_id(index)
    if verb == "release":
        return release_participant_resource_reservation(
            snapshot,
            operation_id=operation_id,
            execution_generation=model.generation,
            evidence_refs=(f"evidence:{operation_id}:release",),
        )
    reserved = {
        str(event["budget_state_ref"]): int(event["requested"]) * numerator // 2
        for event in snapshot.participant_resource_budget_events.values()
        if event["operation_id"] == operation_id and event["transition"] == "reserve"
    }
    return commit_participant_resource_reservation(
        snapshot,
        operation_id=operation_id,
        execution_generation=model.generation,
        measured_quantities=reserved,
        evidence_refs=(f"evidence:{operation_id}:meter",),
    )


def _apply(snapshot: RuntimeSnapshot, model: _Model, operation: tuple) -> tuple[ApplyResult, list[str]]:
    kind = operation[0]
    if kind == "reserve":
        index = len(model.reservations)
        result = reserve_participant_resources(
            snapshot,
            POLICY,
            operation_id=_operation_id(index),
            execution_generation=model.generation,
            requested_quantities=operation[1],
        )
        return result, model.reserve(operation[1])
    if kind == "reconcile":
        crossed = frozenset(operation[1])
        result = reconcile_participant_resource_budgets(
            snapshot,
            policy_address=POLICY.address,
            current_generation=model.generation,
            next_generation=model.generation + 1,
            boundary=crossed,
            evidence_refs=(f"evidence:reset:{model.generation + 1}",),
        )
        return result, model.reconcile(crossed)
    index = operation[1] % len(model.reservations)
    numerator = operation[2] if kind == "commit" else 0
    return _runtime_settle(snapshot, model, index, kind, numerator), model.settle(index, kind, numerator)


def _assert_matches(previous: RuntimeSnapshot, snapshot: RuntimeSnapshot, model: _Model) -> None:
    for budget_id, dimension in model.dimensions.items():
        state = ParticipantResourceBudgetStateModel.model_validate(
            snapshot.participant_resource_budget_states[
                participant_resource_budget_state_ref(POLICY.address, budget_id)
            ]
        )
        assert (state.reserved, participant_resource_used(state), state.generation) == (
            dimension.reserved,
            0 if dimension.gauge else dimension.used,
            model.generation,
        ), budget_id
        assert participant_resource_admission_state(state) == ("open" if dimension.remaining() > 0 else "exhausted")
    events = snapshot.participant_resource_budget_events
    assert (
        list(iter_participant_resource_budget_event_violations(snapshot.participant_resource_budget_states, events))
        == []
    )
    assert (
        list(
            iter_participant_resource_budget_event_transition_violations(
                previous.participant_resource_budget_events, events
            )
        )
        == []
    )


_REQUESTED = st.fixed_dictionaries(
    {
        "participant-actions": st.integers(0, 2),
        "concurrency": st.integers(0, 1),
        "tokens": st.sampled_from((0, 250, 500, 1500)),
        "images": st.integers(0, 2),
    }
)
_OPERATION = st.one_of(
    st.tuples(st.just("reserve"), _REQUESTED),
    st.tuples(st.just("commit"), st.integers(0, 15), st.integers(0, 2)),
    st.tuples(st.just("release"), st.integers(0, 15)),
    st.tuples(st.just("reconcile"), st.sets(st.sampled_from(RESET_MODES), min_size=1)),
)


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(operations=st.lists(_OPERATION, min_size=1, max_size=10))
def test_accounting_matches_the_reference_state_machine(operations: list[tuple]) -> None:
    snapshot, model = _initial()
    for operation in operations:
        if operation[0] in {"commit", "release"} and not model.reservations:
            continue
        result, expected_codes = _apply(snapshot, model, operation)
        assert [diagnostic.code for diagnostic in result.diagnostics] == expected_codes, operation
        assert result.success is (not expected_codes), operation
        if expected_codes and operation[0] != "reserve":
            assert result.snapshot is snapshot, operation
        _assert_matches(snapshot, result.snapshot, model)
        snapshot = result.snapshot


def _design_routed_invariants() -> set[str]:
    """EBM ids that the issue #122 matrix routes to issue #306."""

    routed: set[str] = set()
    in_matrix = False
    for line in DESIGN.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_matrix = line.startswith("## Source-to-contract-to-test matrix")
        elif in_matrix and line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if "#306" in cells[-1]:
                routed.update(re.findall(r"EBM-\d{2}", cells[0]))
    return routed


def _sem223_cross_clause_invariants() -> set[str]:
    return {
        match.group(1)
        for line in DESIGN.read_text(encoding="utf-8").splitlines()
        if (match := re.match(r"\|\s*(EBM-\d{2})\s*\|", line)) and "SEM-223" in line
    }


def _traceability_rows() -> list[list[str]]:
    rows: list[list[str]] = []
    in_table = False
    for line in SEMANTICS.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            in_table = line.startswith("### SEM-223 Traceability")
        elif in_table and line.startswith("|") and not line.startswith("| ---"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows[1:]


def _defined_tests() -> set[str]:
    return {
        node.name
        for module in TEST_MODULES
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


def test_traceability_table_covers_the_design_routed_invariants() -> None:
    rows = _traceability_rows()
    covered = {invariant for row in rows for invariant in re.findall(r"EBM-\d{2}", row[1])}
    named_tests = {name for row in rows for cell in row[3:] for name in re.findall(r"`(test_[a-z0-9_]+)`", cell)}

    assert rows
    assert _design_routed_invariants() <= covered
    assert covered <= _sem223_cross_clause_invariants()
    assert named_tests
    assert named_tests <= _defined_tests()
    assert all(re.search(r"`test_", cell) for row in rows for cell in row[3:])
