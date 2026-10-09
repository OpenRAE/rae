"""A provisioning result cannot bind the snapshot to an envelope the plan never selected (issue #1450).

When the submitted provisioning plan names a realization envelope, the returned
snapshot's envelope must be that identity or the accepted predecessor's. A
network-only plan has no compute-substrate requirement to catch a forged
identity later, so the binding is checked directly. Teardown is bound as well:
the destroy delete plan names the predecessor's envelope.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot
from raes_reference_backend import create_reference_backend_target
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
_ENVELOPE_ADDRESS = "runtime.snapshot.realization-envelope"
# Control-plane operation statuses carry the portable JSON-Pointer form of the same address.
_PORTABLE_ENVELOPE_ADDRESS = "/" + _ENVELOPE_ADDRESS


def _forged(envelope):
    return envelope.model_copy(update={"configuration_digest": _FORGED})


class _ForgesEnvelope:
    """Delegates to the reference provisioner; successful results carry a forged configuration digest."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def apply(self, plan, snapshot):
        result = self._inner.apply(plan, snapshot)
        if not result.success:
            return result
        forged = _forged(plan.realization_envelope)
        return replace(
            result, snapshot=result.snapshot.with_entries(dict(result.snapshot.entries), realization_envelope=forged)
        )


def _target(*, forged: bool):
    target = create_reference_backend_target()
    return replace(target, provisioner=_ForgesEnvelope(target.provisioner)) if forged else target


def _honest_snapshot():
    """Return the snapshot an honest network-only apply commits."""

    manager = RuntimeManager(_target(forged=False))
    assert manager.apply(manager.plan(parse_sdl(_NETWORK_ONLY))).success
    assert manager.snapshot.realization_envelope is not None
    return manager.snapshot


def _refusal_addresses(diagnostics) -> set[str]:
    return {diagnostic.address for diagnostic in diagnostics if diagnostic.code == "runtime.backend-contract-invalid"}


@pytest.mark.parametrize("scenario", [_NETWORK_ONLY, _WITH_WEB], ids=["network-only", "compute-node"])
def test_manager_refuses_an_unbound_realization_envelope(scenario):
    manager = RuntimeManager(_target(forged=True))

    result = manager.apply(manager.plan(parse_sdl(scenario)))

    assert result.success is False
    assert _ENVELOPE_ADDRESS in _refusal_addresses(result.diagnostics)
    assert manager.snapshot.realization_envelope is None
    assert manager.snapshot.entries == {}


@pytest.mark.parametrize("applied", [False, True], ids=["empty-predecessor", "applied-predecessor"])
def test_control_plane_keeps_the_predecessor_envelope(applied):
    predecessor = _honest_snapshot() if applied else RuntimeSnapshot()
    target = _target(forged=True)
    control = RuntimeControlPlane(target, initial_snapshot=predecessor)
    try:
        execution = RuntimeManager(target).plan(parse_sdl(_NETWORK_ONLY), snapshot=control.snapshot)
        control.register_planner_produced_plan(execution)
        status = control.get_operation(control.submit_provisioning(execution.provisioning).operation_id)
        snapshot = control.snapshot
    finally:
        control.close()

    assert status.state is OperationState.FAILED
    assert _PORTABLE_ENVELOPE_ADDRESS in _refusal_addresses(status.diagnostics)
    assert snapshot.realization_envelope == predecessor.realization_envelope
    assert snapshot.entries == predecessor.entries


@pytest.mark.parametrize(
    ("forged_result", "foreign_predecessor"),
    [(True, False), (False, True)],
    ids=["forged-teardown-result", "predecessor-names-another-envelope"],
)
def test_destroy_refuses_a_teardown_envelope_other_than_the_predecessor(forged_result, foreign_predecessor):
    predecessor = _honest_snapshot()
    if foreign_predecessor:
        predecessor = predecessor.with_entries(
            dict(predecessor.entries), realization_envelope=_forged(predecessor.realization_envelope)
        )
    manager = RuntimeManager(_target(forged=forged_result), initial_snapshot=predecessor)

    result = manager.destroy()

    assert result.success is False
    assert _ENVELOPE_ADDRESS in _refusal_addresses(result.diagnostics)
    assert manager.snapshot.realization_envelope == predecessor.realization_envelope
    assert manager.snapshot.entries == predecessor.entries


def test_honest_apply_binds_the_selected_envelope():
    manager = RuntimeManager(_target(forged=False))
    execution = manager.plan(parse_sdl(_NETWORK_ONLY))

    assert manager.apply(execution).success
    assert manager.snapshot.realization_envelope == execution.provisioning.realization_envelope
