"""Materialization admission compares account material value-free, as the runtime stores it."""

import pytest
from raes_contracts.account_credentials import value_free_account_placement_payload
from raes_contracts.errors import InvalidInputError
from raes_contracts.planning import PlannedResource, RuntimeDomain
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_processor.planner.materialization_admission import _validate_current_scope

ADDRESS = "provision.account.admin"
PAYLOAD = {
    "name": "admin",
    "spec": {
        "username": "admin",
        "node": "host",
        "auth_method": "password",
        "credential_bindings": [
            {
                "credential_id": "admin-password",
                "purpose": "primary_authentication",
                "auth_method": "password",
                "material": {"classification": "secret_fixture", "value": "fixture"},
            }
        ],
    },
}


def _scope(payload):
    entry = SnapshotEntry(
        address=ADDRESS, domain=RuntimeDomain.PROVISIONING, resource_type="account-placement", payload=payload
    )
    return RuntimeSnapshot(entries={ADDRESS: entry})


def test_described_account_matches_its_value_free_runtime_entry():
    resource = PlannedResource(
        address=ADDRESS, domain=RuntimeDomain.PROVISIONING, resource_type="account-placement", payload=PAYLOAD
    )
    stored = value_free_account_placement_payload(PAYLOAD)
    _validate_current_scope({ADDRESS: resource}, _scope(stored), RuntimeDomain.PROVISIONING)
    changed = {**stored, "spec": {**stored["spec"], "username": "root"}}
    with pytest.raises(InvalidInputError):
        _validate_current_scope({ADDRESS: resource}, _scope(changed), RuntimeDomain.PROVISIONING)
