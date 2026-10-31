from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import Enum

from raes_contracts.behavioral_relations import validate_behavioral_claim_binding
from raes_contracts.contracts import (
    BehavioralClaimBindingModel,
    PropositionTruthOutcome,
)
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.json_serialization import sorted_json_digest

from .necessity_types import (
    BoundedButForEvidence,
    VerificationBinding,
    VerificationDisposition,
    VerificationRecordIdentity,
)

BOUNDED_BUT_FOR_RELATION_ID = "bounded-but-for-necessity"
_CRITERION_ID = "binary-but-for"
_CRITERION_VERSION = "1.0.0"
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
NecessityVerificationAuthority = VerificationBinding


class InterventionKind(str, Enum):
    REMOVE = "remove"
    DISABLE = "disable"
    REPLACE = "replace"
    BLOCK = "block"


class NecessityComparisonOutcome(str, Enum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"
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
class NecessityWorldRef:
    """Immutable identity of one already-admitted experiment world and run."""

    world_id: str
    run_ref: str
    run_digest: str
    subject_ref: str
    subject_digest: str
    family_ref: str
    baseline_lineage_ref: str

    def __post_init__(self) -> None:
        for field_name in (
            "world_id",
            "run_ref",
            "subject_ref",
            "family_ref",
            "baseline_lineage_ref",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_digest(self.run_digest, "run_digest")
        _require_digest(self.subject_digest, "subject_digest")


@dataclass(frozen=True)
class NecessityMatchingPolicy:
    """Named policy for held-fixed dimensions and the admitted difference."""

    policy_id: str
    policy_version: str
    held_fixed_dimensions: tuple[str, ...]
    permitted_difference_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.policy_id, "policy_id")
        _require_text(self.policy_version, "policy_version")
        _require_unique_text(self.held_fixed_dimensions, "held_fixed_dimensions")
        _require_unique_text(self.permitted_difference_refs, "permitted_difference_refs")
        if not self.held_fixed_dimensions:
            raise ValueError("held_fixed_dimensions must not be empty")
        if not self.permitted_difference_refs:
            raise ValueError("permitted_difference_refs must not be empty")


@dataclass(frozen=True)
class BoundedButForCase:
    """Trusted, subject-bound input to one binary but-for comparison."""

    case_id: str
    claim: BehavioralClaimBindingModel
    candidate_ref: str
    outcome_proposition_address: str
    outcome_assertion_address: str
    baseline_world: NecessityWorldRef
    counterfactual_world: NecessityWorldRef
    intervention_kind: InterventionKind
    intervention_ref: str
    intervention_version: str
    intervention_digest: str
    criterion_id: str
    criterion_version: str
    matching_policy: NecessityMatchingPolicy
    required_capability_refs: tuple[str, ...]
    verification_authority: NecessityVerificationAuthority
    input_digest: str

    def __post_init__(self) -> None:
        for field_name in (
            "case_id",
            "candidate_ref",
            "outcome_proposition_address",
            "outcome_assertion_address",
            "intervention_ref",
            "intervention_version",
            "criterion_id",
            "criterion_version",
        ):
            _require_text(getattr(self, field_name), field_name)
        if not isinstance(self.claim, BehavioralClaimBindingModel):
            raise ValueError("claim must be a BehavioralClaimBindingModel")
        if not isinstance(self.baseline_world, NecessityWorldRef):
            raise ValueError("baseline_world must be a NecessityWorldRef")
        if not isinstance(self.counterfactual_world, NecessityWorldRef):
            raise ValueError("counterfactual_world must be a NecessityWorldRef")
        if not isinstance(self.intervention_kind, InterventionKind):
            raise ValueError("intervention_kind must be an InterventionKind")
        if not isinstance(self.matching_policy, NecessityMatchingPolicy):
            raise ValueError("matching_policy must be a NecessityMatchingPolicy")
        if not isinstance(self.verification_authority, VerificationBinding):
            raise ValueError("verification_authority must be a NecessityVerificationAuthority")
        _require_digest(self.intervention_digest, "intervention_digest")
        _require_digest(self.input_digest, "input_digest")
        _require_unique_text(self.required_capability_refs, "required_capability_refs")
        if not self.required_capability_refs:
            raise ValueError("required_capability_refs must not be empty")
        self._validate_world_join()
        if self.candidate_ref not in self.matching_policy.permitted_difference_refs:
            raise ValueError("matching_policy permitted_difference_refs must include candidate_ref")

    def _validate_world_join(self) -> None:
        if self.baseline_world.world_id == self.counterfactual_world.world_id:
            raise ValueError("baseline and counterfactual worlds must use distinct world_id values")
        if self.baseline_world.run_ref == self.counterfactual_world.run_ref:
            raise ValueError("baseline and counterfactual worlds must use distinct run_ref values")
        if self.baseline_world.family_ref != self.counterfactual_world.family_ref:
            raise ValueError("baseline and counterfactual worlds must use the same family_ref")
        if self.baseline_world.baseline_lineage_ref != self.counterfactual_world.baseline_lineage_ref:
            raise ValueError("baseline and counterfactual worlds must use the same baseline_lineage_ref")

    @property
    def digest(self) -> str:
        """Return the canonical identity of every comparison join input."""

        payload = {
            "case_id": self.case_id,
            "claim": self.claim.model_dump(mode="json"),
            "candidate_ref": self.candidate_ref,
            "outcome_proposition_address": self.outcome_proposition_address,
            "outcome_assertion_address": self.outcome_assertion_address,
            "baseline_world": asdict(self.baseline_world),
            "counterfactual_world": asdict(self.counterfactual_world),
            "intervention_kind": self.intervention_kind.value,
            "intervention_ref": self.intervention_ref,
            "intervention_version": self.intervention_version,
            "intervention_digest": self.intervention_digest,
            "criterion_id": self.criterion_id,
            "criterion_version": self.criterion_version,
            "matching_policy": {
                "policy_id": self.matching_policy.policy_id,
                "policy_version": self.matching_policy.policy_version,
                "held_fixed_dimensions": list(self.matching_policy.held_fixed_dimensions),
                "permitted_difference_refs": list(self.matching_policy.permitted_difference_refs),
            },
            "required_capability_refs": list(self.required_capability_refs),
            "verification_authority": asdict(self.verification_authority),
            "input_digest": self.input_digest,
        }
        return sorted_json_digest(payload)


@dataclass(frozen=True)
class BoundedButForResult:
    """Finite comparison result whose identities come only from the case."""

    case_id: str
    case_digest: str
    claim: BehavioralClaimBindingModel
    baseline_world: NecessityWorldRef
    counterfactual_world: NecessityWorldRef
    outcome: NecessityComparisonOutcome
    evidence_refs: tuple[str, ...]
    verification_identities: tuple[VerificationRecordIdentity, ...]
    diagnostics: tuple[Diagnostic, ...]

    @property
    def supported(self) -> bool:
        return self.outcome is NecessityComparisonOutcome.SUPPORTED


def _diagnostic(case: BoundedButForCase, code: str, message: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        domain="conformance",
        address=f"necessity-comparison.{case.case_id}",
        message=message,
        severity=Severity.ERROR,
    )


def _result(
    case: BoundedButForCase,
    evidence: BoundedButForEvidence,
    outcome: NecessityComparisonOutcome,
    diagnostics: tuple[Diagnostic, ...] = (),
) -> BoundedButForResult:
    evidence_refs = tuple(
        dict.fromkeys(
            (
                *evidence.baseline_truth.evidence_refs,
                *evidence.counterfactual_truth.evidence_refs,
                *evidence.intervention_evidence_refs,
                *evidence.cleanup_evidence_refs,
            )
        )
    )
    return BoundedButForResult(
        case_id=case.case_id,
        case_digest=case.digest,
        claim=case.claim,
        baseline_world=case.baseline_world,
        counterfactual_world=case.counterfactual_world,
        outcome=outcome,
        evidence_refs=evidence_refs,
        verification_identities=evidence.verification_identities,
        diagnostics=diagnostics,
    )


def _claim_catalog_diagnostic(case: BoundedButForCase) -> Diagnostic | None:
    diagnostic = None
    try:
        validate_behavioral_claim_binding(case.claim)
    except ValueError:
        diagnostic = _diagnostic(
            case,
            "conformance.necessity-claim-invalid",
            "The claim does not resolve against the canonical behavioral-relation catalog.",
        )
    return diagnostic


def _claim_admission_diagnostic(case: BoundedButForCase) -> Diagnostic | None:
    diagnostic = None
    if case.claim.relation_id != BOUNDED_BUT_FOR_RELATION_ID:
        diagnostic = _diagnostic(
            case,
            "conformance.necessity-claim-relation-invalid",
            "The claim does not use the bounded but-for necessity relation.",
        )
    elif (catalog_diagnostic := _claim_catalog_diagnostic(case)) is not None:
        diagnostic = catalog_diagnostic
    elif case.claim.quantifier_scope != "finite-cases" or case.claim.evidence_scope != "finite":
        diagnostic = _diagnostic(
            case,
            "conformance.necessity-claim-boundary-invalid",
            "The binary comparator accepts only finite-case claims with finite evidence.",
        )
    elif (
        case.claim.left_carrier_ref != case.candidate_ref
        or case.claim.right_carrier_ref != case.outcome_proposition_address
    ):
        diagnostic = _diagnostic(
            case,
            "conformance.necessity-claim-case-mismatch",
            "The claim carriers do not identify the admitted candidate and outcome.",
        )
    elif (case.criterion_id, case.criterion_version) != (_CRITERION_ID, _CRITERION_VERSION):
        diagnostic = _diagnostic(
            case,
            "conformance.necessity-criterion-unsupported",
            "The requested necessity criterion is not supported by this comparator.",
        )
    return diagnostic


def _evidence_admission_diagnostic(
    case: BoundedButForCase,
    evidence: BoundedButForEvidence,
) -> Diagnostic | None:
    diagnostic = None
    world_mismatch = (
        evidence.baseline_world_id != case.baseline_world.world_id
        or evidence.baseline_run_ref != case.baseline_world.run_ref
        or evidence.counterfactual_world_id != case.counterfactual_world.world_id
        or evidence.counterfactual_run_ref != case.counterfactual_world.run_ref
    )
    authority_mismatch = evidence.verification_binding != case.verification_authority or any(
        identity.binding != case.verification_authority for identity in evidence.verification_identities
    )
    truth_mismatch = any(
        truth.proposition_address != case.outcome_proposition_address
        or truth.assertion_address != case.outcome_assertion_address
        for truth in (evidence.baseline_truth, evidence.counterfactual_truth)
    )
    if world_mismatch:
        diagnostic = _diagnostic(
            case,
            "conformance.necessity-world-evidence-mismatch",
            "The evidence does not identify the admitted worlds and immutable run references.",
        )
    elif authority_mismatch:
        diagnostic = _diagnostic(
            case,
            "conformance.necessity-verification-authority-mismatch",
            "The verification identities do not match the authority admitted by the case.",
        )
    elif truth_mismatch:
        diagnostic = _diagnostic(
            case,
            "conformance.necessity-world-evidence-mismatch",
            "A world truth result does not identify the admitted outcome.",
        )
    return diagnostic


def _admission_diagnostic(
    case: BoundedButForCase,
    evidence: BoundedButForEvidence,
    available_capability_refs: frozenset[str],
) -> Diagnostic | None:
    diagnostic = None
    if not evidence._has_authentic_assembly():
        diagnostic = _diagnostic(
            case,
            "conformance.necessity-evidence-unauthenticated",
            "The comparison evidence was not produced by the trusted necessity assembler.",
        )
    elif evidence.case_digest != case.digest:
        diagnostic = _diagnostic(
            case,
            "conformance.necessity-case-evidence-mismatch",
            "The assembled evidence does not belong to the admitted comparison case.",
        )
    elif (claim_diagnostic := _claim_admission_diagnostic(case)) is not None:
        diagnostic = claim_diagnostic
    elif set(case.required_capability_refs) - set(available_capability_refs):
        diagnostic = _diagnostic(
            case,
            "conformance.necessity-capability-unsupported",
            "The comparator does not have every capability required by the admitted case.",
        )
    else:
        diagnostic = _evidence_admission_diagnostic(case, evidence)
    return diagnostic


def _gate_diagnostics(
    case: BoundedButForCase,
    evidence: BoundedButForEvidence,
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    if (
        evidence.intervention_disposition is not VerificationDisposition.VERIFIED
        or not evidence.intervention_evidence_refs
    ):
        diagnostics.append(
            _diagnostic(
                case,
                "conformance.necessity-intervention-unverified",
                "The declared intervention was not independently verified.",
            )
        )
    if evidence.matching_disposition is not VerificationDisposition.VERIFIED or evidence.unmatched_dimension_refs:
        diagnostics.append(
            _diagnostic(
                case,
                "conformance.necessity-worlds-incomparable",
                "The worlds do not satisfy the declared matching policy.",
            )
        )
    if evidence.cleanup_disposition is not VerificationDisposition.VERIFIED or not evidence.cleanup_evidence_refs:
        diagnostics.append(
            _diagnostic(
                case,
                "conformance.necessity-cleanup-unverified",
                "Reset and cleanup were not independently verified.",
            )
        )
    if evidence.residual_state:
        diagnostics.append(
            _diagnostic(
                case,
                "conformance.necessity-residual-state",
                "The comparison left residual owned state.",
            )
        )
    return tuple(diagnostics)


def _comparison_disposition(
    case: BoundedButForCase,
    evidence: BoundedButForEvidence,
) -> tuple[NecessityComparisonOutcome, tuple[Diagnostic, ...]]:
    outcome = NecessityComparisonOutcome.SUPPORTED
    diagnostics: tuple[Diagnostic, ...] = ()
    truth_outcomes = (
        evidence.baseline_truth.proposition_outcome,
        evidence.counterfactual_truth.proposition_outcome,
    )
    verification_dispositions = (
        evidence.intervention_disposition,
        evidence.matching_disposition,
        evidence.cleanup_disposition,
    )
    if PropositionTruthOutcome.UNSUPPORTED in truth_outcomes:
        outcome = NecessityComparisonOutcome.UNSUPPORTED
        diagnostics = (
            _diagnostic(
                case,
                "conformance.necessity-outcome-unsupported",
                "At least one world outcome is unsupported by the admitted apparatus.",
            ),
        )
    elif PropositionTruthOutcome.UNKNOWN in truth_outcomes:
        outcome = NecessityComparisonOutcome.INCONCLUSIVE
        diagnostics = (
            _diagnostic(
                case,
                "conformance.necessity-outcome-inconclusive",
                "At least one world outcome is indeterminate.",
            ),
        )
    elif VerificationDisposition.UNSUPPORTED in verification_dispositions:
        outcome = NecessityComparisonOutcome.UNSUPPORTED
        diagnostics = (
            _diagnostic(
                case,
                "conformance.necessity-verification-unsupported",
                "At least one required verification fact is unsupported by the admitted validator.",
            ),
        )
    elif evidence.baseline_truth.proposition_outcome is PropositionTruthOutcome.FALSE:
        outcome = NecessityComparisonOutcome.INCONCLUSIVE
        diagnostics = (
            _diagnostic(
                case,
                "conformance.necessity-baseline-nonvacuity-failed",
                "The baseline outcome is false, so the necessity comparison is non-vacuous only as inconclusive.",
            ),
        )
    elif gate_diagnostics := _gate_diagnostics(case, evidence):
        outcome = NecessityComparisonOutcome.INCONCLUSIVE
        diagnostics = gate_diagnostics
    elif evidence.counterfactual_truth.proposition_outcome is PropositionTruthOutcome.TRUE:
        outcome = NecessityComparisonOutcome.REFUTED
    return outcome, diagnostics


def compare_bounded_but_for(
    case: BoundedButForCase,
    evidence: BoundedButForEvidence,
    *,
    available_capability_refs: frozenset[str],
) -> BoundedButForResult:
    """Evaluate one admitted finite binary but-for necessity comparison."""
    admission_diagnostic = _admission_diagnostic(case, evidence, available_capability_refs)
    if admission_diagnostic is not None:
        outcome = NecessityComparisonOutcome.UNSUPPORTED
        diagnostics = (admission_diagnostic,)
    else:
        outcome, diagnostics = _comparison_disposition(case, evidence)
    return _result(case, evidence, outcome, diagnostics)
