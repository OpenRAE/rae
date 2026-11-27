"""Issue #1551: target conformance validates the snapshot payload the API publishes.

The ``target-snapshot`` case used to validate a hand-built payload that dropped
``realization_envelope`` and ``realization_provenance``. It now validates the
payload the control plane's ``/snapshot`` route emits, so an invalid published
realization carrier fails the case instead of passing unseen.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_conformance.conformance import run_target_conformance, target_probes
from raes_contracts.contracts import RuntimeSnapshotEnvelopeModel
from raes_contracts.realization_envelope import RealizationEnvelopeIdentityModel
from raes_contracts.runtime_state import RuntimeSnapshot, RuntimeSnapshotEnvelope
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api_models import _snapshot_model


def _corrupt_envelope(snapshot: RuntimeSnapshot) -> RuntimeSnapshot:
    identity = snapshot.realization_envelope
    if identity is None:
        return snapshot
    bad = RealizationEnvelopeIdentityModel.model_construct(**{**identity.model_dump(), "digest": "sha256:bad"})
    return replace(snapshot, realization_envelope=bad)


def _corrupt_provenance(snapshot: RuntimeSnapshot) -> RuntimeSnapshot:
    if not snapshot.realization_provenance:
        return snapshot
    first, *rest = snapshot.realization_provenance
    return replace(snapshot, realization_provenance=(replace(first, field_path=""), *rest))


def _snapshot_case(report):
    return next(case for case in report.cases if case.name == "target-snapshot")


@pytest.mark.parametrize(
    ("corrupt", "carrier"),
    [
        pytest.param(_corrupt_envelope, "realization_envelope", id="envelope"),
        pytest.param(_corrupt_provenance, "realization_provenance", id="provenance"),
    ],
)
def test_target_snapshot_rejects_invalid_published_carrier(monkeypatch, corrupt, carrier):
    real_get_snapshot = RuntimeControlPlane.get_snapshot
    corrupted: list[RuntimeSnapshot] = []

    def corrupting_get_snapshot(self: RuntimeControlPlane) -> RuntimeSnapshotEnvelope:
        envelope = real_get_snapshot(self)
        snapshot = corrupt(envelope.snapshot)
        if snapshot is not envelope.snapshot:
            corrupted.append(snapshot)
        return replace(envelope, snapshot=snapshot)

    monkeypatch.setattr(RuntimeControlPlane, "get_snapshot", corrupting_get_snapshot)

    report = run_target_conformance(create_stub_target())

    case = _snapshot_case(report)
    assert case.passed is False
    schema_failures = [diag for diag in case.diagnostics if diag.code == "conformance.schema-invalid"]
    assert any(carrier in diag.message for diag in schema_failures)
    assert report.passed is False
    assert corrupted, f"the stub run published no {carrier} to corrupt"


def test_target_snapshot_validates_the_route_payload(monkeypatch):
    real_get_snapshot = RuntimeControlPlane.get_snapshot
    real_validate = target_probes._validate_payload
    envelopes: list[RuntimeSnapshotEnvelope] = []
    validated: list[tuple[object, RuntimeSnapshotEnvelope | None]] = []

    def recording_get_snapshot(self: RuntimeControlPlane) -> RuntimeSnapshotEnvelope:
        envelope = real_get_snapshot(self)
        envelopes.append(envelope)
        return envelope

    def recording_validate(contract_name: str, payload: object):
        if contract_name == "runtime-snapshot-v1":
            validated.append((payload, envelopes[-1] if envelopes else None))
        return real_validate(contract_name, payload)

    monkeypatch.setattr(RuntimeControlPlane, "get_snapshot", recording_get_snapshot)
    monkeypatch.setattr(target_probes, "_validate_payload", recording_validate)

    report = run_target_conformance(create_stub_target())

    assert _snapshot_case(report).passed is True
    assert len(validated) == 1
    payload, envelope = validated[0]
    assert envelope is not None
    published = RuntimeSnapshotEnvelopeModel.model_validate(payload).model_dump(mode="json")
    assert published == _snapshot_model(envelope).model_dump(mode="json")
    assert published["realization_envelope"] is not None
    assert published["realization_provenance"]
