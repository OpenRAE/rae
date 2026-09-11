"""Provisioner implementation for the libvirt/QEMU backend."""

from __future__ import annotations

from dataclasses import dataclass

from raes_backend_protocols.capabilities import ProvisionerCapabilities
from raes_contracts.contracts import RealizationEnvelopeIdentityModel
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_contracts.realization_observation import (
    RealizationObservation,
    RealizationObservationDisclosure,
    bind_compute_substrate_observations,
    compute_substrate_readback_addresses,
    missing_compute_substrate_readbacks,
)
from raes_contracts.realization_observation_demand import compute_substrate_collection_addresses
from raes_contracts.realization_operational_observation import invoke_native_readback
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry

from ._payload import NETWORK_RESOURCE_TYPE, NODE_RESOURCE_TYPE
from .driver import DomainSpec, DriverResult, LibvirtDriver, NetworkSpec
from .envelopes import LibvirtDriverMode, load_libvirt_realization_envelope
from .manifest import _provisioner_capabilities
from .realization import Realization, interpret_provisioning_plan
from .techvault_concerns import techvault_observation_diagnostics
from .techvault_plan_admission import techvault_admission_diagnostics

_DOMAIN = "runtime"
INVALID_PLAN_CODE = "libvirt-backend.invalid-plan"
UNCONFIRMED_DESTROY_CODE = "libvirt-backend.driver.unconfirmed-destroy"
UNCONFIRMED_REALIZATION_CODE = "libvirt-backend.driver.unconfirmed-realization"
UNCONFIRMED_OBSERVATION_CODE = "libvirt-backend.driver.compute-substrate-unobserved"
MISSING_ENVELOPE_CODE = "libvirt-backend.realization-envelope.missing"
MISMATCHED_ENVELOPE_CODE = "libvirt-backend.realization-envelope.mismatch"
BASELINE_ENVELOPE_MISMATCH_CODE = "libvirt-backend.realization-envelope.baseline-mismatch"


@dataclass
class _SnapshotReconciliation:
    entries: dict[str, SnapshotEntry]
    changed_addresses: list[str]
    delete_networks: list[str]
    delete_domains: list[str]


