"""Behavioral-relation authority, examples, and claim-binding tests."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from copy import deepcopy
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from raes_conformance.conformance import _fixture_case_diagnostics
from raes_contracts.behavioral_claims import BehavioralClaimBindingModel
from raes_contracts.behavioral_relations import (
    ExampleTransitionModel,
    ExampleTransitionSystemModel,
    load_behavioral_relation_catalog,
)
from raes_contracts.contracts import ExperimentStudyModel
from raes_contracts.scientific_completeness import load_scientific_completeness_taxonomy
from raes_schemas import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
REQUIRED_RELATION_IDS = {
    "structural-validity",
    "semantic-validity",
    "capability-declaration",
    "profile-satisfaction",
    "bounded-probe-success",
    "bounded-but-for-necessity",
    "canonical-artifact-identity",
    "realization-envelope-membership",
    "realization-envelope-subsumption",
    "trace-inclusion",
    "trace-equivalence",
    "forward-simulation",
    "backward-simulation",
    "data-refinement",
    "strong-bisimulation",
    "weak-bisimulation",
    "divergence-preserving-branching-bisimulation",
    "participant-predicate-opacity",
    "participant-projected-history-equivalence",
    "policy-noninterference",
    "io-alternating-refinement",
    "epistemic-indistinguishability",
    "alternating-strategic-equivalence",
    "probabilistic-bisimulation",
    "statistical-similarity",
    "statistical-equivalence",
    "empirical-adequacy",
}


def _bounded_empirical_claim() -> dict[str, object]:
    return {
        "taxonomy_id": "raes-behavioral-relations",
        "taxonomy_revision": "rev8",
        "relation_id": "empirical-adequacy",
        "subject": "TechVault baseline study",
        "left_carrier_ref": "study-techvault-baseline@1.0.0",
        "observation_projection_ref": "analysis-plan:baseline-proportion",
        "observation_projection_revision": "experiment-study/v1",
        "quantifier_scope": "sampled-population",
        "evidence_scope": "statistical",
        "evidence_boundary": "The one predeclared baseline condition and included evaluation runs.",
        "assurance_status": "deliberately-unproved",
        "evidence_refs": ["analysis_plan:baseline-proportion"],
        "limitations": ["The fixture has one run and cannot establish population adequacy."],
        "explicit_non_claims": ["No behavioral equivalence or generalizability claim."],
    }


def _transition_index(system):
    index = defaultdict(list)
    for transition in system.transitions:
        index[transition.source].append((transition.action, transition.target))
    return index


def _trace_exists(system, actions: tuple[str, ...]) -> bool:
    states = {system.initial_state}
    index = _transition_index(system)
    for action in actions:
        states = {target for state in states for candidate, target in index[state] if candidate == action}
    return bool(states)


def _enabled_actions(system, state: str) -> set[str]:
    return {action for action, _ in _transition_index(system)[state]}


def _strongly_bisimilar(left, right) -> bool:
    left_index = _transition_index(left)
    right_index = _transition_index(right)
    candidates = {(lstate, rstate) for lstate in left.states for rstate in right.states}
    changed = True
    while changed:
        changed = False
        for pair in tuple(candidates):
            lstate, rstate = pair
            left_ok = all(
                any(
                    action == other_action and (target, other_target) in candidates
                    for other_action, other_target in right_index[rstate]
                )
                for action, target in left_index[lstate]
            )
            right_ok = all(
                any(
                    action == other_action and (other_target, target) in candidates
                    for other_action, other_target in left_index[lstate]
                )
                for action, target in right_index[rstate]
            )
            if not left_ok or not right_ok:
                candidates.remove(pair)
                changed = True
    return (left.initial_state, right.initial_state) in candidates


def _tau_closure(system, states: set[str], tau: str) -> set[str]:
    index = _transition_index(system)
    closure = set(states)
    queue = deque(states)
    while queue:
        state = queue.popleft()
        for action, target in index[state]:
            if action == tau and target not in closure:
                closure.add(target)
                queue.append(target)
    return closure


def _weak_trace_exists(system, actions: tuple[str, ...], tau: str) -> bool:
    index = _transition_index(system)
    states = _tau_closure(system, {system.initial_state}, tau)
    for action in actions:
        targets = {target for state in states for candidate, target in index[state] if candidate == action}
        states = _tau_closure(system, targets, tau)
    return bool(states)


def test_authoritative_catalog_covers_required_relation_classes_and_dimensions():
    catalog = load_behavioral_relation_catalog()

    assert catalog.schema_version == "behavioral-relations/v1"
    assert catalog.taxonomy_id == "raes-behavioral-relations"
    assert catalog.taxonomy_revision == "rev13"
    assert set(catalog.relations) >= REQUIRED_RELATION_IDS
    for relation_id, relation in catalog.relations.items():
        assert relation.left_carrier
        assert relation.right_carrier
        assert relation.direction
        assert relation.quantification.states
        assert relation.quantification.traces
        assert relation.preservation.proof_obligation
        assert relation.bounded_evidence
        assert relation.explicit_non_claims
        assert relation.source_refs
        assert set(relation.dimensions.model_dump()) == {
            "nondeterminism",
            "concurrency",
            "probability",
            "time",
            "partial_order",
        }, relation_id


def test_catalog_bibliography_claim_surfaces_and_relation_references_resolve():
    catalog = load_behavioral_relation_catalog()
    source_ids = {source.source_id for source in catalog.bibliography}

    assert source_ids >= {
        "park-1981",
        "milner-1980",
        "van-glabbeek-1990",
        "van-glabbeek-weijland-1996",
        "van-glabbeek-luttik-trcka-2009",
        "abadi-lamport-1991",
        "lynch-vaandrager-1995",
        "fagin-halpern-moses-vardi-1995",
        "alur-henzinger-kupferman-vardi-1998",
        "alur-henzinger-kupferman-2002",
        "goguen-meseguer-1982",
        "sabelfeld-sands-2009",
        "lynch-tuttle-1989",
        "clarkson-schneider-2010",
        "bohannon-pierce-sjoberg-weirich-zdancewic-2009",
        "halpern-pearl-2005",
        "bryans-koutny-mazare-ryan-2008",
        "schoepe-sabelfeld-2015",
        "cui-ma-giua-yin-2026",
        "partovi-jung-hai-2020",
    }
    assert all(source.immutable_locator.kind in {"doi", "isbn", "report"} for source in catalog.bibliography)
    assert all(set(relation.source_refs) <= source_ids for relation in catalog.relations.values())
    assert {surface.surface_id for surface in catalog.claim_surfaces} == {
        "sdl-transformation",
        "backend-realization",
        "backend-comparison",
        "participant-visible-behavior",
        "participant-information-flow-policy",
        "participant-opacity",
        "participant-crossing-bisimulation",
        "multi-agent-interaction",
        "counterfactual-necessity-validation",
        "independent-adequacy-study",
    }
    assert all(
        set(surface.intended_relation_ids) <= set(catalog.relations)
        and set(surface.prohibited_relation_ids) <= set(catalog.relations)
        for surface in catalog.claim_surfaces
    )


def test_finite_probe_counterexample_passes_probe_but_fails_strong_bisimulation():
    example = load_behavioral_relation_catalog().worked_examples["finite-probe-counterexample"]

    trace = tuple(example.tested_visible_trace)
    assert _trace_exists(example.left_system, trace)
    assert _trace_exists(example.right_system, trace)
    assert not _strongly_bisimilar(example.left_system, example.right_system)
    assert example.expected_strong_bisimulation is False


def test_hidden_action_example_distinguishes_strong_from_weak_matching():
    example = load_behavioral_relation_catalog().worked_examples["hidden-action-counterexample"]

    trace = tuple(example.tested_visible_trace)
    assert not _strongly_bisimilar(example.left_system, example.right_system)
    assert _weak_trace_exists(example.left_system, trace, example.hidden_action)
    assert _weak_trace_exists(example.right_system, trace, example.hidden_action)
    assert example.expected_strong_bisimulation is False
    assert example.expected_weak_matching is True


def test_decision_epoch_zero_hidden_projection_step_can_weakly_match_without_strong_bisimulation():
    abstract = ExampleTransitionSystemModel(
        states=["a-ready", "a-delivered"],
        initial_state="a-ready",
        transitions=[
            ExampleTransitionModel(
                source="a-ready",
                action="deliver:decision-epoch-0",
                target="a-delivered",
            )
        ],
    )
    concrete = ExampleTransitionSystemModel(
        states=["c-ready", "c-projected", "c-delivered"],
        initial_state="c-ready",
        transitions=[
            ExampleTransitionModel(source="c-ready", action="tau:projection", target="c-projected"),
            ExampleTransitionModel(
                source="c-projected",
                action="deliver:decision-epoch-0",
                target="c-delivered",
            ),
        ],
    )

    assert not _strongly_bisimilar(abstract, concrete)
    assert _weak_trace_exists(abstract, ("deliver:decision-epoch-0",), "tau:projection")
    assert _weak_trace_exists(concrete, ("deliver:decision-epoch-0",), "tau:projection")


def test_projected_trace_inclusion_does_not_establish_required_participant_input_availability():
    abstract = ExampleTransitionSystemModel(
        states=["a0", "a1"],
        initial_state="a0",
        transitions=[ExampleTransitionModel(source="a0", action="select:scan", target="a1")],
    )
    refusing_backend = ExampleTransitionSystemModel(
        states=["c0"],
        initial_state="c0",
        transitions=[ExampleTransitionModel(source="c0", action="tau:idle", target="c0")],
    )
    candidate_visible_traces = ((), ("select:scan",))
    observed_concrete_traces = {trace for trace in candidate_visible_traces if _trace_exists(refusing_backend, trace)}
    observed_abstract_traces = {trace for trace in candidate_visible_traces if _trace_exists(abstract, trace)}

    assert observed_concrete_traces == {()}
    assert observed_abstract_traces == {(), ("select:scan",)}
    assert observed_concrete_traces <= observed_abstract_traces
    assert "select:scan" in _enabled_actions(abstract, abstract.initial_state)
    assert "select:scan" not in _enabled_actions(refusing_backend, refusing_backend.initial_state)


@settings(max_examples=40)
@given(
    visible=st.text(alphabet="abcxyz", min_size=1, max_size=5),
    unmatched=st.text(alphabet="abcxyz", min_size=1, max_size=5),
)
def test_any_unmatched_initial_branch_refutes_strong_bisimulation_after_a_shared_probe(
    visible: str,
    unmatched: str,
):
    assume(visible != unmatched)
    left = ExampleTransitionSystemModel(
        states=["l0", "l1", "l2"],
        initial_state="l0",
        transitions=[
            ExampleTransitionModel(source="l0", action=visible, target="l1"),
            ExampleTransitionModel(source="l0", action=unmatched, target="l2"),
        ],
    )
    right = ExampleTransitionSystemModel(
        states=["r0", "r1"],
        initial_state="r0",
        transitions=[ExampleTransitionModel(source="r0", action=visible, target="r1")],
    )

    assert _trace_exists(left, (visible,))
    assert _trace_exists(right, (visible,))
    assert not _strongly_bisimilar(left, right)


@settings(max_examples=40)
@given(
    visible=st.text(alphabet="abcxyz", min_size=1, max_size=5),
    hidden=st.text(alphabet="tuv", min_size=1, max_size=5),
)
def test_a_generated_hidden_prefix_separates_strong_matching_from_weak_visible_trace_matching(
    visible: str,
    hidden: str,
):
    assume(visible != hidden)
    abstract = ExampleTransitionSystemModel(
        states=["a0", "a1"],
        initial_state="a0",
        transitions=[ExampleTransitionModel(source="a0", action=visible, target="a1")],
    )
    concrete = ExampleTransitionSystemModel(
        states=["c0", "c1", "c2"],
        initial_state="c0",
        transitions=[
            ExampleTransitionModel(source="c0", action=hidden, target="c1"),
            ExampleTransitionModel(source="c1", action=visible, target="c2"),
        ],
    )

    assert not _strongly_bisimilar(abstract, concrete)
    assert _weak_trace_exists(abstract, (visible,), hidden)
    assert _weak_trace_exists(concrete, (visible,), hidden)


def test_claim_binding_rejects_bounded_evidence_promoted_to_universal_claim():
    with pytest.raises(ValidationError, match="universal quantification requires model-check or proof evidence"):
        BehavioralClaimBindingModel(
            taxonomy_id="raes-behavioral-relations",
            taxonomy_revision="rev8",
            relation_id="trace-equivalence",
            subject="two finite backend runs",
            left_carrier_ref="backend-run:left",
            right_carrier_ref="backend-run:right",
            quantifier_scope="all-traces",
            evidence_scope="finite",
            evidence_boundary="one named probe trace",
            assurance_status="tested",
            limitations=["Only one trace was exercised."],
            explicit_non_claims=["Does not establish trace equivalence."],
        )


def test_schema_bundle_publishes_behavioral_relation_catalog():
    schema = schema_bundle()["behavioral-relations-v1"]

    assert schema["properties"]["schema_version"]["const"] == "behavioral-relations/v1"
    assert schema["properties"]["relations"]["minProperties"] == 1
    assert {item["id"] for item in schema["x-raes-invariants"]} == {"behavioral-relations-reference-resolution"}


@pytest.mark.parametrize(
    ("fixture", "valid"),
    [
        ("valid/reference.json", True),
        ("invalid/missing-taxonomy-id.json", False),
    ],
)
def test_behavioral_relation_catalog_fixtures_exercise_conformance(fixture: str, valid: bool):
    path = REPO_ROOT / "contracts/fixtures/concept-authority/behavioral-relations-v1" / fixture
    diagnostics = _fixture_case_diagnostics(
        "behavioral-relations-v1",
        json.loads(path.read_text(encoding="utf-8")),
    )
    assert (not diagnostics) is valid


def test_scientific_completeness_profiles_bind_claims_and_nonclaims_to_catalog():
    catalog = load_behavioral_relation_catalog()
    taxonomy = load_scientific_completeness_taxonomy()

    for profile in taxonomy.profiles:
        assert profile.behavioral_claims, profile.profile_id
        assert profile.non_claimed_relation_ids, profile.profile_id
        assert {claim.relation_id for claim in profile.behavioral_claims} <= set(catalog.relations)
        assert set(profile.non_claimed_relation_ids) <= set(catalog.relations)
    benchmark = next(
        profile for profile in taxonomy.profiles if profile.profile_id == "reproducible-benchmark-study-input"
    )
    assert {claim.relation_id for claim in benchmark.behavioral_claims} == {"profile-satisfaction"}
    assert "empirical-adequacy" in benchmark.non_claimed_relation_ids
    assert "trace-equivalence" in benchmark.non_claimed_relation_ids


def test_scientific_completeness_profile_rejects_unknown_relation_binding():
    payload = json.loads(
        (REPO_ROOT / "contracts/profiles/scientific-completeness/scientific-scenario-completeness-rev1.json").read_text(
            encoding="utf-8"
        )
    )
    payload["profiles"][0]["behavioral_claims"][0]["relation_id"] = "unknown-relation"
    taxonomy_type = type(load_scientific_completeness_taxonomy())

    with pytest.raises(ValidationError, match="unknown relation"):
        taxonomy_type.model_validate(payload)


def test_study_claims_are_revisioned_bounded_and_required_for_claim_bearing_studies():
    fixture_path = REPO_ROOT / "contracts/fixtures/experiment-core/experiment-study-v1/valid/reference.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["behavioral_claims"] = [_bounded_empirical_claim()]

    study = ExperimentStudyModel.model_validate(payload)
    assert study.behavioral_claims[0].relation_id == "empirical-adequacy"

    missing_claims = deepcopy(payload)
    del missing_claims["behavioral_claims"]
    with pytest.raises(ValidationError, match="behavioral claim"):
        ExperimentStudyModel.model_validate(missing_claims)


def test_study_rejects_unknown_behavioral_relation():
    fixture_path = REPO_ROOT / "contracts/fixtures/experiment-core/experiment-study-v1/valid/reference.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["behavioral_claims"] = [_bounded_empirical_claim()]
    payload["behavioral_claims"][0]["relation_id"] = "unknown-relation"

    with pytest.raises(ValidationError, match="unknown relation"):
        ExperimentStudyModel.model_validate(payload)
