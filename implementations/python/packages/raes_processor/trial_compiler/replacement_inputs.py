"""Bounded coordinate and identity projection for the replacement compiler profile."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from raes_contracts.contracts import AdmittedTrialEntryModel, AdmittedTrialPlanInputRefsModel, TrialCoordinateModel
from raes_contracts.contracts.trial_coordinate_order import replicate_ordinal
from raes_contracts.contracts.trial_replacement import TrialReplacementOriginModel

from .inputs import canonical_input_refs, coordinate_replicate_id
from .models import TrialCompilationRequest
from .profiles import derive_identity, realization_assignment_key


def replacement_coordinate(
    coordinates: list[TrialCoordinateModel],
    index: int,
    maximum_replacements: int,
    ordinal: int,
) -> TrialCoordinateModel:
    """Use the same reserved replicate interval for compilation and source checks."""
    original = coordinates[index]
    maximum = max(replicate_ordinal(item.replicate_id) for item in coordinates)
    return TrialCoordinateModel(
        condition_id=original.condition_id,
        block_id=original.block_id,
        replicate_id=coordinate_replicate_id(maximum + index * maximum_replacements + ordinal),
    )


@dataclass(frozen=True)
class ReplacementCompilationContext:
    origin: TrialReplacementOriginModel
    coordinate_index: int

    def plan_id(self) -> str:
        # Slot identities do not depend on delivery, changed evidence, completion
        # order, or a caller's idempotency key. One slot has one successor id.
        return derive_identity(
            "replacement-plan",
            {
                "profile": "trial-compiler-replacement-v1",
                "root_plan_id": self.origin.root_plan_id,
                "root_plan_digest": self.origin.root_plan_digest,
                "root_entry_id": self.origin.root_entry_id,
                "ordinal": self.origin.ordinal,
            },
        )

    def prepare(
        self,
        request: TrialCompilationRequest,
        coordinates: list[TrialCoordinateModel],
    ) -> tuple[TrialCompilationRequest, list[TrialCoordinateModel]]:
        original = coordinates[self.coordinate_index]
        # Reserve a disjoint numerical interval per original slot. All original
        # coordinates/selection rows still participate in deterministic selection;
        # only this slot's new entry is emitted. No old plan is re-sealed.
        policy = request.experiment.run_plan.replacement_policy
        assert policy is not None
        coordinate = replacement_coordinate(
            coordinates,
            self.coordinate_index,
            policy.max_replacements,
            self.origin.ordinal,
        )
        updated = list(coordinates)
        updated[self.coordinate_index] = coordinate
        assignments = dict(request.realization_assignments)
        if assignments:
            assignments[realization_assignment_key(coordinate)] = assignments.pop(realization_assignment_key(original))
        return replace(request, realization_assignments=assignments), updated

    @staticmethod
    def input_refs(
        request: TrialCompilationRequest, entries: Mapping[str, AdmittedTrialEntryModel]
    ) -> AdmittedTrialPlanInputRefsModel:
        refs = canonical_input_refs(request)
        if not request.realization_assignments:
            return refs
        used = {entry.apparatus.profile_ref.ref_id for entry in entries.values()}
        return refs.model_copy(
            update={
                "mixed_composition_profile_refs": [
                    ref for ref in refs.mixed_composition_profile_refs if ref.ref_id in used
                ]
            }
        )
