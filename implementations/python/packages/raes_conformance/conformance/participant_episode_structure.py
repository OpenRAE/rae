"""Participant episode-structure conformance (ACT-623).

A behavior specification's compiled episode policy is the first-class episode
structure of every participant it selects. These diagnostics compare recorded
ADR-013 episode history for those participants with that structure: a realized
terminal reason must come from an authored condition unless the stop was an
externally induced interruption, and a recorded reset or restart must be one the
reset policy admits. Snapshot integrity itself stays with
``iter_participant_episode_snapshot_violations``; nothing here evaluates an
authored condition or claims that a backend enforces the policy.
"""

from __future__ import annotations

from collections.abc import Mapping

from raes_contracts.diagnostics import Diagnostic
from raes_processor.models import ParticipantEpisodePolicyRuntime
from raes_processor.models.participant_episode_validation import participant_episode_history_policy_violations

from raes_conformance.conformance.diagnostics import (
    _PARTICIPANT_EPISODE_STRUCTURE_INVALID_DIAGNOSTIC_CODE,
    _diagnostic,
)

_HISTORY_KEY = "runtime.snapshot.participant-episode-history"


def participant_episode_structure_conformance_diagnostics(
    policies: Mapping[str, ParticipantEpisodePolicyRuntime],
    participant_episode_history: Mapping[str, object],
) -> tuple[Diagnostic, ...]:
    """Return ACT-623 diagnostics for recorded episodes that contradict their authored structure."""

    governing: dict[str, list[ParticipantEpisodePolicyRuntime]] = {}
    for policy in policies.values():
        for participant_address in policy.participant_addresses:
            governing.setdefault(participant_address, []).append(policy)
    diagnostics: list[Diagnostic] = []
    for participant_address, governed_by in sorted(governing.items()):
        address = f"{_HISTORY_KEY}.{participant_address}"
        if len(governed_by) > 1:
            joined = ", ".join(sorted(policy.address for policy in governed_by))
            diagnostics.append(
                _diagnostic(
                    _PARTICIPANT_EPISODE_STRUCTURE_INVALID_DIAGNOSTIC_CODE,
                    address,
                    f"participant is governed by more than one episode policy: {joined}",
                )
            )
            continue
        diagnostics.extend(
            _diagnostic(_PARTICIPANT_EPISODE_STRUCTURE_INVALID_DIAGNOSTIC_CODE, f"{address}[{index}]", message)
            for index, message in participant_episode_history_policy_violations(
                governed_by[0], participant_episode_history.get(participant_address)
            )
        )
    return tuple(diagnostics)


__all__ = ["participant_episode_structure_conformance_diagnostics"]
