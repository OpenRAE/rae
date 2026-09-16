"""Enforcement precedes mutation and post-apply descriptions cannot widen it."""

import json
from dataclasses import replace

import pytest
from raes_backend_protocols.augmentation import augmentation_preparation
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_operations.run_artifacts import RunMaterializationArchive
from raes_runtime.backend_calls import _BackendCallContext, _call_backend_apply, _RealizationApplyContext
from test_issue_1241_materialization_runtime import ReportingProvisioner
from test_issue_1242_scope_admission import scoped_plan


class ScopeReportingProvisioner(ReportingProvisioner):
    def __init__(self, manifest, *, addition=False, unreported=False):
        self.addition = addition
        self.preparations = 0
        super().__init__(
            manifest, self.add_listener if addition or unreported else None, realize=addition or unreported
        )

    @staticmethod
    def add_listener(document):
        document["nodes"]["host"]["services"] = [{"name": "metrics", "port": 9090}]

    def prepare_augmentation(self, request, previous):
        from raes_contracts.augmentation_preparation import AugmentationEffect

        self.preparations += 1
        document = json.loads(request.materialization_source.snapshot)["scenario"]
        document.pop("instantiation_provenance")
        effects = ()
        if self.addition:
            self.add_listener(document)
            effects = (
                AugmentationEffect(
                    field_pointer="/nodes/host/services/0",
                    requirement_refs=("backend-operational",),
                    affected_scopes=("/nodes/host",),
                ),
            )
        return augmentation_preparation(request, self.manifest, previous, content=json.dumps(document), effects=effects)


def apply(tmp_path, policy, *, addition=False, unreported=False, unsupported=False):
    execution = scoped_plan(policy)
    backend = (
        ReportingProvisioner(execution.manifest)
        if unsupported
        else ScopeReportingProvisioner(execution.manifest, addition=addition, unreported=unreported)
    )
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        backend.apply,
        execution.provisioning,
        previous,
        snapshot=previous,
        address="runtime.scoped",
        realization=_RealizationApplyContext(plan=execution.provisioning, manifest=execution.manifest),
        call=_BackendCallContext(materialization_archive=RunMaterializationArchive(tmp_path)),
    )
    return result, backend


def test_closed_scope_refuses_needed_addition_before_apply_or_archive(tmp_path):
    result, backend = apply(tmp_path, {"default": "closed"}, addition=True)
    assert not result.success
    assert backend.calls == 0
    assert not result.snapshot.entries
    assert not list(tmp_path.iterdir())
    diagnostic = next(item for item in result.diagnostics if item.code == "augmentation.scope-closed")
    assert "backend-operational" in diagnostic.message
    assert "/nodes/host/services/0" in diagnostic.message


@pytest.mark.parametrize("policy", [None, {"default": "open"}])
def test_open_permission_reaches_apply_and_archives_actual_effects(tmp_path, policy):
    result, backend = apply(tmp_path, policy, addition=True)
    assert result.success, result.diagnostics
    assert backend.preparations == 1
    assert backend.calls == 1
    assert result.snapshot.materialization_attestations


def test_closed_scope_with_no_extra_effects_is_not_an_execution_ban(tmp_path):
    result, backend = apply(tmp_path, {"default": "closed"})
    assert result.success, result.diagnostics
    assert backend.preparations == 1
    assert backend.calls == 1


def test_missing_preparation_fails_before_apply_even_when_manifest_claims_support(tmp_path):
    result, backend = apply(tmp_path, {"default": "closed"}, unsupported=True)
    assert not result.success
    assert backend.calls == 0


def test_malformed_direct_plan_diagnostics_are_refused_without_attribute_access():
    from raes_runtime.backend_input_contracts import backend_input_violation

    plan = replace(scoped_plan(None).provisioning, diagnostics=({"message": "untyped"},))
    assert backend_input_violation((plan,)) is not None


def test_actual_unadmitted_effects_fail_and_retain_cleanup_without_archival(tmp_path):
    result, backend = apply(tmp_path, {"default": "open"}, unreported=True)
    assert not result.success
    assert backend.calls == 1
    assert "provision.node.host" in result.snapshot.entries
    assert not result.snapshot.materialization_attestations


