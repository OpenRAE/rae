"""Role-allocation constants for the objective dependency partitioning decision."""

from __future__ import annotations

from ..objectives import ObjectiveDependencyRole

# Role allocation by reference category (single authority for the planner-
# facing decision). Success and depends_on order *and* refresh; window only
# refreshes; actor and target are empty today — they are normalized for
# fail-closed validation but the compiler does not propagate through them, so
# advertising a role here would lie about reaching the planner. A future
# change that compiles actor/target into runtime addresses lifts the constant
# in lockstep.
_BOTH_ROLES = (ObjectiveDependencyRole.ORDERING, ObjectiveDependencyRole.REFRESH)
OBJECTIVE_SUCCESS_DEPENDENCY_ROLES: tuple[ObjectiveDependencyRole, ...] = _BOTH_ROLES
OBJECTIVE_DEPENDENCY_DEPENDENCY_ROLES: tuple[ObjectiveDependencyRole, ...] = _BOTH_ROLES
OBJECTIVE_OWNER_DEPENDENCY_ROLES: tuple[ObjectiveDependencyRole, ...] = ()
OBJECTIVE_ASSIGNMENT_DEPENDENCY_ROLES: tuple[ObjectiveDependencyRole, ...] = ()
OBJECTIVE_ACTION_CONSTRAINT_DEPENDENCY_ROLES: tuple[ObjectiveDependencyRole, ...] = ()
OBJECTIVE_TARGET_DEPENDENCY_ROLES: tuple[ObjectiveDependencyRole, ...] = ()
OBJECTIVE_WINDOW_DEPENDENCY_ROLES: tuple[ObjectiveDependencyRole, ...] = (ObjectiveDependencyRole.REFRESH,)
