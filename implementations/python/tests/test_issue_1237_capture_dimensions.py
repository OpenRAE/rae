"""Independent dimension oracles prevent partially implemented capture terms."""

from __future__ import annotations

from dataclasses import fields, replace

import pytest
from raes_backend_protocols.capabilities import ObservationCaptureOffer
from raes_backend_protocols.manifest import backend_manifest_from_v2_model, backend_manifest_v2_model
from raes_contracts.contracts import ObservationCaptureOfferModel
from raes_processor.capture_admission import (
    CaptureDemand,
    capture_admission_diagnostics,
    compile_capture_spec_demands,
    compile_scenario_capture_demands,
)
from test_issue_1112_capture_admission import _capture_scenario, _evidence_bundle, _manifest_with_offers, _offer

# Each row independently specifies a demanded value, a rejecting offer value,
# and the externally observable diagnostic. Every governed dimension needs one.
DIMENSION_CASES = {
    "output_contract": (
        "participant-behavior-history-event-stream-v1",
        "experiment-evidence-record-v1",
        "output-contract-mismatch",
    ),
    "field_selectors": (("/required",), ("/different",), "field-selector-missing"),
    "artifact_roles": (("observation",), frozenset({"other"}), "artifact-role-mismatch"),
    "media_types": (("application/jsonl",), frozenset({"application/json"}), "media-type-mismatch"),
    "capture_kind": ("log", "trace", "capture-kind-mismatch"),
    "source_classes": (("participant_action",), frozenset({"other"}), "source-class-mismatch"),
    "source_refs": (("source-a",), frozenset({"source-b"}), "source-ref-mismatch"),
    "scopes": (("run",), frozenset({"task"}), "scope-mismatch"),
    "scope_refs": (("nodes.vm",), frozenset({"nodes.other"}), "scope-ref-mismatch"),
    "channel_kinds": (("backend-log",), frozenset({"packet-capture"}), "channel-mismatch"),
    "channel_refs": (("channel-a",), frozenset({"channel-b"}), "channel-ref-mismatch"),
    "window_kinds": (("task",), frozenset({"run"}), "window-mismatch"),
    "integrity_modes": (("checksum",), frozenset({"signature"}), "integrity-mismatch"),
    "sensitivity": ("plain", "restricted", "sensitivity-mismatch"),
    "availability": (None, "unavailable", "availability-insufficient"),
    "fidelity": (None, "lossy", "fidelity-insufficient"),
    "disclosure": ("redacted", "full", "disclosure-insufficient"),
    "retention_policy_refs": (("study_lifetime",), frozenset({"run_lifetime"}), "retention-mismatch"),
    "export_policy": ("available", "unavailable", "export-policy-mismatch"),
    "redaction_policy": ("redact_sensitive", None, "redaction-policy-mismatch"),
}


def test_dimension_registry_covers_every_closed_model_and_behavior_case() -> None:
    from raes_contracts.capture_dimensions import CAPTURE_DIMENSIONS

    names = {dimension.name for dimension in CAPTURE_DIMENSIONS}
    assert names == set(DIMENSION_CASES)
    assert names | {"offer_id", "offer_version"} == set(ObservationCaptureOfferModel.model_fields)
    assert names | {"offer_id", "offer_version"} == {item.name for item in fields(ObservationCaptureOffer)}
    assert names - {"availability", "fidelity"} == {item.name for item in fields(CaptureDemand)} - {
        "demand_id",
        "address",
        "capture_spec_ref",
        "capture_requirement_ref",
    }


@pytest.mark.parametrize("name", DIMENSION_CASES)
def test_each_dimension_has_a_round_trip_and_rejection_diagnostic(name: str) -> None:
    required, unsupported, failure = DIMENSION_CASES[name]
    demand = compile_scenario_capture_demands(_capture_scenario())[0]
    if required is not None:
        demand = replace(demand, **{name: required})
    offer = _offer(**{name: unsupported})
    manifest = _manifest_with_offers(offer)
    reconstructed = backend_manifest_from_v2_model(backend_manifest_v2_model(manifest))
    assert reconstructed == manifest
    diagnostics = capture_admission_diagnostics((demand,), reconstructed.observation)
    assert any(item.code == f"capture.{failure}" and item.address == demand.address for item in diagnostics)


def test_partial_projection_overrides_fail_closed() -> None:
    from raes_contracts.capture_dimensions import project_capture_dimensions

    requirement = _capture_scenario().evidence_requirements["attacker-action-log"]
    with pytest.raises(ValueError, match="projection"):
        project_capture_dimensions(requirement, source="sdl", overrides={"unknown_dimension": "value"})


@pytest.mark.parametrize("source", ["sdl", "capture"])
def test_every_dimension_has_an_independent_projection_oracle(source: str) -> None:
    from raes_contracts.capture_dimensions import CAPTURE_DIMENSIONS

    expected = {
        "output_contract": "participant-behavior-history-event-stream-v1",
        "field_selectors": ("/0", "/0/action_contract_address"),
        "artifact_roles": ("observation",),
        "media_types": ("application/json",),
        "capture_kind": "log",
        "source_classes": ("participant_action",),
        "source_refs": (),
        "scopes": ("run",),
        "scope_refs": (),
        "channel_kinds": ("backend-log",),
        "channel_refs": (),
        "window_kinds": ("task",),
        "integrity_modes": ("checksum",),
        "sensitivity": "plain",
        "disclosure": "full",
        "retention_policy_refs": ("study_lifetime",),
        "export_policy": "not-required",
        "redaction_policy": None,
    }
    if source == "sdl":
        demand = compile_scenario_capture_demands(_capture_scenario())[0]
    else:
        _, _, spec, _, _ = _evidence_bundle()
        demand = compile_capture_spec_demands((spec,))[0]
        expected.update(
            field_selectors=("/0/action_contract_address",),
            capture_kind="trace",
            source_classes=(),
            scopes=("network",),
            channel_kinds=(),
            channel_refs=("evaluation-history-channel",),
            window_kinds=("run",),
            integrity_modes=("sha256-digest",),
            sensitivity="internal",
            retention_policy_refs=("Retain raw evidence for the experiment review window.",),
        )
    assert {dimension.name for dimension in CAPTURE_DIMENSIONS if dimension.required_value is None} == set(expected)
    assert {name: getattr(demand, name) for name in expected} == expected


def test_atomic_offers_cannot_pool_dimensions_and_diagnostics_ignore_offer_order() -> None:
    demand = compile_scenario_capture_demands(_capture_scenario())[0]
    offers = (
        _offer(offer_id="wrong-window", window_kinds=frozenset({"run"})),
        _offer(offer_id="wrong-source", source_classes=frozenset({"other"})),
    )
    diagnostics = capture_admission_diagnostics((demand,), _manifest_with_offers(*offers).observation)
    assert diagnostics
    assert diagnostics == capture_admission_diagnostics((demand,), _manifest_with_offers(*reversed(offers)).observation)
