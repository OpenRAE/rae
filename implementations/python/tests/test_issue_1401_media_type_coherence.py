"""Required media declarations must be offerable and content-provable."""

from __future__ import annotations

import io
import json

import pytest
from pydantic import ValidationError
from raes_contracts.contracts import ExperimentCaptureSpecModel
from raes_contracts.evidence_satisfaction import validate_experiment_run_evidence
from test_issue_1112_capture_admission import (
    EVENT_STREAM_FIXTURE,
    _capture_scenario,
    _evidence_bundle,
    _fixture,
    _offer,
)


@pytest.mark.parametrize("media_type", ["text/plain", "application/x-ndjson", "application/vnd.tcpdump.pcap"])
def test_sdl_rejects_unprovable_required_media_type(media_type: str) -> None:
    scenario = _capture_scenario()
    payload = scenario.evidence_requirements["attacker-action-log"].model_dump(mode="json")
    payload["media_types"] = ["application/json", media_type]
    with pytest.raises(ValidationError, match="unsupported.*media type"):
        type(scenario.evidence_requirements["attacker-action-log"]).model_validate(payload)


@pytest.mark.parametrize("media_type", ["text/plain", "application/x-ndjson", "application/vnd.tcpdump.pcap"])
def test_capture_spec_rejects_unprovable_required_media_type(media_type: str) -> None:
    payload = _fixture("experiment-capture-spec-v1")
    requirement = next(iter(payload["capture_requirements"].values()))
    requirement["expected_media_types"] = ["application/json", media_type]
    with pytest.raises(ValidationError, match="unsupported.*media type"):
        ExperimentCaptureSpecModel.model_validate(payload)


@pytest.mark.parametrize("media_type", ["application/json", "application/jsonl"])
def test_explicit_contract_rejects_misleading_encoding(media_type: str) -> None:
    payload = _fixture("experiment-capture-spec-v1")
    requirement = next(iter(payload["capture_requirements"].values()))
    requirement["output_contract"] = "experiment-evidence-record-v1"
    requirement["expected_media_types"] = [media_type]
    if media_type == "application/json":
        ExperimentCaptureSpecModel.model_validate(payload)
    else:
        with pytest.raises(ValidationError, match="media.*output_contract"):
            ExperimentCaptureSpecModel.model_validate(payload)


@pytest.mark.parametrize("media_type", ["application/json", "application/jsonl"])
def test_accepted_declaration_has_offer_and_content_proof(media_type: str) -> None:
    events = json.loads(EVENT_STREAM_FIXTURE.read_text(encoding="utf-8"))
    payload = (
        EVENT_STREAM_FIXTURE.read_bytes()
        if media_type == "application/json"
        else b"\n".join(json.dumps(event).encode() for event in events)
    )
    task, run, spec, record, _ = _evidence_bundle(payload, media_type=media_type)
    offer = _offer(media_types=frozenset({media_type}))
    assert media_type in offer.media_types
    proof = validate_experiment_run_evidence(
        task,
        run,
        capture_specs={spec.capture_spec_id: spec},
        evidence_records={record.evidence_record_id: record},
        artifact_readers={run.evidence_artifacts[0].artifact_id: io.BytesIO(payload)},
    )
    assert proof.bindings


def test_unknown_sdl_output_contract_is_rejected_at_authoring() -> None:
    scenario = _capture_scenario()
    payload = scenario.evidence_requirements["attacker-action-log"].model_dump(mode="json")
    payload["output_contract"] = "unknown-output-contract-v1"
    with pytest.raises(ValidationError, match="output_contract"):
        type(scenario.evidence_requirements["attacker-action-log"]).model_validate(payload)


def test_sdl_object_contract_rejects_json_lines_at_authoring() -> None:
    scenario = _capture_scenario(output_contract="experiment-evidence-record-v1")
    payload = scenario.evidence_requirements["attacker-action-log"].model_dump(mode="json")
    payload["media_types"] = ["application/jsonl"]
    with pytest.raises(ValidationError, match="media.*output_contract"):
        type(scenario.evidence_requirements["attacker-action-log"]).model_validate(payload)
