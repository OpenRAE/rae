"""Conformance case/report dataclasses, payload projection, and bounded claim."""

from __future__ import annotations

from dataclasses import dataclass, field

from raes_contracts.behavioral_relations import validate_behavioral_claim_binding
from raes_contracts.contracts import BehavioralClaimBindingModel
from raes_contracts.diagnostics import Diagnostic

from raes_conformance.conformance.diagnostics import _diagnostic_payload
from raes_conformance.conformance.mixed_backend_types import MixedBackendCaseBinding, mixed_case_binding_payload
from raes_conformance.realization import ExecutionBasis


@dataclass(frozen=True)
class ParticipantPolicyAssumptions:
    """Named assumption boundary for one participant-policy case.

    ADR-085 and SEM-230 require every information-flow result to fix its model
    and assumption parameters rather than inherit them silently, so these are
    separate declared fields instead of prose in a case name.
    """

    order_model: str
    scheduler_class: str
    environment_class: str
    nondeterminism: str
    termination_and_progress: str
    timing: str
    probability: str
    partial_order: str


@dataclass(frozen=True)
class ParticipantPolicyBinding:
    """Machine-reviewable coordinates for one finite participant-policy case.

    The relation identity, carriers, quantifier and evidence scope, assurance
    status, limitations, and nonclaims live in ``claim`` — a real
    :class:`BehavioralClaimBindingModel`, so the catalog stays the single claim
    authority and these coordinates cannot drift into unconstrained strings that
    name a relation the taxonomy does not define. Only the participant, policy,
    and assumption coordinates the claim model has no field for are carried
    alongside it.

    Referencing an obligation is not claiming it: the report's own relation
    stays ``bounded-probe-success`` and these finite cases never establish
    ``policy-noninterference``.
    """

    obligation: str
    claim: BehavioralClaimBindingModel
    participant_ref: str
    audience_ref: str
    memory_scope: str
    policy_id: str
    policy_revision: str
    policy_decision_ref: str
    decision_cut_ref: str
    assumptions: ParticipantPolicyAssumptions
    declassification_schedule_ref: str | None = None
    counterexample_ref: str | None = None


@dataclass(frozen=True)
class ConformanceCaseResult:
    """Result for one fixture or probe case."""

    name: str
    contract_name: str
    valid: bool
    passed: bool
    diagnostics: tuple[Diagnostic, ...] = ()
    execution_basis: str = ExecutionBasis.FIXTURE_ONLY.value
    outcome: str = "passed"
    probe_kind: str | None = None
    probe_digest: str | None = None
    probe_set_digest: str | None = None
    envelope_digest: str | None = None
    configuration_digest: str | None = None
    target_binding: str | None = None
    expected_operations: tuple[str, ...] = ()
    accounted_operations: tuple[str, ...] = ()
    expected_observation_strengths: tuple[str, ...] = ()
    actual_observation_strengths: tuple[str, ...] = ()
    portable_state_unchanged: bool | None = None
    native_state_unchanged: bool | None = None
    cleanup_verified: bool | None = None
    residual_state: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    capability_feature: str | None = None
    declared_support_level: str | None = None
    effective_support_level: str | None = None
    finite_scope: str | None = None
    limitations: tuple[str, ...] = ()
    explicit_non_claims: tuple[str, ...] = ()
    policy_binding: ParticipantPolicyBinding | None = None
    claim_bindings: tuple[BehavioralClaimBindingModel, ...] = ()
    realization_owner: str | None = None
    evidence_origin: str | None = None
    profile_digest: str | None = None
    manifest_digest: str | None = None
    tool_digest: str | None = None
    environment_digest: str | None = None
    mixed_binding: MixedBackendCaseBinding | None = None

    def __post_init__(self) -> None:
        """Keep the closed outcome vocabulary aligned with the gating boolean."""

        if self.outcome == "passed" and not self.passed:
            object.__setattr__(self, "outcome", "failed")


