"""SEM-231/API-407/ASR-535 backend participant-opacity assurance.

The generic conformance runner owns execution, the transcript, and every
verdict (issue #1374). An external-style harness supplies exact-cut point
resolvers, typed carriers, the transcript the backend reports, and a backend
state commitment, as a downstream backend distribution would. Every backend
double here is explicitly synthetic.
"""

from __future__ import annotations

import logging
from dataclasses import replace

import pytest
from participant_crossing_fixtures import (
    PARTICIPANT,
    admission_request,
    behavior,
    control_specification,
    evidence,
    identity,
    policy_capable_target,
)
from raes_backend_protocols.capabilities import (
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS,
    PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES,
    PARTICIPANT_RUNTIME_POLICY_FEATURES,
    ParticipantFeatureSupport,
)
from raes_backend_protocols.manifest import backend_manifest_payload
from raes_backend_protocols.participant_feature_admission import resolve_participant_feature_support
from raes_backend_stubs.stubs import StubParticipantRuntime, create_stub_target
from raes_conformance.conformance.participant_opacity_execution import _OperationFacts, _PointMeasurement
from raes_conformance.conformance.participant_opacity_probes import (
    ParticipantOpacityBackendReadback,
    ParticipantOpacityProbeCase,
    ParticipantOpacityProbeObservation,
    ParticipantOpacityProbePoint,
    ParticipantOpacityReadbackRequest,
)
from raes_conformance.conformance.participant_opacity_projection import project_observation
from raes_conformance.conformance.report import (
    backend_conformance_report_payload,
    validate_backend_conformance_report,
)
from raes_conformance.conformance.target import run_target_conformance
from raes_conformance.realization import ExecutionBasis
from raes_contracts.behavioral_relation_profiles import load_behavioral_relation_profile
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import BackendManifestV2Model
from raes_contracts.contracts.participant_crossing import ParticipantCrossingGateDisposition
from raes_contracts.errors import ConflictError
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel
from test_issue_964_participant_opacity_runtime import _OpacityResolver

FEATURE = "participant_predicate_opacity"
PROFILE_ID = "participant-opacity-runtime-reference-v1"
SECRET_MARKER = "participant-secret-never-report-965"
PROTECTED = "possible-point:runtime-reference-protected"
COMPLEMENT = "possible-point:runtime-reference-complement"
FINAL_SINK_LIMITATION = "Final-sink flow-control enforcement was disabled for this case."

UNIFORM_DENIAL = ParticipantOpacityProbeObservation(
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


class ReadbackParticipantRuntime(StubParticipantRuntime):
    """Synthetic backend double whose admitted effects are visible through readback."""

    def __init__(self) -> None:
        super().__init__()
        self.effects: list[str] = []

    def admit_action(self, request, snapshot):
        self.effects.append(request.action_instance_id)
        return super().admit_action(request, snapshot)

    def state_digest(self) -> str:
        return canonical_json_digest({"effects": list(self.effects)})


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
        disclosure_refs=("disclosure:participant-opacity:runtime-mediated-double",),
        evidence_refs=("conformance:participant-opacity-backend:observed-transcript",),
    )


def _declare_opacity(target, participant_runtime=None):
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
        participant_runtime=participant_runtime or target.participant_runtime,
    )


def create_opacity_backend_target():
    """Return stub components with only a bounded opacity declaration."""

    return _declare_opacity(create_stub_target())


def create_probe_target(participant_runtime=None):
    """Return a policy-capable synthetic target that can execute governed crossings."""

    return _declare_opacity(
        policy_capable_target(
            "participant_ingress_admission",
            "participant_egress_projection",
            "participant_transformation",
        ),
        participant_runtime or ReadbackParticipantRuntime(),
    )


