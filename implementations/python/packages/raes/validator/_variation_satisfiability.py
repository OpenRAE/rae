"""Deterministic finite satisfiability engine for SDL variation members."""

from __future__ import annotations

from dataclasses import dataclass

from raes_contracts.errors import OperationalError

from ..variation import VARIATION_SATISFIABILITY_STATE_LIMIT

_SelectionVariable = tuple[str, str]
_SelectionLiteral = tuple[_SelectionVariable, bool]


@dataclass(frozen=True)
class _SelectionGroup:
    members: tuple[_SelectionVariable, ...]
    minimum: int
    maximum: int


class _SelectionBudgetExceeded(OperationalError):
    pass


class _SelectionSatisfiability:
    def __init__(
        self,
        groups: list[_SelectionGroup],
        clauses: list[tuple[_SelectionLiteral, _SelectionLiteral]],
    ) -> None:
        self._groups = groups
        self._clauses = clauses
        self._variables = tuple(sorted(variable for group in groups for variable in group.members))
        self._remaining_states = VARIATION_SATISFIABILITY_STATE_LIMIT
        occurrence_count = dict.fromkeys(self._variables, 0)
        for clause in clauses:
            for variable, _value in clause:
                occurrence_count[variable] += 1
        self._branch_order = tuple(sorted(self._variables, key=lambda item: (-occurrence_count[item], item)))

    def has_witness(self, required: dict[_SelectionVariable, bool] | None = None) -> bool:
        assignments = dict(required or {})
        return self._search(assignments, seen=set())

    def _search(
        self,
        assignments: dict[_SelectionVariable, bool],
        *,
        seen: set[frozenset[tuple[_SelectionVariable, bool]]],
    ) -> bool:
        self._remaining_states -= 1
        if self._remaining_states < 0:
            raise _SelectionBudgetExceeded
        result = False
        if self._propagate(assignments):
            state = frozenset(assignments.items())
            if state not in seen:
                seen.add(state)
                variable = next((item for item in self._branch_order if item not in assignments), None)
                result = variable is None or self._branch_has_witness(variable, assignments, seen)
        return result

    def _branch_has_witness(
        self,
        variable: _SelectionVariable,
        assignments: dict[_SelectionVariable, bool],
        seen: set[frozenset[tuple[_SelectionVariable, bool]]],
    ) -> bool:
        for value in (True, False):
            branch = dict(assignments)
            branch[variable] = value
            if self._search(branch, seen=seen):
                return True
        return False

    def _propagate(self, assignments: dict[_SelectionVariable, bool]) -> bool:
        consistent = True
        changed = True
        while consistent and changed:
            consistent, changed = self._propagate_once(assignments)
        return consistent

    def _propagate_once(self, assignments: dict[_SelectionVariable, bool]) -> tuple[bool, bool]:
        consistent, clauses_changed = self._propagate_clauses(assignments)
        groups_changed = False
        if consistent:
            consistent, groups_changed = self._propagate_groups(assignments)
        return consistent, clauses_changed or groups_changed

    def _propagate_clauses(self, assignments: dict[_SelectionVariable, bool]) -> tuple[bool, bool]:
        consistent = True
        changed = False
        for clause in self._clauses:
            clause_consistent, clause_changed = self._propagate_clause(assignments, clause)
            if not clause_consistent:
                consistent = False
                break
            changed = changed or clause_changed
        return consistent, changed

    def _propagate_clause(
        self,
        assignments: dict[_SelectionVariable, bool],
        clause: tuple[_SelectionLiteral, _SelectionLiteral],
    ) -> tuple[bool, bool]:
        satisfied = any(assignments.get(variable) is value for variable, value in clause if variable in assignments)
        unassigned = [(variable, value) for variable, value in clause if variable not in assignments]
        consistent = satisfied or bool(unassigned)
        changed = False
        if consistent and not satisfied and len(unassigned) == 1:
            variable, value = unassigned[0]
            consistent = self._assign(assignments, variable, value)
            changed = consistent
        return consistent, changed

    def _propagate_groups(self, assignments: dict[_SelectionVariable, bool]) -> tuple[bool, bool]:
        consistent = True
        changed = False
        for group in self._groups:
            group_consistent, group_changed = self._propagate_group(assignments, group)
            if not group_consistent:
                consistent = False
                break
            changed = changed or group_changed
        return consistent, changed

    def _propagate_group(
        self,
        assignments: dict[_SelectionVariable, bool],
        group: _SelectionGroup,
    ) -> tuple[bool, bool]:
        selected = sum(assignments.get(member) is True for member in group.members)
        unknown = [member for member in group.members if member not in assignments]
        consistent = self._group_is_consistent(selected, len(unknown), group)
        changed = False
        forced_value = self._forced_group_value(selected, len(unknown), group) if consistent else None
        if forced_value is not None:
            for member in unknown:
                consistent = self._assign(assignments, member, forced_value)
                if not consistent:
                    break
                changed = True
        return consistent, changed

    @staticmethod
    def _group_is_consistent(selected: int, unknown: int, group: _SelectionGroup) -> bool:
        return selected <= group.maximum and selected + unknown >= group.minimum

    @staticmethod
    def _forced_group_value(selected: int, unknown: int, group: _SelectionGroup) -> bool | None:
        forced_value: bool | None = None
        if selected == group.maximum:
            forced_value = False
        elif selected + unknown == group.minimum:
            forced_value = True
        return forced_value

    @staticmethod
    def _assign(
        assignments: dict[_SelectionVariable, bool],
        variable: _SelectionVariable,
        value: bool,
    ) -> bool:
        if variable in assignments:
            return assignments[variable] is value
        assignments[variable] = value
        return True


__all__ = [
    "_SelectionBudgetExceeded",
    "_SelectionGroup",
    "_SelectionLiteral",
    "_SelectionSatisfiability",
    "_SelectionVariable",
]
