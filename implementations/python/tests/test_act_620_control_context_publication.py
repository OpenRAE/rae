"""Published asset contracts, structural parity and existing evidence carriers."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from raes_conformance.conformance import _fixture_case_diagnostics
from raes_conformance.conformance.validators import validate_contract_payload
from raes_contracts.contracts import schema_bundle
from raes_contracts.participant_control_context import load_control_context_json
from test_act_620_control_context_assets import _asset, _change, _context, _exposed, _record

ROOT = Path(__file__).resolve().parents[3]
KINDS = ("asset", "change", "record")


@pytest.mark.parametrize("kind", KINDS)
def test_published_contract_matches_bundle_and_exercises_conformance_corpus(kind):
    contract = f"participant-control-context-{kind}-v1"
    schema = json.loads((ROOT / f"contracts/schemas/participant-runtime/{contract}.json").read_text())
    assert schema == schema_bundle()[contract]
    fixtures = ROOT / f"contracts/fixtures/participant-runtime/{contract}"
    for path in sorted((fixtures / "valid").glob("*.json")):
        payload = json.loads(path.read_text())
        Draft202012Validator(schema).validate(payload)
        assert [item.code for item in _fixture_case_diagnostics(contract, payload)] == [
            "conformance.semantic-context-required"
        ]
    assert list((fixtures / "valid").glob("*.json"))
    for path in sorted((fixtures / "invalid").glob("*.json")):
        assert [item.code for item in _fixture_case_diagnostics(contract, json.loads(path.read_text()))] == [
            "conformance.schema-invalid"
        ]
    assert list((fixtures / "invalid").glob("*.json"))


@pytest.mark.parametrize("model", [_asset, _record, _change])
def test_portable_round_trip_retains_exact_version_and_separate_evidence(model):
    value = model()
    assert load_control_context_json(value.model_dump_json(), type(value)) == value


def test_run_manifest_retains_selections_and_delivery_as_distinct_artifacts():
    from hashlib import sha256
    from io import BytesIO

    from raes_contracts.associated_artifacts import (
        associated_artifact_set_digest,
        validate_associated_artifact_manifest,
    )
    from raes_contracts.contracts import AssociatedArtifactManifestModel, ExperimentRunModel

    run_payload = json.loads(
        (ROOT / "contracts/fixtures/experiment-core/experiment-run-v1/valid/reference.json").read_text()
    )
    run = ExperimentRunModel.model_validate(run_payload)
    records = {"selection": _record(run_id=run.run_id), "delivery": _exposed(run_id=run.run_id)}
    encoded = {key: record.model_dump_json().encode() for key, record in records.items()}
    artifacts = {
        key: {
            "artifact_id": key,
            "role": "apparatus-evidence",
            "media_type": "application/json",
            "uri": "urn:sha256:" + sha256(data).hexdigest(),
            "checksum": {"algorithm": "sha256", "value": sha256(data).hexdigest()},
            "size_bytes": len(data),
            "created_at": "2026-10-26T00:00:00Z",
            "source": "evidence.capture",
            "sensitivity": "restricted",
        }
        for key, data in encoded.items()
    }
    manifest = AssociatedArtifactManifestModel(
        schema_version="associated-artifact-manifest/v1",
        manifest_id="control-context-evidence",
        manifest_version="one",
        canonicalization_profile="associated-artifact-set/v1",
        scope="experiment",
        parent_ref={"ref_kind": "run", "ref_id": run.run_id},
        artifacts=artifacts,
        set_digest="sha256:" + "0" * 64,
    )
    manifest = manifest.model_copy(update={"set_digest": associated_artifact_set_digest(manifest)})
    recovered = type(manifest).model_validate_json(manifest.model_dump_json())
    assert (
        validate_associated_artifact_manifest(
            recovered, parent=run, artifact_readers={key: BytesIO(data) for key, data in encoded.items()}
        )
        == ()
    )
    selected, delivered = (
        load_control_context_json(encoded[key], type(records[key])) for key in ("selection", "delivery")
    )
    assert selected.asset_ref == delivered.asset_ref
    assert selected.run_id == delivered.run_id == run.run_id
    assert selected.delivery_ref is None
    assert delivered.delivery_ref is not None


def test_public_diagnostics_omit_private_resolver_exceptions():
    def fail(_request):
        raise RuntimeError("private instruction and credentials must not escape")

    diagnostics = validate_contract_payload(
        "participant-control-context-record-v1",
        _record().model_dump(),
        control_context_asset_context=replace(_context(), authorize=fail),
    )
    assert diagnostics[0].code == "conformance.context-resolution-failed"
    assert "private instruction" not in str(diagnostics)


@pytest.mark.parametrize(
    "family,contract",
    [
        ("participant-runtime", "participant-flow-control-relation-v1"),
        ("plans", "mixed-participant-composition-profile-v1"),
    ],
)
def test_other_context_required_contracts_return_a_diagnostic_instead_of_crashing(family, contract):
    fixture = next((ROOT / f"contracts/fixtures/{family}/{contract}/valid").glob("*.json"))
    diagnostics = _fixture_case_diagnostics(contract, json.loads(fixture.read_text()))
    assert [item.code for item in diagnostics] == ["conformance.semantic-context-required"]


@pytest.mark.parametrize("disposition", ["selected", "withheld", "disclosed", "delivered"])
def test_schema_rejects_false_delivery_and_disposition_shapes(disposition):
    schema = schema_bundle()["participant-control-context-record-v1"]
    payload = _record().model_dump()
    payload.update(disposition=disposition, delivery_ref="forged")
    assert list(Draft202012Validator(schema).iter_errors(payload))
