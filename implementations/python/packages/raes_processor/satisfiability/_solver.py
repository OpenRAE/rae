"""Pinned deterministic Z3 adapter for normalized finite-domain models."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from math import ceil
from typing import Literal

import z3
from raes_contracts.errors import OperationalError
from raes_contracts.satisfiability import NormalizedConstraintModel, SatisfiabilityOutcome

SOLVER_TIMEOUT_MS: Literal[5000] = 5000
_MAX_OPERATIONAL_REASON_CHARS = 256
_NANOSECONDS_PER_MILLISECOND = 1_000_000


def _monotonic_ns() -> int:
    return time.monotonic_ns()


class SolverOperationalError(OperationalError):
    """The pinned adapter could not produce a completed governed outcome."""

    def __init__(
        self,
        message: str,
        *,
        phase: str,
        check_count: int | None = None,
        check_budget: int | None = None,
        reason: str | None = None,
    ) -> None:
        self.phase = phase
        self.check_count = check_count
        self.check_budget = check_budget
        self.timeout_ms = SOLVER_TIMEOUT_MS
        self.reason = reason
        details = [f"phase={phase}", f"timeout_ms={SOLVER_TIMEOUT_MS}"]
        if check_count is not None and check_budget is not None:
            details.append(f"check={check_count}/{check_budget}")
        if reason is not None:
            details.append(f"reason={reason}")
        super().__init__(f"{message} ({', '.join(details)})")


@dataclass
class _CheckBudget:
    """Check-count and monotonic wall-time bounds for one solver operation."""

    max_checks: int
    checks_used: int = 0
    started_ns: int = field(default_factory=_monotonic_ns)
    deadline_ns: int = field(init=False)

    def __post_init__(self) -> None:
        self.deadline_ns = self.started_ns + SOLVER_TIMEOUT_MS * _NANOSECONDS_PER_MILLISECOND

    def checkpoint(self, phase: str, *, check_count: int | None = None) -> None:
        if _monotonic_ns() >= self.deadline_ns:
            raise SolverOperationalError(
                "solver operation deadline exhausted",
                phase=phase,
                check_count=self.checks_used if check_count is None else check_count,
                check_budget=self.max_checks,
                reason="operation-deadline-exhausted",
            )

    def remaining_timeout_ms(self, phase: str, *, check_count: int) -> int:
        remaining_ns = self.deadline_ns - _monotonic_ns()
        if remaining_ns <= 0:
            self.checkpoint(phase, check_count=check_count)
        return min(SOLVER_TIMEOUT_MS, max(1, ceil(remaining_ns / _NANOSECONDS_PER_MILLISECOND)))

    def consume(self, phase: str) -> int:
        self.checkpoint(phase)
        if self.checks_used >= self.max_checks:
            raise SolverOperationalError(
                "solver check budget exhausted",
                phase=phase,
                check_count=self.checks_used,
                check_budget=self.max_checks,
                reason="derived-check-budget-exhausted",
            )
        self.checks_used += 1
        return self.checks_used


@dataclass(frozen=True)
class SolverResult:
    outcome: SatisfiabilityOutcome
    assignment: dict[str, str | int | bool] | None = None
    core: tuple[str, ...] | None = None


def solve_model(model: NormalizedConstraintModel) -> SolverResult:
    """Solve one normalized model and select deterministic portable evidence."""

    started_ns = _monotonic_ns()
    budget = _solver_check_budget(model, started_ns=started_ns)
    _require_unique_clause_ids(model)
    all_clause_ids = tuple(clause.clause_id for clause in model.clauses)
    budget.checkpoint("model-validation", check_count=budget.checks_used)
    session = _SolverSession(model, budget)
    # ``_check`` fails loudly on ``z3.unknown``, so a non-satisfiable decision
    # here is decisively unsatisfiable rather than an incomplete timeout.
    if session.check(all_clause_ids, {}, phase="initial-decision") == z3.sat:
        result = SolverResult(
            outcome=SatisfiabilityOutcome.SATISFIABLE,
            assignment=_select_witness(model, all_clause_ids, session),
        )
    else:
        result = SolverResult(
            outcome=SatisfiabilityOutcome.UNSATISFIABLE,
            core=_reduce_unsat_core(all_clause_ids, session),
        )
    budget.checkpoint("result-selection", check_count=budget.checks_used)
    return result


def _require_unique_clause_ids(model: NormalizedConstraintModel) -> None:
    """Reject collapsed clause identity before tracked-assumption construction."""

    clause_ids = [clause.clause_id for clause in model.clauses]
    if len(set(clause_ids)) != len(clause_ids):
        raise SolverOperationalError(
            "normalized model contains duplicate clause ids",
            phase="model-validation",
            reason="duplicate-clause-id",
        )


def _solver_check_budget(
    model: NormalizedConstraintModel,
    *,
    started_ns: int | None = None,
) -> _CheckBudget:
    """Bound the two possible finite algorithms without a second profile knob."""

    witness_checks = sum(len(symbol.domain) for symbol in model.symbols)
    core_checks = len(model.clauses)
    return _CheckBudget(
        max_checks=1 + max(witness_checks, core_checks),
        started_ns=_monotonic_ns() if started_ns is None else started_ns,
    )


def _select_witness(
    model: NormalizedConstraintModel,
    all_clause_ids: tuple[str, ...],
    session: _SolverSession,
) -> dict[str, str | int | bool]:
    fixed: dict[str, int] = {}
    assignment: dict[str, str | int | bool] = {}
    for symbol in model.symbols:
        for index, value in enumerate(symbol.domain):
            candidate = {**fixed, symbol.symbol_id: index}
            if (
                session.check(
                    all_clause_ids,
                    candidate,
                    phase="witness-selection",
                )
                == z3.sat
            ):
                fixed[symbol.symbol_id] = index
                assignment[symbol.variable] = value
                break
        else:
            # This is guarded by the initial satisfiable result.
            raise SolverOperationalError(
                "deterministic witness selection failed",
                phase="witness-selection",
                check_count=session.budget.checks_used,
                check_budget=session.budget.max_checks,
                reason="no-feasible-domain-member-after-sat",
            )
    return assignment


def _reduce_unsat_core(
    all_clause_ids: tuple[str, ...],
    session: _SolverSession,
) -> tuple[str, ...]:
    core = list(all_clause_ids)
    for clause_id in all_clause_ids:
        candidate = tuple(item for item in core if item != clause_id)
        if session.check(candidate, {}, phase="core-reduction") == z3.unsat:
            core = list(candidate)
    return tuple(sorted(core))


class _SolverSession:
    """One incrementally queried expression graph for one normalized model."""

    def __init__(self, model: NormalizedConstraintModel, budget: _CheckBudget) -> None:
        self.budget = budget
        budget.checkpoint("model-construction", check_count=budget.checks_used)
        self.solver = z3.SolverFor("QF_LIA")
        self.solver.set(
            random_seed=0,
            timeout=SOLVER_TIMEOUT_MS,
            threads=1,
            auto_config=False,
            model=True,
            unsat_core=True,
        )
        self.variables: dict[str, z3.ArithRef] = {}
        for symbol in model.symbols:
            self.variables[symbol.symbol_id] = z3.Int(_z3_name(symbol.symbol_id))
            budget.checkpoint("model-construction", check_count=budget.checks_used)
        self.trackers: dict[str, z3.BoolRef] = {}
        symbols = {item.symbol_id: item for item in model.symbols}
        for clause in model.clauses:
            symbol = symbols[clause.symbol_id]
            indexes = []
            for index, value in enumerate(symbol.domain):
                if any(_scalar_equal(value, allowed) for allowed in clause.allowed_values):
                    indexes.append(index)
                budget.checkpoint("model-construction", check_count=budget.checks_used)
            expression = (
                z3.Or(*(self.variables[symbol.symbol_id] == index for index in indexes))
                if indexes
                else z3.BoolVal(False)
            )
            tracker = z3.Bool(_z3_name(clause.clause_id))
            self.trackers[clause.clause_id] = tracker
            self.solver.add(z3.Implies(tracker, expression))
            budget.checkpoint("model-construction", check_count=budget.checks_used)
        budget.checkpoint("model-construction", check_count=budget.checks_used)

    def check(
        self,
        clause_ids: tuple[str, ...],
        fixed: dict[str, int],
        *,
        phase: str,
    ) -> z3.CheckSatResult:
        check_count = self.budget.consume(phase)
        return self._check_consumed(clause_ids, fixed, phase=phase, check_count=check_count)

    def _check_consumed(
        self,
        clause_ids: tuple[str, ...],
        fixed: dict[str, int],
        *,
        phase: str,
        check_count: int,
    ) -> z3.CheckSatResult:
        assumptions = [self.trackers[clause_id] for clause_id in clause_ids]
        assumptions.extend(self.variables[symbol_id] == index for symbol_id, index in fixed.items())
        timeout_ms = self.budget.remaining_timeout_ms(phase, check_count=check_count)
        self.solver.set(timeout=timeout_ms)
        result = self.solver.check(*assumptions)
        self.budget.checkpoint(phase, check_count=check_count)
        if result == z3.unknown:
            reason = " ".join(self.solver.reason_unknown().split())[:_MAX_OPERATIONAL_REASON_CHARS] or "unspecified"
            raise SolverOperationalError(
                "solver returned unknown",
                phase=phase,
                check_count=check_count,
                check_budget=self.budget.max_checks,
                reason=reason,
            )
        return result


def _check(
    model: NormalizedConstraintModel,
    clause_ids: tuple[str, ...],
    fixed: dict[str, int],
    *,
    budget: _CheckBudget,
    phase: str,
) -> z3.CheckSatResult:
    """Compatibility seam for one governed probe; production reuses a session."""

    check_count = budget.consume(phase)
    session = _SolverSession(model, budget)
    return session._check_consumed(clause_ids, fixed, phase=phase, check_count=check_count)


def _scalar_equal(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _z3_name(value: str) -> str:
    return "raes_" + value.encode("utf-8").hex()