class OpacityHarness:
    """External-style harness: supplies inputs, a report, and readback; never a verdict."""

    probe_set_digest = canonical_json_digest({"probe_set": "participant-opacity-backend/rev2"})
    environment_digest = canonical_json_digest({"environment": "in-process-double"})

    def protected_resolver(self):
        return _OpacityResolver()

    def complement_resolver(self):
        return _OpacityResolver(gate_overrides={"action_admission": ParticipantCrossingGateDisposition.DENY})

    def probe_identity(self):
        return identity(audience_bound=True)

    def cases(self, target) -> tuple[ParticipantOpacityProbeCase, ...]:
        del target
        profile = load_behavioral_relation_profile(PROFILE_ID)
        return (
            ParticipantOpacityProbeCase(
                name="observed-uniform-denial",
                profile_id=profile.profile_id,
                profile_revision=profile.profile_revision,
                profile_digest=profile.canonical_digest,
                protected_point=ParticipantOpacityProbePoint(PROTECTED, self.protected_resolver()),
                complement_point=ParticipantOpacityProbePoint(COMPLEMENT, self.complement_resolver()),
                participant_address=PARTICIPANT,
                episode_id="episode-1",
                behavior=behavior(),
                admission_request=admission_request(),
                identity=self.probe_identity(),
                crossing_evidence=evidence(),
                idempotency_key="opacity-probe",
                environment_digest=self.environment_digest,
                evidence_refs=("conformance:participant-opacity-backend:observed-transcript",),
                limitations=("Limited to the named finite profile and probe set.",),
                explicit_non_claims=(
                    "No universal backend opacity, proof, model check, or cross-backend equivalence.",
                ),
                # The synthetic resolvers predate the SEM-233 final-sink hook.
                enforce_final_sink_flow_control=False,
            ),
        )

    def reported_observation(self, target, case, point_ref) -> ParticipantOpacityProbeObservation:
        del target, case, point_ref
        return UNIFORM_DENIAL

    def backend_readback(self, target, case, request) -> ParticipantOpacityBackendReadback:
        del case
        return ParticipantOpacityBackendReadback(
            request=request,
            source_ref="backend-state:readback-double",
            state_digest=target.participant_runtime.state_digest(),
        )


def _opacity_case(report):
    return next(case for case in report.cases if case.capability_feature == FEATURE)


def _codes(case) -> set[str]:
    return {diag.code for diag in case.diagnostics}


def _diagnostic(case, code: str):
    return next(diag for diag in case.diagnostics if diag.code == code)


def _run(harness=None, *, participant_runtime=None, **options):
    return run_target_conformance(
        create_probe_target(participant_runtime),
        participant_opacity_harness=harness or OpacityHarness(),
        **options,
    )


def test_manifest_round_trip_declares_one_bounded_relation_feature() -> None:
    target = create_opacity_backend_target()
    declaration = next(item for item in target.manifest.participant_runtime.feature_support if item.feature == FEATURE)

    payload = backend_manifest_payload(target.manifest)
    round_trip = BackendManifestV2Model.model_validate(payload).model_dump(mode="json")

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
    declaration = next(item for item in target.manifest.participant_runtime.feature_support if item.feature == FEATURE)

    with pytest.raises(ValueError, match="evidence_refs"):
        replace(declaration, evidence_refs=())

    manifest = replace(
        target.manifest,
        supported_contract_versions=(
            target.manifest.supported_contract_versions - {"participant-crossing-occurrence-v1"}
        ),
    )
    with pytest.raises(ConflictError, match="missing required contracts"):
        resolve_participant_feature_support(
            manifest,
            FEATURE,
            required_level=ParticipantFeatureSupportLevel.BOUNDED,
        )


def test_declared_profile_without_executed_cases_is_unsupported() -> None:
    report = run_target_conformance(create_opacity_backend_target())

    case = _opacity_case(report)
    assert case.outcome == "unsupported"
    assert not case.passed
    assert not report.passed
    assert case.evidence_origin == "declaration"
    assert {binding.assurance_axis for binding in case.claim_bindings} == {"backend-declaration"}


def test_empty_harness_cannot_erase_a_positive_declaration() -> None:
    class EmptyHarness(OpacityHarness):
        def cases(self, target):
            del target
            return ()

    case = _opacity_case(_run(EmptyHarness()))

    assert not case.passed
    assert case.outcome == "unsupported"
    assert "conformance.participant-opacity-harness-empty" in _codes(case)


