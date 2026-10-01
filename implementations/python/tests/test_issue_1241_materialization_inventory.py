"""Attestation inventory checks use full native SDL without inventing evidence."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.planner import admit_materialization_submission
from test_issue_1241_materialization_context import attesting_plan
from test_issue_1241_materialization_runtime import ReportingProvisioner


def test_sparse_native_runtime_inventory_matches_the_same_described_sdl():
    execution, _ = attesting_plan("name: augmented\nrealization: {default: open}\nnodes:\n  host: {type: compute}")
    request = replace(execution.provisioning, operation_id="reported-operation")
    previous = RuntimeSnapshot()
    reporter = ReportingProvisioner(
        execution.manifest,
        lambda document: document["nodes"]["host"].update(
            runtime={"environment": [{"name": "COLLECTOR", "value": "enabled"}]}
        ),
        realize=True,
    )
    result = reporter.apply(request, previous)
    # The backend reports only actual native members, not all optional SDL defaults.
    entry = result.snapshot.entries["provision.node.host"]
    payload = {
        **entry.payload,
        "spec": {
            **entry.payload["spec"],
            "node": {
                **entry.payload["spec"]["node"],
                "runtime": {"environment": [{"name": "COLLECTOR", "value": "enabled"}]},
            },
        },
    }
    actual = result.snapshot.with_entries({entry.address: replace(entry, payload=payload)})
    admitted = admit_materialization_submission(
        result.materialization_attestation, request, execution.manifest, previous, actual
    )
    assert "COLLECTOR" in admitted.sdl
    # This descriptive check alone does not satisfy runtime corroboration requirements.


def test_replica_cardinality_is_bounded_before_enumerating_indices(monkeypatch):
    import raes_processor.planner.materialization_admission as admission

    execution, _ = attesting_plan(
        "name: many\nnodes:\n  host: {type: compute}\ninfrastructure:\n  host: {count: 1000000}"
    )
    request = replace(execution.provisioning, operation_id="many")
    previous = RuntimeSnapshot()
    result = ReportingProvisioner(execution.manifest).apply(request, previous)
    enumerated = []

    def bounded_range(count):
        enumerated.append(count)
        raise AssertionError("cardinality must be checked before allocating indices")

    monkeypatch.setattr(admission, "range", bounded_range, raising=False)
    with pytest.raises(ValueError):
        admit_materialization_submission(
            result.materialization_attestation, request, execution.manifest, previous, result.snapshot
        )
    assert not enumerated


@pytest.mark.parametrize("phase", ["orchestration", "evaluation"])
@pytest.mark.parametrize("tampered", [False, True])
def test_later_phase_checks_retained_safe_inventory_without_revealing_values(phase, tampered):
    from raes_contracts.runtime_state import ApplyResult
    from raes_processor.semantics.realization_snapshot_sanitization import sanitize_realization_snapshot

    execution, model = attesting_plan(
        "name: prior-world\nnodes:\n  host:\n    type: compute\n    runtime:\n"
        "      environment: [{name: MODE, value: enabled}]\n"
    )
    provision = replace(execution.provisioning, operation_id="provision")
    reporter = ReportingProvisioner(execution.manifest)
    raw = reporter.apply(provision, RuntimeSnapshot())
    previous = sanitize_realization_snapshot(model.realization_requirements, raw.snapshot)
    entry = previous.entries["provision.node.host"]
    payload = deepcopy(entry.payload)
    environment = payload["spec"]["node"]["runtime"]["environment"][0]
    assert "value" not in environment
    assert "value_commitment" in environment
    if tampered:
        environment["value_commitment"] = "raes-runtime-value-jcs-sha256-v1:sha256:" + "0" * 64
    previous = previous.with_entries({entry.address: replace(entry, payload=payload)})
    request = replace(getattr(execution, phase), operation_id=phase)
    report = reporter.report(request, previous, ApplyResult(True, previous)).materialization_attestation
    if tampered:
        with pytest.raises(ValueError, match="outside its operation domain"):
            admit_materialization_submission(report, request, execution.manifest, previous, previous)
    else:
        admitted = admit_materialization_submission(report, request, execution.manifest, previous, previous)
        assert "value_commitment" not in admitted.sdl
