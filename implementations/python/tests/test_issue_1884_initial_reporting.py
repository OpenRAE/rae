"""Initial-only reporting keeps runtime validation, collection and cleanup."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.apparatus import RealizationObservationCapability
from raes_contracts.contracts.plan_projection import (
    evaluation_plan_model,
    orchestration_plan_model,
    provisioning_plan_model,
    runtime_plan_digest,
)
from raes_contracts.materialization import MATERIALIZATION_ATTESTATION_CONTRACT, MaterializationSubmission
from raes_contracts.planning import PlanScope, RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, OperationState, RealizationObservationDisclosure, RuntimeSnapshot
from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope
from raes_operations.run_artifacts import RunMaterializationArchive
from raes_runtime import RuntimeManager
from raes_runtime.backend_materialization import finalize_materialization
from raes_runtime.backend_realization_authority import _RealizationApplyContext
from test_issue_1241_materialization_context import attesting_plan
from test_issue_1241_materialization_runtime import ReportingProvisioner

_SOURCE = """name: initial-reporting
nodes:
  host:
    type: compute
    conditions: {health: ops}
    roles: {ops: operator}
    runtime:
      environment: [{name: MODE, value: fixture, value_classification: plain, provenance: runtime}]
conditions:
  health: {command: /bin/true, interval: 15}
events:
  kickoff: {}
scripts:
  timeline: {start_time: 0, end_time: 60, speed: 1, events: {kickoff: 10}}
