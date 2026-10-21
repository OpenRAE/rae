"""SEM-231/API-407/ASR-535 backend participant-opacity assurance.

The generic conformance runner owns every verdict. An external-style opacity
backend double (stub components plus a bounded opacity declaration and an
in-process relation probe) and its harness supply the backend inputs, as a
downstream backend distribution would.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from raes_backend_protocols.capabilities import (
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS,
    PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES,
    PARTICIPANT_RUNTIME_POLICY_FEATURES,
    ParticipantFeatureSupport,
)
from raes_backend_protocols.manifest import backend_manifest_payload
from raes_backend_protocols.participant_feature_admission import resolve_participant_feature_support
from raes_backend_stubs.stubs import StubParticipantRuntime, create_stub_target
from raes_conformance.conformance.participant_opacity_probes import (
    ParticipantOpacityProbeCase,
    ParticipantOpacityProbeObservation,
    ParticipantOpacityRealizationOwner,
)
from raes_conformance.conformance.report import (
    backend_conformance_report_payload,
    validate_backend_conformance_report,
)
from raes_conformance.conformance.target import run_target_conformance
from raes_contracts.behavioral_relation_profiles import load_behavioral_relation_profile
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import BackendManifestV2Model
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel

FEATURE = "participant_predicate_opacity"
PROFILE_ID = "participant-opacity-runtime-reference-v1"
SECRET_MARKER = "participant-secret-never-report-965"

EXPECTED_OBSERVATION = ParticipantOpacityProbeObservation(
    decision="deny",
    failure="uniform-refusal",
    action_availability="denied",
    delivery="withheld",
    omission="recorded-at-governed-opportunity",
    retry="stable-replay",
    logical_timing="logical-bucket:contained",
    logical_order="stable-causal-order",
    policy_release_effect="contained",
    external_effect="none",
    payload_released=False,
)


_PROTECTED_POINT = "possible-point:runtime-reference-protected"
_COMPLEMENT_POINT = "possible-point:runtime-reference-complement"


class OpacityParticipantRuntime(StubParticipantRuntime):
    """Backend double exposing the closed finite opacity observation transcript."""

    def participant_relation_probe(
        self, *, relation_id: str, profile_id: str, profile_revision: str, possible_point_ref: str
    ) -> dict[str, object]:
        profile = load_behavioral_relation_profile(PROFILE_ID)
        if (
            relation_id != "participant-predicate-opacity"
            or profile_id != PROFILE_ID
            or profile_revision != profile.profile_revision
            or possible_point_ref not in {_PROTECTED_POINT, _COMPLEMENT_POINT}
        ):
            raise ValueError("unsupported participant relation probe coordinates")
        return EXPECTED_OBSERVATION.__dict__.copy()


def _opacity_support() -> ParticipantFeatureSupport:
    profile = load_behavioral_relation_profile(PROFILE_ID)
    return ParticipantFeatureSupport(
        feature=FEATURE,
        support_level=ParticipantFeatureSupportLevel.BOUNDED,
        constraint_refs=(f"profile:{PROFILE_ID}@{profile.profile_revision}", "scope:finite-backend-double-carrier"),
        limitation_refs=(
            "limitation:participant-opacity:finite-profile-and-probe-set",
            "limitation:participant-opacity:no-universal-proof-or-cross-backend-equivalence",
        ),
        disclosure_refs=("disclosure:participant-opacity:backend-native-double-realization",),
        evidence_refs=("conformance:participant-opacity-backend:complete-transcript",),
    )


def create_opacity_backend_target(participant_runtime=None):
    """Return stub components with a bounded opacity declaration and relation probe."""

    target = create_stub_target()
    capability = target.manifest.participant_runtime
    assert capability is not None
    capability = replace(
        capability,
        supported_behavior_features=capability.supported_behavior_features | {FEATURE},
        feature_support=(
            _opacity_support(),
            *(item for item in capability.feature_support if item.feature != FEATURE),
        ),
    )
    manifest = replace(
        target.manifest,
        capabilities=replace(target.manifest.capabilities, participant_runtime=capability),
    )
    return replace(
        target,
        manifest=manifest,
        participant_runtime=participant_runtime or OpacityParticipantRuntime(),
    )


class OpacityHarness:
    """External-style harness: supplies backend inputs while the runner owns verdicts."""

    probe_set_digest = canonical_json_digest({"probe_set": "participant-opacity-backend/rev1"})
    configuration_digest = canonical_json_digest({"configuration": "opacity-backend-double/default"})
    tool_digest = canonical_json_digest({"tool": "raes-conformance-participant-opacity/rev1"})
    environment_digest = canonical_json_digest({"environment": "in-process-double"})

    def cases(self, target) -> tuple[ParticipantOpacityProbeCase, ...]:
        profile = load_behavioral_relation_profile(PROFILE_ID)
        return (
            ParticipantOpacityProbeCase(
                name="complete-observation-transcript",
                profile_id=profile.profile_id,
                profile_revision=profile.profile_revision,
                profile_digest=profile.canonical_digest,
                actual_point_ref=_PROTECTED_POINT,
                alternative_point_ref=_COMPLEMENT_POINT,
                expected_observation=EXPECTED_OBSERVATION,
                realization_owner=ParticipantOpacityRealizationOwner.BACKEND_NATIVE,
                execution_basis="hermetic-live",
                manifest_digest=canonical_json_digest(backend_manifest_payload(target.manifest)),
                configuration_digest=self.configuration_digest,
                tool_digest=self.tool_digest,
                environment_digest=self.environment_digest,
                evidence_refs=("conformance:participant-opacity-backend:complete-transcript",),
                limitations=("Limited to the named finite profile and probe set.",),
                explicit_non_claims=(
                    "No universal backend opacity, proof, model check, or cross-backend equivalence.",
                ),
            ),
        )

    @staticmethod
    def observe(target, case: ParticipantOpacityProbeCase, point_ref: str) -> ParticipantOpacityProbeObservation:
        runtime = target.participant_runtime
        if runtime is None:
            raise ValueError("participant runtime is unavailable")
        payload = runtime.participant_relation_probe(
            relation_id="participant-predicate-opacity",
            profile_id=case.profile_id,
            profile_revision=case.profile_revision,
            possible_point_ref=point_ref,
        )
        return ParticipantOpacityProbeObservation(**payload)


class RuntimeMediatedOnlyHarness(OpacityHarness):
    def observe(self, target, case: ParticipantOpacityProbeCase, point_ref: str):
        del target, case, point_ref
        return EXPECTED_OBSERVATION


class EmptyOpacityHarness(OpacityHarness):
    def cases(self, target):
        del target
        return ()


class LeakingParticipantRuntime(OpacityParticipantRuntime):
    def participant_relation_probe(self, **coordinates):
        observation = super().participant_relation_probe(**coordinates)
        if coordinates["possible_point_ref"].endswith("protected"):
            observation = {**observation, "decision": "allow"}
        return observation


class SecretFailureHarness(OpacityHarness):
    def observe(self, target, case: ParticipantOpacityProbeCase, point_ref: str):
        del target, case, point_ref
        raise ValueError(f"rejected {SECRET_MARKER}")


def _opacity_declaration(target):
    capability = target.manifest.participant_runtime
    assert capability is not None
    return next(item for item in capability.feature_support if item.feature == FEATURE)


def _opacity_cases(report):
    return [
        case
        for case in report.cases
        if any(binding.relation_id == "participant-predicate-opacity" for binding in case.claim_bindings)
    ]


def test_manifest_round_trip_declares_one_bounded_relation_feature() -> None:
    target = create_opacity_backend_target()
    declaration = _opacity_declaration(target)

    payload = backend_manifest_payload(target.manifest)
    model = BackendManifestV2Model.model_validate(payload)
    round_trip = model.model_dump(mode="json")

    assert round_trip == payload
    assert declaration.support_level is ParticipantFeatureSupportLevel.BOUNDED
    assert declaration.constraint_refs
    assert declaration.limitation_refs
    assert declaration.disclosure_refs
    assert declaration.evidence_refs
    assert FEATURE in PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES
    assert FEATURE not in PARTICIPANT_RUNTIME_POLICY_FEATURES
    assert PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS[
        "capabilities.participant_runtime.supported_behavior_features"
    ][FEATURE] >= {
        "operation-receipt-v1",
        "operation-status-v1",
        "runtime-snapshot-v1",
        "participant-episode-state-envelope-v1",
        "participant-episode-history-event-stream-v1",
        "participant-behavior-history-event-stream-v1",
        "participant-control-occurrence-v1",
        "participant-crossing-occurrence-v1",
        "participant-observation-envelope-v1",
    }


def test_positive_declaration_rejects_missing_evidence_or_contracts() -> None:
    target = create_opacity_backend_target()
    capability = target.manifest.participant_runtime
    assert capability is not None
    declaration = _opacity_declaration(target)

    with pytest.raises(ValueError, match="evidence_refs"):
        replace(declaration, evidence_refs=())

    manifest = replace(
        target.manifest,
        supported_contract_versions=(
            target.manifest.supported_contract_versions - {"participant-crossing-occurrence-v1"}
        ),
    )
    with pytest.raises(ValueError, match="missing required contracts"):
        resolve_participant_feature_support(
            manifest,
            FEATURE,
            required_level=ParticipantFeatureSupportLevel.BOUNDED,
        )


def test_declared_profile_without_executed_cases_is_unsupported() -> None:
    report = run_target_conformance(create_opacity_backend_target())

    case = next(case for case in report.cases if case.capability_feature == FEATURE and case.outcome == "unsupported")
    assert not case.passed
    assert not report.passed
    assert {binding.assurance_axis for binding in case.claim_bindings} == {"backend-declaration"}


def test_empty_harness_cannot_erase_a_positive_declaration() -> None:
    report = run_target_conformance(
        create_opacity_backend_target(),
        participant_opacity_harness=EmptyOpacityHarness(),
    )

    case = next(case for case in report.cases if case.capability_feature == FEATURE)
    assert not case.passed
    assert case.outcome == "unsupported"
    assert any(diag.code == "conformance.participant-opacity-harness-empty" for diag in case.diagnostics)


def test_backend_native_cases_emit_three_independent_bound_claims() -> None:
    target = create_opacity_backend_target()
    profile = load_behavioral_relation_profile(PROFILE_ID)

    report = run_target_conformance(target, participant_opacity_harness=OpacityHarness())

    cases = _opacity_cases(report)
    native = next(case for case in cases if case.realization_owner == "backend-native")
    assert native.passed
    assert not report.passed
    envelope_cases = tuple(case for case in report.cases if case.contract_name == "realization-envelope-v1")
    assert envelope_cases
    assert all(not case.passed for case in envelope_cases)
    assert {binding.assurance_axis for binding in native.claim_bindings} == {
        "backend-declaration",
        "backend-realization",
        "backend-conformance",
    }
    assert all(binding.taxonomy_revision == profile.taxonomy_revision for binding in native.claim_bindings)
    assert all(
        binding.relation_parameter_profile_revision == profile.profile_revision for binding in native.claim_bindings
    )
    assert native.profile_digest == profile.canonical_digest
    assert native.manifest_digest
    assert native.configuration_digest
    assert native.tool_digest
    assert native.environment_digest
    assert native.probe_set_digest == OpacityHarness.probe_set_digest
    assert report.claim.relation_id == "bounded-probe-success"
    assert report.claim.evidence_scope == "finite"


def test_adversarial_backend_is_detected_with_runtime_configuration_fixed() -> None:
    target = create_opacity_backend_target(participant_runtime=LeakingParticipantRuntime())

    report = run_target_conformance(target, participant_opacity_harness=OpacityHarness())

    case = next(case for case in report.cases if case.capability_feature == FEATURE)
    assert not case.passed
    assert not report.passed
    assert {binding.assurance_axis for binding in case.claim_bindings} == {"backend-declaration"}
    assert any(diag.code == "conformance.participant-opacity-observation-mismatch" for diag in case.diagnostics)


def test_runtime_mediation_cannot_be_reported_as_backend_native() -> None:
    report = run_target_conformance(
        create_opacity_backend_target(),
        participant_opacity_harness=RuntimeMediatedOnlyHarness(),
    )

    case = next(case for case in _opacity_cases(report) if case.realization_owner == "backend-native")
    assert not case.passed
    assert any(diag.code == "conformance.participant-opacity-backend-unobserved" for diag in case.diagnostics)
    assert {binding.assurance_axis for binding in case.claim_bindings} == {"backend-declaration"}


def test_forged_manifest_digest_cannot_bind_backend_conformance() -> None:
    class ForgedDigestHarness(OpacityHarness):
        def cases(self, target):
            case = super().cases(target)[0]
            return (replace(case, manifest_digest=canonical_json_digest({"manifest": "other"})),)

    report = run_target_conformance(
        create_opacity_backend_target(),
        participant_opacity_harness=ForgedDigestHarness(),
    )

    case = next(case for case in report.cases if case.capability_feature == FEATURE)
    assert not case.passed
    assert {binding.assurance_axis for binding in case.claim_bindings} == {"backend-declaration"}
    assert any(diag.code == "conformance.participant-opacity-harness-rejected" for diag in case.diagnostics)


def test_undeclared_profile_cannot_bind_backend_conformance() -> None:
    class UndeclaredProfileHarness(OpacityHarness):
        def cases(self, target):
            case = super().cases(target)[0]
            profile = load_behavioral_relation_profile("participant-opacity-baseline-v1")
            return (
                replace(
                    case,
                    profile_id=profile.profile_id,
                    profile_revision=profile.profile_revision,
                    profile_digest=profile.canonical_digest,
                ),
            )

    report = run_target_conformance(
        create_opacity_backend_target(),
        participant_opacity_harness=UndeclaredProfileHarness(),
    )

    case = next(case for case in report.cases if case.capability_feature == FEATURE)
    assert not case.passed
    assert {binding.assurance_axis for binding in case.claim_bindings} == {"backend-declaration"}
    assert any(diag.code == "conformance.participant-opacity-harness-rejected" for diag in case.diagnostics)


def test_authorized_weakening_removes_realization_and_conformance_claims() -> None:
    target = create_opacity_backend_target()
    capability = target.manifest.participant_runtime
    assert capability is not None
    weakened = tuple(
        replace(item, support_level=ParticipantFeatureSupportLevel.DISCLOSED_WEAK) if item.feature == FEATURE else item
        for item in capability.feature_support
    )
    manifest = replace(
        target.manifest,
        capabilities=replace(
            target.manifest.capabilities,
            participant_runtime=replace(capability, feature_support=weakened),
        ),
    )
    target = replace(target, manifest=manifest)

    report = run_target_conformance(target, participant_opacity_harness=OpacityHarness())

    case = next(case for case in _opacity_cases(report) if case.capability_feature == FEATURE)
    assert not case.passed
    assert case.limitations
    assert {binding.assurance_axis for binding in case.claim_bindings} == {"backend-declaration"}


def test_secret_bearing_failures_are_sanitized_before_report_projection() -> None:
    report = run_target_conformance(
        create_opacity_backend_target(),
        participant_opacity_harness=SecretFailureHarness(),
    )

    payload = backend_conformance_report_payload(report)
    rendered = str(payload)
    assert SECRET_MARKER not in rendered
    assert "input_value" not in rendered
    assert not report.passed


def test_report_validator_rejects_conformance_without_realization() -> None:
    report = run_target_conformance(
        create_opacity_backend_target(),
        participant_opacity_harness=OpacityHarness(),
    )
    case = next(case for case in _opacity_cases(report) if case.realization_owner == "backend-native")
    claims = tuple(binding for binding in case.claim_bindings if binding.assurance_axis != "backend-realization")
    forged = replace(case, claim_bindings=claims)
    forged_report = replace(report, cases=tuple(forged if item is case else item for item in report.cases))

    with pytest.raises(ValueError, match="backend conformance.*realization"):
        validate_backend_conformance_report(forged_report)


def test_adapter_probes_pass_for_every_hermetic_backend() -> None:
    """The provisioning/snapshot adapter probes must stay envelope-neutral.

    An authored ``os`` in the default probe scenario becomes an exact SEM-218
    realization requirement no hermetic in-process backend can corroborate, so
    the default probe must stay admissible on every declared envelope (issue
    #663's runner parameter stays the escape hatch for bounded backends).
    """

    for target in (create_stub_target(), create_opacity_backend_target()):
        report = run_target_conformance(target)
        cases = {case.name: case for case in report.cases}
        for name in ("target-provisioning", "target-snapshot"):
            assert cases[name].passed, (
                f"{name} must pass for an honest hermetic backend; "
                f"diagnostics: {[diag.message for diag in cases[name].diagnostics]}"
            )


def test_a_positive_declaration_adds_only_the_unexecuted_opacity_case() -> None:
    double_report = run_target_conformance(create_opacity_backend_target())
    stub_report = run_target_conformance(create_stub_target())

    assert double_report.profile == stub_report.profile
    assert double_report.passed is False
    assert stub_report.passed is False
    assert {case.name for case in double_report.cases} - {case.name for case in stub_report.cases} == {
        "participant-opacity-backend-not-executed"
    }
