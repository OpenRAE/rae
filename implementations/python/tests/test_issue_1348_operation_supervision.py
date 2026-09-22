"""Bounded design witnesses; these are not runtime/backend conformance claims."""

from dataclasses import replace
from itertools import product

import pytest
from operation_supervision_model import (
    Evidence,
    Operation,
    admit,
    continuation_allowed,
    deadline_expired,
    publish,
    settle,
    start,
    stop_admission,
    supervise,
)


@pytest.mark.parametrize("supported,willing", [(False, True), (True, False), (False, False)])
def test_required_guarantee_rejected_before_claim(supported: bool, willing: bool) -> None:
    with pytest.raises(ValueError, match="admission"):
        admit(
            required=frozenset({"interrupt"}),
            supported=frozenset({"interrupt"}) if supported else frozenset(),
            willing=willing,
        )


def test_stopping_admission_does_not_interrupt_running_work() -> None:
    running = start(admit())
    stopped = stop_admission(running)
    assert stopped.state == "RUNNING"
    assert stopped.invocations == 1
    assert not stopped.quiescent
    assert stopped.cancel == "none"
    with pytest.raises(ValueError, match="admission"):
        start(stop_admission(admit()))


def test_pre_dispatch_cancellation_wins_without_backend_invocation() -> None:
    cancelled = supervise(admit(), actor="supervisor")
    assert cancelled.state == "CANCELLED"
    assert cancelled.invocations == 0
    assert cancelled.actor == "author"
    assert cancelled.supervisor == "supervisor"
    assert cancelled.audit == ("CANCELLED",)
    with pytest.raises(ValueError):
        start(cancelled)


@pytest.mark.parametrize("reply", ["requested", "accepted", "refused", "unsupported"])
def test_cancellation_disposition_is_not_a_terminal_outcome(reply: str) -> None:
    requested = supervise(start(admit()), actor="operator", reply=reply)
    assert requested.state == "RUNNING"
    assert not requested.quiescent
    assert requested.audit == ()
    terminal = settle(requested, Evidence("absent", quiescent=False), cancelled=True)
    assert terminal.state == "INDETERMINATE"
    assert terminal.quarantined


def test_supervision_reauthorizes_and_never_replaces_original_actor() -> None:
    running = start(admit())
    with pytest.raises(ValueError, match="authorization"):
        supervise(running, actor="other", authorized=False)
    assert running.actor == "author"
    assert running.supervisor is None


@pytest.mark.parametrize(
    "effects,quiescent,validated,satisfies,expected",
    [
        ("absent", True, True, False, "FAILED"),
        ("partial", True, True, False, "FAILED"),
        ("complete", True, True, True, "SUCCEEDED"),
        ("complete", True, True, False, "FAILED"),
        ("unknown", True, True, False, "INDETERMINATE"),
        ("partial", False, True, False, "INDETERMINATE"),
        ("complete", True, False, True, "INDETERMINATE"),
        ("absent", False, True, False, "INDETERMINATE"),
    ],
)
def test_outcome_requires_effect_evidence_and_full_semantic_satisfaction(
    effects: str,
    quiescent: bool,
    validated: bool,
    satisfies: bool,
    expected: str,
) -> None:
    terminal = settle(start(admit()), Evidence(effects, quiescent, validated, satisfies))
    assert terminal.state == expected
    assert terminal.audit == (expected,)
    assert terminal.quarantined == (expected == "INDETERMINATE")


def test_proven_cancellation_can_retain_known_partial_effects() -> None:
    running = supervise(start(admit()), actor="operator", reply="accepted")
    result = settle(running, Evidence("partial", quiescent=True), cancelled=True)
    assert result.state == "CANCELLED"
    assert result.effects == "partial"
    assert not result.quarantined
    assert result.revision == running.revision + 1


def test_validated_noop_can_satisfy_the_contract_without_snapshot_change() -> None:
    running = start(admit())
    result = settle(running, Evidence("absent", quiescent=True, satisfies=True))
    assert result.state == "SUCCEEDED"
    assert result.revision == running.revision


def test_completion_cancel_race_commits_only_one_terminal_result() -> None:
    running = start(admit())
    completed = settle(running, Evidence("complete", True, satisfies=True))
    assert supervise(completed, actor="operator") == completed
    with pytest.raises(ValueError, match="terminal"):
        settle(completed, Evidence("absent", True), cancelled=True)
    requested = supervise(running, actor="operator", reply="accepted")
    # An accepted request does not make an already-completed effect disappear.
    result = settle(requested, Evidence("complete", True, satisfies=True))
    assert result.state == "SUCCEEDED"
    assert result.cancel == "accepted"


def test_duplicate_cancel_and_late_completion_do_not_reinvoke_or_rewrite() -> None:
    requested = supervise(start(admit()), actor="operator")
    assert supervise(requested, actor="operator") == requested
    terminal = settle(requested, Evidence("unknown", False))
    with pytest.raises(ValueError, match="terminal"):
        settle(terminal, Evidence("complete", True, satisfies=True))
    assert terminal.invocations == 1
    assert terminal.state == "INDETERMINATE"
    assert terminal.quarantined


