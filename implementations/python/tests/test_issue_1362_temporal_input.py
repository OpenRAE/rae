"""Both archive and executable identities gate the hosted test server."""

import hashlib
import io
import json
import tarfile

import pytest
from implementations.tooling import runtime_execution_ci
from raes_contracts.errors import InvalidInputError


def test_server_input_cannot_substitute_an_executable_even_with_a_valid_archive(tmp_path, monkeypatch):
    data = b"reviewed-input"
    archive_path = tmp_path / "input.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        entry = tarfile.TarInfo("temporal")
        entry.size = len(data)
        archive.addfile(entry, io.BytesIO(data))
    raw = archive_path.read_bytes()
    authority = tmp_path / "implementations/tooling/artifacts.lock.json"
    authority.parent.mkdir(parents=True)
    authority.write_text(
        json.dumps({"artifacts": [{"artifact_id": "temporal-cli-runtime-test", "version": "fixture"}]})
    )
    selection = {
        "platform": {
            "raw_manifest": [{"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}],
            "installed_manifest": [{"size": len(data), "sha256": "a" * 64}],
        }
    }
    monkeypatch.setattr(runtime_execution_ci, "select_tooling_artifact", lambda *args, **kwargs: selection)
    output = tmp_path / "bin/temporal"
    with pytest.raises(InvalidInputError):
        runtime_execution_ci.install_temporal_cli(archive_path, output, repo_root=tmp_path)
    assert not output.exists()
    selection["platform"]["installed_manifest"][0]["sha256"] = hashlib.sha256(data).hexdigest()
    runtime_execution_ci.install_temporal_cli(archive_path, output, repo_root=tmp_path)
    assert output.read_bytes() == data
    archive_path.write_bytes(b"substituted-archive")
    with pytest.raises(InvalidInputError):
        runtime_execution_ci.install_temporal_cli(archive_path, output, repo_root=tmp_path)
    assert output.read_bytes() == data
