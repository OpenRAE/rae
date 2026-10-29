"""ASR-512 subject-bound executable behavioral validation probes."""

from __future__ import annotations

import logging
from dataclasses import replace

import pytest
from raes_conformance.behavioral_validation import (
    BehavioralProbeBinding,
    BehavioralProbeCase,
    BehavioralProbeEvidence,
    BehavioralProbeOutcome,
    BehavioralSubjectKind,
    run_behavioral_validation_probe,
)
from raes_contracts.contracts import BehavioralClaimBindingModel
from raes_contracts.diagnostics import Diagnostic

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64


def _claim(
    relation_id: str = "bounded-probe-success",
    *,
    left_carrier_ref: str = "scenario:example",
) -> BehavioralClaimBindingModel:
    return BehavioralClaimBindingModel(
        taxonomy_id="raes-behavioral-relations",
        taxonomy_revision="rev8",
        relation_id=relation_id,
        subject="The named subject satisfies its bounded validation property.",
        left_carrier_ref=left_carrier_ref,
        right_carrier_ref="probe-case:health",
        observation_projection_ref="behavioral-probe-result",
        observation_projection_revision="rev1",
        quantifier_scope="finite-cases",
        evidence_scope="finite",
        evidence_boundary="One admitted subject-bound executable probe case.",
        assurance_status="implemented",
        evidence_refs=[],
        limitations=["The result covers only the recorded subject, input, target, and execution basis."],
        explicit_non_claims=["Does not establish coverage of all inputs or traces."],
    )


def _case(
    subject_kind: BehavioralSubjectKind = BehavioralSubjectKind.SCENARIO,
    *,
    claim: BehavioralClaimBindingModel | None = None,
    mutates_state: bool = False,
) -> BehavioralProbeCase:
    subject_ref = f"{subject_kind.value}:example"
    return BehavioralProbeCase(
        case_id="health-check",
        subject_kind=subject_kind,
        subject_ref=subject_ref,
        claim=claim or _claim(left_carrier_ref=subject_ref),
        probe_binding=BehavioralProbeBinding(
            implementation_id="example/health-probe",
            implementation_version="1.0.0",
            artifact_digest=_DIGEST_A,
            capability_refs=("observation.health",),
        ),
        input_digest=_DIGEST_B,
        execution_basis="hermetic-live",
        mutates_state=mutates_state,
    )


class _Executor:
    def __init__(
        self,
        evidence: BehavioralProbeEvidence | None = None,
        *,
        capability_refs: tuple[str, ...] = ("observation.health",),
        error: Exception | None = None,
    ) -> None:
        self.capability_refs = frozenset(capability_refs)
        self.evidence = evidence or BehavioralProbeEvidence(
            outcome=BehavioralProbeOutcome.PASSED,
            evidence_refs=("evidence:probe-run-1",),
            cleanup_verified=True,
        )
        self.error = error
        self.calls: list[BehavioralProbeCase] = []

    def execute(self, case: BehavioralProbeCase) -> BehavioralProbeEvidence:
        self.calls.append(case)
        if self.error is not None:
            raise self.error
        return self.evidence


@pytest.mark.parametrize("subject_kind", list(BehavioralSubjectKind))
def test_probe_result_joins_subject_claim_binding_execution_and_evidence(
    subject_kind: BehavioralSubjectKind,
) -> None:
    case = _case(subject_kind)
    executor = _Executor()

    result = run_behavioral_validation_probe(case, executor)

    assert result.passed
    assert result.outcome is BehavioralProbeOutcome.PASSED
    assert result.case_digest.startswith("sha256:")
    assert result.subject_kind is subject_kind
    assert result.subject_ref == case.subject_ref
    assert result.claim == case.claim
    assert result.probe_binding == case.probe_binding
    assert result.input_digest == case.input_digest
    assert result.execution_basis == case.execution_basis
    assert result.evidence_refs == ("evidence:probe-run-1",)
    assert executor.calls == [case]


def test_case_digest_changes_when_any_joined_identity_changes() -> None:
    case = _case()
    variants = (
        replace(case, case_id="other"),
        replace(case, subject_kind=BehavioralSubjectKind.PARTICIPANT),
        replace(case, subject_ref="scenario:other"),
        replace(
            case,
            claim=case.claim.model_copy(
                update={"subject": "The named subject satisfies a different bounded property."}
            ),
        ),
        replace(
            case,
            probe_binding=replace(case.probe_binding, implementation_id="example/other-probe"),
        ),
        replace(
            case,
            probe_binding=replace(case.probe_binding, implementation_version="1.0.1"),
        ),
        replace(
            case,
            probe_binding=replace(case.probe_binding, artifact_digest="sha256:" + "c" * 64),
        ),
        replace(
            case,
            probe_binding=replace(case.probe_binding, capability_refs=("observation.other",)),
        ),
        replace(case, input_digest="sha256:" + "c" * 64),
        replace(case, execution_basis="native-live"),
        replace(case, mutates_state=True),
    )

    assert all(case.digest != variant.digest for variant in variants)


def test_unknown_claim_relation_fails_closed_before_execution() -> None:
    executor = _Executor()

    result = run_behavioral_validation_probe(
        _case(claim=_claim("unknown-relation", left_carrier_ref="scenario:example")),
        executor,
    )

    assert result.outcome is BehavioralProbeOutcome.UNSUPPORTED
    assert {diagnostic.code for diagnostic in result.diagnostics} == {"conformance.behavioral-probe-claim-invalid"}
    assert not executor.calls


