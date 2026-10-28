"""Structural acceptance gate for issue #811's bisimulation proof program."""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROGRAM_PATH = REPO_ROOT / "docs/research/participant-bisimulation/implementation-program.json"
CATALOG_PATH = REPO_ROOT / "contracts/concept-authority/behavioral-relations-v1.json"
MILESTONE = "Participant Information-Flow & Behavioral Equivalence"

REQUIRED_DELIVERABLES = {
    "docs/decisions/adrs/adr-100-participant-crossing-bisimulation.md",
    "docs/research/participant-bisimulation/current-state-assessment.md",
    "docs/research/participant-bisimulation/candidate-comparison.md",
    "docs/research/participant-bisimulation/theorem-selection.md",
    "docs/research/participant-bisimulation/proof-tool-decision.md",
    "docs/research/participant-bisimulation/worked-evidence.md",
    "docs/research/participant-bisimulation/requirement-disposition.md",
    "docs/research/participant-bisimulation/implementation-program.md",
    "specs/formal/participant-semantics/participant-crossing-bisimulation.md",
}
REQUIRED_CANDIDATES = {
    "abstract-semantics-vs-complete-reference-runtime",
    "two-policy-configurations",
    "abstract-crossing-vs-concrete-crossing-kernel",
    "two-backend-realizations",
    "high-action-hidden-vs-purge-restriction",
}
REQUIRED_REQUIREMENTS = {"SEM-230", "SEM-231", "SEM-232", "ASR-535", "RUN-319", "API-423"}
REQUIRED_CHILDREN = {
    "formal-models",
    "runtime-mapping",
    "counterexample-corpus",
    "finite-equivalence-check",
    "independent-reproduction",
    "scientific-documentation",
}
REQUIRED_VISIBLE_LABELS = {
    "crossing.request",
    "crossing.decision.permit",
    "crossing.decision.deny",
    "crossing.decision.unsupported",
    "crossing.transform",
    "crossing.declassify",
    "crossing.delivery",
    "crossing.observation",
    "crossing.replay.reject",
    "policy.cut.advance",
}
REQUIRED_TAU_LABELS = {
    "internal.validate",
    "internal.resolve-policy-cut",
    "internal.resolve-capability",
    "internal.prepare-record",
    "internal.atomic-commit",
}
REQUIRED_NEGATIVE_MUTATIONS = {
    "visible-denial-hidden",
    "hidden-divergence-added",
    "delivery-branch-removed",
    "later-cut-replay-permitted",
}


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_program_covers_every_candidate_and_selects_one_exact_theorem() -> None:
    program = _load_json(PROGRAM_PATH)

    assert program["schema_version"] == "participant-bisimulation-program/v1"
    assert program["parent_issue"] == 811
    assert program["milestone"] == MILESTONE
    assert set(program["deliverables"]) >= REQUIRED_DELIVERABLES
    assert all((REPO_ROOT / path).is_file() for path in REQUIRED_DELIVERABLES)

    candidates = {entry["id"]: entry for entry in program["candidate_surfaces"]}
    assert set(candidates) == REQUIRED_CANDIDATES
    assert program["selected_candidate"] == "abstract-crossing-vs-concrete-crossing-kernel"
    assert candidates[program["selected_candidate"]]["disposition"] == "selected"
    for candidate in candidates.values():
        assert candidate["left_carrier"]
        assert candidate["right_carrier"]
        assert candidate["state_space"]
        assert candidate["initial_relation"]
        assert candidate["transitions_and_enabledness"]
        assert candidate["label_and_projection_boundary"]
        assert candidate["exact_relation"]
        assert candidate["dimensions"]
        assert candidate["tau_and_divergence"]
        assert candidate["disposition"]
        assert candidate["rationale"]