def test_observed_runtime_mediated_containment_keeps_only_the_declaration_claim() -> None:
    report = _run(execution_basis=ExecutionBasis.HERMETIC_LIVE)
    case = _opacity_case(report)
    profile = load_behavioral_relation_profile(PROFILE_ID)

    assert case.passed, [diag.message for diag in case.diagnostics]
    assert case.realization_owner == "runtime-mediated"
    assert case.evidence_origin == "observed-execution"
    assert case.execution_basis == "hermetic-live"
    assert case.effective_support_level == "bounded"
    assert {binding.assurance_axis for binding in case.claim_bindings} == {"backend-declaration"}
    assert case.profile_digest == profile.canonical_digest
    assert case.manifest_digest
    assert case.configuration_digest
    assert case.tool_digest
    assert case.environment_digest == OpacityHarness.environment_digest
    assert case.probe_set_digest == OpacityHarness.probe_set_digest
    assert FINAL_SINK_LIMITATION in case.limitations
    assert report.claim.relation_id == "bounded-probe-success"
    validate_backend_conformance_report(report)


def test_execution_basis_comes_from_the_run_not_a_default() -> None:
    case = _opacity_case(_run(execution_basis=ExecutionBasis.NATIVE_LIVE))

    assert case.execution_basis == "native-live"


def test_constant_transcript_without_runtime_containment_cannot_pass() -> None:
    """The issue #1374 defect: a fixed report after unrelated backend calls."""

    class UnenforcedHarness(OpacityHarness):
        def protected_resolver(self):
            return _OpacityResolver(include_claim=False)

        def complement_resolver(self):
            return _OpacityResolver(include_claim=False)

    case = _opacity_case(_run(UnenforcedHarness()))

    assert not case.passed
    assert case.realization_owner == "declaration-only"
    assert {binding.assurance_axis for binding in case.claim_bindings} == {"backend-declaration"}
    assert {
        "conformance.participant-opacity-transcript-disagreement",
        "conformance.participant-opacity-normal-form-mismatch",
        "conformance.participant-opacity-realization-unestablished",
    } <= _codes(case)


def test_fabricated_report_disagrees_with_instrumented_execution() -> None:
    class FabricatingHarness(OpacityHarness):
        def reported_observation(self, target, case, point_ref):
            del target, case
            return replace(UNIFORM_DENIAL, retry="divergent-replay") if point_ref == PROTECTED else UNIFORM_DENIAL

    case = _opacity_case(_run(FabricatingHarness()))

    assert not case.passed
    assert case.evidence_origin == "observed-execution"
    assert "retry" in _diagnostic(case, "conformance.participant-opacity-transcript-disagreement").message


def test_secret_dependent_runtime_policy_is_detected_across_points() -> None:
    class LeakingHarness(OpacityHarness):
        def protected_resolver(self):
            return _OpacityResolver(include_claim=False)

    case = _opacity_case(_run(LeakingHarness()))

    assert not case.passed
    assert "conformance.participant-opacity-observation-mismatch" in _codes(case)
    assert case.realization_owner == "declaration-only"


def test_hidden_backend_effect_is_visible_through_readback() -> None:
    class DriftingRuntime(ReadbackParticipantRuntime):
        def state_digest(self) -> str:
            self.effects.append("hidden")
            return super().state_digest()

    case = _opacity_case(_run(participant_runtime=DriftingRuntime()))

    assert not case.passed
    assert "conformance.participant-opacity-normal-form-mismatch" in _codes(case)


def test_missing_backend_readback_is_synthetic_and_cannot_pass() -> None:
    class NoReadbackHarness(OpacityHarness):
        def backend_readback(self, target, case, request):
            raise LookupError("backend readback unavailable")

    case = _opacity_case(_run(NoReadbackHarness()))

    assert not case.passed
    assert case.evidence_origin == "synthetic-model"
    assert "external_effect" in _diagnostic(case, "conformance.participant-opacity-observation-missing").message


def test_refusal_before_the_delivery_opportunity_is_not_withholding() -> None:
    class UnboundAudienceHarness(OpacityHarness):
        def probe_identity(self):
            return identity(audience_bound=False)

    case = _opacity_case(_run(UnboundAudienceHarness()))

    assert not case.passed
    assert case.evidence_origin == "synthetic-model"
    missing = _diagnostic(case, "conformance.participant-opacity-observation-missing").message
    assert "delivery" in missing
    assert "omission" in missing


def test_unexpected_runtime_error_is_not_counted_as_denial() -> None:
    class RaisingResolver(_OpacityResolver):
        def resolve(self, intent, snapshot):
            raise RuntimeError("policy store offline")

    class RaisingHarness(OpacityHarness):
        def protected_resolver(self):
            return RaisingResolver()

    case = _opacity_case(_run(RaisingHarness()))

    assert not case.passed
    assert case.evidence_origin == "synthetic-model"
    assert {
        "conformance.participant-opacity-probe-rejected",
        "conformance.participant-opacity-observation-missing",
    } <= _codes(case)


