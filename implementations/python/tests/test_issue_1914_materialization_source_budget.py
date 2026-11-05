"""Dense SDL documents use a bounded document budget through delivery (#1914)."""

import json
from dataclasses import replace

import pytest
from pydantic import ValidationError
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.materialization import MATERIALIZATION_MAX_BYTES, MaterializationSource
from raes_contracts.realization_structure import validate_realization_value
from raes_contracts.runtime_value_limits import MATERIALIZATION_VALUE_LIMITS, RUNTIME_SNAPSHOT_VALUE_LIMITS
from test_issue_1241_materialization_context import attesting_plan
from test_issue_1241_materialization_runtime import _apply


@pytest.fixture(autouse=True)
def environment_backend(monkeypatch):
    import test_issue_1241_materialization_context as context
    import test_issue_1241_materialization_runtime as runtime
    from raes_contracts.apparatus import RealizationObservationCapability
    from raes_contracts.realization_observation import RealizationObservationDisclosure
    from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope

    original_manifest = context._manifest
    original_apply = runtime.ReportingProvisioner.apply

    def manifest(mode):
        base = original_manifest(mode)
        return replace(
            base,
            realization_support=tuple(
                replace(
                    support,
                    supported_exact_requirement_kinds=support.supported_exact_requirement_kinds
                    | {"runtime-environment"},
                    observation_capabilities={
                        **support.observation_capabilities,
                        "runtime-environment": RealizationObservationCapability(
                            verification_scope=RealizationVerificationScope.CONFIGURATION,
                            observation_strength=ObservationStrength.GUEST_OBSERVED,
                        ),
                    },
                )
                for support in base.realization_support
            ),
        )

    def apply(self, request, previous):
        result = original_apply(self, request, previous)
        disclosures = tuple(
            RealizationObservationDisclosure(
                address=op.address,
                field_path=f"nodes.{op.address.removeprefix('provision.node.')}.runtime.environment",
                domain="runtime-realization",
                requirement_kind="runtime-environment",
                verification_scope=RealizationVerificationScope.CONFIGURATION,
                observation_strength=ObservationStrength.GUEST_OBSERVED,
            )
            for op in request.operations
        )
        return replace(result, snapshot=replace(result.snapshot, realization_observations=disclosures))

    monkeypatch.setattr(context, "_manifest", manifest)
    monkeypatch.setattr(runtime.ReportingProvisioner, "apply", apply)


def dense_source(count):
    return json.dumps(
        {
            "name": "source-budget-repro",
            "nodes": {
                ("host" if i == 0 else f"node-{i}"): {
                    "type": "compute",
                    "runtime": {
                        "environment": [
                            {
                                "name": f"MODE_{j}",
                                "value": "fixture",
                                "value_classification": "plain",
                                "provenance": "runtime",
                                "source": "fixture",
                            }
                            for j in range(50)
                        ]
                    },
                }
                for i in range(count)
            },
        }
    )


@pytest.mark.parametrize("count", [32, 64])
def test_dense_source_planning_and_report_admission(tmp_path, count):
    execution, _ = attesting_plan(dense_source(count))
    assert execution.is_valid, execution.diagnostics
    source = execution.provisioning.materialization_source
    assert 1048576 < len(source.snapshot.encode()) < MATERIALIZATION_MAX_BYTES
    payload = json.loads(source.snapshot)
    assert not validate_realization_value(payload, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS).conformant
    assert validate_realization_value(payload, limits=MATERIALIZATION_VALUE_LIMITS).conformant

    def bind_all_nodes(document):
        document["materialization_provenance"]["resource_bindings"] = [
            {"address": f"provision.node.{name}", "node_name": name, "source_node": name, "instance_index": 0}
            for name in document["nodes"]
        ]

    result, backend = _apply(tmp_path, source=dense_source(count), mutate=bind_all_nodes)
    assert result.success, result.diagnostics
    assert backend.calls == 1
    assert len(result.snapshot.materialization_attestations) == 1
    wrong_instantiated = {**source.model_dump(), "instantiated_digest": "sha256:" + "0" * 64}
    wrong_authored = {**source.model_dump(), "authored_digest": "sha256:" + "0" * 64}
    with pytest.raises(ValidationError, match="instantiated identity"):
        MaterializationSource.model_validate(wrong_instantiated)
    with pytest.raises(ValidationError, match="authored identity"):
        MaterializationSource.model_validate(wrong_authored)


def test_dense_source_over_byte_limit_is_refused():
    from test_issue_1742_bounded_materialization_source import _full_size_source

    execution, _ = attesting_plan(_full_size_source(entities=1500))
    assert not execution.is_valid
    assert "materialization.source-limit-exceeded" in {d.code for d in execution.diagnostics}


@pytest.mark.parametrize("content", [[[None] * 1024 for _ in range(257)], [None] * 65537], ids=["nodes", "members"])
def test_source_over_work_limit_is_refused(content):
    execution, _ = attesting_plan()
    source = execution.provisioning.materialization_source
    payload = json.loads(source.snapshot)
    # Small scalars in bounded collections exhaust nodes before the document byte limit.
    payload["scenario"]["description"] = content
    snapshot = json.dumps(payload, separators=(",", ":"))
    assert len(snapshot.encode()) < MATERIALIZATION_MAX_BYTES
    oversized = {**source.model_dump(), "snapshot": snapshot, "instantiated_digest": canonical_json_digest(payload)}
    with pytest.raises(ValidationError, match="portable bounds"):
        MaterializationSource.model_validate(oversized)
