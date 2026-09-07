"""Issue #899 participant resource budgets and shared-service fairness."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from implementations.python.tests.test_dsl_437_benign_participant_execution import (
    SCENARIO_CLOCK_ADDRESS,
    SCENARIO_CLOCK_STEP_TICKS,
    _activity_control,
    _activity_policy_yaml,
    _advance_stepped_clock_to_tick,
    _autonomous_manifest,
    _compiled,
    _NativeParticipantRuntime,
)
from pydantic import BaseModel
from raes import parse_sdl
from raes._errors import SDLValidationError
from raes.composition import _namespace_payload
from raes.participant_execution import ParticipantAutonomousExecutionPolicyV3
from raes_backend_protocols.capability_admission import (
    participant_autonomous_execution_capability_gaps,
)
from raes_backend_protocols.participant_resource_budgets import (
    ParticipantResourceBudgetCapabilities,
    ParticipantResourcePoolCapacity,
)
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts import schema_bundle
from raes_contracts.contracts.participant_resource_budgets import (
    ParticipantResourceBudgetEventModel,
    ParticipantResourceBudgetPolicyModel,
    ParticipantResourceBudgetStateModel,
    ParticipantResourcePoolCapacityModel,
    participant_resource_budget_state_ref,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.compiler import compile_runtime_model
from raes_runtime.control_plane_store import LocalControlPlaneStore
from raes_runtime.manager import RuntimeManager
from raes_runtime.participant_resource_accounting import (
    commit_participant_resource_reservation,
    reconcile_participant_resource_budgets,
)
from raes_runtime.participant_resource_budgets import (
    initialize_participant_resource_budgets,
    reserve_participant_resources,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


class _UnmeasuredParticipantRuntime(_NativeParticipantRuntime):
    def _model_action(self, request, snapshot, *, episode_id):
        execution = super()._model_action(request, snapshot, episode_id=episode_id)
        assert execution.action_result is not None
        return replace(
            execution,
            action_result=execution.action_result.model_copy(update={"resource_measurements": []}),
        )


def _measured_vector(
    snapshot: RuntimeSnapshot,
    operation_id: str,
    **overrides: int,
) -> dict[str, int]:
    return {
        str(event["budget_state_ref"]): overrides.get(
            str(event["budget_id"]),
            int(event["requested"]),
        )
        for event in snapshot.participant_resource_budget_events.values()
        if event["operation_id"] == operation_id and event["transition"] == "reserve"
    }


def _budget_policy_yaml() -> str:
    payload = yaml.safe_load(_activity_policy_yaml())
    policy = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    policy["profile"] = "participant-autonomous-execution/v3"
    policy["resource_budget"] = {
        "policy_id": "green-shared-capacity",
        "owners": {
            "green": {"kind": "participant", "ref": "participant-agent"},
            "range-a": {"kind": "deployment_tenant", "ref": "range-a"},
            "inference": {
                "kind": "shared_service",
                "ref": "nodes.customer-portal.services.http",
            },
            "fleet": {"kind": "fleet", "ref": "fleet.primary"},
        },
        "fairness": {
            "policy": "weighted_fair",
            "priority_class": "background",
            "weight": 1,
            "protected": False,
            "borrowing": "lendable_only",
            "reclaim": "yield",
            "max_queue_ticks": 20,
            "starvation_bound_ticks": 100,
        },
        "dimensions": {
            "participant-actions": {
                "owner_ref": "green",
                "pool_ref": "participant-pool",
                "resource_kind": "action_rate",
                "unit": "actions",
                "accounting_mode": "windowed_counter",
                "meter_profile_ref": "raes.action-attempt/v1",
                "limit": 24,
                "reservation": 1,
                "reset": "time_segment",
                "window_ticks": 100,
                "parent_budget_ref": "range-actions",
            },
            "range-actions": {
                "owner_ref": "range-a",
                "pool_ref": "range-pool",
                "resource_kind": "action_rate",
                "unit": "actions",
                "accounting_mode": "windowed_counter",
                "meter_profile_ref": "raes.action-attempt/v1",
                "limit": 240,
                "reservation": 1,
                "reset": "run",
                "window_ticks": 100,
                "parent_budget_ref": "fleet-actions",
            },
            "fleet-actions": {
                "owner_ref": "fleet",
                "pool_ref": "fleet-pool",
                "resource_kind": "action_rate",
                "unit": "actions",
                "accounting_mode": "windowed_counter",
                "meter_profile_ref": "raes.action-attempt/v1",
                "limit": 2400,
                "reservation": 1,
                "reset": "run",
                "window_ticks": 100,
            },
            "concurrency": {
                "owner_ref": "green",
                "pool_ref": "participant-pool",
                "resource_kind": "concurrent_actions",
                "unit": "actions",
                "accounting_mode": "reservable_gauge",
                "meter_profile_ref": "raes.concurrent-action/v1",
                "limit": 1,
                "reservation": 1,
                "reset": "reconciled",
            },
            "storage": {
                "owner_ref": "range-a",
                "pool_ref": "range-pool",
                "resource_kind": "storage_growth",
                "unit": "bytes",
                "accounting_mode": "growth_counter",
                "meter_profile_ref": "raes.logical-byte/v1",
                "limit": 1048576,
                "reservation": 4096,
                "reset": "reconciled",
            },
            "tokens": {
                "owner_ref": "inference",
                "pool_ref": "inference-pool",
                "resource_kind": "inference_tokens",
                "unit": "tokens",
                "accounting_mode": "windowed_counter",
                "meter_profile_ref": "tokenizer.example/v1",
                "limit": 20000,
                "reservation": 500,
                "reset": "time_segment",
                "window_ticks": 100,
            },
            "images": {
                "owner_ref": "inference",
                "pool_ref": "inference-pool",
                "resource_kind": "image_generations",
                "unit": "images",
                "accounting_mode": "cumulative_counter",
                "meter_profile_ref": "raes.image-generation/v1",
                "limit": 20,
                "reservation": 1,
                "reset": "run",
            },
            "accelerator": {
                "owner_ref": "fleet",
                "pool_ref": "accelerator-pool",
                "resource_kind": "accelerator",
                "unit": "accelerator_milliseconds",
                "accounting_mode": "lease",
                "meter_profile_ref": "raes.accelerator-class.generic/v1",
                "limit": 60000,
                "reservation": 1000,
                "reset": "reconciled",
            },
        },
    }
    payload["deployment_tenants"] = {
        "range-a": {"description": "Evaluated range A."},
        "range-b": {"description": "Independent range B."},
    }
    payload.setdefault("relationships", {})["range-a-inference-service"] = {
        "type": "uses_shared_service",
        "source": "deployment_tenants.range-a",
        "target": "nodes.customer-portal.services.http",
        "description": "Range A is authorized to consume the governed inference service.",
        "shared_service": {
            "tenant_isolation": "stateless",
            "workload_authentication": "tenant_scoped_workload_identity",
            "mutable_state_refs": [],
            "mutable_state_owner": "none",
            "reset_generation_owner": "none",
        },
    }
    return yaml.safe_dump(payload, sort_keys=False)


def _pool(
    pool_ref: str,
    *,
    owner_kind: str,
    owner_ref: str,
    resource_kind: str,
    unit: str,
    meter_profile_ref: str,
    capacity: int,
    isolation: str = "tenant_partitioned",
) -> ParticipantResourcePoolCapacity:
    return ParticipantResourcePoolCapacity(
        pool_ref=pool_ref,
        owner_kind=owner_kind,
        owner_ref=owner_ref,
        resource_kind=resource_kind,
        unit=unit,
        accounting_mode=(
            "reservable_gauge"
            if resource_kind == "concurrent_actions"
            else "growth_counter"
            if resource_kind == "storage_growth"
            else "lease"
            if resource_kind == "accelerator"
            else "cumulative_counter"
            if resource_kind == "image_generations"
            else "windowed_counter"
        ),
        meter_profile_ref=meter_profile_ref,
        capacity=capacity,
        tenant_isolation=isolation,
        configuration_digest="sha256:" + "1" * 64,
        fairness_policy="weighted_fair",
        priority_classes=("evaluated", "standard", "background"),
        borrowing="lendable_only",
        reclaim="yield",
        max_queue_ticks=20,
        starvation_bound_ticks=100,
        protected_capacity=1,
        evidence_contract_ids=("participant-resource-budget-event-v1",),
    )


def _capabilities() -> ParticipantResourceBudgetCapabilities:
    return ParticipantResourceBudgetCapabilities(
        support_strength="exact",
        supported_owner_kinds=frozenset({"participant", "deployment_tenant", "shared_service", "fleet"}),
        supported_resource_kinds=frozenset(
            {
                "action_rate",
                "concurrent_actions",
                "storage_growth",
                "inference_tokens",
                "image_generations",
                "accelerator",
            }
        ),
        supported_accounting_modes=frozenset(
            {
                "windowed_counter",
                "cumulative_counter",
                "reservable_gauge",
                "growth_counter",
                "lease",
            }
        ),
        supported_reset_modes=frozenset({"time_segment", "run", "reconciled"}),
        supported_fairness_policies=frozenset({"weighted_fair"}),
        supported_isolation_strengths=frozenset({"tenant_partitioned"}),
        configured_pools=(
            _pool(
                "participant-pool",
                owner_kind="participant",
                owner_ref="participant.behavior.participant-agent",
                resource_kind="action_rate",
                unit="actions",
                meter_profile_ref="raes.action-attempt/v1",
                capacity=24,
            ),
            _pool(
                "participant-pool",
                owner_kind="participant",
                owner_ref="participant.behavior.participant-agent",
                resource_kind="concurrent_actions",
                unit="actions",
                meter_profile_ref="raes.concurrent-action/v1",
                capacity=2,
            ),
            _pool(
                "range-pool",
                owner_kind="deployment_tenant",
                owner_ref="deployment.tenant.range-a",
                resource_kind="action_rate",
                unit="actions",
                meter_profile_ref="raes.action-attempt/v1",
                capacity=240,
            ),
            _pool(
                "range-pool",
                owner_kind="deployment_tenant",
                owner_ref="deployment.tenant.range-a",
                resource_kind="storage_growth",
                unit="bytes",
                meter_profile_ref="raes.logical-byte/v1",
                capacity=1048576,
            ),
            _pool(
                "inference-pool",
                owner_kind="shared_service",
                owner_ref="provision.node.customer-portal.service.http",
                resource_kind="inference_tokens",
                unit="tokens",
                meter_profile_ref="tokenizer.example/v1",
                capacity=20000,
            ),
            _pool(
                "inference-pool",
                owner_kind="shared_service",
                owner_ref="provision.node.customer-portal.service.http",
                resource_kind="image_generations",
                unit="images",
                meter_profile_ref="raes.image-generation/v1",
                capacity=20,
            ),
            _pool(
                "fleet-pool",
                owner_kind="fleet",
                owner_ref="fleet.primary",
                resource_kind="action_rate",
                unit="actions",
                meter_profile_ref="raes.action-attempt/v1",
                capacity=2400,
            ),
            _pool(
                "accelerator-pool",
                owner_kind="fleet",
                owner_ref="fleet.primary",
                resource_kind="accelerator",
                unit="accelerator_milliseconds",
                meter_profile_ref="raes.accelerator-class.generic/v1",
                capacity=60000,
            ),
        ),
        realization_contract_ids=frozenset(
            {
                "participant-resource-budget-state-v1",
                "participant-resource-budget-event-v1",
            }
        ),
    )


def _governed_manifest() -> object:
    base_runtime = compile_runtime_model(parse_sdl(_activity_policy_yaml()))
    manifest = _autonomous_manifest(base_runtime)
    capability = manifest.participant_runtime
    assert capability is not None
    governed = replace(
        capability,
        supported_autonomous_policy_profiles=(
            capability.supported_autonomous_policy_profiles | {"participant-autonomous-execution/v3"}
        ),
        resource_budgets=_capabilities(),
    )
    return replace(
        manifest,
        capabilities=replace(manifest.capabilities, participant_runtime=governed),
    )


def test_v3_resource_budget_compiles_complete_typed_vector() -> None:
    runtime_model = compile_runtime_model(parse_sdl(_budget_policy_yaml()))
    policy = next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )

    assert policy.profile == "participant-autonomous-execution/v3"
    assert {demand.resource_kind for demand in policy.resource_demands} == {
        "action_rate",
        "concurrent_actions",
        "storage_growth",
        "inference_tokens",
        "image_generations",
        "accelerator",
    }
    assert {owner.kind for owner in policy.resource_owners} == {
        "participant",
        "deployment_tenant",
        "shared_service",
        "fleet",
    }
    assert policy.resource_fairness.priority_class == "background"


def test_resource_owners_must_bind_to_authorized_execution_topology() -> None:
    payload = yaml.safe_load(_budget_policy_yaml())
    del payload["relationships"]["range-a-inference-service"]
    serialized = yaml.safe_dump(payload, sort_keys=False)

    with pytest.raises(
        SDLValidationError,
        match="lacks an authorized tenant uses_shared_service edge",
    ):
        parse_sdl(serialized)


def test_composition_rewrites_kind_specific_resource_owner_refs() -> None:
    payload = yaml.safe_load(_budget_policy_yaml())
    payload["module"] = {
        "id": "example/resource-governed-participant",
        "version": "1.0.0",
        "exports": {
            "agents": ["participant-agent"],
            "behavior_specifications": ["participant-behavior"],
            "deployment_tenants": ["range-a", "range-b"],
            "nodes": ["customer-portal"],
        },
    }
    imported = parse_sdl(yaml.safe_dump(payload, sort_keys=False))
    assert imported.module is not None
    namespaced = _namespace_payload(
        payload,
        imported,
        "shared",
        imported.module,
    )

    owners = namespaced["behavior_specifications"]["shared.participant-behavior"]["autonomous_execution"][
        "resource_budget"
    ]["owners"]
    assert owners["green"]["ref"] == "shared.participant-agent"
    assert owners["range-a"]["ref"] == "shared.range-a"
    assert owners["inference"]["ref"] == "nodes.shared.customer-portal.services.http"
    assert owners["fleet"]["ref"] == "fleet.primary"


def test_v3_resource_budget_rejects_incompatible_units_cycles_and_episode_reset() -> None:
    payload = yaml.safe_load(_budget_policy_yaml())
    dimensions = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]["resource_budget"][
        "dimensions"
    ]

    dimensions["tokens"]["unit"] = "bytes"
    policy = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    with pytest.raises(ValueError, match="inference_tokens.*tokens"):
        ParticipantAutonomousExecutionPolicyV3.model_validate(policy)

    payload = yaml.safe_load(_budget_policy_yaml())
    dimensions = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]["resource_budget"][
        "dimensions"
    ]
    dimensions["range-actions"]["limit"] = 24
    dimensions["fleet-actions"]["limit"] = 24
    dimensions["fleet-actions"]["parent_budget_ref"] = "participant-actions"
    policy = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    with pytest.raises(ValueError, match="acyclic"):
        ParticipantAutonomousExecutionPolicyV3.model_validate(policy)

    payload = yaml.safe_load(_budget_policy_yaml())
    dimensions = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]["resource_budget"][
        "dimensions"
    ]
    dimensions["storage"]["reset"] = "episode"
    policy = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    with pytest.raises(ValueError, match="storage_growth.*reconciled"):
        ParticipantAutonomousExecutionPolicyV3.model_validate(policy)

    payload = yaml.safe_load(_budget_policy_yaml())
    dimensions = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]["resource_budget"][
        "dimensions"
    ]
    dimensions["tokens-copy"] = dict(dimensions["tokens"])
    policy = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    with pytest.raises(ValueError, match="alias the same canonical resource pool"):
        ParticipantAutonomousExecutionPolicyV3.model_validate(policy)


def test_resource_event_rejects_contradictory_transition_disposition() -> None:
    payload = json.loads(
        (
            REPO_ROOT
            / "contracts/fixtures/participant-runtime/participant-resource-budget-event-v1/valid/token-commit-event.json"
        ).read_text(encoding="utf-8")
    )
    payload["disposition"] = "released"
    with pytest.raises(ValueError, match="disposition must match"):
        ParticipantResourceBudgetEventModel.model_validate(payload)


def test_legacy_profiles_compile_into_canonical_demand_representation() -> None:
    _, v1 = _compiled()
    v2 = next(
        specification.autonomous_execution
        for specification in compile_runtime_model(parse_sdl(_activity_policy_yaml())).behavior_specifications.values()
        if specification.autonomous_execution is not None
    )

    for policy in (v1, v2):
        by_kind = {demand.resource_kind: demand for demand in policy.resource_demands}
        assert by_kind["action_rate"].limit == policy.max_action_attempts
        assert by_kind["concurrent_actions"].limit == policy.max_in_flight
        assert by_kind["action_rate"].provenance == "legacy_maximum"


def test_manifest_round_trip_separates_support_capacity_and_realization() -> None:
    runtime_model, _ = _compiled()
    manifest = _autonomous_manifest(runtime_model, with_realization_envelope=False)
    capability = manifest.participant_runtime
    assert capability is not None
    governed = replace(capability, resource_budgets=_capabilities())
    governed_manifest = replace(
        manifest,
        capabilities=replace(manifest.capabilities, participant_runtime=governed),
    )

    from raes_backend_protocols.manifest import (
        backend_manifest_from_v2_model,
        backend_manifest_v2_model,
    )

    wire = backend_manifest_v2_model(governed_manifest)
    restored = backend_manifest_from_v2_model(wire)

    assert restored.participant_runtime is not None
    restored_budgets = restored.participant_runtime.resource_budgets
    assert restored_budgets is not None
    assert restored_budgets.support_strength == "exact"
    assert restored_budgets.configured_pools[0].configuration_digest.startswith("sha256:")
    assert "participant-resource-budget-event-v1" in restored_budgets.realization_contract_ids


def test_admission_is_atomic_for_complete_vector_and_exact_meters() -> None:
    runtime_model = compile_runtime_model(parse_sdl(_budget_policy_yaml()))
    policy = next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )
    admitted_manifest = _governed_manifest()
    governed = admitted_manifest.participant_runtime
    assert governed is not None

    assert (
        participant_autonomous_execution_capability_gaps(
            admitted_manifest,
            (policy,),
            runtime_model.time_model,
        )
        == ()
    )

    weakened_pools = tuple(
        replace(pool, capacity=499) if pool.resource_kind == "inference_tokens" else pool
        for pool in _capabilities().configured_pools
    )
    weakened = replace(_capabilities(), configured_pools=weakened_pools)
    weakened_manifest = replace(
        admitted_manifest,
        capabilities=replace(
            admitted_manifest.capabilities,
            participant_runtime=replace(governed, resource_budgets=weakened),
        ),
    )
    gaps = participant_autonomous_execution_capability_gaps(
        weakened_manifest,
        (policy,),
        runtime_model.time_model,
    )
    assert any("inference_tokens" in gap and "capacity" in gap for gap in gaps)

    weak_fairness = replace(
        _capabilities(),
        configured_pools=tuple(
            replace(pool, priority_classes=("evaluated", "standard")) for pool in _capabilities().configured_pools
        ),
    )
    fairness_manifest = replace(
        admitted_manifest,
        capabilities=replace(
            admitted_manifest.capabilities,
            participant_runtime=replace(governed, resource_budgets=weak_fairness),
        ),
    )
    fairness_gaps = participant_autonomous_execution_capability_gaps(
        fairness_manifest,
        (policy,),
        runtime_model.time_model,
    )
    assert any("priority class background" in gap for gap in fairness_gaps)

    incomplete_manifest = replace(
        admitted_manifest,
        supported_contract_versions=(
            admitted_manifest.supported_contract_versions - {"participant-resource-pool-capacity-v1"}
        ),
    )
    contract_gaps = participant_autonomous_execution_capability_gaps(
        incomplete_manifest,
        (policy,),
        runtime_model.time_model,
    )
    assert any(
        "missing manifest contracts" in gap and "participant-resource-pool-capacity-v1" in gap for gap in contract_gaps
    )

    competing = replace(policy, address=f"{policy.address}.competing")
    aggregate_gaps = participant_autonomous_execution_capability_gaps(
        admitted_manifest,
        (policy, competing),
        runtime_model.time_model,
    )
    assert any("aggregate policy limits" in gap for gap in aggregate_gaps)


def test_runtime_pool_ledger_prevents_competing_policy_overcommit() -> None:
    runtime_model = compile_runtime_model(parse_sdl(_budget_policy_yaml()))
    policy = next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )
    competing = replace(policy, address=f"{policy.address}.competing")
    initialized = initialize_participant_resource_budgets(
        RuntimeSnapshot(),
        (policy, competing),
        _capabilities(),
        execution_generation=0,
    )
    assert initialized.success
    assert len(initialized.snapshot.participant_resource_budget_states) == 16

    first = reserve_participant_resources(
        initialized.snapshot,
        policy,
        operation_id="first-policy",
        execution_generation=0,
        requested_quantities={"participant-actions": 23},
    )
    assert first.success
    second = reserve_participant_resources(
        first.snapshot,
        competing,
        operation_id="competing-policy",
        execution_generation=0,
    )
    assert second.success is False
    assert second.diagnostics[0].code == "runtime.participant-resource-throttled"
    assert "shared pool" in second.diagnostics[0].message


def test_runtime_reserve_commit_throttle_and_idempotency_are_generation_fenced(
    tmp_path: Path,
) -> None:
    runtime_model = compile_runtime_model(parse_sdl(_budget_policy_yaml()))
    policy = next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )
    initialized = initialize_participant_resource_budgets(
        RuntimeSnapshot(),
        (policy,),
        _capabilities(),
        execution_generation=3,
    )
    assert initialized.success

    reserved = reserve_participant_resources(
        initialized.snapshot,
        policy,
        operation_id="action-1",
        execution_generation=3,
    )
    assert reserved.success
    repeated = reserve_participant_resources(
        reserved.snapshot,
        policy,
        operation_id="action-1",
        execution_generation=3,
    )
    assert repeated.success
    assert repeated.snapshot.participant_resource_budget_events == (
        reserved.snapshot.participant_resource_budget_events
    )

    committed = commit_participant_resource_reservation(
        reserved.snapshot,
        operation_id="action-1",
        execution_generation=3,
        measured_quantities=_measured_vector(reserved.snapshot, "action-1", tokens=450),
        evidence_refs=("evidence.resource-meter.action-1",),
    )
    assert committed.success
    state = ParticipantResourceBudgetStateModel.model_validate(
        committed.snapshot.participant_resource_budget_states[
            participant_resource_budget_state_ref(policy.address, "tokens")
        ]
    )
    assert state.reserved == 0
    assert state.cumulative_use == 450
    assert state.evidence_refs == ("evidence.resource-meter.action-1",)

    store = LocalControlPlaneStore(tmp_path / "control-plane")
    store.save_snapshot(
        committed.snapshot,
        expected_revision=store.load_snapshot_state().revision,
    )
    restored = store.load_snapshot()
    assert restored.participant_resource_budget_states == (committed.snapshot.participant_resource_budget_states)
    assert restored.participant_resource_budget_events == (committed.snapshot.participant_resource_budget_events)

    stale = reserve_participant_resources(
        restored,
        policy,
        operation_id="action-stale",
        execution_generation=2,
    )
    assert stale.success is False
    assert stale.snapshot is restored
    assert stale.diagnostics[0].code == "runtime.participant-resource-stale-generation"

    exhausted = reserve_participant_resources(
        restored,
        policy,
        operation_id="action-too-large",
        execution_generation=3,
        requested_quantities={"tokens": 20000},
    )
    assert exhausted.success is False
    event = ParticipantResourceBudgetEventModel.model_validate(
        next(
            payload
            for payload in exhausted.snapshot.participant_resource_budget_events.values()
            if payload["operation_id"] == "action-too-large"
        )
    )
    assert event.disposition == "throttled"


def test_reset_reconciles_participant_window_without_erasing_persistent_owners() -> None:
    runtime_model = compile_runtime_model(parse_sdl(_budget_policy_yaml()))
    policy = next(
        specification.autonomous_execution
        for specification in runtime_model.behavior_specifications.values()
        if specification.autonomous_execution is not None
    )
    initialized = initialize_participant_resource_budgets(
        RuntimeSnapshot(),
        (policy,),
        _capabilities(),
        execution_generation=0,
    )
    reserved = reserve_participant_resources(
        initialized.snapshot,
        policy,
        operation_id="action-1",
        execution_generation=0,
    )
    committed = commit_participant_resource_reservation(
        reserved.snapshot,
        operation_id="action-1",
        execution_generation=0,
        measured_quantities=_measured_vector(
            reserved.snapshot,
            "action-1",
            participant_actions=1,
            storage=4096,
        ),
        evidence_refs=("evidence.action-1",),
    )
    reconciled = reconcile_participant_resource_budgets(
        committed.snapshot,
        policy_address=policy.address,
        current_generation=0,
        next_generation=1,
        boundary="time_segment",
        evidence_refs=("evidence.reset.generation-1",),
    )
    assert reconciled.success

    states = {
        key: ParticipantResourceBudgetStateModel.model_validate(value)
        for key, value in reconciled.snapshot.participant_resource_budget_states.items()
    }
    participant_actions_ref = participant_resource_budget_state_ref(policy.address, "participant-actions")
    storage_ref = participant_resource_budget_state_ref(policy.address, "storage")
    assert states[participant_actions_ref].cumulative_use == 0
    assert states[participant_actions_ref].generation == 1
    assert states[storage_ref].cumulative_use == 4096
    assert states[storage_ref].generation == 1


def test_runtime_manager_enforces_v3_budgets_and_reconciles_reset_generation() -> None:
    scenario = parse_sdl(_budget_policy_yaml())
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _NativeParticipantRuntime()
    target = replace(
        create_stub_target(),
        manifest=_governed_manifest(),
        participant_runtime=participant_runtime,
    )
    manager = RuntimeManager(target, stochastic_controls=[_activity_control()])

    applied = manager.apply(manager.plan(scenario))

    assert applied.success
    service = next(iter(applied.snapshot.participant_execution_services.values()))
    assert set(service["resource_budget_state_refs"]) == set(applied.snapshot.participant_resource_budget_states)
    scheduler_state = next(iter(applied.snapshot.participant_autonomous_execution_states.values()))
    due = _advance_stepped_clock_to_tick(manager, scheduler_state["next_tick"])
    assert due.success
    assert any(event["transition"] == "commit" for event in due.snapshot.participant_resource_budget_events.values())

    reset = manager.reset_time("time.clock.scenario-clock")

    assert reset.success
    assert {state["generation"] for state in reset.snapshot.participant_resource_budget_states.values()} == {1}


def test_scheduler_releases_reservations_when_native_measurements_are_absent() -> None:
    scenario = parse_sdl(_budget_policy_yaml())
    runtime_model = compile_runtime_model(scenario)
    target = replace(
        create_stub_target(),
        manifest=_governed_manifest(),
        participant_runtime=_UnmeasuredParticipantRuntime(),
    )
    manager = RuntimeManager(target, stochastic_controls=[_activity_control()])
    applied = manager.apply(manager.plan(scenario))
    assert applied.success
    scheduler_state = next(iter(applied.snapshot.participant_autonomous_execution_states.values()))

    assert scheduler_state["next_tick"] == SCENARIO_CLOCK_STEP_TICKS
    due = manager.advance_time(SCENARIO_CLOCK_ADDRESS, ticks=SCENARIO_CLOCK_STEP_TICKS)

    assert due.success is False
    assert any(
        diagnostic.code == "runtime.participant-resource-measurement-untrusted" for diagnostic in due.diagnostics
    )
    assert all(state["reserved"] == 0 for state in due.snapshot.participant_resource_budget_states.values())
    assert not any(
        event["transition"] == "commit" for event in due.snapshot.participant_resource_budget_events.values()
    )


def test_cross_range_shared_pool_requires_partitioned_isolation() -> None:
    capabilities = _capabilities()
    shared = tuple(
        replace(pool, tenant_isolation="none") if pool.pool_ref == "inference-pool" else pool
        for pool in capabilities.configured_pools
    )
    cross_range_pool_refs = frozenset({"inference-pool"})

    with pytest.raises(ValueError, match="cross-range.*tenant_partitioned"):
        ParticipantResourceBudgetCapabilities(
            support_strength=capabilities.support_strength,
            supported_owner_kinds=capabilities.supported_owner_kinds,
            supported_resource_kinds=capabilities.supported_resource_kinds,
            supported_accounting_modes=capabilities.supported_accounting_modes,
            supported_reset_modes=capabilities.supported_reset_modes,
            supported_fairness_policies=capabilities.supported_fairness_policies,
            supported_isolation_strengths=capabilities.supported_isolation_strengths,
            configured_pools=shared,
            realization_contract_ids=capabilities.realization_contract_ids,
            cross_range_pool_refs=cross_range_pool_refs,
        )


@pytest.mark.parametrize(
    ("contract_id", "model", "filename"),
    [
        (
            "participant-resource-budget-policy-v1",
            ParticipantResourceBudgetPolicyModel,
            "complete-resource-vector.json",
        ),
        (
            "participant-resource-pool-capacity-v1",
            ParticipantResourcePoolCapacityModel,
            "configured-inference-pool.json",
        ),
        (
            "participant-resource-budget-state-v1",
            ParticipantResourceBudgetStateModel,
            "token-budget-state.json",
        ),
        (
            "participant-resource-budget-event-v1",
            ParticipantResourceBudgetEventModel,
            "token-commit-event.json",
        ),
    ],
)
def test_published_resource_budget_fixtures_match_contract_models(
    contract_id: str,
    model: type[BaseModel],
    filename: str,
) -> None:
    payload = json.loads(
        (REPO_ROOT / "contracts" / "fixtures" / "participant-runtime" / contract_id / "valid" / filename).read_text(
            encoding="utf-8"
        )
    )

    model.model_validate(payload)
    assert schema_bundle()[contract_id]["additionalProperties"] is False
