"""Executable invariant oracle for SEM-222 episode/termination semantics.

This module is the executable realization of the SEM-222-owned cross-clause
invariants published in ``specs/formal/participant-episode-model/README.md``.
Per that design's source-to-contract-to-test matrix, issue #305 (SEM-222) owns
the episode facets of **EBM-02** (distinct terminal reasons), **EBM-03** (reset
generation + lineage), **EBM-08** (ordered, generation-fenced, append-only
history), and **EBM-10** (RL termination/truncation closure record). The
budget-domain facets (EBM-06 and the budget parts of EBM-03/08) and the authored
intent facet (EBM-01) are owned by #306/#307 and are out of scope here.

Unlike a pure self-consistency oracle, every predicate here runs the **real**
ADR-013 / SEM-222 production validators
(``iter_participant_episode_snapshot_violations`` and
``iter_participant_episode_closure_violations``) over a test-local episode
progression, so a green run exercises the shipped enforcement code rather than a
parallel re-encoding.

Two things are checked about the encoding:

* **Spec sync** — the catalog stays in lock-step with the design document: every
  cataloged invariant is a real SEM-222-tagged row of the cross-clause invariant
  table, and the catalog is exactly the set of EBM invariants the design's
  source-to-contract-to-test matrix routes to issue #305
  (``test_catalog_matches_design_ownership``).
* **Discrimination** — ``test_canonical_progression_satisfies_all_invariants``
  is the positive control and ``test_each_invariant_rejects_its_targeted_mutation``
  is the negative control, so each predicate proves a real True -> False flip.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from raes_contracts.participant_episode_closure import (
    PARTICIPANT_EPISODE_CLOSURE_SIGNAL_TERMINAL_REASONS,
    ParticipantEpisodeClosureRecord,
    ParticipantEpisodeClosureSignal,
    iter_participant_episode_closure_violations,
)
from raes_contracts.participant_episode_snapshot import iter_participant_episode_snapshot_violations

SPEC_PATH = Path(__file__).resolve().parents[3] / "specs/formal/participant-episode-model/README.md"
_OWNER_ISSUE = "#305"

_ADDRESS = "scenario/participant/agent-0"


@dataclass(frozen=True)
class EpisodeProgression:
    """A test-local participant-episode progression as runtime snapshot data."""

    results: dict[str, dict[str, object]]
    history: dict[str, list[dict[str, object]]]
    closures: dict[str, list[dict[str, object]]]


def canonical_progression() -> EpisodeProgression:
    """A spec-conforming two-generation progression with valid closure records.

    Generation 0 (episode ``E0``, sequence 0) is externally truncated; a reset
    then opens generation 1 (episode ``E1``, sequence 1) which completes. Each
    realized terminal reason carries a governed, evidence-bearing closure record.
    """

    history = {
        _ADDRESS: [
            {
                "event_type": "episode_initialized",
                "timestamp": "2026-01-01T00:00:00Z",
                "participant_address": _ADDRESS,
                "episode_id": "E0",
                "sequence_number": 0,
                "control_action": "initialize",
            },
            {
                "event_type": "episode_truncated",
                "timestamp": "2026-01-01T00:05:00Z",
                "participant_address": _ADDRESS,
                "episode_id": "E0",
                "sequence_number": 0,
                "terminal_reason": "truncated",
            },
            {
                "event_type": "episode_reset",
                "timestamp": "2026-01-01T00:06:00Z",
                "participant_address": _ADDRESS,
                "episode_id": "E1",
                "sequence_number": 1,
                "control_action": "reset",
            },
            {
                "event_type": "episode_completed",
                "timestamp": "2026-01-01T00:09:00Z",
                "participant_address": _ADDRESS,
                "episode_id": "E1",
                "sequence_number": 1,
                "terminal_reason": "completed",
            },
        ]
    }
    results = {
        _ADDRESS: {
            "state_schema_version": "participant-episode-state/v1",
            "participant_address": _ADDRESS,
            "episode_id": "E1",
            "sequence_number": 1,
            "status": "terminated",
            "terminal_reason": "completed",
            "initialized_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:09:00Z",
            "terminated_at": "2026-01-01T00:09:00Z",
            "last_control_action": "reset",
            "previous_episode_id": "E0",
        }
    }
    closures = {
        _ADDRESS: [
            {
                "participant_address": _ADDRESS,
                "episode_id": "E0",
                "sequence_number": 0,
                "source_signal": "rl_truncation",
                "mapped_terminal_reason": "truncated",
                "deriving_authority": "runtime.participant-episode-closure",
                "evidence_refs": ["evidence://step-signal/E0"],
                "derived_at": "2026-01-01T00:05:00Z",
            },
            {
                "participant_address": _ADDRESS,
                "episode_id": "E1",
                "sequence_number": 1,
                "source_signal": "rl_termination",
                "mapped_terminal_reason": "completed",
                "deriving_authority": "runtime.participant-episode-closure",
                "evidence_refs": ["evidence://step-signal/E1"],
                "derived_at": "2026-01-01T00:09:00Z",
            },
        ]
    }
    return EpisodeProgression(results=results, history=history, closures=closures)


def _snapshot_violations(state: EpisodeProgression) -> list[tuple[str, str]]:
    return list(iter_participant_episode_snapshot_violations(state.results, state.history))


def _closure_violations(state: EpisodeProgression) -> list[tuple[str, str]]:
    return list(iter_participant_episode_closure_violations(state.closures, state.history))


def _closures_normalize(state: EpisodeProgression) -> bool:
    for records in state.closures.values():
        for payload in records:
            try:
                ParticipantEpisodeClosureRecord.from_payload(payload)
            except TypeError, ValueError:
                return False
    return True


def _signal_reason_sets_are_distinct() -> bool:
    termination = PARTICIPANT_EPISODE_CLOSURE_SIGNAL_TERMINAL_REASONS[ParticipantEpisodeClosureSignal.RL_TERMINATION]
    truncation = PARTICIPANT_EPISODE_CLOSURE_SIGNAL_TERMINAL_REASONS[ParticipantEpisodeClosureSignal.RL_TRUNCATION]
    return not (termination & truncation)


# --- Predicates: True iff the progression satisfies the invariant. ---


def _p_ebm02(state: EpisodeProgression) -> bool:
    # Distinct terminal reasons: every closure obeys the governed signal->reason
    # mapping and the two RL signals never collapse onto a shared reason, so
    # truncation is never aliased to a termination reason.
    return _closures_normalize(state) and _signal_reason_sets_are_distinct()


def _p_ebm03(state: EpisodeProgression) -> bool:
    # Reset generation + lineage: reset/restart advance the generation, carry a
    # distinct previous_episode_id, and never rewrite the history head. The
    # ADR-013 contract surface is the enforcement point.
    return not _snapshot_violations(state)


def _p_ebm08(state: EpisodeProgression) -> bool:
    # Ordered, generation-fenced, append-only: episode history sequence is
    # monotonic and closure facts are fenced to an existing generation.
    return not _snapshot_violations(state) and not _closure_violations(state)


def _p_ebm10(state: EpisodeProgression) -> bool:
    # RL closure record: an RL signal relates to an episode terminal reason only
    # through a closure record that matches a realized terminal event.
    return not _closure_violations(state)


# --- Mutations: each returns a progression that violates its own invariant. ---


def _mutate_ebm02(state: EpisodeProgression) -> EpisodeProgression:
    closures = copy.deepcopy(state.closures)
    closures[_ADDRESS][0]["source_signal"] = "rl_truncation"
    closures[_ADDRESS][0]["mapped_terminal_reason"] = "completed"
    return replace(state, closures=closures)


def _mutate_ebm03(state: EpisodeProgression) -> EpisodeProgression:
    results = copy.deepcopy(state.results)
    results[_ADDRESS]["previous_episode_id"] = results[_ADDRESS]["episode_id"]
    return replace(state, results=results)


def _mutate_ebm08(state: EpisodeProgression) -> EpisodeProgression:
    history = copy.deepcopy(state.history)
    history[_ADDRESS] = list(reversed(history[_ADDRESS]))
    return replace(state, history=history)


def _mutate_ebm10(state: EpisodeProgression) -> EpisodeProgression:
    closures = copy.deepcopy(state.closures)
    # rl_truncation -> timed_out is governed, so the record constructs, but the
    # realized head is 'truncated', so the asserted relation is rejected.
    closures[_ADDRESS][0]["mapped_terminal_reason"] = "timed_out"
    return replace(state, closures=closures)


@dataclass(frozen=True)
class Invariant:
    invariant_id: str
    predicate: Callable[[EpisodeProgression], bool]
    mutate: Callable[[EpisodeProgression], EpisodeProgression]


INVARIANTS = (
    Invariant("EBM-02", _p_ebm02, _mutate_ebm02),
    Invariant("EBM-03", _p_ebm03, _mutate_ebm03),
    Invariant("EBM-08", _p_ebm08, _mutate_ebm08),
    Invariant("EBM-10", _p_ebm10, _mutate_ebm10),
)


def _spec_text() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


def _cross_clause_rows(spec_text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in spec_text.splitlines():
        match = re.match(r"\|\s*(EBM-\d{2})\s*\|", line)
        if match:
            rows[match.group(1)] = line
    return rows


def _design_owned_ebm_ids(spec_text: str) -> set[str]:
    """EBM ids the source-to-contract-to-test matrix routes to issue #305."""

    owned: set[str] = set()
    in_matrix = False
    for line in spec_text.splitlines():
        if line.startswith("## "):
            in_matrix = line.startswith("## Source-to-contract-to-test matrix")
            continue
        if not in_matrix or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and _OWNER_ISSUE in cells[-1]:
            owned.update(re.findall(r"EBM-\d{2}", cells[0]))
    return owned


def test_catalog_matches_design_ownership() -> None:
    spec_text = _spec_text()
    cross_clause_rows = _cross_clause_rows(spec_text)
    catalog_ids = {invariant.invariant_id for invariant in INVARIANTS}

    # Every cataloged invariant is a real cross-clause row that names SEM-222.
    for invariant_id in catalog_ids:
        assert invariant_id in cross_clause_rows, invariant_id
        assert "SEM-222" in cross_clause_rows[invariant_id], invariant_id

    # The catalog is exactly what the design routes to issue #305, so dropping or
    # inventing a SEM-222 episode obligation breaks this test.
    assert catalog_ids == _design_owned_ebm_ids(spec_text)


@pytest.mark.parametrize("invariant", INVARIANTS, ids=lambda invariant: invariant.invariant_id)
def test_each_invariant_rejects_its_targeted_mutation(invariant: Invariant) -> None:
    mutated = invariant.mutate(canonical_progression())
    assert not invariant.predicate(mutated), invariant.invariant_id


def test_canonical_progression_satisfies_all_invariants() -> None:
    state = canonical_progression()
    for invariant in INVARIANTS:
        assert invariant.predicate(state), invariant.invariant_id