def test_selected_profile_is_closed_independently_derived_and_divergence_preserving() -> None:
    profile = _load_json(PROGRAM_PATH)["theorem_profile"]

    assert profile["profile_id"] == "participant-crossing-dpbb-finite-v1"
    assert profile["relation_id"] == "divergence-preserving-branching-bisimulation"
    assert profile["quantifier_scope"] == "complete-finite-carrier"
    assert profile["finite_carrier_is_complete"] is True
    assert profile["depth_or_sample_bound"] is None
    assert profile["initial_relation"]

    left = profile["left_model"]
    right = profile["right_model"]
    assert left["model_id"] != right["model_id"]
    assert left["authority"] != right["authority"]
    assert left["transition_source"] != right["transition_source"]
    assert left["independent_construction"] is True
    assert right["independent_construction"] is True
    assert left["state_coordinates"]
    assert right["state_coordinates"]
    assert left["initial_state"]
    assert right["initial_state"]

    mapping = profile["state_runtime_mapping"]
    assert mapping["claim_axis"] == "runtime-realization"
    assert mapping["separate_from_formal_equivalence"] is True
    assert mapping["coordinates"]
    assert mapping["evidence_required"]

    dimensions = profile["dimensions"]
    assert dimensions == {
        "nondeterminism": "finite-possibilistic-branching",
        "concurrency": "sequential-per-participant-total-order",
        "probability": "excluded",
        "time": "untimed",
        "partial_order": "excluded",
        "fairness": "none-assumed",
        "controller_handoff": "excluded-fixed-controller",
        "policy_change": "finite-visible-exact-cut-advance",
    }

    labels = profile["label_partition"]
    visible = set(labels["visible"])
    tau = set(labels["tau"])
    assert visible >= REQUIRED_VISIBLE_LABELS
    assert tau == REQUIRED_TAU_LABELS
    assert visible.isdisjoint(tau)
    assert labels["closed"] is True
    assert labels["redacted_occurrence_is_not_tau"] is True

    semantics = profile["transition_semantics"]
    assert semantics["enabledness"]
    assert semantics["branching"]
    assert semantics["deadlock"] == "structural-and-observable"
    assert semantics["termination"] == "explicit-success-or-refusal-terminal-state"
    assert semantics["divergence"] == "explicit-infinite-tau-path-must-be-related"
    assert semantics["stuttering"] == "finite-tau-stuttering-only"
    assert semantics["same_cut_replay"] == "visible-request-with-idempotent-matched-result"
    assert semantics["later_cut_replay"] == "visible-rejection"


def test_tool_record_is_exact_reproducible_and_does_not_overclaim() -> None:
    program = _load_json(PROGRAM_PATH)
    decision = program["proof_tool_decision"]
    tools = {entry["id"]: entry for entry in decision["evaluated_tools"]}

    assert set(tools) == {"mcrl2", "tlc", "isabelle-hol"}
    assert all(
        entry["exact_relation_fit"]
        and entry["counterexample_behavior"]
        and entry["ci_viability"]
        and entry["reproduction"]
        and entry["disposition"]
        for entry in tools.values()
    )
    assert decision["selected_tool"] == "mcrl2"
    assert decision["selected_version"] == "202607.0"
    assert decision["assurance_axis"] == "model-check"
    assert decision["positive_exit_is_certificate"] is False
    command = decision["fixed_command"]
    assert command[:2] == ["ltscompare", "--equivalence=dpbranching-bisim"]
    assert "--tau=internal" in command
    assert command[-2:] == ["abstract.aut", "concrete.aut"]
    assert decision["independent_input_generation"] is True
    assert decision["no_shell"] is True
    assert decision["verification_time_network"] is False
    assert decision["tool_archive_checksum_or_container_digest_required"] is True
    assert decision["complete_domain_counts_required"] is True
    assert decision["drift_gate"]
    assert decision["ci_gate"]
    assert decision["independent_reproduction"]
    assert decision["safe_artifacts"]

    evidence = {entry["id"]: entry for entry in program["worked_evidence"]}
    assert evidence["positive-relation-witness"]["kind"] == "design-witness"
    assert evidence["positive-relation-witness"]["result_claimed"] is False
    mutations = {entry["id"]: entry for entry in program["negative_mutations"]}
    assert set(mutations) == REQUIRED_NEGATIVE_MUTATIONS
    assert all(
        entry["mutation"]
        and entry["expected_relation_result"] == "not-equivalent"
        and entry["safe_counterexample_obligation"]
        for entry in mutations.values()
    )