def test_swapped_points_do_not_rejoin_the_runtime_support() -> None:
    class SwappedHarness(OpacityHarness):
        def cases(self, target):
            case = super().cases(target)[0]
            return (
                replace(
                    case,
                    protected_point=replace(case.protected_point, point_ref=COMPLEMENT),
                    complement_point=replace(case.complement_point, point_ref=PROTECTED),
                ),
            )

    case = _opacity_case(_run(SwappedHarness()))

    assert not case.passed
    assert case.realization_owner == "declaration-only"
    assert "conformance.participant-opacity-realization-unestablished" in _codes(case)


def test_final_sink_enforcement_is_not_silently_disabled() -> None:
    class EnforcingHarness(OpacityHarness):
        def cases(self, target):
            return (replace(super().cases(target)[0], enforce_final_sink_flow_control=True),)

    case = _opacity_case(_run(EnforcingHarness()))

    assert not case.passed
    assert FINAL_SINK_LIMITATION not in case.limitations
    assert case.evidence_origin == "synthetic-model"
    assert _diagnostic(case, "conformance.participant-opacity-probe-rejected").message.startswith("execution:")


def test_configuration_digest_is_derived_from_the_actual_configuration() -> None:
    baseline = _opacity_case(_run()).configuration_digest

    class OtherSupportHarness(OpacityHarness):
        def complement_resolver(self):
            resolver = super().complement_resolver()
            resolver.support = resolver.support.model_copy(
                update={"predicate_negative_case_ref": "possible-point:other"}
            )
            return resolver

    assert _opacity_case(_run(OtherSupportHarness())).configuration_digest != baseline


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

    case = _opacity_case(_run(UndeclaredProfileHarness()))

    assert not case.passed
    assert {binding.assurance_axis for binding in case.claim_bindings} == {"backend-declaration"}
    assert "conformance.participant-opacity-harness-rejected" in _codes(case)


def test_authorized_weakening_cannot_execute_a_bounded_probe() -> None:
    target = create_probe_target()
    capability = target.manifest.participant_runtime
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

    report = run_target_conformance(replace(target, manifest=manifest), participant_opacity_harness=OpacityHarness())

    case = _opacity_case(report)
    assert not case.passed
    assert case.limitations
    assert {binding.assurance_axis for binding in case.claim_bindings} == {"backend-declaration"}


def test_secret_bearing_failures_are_sanitized_before_report_projection() -> None:
    class SecretResolver(_OpacityResolver):
        def resolve(self, intent, snapshot):
            raise ValueError(f"rejected {SECRET_MARKER}")

    class SecretHarness(OpacityHarness):
        def protected_resolver(self):
            return SecretResolver()

        def reported_observation(self, target, case, point_ref):
            raise ValueError(f"report {SECRET_MARKER}")

    report = _run(SecretHarness())

    rendered = str(backend_conformance_report_payload(report))
    assert SECRET_MARKER not in rendered
    assert "input_value" not in rendered
    assert not report.passed


def test_harness_failure_is_logged_without_foreign_values(caplog: pytest.LogCaptureFixture) -> None:
    class SecretReportHarness(OpacityHarness):
        def reported_observation(self, target, case, point_ref):
            raise ValueError(f"report {SECRET_MARKER}")

    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        _run(SecretReportHarness())

    records = [record for record in caplog.records if record.name.endswith("participant_opacity_probes")]
    assert records
    for record in records:
        assert SECRET_MARKER not in record.getMessage()
        assert SECRET_MARKER not in (record.exc_text or "")
        assert "ForeignCodeFailure" in (record.exc_text or "")
        assert "ValueError" not in (record.exc_text or "")


