"""Review findings cannot be reintroduced by generic refusals or method counts."""

from dataclasses import replace

import pytest
from participant_crossing_fixtures import PARTICIPANT, identity
from raes_conformance.conformance import run_modular_control_conformance
from raes_conformance.conformance.modular_control_types import ModularControlOperation, ModularControlStep
from raes_runtime.control_plane import RuntimeControlPlane
from test_issue_1069_participant_control_effects import _target
from test_issue_1071_effect_conformance import handoff_case
from test_issue_1071_modular_conformance import Harness, action_step, case_for, run


@pytest.mark.parametrize("obligation", ["mandatory-coverage", "strict-denial", "stale-cut", "conflict", "integrity"])
def test_unrelated_authority_refusal_cannot_earn_other_negative_coverage(obligation):
    step = ModularControlStep(
        ModularControlOperation.DISPATCH,
        dict(participant_address=PARTICIPANT, identity=identity(bound=False)),
        expect_refusal=True,
    )
    selected = case_for(obligation, disposition=None, calls=0, steps=(step,))
    assert not run(selected, required=(obligation,)).passed


@pytest.mark.parametrize("reopen", [False, True])
def test_distinct_requests_cannot_establish_exact_retry_or_restart(reopen):
    obligation = "restart" if reopen else "duplicate"
    steps = (action_step(key="first"),)
    if reopen:
        steps += (ModularControlStep(ModularControlOperation.REOPEN, {}),)
    selected = replace(
        case_for(obligation, calls=2, steps=(*steps, action_step(key="second"))),
        expected_compositions=("eligible", "eligible"),
    )
    assert not run(selected, required=(obligation,)).passed


def test_changed_effect_receipt_cannot_pass_an_exact_repeat(monkeypatch):
    original = RuntimeControlPlane.dispatch_participant_control_effects
    calls = 0

    def changed(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        values = original(self, *args, **kwargs)
        return values if calls == 1 else tuple(replace(value, receipt_ref="different-owner") for value in values)

    monkeypatch.setattr(RuntimeControlPlane, "dispatch_participant_control_effects", changed)
    report = run_modular_control_conformance(
        _target(), harness=Harness(handoff_case()), obligations=(), effect_kinds=("handoff",)
    )
    assert not report.passed


def test_eligible_evaluation_does_not_hide_a_failed_backend_operation():
    from test_issue_1069_participant_control_orchestration import control_target

    selected = control_target()

    def failed(*args, **kwargs):
        raise RuntimeError("PRIVATE-BACKEND-FAILURE")

    selected.participant_runtime.admit_action = failed
    report = run_modular_control_conformance(selected, harness=Harness(case_for()), obligations=("dependency",))
    assert not report.passed


def test_reopen_requires_a_matching_replay_after_the_reopen():
    selected = case_for(
        "restart", steps=(action_step(), action_step(), ModularControlStep(ModularControlOperation.REOPEN, {}))
    )
    assert not run(selected, required=("restart",)).passed


def test_reopen_detects_a_lost_durable_worker_claim(monkeypatch):
    from raes_runtime.control_plane import LocalControlPlaneStore

    close = RuntimeControlPlane.close
    load = LocalControlPlaneStore.load_records
    reopened = False

    def close_first(self):
        nonlocal reopened
        close(self)
        reopened = True

    def lost_claim(self):
        records = load(self)
        if reopened:
            # Fault the store's read surface, never live database bytes. The
            # parent receipt and evaluation remain; a worker claim disappears.
            return {key: value for key, value in records.items() if value.idempotency_key == "parent"}
        return records

    monkeypatch.setattr(RuntimeControlPlane, "close", close_first)
    monkeypatch.setattr(LocalControlPlaneStore, "load_records", lost_claim)
    selected = case_for(
        "restart", steps=(action_step(), ModularControlStep(ModularControlOperation.REOPEN, {}), action_step())
    )
    report = run(selected, required=("restart",))
    assert not report.passed


def test_genuine_unresolved_coverage_has_bound_negative_evidence():
    from participant_control_v2_fixtures import Resolver

    owner = Resolver()
    owner.coverage = "unresolved"
    selected = case_for("mandatory-coverage", owner=owner, disposition="withhold", calls=0)
    report = run(selected, required=("mandatory-coverage",))
    assert report.passed
    assert report.cases[0].modular_control.refusal_causes == ("mandatory-coverage",)


def test_optional_corruption_cannot_explain_an_unrelated_required_failure():
    from participant_control_v2_fixtures import optional_advice

    owner = optional_advice()
    owner.selection = owner.selection.model_copy(
        update={"slots": tuple(slot.model_copy(update={"dependencies": ()}) for slot in owner.selection.slots)}
    )
    owner.providers["influence"].failure = "missing"
    owner.providers["monitor"].failure = "malformed"
    report = run(case_for("integrity", owner=owner, disposition="failed", calls=0), required=("integrity",))
    assert not report.passed


def test_unresolved_coverage_cannot_earn_strict_policy_denial_credit():
    from participant_control_v2_fixtures import Resolver

    owner = Resolver()
    owner.coverage = "unresolved"
    report = run(case_for("strict-denial", owner=owner, disposition="withhold", calls=0), required=("strict-denial",))
    assert not report.passed


def test_report_names_a_runtime_suite_instead_of_an_unpublished_backend_profile():
    report = run(required=("authored-recovery",))
    assert report.claim.right_carrier_ref == "runtime-probe-suite:modular-control-runtime/v2"


def test_an_earlier_replay_cannot_cover_a_later_reopen():
    reopen = ModularControlStep(ModularControlOperation.REOPEN, {})
    selected = case_for("restart", steps=(action_step(), reopen, action_step(), reopen))
    assert not run(selected, required=("restart",)).passed
