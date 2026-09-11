"""Admission of normalized observation demand against runtime capability."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.observation_demand import (
    EffectiveObservationDemand,
    ObservationBasis,
    ObservationDemandResolution,
    ObservationLifecycleDecision,
    ObservationLifecycleStage,
    ObservationPurpose,
    ObservationSelector,
    observation_selector_has_more_specific_policy,
)

from .observation_capabilities import ObservationRuntimeCapability, resolve_observation_runtime_capability

if TYPE_CHECKING:
    from .observation_execution import ObservationRuntime

_OBSERVATION_ADDRESS = "runtime.observation-demand"


class _ObservationRuntimeCapabilities(Protocol):
    @property
    def capabilities(self) -> tuple[ObservationRuntimeCapability, ...]: ...


def observation_submission_diagnostic(
    plan: object,
    manifest: BackendManifest | None,
    runtime: ObservationRuntime | None,
    *,
    durable_lifecycle_available: bool,
) -> Diagnostic | None:
    """Reject required demand lacking exact executable backend support."""

    demands = tuple(getattr(plan, "observation_demands", ()))
    return next(
        (
            diagnostic
            for demand in demands
            if (
                diagnostic := _demand_submission_diagnostic(
                    demand,
                    demands,
                    plan=plan,
                    manifest=manifest,
                    runtime=runtime,
                    durable_lifecycle_available=durable_lifecycle_available,
                )
            )
            is not None
        ),
        None,
    )


def _demand_submission_diagnostic(
    demand: EffectiveObservationDemand,
    demands: tuple[EffectiveObservationDemand, ...],
    *,
    plan: object,
    manifest: BackendManifest | None,
    runtime: ObservationRuntime | None,
    durable_lifecycle_available: bool,
) -> Diagnostic | None:
    diagnostic = _demand_conflict(demand) or _export_unavailable_diagnostic(demand)
    executable_selectors = _executable_selectors(demand, demands, manifest, runtime)
    if diagnostic is None:
        diagnostic = _durable_lifecycle_diagnostic(demand, executable_selectors, durable_lifecycle_available)
    if diagnostic is None and demand.required:
        diagnostic = _required_selector_diagnostic(demand, demands, manifest, runtime)
    if diagnostic is None and demand.required and demand.selectors and getattr(plan, "actionable_operations", ()):
        diagnostic = _atomicity_unavailable_diagnostic(demand)
    return diagnostic


def _export_unavailable_diagnostic(demand: EffectiveObservationDemand) -> Diagnostic | None:
    if demand.export is not ObservationLifecycleDecision.REQUIRE:
        return None
    return Diagnostic(
        code="observation.export-runtime-unavailable",
        domain="runtime",
        address=demand.scope or _OBSERVATION_ADDRESS,
        message="This runtime has no governed export delivery owner; export cannot be requested.",
    )


def _executable_selectors(
    demand: EffectiveObservationDemand,
    demands: tuple[EffectiveObservationDemand, ...],
    manifest: BackendManifest | None,
    runtime: ObservationRuntime | None,
) -> tuple[ObservationSelector, ...]:
    return tuple(
        selector
        for selector in demand.selectors
        if not observation_selector_has_more_specific_policy(demands, demand, selector)
        and (capability := capability_for_observation_selector(runtime, selector)) is not None
        and _capability_admits(demand, capability, manifest)
    )


def _durable_lifecycle_diagnostic(
    demand: EffectiveObservationDemand,
    executable_selectors: tuple[ObservationSelector, ...],
    durable_lifecycle_available: bool,
) -> Diagnostic | None:
    later_stage_required = ObservationLifecycleDecision.REQUIRE in (demand.retention, demand.export)
    if durable_lifecycle_available or not executable_selectors or not later_stage_required:
        return None
    return Diagnostic(
        code="observation.durable-lifecycle-owner-unavailable",
        domain="runtime",
        address=demand.scope or _OBSERVATION_ADDRESS,
        message="Retention and export require a durable operation lifecycle owner.",
    )


def _required_selector_diagnostic(
    demand: EffectiveObservationDemand,
    demands: tuple[EffectiveObservationDemand, ...],
    manifest: BackendManifest | None,
    runtime: ObservationRuntime | None,
) -> Diagnostic | None:
    for selector in demand.selectors:
        if observation_selector_has_more_specific_policy(demands, demand, selector):
            return Diagnostic(
                code="observation.required-selector-partitioned",
                domain="runtime",
                address=demand.scope or _OBSERVATION_ADDRESS,
                message="Required broad selector overlaps a more-specific effective policy.",
            )
        capability = capability_for_observation_selector(runtime, selector)
        if capability is None or not _capability_admits(demand, capability, manifest):
            return Diagnostic(
                code="observation.unsupported-required-selector",
                domain="runtime",
                address=demand.scope or _OBSERVATION_ADDRESS,
                message=f"Backend cannot execute required observation selector '{selector.key}'.",
            )
    return None


def _atomicity_unavailable_diagnostic(demand: EffectiveObservationDemand) -> Diagnostic:
    return Diagnostic(
        code="observation.required-execution-atomicity-unavailable",
        domain="runtime",
        address=demand.scope or _OBSERVATION_ADDRESS,
        message="Required observations cannot accompany backend mutation without a compensating execution owner.",
    )


def _demand_conflict(demand: EffectiveObservationDemand) -> Diagnostic | None:
    decisions = {
        ObservationLifecycleStage.COLLECTION: demand.collection,
        ObservationLifecycleStage.RETENTION: demand.retention,
        ObservationLifecycleStage.EXPORT: demand.export,
    }
    conflict = next(
        (
            stage
            for stage, decision in decisions.items()
            if decision is ObservationLifecycleDecision.REQUIRE and stage in demand.prohibited_stages
        ),
        None,
    )
    if conflict is not None:
        return Diagnostic(
            code="observation.required-prohibited-conflict",
            domain="runtime",
            address=demand.scope or _OBSERVATION_ADDRESS,
            message=f"Required observation stage '{conflict.value}' is prohibited at this scope.",
        )
    if demand.purpose is ObservationPurpose.OPERATIONAL and any(
        decision is ObservationLifecycleDecision.REQUIRE
        for stage, decision in decisions.items()
        if stage is not ObservationLifecycleStage.COLLECTION
    ):
        return Diagnostic(
            code="observation.operational-persistence-conflict",
            domain="runtime",
            address=demand.scope or _OBSERVATION_ADDRESS,
            message="Operational-only inputs cannot be retained or exported as study data.",
        )
    return None


def capability_for_observation_selector(
    runtime: _ObservationRuntimeCapabilities | None,
    selector: ObservationSelector,
) -> ObservationRuntimeCapability | None:
    if runtime is None:
        return None
    return resolve_observation_runtime_capability(runtime.capabilities, selector)


def _capability_admits(
    demand: EffectiveObservationDemand,
    capability: ObservationRuntimeCapability,
    manifest: BackendManifest | None,
) -> bool:
    required_stages = _required_lifecycle_stages(demand)
    if demand.purpose is ObservationPurpose.REALIZATION_DESCRIPTION:
        required_stages.discard(ObservationLifecycleStage.COLLECTION)
    observation = None if manifest is None else manifest.observation
    if observation is None:
        return _manifestless_description_admitted(demand, capability, manifest, required_stages)
    return bool(
        capability.capture_kind in observation.supported_capture_kinds
        and capability.channel_kind in observation.supported_channel_kinds
        and required_stages.issubset(capability.stages)
        and _reporting_basis_admitted(demand, capability)
        and _redaction_admitted(demand, capability, observation.supports_redaction)
        and _integrity_admitted(demand, capability, observation.supported_sealing_modes)
    )


def _required_lifecycle_stages(demand: EffectiveObservationDemand) -> set[ObservationLifecycleStage]:
    return {
        stage
        for stage, decision in (
            (ObservationLifecycleStage.COLLECTION, demand.collection),
            (ObservationLifecycleStage.RETENTION, demand.retention),
            (ObservationLifecycleStage.EXPORT, demand.export),
        )
        if decision is ObservationLifecycleDecision.REQUIRE
    }


def _manifestless_description_admitted(
    demand: EffectiveObservationDemand,
    capability: ObservationRuntimeCapability,
    manifest: BackendManifest | None,
    required_stages: set[ObservationLifecycleStage],
) -> bool:
    return bool(
        manifest is not None
        and demand.purpose is ObservationPurpose.REALIZATION_DESCRIPTION
        and demand.basis is ObservationBasis.BACKEND_SELECTED
        and capability.bases == frozenset({ObservationBasis.BACKEND_SELECTED})
        and required_stages.issubset(capability.stages)
        and (demand.redaction in {None, "none"} or demand.redaction in capability.redaction_policies)
        and (demand.integrity in {None, "none"} or demand.integrity in capability.integrity_policies)
    )


def _reporting_basis_admitted(
    demand: EffectiveObservationDemand,
    capability: ObservationRuntimeCapability,
) -> bool:
    return demand.purpose is not ObservationPurpose.REALIZATION_DESCRIPTION or any(
        _basis_satisfies(achieved, demand.basis) for achieved in capability.bases
    )


def _redaction_admitted(
    demand: EffectiveObservationDemand,
    capability: ObservationRuntimeCapability,
    supports_redaction: bool,
) -> bool:
    no_redaction = demand.redaction in {None, "none"}
    return bool(no_redaction or supports_redaction and demand.redaction in capability.redaction_policies)


def _integrity_admitted(
    demand: EffectiveObservationDemand,
    capability: ObservationRuntimeCapability,
    supported_sealing_modes: frozenset[str],
) -> bool:
    no_integrity = demand.integrity in {None, "none"}
    return bool(
        no_integrity
        or demand.integrity in supported_sealing_modes
        and demand.integrity in capability.integrity_policies
    )


def _basis_satisfies(achieved: ObservationBasis, requested: ObservationBasis) -> bool:
    strength = {
        ObservationBasis.BACKEND_SELECTED: 0,
        ObservationBasis.OBSERVED: 1,
        ObservationBasis.INDEPENDENTLY_VERIFIED: 2,
    }
    return achieved in strength and requested in strength and strength[achieved] >= strength[requested]


def admitted_observation_resolution(
    plan: object,
    manifest: BackendManifest | None,
    runtime: ObservationRuntime,
) -> ObservationDemandResolution:
    effective = []
    for demand in plan.observation_demands:
        selectors = tuple(
            selector
            for selector in demand.selectors
            if (capability := capability_for_observation_selector(runtime, selector)) is not None
            and _capability_admits(demand, capability, manifest)
        )
        if selectors:
            effective.append(demand.model_copy(update={"selectors": selectors}))
        elif not demand.selectors:
            effective.append(demand)
    return ObservationDemandResolution(tuple(effective))


__all__ = [
    "admitted_observation_resolution",
    "capability_for_observation_selector",
    "observation_submission_diagnostic",
]