def test_validator_refuses_realization_without_native_observed_evidence() -> None:
    report = _run()
    case = _opacity_case(report)
    declaration = case.claim_bindings[0]
    realization = declaration.model_copy(
        update={
            "assurance_axis": "backend-realization",
            "assurance_status": "realized",
            "evidence_scope": "finite",
            "quantifier_scope": "finite-cases",
        }
    )
    forged = replace(case, claim_bindings=(declaration, realization))

    def forged_report(item):
        return replace(report, cases=tuple(item if entry is case else entry for entry in report.cases))

    runtime_mediated = forged_report(forged)
    synthetic_native = forged_report(
        replace(forged, realization_owner="backend-native", evidence_origin="synthetic-model")
    )
    with pytest.raises(ValueError, match="backend realization claim requires backend-native"):
        validate_backend_conformance_report(runtime_mediated)
    with pytest.raises(ValueError, match="backend realization claim requires observed-execution"):
        validate_backend_conformance_report(synthetic_native)


def _facts(*stages: str, operation_id: str | None = "op-1", first_order: int = 1, **values) -> _OperationFacts:
    records = tuple(
        {
            "event_id": f"event-{first_order + index}",
            "predecessor_event_refs": [f"event-{first_order + index - 1}"] if index else [],
            "occurrence": {"stage": stage, "effective_order": first_order + index},
        }
        for index, stage in enumerate(stages)
    )
    return _OperationFacts(records=records, backend_calls=(), operation_id=operation_id, **values)


def test_projection_refuses_to_promote_divergent_replay_or_reordered_stages() -> None:
    measurement = _PointMeasurement(
        point_ref=PROTECTED,
        ingress=_facts("decided", "requested", terminal_state="failed"),
        replay=_facts("requested", operation_id="op-2", terminal_state="failed"),
        egress=_facts("requested", "decided", "delivered", operation_id=None, result="view"),
        readback_before=None,
        readback_after=None,
        history_valid=True,
        opacity_supports=(),
        failures=(),
    )

    observed = project_observation(measurement)

    assert observed["retry"] == "divergent-replay"
    assert str(observed["logical_order"]).startswith("order:")
    assert observed["logical_timing"] == "logical-bucket:2-1-3"
    assert observed["policy_release_effect"] == "released"
    assert observed["delivery"] == "delivered"
    assert observed["omission"] == "not-recorded"
    assert observed["payload_released"] is True
    assert observed["external_effect"] is None


def test_adapter_probes_pass_for_every_hermetic_backend() -> None:
    """The provisioning/snapshot adapter probes must stay envelope-neutral."""

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


@pytest.mark.parametrize("state", ["indeterminate", "running", "accepted"])
def test_projection_never_counts_an_unfinished_action_as_denial(state: str) -> None:
    measurement = _PointMeasurement(
        point_ref=PROTECTED,
        ingress=_facts("requested", "decided", terminal_state=state),
        replay=None,
        egress=None,
        readback_before=None,
        readback_after=None,
        history_valid=True,
        opacity_supports=(),
        failures=(),
    )

    observed = project_observation(measurement)

    assert observed["decision"] == observed["failure"] == observed["action_availability"] == "indeterminate"
    assert observed["logical_order"] is None
    assert observed["retry"] is None


def test_projection_rejects_a_broken_causal_chain_with_contained_stages() -> None:
    def measurement(egress: _OperationFacts) -> _PointMeasurement:
        return _PointMeasurement(
            point_ref=PROTECTED,
            ingress=_facts("requested", "decided", terminal_state="failed"),
            replay=_facts(operation_id="op-1"),
            egress=egress,
            readback_before="sha256:" + "0" * 64,
            readback_after="sha256:" + "1" * 64,
            history_valid=True,
            opacity_supports=(),
            failures=(),
        )

    egress = _facts("requested", "decided", "delivery-attempted", operation_id=None, first_order=3, result="refused")
    broken = replace(
        egress,
        records=(
            egress.records[0],
            {**egress.records[1], "predecessor_event_refs": ["event-unknown"]},
            egress.records[2],
        ),
    )

    intact = project_observation(measurement(egress))
    observed = project_observation(measurement(broken))

    assert intact["logical_order"] == "stable-causal-order"
    assert observed["logical_timing"] == "logical-bucket:contained"
    assert str(observed["logical_order"]).startswith("order:")
    assert observed["delivery"] is None
    assert observed["external_effect"] == "observed"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"complement_point": ParticipantOpacityProbePoint(PROTECTED, None)}, "distinct possible points"),
        ({"idempotency_key": ""}, "idempotency key"),
        ({"environment_digest": "environment"}, "environment digest"),
    ],
)
def test_probe_case_rejects_ambiguous_inputs(change: dict[str, object], message: str) -> None:
    case = OpacityHarness().cases(None)[0]

    with pytest.raises(ValueError, match=message):
        replace(case, **change)


