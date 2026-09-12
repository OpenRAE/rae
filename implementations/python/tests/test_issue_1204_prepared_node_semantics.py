"""Portable additions must satisfy native references before backend mutation."""

from dataclasses import replace

import pytest
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.planner.realization_preparation import preparation_authority
from raes_processor.semantics.realization_concerns import realization_concern_descriptors
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from test_issue_1204_resource_collections import _collection_request, _isolated_designation, _PreparingNodes


@pytest.mark.parametrize(
    "mutation", ["cpu-variable", "missing-service", "missing-artifact", "missing-acl-network", "valid-service"]
)
def test_prepared_node_native_semantic_failure_precedes_apply(mutation):
    request, manifest = _collection_request(_isolated_designation(True))
    manifest = replace(
        manifest,
        realization_support=tuple(
            replace(
                support,
                supported_exact_requirement_kinds=support.supported_exact_requirement_kinds
                | {descriptor.concern_kind for descriptor in realization_concern_descriptors()},
            )
            for support in manifest.realization_support
        ),
    )
    request = replace(
        request,
        preparation=preparation_authority(manifest).model_copy(
            update={"node_collection": request.preparation.node_collection}
        ),
    )

    class InvalidSemantics(_PreparingNodes):
        def prepare(self, request, snapshot):
            response = super().prepare(request, snapshot)
            spec = response.operations[-1].payload["spec"]
            if mutation == "cpu-variable":
                spec["node"]["resources"] = {"ram": 1024, "cpu": "${unresolved_cpu}"}
            elif mutation in {"missing-service", "valid-service"}:
                spec["node"]["runtime"] = {
                    "database_services": [{"database_service_id": "db", "engine": "sqlite", "service": "database"}]
                }
                if mutation == "valid-service":
                    spec["node"]["services"] = [{"name": "database", "port": 5432}]
            elif mutation == "missing-artifact":
                spec["node"]["runtime"] = {
                    "environment": [
                        {
                            "name": "MODE",
                            "value_classification": "plain",
                            "provenance": "runtime",
                            "value_from": {"generated_artifact": "generated_artifacts.absent", "output": "mode"},
                        }
                    ]
                }
            else:
                spec["infrastructure"]["acls"] = [{"from_net": "absent-network", "to_net": "absent-network"}]
            return response

    backend = InvalidSemantics(manifest)
    previous = RuntimeSnapshot(metadata={"trusted": "predecessor"})
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.prepared-native-semantics",
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    assert result.success is (mutation == "valid-service"), result.diagnostics
    assert backend.applies == int(mutation == "valid-service")
    if result.success:
        assert (
            result.snapshot.entries["provision.node.extra"].payload["spec"]["node"]["services"][0]["name"] == "database"
        )
        return
    assert result.snapshot == previous
    assert result.diagnostics[0].code == "runtime.backend-preparation-invalid"


def test_prepared_node_context_accepts_existing_compiler_owned_artifact_delivery():
    from raes import parse_sdl
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.planner.prepared_node_semantics import validate_prepared_node_semantics
    from raes_processor.planner.resources import _collect_resources
    from test_issue_1074_generated_artifact_env_consumers import _ENV_SCALAR, _scenario

    model = compile_runtime_model(parse_sdl(_scenario(environment=_ENV_SCALAR)))
    live = _collect_resources(model)
    validate_prepared_node_semantics(live)
    node = live["provision.node.cortex"]
    node.payload["spec"]["node"]["runtime"] = live["provision.node.thehive"].payload["spec"]["node"]["runtime"]
    with pytest.raises(ValueError, match="delivery authority"):
        validate_prepared_node_semantics(live)


@pytest.mark.parametrize("service,accepted", [("database", True), ("missing", False)])
def test_preparation_validates_original_node_references_not_only_additions(service, accepted):
    from raes import parse_sdl
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.planner import plan
    from test_issue_1200_mixed_runtime_constraints import _fixture
    from test_issue_1204_backend_preparation import _PreparingBackend

    source = """
name: selected-original-node
variables:
  service_name:
    type: string
    default: database
    allowed_values: [database, missing]
nodes:
  host:
    type: compute
    services: [{name: database, port: 5432}]
    runtime:
      database_services:
        - {database_service_id: db, engine: sqlite, service: '${service_name}'}
"""
    _, _, manifest = _fixture({"database_services": [{"database_service_id": "db", "engine": "sqlite"}]})
    manifest = replace(
        manifest,
        supported_contract_versions=manifest.supported_contract_versions | {"backend-realization-preparation-v1"},
    )
    execution = plan(compile_runtime_model(parse_sdl(source)), manifest)
    assert execution.is_valid, execution.diagnostics

    class SelectingReference(_PreparingBackend):
        def prepare(self, request, snapshot):
            response = super().prepare(request, snapshot)
            response.operations[0].payload["spec"]["node"]["runtime"]["database_services"][0]["service"] = service
            return response

    backend = SelectingReference()
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        backend.apply,
        execution.provisioning,
        previous,
        snapshot=previous,
        address="runtime.selected-references",
        realization=_RealizationApplyContext(plan=execution.provisioning, manifest=manifest),
    )
    assert result.success is accepted, result.diagnostics
    assert backend.applies == int(accepted)
    if not accepted:
        assert result.snapshot == previous