@pytest.mark.parametrize("subject_kind", list(BehavioralSubjectKind))
def test_claim_for_another_subject_fails_closed_before_execution(
    subject_kind: BehavioralSubjectKind,
) -> None:
    executor = _Executor()
    claim = _claim(left_carrier_ref=f"{subject_kind.value}:other")

    result = run_behavioral_validation_probe(_case(subject_kind, claim=claim), executor)

    assert result.outcome is BehavioralProbeOutcome.UNSUPPORTED
    assert {diagnostic.code for diagnostic in result.diagnostics} == {
        "conformance.behavioral-probe-subject-claim-mismatch"
    }
    assert not executor.calls


def test_missing_executor_capability_fails_closed_before_execution() -> None:
    executor = _Executor(capability_refs=())

    result = run_behavioral_validation_probe(_case(), executor)

    assert result.outcome is BehavioralProbeOutcome.UNSUPPORTED
    assert {diagnostic.code for diagnostic in result.diagnostics} == {
        "conformance.behavioral-probe-capability-unsupported"
    }
    assert not executor.calls


def test_passed_probe_requires_evidence() -> None:
    executor = _Executor(
        BehavioralProbeEvidence(
            outcome=BehavioralProbeOutcome.PASSED,
            cleanup_verified=True,
        )
    )

    result = run_behavioral_validation_probe(_case(), executor)

    assert result.outcome is BehavioralProbeOutcome.FAILED
    assert {diagnostic.code for diagnostic in result.diagnostics} == {"conformance.behavioral-probe-evidence-missing"}


@pytest.mark.parametrize("evidence_ref", ["", "   "])
def test_passed_probe_rejects_blank_evidence_reference(evidence_ref: str) -> None:
    executor = _Executor(
        BehavioralProbeEvidence(
            outcome=BehavioralProbeOutcome.PASSED,
            evidence_refs=(evidence_ref,),
            cleanup_verified=True,
        )
    )

    result = run_behavioral_validation_probe(_case(), executor)

    assert result.outcome is BehavioralProbeOutcome.FAILED
    assert {diagnostic.code for diagnostic in result.diagnostics} == {"conformance.behavioral-probe-evidence-invalid"}


def test_executor_reported_failure_is_preserved_without_synthetic_diagnostic() -> None:
    executor = _Executor(
        BehavioralProbeEvidence(
            outcome=BehavioralProbeOutcome.FAILED,
            evidence_refs=("evidence:probe-run-1",),
            cleanup_verified=True,
        )
    )

    result = run_behavioral_validation_probe(_case(), executor)

    assert result.outcome is BehavioralProbeOutcome.FAILED
    assert not result.diagnostics


def test_executor_diagnostic_is_preserved_and_downgrades_passed_outcome() -> None:
    executor_diagnostic = Diagnostic(
        code="conformance.behavioral-probe-property-failed",
        domain="conformance",
        address="behavioral-probe.health-check",
        message="The observed behavior did not satisfy the admitted property.",
    )
    executor = _Executor(
        BehavioralProbeEvidence(
            outcome=BehavioralProbeOutcome.PASSED,
            evidence_refs=("evidence:probe-run-1",),
            diagnostics=(executor_diagnostic,),
            cleanup_verified=True,
        )
    )

    result = run_behavioral_validation_probe(_case(), executor)

    assert result.outcome is BehavioralProbeOutcome.FAILED
    assert result.diagnostics == (executor_diagnostic,)


@pytest.mark.parametrize(
    ("evidence", "expected_code"),
    [
        (
            BehavioralProbeEvidence(
                outcome=BehavioralProbeOutcome.PASSED,
                evidence_refs=("evidence:probe-run-1",),
                cleanup_verified=False,
            ),
            "conformance.behavioral-probe-cleanup-unverified",
        ),
        (
            BehavioralProbeEvidence(
                outcome=BehavioralProbeOutcome.PASSED,
                evidence_refs=("evidence:probe-run-1",),
                cleanup_verified=True,
                residual_state=("owned-resource:residual",),
            ),
            "conformance.behavioral-probe-residual-state",
        ),
    ],
)
def test_mutating_probe_requires_verified_cleanup_without_residual_state(
    evidence: BehavioralProbeEvidence,
    expected_code: str,
) -> None:
    result = run_behavioral_validation_probe(_case(mutates_state=True), _Executor(evidence))

    assert result.outcome is BehavioralProbeOutcome.FAILED
    assert expected_code in {diagnostic.code for diagnostic in result.diagnostics}


def test_executor_failure_is_sanitized_and_fails_closed() -> None:
    executor = _Executor(error=RuntimeError("credential=do-not-leak"))

    result = run_behavioral_validation_probe(_case(), executor)

    assert result.outcome is BehavioralProbeOutcome.FAILED
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.code == "conformance.behavioral-probe-execution-failed"
    assert "RuntimeError" in diagnostic.message
    assert "credential" not in diagnostic.message
    assert "do-not-leak" not in diagnostic.message


def test_executor_failure_is_logged_once_without_values(caplog: pytest.LogCaptureFixture) -> None:
    executor = _Executor(error=RuntimeError("credential=do-not-leak"))

    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        run_behavioral_validation_probe(_case(), executor)

    records = [record for record in caplog.records if record.name == "raes_conformance.behavioral_validation"]
    assert len(records) == 1
    assert "do-not-leak" not in records[0].getMessage()
    assert "do-not-leak" not in (records[0].exc_text or "")
    assert "ForeignCodeFailure" in (records[0].exc_text or "")
