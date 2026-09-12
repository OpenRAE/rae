"""Reference provisioner: portable snapshot reconciliation + driver side effects.

The provisioner preserves planned payloads honestly into snapshot entries
(the portable surface SEM-218 provenance is computed against), sets entry
status, and drives the injected :class:`DeploymentDriver` to realize or
destroy the corresponding emulated infrastructure. Real container
realization is a DRIVER side effect; it never mutates the portable
snapshot. Driver diagnostics are surfaced through ``ApplyResult`` -- never
as a backend-specific exception.
"""

from __future__ import annotations

from collections.abc import Mapping

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.domain_profiles import DomainProfileResolutionContextModel
from raes_contracts.planning import ChangeAction, PlanOperation, ProvisioningPlan, RuntimeDomain
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel
from raes_contracts.realization_observation import (
    RealizationObservation,
    RealizationObservationDisclosure,
    bind_compute_substrate_observations,
    compute_substrate_readback_addresses,
    missing_compute_substrate_readbacks,
)
from raes_contracts.realization_observation_demand import compute_substrate_collection_addresses
from raes_contracts.realization_operational_observation import invoke_native_readback
from raes_contracts.realization_preparation import RealizationPreparation
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry

from .driver import ContainerSpec, DeploymentDriver, NetworkSpec
from .profile_preparation import (
    prepare_reference_profiles,
    reference_profile_configuration,
    reference_profile_diagnostics,
)
from .realization import (
    NETWORK_RESOURCE_TYPE,
    NODE_RESOURCE_TYPE,
    Realization,
    interpret_provisioning_plan,
)


