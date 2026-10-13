"""Shared ACT-617 mixed-control vocabulary for the legacy and rev1 policy forms.

The legacy fixed-coordinate form and the ``mixed-control-policy-occurrence/rev1``
form reuse these enums and the controller-state binding rather than copying them.
API-409 contracts re-export :class:`ParticipantControlTargetKind` from here, so
the SDL and the occurrence carriers share one target vocabulary.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field, StrictInt, field_validator, model_validator

from ._base import SDLModel

MIXED_CONTROL_COORDINATE_LIMIT = 1_000_000
"""MC-08 range bound shared with API-424 ``ControlCount`` (a test pins the two)."""


_PRESENT = object()


def omit_property_titles(schema: dict[str, Any]) -> None:
    """Drop generated property titles and null defaults from a published rev1 shape.

    Both are annotations with no validation effect. Omitting them keeps the
    self-contained materialized-scenario schema inside its publication budget.
    """

    for value in schema.get("properties", {}).values():
        if isinstance(value, dict):
            value.pop("title", None)
            if value.get("default", _PRESENT) is None:
                del value["default"]


class MixedControlOrderStrategy(str, Enum):
    """Portable ordering strategies for authored control decisions."""

    TOTAL_EFFECTIVE_ORDER = "total-effective-order"


class MixedControlTransitionKind(str, Enum):
    """Control-owned facts kept distinct from admission and execution."""

    PROPOSAL = "proposal"
    APPROVAL = "approval"
    DENIAL = "denial"
    EXTERNAL_DIRECTION = "external-direction"
    INTERVENTION = "intervention"
    HANDOFF = "handoff"
    OVERRIDE = "override"
    CANCELLATION = "cancellation"


class MixedControlAuthorityStatus(str, Enum):
    """Authored authority state for one controller binding."""

    ACTIVE = "active"
    REVOKED = "revoked"


class MixedControlDuplicateDisposition(str, Enum):
    """Disposition for a repeated decision identity."""

    IDEMPOTENT_IF_EQUIVALENT = "idempotent-if-equivalent"


class MixedControlRejectDisposition(str, Enum):
    """Fail-closed disposition that preserves the current state."""

    REJECT_NO_STATE_CHANGE = "reject-no-state-change"


class MixedControlConcurrentDisposition(str, Enum):
    """Disposition for decisions that share a control-state revision."""

    ORDER_THEN_REVALIDATE = "order-then-revalidate"


class MixedControlDispositionRules(SDLModel):
    """Explicit deterministic rules for invalid or competing decisions."""

    duplicate: MixedControlDuplicateDisposition
    stale: MixedControlRejectDisposition
    revoked: MixedControlRejectDisposition
    late: MixedControlRejectDisposition
    concurrent: MixedControlConcurrentDisposition
    conflict: MixedControlRejectDisposition


class MixedControlControllerState(SDLModel):
    """One authored controller, authority, scope, and validity binding."""

    controller_ref: str
    authority_basis_refs: list[str]
    scope_refs: list[str]
    policy_revision: str
    valid_from_order: StrictInt = Field(ge=0)
    valid_until_order: StrictInt = Field(ge=0)
    authority_status: MixedControlAuthorityStatus
    evidence_refs: list[str]

    @field_validator("controller_ref", "policy_revision")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mixed-control controller-state fields must be non-empty")
        return value

    @field_validator("authority_basis_refs", "scope_refs", "evidence_refs")
    @classmethod
    def _require_unique_non_empty_refs(cls, values: list[str]) -> list[str]:
        if not values or any(not value.strip() for value in values):
            raise ValueError("mixed-control controller-state refs must be non-empty")
        if len(set(values)) != len(values):
            raise ValueError("mixed-control controller-state refs must be unique")
        return values

    @model_validator(mode="after")
    def _validate_interval(self) -> MixedControlControllerState:
        if self.valid_until_order < self.valid_from_order:
            raise ValueError("mixed-control controller-state validity interval must not be inverted")
        return self


class ParticipantControlTargetKind(str, Enum):
    """Closed kinds for typed API-409 target relations."""

    PROPOSAL = "proposal"
    ACTION = "action"
    CONTROL = "control"
    DECISION = "decision"
    ADMITTED_ACTION = "admitted-action"
    ATTEMPT = "attempt"
