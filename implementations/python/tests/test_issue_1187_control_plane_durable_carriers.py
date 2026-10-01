"""Offline carrier mutation must fail admission even with a matching digest."""

from __future__ import annotations

import json
import sqlite3

import pytest
from control_plane_conformance_fixtures import DURABLE_PROFILES, profile_harness, witness_events
from raes_runtime.control_plane_store_local_codec import encode_payload

pytestmark = pytest.mark.control_plane_conformance


@pytest.mark.parametrize("profile", DURABLE_PROFILES)
@pytest.mark.parametrize(
    "mutation",
    [
        "missing-state",
        "unknown-state",
        "unknown-field",
        "actor-mismatch",
        "scope-mismatch",
        "durable-key-mismatch",
        "bad-digest",
    ],
)
def test_malformed_durable_carrier_blocks_reopen_without_backend_replay(profile, mutation, tmp_path) -> None:
    with profile_harness(profile, tmp_path) as harness:
        operation_id = harness.submit()
    database = tmp_path / "store" / "control-plane.sqlite3"
    with sqlite3.connect(database) as connection:
        original = connection.execute(
            "SELECT payload FROM operations WHERE operation_id=?", (operation_id,)
        ).fetchone()[0]
        payload = json.loads(original)
        if mutation == "missing-state":
            del payload["status"]["state"]
        elif mutation == "unknown-state":
            payload["status"]["state"] = "replay-me"
        elif mutation == "unknown-field":
            payload["status"]["trusted"] = True
        elif mutation == "actor-mismatch":
            payload["status"]["context"]["actor_id"] = "other"
        elif mutation == "scope-mismatch":
            for field in ("receipt", "status"):
                payload[field]["context"]["run_scope"] = "run:other"
        elif mutation == "durable-key-mismatch":
            for field in ("receipt", "status"):
                payload[field]["operation_id"] = "other-operation"
        content, digest = encode_payload(payload)
        if mutation == "bad-digest":
            digest = "0" * 64
        connection.execute(
            "UPDATE operations SET payload=?, digest=? WHERE operation_id=?", (content, digest, operation_id)
        )
    effects = witness_events(tmp_path / "effects.jsonl")
    with pytest.raises((ValueError, RuntimeError)), profile_harness(profile, tmp_path):
        pytest.fail("malformed persisted operation reached readiness")
    assert witness_events(tmp_path / "effects.jsonl") == effects
    # Rejection does not silently repair, drop, or replace the invalid history.
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT payload, digest FROM operations WHERE operation_id=?", (operation_id,)
        ).fetchone() == (content, digest)
