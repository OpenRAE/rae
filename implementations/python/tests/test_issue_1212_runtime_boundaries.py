"""Real API and persistence boundaries for scoped observation policy."""

from dataclasses import replace

import pytest
from raes.parser import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.observation_demand import (
    AchievedObservationValue,
    EffectiveObservationDemand,
    ObservationBasis,
    ObservationDemandDocument,
    ObservationDemandRule,
    ObservationLifecycleStage,
    ObservationSelector,
    normalize_observation_demands,
)
from raes_contracts.plan_projection import evaluation_plan_model
from raes_contracts.planning import ProvisioningPlan
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole, ControlPlaneSecurityConfig
from raes_runtime.control_plane_store import InMemoryControlPlaneStore
from raes_runtime.manager import RuntimeManager
from raes_runtime.observation_execution import (
    ConfiguredObservationRuntime,
    ObservationRuntimeCapability,
    ObservationSelectorPattern,
)
from starlette.testclient import TestClient


def _demands(selector, **policy):
    return normalize_observation_demands(
        ObservationDemandDocument(
            schema_version="observation-demand/v1",
            document_id="runtime-boundaries",
            scope_profile="recursive-realization-constraint/v1",
            rules=(
                ObservationDemandRule(
                    rule_id="request",
                    scope=selector.semantic_scope,
                    mode="selected",
                    selector=selector,
                    redaction="none",
                    integrity="none",
                    **policy,
                ),
            ),
        ),
        target_scopes=(selector.semantic_scope,),
    ).effective


def _runtime(selector, *, producer=None, describer=None, stages=frozenset(), redactors=None):
    return ConfiguredObservationRuntime(
        capabilities=(
            ObservationRuntimeCapability(
                capability_id="test-observation",
                selector_pattern=ObservationSelectorPattern(
                    data_kind=selector.data_kind,
                    names=frozenset(selector.names),
                ),
                capture_kind="trace",
                channel_kind="runtime-snapshot",
                stages=stages,
                bases=frozenset({ObservationBasis.BACKEND_SELECTED}) if describer else frozenset(),
                redaction_policies=frozenset(redactors or ()),
            ),
        ),
        producers={"test-observation": producer} if producer else {},
        describers={"test-observation": describer} if describer else {},
        redactors=redactors,
    )


@pytest.mark.parametrize("retention", ["disable", "forbid", "require"])
def test_description_persistence_and_recovery_require_retention(retention):
    selector = ObservationSelector(semantic_scope="", data_kind="field", names=("distribution",))
    demands = _demands(
        selector,
        purpose="realization-description",
        collection="require" if retention == "require" else "disable",
        retention=retention,
        export="forbid",
        required=True,
    )
    runtime = _runtime(
        selector,
        stages=frozenset({ObservationLifecycleStage.RETENTION}),
        describer=lambda *_: AchievedObservationValue("protected-description", ObservationBasis.BACKEND_SELECTED),
    )
    target = replace(create_stub_target(), observation_runtime=runtime)
    store = InMemoryControlPlaneStore()
    cp = RuntimeControlPlane(target, store=store)
    receipt = cp.submit_provisioning(ProvisioningPlan(observation_demands=demands))
    assert receipt.accepted
    assert cp.get_operation(receipt.operation_id).state.value == "succeeded"
    payload = store.load_records()[receipt.operation_id].result_payload
    assert ("protected-description" in repr(payload)) == (retention == "require")
    recovered = RuntimeControlPlane(target, store=store).observation_execution(receipt.operation_id)
    assert bool(recovered.realized_form_disclosures) == (retention == "require")


def test_same_selector_report_retains_only_the_authorized_protected_variant():
    selector = ObservationSelector(semantic_scope="", data_kind="field", names=("distribution",))
    rules = tuple(
        ObservationDemandRule(
            rule_id=authority,
            authority_ref=authority,
            scope="",
            purpose="realization-description",
            mode="selected",
            selector=selector,
            collection="require",
            retention=retention,
            redaction=redaction,
        )
        for authority, retention, redaction in (
            ("immediate", "disable", "none"),
            ("archive", "require", "scrub"),
        )
    )
    resolution = normalize_observation_demands(
        ObservationDemandDocument(
            schema_version="observation-demand/v1",
            document_id="shared-selector",
            scope_profile="recursive-realization-constraint/v1",
            rules=rules,
        ),
        target_scopes=("",),
    )
    assert resolution.is_valid
    runtime = _runtime(
        selector,
        stages=frozenset({ObservationLifecycleStage.RETENTION}),
        describer=lambda *_: AchievedObservationValue("private-value", ObservationBasis.BACKEND_SELECTED),
        redactors={"scrub": lambda _: ("[REDACTED]",)},
    )
    target = replace(create_stub_target(), observation_runtime=runtime)
    store = InMemoryControlPlaneStore()
    cp = RuntimeControlPlane(target, store=store)
    receipt = cp.submit_provisioning(ProvisioningPlan(observation_demands=resolution.effective))
    assert receipt.accepted
    assert cp.get_operation(receipt.operation_id).state.value == "succeeded"
    payload = store.load_records()[receipt.operation_id].result_payload
    assert "private-value" not in repr(payload)
    recovered = RuntimeControlPlane(target, store=store).observation_execution(receipt.operation_id)
    assert len(recovered.realized_form_disclosures) == 1
    assert recovered.realized_form_disclosures[0].realized_value_summary == '"[REDACTED]"'


