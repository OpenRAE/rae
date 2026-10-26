"""Narrow provisioner double with a separate native realize/readback seam.

The double exercises the portable runtime boundary that a concrete backend
reaches after it creates resources: post-creation native readback through
``invoke_native_readback`` and fresh compute-substrate binding. It owns no
container, daemon, or host effect. The runtime owns every verdict that the
tests assert; the double only reports what its in-memory "driver" did.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_stubs.stubs import create_stub_components
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ChangeAction, ProvisioningPlan, RuntimeDomain
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel, RealizationConcern
from raes_contracts.realization_observation import (
    RealizationObservation,
    bind_compute_substrate_observations,
    compute_substrate_readback_addresses,
    missing_compute_substrate_readbacks,
)
from raes_contracts.realization_observation_demand import compute_substrate_collection_addresses
from raes_contracts.realization_operational_observation import invoke_native_readback
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_contracts.vocabulary import ObservationStrength
from raes_runtime.registry import RuntimeTarget
from t2_envelope_manifests import VIRTUAL_MACHINE_ENVELOPE, stub_manifest_with_envelope

NATIVE_READBACK_TARGET_NAME = "native-readback-double"


@dataclass(frozen=True)
class DriverResult:
    """Native call outcome: diagnostics plus freshly observed facts."""

    diagnostics: tuple[Diagnostic, ...] = ()
    observations: tuple[RealizationObservation, ...] = ()


@dataclass
class InMemoryNativeDriver:
    """Record realized addresses and answer substrate readback from memory."""

    envelope: BackendRealizationEnvelopeModel
    _realized: set[str] = field(default_factory=set)
    _sequence: int = 0

    def realized_addresses(self) -> frozenset[str]:
        return frozenset(self._realized)

    def realize(self, *, addresses: tuple[str, ...]) -> DriverResult:
        self._realized.update(addresses)
        return DriverResult()

    def destroy(self, *, addresses: tuple[str, ...]) -> DriverResult:
        self._realized.difference_update(addresses)
        return DriverResult()

    def observe(self, *, addresses: tuple[str, ...]) -> DriverResult:
        """Read back the compute substrate of addresses that this driver realized."""

        claim = next(item for item in self.envelope.concerns if item.concern is RealizationConcern.COMPUTE_SUBSTRATE)
        observations = []
        for address in addresses:
            if address not in self._realized:
                continue
            self._sequence += 1
            observations.append(
                RealizationObservation(
                    address=address,
                    field_path="compute-substrate",
                    concern=RealizationConcern.COMPUTE_SUBSTRATE,
                    source=ObservationStrength.DAEMON_OBSERVED,
                    value=claim.mechanism,
                    envelope_digest=self.envelope.digest,
                    configuration_digest=self.envelope.configuration.configuration_digest,
                    observer_version="native-readback-double/v1",
                    sequence=self._sequence,
                    binding_verified=True,
                )
            )
        return DriverResult(observations=tuple(observations))


class NativeReadbackProvisioner:
    """Project plan operations, drive the in-memory driver, then read back."""

    def __init__(self, envelope: BackendRealizationEnvelopeModel, driver: InMemoryNativeDriver) -> None:
        self._envelope = envelope
        self.driver = driver

    def validate(self, plan: ProvisioningPlan) -> list[Diagnostic]:
        del plan
        return []

    def apply(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        if plan.realization_constraints and plan.realization_envelope != self._envelope.identity:
            return ApplyResult(
                success=False,
                snapshot=snapshot,
                diagnostics=[
                    Diagnostic(
                        code="native-readback-double.realization-envelope.mismatch",
                        domain="runtime",
                        address="runtime.native-readback-double.provisioning",
                        message="Provisioning plan does not match the double's realization envelope.",
                    )
                ],
            )
        entries = dict(snapshot.entries)
        changed: list[str] = []
        active: list[str] = []
        deleted: list[str] = []
        for operation in plan.operations:
            if operation.action == ChangeAction.DELETE:
                entries.pop(operation.address, None)
                changed.append(operation.address)
                deleted.append(operation.address)
                continue
            entries[operation.address] = SnapshotEntry(
                address=operation.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=operation.resource_type,
                payload=operation.payload,
                ordering_dependencies=operation.ordering_dependencies,
                refresh_dependencies=operation.refresh_dependencies,
                status="unchanged" if operation.action == ChangeAction.UNCHANGED else "applied",
            )
            if operation.action != ChangeAction.UNCHANGED:
                changed.append(operation.address)
                active.append(operation.address)
        diagnostics = [*self.driver.realize(addresses=tuple(active)).diagnostics]
        diagnostics.extend(self.driver.destroy(addresses=tuple(deleted)).diagnostics)
        readback = compute_substrate_readback_addresses(
            plan=plan, envelope=self._envelope, previous=snapshot.realization_observations
        )
        observations: tuple[RealizationObservation, ...] = ()
        if readback:
            readback_diagnostics, observations = invoke_native_readback(
                lambda: self.driver.observe(addresses=tuple(readback))
            )
            diagnostics.extend(readback_diagnostics)
        diagnostics.extend(
            Diagnostic(
                code="native-readback-double.compute-substrate-unobserved",
                domain="runtime",
                address=address,
                message=f"Native readback did not return a fresh substrate fact for '{address}'.",
            )
            for address in missing_compute_substrate_readbacks(
                plan=plan,
                observations=observations,
                envelope=self._envelope,
                previous=snapshot.realization_observations,
            )
        )
        success = not any(diagnostic.is_error for diagnostic in diagnostics)
        disclosures = (
            bind_compute_substrate_observations(
                plan=plan,
                observations=observations,
                envelope=self._envelope,
                previous=snapshot.realization_observations,
                selected_addresses=set(compute_substrate_collection_addresses(plan=plan)),
            )
            if success
            else ()
        )
        return ApplyResult(
            success=success,
            snapshot=snapshot.with_entries(
                entries, realization_observations=(), realization_envelope=self._envelope.identity
            ),
            diagnostics=diagnostics,
            changed_addresses=changed,
            operational_realization_observations=disclosures,
        )


def create_native_readback_target(*, manifest: BackendManifest | None = None) -> RuntimeTarget:
    """Return a stub-composed target whose provisioner reads back natively.

    The default apparatus binds the published daemon-observed virtual-machine
    envelope, so fresh readback is independent evidence for that envelope.
    """

    manifest = manifest or stub_manifest_with_envelope(VIRTUAL_MACHINE_ENVELOPE, with_time=True)
    envelope = manifest.realization_envelope
    assert envelope is not None
    components = create_stub_components(manifest=manifest)
    return RuntimeTarget(
        name=NATIVE_READBACK_TARGET_NAME,
        manifest=manifest,
        provisioner=NativeReadbackProvisioner(envelope, InMemoryNativeDriver(envelope)),
        orchestrator=components.orchestrator,
        evaluator=components.evaluator,
        participant_runtime=components.participant_runtime,
        time_runtime=components.time_runtime,
        observation_runtime=components.observation_runtime,
    )
