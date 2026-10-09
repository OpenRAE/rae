"""Shared participant resource-budget literals, identities, and quantity rules."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from ..domain_profiles import DomainProfileCoordinateModel

PARTICIPANT_RESOURCE_BUDGET_POLICY_SCHEMA_VERSION = "participant-resource-budget-policy/v1"
PARTICIPANT_RESOURCE_POOL_CAPACITY_SCHEMA_VERSION = "participant-resource-pool-capacity/v1"
PARTICIPANT_RESOURCE_BUDGET_STATE_SCHEMA_VERSION = "participant-resource-budget-state/v1"
PARTICIPANT_RESOURCE_BUDGET_EVENT_SCHEMA_VERSION = "participant-resource-budget-event/v1"

ParticipantResourceOwnerKind = Literal[
    "participant",
    "deployment_tenant",
    "shared_service",
    "fleet",
]
ParticipantResourceKind = (
    Literal[
        "action_rate",
        "concurrent_actions",
        "storage_growth",
        "inference_tokens",
        "image_generations",
        "accelerator",
        "interaction_steps",
        "interaction_turns",
        "tool_invocations",
        "scenario_time",
    ]
    | DomainProfileCoordinateModel
)
ParticipantResourceAccountingMode = Literal[
    "windowed_counter",
    "cumulative_counter",
    "reservable_gauge",
    "growth_counter",
    "lease",
]
ParticipantResourceResetMode = Literal["episode", "time_segment", "run", "reconciled"]
ParticipantResourceIsolationStrength = Literal["none", "stateless", "tenant_partitioned"]

RESOURCE_UNIT = {
    "action_rate": "actions",
    "concurrent_actions": "actions",
    "storage_growth": "bytes",
    "inference_tokens": "tokens",
    "image_generations": "images",
    "accelerator": "accelerator_milliseconds",
    "interaction_steps": "steps",
    "interaction_turns": "turns",
    "tool_invocations": "invocations",
    "scenario_time": "ticks",
}
RESOURCE_ACCOUNTING = {
    "action_rate": {"windowed_counter"},
    "concurrent_actions": {"reservable_gauge"},
    "storage_growth": {"growth_counter"},
    "inference_tokens": {"windowed_counter", "cumulative_counter"},
    "image_generations": {"windowed_counter", "cumulative_counter"},
    "accelerator": {"lease"},
    "interaction_steps": {"windowed_counter", "cumulative_counter"},
    "interaction_turns": {"windowed_counter", "cumulative_counter"},
    "tool_invocations": {"windowed_counter", "cumulative_counter"},
    "scenario_time": {"cumulative_counter"},
}
# Every v3 policy declares the complete ADR-097 vector. DSL-121 interaction
# dimensions extend the governed catalog and are optional members of it.
REQUIRED_RESOURCE_KINDS = frozenset(
    {
        "action_rate",
        "concurrent_actions",
        "storage_growth",
        "inference_tokens",
        "image_generations",
        "accelerator",
    }
)
# Logical scenario time is the elapsed ticks of the governing shared clock,
# metered by RAES as the shared-time authority. Host or watchdog time is never
# a scenario quota. Elapsed time is relative to a shared-clock boundary, so a
# scenario-time dimension resets per time segment or per run (DSL-121).
SCENARIO_TIME_RESOURCE_KIND = "scenario_time"
SCENARIO_TIME_METER_PROFILE = "raes.shared-time-ticks/v1"
_SCENARIO_TIME_RESETS = frozenset({"time_segment", "run"})
EVENT_DISPOSITION = {
    "reserve": "reserved",
    "commit": "committed",
    "release": "released",
    "throttle": "throttled",
    "reject": "rejected",
    "reconcile": "reconciled",
}


def require_scenario_time_meter(resource_kind: str | DomainProfileCoordinateModel, meter_profile_ref: str) -> None:
    """Reject a scenario-time quantity metered by anything but the shared-time authority."""

    if resource_kind == SCENARIO_TIME_RESOURCE_KIND and meter_profile_ref != SCENARIO_TIME_METER_PROFILE:
        raise ValueError(
            f"scenario_time resource quantity requires meter {SCENARIO_TIME_METER_PROFILE!r}; "
            "host or watchdog time is not scenario time"
        )


def require_quantity_semantics(
    resource_kind: str | DomainProfileCoordinateModel,
    unit: str,
    accounting_mode: str,
    meter_profile_ref: str,
) -> None:
    if isinstance(resource_kind, DomainProfileCoordinateModel):
        # Extension shape is portable data. Exact unit/meter/reset semantics
        # require independent profile admission against the configured pool.
        return
    expected_unit = RESOURCE_UNIT[resource_kind]
    if unit != expected_unit:
        raise ValueError(f"{resource_kind} resource quantity requires unit {expected_unit!r}")
    if accounting_mode not in RESOURCE_ACCOUNTING[resource_kind]:
        raise ValueError(f"{resource_kind} resource quantity does not support accounting mode {accounting_mode!r}")
    require_scenario_time_meter(resource_kind, meter_profile_ref)


def require_demand_semantics(
    resource_kind: str | DomainProfileCoordinateModel,
    reset: str,
    scope_refs: tuple[str, ...] | list[str],
    *,
    scope_field: str = "action_contract_refs",
) -> None:
    """Check the reset basis and tool scope a dimension's kind requires (DSL-121).

    ``scope_field`` names the scope in the caller's surface: the published demand
    scopes a tool budget by action contract, the authored dimension by tool
    affordance.
    """

    if resource_kind == SCENARIO_TIME_RESOURCE_KIND and reset not in _SCENARIO_TIME_RESETS:
        raise ValueError("scenario_time resource budget requires a time_segment or run reset")
    if (resource_kind == "tool_invocations") != bool(scope_refs):
        raise ValueError(f"tool_invocations resource budgets require {scope_field} and other kinds forbid them")
    if len(scope_refs) != len(set(scope_refs)):
        raise ValueError(f"resource budget {scope_field} must be unique")


def participant_resource_budget_state_ref(policy_address: str, budget_id: str) -> str:
    """Return the globally stable identity of one policy-local budget state."""

    return f"{policy_address}.resource-budget-state.{budget_id}"


def participant_resource_pool_state_ref(
    *,
    pool_ref: str,
    owner_kind: str,
    owner_ref: str,
    resource_kind: str,
    unit: str,
    accounting_mode: str,
    meter_profile_ref: str,
) -> str:
    """Return the stable identity of one exact physical accounting pool."""

    canonical = json.dumps(
        (
            pool_ref,
            owner_kind,
            owner_ref,
            resource_kind.model_dump(mode="json")
            if isinstance(resource_kind, DomainProfileCoordinateModel)
            else resource_kind,
            unit,
            accounting_mode,
            meter_profile_ref,
        ),
        separators=(",", ":"),
    )
    return "participant-resource-pool:sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "EVENT_DISPOSITION",
    "PARTICIPANT_RESOURCE_BUDGET_EVENT_SCHEMA_VERSION",
    "PARTICIPANT_RESOURCE_BUDGET_POLICY_SCHEMA_VERSION",
    "PARTICIPANT_RESOURCE_BUDGET_STATE_SCHEMA_VERSION",
    "PARTICIPANT_RESOURCE_POOL_CAPACITY_SCHEMA_VERSION",
    "ParticipantResourceAccountingMode",
    "ParticipantResourceIsolationStrength",
    "ParticipantResourceKind",
    "ParticipantResourceOwnerKind",
    "ParticipantResourceResetMode",
    "REQUIRED_RESOURCE_KINDS",
    "RESOURCE_ACCOUNTING",
    "RESOURCE_UNIT",
    "SCENARIO_TIME_METER_PROFILE",
    "SCENARIO_TIME_RESOURCE_KIND",
    "participant_resource_budget_state_ref",
    "participant_resource_pool_state_ref",
    "require_demand_semantics",
    "require_quantity_semantics",
    "require_scenario_time_meter",
]
