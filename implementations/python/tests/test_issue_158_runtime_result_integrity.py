"""Characterize RuntimeManager result-integrity enforcement (issue #158).

RAE owns validation of portable results admitted into its runtime state. Backend
implementation correctness, capability certification, and infrastructure
realization remain outside this test's scope.

Each case uses the real ``ReferenceProvisioner`` and perturbs only its returned
``ApplyResult``. The unmodified control proves that the shared target, scenario,
and realization context are accepted before a result perturbation is evaluated.

Every perturbation must reject with the violated invariant and preserve the
entire trusted predecessor, without accepting rejected details or change claims.
"""

from __future__ import annotations

import dataclasses

from raes import parse_sdl
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_reference_backend import create_reference_backend_target
from raes_reference_backend.provisioner import ReferenceProvisioner
from raes_runtime.manager import RuntimeManager

_SCENARIO = """
name: runtime-result-integrity
nodes:
  lab: {type: switch}
  web: {type: compute, resources: {ram: 1 gib, cpu: 1}}
infrastructure:
  lab: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  web: {count: 1, links: [lab]}
"""

_UNPLANNED_ADDRESS = "provision.node.unplanned"


def _predecessor():
    return RuntimeSnapshot(metadata={"trusted": {"run": "predecessor"}})


class _ReturnsPredecessorSnapshot(ReferenceProvisioner):
    """Returns the predecessor snapshot while reporting successful changes."""

    def apply(self, plan, snapshot):
        super().apply(plan, snapshot)
        return ApplyResult(
            success=True,
            snapshot=snapshot,
            changed_addresses=[operation.address for operation in plan.operations],
        )


class _AddsUnplannedPortableResource(ReferenceProvisioner):
    """Adds a portable snapshot entry with no corresponding plan address."""

    def apply(self, plan, snapshot):
        result = super().apply(plan, snapshot)
        if not result.success:
            return result
        entries = dict(result.snapshot.entries)
        entries[_UNPLANNED_ADDRESS] = dataclasses.replace(
            next(iter(entries.values())),
            address=_UNPLANNED_ADDRESS,
        )
        return dataclasses.replace(
            result,
            snapshot=result.snapshot.with_entries(entries),
            changed_addresses=[*result.changed_addresses, _UNPLANNED_ADDRESS],
        )


class _RewritesResourceType(ReferenceProvisioner):
    """Rewrites the plan-owned type of one returned resource."""

    def apply(self, plan, snapshot):
        result = super().apply(plan, snapshot)
        if not result.success:
            return result
        entries = dict(result.snapshot.entries)
        for address, entry in entries.items():
            if entry.resource_type == "node":
                entries[address] = dataclasses.replace(entry, resource_type="network")
                break
        return dataclasses.replace(result, snapshot=result.snapshot.with_entries(entries))


class _OmitsChangedAddressAccounting(ReferenceProvisioner):
    """Returns a snapshot transition without changed-address accounting."""

    def apply(self, plan, snapshot):
        result = super().apply(plan, snapshot)
        if not result.success:
            return result
        return dataclasses.replace(result, changed_addresses=[])


class _RewritesRuntimeDomain(ReferenceProvisioner):
    """Rewrites provisioning entries to the evaluation runtime domain."""

    def apply(self, plan, snapshot):
        result = super().apply(plan, snapshot)
        if not result.success:
            return result
        entries = {
            address: dataclasses.replace(entry, domain=RuntimeDomain.EVALUATION)
            for address, entry in result.snapshot.entries.items()
        }
        return dataclasses.replace(result, snapshot=result.snapshot.with_entries(entries))


def _apply_with(provisioner_class=None):
    """Apply the scenario through the reference target, optionally perturbed.

    The perturbed provisioner is built from the reference provisioner's driver and
    realization envelope, so the returned result is the only changed surface.
    """

    target = create_reference_backend_target()
    if provisioner_class is not None:
        reference = target.provisioner
        target = dataclasses.replace(
            target,
            provisioner=provisioner_class(
                reference._driver,  # noqa: SLF001 - perturbing the real provisioner is the method
                realization_envelope=reference._realization_envelope,  # noqa: SLF001
            ),
        )
    manager = RuntimeManager(target, initial_snapshot=_predecessor())
    return manager.apply(manager.plan(parse_sdl(_SCENARIO)))


def _assert_rejected(result, address, message):
    assert result.success is False
    assert result.snapshot == _predecessor()
    assert result.changed_addresses == []
    assert result.details == {}
    assert [(item.code, item.address, item.message) for item in result.diagnostics] == [
        ("runtime.backend-contract-invalid", address, message)
    ]


def test_unmodified_reference_result_is_accepted():
    """Control for the shared target, scenario, and realization context."""

    result = _apply_with()

    assert result.success, [diagnostic.message for diagnostic in result.diagnostics]
    assert sorted(result.snapshot.entries) == ["provision.network.lab", "provision.node.web"]


def test_success_with_predecessor_snapshot_is_rejected_with_transition_diagnostic():
    """Attribute the existing rejection to changed-address transition validation."""

    result = _apply_with(_ReturnsPredecessorSnapshot)

    assert result.success is False
    assert result.snapshot.entries == {}
    assert result.changed_addresses == []
    assert [(diagnostic.code, diagnostic.address, diagnostic.message) for diagnostic in result.diagnostics] == [
        (
            "runtime.backend-contract-invalid",
            "runtime.changed-addresses",
            "Backend reported a changed address outside the snapshot transition.",
        )
    ]


def test_unplanned_portable_address_is_not_admitted_without_contract_authority():
    result = _apply_with(_AddsUnplannedPortableResource)
    _assert_rejected(result, _UNPLANNED_ADDRESS, "Backend added a resource without admitted collection authority.")


def test_plan_owned_resource_type_cannot_be_rewritten():
    result = _apply_with(_RewritesResourceType)
    _assert_rejected(result, "provision.node.web", "Backend changed a plan-owned resource type.")


def test_snapshot_transition_requires_changed_address_accounting():
    result = _apply_with(_OmitsChangedAddressAccounting)
    _assert_rejected(result, "runtime.changed-addresses", "Backend omitted an authorized resource change.")


def test_provisioning_result_cannot_rewrite_the_runtime_domain():
    result = _apply_with(_RewritesRuntimeDomain)
    _assert_rejected(result, "provision.network.lab", "Backend changed a plan-owned runtime domain.")
