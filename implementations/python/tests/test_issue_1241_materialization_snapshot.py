"""Only admitted archive references enter ordinary durable runtime snapshots."""

import json

import pytest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, RuntimeSnapshotEnvelope
from raes_operations.run_artifacts import RunMaterializationArchive
from raes_runtime.backend_calls import _call_backend_apply
from raes_runtime.control_plane_api_models import _snapshot_model
from raes_runtime.control_plane_store_snapshots import _snapshot_from_payload, _snapshot_payload
from test_issue_1241_materialized_sdl import materialized_payload


def test_archive_reference_survives_updates_store_and_api_roundtrips(tmp_path):
    record = RunMaterializationArchive(tmp_path).publish(json.dumps(materialized_payload()))
    snapshot = RuntimeSnapshot(materialization_attestations=(record,))
    updated = snapshot.with_entries({})
    assert updated.materialization_attestations == (record,)
    restored = _snapshot_from_payload(_snapshot_payload(updated))
    assert restored.materialization_attestations == (record,)
    wire = _snapshot_model(RuntimeSnapshotEnvelope(snapshot=restored))
    assert wire.materialization_attestations == [record]
    assert _snapshot_from_payload(wire.model_dump(mode="json")).materialization_attestations == (record,)


def test_backend_cannot_forge_a_runtime_owned_archive_reference(tmp_path):
    record = RunMaterializationArchive(tmp_path).publish(json.dumps(materialized_payload()))
    previous = RuntimeSnapshot()

    def apply(snapshot):
        return ApplyResult(True, RuntimeSnapshot(materialization_attestations=(record,)))

    result = _call_backend_apply(apply, previous, address="runtime.forged-archive", snapshot=previous)
    assert not result.success
    assert result.snapshot == previous
    assert any(item.address == "runtime.snapshot.materialization-attestations" for item in result.diagnostics)


def test_portable_snapshot_rejects_duplicate_archive_identities(tmp_path):
    from raes_contracts.contracts import RuntimeSnapshotEnvelopeModel

    record = RunMaterializationArchive(tmp_path).publish(json.dumps(materialized_payload()))
    wire = _snapshot_model(RuntimeSnapshotEnvelope(snapshot=RuntimeSnapshot(materialization_attestations=(record,))))
    payload = wire.model_dump(mode="json")
    payload["materialization_attestations"].append(record.model_dump(mode="json"))
    with pytest.raises(ValueError):
        RuntimeSnapshotEnvelopeModel.model_validate(payload)
