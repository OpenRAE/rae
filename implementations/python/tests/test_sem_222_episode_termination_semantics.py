"""SEM-222 - Episode Boundary And Termination Semantics.

Direct semantic-gate tests for the participant episode termination surface and
the RL termination/truncation closure record (EBM-02, EBM-06, EBM-08, EBM-10 of
``specs/formal/participant-episode-model/README.md``). The invariant oracle in
``test_sem_222_episode_termination_oracle.py`` covers the same invariants as a
model-level property/mutation catalog; this module drives the concrete
``ParticipantEpisodeClosureRecord`` contract and the
``iter_participant_episode_closure_violations`` fail-closed helper against the
real ADR-013 ``ParticipantEpisode*`` surface.
"""

from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator
from raes_conformance.conformance.semantics import _semantic_diagnostics
from raes_contracts.contracts import RuntimeSnapshotEnvelopeModel, schema_bundle
from raes_contracts.participant_episode import (
    ParticipantEpisodeControlAction,
    ParticipantEpisodeStatus,
    ParticipantEpisodeTerminalReason,
)
from raes_contracts.participant_episode_closure import (
    PARTICIPANT_EPISODE_CLOSURE_SIGNAL_TERMINAL_REASONS,
    ParticipantEpisodeClosureRecord,
    ParticipantEpisodeClosureSignal,
    iter_participant_episode_closure_violations,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.control_plane_store_snapshots import _snapshot_payload

_ADDRESS = "scenario/participant/agent-0"
_EPISODE = "episode-0"


def _terminal_history(
    *,
    address: str = _ADDRESS,
    episode_id: str = _EPISODE,
    sequence_number: int = 0,
    event_type: str = "episode_truncated",
    terminal_reason: str = "truncated",
) -> dict[str, list[dict[str, object]]]:
    return {
        address: [
            {
                "event_type": "episode_initialized",
                "timestamp": "2026-01-01T00:00:00Z",
                "participant_address": address,
                "episode_id": episode_id,
                "sequence_number": sequence_number,
                "control_action": "initialize",
            },
            {
                "event_type": event_type,
                "timestamp": "2026-01-01T00:05:00Z",
                "participant_address": address,
                "episode_id": episode_id,
                "sequence_number": sequence_number,
                "terminal_reason": terminal_reason,
            },
        ]
    }


def _terminal_result(
    *,
    address: str = _ADDRESS,
    episode_id: str = _EPISODE,
    sequence_number: int = 0,
    terminal_reason: str = "truncated",
) -> dict[str, dict[str, object]]:
    return {
        address: {
            "state_schema_version": "participant-episode-state/v1",
            "participant_address": address,
            "episode_id": episode_id,
            "sequence_number": sequence_number,
            "status": ParticipantEpisodeStatus.TERMINATED.value,
            "terminal_reason": terminal_reason,
            "initialized_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:05:00Z",
            "terminated_at": "2026-01-01T00:05:00Z",
            "last_control_action": ParticipantEpisodeControlAction.INITIALIZE.value,
            "previous_episode_id": None,
        }
    }


def _closure_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "participant_address": _ADDRESS,
        "episode_id": _EPISODE,
        "sequence_number": 0,
        "source_signal": "rl_truncation",
        "mapped_terminal_reason": "truncated",
        "deriving_authority": "runtime.participant-episode-closure",
        "evidence_refs": ["evidence://step-signal/0"],
        "derived_at": "2026-01-01T00:05:00Z",
    }
    payload.update(overrides)
    return payload


def _violations(closure_records: object) -> list[tuple[str, str]]:
    return list(
        iter_participant_episode_closure_violations(
            closure_records,
            _terminal_history(),
        )
    )


# --- EBM-02: the four terminal reasons are distinct, governed relations. ---


