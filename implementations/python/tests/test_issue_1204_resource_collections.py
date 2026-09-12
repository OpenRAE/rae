"""Only enclosing, authenticated collection authority can permit new nodes."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_contracts.contracts import ProvisioningPlanModel
from raes_contracts.plan_projection import provisioning_plan_model, runtime_plan_digest
from raes_contracts.realization_structure import evaluate_realization_constraint
from raes_contracts.vocabulary import RealizationSupportMode
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.control_plane_api_models import _provisioning_plan
from test_sem_218_realization_designation import _manifest


def _collection_request(designation):
    source = "name: collection-admission\n" + designation + "\nnodes:\n"
    source += "\n".join(f"  n{index}: {{type: compute}}" for index in range(5))
    base = _manifest(RealizationSupportMode.OPEN_REALIZATION)
    manifest = replace(
        base,
        supported_contract_versions=base.supported_contract_versions
        | {
            "backend-realization-preparation-v1",
        },
    )
    execution = plan(compile_runtime_model(parse_sdl(source)), manifest)
    assert execution.is_valid, execution.diagnostics
    return execution.provisioning, manifest


@pytest.mark.parametrize(
    "designation,allows_extra",
    [
        ("realization:\n  default: closed", False),
        ("realization:\n  default: closed\n  scopes:\n    - {field_pointer: /nodes, posture: open}", True),
        ("realization:\n  default: closed\n  scopes:\n    - {field_pointer: /nodes/n0/runtime, posture: open}", False),
    ],
)
def test_only_enclosing_collection_openness_admits_a_sixth_member(designation, allows_extra):
    from raes_contracts.realization_collections import node_collection_members

    request, _ = _collection_request(designation)
    authority = request.preparation.node_collection
    assert authority.scope_pointer == "/nodes"
    authored = node_collection_members(request.operations)
    assert len(authored[""]) == 5
    assert evaluate_realization_constraint(authority.constraint_document, authored).conformant
    actual = {"": [*authored[""], {"address": "provision.node.extra", "resource_type": "node", "name": "extra"}]}
    assert evaluate_realization_constraint(authority.constraint_document, actual).conformant is allows_extra
    changed = deepcopy(authored)
    changed[""][0]["name"] = "renamed"
    assert not evaluate_realization_constraint(authority.constraint_document, changed).conformant


def test_collection_authority_roundtrip_is_in_the_authenticated_plan_commitment():
    request, _ = _collection_request(
        "realization:\n  default: closed\n  scopes:\n    - {field_pointer: /nodes, posture: open}"
    )
    wire = provisioning_plan_model(request).model_dump(mode="json", exclude_none=True)
    restored = _provisioning_plan(ProvisioningPlanModel.model_validate(wire))
    assert restored.preparation.node_collection == request.preparation.node_collection
    assert runtime_plan_digest(restored) == runtime_plan_digest(request)
    wire["preparation"]["node_collection"] = None
    tampered = _provisioning_plan(ProvisioningPlanModel.model_validate(wire))
    assert runtime_plan_digest(tampered) != runtime_plan_digest(request)


def _isolated_designation(opened):
    if not opened:
        return "realization:\n  default: closed"
    lines = ["realization:", "  default: closed", "  scopes:", "    - {field_pointer: /nodes, posture: open}"]
    lines.extend(f"    - {{field_pointer: /nodes/n{index}, posture: closed}}" for index in range(5))
    return "\n".join(lines)


class _PreparingNodes:
    def __init__(self, manifest, *, add=True, unsupported=False):
        from raes_backend_stubs.stubs import StubProvisioner

        self.backend = StubProvisioner(manifest.realization_envelope)
        self.add = add
        self.unsupported = unsupported
        self.applies = 0

    def prepare(self, request, snapshot):
        from raes_contracts.realization_preparation import RealizationPreparation

        operations = deepcopy(request.operations)
        if self.add:
            payload = deepcopy(operations[0].payload)
            payload.update(
                name="extra", node_name="extra", os_family="linux", os_distribution="ubuntu", os_version="22.04"
            )
            payload["spec"]["node"].update(os="linux", os_distribution="ubuntu", os_version="22.04")
            if self.unsupported:
                payload.update(os_family="windows", os_distribution="windows-server", os_version="2022")
                payload["spec"]["node"].update(os="windows", os_distribution="windows-server", os_version="2022")
            operations.append(replace(operations[0], address="provision.node.extra", payload=payload))
        return RealizationPreparation.for_request(request, snapshot, operations=tuple(operations))

    def validate(self, request):
        return []

    def apply(self, request, snapshot):
        self.applies += 1
        return self.backend.apply(request, snapshot)


@pytest.mark.parametrize(
    "opened,add,unsupported,accepted",
    [
        (False, False, False, True),
        (False, True, False, False),
        (True, True, False, True),
        (True, True, True, False),
    ],
)
def test_prepared_nodes_require_enclosing_membership_and_known_capability_before_apply(
    opened, add, unsupported, accepted
):
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext

    request, manifest = _collection_request(_isolated_designation(opened))
    backend = _PreparingNodes(manifest, add=add, unsupported=unsupported)
    previous = RuntimeSnapshot(metadata={"trusted": "predecessor"})
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.prepared-nodes",
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    assert result.success is accepted, result.diagnostics
    assert backend.applies == int(accepted)
    if accepted:
        assert len(result.snapshot.entries) == 5 + int(add)
    else:
        assert result.snapshot == previous
        assert result.diagnostics[0].code == "runtime.backend-preparation-invalid"


@pytest.mark.parametrize("mutation", ["count", "os_version", "unprepared-node"])
def test_prepared_extra_node_delivery_cannot_change_the_admitted_completion(mutation):
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext

    request, manifest = _collection_request(_isolated_designation(True))

    class ChangedDelivery(_PreparingNodes):
        def apply(self, selected, snapshot):
            result = super().apply(selected, snapshot)
            if mutation == "unprepared-node":
                result.snapshot.entries["provision.node.unprepared"] = replace(
                    result.snapshot.entries["provision.node.extra"],
                    address="provision.node.unprepared",
                )
                result.changed_addresses.append("provision.node.unprepared")
            else:
                result.snapshot.entries["provision.node.extra"].payload[mutation] = (
                    2 if mutation == "count" else "20.04"
                )
            return result

    backend = ChangedDelivery(manifest)
    previous = RuntimeSnapshot(metadata={"trusted": "predecessor"})
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.prepared-nodes",
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    assert backend.applies == 1
    assert not result.success
    assert result.snapshot == previous
    assert result.diagnostics[0].message == (
        "Backend added a resource without admitted collection authority."
        if mutation == "unprepared-node"
        else "Backend did not deliver its admitted portable node completion."
    )


@pytest.mark.parametrize("namespace,accepted", [("", True), ("closedmod.", False), ("openmod.", True)])
def test_preparation_respects_imported_collection_closure(tmp_path, namespace, accepted):
    from raes import instantiate_scenario, parse_sdl_file
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext

    for module, posture in (("closedmod", "closed"), ("openmod", "open")):
        (tmp_path / f"{module}.yaml").write_text(
            f"name: {module}\nversion: 1.0.0\nmodule:\n  id: acme/{module}\n  version: 1.0.0\n"
            "  exports: {nodes: [worker]}\nrealization:\n  default: closed\n  scopes:\n"
            f"    - {{field_pointer: /nodes, posture: {posture}}}\n"
            "    - {field_pointer: /nodes/worker, posture: closed}\nnodes:\n  worker: {type: compute}\n",
            encoding="utf-8",
        )
    root = tmp_path / "root.yaml"
    root.write_text(
        "name: namespace-authority\nrealization:\n  default: closed\n  scopes:\n"
        "    - {field_pointer: /nodes, posture: open}\n"
        "imports:\n  - {source: local:closedmod.yaml, namespace: closedmod}\n"
        "  - {source: local:openmod.yaml, namespace: openmod}\n",
        encoding="utf-8",
    )
    _, manifest = _collection_request(_isolated_designation(True))
    execution = plan(compile_runtime_model(instantiate_scenario(parse_sdl_file(root))), manifest)
    assert execution.is_valid, execution.diagnostics

    class NamespacedPreparation(_PreparingNodes):
        def prepare(self, request, snapshot):
            response = super().prepare(request, snapshot)
            extra = response.operations[-1]
            name = namespace + "extra"
            extra.payload.update(name=name, node_name=name)
            return replace(
                response, operations=(*response.operations[:-1], replace(extra, address=f"provision.node.{name}"))
            )

    backend = NamespacedPreparation(manifest)
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        backend.apply,
        execution.provisioning,
        previous,
        snapshot=previous,
        address="runtime.namespace-collection",
        realization=_RealizationApplyContext(plan=execution.provisioning, manifest=manifest),
    )
    assert result.success is accepted, result.diagnostics
    assert backend.applies == int(accepted)


def test_open_collection_retains_prepared_nodes_until_closure_is_revoked():
    from raes_contracts.planning import ChangeAction
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext

    request, manifest = _collection_request(_isolated_designation(True))
    backend = _PreparingNodes(manifest)
    previous = RuntimeSnapshot()
    first = _call_backend_apply(
        backend.apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.collection-reconcile",
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    assert first.success, first.diagnostics
    for opened in (True, False):
        source = "name: collection-admission\n" + _isolated_designation(opened) + "\nnodes:\n"
        source += "\n".join(f"  n{index}: {{type: compute}}" for index in range(5))
        execution = plan(compile_runtime_model(parse_sdl(source)), manifest, first.snapshot)
        assert execution.is_valid, execution.diagnostics
        deletions = {
            operation.address
            for operation in execution.provisioning.operations
            if operation.action is ChangeAction.DELETE
        }
        assert ("provision.node.extra" not in deletions) is opened
        retaining_backend = _PreparingNodes(manifest, add=False)
        result = _call_backend_apply(
            retaining_backend.apply,
            execution.provisioning,
            first.snapshot,
            snapshot=first.snapshot,
            address="runtime.collection-reconcile",
            realization=_RealizationApplyContext(plan=execution.provisioning, manifest=manifest),
        )
        assert result.success, result.diagnostics
        assert ("provision.node.extra" in result.snapshot.entries) is opened