class ReferenceProvisioner:
    """Container-backed provisioner over an injected deployment driver."""

    def __init__(
        self,
        driver: DeploymentDriver,
        realization_envelope: BackendRealizationEnvelopeModel | None = None,
        *,
        domain_profile_context: DomainProfileResolutionContextModel | None = None,
        profile_choices: Mapping[str, object] | None = None,
    ) -> None:
        self._driver = driver
        self._realization_envelope = realization_envelope
        self.domain_profile_context, self._profile_choices = reference_profile_configuration(
            domain_profile_context, profile_choices or {}
        )

    def validate(self, plan: ProvisioningPlan) -> list[Diagnostic]:
        realization = interpret_provisioning_plan(plan)
        return [*realization.diagnostics, *reference_profile_diagnostics(plan, self.domain_profile_context)]

    def prepare(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> RealizationPreparation:
        return prepare_reference_profiles(plan, snapshot, self.domain_profile_context, self._profile_choices)

    def validate_profiles(self, plan: ProvisioningPlan) -> list[Diagnostic]:
        return reference_profile_diagnostics(plan, self.domain_profile_context)

    def apply(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        failure = self._realization_envelope_mismatch(plan, snapshot)
        realization = interpret_provisioning_plan(plan)
        diagnostics: list[Diagnostic] = [
            *realization.diagnostics,
            *reference_profile_diagnostics(plan, self.domain_profile_context),
        ]
        if failure is None and any(diag.is_error for diag in diagnostics):
            failure = ApplyResult(success=False, snapshot=snapshot, diagnostics=diagnostics)
        if failure is not None:
            return failure

        entries, changed_addresses, delete_networks, delete_containers = _project_snapshot_entries(plan, snapshot)

        driver_diagnostics, observations, readback_diagnostics = self._drive(
            plan,
            realization,
            delete_networks,
            delete_containers,
            previous=snapshot.realization_observations,
        )
        diagnostics.extend(driver_diagnostics)
        if any(diag.is_error for diag in diagnostics):
            return ApplyResult(success=False, snapshot=snapshot, diagnostics=diagnostics)
        diagnostics.extend(readback_diagnostics)
        diagnostics.extend(self._missing_observation_diagnostics(plan, observations, snapshot))
        success = not any(diag.is_error for diag in diagnostics)
        observation_disclosures = self._bound_observation_disclosures(plan, observations, snapshot) if success else ()
        return ApplyResult(
            success=success,
            snapshot=snapshot.with_entries(
                entries,
                realization_observations=(),
                realization_envelope=(
                    self._realization_envelope.identity
                    if self._realization_envelope is not None
                    else snapshot.realization_envelope
                ),
            ),
            diagnostics=diagnostics,
            changed_addresses=changed_addresses,
            operational_realization_observations=observation_disclosures,
        )

    def _realization_envelope_mismatch(
        self,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult | None:
        if not plan.realization_constraints or (
            self._realization_envelope is not None and plan.realization_envelope == self._realization_envelope.identity
        ):
            return None
        return ApplyResult(
            success=False,
            snapshot=snapshot,
            diagnostics=[
                Diagnostic(
                    code="reference-backend.realization-envelope.mismatch",
                    domain="runtime",
                    address="runtime.reference.provisioning",
                    message="Provisioning plan does not match the selected reference realization envelope.",
                )
            ],
        )

    def _missing_observation_diagnostics(
        self,
        plan: ProvisioningPlan,
        observations: tuple[RealizationObservation, ...],
        snapshot: RuntimeSnapshot,
    ) -> list[Diagnostic]:
        if self._realization_envelope is None:
            return []
        return [
            Diagnostic(
                code="reference-backend.driver.compute-substrate-unobserved",
                domain="runtime",
                address=address,
                message=f"Reference driver did not return fresh substrate readback for '{address}'.",
            )
            for address in missing_compute_substrate_readbacks(
                plan=plan,
                observations=observations,
                envelope=self._realization_envelope,
                previous=snapshot.realization_observations,
            )
        ]

    def _bound_observation_disclosures(
        self,
        plan: ProvisioningPlan,
        observations: tuple[RealizationObservation, ...],
        snapshot: RuntimeSnapshot,
    ) -> tuple[RealizationObservationDisclosure, ...]:
        if self._realization_envelope is None:
            return snapshot.realization_observations
        return bind_compute_substrate_observations(
            plan=plan,
            observations=observations,
            envelope=self._realization_envelope,
            previous=snapshot.realization_observations,
            selected_addresses=set(compute_substrate_collection_addresses(plan=plan)),
        )

    def _drive(
        self,
        plan: ProvisioningPlan,
        realization: Realization,
        delete_networks: list[str],
        delete_containers: list[str],
        *,
        previous: tuple[RealizationObservationDisclosure, ...],
    ) -> tuple[list[Diagnostic], tuple[RealizationObservation, ...], list[Diagnostic]]:
        active = {op.address for op in plan.operations if op.action in {ChangeAction.CREATE, ChangeAction.UPDATE}}
        networks = tuple(spec for spec in realization.networks if spec.address in active)
        containers = tuple(spec for spec in realization.containers if spec.address in active)
        diagnostics, observations = self._realize_active(networks, containers)
        diagnostics.extend(self._destroy_deleted(delete_networks, delete_containers))
        if any(diag.is_error for diag in diagnostics):
            return diagnostics, observations, []
        readback_diagnostics, readback_observations = self._observe_selected(
            plan,
            realization,
            previous,
        )
        observations = (*observations, *readback_observations)
        return diagnostics, observations, readback_diagnostics

    def _realize_active(
        self,
        networks: tuple[NetworkSpec, ...],
        containers: tuple[ContainerSpec, ...],
    ) -> tuple[list[Diagnostic], tuple[RealizationObservation, ...]]:
        if networks or containers:
            result = self._driver.realize(networks=networks, containers=containers)
            return list(result.diagnostics), result.observations
        return [], ()

    def _observe_selected(
        self,
        plan: ProvisioningPlan,
        realization: Realization,
        previous: tuple[RealizationObservationDisclosure, ...],
    ) -> tuple[list[Diagnostic], tuple[RealizationObservation, ...]]:
        if self._realization_envelope is None:
            return [], ()
        readback = set(
            compute_substrate_readback_addresses(
                plan=plan,
                envelope=self._realization_envelope,
                previous=previous,
            )
        )
        containers = tuple(spec for spec in realization.containers if spec.address in readback)
        if not containers:
            return [], ()
        return invoke_native_readback(lambda: self._driver.observe(containers=containers))

    def _destroy_deleted(
        self,
        delete_networks: list[str],
        delete_containers: list[str],
    ) -> list[Diagnostic]:
        if delete_networks or delete_containers:
            result = self._driver.destroy(
                networks=tuple(delete_networks),
                containers=tuple(delete_containers),
            )
            return list(result.diagnostics)
        return []


def _project_snapshot_entries(
    plan: ProvisioningPlan,
    snapshot: RuntimeSnapshot,
) -> tuple[dict[str, SnapshotEntry], list[str], list[str], list[str]]:
    entries = dict(snapshot.entries)
    changed_addresses: list[str] = []
    delete_networks: list[str] = []
    delete_containers: list[str] = []
    for operation in plan.operations:
        _project_snapshot_operation(
            operation,
            entries,
            changed_addresses,
            delete_networks,
            delete_containers,
        )
    return entries, changed_addresses, delete_networks, delete_containers


def _project_snapshot_operation(
    operation: PlanOperation,
    entries: dict[str, SnapshotEntry],
    changed_addresses: list[str],
    delete_networks: list[str],
    delete_containers: list[str],
) -> None:
    if operation.action == ChangeAction.DELETE:
        entries.pop(operation.address, None)
        changed_addresses.append(operation.address)
        if operation.resource_type == NETWORK_RESOURCE_TYPE:
            delete_networks.append(operation.address)
        elif operation.resource_type == NODE_RESOURCE_TYPE:
            delete_containers.append(operation.address)
        return
    status = "unchanged" if operation.action == ChangeAction.UNCHANGED else "applied"
    entries[operation.address] = SnapshotEntry(
        address=operation.address,
        domain=RuntimeDomain.PROVISIONING,
        resource_type=operation.resource_type,
        payload=operation.payload,
        ordering_dependencies=operation.ordering_dependencies,
        refresh_dependencies=operation.refresh_dependencies,
        status=status,
        profile_bindings=getattr(operation, "profile_bindings", ()),
    )
    if operation.action != ChangeAction.UNCHANGED:
        changed_addresses.append(operation.address)
