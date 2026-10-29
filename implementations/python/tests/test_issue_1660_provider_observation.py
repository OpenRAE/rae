"""Composite observation ownership survives public provider execution."""

from copy import deepcopy
from dataclasses import replace

import pytest
import yaml
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.observation_demand import AchievedObservationValue, ObservationBasis
from raes_contracts.planning import PlanScope, RuntimeDomain
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot
from raes_contracts.versions import BACKEND_OPERATION_CONTRACT_IDS
from raes_operations.run_artifacts import RunMaterializationArchive
from raes_processor.planner import plan
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_snapshots import _snapshot_payload
from raes_runtime.manager import RuntimeManager
from raes_runtime.observation_execution import ConfiguredObservationRuntime
from raes_runtime.operation_command_commitment import native_command_commitment
from raes_runtime.registry import RuntimeTarget
from test_issue_1212_observation_demand import _runtime_capability, _runtime_capability_id, _selector
from test_issue_1241_materialization_context import attesting_plan
from test_issue_1241_materialization_runtime import ReportingProvisioner
from test_issue_1362_distributed_authority import Dispatcher
from test_issue_1362_provider_execution import Evidence, Provider, target
from test_runtime_manager import _full_scenario


class CompositeProvider(Provider):
    def __init__(self):
        super().__init__()
        self.commands = {}
        self.results = {}
        self.snapshot = RuntimeSnapshot()
        self.domains = []
        self.outcome = "succeeded"

    def operation_capabilities(self):
        capabilities = super().operation_capabilities()
        return type(capabilities).model_validate(
            {**capabilities.model_dump(), "supported_operation_kinds": ("provisioning", "evaluation", "orchestration")}
        )

    def start_operation(self, request):
        plan, method = self.commands[request.command.digest]
        bound_plan = replace(plan, operation_id=request.binding.operation_id)
        result = method(bound_plan, deepcopy(self.store.load_snapshot()))
        assert result.success, result.diagnostics
        self.results[request.binding.operation_id] = result
        self.snapshot = result.snapshot
        self.domains.append(request.binding.context.operation_kind.value)
        return super().start_operation(request)

    def observe_operation(self, control):
        reference = {
            "contract_id": "runtime-snapshot-v1",
            "artifact_id": "composite-provider-result",
            "digest": canonical_json_digest(_snapshot_payload(self.snapshot)),
        }
        return self.report(
            self.request,
            {
                "kind": "outcome",
                "proposed_state": self.outcome,
                "effects": {"effect": "complete", "cessation_established": True, "evidence_refs": [reference]},
                "satisfaction": "unsatisfied" if self.outcome == "failed" else "satisfied",
                "release_gates_satisfied": True,
                "cancellation_established": False,
                "result": reference,
            },
        )

    def validate_effects(self, request, response):
        return response.binding == request.binding and response.message.effects.effect == "complete"

    def resolve_result(self, request, response, predecessor):
        return deepcopy(self.results[request.binding.operation_id])


def test_composite_provider_collects_only_after_its_designated_owner(tmp_path):
    payload = _full_scenario().model_dump(mode="json", exclude_none=True, exclude_unset=True)
    payload["evidence_requirements"] = {
        "activity": {
            "source_class": "processor_backend",
            "scope_refs": ["nodes.vm"],
            "window": "run",
            "channel": "api_response",
            "sensitivity": "plain",
            "redaction": "redact_sensitive",
            "integrity": "checksum",
            "retention": "not_retained",
            "loss_disclosure": "required",
            "observation_demand": {
                "rule_id": "activity",
                "scope": "/nodes/vm",
                "purpose": "realization-description",
                "mode": "selected",
                "selector": {"semantic_scope": "/nodes/vm", "data_kind": "field", "names": ["os_distribution"]},
                "basis": "backend-selected",
                "required": False,
            },
        }
    }
    scenario = parse_sdl(yaml.safe_dump(payload))
    selector = _selector("/nodes/vm", "os_distribution", kind="field")
    calls = []

    def collect(_selector, _plan, snapshot):
        calls.append("collect")
        assert any(entry.domain is RuntimeDomain.ORCHESTRATION for entry in snapshot.entries.values())
        return AchievedObservationValue("Kali", ObservationBasis.BACKEND_SELECTED)

    observation = ConfiguredObservationRuntime(
        capabilities=(
            _runtime_capability(
                selector,
                stages=frozenset(),
                bases=frozenset({ObservationBasis.BACKEND_SELECTED}),
            ),
        ),
        describers={_runtime_capability_id(selector): collect},
    )
    provider = CompositeProvider()
    base = create_stub_target()
    selected = replace(
        base,
        manifest=replace(
            base.manifest,
            supported_contract_versions=base.manifest.supported_contract_versions | set(BACKEND_OPERATION_CONTRACT_IDS),
        ),
        operation_provider=provider,
        observation_runtime=observation,
    )
    provider.store = LocalControlPlaneStore(tmp_path / "ledger")
    with RuntimeManager(selected, operation_evidence=provider, store=provider.store) as runtime:
        execution = runtime.plan(scenario)
        assert execution.is_valid, execution.diagnostics
        assert execution.observation_owner is RuntimeDomain.ORCHESTRATION
        for phase, method in (
            (execution.provisioning, selected.provisioner.apply),
            (execution.evaluation, selected.evaluator.start),
            (execution.orchestration, selected.orchestrator.start),
        ):
            provider.commands[native_command_commitment(runtime, phase)] = (phase, method)
        result = runtime.apply(execution)
        assert result.success, result.diagnostics
        assert provider.domains == ["provisioning", "evaluation", "orchestration"]
        assert calls == ["collect"]
        assert result.details["realized_form_disclosures"][0]["realized_value_summary"] == '"Kali"'


