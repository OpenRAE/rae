"""ASR-535 participant-policy conformance probes.

API-407 lets a backend *declare* participant information-flow support. Before
this module the target runner projected that declaration straight into a passing
conformance case, so a backend could declare exact support and conform without
any participant-policy behavior ever being driven. Declaration is not
realization.

**The runner owns execution and the verdict.** A harness supplies declarative
case inputs — the deployment's policy resolver, the participant and audience
coordinates, the typed carriers, and the expected disposition — and nothing
else. It never supplies a control plane, a boolean outcome, or a side-effect
fact. The runner constructs the real :class:`RuntimeControlPlane` on the target
under evaluation, wraps that target's participant runtime in a call counter,
invokes the typed boundary itself, and derives every reported fact from the raw
boundary result plus its own before/after ledger. A harness able to supply the
execution object or the verdict could certify a backend it never ran, which is
precisely the substitution this probe family exists to detect.

The probe set is finite falsification evidence for the named target, profile,
and cases. It establishes no universal property: the report relation stays
``bounded-probe-success``, and a case that references the SEM-230
``policy-noninterference`` obligation is recording what it attempted to falsify,
not asserting that the obligation holds.
"""

from __future__ import annotations

from dataclasses import replace

from raes_backend_protocols.capabilities import PARTICIPANT_RUNTIME_POLICY_FEATURES
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import RaesError
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel
from raes_runtime.registry import RuntimeTarget

from raes_conformance.conformance.diagnostics import _diagnostic, sanitized_failure_message
from raes_conformance.conformance.participant_policy_execution import _Outcome, _run_case
from raes_conformance.conformance.participant_policy_types import (
    _EXPECTED_DISPOSITIONS,
    _REFUSAL_EXPECTATIONS,
    _STANDING_LIMITATIONS,
    _STANDING_NON_CLAIMS,
    ParticipantPolicyExpectation,
    ParticipantPolicyOperation,
    ParticipantPolicyProbeCase,
    ParticipantPolicyProbeHarness,
    _declared_level,
    _unprobed_binding,
)
from raes_conformance.conformance.profiles import BackendProfileSelector, _to_profile_id
from raes_conformance.conformance.report import ConformanceCaseResult

_LOGGER = get_logger(__name__)
_PROBE_MISSING_CODE = "conformance.participant-policy-probe-missing"
_OVERCLAIM_CODE = "conformance.participant-policy-overclaim"
_PROBE_FAILED_CODE = "conformance.participant-policy-probe-failed"

_CONTRACT_NAME = "participant-crossing-occurrence-v1"


def declared_policy_features(target: RuntimeTarget) -> tuple[str, ...]:
    """Return governed participant-policy features declared above unsupported."""

    capabilities = target.manifest.participant_runtime
    if capabilities is None:
        return ()
    return tuple(
        sorted(
            entry.feature
            for entry in capabilities.feature_support
            if entry.feature in PARTICIPANT_RUNTIME_POLICY_FEATURES
            and entry.support_level != ParticipantFeatureSupportLevel.UNSUPPORTED
        )
    )


def _finite_scope(target: RuntimeTarget, profile_id: str, obligation: str, digest: str) -> str:
    return (
        f"Single-fault {obligation!r} probe for target {target.name!r} under profile "
        f"{profile_id!r}, probe set {digest}; no unexecuted participant, policy, strategy, "
        "scheduler, environment, or trace is quantified."
    )


def _unsupported_case(
    target: RuntimeTarget,
    profile_id: str,
    feature: str,
    reason: str,
) -> ConformanceCaseResult:
    """Record a declared feature whose authorized behavior was never established.

    Counting this as passed would let a positive manifest entry substitute for
    behavior, which is exactly the overclaim this probe family exists to catch.
    """

    return ConformanceCaseResult(
        name=f"participant-policy-{feature}-unprobed",
        contract_name=_CONTRACT_NAME,
        valid=True,
        passed=False,
        outcome="unsupported",
        capability_feature=feature,
        declared_support_level=_declared_level(target, feature),
        effective_support_level=None,
        diagnostics=(_diagnostic(_PROBE_MISSING_CODE, feature, reason),),
        finite_scope=(
            f"Static declaration only for target {target.name!r} under profile {profile_id!r}; "
            "no authorized participant-policy behavior was established."
        ),
        limitations=_STANDING_LIMITATIONS,
        explicit_non_claims=_STANDING_NON_CLAIMS,
        policy_binding=_unprobed_binding(feature),
    )


