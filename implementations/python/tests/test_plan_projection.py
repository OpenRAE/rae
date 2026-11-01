"""Tests for the internal-plan -> published-contract projector (issue #609)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from paths import EXAMPLES_DIR, REPO_ROOT
from raes_backend_stubs.manifest import create_stub_manifest
from raes_contracts.contracts import (
    EvaluationPlanModel,
    OrchestrationPlanModel,
    ProvisioningPlanModel,
    RealizationEnvelopeIdentityModel,
)
from raes_contracts.contracts.plan_projection import (
    evaluation_plan_model,
    orchestration_plan_model,
    provisioning_plan_model,
)
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.planning import ProvisioningPlan
from raes_processor.reference import run_reference_processor

_PLAN_FIXTURES = REPO_ROOT / "contracts" / "fixtures" / "plans"
_SCENARIO = EXAMPLES_DIR / "techvault-defensive-min.sdl.yaml"


def test_empty_plans_project_to_minimal_contract_shape() -> None:
    provisioning = provisioning_plan_model(ProvisioningPlan())
    assert provisioning.operations == []
    assert provisioning.diagnostics == []
    assert provisioning.realization_envelope is None


def test_diagnostics_are_projected_json_safe() -> None:
    plan = ProvisioningPlan(
        operations=[],
        diagnostics=[
            Diagnostic(
                code="planner.capability-gap",
                domain="provisioning",
                address="runtime.provisioning",
                message="node type unsupported",
                severity=Severity.WARNING,
            )
        ],
    )

    projected = provisioning_plan_model(plan)
    dumped = json.loads(projected.model_dump_json())

    assert dumped["diagnostics"] == [
        {
            "code": "planner.capability-gap",
            "domain": "provisioning",
            "address": "runtime.provisioning",
            "message": "node type unsupported",
            "severity": "warning",
        }
    ]


def test_real_execution_plan_projects_and_round_trips() -> None:
    result = run_reference_processor(_SCENARIO, create_stub_manifest())
    execution_plan = result.execution_plan

    provisioning = provisioning_plan_model(execution_plan.provisioning)
    orchestration = orchestration_plan_model(execution_plan.orchestration)
    evaluation = evaluation_plan_model(execution_plan.evaluation)

    assert provisioning.operations, "expected the defensive-min scenario to yield provisioning operations"
    # The per-field comparison below is only a real regression detector if the
    # fixture actually populates payload and refresh_dependencies.
    assert any(op.payload for op in execution_plan.provisioning.operations)
    assert any(op.refresh_dependencies for op in execution_plan.provisioning.operations)

    # Every projected operation matches its source operation field-for-field,
    # across all three domains that share _plan_operation_model.
    for projected_plan, source_plan in (
        (provisioning, execution_plan.provisioning),
        (orchestration, execution_plan.orchestration),
        (evaluation, execution_plan.evaluation),
    ):
        assert len(projected_plan.operations) == len(source_plan.operations)
        for projected_op, source_op in zip(projected_plan.operations, source_plan.operations, strict=True):
            assert projected_op.action == source_op.action.value
            assert projected_op.address == source_op.address
            assert projected_op.resource_type == source_op.resource_type
            assert projected_op.payload == dict(source_op.payload)
            assert projected_op.ordering_dependencies == list(source_op.ordering_dependencies)
            assert projected_op.refresh_dependencies == list(source_op.refresh_dependencies)

    # startup_order threads through the orchestration/evaluation wrappers.
    assert orchestration.startup_order == list(execution_plan.orchestration.startup_order)
    assert evaluation.startup_order == list(execution_plan.evaluation.startup_order)

    # Each domain member independently validates against its published model and
    # its JSON serialization is stable under re-parse + re-serialize.
    for model, cls in (
        (provisioning, ProvisioningPlanModel),
        (orchestration, OrchestrationPlanModel),
        (evaluation, EvaluationPlanModel),
    ):
        dumped = json.loads(model.model_dump_json())
        revalidated = cls.model_validate(dumped)
        assert json.loads(revalidated.model_dump_json()) == dumped


def test_projection_excludes_internal_resources() -> None:
    result = run_reference_processor(_SCENARIO, create_stub_manifest())
    provisioning = provisioning_plan_model(result.execution_plan.provisioning)

    # The internal resources map must not leak into the published contract.
    assert "resources" not in provisioning.model_dump()


def test_operation_projection_maps_every_field() -> None:
    # Fixture-independent: a no-op drop of ANY of the six mapped fields must fail.
    # Reuse a real operation's validated address/resource_type, then set every
    # other field to a known, distinct value the projection must reflect exactly.
    operations = run_reference_processor(_SCENARIO, create_stub_manifest()).execution_plan.provisioning.operations
    addresses = [op.address for op in operations]
    source = replace(
        operations[0],
        payload={"marker": "value", "count": 3, "nested": {"k": "v"}},
        ordering_dependencies=(addresses[1],),
        refresh_dependencies=(addresses[2],),
    )

    projected = provisioning_plan_model(ProvisioningPlan(operations=[source])).operations[0]

    assert projected.action == source.action.value
    assert projected.address == source.address
    assert projected.resource_type == source.resource_type
    assert projected.payload == {"marker": "value", "count": 3, "nested": {"k": "v"}}
    assert projected.ordering_dependencies == [addresses[1]]
    assert projected.refresh_dependencies == [addresses[2]]


def test_realization_envelope_threads_through_projection() -> None:
    # The optional provisioning realization-envelope identity must survive the
    # projection, not only the trivial None -> None case.
    identity = RealizationEnvelopeIdentityModel(
        envelope_id="cli-test-envelope",
        digest="sha256:" + "a" * 64,
        configuration_digest="sha256:" + "b" * 64,
    )

    projected = provisioning_plan_model(ProvisioningPlan(realization_envelope=identity))

    assert projected.realization_envelope == identity


def test_published_plan_fixtures_validate_against_the_same_models() -> None:
    # The projector's target models are exactly the ones that admit the published
    # plan fixtures, so CLI output shares the fixtures' contract shape.
    for family, cls in (
        ("provisioning-plan-v1", ProvisioningPlanModel),
        ("orchestration-plan-v1", OrchestrationPlanModel),
        ("evaluation-plan-v1", EvaluationPlanModel),
    ):
        fixture = _PLAN_FIXTURES / family / "valid" / "minimal.json"
        cls.model_validate(json.loads(Path(fixture).read_text(encoding="utf-8")))
