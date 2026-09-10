"""Selector-level observation admission and execution at the runtime boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.observation_demand import (
    AchievedObservationValue,
    EffectiveObservationDemand,
    ObservationBasis,
    ObservationDemandResolution,
    ObservationLifecycleDecision,
    ObservationLifecycleItem,
    ObservationLifecycleStage,
    ObservationPurpose,
    ObservationSelector,
    execute_observation_lifecycle,
    observation_selector_has_more_specific_policy,
    realization_description_report,
)
from raes_contracts.runtime_state import RuntimeSnapshot

from .observation_capabilities import (
    ObservationRuntimeCapability,
    ObservationSelectorPattern,
    resolve_observation_runtime_capability,
)
from .observation_results import (
    ObservationExecution,
    PreparedObservationExecution,
    prepare_observation_execution,
)

Plan = object
Producer = Callable[[ObservationSelector, Plan, RuntimeSnapshot], tuple[object, ...]]
Describer = Callable[[ObservationSelector, Plan, RuntimeSnapshot], AchievedObservationValue | None]
Redactor = Callable[[tuple[object, ...]], tuple[object, ...]]
IntegrityProvider = Callable[[str, tuple[object, ...]], str]
EvidenceVerifier = Callable[[ObservationSelector, AchievedObservationValue, Plan, RuntimeSnapshot], bool]


class ObservationRuntime(Protocol):
    """Backend-owned selector producers, sinks, and truthful describers."""

    @property
    def capabilities(self) -> tuple[ObservationRuntimeCapability, ...]: ...

    def collect(self, selector: ObservationSelector, plan: Plan, snapshot: RuntimeSnapshot) -> tuple[object, ...]: ...

    def describe(
        self,
        selector: ObservationSelector,
        plan: Plan,
        snapshot: RuntimeSnapshot,
    ) -> AchievedObservationValue | None: ...

    def protect(
        self,
        item: ObservationLifecycleItem,
        demand: EffectiveObservationDemand,
    ) -> ObservationLifecycleItem: ...

    def verify_evidence(
        self,
        selector: ObservationSelector,
        achieved: AchievedObservationValue,
        plan: Plan,
        snapshot: RuntimeSnapshot,
    ) -> bool: ...


class ConfiguredObservationRuntime:
    """Callback-backed production adapter with closed selector capabilities."""

    def __init__(
        self,
        *,
        capabilities: tuple[ObservationRuntimeCapability, ...],
        producers: Mapping[str, Producer] | None = None,
        describers: Mapping[str, Describer] | None = None,
        redactors: Mapping[str, Redactor] | None = None,
        integrity_providers: Mapping[str, IntegrityProvider] | None = None,
        evidence_verifier: EvidenceVerifier | None = None,
    ) -> None:
        keys = [capability.capability_id for capability in capabilities]
        if len(keys) != len(set(keys)):
            raise ValueError("observation runtime capabilities must have unique stable identities")
        self._capabilities = capabilities
        self._producers = dict(producers or {})
        self._describers = dict(describers or {})
        self._redactors = dict(redactors or {})
        self._integrity_providers = dict(integrity_providers or {})
        self._evidence_verifier = evidence_verifier
        for capability in capabilities:
            if (
                ObservationLifecycleStage.COLLECTION in capability.stages
                and capability.capability_id not in self._producers
            ):
                raise ValueError("collection capability requires a family producer")
            if capability.bases and capability.capability_id not in self._describers:
                raise ValueError("reporting-basis capability requires a family describer")
            if not capability.redaction_policies.issubset(self._redactors):
                raise ValueError("redaction capability requires trusted policy implementations")
            if not capability.integrity_policies.issubset(self._integrity_providers):
                raise ValueError("integrity capability requires trusted policy implementations")
            if capability.bases.intersection({ObservationBasis.OBSERVED, ObservationBasis.INDEPENDENTLY_VERIFIED}) and (
                evidence_verifier is None
            ):
                raise ValueError("observed reporting capability requires a trusted evidence verifier")

    @property
    def capabilities(self) -> tuple[ObservationRuntimeCapability, ...]:
        return self._capabilities

    def collect(self, selector: ObservationSelector, plan: Plan, snapshot: RuntimeSnapshot) -> tuple[object, ...]:
        capability = resolve_observation_runtime_capability(self._capabilities, selector)
        if capability is None:
            raise KeyError(selector.key)
        return self._producers[capability.capability_id](selector, plan, snapshot)

    def describe(
        self,
        selector: ObservationSelector,
        plan: Plan,
        snapshot: RuntimeSnapshot,
    ) -> AchievedObservationValue | None:
        capability = resolve_observation_runtime_capability(self._capabilities, selector)
        if capability is None:
            raise KeyError(selector.key)
        describer = self._describers.get(capability.capability_id)
        return None if describer is None else describer(selector, plan, snapshot)

    def protect(
        self,
        item: ObservationLifecycleItem,
        demand: EffectiveObservationDemand,
    ) -> ObservationLifecycleItem:
        values = item.values
        if demand.redaction not in {None, "none"}:
            values = self._redactors[demand.redaction](values)
            if not isinstance(values, tuple):
                raise ValueError("redaction policy must return a tuple")
        integrity_ref = None
        if demand.integrity not in {None, "none"}:
            integrity_ref = self._integrity_providers[demand.integrity](item.selector_key, values)
            if not isinstance(integrity_ref, str) or not integrity_ref.strip():
                raise ValueError("integrity policy must return a non-empty reference")
        return ObservationLifecycleItem(item.selector_key, values, integrity_ref)

    def verify_evidence(
        self,
        selector: ObservationSelector,
        achieved: AchievedObservationValue,
        plan: Plan,
        snapshot: RuntimeSnapshot,
    ) -> bool:
        return bool(self._evidence_verifier is not None and self._evidence_verifier(selector, achieved, plan, snapshot))


def observation_submission_diagnostic(
    plan: object,
    manifest: BackendManifest | None,
    runtime: ObservationRuntime | None,
    *,
    durable_lifecycle_available: bool,
) -> Diagnostic | None:
    """Reject required demand lacking exact executable backend support."""

    demands = tuple(getattr(plan, "observation_demands", ()))
    for demand in demands:
        conflict = _demand_conflict(demand)
        if conflict is not None:
            return conflict
        if demand.export is ObservationLifecycleDecision.REQUIRE:
            return Diagnostic(
                code="observation.export-runtime-unavailable",
                domain="runtime",
                address=demand.scope or "runtime.observation-demand",
                message="This runtime has no governed export delivery owner; export cannot be requested.",
            )
        executable_selectors = tuple(
            selector
            for selector in demand.selectors
            if not observation_selector_has_more_specific_policy(demands, demand, selector)
            and (capability := _capability_for(runtime, selector)) is not None
            and _capability_admits(demand, capability, manifest)
        )
        if (
            not durable_lifecycle_available
            and executable_selectors
            and any(decision is ObservationLifecycleDecision.REQUIRE for decision in (demand.retention, demand.export))
        ):
            return Diagnostic(
                code="observation.durable-lifecycle-owner-unavailable",
                domain="runtime",
                address=demand.scope or "runtime.observation-demand",
                message="Retention and export require a durable operation lifecycle owner.",
            )
        if not demand.required:
            continue
        for selector in demand.selectors:
            if observation_selector_has_more_specific_policy(demands, demand, selector):
                return Diagnostic(
                    code="observation.required-selector-partitioned",
                    domain="runtime",
                    address=demand.scope or "runtime.observation-demand",
                    message="Required broad selector overlaps a more-specific effective policy.",
                )
            capability = _capability_for(runtime, selector)
            if capability is None or not _capability_admits(demand, capability, manifest):
                return Diagnostic(
                    code="observation.unsupported-required-selector",
                    domain="runtime",
                    address=demand.scope or "runtime.observation-demand",
                    message=f"Backend cannot execute required observation selector '{selector.key}'.",
                )
        if demand.selectors and getattr(plan, "actionable_operations", ()):
            return Diagnostic(
                code="observation.required-execution-atomicity-unavailable",
                domain="runtime",
                address=demand.scope or "runtime.observation-demand",
                message="Required observations cannot accompany backend mutation without a compensating execution owner.",
            )
    return None


def execute_plan_observation_demand(
    plan: object,
    snapshot: RuntimeSnapshot,
    manifest: BackendManifest | None,
    runtime: ObservationRuntime | None,
    *,
    durable_lifecycle_available: bool,
    operation_id: str | None,
) -> tuple[PreparedObservationExecution | None, Diagnostic | None]:
    """Execute admitted demand after backend success and before snapshot commit."""

    if not getattr(plan, "observation_demands", ()):
        return None, None
    diagnostic = observation_submission_diagnostic(
        plan,
        manifest,
        runtime,
        durable_lifecycle_available=durable_lifecycle_available,
    )
    if diagnostic is not None:
        return None, diagnostic
    if runtime is None:
        return None, None
    resolution = _admitted_resolution(plan, manifest, runtime)
    selectors = {
        selector.key: selector
        for demand in resolution.effective
        for selector in demand.selectors
        if _capability_for(runtime, selector) is not None
    }
    supported = frozenset(selectors)
    try:
        lifecycle = execute_observation_lifecycle(
            resolution,
            producers={
                key: (lambda selector=selector: runtime.collect(selector, plan, snapshot))
                for key, selector in selectors.items()
            },
            supported=supported,
            protector=runtime.protect,
        )
        description_selectors = {
            selector.key: selector
            for demand in resolution.effective
            if demand.purpose is ObservationPurpose.REALIZATION_DESCRIPTION
            for selector in demand.selectors
            if not observation_selector_has_more_specific_policy(resolution.effective, demand, selector)
        }
        achieved = {
            key: value
            for key, selector in description_selectors.items()
            if (value := runtime.describe(selector, plan, snapshot)) is not None
        }
        description = realization_description_report(
            resolution,
            achieved,
            evidence_validator=lambda key, value: runtime.verify_evidence(
                description_selectors[key], value, plan, snapshot
            ),
            protector=lambda key, value, demand: _protect_description(runtime, key, value, demand),
        )
        if manifest is None:
            raise ValueError("observation execution requires a backend manifest")
        execution = prepare_observation_execution(
            lifecycle,
            description,
            manifest,
            operation_id=operation_id,
        )
    except (KeyError, TypeError, ValueError):
        return None, Diagnostic(
            code="observation.runtime-contract-invalid",
            domain="runtime",
            address="runtime.observation-demand",
            message="Observation runtime did not satisfy the admitted selector contract.",
        )
    except Exception as exc:
        return None, Diagnostic(
            code="observation.runtime-adapter-failed",
            domain="runtime",
            address="runtime.observation-demand",
            message=f"Observation runtime adapter did not complete ({type(exc).__name__}).",
        )
    return execution, None


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
            address=demand.scope or "runtime.observation-demand",
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
            address=demand.scope or "runtime.observation-demand",
            message="Operational-only inputs cannot be retained or exported as study data.",
        )
    return None


def _capability_for(
    runtime: ObservationRuntime | None,
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
    observation = None if manifest is None else manifest.observation
    required_stages = {
        stage
        for stage, decision in (
            (ObservationLifecycleStage.COLLECTION, demand.collection),
            (ObservationLifecycleStage.RETENTION, demand.retention),
            (ObservationLifecycleStage.EXPORT, demand.export),
        )
        if decision is ObservationLifecycleDecision.REQUIRE
    }
    if demand.purpose is ObservationPurpose.REALIZATION_DESCRIPTION:
        required_stages.discard(ObservationLifecycleStage.COLLECTION)
    basis_ok = demand.purpose is not ObservationPurpose.REALIZATION_DESCRIPTION or any(
        _basis_satisfies(achieved, demand.basis) for achieved in capability.bases
    )
    if observation is None:
        return bool(
            manifest is not None
            and demand.purpose is ObservationPurpose.REALIZATION_DESCRIPTION
            and demand.basis is ObservationBasis.BACKEND_SELECTED
            and capability.bases == frozenset({ObservationBasis.BACKEND_SELECTED})
            and required_stages.issubset(capability.stages)
            and (demand.redaction in {None, "none"} or demand.redaction in capability.redaction_policies)
            and (demand.integrity in {None, "none"} or demand.integrity in capability.integrity_policies)
        )
    return bool(
        capability.capture_kind in observation.supported_capture_kinds
        and capability.channel_kind in observation.supported_channel_kinds
        and required_stages.issubset(capability.stages)
        and basis_ok
        and (
            demand.redaction is None
            or demand.redaction == "none"
            or observation.supports_redaction
            and demand.redaction in capability.redaction_policies
        )
        and (
            demand.integrity is None
            or demand.integrity == "none"
            or demand.integrity in observation.supported_sealing_modes
            and demand.integrity in capability.integrity_policies
        )
    )


def _basis_satisfies(achieved: ObservationBasis, requested: ObservationBasis) -> bool:
    strength = {
        ObservationBasis.BACKEND_SELECTED: 0,
        ObservationBasis.OBSERVED: 1,
        ObservationBasis.INDEPENDENTLY_VERIFIED: 2,
    }
    return achieved in strength and requested in strength and strength[achieved] >= strength[requested]


def _protect_description(
    runtime: ObservationRuntime,
    selector_key: str,
    achieved: AchievedObservationValue,
    demand: EffectiveObservationDemand,
) -> AchievedObservationValue:
    protected = runtime.protect(ObservationLifecycleItem(selector_key, (achieved.value,)), demand)
    if len(protected.values) != 1:
        raise ValueError("description protection must preserve one selected value")
    return AchievedObservationValue(
        protected.values[0],
        achieved.basis,
        achieved.evidence_ref,
        protected.integrity_ref,
    )


def _admitted_resolution(
    plan: object,
    manifest: BackendManifest | None,
    runtime: ObservationRuntime,
) -> ObservationDemandResolution:
    effective = []
    for demand in plan.observation_demands:
        selectors = tuple(
            selector
            for selector in demand.selectors
            if (capability := _capability_for(runtime, selector)) is not None
            and _capability_admits(demand, capability, manifest)
        )
        if selectors:
            effective.append(demand.model_copy(update={"selectors": selectors}))
        elif not demand.selectors:
            effective.append(demand)
    return ObservationDemandResolution(tuple(effective))


__all__ = [
    "ConfiguredObservationRuntime",
    "ObservationExecution",
    "ObservationRuntime",
    "ObservationRuntimeCapability",
    "ObservationSelectorPattern",
    "execute_plan_observation_demand",
    "observation_submission_diagnostic",
]
