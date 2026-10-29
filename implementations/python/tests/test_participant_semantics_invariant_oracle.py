"""Self-consistency oracle for the participant-semantics formal model.

This file is NOT a test of any production participant-semantics subsystem — no
such runtime subsystem exists, and the invariant predicates below have no
callers under ``src/`` or ``packages/``. It is a closed, test-local executable
encoding of the invariants published in
``specs/formal/participant-semantics/README.md`` (I1-I18), and it checks two
things about that encoding:

* **Spec sync** — the catalog of invariant IDs and their spec section headings
  stay in lock-step with the spec document
  (``test_oracle_and_spec_headings_map_both_directions``).
* **Discrimination** — each invariant predicate actually separates a
  spec-conforming progression from a targeted violation.
  ``test_canonical_progression_satisfies_all_invariants`` is the positive
  control and ``test_each_invariant_rejects_its_targeted_mutation`` is the
  negative control. Because the fixtures and predicates are co-authored, the
  acceptance-direction check is a positive control for the mutation test, not
  evidence of production coverage.

Runtime *enforcement* of participant semantics is covered behaviourally
elsewhere (``test_sem_211_*`` … ``test_sem_218_*``, which drive the real
parser/compiler/validator engines). A green run here does not mean participant
semantics are implemented.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

SPEC_PATH = Path(__file__).resolve().parents[3] / "specs/formal/participant-semantics/README.md"

IMPLEMENTATION_TYPES = (
    "human",
    "ai_agent",
    "script",
    "playbook",
    "simulated_actor",
    "human_control_proxy",
)
FAIL_CLOSED_CLASSES = frozenset({"rejected", "withheld", "unknown", "unsafe_withheld"})
INTERACTION_CLASSES = frozenset({"coordination", "contention", "interference", "shared_state_change"})
ORDERING_BASES = frozenset({"happened_before", "workflow", "episode", "backend_event_order"})
ATTRIBUTION_SUPPORT = frozenset(
    {
        "declared_association",
        "temporal_support",
        "contract_support",
        "observation_support",
        "counterfactual_support",
        "intervention_support",
    }
)
MAPPING_RELATIONS = frozenset({"exact", "narrower", "broader", "approximate", "lossy", "advisory"})
PRESERVATION_STATES = frozenset({"preserved", "weakened", "simulated", "unavailable"})


@dataclass(frozen=True)
class Participant:
    participant_id: str
    implementation_type: str
    semantic_profile: str


@dataclass(frozen=True)
class PreconditionResult:
    precondition_id: str
    resolved: bool
    satisfied: bool


@dataclass(frozen=True)
class ActionAttempt:
    action_id: str
    participant_id: str
    contract_id: str
    preconditions: tuple[PreconditionResult, ...]
    executed: bool
    failure_class: str | None
    declared_effect_classes: frozenset[str]
    actual_effect_classes: frozenset[str]
    declared_side_effect_classes: frozenset[str]
    actual_side_effect_classes: frozenset[str]
    interaction_classes: frozenset[str]
    provenance_interactions: frozenset[str]
    time_domain: str
    clock_authority: str


@dataclass(frozen=True)
class ObservationApparatus:
    capture_basis: str
    capture_granularity: str
    loss_model: str
    redaction_policy: str
    observer_effects: str


@dataclass(frozen=True)
class Observation:
    observation_id: str
    participant_id: str
    source: str
    capture_basis: str
    visibility_basis: str
    latency_domain: str
    certainty: str
    loss_disclosure: str
    evidence_relationship: str
    evidence_refs: frozenset[str]
    visible_refs: frozenset[str]
    disclosure_rule_refs: frozenset[str]
    apparatus: ObservationApparatus
    inferred_from_archival_evidence: bool
    explicit_view_rule: bool


@dataclass(frozen=True)
class AttributionEdge:
    edge_id: str
    cause_action_id: str
    effect_ref: str
    ordering_basis: str
    evidence_strength: str
    evidence_refs: frozenset[str]


@dataclass(frozen=True)
class OutcomeRecord:
    action_status: str
    episode_terminal_reason: str
    objective_success: bool
    workflow_state: str
    evaluation_result: str
    reward: int
    interpretation_rules: frozenset[str]
    collapsed_layers: frozenset[tuple[str, str]]


@dataclass(frozen=True)
class BackendRealization:
    declared_guarantees: frozenset[str]
    unrealized_guarantees: frozenset[str]
    disclosed_weakened_guarantees: frozenset[str]
    capability_validation_failed: bool


@dataclass(frozen=True)
class FidelityClaim:
    semantic_portability_claimed: bool
    fidelity_equivalence_claimed: bool
    portability_claim_implies_fidelity: bool
    preservation_profile: dict[str, str]


@dataclass(frozen=True)
class ExternalMapping:
    vocabulary: str
    relation: str | None


@dataclass(frozen=True)
class RunStudyProvenance:
    repeated_run_claim: bool
    scenario_version: str
    action_contract_versions: frozenset[str]
    participant_implementation_version: str
    backend_version: str
    reset_strategy: str
    random_seed: str
    scaffold_disclosure: str
    environment_fingerprints: frozenset[str]


@dataclass(frozen=True)
class VersionedContent:
    content_id: str
    source: str
    semantic_version: str
    freshness_basis: str
    lifecycle_state: str


@dataclass(frozen=True)
class BoundaryObject:
    object_id: str
    object_class: str
    exposure_recorded: bool
    exposed_to_participant: bool


@dataclass(frozen=True)
class LanguageEvaluation:
    concrete_syntax_declared: bool
    ambiguity_review: bool
    maintainability_review: bool
    domain_expert_review: bool
    consistency_review: bool


@dataclass(frozen=True)
class ParticipantProgression:
    episode_id: str
    participants: tuple[Participant, ...]
    actions: tuple[ActionAttempt, ...]
    observations: tuple[Observation, ...]
    attribution_edges: tuple[AttributionEdge, ...]
    outcomes: tuple[OutcomeRecord, ...]
    backend_realization: BackendRealization
    fidelity_claim: FidelityClaim
    external_mappings: tuple[ExternalMapping, ...]
    provenance: RunStudyProvenance
    versioned_content: tuple[VersionedContent, ...]
    boundary_objects: tuple[BoundaryObject, ...]
    language_evaluation: LanguageEvaluation
    hidden_truth_refs: frozenset[str]
    explicit_disclosure_refs: frozenset[str]


@dataclass(frozen=True)
class Invariant:
    invariant_id: str
    spec_section: str
    sem_refs: tuple[str, ...]
    predicate: Callable[[ParticipantProgression], bool]
    mutate: Callable[[ParticipantProgression], ParticipantProgression]


def _replace_tuple_item[T](items: tuple[T, ...], index: int, value: T) -> tuple[T, ...]:
    return items[:index] + (value,) + items[index + 1 :]


def _replace_first_participant(state: ParticipantProgression, **changes: object) -> ParticipantProgression:
    participant = replace(state.participants[0], **changes)
    return replace(state, participants=_replace_tuple_item(state.participants, 0, participant))


def _replace_first_action(state: ParticipantProgression, **changes: object) -> ParticipantProgression:
    action = replace(state.actions[0], **changes)
    return replace(state, actions=_replace_tuple_item(state.actions, 0, action))


def _replace_first_observation(state: ParticipantProgression, **changes: object) -> ParticipantProgression:
    observation = replace(state.observations[0], **changes)
    return replace(state, observations=_replace_tuple_item(state.observations, 0, observation))


def _replace_first_attribution(state: ParticipantProgression, **changes: object) -> ParticipantProgression:
    edge = replace(state.attribution_edges[0], **changes)
    return replace(state, attribution_edges=_replace_tuple_item(state.attribution_edges, 0, edge))


def _replace_first_outcome(state: ParticipantProgression, **changes: object) -> ParticipantProgression:
    outcome = replace(state.outcomes[0], **changes)
    return replace(state, outcomes=_replace_tuple_item(state.outcomes, 0, outcome))


def _replace_first_mapping(state: ParticipantProgression, **changes: object) -> ParticipantProgression:
    mapping = replace(state.external_mappings[0], **changes)
    return replace(state, external_mappings=_replace_tuple_item(state.external_mappings, 0, mapping))


def _replace_first_content(state: ParticipantProgression, **changes: object) -> ParticipantProgression:
    content = replace(state.versioned_content[0], **changes)
    return replace(state, versioned_content=_replace_tuple_item(state.versioned_content, 0, content))


def _replace_first_boundary_object(state: ParticipantProgression, **changes: object) -> ParticipantProgression:
    boundary_object = replace(state.boundary_objects[0], **changes)
    return replace(state, boundary_objects=_replace_tuple_item(state.boundary_objects, 0, boundary_object))


def canonical_progression() -> ParticipantProgression:
    apparatus = ObservationApparatus(
        capture_basis="sensor-stream",
        capture_granularity="event",
        loss_model="bounded-loss-disclosed",
        redaction_policy="participant-view-redaction",
        observer_effects="passive-capture",
    )
    return ParticipantProgression(
        episode_id="episode-reference",
        participants=(
            Participant("participant-red", "human", "participant-semantics-v1"),
            Participant("participant-blue", "ai_agent", "participant-semantics-v1"),
        ),
        actions=(
            ActionAttempt(
                action_id="action-1",
                participant_id="participant-red",
                contract_id="contract.scan.v1",
                preconditions=(
                    PreconditionResult("authority", True, True),
                    PreconditionResult("knowledge", True, True),
                    PreconditionResult("temporal", True, True),
                ),
                executed=True,
                failure_class=None,
                declared_effect_classes=frozenset({"intended_effect", "evidence_effect"}),
                actual_effect_classes=frozenset({"intended_effect", "evidence_effect"}),
                declared_side_effect_classes=frozenset({"detection_effect", "visibility_effect"}),
                actual_side_effect_classes=frozenset({"detection_effect"}),
                interaction_classes=frozenset({"coordination"}),
                provenance_interactions=frozenset({"joint-action-set-1"}),
                time_domain="episode_step",
                clock_authority="scenario-clock",
            ),
        ),
        observations=(
            Observation(
                observation_id="observation-1",
                participant_id="participant-red",
                source="participant-terminal",
                capture_basis="sensor-stream",
                visibility_basis="view-rule-visible-host",
                latency_domain="episode_step",
                certainty="high",
                loss_disclosure="bounded-loss-disclosed",
                evidence_relationship="supports-observed-service",
                evidence_refs=frozenset({"evidence.service-banner"}),
                visible_refs=frozenset({"asset.public-host"}),
                disclosure_rule_refs=frozenset(),
                apparatus=apparatus,
                inferred_from_archival_evidence=False,
                explicit_view_rule=True,
            ),
        ),
        attribution_edges=(
            AttributionEdge(
                edge_id="attr-1",
                cause_action_id="action-1",
                effect_ref="observation-1",
                ordering_basis="happened_before",
                evidence_strength="observation_support",
                evidence_refs=frozenset({"evidence.service-banner"}),
            ),
        ),
        outcomes=(
            OutcomeRecord(
                action_status="succeeded",
                episode_terminal_reason="completed",
                objective_success=True,
                workflow_state="finished",
                evaluation_result="passed",
                reward=1,
                interpretation_rules=frozenset({"rule.local-action-to-objective.v1"}),
                collapsed_layers=frozenset(),
            ),
        ),
        backend_realization=BackendRealization(
            declared_guarantees=frozenset({"coordination", "visibility_boundary"}),
            unrealized_guarantees=frozenset(),
            disclosed_weakened_guarantees=frozenset(),
            capability_validation_failed=False,
        ),
        fidelity_claim=FidelityClaim(
            semantic_portability_claimed=True,
            fidelity_equivalence_claimed=False,
            portability_claim_implies_fidelity=False,
            preservation_profile={
                "behavior": "preserved",
                "observation": "preserved",
                "timing": "weakened",
                "failure": "preserved",
                "evidence": "preserved",
            },
        ),
        external_mappings=(
            ExternalMapping("ATT&CK", "approximate"),
            ExternalMapping("OCSF", "narrower"),
        ),
        provenance=RunStudyProvenance(
            repeated_run_claim=True,
            scenario_version="scenario@1.0.0",
            action_contract_versions=frozenset({"contract.scan.v1"}),
            participant_implementation_version="participant-red@1.0.0",
            backend_version="stub-backend@1.0.0",
            reset_strategy="clean-snapshot",
            random_seed="seed-487",
            scaffold_disclosure="public-starter-files-only",
            environment_fingerprints=frozenset({"container-sha256:abc123"}),
        ),
        versioned_content=(
            VersionedContent(
                content_id="contract.scan.v1",
                source="scenario-contract-registry",
                semantic_version="1.0.0",
                freshness_basis="reviewed-2026-06",
                lifecycle_state="active",
            ),
        ),
        boundary_objects=(
            BoundaryObject("answer-key", "hidden_truth", True, False),
            BoundaryObject("canary-token", "canary", True, False),
            BoundaryObject("starter-files", "public_starter_files", True, True),
        ),
        language_evaluation=LanguageEvaluation(
            concrete_syntax_declared=True,
            ambiguity_review=True,
            maintainability_review=True,
            domain_expert_review=True,
            consistency_review=True,
        ),
        hidden_truth_refs=frozenset({"answer-key", "canary-token"}),
        explicit_disclosure_refs=frozenset(),
    )


def _i1_role_neutral(state: ParticipantProgression) -> bool:
    profiles = {participant.semantic_profile for participant in state.participants}
    known_implementations = all(
        participant.implementation_type in IMPLEMENTATION_TYPES for participant in state.participants
    )
    return len(profiles) == 1 and known_implementations


def _i2_hidden_truth_boundary(state: ParticipantProgression) -> bool:
    disclosed_hidden_refs = state.hidden_truth_refs & state.explicit_disclosure_refs
    for observation in state.observations:
        leaked_refs = observation.visible_refs & state.hidden_truth_refs
        if leaked_refs - disclosed_hidden_refs:
            return False
    return True


def _i3_observation_projection(state: ParticipantProgression) -> bool:
    required = (
        "source",
        "capture_basis",
        "visibility_basis",
        "latency_domain",
        "certainty",
        "loss_disclosure",
        "evidence_relationship",
    )
    return all(all(getattr(observation, field_name) for field_name in required) for observation in state.observations)


def _i4_fail_closed_action_applicability(state: ParticipantProgression) -> bool:
    for action in state.actions:
        applicable = all(result.resolved and result.satisfied for result in action.preconditions)
        if applicable:
            continue
        if action.executed or action.failure_class not in FAIL_CLOSED_CLASSES:
            return False
    return True


def _i5_explicit_side_effects(state: ParticipantProgression) -> bool:
    return all(
        action.actual_side_effect_classes <= action.declared_side_effect_classes
        and action.actual_effect_classes <= action.declared_effect_classes
        for action in state.actions
    )


def _i6_explicit_interaction_semantics(state: ParticipantProgression) -> bool:
    for action in state.actions:
        if not action.interaction_classes:
            continue
        if not action.interaction_classes <= INTERACTION_CLASSES or not action.provenance_interactions:
            return False
    return True


def _i7_temporal_domain_separation(state: ParticipantProgression) -> bool:
    action_domains = {action.time_domain for action in state.actions}
    observation_domains = {observation.latency_domain for observation in state.observations}
    return all(action.time_domain and action.clock_authority for action in state.actions) and "" not in (
        action_domains | observation_domains
    )


def _i8_ordering_before_causality(state: ParticipantProgression) -> bool:
    return all(edge.ordering_basis in ORDERING_BASES for edge in state.attribution_edges)


def _i9_evidence_labeled_attribution(state: ParticipantProgression) -> bool:
    return all(edge.evidence_strength in ATTRIBUTION_SUPPORT and edge.evidence_refs for edge in state.attribution_edges)


def _i10_outcome_layer_separation(state: ParticipantProgression) -> bool:
    return all(outcome.interpretation_rules and not outcome.collapsed_layers for outcome in state.outcomes)


def _i11_realization_disclosure(state: ParticipantProgression) -> bool:
    unrealized = state.backend_realization.unrealized_guarantees
    return (
        not unrealized
        or state.backend_realization.capability_validation_failed
        or unrealized <= (state.backend_realization.disclosed_weakened_guarantees)
    )


def _i12_fidelity_claim_separation(state: ParticipantProgression) -> bool:
    expected_aspects = {"behavior", "observation", "timing", "failure", "evidence"}
    profile = state.fidelity_claim.preservation_profile
    return (
        not state.fidelity_claim.portability_claim_implies_fidelity
        and set(profile) == expected_aspects
        and all(value in PRESERVATION_STATES for value in profile.values())
    )


def _i13_observation_apparatus_disclosure(state: ParticipantProgression) -> bool:
    for observation in state.observations:
        apparatus = observation.apparatus
        disclosed = (
            apparatus.capture_basis,
            apparatus.capture_granularity,
            apparatus.loss_model,
            apparatus.redaction_policy,
            apparatus.observer_effects,
        )
        if not all(disclosed):
            return False
        if observation.inferred_from_archival_evidence and not observation.explicit_view_rule:
            return False
    return True


def _i14_external_mapping_loss_labels(state: ParticipantProgression) -> bool:
    return all(mapping.relation in MAPPING_RELATIONS for mapping in state.external_mappings)


def _i15_run_and_study_provenance(state: ParticipantProgression) -> bool:
    if not state.provenance.repeated_run_claim:
        return True
    provenance = state.provenance
    return all(
        (
            provenance.scenario_version,
            provenance.action_contract_versions,
            provenance.participant_implementation_version,
            provenance.backend_version,
            provenance.reset_strategy,
            provenance.random_seed,
            provenance.scaffold_disclosure,
            provenance.environment_fingerprints,
        )
    )


def _i16_content_and_contract_lifecycle(state: ParticipantProgression) -> bool:
    return all(
        content.source and content.semantic_version and content.freshness_basis and content.lifecycle_state
        for content in state.versioned_content
    )


def _i17_benchmark_leakage_and_holdout_discipline(state: ParticipantProgression) -> bool:
    boundary_ids = {boundary.object_id for boundary in state.boundary_objects}
    if not state.hidden_truth_refs <= boundary_ids:
        return False
    protected_classes = {"hidden_truth", "canary", "private_reference", "holdout_variant"}
    for boundary in state.boundary_objects:
        if not boundary.exposure_recorded:
            return False
        protected = boundary.object_id in state.hidden_truth_refs or boundary.object_class in protected_classes
        if protected and boundary.exposed_to_participant and boundary.object_id not in state.explicit_disclosure_refs:
            return False
    return True


def _i18_language_evaluation_obligation(state: ParticipantProgression) -> bool:
    if not state.language_evaluation.concrete_syntax_declared:
        return True
    return all(
        (
            state.language_evaluation.ambiguity_review,
            state.language_evaluation.maintainability_review,
            state.language_evaluation.domain_expert_review,
            state.language_evaluation.consistency_review,
        )
    )


def _mutate_i1(state: ParticipantProgression) -> ParticipantProgression:
    return _replace_first_participant(state, semantic_profile="backend-local-human-only")


def _mutate_i2(state: ParticipantProgression) -> ParticipantProgression:
    observation = state.observations[0]
    return _replace_first_observation(state, visible_refs=observation.visible_refs | frozenset({"answer-key"}))


def _mutate_i3(state: ParticipantProgression) -> ParticipantProgression:
    return _replace_first_observation(state, source="")


def _mutate_i4(state: ParticipantProgression) -> ParticipantProgression:
    preconditions = (PreconditionResult("authority", resolved=False, satisfied=False),)
    return _replace_first_action(state, preconditions=preconditions, executed=True, failure_class=None)


def _mutate_i5(state: ParticipantProgression) -> ParticipantProgression:
    action = state.actions[0]
    return _replace_first_action(
        state,
        actual_side_effect_classes=action.actual_side_effect_classes | frozenset({"telemetry_surface_change"}),
    )


def _mutate_i6(state: ParticipantProgression) -> ParticipantProgression:
    return _replace_first_action(
        state, interaction_classes=frozenset({"contention"}), provenance_interactions=frozenset()
    )


def _mutate_i7(state: ParticipantProgression) -> ParticipantProgression:
    return _replace_first_action(state, time_domain="", clock_authority="")


def _mutate_i8(state: ParticipantProgression) -> ParticipantProgression:
    return _replace_first_attribution(state, ordering_basis="timestamp_only")


def _mutate_i9(state: ParticipantProgression) -> ParticipantProgression:
    return _replace_first_attribution(state, evidence_strength="", evidence_refs=frozenset())


def _mutate_i10(state: ParticipantProgression) -> ParticipantProgression:
    return _replace_first_outcome(
        state,
        interpretation_rules=frozenset(),
        collapsed_layers=frozenset({("action_status", "objective_success")}),
    )


def _mutate_i11(state: ParticipantProgression) -> ParticipantProgression:
    realization = replace(
        state.backend_realization,
        unrealized_guarantees=frozenset({"simultaneity"}),
        disclosed_weakened_guarantees=frozenset(),
        capability_validation_failed=False,
    )
    return replace(state, backend_realization=realization)


def _mutate_i12(state: ParticipantProgression) -> ParticipantProgression:
    fidelity_claim = replace(
        state.fidelity_claim,
        semantic_portability_claimed=True,
        fidelity_equivalence_claimed=True,
        portability_claim_implies_fidelity=True,
        preservation_profile={"behavior": "preserved"},
    )
    return replace(state, fidelity_claim=fidelity_claim)


def _mutate_i13(state: ParticipantProgression) -> ParticipantProgression:
    apparatus = replace(state.observations[0].apparatus, loss_model="")
    return _replace_first_observation(
        state,
        apparatus=apparatus,
        inferred_from_archival_evidence=True,
        explicit_view_rule=False,
    )


def _mutate_i14(state: ParticipantProgression) -> ParticipantProgression:
    return _replace_first_mapping(state, relation=None)


def _mutate_i15(state: ParticipantProgression) -> ParticipantProgression:
    provenance = replace(state.provenance, random_seed="", reset_strategy="")
    return replace(state, provenance=provenance)


def _mutate_i16(state: ParticipantProgression) -> ParticipantProgression:
    return _replace_first_content(state, semantic_version="", lifecycle_state="")


def _mutate_i17(state: ParticipantProgression) -> ParticipantProgression:
    return _replace_first_boundary_object(state, exposed_to_participant=True)


def _mutate_i18(state: ParticipantProgression) -> ParticipantProgression:
    language_evaluation = replace(
        state.language_evaluation,
        concrete_syntax_declared=True,
        domain_expert_review=False,
    )
    return replace(state, language_evaluation=language_evaluation)


INVARIANTS = (
    Invariant("I1", "### I1 - Role-Neutral Participant Semantics", ("SEM-208",), _i1_role_neutral, _mutate_i1),
    Invariant("I2", "### I2 - Hidden Truth Boundary", ("SEM-210",), _i2_hidden_truth_boundary, _mutate_i2),
    Invariant("I3", "### I3 - Observation Projection", ("SEM-208", "SEM-210"), _i3_observation_projection, _mutate_i3),
    Invariant(
        "I4",
        "### I4 - Fail-Closed Action Applicability",
        ("SEM-211",),
        _i4_fail_closed_action_applicability,
        _mutate_i4,
    ),
    Invariant("I5", "### I5 - Explicit Side Effects", ("SEM-211",), _i5_explicit_side_effects, _mutate_i5),
    Invariant(
        "I6", "### I6 - Explicit Interaction Semantics", ("SEM-209",), _i6_explicit_interaction_semantics, _mutate_i6
    ),
    Invariant("I7", "### I7 - Temporal Domain Separation", ("SEM-213",), _i7_temporal_domain_separation, _mutate_i7),
    Invariant(
        "I8", "### I8 - Ordering Before Causality", ("SEM-212", "SEM-213"), _i8_ordering_before_causality, _mutate_i8
    ),
    Invariant(
        "I9", "### I9 - Evidence-Labeled Attribution", ("SEM-212",), _i9_evidence_labeled_attribution, _mutate_i9
    ),
    Invariant("I10", "### I10 - Outcome-Layer Separation", ("SEM-215",), _i10_outcome_layer_separation, _mutate_i10),
    Invariant(
        "I11", "### I11 - Realization Disclosure", ("SEM-208", "SEM-209"), _i11_realization_disclosure, _mutate_i11
    ),
    Invariant(
        "I12",
        "### I12 - Fidelity Claim Separation",
        ("SEM-208", "SEM-215"),
        _i12_fidelity_claim_separation,
        _mutate_i12,
    ),
    Invariant(
        "I13",
        "### I13 - Observation Apparatus Disclosure",
        ("SEM-210",),
        _i13_observation_apparatus_disclosure,
        _mutate_i13,
    ),
    Invariant(
        "I14", "### I14 - External Mapping Loss Labels", ("SEM-208",), _i14_external_mapping_loss_labels, _mutate_i14
    ),
    Invariant("I15", "### I15 - Run And Study Provenance", ("SEM-215",), _i15_run_and_study_provenance, _mutate_i15),
    Invariant(
        "I16",
        "### I16 - Content And Contract Lifecycle",
        ("SEM-208",),
        _i16_content_and_contract_lifecycle,
        _mutate_i16,
    ),
    Invariant(
        "I17",
        "### I17 - Benchmark Leakage And Holdout Discipline",
        ("SEM-210", "SEM-215"),
        _i17_benchmark_leakage_and_holdout_discipline,
        _mutate_i17,
    ),
    Invariant(
        "I18",
        "### I18 - Language Evaluation Obligation",
        ("SEM-208",),
        _i18_language_evaluation_obligation,
        _mutate_i18,
    ),
)


def test_oracle_and_spec_headings_map_both_directions() -> None:
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    spec_headings = {
        line.split(" - ", 1)[0].removeprefix("### ")
        for line in spec_text.splitlines()
        if line.startswith("### I") and " - " in line
    }

    assert spec_headings == {invariant.invariant_id for invariant in INVARIANTS}
    for invariant in INVARIANTS:
        assert invariant.spec_section in spec_text
        assert invariant.sem_refs


@pytest.mark.parametrize("invariant", INVARIANTS, ids=lambda invariant: invariant.invariant_id)
def test_each_invariant_rejects_its_targeted_mutation(invariant: Invariant) -> None:
    base_state = canonical_progression()
    mutated = invariant.mutate(base_state)

    assert not invariant.predicate(mutated), invariant.invariant_id


def test_canonical_progression_satisfies_all_invariants() -> None:
    # Positive control. The canonical progression must satisfy every predicate so
    # that test_each_invariant_rejects_its_targeted_mutation proves a real
    # True -> False flip rather than a vacuous False -> False. This is not
    # evidence of production coverage; nothing under src/ or packages/ consumes
    # these predicates.
    state = canonical_progression()

    for invariant in INVARIANTS:
        assert invariant.predicate(state), invariant.invariant_id
