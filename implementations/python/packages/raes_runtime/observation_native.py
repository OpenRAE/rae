"""Truthful descriptions of already-selected backend apparatus; no probes."""

from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.observation_demand import AchievedObservationValue, ObservationBasis, ObservationLifecycleStage
from raes_contracts.realization_envelope import RealizationConcern
from raes_contracts.realization_observation_demand import observation_field_selector_matches

from .observation_execution import (
    ConfiguredObservationRuntime,
    ObservationRuntimeCapability,
    ObservationSelectorPattern,
)


def backend_selection_observation_runtime(manifest: BackendManifest) -> ConfiguredObservationRuntime:
    """Expose only apparatus selections bound to realized inventory."""

    def describe(selector, plan, snapshot):
        envelope = manifest.realization_envelope
        if (
            envelope is None
            or plan.realization_envelope != envelope.identity
            or snapshot.realization_envelope != envelope.identity
        ):
            return None
        mechanism = next(
            (item.mechanism for item in envelope.concerns if item.concern is RealizationConcern.COMPUTE_SUBSTRATE), None
        )
        if mechanism is None:
            return None
        values = {
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
        return AchievedObservationValue(values, ObservationBasis.BACKEND_SELECTED) if values else None

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
        describers={"backend-selected-substrate/v1": describe},
    )