def test_governance_program_is_requirement_backed_acyclic_and_reproduction_gated() -> None:
    program = _load_json(PROGRAM_PATH)
    requirements = {entry["uid"]: entry for entry in program["requirement_dispositions"]}

    assert set(requirements) >= REQUIRED_REQUIREMENTS
    assert requirements["SEM-232"]["disposition"] == "new"
    assert requirements["SEM-232"]["status"] == "DRAFT"
    assert requirements["SEM-232"]["ground_control_id"] == "860b0b1e-55cc-42e6-9da8-b7eeeab7172c"
    assert all(entry["scope"] and entry["rationale"] for entry in requirements.values())

    issues = {entry["key"]: entry for entry in program["implementation_issues"]}
    assert set(issues) == REQUIRED_CHILDREN
    issue_numbers: set[int] = set()
    for key, entry in issues.items():
        assert isinstance(entry["issue_number"], int), key
        assert entry["issue_number"] > 0, key
        assert entry["issue_number"] not in issue_numbers
        issue_numbers.add(entry["issue_number"])
        assert entry["milestone"] == MILESTONE
        assert "SEM-232" in entry["requirements"]
        assert entry["bounded_outcome"]
        assert entry["negative_cases"]
        assert entry["evidence_required"]
        assert entry["explicit_nonclaims"]
        assert set(entry["dependencies"]) <= set(issues)

    incoming = {key: len(entry["dependencies"]) for key, entry in issues.items()}
    outgoing: dict[str, list[str]] = {key: [] for key in issues}
    for key, entry in issues.items():
        for dependency in entry["dependencies"]:
            outgoing[dependency].append(key)
    queue = deque(key for key, degree in incoming.items() if degree == 0)
    visited: list[str] = []
    while queue:
        key = queue.popleft()
        visited.append(key)
        for child in outgoing[key]:
            incoming[child] -= 1
            if incoming[child] == 0:
                queue.append(child)
    assert set(visited) == set(issues)
    assert issues["scientific-documentation"]["dependencies"] == [
        "finite-equivalence-check",
        "independent-reproduction",
    ]
    assert issues["scientific-documentation"]["completion_gate"] == (
        "independently reproduced positive equivalence result"
    )

    boundaries = program["claim_boundaries"]
    assert boundaries["formal_equivalence"] == "not-established-by-issue-811"
    assert boundaries["runtime_realization"] == "separate-downstream-claim"
    assert boundaries["backend_conformance"] == "separate-downstream-claim"
    assert boundaries["policy_noninterference"] == "separate-preservation-theorem-required"
    assert boundaries["predicate_opacity"] == "separate-preservation-theorem-required"


def test_catalog_has_exact_relation_and_bounded_claim_surface() -> None:
    catalog = _load_json(CATALOG_PATH)

    assert catalog["taxonomy_revision"] == "rev13"
    relation = catalog["relations"]["divergence-preserving-branching-bisimulation"]
    assert relation["direction"] == "symmetric"
    assert relation["quantification"]["states"] == "greatest-fixed-point relation"
    assert "explicit divergence" in relation["preservation"]["property"].lower()
    assert relation["relation_parameter_profile_required"] is True
    assert relation["bounded_evidence"]
    assert relation["explicit_non_claims"]

    surfaces = {entry["surface_id"]: entry for entry in catalog["claim_surfaces"]}
    surface = surfaces["participant-crossing-bisimulation"]
    assert surface["intended_relation_ids"] == ["divergence-preserving-branching-bisimulation"]
    assert {
        "policy-noninterference",
        "participant-predicate-opacity",
        "probabilistic-bisimulation",
    } <= set(surface["prohibited_relation_ids"])
    assert surface["evidence_boundary"]
    assert surface["explicit_non_claims"]
