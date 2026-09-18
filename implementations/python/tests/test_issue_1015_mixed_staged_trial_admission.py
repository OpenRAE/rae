"""Mixed and staged participant trial admission (issue #1015)."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
import raes_processor.trial_compiler.compiler as trial_compiler_module
from paths import REPO_ROOT
from raes import canonical_instantiated_sdl_digest, select_scenario_family
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    AdmittedMixedCompositionBindingModel,
    AdmittedTrialSourceReferenceModel,
    BackendManifestV2Model,
    ExperimentBackendReferenceModel,
    ExperimentManifestReferenceModel,
    ExperimentReferenceModel,
    seal_mixed_composition_profile,
)
from raes_contracts.contracts.mixed_composition import MixedCompositionValidationLimits
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_compiler.profiles import derive_identity, realization_assignment_key
from raes_processor.trial_compiler.realization_admission import validate_mixed_authority
from raes_processor.trial_realization import TrialRealizationInputs, realize_admitted_trial_entry
from raes_processor.trial_scheduler import plan_batch_schedule
from test_issue_1014_mixed_composition_contracts import (
    _alternative_profile,
    _context,
    _profile,
    _staged_profile,
)
from test_sce_002_trial_compiler import _bound_spec, _request, _with_participant_manifest
from test_sce_002_trial_realization import _BACKEND_KEY


def _mixed_request(profile_factory=_alternative_profile, *, base_request=None):
    request = base_request or _request(run_count=2)
    pure = compile_admitted_trial_plan(request)
    assert pure.plan is not None
    assignments = {}
    profiles = {}
    contexts = {}
    profile_refs = []
    apparatus_manifests = dict(request.apparatus_manifests)
    for pure_entry in pure.plan.entries.values():
        outcomes = {selection.variation_point_id: selection.outcome for selection in pure_entry.selections}
        selected = select_scenario_family(request.family, outcomes)
        snapshot_ref = ExperimentReferenceModel(
            ref_kind="scenario-snapshot",
            ref_id=f"snapshot:compiler-family:{pure_entry.coordinate.replicate_id}",
            ref_version="instantiated-scenario-snapshot/v1",
            ref_digest=canonical_instantiated_sdl_digest(selected).value,
        )

        source = profile_factory()
        fields = source.model_dump(mode="python", exclude={"profile_digest"})
        profile_suffix = ":".join(
            filter(None, (pure_entry.coordinate.condition_id, pure_entry.coordinate.replicate_id))
        )
        fields["profile_id"] = f"profile:{profile_suffix}"
        for component_id, component in fields["components"].items():
            component["apparatus_identity_ref"] = f"apparatus:{component_id}"
            manifest_name = f"backend-{profile_suffix}-{component_id}"
            manifest_payload = next(iter(request.apparatus_manifests.values())).model_dump(mode="python")
            manifest_payload["identity"]["name"] = manifest_name
            manifest = BackendManifestV2Model.model_validate(manifest_payload)
            manifest_ref = ExperimentManifestReferenceModel(
                ref_kind="manifest",
                ref_id=manifest_name,
                ref_version=manifest.schema_version,
                ref_digest=canonical_json_digest(manifest.model_dump(mode="json")),
                subject_ref=ExperimentBackendReferenceModel(
                    ref_kind="backend",
                    ref_id=manifest_name,
                    ref_version=manifest.identity.version,
                ),
            )
            component["manifest_ref"] = manifest_ref.model_dump(mode="python")
            component["realization_envelope"] = request.realization_envelope.identity.model_dump(mode="python")
            apparatus_manifests[("backend", manifest_name, manifest.identity.version, manifest.schema_version)] = (
                manifest
            )
        fields["scenario_snapshot_ref"] = snapshot_ref
        profile = seal_mixed_composition_profile(**fields)
        profile_ref = ExperimentReferenceModel(
            ref_kind="profile",
            ref_id=profile.profile_id,
            ref_version=profile.profile_revision,
            ref_digest=profile.profile_digest,
        )
        assignments[realization_assignment_key(pure_entry.coordinate)] = AdmittedMixedCompositionBindingModel(
            profile_ref=profile_ref
        )
        profiles[profile.profile_id] = profile
        contexts[profile.profile_id] = replace(
            _context(profile),
            allocation_effects={
                (profile.profile_id, allocation_id): frozenset({f"effect:{allocation_id}"})
                for allocation_id in profile.allocations
            },
            resource_refs={profile.profile_id: frozenset({"range:compiler-fixture"})},
            component_projection_membership={
                (profile.profile_id, component_id): True for component_id in profile.components
            },
        )
        profile_refs.append(profile_ref)
    refs = request.input_refs.model_copy(update={"mixed_composition_profile_refs": profile_refs})
    return replace(
        request,
        input_refs=refs,
        realization_assignments=assignments,
        mixed_profiles=profiles,
        mixed_profile_contexts=contexts,
        mixed_realization_envelopes={
            request.realization_envelope.identity.envelope_id: request.realization_envelope,
        },
        apparatus_manifests=apparatus_manifests,
    )


def _reject_feature(*_args) -> None:
    raise ValueError("unsupported feature")


def _profile_context(profile):
    return replace(
        _context(profile),
        allocation_effects={
            (profile.profile_id, allocation_id): frozenset({f"effect:{allocation_id}"})
            for allocation_id in profile.allocations
        },
        resource_refs={profile.profile_id: frozenset({"range:compiler-fixture"})},
        component_projection_membership={
            (profile.profile_id, component_id): True for component_id in profile.components
        },
    )


def _replace_root_profile(request, profile, context):
    profile_ref = ExperimentReferenceModel(
        ref_kind="profile",
        ref_id=profile.profile_id,
        ref_version=profile.profile_revision,
        ref_digest=profile.profile_digest,
    )
    assignments = {
        key: binding.model_copy(update={"profile_ref": profile_ref})
        if binding.profile_ref.ref_id == profile.profile_id
        else binding
        for key, binding in request.realization_assignments.items()
    }
    input_refs = request.input_refs.model_copy(
        update={
            "mixed_composition_profile_refs": [
                profile_ref if reference.ref_id == profile.profile_id else reference
                for reference in request.input_refs.mixed_composition_profile_refs
            ]
        }
    )
    return replace(
        request,
        input_refs=input_refs,
        realization_assignments=assignments,
        mixed_profiles={**request.mixed_profiles, profile.profile_id: profile},
        mixed_profile_contexts={**request.mixed_profile_contexts, profile.profile_id: context},
    )


def _with_nested_profile(request):
    root_id = sorted(request.mixed_profiles)[0]
    original = request.mixed_profiles[root_id]
    child_fields = original.model_dump(mode="python", exclude={"profile_digest"})
    child_fields["profile_id"] = f"{root_id}:child"
    child_fields["nested_profile_refs"] = {}
    manifests = dict(request.apparatus_manifests)
    for component_id, component in child_fields["components"].items():
        source_key = next(
            key for key in request.apparatus_manifests if key[1] == component["manifest_ref"]["subject_ref"]["ref_id"]
        )
        payload = request.apparatus_manifests[source_key].model_dump(mode="python")
        name = f"backend-child-{component_id}"
        payload["identity"]["name"] = name
        manifest = BackendManifestV2Model.model_validate(payload)
        reference = ExperimentManifestReferenceModel(
            ref_kind="manifest",
            ref_id=name,
            ref_version=manifest.schema_version,
            ref_digest=canonical_json_digest(manifest.model_dump(mode="json")),
            subject_ref=ExperimentBackendReferenceModel(
                ref_kind="backend",
                ref_id=name,
                ref_version=manifest.identity.version,
            ),
        )
        component["manifest_ref"] = reference.model_dump(mode="python")
        manifests[("backend", name, manifest.identity.version, manifest.schema_version)] = manifest
    child = seal_mixed_composition_profile(**child_fields)
    root_fields = original.model_dump(mode="python", exclude={"profile_digest"})
    root_fields["nested_profile_refs"] = {child.profile_id: child.profile_digest}
    root = seal_mixed_composition_profile(**root_fields)
    root_context = _profile_context(root)
    child_context = _profile_context(child)
    combined = replace(
        root_context,
        scenario_snapshots={**root_context.scenario_snapshots, **child_context.scenario_snapshots},
        compiled_targets={**root_context.compiled_targets, **child_context.compiled_targets},
        components={**root_context.components, **child_context.components},
        allocations={**root_context.allocations, **child_context.allocations},
        edges={**root_context.edges, **child_context.edges},
        transitions={**root_context.transitions, **child_context.transitions},
        evidence_satisfaction={**root_context.evidence_satisfaction, **child_context.evidence_satisfaction},
        nested_profiles={child.profile_id: child},
        allocation_effects={**root_context.allocation_effects, **child_context.allocation_effects},
        resource_refs={**root_context.resource_refs, **child_context.resource_refs},
        component_projection_membership={
            **root_context.component_projection_membership,
            **child_context.component_projection_membership,
        },
    )
    return replace(
        _replace_root_profile(request, root, combined),
        apparatus_manifests=manifests,
    ), child


def test_alternative_profile_is_admitted_as_exact_identity_bearing_realization() -> None:
    request = _mixed_request()

    first = compile_admitted_trial_plan(request)
    second = compile_admitted_trial_plan(request)

    assert first.diagnostics == second.diagnostics == ()
    assert first.plan == second.plan
    assert first.plan is not None
    entry = next(iter(first.plan.entries.values()))
    assert isinstance(entry.apparatus, AdmittedMixedCompositionBindingModel)
    assert entry.apparatus.profile_ref == next(iter(request.realization_assignments.values())).profile_ref
    assert first.plan.profiles.compiler_profile == "trial-compiler-mixed-composition-v1"
    assert first.plan.profiles.entry_identity_profile == "trial-entry-identity-mixed-composition-v1"


def test_mixed_profile_inputs_require_total_coordinate_assignment() -> None:
    request = _mixed_request()

    rejected = compile_admitted_trial_plan(replace(request, realization_assignments={}))

    assert rejected.plan is None
    assert [diagnostic.code for diagnostic in rejected.diagnostics] == [
        "trial-compiler.realization-assignment-incomplete"
    ]


def test_single_backend_realizer_rejects_mixed_entry_before_backend_selection() -> None:
    request = _mixed_request()
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None
    entry = next(iter(result.plan.entries.values()))

    inputs = TrialRealizationInputs(
        plan=result.plan,
        family=request.family,
        experiment=request.experiment,
        task=request.task,
        capture_specs=request.capture_specs,
        apparatus_manifests=request.apparatus_manifests,
        realization_envelope=request.realization_envelope,
        backend_key=_BACKEND_KEY,
    )
    with pytest.raises(ValueError, match="mixed-composition runtime coordination"):
        realize_admitted_trial_entry(inputs=inputs, plan_entry_id=entry.plan_entry_id)


@pytest.mark.parametrize(
    ("profile_factory", "mode"),
    [
        (_alternative_profile, "alternative"),
        (_profile, "simultaneous-mixed"),
        (_staged_profile, "staged"),
    ],
)
def test_compiler_admits_all_closed_composition_modes(profile_factory, mode: str) -> None:
    request = _mixed_request(profile_factory)

    result = compile_admitted_trial_plan(request)

    assert result.diagnostics == ()
    assert result.plan is not None
    admitted_modes = {
        request.mixed_profiles[entry.apparatus.profile_ref.ref_id].composition_mode
        for entry in result.plan.entries.values()
    }
    assert admitted_modes == {mode}


def test_mixed_compilation_is_stable_across_maps_partitions_threads_and_repetition() -> None:
    request = _mixed_request(_profile)
    reversed_request = replace(
        request,
        input_refs=request.input_refs.model_copy(
            update={"mixed_composition_profile_refs": list(reversed(request.input_refs.mixed_composition_profile_refs))}
        ),
        realization_assignments=dict(reversed(tuple(request.realization_assignments.items()))),
        mixed_profiles=dict(reversed(tuple(request.mixed_profiles.items()))),
        mixed_profile_contexts=dict(reversed(tuple(request.mixed_profile_contexts.items()))),
    )

    canonical = compile_admitted_trial_plan(request)
    reversed_result = compile_admitted_trial_plan(
        reversed_request,
        coordinate_partitions=((1,), (0,)),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        threaded = tuple(pool.map(compile_admitted_trial_plan, (request, reversed_request)))

    assert canonical.diagnostics == reversed_result.diagnostics == ()
    assert canonical.plan == reversed_result.plan
    assert all(result.plan == canonical.plan for result in threaded)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("context", "trial-compiler.composition-context-rejected"),
        ("envelope", "trial-compiler.apparatus-envelope-identity-mismatch"),
        ("resources", "trial-compiler.composition-resource-coverage-missing"),
        ("effects", "trial-compiler.composition-context-rejected"),
        ("projection", "trial-compiler.composition-context-rejected"),
        ("feature", "trial-compiler.composition-context-rejected"),
        ("clock", "trial-compiler.composition-context-rejected"),
        ("evidence", "trial-compiler.composition-context-rejected"),
    ],
)
def test_mixed_admission_rejects_context_envelope_resource_and_effect_drift(
    mutation: str,
    code: str,
) -> None:
    request = _mixed_request(_profile)
    profile_id = next(iter(request.mixed_profiles))
    context = request.mixed_profile_contexts[profile_id]
    if mutation == "context":
        allocation_key = next(iter(context.allocations))
        contexts = {
            **request.mixed_profile_contexts,
            profile_id: replace(
                context,
                allocations={key: value for key, value in context.allocations.items() if key != allocation_key},
            ),
        }
        request = replace(request, mixed_profile_contexts=contexts)
    elif mutation == "envelope":
        request = replace(request, mixed_realization_envelopes={})
    elif mutation == "resources":
        contexts = {
            **request.mixed_profile_contexts,
            profile_id: replace(context, resource_refs={profile_id: frozenset({"range:unowned"})}),
        }
        request = replace(request, mixed_profile_contexts=contexts)
    elif mutation == "projection":
        memberships = dict(context.component_projection_membership)
        memberships[next(iter(memberships))] = False
        contexts = {
            **request.mixed_profile_contexts,
            profile_id: replace(context, component_projection_membership=memberships),
        }
        request = replace(request, mixed_profile_contexts=contexts)
    elif mutation == "feature":
        contexts = {
            **request.mixed_profile_contexts,
            profile_id: replace(context, feature_support_resolver=_reject_feature),
        }
        request = replace(request, mixed_profile_contexts=contexts)
    elif mutation == "clock":
        contexts = {
            **request.mixed_profile_contexts,
            profile_id: replace(context, time_models={}),
        }
        request = replace(request, mixed_profile_contexts=contexts)
    elif mutation == "evidence":
        contexts = {
            **request.mixed_profile_contexts,
            profile_id: replace(context, evidence_satisfaction={}),
        }
        request = replace(request, mixed_profile_contexts=contexts)
    else:
        profile = request.mixed_profiles[profile_id]
        providers = {}
        for allocation_id, allocation in profile.allocations.items():
            providers.setdefault(allocation.provider_component_id, allocation_id)
        conflicting = tuple(list(providers.values())[:2])
        effects = dict(context.allocation_effects)
        effects[(profile_id, conflicting[0])] = frozenset({"effect:overlap"})
        effects[(profile_id, conflicting[1])] = frozenset({"effect:overlap"})
        contexts = {**request.mixed_profile_contexts, profile_id: replace(context, allocation_effects=effects)}
        request = replace(request, mixed_profile_contexts=contexts)

    rejected = compile_admitted_trial_plan(request)

    assert rejected.plan is None
    assert [diagnostic.code for diagnostic in rejected.diagnostics] == [code]


def test_mixed_admission_rejects_aggregate_context_limit_without_partial_plan() -> None:
    request = replace(
        _mixed_request(_profile),
        mixed_composition_limits=MixedCompositionValidationLimits(max_components=1),
    )

    rejected = compile_admitted_trial_plan(request)

    assert rejected.plan is None
    assert [diagnostic.code for diagnostic in rejected.diagnostics] == ["trial-compiler.composition-context-rejected"]


def test_mixed_admission_rejects_plan_aggregate_profile_and_work_bounds() -> None:
    request = _mixed_request(_profile)

    profile_limited = compile_admitted_trial_plan(
        replace(
            request,
            limits=request.limits.model_copy(update={"max_mixed_profiles": 1}),
        )
    )
    work_limited = compile_admitted_trial_plan(
        replace(
            request,
            limits=request.limits.model_copy(update={"max_mixed_context_work": 1}),
        )
    )

    assert profile_limited.plan is None
    assert [diagnostic.code for diagnostic in profile_limited.diagnostics] == [
        "trial-compiler.mixed-profile-limit-exceeded"
    ]
    assert work_limited.plan is None
    assert [diagnostic.code for diagnostic in work_limited.diagnostics] == [
        "trial-compiler.mixed-context-work-limit-exceeded"
    ]


def test_mutated_sealed_profile_is_reconstructed_and_rejected() -> None:
    request = _mixed_request(_alternative_profile)
    profile_id = next(iter(request.mixed_profiles))
    profile = request.mixed_profiles[profile_id].model_copy(deep=True)
    profile.__dict__["profile_digest"] = "sha256:" + "0" * 64
    stale_ref = request.input_refs.mixed_composition_profile_refs[0].model_copy(
        update={"ref_digest": profile.profile_digest}
    )
    assignments = {
        key: (
            binding.model_copy(update={"profile_ref": stale_ref})
            if binding.profile_ref.ref_id == profile_id
            else binding
        )
        for key, binding in request.realization_assignments.items()
    }
    refs = [
        stale_ref if reference.ref_id == profile_id else reference
        for reference in request.input_refs.mixed_composition_profile_refs
    ]
    mutated = replace(
        request,
        input_refs=request.input_refs.model_copy(update={"mixed_composition_profile_refs": refs}),
        realization_assignments=assignments,
        mixed_profiles={**request.mixed_profiles, profile_id: profile},
    )

    rejected = compile_admitted_trial_plan(mutated)

    assert rejected.plan is None
    assert [diagnostic.code for diagnostic in rejected.diagnostics] == ["trial-compiler.mixed-profile-invalid"]


def test_staged_profile_remains_one_scheduler_entry_per_trial() -> None:
    request = _mixed_request(_staged_profile)
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None

    schedule = plan_batch_schedule(result.plan)

    phase_count = sum(
        len(request.mixed_profiles[entry.apparatus.profile_ref.ref_id].phases) for entry in result.plan.entries.values()
    )
    assert len(schedule.entries) == len(result.plan.entries)
    assert phase_count > len(schedule.entries)
    assert {scheduled.plan_entry_id for scheduled in schedule.entries} == set(result.plan.entries)


def test_mixed_identity_profile_has_fixed_conformance_vectors() -> None:
    fixture = (
        REPO_ROOT / "contracts" / "fixtures" / "plans" / "trial-compiler-mixed-composition-v1" / "identity-vectors.json"
    )
    vectors = json.loads(fixture.read_text(encoding="utf-8"))

    assert vectors["profile_id"] == "trial-compiler-mixed-composition-v1"
    for case in vectors["identities"]:
        assert (
            derive_identity(
                case["kind"],
                case["projection"],
                mixed_composition=True,
            )
            == case["expected"]
        )


def test_linked_realization_change_uses_exact_source_tuple_and_new_identity() -> None:
    request = _mixed_request(_alternative_profile)
    source_request = _request(run_count=2)
    source_result = compile_admitted_trial_plan(source_request)
    assert source_result.plan is not None
    source_entry = next(iter(source_result.plan.entries.values()))
    source_ref = AdmittedTrialSourceReferenceModel(
        plan_id=source_result.plan.plan_id,
        plan_digest=source_result.plan.plan_digest,
        plan_entry_id=source_entry.plan_entry_id,
        entry_digest=source_entry.entry_digest,
        run_id=source_entry.run_id,
    )
    assignment_key = next(iter(request.realization_assignments))
    linked_binding = request.realization_assignments[assignment_key].model_copy(update={"source_trial": source_ref})
    linked = replace(
        request,
        realization_assignments={**request.realization_assignments, assignment_key: linked_binding},
        source_plans={source_result.plan.plan_id: source_result.plan},
    )

    baseline = compile_admitted_trial_plan(request)
    changed = compile_admitted_trial_plan(linked)

    assert baseline.plan is not None
    assert changed.plan is not None
    assert baseline.plan.plan_id != changed.plan.plan_id
    baseline_runs = {entry.coordinate.replicate_id: entry.run_id for entry in baseline.plan.entries.values()}
    changed_runs = {entry.coordinate.replicate_id: entry.run_id for entry in changed.plan.entries.values()}
    assert baseline_runs != changed_runs

    stale_ref = source_ref.model_copy(update={"run_id": "archival-run-stale"})
    stale = replace(
        linked,
        realization_assignments={
            **linked.realization_assignments,
            assignment_key: linked_binding.model_copy(update={"source_trial": stale_ref}),
        },
    )
    rejected = compile_admitted_trial_plan(stale)
    assert rejected.plan is None
    assert [diagnostic.code for diagnostic in rejected.diagnostics] == [
        "trial-compiler.composition-source-trial-mismatch"
    ]

    alias_ref = source_ref.model_copy(update={"plan_id": "trial-plan-alias"})
    aliased = replace(
        request,
        realization_assignments={
            **request.realization_assignments,
            assignment_key: linked_binding.model_copy(update={"source_trial": alias_ref}),
        },
        source_plans={"trial-plan-alias": source_result.plan},
    )
    alias_rejected = compile_admitted_trial_plan(aliased)
    assert [diagnostic.code for diagnostic in alias_rejected.diagnostics] == [
        "trial-compiler.composition-source-trial-mismatch"
    ]


def test_mixed_binding_carries_and_validates_exact_participant_manifest_authority() -> None:
    baseline = _mixed_request()
    request = _with_participant_manifest(baseline)
    missing = compile_admitted_trial_plan(request)
    assert [diagnostic.code for diagnostic in missing.diagnostics] == [
        "trial-compiler.realization-assignment-participant-manifest-mismatch"
    ]

    assignments = {
        key: binding.model_copy(update={"participant_manifest_refs": list(request.apparatus.participant_manifest_refs)})
        for key, binding in request.realization_assignments.items()
    }
    admitted_request = replace(request, realization_assignments=assignments)
    admitted = compile_admitted_trial_plan(admitted_request)
    baseline_result = compile_admitted_trial_plan(baseline)

    assert admitted.plan is not None
    assert baseline_result.plan is not None
    assert admitted.plan.plan_id != baseline_result.plan.plan_id
    assert all(
        entry.apparatus.participant_manifest_refs == request.apparatus.participant_manifest_refs
        for entry in admitted.plan.entries.values()
    )

    stale = compile_admitted_trial_plan(replace(admitted_request, participant_manifests={}))
    assert [diagnostic.code for diagnostic in stale.diagnostics] == [
        "trial-compiler.participant-manifest-payload-missing"
    ]


def test_mixed_descriptor_authority_excludes_unselected_caller_maps() -> None:
    request = _mixed_request(_alternative_profile)
    participant_request = _with_participant_manifest(request)
    authority = validate_mixed_authority(replace(participant_request, apparatus=request.apparatus))

    selected_keys = {
        (
            component.manifest_ref.subject_ref.ref_kind,
            component.manifest_ref.subject_ref.ref_id,
            component.manifest_ref.subject_ref.ref_version,
            component.manifest_ref.ref_version,
        )
        for profile in request.mixed_profiles.values()
        for component in profile.components.values()
    }
    admitted_keys = set().union(*(set(manifests) for manifests in authority.apparatus_manifests_by_root.values()))
    assert admitted_keys == selected_keys
    assert admitted_keys != set(request.apparatus_manifests)
    assert authority.participant_manifests == {}


def test_mixed_binding_targets_receive_only_the_coordinate_profile_authority(monkeypatch) -> None:
    experiment = _bound_spec()
    base = _request(run_count=2).with_experiment(experiment)
    descriptor_ref = ExperimentReferenceModel(
        ref_kind="other",
        ref_id="compiler-bindings",
        ref_version="experiment-binding-descriptors/v1",
        ref_digest=canonical_json_digest(experiment.binding_descriptors.model_dump(mode="json")),
    )
    base = replace(
        base,
        input_refs=base.input_refs.model_copy(update={"binding_descriptor_set_ref": descriptor_ref}),
    )
    request = _mixed_request(_alternative_profile, base_request=base)
    observed: list[frozenset[tuple[str, str, str, str]]] = []
    incumbent = trial_compiler_module.validate_experiment_binding_targets

    def capture_authority(descriptors, **kwargs):
        observed.append(frozenset(kwargs["apparatus_manifests"]))
        return incumbent(descriptors, **kwargs)

    monkeypatch.setattr(trial_compiler_module, "validate_experiment_binding_targets", capture_authority)
    result = compile_admitted_trial_plan(request)

    expected = [
        frozenset(manifests) for manifests in validate_mixed_authority(request).apparatus_manifests_by_root.values()
    ]
    assert result.diagnostics == ()
    assert sorted(observed, key=sorted) == sorted(expected, key=sorted)


def test_mixed_components_may_reuse_one_governed_implementation_manifest() -> None:
    request = _mixed_request(_profile)
    profile_id = sorted(request.mixed_profiles)[0]
    original = request.mixed_profiles[profile_id]
    fields = original.model_dump(mode="python", exclude={"profile_digest"})
    component_ids = sorted(fields["components"])
    fields["components"][component_ids[1]]["manifest_ref"] = fields["components"][component_ids[0]]["manifest_ref"]
    duplicate = seal_mixed_composition_profile(**fields)
    admitted = compile_admitted_trial_plan(_replace_root_profile(request, duplicate, _profile_context(duplicate)))

    assert admitted.diagnostics == ()
    assert admitted.plan is not None


def test_independent_root_profiles_may_reuse_one_implementation_manifest() -> None:
    request = _mixed_request(_alternative_profile)
    first_id, second_id = sorted(request.mixed_profiles)
    first = request.mixed_profiles[first_id]
    second = request.mixed_profiles[second_id]
    shared_reference = next(iter(first.components.values())).manifest_ref
    fields = second.model_dump(mode="python", exclude={"profile_digest"})
    next(iter(fields["components"].values()))["manifest_ref"] = shared_reference.model_dump(mode="python")
    reused = seal_mixed_composition_profile(**fields)

    result = compile_admitted_trial_plan(_replace_root_profile(request, reused, _profile_context(reused)))

    assert result.diagnostics == ()
    assert result.plan is not None


def test_mixed_failure_selection_is_independent_of_input_map_order() -> None:
    request = _mixed_request(_profile)
    first_id, second_id = sorted(request.mixed_profiles)
    first_context = request.mixed_profile_contexts[first_id]
    second_context = request.mixed_profile_contexts[second_id]
    invalid_contexts = {
        first_id: replace(first_context, components={}),
        second_id: replace(
            second_context,
            resource_refs={second_id: frozenset({"range:unowned"})},
        ),
    }
    forward = replace(request, mixed_profile_contexts=invalid_contexts)
    reversed_request = replace(
        forward,
        mixed_profiles=dict(reversed(tuple(forward.mixed_profiles.items()))),
        mixed_profile_contexts=dict(reversed(tuple(forward.mixed_profile_contexts.items()))),
    )

    forward_result = compile_admitted_trial_plan(forward)
    reversed_result = compile_admitted_trial_plan(reversed_request)

    assert forward_result.diagnostics == reversed_result.diagnostics
    assert [diagnostic.code for diagnostic in forward_result.diagnostics] == [
        "trial-compiler.composition-context-rejected"
    ]


def test_nested_profiles_receive_full_trial_admission_and_aggregate_limits() -> None:
    request, child = _with_nested_profile(_mixed_request(_alternative_profile))
    admitted = compile_admitted_trial_plan(request)
    assert admitted.plan is not None

    root_id = sorted(request.mixed_profiles)[0]
    context = request.mixed_profile_contexts[root_id]
    membership = dict(context.component_projection_membership)
    membership[(child.profile_id, next(iter(child.components)))] = False
    projection_rejected = compile_admitted_trial_plan(
        replace(
            request,
            mixed_profile_contexts={
                **request.mixed_profile_contexts,
                root_id: replace(context, component_projection_membership=membership),
            },
        )
    )
    assert [diagnostic.code for diagnostic in projection_rejected.diagnostics] == [
        "trial-compiler.composition-context-rejected"
    ]

    resources = dict(context.resource_refs)
    resources[child.profile_id] = frozenset({"range:unowned"})
    resource_rejected = compile_admitted_trial_plan(
        replace(
            request,
            mixed_profile_contexts={
                **request.mixed_profile_contexts,
                root_id: replace(context, resource_refs=resources),
            },
        )
    )
    assert [diagnostic.code for diagnostic in resource_rejected.diagnostics] == [
        "trial-compiler.composition-resource-coverage-missing"
    ]

    limit_rejected = compile_admitted_trial_plan(
        replace(
            request,
            limits=request.limits.model_copy(update={"max_mixed_profiles": len(request.mixed_profiles)}),
        )
    )
    assert [diagnostic.code for diagnostic in limit_rejected.diagnostics] == [
        "trial-compiler.mixed-profile-limit-exceeded"
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("entry_identity_profile", "trial-entry-identity-mixed-composition-v1"),
        ("run_identity_profile", "archival-run-identity-mixed-composition-v1"),
    ],
)
def test_legacy_plan_rejects_mixed_identity_profile_claims(field: str, value: str) -> None:
    result = compile_admitted_trial_plan(_request())
    assert result.plan is not None
    payload = result.plan.model_dump(mode="python")
    payload["profiles"][field] = value

    plan_type = type(result.plan)
    with pytest.raises(ValueError, match="legacy compiler and identity profiles"):
        plan_type.model_validate(payload)


def test_legacy_empty_participant_manifest_serialization_remains_omitted() -> None:
    result = compile_admitted_trial_plan(_request())
    assert result.plan is not None
    entry = next(iter(result.plan.entries.values()))

    assert "participant_manifest_refs" not in entry.apparatus.model_dump(mode="json")