"""


class ProjectedProvisioner(ReportingProvisioner):
    def apply(self, request, previous):
        from raes_processor.semantics.realization_concerns import realization_concern_descriptor

        result = super().apply(request, previous)
        if request.materialization_source is None:
            return result
        entries = dict(result.snapshot.entries)
        entry = entries["provision.node.host"]
        payload = deepcopy(entry.payload)
        owner = realization_concern_descriptor("runtime-environment")
        payload["spec"]["node"]["runtime"]["environment"] = owner.project(
            payload["spec"]["node"]["runtime"]["environment"]
        )
        entries[entry.address] = replace(entry, payload=payload)
        return replace(
            result,
            snapshot=result.snapshot.with_entries(entries),
            operational_realization_observations=(
                *result.operational_realization_observations,
                RealizationObservationDisclosure(
                    address=entry.address,
                    field_path="nodes.host.runtime.environment",
                    domain="runtime-realization",
                    requirement_kind="runtime-environment",
                    verification_scope=RealizationVerificationScope.CONFIGURATION,
                    observation_strength=ObservationStrength.DAEMON_OBSERVED,
                ),
            ),
        )


def _manager(tmp_path, *, omit=False, archive=True):
    original_target = create_stub_target(with_realization_envelope=True)
    original = original_target.manifest
    manifest = replace(
        original,
        supported_contract_versions=original.supported_contract_versions | {MATERIALIZATION_ATTESTATION_CONTRACT},
        realization_support=tuple(
            replace(
                support,
                supported_constraint_kinds=support.supported_constraint_kinds | {"runtime-environment"},
                supported_exact_requirement_kinds=support.supported_exact_requirement_kinds | {"runtime-environment"},
                observation_capabilities={
                    **support.observation_capabilities,
                    "runtime-environment": RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.CONFIGURATION,
                        observation_strength=ObservationStrength.DAEMON_OBSERVED,
                    ),
                },
            )
            for support in original.realization_support
        ),
    )
    backend = ProjectedProvisioner(manifest, omit=omit)
    target = replace(original_target, name="initial", manifest=manifest, provisioner=backend)
    return RuntimeManager(
        target, materialization_archive=RunMaterializationArchive(tmp_path) if archive else None, run_scope="run:run-1"
    ), backend


@pytest.mark.parametrize("reporting", ["provisioning", "all-phases"])
def test_public_runtime_initial_report_and_later_command_results(tmp_path, reporting):
    manager, backend = _manager(tmp_path)
    try:
        execution = manager.plan(
            parse_sdl(_SOURCE), run_scope=PlanScope(run_id="run-1"), materialization_reporting=reporting
        )
        assert execution.is_valid, execution.diagnostics
        assert execution.orchestration.actionable_operations
        assert execution.evaluation.actionable_operations
        sources = [
            getattr(execution, phase).materialization_source
            for phase in ("provisioning", "orchestration", "evaluation")
        ]
        assert all(source == sources[0] for source in sources)
        result = manager.apply(execution)
        assert backend.calls == 1
        assert result.success is (reporting == "provisioning"), result.diagnostics
        if reporting == "all-phases":
            assert any(item.code == "runtime.materialization-attestation-invalid" for item in result.diagnostics)
            return
        assert result.materialization_attestation is not None
        assert len(result.snapshot.materialization_attestations) == 1
        environment = result.snapshot.entries["provision.node.host"].payload["spec"]["node"]["runtime"]["environment"]
        assert "value" not in environment[0]
        assert "value_commitment" in environment[0]
        assert result.snapshot.evaluation_results
        assert result.snapshot.for_domain(RuntimeDomain.ORCHESTRATION)
        refreshed = manager._plan_evaluation_refresh(execution, manager.snapshot)
        assert refreshed.evaluation.materialization_source.reporting_scope == reporting
        receipt = manager.evaluate(execution, idempotency_key="capture-selected-evidence")
        assert receipt.accepted, receipt.diagnostics
        status = manager.get_operation(receipt.operation_id)
        assert status.state is OperationState.SUCCEEDED, status.diagnostics
        assert manager.snapshot.evaluation_results
        assert len(manager.snapshot.materialization_attestations) == 1
        destroyed = manager.destroy()
        assert destroyed.success, destroyed.diagnostics
        assert not destroyed.snapshot.entries
        assert len(destroyed.snapshot.materialization_attestations) == 1
    finally:
        manager.close()


@pytest.mark.parametrize("archive,omit,expected_calls", [(True, True, 1), (False, False, 0)])
def test_provisioning_only_still_requires_initial_report_and_archive(tmp_path, archive, omit, expected_calls):
    manager, backend = _manager(tmp_path, omit=omit, archive=archive)
    try:
        execution = manager.plan(
            parse_sdl(_SOURCE), run_scope=PlanScope(run_id="run-1"), materialization_reporting="provisioning"
        )
        result = manager.apply(execution)
        assert not result.success
        assert backend.calls == expected_calls
        assert not result.snapshot.materialization_attestations
    finally:
        manager.close()


@pytest.mark.parametrize(
    "phase,model",
    [
        ("provisioning", provisioning_plan_model),
        ("orchestration", orchestration_plan_model),
        ("evaluation", evaluation_plan_model),
    ],
)
def test_reporting_scope_is_bound_and_published_for_every_phase(phase, model):
    execution, _ = attesting_plan()
    original = getattr(execution, phase)
    source = original.materialization_source
    assert "reporting_scope" not in source.model_dump(mode="json")
    changed = replace(original, materialization_source=source.model_copy(update={"reporting_scope": "provisioning"}))
    assert runtime_plan_digest(changed) != runtime_plan_digest(original)
    schema_path = Path(__file__).resolve().parents[3] / f"contracts/schemas/plans/{phase}-plan-v1.json"
    schema = json.loads(schema_path.read_text())
    jsonschema.Draft202012Validator(schema).validate(model(changed).model_dump(mode="json"))
    with pytest.raises(ValueError):
        type(source).model_validate({**source.model_dump(), "reporting_scope": "none"})


@pytest.mark.parametrize("phase", ["orchestration", "evaluation"])
def test_later_augmentation_still_requires_a_report_and_supplied_reports_are_admitted(tmp_path, phase):
    execution, _ = attesting_plan("name: empty")
    request = getattr(execution, phase)
    request = replace(
        request,
        materialization_source=request.materialization_source.model_copy(update={"reporting_scope": "provisioning"}),
    )
    previous = RuntimeSnapshot()
    result = ApplyResult(True, previous)
    context = _RealizationApplyContext(operation_plan=request, manifest=execution.manifest)
    assert finalize_materialization(result, result, context, previous, None).success
    context = replace(context, augmentation=SimpleNamespace(preparation=SimpleNamespace(effects=(object(),))))
    assert not finalize_materialization(result, result, context, previous, RunMaterializationArchive(tmp_path)).success
    invalid = replace(result, materialization_attestation=MaterializationSubmission(sdl="invalid"))
    assert not finalize_materialization(invalid, result, replace(context, augmentation=None), previous, None).success