def test_governed_signal_reason_map_is_distinct_and_total() -> None:
    mapping = PARTICIPANT_EPISODE_CLOSURE_SIGNAL_TERMINAL_REASONS
    assert set(mapping) == set(ParticipantEpisodeClosureSignal)
    # rl_termination is a task-dynamics terminal (completed); rl_truncation is a
    # bounded external stop (truncated/timed_out). Neither maps to interrupted
    # (operator-induced, never an RL step signal) and the two never overlap.
    assert ParticipantEpisodeClosureSignal.RL_TERMINATION in mapping
    assert mapping[ParticipantEpisodeClosureSignal.RL_TERMINATION] == frozenset(
        {ParticipantEpisodeTerminalReason.COMPLETED}
    )
    assert ParticipantEpisodeTerminalReason.TRUNCATED in mapping[ParticipantEpisodeClosureSignal.RL_TRUNCATION]
    assert ParticipantEpisodeTerminalReason.INTERRUPTED not in mapping[ParticipantEpisodeClosureSignal.RL_TERMINATION]
    assert ParticipantEpisodeTerminalReason.INTERRUPTED not in mapping[ParticipantEpisodeClosureSignal.RL_TRUNCATION]


def test_closure_record_rejects_ungoverned_signal_reason_mapping() -> None:
    # EBM-02/EBM-10: truncation may not be aliased to timeout-as-termination or
    # to an arbitrary terminal reason; the signal->reason mapping is governed.
    payload = _closure_payload(source_signal="rl_termination", mapped_terminal_reason="truncated")
    with pytest.raises(ValueError, match="governed"):
        ParticipantEpisodeClosureRecord.from_payload(payload)


# --- Closure record round-trips and validates its own shape. ---


def test_closure_record_round_trip() -> None:
    record = ParticipantEpisodeClosureRecord.from_payload(_closure_payload())
    assert record.source_signal is ParticipantEpisodeClosureSignal.RL_TRUNCATION
    assert record.mapped_terminal_reason is ParticipantEpisodeTerminalReason.TRUNCATED
    assert record.evidence_refs == ("evidence://step-signal/0",)
    assert ParticipantEpisodeClosureRecord.from_payload(record.to_payload()) == record


def test_closure_record_requires_evidence() -> None:
    payload = _closure_payload(evidence_refs=[])
    with pytest.raises((ValueError, TypeError)):
        ParticipantEpisodeClosureRecord.from_payload(payload)


def test_closure_record_rejects_unknown_signal() -> None:
    payload = _closure_payload(source_signal="done")
    with pytest.raises((ValueError, TypeError)):
        ParticipantEpisodeClosureRecord.from_payload(payload)


# --- EBM-10 positive: a valid closure record relates the RL signal to the
#     realized terminal reason at the episode history head. ---


def test_valid_closure_record_has_no_violations() -> None:
    assert _violations({_ADDRESS: [_closure_payload()]}) == []


# --- EBM-10 / EBM-08 negatives: fail closed. ---


def test_closure_record_reason_must_match_realized_terminal_reason() -> None:
    # A backend `terminated` signal cannot be equated to a truncation head:
    # rl_termination->completed does not match the truncated realized reason.
    violations = _violations(
        {_ADDRESS: [_closure_payload(source_signal="rl_termination", mapped_terminal_reason="completed")]}
    )
    assert violations
    assert any("terminal_reason" in message for _, message in violations)


def test_closure_record_absent_generation_fails_closed() -> None:
    # Cross-generation / future reference: no terminal head at sequence_number=3.
    violations = _violations({_ADDRESS: [_closure_payload(sequence_number=3)]})
    assert violations
    assert any("history" in message for _, message in violations)


def test_closure_record_cross_episode_fails_closed() -> None:
    violations = _violations({_ADDRESS: [_closure_payload(episode_id="other-episode")]})
    assert violations


def test_closure_record_outer_key_must_match_participant_address() -> None:
    violations = _violations({"someone-else": [_closure_payload()]})
    assert violations
    assert any("participant_address" in message for _, message in violations)


