"""Optional node identity survives compilation, projection, and runtime admission."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest
from issue_1629_trial_fixture import TrialServices
from raes import admit_scenario_family, parse_sdl
from raes_backend_stubs.manifest import load_stub_realization_envelope
from raes_backend_stubs.stubs import create_stub_components
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ProvisioningPlanModel
from raes_contracts.contracts.plan_projection import provisioning_plan_model, runtime_plan_digest
from raes_contracts.errors import ConflictError, InvalidInputError
from raes_contracts.realization_structure import realization_constraint_binding
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan, realization_authority_diagnostics
from raes_processor.planner.prepared_node_admission import validate_portable_node_inventory
from raes_processor.planner.realization_preparation import prepared_realization_violation
from raes_processor.semantics.realization_concerns import project_realization_concern
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_realization import realize_admitted_trial_entry
from raes_runtime import RuntimeControlPlane
from raes_runtime.control_plane_api_models import _provisioning_plan
from raes_runtime.registry import RuntimeTarget
from test_sce_002_trial_realization import _realization_inputs, _request_with_processor

_ADDRESS = "provision.node.primary"
_IDENTITIES = (("os_distribution", "os-distribution"), ("architecture", "node-architecture"))
_CASES = [
    pytest.param({}, (None, None), id="both-omitted"),
    pytest.param({"architecture": "x86_64"}, (None, "x86_64"), id="distribution-omitted"),
    pytest.param({"os_distribution": "ubuntu"}, ("ubuntu", None), id="architecture-omitted"),
    pytest.param({"os_distribution": "ubuntu", "architecture": "x86_64"}, ("ubuntu", "x86_64"), id="explicit"),
    pytest.param({"os_distribution": "Ubuntu", "architecture": "amd64"}, ("ubuntu", "x86_64"), id="aliases"),
]


def _source(identity):
    return json.dumps(
        {
            "name": "compiler-family",
            "nodes": {"primary": {"type": "compute", "os": "linux", **identity}},
            "infrastructure": {"primary": {"count": 1}},
        }
    )


@pytest.mark.parametrize("identity,expected", _CASES)
def test_identity_values_and_recursive_commitments_survive_plan_roundtrip(identity, expected):
    _, target, realized = _trial(identity)
    scenario = realized.instantiated
    model = compile_runtime_model(scenario)
    execution = plan(model, target.manifest)
    assert execution.is_valid, execution.diagnostics
    provisioning = execution.provisioning
    operation = next(operation for operation in provisioning.operations if operation.address == _ADDRESS)
    restored = _provisioning_plan(
        ProvisioningPlanModel.model_validate_json(provisioning_plan_model(provisioning).model_dump_json())
    )
    assert runtime_plan_digest(restored) == runtime_plan_digest(provisioning)

    for (field, kind), value in zip(_IDENTITIES, expected, strict=True):
        assert getattr(scenario.nodes["primary"], field) == value
        assert getattr(model.node_deployments[_ADDRESS], field) == value
        assert provisioning.resources[_ADDRESS].payload[field] == value
        assert operation.payload[field] == value
        restored_operation = next(operation for operation in restored.operations if operation.address == _ADDRESS)
        assert field in restored_operation.payload
        assert restored_operation.payload[field] == value
        authority = next(entry for entry in provisioning.realization_authority if entry.requirement_kind == kind)
        assert authority.constraint_document is not None
        projected = project_realization_concern(kind, operation.payload[field], recursive=True)
        assert realization_constraint_binding(authority.constraint_document, projected) == authority.constraint_binding
    assert realization_authority_diagnostics(provisioning, execution.manifest) == []
    assert realization_authority_diagnostics(restored, execution.manifest) == []


def _trial(identity):
    request = _request_with_processor().with_family(admit_scenario_family(parse_sdl(_source(identity))))
    experiment = request.experiment.model_dump(mode="json")
    experiment["run_plan"].update(target_run_count=1, selection_policies={}, stochastic_controls=[])
    request = request.with_experiment(type(request.experiment).model_validate(experiment))
    envelope = load_stub_realization_envelope()
    backend_key = next(key for key in request.apparatus_manifests if key[0] == "backend")
    manifest = request.apparatus_manifests[backend_key].model_copy(update={"realization_envelope": envelope.identity})
    refs = [
        ref.model_copy(update={"ref_digest": canonical_json_digest(manifest.model_dump(mode="json"))})
        if ref.subject_ref.ref_kind == "backend"
        else ref
        for ref in request.apparatus.manifest_refs
    ]
    request = replace(
        request,
        realization_envelope=envelope,
        apparatus_manifests={**request.apparatus_manifests, backend_key: manifest},
        apparatus=request.apparatus.model_copy(
            update={"realization_envelope": envelope.identity, "manifest_refs": refs}
        ),
    )
    compiled = compile_admitted_trial_plan(request)
    assert compiled.plan is not None, compiled.diagnostics
    assert len(compiled.plan.entries) == 1
    inputs = _realization_inputs(request, compiled.plan, request.task)
    realized = realize_admitted_trial_entry(
        inputs=inputs, plan_entry_id=next(iter(compiled.plan.entries)), target_name="identity"
    )
    assert realized.execution_plan.is_valid, realized.execution_plan.diagnostics
    manifest = realized.execution_plan.manifest
    target = RuntimeTarget(name="identity", manifest=manifest, **vars(create_stub_components(manifest=manifest)))
    return inputs, target, realized


@pytest.mark.parametrize("identity,expected", _CASES)
def test_fixed_control_only_trial_passes_public_runtime_admission(identity, expected):
    inputs, target, _ = _trial(identity)
    services = TrialServices(target)
    with RuntimeControlPlane(target) as runtime:
        assert runtime.admit_experiment(inputs, services=services)
        assert services.live == {}


@pytest.mark.parametrize("identity,expected", _CASES)
def test_prepared_node_preserves_nullable_identity_without_rewriting_payload(identity, expected):
    _, target, realized = _trial(identity)
    provisioning = realized.execution_plan.provisioning
    before = deepcopy(provisioning)
    assert prepared_realization_violation(provisioning, provisioning, target.manifest) is None
    operation = next(operation for operation in provisioning.operations if operation.address == _ADDRESS)
    validate_portable_node_inventory({_ADDRESS: operation}, set(), target.manifest, added=(operation,))
    assert provisioning == before


@pytest.mark.parametrize("field,kind", _IDENTITIES)
def test_prepared_node_rejects_identity_that_differs_from_its_typed_specification(field, kind):
    _, target, realized = _trial({})
    operation = deepcopy(realized.execution_plan.provisioning.operations[0])
    operation.payload[field] = {"os_distribution": "ubuntu", "architecture": "x86_64"}[field]
    with pytest.raises(InvalidInputError, match="identity differs"):
        validate_portable_node_inventory({_ADDRESS: operation}, set(), target.manifest, added=(operation,))


@pytest.mark.parametrize("field,kind", _IDENTITIES)
@pytest.mark.parametrize("substitution", ["", "supported", "binding"])
def test_inconsistent_identity_is_refused_before_experiment_admission(monkeypatch, field, kind, substitution):
    import raes_runtime.runtime_experiment as experiment_module

    inputs, target, _ = _trial({})
    original = experiment_module.realize_admitted_trial_entry

    def substituted(**kwargs):
        realized = original(**kwargs)
        provisioning = deepcopy(realized.execution_plan.provisioning)
        operation = next(operation for operation in provisioning.operations if operation.address == _ADDRESS)
        if substitution == "binding":
            provisioning = replace(
                provisioning,
                realization_authority=tuple(
                    replace(item, constraint_binding="sha256:" + "0" * 64) if item.requirement_kind == kind else item
                    for item in provisioning.realization_authority
                ),
            )
        else:
            operation.payload[field] = (
                {"os_distribution": "ubuntu", "architecture": "aarch64"}[field]
                if substitution == "supported"
                else substitution
            )
        assert [diagnostic.code for diagnostic in realization_authority_diagnostics(provisioning)] == [
            "realization.authority-selection-invalid"
        ]
        return replace(realized, execution_plan=replace(realized.execution_plan, provisioning=provisioning))

    monkeypatch.setattr(experiment_module, "realize_admitted_trial_entry", substituted)
    services = TrialServices(target)
    with RuntimeControlPlane(target) as runtime:
        with pytest.raises(ConflictError, match="realization.authority-selection-invalid"):
            runtime.admit_experiment(inputs, services=services)
        assert services.live == {}
        assert not runtime.audit_log()
        assert not runtime._store.load_runtime_decisions()