@dataclass(frozen=True)
class BackendConformanceReport:
    """Machine-friendly conformance result.

    ``profile`` is the requested profile id as a string. When the request used
    a :class:`BackendCapabilityProfile` enum member, equality comparisons against
    that member still work because the enum is ``str``-valued. Carrying the
    field as ``str`` lets the runner accept (and report) profile ids that have
    no Python-side enum member.
    """

    profile: str
    passed: bool
    claim: BehavioralClaimBindingModel
    cases: tuple[ConformanceCaseResult, ...] = ()
    contract_versions: dict[str, str] = field(default_factory=dict)
    unsupported_contract_gaps: tuple[str, ...] = ()
    unsupported_capability_gaps: tuple[str, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    probe_set_digest: str | None = None
    native_conformance: bool = False


_UNIVERSAL_QUANTIFIER_SCOPES = frozenset({"all-admitted-inputs", "all-traces", "all-strategies"})
_UNIVERSAL_EVIDENCE_SCOPES = frozenset({"model-check", "proof"})
_NATIVE_EXECUTION_BASES = frozenset({"native-live"})


def validate_backend_conformance_report(report: BackendConformanceReport) -> BackendConformanceReport:
    """Validate a report's cross-field honesty before it is serialized or persisted.

    Individual case and claim models are each valid in isolation while the
    report as a whole still overstates what it established, so this is the one
    seam where the claim, the case set, and the execution basis are checked
    against each other. It refuses a universal quantifier backed only by finite
    evidence, a native-conformance flag with no natively-executed case, and a
    claim whose cited cases are not all present — including the failed,
    unsupported, and counterexample cases, whose absence would turn a partial
    run into an apparently clean one.
    """

    _validate_catalog_bindings(report)
    _validate_claim_strength(report)
    _validate_case_evidence(report)
    _validate_case_outcomes(report)
    return report


def _validate_case_outcomes(report: BackendConformanceReport) -> None:
    """Keep outcome and pass fields consistent and mixed coordinates resolvable.

    An empty case set certifies nothing, and a native report must have executed
    every mixed obligation natively, not just one unrelated case.
    """

    if report.passed and not report.cases:
        raise ValueError("backend conformance report is marked passed without any case")
    for case in report.cases:
        if case.passed != (case.outcome == "passed"):
            raise ValueError(f"conformance case {case.name!r} has inconsistent outcome and pass fields")
        if case.mixed_binding is None:
            continue
        if report.native_conformance and case.execution_basis not in _NATIVE_EXECUTION_BASES:
            raise ValueError("a native report requires a native basis for every mixed-backend case")
        coordinates = (case.configuration_digest, case.tool_digest, case.environment_digest)
        if case.passed and (not case.mixed_binding.components or not all(coordinates)):
            raise ValueError(
                "a passing mixed-backend case requires component coordinates and configuration, "
                "tool, and environment digests"
            )


def _validate_catalog_bindings(report: BackendConformanceReport) -> None:
    """Send the report claim and every case binding through the catalog.

    Publishing a case binding the taxonomy does not define would let a durable
    report name a relation nobody governs.
    """

    validate_behavioral_claim_binding(report.claim)
    for case in report.cases:
        if case.policy_binding is not None:
            validate_behavioral_claim_binding(case.policy_binding.claim)
        for binding in case.claim_bindings:
            validate_behavioral_claim_binding(binding)
        _validate_case_claim_chain(case)


def _validate_case_claim_chain(case: ConformanceCaseResult) -> None:
    """Require declaration, realization, and conformance to remain distinct."""

    if not case.claim_bindings:
        return
    axes = {binding.assurance_axis for binding in case.claim_bindings}
    _validate_claim_axes(axes)
    _validate_claim_coordinates(case)
    if "backend-realization" in axes:
        _validate_observed_native_evidence(case, "backend realization")
    if "backend-conformance" in axes:
        _validate_observed_native_evidence(case, "backend conformance")
        _validate_backend_conformance_claim(case)


def _validate_claim_axes(axes: set[str | None]) -> None:
    """Require each stronger assurance axis to retain its prerequisites."""

    if "backend-realization" in axes and "backend-declaration" not in axes:
        raise ValueError("backend realization claim requires a backend declaration claim")
    if "backend-conformance" in axes and "backend-realization" not in axes:
        raise ValueError("backend conformance claim requires a backend realization claim")
    if "backend-conformance" in axes and "backend-declaration" not in axes:
        raise ValueError("backend conformance claim requires a backend declaration claim")


def _validate_claim_coordinates(case: ConformanceCaseResult) -> None:
    """Require every assurance step to use one governed relation coordinate."""

    coordinates = {
        (
            binding.taxonomy_id,
            binding.taxonomy_revision,
            binding.relation_id,
            binding.relation_parameter_profile_ref,
            binding.relation_parameter_profile_revision,
        )
        for binding in case.claim_bindings
    }
    if len(coordinates) != 1:
        raise ValueError("backend assurance claims for one case must use identical governed coordinates")


def _validate_observed_native_evidence(case: ConformanceCaseResult, claim: str) -> None:
    """Require a backend-native owner derived from fully observed execution.

    A reported or finite-model transcript, or a runtime-mediated result, cannot
    carry a backend realization or conformance claim, even in a report built by
    hand rather than by the runner.
    """

    if case.realization_owner != "backend-native":
        raise ValueError(f"{claim} claim requires backend-native realization ownership")
    if case.evidence_origin != "observed-execution":
        raise ValueError(f"{claim} claim requires observed-execution evidence")


def _validate_backend_conformance_claim(case: ConformanceCaseResult) -> None:
    """Require exact evidence coordinates for a backend conformance claim."""

    digests = (
        case.profile_digest,
        case.manifest_digest,
        case.configuration_digest,
        case.tool_digest,
        case.environment_digest,
        case.probe_set_digest,
    )
    if any(not digest for digest in digests):
        raise ValueError(
            "backend conformance claim requires exact profile, manifest, configuration, "
            "tool, environment, and probe-set digests"
        )


def _validate_claim_strength(report: BackendConformanceReport) -> None:
    """Refuse a claim stronger than the evidence behind it."""

    claim = report.claim
    universal = claim.quantifier_scope in _UNIVERSAL_QUANTIFIER_SCOPES
    if universal and claim.evidence_scope not in _UNIVERSAL_EVIDENCE_SCOPES:
        raise ValueError(
            "backend conformance report states a universal quantifier "
            f"({claim.quantifier_scope!r}) with {claim.evidence_scope!r} evidence; "
            "universal quantification requires model-check or proof evidence"
        )
    natively_executed = any(case.execution_basis in _NATIVE_EXECUTION_BASES for case in report.cases)
    if report.native_conformance and not natively_executed:
        raise ValueError(
            "backend conformance report claims native conformance but no case executed "
            "on a native basis; fixture-only and hermetic evidence do not establish it"
        )


def _validate_case_evidence(report: BackendConformanceReport) -> None:
    """Require every cited case to be present, and a pass to carry no failure."""

    present = {f"conformance-case:{case.contract_name}:{case.name}" for case in report.cases}
    missing = sorted(
        ref for ref in report.claim.evidence_refs if ref.startswith("conformance-case:") and ref not in present
    )
    if missing:
        raise ValueError(f"backend conformance report claimed case evidence that is absent: {missing}")
    if report.passed and any(not case.passed for case in report.cases):
        raise ValueError("backend conformance report is marked passed while carrying a non-passing case")


def _policy_binding_payload(
    binding: ParticipantPolicyBinding | None,
) -> dict[str, object] | None:
    """Project the participant-policy coordinates into the one report family."""

    if binding is None:
        return None
    return {
        "obligation": binding.obligation,
        "claim": binding.claim.model_dump(mode="json"),
        "participant_ref": binding.participant_ref,
        "audience_ref": binding.audience_ref,
        "memory_scope": binding.memory_scope,
        "policy_id": binding.policy_id,
        "policy_revision": binding.policy_revision,
        "policy_decision_ref": binding.policy_decision_ref,
        "decision_cut_ref": binding.decision_cut_ref,
        "declassification_schedule_ref": binding.declassification_schedule_ref,
        "counterexample_ref": binding.counterexample_ref,
        "assumptions": {
            "order_model": binding.assumptions.order_model,
            "scheduler_class": binding.assumptions.scheduler_class,
            "environment_class": binding.assumptions.environment_class,
            "nondeterminism": binding.assumptions.nondeterminism,
            "termination_and_progress": binding.assumptions.termination_and_progress,
            "timing": binding.assumptions.timing,
            "probability": binding.assumptions.probability,
            "partial_order": binding.assumptions.partial_order,
        },
    }


def backend_conformance_report_payload(report: BackendConformanceReport) -> dict[str, object]:
    """Render the single machine-readable backend conformance report projection."""

    validate_backend_conformance_report(report)
    return {
        "profile": report.profile,
        "passed": report.passed,
        "native_conformance": report.native_conformance,
        "probe_set_digest": report.probe_set_digest,
        "claim": report.claim.model_dump(mode="json"),
        "contract_versions": dict(report.contract_versions),
        "unsupported_contract_gaps": list(report.unsupported_contract_gaps),
        "unsupported_capability_gaps": list(report.unsupported_capability_gaps),
        "cases": [
            {
                "name": case.name,
                "contract_name": case.contract_name,
                "valid": case.valid,
                "passed": case.passed,
                "execution_basis": case.execution_basis,
                "outcome": case.outcome,
                "probe_kind": case.probe_kind,
                "probe_digest": case.probe_digest,
                "probe_set_digest": case.probe_set_digest,
                "envelope_digest": case.envelope_digest,
                "configuration_digest": case.configuration_digest,
                "target_binding": case.target_binding,
                "expected_operations": list(case.expected_operations),
                "accounted_operations": list(case.accounted_operations),
                "expected_observation_strengths": list(case.expected_observation_strengths),
                "actual_observation_strengths": list(case.actual_observation_strengths),
                "portable_state_unchanged": case.portable_state_unchanged,
                "native_state_unchanged": case.native_state_unchanged,
                "cleanup_verified": case.cleanup_verified,
                "residual_state": list(case.residual_state),
                "evidence_refs": list(case.evidence_refs),
                "capability_feature": case.capability_feature,
                "declared_support_level": case.declared_support_level,
                "effective_support_level": case.effective_support_level,
                "finite_scope": case.finite_scope,
                "limitations": list(case.limitations),
                "explicit_non_claims": list(case.explicit_non_claims),
                "policy_binding": _policy_binding_payload(case.policy_binding),
                "claim_bindings": [binding.model_dump(mode="json") for binding in case.claim_bindings],
                "realization_owner": case.realization_owner,
                "evidence_origin": case.evidence_origin,
                "profile_digest": case.profile_digest,
                "manifest_digest": case.manifest_digest,
                "tool_digest": case.tool_digest,
                "environment_digest": case.environment_digest,
                "mixed_binding": mixed_case_binding_payload(case.mixed_binding),
                "diagnostics": [_diagnostic_payload(diag) for diag in case.diagnostics],
            }
            for case in report.cases
        ],
        "diagnostics": [_diagnostic_payload(diag) for diag in report.diagnostics],
    }


def _bounded_conformance_claim(
    *,
    profile: str,
    cases: tuple[ConformanceCaseResult, ...],
    left_carrier_ref: str,
    subject: str | None = None,
    right_carrier_ref: str | None = None,
    evidence_boundary: str | None = None,
) -> BehavioralClaimBindingModel:
    """Describe exactly what a conformance report's finite cases establish.

    A probe family that does not certify a published backend profile names its
    own subject, catalog carrier, and evidence boundary.
    """

    evidence_refs = [f"conformance-case:{case.contract_name}:{case.name}" for case in cases]
    binding = BehavioralClaimBindingModel(
        taxonomy_id="raes-behavioral-relations",
        taxonomy_revision="rev8",
        relation_id="bounded-probe-success",
        subject=subject or f"Backend conformance for profile {profile}",
        left_carrier_ref=left_carrier_ref,
        right_carrier_ref=right_carrier_ref or f"backend-profile:{profile}",
        observation_projection_ref="backend-conformance-case-report",
        observation_projection_revision="rev1",
        quantifier_scope="finite-cases",
        evidence_scope="finite",
        evidence_boundary=evidence_boundary
        or (
            f"The {len(cases)} named fixture and target-probe cases recorded in this report; "
            "no unexecuted input, trace, scheduler, strategy, or environment is quantified."
        ),
        assurance_status="tested",
        evidence_refs=evidence_refs,
        limitations=[
            "Case results are bounded by the selected profile, corpus revision, target, and execution environment."
        ],
        explicit_non_claims=[
            "Does not establish trace equivalence or bisimulation.",
            "Does not establish strategic, epistemic, probabilistic, timed, or partial-order equivalence.",
            (
                "Finite generated probes do not establish universal realizability "
                "outside the recorded envelope dimensions."
            ),
            "Fixture-only and hermetic-live execution do not establish native-daemon conformance.",
        ],
    )
    return validate_behavioral_claim_binding(binding)
