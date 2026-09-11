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
    ObservationLifecycleItem,
    ObservationLifecycleStage,
    ObservationPurpose,
    ObservationSelector,
    execute_observation_lifecycle,
    observation_selector_has_more_specific_policy,
    realization_description_report,
)
from raes_contracts.runtime_state import RuntimeSnapshot

from .observation_admission import (
    admitted_observation_resolution as _admitted_resolution,
)
from .observation_admission import (
    capability_for_observation_selector as _capability_for,
)
from .observation_admission import (
    observation_submission_diagnostic as observation_submission_diagnostic,
)
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
_OBSERVATION_ADDRESS = "runtime.observation-demand"


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
        _require_unique_capability_ids(capabilities)
        self._capabilities = capabilities
        self._producers = dict(producers or {})
        self._describers = dict(describers or {})
        self._redactors = dict(redactors or {})
        self._integrity_providers = dict(integrity_providers or {})
        self._evidence_verifier = evidence_verifier
        for capability in capabilities:
            _validate_capability_callbacks(
                capability,
                producers=self._producers,
                describers=self._describers,
                redactors=self._redactors,
                integrity_providers=self._integrity_providers,
                evidence_verifier=evidence_verifier,
            )

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


def _require_unique_capability_ids(capabilities: tuple[ObservationRuntimeCapability, ...]) -> None:
    keys = [capability.capability_id for capability in capabilities]
    if len(keys) != len(set(keys)):
        raise ValueError("observation runtime capabilities must have unique stable identities")


def _validate_capability_callbacks(
    capability: ObservationRuntimeCapability,
    *,
    producers: Mapping[str, Producer],
    describers: Mapping[str, Describer],
    redactors: Mapping[str, Redactor],
    integrity_providers: Mapping[str, IntegrityProvider],
    evidence_verifier: EvidenceVerifier | None,
) -> None:
    capability_id = capability.capability_id
    if ObservationLifecycleStage.COLLECTION in capability.stages and capability_id not in producers:
        raise ValueError("collection capability requires a family producer")
    if capability.bases and capability_id not in describers:
        raise ValueError("reporting-basis capability requires a family describer")
    if not capability.redaction_policies.issubset(redactors):
        raise ValueError("redaction capability requires trusted policy implementations")
    if not capability.integrity_policies.issubset(integrity_providers):
        raise ValueError("integrity capability requires trusted policy implementations")
    evidence_bases = {ObservationBasis.OBSERVED, ObservationBasis.INDEPENDENTLY_VERIFIED}
    if capability.bases.intersection(evidence_bases) and evidence_verifier is None:
        raise ValueError("observed reporting capability requires a trusted evidence verifier")


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
    if diagnostic is not None or runtime is None:
        return None, diagnostic
    return _execute_admitted_plan_observation(plan, snapshot, manifest, runtime, operation_id)


def _execute_admitted_plan_observation(
    plan: object,
    snapshot: RuntimeSnapshot,
    manifest: BackendManifest | None,
    runtime: ObservationRuntime,
    operation_id: str | None,
) -> tuple[PreparedObservationExecution | None, Diagnostic | None]:
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
            address=_OBSERVATION_ADDRESS,
            message="Observation runtime did not satisfy the admitted selector contract.",
        )
    except Exception as exc:
        return None, Diagnostic(
            code="observation.runtime-adapter-failed",
            domain="runtime",
            address=_OBSERVATION_ADDRESS,
            message=f"Observation runtime adapter did not complete ({type(exc).__name__}).",
        )
    return execution, None


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


__all__ = [
    "ConfiguredObservationRuntime",
    "ObservationExecution",
    "ObservationRuntime",
    "ObservationRuntimeCapability",
    "ObservationSelectorPattern",
    "execute_plan_observation_demand",
    "observation_submission_diagnostic",
]
