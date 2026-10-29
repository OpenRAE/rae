"""Portable modular-control probes measure the actual shared-runtime boundary."""

from dataclasses import replace

import pytest
from participant_control_v2_fixtures import Resolver, binding, optional_advice
from participant_crossing_fixtures import PARTICIPANT, admission_request, behavior, evidence, identity
from raes_conformance.conformance import run_modular_control_conformance
from raes_conformance.conformance.modular_control_types import (
    ModularControlCase,
    ModularControlOperation,
    ModularControlStep,
)
from raes_conformance.conformance.report import backend_conformance_report_payload
from sem233_flow_sink_fixtures import permit_resolver
from test_issue_1069_participant_control_orchestration import control_target


class Harness:
    def __init__(self, *cases):
        self.items = cases

    def cases(self, target):
        return self.items


def action_step(*, key="parent", refusal=False):
    return ModularControlStep(
        ModularControlOperation.ACTION,
        dict(
            participant_behavior=behavior(),
            admission_request=admission_request(),
            identity=identity(audience_bound=True),
            crossing_evidence=evidence(),
            idempotency_key=key,
        ),
        expect_refusal=refusal,
    )


def case_for(obligation="dependency", *, owner=None, disposition="eligible", calls=1, steps=None):
    owner = owner or Resolver()
    return ModularControlCase(
        name=obligation,
        obligation=obligation,
        participant_address=PARTICIPANT,
        episode_id="episode-1",
        options=dict(participant_control=binding(owner), crossing_policy_resolver=permit_resolver()),
        steps=steps or (action_step(),),
        expected_compositions=(disposition,) if disposition is not None else (),
        expected_calls={"participant_runtime.admit_action": calls},
    )


def run(*cases, required=("dependency",), effects=()):
    return run_modular_control_conformance(
        control_target(), harness=Harness(*cases), obligations=required, effect_kinds=effects
    )


def test_dependency_case_drives_real_providers_and_binds_report():
    owner = Resolver()
    report = run(case_for(owner=owner))
    assert report.passed
    assert owner.calls == ["fact", "assessment", "rule"]
    payload = backend_conformance_report_payload(report)
    case = payload["cases"][0]
    assert case["execution_basis"] == "hermetic-live"
    assert not payload["native_conformance"]
    binding = case["modular_control"]
    assert binding["obligation"] == "dependency"
    assert binding["artifact_digests"]["apparatus"]
    assert binding["artifact_digests"]["cut"]
    assert binding["actual_calls"] == {"participant_runtime.admit_action": 1}


@pytest.mark.parametrize("harness", [None, Harness()])
def test_missing_required_case_never_passes(harness):
    report = run_modular_control_conformance(control_target(), harness=harness, obligations=("dependency",))
    assert not report.passed
    assert report.cases[0].outcome == "unsupported"
    assert report.cases[0].modular_control.obligation == "dependency"


@pytest.mark.parametrize("decision", ["deny", "withhold"])
def test_strict_parent_refusal_counts_zero_prohibited_calls(decision):
    owner = Resolver()
    owner.decision = decision
    report = run(case_for("strict-denial", owner=owner, disposition=decision, calls=0), required=("strict-denial",))
    assert report.passed
    assert report.cases[0].modular_control.actual_calls == {}


def test_dishonest_denial_expectation_cannot_pass():
    # A caller cannot turn a permit into a passing denial case by expecting it.
    report = run(case_for("strict-denial"), required=("strict-denial",))
    assert not report.passed


@pytest.mark.parametrize("failure", ["exception", "malformed", "missing", "stale"])
def test_optional_failure_has_no_veto(failure):
    owner = optional_advice()
    owner.providers["monitor"].failure = failure
    report = run(case_for("optional-failure", owner=owner), required=("optional-failure",))
    assert report.passed


def test_optional_label_cannot_replace_observed_lost_advice():
    assert not run(case_for("optional-failure"), required=("optional-failure",)).passed


@pytest.mark.parametrize("mode", ["none", "bad_coverage", "stale"])
def test_missing_coverage_or_stale_cut_prevents_dispatch(mode):
    owner = Resolver()
    setattr(owner, mode, True)
    obligation = "stale-cut" if mode == "stale" else "mandatory-coverage"
    report = run(case_for(obligation, owner=owner, disposition=None, calls=0), required=(obligation,))
    # A callback that throws before returning a typed request supplies no
    # evidence for why applicability failed. It must not earn coverage.
    assert report.passed is (mode != "bad_coverage")
    assert owner.calls == []