@pytest.mark.parametrize("outcome", ["succeeded", "failed"])
def test_provider_apply_preserves_materialization_submission(tmp_path, outcome):
    original, model = attesting_plan()
    manifest = replace(
        original.manifest,
        supported_contract_versions=original.manifest.supported_contract_versions | set(BACKEND_OPERATION_CONTRACT_IDS),
    )
    provider = CompositeProvider()
    provider.outcome = outcome
    backend = ReportingProvisioner(manifest)
    selected = RuntimeTarget(name="stub", manifest=manifest, provisioner=backend, operation_provider=provider)
    provider.store = LocalControlPlaneStore(tmp_path / "ledger")
    archive = RunMaterializationArchive(tmp_path / "archive")
    with RuntimeManager(
        selected,
        operation_evidence=provider,
        store=provider.store,
        materialization_archive=archive,
        run_scope="run:run-1",
    ) as runtime:
        execution = plan(model, manifest, scope=PlanScope(target_name=selected.name, run_id="run-1"))
        assert execution.is_valid, execution.diagnostics
        provider.commands[native_command_commitment(runtime, execution.provisioning)] = (
            execution.provisioning,
            backend.apply,
        )
        result = runtime.apply(execution)
        assert result.success is (outcome == "succeeded"), result.diagnostics
        assert result.materialization_attestation is not None
        assert result.snapshot.materialization_attestations == runtime.snapshot.materialization_attestations
        (reference,) = result.snapshot.materialization_attestations
        assert (tmp_path / "archive" / reference.reference.ref_path).is_file()


@pytest.mark.parametrize("method", ["apply", "destroy", "refresh_inventory"])
def test_synchronous_lifecycle_refuses_distributed_work_before_any_effect(method):
    provider, dispatcher = Provider(), Dispatcher()
    with RuntimeManager(target(provider), operation_evidence=Evidence(), distributed_execution=dispatcher) as runtime:
        execution = runtime.plan(_full_scenario())
        before = runtime.get_snapshot()
        result = getattr(runtime, method)(*(() if method == "destroy" else (execution,)))
        assert not result.success
        assert "runtime.interaction.distributed-unsupported" in {diagnostic.code for diagnostic in result.diagnostics}
        assert runtime.get_snapshot() == before
        assert runtime._store.load_records() == {}
        assert dispatcher.commands == []
        assert provider.starts == 0


def test_same_distributed_owner_exposes_pending_evaluation_by_receipt():
    provider, dispatcher = CompositeProvider(), Dispatcher()
    with RuntimeManager(target(provider), operation_evidence=provider, distributed_execution=dispatcher) as runtime:
        execution = runtime.plan(parse_sdl("name: distributed-evaluation"))
        receipt = runtime.evaluate(execution, idempotency_key="queued-evaluation")
        assert receipt.accepted
        assert runtime.get_operation(receipt.operation_id).state is OperationState.ACCEPTED
        assert dispatcher.commands[0].binding.operation_id == receipt.operation_id
        assert provider.starts == 0
