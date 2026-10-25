"""Credential closure composes with admitted observed concern values (#1638)."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest
from raes_contracts.planning import ProvisioningPlan, RuntimeDomain
from raes_contracts.runtime_state import (
    ApplyResult,
    RealizationObservationDisclosure,
    RuntimeSnapshot,
    RuntimeSnapshotEnvelope,
    SnapshotEntry,
)
from raes_contracts.vocabulary import ObservationStrength
from raes_runtime.backend_calls import _call_backend_apply
from raes_runtime.backend_realization_authority import _RealizationApplyContext
from raes_runtime.control_plane_api_models import _snapshot_model
from raes_runtime.control_plane_store import _snapshot_from_payload, _snapshot_payload
from test_issue_673_account_credential_bindings import FIXTURE_SENTINEL, OPERATOR_REFERENCE, _credential_plan
from test_issue_1200_mixed_runtime_constraints import _fixture

_ADDRESS = "provision.node.host"
_CAPABILITIES = {
    "required": [],
    "effective": [],
    "add": ["CAP_NET_ADMIN", "CAP_NET_RAW", "CAP_SYS_NICE"],
    "drop": [],
    "process_overrides": [],
}


def _apply_observed(
    runtime, observed, *, scope=None, corruption=None, observe=True, credentials=True, setup=None, omit_parent=False
):
    _, plan, manifest = setup or _fixture(runtime, scope=scope)
    if omit_parent:
        operations = deepcopy(plan.operations)
        operations[0].payload["spec"]["node"]["runtime"].pop("network")
        plan = replace(plan, operations=operations)
    account = _credential_plan().operations[0]
    account = replace(account, payload={**account.payload, "node_name": "host", "target_address": _ADDRESS})
    plan = replace(plan, operations=[*plan.operations, *([account] if credentials else [])])
    baseline = RuntimeSnapshot(
        entries={
            "provision.node.retained": SnapshotEntry(
                "provision.node.retained",
                RuntimeDomain.PROVISIONING,
                "node",
                {"name": "retained", "node_name": "retained"},
            )
        }
    )

    def apply(submitted: ProvisioningPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        entries = deepcopy(dict(snapshot.entries))
        for op in submitted.operations:
            entries[op.address] = SnapshotEntry(
                op.address,
                RuntimeDomain.PROVISIONING,
                op.resource_type,
                deepcopy(op.payload),
                status="applied",
                ordering_dependencies=op.ordering_dependencies,
                refresh_dependencies=op.refresh_dependencies,
            )
        payload = entries[_ADDRESS].payload
        payload["spec"]["node"]["runtime"].update(deepcopy(observed))
        if corruption == "sibling-fixture":
            payload["copied"] = FIXTURE_SENTINEL
        elif corruption == "nested-reference":
            payload["spec"]["node"]["runtime"]["copied"] = {"reference": OPERATOR_REFERENCE}
        elif corruption == "unknown-concern-field":
            payload["spec"]["node"]["runtime"]["linux_capabilities"]["copied"] = FIXTURE_SENTINEL
        elif corruption == "wrong-address":
            entries[account.address].payload["spec"]["node"] = deepcopy(payload["spec"]["node"])
        observations = tuple(
            RealizationObservationDisclosure(
                address=a.address,
                field_path=a.field_path,
                domain=a.domain,
                requirement_kind=a.requirement_kind,
                verification_scope=a.verification_scope,
                observation_strength=a.required_observation_strength or ObservationStrength.GUEST_OBSERVED,
            )
            for a in submitted.realization_authority
            if a.verification_scope is not None and a.mode.value != "closed"
        )
        return ApplyResult(
            True,
            snapshot.with_entries(
                entries,
                realization_envelope=submitted.realization_envelope,
                realization_observations=observations if observe else (),
            ),
            changed_addresses=[op.address for op in submitted.operations],
        )

    result = _call_backend_apply(
        apply,
        plan,
        baseline,
        address="runtime.apply.provisioning",
        snapshot=baseline,
        realization=_RealizationApplyContext(plan=plan, manifest=manifest),
    )
    return result, baseline


def test_open_capabilities_with_credentials_preserve_observed_values_and_safe_state():
    result, baseline = _apply_observed(
        {},
        {"linux_capabilities": _CAPABILITIES},
        scope="/nodes/host/runtime/linux_capabilities",
    )

    assert result.success, result.diagnostics
    assert result.snapshot.entries[_ADDRESS].payload["spec"]["node"]["runtime"]["linux_capabilities"] == _CAPABILITIES
    assert result.snapshot.entries["provision.node.retained"] == baseline.entries["provision.node.retained"]
    assert any(item.requirement_kind == "linux-capabilities" for item in result.snapshot.realization_provenance)
    assert result.snapshot.realization_observations == ()
    serialized = _snapshot_payload(result.snapshot)
    assert _snapshot_from_payload(serialized) == result.snapshot
    published = _snapshot_model(RuntimeSnapshotEnvelope(snapshot=result.snapshot)).model_dump(mode="json")
    rendered = json.dumps({"stored": serialized, "published": published})
    assert FIXTURE_SENTINEL not in rendered
    assert OPERATOR_REFERENCE not in rendered


@pytest.mark.parametrize(
    "corruption", ["sibling-fixture", "nested-reference", "unknown-concern-field", "wrong-address"]
)
def test_credential_observations_refuse_unauthorized_material(corruption):
    result, baseline = _apply_observed(
        {},
        {"linux_capabilities": _CAPABILITIES},
        scope="/nodes/host/runtime/linux_capabilities",
        corruption=corruption,
    )
    assert not result.success
    assert result.snapshot == baseline
    assert result.changed_addresses == []
    assert result.details == {}
    assert {item.code for item in result.diagnostics} == {"runtime.backend-contract-invalid"}
    assert FIXTURE_SENTINEL not in repr(result)
    assert OPERATOR_REFERENCE not in repr(result)


@pytest.mark.parametrize("credentials", [True, False])
def test_exact_capabilities_compare_semantically_and_persist_native_observation(credentials):
    declared = {**_CAPABILITIES, "add": list(reversed(_CAPABILITIES["add"]))}
    result, _ = _apply_observed(
        {"linux_capabilities": declared}, {"linux_capabilities": _CAPABILITIES}, credentials=credentials
    )
    assert result.success, result.diagnostics
    assert result.snapshot.entries[_ADDRESS].payload["spec"]["node"]["runtime"]["linux_capabilities"] == _CAPABILITIES


@pytest.mark.parametrize("version, accepted", [("7.95", True), ("7.94", False)])
def test_open_typed_concern_preserves_exact_children(version, accepted):
    package = {"manager": "apt", "name": "nmap", "version": "7.95"}
    observed = [{**package, "version": version}, {"manager": "apt", "name": "curl", "version": "8.0"}]
    result, baseline = _apply_observed(
        {"packages": [package]}, {"packages": observed}, scope="/nodes/host/runtime/packages"
    )
    assert result.success is accepted, result.diagnostics
    if accepted:
        packages = result.snapshot.entries[_ADDRESS].payload["spec"]["node"]["runtime"]["packages"]
        assert {item["name"] for item in packages} == {"nmap", "curl"}
    else:
        assert result.snapshot == baseline


def _constrained_fixture():
    from raes import parse_sdl
    from raes.instantiate import instantiate_scenario
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.planner import plan
    from test_issue_1066_runtime_resource_limits import _scenario

    source = _scenario(
        """
        - resource: open_file_descriptors
          soft: ${soft_limit}
          hard: 65536
          subject: {name: search}
          scope: subtree
        """,
        variables="""
        variables:
          soft_limit:
            type: integer
            default: 32768
            allowed_values: [16384, 32768, 65536]
        """,
    ).replace("worker:", "host:")
    model = compile_runtime_model(instantiate_scenario(parse_sdl(source)))
    _, _, manifest = _fixture({})
    execution = plan(model, manifest)
    assert execution.is_valid, execution.diagnostics
    return model, execution.provisioning, manifest


@pytest.mark.parametrize("soft, accepted", [(65536, True), (8192, False)])
def test_constrained_observed_choice_retains_its_bound(soft, accepted):
    from test_issue_1066_runtime_resource_limits import _exact_limit

    setup = _constrained_fixture()
    declared = deepcopy(setup[1].operations[0].payload["spec"]["node"]["runtime"])
    observed = deepcopy(declared)
    observed["operational_policy"]["resource_limits"]["process_limits"] = [
        {**_exact_limit(soft=soft), "subject": {"name": "search"}}
    ]
    result, baseline = _apply_observed(declared, observed, setup=setup)
    assert result.success is accepted, result.diagnostics
    if accepted:
        runtime = result.snapshot.entries[_ADDRESS].payload["spec"]["node"]["runtime"]
        assert runtime["operational_policy"]["resource_limits"]["process_limits"][0]["soft"] == soft
    else:
        assert result.snapshot == baseline


@pytest.mark.parametrize("mode", ["closed", "exact", "missing-observation"])
def test_credential_plan_does_not_weaken_realization_admission(mode):
    declared = {} if mode == "closed" else {"linux_capabilities": {"required": ["CAP_NET_RAW"]}}
    if mode == "missing-observation":
        declared = {"linux_capabilities": _CAPABILITIES}
    result, baseline = _apply_observed(
        declared,
        {"linux_capabilities": _CAPABILITIES},
        observe=mode != "missing-observation",
    )
    assert not result.success
    assert result.snapshot == baseline
    assert result.changed_addresses == []


def test_observed_concerns_and_artifact_evidence_coexist_with_credentials():
    from test_issue_1603_credential_artifact_evidence import _apply_artifact_result

    result, evidence = _apply_artifact_result(observed_capabilities=_CAPABILITIES)
    assert result.success, result.diagnostics
    payload = result.snapshot.entries[_ADDRESS].payload
    assert payload["artifact_satisfaction"] == evidence
    assert payload["spec"]["node"]["runtime"]["linux_capabilities"] == _CAPABILITIES
    assert any(item.artifact_satisfaction is not None for item in result.snapshot.realization_provenance)
    assert any(item.requirement_kind == "linux-capabilities" for item in result.snapshot.realization_provenance)


@pytest.mark.parametrize("omit_parent", [False, True])
@pytest.mark.parametrize("extra_sibling", ["absent", "fixture", "null"])
def test_nested_open_observation_restores_only_authorized_ancestor_scaffolding(omit_parent, extra_sibling):
    network = {"hostname": "observed-host", "domainname": "example.test"}
    if extra_sibling != "absent":
        network["copied"] = FIXTURE_SENTINEL if extra_sibling == "fixture" else None
    result, baseline = _apply_observed(
        {},
        {"network": network},
        scope="/nodes/host/runtime/network",
        omit_parent=omit_parent,
    )
    assert result.success is (extra_sibling == "absent"), result.diagnostics
    if extra_sibling != "absent":
        assert result.snapshot == baseline
        assert result.changed_addresses == []
        assert FIXTURE_SENTINEL not in repr(result)
    else:
        assert result.snapshot.entries[_ADDRESS].payload["spec"]["node"]["runtime"]["network"] == network
        assert _snapshot_from_payload(_snapshot_payload(result.snapshot)) == result.snapshot