def test_closure_record_against_non_terminal_episode_fails_closed() -> None:
    # A running episode has no realized terminal reason to close over.
    running_history = {
        _ADDRESS: [
            {
                "event_type": "episode_initialized",
                "timestamp": "2026-01-01T00:00:00Z",
                "participant_address": _ADDRESS,
                "episode_id": _EPISODE,
                "sequence_number": 0,
                "control_action": "initialize",
            }
        ]
    }
    violations = list(
        iter_participant_episode_closure_violations(
            {_ADDRESS: [_closure_payload()]},
            running_history,
        )
    )
    assert violations


def test_closure_records_container_must_be_mapping() -> None:
    violations = _violations([_closure_payload()])
    assert violations


# --- Runtime episode-validation seam (EBM-10 enforcement point). ---


def test_runtime_closure_diagnostics_accept_valid_record() -> None:
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_runtime.result_contracts import participant_episode_closure_contract_diagnostics

    snapshot = RuntimeSnapshot(
        participant_episode_history=_terminal_history(),
        participant_episode_closure_records={_ADDRESS: [_closure_payload()]},
    )
    assert participant_episode_closure_contract_diagnostics(snapshot) == []


def test_runtime_closure_diagnostics_reject_unrelated_terminal() -> None:
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_runtime.result_contracts import participant_episode_closure_contract_diagnostics

    # A backend 'terminated' equated to the episode terminal reason with no valid
    # closure record must be flagged as a backend-contract violation.
    snapshot = RuntimeSnapshot(
        participant_episode_history=_terminal_history(),
        participant_episode_closure_records={
            _ADDRESS: [_closure_payload(source_signal="rl_termination", mapped_terminal_reason="completed")]
        },
    )
    diagnostics = participant_episode_closure_contract_diagnostics(snapshot)
    assert diagnostics
    assert all(diag.code == "runtime.backend-contract-invalid" for diag in diagnostics)


def test_canonical_runtime_state_validation_enforces_closure_records() -> None:
    # EBM-10 enforcement is wired into the aggregate backend-result validation
    # path, not just the standalone helper: a contradictory closure record on the
    # snapshot is rejected by participant_runtime_state_contract_diagnostics.
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_runtime.result_contracts import participant_runtime_state_contract_diagnostics

    valid = RuntimeSnapshot(
        participant_episode_results=_terminal_result(),
        participant_episode_history=_terminal_history(),
        participant_episode_closure_records={_ADDRESS: [_closure_payload()]},
    )
    assert participant_runtime_state_contract_diagnostics(valid) == []

    contradictory = RuntimeSnapshot(
        participant_episode_results=_terminal_result(),
        participant_episode_history=_terminal_history(),
        participant_episode_closure_records={_ADDRESS: [_closure_payload(sequence_number=3)]},
    )
    diagnostics = participant_runtime_state_contract_diagnostics(contradictory)
    assert diagnostics
    assert all(diag.code == "runtime.backend-contract-invalid" for diag in diagnostics)


def test_public_runtime_snapshot_preserves_and_validates_closure_records() -> None:
    snapshot = RuntimeSnapshot(
        participant_episode_results=_terminal_result(),
        participant_episode_history=_terminal_history(),
        participant_episode_closure_records={_ADDRESS: [_closure_payload()]},
    )
    payload = _snapshot_payload(snapshot)

    model = RuntimeSnapshotEnvelopeModel.model_validate(payload)
    schema_errors = list(Draft202012Validator(schema_bundle()["runtime-snapshot-v1"]).iter_errors(payload))

    assert model.participant_episode_closure_records == snapshot.participant_episode_closure_records
    assert schema_errors == []
    assert _semantic_diagnostics("runtime-snapshot-v1", payload) == []


def test_public_runtime_snapshot_rejects_invalid_closure_record_semantics() -> None:
    snapshot = RuntimeSnapshot(
        participant_episode_results=_terminal_result(),
        participant_episode_history=_terminal_history(),
        participant_episode_closure_records={_ADDRESS: [_closure_payload(sequence_number=3)]},
    )

    diagnostics = _semantic_diagnostics("runtime-snapshot-v1", _snapshot_payload(snapshot))

    assert any("history" in diagnostic.message for diagnostic in diagnostics)
