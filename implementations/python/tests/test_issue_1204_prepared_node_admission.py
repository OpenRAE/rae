"""Prepared additions pass the incumbent capability and dependency owners."""

from dataclasses import replace

import pytest
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from test_issue_1204_resource_collections import _collection_request, _isolated_designation, _PreparingNodes


@pytest.mark.parametrize(
    "mutation", ["unsupported-runtime", "unknown-count", "self-dependency", "missing-namespace-binding"]
)
def test_inadmissible_prepared_node_never_reaches_apply(mutation):
    request, manifest = _collection_request(_isolated_designation(True))

    class InvalidPreparation(_PreparingNodes):
        def prepare(self, request, snapshot):
            response = super().prepare(request, snapshot)
            extra = response.operations[-1]
            if mutation == "unsupported-runtime":
                extra.payload["spec"]["node"]["runtime"] = {"container": {"privileged": True}}
            elif mutation == "unknown-count":
                extra.payload["count"] = extra.payload["spec"]["infrastructure"]["count"] = "${unresolved_count}"
            elif mutation == "self-dependency":
                extra = replace(extra, ordering_dependencies=(extra.address,), refresh_dependencies=(extra.address,))
            else:
                extra.payload["spec"]["node"]["runtime"] = {
                    "container": {"namespaces": {"network": {"target_node_ref": "nodes.n0"}}},
                }
            return replace(response, operations=(*response.operations[:-1], extra))

    backend = InvalidPreparation(manifest)
    previous = RuntimeSnapshot(metadata={"trusted": "previous"})
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.node-capability",
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    assert not result.success
    assert backend.applies == 0
    assert result.snapshot == previous
    assert result.diagnostics[0].code == "runtime.backend-preparation-invalid"


def test_supported_runtime_choice_on_an_additional_node_is_delivered():
    from raes_processor.planner.realization_preparation import preparation_authority

    request, manifest = _collection_request(_isolated_designation(True))
    manifest = replace(
        manifest,
        realization_support=tuple(
            replace(
                support,
                supported_exact_requirement_kinds=support.supported_exact_requirement_kinds
                | {"runtime-container-privileged"},
            )
            for support in manifest.realization_support
        ),
    )
    request = replace(
        request,
        preparation=preparation_authority(manifest).model_copy(
            update={
                "node_collection": request.preparation.node_collection,
            }
        ),
    )

    class SupportedRuntime(_PreparingNodes):
        def prepare(self, request, snapshot):
            response = super().prepare(request, snapshot)
            response.operations[-1].payload["spec"]["node"]["runtime"] = {"container": {"privileged": True}}
            return response

    backend = SupportedRuntime(manifest)
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.supported-node",
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    assert result.success, result.diagnostics
    assert backend.applies == 1
    assert (
        result.snapshot.entries["provision.node.extra"].payload["spec"]["node"]["runtime"]["container"]["privileged"]
        is True
    )


def test_retained_additions_are_rechecked_against_changed_capability_limits():
    from raes import parse_sdl
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.planner import plan

    request, manifest = _collection_request(_isolated_designation(True))
    previous = RuntimeSnapshot()
    backend = _PreparingNodes(manifest)
    first = _call_backend_apply(
        backend.apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.retained-node",
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    assert first.success, first.diagnostics
    smaller = replace(
        manifest,
        capabilities=replace(manifest.capabilities, provisioner=replace(manifest.provisioner, max_total_nodes=5)),
    )
    source = "name: retained-node\n" + _isolated_designation(True) + "\nnodes:\n"
    source += "\n".join(f"  n{index}: {{type: compute}}" for index in range(5))
    execution = plan(compile_runtime_model(parse_sdl(source)), smaller, first.snapshot)
    assert execution.is_valid, execution.diagnostics
    backend = _PreparingNodes(smaller, add=False)
    result = _call_backend_apply(
        backend.apply,
        execution.provisioning,
        first.snapshot,
        snapshot=first.snapshot,
        address="runtime.retained-node",
        realization=_RealizationApplyContext(plan=execution.provisioning, manifest=smaller),
    )
    assert not result.success
    assert backend.applies == 0
    assert result.snapshot == first.snapshot
    assert result.diagnostics[0].code == "runtime.backend-preparation-invalid"


def test_invalid_collection_binding_is_rejected_before_preparation_callback():
    request, manifest = _collection_request(_isolated_designation(True))
    authority = request.preparation.node_collection.model_copy(update={"constraint_binding": "sha256:" + "a" * 64})
    request = replace(request, preparation=request.preparation.model_copy(update={"node_collection": authority}))
    calls = []

    class UncalledPreparation(_PreparingNodes):
        def prepare(self, request, snapshot):
            calls.append("prepare")
            return super().prepare(request, snapshot)

    previous = RuntimeSnapshot()
    backend = UncalledPreparation(manifest)
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.collection-binding",
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    assert not result.success
    assert calls == []
    assert backend.applies == 0
