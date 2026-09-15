"""Protected immutable SDL bytes, not a path-only reproducibility claim."""

import hashlib
import json
import stat

import pytest
from raes import parse_sdl
from test_issue_1241_materialized_sdl import materialized_payload


def _archive(tmp_path):
    from raes_operations.run_artifacts import RunMaterializationArchive

    return RunMaterializationArchive(tmp_path)


def test_archive_publishes_actual_valid_sdl_with_a_verified_typed_reference(tmp_path):
    archive = _archive(tmp_path)
    record = archive.publish(json.dumps(materialized_payload()))
    artifact = record.artifact
    path = tmp_path / record.reference.ref_path
    data = path.read_bytes()
    parsed = parse_sdl(data.decode())
    assert type(parsed).__name__ == "MaterializedScenario"
    assert artifact.role == "materialization-attestation"
    assert record.reference.ref_kind == "materialization-attestation"
    assert record.reference.ref_id == parsed.materialization_provenance.attestation_id
    assert artifact.checksum.value == hashlib.sha256(data).hexdigest()
    assert artifact.size_bytes == len(data)
    assert artifact.sensitivity == "restricted"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert archive.publish(json.dumps(materialized_payload())) == record


def test_archive_refuses_a_conflicting_republication_without_overwriting(tmp_path):
    archive = _archive(tmp_path)
    first = archive.publish(json.dumps(materialized_payload()))
    path = tmp_path / first.reference.ref_path
    original = path.read_bytes()
    conflicting = json.dumps(materialized_payload(description="different"))
    with pytest.raises(ValueError):
        archive.publish(conflicting)
    assert path.read_bytes() == original


@pytest.mark.parametrize("run_id", ["../escape", "run/elsewhere", "valid\n", "/absolute"])
def test_archive_rejects_untrusted_run_paths_before_writing(tmp_path, run_id):
    archive = _archive(tmp_path)
    payload = materialized_payload()
    payload["materialization_provenance"]["run_id"] = run_id
    content = json.dumps(payload)
    with pytest.raises(ValueError):
        archive.publish(content)
    assert not list(tmp_path.iterdir())


def test_archive_refuses_symlinked_run_directories(tmp_path):
    archive = _archive(tmp_path / "archive")
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "runs").symlink_to(outside, target_is_directory=True)
    content = json.dumps(materialized_payload())
    with pytest.raises((OSError, ValueError)):
        archive.publish(content)
    assert not list(outside.iterdir())


def test_archive_refuses_an_existing_symlink_artifact(tmp_path):
    archive = _archive(tmp_path)
    record = archive.publish(json.dumps(materialized_payload()))
    artifact = tmp_path / record.reference.ref_path
    saved = artifact.with_suffix(".saved")
    artifact.rename(saved)
    artifact.symlink_to(saved)
    content = json.dumps(materialized_payload())
    with pytest.raises((OSError, ValueError)):
        archive.publish(content)
