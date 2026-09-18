"""Selected-scenario and mixed-composition admission for trial compilation."""

from __future__ import annotations

from dataclasses import dataclass

from raes import (
    InstantiatedScenario,
    canonical_instantiated_sdl_digest,
    select_scenario_family,
)
from raes.realization_envelope import member
from raes_contracts.admitted_trial_plan_ingress import revalidate_admitted_trial_plan
from raes_contracts.contracts import (
    AdmittedMixedCompositionBindingModel,
    BackendManifestV2Model,
    ParticipantImplementationManifestModel,
    TrialCoordinateModel,
)
from raes_contracts.contracts.mixed_composition import MixedParticipantCompositionProfileModel
from raes_contracts.contracts.mixed_composition_resolution import (
    MixedCompositionResolutionContext,
    resolve_mixed_composition_profiles,
)
from raes_contracts.experiment_bindings import (
    ApparatusManifest,
    ApparatusManifestKey,
    ParticipantManifestKey,
)

from .apparatus import (
    apparatus_manifest_key,
    validate_composition_components,
    validate_selected_participant_manifests,
)
from .models import CompilationFailure, TrialCompilationRequest
from .policies import CoordinateSelections
from .profiles import realization_assignment_key

_ENTRIES_ADDRESS = "/entries/"


@dataclass(frozen=True)
class MixedCompositionAuthority:
    """Exact authority admitted across every reachable mixed profile."""

    apparatus_manifests_by_root: dict[str, dict[ApparatusManifestKey, ApparatusManifest]]
    participant_manifests: dict[ParticipantManifestKey, ParticipantImplementationManifestModel]
    backend_manifests_by_root: dict[str, tuple[BackendManifestV2Model, ...]]


def _fail(code: str, address: str, message: str) -> CompilationFailure:
    return CompilationFailure(code, address, message)


def validate_selected_scenario(
    request: TrialCompilationRequest,
    row: CoordinateSelections,
    coordinate: TrialCoordinateModel,
) -> InstantiatedScenario:
    """Reconstruct and admit the complete scenario selected for one coordinate."""

    outcomes = {selection.point_id: selection.outcome for selection in row.selections}
    try:
        selected = select_scenario_family(request.family, outcomes)
    except (TypeError, ValueError) as exc:
        raise _fail(
            "selected-scenario-rejected",
            _ENTRIES_ADDRESS + (coordinate.replicate_id or "coordinate"),
            "the complete selection failed SDL-owned whole-scenario admission",
        ) from exc
    if request.realization_assignments.get(realization_assignment_key(coordinate)) is None:
        envelope_result = member(selected, request.realization_envelope.expression)
        if not envelope_result.holds:
            raise _fail(
                "realization-envelope-membership-rejected",
                _ENTRIES_ADDRESS + (coordinate.replicate_id or "coordinate"),
                "the selected scenario is outside the admitted realization envelope",
            )
    return selected


def _validate_mixed_resources(
    request: TrialCompilationRequest,
    context: MixedCompositionResolutionContext,
    profile_id: str,
) -> None:
    required = context.resource_refs.get(profile_id)
    if required is None:
        raise _fail(
            "composition-resource-coverage-unresolved",
            "/realization_assignments",
            "composition cleanup and isolation resource coverage is unresolved",
        )
    covered = {
        resource
        for boundary in request.execution_authority.cleanup.resource_boundaries.values()
        for resource in boundary.resource_refs
    }
    if not required.issubset(covered):
        raise _fail(
            "composition-resource-coverage-missing",
            "/execution_authority/cleanup",
            "composition cleanup omits a resource reachable in an admitted phase",
        )


def _profile_work(profile: MixedParticipantCompositionProfileModel) -> int:
    return (
        len(profile.components)
        + len(profile.allocations)
        + len(profile.edges)
        + len(profile.phases)
        + len(profile.transitions)
        + len(profile.nested_profile_refs)
        + sum(len(allocation.feature_requirements) for allocation in profile.allocations.values())
        + sum(len(edge.evidence_bindings) for edge in profile.edges.values())
        + sum(len(phase.evidence_bindings) for phase in profile.phases.values())
        + sum(len(transition.evidence_bindings) for transition in profile.transitions.values())
    )


def _resolve_profile_closure(
    request: TrialCompilationRequest,
    profile: MixedParticipantCompositionProfileModel,
) -> tuple[MixedCompositionResolutionContext, tuple[MixedParticipantCompositionProfileModel, ...]]:
    context = request.mixed_profile_contexts.get(profile.profile_id)
    if context is None:
        raise _fail(
            "composition-context-missing",
            "/realization_assignments",
            "composition profile trusted resolution context is missing",
        )
    try:
        profiles = resolve_mixed_composition_profiles(
            profile,
            context,
            limits=request.mixed_composition_limits,
            require_trial_admission=True,
        )
    except ValueError as exc:
        raise _fail(
            "composition-context-rejected",
            "/realization_assignments",
            "composition profile failed trusted contextual admission",
        ) from exc
    return context, profiles


def _validate_profile_apparatus(
    request: TrialCompilationRequest,
    profile: MixedParticipantCompositionProfileModel,
) -> dict[str, ApparatusManifest]:
    return validate_composition_components(
        profile.components,
        request.apparatus_manifests,
        request.mixed_realization_envelopes,
        intent=request.experiment.apparatus_intent,
    )


