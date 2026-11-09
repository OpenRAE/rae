"""ASR-535 executable participant information-flow and relation assurance.

Four assurance lanes stay independent here: bounded semantic falsification over
the SEM-230 test-local model, RUN-319 runtime enforcement, API-407 backend
conformance, and formal verification. ASR-535 deliberately does not enter the
formal lane: it makes no model-check and no proof claim, so the governed
relation ``policy-noninterference`` keeps its ``deliberately-unproved`` status
and every case below is finite falsification evidence only.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from itertools import product

import pytest
from asr535_policy_probe_harness import (
    ALL_POLICY_FEATURES,
    PROBED_POLICY_FEATURES,
    OverclaimingPolicyProbeHarness,
    ParticipantPolicyConformanceHarness,
    RefusalOnlyPolicyProbeHarness,
)
from hypothesis import given, settings
from hypothesis import strategies as st
from participant_crossing_fixtures import policy_capable_target
from raes_conformance.conformance.diagnostics import sanitized_failure_message
from raes_conformance.conformance.fixture_suite import run_fixture_suite
from raes_conformance.conformance.profiles import BackendCapabilityProfile
from raes_conformance.conformance.report import (
    backend_conformance_report_payload,
    validate_backend_conformance_report,
)
from raes_conformance.conformance.target import run_target_conformance
from raes_conformance.conformance.validators import validate_contract_payload
from sem230_information_flow_model import (
    Crossing,
    CrossingKind,
    Label,
    ProjectionPolicyDecision,
    policy_noninterference_holds,
    project_history,
)

_SECRET_MARKER = "participant-hidden-answer-9d41c0"


def test_rejected_payload_content_never_reaches_a_conformance_diagnostic() -> None:
    """A rejected payload is described, never echoed, into report diagnostics.

    Pydantic's ``ValidationError`` carries ``input_value``. Concatenating it into
    a conformance diagnostic turns a malformed-payload failure into a disclosure
    oracle once the report is persisted.
    """

    diagnostics = validate_contract_payload(
        "participant-crossing-occurrence-v1",
        {"occurrence": {"policy": {"hidden_answer": _SECRET_MARKER}}},
    )

    assert diagnostics
    for diagnostic in diagnostics:
        assert _SECRET_MARKER not in diagnostic.message
        assert "input_value" not in diagnostic.message


def test_sanitized_failure_message_describes_without_echoing_input() -> None:
    class _Boom(ValueError):
        pass

    message = sanitized_failure_message(_Boom(f"rejected {_SECRET_MARKER}"))

    assert _SECRET_MARKER not in message
    assert message


def test_profile_load_diagnostics_carry_no_host_path(tmp_path) -> None:
    """Report diagnostics identify a bad profile without disclosing the filesystem.

    Conformance reports are persisted as run artifacts, so a host path in a
    diagnostic leaves the checkout layout in durable evidence.
    """

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / "provisioning-only.json").write_text(
        json.dumps({"profile": "full-remote-control-plane", "required_contracts": ["backend-manifest-v2"]}),
        encoding="utf-8",
    )

    report = run_fixture_suite(profile=BackendCapabilityProfile.PROVISIONING_ONLY, profiles_root=backend_dir)

    messages = [diag.message for diag in report.diagnostics]
    assert any(diag.code == "conformance.profile-load-failed" for diag in report.diagnostics)
    assert any("full-remote-control-plane" in message for message in messages)
    assert not any(str(tmp_path) in message for message in messages)


def test_declared_policy_support_without_a_probe_harness_is_unsupported_not_passed() -> None:
    """A positive API-407 declaration is never satisfied by an absent probe.

    Before ASR-535 the target runner projected the static manifest declaration
    into a passing case, so a backend could declare exact participant-policy
    support and conform without any behavior ever being driven.
    """

    target = policy_capable_target(*ALL_POLICY_FEATURES)

    report = run_target_conformance(target)

    policy_cases = [case for case in report.cases if case.policy_binding is not None]
    assert policy_cases, "declared participant-policy support must produce policy cases"
    assert {case.capability_feature for case in policy_cases} == set(ALL_POLICY_FEATURES)
    assert all(case.outcome == "unsupported" for case in policy_cases)
    assert not any(case.passed for case in policy_cases)
    assert not report.passed


def test_unsupported_declarations_claim_nothing_and_add_no_policy_case() -> None:
    """The shipped stub declares every policy feature unsupported."""

    report = run_target_conformance(policy_capable_target())

    unsupported_features = {
        entry.feature
        for entry in policy_capable_target().manifest.participant_runtime.feature_support
        if entry.feature in ALL_POLICY_FEATURES and entry.support_level.value == "unsupported"
    }
    policy_cases = [case for case in report.cases if case.policy_binding is not None]
    assert unsupported_features == set(ALL_POLICY_FEATURES) - {"participant_ingress_admission"}
    assert {case.capability_feature for case in policy_cases} == {"participant_ingress_admission"}
    assert not [case for case in policy_cases if case.capability_feature in unsupported_features]


def test_every_finite_obligation_is_driven_through_the_shipped_runtime_boundary() -> None:
    """The eleven ASR-535 obligations each produce a bound, passing case."""

    target = policy_capable_target(*PROBED_POLICY_FEATURES)

    report = run_target_conformance(target, participant_policy_harness=ParticipantPolicyConformanceHarness())

    policy_cases = [case for case in report.cases if case.policy_binding is not None]
    obligations = {case.policy_binding.obligation for case in policy_cases}
    assert obligations == {
        # authorized paths, which are what establish the declared capabilities
        "admitted-ingress",
        "authorized-projection",
        "governed-declassification-release",
        "redaction",
        "participant-directed-inject-delivery",
        # refusal obligations
        "denial",
        "withholding",
        "unauthorized-declassification",
        "transformation",
        "stale-or-revoked-policy",
        "cross-participant-leakage",
        "backend-weakening",
        "unsupported-capability",
    }
    failed = [(case.name, [diag.message for diag in case.diagnostics]) for case in policy_cases if not case.passed]
    assert not failed, failed


def test_policy_cases_bind_exact_coordinates_rather_than_prose_in_a_case_name() -> None:
    target = policy_capable_target(*PROBED_POLICY_FEATURES)

    report = run_target_conformance(target, participant_policy_harness=ParticipantPolicyConformanceHarness())

    policy_cases = [case for case in report.cases if case.policy_binding is not None]
    assert policy_cases, "the probe harness must emit bound participant-policy cases"
    for case in policy_cases:
        binding = case.policy_binding
        assert binding.claim.taxonomy_revision == "rev8"
        assert binding.claim.relation_id == "policy-noninterference"
        assert binding.claim.quantifier_scope == "finite-cases"
        assert binding.claim.evidence_scope == "finite"
        assert binding.claim.assurance_status == "tested"
        assert binding.claim.observation_projection_revision == "rev1"
        assert binding.policy_revision
        assert binding.decision_cut_ref
        assert binding.assumptions.order_model
        assert binding.assumptions.scheduler_class
        assert binding.assumptions.probability.startswith("outside scope")
        assert case.finite_scope
        assert case.probe_set_digest
        assert any("noninterference" in claim for claim in case.explicit_non_claims)


def test_an_overclaiming_target_fails_instead_of_retaining_its_exact_claim() -> None:
    """Declaring exact support and then releasing on denial must not conform."""

    target = policy_capable_target(*ALL_POLICY_FEATURES)

    report = run_target_conformance(target, participant_policy_harness=OverclaimingPolicyProbeHarness())

    denial_case = next(
        case for case in report.cases if case.policy_binding and case.policy_binding.obligation == "denial"
    )
    assert not denial_case.passed
    assert denial_case.outcome == "failed"
    assert denial_case.declared_support_level == "exact"
    assert any(diag.code == "conformance.participant-policy-overclaim" for diag in denial_case.diagnostics)
    assert not report.passed


def test_finite_policy_cases_never_promote_the_report_to_a_noninterference_claim() -> None:
    target = policy_capable_target(*PROBED_POLICY_FEATURES)

    report = run_target_conformance(target, participant_policy_harness=ParticipantPolicyConformanceHarness())

    assert report.claim.relation_id == "bounded-probe-success"
    assert report.claim.quantifier_scope == "finite-cases"
    assert report.claim.evidence_scope == "finite"
    assert report.claim.assurance_status == "tested"


def test_report_validation_rejects_a_universal_quantifier_backed_by_finite_evidence() -> None:
    report = run_target_conformance(
        policy_capable_target(*PROBED_POLICY_FEATURES),
        participant_policy_harness=ParticipantPolicyConformanceHarness(),
    )
    inflated = replace(
        report,
        claim=report.claim.model_copy(update={"quantifier_scope": "all-traces", "evidence_scope": "finite"}),
    )

    with pytest.raises(ValueError, match="universal quantifier"):
        validate_backend_conformance_report(inflated)


def test_report_validation_rejects_native_conformance_without_native_evidence() -> None:
    report = run_target_conformance(
        policy_capable_target(*PROBED_POLICY_FEATURES),
        participant_policy_harness=ParticipantPolicyConformanceHarness(),
    )
    inflated = replace(report, native_conformance=True)

    with pytest.raises(ValueError, match="native conformance"):
        validate_backend_conformance_report(inflated)


def test_report_validation_requires_every_claimed_case_to_be_present() -> None:
    report = run_target_conformance(
        policy_capable_target(*PROBED_POLICY_FEATURES),
        participant_policy_harness=ParticipantPolicyConformanceHarness(),
    )
    dropped = replace(report, cases=report.cases[:-1])

    with pytest.raises(ValueError, match="claimed case"):
        validate_backend_conformance_report(dropped)


def test_serialization_runs_the_validation_seam_before_the_payload_is_produced() -> None:
    report = run_target_conformance(
        policy_capable_target(*PROBED_POLICY_FEATURES),
        participant_policy_harness=ParticipantPolicyConformanceHarness(),
    )

    payload = backend_conformance_report_payload(report)

    policy_payloads = [case["policy_binding"] for case in payload["cases"] if case["policy_binding"]]
    assert policy_payloads
    assert all(entry["assumptions"]["scheduler_class"] for entry in policy_payloads)
    inflated = replace(report, native_conformance=True)
    with pytest.raises(ValueError):
        backend_conformance_report_payload(inflated)


# --- semantic falsification lane -------------------------------------------
#
# The cases below exhaust a *declared finite domain* of the SEM-230 test-local
# model. Exhausting a bound is not model checking and not proof: the domain is
# fixed by _BOUND below, and nothing outside it is quantified.

_LOW_REF = "status"
_HIGH_REF = "secret"
_HIGH_VALUES = ("h0", "h1")
_BOUND_RUN_LENGTH = 3


def _bounded_policy() -> ProjectionPolicyDecision:
    return ProjectionPolicyDecision(
        policy_id="participant-egress",
        revision="rev1",
        decision_ref="policy-decisions.participant-egress.cut-1",
        decision_cut_ref="state-cuts.1",
        visible_low_refs=frozenset({_LOW_REF}),
        permitted_declassifications=frozenset(),
    )


def _crossing(order: int, source_ref: str, value: str, **overrides: object) -> Crossing:
    fields: dict[str, object] = {
        "participant": "alice",
        "audience": "participant:alice",
        "order": order,
        "kind": CrossingKind.DISCLOSURE,
        "label": Label.DISCLOSURE,
        "source_ref": source_ref,
        "value": value,
        "policy_revision": "rev1",
        "policy_decision_ref": "policy-decisions.participant-egress.cut-1",
        "decision_cut_ref": "state-cuts.1",
        "authorized": True,
        "admitted": True,
        "visible": True,
        "marking_authorized": True,
        "declassification_authorized": False,
        "backend_supported": True,
        "transformation_valid": True,
    }
    fields.update(overrides)
    return Crossing(**fields)


def _enumerate_bounded_runs(high_value: str) -> list[tuple[Crossing, ...]]:
    """Enumerate every run in the declared finite domain for one high value."""

    alphabet = (
        (_LOW_REF, "l0"),
        (_LOW_REF, "l1"),
        (_HIGH_REF, high_value),
    )
    runs: list[tuple[Crossing, ...]] = []
    for length in range(1, _BOUND_RUN_LENGTH + 1):
        for combination in product(alphabet, repeat=length):
            runs.append(
                tuple(
                    _crossing(order, source_ref, value)
                    for order, (source_ref, value) in enumerate(combination, start=1)
                )
            )
    return runs


def test_unauthorized_high_variation_is_purged_across_the_whole_declared_bound() -> None:
    """Exhaust the finite domain rather than sampling it.

    This is finite falsification evidence over the declared bound. It does not
    establish the universal policy-noninterference obligation, which stays
    deliberately unproved and is owned downstream by issue #811.
    """

    policy = _bounded_policy()
    left_runs = _enumerate_bounded_runs(_HIGH_VALUES[0])
    right_runs = _enumerate_bounded_runs(_HIGH_VALUES[1])
    assert len(left_runs) == len(right_runs) == 3 + 9 + 27

    assert policy_noninterference_holds(
        left_runs=tuple(left_runs),
        right_runs=tuple(right_runs),
        policy_decisions=(policy,),
        participant="alice",
        audience="participant:alice",
    )


def test_the_bounded_enumeration_can_actually_refute_a_leak() -> None:
    """Evidence with no refutation power is not evidence.

    If the high reference is made visible, the exhaustive comparison must fail;
    otherwise the passing case above would prove nothing.
    """

    leaking_policy = replace(_bounded_policy(), visible_low_refs=frozenset({_LOW_REF, _HIGH_REF}))

    assert not policy_noninterference_holds(
        left_runs=tuple(_enumerate_bounded_runs(_HIGH_VALUES[0])),
        right_runs=tuple(_enumerate_bounded_runs(_HIGH_VALUES[1])),
        policy_decisions=(leaking_policy,),
        participant="alice",
        audience="participant:alice",
    )


@given(
    high_left=st.text(min_size=1, max_size=8),
    high_right=st.text(min_size=1, max_size=8),
    low=st.text(min_size=1, max_size=8),
)
@settings(max_examples=100, deadline=None)
def test_no_generated_unauthorized_high_value_reaches_the_projection(
    high_left: str,
    high_right: str,
    low: str,
) -> None:
    policy = _bounded_policy()
    left = (_crossing(1, _LOW_REF, low), _crossing(2, _HIGH_REF, high_left))
    right = (_crossing(1, _LOW_REF, low), _crossing(2, _HIGH_REF, high_right))

    assert project_history(left, (policy,), participant="alice", audience="participant:alice") == project_history(
        right, (policy,), participant="alice", audience="participant:alice"
    )


def test_declassification_releases_only_at_its_exact_governed_state_cut() -> None:
    """Authority at another cut is not authority here."""

    policy = replace(_bounded_policy(), permitted_declassifications=frozenset({_HIGH_REF}))
    at_cut = (_crossing(1, _HIGH_REF, "h0", declassification_authorized=True),)
    other_cut = (
        _crossing(
            1,
            _HIGH_REF,
            "h0",
            declassification_authorized=True,
            decision_cut_ref="state-cuts.2",
        ),
    )

    released = project_history(at_cut, (policy,), participant="alice", audience="participant:alice")
    withheld = project_history(other_cut, (policy,), participant="alice", audience="participant:alice")

    assert released == ((1, _HIGH_REF, "h0"),)
    assert withheld == ()


def test_declassification_authority_alone_does_not_release_an_unpermitted_reference() -> None:
    policy = _bounded_policy()
    authorized_but_unpermitted = (_crossing(1, _HIGH_REF, "h0", declassification_authorized=True),)

    assert (
        project_history(
            authorized_but_unpermitted,
            (policy,),
            participant="alice",
            audience="participant:alice",
        )
        == ()
    )


def test_a_secret_used_as_a_rejected_field_name_never_reaches_a_diagnostic() -> None:
    """Pydantic puts an unknown extra key in ``loc``; the key itself is caller-chosen.

    Character shape cannot distinguish a legitimate field name from a credential
    that looks like one, so an ``extra_forbidden`` location is redacted rather
    than quoted into a durable report.
    """

    diagnostics = validate_contract_payload(
        "participant-crossing-occurrence-v1",
        {"occurrence": {_SECRET_MARKER: "value"}, _SECRET_MARKER: "value"},
    )

    assert diagnostics
    for diagnostic in diagnostics:
        assert _SECRET_MARKER not in diagnostic.message


def test_refusal_only_coverage_never_establishes_a_declared_capability() -> None:
    """Failing closed is what an absent implementation does too.

    A target that only ever refuses satisfies every refusal obligation while
    realizing none of its declared capabilities, so its declarations must come
    back unsupported rather than conformant.
    """

    target = policy_capable_target(*PROBED_POLICY_FEATURES)

    report = run_target_conformance(target, participant_policy_harness=RefusalOnlyPolicyProbeHarness())

    denial_case = next(
        case for case in report.cases if case.policy_binding and case.policy_binding.obligation == "denial"
    )
    assert denial_case.passed, "the refusal itself is correct behavior"
    unprobed = [case for case in report.cases if case.outcome == "unsupported" and case.capability_feature is not None]
    assert {case.capability_feature for case in unprobed} == set(PROBED_POLICY_FEATURES)
    assert not report.passed


def test_every_case_binding_is_validated_against_the_relation_catalog() -> None:
    """A case binding cannot publish a relation the taxonomy does not define."""

    report = run_target_conformance(
        policy_capable_target(*PROBED_POLICY_FEATURES),
        participant_policy_harness=ParticipantPolicyConformanceHarness(),
    )
    bound = next(case for case in report.cases if case.policy_binding is not None)
    forged = replace(
        bound,
        policy_binding=replace(
            bound.policy_binding,
            claim=bound.policy_binding.claim.model_copy(update={"relation_id": "invented-relation"}),
        ),
    )

    forged_report = replace(report, cases=(forged,))
    with pytest.raises(ValueError):
        validate_backend_conformance_report(forged_report)


def test_the_probe_ledger_is_derived_by_the_runner_not_self_reported() -> None:
    """Backend invocation and audit facts come from runner-owned state."""

    report = run_target_conformance(
        policy_capable_target(*PROBED_POLICY_FEATURES),
        participant_policy_harness=ParticipantPolicyConformanceHarness(),
    )

    denial = next(case for case in report.cases if case.policy_binding and case.policy_binding.obligation == "denial")
    # The denial obligation refuses before the backend runs, so the runner's own
    # before/after ledger must show evidence refs from the committed decision
    # and an effective strength resolved from the recorded crossing.
    assert denial.passed
    assert denial.evidence_refs
    assert denial.effective_support_level == "exact"
    assert denial.policy_binding.counterexample_ref == "crossing-disposition:deny"


def test_a_case_for_an_undeclared_feature_is_a_refused_probe_without_a_record(caplog) -> None:
    class UndeclaredFeatureHarness(ParticipantPolicyConformanceHarness):
        def cases(self, target):
            return (replace(super().cases(target)[0], feature="participant_undeclared_feature"),)

    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        report = run_target_conformance(
            policy_capable_target(*PROBED_POLICY_FEATURES),
            participant_policy_harness=UndeclaredFeatureHarness(),
        )

    case = next(case for case in report.cases if case.capability_feature == "participant_undeclared_feature")
    assert case.outcome == "failed"
    assert [diag.code for diag in case.diagnostics] == ["conformance.participant-policy-probe-failed"]
    assert "InvalidInputError" in case.diagnostics[0].message
    assert not [record for record in caplog.records if record.name.endswith("participant_policy_probes")]


def test_a_failing_probe_is_reported_and_logged_without_its_values(monkeypatch, caplog) -> None:
    from raes_conformance.conformance import participant_policy_probes

    def _fail(case, target):
        raise RuntimeError(f"backend detail {_SECRET_MARKER}")

    monkeypatch.setattr(participant_policy_probes, "_run_case", _fail)
    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        report = run_target_conformance(
            policy_capable_target(*PROBED_POLICY_FEATURES),
            participant_policy_harness=ParticipantPolicyConformanceHarness(),
        )

    failed = [case for case in report.cases if case.policy_binding is not None and case.outcome == "failed"]
    assert failed
    assert {diag.code for case in failed for diag in case.diagnostics} == {
        "conformance.participant-policy-probe-failed"
    }
    assert _SECRET_MARKER not in repr(report)
    records = [record for record in caplog.records if record.name.endswith("participant_policy_probes")]
    assert len(records) == len(failed)
    for record in records:
        assert _SECRET_MARKER not in record.getMessage()
        assert _SECRET_MARKER not in (record.exc_text or "")
        assert "ForeignCodeFailure" in (record.exc_text or "")


def test_a_record_validation_defect_is_not_reported_as_an_invalid_record(monkeypatch, caplog) -> None:
    from raes_conformance.conformance import participant_policy_execution

    class _DefectiveRecordModel:
        @staticmethod
        def model_validate(_entry):
            raise TypeError("record validation defect")

    monkeypatch.setattr(participant_policy_execution, "ParticipantCrossingOccurrenceModel", _DefectiveRecordModel)
    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        report = run_target_conformance(
            policy_capable_target(*PROBED_POLICY_FEATURES),
            participant_policy_harness=ParticipantPolicyConformanceHarness(),
        )

    denial = next(case for case in report.cases if case.policy_binding and case.policy_binding.obligation == "denial")
    assert [diag.code for diag in denial.diagnostics] == ["conformance.participant-policy-probe-failed"]
    assert any(record.name.endswith("participant_policy_probes") for record in caplog.records)


def test_a_validator_defect_is_not_reported_as_an_invalid_payload(monkeypatch) -> None:
    from raes_conformance.conformance import validators

    def _defect(_payload):
        raise TypeError("validator defect")

    monkeypatch.setitem(validators._MODEL_VALIDATORS, "operation-status-v1", _defect)
    with pytest.raises(TypeError, match="validator defect"):
        validate_contract_payload("operation-status-v1", {})
