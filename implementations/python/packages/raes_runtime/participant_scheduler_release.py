"""Scheduler-side release checks for autonomous participants (issue #2020)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import ParticipantAutonomousExecutionRuntime

from .participant_release import ReleaseDisposition, participant_disposition, waiting_participant_addresses


def execution_service_accepts_work(service: ParticipantExecutionServiceStateModel) -> bool:
    """Return whether the policy execution service may start new work."""

    return service.observed_lifecycle == "running" and service.accepting_new_work and service.readiness == "ready"


def start_disposition(
    policy: ParticipantAutonomousExecutionRuntime,
    release_assertions: Mapping[str, tuple[str, ...]],
    snapshot: RuntimeSnapshot,
    participant_address: str,
) -> ReleaseDisposition:
    """Decide one native participant start: the service must accept work and the gate must release."""

    payload = snapshot.participant_execution_services.get(policy.address)
    if payload is None or not execution_service_accepts_work(
        ParticipantExecutionServiceStateModel.model_validate(payload)
    ):
        return ReleaseDisposition.WAITING
    return participant_disposition(release_assertions, snapshot, participant_address)


def release_pending(
    policies: Iterable[ParticipantAutonomousExecutionRuntime],
    release_assertions: Mapping[str, tuple[str, ...]],
    snapshot: RuntimeSnapshot,
) -> bool:
    """Return whether a scheduler pass can now release or refuse a waiting participant.

    A participant waits for release only while its service accepts work. An empty
    map, as before the participant start phase, never releases anyone.
    """

    return any(
        start_disposition(policy, release_assertions, snapshot, participant_address) is not ReleaseDisposition.WAITING
        for policy in policies
        for participant_address in waiting_participant_addresses(policy, snapshot)
    )


__all__ = ["execution_service_accepts_work", "release_pending", "start_disposition"]
