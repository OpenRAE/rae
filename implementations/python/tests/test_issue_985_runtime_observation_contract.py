"""Issue #985: backend observation contracts and safe persistence."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from pydantic import TypeAdapter
from raes import parse_sdl
from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.apparatus import RealizationObservationCapability
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_contracts.realization_observation import RealizationObservationDisclosure
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan as build_plan
from raes_processor.semantics.realization import (
    CompiledRealizationRequirement,
    project_realization_concern,
    realization_disclosure,
)
from raes_processor.semantics.realization_concerns import realization_concern_descriptor
from raes_processor.semantics.realization_typed_runtime_projection import project_typed_runtime_concern
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext

_ADDRESS = "provision.node.worker"
_FIELD_PATH = "nodes.worker.runtime.environment"


def _payload(value: object) -> dict[str, object]:
    return {"spec": {"node": {"runtime": {"environment": value}}}}


def _requirement(explicitness: ExplicitnessClass) -> CompiledRealizationRequirement:
    return CompiledRealizationRequirement(
        field_path=_FIELD_PATH,
        address=_ADDRESS,
        domain="runtime-realization",
        requirement_kind="runtime-environment",
        explicitness=explicitness,
        provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
    )


def _plan(value: object) -> ProvisioningPlan:
    return ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address=_ADDRESS,
                resource_type="node",
                payload=_payload(value),
            )
        ]
    )


def _authoritative_environment_plan() -> tuple[ProvisioningPlan, BackendManifest]:
    target = create_stub_target()
    declaration = target.manifest.realization_support[0]
    manifest = replace(
        target.manifest,
        realization_support=(
            replace(
                declaration,
                supported_exact_requirement_kinds=(
                    declaration.supported_exact_requirement_kinds | {"runtime-environment"}
                ),
                observation_capabilities={
                    **declaration.observation_capabilities,
                    "runtime-environment": RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.CONFIGURATION,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                    ),
                },
            ),
        ),
    )
    execution = build_plan(
        compile_runtime_model(
            parse_sdl(
                """
name: issue-985-authoritative-runtime-observation
nodes:
  worker:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    runtime:
      environment:
        - name: MODE
          value: production
          value_classification: plain
          provenance: runtime
          source: ""
