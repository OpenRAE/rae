"""Backend snapshot entries keep the typed runtime domain the plan owns (issue #1434).

``RuntimeDomain`` is a ``str`` enum, so ``"provisioning"`` compares equal to
``RuntimeDomain.PROVISIONING``. The control plane and the credential path read
the domain by identity, so an equal-valued string committed from a backend
result made every later planner-authorized plan for that resource incoherent.
Backend snapshot admission refuses an untyped domain instead.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import OperationState
from raes_reference_backend import create_reference_backend_target
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.manager import RuntimeManager

_LAB = """\
  lab: {type: switch}
infrastructure:
  lab: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
"""
_WITH_WEB = (
    "name: typed-domain\nnodes:\n  web: {type: compute, resources: {ram: 1 gib, cpu: 1}}\n"
    + _LAB
    + "  web: {count: 1, links: [lab]}\n"
)
_LAB_ONLY = "name: typed-domain\nnodes:\n" + _LAB


class _StringDomainsOnce:
    """Delegates to the reference provisioner; its first successful result names changed domains as strings."""

    def __init__(self, inner):
        self._inner = inner
        self._lies = 1

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def apply(self, plan, snapshot):
        result = self._inner.apply(plan, snapshot)
        if not result.success or not self._lies:
            return result
        self._lies -= 1
        entries = {
            address: replace(entry, domain=entry.domain.value) if address in result.changed_addresses else entry
            for address, entry in result.snapshot.entries.items()
        }
        return replace(result, snapshot=result.snapshot.with_entries(entries))


def _target(*, string_domains: bool):
    target = create_reference_backend_target()
    if not string_domains:
        return target
    return replace(target, provisioner=_StringDomainsOnce(target.provisioner))


def _codes(diagnostics) -> list[str]:
    return [diagnostic.code for diagnostic in diagnostics]


def test_manager_refuses_a_successful_result_with_a_string_domain():
    manager = RuntimeManager(_target(string_domains=True))

    result = manager.apply(manager.plan(parse_sdl(_WITH_WEB)))

    assert result.success is False
    assert "runtime.backend-contract-invalid" in _codes(result.diagnostics)
    assert manager.snapshot.entries == {}


@pytest.mark.parametrize(
    ("string_domains", "first_state"),
    [(False, OperationState.SUCCEEDED), (True, OperationState.FAILED)],
    ids=["typed", "string-domain"],
)
def test_a_string_domain_cannot_wedge_the_next_planned_operation(string_domains, first_state):
    target = _target(string_domains=string_domains)
    control = RuntimeControlPlane(target)
    planner = RuntimeManager(target)
    states = []
    try:
        for scenario in (_WITH_WEB, _LAB_ONLY):
            execution = planner.plan(parse_sdl(scenario), snapshot=control.snapshot)
            control.register_planner_produced_plan(execution)
            receipt = control.submit_provisioning(execution.provisioning)
            assert receipt.accepted, _codes(receipt.diagnostics)
            states.append(control.get_operation(receipt.operation_id).state)
        entries = control.snapshot.entries
    finally:
        control.close()

    assert states == [first_state, OperationState.SUCCEEDED]
    assert sorted(entries) == ["provision.network.lab"]
    assert all(type(entry.domain) is RuntimeDomain for entry in entries.values())
