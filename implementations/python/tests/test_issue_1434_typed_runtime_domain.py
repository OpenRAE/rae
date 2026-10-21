"""Backend snapshot entries keep the typed runtime domain the plan owns (issue #1434).

``RuntimeDomain`` is a ``str`` enum, so ``"provisioning"`` compares equal to
``RuntimeDomain.PROVISIONING``. The control plane and the credential path read
the domain by identity, so an equal-valued string committed from a backend
result made every later planner-authorized plan for that resource incoherent.
Backend snapshot admission refuses an untyped domain instead.
"""

from __future__ import annotations

from dataclasses import replace

from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import OperationState
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.manager import RuntimeManager

_WITH_WEB = """\
name: typed-domain
nodes:
  web: {type: compute, resources: {ram: 1 gib, cpu: 1}}
  lab: {type: switch}
infrastructure:
  lab: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  web: {count: 1, links: [lab]}
"""
_LAB_ONLY = """\
name: typed-domain
nodes:
  lab: {type: switch}
infrastructure:
  lab: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
"""
_UNTYPED_DOMAIN = ("runtime.backend-contract-invalid", "Backend snapshot contains an untyped runtime domain.")
_OPERATION_INDETERMINATE = (
    "runtime.control-plane.operation-indeterminate",
    "Operation outcome could not be established; explicit resolution is required.",
)


class _StringDomainsOnce:
    """Delegates to the stub provisioner; its first successful result names changed domains as strings."""

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
    target = create_stub_target()
    if not string_domains:
        return target
    return replace(target, provisioner=_StringDomainsOnce(target.provisioner))


def _pairs(diagnostics) -> list[tuple[str, str]]:
    return [(diagnostic.code, diagnostic.message) for diagnostic in diagnostics]


def test_manager_refuses_a_successful_result_with_a_string_domain():
    manager = RuntimeManager(_target(string_domains=True))

    result = manager.apply(manager.plan(parse_sdl(_WITH_WEB)))

    assert result.success is False
    assert _pairs(result.diagnostics) == [_UNTYPED_DOMAIN]
    assert manager.snapshot.entries == {}

    # The refused result committed nothing, so the next planned operation is coherent.
    retry = manager.apply(manager.plan(parse_sdl(_WITH_WEB)))
    assert retry.success is True, _pairs(retry.diagnostics)
    assert manager.snapshot.entries
    assert all(type(entry.domain) is RuntimeDomain for entry in manager.snapshot.entries.values())


def _submit(control: RuntimeControlPlane, target, scenario: str):
    execution = plan(compile_runtime_model(parse_sdl(scenario)), target.manifest, control.snapshot)
    control.register_planner_produced_plan(execution)
    receipt = control.submit_provisioning(execution.provisioning)
    assert receipt.accepted, _pairs(receipt.diagnostics)
    operation = control.get_operation(receipt.operation_id)
    return operation, (operation.state, _pairs(operation.diagnostics))


def test_control_plane_commits_no_untyped_domain():
    target = _target(string_domains=True)
    control = RuntimeControlPlane(target)
    try:
        _, observed = _submit(control, target, _WITH_WEB)
        entries = control.snapshot.entries
    finally:
        control.close()

    # A native invocation that dispatched and then returned an invalid result has
    # unknown effects, so the supervised runtime records it as indeterminate.
    assert observed == (OperationState.INDETERMINATE, [_UNTYPED_DOMAIN, _OPERATION_INDETERMINATE])
    assert entries == {}


def test_typed_domains_keep_the_next_planned_operation_coherent():
    target = _target(string_domains=False)
    control = RuntimeControlPlane(target)
    try:
        outcomes = [_submit(control, target, scenario)[1] for scenario in (_WITH_WEB, _LAB_ONLY)]
        entries = control.snapshot.entries
    finally:
        control.close()

    assert outcomes == [(OperationState.SUCCEEDED, []), (OperationState.SUCCEEDED, [])]
    assert sorted(entries) == ["provision.network.lab"]
    assert all(type(entry.domain) is RuntimeDomain for entry in entries.values())
