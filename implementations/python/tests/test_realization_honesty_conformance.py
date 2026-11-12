"""ASR-519 falsification tests for realization-honesty conformance."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_stubs.stubs import StubProvisioner
from raes_conformance.conformance import (
    BackendCapabilityProfile,
    backend_conformance_report_payload,
    run_target_conformance,
)
from raes_conformance.realization import (
    ExecutionBasis,
    ExpectedRealizationObservation,
    RealizationProbeEvidence,
    RealizationProbeRequest,
    RealizationTransformation,
)
from raes_contracts.realization_envelope import (
    BackendRealizationEnvelopeModel,
    ConcernDisposition,
    EnvelopeBinding,
    EnvelopeScope,
    ExactDomain,
    ObservationStrength,
    Posture,
    RealizationConcern,
    RealizationEnvelopeModel,
    realization_envelope_digest,
)
from raes_contracts.realization_observation import RealizationObservation
from raes_runtime.registry import RuntimeTarget
from t2_envelope_manifests import VIRTUAL_MACHINE_ENVELOPE, provisioning_only_manifest, published_envelope

# Published virtual-machine envelope fixtures for two realizer configurations.
_GENERIC_ENVELOPE = VIRTUAL_MACHINE_ENVELOPE
_APPLIANCE_ENVELOPE = "libvirt-qemu/techvault-appliance-v1.json"
_TARGET_NAME = "honesty-target"

_SCENARIO = """\
name: honesty
realization:
  constraints:
    - field_pointer: /nodes/vm
      concern: compute-substrate
      posture: exact
      domain: {kind: exact, value: virtual-machine}
nodes:
  vm:
    type: compute
