"""All plan domains share the result gate; openness never changes ownership."""

from dataclasses import fields, replace

import pytest
from raes_contracts.planning import (
    ChangeAction,
    EvaluationOp,
    EvaluationPlan,
    OrchestrationOp,
    OrchestrationPlan,
    ProvisioningPlan,
    ProvisionOp,
    RuntimeDomain,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_runtime.backend_calls import _call_backend_apply
from raes_runtime.backend_realization_authority import _RealizationApplyContext
from raes_runtime.backend_snapshot_contracts import (
    SNAPSHOT_CARRIER_OWNERS,
    SNAPSHOT_VALUE_OWNERS,
    snapshot_shape_violation,
)

_DOMAINS = [
    (ProvisioningPlan, ProvisionOp, RuntimeDomain.PROVISIONING, "feature-binding", "provision.feature.web.lab"),
    (OrchestrationPlan, OrchestrationOp, RuntimeDomain.ORCHESTRATION, "script", "orchestration.script.lab"),
    (EvaluationPlan, EvaluationOp, RuntimeDomain.EVALUATION, "assertion", "evaluation.assertion.lab"),
]


@pytest.mark.parametrize("plan_type,op_type,domain,kind,address", _DOMAINS)
@pytest.mark.parametrize("perturb", [None, "type", "domain", "accounting", "metadata"])
def test_domain_plan_owns_identity_accounting_and_preserved_metadata(
    plan_type, op_type, domain, kind, address, perturb
):
    previous = RuntimeSnapshot(metadata={"trusted": ["predecessor"]})
    plan = plan_type(operations=[op_type(ChangeAction.CREATE, address, kind, {"name": "lab"})])
    entry = SnapshotEntry(address, domain, kind, {"name": "lab"})
    messages = {
        "type": "Backend changed a plan-owned resource type.",
        "domain": "Backend changed a plan-owned runtime domain.",
        "accounting": "Backend omitted an authorized resource change.",
        "metadata": "Backend changed runtime-owned snapshot metadata.",
    }
    if perturb == "type":
        entry = replace(entry, resource_type="node")
    if perturb == "domain":
        entry = replace(entry, domain=RuntimeDomain.PARTICIPANT)
    candidate = previous.with_entries({address: entry})
    if perturb == "metadata":
        candidate.metadata = {"candidate": "untrusted"}
    result = _call_backend_apply(
        lambda *_: ApplyResult(True, candidate, changed_addresses=[] if perturb == "accounting" else [address]),
        plan,
        previous,
        address="runtime.apply.test",
        snapshot=previous,
    )
    if perturb is None:
        assert result.success, result.diagnostics
    else:
        assert result.success is False
        assert result.snapshot == previous
        assert result.changed_addresses == []
        assert [(item.code, item.message) for item in result.diagnostics] == [
            ("runtime.backend-contract-invalid", messages[perturb])
        ]


def test_each_snapshot_field_has_one_exhaustive_owner_classification():
    assert SNAPSHOT_CARRIER_OWNERS.keys().isdisjoint(SNAPSHOT_VALUE_OWNERS)
    assert {
        item.name for item in fields(RuntimeSnapshot)
    } == SNAPSHOT_CARRIER_OWNERS.keys() | SNAPSHOT_VALUE_OWNERS.keys()


@pytest.mark.parametrize("field", ["time_management_contexts", "metadata"])
def test_snapshot_shape_rejects_a_populated_field_with_missing_owner(monkeypatch, field):
    snapshot = RuntimeSnapshot(
        time_management_contexts={
            "time.context.extra": {
                "context_id": "time.context.extra",
                "mode": "unsupported",
                "unsupported_disclosure": True,
            }
        },
        metadata={"trusted": "predecessor"},
    )
    assert snapshot_shape_violation(snapshot) is None
    owners = SNAPSHOT_CARRIER_OWNERS if field in SNAPSHOT_CARRIER_OWNERS else SNAPSHOT_VALUE_OWNERS
    monkeypatch.delitem(owners, field)
    assert snapshot_shape_violation(snapshot) == "Backend snapshot contains an unclassified carrier."


def test_provisioner_cannot_populate_an_unrelated_domain_carrier():
    previous = RuntimeSnapshot()
    candidate = RuntimeSnapshot(
        time_management_contexts={
            "time.context.extra": {
                "context_id": "time.context.extra",
                "mode": "unsupported",
                "unsupported_disclosure": True,
            }
        }
    )
    result = _call_backend_apply(
        lambda *_: ApplyResult(True, candidate),
        ProvisioningPlan(),
        previous,
        address="runtime.apply.provisioning",
        snapshot=previous,
    )
    assert result.success is False
    assert result.snapshot == previous
    assert result.diagnostics[0].message == "Backend changed a snapshot carrier outside its runtime-domain authority."


def test_effect_capable_call_without_context_cannot_create_portable_state():
    previous = RuntimeSnapshot()
    address = "orchestration.script.extra"
    candidate = RuntimeSnapshot(entries={address: SnapshotEntry(address, RuntimeDomain.ORCHESTRATION, "script", {})})
    result = _call_backend_apply(
        lambda *_: ApplyResult(True, candidate, changed_addresses=[address]),
        previous,
        address="runtime.test",
        snapshot=previous,
    )
    assert result.success is False
    assert result.snapshot == previous
    assert result.diagnostics[0].message == "Backend changed a resource outside the submitted authority."


@pytest.mark.parametrize("remove_unowned", [False, True])
def test_service_stop_is_bound_to_its_explicit_runtime_domain(remove_unowned):
    owned = "evaluation.assertion.lab"
    unowned = "orchestration.script.lab"
    previous = RuntimeSnapshot(
        entries={
            owned: SnapshotEntry(owned, RuntimeDomain.EVALUATION, "assertion", {}),
            unowned: SnapshotEntry(unowned, RuntimeDomain.ORCHESTRATION, "script", {}),
        }
    )
    candidate = previous.with_entries({} if remove_unowned else {unowned: previous.entries[unowned]})
    result = _call_backend_apply(
        lambda *_: ApplyResult(True, candidate, changed_addresses=[owned, unowned] if remove_unowned else [owned]),
        previous,
        address="runtime.stop",
        snapshot=previous,
        realization=_RealizationApplyContext(stop_domain=RuntimeDomain.EVALUATION),
    )
    assert result.success is not remove_unowned
    if remove_unowned:
        assert result.snapshot == previous
        assert result.diagnostics[0].message == "Backend changed a resource outside the submitted authority."


def test_owned_carrier_changes_require_honest_accounting():
    from test_run_308_concurrent_participant_execution import _snapshot_payload

    previous = RuntimeSnapshot()
    candidate = RuntimeSnapshot(**{key: value for key, value in _snapshot_payload().items() if key != "schema_version"})
    result = _call_backend_apply(
        lambda *_: ApplyResult(True, candidate),
        previous,
        address="runtime.participant",
        snapshot=previous,
        realization=_RealizationApplyContext(effect_owners=frozenset({"participant"})),
    )
    assert result.success is False
    assert result.snapshot == previous
    assert result.diagnostics[0].message == "Backend omitted a snapshot carrier change."


def test_runtime_metadata_preserves_json_type_identity():
    previous = RuntimeSnapshot(metadata={"trusted": 1})
    candidate = RuntimeSnapshot(metadata={"trusted": True})
    result = _call_backend_apply(
        lambda *_: ApplyResult(True, candidate),
        ProvisioningPlan(),
        previous,
        address="runtime.apply.provisioning",
        snapshot=previous,
    )
    assert result.success is False
    assert type(result.snapshot.metadata["trusted"]) is int
    assert result.diagnostics[0].message == "Backend changed runtime-owned snapshot metadata."


@pytest.mark.parametrize("stub", [False, True])
def test_reference_evaluator_partial_refresh_preserves_unchanged_results(stub):
    from raes_backend_stubs.stubs import StubEvaluator
    from raes_reference_backend.evaluator import ReferenceEvaluator

    evaluator = StubEvaluator() if stub else ReferenceEvaluator()
    addresses = ("evaluation.condition.web.first", "evaluation.condition.web.second")
    operations = [
        EvaluationOp(
            ChangeAction.CREATE,
            address,
            "condition-binding",
            {
                "name": address.rsplit(".", 1)[-1],
                "result_contract": {
                    "state_schema_version": "evaluation-result-state/v1",
                    "resource_type": "condition",
                    "supports_passed": True,
                },
                "execution_contract": {
                    "state_schema_version": "evaluation-result-state/v1",
                    "resource_type": "condition",
                },
            },
        )
        for address in addresses
    ]
    previous = RuntimeSnapshot()
    first = _call_backend_apply(
        evaluator.start, EvaluationPlan(operations=operations), previous, address="runtime.evaluator", snapshot=previous
    )
    assert first.success, first.diagnostics
    second_plan = EvaluationPlan(
        operations=[
            replace(operations[0], action=ChangeAction.UNCHANGED),
            replace(operations[1], action=ChangeAction.UPDATE),
        ]
    )
    second = _call_backend_apply(
        evaluator.start, second_plan, first.snapshot, address="runtime.evaluator", snapshot=first.snapshot
    )
    assert second.success, second.diagnostics
    assert second.changed_addresses == [addresses[1]]
    assert second.snapshot.evaluation_results[addresses[0]] == first.snapshot.evaluation_results[addresses[0]]
    assert second.snapshot.evaluation_history[addresses[0]] == first.snapshot.evaluation_history[addresses[0]]


@pytest.mark.parametrize("stub", [False, True])
def test_reference_orchestrator_partial_refresh_preserves_unchanged_results(stub):
    from raes_backend_stubs.stubs import StubOrchestrator
    from raes_reference_backend.orchestrator import ReferenceOrchestrator

    orchestrator = StubOrchestrator() if stub else ReferenceOrchestrator()
    addresses = ("orchestration.workflow.first", "orchestration.workflow.second")
    operations = [
        OrchestrationOp(
            ChangeAction.CREATE,
            address,
            "workflow",
            {
                "name": address.rsplit(".", 1)[-1],
                "result_contract": {},
                "execution_contract": {},
            },
        )
        for address in addresses
    ]
    previous = RuntimeSnapshot()
    first = _call_backend_apply(
        orchestrator.start,
        OrchestrationPlan(operations=operations),
        previous,
        address="runtime.orchestrator",
        snapshot=previous,
    )
    assert first.success, first.diagnostics
    second_plan = OrchestrationPlan(
        operations=[
            replace(operations[0], action=ChangeAction.UNCHANGED),
            replace(operations[1], action=ChangeAction.UPDATE),
        ]
    )
    second = _call_backend_apply(
        orchestrator.start, second_plan, first.snapshot, address="runtime.orchestrator", snapshot=first.snapshot
    )
    assert second.success, second.diagnostics
    assert second.changed_addresses == [addresses[1]]
    assert second.snapshot.orchestration_results[addresses[0]] == first.snapshot.orchestration_results[addresses[0]]
    assert second.snapshot.orchestration_history[addresses[0]] == first.snapshot.orchestration_history[addresses[0]]


@pytest.mark.parametrize("carrier", ["realization_envelope", "realization_observations"])
def test_nonprovisioning_calls_cannot_forge_realization_carriers(carrier):
    from raes_backend_stubs.stubs import create_stub_target
    from raes_contracts.realization_observation import RealizationObservationDisclosure
    from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope

    previous = RuntimeSnapshot()
    value = (
        create_stub_target().manifest.realization_envelope.identity
        if carrier == "realization_envelope"
        else (
            RealizationObservationDisclosure(
                address="provision.node.web",
                field_path="nodes.web.runtime.packages",
                domain="runtime-realization",
                requirement_kind="runtime-packages",
                verification_scope=RealizationVerificationScope.CONFIGURATION,
                observation_strength=ObservationStrength.GUEST_OBSERVED,
            ),
        )
    )
    candidate = replace(previous, **{carrier: value})
    result = _call_backend_apply(
        lambda *_: ApplyResult(True, candidate),
        OrchestrationPlan(),
        previous,
        snapshot=previous,
        address="runtime.orchestration",
    )
    assert not result.success
    assert result.snapshot == previous
    assert result.diagnostics[0].message == "Backend changed realization state outside provisioning authority."


def _shape_entry(**changes: object) -> SnapshotEntry:
    """Build a resource entry the way an out-of-contract backend would return one.

    ``SnapshotEntry`` admits its own addresses on construction, so a
    structurally invalid entry cannot be built through the constructor. These
    cases write past the frozen dataclass to reproduce exactly what the shape
    gate exists to refuse.
    """

    entry = SnapshotEntry("provision.node.host", RuntimeDomain.PROVISIONING, "node", {"name": "host"})
    for name, value in changes.items():
        object.__setattr__(entry, name, value)
    return entry


def _entry_snapshot(entry: SnapshotEntry) -> RuntimeSnapshot:
    """Carry one entry under its own address without re-admitting the map."""

    snapshot = RuntimeSnapshot()
    snapshot.entries[entry.address] = entry
    return snapshot


@pytest.mark.parametrize("identities", ["non-string", "excessive"])
def test_snapshot_shape_rejects_invalid_or_excessive_carrier_identities(identities):
    snapshot = RuntimeSnapshot()
    snapshot.orchestration_results = (
        {1: {}} if identities == "non-string" else {f"orchestration.script.n{index}": {} for index in range(16385)}
    )
    assert snapshot_shape_violation(snapshot) == "Backend snapshot contains invalid or excessive carrier identities."


def test_snapshot_shape_rejects_a_carrier_value_outside_the_portable_bounds():
    snapshot = RuntimeSnapshot()
    snapshot.orchestration_results = {"orchestration.script.lab": {"handle": object()}}
    assert snapshot_shape_violation(snapshot) == "Backend snapshot contains an invalid or excessive carrier value."


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("untyped-collection", "Backend snapshot contains invalid profile bindings."),
        ("non-portable", "Backend snapshot contains invalid profile bindings."),
        ("untyped-member", "Backend snapshot contains untyped profile bindings."),
        ("unrevalidatable", "Backend snapshot contains invalid profile bindings."),
    ],
)
def test_snapshot_shape_rejects_profile_bindings_that_are_not_typed_records(mutation, message):
    from test_issue_1204_profile_carrier import _profiles

    authority, _ = _profiles()
    binding = authority.bindings[0]
    if mutation == "unrevalidatable":
        binding = binding.model_copy()
        object.__setattr__(binding, "binding_id", "")
    bindings = {
        "untyped-collection": [binding],
        "non-portable": (object(),),
        "untyped-member": ("not-a-binding",),
        "unrevalidatable": (binding,),
    }[mutation]
    assert snapshot_shape_violation(_entry_snapshot(_shape_entry(profile_bindings=bindings))) == message


@pytest.mark.parametrize("payload", ["untyped", "non-portable"])
def test_snapshot_shape_rejects_an_invalid_resource_payload(payload):
    entry = _shape_entry(payload=[] if payload == "untyped" else {"handle": object()})
    assert snapshot_shape_violation(_entry_snapshot(entry)) == "Backend snapshot contains an invalid resource payload."


@pytest.mark.parametrize("status", [b"ready", "", "x" * 129])
def test_snapshot_shape_rejects_an_invalid_resource_status(status):
    entry = _shape_entry(status=status)
    assert snapshot_shape_violation(_entry_snapshot(entry)) == "Backend snapshot contains an invalid resource status."


@pytest.mark.parametrize("dependencies", ["untyped", "excessive", "uncompiled"])
def test_snapshot_shape_rejects_invalid_resource_dependencies(dependencies):
    value = {
        "untyped": ["provision.node.peer"],
        "excessive": tuple(f"provision.node.n{index}" for index in range(16385)),
        "uncompiled": ("not an address",),
    }[dependencies]
    entry = _shape_entry(ordering_dependencies=value)
    message = "Backend snapshot contains invalid resource dependencies."
    assert snapshot_shape_violation(_entry_snapshot(entry)) == message