def test_later_evaluator_addition_is_refused_before_provisioning(tmp_path):
    from raes import parse_sdl
    from raes_backend_stubs.stubs import create_stub_manifest
    from raes_contracts.planning import PlanScope
    from raes_runtime import RuntimeManager
    from raes_runtime.registry import RuntimeTarget
    from test_runtime_manager import RecordingEvaluator

    original_manifest = scoped_plan({"default": "closed"}).manifest
    manifest = replace(
        original_manifest,
        capabilities=replace(original_manifest.capabilities, evaluator=create_stub_manifest().evaluator),
    )
    provisioner = ScopeReportingProvisioner(manifest)

    class CollectorEvaluator(RecordingEvaluator):
        def prepare_augmentation(self, request, previous):
            return ScopeReportingProvisioner(manifest, addition=True).prepare_augmentation(request, previous)

    calls = []
    manager = RuntimeManager(
        RuntimeTarget(
            name="scoped", manifest=manifest, provisioner=provisioner, evaluator=CollectorEvaluator(calls, "evaluator")
        ),
        materialization_archive=RunMaterializationArchive(tmp_path),
    )
    scenario = parse_sdl("""
name: scoped
augmentation_scope: {default: closed}
realization: {default: open}
nodes: {host: {type: compute}}
propositions:
  health:
    description: The subject has runtime state.
    subjects: [nodes.host]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: 'urn:raes:declared-property:runtime', operator: exists}
assertions:
  health: {proposition: health, role: precondition, polarity: positive}
""")
    execution = manager.plan(scenario, run_scope=PlanScope(run_id="run-1"))
    assert execution.is_valid, execution.diagnostics
    assert execution.evaluation.actionable_operations
    result = manager.apply(execution)
    assert not result.success
    assert any(item.code == "augmentation.scope-closed" for item in result.diagnostics)
    assert provisioner.calls == 0
    assert not calls
    assert not manager.snapshot.entries


def test_empty_operations_with_prospective_authority_are_not_read_only():
    from raes_contracts.plan_effects import plan_can_mutate

    request = replace(
        scoped_plan({"default": "open"}).provisioning,
        operations=[],
        realization_constraints=(),
        realization_authority=(),
    )
    assert plan_can_mutate(request)


@pytest.mark.parametrize("permission", ["closed", "open"])
def test_world_changing_observation_hook_refuses_before_backend_mutation(tmp_path, permission):
    from raes_backend_stubs.stubs import create_stub_manifest
    from raes_contracts.observation_demand import EffectiveObservationDemand, ObservationLifecycleStage
    from raes_runtime.backend_observation_calls import _call_backend_apply_with_observation, _ObservationApplyRequest
    from raes_runtime.observation_execution import ConfiguredObservationRuntime
    from test_issue_1212_observation_demand import _runtime_capability, _selector

    execution = scoped_plan({"default": permission})
    manifest = replace(
        execution.manifest,
        capabilities=replace(execution.manifest.capabilities, observation=create_stub_manifest().observation),
    )
    selector = _selector("/nodes/host", "trace")
    demand = EffectiveObservationDemand(
        scope="/nodes/host",
        purpose="experimental",
        mode="selected",
        selectors=(selector,),
        collection="require",
        retention="disable",
        export="disable",
        basis="observed",
        required=False,
    )
    request = replace(execution.provisioning, observation_demands=(demand,))
    collected = []

    class InstallingObserver(ConfiguredObservationRuntime):
        def prepare_augmentation(self, request, previous):
            return ScopeReportingProvisioner(manifest, addition=True).prepare_augmentation(request, previous)

    capability = _runtime_capability(selector, stages=frozenset({ObservationLifecycleStage.COLLECTION}))
    observer = InstallingObserver(
        capabilities=(capability,),
        producers={capability.capability_id: lambda *args: (collected.append("installed") or "event",)},
    )
    backend = ScopeReportingProvisioner(manifest)
    previous = RuntimeSnapshot()
    result, _ = _call_backend_apply_with_observation(
        backend.apply,
        request,
        previous,
        request=_ObservationApplyRequest(
            address="runtime.scoped",
            snapshot=previous,
            plan=request,
            manifest=manifest,
            runtime=observer,
            materialization_archive=RunMaterializationArchive(tmp_path),
        ),
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    assert not result.success
    expected = "augmentation.scope-closed" if permission == "closed" else "augmentation.phase-unattested"
    assert any(item.code == expected for item in result.diagnostics), result.diagnostics
    assert backend.calls == 0
    assert not collected


def test_unsupported_scope_cannot_be_executed_via_a_detached_phase_plan():
    from raes_contracts.planning import PlanScope
    from raes_processor.planner import plan

    original = scoped_plan({"default": "closed"})
    manifest = replace(
        original.manifest,
        supported_contract_versions=original.manifest.supported_contract_versions
        - {"backend-augmentation-scope-v1", "backend-materialization-attestation-v1"},
    )
    execution = plan(original.model, manifest, scope=PlanScope(run_id="run-1"))
    assert not execution.is_valid
    backend = ReportingProvisioner(manifest)
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        backend.apply,
        execution.provisioning,
        previous,
        snapshot=previous,
        address="runtime.detached",
        realization=_RealizationApplyContext(plan=execution.provisioning, manifest=manifest),
    )
    assert not result.success
    assert backend.calls == 0
