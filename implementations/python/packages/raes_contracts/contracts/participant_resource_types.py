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
}
RESOURCE_ACCOUNTING = {
    "action_rate": {"windowed_counter"},
    "concurrent_actions": {"reservable_gauge"},
    "storage_growth": {"growth_counter"},
    "inference_tokens": {"windowed_counter", "cumulative_counter"},
    "image_generations": {"windowed_counter", "cumulative_counter"},
    "accelerator": {"lease"},
}
EVENT_DISPOSITION = {
    "reserve": "reserved",
    "commit": "committed",
    "release": "released",
    "throttle": "throttled",
    "reject": "rejected",
    "reconcile": "reconciled",
}


def require_quantity_semantics(
    resource_kind: str | DomainProfileCoordinateModel,
    unit: str,
    accounting_mode: str,
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
    "RESOURCE_ACCOUNTING",
    "RESOURCE_UNIT",
    "participant_resource_budget_state_ref",
    "participant_resource_pool_state_ref",
    "require_quantity_semantics",
]
