"""Tests for the backend-manifest-v2 -> BackendManifest reverse adapter (issue #609).

The adapter is the inverse of ``backend_manifest_v2_model``: it reconstructs the
internal typed :class:`BackendManifest` (running its own capability validators)
from a validated ``BackendManifestV2Model`` so the plan-inspection CLI can plan
against an externally supplied manifest. Realization-envelope-bearing manifests
fail closed because a v2 payload carries only the envelope identity, not the full
digest-checked declaration the planner needs.
"""

from __future__ import annotations

import pytest
from raes_backend_protocols.manifest import (
    BackendManifestEnvelopeUnsupportedError,
    BackendManifestInvalidError,
    backend_manifest_from_v2_model,
    backend_manifest_from_v2_model_with_envelope,
    backend_manifest_v2_model,
)
from raes_backend_stubs.manifest import create_stub_manifest
from raes_contracts.contracts import BackendManifestV2Model
from raes_contracts.errors import InvalidInputError

_SECRET = "manifest-secret-sentinel-4b1d"


def test_round_trips_the_full_stub_manifest() -> None:
    original = create_stub_manifest()
    v2_model = backend_manifest_v2_model(original)

    reconstructed = backend_manifest_from_v2_model(v2_model)

    assert reconstructed == original


@pytest.mark.parametrize(
    ("with_participant_runtime", "with_observation"),
    [(False, True), (True, False), (False, False)],
)
def test_round_trips_reduced_capability_stub_manifests(with_participant_runtime: bool, with_observation: bool) -> None:
    original = create_stub_manifest(
        with_participant_runtime=with_participant_runtime,
        with_observation=with_observation,
    )

    reconstructed = backend_manifest_from_v2_model(backend_manifest_v2_model(original))

    assert reconstructed == original
    assert (reconstructed.participant_runtime is not None) == with_participant_runtime
    assert (reconstructed.observation is not None) == with_observation


def test_round_trip_reconstructs_via_serialized_payload() -> None:
    """A payload that survives JSON serialization + revalidation still round-trips."""

    original = create_stub_manifest()
    payload = backend_manifest_v2_model(original).model_dump(mode="json")

    revalidated = BackendManifestV2Model.model_validate(payload)
    reconstructed = backend_manifest_from_v2_model(revalidated)

    assert reconstructed == original


def test_envelope_bearing_manifest_fails_closed() -> None:
    stub_payload = backend_manifest_v2_model(create_stub_manifest()).model_dump(mode="json")
    stub_payload["supported_contract_versions"].append("realization-envelope-v1")
    stub_payload["realization_envelope"] = {
        "contract_id": "realization-envelope-v1",
        "envelope_id": "example-envelope",
        "schema_version": "realization-envelope/v1",
        "digest": "sha256:" + "0" * 64,
        "configuration_digest": "sha256:" + "1" * 64,
    }
    envelope_model = BackendManifestV2Model.model_validate(stub_payload)

    with pytest.raises(BackendManifestEnvelopeUnsupportedError, match="realization envelope") as caught:
        backend_manifest_from_v2_model(envelope_model)
    assert isinstance(caught.value, InvalidInputError)


def _with_rejected_evaluator_section(model: BackendManifestV2Model) -> BackendManifestV2Model:
    """Return a contract model whose evaluator section only the internal validators reject."""

    evaluator = model.capabilities.evaluator.model_copy(update={"supported_sections": [_SECRET]})
    return model.model_copy(update={"capabilities": model.capabilities.model_copy(update={"evaluator": evaluator})})


@pytest.mark.parametrize("with_envelope", [False, True], ids=["plain", "with-envelope"])
def test_capability_rejection_is_value_free_invalid_input(with_envelope: bool) -> None:
    original = create_stub_manifest(with_realization_envelope=with_envelope)
    tampered = _with_rejected_evaluator_section(backend_manifest_v2_model(original))

    with pytest.raises(BackendManifestInvalidError) as caught:
        if with_envelope:
            backend_manifest_from_v2_model_with_envelope(tampered, original.realization_envelope)
        else:
            backend_manifest_from_v2_model(tampered)

    assert isinstance(caught.value, InvalidInputError)
    assert str(caught.value) == "backend manifest was rejected by backend capability validation"
    # The cause keeps the validator detail for diagnosis; the message itself names no manifest value.
    assert isinstance(caught.value.__cause__, ValueError)
    assert _SECRET in str(caught.value.__cause__)
    assert _SECRET not in str(caught.value)
