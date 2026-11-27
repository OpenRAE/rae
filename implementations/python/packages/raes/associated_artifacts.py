"""SDL parents of associated-artifact manifests and the scenario reference join.

``raes_contracts.associated_artifacts`` validates manifests. The SDL owns the
rules that identify an SDL parent (ADR-121).
"""

from __future__ import annotations

from dataclasses import dataclass

from raes_contracts.contracts import AssociatedArtifactParentReferenceModel, OperationArtifactReferenceModel

from .canonical import canonical_instantiated_sdl_digest, canonical_materialized_sdl_digest, canonical_sdl_digest
from .instantiate import admit_instantiated_scenario, instantiate_scenario
from .materialization import MaterializedScenario
from .scenario import ExpandedScenario, InstantiatedScenario, Scenario


def require_instantiated_scenario_reference(
    parent: object, reference: OperationArtifactReferenceModel, *, instantiated: object | None = None
) -> None:
    """Join a trusted scenario association to its admitted instantiated content."""

    if not isinstance(parent, (Scenario, InstantiatedScenario)) or reference.contract_id != "instantiated-scenario-v1":
        raise ValueError("artifact association requires its admitted scenario reference")
    if instantiated is not None and not isinstance(instantiated, InstantiatedScenario):
        raise ValueError("artifact association requires an instantiated scenario")
    if instantiated is None:
        instantiated = parent if isinstance(parent, InstantiatedScenario) else instantiate_scenario(parent)
    admitted = admit_instantiated_scenario(instantiated)
    if reference.artifact_id != admitted.name or reference.digest != canonical_instantiated_sdl_digest(admitted).value:
        raise ValueError("scenario reference does not bind its admitted instantiated content")


def _scenario_parent_matches(reference: AssociatedArtifactParentReferenceModel, parent: object) -> bool:
    if reference.ref_kind == "scenario":
        # Generic scenario association remains the incumbent id-only contract.
        return isinstance(parent, Scenario) and parent.name == reference.ref_id

    snapshot_types = (Scenario, ExpandedScenario)
    matches = (
        isinstance(parent, snapshot_types)
        and not isinstance(parent, InstantiatedScenario)
        and parent.semantic_validated
        and parent.name == reference.ref_id
    )
    if matches:
        matches = reference.ref_version is None or parent.version == reference.ref_version
    if matches and reference.ref_digest is not None:
        matches = canonical_sdl_digest(parent).value.casefold() == reference.ref_digest.casefold()
    return matches


def _materialization_parent_matches(reference: AssociatedArtifactParentReferenceModel, parent: object) -> bool:
    return (
        isinstance(parent, MaterializedScenario)
        and parent.semantic_validated
        and parent.materialization_provenance.attestation_id == reference.ref_id
        and reference.ref_version == "raes-sdl-materialized/v1"
        and canonical_materialized_sdl_digest(parent).value == reference.ref_digest
    )


@dataclass(frozen=True)
class ScenarioArtifactParent:
    """An SDL scenario, expanded scenario or materialized scenario as a manifest parent.

    Scenario snapshots accept only semantically validated ``Scenario`` or
    ``ExpandedScenario`` authoring parents. Generic scenario association keeps
    its id-only ``Scenario`` behavior; instantiated scenarios are never
    canonical authoring snapshot parents.
    """

    parent: object

    def matches_parent_ref(self, reference: AssociatedArtifactParentReferenceModel) -> bool:
        if reference.ref_kind == "materialization-attestation":
            return _materialization_parent_matches(reference, self.parent)
        if reference.ref_kind in {"scenario", "scenario-snapshot"}:
            return _scenario_parent_matches(reference, self.parent)
        return False


__all__ = ["ScenarioArtifactParent", "require_instantiated_scenario_reference"]
