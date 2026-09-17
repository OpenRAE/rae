"""Cross-record authority joins for execution-service snapshot projections."""

from collections.abc import Mapping

from .participant_execution import ParticipantExecutionServiceStateModel
from .participant_resource_budgets import ParticipantResourceBudgetStateModel


def validate_execution_service_budget_projection(
    services: Mapping[str, ParticipantExecutionServiceStateModel],
    budget_states: Mapping[str, ParticipantResourceBudgetStateModel],
) -> None:
    budget_refs = set(budget_states)
    for service in services.values():
        missing = sorted(set(service.resource_budget_state_refs) - budget_refs)
        if missing:
            raise ValueError(
                "Participant execution service references missing resource-budget states: " + ", ".join(missing)
            )
        concurrency = [
            budget_states[budget_ref]
            for budget_ref in service.resource_budget_state_refs
            if budget_states[budget_ref].resource_kind == "concurrent_actions"
        ]
        if not concurrency:
            continue
        if len(concurrency) != 1:
            raise ValueError(
                "Participant execution service must reference exactly one authoritative concurrency budget"
            )
        authoritative = concurrency[0]
        projection = (service.capacity, service.reserved, service.in_flight)
        authority = (authoritative.limit, authoritative.reserved, authoritative.current_use)
        if projection != authority:
            raise ValueError(
                "Participant execution service concurrency projection must "
                "equal its authoritative resource-budget state"
            )
