"""Test-only ADR-104 compositions and an independently surviving effect witness."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from pathlib import Path

from raes_backend_protocols.capabilities import RecoveryObservationCapabilities
from raes_backend_protocols.recovery_observation import (
    RecoveryEffectClassification,
    RecoveryObservationRequest,
    RecoveryObservationResult,
)
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.plan_projection import provisioning_plan_model
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import OperationKind, OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_profiles import ControlPlaneProfile
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole, ControlPlaneSecurityConfig
from raes_runtime.control_plane_store import InMemoryControlPlaneStore
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_snapshots import _snapshot_from_payload, _snapshot_payload
from starlette.testclient import TestClient

PROFILES = ("P0", "P1", "P2")
DURABLE_PROFILES = ("P1", "P2")
RUN_SCOPE = "run:conformance"
TARGET_SCOPE = "target:stub"
KEY = "conformance-key"


def identities() -> dict[str, ControlPlaneIdentity]:
    alice = ControlPlaneIdentity(identity="alice", roles=frozenset({ControlPlaneRole.OPERATOR}), target_name="stub")
    return {
        "alice": alice,
        "bob": replace(alice, identity="bob"),
        "changed-scope": replace(alice, roles=frozenset({ControlPlaneRole.OPERATOR, ControlPlaneRole.AUDITOR})),
        "other-target": replace(alice, target_name="other"),
    }


def witness_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def record_effect(path: Path, event: str, operation_id: str, *, snapshot=None) -> None:
    # This is a synthetic backend's own state, outside the control-plane store.
    with path.open("a", encoding="utf-8") as stream:
        payload = {"event": event, "operation_id": operation_id}
        if snapshot is not None:
            payload["snapshot"] = _snapshot_payload(snapshot)
        stream.write(json.dumps(payload) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


class WitnessProvisioner:
    def __init__(self, delegate, witness: Path, boundary=None) -> None:
        self.delegate = delegate
        self.witness = witness
        self.boundary = boundary or (lambda _name: None)

    def validate(self, plan):
        return self.delegate.validate(plan)

    def apply(self, plan, snapshot):
        self.boundary("before-invoke")
        assert plan.operation_id
        record_effect(self.witness, "invoke", plan.operation_id)
        self.boundary("after-dispatch")
        result = self.delegate.apply(plan, snapshot)
        assert result.success
        record_effect(self.witness, "applied", plan.operation_id, snapshot=result.snapshot)
        self.boundary("after-invoke")
        return result


class WitnessObserver:
    def __init__(self, witness: Path) -> None:
        self.witness = witness

    def observe_effect(self, request: RecoveryObservationRequest) -> RecoveryObservationResult:
        applied = next(
            (
                item
                for item in witness_events(self.witness)
                if item["event"] == "applied" and item["operation_id"] == request.operation_id
            ),
            None,
        )
        return RecoveryObservationResult(
            classification=(
                RecoveryEffectClassification.EFFECT_APPLIED if applied else RecoveryEffectClassification.EFFECT_ABSENT
            ),
            operation_id=request.operation_id,
            request_commitment=request.request_commitment,
            snapshot=_snapshot_from_payload(applied["snapshot"]) if applied else None,
        )


def witness_target(witness: Path, *, observe: bool = False, boundary=None):
    # The observed empty-plan effect requires no new realization authority.
    # Recovery intentionally refuses to invent a provisioning plan to authorize
    # new realization/resource state from an observer's assertion alone.
    target = create_stub_target(with_realization_envelope=False)
    target = replace(target, provisioner=WitnessProvisioner(target.provisioner, witness, boundary))
    if observe:
        capability = RecoveryObservationCapabilities(
            name="conformance-witness", supported_operation_kinds=frozenset({OperationKind.PROVISIONING})
        )
        target = replace(
            target,
            manifest=replace(
                target.manifest, capabilities=replace(target.manifest.capabilities, recovery_observation=capability)
            ),
            recovery_observer=WitnessObserver(witness),
        )
    return target


class ProfileHarness:
    def __init__(self, profile: str, plane: RuntimeControlPlane, store, client: TestClient | None) -> None:
        self.profile, self.plane, self.store, self.client = profile, plane, store, client

    @staticmethod
    def headers(actor: str = "alice") -> dict[str, str]:
        return {"authorization": f"Bearer synthetic-{actor}", "idempotency-key": KEY}

    def submit(self, *, key: str = KEY, actor: str = "alice") -> str:
        if self.client is not None:
            response = self.client.post(
                "/operations/provisioning",
                json=provisioning_plan_model(ProvisioningPlan()).model_dump(mode="json"),
                headers={**self.headers(actor), "idempotency-key": key},
            )
            assert response.status_code == 200, response.text
            assert response.json()["accepted"]
            return response.json()["operation_id"]
        receipt = self.plane.submit_provisioning(ProvisioningPlan(), idempotency_key=key, identity=identities()[actor])
        assert receipt.accepted, receipt.diagnostics
        return receipt.operation_id

    def status(self, operation_id: str, *, actor: str = "alice") -> OperationState | None:
        if self.client is not None:
            response = self.client.get(f"/operations/{operation_id}", headers=self.headers(actor))
            if response.status_code in (403, 404):
                return None
            assert response.status_code == 200, response.text
            return OperationState(response.json()["state"])
        status = self.plane.get_operation(operation_id, identity=identities()[actor])
        return None if status is None else status.state

    def snapshot_cut(self) -> tuple[dict[str, object], int]:
        if self.client is not None:
            response = self.client.get("/snapshot", headers=self.headers())
            assert response.status_code == 200
            return response.json()["metadata"], int(response.headers["X-RAES-Snapshot-Revision"])
        return self.plane._project_snapshot_read(lambda: dict(self.plane.snapshot.metadata))


@contextmanager
def profile_harness(
    profile: str,
    path: Path,
    *,
    observe: bool = False,
    boundary=None,
    store=None,
) -> Iterator[ProfileHarness]:
    if profile not in PROFILES:
        raise ValueError("unsupported conformance composition")
    selected_store = (
        store
        if store is not None
        else (InMemoryControlPlaneStore() if profile == "P0" else LocalControlPlaneStore(path / "store"))
    )
    target = witness_target(path / "effects.jsonl", observe=observe, boundary=boundary)
    with ExitStack() as stack:
        core_profile = ControlPlaneProfile.P0 if profile == "P0" else ControlPlaneProfile.P1
        plane = RuntimeControlPlane(target, store=selected_store, run_scope=RUN_SCOPE, profile=core_profile)
        stack.callback(plane.close)
        client = None
        if profile == "P2":
            security = ControlPlaneSecurityConfig(
                bearer_tokens={f"synthetic-{key}": value for key, value in identities().items()}
            )
            client = stack.enter_context(
                TestClient(create_control_plane_app(plane, security=security, profile=ControlPlaneProfile.P2))
            )
        yield ProfileHarness(profile, plane, selected_store, client)


@contextmanager
def inspect_store(path: Path):
    store = LocalControlPlaneStore(path / "store")
    lease = store.admit_runtime(target_scope=TARGET_SCOPE, run_scope=RUN_SCOPE)
    try:
        yield store
    finally:
        store.close()
        lease.close()


def terminal_audits(store, operation_id: str):
    return [
        event
        for event in store.read_audit()
        if event.operation_id == operation_id and event.action.endswith("_terminal")
    ]
