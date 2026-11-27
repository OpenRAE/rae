"""RUN-311: participant-episode lifecycle and reset integrity tests.

RUN-311 ("Participant Episode Lifecycle And Reset") requires the runtime
to support episodic participant execution with explicit initialization,
reset, completion, timeout, truncation, interruption, and restart
handling.

ADR-013 ("Participant Episode Lifecycle Boundaries") locks in that
participant episodes are their own processor/runtime contract surface
that must not be aliased into ``WorkflowExecutionState``,
``EvaluationExecutionState``, ``OperationStatus``, or
``RuntimeSnapshot.metadata``. Lifecycle state, terminal reason, and
control actions are kept as three distinct categories, and reset/restart
must create a new episode instance while preserving stable participant
identity.

The tests in this module exercise every clause of RUN-311 against the
``ParticipantEpisodeExecutionState`` and ``ParticipantEpisodeHistoryEvent``
contract surfaces, plus the published JSON Schemas.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from raes_processor.models import (
    ParticipantEpisodeControlAction,
    ParticipantEpisodeExecutionState,
    ParticipantEpisodeHistoryEvent,
    ParticipantEpisodeHistoryEventType,
    ParticipantEpisodeStatus,
    ParticipantEpisodeTerminalReason,
    RuntimeSnapshot,
)
from raes_runtime.result_contracts import participant_episode_contract_diagnostics
from raes_schemas import schema_bundle

PARTICIPANT_ADDRESS = "participant.alice"
EP1 = "ep-0001"
EP2 = "ep-0002"
EP3 = "ep-0003"
EP4 = "ep-0004"
T0 = "2026-04-11T10:00:00Z"
T1 = "2026-04-11T10:00:05Z"
T2 = "2026-04-11T10:00:10Z"
T3 = "2026-04-11T10:00:15Z"
T4 = "2026-04-11T10:00:20Z"
T5 = "2026-04-11T10:00:25Z"
T6 = "2026-04-11T10:00:30Z"
T7 = "2026-04-11T10:00:35Z"
T8 = "2026-04-11T10:00:40Z"
T9 = "2026-04-11T10:00:45Z"
T10 = "2026-04-11T10:00:50Z"
T11 = "2026-04-11T10:00:55Z"


def _initialized_state(**overrides):
    base = dict(
        participant_address=PARTICIPANT_ADDRESS,
        episode_id=EP1,
        sequence_number=0,
        status=ParticipantEpisodeStatus.INITIALIZING,
        terminal_reason=None,
        initialized_at=T0,
        updated_at=T0,
        terminated_at=None,
        last_control_action=ParticipantEpisodeControlAction.INITIALIZE,
        previous_episode_id=None,
    )
    base.update(overrides)
    return ParticipantEpisodeExecutionState(**base)


def _terminated_state(*, terminal_reason, **overrides):
    base = dict(
        participant_address=PARTICIPANT_ADDRESS,
        episode_id=EP1,
        sequence_number=0,
        status=ParticipantEpisodeStatus.TERMINATED,
        terminal_reason=terminal_reason,
        initialized_at=T0,
        updated_at=T1,
        terminated_at=T1,
        last_control_action=ParticipantEpisodeControlAction.INITIALIZE,
        previous_episode_id=None,
    )
    base.update(overrides)
    return ParticipantEpisodeExecutionState(**base)


def _history_event(**overrides):
    base = dict(
        event_type=ParticipantEpisodeHistoryEventType.EPISODE_RUNNING,
        timestamp=T1,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id=EP1,
        sequence_number=0,
        terminal_reason=None,
        control_action=None,
        details={},
    )
    base.update(overrides)
    return ParticipantEpisodeHistoryEvent(**base)


class TestRun311ParticipantEpisodeLifecycle:
    """End-to-end participant-episode lifecycle integrity tests for RUN-311."""

    def test_first_episode_initializes_with_stable_identity(self):
        """Clauses 1, 2 — episodes carry explicit stable identity from initialization onward.

        The first episode must use ``sequence_number=0`` and the
        ``INITIALIZE`` control action, must not link to a previous
        episode, must round-trip cleanly through ``to_payload`` /
        ``from_payload`` (the schema-first contract boundary), and must
        carry a stable ``participant_address`` and per-episode
        ``episode_id`` so downstream consumers can distinguish the
        participant from the bounded episode instance.
        """

        state = _initialized_state()

        assert state.status == ParticipantEpisodeStatus.INITIALIZING
        assert state.last_control_action == ParticipantEpisodeControlAction.INITIALIZE
        assert state.previous_episode_id is None
        assert state.terminal_reason is None
        assert state.terminated_at is None
        assert state.participant_address == PARTICIPANT_ADDRESS
        assert state.episode_id == EP1

        running = ParticipantEpisodeExecutionState(
            participant_address=state.participant_address,
            episode_id=state.episode_id,
            sequence_number=state.sequence_number,
            status=ParticipantEpisodeStatus.RUNNING,
            initialized_at=state.initialized_at,
            updated_at=T1,
            last_control_action=state.last_control_action,
        )
        assert running.status == ParticipantEpisodeStatus.RUNNING
        assert running.participant_address == state.participant_address
        assert running.episode_id == state.episode_id
        assert running.terminal_reason is None

        round_trip = ParticipantEpisodeExecutionState.from_payload(running.to_payload())
        assert round_trip == running, (
            "Schema-first boundary must round-trip without loss; any drift "
            "would mean the published JSON envelope cannot reconstruct the "
            "in-process contract identity."
        )

    @pytest.mark.parametrize(
        "terminal_reason",
        [
            ParticipantEpisodeTerminalReason.COMPLETED,
            ParticipantEpisodeTerminalReason.TIMED_OUT,
            ParticipantEpisodeTerminalReason.TRUNCATED,
            ParticipantEpisodeTerminalReason.INTERRUPTED,
        ],
    )
    def test_terminal_states_require_matching_terminal_reason(self, terminal_reason):
        """Clauses 4-7 — every terminal outcome (completion, timeout, truncation,
        interruption) is reachable, requires its terminal reason, and is
        forbidden from non-terminal states.
        """

        state = _terminated_state(terminal_reason=terminal_reason)
        assert state.status == ParticipantEpisodeStatus.TERMINATED
        assert state.terminal_reason == terminal_reason
        assert state.terminated_at == T1

        with pytest.raises(ValueError, match="terminated participant episodes must report a terminal_reason"):
            _terminated_state(terminal_reason=None)

        with pytest.raises(
            ValueError,
            match="non-terminal participant episodes may not report a terminal_reason",
        ):
            _initialized_state(terminal_reason=terminal_reason)

        with pytest.raises(
            ValueError,
            match="non-terminal participant episodes may not report a terminal_reason",
        ):
            _initialized_state(
                status=ParticipantEpisodeStatus.RUNNING,
                updated_at=T1,
                terminal_reason=terminal_reason,
            )

    def test_reset_creates_new_episode_preserving_participant_identity(self):
        """Clause 3 — reset spawns a new episode instance that keeps the
        stable participant identity but has a fresh ``episode_id``,
        an incremented ``sequence_number``, and a backreference to the
        prior episode. The reset state must NOT mutate the prior state
        in place (ADR-013 §4).
        """

        first = _initialized_state()
        first_payload_before = first.to_payload()

        reset = ParticipantEpisodeExecutionState(
            participant_address=first.participant_address,
            episode_id=EP2,
            sequence_number=first.sequence_number + 1,
            status=ParticipantEpisodeStatus.INITIALIZING,
            initialized_at=T2,
            updated_at=T2,
            last_control_action=ParticipantEpisodeControlAction.RESET,
            previous_episode_id=first.episode_id,
        )

        assert reset.participant_address == first.participant_address, (
            "Participant identity must be preserved across resets so the "
            "runtime can recognize that this is the same participant on a new "
            "episode instance."
        )
        assert reset.episode_id != first.episode_id, (
            "Each reset must allocate a new episode_id so prior episode history is never overwritten."
        )
        assert reset.sequence_number == first.sequence_number + 1
        assert reset.previous_episode_id == first.episode_id
        assert reset.last_control_action == ParticipantEpisodeControlAction.RESET
        assert first.to_payload() == first_payload_before, (
            "Reset must allocate a new state instance, not mutate the prior episode state in place."
        )

    def test_restart_after_termination_creates_new_episode_with_link_to_prior(self):
        """Clause 8 — restart creates a fresh episode that links back to the
        terminated prior episode. The chain ``initialized → terminated →
        restarted`` must be reconstructable from the contract surface.
        """

        terminated = _terminated_state(terminal_reason=ParticipantEpisodeTerminalReason.COMPLETED)
        restart = ParticipantEpisodeExecutionState(
            participant_address=terminated.participant_address,
            episode_id=EP2,
            sequence_number=terminated.sequence_number + 1,
            status=ParticipantEpisodeStatus.RUNNING,
            initialized_at=T2,
            updated_at=T3,
            last_control_action=ParticipantEpisodeControlAction.RESTART,
            previous_episode_id=terminated.episode_id,
        )

        assert restart.participant_address == terminated.participant_address
        assert restart.previous_episode_id == terminated.episode_id
        assert restart.last_control_action == ParticipantEpisodeControlAction.RESTART
        assert restart.sequence_number == terminated.sequence_number + 1
        assert restart.episode_id != terminated.episode_id

    @pytest.mark.parametrize(
        "control_action",
        [
            ParticipantEpisodeControlAction.RESET,
            ParticipantEpisodeControlAction.RESTART,
        ],
    )
    def test_first_episode_rejects_reset_or_restart_control_action(self, control_action):
        """Invariant — sequence_number=0 cannot be a reset or restart, because
        there is no prior episode to come from.
        """

        with pytest.raises(
            ValueError,
            match=("the first participant episode \\(sequence_number=0\\) must use the INITIALIZE control action"),
        ):
            _initialized_state(last_control_action=control_action)

    def test_subsequent_episode_requires_previous_episode_id(self):
        """Invariant — sequence_number > 0 must always link to a previous episode
        and cannot use the INITIALIZE control action.
        """

        with pytest.raises(
            ValueError,
            match=("subsequent participant episodes \\(sequence_number>0\\) must link to a previous_episode_id"),
        ):
            ParticipantEpisodeExecutionState(
                participant_address=PARTICIPANT_ADDRESS,
                episode_id=EP2,
                sequence_number=1,
                status=ParticipantEpisodeStatus.RUNNING,
                initialized_at=T2,
                updated_at=T2,
                last_control_action=ParticipantEpisodeControlAction.RESET,
                previous_episode_id=None,
            )

        with pytest.raises(
            ValueError,
            match=("subsequent participant episodes \\(sequence_number>0\\) must use RESET or RESTART, not INITIALIZE"),
        ):
            ParticipantEpisodeExecutionState(
                participant_address=PARTICIPANT_ADDRESS,
                episode_id=EP2,
                sequence_number=1,
                status=ParticipantEpisodeStatus.RUNNING,
                initialized_at=T2,
                updated_at=T2,
                last_control_action=ParticipantEpisodeControlAction.INITIALIZE,
                previous_episode_id=EP1,
            )

        with pytest.raises(
            ValueError,
            match="previous_episode_id must differ from episode_id",
        ):
            ParticipantEpisodeExecutionState(
                participant_address=PARTICIPANT_ADDRESS,
                episode_id=EP2,
                sequence_number=1,
                status=ParticipantEpisodeStatus.RUNNING,
                initialized_at=T2,
                updated_at=T2,
                last_control_action=ParticipantEpisodeControlAction.RESET,
                previous_episode_id=EP2,
            )

    @pytest.mark.parametrize(
        ("event_type", "expected_reason"),
        [
            (ParticipantEpisodeHistoryEventType.EPISODE_COMPLETED, ParticipantEpisodeTerminalReason.COMPLETED),
            (ParticipantEpisodeHistoryEventType.EPISODE_TIMED_OUT, ParticipantEpisodeTerminalReason.TIMED_OUT),
            (ParticipantEpisodeHistoryEventType.EPISODE_TRUNCATED, ParticipantEpisodeTerminalReason.TRUNCATED),
            (ParticipantEpisodeHistoryEventType.EPISODE_INTERRUPTED, ParticipantEpisodeTerminalReason.INTERRUPTED),
        ],
    )
    def test_history_event_terminal_reason_must_match_event_type(self, event_type, expected_reason):
        """Clauses 4-7 expressed as history events — each terminal event type is
        coupled to exactly one terminal reason, and non-terminal event types
        cannot carry a terminal_reason.
        """

        ok = _history_event(event_type=event_type, terminal_reason=expected_reason)
        assert ok.terminal_reason == expected_reason

        wrong_reasons = [reason for reason in ParticipantEpisodeTerminalReason if reason != expected_reason]
        for reason in wrong_reasons:
            with pytest.raises(ValueError, match="must report terminal_reason"):
                _history_event(event_type=event_type, terminal_reason=reason)

        with pytest.raises(ValueError, match="must report terminal_reason"):
            _history_event(event_type=event_type, terminal_reason=None)

        with pytest.raises(ValueError, match="may not report a terminal_reason"):
            _history_event(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_RUNNING,
                terminal_reason=expected_reason,
            )

    @pytest.mark.parametrize(
        ("event_type", "expected_action", "sequence_number"),
        [
            (ParticipantEpisodeHistoryEventType.EPISODE_INITIALIZED, ParticipantEpisodeControlAction.INITIALIZE, 0),
            (ParticipantEpisodeHistoryEventType.EPISODE_RESET, ParticipantEpisodeControlAction.RESET, 1),
            (ParticipantEpisodeHistoryEventType.EPISODE_RESTARTED, ParticipantEpisodeControlAction.RESTART, 1),
        ],
    )
    def test_history_event_control_action_must_match_event_type(self, event_type, expected_action, sequence_number):
        """Clauses 2, 3, 8 expressed as history events — each control event type
        is coupled to exactly one control action, and non-control event types
        cannot carry a control_action.
        """

        ok = _history_event(event_type=event_type, control_action=expected_action, sequence_number=sequence_number)
        assert ok.control_action == expected_action

        wrong_actions = [action for action in ParticipantEpisodeControlAction if action != expected_action]
        for action in wrong_actions:
            with pytest.raises(ValueError, match="must report control_action"):
                _history_event(event_type=event_type, control_action=action, sequence_number=sequence_number)

        with pytest.raises(ValueError, match="must report control_action"):
            _history_event(event_type=event_type, control_action=None, sequence_number=sequence_number)

        with pytest.raises(ValueError, match="may not report a control_action"):
            _history_event(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_RUNNING,
                control_action=expected_action,
            )

    def test_history_event_payload_round_trip_for_full_lifecycle(self):
        """Clauses 1-8 in one assertion — build a participant history that hits
        every control action and every terminal reason and round-trip every
        event through the schema-first payload boundary.
        """

        history = [
            _history_event(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_INITIALIZED,
                timestamp=T0,
                control_action=ParticipantEpisodeControlAction.INITIALIZE,
            ),
            _history_event(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_RUNNING,
                timestamp=T1,
            ),
            _history_event(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_COMPLETED,
                timestamp=T2,
                terminal_reason=ParticipantEpisodeTerminalReason.COMPLETED,
            ),
            _history_event(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_RESET,
                timestamp=T3,
                episode_id=EP2,
                sequence_number=1,
                control_action=ParticipantEpisodeControlAction.RESET,
            ),
            _history_event(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_RUNNING,
                timestamp=T4,
                episode_id=EP2,
                sequence_number=1,
            ),
            _history_event(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_INTERRUPTED,
                timestamp=T5,
                episode_id=EP2,
                sequence_number=1,
                terminal_reason=ParticipantEpisodeTerminalReason.INTERRUPTED,
            ),
            _history_event(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_RESTARTED,
                timestamp=T6,
                episode_id=EP3,
                sequence_number=2,
                control_action=ParticipantEpisodeControlAction.RESTART,
            ),
            _history_event(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_RUNNING,
                timestamp=T7,
                episode_id=EP3,
                sequence_number=2,
            ),
            _history_event(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_TIMED_OUT,
                timestamp=T8,
                episode_id=EP3,
                sequence_number=2,
                terminal_reason=ParticipantEpisodeTerminalReason.TIMED_OUT,
            ),
            _history_event(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_RESTARTED,
                timestamp=T9,
                episode_id=EP4,
                sequence_number=3,
                control_action=ParticipantEpisodeControlAction.RESTART,
            ),
            _history_event(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_RUNNING,
                timestamp=T10,
                episode_id=EP4,
                sequence_number=3,
            ),
            _history_event(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_TRUNCATED,
                timestamp=T11,
                episode_id=EP4,
                sequence_number=3,
                terminal_reason=ParticipantEpisodeTerminalReason.TRUNCATED,
            ),
        ]

        terminal_reasons_seen = {event.terminal_reason for event in history if event.terminal_reason is not None}
        control_actions_seen = {event.control_action for event in history if event.control_action is not None}
        assert terminal_reasons_seen == set(ParticipantEpisodeTerminalReason), (
            "Lifecycle smoke history must reach every terminal reason exactly once."
        )
        assert control_actions_seen == set(ParticipantEpisodeControlAction), (
            "Lifecycle smoke history must reach every control action exactly once."
        )

        for event in history:
            assert event.participant_address == PARTICIPANT_ADDRESS, (
                "Participant identity must be stable across the entire history, even after resets and restarts."
            )
            round_trip = ParticipantEpisodeHistoryEvent.from_payload(event.to_payload())
            assert round_trip == event, (
                "History event payload must round-trip via the schema-first "
                f"boundary; drift on {event.event_type.value} would silently "
                "lose lifecycle data."
            )

    def test_initialized_history_event_requires_sequence_number_zero(self):
        """Invariant — ``episode_initialized`` events describe the very first
        episode of a participant, so they must carry ``sequence_number=0``.
        A history stream that emits ``episode_initialized`` at any later
        sequence cannot correspond to a valid
        ``ParticipantEpisodeExecutionState`` chain.
        """

        with pytest.raises(ValueError, match="episode_initialized history events must report sequence_number=0"):
            _history_event(
                event_type=ParticipantEpisodeHistoryEventType.EPISODE_INITIALIZED,
                sequence_number=1,
                control_action=ParticipantEpisodeControlAction.INITIALIZE,
            )

    @pytest.mark.parametrize(
        "event_type",
        [
            ParticipantEpisodeHistoryEventType.EPISODE_RESET,
            ParticipantEpisodeHistoryEventType.EPISODE_RESTARTED,
        ],
    )
    def test_reset_and_restart_history_events_require_sequence_number_greater_than_zero(self, event_type):
        """Invariant — ``episode_reset`` and ``episode_restarted`` events describe
        transitions into a new episode instance, which only exists for
        ``sequence_number > 0``. The very first episode must arrive via
        ``episode_initialized`` instead.
        """

        expected_action = (
            ParticipantEpisodeControlAction.RESET
            if event_type == ParticipantEpisodeHistoryEventType.EPISODE_RESET
            else ParticipantEpisodeControlAction.RESTART
        )
        with pytest.raises(ValueError, match="must report sequence_number>0"):
            _history_event(
                event_type=event_type,
                sequence_number=0,
                control_action=expected_action,
            )

    def test_runtime_apply_path_rejects_invalid_participant_episode_result(self):
        """Runtime integration — ``participant_episode_contract_diagnostics``
        is called on every backend apply. It must emit a
        ``runtime.backend-contract-invalid`` diagnostic for any participant
        episode result that violates the dataclass invariants, so invalid
        RUN-311 data cannot be silently persisted through the manager path.
        """

        snapshot = RuntimeSnapshot(
            participant_episode_results={
                "participant.alice": {
                    "state_schema_version": "participant-episode-state/v1",
                    "participant_address": "participant.alice",
                    "episode_id": "ep-0001",
                    "sequence_number": 0,
                    "status": "running",
                    "terminal_reason": "completed",
                    "initialized_at": T0,
                    "updated_at": T1,
                    "terminated_at": None,
                    "last_control_action": "initialize",
                    "previous_episode_id": None,
                }
            },
        )

        diagnostics = participant_episode_contract_diagnostics(snapshot)

        assert diagnostics, "apply path must reject invalid participant episode result"
        assert all(diag.code == "runtime.backend-contract-invalid" for diag in diagnostics)
        assert any(
            "non-terminal participant episodes may not report a terminal_reason" in diag.message for diag in diagnostics
        )

    def test_runtime_apply_path_rejects_invalid_participant_episode_history_event(self):
        """Runtime integration — the apply path must also reject a participant
        episode history event whose sequence number disagrees with its event
        type (for example ``episode_reset`` at ``sequence_number=0``).
        """

        snapshot = RuntimeSnapshot(
            participant_episode_history={
                "participant.alice": [
                    {
                        "event_type": "episode_reset",
                        "timestamp": T0,
                        "participant_address": "participant.alice",
                        "episode_id": "ep-0001",
                        "sequence_number": 0,
                        "terminal_reason": None,
                        "control_action": "reset",
                        "details": {},
                    }
                ]
            },
        )

        diagnostics = participant_episode_contract_diagnostics(snapshot)

        assert diagnostics, "apply path must reject invalid participant episode history"
        assert all(diag.code == "runtime.backend-contract-invalid" for diag in diagnostics)
        assert any("must report sequence_number>0" in diag.message for diag in diagnostics)

    def test_runtime_apply_path_rejects_outer_key_mismatch_on_result(self):
        """Stream invariant — the outer ``participant_episode_results`` key must
        equal the inner ``participant_address``. Backends that key results by
        one address but set a different ``participant_address`` on the state
        corrupt the participant identity and must be rejected.
        """

        snapshot = RuntimeSnapshot(
            participant_episode_results={
                "participant.alice": {
                    "state_schema_version": "participant-episode-state/v1",
                    "participant_address": "participant.bob",
                    "episode_id": EP1,
                    "sequence_number": 0,
                    "status": "initializing",
                    "terminal_reason": None,
                    "initialized_at": T0,
                    "updated_at": T0,
                    "terminated_at": None,
                    "last_control_action": "initialize",
                    "previous_episode_id": None,
                }
            },
        )

        diagnostics = participant_episode_contract_diagnostics(snapshot)

        assert diagnostics, "apply path must reject participant episode result with outer-key mismatch"
        assert all(diag.code == "runtime.backend-contract-invalid" for diag in diagnostics)
        assert any("does not match inner participant_address" in diag.message for diag in diagnostics)

    def test_runtime_apply_path_rejects_outer_key_mismatch_on_history_event(self):
        """Stream invariant — history events must carry the same
        ``participant_address`` as the outer key they were indexed under.
        """

        snapshot = RuntimeSnapshot(
            participant_episode_history={
                "participant.alice": [
                    {
                        "event_type": "episode_initialized",
                        "timestamp": T0,
                        "participant_address": "participant.bob",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": None,
                        "control_action": "initialize",
                        "details": {},
                    }
                ]
            },
        )

        diagnostics = participant_episode_contract_diagnostics(snapshot)

        assert diagnostics
        assert all(diag.code == "runtime.backend-contract-invalid" for diag in diagnostics)
        assert any("does not match inner participant_address" in diag.message for diag in diagnostics)

    def test_runtime_apply_path_rejects_history_sequence_going_backward(self):
        """Stream invariant — sequence_number is monotonic non-decreasing
        within one participant's history. A backend cannot emit events for
        older episodes after newer ones.
        """

        snapshot = RuntimeSnapshot(
            participant_episode_history={
                "participant.alice": [
                    {
                        "event_type": "episode_initialized",
                        "timestamp": T0,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": None,
                        "control_action": "initialize",
                        "details": {},
                    },
                    {
                        "event_type": "episode_reset",
                        "timestamp": T1,
                        "participant_address": "participant.alice",
                        "episode_id": EP2,
                        "sequence_number": 1,
                        "terminal_reason": None,
                        "control_action": "reset",
                        "details": {},
                    },
                    {
                        "event_type": "episode_running",
                        "timestamp": T2,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": None,
                        "control_action": None,
                        "details": {},
                    },
                ]
            },
        )

        diagnostics = participant_episode_contract_diagnostics(snapshot)

        assert diagnostics
        assert any("sequence_number went backward" in diag.message for diag in diagnostics)

    def test_runtime_apply_path_rejects_sequence_increment_without_reset_or_restart(self):
        """Stream invariant — a transition into a new episode sequence must
        be gated by an ``EPISODE_RESET`` or ``EPISODE_RESTARTED`` event, not
        a plain ``EPISODE_RUNNING`` or terminal event.
        """

        snapshot = RuntimeSnapshot(
            participant_episode_history={
                "participant.alice": [
                    {
                        "event_type": "episode_initialized",
                        "timestamp": T0,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": None,
                        "control_action": "initialize",
                        "details": {},
                    },
                    {
                        "event_type": "episode_running",
                        "timestamp": T1,
                        "participant_address": "participant.alice",
                        "episode_id": EP2,
                        "sequence_number": 1,
                        "terminal_reason": None,
                        "control_action": None,
                        "details": {},
                    },
                ]
            },
        )

        diagnostics = participant_episode_contract_diagnostics(snapshot)

        assert diagnostics
        assert any("must arrive via episode_reset or episode_restarted" in diag.message for diag in diagnostics)

    def test_runtime_apply_path_rejects_episode_id_changing_within_sequence(self):
        """Stream invariant — within one sequence number, every history event
        must share the same episode_id. A sudden change would mean the same
        ``sequence_number`` spans two distinct episode instances.
        """

        snapshot = RuntimeSnapshot(
            participant_episode_history={
                "participant.alice": [
                    {
                        "event_type": "episode_initialized",
                        "timestamp": T0,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": None,
                        "control_action": "initialize",
                        "details": {},
                    },
                    {
                        "event_type": "episode_running",
                        "timestamp": T1,
                        "participant_address": "participant.alice",
                        "episode_id": EP2,
                        "sequence_number": 0,
                        "terminal_reason": None,
                        "control_action": None,
                        "details": {},
                    },
                ]
            },
        )

        diagnostics = participant_episode_contract_diagnostics(snapshot)

        assert diagnostics
        assert any("episode_id changed within sequence_number" in diag.message for diag in diagnostics)

    def test_runtime_apply_path_stream_violations_do_not_cascade(self):
        """Stream invariant — after a stream-level violation on one event,
        subsequent events must be validated against the advanced sequence
        state, not the pre-violation state. Otherwise a single bad
        transition would produce the same "must arrive via reset/restart"
        error on every follow-up event at the new sequence number.
        """

        snapshot = RuntimeSnapshot(
            participant_episode_history={
                "participant.alice": [
                    {
                        "event_type": "episode_initialized",
                        "timestamp": T0,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": None,
                        "control_action": "initialize",
                        "details": {},
                    },
                    {
                        "event_type": "episode_running",
                        "timestamp": T1,
                        "participant_address": "participant.alice",
                        "episode_id": EP2,
                        "sequence_number": 1,
                        "terminal_reason": None,
                        "control_action": None,
                        "details": {},
                    },
                    {
                        "event_type": "episode_running",
                        "timestamp": T2,
                        "participant_address": "participant.alice",
                        "episode_id": EP2,
                        "sequence_number": 1,
                        "terminal_reason": None,
                        "control_action": None,
                        "details": {},
                    },
                ]
            },
        )

        diagnostics = participant_episode_contract_diagnostics(snapshot)

        gate_messages = [
            diag.message for diag in diagnostics if "must arrive via episode_reset or episode_restarted" in diag.message
        ]
        assert len(gate_messages) == 1, (
            "Stream gate violation must fire exactly once per ungated transition, not once "
            f"per event at the new sequence; got {len(gate_messages)} occurrences: {gate_messages}"
        )

    def test_runtime_apply_path_episode_id_mismatch_reports_transitions_not_repeats(self):
        """Stream invariant — an ``episode_id`` mismatch within one sequence
        must be reported as a one-off *transition* between episode_ids, not
        as a repeated comparison against the first-observed id. For the
        history ``[A, B, B, C]`` at the same sequence number the validator
        must yield exactly two mismatch errors (``A -> B`` and ``B -> C``),
        not three (``A -> B``, ``A -> B``, ``A -> C``).
        """

        def _event(timestamp: str, episode_id: str, event_type: str, control_action: str | None):
            return {
                "event_type": event_type,
                "timestamp": timestamp,
                "participant_address": "participant.alice",
                "episode_id": episode_id,
                "sequence_number": 0,
                "terminal_reason": None,
                "control_action": control_action,
                "details": {},
            }

        snapshot = RuntimeSnapshot(
            participant_episode_history={
                "participant.alice": [
                    _event(T0, EP1, "episode_initialized", "initialize"),
                    _event(T1, EP2, "episode_running", None),
                    _event(T2, EP2, "episode_running", None),
                    _event(T3, EP3, "episode_running", None),
                ]
            },
        )

        diagnostics = participant_episode_contract_diagnostics(snapshot)

        mismatch_messages = [
            diag.message for diag in diagnostics if "episode_id changed within sequence_number" in diag.message
        ]
        assert len(mismatch_messages) == 2, (
            "episode_id mismatches must be reported as transitions (A->B, B->C), "
            f"not as repeated comparisons against the first-observed id. Got "
            f"{len(mismatch_messages)} mismatches: {mismatch_messages}"
        )
        assert any(f"{EP1!r} -> {EP2!r}" in msg for msg in mismatch_messages)
        assert any(f"{EP2!r} -> {EP3!r}" in msg for msg in mismatch_messages)

    def test_runtime_apply_path_rejects_stale_result_not_matching_history_head(self):
        """Cross-check invariant — when both a result and a non-empty history
        exist for the same participant, the result must be the head of the
        history chain. Reproduces the reviewer's exact scenario: the result
        still points at terminated episode ``ep-0001`` / sequence ``0`` while
        the history already shows a restart into running episode ``ep-0002``
        / sequence ``1``. Prior to this check the validator returned zero
        diagnostics for that snapshot.
        """

        snapshot = RuntimeSnapshot(
            participant_episode_results={
                "participant.alice": {
                    "state_schema_version": "participant-episode-state/v1",
                    "participant_address": "participant.alice",
                    "episode_id": EP1,
                    "sequence_number": 0,
                    "status": "terminated",
                    "terminal_reason": "completed",
                    "initialized_at": T0,
                    "updated_at": T1,
                    "terminated_at": T1,
                    "last_control_action": "initialize",
                    "previous_episode_id": None,
                }
            },
            participant_episode_history={
                "participant.alice": [
                    {
                        "event_type": "episode_initialized",
                        "timestamp": T0,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": None,
                        "control_action": "initialize",
                        "details": {},
                    },
                    {
                        "event_type": "episode_completed",
                        "timestamp": T1,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": "completed",
                        "control_action": None,
                        "details": {},
                    },
                    {
                        "event_type": "episode_restarted",
                        "timestamp": T2,
                        "participant_address": "participant.alice",
                        "episode_id": EP2,
                        "sequence_number": 1,
                        "terminal_reason": None,
                        "control_action": "restart",
                        "details": {},
                    },
                    {
                        "event_type": "episode_running",
                        "timestamp": T3,
                        "participant_address": "participant.alice",
                        "episode_id": EP2,
                        "sequence_number": 1,
                        "terminal_reason": None,
                        "control_action": None,
                        "details": {},
                    },
                ]
            },
        )

        diagnostics = participant_episode_contract_diagnostics(snapshot)

        assert diagnostics, (
            "apply path must reject a stale result that does not match the "
            "head of the history chain (reviewer finding 2)"
        )
        assert all(diag.code == "runtime.backend-contract-invalid" for diag in diagnostics)
        assert any("does not match head of history chain" in diag.message for diag in diagnostics)

    def test_runtime_apply_path_rejects_terminated_result_with_non_terminal_history_head(self):
        """Cross-check invariant — a result claiming ``status=terminated`` must
        be accompanied by a terminal history event. A running result claiming
        termination without matching terminal history is inconsistent.
        """

        snapshot = RuntimeSnapshot(
            participant_episode_results={
                "participant.alice": {
                    "state_schema_version": "participant-episode-state/v1",
                    "participant_address": "participant.alice",
                    "episode_id": EP1,
                    "sequence_number": 0,
                    "status": "terminated",
                    "terminal_reason": "completed",
                    "initialized_at": T0,
                    "updated_at": T1,
                    "terminated_at": T1,
                    "last_control_action": "initialize",
                    "previous_episode_id": None,
                }
            },
            participant_episode_history={
                "participant.alice": [
                    {
                        "event_type": "episode_initialized",
                        "timestamp": T0,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": None,
                        "control_action": "initialize",
                        "details": {},
                    },
                    {
                        "event_type": "episode_running",
                        "timestamp": T1,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": None,
                        "control_action": None,
                        "details": {},
                    },
                ]
            },
        )

        diagnostics = participant_episode_contract_diagnostics(snapshot)

        assert diagnostics
        assert any("terminated" in diag.message and "not a terminal event" in diag.message for diag in diagnostics)

    def test_runtime_apply_path_rejects_terminal_reason_mismatch_with_history_head(self):
        """Cross-check invariant — when result and history agree on episode
        identity, their terminal reasons must also agree. A result with
        ``terminal_reason=completed`` pointing at a history head whose
        ``terminal_reason=timed_out`` is semantically inconsistent.
        """

        snapshot = RuntimeSnapshot(
            participant_episode_results={
                "participant.alice": {
                    "state_schema_version": "participant-episode-state/v1",
                    "participant_address": "participant.alice",
                    "episode_id": EP1,
                    "sequence_number": 0,
                    "status": "terminated",
                    "terminal_reason": "completed",
                    "initialized_at": T0,
                    "updated_at": T1,
                    "terminated_at": T1,
                    "last_control_action": "initialize",
                    "previous_episode_id": None,
                }
            },
            participant_episode_history={
                "participant.alice": [
                    {
                        "event_type": "episode_timed_out",
                        "timestamp": T1,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": "timed_out",
                        "control_action": None,
                        "details": {},
                    },
                ]
            },
        )

        diagnostics = participant_episode_contract_diagnostics(snapshot)

        assert diagnostics
        assert any("terminal_reason" in diag.message and "does not match" in diag.message for diag in diagnostics)

    def test_runtime_apply_path_rejects_running_result_with_terminal_history_head(self):
        """Cross-check invariant — a non-terminal result cannot coexist with a
        terminal head event. The reviewer's scenario generalized: the head
        is ahead of the result rather than behind.
        """

        snapshot = RuntimeSnapshot(
            participant_episode_results={
                "participant.alice": {
                    "state_schema_version": "participant-episode-state/v1",
                    "participant_address": "participant.alice",
                    "episode_id": EP1,
                    "sequence_number": 0,
                    "status": "running",
                    "terminal_reason": None,
                    "initialized_at": T0,
                    "updated_at": T1,
                    "terminated_at": None,
                    "last_control_action": "initialize",
                    "previous_episode_id": None,
                }
            },
            participant_episode_history={
                "participant.alice": [
                    {
                        "event_type": "episode_completed",
                        "timestamp": T1,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": "completed",
                        "control_action": None,
                        "details": {},
                    },
                ]
            },
        )

        diagnostics = participant_episode_contract_diagnostics(snapshot)

        assert diagnostics
        assert any("running" in diag.message and "terminal" in diag.message for diag in diagnostics)

    def test_runtime_apply_path_accepts_result_matching_history_head(self):
        """Cross-check invariant — the positive counterpart: a result whose
        identity and status match the head of the history chain must pass
        cleanly.
        """

        snapshot = RuntimeSnapshot(
            participant_episode_results={
                "participant.alice": {
                    "state_schema_version": "participant-episode-state/v1",
                    "participant_address": "participant.alice",
                    "episode_id": EP2,
                    "sequence_number": 1,
                    "status": "running",
                    "terminal_reason": None,
                    "initialized_at": T0,
                    "updated_at": T3,
                    "terminated_at": None,
                    "last_control_action": "restart",
                    "previous_episode_id": EP1,
                }
            },
            participant_episode_history={
                "participant.alice": [
                    {
                        "event_type": "episode_initialized",
                        "timestamp": T0,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": None,
                        "control_action": "initialize",
                        "details": {},
                    },
                    {
                        "event_type": "episode_completed",
                        "timestamp": T1,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": "completed",
                        "control_action": None,
                        "details": {},
                    },
                    {
                        "event_type": "episode_restarted",
                        "timestamp": T2,
                        "participant_address": "participant.alice",
                        "episode_id": EP2,
                        "sequence_number": 1,
                        "terminal_reason": None,
                        "control_action": "restart",
                        "details": {},
                    },
                    {
                        "event_type": "episode_running",
                        "timestamp": T3,
                        "participant_address": "participant.alice",
                        "episode_id": EP2,
                        "sequence_number": 1,
                        "terminal_reason": None,
                        "control_action": None,
                        "details": {},
                    },
                ]
            },
        )

        diagnostics = participant_episode_contract_diagnostics(snapshot)

        assert diagnostics == []

    def test_runtime_apply_path_accepts_valid_participant_episode_snapshot(self):
        """Runtime integration — a snapshot that contains only valid RUN-311
        data must pass the apply-path diagnostic helper cleanly. This is the
        positive pair for the two rejection tests above.
        """

        snapshot = RuntimeSnapshot(
            participant_episode_results={
                "participant.alice": {
                    "state_schema_version": "participant-episode-state/v1",
                    "participant_address": "participant.alice",
                    "episode_id": EP1,
                    "sequence_number": 0,
                    "status": "initializing",
                    "terminal_reason": None,
                    "initialized_at": T0,
                    "updated_at": T0,
                    "terminated_at": None,
                    "last_control_action": "initialize",
                    "previous_episode_id": None,
                }
            },
            participant_episode_history={
                "participant.alice": [
                    {
                        "event_type": "episode_initialized",
                        "timestamp": T0,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": None,
                        "control_action": "initialize",
                        "details": {},
                    }
                ]
            },
        )

        diagnostics = participant_episode_contract_diagnostics(snapshot)

        assert diagnostics == []

    def test_runtime_snapshot_with_entries_preserves_participant_episode_surfaces(self):
        """Snapshot integration — ``RuntimeSnapshot.with_entries`` must preserve
        ``participant_episode_results`` and ``participant_episode_history`` when
        they are not overridden, and must replace them when the caller passes
        an explicit value. Both modes are exercised here.
        """

        results = {
            "participant.alice": {
                "state_schema_version": "participant-episode-state/v1",
                "participant_address": "participant.alice",
                "episode_id": EP1,
                "sequence_number": 0,
                "status": "running",
                "terminal_reason": None,
                "initialized_at": T0,
                "updated_at": T1,
                "terminated_at": None,
                "last_control_action": "initialize",
                "previous_episode_id": None,
            }
        }
        history = {
            "participant.alice": [
                {
                    "event_type": "episode_initialized",
                    "timestamp": T0,
                    "participant_address": "participant.alice",
                    "episode_id": EP1,
                    "sequence_number": 0,
                    "terminal_reason": None,
                    "control_action": "initialize",
                    "details": {},
                }
            ]
        }
        snapshot = RuntimeSnapshot(
            participant_episode_results=results,
            participant_episode_history=history,
        )

        preserved = snapshot.with_entries({})
        assert preserved.participant_episode_results == results
        assert preserved.participant_episode_history == history

        replacement_results = {
            "participant.bob": {
                "state_schema_version": "participant-episode-state/v1",
                "participant_address": "participant.bob",
                "episode_id": "ep-bob-1",
                "sequence_number": 0,
                "status": "initializing",
                "terminal_reason": None,
                "initialized_at": T2,
                "updated_at": T2,
                "terminated_at": None,
                "last_control_action": "initialize",
                "previous_episode_id": None,
            }
        }
        replaced = snapshot.with_entries(
            {},
            participant_episode_results=replacement_results,
            participant_episode_history={},
        )
        assert replaced.participant_episode_results == replacement_results
        assert replaced.participant_episode_history == {}
        assert snapshot.participant_episode_results == results, (
            "with_entries must not mutate the source snapshot's participant results"
        )
        assert snapshot.participant_episode_history == history, (
            "with_entries must not mutate the source snapshot's participant history"
        )

    def test_runtime_snapshot_semantic_diagnostics_accept_valid_populated_payload(self):
        """Conformance integration — a runtime-snapshot-v1 payload that
        populates participant_episode_results and participant_episode_history
        with a coherent initialize→running history must pass
        ``_semantic_diagnostics`` cleanly. This is the positive counterpart to
        the rejection tests in ``test_runtime_conformance.py`` and gives the
        live probe direct coverage of the populated-payload path in
        ``_live_target_cases``.
        """

        from raes_conformance.conformance import _semantic_diagnostics

        snapshot_payload = {
            "schema_version": "runtime-snapshot/v1",
            "entries": {},
            "orchestration_results": {},
            "orchestration_history": {},
            "evaluation_results": {},
            "evaluation_history": {},
            "participant_episode_results": {
                "participant.alice": {
                    "state_schema_version": "participant-episode-state/v1",
                    "participant_address": "participant.alice",
                    "episode_id": EP1,
                    "sequence_number": 0,
                    "status": "running",
                    "terminal_reason": None,
                    "initialized_at": T0,
                    "updated_at": T1,
                    "terminated_at": None,
                    "last_control_action": "initialize",
                    "previous_episode_id": None,
                }
            },
            "participant_episode_history": {
                "participant.alice": [
                    {
                        "event_type": "episode_initialized",
                        "timestamp": T0,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": None,
                        "control_action": "initialize",
                        "details": {},
                    },
                    {
                        "event_type": "episode_running",
                        "timestamp": T1,
                        "participant_address": "participant.alice",
                        "episode_id": EP1,
                        "sequence_number": 0,
                        "terminal_reason": None,
                        "control_action": None,
                        "details": {},
                    },
                ]
            },
            "metadata": {},
        }

        diagnostics = _semantic_diagnostics("runtime-snapshot-v1", snapshot_payload)

        assert diagnostics == []

    def test_published_state_schema_matches_bundle_for_run_311(self):
        """Schema parity — the on-disk control-plane schemas for the participant
        episode envelope and the history event stream must equal the live
        schema bundle. If a developer edits ``raes_contracts/contracts.py``
        without re-running ``tools/generate_contract_schemas.py``, this test
        gives a clear local failure mode.
        """

        repo_root = Path(__file__).resolve().parents[3]
        schemas_dir = repo_root / "contracts" / "schemas" / "control-plane"
        bundle = schema_bundle()
        for schema_name in (
            "participant-episode-state-envelope-v1",
            "participant-episode-history-event-stream-v1",
        ):
            on_disk = json.loads((schemas_dir / f"{schema_name}.json").read_text(encoding="utf-8"))
            assert on_disk == bundle[schema_name], (
                f"Published schema {schema_name}.json drifted from "
                "schema_bundle(); re-run tools/generate_contract_schemas.py."
            )
