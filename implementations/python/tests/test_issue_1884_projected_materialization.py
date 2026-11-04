"""Native SDL admits against owner-projected readback without recovering values."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_contracts.errors import InvalidInputError
from raes_contracts.materialization import MaterializationSubmission
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.compiler.materialization_origins import materialization_node_payloads_match
from raes_processor.planner import admit_materialization_submission
from raes_processor.semantics.realization_concerns import realization_concern_descriptor
from test_issue_1241_materialization_context import attesting_plan
from test_issue_1241_materialization_runtime import ReportingProvisioner

_CASES = [
    (
        "runtime-environment",
        "environment",
        [{"name": "MODE", "value": "fixture", "value_classification": "plain", "provenance": "runtime"}],
        (0,),
        "value",
    ),
    (
        "runtime-database-services",
        "database_services",
        [
            {
                "database_service_id": "primary",
                "settings": [{"name": "mode", "value": "strict", "value_classification": "plain"}],
            }
        ],
        (0, "settings", 0),
        "value",
    ),
    (
        "runtime-local-control-interfaces",
        "local_control_interfaces",
        [
            {
                "control_interface_id": "engine",
                "path": "/run/engine.sock",
                "bind_source": "/run/native.sock",
                "bind_source_sensitivity": "plain",
            }
        ],
        (0,),
        "bind_source",
    ),
]


def _case(kind, field, value):
    source = json.dumps({"name": "projected-world", "nodes": {"host": {"type": "compute", "runtime": {field: value}}}})
    execution, _ = attesting_plan(source)
    request = replace(execution.provisioning, operation_id="initial-materialization")
    previous = RuntimeSnapshot()
    result = ReportingProvisioner(execution.manifest, realize=True).apply(request, previous)
    entry = result.snapshot.entries["provision.node.host"]
    payload = deepcopy(entry.payload)
    owner = realization_concern_descriptor(kind)
    raw = payload["spec"]["node"]["runtime"][field]
    projected = owner.project(raw)
    projected = owner.sanitize_observation(projected)
    payload["spec"]["node"]["runtime"][field] = projected
    return execution, request, previous, result, entry, payload


@pytest.mark.parametrize("kind,field,value,path,raw_field", _CASES)
def test_public_admission_accepts_raw_and_projected_unchanged_values(kind, field, value, path, raw_field):
    execution, request, previous, result, entry, payload = _case(kind, field, value)
    for snapshot in (result.snapshot, result.snapshot.with_entries({entry.address: replace(entry, payload=payload)})):
        admitted = admit_materialization_submission(
            result.materialization_attestation, request, execution.manifest, previous, snapshot
        )
        described = parse_sdl(admitted.sdl)
        record = described.model_dump(mode="json")["nodes"]["host"]["runtime"][field]
        projected_record = payload["spec"]["node"]["runtime"][field]
        for token in path:
            record, projected_record = record[token], projected_record[token]
        assert raw_field in record
        assert raw_field not in projected_record
        assert f"{raw_field}_commitment" in projected_record
        assert "value_commitment" not in admitted.sdl
        assert "bind_source_commitment" not in admitted.sdl


@pytest.mark.parametrize("kind,field,value,path,raw_field", _CASES)
@pytest.mark.parametrize("tamper", ["commitment", "presence", "identity", "unknown-field"])
def test_public_admission_rejects_changed_or_invalid_projection(kind, field, value, path, raw_field, tamper):
    execution, request, previous, result, entry, payload = _case(kind, field, value)
    record = payload["spec"]["node"]["runtime"][field]
    for token in path:
        record = record[token]
    if tamper == "commitment":
        record[f"{raw_field}_commitment"] = "raes-runtime-value-jcs-sha256-v1:sha256:" + "0" * 64
    elif tamper == "presence":
        record[f"{raw_field}_present"] = False
    elif tamper == "identity":
        identity = "control_interface_id" if raw_field == "bind_source" else "name"
        record[identity] = "other"
    else:
        record["backend_private"] = True
    snapshot = result.snapshot.with_entries({entry.address: replace(entry, payload=payload)})
    with pytest.raises(InvalidInputError, match="complete returned scope"):
        admit_materialization_submission(
            result.materialization_attestation, request, execution.manifest, previous, snapshot
        )


@pytest.mark.parametrize("kind,field,value,path,raw_field", _CASES)
@pytest.mark.parametrize("membership", ["missing", "extra", "duplicate"])
def test_projected_admission_keeps_exact_inventory_membership(kind, field, value, path, raw_field, membership):
    execution, request, previous, result, entry, payload = _case(kind, field, value)
    entries = {entry.address: replace(entry, payload=payload)}
    if membership == "missing":
        entries.clear()
    elif membership == "extra":
        entries["provision.node.other"] = replace(entry, address="provision.node.other", payload=payload)
    else:
        payload["spec"]["node"]["runtime"][field] *= 2
    with pytest.raises(InvalidInputError, match="complete returned scope"):
        admit_materialization_submission(
            result.materialization_attestation,
            request,
            execution.manifest,
            previous,
            result.snapshot.with_entries(entries),
        )


@pytest.mark.parametrize("classification", ["redacted", "operator_secret"])
@pytest.mark.parametrize("kind,field,value,path,raw_field", _CASES)
def test_withheld_values_compare_by_presence_without_raw_material(kind, field, value, path, raw_field, classification):
    value = deepcopy(value)
    record = value
    for token in path:
        record = record[token]
    record.pop(raw_field)
    classification_field = "bind_source_sensitivity" if raw_field == "bind_source" else "value_classification"
    record[classification_field] = classification
    execution, request, previous, result, entry, payload = _case(kind, field, value)
    snapshot = result.snapshot.with_entries({entry.address: replace(entry, payload=payload)})
    admit_materialization_submission(
        result.materialization_attestation, request, execution.manifest, previous, snapshot
    )
    record = payload["spec"]["node"]["runtime"][field]
    for token in path:
        record = record[token]
    assert record[f"{raw_field}_present"] is True
    assert f"{raw_field}_commitment" not in record
    record[f"{raw_field}_present"] = False
    with pytest.raises(InvalidInputError):
        admit_materialization_submission(
            result.materialization_attestation, request, execution.manifest, previous, snapshot
        )


def test_comparison_keeps_ordered_commands_and_residual_node_fields():
    described = {"type": "compute", "runtime": {"container": {"command": ["first", "second"]}}}
    observed = deepcopy(described)
    assert materialization_node_payloads_match("host", described, observed)
    observed["runtime"]["container"]["command"].reverse()
    assert not materialization_node_payloads_match("host", described, observed)
    observed = {**described, "architecture": "aarch64"}
    assert not materialization_node_payloads_match("host", described, observed)


def test_comparison_does_not_admit_commitments_as_sdl():
    kind, field, value, *_ = _CASES[0]
    _, _, _, result, entry, payload = _case(kind, field, value)
    observed = payload["spec"]["node"]
    assert not materialization_node_payloads_match("host", observed, observed)
    assert materialization_node_payloads_match("host", entry.payload["spec"]["node"], observed)
    assert result.materialization_attestation is not None


@pytest.mark.parametrize(
    "field", ["authored_digest", "instantiated_digest", "plan_digest", "predecessor_digest", "operation_id", "run_id"]
)
def test_projected_values_do_not_excuse_invalid_source_or_execution_bindings(field):
    kind, name, value, *_ = _CASES[0]
    execution, request, previous, result, entry, payload = _case(kind, name, value)
    document = json.loads(result.materialization_attestation.sdl)
    provenance = document["materialization_provenance"]
    if field in {"authored_digest", "instantiated_digest"}:
        provenance[field]["value"] = "sha256:" + "0" * 64
    else:
        provenance[field] = "sha256:" + "0" * 64 if field.endswith("digest") else "other"
    with pytest.raises(InvalidInputError, match="bind this source and execution"):
        admit_materialization_submission(
            MaterializationSubmission(sdl=json.dumps(document)),
            request,
            execution.manifest,
            previous,
            result.snapshot.with_entries({entry.address: replace(entry, payload=payload)}),
        )
