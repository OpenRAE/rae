"""SEM-225 realization augmentation and visibility semantics."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_contracts.contracts import ExperimentAugmentationDisclosureModel, ExperimentRunModel
from raes_schemas import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]


def _experiment_fixture(contract_id: str, fixture_name: str = "reference.json") -> dict:
    fixture_path = REPO_ROOT / "contracts" / "fixtures" / "experiment-core" / contract_id / "valid" / fixture_name
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _base_augmentation_disclosure() -> dict:
    return {
        "augmentation_id": "packet-capture-sidecar",
        "purpose": "evidence",
        "realization_layer": "backend",
        "classifications": ["apparatus_only", "comparability_relevant"],
        "augmented_by_ref": {
            "ref_kind": "backend",
            "ref_id": "stub-backend",
            "ref_version": "0.1.0",
        },
        "carrier_refs": [
            {
                "ref_kind": "measurement-channel",
                "ref_id": "evaluation-history-channel",
                "ref_version": "1.0.0",
            },
            {
                "ref_kind": "evidence-record",
                "ref_id": "evidence-techvault-network-trace-001",
                "ref_version": "1.0.0",
            },
        ],
        "affected_refs": [
            {
                "ref_kind": "capture-spec",
                "ref_id": "capture-techvault-evidence-v1",
                "ref_version": "1.0.0",
            }
        ],
        "evidence_refs": [
            {
                "ref_kind": "evidence-record",
                "ref_id": "evidence-techvault-network-trace-001",
                "ref_version": "1.0.0",
            }
        ],
        "disclosure_policy": "Internal run-provenance disclosure; no raw packet content is embedded.",
        "markings": ["internal"],
        "observer_effect": "The sidecar observes run traffic without modifying scenario services.",
        "comparability_effect": "Compare only with runs that declare equivalent capture support.",
    }


def _assert_schema_and_model_reject(payload: dict) -> None:
    validator = Draft202012Validator(schema_bundle()["experiment-run-v1"])
    assert list(validator.iter_errors(payload))
    with pytest.raises(ValidationError):
        ExperimentRunModel.model_validate(payload)


def _conditional_then_for(disclosure_schema: dict, classification: str) -> dict:
    for branch in disclosure_schema["allOf"]:
        contains = branch.get("if", {}).get("properties", {}).get("classifications", {}).get("contains", {})
        if contains.get("const") == classification:
            return branch["then"]
    raise AssertionError(f"missing conditional schema branch for {classification!r}")


def test_sem_225_accepts_run_augmentation_disclosure():
    payload = _experiment_fixture("experiment-run-v1")
    payload["augmentation_disclosures"] = [_base_augmentation_disclosure()]

    schema = schema_bundle()["experiment-run-v1"]
    assert not list(Draft202012Validator(schema).iter_errors(payload))
    run = ExperimentRunModel.model_validate(payload)

    disclosure = run.augmentation_disclosures[0]
    assert disclosure.augmentation_id == "packet-capture-sidecar"
    assert "comparability_relevant" in disclosure.classifications


def test_experiment_run_schema_publishes_sem_225_augmentation_surface():
    run_schema = schema_bundle()["experiment-run-v1"]

    assert run_schema["properties"]["augmentation_disclosures"]["items"]["$ref"] == (
        "#/$defs/ExperimentAugmentationDisclosureModel"
    )
    disclosure_schema = run_schema["$defs"]["ExperimentAugmentationDisclosureModel"]
    assert disclosure_schema["additionalProperties"] is False
    invariant_ids = {invariant["id"] for invariant in disclosure_schema.get("x-raes-invariants", [])}
    assert "augmentation-disclosure-semantics-valid" in invariant_ids
    run_invariant_ids = {invariant["id"] for invariant in run_schema.get("x-raes-invariants", [])}
    assert "augmentation-disclosure-evidence-refs-traced" in run_invariant_ids
    environment_then = _conditional_then_for(disclosure_schema, "environment_visible")
    assert {"carrier_refs", "environment_effect", "evidence_refs"} <= set(environment_then["required"])
    participant_then = _conditional_then_for(disclosure_schema, "participant_visible")
    assert {"participant_visibility", "markings", "evidence_refs"} <= set(participant_then["required"])


def test_sem_225_rejects_environment_visible_backend_log_only_disclosure():
    payload = _experiment_fixture("experiment-run-v1")
    disclosure = _base_augmentation_disclosure()
    disclosure["classifications"] = ["environment_visible"]
    disclosure["environment_effect"] = "Instrumentation adds an in-world sensor service."
    disclosure["carrier_refs"] = [{"ref_kind": "other", "ref_id": "backend-log"}]
    payload["augmentation_disclosures"] = [disclosure]

    _assert_schema_and_model_reject(payload)


def test_sem_225_rejects_participant_visible_augmentation_without_markings():
    payload = _experiment_fixture("experiment-run-v1")
    disclosure = _base_augmentation_disclosure()
    disclosure["classifications"] = ["participant_visible"]
    disclosure["participant_visibility"] = "Participant sees the monitoring dashboard."
    disclosure["markings"] = []
    payload["augmentation_disclosures"] = [disclosure]

    _assert_schema_and_model_reject(payload)


def test_sem_225_rejects_comparability_relevant_augmentation_without_observer_effect():
    payload = _experiment_fixture("experiment-run-v1")
    disclosure = _base_augmentation_disclosure()
    disclosure["observer_effect"] = None
    payload["augmentation_disclosures"] = [disclosure]

    _assert_schema_and_model_reject(payload)


def test_sem_225_rejects_non_processor_backend_augmentation_authority():
    payload = _experiment_fixture("experiment-run-v1")
    disclosure = _base_augmentation_disclosure()
    disclosure["augmented_by_ref"] = {
        "ref_kind": "participant-implementation",
        "ref_id": "reference-red-agent",
        "ref_version": "1.0.0",
    }
    payload["augmentation_disclosures"] = [disclosure]

    _assert_schema_and_model_reject(payload)


def test_sem_225_augmentation_evidence_refs_must_be_run_traced():
    payload = _experiment_fixture("experiment-run-v1")
    disclosure = _base_augmentation_disclosure()
    disclosure["evidence_refs"] = [{"ref_kind": "evidence-record", "ref_id": "untraced-evidence"}]
    payload["augmentation_disclosures"] = [disclosure]

    assert not list(Draft202012Validator(schema_bundle()["experiment-run-v1"]).iter_errors(payload))
    with pytest.raises(ValidationError, match="augmentation_disclosures evidence_refs must be listed"):
        ExperimentRunModel.model_validate(payload)


def test_sem_225_rejects_duplicate_disclosure_references():
    duplicate = deepcopy(_base_augmentation_disclosure())
    duplicate["carrier_refs"].append(deepcopy(duplicate["carrier_refs"][0]))

    with pytest.raises(ValidationError, match="augmentation disclosure carrier_refs must not contain duplicates"):
        ExperimentAugmentationDisclosureModel.model_validate(duplicate)
