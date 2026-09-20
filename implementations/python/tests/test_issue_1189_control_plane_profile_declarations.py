"""Profile selection and capability declarations for CP-10."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_profiles import (
    ControlPlaneCapability,
    ControlPlaneProfile,
    ControlPlaneStoreCapabilities,
    profile_declaration,
)
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_memory import InMemoryControlPlaneStore


def test_canonical_profile_matrix_and_unavailable_p3() -> None:
    expected = {
        ControlPlaneProfile.P0: (
            "embedder",
            "not-applicable",
            {"in-process-safety", "actor-scoped-idempotency", "target-run-isolation", "revision-cas", "atomic-audit"},
            {"durability", "restart-recovery", "multi-owner", "high-availability", "multitenancy"},
            {
                "store.ephemeral",
                "store.atomic-claims",
                "store.atomic-terminal",
                "store.revision-cas",
                "store.audit",
                "store.scope-bound",
                "core.actor-context",
                "core.mutation-authority",
            },
        ),
        ControlPlaneProfile.P1: (
            "embedder",
            "optional-indeterminate",
            {
                "in-process-safety",
                "actor-scoped-idempotency",
                "target-run-isolation",
                "revision-cas",
                "atomic-audit",
                "durable-state",
                "retained-idempotency",
                "lease-admission",
                "startup-reconciliation",
            },
            {"multi-owner", "high-availability", "exactly-once-effects", "multitenancy"},
            {
                "store.durable",
                "store.atomic-claims",
                "store.atomic-terminal",
                "store.revision-cas",
                "store.audit",
                "store.scope-bound",
                "store.owner-lease",
                "core.actor-context",
                "core.mutation-authority",
                "core.startup-reconciliation",
            },
        ),
        ControlPlaneProfile.P2: (
            "authenticated-http",
            "optional-indeterminate",
            {
                "in-process-safety",
                "actor-scoped-idempotency",
                "target-run-isolation",
                "revision-cas",
                "atomic-audit",
                "durable-state",
                "retained-idempotency",
                "lease-admission",
                "startup-reconciliation",
                "authenticated-transport",
                "actor-bound-disclosure",
                "owner-serialized-mutation",
                "revision-carrying-reads",
            },
            {"multi-worker", "tls-proxy-deployment", "high-availability", "exactly-once-effects", "multitenancy"},
            {
                "store.durable",
                "store.atomic-claims",
                "store.atomic-terminal",
                "store.revision-cas",
                "store.audit",
                "store.scope-bound",
                "store.owner-lease",
                "core.actor-context",
                "core.mutation-authority",
                "core.startup-reconciliation",
                "http.authenticated-identity",
                "http.single-worker",
                "http.bounded-admission",
                "http.revision-reads",
            },
        ),
        ControlPlaneProfile.P3: ("unavailable", "future-unspecified", set(), {"future-coordination"}, set()),
    }
    for profile, (actor, recovery, guarantees, nonclaims, required) in expected.items():
        declaration = profile_declaration(profile)
        assert declaration.profile is profile
        assert declaration.actor_boundary.value == actor
        assert declaration.recovery_observation.value == recovery
        assert {claim.identifier for claim in declaration.guarantees} == guarantees
        assert {claim.identifier for claim in declaration.nonclaims} == nonclaims
        assert declaration.one_target_per_store is (profile is not ControlPlaneProfile.P3)
        assert declaration.one_run_per_store is (profile is not ControlPlaneProfile.P3)
        assert {item.value for item in declaration.required_capabilities} == required
        assert declaration.available is (profile is not ControlPlaneProfile.P3)
    assert not profile_declaration(ControlPlaneProfile.P3).guarantees


def test_selected_p0_uses_canonical_declaration_and_binds_one_scope() -> None:
    store = InMemoryControlPlaneStore()
    first = RuntimeControlPlane(create_stub_target(), store=store, profile=ControlPlaneProfile.P0)
    try:
        assert first.profile_declaration is profile_declaration(ControlPlaneProfile.P0)
        assert store.control_plane_capabilities.capabilities >= {
            ControlPlaneCapability.STORE_EPHEMERAL,
            ControlPlaneCapability.STORE_ATOMIC_CLAIMS,
        }
    finally:
        first.close()
    with pytest.raises(ValueError, match="store scope"):
        RuntimeControlPlane(
            replace(create_stub_target(), name="other"),
            store=store,
            profile=ControlPlaneProfile.P0,
        )


def test_unselected_legacy_memory_store_can_be_reused_for_another_scope() -> None:
    store = InMemoryControlPlaneStore()
    first = RuntimeControlPlane(create_stub_target(), store=store)
    first.close()
    second = RuntimeControlPlane(
        replace(create_stub_target(), name="other"),
        store=store,
        run_scope="run:other",
    )
    second.close()


def test_selected_p0_store_has_one_active_owner_and_releases_it_on_close() -> None:
    store = InMemoryControlPlaneStore()
    first = RuntimeControlPlane(create_stub_target(), store=store, profile=ControlPlaneProfile.P0)
    second = None
    try:
        with pytest.raises(RuntimeError, match="already has a runtime owner"):
            second = RuntimeControlPlane(create_stub_target(), store=store, profile=ControlPlaneProfile.P0)
    finally:
        if second is not None:
            second.close()
        first.close()
    third = RuntimeControlPlane(create_stub_target(), store=store, profile=ControlPlaneProfile.P0)
    third.close()


def test_selected_p1_and_p2_share_canonical_declarations(tmp_path) -> None:
    store = LocalControlPlaneStore(tmp_path / "store")
    plane = RuntimeControlPlane(create_stub_target(), store=store, profile=ControlPlaneProfile.P1)
    try:
        assert plane.profile_declaration is profile_declaration(ControlPlaneProfile.P1)
        app = create_control_plane_app(plane, profile=ControlPlaneProfile.P2)
        assert app.state.control_plane_profile is profile_declaration(ControlPlaneProfile.P2)
        assert plane.profile_declaration is profile_declaration(ControlPlaneProfile.P1)
    finally:
        plane.close()


def test_missing_p1_capabilities_fail_before_store_access(tmp_path) -> None:
    class ObservedMemoryStore(InMemoryControlPlaneStore):
        def load_snapshot_state(self):
            raise AssertionError("store was accessed")

    with pytest.raises(TypeError, match="store.durable.*store.owner-lease"):
        RuntimeControlPlane(
            create_stub_target(),
            store=ObservedMemoryStore(),
            profile=ControlPlaneProfile.P1,
        )
    assert not (tmp_path / "store").exists()


@pytest.mark.parametrize(
    "capability",
    sorted(LocalControlPlaneStore.control_plane_capabilities.capabilities, key=lambda item: item.value),
)
def test_every_p1_store_capability_is_required_before_admission(tmp_path, capability) -> None:
    class DeficientStore(LocalControlPlaneStore):
        control_plane_capabilities = ControlPlaneStoreCapabilities(
            LocalControlPlaneStore.control_plane_capabilities.capabilities - {capability}
        )

    path = tmp_path / "unopened"
    with pytest.raises(TypeError, match=capability.value):
        RuntimeControlPlane(create_stub_target(), store=DeficientStore(path), profile=ControlPlaneProfile.P1)
    assert not path.exists()


def test_store_capability_declaration_cannot_be_mutated() -> None:
    capabilities = {ControlPlaneCapability.STORE_EPHEMERAL}
    declaration = ControlPlaneStoreCapabilities(capabilities)
    capabilities.clear()
    assert declaration.capabilities == {ControlPlaneCapability.STORE_EPHEMERAL}
    with pytest.raises(AttributeError):
        declaration.capabilities.add(ControlPlaneCapability.STORE_DURABLE)


def test_p2_rejects_p0_core_and_p3_rejects_before_provider_access() -> None:
    plane = RuntimeControlPlane(create_stub_target(), profile=ControlPlaneProfile.P0)
    try:
        with pytest.raises(ValueError, match="P1"):
            create_control_plane_app(plane, profile=ControlPlaneProfile.P2)
    finally:
        plane.close()
    with pytest.raises(ValueError, match="P3"):
        RuntimeControlPlane(create_stub_target(), profile=ControlPlaneProfile.P3)


def test_explicit_selection_does_not_infer_or_downgrade() -> None:
    with pytest.raises(TypeError):
        RuntimeControlPlane(create_stub_target(), profile="P0")
    plane = RuntimeControlPlane(create_stub_target())
    try:
        assert plane.profile_declaration is None
        app = create_control_plane_app(plane)
        assert app.state.control_plane_profile is None
    finally:
        plane.close()


def test_explain_profile_identifiers_match_canonical_catalog() -> None:
    page = Path(__file__).resolve().parents[3] / "docs/explain/sdl/runtime-architecture.md"
    section = page.read_text().split("## Control-plane operating profiles", 1)[1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        if re.match(r"^\| P[0-9] \|", line):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            rows[cells[0]] = cells
    assert set(rows) == {profile.value for profile in ControlPlaneProfile}
    for profile in ControlPlaneProfile:
        declaration = profile_declaration(profile)
        _, guarantees, nonclaims = rows[profile.value]
        assert set(guarantees.split(", ")) - {"none"} == {claim.identifier for claim in declaration.guarantees}
        assert set(nonclaims.split(", ")) == {claim.identifier for claim in declaration.nonclaims}
