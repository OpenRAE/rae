"""The distinct SDL artifact reuses experiment and associated-artifact machinery."""

import json
from io import BytesIO

import pytest
from raes import parse_sdl
from raes_contracts.associated_artifacts import associated_artifact_set_digest, validate_associated_artifact_manifest
from raes_contracts.contracts import AssociatedArtifactManifestModel, ExperimentRunModel
from raes_operations.run_artifacts import RunMaterializationArchive
from test_issue_1241_materialized_sdl import materialized_payload
from test_sem_225_augmentation_semantics import _base_augmentation_disclosure, _experiment_fixture


def test_protected_archive_is_a_byte_bound_associated_artifact(tmp_path):
    record = RunMaterializationArchive(tmp_path).publish(json.dumps(materialized_payload()))
    manifest = AssociatedArtifactManifestModel.model_validate(
        {
            "schema_version": "associated-artifact-manifest/v1",
            "manifest_id": "materialized",
            "manifest_version": "1.0.0",
            "canonicalization_profile": "associated-artifact-set/v1",
            "scope": "scenario",
            "parent_ref": record.reference.model_dump(mode="json"),
            "artifacts": {record.artifact.artifact_id: record.artifact.model_dump(mode="json")},
            "set_digest": "sha256:" + "0" * 64,
        }
    )
    manifest = manifest.model_copy(update={"set_digest": associated_artifact_set_digest(manifest)})
    data = (tmp_path / record.reference.ref_path).read_bytes()
    parent = parse_sdl(data.decode())
    assert (
        validate_associated_artifact_manifest(
            manifest,
            parent=parent,
            artifact_readers={record.artifact.artifact_id: BytesIO(data)},
        )
        == ()
    )
    assert validate_associated_artifact_manifest(
        manifest,
        parent=parse_sdl("name: materialized"),
        artifact_readers={record.artifact.artifact_id: BytesIO(data)},
    )


def _run(tmp_path):
    payload = _experiment_fixture("experiment-run-v1")
    sdl = materialized_payload()
    sdl["materialization_provenance"]["run_id"] = payload["run_id"]
    record = RunMaterializationArchive(tmp_path).publish(json.dumps(sdl))
    payload["materialization_attestations"] = [record.model_dump(mode="json")]
    disclosure = _base_augmentation_disclosure()
    disclosure.update(
        classifications=["environment_visible", "participant_visible", "comparability_relevant"],
        environment_effect="An in-world sensor service is present.",
        participant_visibility="The service is network-visible.",
        carrier_refs=[record.reference.model_dump(mode="json")],
    )
    payload["augmentation_disclosures"] = [disclosure]
    return payload


def test_run_links_materialized_sdl_without_replacing_original_input(tmp_path):
    payload = _run(tmp_path)
    run = ExperimentRunModel.model_validate(payload)
    assert run.scenario_snapshot_ref.model_dump(mode="json", exclude_none=True) == payload["scenario_snapshot_ref"]
    assert run.materialization_attestations[0].reference.ref_kind == "materialization-attestation"


@pytest.mark.parametrize("field", ["evidence_refs", "markings", "participant_visibility", "observer_effect"])
def test_attestation_does_not_replace_visibility_or_evidence_requirements(tmp_path, field):
    payload = _run(tmp_path)
    del payload["augmentation_disclosures"][0][field]
    with pytest.raises(ValueError):
        ExperimentRunModel.model_validate(payload)


def test_run_refuses_cross_run_and_unarchived_attestation_carriers(tmp_path):
    payload = _run(tmp_path)
    payload["materialization_attestations"][0]["run_id"] = "another-run"
    with pytest.raises(ValueError):
        ExperimentRunModel.model_validate(payload)
    payload["materialization_attestations"] = []
    with pytest.raises(ValueError):
        ExperimentRunModel.model_validate(payload)
