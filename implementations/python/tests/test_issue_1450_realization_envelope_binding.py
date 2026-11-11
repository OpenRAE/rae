"""A provisioning result cannot bind the snapshot to an envelope the plan never selected (issue #1450).

When the submitted provisioning plan names a realization envelope, the returned
snapshot's envelope must be that identity or the accepted predecessor's. A
network-only plan has no compute-substrate requirement to catch a forged
identity later, so the binding is checked directly. Teardown is bound as well:
the destroy delete plan names the predecessor's envelope.
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock

import pytest
from raes import parse_sdl
from raes_backend_stubs.stubs import StubProvisioner, create_stub_target
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.realization_envelope import RealizationEnvelopeIdentityModel
from raes_contracts.runtime_state import ApplyResult, OperationState, RuntimeSnapshot
from raes_processor.planner import realization_authority as authority
from raes_runtime.backend_calls import _call_backend_apply
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.manager import RuntimeManager

_FORGED = "sha256:" + "f" * 64
_LAB = """\
  lab: {type: switch}
infrastructure:
  lab: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
"""
_NETWORK_ONLY = "name: envelope-binding\nnodes:\n" + _LAB
_WITH_WEB = (
    "name: envelope-binding\nnodes:\n  web: {type: compute, resources: {ram: 1 gib, cpu: 1}}\n"
    + _LAB
    + "  web: {count: 1, links: [lab]}\n"
)
_ENVELOPE_ADDRESS = "/runtime.snapshot.realization-envelope"
_MISMATCH_CODE = "realization.authority-envelope-mismatch"


def _forged(envelope: RealizationEnvelopeIdentityModel) -> RealizationEnvelopeIdentityModel:
    return envelope.model_copy(update={"configuration_digest": _FORGED})


class _ForgesEnvelope(StubProvisioner):
    """Keep the existing stub behavior and change only its returned envelope."""

    def apply(self, plan, snapshot):
        result = super().apply(plan, snapshot)
        if not result.success:
            return result
        forged = _forged(plan.realization_envelope)
        return replace(
            result, snapshot=result.snapshot.with_entries(dict(result.snapshot.entries), realization_envelope=forged)
        )


def _target(*, forged: bool):
    target = create_stub_target()
    return replace(target, provisioner=_ForgesEnvelope(target.manifest.realization_envelope)) if forged else target


def _honest_snapshot():
    """Return the snapshot an honest network-only apply commits."""

    with RuntimeManager(_target(forged=False)) as manager:
        assert manager.apply(manager.plan(parse_sdl(_NETWORK_ONLY))).success
        assert manager.snapshot.realization_envelope is not None
        return manager.snapshot


def _refusal_addresses(diagnostics) -> set[str]:
    return {diagnostic.address for diagnostic in diagnostics if diagnostic.code == "runtime.backend-contract-invalid"}


@pytest.mark.parametrize("scenario", [_NETWORK_ONLY, _WITH_WEB], ids=["network-only", "compute-node"])
def test_manager_refuses_an_unbound_realization_envelope(scenario):
    with RuntimeManager(_target(forged=True)) as manager:
        result = manager.apply(manager.plan(parse_sdl(scenario)))

        assert result.success is False
        assert _ENVELOPE_ADDRESS in _refusal_addresses(result.diagnostics)
        assert manager.snapshot.realization_envelope is None
        assert manager.snapshot.entries == {}


@pytest.mark.parametrize("applied", [False, True], ids=["empty-predecessor", "applied-predecessor"])
def test_control_plane_keeps_the_predecessor_envelope(applied):
    predecessor = _honest_snapshot() if applied else RuntimeSnapshot()
    target = _target(forged=True)
    with RuntimeControlPlane(target, initial_snapshot=predecessor) as control:
        execution = control.plan(parse_sdl(_NETWORK_ONLY))
        control.register_planner_produced_plan(execution)
        status = control.get_operation(control.submit_provisioning(execution.provisioning).operation_id)
        snapshot = control.snapshot

    assert status.state is OperationState.FAILED
    assert _ENVELOPE_ADDRESS in _refusal_addresses(status.diagnostics)
    assert snapshot.realization_envelope == predecessor.realization_envelope
    assert snapshot.entries == predecessor.entries


def test_destroy_refuses_a_forged_teardown_result():
    predecessor = _honest_snapshot()
    with RuntimeManager(_target(forged=True), initial_snapshot=predecessor) as manager:
        result = manager.destroy()

        assert result.success is False
        assert _ENVELOPE_ADDRESS in _refusal_addresses(result.diagnostics)
        assert manager.snapshot == predecessor


@pytest.mark.parametrize("foreign_predecessor", [False, True], ids=["matching-envelope", "foreign-envelope"])
def test_destroy_checks_the_envelope_before_effects_and_on_retry(foreign_predecessor):
    target = _target(forged=False)
    live_addresses: set[str] = set()
    apply = target.provisioner.apply

    def apply_with_effects(plan, snapshot):
        result = apply(plan, snapshot)
        if result.success:
            live_addresses.clear()
            live_addresses.update(result.snapshot.entries)
        return result

    target.provisioner.apply = Mock(wraps=apply_with_effects)
    with RuntimeManager(target) as manager:
        applied = manager.apply(manager.plan(parse_sdl(_NETWORK_ONLY)))
        assert applied.success, applied.diagnostics
        predecessor = manager.snapshot
    assert live_addresses == set(predecessor.entries)
    assert live_addresses
    if foreign_predecessor:
        predecessor = replace(predecessor, realization_envelope=_forged(predecessor.realization_envelope))
    target.provisioner.apply.reset_mock()

    with RuntimeManager(target, initial_snapshot=predecessor) as manager:
        for _ in range(2):
            result = manager.destroy()

            assert live_addresses == set(manager.snapshot.entries), "teardown changed resources before refusal"
            assert result.success is not foreign_predecessor, result.diagnostics
            if foreign_predecessor:
                assert _MISMATCH_CODE in {diagnostic.code for diagnostic in result.diagnostics}
                assert manager.snapshot == predecessor
                target.provisioner.apply.assert_not_called()
            else:
                assert live_addresses == set()


def test_destroy_regression_detects_a_disabled_envelope_check(monkeypatch):
    """The effects assertion must kill a mutation that skips manifest admission."""

    monkeypatch.setattr(authority, "_manifest_authority_diagnostic", lambda *_: None)
    with pytest.raises(AssertionError, match="teardown changed resources before refusal"):
        test_destroy_checks_the_envelope_before_effects_and_on_retry(True)


def test_honest_apply_binds_the_selected_envelope():
    with RuntimeManager(_target(forged=False)) as manager:
        execution = manager.plan(parse_sdl(_NETWORK_ONLY))

        assert manager.apply(execution).success
        assert manager.snapshot.realization_envelope == execution.provisioning.realization_envelope


@pytest.mark.parametrize("selected", [False, True], ids=["no-envelope", "selected-envelope"])
@pytest.mark.parametrize("returned", ["selected", "predecessor", "other"])
def test_result_envelope_binding_keeps_existing_compatibility(selected, returned):
    identity = create_stub_target().manifest.realization_envelope.identity
    predecessor = RuntimeSnapshot(realization_envelope=_forged(identity))
    other = identity.model_copy(update={"configuration_digest": "sha256:" + "e" * 64})
    envelopes = {"selected": identity, "predecessor": predecessor.realization_envelope, "other": other}
    plan = ProvisioningPlan(realization_envelope=identity if selected else None)

    def apply(plan, snapshot):
        return ApplyResult(True, replace(snapshot, realization_envelope=envelopes[returned]))

    result = _call_backend_apply(apply, plan, predecessor, address="runtime.test", snapshot=predecessor)

    assert result.success is (not selected or returned != "other"), result.diagnostics
    if not result.success:
        assert result.snapshot == predecessor