def _record_integrity_failures(case: ParticipantPolicyProbeCase, observed: _Outcome) -> list[str]:
    """Breaches of record validity, append-only integrity, and disposition."""

    failures: list[str] = []
    if observed.invalid_reason is not None:
        failures.append(f"a committed crossing record failed contract validation ({observed.invalid_reason})")
    if observed.mutated_existing:
        failures.append("an existing append-only crossing record was mutated")
    permitted = _EXPECTED_DISPOSITIONS[case.expectation]
    if observed.appended_dispositions and not (set(observed.appended_dispositions) & permitted):
        failures.append(
            f"the recorded disposition {observed.appended_dispositions[-1]!r} is not one the "
            f"{case.expectation.value!r} obligation permits"
        )
    return failures


def _refusal_failures(case: ParticipantPolicyProbeCase, observed: _Outcome) -> list[str]:
    """Breaches of a refusal obligation, including its side-effect boundary.

    Checking only the final disposition would pass a target that denied the
    crossing after already invoking the backend or serializing a
    participant-visible value.
    """

    failures: list[str] = []
    if not observed.refused:
        failures.append("the prohibited crossing was not refused")
    if observed.released:
        failures.append("a participant-visible value was released despite refusal")
    if observed.backend_calls:
        failures.append("the backend participant runtime was invoked despite refusal")
    if case.expect_audit and not observed.audited:
        failures.append("the refusal recorded no safe audit evidence")
    if case.expectation is ParticipantPolicyExpectation.WITHHELD and not observed.appended_dispositions:
        failures.append("intentional withholding recorded no decision, so it is indistinguishable from failure")
    return failures


def _release_failures(observed: _Outcome) -> list[str]:
    """Breaches of an authorized-release obligation."""

    failures: list[str] = []
    if observed.refused:
        failures.append("an authorized crossing was refused")
    if not observed.released:
        failures.append("the authorized crossing released nothing")
    if not observed.evidence_refs:
        failures.append("the permitted crossing recorded no evidence refs")
    if observed.effective_support_level != observed.declared_support_level:
        failures.append(
            "effective backend strength is weaker than the declared strength without an authorized downgrade"
        )
    return failures


def _violations(case: ParticipantPolicyProbeCase, observed: _Outcome) -> tuple[str, ...]:
    """Return the obligation breaches this outcome exhibits."""

    expectation_failures = (
        _refusal_failures(case, observed) if case.expectation in _REFUSAL_EXPECTATIONS else _release_failures(observed)
    )
    return (*_record_integrity_failures(case, observed), *expectation_failures)


