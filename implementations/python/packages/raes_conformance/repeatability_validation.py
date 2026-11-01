"""Bounded repeatability-consistency comparison (ASR-514).

Decides one finite determinism / replay-consistency claim as a single binary
baseline-to-repetition comparison of the same held-fixed subject. The claim
binds the existing ``canonical-artifact-identity`` relation, and its two
carriers name the two compared projected artifacts (baseline and repetition).
A larger set of repeated runs composes as several such pairwise cases; this
module never reinterprets the binary relation as an n-ary one.

It performs no execution, scheduling, replay, canonicalization of runs, I/O, or
persistence: every fact comes from the trusted assembler in
``repeatability_evidence``. Identity digests use the repository JCS canonical
digest, not a local serializer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

from raes_contracts.behavioral_claims import BehavioralClaimBindingModel
from raes_contracts.behavioral_relations import validate_behavioral_claim_binding
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.diagnostics import Diagnostic, Severity

from .repeatability_types import (
    ProjectionOutcome,
    RepeatabilityConsistencyEvidence,
)
from .verification_authority import (
    VerificationBinding,
    VerificationDisposition,
    VerificationRecordIdentity,
)

CANONICAL_ARTIFACT_IDENTITY_RELATION_ID = "canonical-artifact-identity"
SUPPORTED_REPEATABILITY_RELATION_IDS = frozenset({CANONICAL_ARTIFACT_IDENTITY_RELATION_ID})
_CRITERION_ID = "canonical-projection-equality"
_CRITERION_VERSION = "1.0.0"
_DIAGNOSTIC_ADDRESS = "/conformance/repeatability-comparison"
RepeatabilityVerificationAuthority = VerificationBinding


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_digest(value: str, field_name: str) -> None:
    prefix, _, hexpart = value.partition(":") if isinstance(value, str) else ("", "", "")
    if prefix != "sha256" or len(hexpart) != 64 or any(character not in "0123456789abcdef" for character in hexpart):
        raise ValueError(f"{field_name} must be a sha256 digest")


def _require_unique_text(values: tuple[str, ...], field_name: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{field_name} entries must be non-empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} entries must be unique")


@dataclass(frozen=True)
class RepetitionRef:
    """Immutable identity of one already-admitted run and its projected artifact."""

    repetition_id: str
    run_ref: str
    run_digest: str
    subject_ref: str
    subject_digest: str
    projected_artifact_ref: str

    def __post_init__(self) -> None:
        for field_name in ("repetition_id", "run_ref", "subject_ref", "projected_artifact_ref"):
            _require_text(getattr(self, field_name), field_name)
        _require_digest(self.run_digest, "run_digest")
        _require_digest(self.subject_digest, "subject_digest")


@dataclass(frozen=True)
class VariationPolicy:
    """Named policy for the held-fixed and deliberately-varied dimensions."""

    policy_id: str
    policy_version: str
    held_fixed_dimensions: tuple[str, ...]
    permitted_variation_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.policy_id, "policy_id")
        _require_text(self.policy_version, "policy_version")
        _require_unique_text(self.held_fixed_dimensions, "held_fixed_dimensions")
        _require_unique_text(self.permitted_variation_refs, "permitted_variation_refs")
        if not self.held_fixed_dimensions:
            raise ValueError("held_fixed_dimensions must not be empty")


@dataclass(frozen=True)
class RepeatabilityConsistencyCase:
    """Trusted, subject-bound input to one binary repeatability comparison."""

    case_id: str
    claim: BehavioralClaimBindingModel
    subject_ref: str
    baseline: RepetitionRef
    repetition: RepetitionRef
    observation_projection_ref: str
    observation_projection_revision: str
    criterion_id: str
    criterion_version: str
    variation_policy: VariationPolicy
    required_capability_refs: tuple[str, ...]
    verification_authority: RepeatabilityVerificationAuthority

    def __post_init__(self) -> None:
        for field_name in (
            "case_id",
            "subject_ref",
            "observation_projection_ref",
            "observation_projection_revision",
            "criterion_id",
            "criterion_version",
        ):
            _require_text(getattr(self, field_name), field_name)
        if not isinstance(self.claim, BehavioralClaimBindingModel):
            raise ValueError("claim must be a BehavioralClaimBindingModel")
        if not isinstance(self.baseline, RepetitionRef) or not isinstance(self.repetition, RepetitionRef):
            raise ValueError("baseline and repetition must be RepetitionRef values")
        if not isinstance(self.variation_policy, VariationPolicy):
            raise ValueError("variation_policy must be a VariationPolicy")
        if not isinstance(self.verification_authority, VerificationBinding):
            raise ValueError("verification_authority must be a RepeatabilityVerificationAuthority")
        _require_unique_text(self.required_capability_refs, "required_capability_refs")
        if not self.required_capability_refs:
            raise ValueError("required_capability_refs must not be empty")
        self._validate_pair()

    def _validate_pair(self) -> None:
        if self.baseline.run_ref == self.repetition.run_ref:
            raise ValueError("baseline and repetition must use distinct run_ref values")
        if self.baseline.projected_artifact_ref == self.repetition.projected_artifact_ref:
            raise ValueError("baseline and repetition must name distinct projected_artifact_ref values")
        for side in (self.baseline, self.repetition):
            if side.subject_ref != self.subject_ref:
                raise ValueError("baseline and repetition must repeat the case subject_ref")
        if self.baseline.subject_digest != self.repetition.subject_digest:
            raise ValueError("baseline and repetition must hold the subject fixed by digest")

    @property
    def digest(self) -> str:
        """Return the JCS canonical identity of every comparison join input."""

        payload = {
            "case_id": self.case_id,
            "claim": self.claim.model_dump(mode="json"),
            "subject_ref": self.subject_ref,
            "baseline": asdict(self.baseline),
            "repetition": asdict(self.repetition),
            "observation_projection_ref": self.observation_projection_ref,
            "observation_projection_revision": self.observation_projection_revision,
            "criterion_id": self.criterion_id,
            "criterion_version": self.criterion_version,
            "variation_policy": {
                "policy_id": self.variation_policy.policy_id,
                "policy_version": self.variation_policy.policy_version,
                "held_fixed_dimensions": list(self.variation_policy.held_fixed_dimensions),
                "permitted_variation_refs": list(self.variation_policy.permitted_variation_refs),
            },
            "required_capability_refs": list(self.required_capability_refs),
            "verification_authority": asdict(self.verification_authority),
        }
        return canonical_json_digest(payload)


class RepeatabilityConsistencyOutcome(str, Enum):
    """Finite decision for one admitted repeatability comparison."""

    CONSISTENT = "consistent"
    DIVERGENT = "divergent"
    INCONCLUSIVE = "inconclusive"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class RepeatabilityConsistencyResult:
    """Finite comparison result whose identities come only from the case."""

    case_id: str
    case_digest: str
    claim: BehavioralClaimBindingModel
    subject_ref: str
    baseline_artifact_ref: str
    repetition_artifact_ref: str
    baseline_run_ref: str
    repetition_run_ref: str
    outcome: RepeatabilityConsistencyOutcome
    evidence_refs: tuple[str, ...]
    verification_identities: tuple[VerificationRecordIdentity, ...]
    diagnostics: tuple[Diagnostic, ...]

    @property
    def consistent(self) -> bool:
        return self.outcome is RepeatabilityConsistencyOutcome.CONSISTENT


def _diagnostic(code: str, message: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        domain="conformance",
        address=_DIAGNOSTIC_ADDRESS,
        message=message,
        severity=Severity.ERROR,
    )


def _result(
    case: RepeatabilityConsistencyCase,
    evidence: RepeatabilityConsistencyEvidence,
    outcome: RepeatabilityConsistencyOutcome,
    diagnostics: tuple[Diagnostic, ...] = (),
) -> RepeatabilityConsistencyResult:
    evidence_refs = tuple(
        dict.fromkeys(
            ref
            for source in (
                evidence.baseline_projection.evidence_refs,
                evidence.repetition_projection.evidence_refs,
                evidence.reset_evidence_refs,
                evidence.cleanup_evidence_refs,
            )
            for ref in source
        )
    )
    return RepeatabilityConsistencyResult(
        case_id=case.case_id,
        case_digest=case.digest,
        claim=case.claim,
        subject_ref=case.subject_ref,
        baseline_artifact_ref=case.baseline.projected_artifact_ref,
        repetition_artifact_ref=case.repetition.projected_artifact_ref,
        baseline_run_ref=case.baseline.run_ref,
        repetition_run_ref=case.repetition.run_ref,
        outcome=outcome,
        evidence_refs=evidence_refs,
        verification_identities=evidence.verification_identities,
        diagnostics=diagnostics,
    )


def _claim_catalog_diagnostic(case: RepeatabilityConsistencyCase) -> Diagnostic | None:
    diagnostic = None
    try:
        validate_behavioral_claim_binding(case.claim)
    except ValueError:
        diagnostic = _diagnostic(
            "conformance.repeatability-claim-invalid",
            "The claim does not resolve against the canonical behavioral-relation catalog.",
        )
    return diagnostic


def _claim_admission_diagnostic(case: RepeatabilityConsistencyCase) -> Diagnostic | None:
    diagnostic = None
    if case.claim.relation_id not in SUPPORTED_REPEATABILITY_RELATION_IDS:
        diagnostic = _diagnostic(
            "conformance.repeatability-claim-relation-invalid",
            "The claim does not use a supported repeatability relation.",
        )
    elif (catalog_diagnostic := _claim_catalog_diagnostic(case)) is not None:
        diagnostic = catalog_diagnostic
    elif case.claim.quantifier_scope != "finite-cases" or case.claim.evidence_scope != "finite":
        diagnostic = _diagnostic(
            "conformance.repeatability-claim-boundary-invalid",
            "The bounded comparator accepts only finite-case claims with finite evidence.",
        )
    elif (
        case.claim.left_carrier_ref != case.baseline.projected_artifact_ref
        or case.claim.right_carrier_ref != case.repetition.projected_artifact_ref
        or case.claim.observation_projection_ref != case.observation_projection_ref
        or case.claim.observation_projection_revision != case.observation_projection_revision
    ):
        diagnostic = _diagnostic(
            "conformance.repeatability-claim-case-mismatch",
            "The claim carriers and projection do not identify the baseline and repetition artifacts.",
        )
    elif (case.criterion_id, case.criterion_version) != (_CRITERION_ID, _CRITERION_VERSION):
        diagnostic = _diagnostic(
            "conformance.repeatability-criterion-unsupported",
            "The requested repeatability criterion is not supported by this comparator.",
        )
    return diagnostic


def _evidence_admission_diagnostic(
    case: RepeatabilityConsistencyCase,
    evidence: RepeatabilityConsistencyEvidence,
) -> Diagnostic | None:
    diagnostic = None
    pair_mismatch = (
        evidence.baseline_artifact_ref != case.baseline.projected_artifact_ref
        or evidence.repetition_artifact_ref != case.repetition.projected_artifact_ref
        or evidence.baseline_projection.run_ref != case.baseline.run_ref
        or evidence.repetition_projection.run_ref != case.repetition.run_ref
    )
    authority_mismatch = evidence.verification_binding != case.verification_authority or any(
        identity.binding != case.verification_authority for identity in evidence.verification_identities
    )
    if pair_mismatch:
        diagnostic = _diagnostic(
            "conformance.repeatability-pair-evidence-mismatch",
            "The evidence does not project exactly the admitted baseline and repetition.",
        )
    elif authority_mismatch:
        diagnostic = _diagnostic(
            "conformance.repeatability-verification-authority-mismatch",
            "The verification identities do not match the authority admitted by the case.",
        )
    return diagnostic


def _admission_diagnostic(
    case: RepeatabilityConsistencyCase,
    evidence: RepeatabilityConsistencyEvidence,
    available_capability_refs: frozenset[str],
) -> Diagnostic | None:
    diagnostic = None
    if not evidence._has_authentic_assembly():
        diagnostic = _diagnostic(
            "conformance.repeatability-evidence-unauthenticated",
            "The comparison evidence was not produced by the trusted repeatability assembler.",
        )
    elif evidence.case_digest != case.digest:
        diagnostic = _diagnostic(
            "conformance.repeatability-case-evidence-mismatch",
            "The assembled evidence does not belong to the admitted comparison case.",
        )
    elif (claim_diagnostic := _claim_admission_diagnostic(case)) is not None:
        diagnostic = claim_diagnostic
    elif set(case.required_capability_refs) - set(available_capability_refs):
        diagnostic = _diagnostic(
            "conformance.repeatability-capability-unsupported",
            "The comparator does not have every capability required by the admitted case.",
        )
    else:
        diagnostic = _evidence_admission_diagnostic(case, evidence)
    return diagnostic


def _gate_diagnostics(evidence: RepeatabilityConsistencyEvidence) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    if evidence.variation_disposition is not VerificationDisposition.VERIFIED or evidence.unmatched_dimension_refs:
        diagnostics.append(
            _diagnostic(
                "conformance.repeatability-variation-unverified",
                "The pair does not satisfy the declared variation policy.",
            )
        )
    if evidence.reset_disposition is not VerificationDisposition.VERIFIED or not evidence.reset_evidence_refs:
        diagnostics.append(
            _diagnostic(
                "conformance.repeatability-reset-unverified",
                "Reset and isolation between runs were not independently verified.",
            )
        )
    if evidence.cleanup_disposition is not VerificationDisposition.VERIFIED or not evidence.cleanup_evidence_refs:
        diagnostics.append(
            _diagnostic(
                "conformance.repeatability-cleanup-unverified",
                "Reset and cleanup were not independently verified.",
            )
        )
    if evidence.residual_state:
        diagnostics.append(
            _diagnostic(
                "conformance.repeatability-residual-state",
                "The comparison left residual owned state.",
            )
        )
    return tuple(diagnostics)


def _comparison_disposition(
    evidence: RepeatabilityConsistencyEvidence,
) -> tuple[RepeatabilityConsistencyOutcome, tuple[Diagnostic, ...]]:
    outcome = RepeatabilityConsistencyOutcome.CONSISTENT
    diagnostics: tuple[Diagnostic, ...] = ()
    projection_outcomes = (evidence.baseline_projection.outcome, evidence.repetition_projection.outcome)
    gate_dispositions = (
        evidence.variation_disposition,
        evidence.reset_disposition,
        evidence.cleanup_disposition,
    )
    if ProjectionOutcome.UNSUPPORTED in projection_outcomes:
        outcome = RepeatabilityConsistencyOutcome.UNSUPPORTED
        diagnostics = (
            _diagnostic(
                "conformance.repeatability-outcome-unsupported",
                "At least one projected outcome is unsupported by the admitted apparatus.",
            ),
        )
    elif ProjectionOutcome.INDETERMINATE in projection_outcomes:
        outcome = RepeatabilityConsistencyOutcome.INCONCLUSIVE
        diagnostics = (
            _diagnostic(
                "conformance.repeatability-outcome-inconclusive",
                "At least one projected outcome is indeterminate.",
            ),
        )
    elif VerificationDisposition.UNSUPPORTED in gate_dispositions:
        outcome = RepeatabilityConsistencyOutcome.UNSUPPORTED
        diagnostics = (
            _diagnostic(
                "conformance.repeatability-verification-unsupported",
                "At least one required verification fact is unsupported by the admitted validator.",
            ),
        )
    elif gate_diagnostics := _gate_diagnostics(evidence):
        outcome = RepeatabilityConsistencyOutcome.INCONCLUSIVE
        diagnostics = gate_diagnostics
    elif evidence.baseline_projection.projected_digest != evidence.repetition_projection.projected_digest:
        outcome = RepeatabilityConsistencyOutcome.DIVERGENT
    return outcome, diagnostics


def compare_repeatability_consistency(
    case: RepeatabilityConsistencyCase,
    evidence: RepeatabilityConsistencyEvidence,
    *,
    available_capability_refs: frozenset[str],
) -> RepeatabilityConsistencyResult:
    """Evaluate one admitted finite baseline-to-repetition consistency comparison."""
    admission_diagnostic = _admission_diagnostic(case, evidence, available_capability_refs)
    if admission_diagnostic is not None:
        outcome = RepeatabilityConsistencyOutcome.UNSUPPORTED
        diagnostics = (admission_diagnostic,)
    else:
        outcome, diagnostics = _comparison_disposition(evidence)
    return _result(case, evidence, outcome, diagnostics)
