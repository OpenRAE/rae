"""Admission, disclosure and persistence must use the same portable payload.

Models cannot hide or rewrite fields admission inspected. Credential and
prepared-node checks must see through admitted carriers before sanitizing.
Durable storage must encode the same values that the runtime admitted.
"""

from copy import deepcopy
from dataclasses import replace

import pytest
from pydantic import BaseModel, Field, model_serializer
from pydantic_core import to_jsonable_python
from raes_contracts.errors import InvalidInputError
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_processor.planner import sanitize_prepared_node_snapshot
from raes_runtime.backend_account_credentials import sanitize_account_credential_result
from raes_runtime.backend_apply_results import _finalize_backend_apply
from raes_runtime.backend_realization_authority import _RealizationApplyContext
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from test_issue_673_account_credential_bindings import FIXTURE_SENTINEL, OPERATOR_REFERENCE, _credential_plan
from test_issue_985_runtime_observation_contract import _authoritative_environment_plan, _authoritative_snapshot
from test_issue_1204_resource_collections import _collection_request, _isolated_designation
from test_issue_1451_portable_disclosure_payloads import (
    _ADDRESS,
    _OBSERVED,
    _SPEC_CARRIERS,
    _WEB,
    _apply,
    _closed_excess,
    _enum_member,
    _observed_apply,
    _plain,
)


class _MappingCarrier(BaseModel):
    model_config = {"extra": "allow"}


class _ExcludedRuntime(_MappingCarrier):
    runtime: dict = Field(exclude=True)


class _AliasedRuntime(_MappingCarrier):
    runtime: dict = Field(serialization_alias="rt")


class _RewrittenRuntime(_MappingCarrier):
    @model_serializer(mode="wrap")
    def serialize(self, handler):
        projected = handler(self)
        projected["runtime"] = {"environment": []}
        return projected


def _model(value):
    return _MappingCarrier.model_validate(value)


def _node_carrier(carrier):
    def wrap(spec):
        return {**spec, "node": carrier.model_validate(spec["node"])}

    return wrap


_CARRIERS = {**_SPEC_CARRIERS, "model": _model}
_LOSSY_CARRIERS = [_ExcludedRuntime, _AliasedRuntime, _RewrittenRuntime]


@pytest.mark.parametrize("carrier", _LOSSY_CARRIERS)
def test_serializer_cannot_hide_closed_excess_from_admission(carrier):
    manager, result = _apply(_closed_excess(_node_carrier(carrier)))

    assert not result.success
    assert manager.snapshot.entries == {}
    assert any(d.code == "runtime.backend-contract-invalid" for d in result.diagnostics)


@pytest.mark.parametrize("carrier", _LOSSY_CARRIERS)
def test_serializer_cannot_keep_a_raw_open_observation(carrier):
    result = _observed_apply("open", _node_carrier(carrier))

    assert not result.success
    assert result.snapshot.entries == {}
    assert any(d.code == "runtime.backend-contract-invalid" for d in result.diagnostics)


@pytest.mark.parametrize("carrier", _LOSSY_CARRIERS)
def test_serializer_mismatch_is_refused_inside_an_enum(carrier):
    def wrap(spec):
        return _enum_member(_node_carrier(carrier)(spec))

    manager, result = _apply(_closed_excess(wrap))

    assert not result.success
    assert manager.snapshot.entries == {}
    assert any(d.code == "runtime.backend-contract-invalid" for d in result.diagnostics)


@pytest.mark.parametrize("wrap", list(_CARRIERS.values()), ids=list(_CARRIERS))
def test_admitted_payload_carriers_survive_durable_storage(tmp_path, wrap):
    def rewrite(entry):
        if entry.address != _WEB:
            return entry
        return replace(entry, payload={**entry.payload, "spec": wrap(entry.payload["spec"])})

    manager, result = _apply(rewrite)
    assert result.success, result.diagnostics
    expected = to_jsonable_python(manager.snapshot.entries[_WEB].payload)

    store = LocalControlPlaneStore(tmp_path / "state")
    store.save_snapshot(manager.snapshot, expected_revision=0)

    assert store.load_snapshot().entries[_WEB].payload == expected


@pytest.mark.parametrize("wrap", [_plain, _enum_member, _model], ids=["plain", "enum", "model"])
@pytest.mark.parametrize("unauthorized", [False, True], ids=["honest", "extra-field"])
def test_credential_closure_uses_the_portable_payload(wrap, unauthorized):
    plan = _credential_plan()
    operation = plan.operations[0]
    payload = deepcopy(operation.payload)
    if unauthorized:
        payload["copied"] = FIXTURE_SENTINEL
    payload["spec"] = wrap(payload["spec"])
    entry = SnapshotEntry(
        operation.address, RuntimeDomain.PROVISIONING, operation.resource_type, payload, status="applied"
    )
    result = ApplyResult(True, RuntimeSnapshot(entries={entry.address: entry}), changed_addresses=[entry.address])

    if unauthorized:
        with pytest.raises(InvalidInputError):
            sanitize_account_credential_result(result, plan, RuntimeSnapshot())
        return
    safe = sanitize_account_credential_result(result, plan, RuntimeSnapshot())

    assert safe.success
    assert FIXTURE_SENTINEL not in repr(safe.snapshot)
    assert OPERATOR_REFERENCE not in repr(safe.snapshot)
    assert safe.snapshot.entries[entry.address].payload["spec"]["credential_bindings"]


@pytest.mark.parametrize("wrap", list(_CARRIERS.values()), ids=list(_CARRIERS))
def test_prepared_delivery_reads_the_same_portable_concern(wrap):
    plan, manifest = _authoritative_environment_plan()
    snapshot = _authoritative_snapshot(plan, deepcopy(_OBSERVED))
    entry = snapshot.entries[_ADDRESS]
    entry = replace(entry, payload={**entry.payload, "spec": wrap(entry.payload["spec"])})
    result = ApplyResult(True, snapshot.with_entries({_ADDRESS: entry}), changed_addresses=[_ADDRESS])

    accepted = _finalize_backend_apply(
        result,
        address="runtime.prepared-portable",
        baseline_snapshot=RuntimeSnapshot(),
        realization=_RealizationApplyContext(plan=plan, operation_plan=plan, completion_plan=plan, manifest=manifest),
        information_state_context_resolver=None,
    )

    assert accepted.success, accepted.diagnostics
    assert "production" not in repr(to_jsonable_python(accepted.snapshot.entries[_ADDRESS].payload))
    assert any(row.requirement_kind == "runtime-environment" for row in accepted.snapshot.realization_provenance)


@pytest.mark.parametrize("wrap", list(_CARRIERS.values()), ids=list(_CARRIERS))
def test_prepared_additional_node_is_sanitized_before_serialization(wrap):
    request, _ = _collection_request(_isolated_designation(True))
    operation = request.operations[0]
    payload = deepcopy(operation.payload)
    payload["spec"]["node"]["runtime"] = {"environment": deepcopy(_OBSERVED)}
    address = "provision.node.extra"
    selected = replace(request, operations=[replace(operation, address=address, payload=payload)])
    entry = SnapshotEntry(
        address,
        RuntimeDomain.PROVISIONING,
        operation.resource_type,
        {**payload, "spec": wrap(payload["spec"])},
    )

    safe = sanitize_prepared_node_snapshot(selected, RuntimeSnapshot(entries={address: entry}))

    persisted = safe.entries[address].payload
    assert "production" not in repr(persisted)
    assert "description" not in repr(persisted["spec"]["node"]["runtime"]["environment"])
    assert persisted["spec"]["node"]["runtime"]["environment"][0]["value_present"] is True