"""


def _constructive_expression() -> RealizationEnvelopeModel:
    return RealizationEnvelopeModel(
        id="honesty.expression.v1",
        scope=EnvelopeScope.SCENARIO,
        domains={
            "name": ExactDomain(value="honesty"),
            "type": ExactDomain(value="compute"),
        },
        bindings=[
            EnvelopeBinding(path="name", scope=EnvelopeScope.SCENARIO, posture=Posture.EXACT, domain="name"),
            EnvelopeBinding(path="nodes.vm.type", scope=EnvelopeScope.NODE, posture=Posture.EXACT, domain="type"),
        ],
    )


def _constructive_envelope(
    fixture: str = _GENERIC_ENVELOPE,
    strength: ObservationStrength = ObservationStrength.DRIVER_REPORTED,
) -> BackendRealizationEnvelopeModel:
    base = published_envelope(fixture)
    payload = base.model_dump(mode="json")
    payload["id"] = f"{base.id}.honesty-test"
    payload["expression"] = _constructive_expression().model_dump(mode="json")
    for disclosure in payload["concerns"]:
        if disclosure["concern"] == RealizationConcern.TOPOLOGY.value:
            disclosure.update(
                disposition=ConcernDisposition.REALIZED.value,
                observation_strength=strength.value,
                mechanism="test-addressed-observer",
                transformations=[],
            )
        elif disclosure["concern"] == RealizationConcern.COMPUTE_SUBSTRATE.value:
            disclosure.update(
                disposition=ConcernDisposition.REALIZED.value,
                observation_strength=ObservationStrength.DAEMON_OBSERVED.value,
                mechanism="virtual-machine",
                transformations=[],
            )
        else:
            disclosure.update(
                disposition=ConcernDisposition.UNSUPPORTED.value,
                observation_strength=ObservationStrength.NONE.value,
                mechanism=None,
                transformations=[],
            )
    payload["digest"] = realization_envelope_digest(payload)
    return BackendRealizationEnvelopeModel.model_validate(payload)


def _manifest_with_envelope(envelope: BackendRealizationEnvelopeModel) -> BackendManifest:
    return provisioning_only_manifest(envelope)


def _target(envelope: BackendRealizationEnvelopeModel | None = None) -> RuntimeTarget:
    selected = envelope or _constructive_envelope()
    return RuntimeTarget(
        name=_TARGET_NAME,
        manifest=_manifest_with_envelope(selected),
        provisioner=StubProvisioner(realization_envelope=selected),
    )


def _fixture_target(fixture: str) -> RuntimeTarget:
    return RuntimeTarget(
        name=_TARGET_NAME,
        manifest=provisioning_only_manifest(published_envelope(fixture)),
        provisioner=StubProvisioner(),
    )


class _ScriptedHarness:
    def __init__(
        self,
        fault: str | None = None,
        observation_strength: ObservationStrength = ObservationStrength.DRIVER_REPORTED,
    ) -> None:
        self.fault = fault
        self.observation_strength = observation_strength
        self.calls: list[RealizationProbeRequest] = []

    def execute(self, request: RealizationProbeRequest) -> RealizationProbeEvidence:
        self.calls.append(request)
        if request.negative:
            return self._negative(request)
        return self._positive(request)

    def _positive(self, request: RealizationProbeRequest) -> RealizationProbeEvidence:
        operations = tuple(operation.address for operation in request.provisioning_plan.actionable_operations)
        expected = tuple(
            ExpectedRealizationObservation(
                address=address,
                field_path="exists",
                concern=RealizationConcern.TOPOLOGY,
                value=True,
            )
            for address in operations
        )
        observations = tuple(
            RealizationObservation(
                address=item.address,
                field_path=item.field_path,
                concern=item.concern,
                source=self.observation_strength,
                value=item.value,
                operation_id=item.address,
                probe_digest=request.probe_digest,
                envelope_digest=request.envelope_digest,
                configuration_digest=request.configuration_digest,
                observer_version=request.observer_version,
                sequence=2,
                origin="observed",
                binding_verified=True,
            )
            for item in expected
        )
        evidence = RealizationProbeEvidence(
            accepted=True,
            accounted_operations=operations,
            changed_addresses=operations,
            expected_observations=expected,
            observations=observations,
            driver_invoked=True,
            native_mutated=True,
            portable_state_before="sha256:" + "0" * 64,
            portable_state_after="sha256:" + "1" * 64,
            native_state_before="sha256:" + "2" * 64,
            native_state_after="sha256:" + "3" * 64,
            baseline_sequence=1,
            cleanup_verified=True,
        )
        fault = self.fault
        if fault == "missing-operation":
            return replace(evidence, accounted_operations=())
        if fault == "schema-valid-noop":
            return replace(evidence, portable_state_after=evidence.portable_state_before)
        if fault == "missing-disclosure":
            return replace(evidence, expected_observations=(), observations=())
        if fault == "missing-observation":
            return replace(evidence, observations=())
        if fault == "stale-observation":
            return replace(evidence, observations=tuple(replace(item, sequence=1) for item in observations))
        if fault == "planned-as-observed":
            return replace(evidence, observations=tuple(replace(item, origin="planned") for item in observations))
        if fault == "fabricated-observation":
            return replace(
                evidence,
                observations=tuple(replace(item, binding_verified=False) for item in observations),
            )
        if fault in {"silent-transform", "resource-clamp", "image-substitution"}:
            kind = {
                "silent-transform": "default-substitution",
                "resource-clamp": "bounded-normalization",
                "image-substitution": "image-substitution",
            }[fault]
            concern = (
                RealizationConcern.IMAGE if fault == "image-substitution" else RealizationConcern.RESOURCE_ALLOCATION
            )
            return replace(
                evidence,
                transformations=(
                    RealizationTransformation(
                        address=operations[0], concern=concern, kind=kind, disclosed=fault != "silent-transform"
                    ),
                ),
            )
        if fault == "cleanup":
            return replace(evidence, cleanup_verified=False)
        if fault == "residual":
            return replace(evidence, residual_state=(operations[0],))
        return evidence

    def _negative(self, request: RealizationProbeRequest) -> RealizationProbeEvidence:
        evidence = RealizationProbeEvidence(
            accepted=False,
            driver_invoked=False,
            native_mutated=False,
            portable_state_before="sha256:" + "4" * 64,
            portable_state_after="sha256:" + "4" * 64,
            native_state_before="sha256:" + "5" * 64,
            native_state_after="sha256:" + "5" * 64,
            cleanup_verified=True,
        )
        if self.fault == "negative-driver":
            return replace(evidence, driver_invoked=True)
        if self.fault == "negative-native":
            return replace(evidence, native_mutated=True)
        if self.fault == "negative-portable-state":
            return replace(evidence, portable_state_after="sha256:" + "6" * 64)
        if self.fault == "negative-native-state":
            return replace(evidence, native_state_after="sha256:" + "7" * 64)
        if self.fault == "negative-cleanup":
            return replace(evidence, cleanup_verified=False, residual_state=("node.vm",))
        return evidence


def _run(
    harness: _ScriptedHarness,
    envelope: BackendRealizationEnvelopeModel | None = None,
    **kwargs,
):
    return run_target_conformance(
        _target(envelope),
        reference_scenario=_SCENARIO,
        realization_harness=harness,
        execution_basis=ExecutionBasis.HERMETIC_LIVE,
        **kwargs,
    )


def test_constructive_envelope_runs_positive_and_negative_honesty_probes() -> None:
    harness = _ScriptedHarness()

    report = _run(harness)

    assert report.passed is True, [diag.code for case in report.cases for diag in case.diagnostics]
    honesty = [case for case in report.cases if case.probe_kind is not None]
    assert {case.probe_kind for case in honesty} == {"positive", "negative"}
    assert all(case.execution_basis == "hermetic-live" for case in honesty)
    assert all(case.envelope_digest == _constructive_envelope().digest for case in honesty)
    assert all(case.probe_set_digest for case in honesty)
    assert report.native_conformance is False
    assert report.claim.left_carrier_ref != f"backend-target:{_TARGET_NAME}"
    assert _constructive_envelope().configuration.mode in report.claim.left_carrier_ref


@pytest.mark.parametrize(
    "required_strength",
    [ObservationStrength.DAEMON_OBSERVED, ObservationStrength.GUEST_OBSERVED],
)
def test_positive_probe_enforces_declared_daemon_or_guest_strength(
    required_strength: ObservationStrength,
) -> None:
    envelope = _constructive_envelope(strength=required_strength)

    weak = _run(_ScriptedHarness(), envelope=envelope)
    strong = _run(
        _ScriptedHarness(observation_strength=required_strength),
        envelope=envelope,
    )

    assert weak.passed is False
    assert "conformance.observation-strength-insufficient" in {
        diag.code for case in weak.cases for diag in case.diagnostics
    }
    assert strong.passed is True


@pytest.mark.parametrize(
    "required,actual",
    [
        (ObservationStrength.DAEMON_OBSERVED, ObservationStrength.GUEST_OBSERVED),
        (ObservationStrength.GUEST_OBSERVED, ObservationStrength.DAEMON_OBSERVED),
        (ObservationStrength.DRIVER_REPORTED, ObservationStrength.DAEMON_OBSERVED),
    ],
)
def test_conformance_rejects_different_source_even_when_formerly_ranked_stronger(required, actual):
    report = _run(_ScriptedHarness(observation_strength=actual), envelope=_constructive_envelope(strength=required))
    assert not report.passed
    assert "conformance.observation-strength-insufficient" in {
        diagnostic.code for case in report.cases for diagnostic in case.diagnostics
    }


@pytest.mark.parametrize(
    ("fault", "code"),
    [
        ("missing-operation", "conformance.operation-accounting-incomplete"),
        ("schema-valid-noop", "conformance.positive-portable-state-unchanged"),
        ("missing-disclosure", "conformance.observation-inventory-incomplete"),
        ("missing-observation", "conformance.observation-missing"),
        ("stale-observation", "conformance.observation-stale"),
        ("planned-as-observed", "conformance.observation-not-independent"),
        ("fabricated-observation", "conformance.observation-binding-invalid"),
        ("silent-transform", "conformance.transformation-undisclosed"),
        ("resource-clamp", "conformance.transformation-unverified"),
        ("image-substitution", "conformance.transformation-unverified"),
        ("cleanup", "conformance.cleanup-unverified"),
        ("residual", "conformance.residual-state"),
    ],
)
def test_dishonest_positive_behaviors_fail_for_stable_reason(fault: str, code: str) -> None:
    report = _run(_ScriptedHarness(fault))

    assert report.passed is False
    assert code in {diag.code for case in report.cases for diag in case.diagnostics}


@pytest.mark.parametrize(
    ("fault", "code"),
    [
        ("negative-driver", "conformance.negative-driver-invoked"),
        ("negative-native", "conformance.negative-native-mutation"),
        ("negative-portable-state", "conformance.negative-portable-state-mutated"),
        ("negative-native-state", "conformance.negative-native-state-mutated"),
        ("negative-cleanup", "conformance.cleanup-unverified"),
    ],
)
def test_negative_probe_requires_rejection_without_mutation(fault: str, code: str) -> None:
    report = _run(_ScriptedHarness(fault))

    assert report.passed is False
    assert code in {diag.code for case in report.cases for diag in case.diagnostics}


def test_open_published_envelope_fails_as_non_constructive_without_fallback() -> None:
    harness = _ScriptedHarness()
    report = run_target_conformance(
        _fixture_target(_GENERIC_ENVELOPE),
        reference_scenario=_SCENARIO,
        realization_harness=harness,
        execution_basis=ExecutionBasis.HERMETIC_LIVE,
    )

    assert report.passed is False
    case = next(case for case in report.cases if case.name == "realization-envelope-constructive")
    assert case.outcome == "unsupported"
    assert not harness.calls


@pytest.mark.parametrize(
    ("target_fixture", "wrong_fixture"),
    [
        (_GENERIC_ENVELOPE, _APPLIANCE_ENVELOPE),
        (_APPLIANCE_ENVELOPE, _GENERIC_ENVELOPE),
    ],
)
def test_configuration_modes_refuse_wrong_configuration_envelope_before_execution(
    target_fixture: str,
    wrong_fixture: str,
) -> None:
    harness = _ScriptedHarness()
    report = run_target_conformance(
        _fixture_target(target_fixture),
        realization_harness=harness,
        realization_envelope=published_envelope(wrong_fixture),
        execution_basis=ExecutionBasis.HERMETIC_LIVE,
    )

    assert report.passed is False
    assert not harness.calls
    assert "conformance.realization-envelope-mismatch" in {
        diag.code for case in report.cases for diag in case.diagnostics
    }


def test_only_native_live_can_support_native_conformance() -> None:
    hermetic = _run(_ScriptedHarness(), native_conformance=True)
    native = run_target_conformance(
        _target(),
        reference_scenario=_SCENARIO,
        realization_harness=_ScriptedHarness(),
        execution_basis=ExecutionBasis.NATIVE_LIVE,
        native_conformance=True,
    )

    assert hermetic.passed is False
    assert hermetic.native_conformance is False
    assert native.passed is True
    assert native.native_conformance is True


def test_failed_report_cannot_claim_native_conformance() -> None:
    report = run_target_conformance(
        _target(),
        profile=BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE,
        reference_scenario=_SCENARIO,
        realization_harness=_ScriptedHarness(),
        execution_basis=ExecutionBasis.NATIVE_LIVE,
        native_conformance=True,
    )

    assert report.passed is False
    assert report.native_conformance is False


def test_report_payload_enumerates_probe_evidence_without_raw_values() -> None:
    report = _run(_ScriptedHarness())

    payload = backend_conformance_report_payload(report)
    honesty = [case for case in payload["cases"] if case["probe_kind"] is not None]

    assert honesty
    assert all(case["outcome"] == "passed" for case in honesty)
    assert all(case["probe_digest"].startswith("sha256:") for case in honesty)
    assert all("expected_operations" in case for case in honesty)
    assert all("cleanup_verified" in case for case in honesty)
    assert "honesty" not in json.dumps(honesty)