"""
            )
        ),
        manifest,
    )
    return execution.provisioning, manifest


def _authoritative_snapshot(plan: ProvisioningPlan, value: object) -> RuntimeSnapshot:
    operation = plan.operations[0]
    payload = deepcopy(operation.payload)
    payload["spec"]["node"]["runtime"]["environment"] = value
    return RuntimeSnapshot(
        realization_envelope=plan.realization_envelope,
        entries={
            _ADDRESS: SnapshotEntry(
                address=_ADDRESS,
                domain=RuntimeDomain.PROVISIONING,
                resource_type="node",
                payload=payload,
            )
        },
        realization_observations=(
            RealizationObservationDisclosure(
                address=_ADDRESS,
                field_path=_FIELD_PATH,
                domain="runtime-realization",
                requirement_kind="runtime-environment",
                verification_scope=RealizationVerificationScope.CONFIGURATION,
                observation_strength=ObservationStrength.GUEST_OBSERVED,
            ),
        ),
    )


def _snapshot(value: object) -> RuntimeSnapshot:
    return RuntimeSnapshot(
        entries={
            _ADDRESS: SnapshotEntry(
                address=_ADDRESS,
                domain=RuntimeDomain.PROVISIONING,
                resource_type="node",
                payload=_payload(value),
            )
        }
    )


def test_open_observation_must_satisfy_the_registered_closed_contract() -> None:
    requirement = _requirement(ExplicitnessClass.OPEN)

    diagnostics, provenance = realization_disclosure(
        (requirement,),
        _plan([]),
        _snapshot([{"value": "missing-name", "unknown": "must-not-be-ignored"}]),
    )

    assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-contract-invalid"]
    assert provenance == ()
    assert "missing-name" not in diagnostics[0].message


@pytest.mark.parametrize(
    ("kind", "observation"),
    [
        (
            "runtime-environment",
            [{"name": "MODE", "value": "production", "unknown": "rejected"}],
        ),
        (
            "runtime-mounts",
            [{"target": "/data", "source_kind": "unknown"}],
        ),
        (
            "linux-capabilities",
            {"required": [], "unknown": "rejected"},
        ),
        (
            "published-ports",
            [{}],
        ),
        (
            "forwarding-agents",
            [
                {
                    "forwarding_agent_id": "agent",
                    "implementation": "other",
                    "agent_kind": "other",
                    "unknown": "rejected",
                }
            ],
        ),
        (
            "service-listeners",
            [{"service_listener_id": "http", "protocol": "tcp"}],
        ),
    ],
)
def test_each_runtime_concern_has_a_closed_observation_contract(
    kind: str,
    observation: object,
) -> None:
    with pytest.raises(ValueError):
        project_realization_concern(kind, observation, observed=True)


def test_runtime_gate_rejects_a_malformed_commitment_wire_value() -> None:
    declared = [
        {
            "name": "TOKEN",
            "value": "fixture-secret",
            "value_classification": "secret_fixture",
            "provenance": "operator",
            "source": "fixture",
        }
    ]
    malformed_observation = [
        {
            "name": "TOKEN",
            "value_classification": "secret_fixture",
            "provenance": "operator",
            "source": "fixture",
            "value_present": True,
            "value_commitment": "raes-runtime-value-jcs-sha256-v1:not-a-digest",
        }
    ]

    diagnostics, provenance = realization_disclosure(
        (_requirement(ExplicitnessClass.EXACT),),
        _plan(declared),
        _snapshot(malformed_observation),
    )

    assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-contract-invalid"]
    assert provenance == ()


@pytest.mark.parametrize("classification", ["redacted", "operator_secret"])
def test_runtime_gate_rejects_raw_material_for_a_protected_observation(classification: str) -> None:
    declared = [
        {
            "name": "TOKEN",
            "value": "fixture-secret",
            "value_classification": "secret_fixture",
            "provenance": "operator",
            "source": "fixture",
        }
    ]
    protected_observation = [
        {
            "name": "TOKEN",
            "value": "must-not-cross-the-boundary",
            "value_classification": classification,
            "provenance": "operator",
            "source": "fixture",
        }
    ]

    diagnostics, provenance = realization_disclosure(
        (_requirement(ExplicitnessClass.EXACT),),
        _plan(declared),
        _snapshot(protected_observation),
    )

    assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-contract-invalid"]
    assert provenance == ()


@pytest.mark.parametrize("classification", ["redacted", "operator_secret"])
def test_typed_runtime_projection_rejects_raw_material_for_a_protected_value(classification: str) -> None:
    protected_value = [
        {
            "name": "TOKEN",
            "value": "must-not-cross-the-boundary",
            "value_classification": classification,
        }
    ]
    adapter = TypeAdapter(list[dict[str, object]])

    with pytest.raises(ValueError, match="protected realization values must not carry raw material"):
        project_typed_runtime_concern(
            protected_value,
            observed=True,
            adapter=adapter,
            concern_kind="runtime-database-services",
        )


def test_mount_persistence_keeps_valid_stateful_records_outside_the_concern() -> None:
    observation = [
        {"target": "/host", "source_kind": "bind", "source": "/srv/host"},
        {"target": "/state", "source_kind": "volume", "source": "state"},
    ]
    descriptor = realization_concern_descriptor("runtime-mounts")
    assert descriptor is not None

    comparison = descriptor.project(observation, observed=True)
    persisted = descriptor.sanitize_observation(observation)

    assert [mount["source_kind"] for mount in comparison] == ["bind"]
    assert [mount["source_kind"] for mount in persisted] == ["bind", "volume"]


def test_backend_boundary_persists_only_the_safe_projection() -> None:
    observed = [
        {
            "name": "MODE",
            "value": "production",
            "value_classification": "plain",
            "provenance": "runtime",
            "source": "",
            "description": "backend annotation must not persist",
        }
    ]
    plan, manifest = _authoritative_environment_plan()

    def backend(_request, _previous) -> ApplyResult:
        return ApplyResult(
            success=True,
            snapshot=_authoritative_snapshot(plan, observed),
            changed_addresses=[_ADDRESS],
        )

    result = _call_backend_apply(
        backend,
        plan,
        RuntimeSnapshot(),
        address="runtime.provision.node.worker",
        snapshot=RuntimeSnapshot(),
        realization=_RealizationApplyContext(plan=plan, manifest=manifest),
    )

    assert result.success is True
    persisted = result.snapshot.entries[_ADDRESS].payload["spec"]["node"]["runtime"]["environment"]
    assert persisted[0]["value_present"] is True
    assert persisted[0]["value_commitment"].startswith("raes-runtime-value-jcs-sha256-v1:")
    assert "production" not in repr(persisted)
    assert "description" not in repr(persisted)


def test_backend_boundary_rejects_unknown_observation_fields() -> None:
    declared = [
        {
            "name": "MODE",
            "value": "production",
            "value_classification": "plain",
            "provenance": "runtime",
            "source": "",
        }
    ]
    observed = [{**declared[0], "backend_extra": "do-not-persist"}]
    plan, manifest = _authoritative_environment_plan()
    calls = []

    def backend(_request, _previous) -> ApplyResult:
        calls.append(True)
        return ApplyResult(
            success=True,
            snapshot=_authoritative_snapshot(plan, observed),
            changed_addresses=[_ADDRESS],
        )

    baseline = RuntimeSnapshot()
    result = _call_backend_apply(
        backend,
        plan,
        baseline,
        address="runtime.provision.node.worker",
        snapshot=baseline,
        realization=_RealizationApplyContext(plan=plan, manifest=manifest),
    )

    assert result.success is False
    assert calls == [True]
    assert result.snapshot == baseline
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["runtime.backend-contract-invalid"]
    assert "do-not-persist" not in result.diagnostics[0].message
