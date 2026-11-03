"""Portable preparation preserves compiled topology without granting changes."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes_backend_stubs.manifest import load_stub_realization_envelope
from raes_backend_stubs.stubs import StubProvisioner, create_stub_manifest
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.backend_preparation import preparation_response_model
from raes_contracts.contracts.realization_preparation import RealizationPreparation
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan, prepared_delivery_violation, prepared_realization_violation
from raes_processor.semantics.realization_comparison import portable_realization_value
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from test_authored_domain_topology import _parse_payload, _valid_payload


@pytest.fixture
def request_plan():
    manifest = create_stub_manifest(with_realization_envelope=True)
    manifest = replace(
        manifest,
        supported_contract_versions=manifest.supported_contract_versions | {"backend-realization-preparation-v1"},
    )
    payload = _valid_payload()
    payload["nodes"]["dc2"] = {"type": "compute", "os": "windows"}
    payload["relationships"]["dc2-role"] = {
        "type": "domain_controller_for",
        "source": "dc2",
        "target": "corp",
        "domain_controller": {},
    }
    payload["relationships"]["workstation-join"]["domain_join"]["controller_refs"] = ["dc", "dc2"]
    for node in payload["nodes"].values():
        del node["os"]
    compiled = compile_runtime_model(_parse_payload(payload))
    execution = plan(compiled, manifest)
    assert not [diagnostic for diagnostic in execution.diagnostics if diagnostic.is_error], execution.diagnostics
    return execution.provisioning, manifest


def _converted(request, operations=None):
    response = RealizationPreparation.for_request(
        request, RuntimeSnapshot(), operations=tuple(request.operations if operations is None else operations)
    )
    return replace(request, operations=list(preparation_response_model(response).to_runtime().operations))


def test_compiled_topology_survives_preparation_transport(request_plan):
    request, manifest = request_plan
    selected = _converted(request)
    topology_operations = [operation for operation in request.operations if "domain_topology" in operation.payload]
    assert {operation.resource_type for operation in topology_operations} >= {
        "node",
        "account-placement",
        "domain-controller-placement",
    }
    returned = {operation.address: operation for operation in selected.operations}
    for operation in topology_operations:
        before = operation.payload["domain_topology"]
        after = returned[operation.address].payload["domain_topology"]
        assert type(before["controller_addresses"]) is tuple
        assert type(after["controller_addresses"]) is list
        assert canonical_json_digest(before) == canonical_json_digest(after)
    assert prepared_realization_violation(request, selected, manifest) is None
    # The comparison must not rewrite the compiler-produced plan.
    assert all(
        type(operation.payload["domain_topology"]["controller_addresses"]) is tuple for operation in topology_operations
    )


class _PreparingProvisioner(StubProvisioner):
    def __init__(self, *, serialized=False, change=None, delivered_change=None):
        super().__init__(load_stub_realization_envelope())
        self.serialized = serialized
        self.change = change
        self.delivered_change = delivered_change
        self.applies = 0
        self.validates = 0

    def prepare(self, request, previous):
        operations = deepcopy(request.operations)
        if self.change is not None:
            self.change(operations)
        response = RealizationPreparation.for_request(request, previous, operations=tuple(operations))
        return preparation_response_model(response).to_runtime() if self.serialized else response

    def validate(self, selected):
        self.validates += 1
        return []

    def apply(self, selected, previous):
        self.applies += 1
        result = super().apply(selected, previous)
        if self.delivered_change is not None:
            self.delivered_change(list(result.snapshot.entries.values()))
        return result


def _apply(request, manifest, backend):
    previous = RuntimeSnapshot(metadata={"trusted": "predecessor"})
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        address="runtime.test.topology-preparation",
        snapshot=previous,
        realization=_RealizationApplyContext(plan=deepcopy(request), manifest=manifest),
    )
    return previous, result


@pytest.mark.parametrize("serialized", [False, True])
def test_runtime_admits_and_delivers_unchanged_compiled_topology(request_plan, serialized):
    request, manifest = request_plan
    backend = _PreparingProvisioner(serialized=serialized)
    _, result = _apply(request, manifest, backend)
    assert result.success, result.diagnostics
    assert backend.applies == 1
    assert backend.validates == 1
    assert result.snapshot.entries
    assert prepared_delivery_violation(request, result.snapshot) is None


def _change_topology(operations, field, value):
    operation = next(operation for operation in operations if "domain_topology" in operation.payload)
    operation.payload["domain_topology"][field] = value


@pytest.mark.parametrize(
    "field,value",
    [
        ("controller_addresses", ["provision.node.workstation"]),
        ("controller_addresses", []),
        ("controller_addresses", ["provision.node.dc", "provision.node.dc"]),
        ("controller_addresses", "provision.node.dc"),
        ("controller_addresses", {"provision.node.dc"}),
        ("controller_addresses", b"provision.node.dc"),
        ("controller_addresses", [True]),
        ("controller_addresses", [1]),
        ("dns_name", "changed.example"),
        ("role", "member"),
        ("extra", "unexpected"),
    ],
)
def test_changed_or_invalid_preparation_never_reaches_apply(request_plan, field, value):
    request, manifest = request_plan
    backend = _PreparingProvisioner(change=lambda operations: _change_topology(operations, field, value))
    previous, result = _apply(request, manifest, backend)
    assert not result.success
    assert backend.applies == 0
    assert backend.validates == 0
    assert result.snapshot == previous
    assert result.changed_addresses == []
    assert result.details == {}
    assert result.diagnostics[0].code == "runtime.backend-preparation-invalid"


def test_missing_topology_field_is_not_transport_equivalence(request_plan):
    request, manifest = request_plan

    def omit(operations):
        operation = next(operation for operation in operations if "domain_topology" in operation.payload)
        del operation.payload["domain_topology"]["dns_name"]

    backend = _PreparingProvisioner(change=omit)
    previous, result = _apply(request, manifest, backend)
    assert not result.success
    assert backend.applies == 0
    assert result.snapshot == previous


@pytest.mark.parametrize("before,after", [((1,), [True]), ((True,), [1]), ((1,), [1.0])])
def test_nested_scalar_types_remain_exact(request_plan, before, after):
    request, manifest = request_plan
    request = deepcopy(request)
    request.operations[0].payload["comparison_probe"] = {"nested": before}
    selected = _converted(request)
    assert prepared_realization_violation(request, selected, manifest) is None
    selected.operations[0].payload["comparison_probe"]["nested"] = after
    assert prepared_realization_violation(request, selected, manifest) is not None


def test_controller_order_remains_exact(request_plan):
    request, manifest = request_plan
    selected = _converted(request)
    assert prepared_realization_violation(request, selected, manifest) is None
    member = next(operation for operation in selected.operations if operation.address == "provision.node.workstation")
    controllers = member.payload["domain_topology"]["controller_addresses"]
    assert len(controllers) == 2
    controllers.reverse()
    assert prepared_realization_violation(request, selected, manifest) is not None


@pytest.mark.parametrize("value", [{"controller"}, b"controller", {1: "controller"}, float("nan"), float("inf")])
def test_comparison_rejects_invalid_values_before_codec_coercion(value):
    with pytest.raises(ValueError, match="bounded portable value"):
        portable_realization_value({"nested": (value,)})


def test_comparison_rejects_cyclic_values():
    value = []
    value.append(value)
    with pytest.raises(ValueError, match="bounded portable value"):
        portable_realization_value(value)


def test_changed_delivery_is_rejected_after_successful_preparation(request_plan):
    request, manifest = request_plan
    backend = _PreparingProvisioner(
        delivered_change=lambda entries: _change_topology(entries, "dns_name", "changed.example")
    )
    previous, result = _apply(request, manifest, backend)
    assert backend.applies == 1
    assert not result.success
    assert result.snapshot == previous
    assert result.changed_addresses == []
    assert result.details == {}
    assert result.diagnostics[0].code == "runtime.backend-contract-invalid"