def test_stale_revision_cannot_publish_or_authorize_another_invocation() -> None:
    running = start(admit())
    with pytest.raises(ValueError, match="revision"):
        settle(running, Evidence("complete", True, satisfies=True), expected_revision=99)
    assert running.invocations == 1
    assert running.state == "RUNNING"


@pytest.mark.parametrize("persisted", [False, True])
def test_lost_commit_acknowledgement_preserves_atomic_cut_and_closes_admission(persisted: bool) -> None:
    before = start(admit())
    after = settle(before, Evidence("complete", True, satisfies=True))
    result = publish(before, after, persisted=persisted, acknowledged=False)
    assert result.visible == before
    assert result.poisoned
    assert result.authoritative in (before, after)
    assert (result.authoritative.state == "SUCCEEDED") == bool(result.authoritative.audit)
    assert result.authoritative.invocations == 1


def test_acknowledged_commit_exposes_snapshot_terminal_and_audit_together() -> None:
    before = start(admit())
    after = settle(before, Evidence("partial", True))
    result = publish(before, after, persisted=True, acknowledged=True)
    assert result.visible == result.authoritative == after
    assert (after.state, after.effects, after.audit) == ("FAILED", "partial", ("FAILED",))


def test_operational_deadline_is_monotonic_and_independent_of_scenario_pause() -> None:
    assert not deadline_expired(started=10, now=14, budget=5)
    assert deadline_expired(started=10, now=15, budget=5)
    assert deadline_expired(started=10, now=16, budget=5)
    with pytest.raises(ValueError):
        deadline_expired(started=10, now=9, budget=5)
    # Expiry supplies no effect or cessation evidence, even if semantic time is paused.
    assert settle(start(admit()), Evidence("unknown", False)).state == "INDETERMINATE"


@pytest.mark.parametrize("action", ["retry", "resume", "new-trial"])
@pytest.mark.parametrize("durable", [False, True])
def test_durability_never_supplies_missing_authored_permission(action: str, durable: bool) -> None:
    assert not continuation_allowed(
        action,
        permitted=False,
        durable=durable,
        quiescent=True,
        effects="absent",
        continuity=True,
        allocated=True,
        clean=True,
    )


def test_resume_requires_continuity_and_new_trial_requires_allocation_and_clean_state() -> None:
    assert not continuation_allowed("resume", permitted=True, quiescent=True, effects="absent")
    assert continuation_allowed("resume", permitted=True, quiescent=True, effects="partial", continuity=True)
    assert not continuation_allowed("new-trial", permitted=True, quiescent=True, effects="absent", clean=True)
    assert not continuation_allowed("new-trial", permitted=True, quiescent=True, effects="absent", allocated=True)
    assert continuation_allowed(
        "new-trial", permitted=True, quiescent=True, effects="absent", allocated=True, clean=True
    )


@pytest.mark.parametrize("posture", ["disallow", "idempotent", "reset", "compensate"])
def test_after_effect_retry_needs_selected_safety_evidence_and_remaining_budget(posture: str) -> None:
    args = dict(permitted=True, quiescent=True, effects="partial", posture=posture)
    assert not continuation_allowed("retry", **args)
    assert continuation_allowed("retry", **args, safety_proved=True) == (posture != "disallow")
    assert not continuation_allowed("retry", **args, safety_proved=True, attempts_left=0)
    assert not continuation_allowed("retry", **{**args, "quiescent": False}, safety_proved=True)


def test_unknown_residual_effects_block_all_continuations_in_the_affected_scope() -> None:
    for action in ("retry", "resume", "new-trial"):
        assert not continuation_allowed(
            action,
            permitted=True,
            quiescent=True,
            effects="unknown",
            continuity=True,
            allocated=True,
            clean=True,
            safety_proved=True,
        )


def test_bounded_outcome_space_never_confuses_uncertainty_with_success_or_cancellation() -> None:
    running = supervise(start(admit()), actor="operator", reply="accepted")
    for effects, quiescent, validated, satisfies, cancelled in product(
        ("absent", "partial", "complete", "unknown"),
        (False, True),
        (False, True),
        (False, True),
        (False, True),
    ):
        result = settle(running, Evidence(effects, quiescent, validated, satisfies), cancelled=cancelled)
        if not quiescent or not validated or effects == "unknown":
            assert result.state == "INDETERMINATE"
            assert result.quarantined
        assert len(result.audit) == 1
        assert result.invocations == 1
        assert result.actor == running.actor


def test_invalid_model_inputs_are_not_positive_evidence() -> None:
    with pytest.raises(ValueError):
        settle(start(admit()), Evidence("invented", True))
    with pytest.raises(ValueError):
        supervise(start(admit()), actor="operator", reply="done")
    with pytest.raises(ValueError):
        start(replace(Operation(), state="FAILED"))