def _case_result(
    target: RuntimeTarget,
    profile_id: str,
    digest: str,
    case: ParticipantPolicyProbeCase,
) -> ConformanceCaseResult:
    try:
        observed = _run_case(case, target)
    except Exception as exc:
        if not isinstance(exc, RaesError):
            # Isolation of the target runtime and the harness resolver: a refusal category needs no record.
            _LOGGER.exception("participant-policy probe failed", exc_info=foreign_failure_record(exc))
        return ConformanceCaseResult(
            name=f"participant-policy-{case.obligation}",
            contract_name=_CONTRACT_NAME,
            valid=True,
            passed=False,
            outcome="failed",
            capability_feature=case.feature,
            declared_support_level=_declared_level(target, case.feature),
            effective_support_level=None,
            diagnostics=(
                _diagnostic(
                    _PROBE_FAILED_CODE,
                    case.feature,
                    f"participant-policy probe {case.obligation!r} failed: {sanitized_failure_message(exc)}",
                ),
            ),
            finite_scope=_finite_scope(target, profile_id, case.obligation, digest),
            limitations=_STANDING_LIMITATIONS,
            explicit_non_claims=_STANDING_NON_CLAIMS,
            policy_binding=case.binding,
            probe_set_digest=digest,
        )

    failures = _violations(case, observed)
    binding = (
        replace(case.binding, counterexample_ref=observed.counterexample_ref)
        if observed.counterexample_ref is not None
        else case.binding
    )
    diagnostics: tuple[Diagnostic, ...] = tuple(
        _diagnostic(
            _OVERCLAIM_CODE,
            case.feature,
            (
                f"Target {target.name!r} declares {case.feature!r} at "
                f"{observed.declared_support_level!r} but the {case.obligation!r} probe observed "
                f"that {failure}."
            ),
        )
        for failure in failures
    )
    return ConformanceCaseResult(
        name=f"participant-policy-{case.obligation}",
        contract_name=_CONTRACT_NAME,
        valid=True,
        passed=not failures,
        outcome="passed" if not failures else "failed",
        capability_feature=case.feature,
        declared_support_level=observed.declared_support_level,
        effective_support_level=observed.effective_support_level,
        diagnostics=diagnostics,
        evidence_refs=observed.evidence_refs,
        finite_scope=_finite_scope(target, profile_id, case.obligation, digest),
        limitations=_STANDING_LIMITATIONS,
        explicit_non_claims=_STANDING_NON_CLAIMS,
        policy_binding=binding,
        probe_set_digest=digest,
    )


def _established_features(
    cases: tuple[ParticipantPolicyProbeCase, ...],
    results: list[ConformanceCaseResult],
) -> set[str]:
    """Return features whose *authorized* behavior was actually established.

    A refusal-only case proves the target can fail closed, which an absent
    implementation also does. Only a passing ``RELEASED`` case that resolved an
    effective backend strength shows the declared capability is realized, so
    only that counts as coverage.
    """

    return {
        case.feature
        for case, result in zip(cases, results, strict=True)
        if case.expectation is ParticipantPolicyExpectation.RELEASED
        and result.passed
        and result.effective_support_level is not None
    }


def participant_policy_cases(
    target: RuntimeTarget,
    profile: BackendProfileSelector,
    harness: ParticipantPolicyProbeHarness | None,
) -> tuple[ConformanceCaseResult, ...]:
    """Project finite participant-policy probe results into the one report family.

    A target that declares no governed policy feature above unsupported claims
    nothing here and receives no case. A target that declares one receives an
    explicitly unsupported, non-passing case unless an authorized probe outcome
    established that feature's behavior against this target.
    """

    declared = declared_policy_features(target)
    if not declared:
        return ()
    profile_id = _to_profile_id(profile)
    if harness is None:
        return tuple(
            _unsupported_case(
                target,
                profile_id,
                feature,
                (
                    f"Target {target.name!r} declares participant-policy feature {feature!r} above "
                    "unsupported, but no participant-policy probe harness drove it. A declaration "
                    "without an executed probe is unsupported, not conformant."
                ),
            )
            for feature in declared
        )

    cases = harness.cases(target)
    results = [_case_result(target, profile_id, harness.probe_set_digest, case) for case in cases]
    established = _established_features(cases, results)
    results.extend(
        _unsupported_case(
            target,
            profile_id,
            feature,
            (
                f"Target {target.name!r} declares participant-policy feature {feature!r} above "
                "unsupported, but no authorized probe outcome established its behavior against this "
                "target. Refusal-only coverage does not distinguish enforcement from absence."
            ),
        )
        for feature in declared
        if feature not in established
    )
    return tuple(results)


__all__ = (
    "ParticipantPolicyExpectation",
    "ParticipantPolicyOperation",
    "ParticipantPolicyProbeCase",
    "ParticipantPolicyProbeHarness",
    "declared_policy_features",
    "participant_policy_cases",
)
