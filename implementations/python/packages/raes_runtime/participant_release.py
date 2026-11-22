"""Release autonomous participants when their starting assertions are true (issue #2020).

A participant's ``starting_assertions`` are its release condition. The backend
reports their truth through its evaluator role. Only an admitted result with a
``true`` assertion outcome releases; missing evidence never becomes true.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from raes_contracts.contracts import PropositionTruthOutcome
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import ParticipantAutonomousExecutionRuntime, RuntimeModel

from .proposition_truth_contracts import admitted_truth_result

WAITING_CODE = "runtime.participant-release-waiting"
UNSUPPORTED_CODE = "runtime.participant-release-unsupported"


class ReleaseDisposition(Enum):
    """Whether a participant may start now."""

    RELEASED = "released"
    WAITING = "waiting"
    UNSUPPORTED = "unsupported"


def participant_release_assertions(model: RuntimeModel) -> dict[str, tuple[str, ...]]:
    """Map each participant behavior address to its starting assertion addresses."""

    return {
        behavior.address: behavior.starting_assertion_addresses for behavior in model.participant_behaviors.values()
    }


def setup_release_assertions(model: RuntimeModel) -> dict[str, tuple[str, ...]]:
    """Map only participants without starting assertions; setup starts no gated participant."""

    return {address: () for address, assertions in participant_release_assertions(model).items() if not assertions}


def release_disposition(snapshot: RuntimeSnapshot, assertion_addresses: tuple[str, ...]) -> ReleaseDisposition:
    """Decide release from the current admitted truth results."""

    disposition = ReleaseDisposition.RELEASED
    for address in assertion_addresses:
        result, _ = admitted_truth_result(snapshot, address, snapshot.proposition_truth_results.get(address))
        if result is not None and result.assertion_outcome is PropositionTruthOutcome.UNSUPPORTED:
            return ReleaseDisposition.UNSUPPORTED
        if result is None or result.assertion_outcome is not PropositionTruthOutcome.TRUE:
            disposition = ReleaseDisposition.WAITING
    return disposition


def participant_disposition(
    release_assertions: Mapping[str, tuple[str, ...]], snapshot: RuntimeSnapshot, participant_address: str
) -> ReleaseDisposition:
    """Decide release for one participant; an unmapped participant waits."""

    assertions = release_assertions.get(participant_address)
    if assertions is None:
        return ReleaseDisposition.WAITING
    return release_disposition(snapshot, assertions)


def released_participant_addresses(
    policy: ParticipantAutonomousExecutionRuntime, snapshot: RuntimeSnapshot
) -> tuple[str, ...]:
    """Return the policy participants that the gate released; they have scheduler state."""

    states = snapshot.participant_autonomous_execution_states
    return tuple(address for address in policy.participant_addresses if f"{policy.address}.state.{address}" in states)


def waiting_participant_addresses(
    policy: ParticipantAutonomousExecutionRuntime, snapshot: RuntimeSnapshot
) -> tuple[str, ...]:
    """Return the policy participants that still wait for release."""

    released = set(released_participant_addresses(policy, snapshot))
    return tuple(address for address in policy.participant_addresses if address not in released)


def release_diagnostic(disposition: ReleaseDisposition, policy_address: str, participant_address: str) -> Diagnostic:
    """Describe a participant that the gate holds, with addresses only."""

    if disposition is ReleaseDisposition.UNSUPPORTED:
        return Diagnostic(
            code=UNSUPPORTED_CODE,
            domain="participant",
            address=f"{policy_address}.state.{participant_address}",
            message="A starting assertion of the participant has an unsupported truth outcome.",
        )
    return Diagnostic(
        code=WAITING_CODE,
        domain="participant",
        address=f"{policy_address}.state.{participant_address}",
        message="The participant waits until every starting assertion is true.",
        severity=Severity.INFO,
    )


__all__ = [
    "UNSUPPORTED_CODE",
    "WAITING_CODE",
    "ReleaseDisposition",
    "participant_disposition",
    "participant_release_assertions",
    "release_diagnostic",
    "released_participant_addresses",
    "waiting_participant_addresses",
    "release_disposition",
    "setup_release_assertions",
]