class LibvirtProvisioner:
    """Provisioning-only backend that realizes plans through a libvirt driver."""

    def __init__(
        self,
        driver: LibvirtDriver | None = None,
        *,
        provisioner_capabilities: ProvisionerCapabilities | None = None,
        realization_envelope: RealizationEnvelopeIdentityModel | None = None,
    ) -> None:
        self._driver = driver if driver is not None else _default_driver()
        mode = LibvirtDriverMode(getattr(self._driver, "driver_mode", LibvirtDriverMode.GENERIC.value))
        expected_capabilities = _provisioner_capabilities(mode)
        expected_envelope = load_libvirt_realization_envelope(mode).identity
        if provisioner_capabilities is not None and provisioner_capabilities != expected_capabilities:
            raise ValueError("libvirt provisioner capabilities do not match driver mode")
        if realization_envelope is not None and realization_envelope != expected_envelope:
            raise ValueError("libvirt provisioner realization envelope does not match driver mode")
        self._provisioner_capabilities = expected_capabilities
        self._mode = mode
        self._name_prefix = str(getattr(self._driver, "name_prefix", "raes-techvault"))
        self._backend_realization_envelope = load_libvirt_realization_envelope(mode)
        self._realization_envelope = expected_envelope

    def validate(self, plan: ProvisioningPlan) -> list[Diagnostic]:
        if not isinstance(plan, ProvisioningPlan):
            return [_invalid_plan_diagnostic()]
        identity_diagnostics = self._identity_diagnostics(plan, RuntimeSnapshot())
        if identity_diagnostics:
            return identity_diagnostics
        realization = interpret_provisioning_plan(plan, provisioner_capabilities=self._provisioner_capabilities)
        diagnostics = list(realization.diagnostics)
        if self._mode is LibvirtDriverMode.TECHVAULT_APPLIANCE:
            diagnostics.extend(
                techvault_admission_diagnostics(
                    plan,
                    self._backend_realization_envelope,
                    name_prefix=self._name_prefix,
                )
            )
        return diagnostics

    def apply(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        if not isinstance(plan, ProvisioningPlan):
            result = ApplyResult(success=False, snapshot=snapshot, diagnostics=[_invalid_plan_diagnostic()])
        else:
            result = self._apply_provisioning_plan(plan, snapshot)
        return result

    def _apply_provisioning_plan(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        identity_diagnostics = self._identity_diagnostics(plan, snapshot)
        if identity_diagnostics:
            result = ApplyResult(success=False, snapshot=snapshot, diagnostics=identity_diagnostics)
        else:
            result = self._apply_realization(plan, snapshot)
        return result

    def _apply_realization(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        realization = interpret_provisioning_plan(plan, provisioner_capabilities=self._provisioner_capabilities)
        diagnostics: list[Diagnostic] = list(realization.diagnostics)
        if self._mode is LibvirtDriverMode.TECHVAULT_APPLIANCE:
            diagnostics.extend(
                techvault_admission_diagnostics(
                    plan,
                    self._backend_realization_envelope,
                    name_prefix=self._name_prefix,
                )
            )
        if _has_error(diagnostics):
            return ApplyResult(success=False, snapshot=snapshot, diagnostics=diagnostics)

        reconciliation = _reconcile_snapshot(plan, snapshot)
        driver_diagnostics, observations, readback_diagnostics = self._drive(
            plan,
            realization,
            reconciliation.delete_networks,
            reconciliation.delete_domains,
            previous=snapshot.realization_observations,
        )
        diagnostics.extend(driver_diagnostics)
        if _has_error(diagnostics):
            return ApplyResult(success=False, snapshot=snapshot, diagnostics=diagnostics)
        diagnostics.extend(readback_diagnostics)
        diagnostics.extend(
            _driver_confirmation_diagnostic(address, code=UNCONFIRMED_OBSERVATION_CODE)
            for address in missing_compute_substrate_readbacks(
                plan=plan,
                observations=observations,
                envelope=self._backend_realization_envelope,
                previous=snapshot.realization_observations,
            )
        )

        success = not _has_error(diagnostics)
        observation_disclosures = (
            bind_compute_substrate_observations(
                plan=plan,
                observations=observations,
                envelope=self._backend_realization_envelope,
                previous=snapshot.realization_observations,
                selected_addresses=set(compute_substrate_collection_addresses(plan=plan)),
            )
            if success
            else ()
        )
        return ApplyResult(
            success=success,
            snapshot=snapshot.with_entries(
                reconciliation.entries,
                realization_observations=(),
                realization_envelope=self._realization_envelope,
            ),
            diagnostics=diagnostics,
            changed_addresses=reconciliation.changed_addresses,
            operational_realization_observations=observation_disclosures,
        )

    def _drive(
        self,
        plan: ProvisioningPlan,
        realization: Realization,
        delete_networks: list[str],
        delete_domains: list[str],
        *,
        previous: tuple[RealizationObservationDisclosure, ...],
    ) -> tuple[list[Diagnostic], tuple[RealizationObservation, ...], list[Diagnostic]]:
        active = self._active_addresses(plan, realization)
        networks = tuple(spec for spec in realization.networks if spec.address in active)
        domains = tuple(spec for spec in realization.domains if spec.address in active)
        diagnostics, observations = self._realize_active(networks, domains)
        diagnostics.extend(self._delete_targets(delete_networks, delete_domains))
        if _has_error(diagnostics):
            return diagnostics, observations, []
        readback = set(
            compute_substrate_readback_addresses(
                plan=plan,
                envelope=self._backend_realization_envelope,
                previous=previous,
            )
        )
        readback_domains = tuple(spec for spec in realization.domains if spec.address in readback)
        readback_diagnostics = []
        if readback_domains:
            readback_diagnostics, readback_observations = invoke_native_readback(
                lambda: self._driver.observe(domains=readback_domains),
            )
            observations = (*observations, *readback_observations)
        return diagnostics, observations, readback_diagnostics

    @staticmethod
    def _active_addresses(plan: ProvisioningPlan, realization: Realization) -> set[str]:
        active = {op.address for op in plan.operations if op.action in {ChangeAction.CREATE, ChangeAction.UPDATE}}
        # A changed placement must realize its target domain even when the node
        # itself is UNCHANGED: the domain's seed now carries different cloud-init.
        for placement_address, node_address in realization.placement_targets.items():
            if placement_address in active:
                active.add(node_address)
        return active

    def _realize_active(
        self,
        networks: tuple[NetworkSpec, ...],
        domains: tuple[DomainSpec, ...],
    ) -> tuple[list[Diagnostic], tuple[RealizationObservation, ...]]:
        if not (networks or domains):
            return [], ()
        result = self._driver.realize(networks=networks, domains=domains)
        realization_diagnostics = [
            *result.diagnostics,
            *_unconfirmed_realization_diagnostics(
                result, requested=tuple(spec.address for spec in (*networks, *domains))
            ),
        ]
        diagnostics = list(realization_diagnostics)
        observation_diagnostics: list[Diagnostic] = []
        if self._mode is LibvirtDriverMode.TECHVAULT_APPLIANCE and not result.diagnostics:
            observation_diagnostics = techvault_observation_diagnostics(
                networks=networks,
                domains=domains,
                result=result,
            )
            diagnostics.extend(observation_diagnostics)
        if self._mode is LibvirtDriverMode.TECHVAULT_APPLIANCE and _has_error(
            [*realization_diagnostics, *observation_diagnostics]
        ):
            diagnostics.extend(self._rollback_realization(networks, domains))
        return diagnostics, result.observations

    def _rollback_realization(
        self,
        networks: tuple[NetworkSpec, ...],
        domains: tuple[DomainSpec, ...],
    ) -> list[Diagnostic]:
        cleanup = self._driver.destroy(
            networks=tuple(spec.address for spec in networks),
            domains=tuple(spec.address for spec in domains),
        )
        return [
            *cleanup.diagnostics,
            *_unconfirmed_destroy_diagnostics(
                cleanup,
                requested=tuple(spec.address for spec in (*domains, *networks)),
            ),
        ]

    def _delete_targets(self, delete_networks: list[str], delete_domains: list[str]) -> list[Diagnostic]:
        if not (delete_networks or delete_domains):
            return []
        result = self._driver.destroy(networks=tuple(delete_networks), domains=tuple(delete_domains))
        return [
            *result.diagnostics,
            *_unconfirmed_destroy_diagnostics(
                result,
                requested=(*delete_networks, *delete_domains),
            ),
        ]

    def _identity_diagnostics(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        if plan.realization_envelope is None:
            diagnostics = [
                _envelope_diagnostic(
                    MISSING_ENVELOPE_CODE, "Provisioning plan is missing realization envelope identity."
                )
            ]
        elif plan.realization_envelope != self._realization_envelope:
            diagnostics = [
                _envelope_diagnostic(
                    MISMATCHED_ENVELOPE_CODE,
                    "Provisioning plan realization envelope does not match the configured libvirt target.",
                )
            ]
        elif (
            snapshot.realization_envelope is not None and snapshot.realization_envelope != self._realization_envelope
        ) or (_snapshot_has_state(snapshot) and snapshot.realization_envelope is None):
            if plan.realization_constraints:
                return diagnostics
            diagnostics = [
                _envelope_diagnostic(
                    BASELINE_ENVELOPE_MISMATCH_CODE,
                    "Runtime snapshot is not bound to the configured libvirt realization envelope.",
                )
            ]
        return diagnostics


def validate(plan: ProvisioningPlan) -> list[Diagnostic]:
    """Validate a provisioning plan with the default libvirt provisioner."""

    return LibvirtProvisioner().validate(plan)


def apply(plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
    """Apply a provisioning plan with the default libvirt provisioner."""

    return LibvirtProvisioner().apply(plan, snapshot)


def _default_driver() -> LibvirtDriver:
    from .drivers.libvirt import LibvirtDeploymentDriver

    return LibvirtDeploymentDriver()


def _reconcile_snapshot(plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> _SnapshotReconciliation:
    reconciliation = _SnapshotReconciliation(
        entries=dict(snapshot.entries),
        changed_addresses=[],
        delete_networks=[],
        delete_domains=[],
    )
    for op in plan.operations:
        _reconcile_operation(reconciliation, op)
    return reconciliation


def _reconcile_operation(reconciliation: _SnapshotReconciliation, op: ProvisionOp) -> None:
    if op.action == ChangeAction.DELETE:
        _record_delete(reconciliation, op)
        return
    _record_snapshot_entry(reconciliation, op)


def _record_delete(reconciliation: _SnapshotReconciliation, op: ProvisionOp) -> None:
    reconciliation.entries.pop(op.address, None)
    reconciliation.changed_addresses.append(op.address)
    delete_targets = {
        NETWORK_RESOURCE_TYPE: reconciliation.delete_networks,
        NODE_RESOURCE_TYPE: reconciliation.delete_domains,
    }
    target = delete_targets.get(op.resource_type)
    if target is not None:
        target.append(op.address)


def _record_snapshot_entry(reconciliation: _SnapshotReconciliation, op: ProvisionOp) -> None:
    status = "unchanged" if op.action == ChangeAction.UNCHANGED else "applied"
    reconciliation.entries[op.address] = SnapshotEntry(
        address=op.address,
        domain=RuntimeDomain.PROVISIONING,
        resource_type=op.resource_type,
        payload=op.payload,
        ordering_dependencies=op.ordering_dependencies,
        refresh_dependencies=op.refresh_dependencies,
        status=status,
    )
    if op.action != ChangeAction.UNCHANGED:
        reconciliation.changed_addresses.append(op.address)


def _has_error(diagnostics: list[Diagnostic]) -> bool:
    return any(diag.is_error for diag in diagnostics)


def _snapshot_has_state(snapshot: RuntimeSnapshot) -> bool:
    return any(
        (
            snapshot.entries,
            snapshot.orchestration_results,
            snapshot.orchestration_history,
            snapshot.evaluation_results,
            snapshot.evaluation_history,
            snapshot.participant_episode_results,
            snapshot.participant_episode_history,
            snapshot.participant_behavior_history,
            snapshot.shared_state_records,
            snapshot.shared_state_history,
            snapshot.joint_action_records,
            snapshot.time_management_contexts,
            snapshot.realization_provenance,
        )
    )


def _invalid_plan_diagnostic() -> Diagnostic:
    return Diagnostic(
        code=INVALID_PLAN_CODE,
        domain=_DOMAIN,
        address="runtime.libvirt.provisioning",
        message="Libvirt provisioner accepts only raes_contracts.planning.ProvisioningPlan inputs.",
        severity=Severity.ERROR,
    )


def _unconfirmed_realization_diagnostics(result: DriverResult, *, requested: tuple[str, ...]) -> list[Diagnostic]:
    confirmed = {handle.address for handle in (*result.networks, *result.domains) if handle.realized}
    errored = {diag.address for diag in result.diagnostics if diag.is_error}
    return [
        _driver_confirmation_diagnostic(address, code=UNCONFIRMED_REALIZATION_CODE)
        for address in requested
        if address not in confirmed and address not in errored
    ]


def _unconfirmed_destroy_diagnostics(result: DriverResult, *, requested: tuple[str, ...]) -> list[Diagnostic]:
    confirmed_destroyed = {handle.address for handle in (*result.networks, *result.domains) if not handle.realized}
    errored = {diag.address for diag in result.diagnostics if diag.is_error}
    return [
        _driver_confirmation_diagnostic(address, code=UNCONFIRMED_DESTROY_CODE)
        for address in requested
        if address not in confirmed_destroyed and address not in errored
    ]


def _driver_confirmation_diagnostic(address: str, *, code: str) -> Diagnostic:
    action = "destroy" if code == UNCONFIRMED_DESTROY_CODE else "realization"
    return Diagnostic(
        code=code,
        domain=_DOMAIN,
        address=address,
        message=f"Libvirt driver did not confirm {action} for '{address}'.",
        severity=Severity.ERROR,
    )


def _envelope_diagnostic(code: str, message: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        domain=_DOMAIN,
        address="runtime.libvirt.realization-envelope",
        message=message,
        severity=Severity.ERROR,
    )
