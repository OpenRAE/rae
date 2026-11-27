"""Subject-bound executable behavioral validation probes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from raes_contracts.behavioral_claims import BehavioralClaimBindingModel
from raes_contracts.behavioral_relations import validate_behavioral_claim_binding
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.errors import RaesError
from raes_contracts.json_serialization import sorted_json_digest
from raes_contracts.operational_logging import foreign_failure_record, get_logger

from ._realization_models import ExecutionBasis

_LOGGER = get_logger(__name__)
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class BehavioralSubjectKind(str, Enum):
    """Claim-bearing subject families admitted by ASR-512."""

    SCENARIO = "scenario"
    PARTICIPANT = "participant"
    WORKFLOW = "workflow"
    EXPERIMENT = "experiment"


class BehavioralProbeOutcome(str, Enum):
    """Closed outcome vocabulary for one bounded behavioral probe."""

    PASSED = "passed"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_digest(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a sha256 digest")


def _require_unique_text(values: tuple[str, ...], field_name: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{field_name} entries must be non-empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} entries must be unique")


@dataclass(frozen=True)
class BehavioralProbeBinding:
    """Digest-pinned identity of trusted code that implements one probe."""

    implementation_id: str
    implementation_version: str
    artifact_digest: str
    capability_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.implementation_id, "implementation_id")
        _require_text(self.implementation_version, "implementation_version")
        _require_digest(self.artifact_digest, "artifact_digest")
        _require_unique_text(self.capability_refs, "capability_refs")
        if not self.capability_refs:
            raise ValueError("capability_refs must not be empty")


@dataclass(frozen=True)
class BehavioralProbeCase:
    """One admitted subject, property claim, implementation, and finite input."""

    case_id: str
    subject_kind: BehavioralSubjectKind
    subject_ref: str
    claim: BehavioralClaimBindingModel
    probe_binding: BehavioralProbeBinding
    input_digest: str
    execution_basis: ExecutionBasis | str
    mutates_state: bool = False

    def __post_init__(self) -> None:
        _require_text(self.case_id, "case_id")
        if not isinstance(self.subject_kind, BehavioralSubjectKind):
            raise ValueError("subject_kind must be a BehavioralSubjectKind")
        _require_text(self.subject_ref, "subject_ref")
        if not isinstance(self.claim, BehavioralClaimBindingModel):
            raise ValueError("claim must be a BehavioralClaimBindingModel")
        if not isinstance(self.probe_binding, BehavioralProbeBinding):
            raise ValueError("probe_binding must be a BehavioralProbeBinding")
        _require_digest(self.input_digest, "input_digest")
        try:
            basis = ExecutionBasis(self.execution_basis)
        except ValueError as exc:
            raise ValueError("execution_basis must be a supported ExecutionBasis") from exc
        object.__setattr__(self, "execution_basis", basis)

    @property
    def digest(self) -> str:
        """Return the canonical identity of every property-to-result join input."""

        payload = {
            "case_id": self.case_id,
            "subject_kind": self.subject_kind.value,
            "subject_ref": self.subject_ref,
            "claim": self.claim.model_dump(mode="json"),
            "probe_binding": {
                "implementation_id": self.probe_binding.implementation_id,
                "implementation_version": self.probe_binding.implementation_version,
                "artifact_digest": self.probe_binding.artifact_digest,
                "capability_refs": list(self.probe_binding.capability_refs),
            },
            "input_digest": self.input_digest,
            "execution_basis": self.execution_basis.value,
            "mutates_state": self.mutates_state,
        }
        return sorted_json_digest(payload)


@dataclass(frozen=True)
class BehavioralProbeEvidence:
    """Evidence returned by a subject-specific injected executor."""

    outcome: BehavioralProbeOutcome
    evidence_refs: tuple[str, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    cleanup_verified: bool = False
    residual_state: tuple[str, ...] = ()


class BehavioralProbeExecutor(Protocol):
    """Trusted, capability-advertising execution adapter."""

    capability_refs: frozenset[str]

    def execute(self, case: BehavioralProbeCase) -> BehavioralProbeEvidence:
        """Execute one already-admitted case."""
        ...


@dataclass(frozen=True)
class BehavioralProbeResult:
    """Bounded result whose identities come only from the admitted case."""

    case_id: str
    case_digest: str
    subject_kind: BehavioralSubjectKind
    subject_ref: str
    claim: BehavioralClaimBindingModel
    probe_binding: BehavioralProbeBinding
    input_digest: str
    execution_basis: ExecutionBasis
    outcome: BehavioralProbeOutcome
    evidence_refs: tuple[str, ...]
    diagnostics: tuple[Diagnostic, ...]
    cleanup_verified: bool
    residual_state: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """Return whether this exact bounded case passed."""

        return self.outcome is BehavioralProbeOutcome.PASSED


def _diagnostic(case: BehavioralProbeCase, code: str, message: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        domain="conformance",
        address=f"behavioral-probe.{case.case_id}",
        message=message,
        severity=Severity.ERROR,
    )


def _result(
    case: BehavioralProbeCase,
    *,
    outcome: BehavioralProbeOutcome,
    evidence_refs: tuple[str, ...] = (),
    diagnostics: tuple[Diagnostic, ...] = (),
    cleanup_verified: bool = False,
    residual_state: tuple[str, ...] = (),
) -> BehavioralProbeResult:
    return BehavioralProbeResult(
        case_id=case.case_id,
        case_digest=case.digest,
        subject_kind=case.subject_kind,
        subject_ref=case.subject_ref,
        claim=case.claim,
        probe_binding=case.probe_binding,
        input_digest=case.input_digest,
        execution_basis=case.execution_basis,
        outcome=outcome,
        evidence_refs=evidence_refs,
        diagnostics=diagnostics,
        cleanup_verified=cleanup_verified,
        residual_state=residual_state,
    )


def _admission_diagnostic(
    case: BehavioralProbeCase,
    executor: BehavioralProbeExecutor,
) -> Diagnostic | None:
    diagnostic = None
    try:
        validate_behavioral_claim_binding(case.claim)
    except ValueError:
        diagnostic = _diagnostic(
            case,
            "conformance.behavioral-probe-claim-invalid",
            "The behavioral probe claim does not resolve against the canonical relation catalog.",
        )
    if diagnostic is None and case.claim.left_carrier_ref != case.subject_ref:
        diagnostic = _diagnostic(
            case,
            "conformance.behavioral-probe-subject-claim-mismatch",
            "The behavioral claim left carrier does not identify the admitted probe subject.",
        )
    if diagnostic is None:
        missing_capabilities = set(case.probe_binding.capability_refs) - set(executor.capability_refs)
        if missing_capabilities:
            diagnostic = _diagnostic(
                case,
                "conformance.behavioral-probe-capability-unsupported",
                "The injected executor does not support every capability required by the probe binding.",
            )
    return diagnostic


def _evidence_diagnostics(
    case: BehavioralProbeCase,
    evidence: BehavioralProbeEvidence,
) -> tuple[Diagnostic, ...]:
    diagnostics = list(evidence.diagnostics)
    if evidence.outcome is BehavioralProbeOutcome.PASSED:
        if not evidence.evidence_refs:
            diagnostics.append(
                _diagnostic(
                    case,
                    "conformance.behavioral-probe-evidence-missing",
                    "A passed behavioral probe requires at least one evidence reference.",
                )
            )
        elif any(not isinstance(reference, str) or not reference.strip() for reference in evidence.evidence_refs):
            diagnostics.append(
                _diagnostic(
                    case,
                    "conformance.behavioral-probe-evidence-invalid",
                    "A passed behavioral probe requires non-empty evidence reference identifiers.",
                )
            )
    if case.mutates_state and not evidence.cleanup_verified:
        diagnostics.append(
            _diagnostic(
                case,
                "conformance.behavioral-probe-cleanup-unverified",
                "A mutating behavioral probe requires independently verified cleanup.",
            )
        )
    if case.mutates_state and evidence.residual_state:
        diagnostics.append(
            _diagnostic(
                case,
                "conformance.behavioral-probe-residual-state",
                "A mutating behavioral probe left residual owned state.",
            )
        )
    return tuple(diagnostics)


def _result_from_evidence(
    case: BehavioralProbeCase,
    evidence: BehavioralProbeEvidence,
) -> BehavioralProbeResult:
    diagnostics = _evidence_diagnostics(case, evidence)
    outcome = evidence.outcome
    if diagnostics and outcome is BehavioralProbeOutcome.PASSED:
        outcome = BehavioralProbeOutcome.FAILED
    return _result(
        case,
        outcome=outcome,
        evidence_refs=evidence.evidence_refs,
        diagnostics=diagnostics,
        cleanup_verified=evidence.cleanup_verified,
        residual_state=evidence.residual_state,
    )


def run_behavioral_validation_probe(
    case: BehavioralProbeCase,
    executor: BehavioralProbeExecutor,
) -> BehavioralProbeResult:
    """Validate and execute one exact subject/property/probe join."""

    admission_diagnostic = _admission_diagnostic(case, executor)
    if admission_diagnostic is not None:
        return _result(
            case,
            outcome=BehavioralProbeOutcome.UNSUPPORTED,
            diagnostics=(admission_diagnostic,),
        )

    try:
        evidence = executor.execute(case)
    except Exception as exc:
        if not isinstance(exc, RaesError):
            # Isolation of the injected executor and the subject it drives: a refusal category needs no record.
            _LOGGER.exception("behavioral probe executor failed", exc_info=foreign_failure_record(exc))
        return _result(
            case,
            outcome=BehavioralProbeOutcome.FAILED,
            diagnostics=(
                _diagnostic(
                    case,
                    "conformance.behavioral-probe-execution-failed",
                    f"Behavioral probe executor raised {type(exc).__name__}.",
                ),
            ),
        )
    return _result_from_evidence(case, evidence)


__all__ = (
    "BehavioralProbeBinding",
    "BehavioralProbeCase",
    "BehavioralProbeEvidence",
    "BehavioralProbeExecutor",
    "BehavioralProbeOutcome",
    "BehavioralProbeResult",
    "BehavioralSubjectKind",
    "run_behavioral_validation_probe",
)