def validate_mixed_authority(request: TrialCompilationRequest) -> MixedCompositionAuthority:
    """Admit only exact participant and reachable component authority."""

    participant_manifests = validate_selected_participant_manifests(request)
    apparatus_manifests_by_root: dict[str, dict[ApparatusManifestKey, ApparatusManifest]] = {}
    admitted_profiles: dict[str, MixedParticipantCompositionProfileModel] = {}
    backends_by_root: dict[str, tuple[BackendManifestV2Model, ...]] = {}
    closures: list[
        tuple[
            str,
            MixedCompositionResolutionContext,
            tuple[MixedParticipantCompositionProfileModel, ...],
        ]
    ] = []
    for root_id, root in sorted(request.mixed_profiles.items()):
        context, profiles = _resolve_profile_closure(request, root)
        for profile in profiles:
            prior = admitted_profiles.get(profile.profile_id)
            if prior is not None and prior != profile:
                raise _fail(
                    "composition-profile-identity-conflict",
                    "/realization_assignments",
                    "one composition profile identity resolves to conflicting payloads",
                )
            admitted_profiles[profile.profile_id] = profile
        closures.append((root_id, context, profiles))
    if len(admitted_profiles) > request.limits.max_mixed_profiles:
        raise _fail(
            "mixed-profile-limit-exceeded",
            "/realization_assignments",
            "reachable mixed composition profiles exceed the compilation limit",
        )
    if sum(_profile_work(profile) for profile in admitted_profiles.values()) > request.limits.max_mixed_context_work:
        raise _fail(
            "mixed-context-work-limit-exceeded",
            "/realization_assignments",
            "reachable mixed composition contextual work exceeds the compilation limit",
        )
    for root_id, context, profiles in closures:
        root_manifests: dict[ApparatusManifestKey, ApparatusManifest] = {}
        root_backends: list[BackendManifestV2Model] = []
        for profile in profiles:
            selected = _validate_profile_apparatus(request, profile)
            _validate_mixed_resources(request, context, profile.profile_id)
            for component_id, manifest in sorted(selected.items()):
                key = apparatus_manifest_key(profile.components[component_id].manifest_ref)
                root_manifests[key] = manifest
                if isinstance(manifest, BackendManifestV2Model):
                    root_backends.append(manifest)
        apparatus_manifests_by_root[root_id] = root_manifests
        backends_by_root[root_id] = tuple(root_backends)
    return MixedCompositionAuthority(
        apparatus_manifests_by_root=apparatus_manifests_by_root,
        participant_manifests=participant_manifests,
        backend_manifests_by_root=backends_by_root,
    )


def _validate_mixed_source(
    request: TrialCompilationRequest,
    binding: AdmittedMixedCompositionBindingModel,
    selected: InstantiatedScenario,
) -> None:
    source_ref = binding.source_trial
    if source_ref is None:
        return
    source = request.source_plans.get(source_ref.plan_id)
    if source is None:
        raise _fail(
            "composition-source-plan-unresolved",
            "/realization_assignments",
            "linked realization source plan is unresolved",
        )
    try:
        admitted = revalidate_admitted_trial_plan(source)
    except ValueError as exc:
        raise _fail(
            "composition-source-plan-invalid",
            "/realization_assignments",
            "linked realization source plan failed closed reconstruction",
        ) from exc
    entry = admitted.entries.get(source_ref.plan_entry_id)
    if (
        admitted.plan_id != source_ref.plan_id
        or admitted.plan_digest != source_ref.plan_digest
        or entry is None
        or entry.entry_digest != source_ref.entry_digest
        or entry.run_id != source_ref.run_id
    ):
        raise _fail(
            "composition-source-trial-mismatch",
            "/realization_assignments",
            "linked realization source tuple does not match the sealed source plan",
        )
    if (
        admitted.input_refs.authoring_input_ref != request.input_refs.authoring_input_ref
        or admitted.input_refs.task_ref != request.input_refs.task_ref
        or admitted.input_refs.task_digest != request.input_refs.task_digest
        or admitted.input_refs.scenario_family_ref != request.input_refs.scenario_family_ref
    ):
        raise _fail(
            "composition-source-input-mismatch",
            "/realization_assignments",
            "linked realization source does not bind the same authoring, task, and scenario-family inputs",
        )
    source_outcomes = {selection.variation_point_id: selection.outcome for selection in entry.selections}
    try:
        source_selected = select_scenario_family(request.family, source_outcomes)
    except (TypeError, ValueError) as exc:
        raise _fail(
            "composition-source-selection-invalid",
            "/realization_assignments",
            "linked realization source selection failed scenario admission",
        ) from exc
    if canonical_instantiated_sdl_digest(source_selected) != canonical_instantiated_sdl_digest(selected):
        raise _fail(
            "composition-source-selection-mismatch",
            "/realization_assignments",
            "linked realization source does not bind the same admitted scenario selection",
        )


def validate_mixed_realization(
    request: TrialCompilationRequest,
    binding: AdmittedMixedCompositionBindingModel,
    selected: InstantiatedScenario,
) -> None:
    """Validate one coordinate's exact mixed-composition realization."""

    profile = request.mixed_profiles[binding.profile_ref.ref_id]
    selected_digest = canonical_instantiated_sdl_digest(selected).value
    if profile.scenario_snapshot_ref.ref_digest != selected_digest:
        raise _fail(
            "composition-scenario-snapshot-mismatch",
            "/realization_assignments",
            "composition profile scenario snapshot does not match the selected scenario",
        )
    context, profiles = _resolve_profile_closure(request, profile)
    for reachable in profiles:
        if reachable.scenario_snapshot_ref.ref_digest != selected_digest:
            raise _fail(
                "composition-scenario-snapshot-mismatch",
                "/realization_assignments",
                "a reachable composition profile scenario snapshot does not match the selected scenario",
            )
        _validate_profile_apparatus(request, reachable)
        _validate_mixed_resources(request, context, reachable.profile_id)
    _validate_mixed_source(request, binding, selected)


__all__ = ["validate_mixed_authority", "validate_mixed_realization", "validate_selected_scenario"]
