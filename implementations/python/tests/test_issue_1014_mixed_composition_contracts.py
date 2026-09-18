"""Portable SEM-234 mixed-composition contract and resolution tests."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from raes_backend_protocols.capabilities import ParticipantFeatureSupport
from raes_backend_protocols.participant_feature_admission import resolve_participant_feature_support
from raes_conformance.conformance import contract_validation_strength, validate_contract_payload
from raes_contracts.contracts import schema_bundle
from raes_contracts.contracts.mixed_composition import (
    MIXED_COMPOSITION_CONTRACT_ID,
    CompositionFeatureRequirementModel,
    MixedCompositionFeatureDowngradeAuthorization,
    MixedCompositionResolutionContext,
    MixedCompositionTrustedAllocation,
    MixedCompositionTrustedComponent,
    MixedCompositionTrustedEdge,
    MixedCompositionTrustedTransition,
    MixedCompositionValidationLimits,
    MixedParticipantCompositionProfileModel,
    parse_mixed_composition_profile,
    seal_mixed_composition_profile,
    validate_mixed_composition_context,
)
from raes_contracts.contracts.time_model import (
    ClockDeclarationModel,
    ExactRatioModel,
    TimeDomainDeclarationModel,
    TimeDomainMappingDeclarationModel,
    TimeModelDeclarationModel,
)
from raes_contracts.json_ingress import parse_bounded_json_object
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel

SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64
SHA_D = "sha256:" + "d" * 64
SHA_E = "sha256:" + "e" * 64
SHA_F = "sha256:" + "f" * 64
REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "contracts/schemas/plans/mixed-participant-composition-profile-v1.json"
FIXTURE_ROOT = REPO_ROOT / "contracts/fixtures/plans/mixed-participant-composition-profile-v1"
PUBLICATION_PATH = REPO_ROOT / "contracts/schema-publication/entries/mixed-participant-composition-profile-v1.json"


def _manifest_ref(component: str, digest: str) -> dict[str, object]:
    return {
        "ref_kind": "manifest",
        "ref_id": component,
        "ref_version": "backend-manifest/v2",
        "ref_digest": digest,
        "subject_ref": {
            "ref_kind": "backend",
            "ref_id": component,
            "ref_version": "1",
        },
    }


def _component(component_id: str, form: str, digest: str, envelope_digest: str) -> dict[str, object]:
    return {
        "component_id": component_id,
        "apparatus_identity_ref": f"apparatus:{component_id}",
        "realization_form": form,
        "manifest_ref": _manifest_ref(component_id, digest),
        "realization_envelope": {
            "contract_id": "realization-envelope-v1",
            "envelope_id": f"envelope:{component_id}",
            "schema_version": "realization-envelope/v1",
            "digest": envelope_digest,
            "configuration_digest": SHA_F,
        },
        "native_ownership_ref": f"native-ownership:{component_id}",
    }


def _allocation(
    allocation_id: str,
    target_kind: str,
    target_address: str,
    provider: str,
    *,
    phase_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "allocation_id": allocation_id,
        "target_kind": target_kind,
        "target_address": target_address,
        "provider_component_id": provider,
        "phase_ids": phase_ids or ["phase.main"],
        "participant_identity_ref": "participant:alice",
        "controller_ref": "controller:operator",
        "action_authority_ref": "authority:action",
        "routing_ref": "route:portable",
        "feature_requirements": [
            {
                "feature": "participant_ingress_admission",
                "required_level": "exact",
            }
        ],
    }


def _edge(*, phase_ids: list[str] | None = None) -> dict[str, object]:
    return {
        "edge_id": "edge.sim-to-emu",
        "source_component_id": "sim",
        "target_component_id": "emu",
        "phase_ids": phase_ids or ["phase.main"],
        "crossing_scope_address": "crossings.alice.status",
        "crossing_subject": {
            "subject_kind": "participant-observation",
            "contract_id": "participant-observation-envelope-v1",
            "subject_ref": "observation:status",
            "subject_revision": "7",
            "participant_address": "participants.alice",
            "episode_id": "episode:1",
        },
        "audience_scope_ref": "audience:alice",
        "policy": {
            "policy_id": "policy:crossing",
            "policy_revision": "3",
            "policy_digest": SHA_C,
            "policy_decision_ref": "decision:7",
            "decision_cut_ref": "cut:7",
            "effective_order": 7,
            "valid_from_order": 1,
            "valid_until_order": 9,
        },
        "controller_ref": "controller:operator",
        "authority_ref": "authority:edge",
        "routing_ref": "route:portable",
        "disclosure_authority_ref": "authority:disclosure",
        "native_ownership_ref": "native-ownership:sim",
        "time_binding": {
            "time_model_ref": "time-model:composition",
            "time_model_digest": SHA_D,
            "source_clock_address": "time.clocks.sim",
            "target_clock_address": "time.clocks.emu",
            "mapping_address": "time.mappings.sim-to-emu",
            "ordering_basis": "partial_order",
            "temporal_coupling": "bounded-asynchronous",
        },
        "mapping_loss": {
            "kind": "semantics_approximated",
            "basis_ref": "mapping:basis",
            "affected_ref": "observation:status",
            "limitation_ref": "limitation:mapping",
        },
        "failure_behavior": {
            "failure_ref": "failure:edge",
            "disposition": "fail-profile",
        },
        "evidence_bindings": [
            {
                "obligation_ref": "obligation:edge-realization",
                "evidence_ref": "evidence:edge-realization",
            }
        ],
    }


def _base_fields() -> dict[str, object]:
    allocations = {
        "allocation.participant": _allocation("allocation.participant", "participant", "participants.alice", "sim"),
        "allocation.scope": _allocation("allocation.scope", "controlled-scope", "nodes.target", "emu"),
        "allocation.action": _allocation("allocation.action", "action-family", "actions.alice.inspect", "sim"),
        "allocation.observation": _allocation(
            "allocation.observation", "observation-source", "observations.target.status", "emu"
        ),
        "allocation.crossing": _allocation("allocation.crossing", "crossing", "crossings.alice.status", "emu"),
    }
    return {
        "profile_id": "profile:mixed",
        "scenario_snapshot_ref": {
            "ref_kind": "scenario-snapshot",
            "ref_id": "scenario:authored",
            "ref_version": "1",
            "ref_digest": SHA_A,
        },
        "composition_mode": "simultaneous-mixed",
        "control_loop_posture": "closed-loop",
        "world_assumption": "bounded-open-world",
        "federation_membership": "pre-admitted-staged",
        "components": {
            "sim": _component("sim", "simulation", SHA_A, SHA_B),
            "emu": _component("emu", "emulation-or-operation", SHA_C, SHA_D),
        },
        "allocations": allocations,
        "edges": {"edge.sim-to-emu": _edge()},
        "phases": {
            "phase.main": {
                "phase_id": "phase.main",
                "active_component_ids": ["sim", "emu"],
                "active_allocation_ids": list(allocations),
                "active_edge_ids": ["edge.sim-to-emu"],
                "evidence_bindings": [
                    {
                        "obligation_ref": "obligation:phase-realization",
                        "evidence_ref": "evidence:phase-realization",
                    }
                ],
            }
        },
        "initial_phase_id": "phase.main",
        "phase_order": ["phase.main"],
        "transitions": {},
        "nested_profile_refs": {},
    }


def _profile(**changes: object) -> MixedParticipantCompositionProfileModel:
    fields = _base_fields()
    fields.update(changes)
    return seal_mixed_composition_profile(**fields)


def _alternative_profile(component_id: str = "sim") -> MixedParticipantCompositionProfileModel:
    fields = _base_fields()
    fields.update(
        composition_mode="alternative",
        federation_membership="fixed",
        components={component_id: fields["components"][component_id]},
        edges={},
    )
    for allocation in fields["allocations"].values():
        allocation["provider_component_id"] = component_id
    fields["phases"]["phase.main"].update(active_component_ids=[component_id], active_edge_ids=[])
    return seal_mixed_composition_profile(**fields)


def _staged_profile() -> MixedParticipantCompositionProfileModel:
    fields = _base_fields()
    fields.update(composition_mode="staged", initial_phase_id="phase.sim", phase_order=["phase.sim", "phase.emu"])
    for allocation_id in ("allocation.participant", "allocation.action"):
        fields["allocations"][allocation_id]["phase_ids"] = ["phase.sim"]
    for allocation_id in ("allocation.scope", "allocation.observation", "allocation.crossing"):
        fields["allocations"][allocation_id]["phase_ids"] = ["phase.emu"]
    fields["allocations"]["allocation.participant"]["provider_component_id"] = "sim"
    fields["allocations"]["allocation.action"]["provider_component_id"] = "sim"
    for allocation_id in ("allocation.scope", "allocation.observation", "allocation.crossing"):
        fields["allocations"][allocation_id]["provider_component_id"] = "emu"
    fields["edges"] = {}
    fields["phases"] = {
        "phase.sim": {
            "phase_id": "phase.sim",
            "active_component_ids": ["sim"],
            "active_allocation_ids": ["allocation.participant", "allocation.action"],
            "active_edge_ids": [],
            "evidence_bindings": [{"obligation_ref": "obligation:sim", "evidence_ref": "evidence:phase-realization"}],
        },
        "phase.emu": {
            "phase_id": "phase.emu",
            "active_component_ids": ["emu"],
            "active_allocation_ids": [
                "allocation.scope",
                "allocation.observation",
                "allocation.crossing",
            ],
            "active_edge_ids": [],
            "evidence_bindings": [{"obligation_ref": "obligation:emu", "evidence_ref": "evidence:phase-realization"}],
        },
    }
    fields["transitions"] = {
        "transition.sim-to-emu": {
            "transition_id": "transition.sim-to-emu",
            "source_phase_id": "phase.sim",
            "target_phase_id": "phase.emu",
            "trigger_ref": "trigger:advance",
            "evaluator_ref": "evaluator:admitted",
            "progress_bound": 1,
            "failure_disposition": "fail-profile",
            "evidence_bindings": [
                {"obligation_ref": "obligation:transition", "evidence_ref": "evidence:phase-realization"}
            ],
        }
    }
    return seal_mixed_composition_profile(**fields)


def _time_model() -> TimeModelDeclarationModel:
    ratio = ExactRatioModel(numerator=1, denominator=1)
    sim_domain = TimeDomainDeclarationModel(
        address="time.domains.sim",
        kind="simulated",
        tick_period_seconds=ratio,
        epoch="scenario_start",
        visibility="runtime_only",
        description="simulation domain",
    )
    emu_domain = TimeDomainDeclarationModel(
        address="time.domains.emu",
        kind="simulated",
        tick_period_seconds=ratio,
        epoch="scenario_start",
        visibility="runtime_only",
        description="emulation domain",
    )
    return TimeModelDeclarationModel(
        domains={sim_domain.address: sim_domain, emu_domain.address: emu_domain},
        clocks={
            "time.clocks.sim": ClockDeclarationModel(
                address="time.clocks.sim",
                time_domain_address=sim_domain.address,
                authority_kind="backend",
                authority_ref="sim",
                monotonicity="non_decreasing",
                description="simulation clock",
            ),
            "time.clocks.emu": ClockDeclarationModel(
                address="time.clocks.emu",
                time_domain_address=emu_domain.address,
                authority_kind="backend",
                authority_ref="emu",
                monotonicity="non_decreasing",
                description="emulation clock",
            ),
        },
        mappings={
            "time.mappings.sim-to-emu": TimeDomainMappingDeclarationModel(
                address="time.mappings.sim-to-emu",
                source_domain_address=sim_domain.address,
                target_domain_address=emu_domain.address,
                mapping_kind="identity",
                description="shared admitted tick scale",
            )
        },
    )


def _backend_manifest(level: ParticipantFeatureSupportLevel = ParticipantFeatureSupportLevel.EXACT) -> object:
    declaration = ParticipantFeatureSupport(
        feature="participant_ingress_admission",
        support_level=level,
        constraint_refs=("constraint:bounded",) if level is ParticipantFeatureSupportLevel.BOUNDED else (),
        limitation_refs=("limitation:bounded",) if level is not ParticipantFeatureSupportLevel.EXACT else (),
        disclosure_refs=("disclosure:bounded",) if level is not ParticipantFeatureSupportLevel.EXACT else (),
        evidence_refs=("evidence:feature",),
    )
    participant_runtime = SimpleNamespace(
        supported_behavior_features=frozenset({"participant_ingress_admission"}),
        supported_interaction_features=frozenset(),
        feature_support=(declaration,),
    )
    return SimpleNamespace(
        participant_runtime=participant_runtime,
        supported_contract_versions=frozenset(
            {"participant-control-occurrence-v1", "participant-crossing-occurrence-v1"}
        ),
    )


def _feature_support_resolver(manifests: dict[str, object]):
    def resolve(
        _profile_id: str,
        provider_component_id: str,
        requirement: CompositionFeatureRequirementModel,
    ) -> None:
        manifest = manifests.get(provider_component_id)
        if manifest is None:
            raise ValueError("provider manifest is unresolved")
        resolve_participant_feature_support(
            manifest,
            requirement.feature,
            required_level=requirement.required_level,
            allowed_downgrade_level=requirement.allowed_downgrade_level,
            downgrade_policy_ref=requirement.downgrade_policy_ref,
            downgrade_provenance_ref=requirement.downgrade_provenance_ref,
        )

    return resolve


def _context(
    profile: MixedParticipantCompositionProfileModel | None = None,
    *,
    backend_manifests: dict[str, object] | None = None,
    downgrade_authorizations: frozenset[MixedCompositionFeatureDowngradeAuthorization] = frozenset(),
) -> MixedCompositionResolutionContext:
    selected = profile or _profile()
    manifests = backend_manifests or {component_id: _backend_manifest() for component_id in selected.components}
    evidence_satisfaction: dict[tuple[str, str], set[str]] = {}
    evidence_carriers = (
        *selected.edges.values(),
        *selected.phases.values(),
        *selected.transitions.values(),
    )
    for carrier in evidence_carriers:
        for binding in carrier.evidence_bindings:
            evidence_satisfaction.setdefault((selected.profile_id, binding.obligation_ref), set()).add(
                binding.evidence_ref
            )
    return MixedCompositionResolutionContext(
        scenario_snapshots={selected.scenario_snapshot_ref.ref_id: selected.scenario_snapshot_ref},
        compiled_targets={
            allocation.target_address: allocation.target_kind for allocation in selected.allocations.values()
        },
        components={
            (selected.profile_id, component.component_id): MixedCompositionTrustedComponent(
                profile_id=selected.profile_id,
                component_id=component.component_id,
                apparatus_identity_ref=component.apparatus_identity_ref,
                manifest_ref=component.manifest_ref,
                realization_envelope=component.realization_envelope,
                native_ownership_ref=component.native_ownership_ref,
            )
            for component in selected.components.values()
        },
        allocations={
            (selected.profile_id, allocation.allocation_id): MixedCompositionTrustedAllocation(
                profile_id=selected.profile_id,
                allocation_id=allocation.allocation_id,
                target_kind=allocation.target_kind,
                target_address=allocation.target_address,
                provider_component_id=allocation.provider_component_id,
                participant_identity_ref=allocation.participant_identity_ref,
                controller_ref=allocation.controller_ref,
                action_authority_ref=allocation.action_authority_ref,
                routing_ref=allocation.routing_ref,
            )
            for allocation in selected.allocations.values()
        },
        edges={
            (selected.profile_id, edge.edge_id): MixedCompositionTrustedEdge(
                profile_id=selected.profile_id,
                edge_id=edge.edge_id,
                source_component_id=edge.source_component_id,
                target_component_id=edge.target_component_id,
                crossing_scope_address=edge.crossing_scope_address,
                crossing_subject=edge.crossing_subject,
                audience_scope_ref=edge.audience_scope_ref,
                policy=edge.policy,
                controller_ref=edge.controller_ref,
                authority_ref=edge.authority_ref,
                routing_ref=edge.routing_ref,
                disclosure_authority_ref=edge.disclosure_authority_ref,
                native_ownership_ref=edge.native_ownership_ref,
                time_binding=edge.time_binding,
                mapping_loss=edge.mapping_loss,
                failure_behavior=edge.failure_behavior,
            )
            for edge in selected.edges.values()
        },
        transitions={
            (selected.profile_id, transition.transition_id): MixedCompositionTrustedTransition(
                profile_id=selected.profile_id,
                transition_id=transition.transition_id,
                source_phase_id=transition.source_phase_id,
                target_phase_id=transition.target_phase_id,
                trigger_ref=transition.trigger_ref,
                evaluator_ref=transition.evaluator_ref,
            )
            for transition in selected.transitions.values()
        },
        feature_support_resolver=_feature_support_resolver(manifests),
        feature_downgrade_authorizations=downgrade_authorizations,
        time_models={"time-model:composition": _time_model()},
        time_model_digests={"time-model:composition": SHA_D},
        evidence_satisfaction={key: frozenset(values) for key, values in evidence_satisfaction.items()},
        nested_profiles={},
    )


def test_profile_round_trip_seals_one_closed_root_and_requires_semantic_context() -> None:
    profile = _profile()
    payload = profile.model_dump(mode="json")

    reparsed = parse_mixed_composition_profile(json.dumps(payload))
    assert reparsed == profile
    assert reparsed.contract_id == MIXED_COMPOSITION_CONTRACT_ID
    assert reparsed.semantic_revision == "sem-234/rev1"
    assert reparsed.profile_revision == "mixed-cross-backend-participant-control-v1@rev1"
    assert profile.profile_digest.startswith("sha256:")
    assert contract_validation_strength(MIXED_COMPOSITION_CONTRACT_ID) == "structural-context-required"
    diagnostics = validate_contract_payload(MIXED_COMPOSITION_CONTRACT_ID, payload)
    assert {diagnostic.code for diagnostic in diagnostics} == {"conformance.semantic-context-required"}
    assert (
        validate_contract_payload(
            MIXED_COMPOSITION_CONTRACT_ID,
            payload,
            mixed_composition_context=_context(),
        )
        == ()
    )


@pytest.mark.parametrize("forbidden", ["backend_choice", "metadata", "trial_id", "run_id", "current_phase"])
def test_profile_rejects_backend_local_open_or_runtime_fields(forbidden: str) -> None:
    payload = _profile().model_dump(mode="json")
    payload[forbidden] = {"hla_handle": "17", "command": "start"}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MixedParticipantCompositionProfileModel.model_validate(payload)


def test_profile_rejects_duplicate_apparatus_identity_and_contradictory_target_authority() -> None:
    fields = _base_fields()
    fields["components"]["emu"]["apparatus_identity_ref"] = "apparatus:sim"
    with pytest.raises(ValidationError, match="apparatus identity"):
        seal_mixed_composition_profile(**fields)

    fields = _base_fields()
    duplicate = deepcopy(fields["allocations"]["allocation.participant"])
    duplicate["allocation_id"] = "allocation.participant.competing"
    duplicate["provider_component_id"] = "emu"
    fields["allocations"][duplicate["allocation_id"]] = duplicate
    fields["phases"]["phase.main"]["active_allocation_ids"].append(duplicate["allocation_id"])
    with pytest.raises(ValidationError, match="canonical provider"):
        seal_mixed_composition_profile(**fields)


def test_profile_modes_are_distinct_and_staged_membership_is_finite() -> None:
    alternative = _alternative_profile()
    assert alternative.composition_mode == "alternative"

    staged = _staged_profile()
    assert staged.composition_mode == "staged"

    invalid = _base_fields()
    invalid["composition_mode"] = "alternative"
    with pytest.raises(ValidationError, match="alternative"):
        seal_mixed_composition_profile(**invalid)


def test_alternative_realizations_are_distinct_roots_without_trial_or_run_identity() -> None:
    simulation = _alternative_profile("sim")
    emulation = _alternative_profile("emu")
    assert simulation.scenario_snapshot_ref == emulation.scenario_snapshot_ref
    assert simulation.profile_digest != emulation.profile_digest
    assert not ({"trial_id", "run_id"} & set(type(simulation).model_fields))


def test_bounded_ingress_rejects_duplicate_members_depth_nodes_and_unknown_revision() -> None:
    assert parse_bounded_json_object('{"value":"[[{{"}', max_bytes=64, max_depth=1) == {"value": "[[{{"}
    with pytest.raises(ValueError, match="duplicate JSON member"):
        parse_mixed_composition_profile('{"profile_id":"a","profile_id":"b"}')

    payload = _profile().model_dump(mode="json")
    with pytest.raises(ValueError, match="depth limit"):
        parse_mixed_composition_profile(
            json.dumps(payload),
            limits=MixedCompositionValidationLimits(max_json_depth=2),
        )
    with pytest.raises(ValueError, match="node limit"):
        parse_mixed_composition_profile(
            json.dumps(payload),
            limits=MixedCompositionValidationLimits(max_json_nodes=10),
        )
    deeply_nested = '{"value":' + "[" * 2_000 + "0" + "]" * 2_000 + "}"
    with pytest.raises(ValueError, match="depth limit"):
        parse_mixed_composition_profile(
            deeply_nested,
            limits=MixedCompositionValidationLimits(max_json_depth=64),
        )

    payload["schema_version"] = "mixed-participant-composition-profile/v2"
    with pytest.raises(ValidationError):
        MixedParticipantCompositionProfileModel.model_validate(payload)


def test_contextual_validation_resolves_all_authorities_without_mutation_or_inference() -> None:
    profile = _profile()
    original = profile.model_dump(mode="json")
    validate_mixed_composition_context(profile, _context())
    assert profile.model_dump(mode="json") == original

    missing_target = replace(_context(), compiled_targets={})
    with pytest.raises(ValueError, match="compiled target"):
        validate_mixed_composition_context(profile, missing_target)

    missing_policy = replace(_context(), edges={})
    with pytest.raises(ValueError, match="edge authority relationship"):
        validate_mixed_composition_context(profile, missing_policy)

    stale_mapping = replace(_context(), time_model_digests={"time-model:composition": SHA_E})
    with pytest.raises(ValueError, match="time model"):
        validate_mixed_composition_context(profile, stale_mapping)

    missing_evidence = replace(_context(), evidence_satisfaction={})
    with pytest.raises(ValueError, match="evidence"):
        validate_mixed_composition_context(profile, missing_evidence)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("scenario_snapshot_ref", "ref_version"), "2"),
        (("components", "sim", "apparatus_identity_ref"), "apparatus:other"),
        (("components", "sim", "realization_envelope", "envelope_id"), "envelope:other"),
        (("allocations", "allocation.participant", "participant_identity_ref"), "participant:mallory"),
        (("allocations", "allocation.participant", "controller_ref"), "controller:other"),
        (("allocations", "allocation.participant", "action_authority_ref"), "authority:other"),
        (("allocations", "allocation.participant", "routing_ref"), "route:other"),
        (("edges", "edge.sim-to-emu", "crossing_scope_address"), "crossings.mallory.status"),
        (("edges", "edge.sim-to-emu", "crossing_subject", "participant_address"), "participants.mallory"),
        (("edges", "edge.sim-to-emu", "audience_scope_ref"), "audience:other"),
        (("edges", "edge.sim-to-emu", "policy", "policy_decision_ref"), "decision:other"),
        (("edges", "edge.sim-to-emu", "controller_ref"), "controller:other"),
        (("edges", "edge.sim-to-emu", "authority_ref"), "authority:other"),
        (("edges", "edge.sim-to-emu", "routing_ref"), "route:other"),
        (("edges", "edge.sim-to-emu", "disclosure_authority_ref"), "authority:other"),
        (("edges", "edge.sim-to-emu", "native_ownership_ref"), "native-ownership:other"),
        (("edges", "edge.sim-to-emu", "time_binding", "mapping_address"), "time.mappings.other"),
        (("edges", "edge.sim-to-emu", "mapping_loss", "basis_ref"), "mapping:other"),
        (("edges", "edge.sim-to-emu", "mapping_loss", "affected_ref"), "observation:other"),
        (("edges", "edge.sim-to-emu", "mapping_loss", "limitation_ref"), "limitation:other"),
        (("edges", "edge.sim-to-emu", "failure_behavior", "failure_ref"), "failure:other"),
        (("edges", "edge.sim-to-emu", "evidence_bindings", 0, "obligation_ref"), "obligation:other"),
    ],
)
def test_context_rejects_resealed_profiles_with_untrusted_external_coordinates(
    path: tuple[str | int, ...],
    replacement: str,
) -> None:
    trusted = _profile()
    fields = _base_fields()
    target = fields
    for coordinate in path[:-1]:
        target = target[coordinate]
    target[path[-1]] = replacement
    attacker_profile = seal_mixed_composition_profile(**fields)

    with pytest.raises(ValueError, match="unresolved|stale"):
        validate_mixed_composition_context(attacker_profile, _context(trusted))


def test_context_rejects_resealed_component_with_consistently_rekeyed_manifest_identity() -> None:
    trusted = _profile()
    fields = _base_fields()
    manifest = fields["components"]["sim"]["manifest_ref"]
    manifest["ref_id"] = "backend:other"
    manifest["subject_ref"]["ref_id"] = "backend:other"
    attacker_profile = seal_mixed_composition_profile(**fields)

    with pytest.raises(ValueError, match="component identity relationship"):
        validate_mixed_composition_context(attacker_profile, _context(trusted))


@pytest.mark.parametrize("coordinate", ["trigger_ref", "evaluator_ref"])
def test_context_rejects_untrusted_staged_transition_ownership(coordinate: str) -> None:
    trusted = _staged_profile()
    fields = trusted.model_dump(
        mode="python",
        exclude={"contract_id", "schema_version", "semantic_revision", "profile_revision", "profile_digest"},
    )
    fields["transitions"]["transition.sim-to-emu"][coordinate] = f"{coordinate}:other"
    attacker_profile = seal_mixed_composition_profile(**fields)

    with pytest.raises(ValueError, match="transition trigger or evaluator"):
        validate_mixed_composition_context(attacker_profile, _context(trusted))


def test_capability_support_is_resolved_per_provider_and_downgrade_requires_authority() -> None:
    profile = _profile()
    unsupported = _context(
        profile,
        backend_manifests={
            "sim": _backend_manifest(ParticipantFeatureSupportLevel.BOUNDED),
            "emu": _backend_manifest(),
        },
    )
    with pytest.raises(ValueError, match="feature support"):
        validate_mixed_composition_context(profile, unsupported)

    fields = _base_fields()
    for allocation in fields["allocations"].values():
        if allocation["provider_component_id"] != "sim":
            continue
        requirement = allocation["feature_requirements"][0]
        requirement.update(
            allowed_downgrade_level="bounded",
            downgrade_policy_ref="policy:downgrade",
            downgrade_provenance_ref="provenance:downgrade",
        )
    downgraded = seal_mixed_composition_profile(**fields)
    authorization = MixedCompositionFeatureDowngradeAuthorization(
        profile_id=downgraded.profile_id,
        provider_component_id="sim",
        feature="participant_ingress_admission",
        required_level=ParticipantFeatureSupportLevel.EXACT,
        allowed_downgrade_level=ParticipantFeatureSupportLevel.BOUNDED,
        policy_ref="policy:downgrade",
        provenance_ref="provenance:downgrade",
    )
    context = _context(
        downgraded,
        backend_manifests={
            "sim": _backend_manifest(ParticipantFeatureSupportLevel.BOUNDED),
            "emu": _backend_manifest(),
        },
        downgrade_authorizations=frozenset({authorization}),
    )
    validate_mixed_composition_context(downgraded, context)

    unrelated_authorization = replace(authorization, provider_component_id="emu")
    with pytest.raises(ValueError, match="downgrade authorization"):
        validate_mixed_composition_context(
            downgraded,
            _context(
                downgraded,
                backend_manifests={
                    "sim": _backend_manifest(ParticipantFeatureSupportLevel.BOUNDED),
                    "emu": _backend_manifest(),
                },
                downgrade_authorizations=frozenset({unrelated_authorization}),
            ),
        )


def test_graph_work_limit_and_unresolved_nested_profile_fail_closed() -> None:
    profile = _profile(nested_profile_refs={"profile:child": SHA_E})
    with pytest.raises(ValueError, match="nested profile"):
        validate_mixed_composition_context(profile, _context())
    with pytest.raises(ValueError, match="work limit"):
        validate_mixed_composition_context(
            _profile(),
            _context(),
            limits=MixedCompositionValidationLimits(max_context_work=1),
        )
    base = _profile()
    cyclic = base.model_copy(update={"nested_profile_refs": {base.profile_id: base.profile_digest}})
    cyclic_context = replace(_context(cyclic), nested_profiles={base.profile_id: cyclic})
    with pytest.raises(ValueError, match="cycle"):
        validate_mixed_composition_context(cyclic, cyclic_context)

    child = _alternative_profile()
    parent = _profile(nested_profile_refs={"profile:child": child.profile_digest})
    wrong_identity = replace(_context(parent), nested_profiles={"profile:child": child})
    with pytest.raises(ValueError, match="nested profile"):
        validate_mixed_composition_context(parent, wrong_identity)


def test_contract_layer_keeps_feature_resolution_dependency_inverted() -> None:
    source = (REPO_ROOT / "implementations/python/packages/raes_contracts/contracts/mixed_composition.py").read_text(
        encoding="utf-8"
    )
    assert "raes_backend_protocols" not in source


def test_published_schema_bundle_fixtures_and_change_ledger_are_consistent() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema_bundle()[MIXED_COMPOSITION_CONTRACT_ID] == schema

    valid = sorted((FIXTURE_ROOT / "valid").glob("*.json"))
    invalid = sorted((FIXTURE_ROOT / "invalid").glob("*.json"))
    assert {path.stem for path in valid} == {"alternative", "simultaneous-mixed", "staged"}
    assert {path.stem for path in invalid} >= {
        "alternative-fallback-pool",
        "duplicate-apparatus-identity",
        "open-metadata",
        "simultaneous-single-form",
        "staged-unadmitted-member",
        "unknown-revision",
    }
    for path in valid:
        MixedParticipantCompositionProfileModel.model_validate(json.loads(path.read_text(encoding="utf-8")))
    for path in invalid:
        with pytest.raises(ValidationError):
            MixedParticipantCompositionProfileModel.model_validate(json.loads(path.read_text(encoding="utf-8")))

    publication = json.loads(PUBLICATION_PATH.read_text(encoding="utf-8"))
    digest = hashlib.sha256(
        json.dumps(schema, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    assert publication == {
        "content_hash": digest,
        "contract_id": MIXED_COMPOSITION_CONTRACT_ID,
        "last_change": {
            "content_hash": digest,
            "summary": "Publish the initial closed SEM-234 mixed-participant composition profile (#1014).",
        },
        "schema_path": "contracts/schemas/plans/mixed-participant-composition-profile-v1.json",
        "stability": "draft",
    }