@pytest.mark.parametrize("required", [False, True])
def test_export_without_delivery_owner_is_rejected_before_collection(required):
    selector = ObservationSelector(semantic_scope="", data_kind="stream", names=("trace",))
    calls = []
    runtime = _runtime(
        selector,
        producer=lambda *_: calls.append("collect") or ("private",),
        stages=frozenset({ObservationLifecycleStage.COLLECTION, ObservationLifecycleStage.EXPORT}),
    )
    target = replace(create_stub_target(), observation_runtime=runtime)
    cp = RuntimeControlPlane(target, store=InMemoryControlPlaneStore())
    receipt = cp.submit_provisioning(
        ProvisioningPlan(
            observation_demands=_demands(
                selector,
                purpose="experimental",
                collection="require",
                export="require",
                required=required,
            )
        )
    )
    assert not receipt.accepted
    assert receipt.diagnostics[0].code == "observation.export-runtime-unavailable"
    assert calls == []


def test_runtime_rejects_required_prohibited_overlap_before_collection():
    selector = ObservationSelector(semantic_scope="", data_kind="stream", names=("trace",))
    calls = []
    runtime = _runtime(
        selector,
        producer=lambda *_: calls.append("collect") or ("private",),
        stages=frozenset({ObservationLifecycleStage.COLLECTION}),
    )
    target = replace(create_stub_target(), observation_runtime=runtime)
    demand = EffectiveObservationDemand(
        scope="",
        purpose="experimental",
        mode="selected",
        selectors=(selector,),
        collection="require",
        retention="disable",
        export="disable",
        basis="observed",
        prohibited_stages=(ObservationLifecycleStage.COLLECTION,),
        required=True,
    )

    receipt = RuntimeControlPlane(target).submit_provisioning(ProvisioningPlan(observation_demands=(demand,)))

    assert not receipt.accepted
    assert receipt.diagnostics[0].code == "observation.required-prohibited-conflict"
    assert calls == []


def test_api_policy_removal_cannot_start_evaluator():
    scenario = parse_sdl("""
name: protected-evaluation
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
""")
    target = create_stub_target()
    cp = RuntimeControlPlane(target)
    execution = RuntimeManager(target).plan(scenario)
    assert cp.submit_provisioning(execution.provisioning).accepted
    selector = ObservationSelector(semantic_scope="/nodes/vm", data_kind="stream", names=("audit",))
    approved = replace(
        execution.evaluation,
        observation_demands=_demands(
            selector,
            purpose="experimental",
            collection="require",
            required=True,
        ),
    )
    cp.register_planner_produced_plan(approved)
    security = ControlPlaneSecurityConfig(
        trust_proxy_identity_headers=True,
        trusted_identities={
            "backend-service": ControlPlaneIdentity(
                identity="backend-service",
                roles=frozenset({ControlPlaneRole.BACKEND}),
                target_name=target.name,
            )
        },
    )
    payload = evaluation_plan_model(approved).model_dump(mode="json", exclude_none=True)
    payload["observation_demands"] = []
    baseline = cp.snapshot
    with TestClient(create_control_plane_app(cp, security=security)) as client:
        response = client.post(
            "/operations/evaluation",
            json=payload,
            headers={
                "x-raes-client-verified": "true",
                "x-raes-client-identity": "backend-service",
            },
        )
    assert response.status_code == 403
    assert cp.snapshot == baseline
    assert not any(address.startswith("evaluation.") for address in cp.snapshot.entries)


@pytest.mark.parametrize("owner", ["manager", "control-plane"])
def test_mandatory_capture_cannot_mutate_a_non_compensating_backend(owner):
    calls = []
    selector = ObservationSelector(semantic_scope="/nodes/vm", data_kind="stream", names=("audit",))
    runtime = _runtime(
        selector,
        producer=lambda *_: calls.append("collect") or ("audit",),
        stages=frozenset({ObservationLifecycleStage.COLLECTION}),
    )
    target = replace(create_stub_target(), observation_runtime=runtime)
    original = target.provisioner.apply

    def apply(plan, snapshot):
        calls.append("apply")
        return original(plan, snapshot)

    target.provisioner.apply = apply
    manager = RuntimeManager(target)
    execution = manager.plan(parse_sdl("name: no-mutation\nnodes:\n  vm: {type: compute}\n"))
    demanded = replace(
        execution.provisioning,
        observation_demands=_demands(
            selector,
            purpose="experimental",
            collection="require",
            required=True,
        ),
    )
    if owner == "manager":
        result = manager.apply(replace(execution, provisioning=demanded))
        assert not result.success
    else:
        result = RuntimeControlPlane(target).submit_provisioning(demanded)
        assert not result.accepted
    assert result.diagnostics[0].code == "observation.required-execution-atomicity-unavailable"
    assert calls == []


def test_builtin_backends_describe_bound_selection_without_capture():
    from test_cross_backend_minimal_scenario import _targets

    scenario = parse_sdl("""
name: selected-backend-description
nodes:
  vm: {type: compute, resources: {ram: 1 gib, cpu: 1}}
evidence_requirements:
  substrate:
    source_class: processor_backend
    scope_refs: [nodes.vm]
    window: run
    channel: api_response
    sensitivity: plain
    redaction: none
    integrity: none
    retention: not_retained
    loss_disclosure: required
    observation_demand:
      rule_id: substrate
      scope: /nodes/vm
      purpose: realization-description
      mode: selected
      selector: {semantic_scope: /nodes/vm, data_kind: field, names: [compute-substrate]}
      basis: backend-selected
""")
    for name, target in _targets():
        manager = RuntimeManager(target)
        result = manager.apply(manager.plan(scenario))
        assert result.success, (name, result.diagnostics)
        [disclosure] = result.details["realized_form_disclosures"]
        assert disclosure["basis"] == "backend-realized"
        assert "provision.node.vm" in disclosure["realized_value_summary"]
        assert not disclosure["evidence_refs"]
        assert result.snapshot.realization_observations == ()
