"""Credential closure must preserve admitted artifact evidence (#1603)."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ProvisioningPlan, RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_runtime.backend_calls import _call_backend_apply
from raes_runtime.backend_realization_authority import _RealizationApplyContext
from raes_runtime.control_plane_store import _snapshot_from_payload, _snapshot_payload
from test_artifact_requirement_satisfaction import (
    _DIGEST_A,
    _DIGEST_B,
    _availability,
    _compiled,
    _exact_requirement,
    _identity,
    _manifest,
    _mechanism,
)
from test_issue_673_account_credential_bindings import FIXTURE_SENTINEL, OPERATOR_REFERENCE, _credential_plan
from test_issue_1200_mixed_runtime_constraints import _fixture

_ADDRESS = "provision.node.host"


def _apply_artifact_result(
    *,
    corruption: str | None = None,
    credentials: bool = True,
    admitted: bool = True,
) -> tuple[ApplyResult, dict[str, object]]:
    requirement = _exact_requirement()
    _, base_plan, base_manifest = _fixture({})
    artifact_manifest = _manifest(requirement)
    manifest = replace(
        base_manifest,
        realization_support=tuple(
            replace(declaration, artifact_mechanisms=artifact_manifest.realization_support[0].artifact_mechanisms)
            for declaration in base_manifest.realization_support
        ),
    )
    trust_ref = requirement.trust_policy_refs[0]
    from raes_contracts.artifact_requirements import ArtifactSatisfactionDisclosureModel

    disclosure = ArtifactSatisfactionDisclosureModel(
        requirement_id=requirement.requirement_id,
        artifact=_identity(),
        mechanism=_mechanism(),
        acquisition="pull",
        timing="realization",
        backend=manifest.identity,
        integrity_refs=[_DIGEST_A],
        admission_refs=[trust_ref],
        provenance_refs=["provenance:verified"],
    ).model_dump(mode="json")
    account = _credential_plan().operations[0]
    account = replace(account, payload={**account.payload, "node_name": "host", "target_address": _ADDRESS})
    plan = replace(
        base_plan,
        operations=[
            *(replace(op, payload={**op.payload, "enabled": True}) for op in base_plan.operations),
            *([account] if credentials else []),
        ],
    )
    context = _RealizationApplyContext(
        plan=plan,
        requirements=(_compiled(requirement, address=_ADDRESS),) if admitted else (),
        manifest=manifest,
        artifact_availability=_availability(
            address=_ADDRESS,
            available_artifact_digests=[_DIGEST_A],
            verified_integrity_refs=[_DIGEST_A],
            verified_admission_refs=[trust_ref],
            verified_provenance_refs=["provenance:verified"],
        ),
    )

    def apply(submitted: ProvisioningPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        entries = {
            op.address: SnapshotEntry(
                address=op.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=op.resource_type,
                payload=deepcopy(op.payload),
                status="applied",
                ordering_dependencies=op.ordering_dependencies,
                refresh_dependencies=op.refresh_dependencies,
            )
            for op in submitted.operations
        }
        payload = entries[_ADDRESS].payload
        evidence = deepcopy(disclosure)
        payload["artifact_satisfaction"] = evidence
        details = {}
        if corruption == "fixture":
            payload["copied"] = FIXTURE_SENTINEL
        elif corruption == "reference":
            payload["copied"] = {"nested": OPERATOR_REFERENCE}
        elif corruption == "evidence-extra":
            evidence["copied"] = FIXTURE_SENTINEL
        elif corruption == "requirement":
            evidence["requirement_id"] = "different-requirement"
        elif corruption == "digest":
            evidence["artifact"]["digest"] = _DIGEST_B
        elif corruption == "backend":
            evidence["backend"]["name"] = "different-backend"
        elif corruption == "route":
            evidence["acquisition"] = "copy"
        elif corruption == "trust":
            evidence["provenance_refs"] = ["provenance:unverified"]
        elif corruption == "address":
            account = entries["provision.account.admin"].payload
            account["artifact_satisfaction"] = payload.pop("artifact_satisfaction")
        elif corruption == "extra-address":
            entries["provision.account.admin"].payload["artifact_satisfaction"] = deepcopy(evidence)
        elif corruption == "typed-value":
            payload["enabled"] = 1
        elif corruption == "details":
            details["copied"] = FIXTURE_SENTINEL
        return ApplyResult(
            True,
            snapshot.with_entries(entries, realization_envelope=submitted.realization_envelope),
            diagnostics=[Diagnostic("backend.applied", "runtime", _ADDRESS, f"applied {FIXTURE_SENTINEL}")],
            changed_addresses=list(entries),
            details=details,
        )

    result = _call_backend_apply(
        apply,
        plan,
        RuntimeSnapshot(),
        address="runtime.apply.provisioning",
        snapshot=RuntimeSnapshot(),
        realization=context,
    )
    return result, disclosure


def test_credential_plan_accepts_exact_artifact_evidence_and_persists_safe_projection() -> None:
    result, disclosure = _apply_artifact_result()

    assert result.success, result.diagnostics
    assert result.snapshot.entries[_ADDRESS].payload["artifact_satisfaction"] == disclosure
    artifact_provenance = [
        item.artifact_satisfaction
        for item in result.snapshot.realization_provenance
        if item.artifact_satisfaction is not None
    ]
    assert len(artifact_provenance) == 1
    assert artifact_provenance[0].model_dump(mode="json") == disclosure
    serialized = _snapshot_payload(result.snapshot)
    rendered = json.dumps(serialized)
    assert FIXTURE_SENTINEL not in rendered
    assert OPERATOR_REFERENCE not in rendered
    assert FIXTURE_SENTINEL not in result.diagnostics[0].message
    assert _snapshot_from_payload(serialized) == result.snapshot


@pytest.mark.parametrize(
    "corruption",
    [
        "fixture",
        "reference",
        "evidence-extra",
        "requirement",
        "digest",
        "backend",
        "route",
        "trust",
        "address",
        "extra-address",
        "typed-value",
        "details",
    ],
)
def test_credential_plan_refuses_unadmitted_payload_and_evidence(corruption: str) -> None:
    result, _ = _apply_artifact_result(corruption=corruption)

    assert not result.success
    assert result.snapshot == RuntimeSnapshot()
    assert result.changed_addresses == []
    assert result.details == {}
    assert {diagnostic.code for diagnostic in result.diagnostics} == {"runtime.backend-contract-invalid"}
    assert FIXTURE_SENTINEL not in json.dumps(_snapshot_payload(result.snapshot))
    assert FIXTURE_SENTINEL not in str(result.diagnostics)
    assert OPERATOR_REFERENCE not in str(result.diagnostics)


def test_credential_plan_refuses_evidence_without_admitted_requirement() -> None:
    result, _ = _apply_artifact_result(admitted=False)
    assert not result.success
    assert result.snapshot == RuntimeSnapshot()


def test_noncredential_plan_still_accepts_artifact_evidence() -> None:
    result, disclosure = _apply_artifact_result(credentials=False)
    assert result.success, result.diagnostics
    assert result.snapshot.entries[_ADDRESS].payload["artifact_satisfaction"] == disclosure