def test_untyped_report_and_readback_cannot_supply_evidence() -> None:
    class UntypedHarness(OpacityHarness):
        def reported_observation(self, target, case, point_ref):
            return UNIFORM_DENIAL.__dict__.copy()

        def backend_readback(self, target, case, request):
            return target.participant_runtime.state_digest()

    case = _opacity_case(_run(UntypedHarness()))

    assert not case.passed
    assert case.evidence_origin == "synthetic-model"
    messages = [diag.message for diag in case.diagnostics if diag.code.endswith("probe-rejected")]
    assert any(message.startswith("reported transcript:") for message in messages)
    assert any(message.startswith("backend readback:") for message in messages)
    request = ParticipantOpacityReadbackRequest("collection", "case", PROTECTED, "before")
    digest = canonical_json_digest({})
    with pytest.raises(ValueError, match="sha256"):
        ParticipantOpacityBackendReadback(request, "backend-state:double", "not-a-digest")
    with pytest.raises(ValueError, match="state source"):
        ParticipantOpacityBackendReadback(request, "", digest)
    with pytest.raises(ValueError, match="runner-issued"):
        ParticipantOpacityBackendReadback("request", "backend-state:double", digest)


def test_committed_history_that_no_longer_validates_cannot_establish_mediation() -> None:
    class StaleContextResolver(_OpacityResolver):
        stale = False

        def validation_context(self, snapshot, participant_address):
            context = super().validation_context(snapshot, participant_address)
            return replace(context, known_subjects=()) if self.stale else context

    class StaleContextHarness(OpacityHarness):
        def __init__(self) -> None:
            self.resolver = StaleContextResolver()
            self.readbacks = 0

        def protected_resolver(self):
            return self.resolver

        def backend_readback(self, target, case, request):
            # The second readback is the last step before the runner validates
            # history; the trusted context no longer admits the committed facts.
            self.readbacks += 1
            self.resolver.stale = self.readbacks == 2
            return super().backend_readback(target, case, request)

    case = _opacity_case(_run(StaleContextHarness()))

    assert not case.passed
    assert case.realization_owner == "declaration-only"
    assert any(diag.message.startswith("committed history:") for diag in case.diagnostics)


def test_cached_backend_readback_cannot_report_no_effect() -> None:
    class CachingHarness(OpacityHarness):
        cached = None

        def backend_readback(self, target, case, request):
            if self.cached is None:
                self.cached = super().backend_readback(target, case, request)
            return self.cached

    case = _opacity_case(_run(CachingHarness()))

    assert not case.passed
    assert case.evidence_origin == "synthetic-model"
    assert "external_effect" in _diagnostic(case, "conformance.participant-opacity-observation-missing").message


def test_wrong_point_backend_readback_is_rejected() -> None:
    class WrongPointHarness(OpacityHarness):
        def backend_readback(self, target, case, request):
            other = COMPLEMENT if request.point_ref == PROTECTED else PROTECTED
            return super().backend_readback(target, case, replace(request, point_ref=other))

    case = _opacity_case(_run(WrongPointHarness()))

    assert not case.passed
    assert case.evidence_origin == "synthetic-model"
    assert any(diag.message.startswith("backend readback:") for diag in case.diagnostics)


def test_readback_from_different_state_sources_is_not_compared() -> None:
    class SourceSwitchingHarness(OpacityHarness):
        def backend_readback(self, target, case, request):
            readback = super().backend_readback(target, case, request)
            return replace(readback, source_ref=f"backend-state:{request.phase}")

    case = _opacity_case(_run(SourceSwitchingHarness()))

    assert not case.passed
    assert case.evidence_origin == "synthetic-model"
    assert "external_effect" in _diagnostic(case, "conformance.participant-opacity-observation-missing").message


def test_configuration_digest_commits_behavior_specification_contents() -> None:
    specification = control_specification()

    def with_specification(value):
        class SpecificationHarness(OpacityHarness):
            def cases(self, target):
                case = super().cases(target)[0]
                return (replace(case, behavior_specifications={PARTICIPANT: value}),)

        return _opacity_case(_run(SpecificationHarness())).configuration_digest

    changed = replace(specification, semantic_version="changed-under-the-same-key")

    assert with_specification(specification) != with_specification(changed)
