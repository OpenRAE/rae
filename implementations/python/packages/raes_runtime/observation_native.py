"""Truthful descriptions of already-selected backend apparatus; no probes."""

from functools import partial

from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.observation_demand import (
    AchievedObservationValue,
    ObservationBasis,
    ObservationLifecycleStage,
    ObservationSelector,
)
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel, RealizationConcern
from raes_contracts.realization_observation_demand import observation_field_selector_matches
from raes_contracts.runtime_state import RuntimeSnapshot

from .observation_execution import (
    ConfiguredObservationRuntime,
    ObservationRuntimeCapability,
    ObservationSelectorPattern,
)


def backend_selection_observation_runtime(manifest: BackendManifest) -> ConfiguredObservationRuntime:
    """Expose only apparatus selections bound to realized inventory."""

    return ConfiguredObservationRuntime(
        capabilities=(
            ObservationRuntimeCapability(
                capability_id="backend-selected-substrate/v1",
                selector_pattern=ObservationSelectorPattern(
                    data_kind="field",
                    names=frozenset({"compute-substrate"}),
                    semantic_scope_prefix="/nodes",
                    component_ref_prefixes=("provision.node",),
                ),
                capture_kind="observation",
                channel_kind="runtime-snapshot",
                stages=frozenset({ObservationLifecycleStage.RETENTION}),
                bases=frozenset({ObservationBasis.BACKEND_SELECTED}),
            ),
        ),
        describers={"backend-selected-substrate/v1": partial(_describe_backend_selection, manifest)},
    )


def _describe_backend_selection(
    manifest: BackendManifest,
    selector: ObservationSelector,
    plan: ProvisioningPlan,
    snapshot: RuntimeSnapshot,
) -> AchievedObservationValue | None:
    envelope = _bound_realization_envelope(manifest, plan, snapshot)
    mechanism = None if envelope is None else _compute_substrate_mechanism(envelope)
    if mechanism is None:
        return None
    values = _selected_substrate_values(selector, plan, snapshot, mechanism)
    return AchievedObservationValue(values, ObservationBasis.BACKEND_SELECTED) if values else None


def _bound_realization_envelope(
    manifest: BackendManifest,
    plan: ProvisioningPlan,
    snapshot: RuntimeSnapshot,
) -> BackendRealizationEnvelopeModel | None:
    envelope = manifest.realization_envelope
    if envelope is None or plan.realization_envelope != envelope.identity:
        return None
    return envelope if snapshot.realization_envelope == envelope.identity else None


def _compute_substrate_mechanism(envelope: BackendRealizationEnvelopeModel) -> str | None:
    return next(
        (item.mechanism for item in envelope.concerns if item.concern is RealizationConcern.COMPUTE_SUBSTRATE),
        None,
    )


def _selected_substrate_values(
    selector: ObservationSelector,
    plan: ProvisioningPlan,
    snapshot: RuntimeSnapshot,
    mechanism: str,
) -> dict[str, str]:
    return {
        item.address: mechanism
        for item in plan.realization_constraints
        if item.concern == "compute-substrate"
        and item.address in snapshot.entries
        and item.governing_scope is not None
        and observation_field_selector_matches(
            selector,
            semantic_scope=item.governing_scope.removeprefix("#"),
            address=item.address,
            names={"compute-substrate"},
        )
    }
