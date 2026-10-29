"""Explicit caller-owned coordinates for a reusable control application."""

from typing import Literal

from pydantic import ConfigDict
from raes_contracts.contracts.base import ContractModel
from raes_contracts.contracts.participant_control_coordinates import ControlCount, ControlRef


class ParticipantControlApplicationCoordinates(ContractModel):
    """An attempted application; no field supplies trusted policy or grant authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    semantics: Literal["mixed-control-policy-occurrence/rev1"]
    policy_ref: ControlRef
    prior_state_ref: ControlRef
    expected_history_head: ControlCount
    effective_order: ControlCount
    script_step_ref: ControlRef | None = None