def test_empty_subset_needs_complete_inapplicability():
    owner = Resolver()
    owner.empty = True
    assert run(case_for("applicable-subset", owner=owner), required=("applicable-subset",)).passed
    assert not run(case_for("applicable-subset"), required=("applicable-subset",)).passed


def test_durable_reopen_and_duplicate_do_not_repeat_parent(tmp_path):
    selected = case_for(
        "restart",
        steps=(action_step(), ModularControlStep(ModularControlOperation.REOPEN, {}), action_step()),
    )
    report = run_modular_control_conformance(
        control_target(), harness=Harness(selected), obligations=("restart",), store_root=tmp_path
    )
    assert report.passed
    assert report.cases[0].modular_control.reopened
    assert report.cases[0].modular_control.actual_calls == {"participant_runtime.admit_action": 1}


def test_wrong_expected_call_count_and_duplicate_case_fail_closed():
    selected = case_for(calls=0)
    assert not run(selected).passed
    assert not run(selected, selected).passed


def test_unselected_or_unknown_obligations_are_not_executed():
    owner = Resolver()
    report = run(case_for("unexpected", owner=owner))
    assert not report.passed
    assert owner.calls == []


def test_private_callback_failure_is_sanitized():
    sentinel = "PRIVATE-CALLBACK-CREDENTIAL-1071"

    def fail(*args):
        raise RuntimeError(sentinel)

    selected = replace(case_for(), steps=(ModularControlStep(ModularControlOperation.ACTION, fail),))
    payload = backend_conformance_report_payload(run(selected))
    assert not payload["passed"]
    assert sentinel not in str(payload)


def test_claimed_effect_with_no_real_case_is_gating_failure():
    report = run(case_for(), effects=("inject",))
    assert not report.passed
    assert any(case.modular_control.obligation == "effect:inject" for case in report.cases)


def test_default_catalog_is_not_an_empty_success():
    report = run_modular_control_conformance(control_target(), harness=Harness())
    assert not report.passed
    assert len(report.cases) > 10


def test_authored_recovery_is_checked_from_sdl_to_plan():
    report = run(required=("authored-recovery",))
    assert report.passed
    selected = report.cases[0]
    assert selected.execution_basis == "fixture-only"
    assert selected.modular_control.artifact_digests["policy"]


def test_serialization_refuses_unbound_or_overstated_modular_pass():
    report = run(case_for())
    assert report.passed
    item = report.cases[0]
    unbound = replace(item, modular_control=replace(item.modular_control, artifact_digests={}))
    unbound_report = replace(report, cases=(unbound,))
    native_report = replace(report, native_conformance=True)
    with pytest.raises(ValueError, match="modular"):
        backend_conformance_report_payload(unbound_report)
    with pytest.raises(ValueError, match="modular"):
        backend_conformance_report_payload(native_report)


def test_cleanup_failure_is_visible_and_keeps_private_details_out():
    sentinel = "PRIVATE-CLEANUP-1071"

    def fail():
        raise RuntimeError(sentinel)

    selected = replace(case_for(), cleanup=fail)
    report = run(selected)
    assert not report.passed
    assert report.cases[0].cleanup_verified is False
    assert report.cases[0].residual_state == ("cleanup-unverified",)
    assert sentinel not in str(backend_conformance_report_payload(report))


def test_target_runner_preserves_harness_failures():
    from raes_conformance.conformance import run_target_conformance

    class BrokenHarness:
        def cases(self, target):
            raise ValueError("PRIVATE-HARNESS-1071")

    report = run_target_conformance(control_target(), modular_control_harness=BrokenHarness())
    assert not report.passed
    assert "conformance.modular-harness-invalid" in {item.code for item in report.diagnostics}
    assert "PRIVATE-HARNESS-1071" not in str(backend_conformance_report_payload(report))


def test_invalid_subset_does_not_echo_private_identifiers():
    sentinel = "PRIVATE-SUBSET-CREDENTIAL-1071"
    report = run_modular_control_conformance(control_target(), obligations=(sentinel,))
    assert not report.passed
    assert sentinel not in str(backend_conformance_report_payload(report))
