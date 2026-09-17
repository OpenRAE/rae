"""REV1 scientific-scenario completeness profile contract tests."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raes.parser import parse_sdl  # noqa: E402
from raes_conformance.conformance import (  # noqa: E402
    _fixture_case_diagnostics,
    validate_contract_payload,
)
from raes_contracts.contracts import schema_bundle  # noqa: E402
from raes_contracts.scientific_completeness import (  # noqa: E402
    DeliveryStatus,
    ProfileDisposition,
    ScientificCompletenessAssessmentModel,
    ScientificCompletenessTaxonomyModel,
    evaluate_profile_completeness,
    load_scientific_completeness_assessment,
    load_scientific_completeness_taxonomy,
)
from tools.check_scientific_scenario_completeness import (  # noqa: E402
    _validate_contract_evidence,
    _validate_evidence_paths,
    _validate_nonclaims,
    _validate_profile_examples,
    _validate_profile_set,
    _validate_required_exclusions,
    _validate_summary,
)
from tools.check_scientific_scenario_completeness import (
    evaluate as evaluate_policy,
)

TAXONOMY_PATH = REPO_ROOT / "contracts/profiles/scientific-completeness/scientific-scenario-completeness-rev1.json"
ASSESSMENT_PATH = REPO_ROOT / "contracts/profiles/scientific-completeness/delivery-assessment-2026-07-12.json"


def _taxonomy_payload() -> dict[str, object]:
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def _assessment_payload() -> dict[str, object]:
    return json.loads(ASSESSMENT_PATH.read_text(encoding="utf-8"))


def test_rev1_taxonomy_and_assessment_are_valid_and_join_exactly() -> None:
    taxonomy = load_scientific_completeness_taxonomy()
    assessment = load_scientific_completeness_assessment()

    assert taxonomy.profile_family == "scientific-scenario-completeness"
    assert taxonomy.revision == "rev1"
    assert assessment.profile_family == taxonomy.profile_family
    assert assessment.taxonomy_revision == taxonomy.revision
    assert {profile.profile_id for profile in taxonomy.profiles} == {
        "valid-sdl-fragment",
        "deployable-scenario-intent",
        "participant-evaluation-scenario",
        "controlled-experiment-scenario",
        "reproducible-benchmark-study-input",
    }
    assert {item.concern_id for item in assessment.concerns} == {concern.concern_id for concern in taxonomy.concerns}


def test_both_completeness_contracts_are_in_the_published_schema_bundle() -> None:
    bundle = schema_bundle()
    assert "scientific-completeness-taxonomy-v1" in bundle
    assert "scientific-completeness-assessment-v1" in bundle
    taxonomy_invariants = {item["id"] for item in bundle["scientific-completeness-taxonomy-v1"]["x-raes-invariants"]}
    assessment_invariants = {
        item["id"] for item in bundle["scientific-completeness-assessment-v1"]["x-raes-invariants"]
    }
    assert taxonomy_invariants == {
        "scientific-completeness-behavioral-claim-resolution",
        "scientific-completeness-taxonomy-rectangular",
    }
    assert assessment_invariants == {
        "scientific-completeness-assessment-status-evidence",
        "scientific-completeness-taxonomy-assessment-join",
    }


@pytest.mark.parametrize(
    ("contract_id", "fixture", "valid"),
    [
        ("scientific-completeness-taxonomy-v1", "valid/minimal.json", True),
        ("scientific-completeness-taxonomy-v1", "invalid/missing-disposition.json", False),
        ("scientific-completeness-assessment-v1", "valid/minimal.json", True),
        ("scientific-completeness-assessment-v1", "invalid/external-without-binding.json", False),
    ],
)
def test_published_completeness_fixtures_exercise_semantic_validation(
    contract_id: str,
    fixture: str,
    valid: bool,
) -> None:
    path = REPO_ROOT / "contracts/fixtures/profiles" / contract_id / fixture
    diagnostics = _fixture_case_diagnostics(contract_id, json.loads(path.read_text(encoding="utf-8")))
    assert (not diagnostics) is valid


def test_issue_required_concerns_are_atomic_and_present() -> None:
    required_concerns = {
        "authored-observed-state-separation",
        "scoped-specificity-open-world-intent",
        "parameter-typing",
        "factor-declaration",
        "controlled-allocation",
        "randomization-policy",
        "seed-preservation",
        "propositions",
        "assertions",
        "workflow-compensation",
        "backend-teardown-reconciliation",
        "manual-rollback",
        "time-domain-declaration",
        "clock-declaration",
        "temporal-ordering-causality",
        "deadlines-and-windows",
        "pacing-and-synchronization",
        "participant-episode-reset",
        "participant-budgets",
        "reference-trajectories",
        "hidden-benchmark-assets",
        "verifier-and-adjudication",
        "graded-reward-in-sdl",
        "credential-intent",
        "credential-materialization",
        "host-architecture-constraints",
        "substrate-constraints",
        "vulnerability-inventory",
        "weakness-exploitability-semantics",
        "flexible-step-tooling",
        "portable-behavior-contracts",
        "behavioral-relation-taxonomy",
    }
    taxonomy = load_scientific_completeness_taxonomy()
    assert required_concerns <= {concern.concern_id for concern in taxonomy.concerns}


def test_completeness_is_computed_and_does_not_overclaim_stronger_profiles() -> None:
    outcomes = {
        result.profile_id: result
        for result in evaluate_profile_completeness(
            load_scientific_completeness_taxonomy(),
            load_scientific_completeness_assessment(),
        )
    }

    assert outcomes["valid-sdl-fragment"].complete
    assert outcomes["valid-sdl-fragment"].blocking_concerns == ()
    for profile_id in {
        "deployable-scenario-intent",
        "participant-evaluation-scenario",
        "controlled-experiment-scenario",
        "reproducible-benchmark-study-input",
    }:
        assert not outcomes[profile_id].complete
        assert outcomes[profile_id].blocking_concerns


def test_every_complete_profile_has_a_production_validated_minimal_example() -> None:
    taxonomy = load_scientific_completeness_taxonomy()
    outcomes = {
        result.profile_id: result
        for result in evaluate_profile_completeness(taxonomy, load_scientific_completeness_assessment())
    }
    for profile in taxonomy.profiles:
        if not outcomes[profile.profile_id].complete:
            continue
        assert profile.example_refs
        for example_ref in profile.example_refs:
            scenario = parse_sdl((REPO_ROOT / example_ref).read_text(encoding="utf-8"))
            assert scenario.name


def test_taxonomy_rejects_missing_rectangular_disposition() -> None:
    payload = _taxonomy_payload()
    missing_id = payload["concerns"][0]["concern_id"]
    del payload["profiles"][0]["dispositions"][missing_id]
    with pytest.raises(ValidationError, match="exactly cover taxonomy concerns"):
        ScientificCompletenessTaxonomyModel.model_validate(payload)


def test_assessment_rejects_duplicate_or_missing_concern_coverage() -> None:
    payload = _assessment_payload()
    payload["concerns"].append(deepcopy(payload["concerns"][0]))
    with pytest.raises(ValidationError, match="assessment concern ids must be unique"):
        ScientificCompletenessAssessmentModel.model_validate(payload)


def test_join_rejects_missing_assessment_concern() -> None:
    assessment_payload = _assessment_payload()
    assessment_payload["concerns"].pop()
    assessment = ScientificCompletenessAssessmentModel.model_validate(assessment_payload)
    with pytest.raises(ValueError, match="exactly cover taxonomy concerns"):
        evaluate_profile_completeness(load_scientific_completeness_taxonomy(), assessment)


def test_external_contract_status_requires_named_binding_and_contract_evidence() -> None:
    payload = _assessment_payload()
    item = next(item for item in payload["concerns"] if item["status"] == DeliveryStatus.EXTERNAL_CONTRACT)
    item["binding_obligation"] = None
    item["external_contract_refs"] = []
    with pytest.raises(ValidationError, match="external-contract status requires"):
        ScientificCompletenessAssessmentModel.model_validate(payload)


def test_external_contract_status_requires_a_satisfiability_witness() -> None:
    payload = _assessment_payload()
    item = next(item for item in payload["concerns"] if item["status"] == DeliveryStatus.EXTERNAL_CONTRACT)
    item["satisfiability_witness_refs"] = {}
    with pytest.raises(ValidationError, match="satisfiability witnesses"):
        ScientificCompletenessAssessmentModel.model_validate(payload)


def test_external_contract_witnesses_are_exactly_bound_and_conforming() -> None:
    assessment = load_scientific_completeness_assessment()
    for item in assessment.concerns:
        if item.status is not DeliveryStatus.EXTERNAL_CONTRACT:
            continue
        assert set(item.satisfiability_witness_refs) == set(item.external_contract_refs)
        for contract_id, witness_ref in item.satisfiability_witness_refs.items():
            payload = json.loads((REPO_ROOT / witness_ref).read_text(encoding="utf-8"))
            assert validate_contract_payload(contract_id, payload) == ()


def test_external_contract_rejects_a_witness_bound_to_the_wrong_contract() -> None:
    payload = _assessment_payload()
    item = next(item for item in payload["concerns"] if item["status"] == DeliveryStatus.EXTERNAL_CONTRACT)
    witness = next(iter(item["satisfiability_witness_refs"].values()))
    item["satisfiability_witness_refs"] = {"experiment-run-v1": witness}
    with pytest.raises(ValidationError, match="exactly one satisfiability witness"):
        ScientificCompletenessAssessmentModel.model_validate(payload)


def test_implemented_status_requires_executable_evidence() -> None:
    payload = _assessment_payload()
    item = next(item for item in payload["concerns"] if item["status"] == DeliveryStatus.IMPLEMENTED)
    item["evidence"] = [
        {
            "kind": "normative-spec",
            "path": "specs/sdl/document-model.md",
            "claim": "Meaning only, not executable delivery.",
        }
    ]
    with pytest.raises(ValidationError, match="implemented status requires executable evidence"):
        ScientificCompletenessAssessmentModel.model_validate(payload)


def test_deliberate_exclusion_cannot_satisfy_a_required_profile_concern() -> None:
    taxonomy_payload = _taxonomy_payload()
    assessment_payload = _assessment_payload()
    concern = next(item for item in assessment_payload["concerns"] if item["status"] == "deliberately-excluded")
    profile = taxonomy_payload["profiles"][0]
    profile["dispositions"][concern["concern_id"]] = ProfileDisposition.REQUIRED
    taxonomy = ScientificCompletenessTaxonomyModel.model_validate(taxonomy_payload)
    assessment = ScientificCompletenessAssessmentModel.model_validate(assessment_payload)
    outcome = next(
        item for item in evaluate_profile_completeness(taxonomy, assessment) if item.profile_id == profile["profile_id"]
    )
    assert not outcome.complete
    assert concern["concern_id"] in outcome.blocking_concerns


def test_repository_policy_gate_accepts_current_matrix_and_nonclaims() -> None:
    assert evaluate_policy(REPO_ROOT) == []


def test_policy_rejects_an_incomplete_rev1_profile_set() -> None:
    payload = _taxonomy_payload()
    payload["profiles"].pop()
    taxonomy = ScientificCompletenessTaxonomyModel.model_validate(payload)

    failures = _validate_profile_set(taxonomy)

    assert {failure.rule_id for failure in failures} == {"scientific-completeness-profile-set"}


def test_policy_rejects_a_missing_evidence_path() -> None:
    payload = _assessment_payload()
    item = next(item for item in payload["concerns"] if item["evidence"])
    item["evidence"][0]["path"] = "contracts/does-not-exist.json"
    assessment = ScientificCompletenessAssessmentModel.model_validate(payload)

    failures = _validate_evidence_paths(REPO_ROOT, assessment)

    assert "scientific-completeness-evidence-missing" in {failure.rule_id for failure in failures}


def test_policy_rejects_contract_evidence_at_the_wrong_published_path() -> None:
    payload = _assessment_payload()
    item = next(item for item in payload["concerns"] if item["status"] == DeliveryStatus.EXTERNAL_CONTRACT)
    item["evidence"][0]["path"] = "contracts/README.md"
    assessment = ScientificCompletenessAssessmentModel.model_validate(payload)

    failures = _validate_contract_evidence(REPO_ROOT, assessment)

    assert "scientific-completeness-contract-evidence-mismatch" in {failure.rule_id for failure in failures}


def test_policy_enforces_complete_and_incomplete_profile_example_rules() -> None:
    payload = _taxonomy_payload()
    payload["profiles"][0]["example_refs"] = []
    payload["profiles"][1]["example_refs"] = ["examples/completeness/rev1/valid-sdl-fragment/minimal.sdl.yaml"]
    taxonomy = ScientificCompletenessTaxonomyModel.model_validate(payload)
    outcomes = evaluate_profile_completeness(taxonomy, load_scientific_completeness_assessment())

    failures = _validate_profile_examples(REPO_ROOT, taxonomy, outcomes)

    assert {
        "scientific-completeness-example-required",
        "scientific-completeness-example-overclaim",
    }.issubset({failure.rule_id for failure in failures})


def test_policy_rejects_eroded_explicit_nonclaims() -> None:
    payload = _taxonomy_payload()
    for profile in payload["profiles"]:
        profile["explicit_non_claims"] = ["No additional claim."]
    taxonomy = ScientificCompletenessTaxonomyModel.model_validate(payload)

    failures = _validate_nonclaims(taxonomy)

    assert {failure.rule_id for failure in failures} == {"scientific-completeness-nonclaim-coverage"}


def test_policy_rejects_reader_summary_drift(tmp_path: Path) -> None:
    spec_path = tmp_path / "specs/sdl/scientific-scenario-completeness.md"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text("# Stale summary\n", encoding="utf-8")
    outcomes = evaluate_profile_completeness(
        load_scientific_completeness_taxonomy(),
        load_scientific_completeness_assessment(),
    )

    failures = _validate_summary(tmp_path, outcomes)

    assert {failure.rule_id for failure in failures} == {"scientific-completeness-summary-drift"}


def test_policy_rejects_a_required_deliberate_exclusion() -> None:
    payload = _assessment_payload()
    item = next(item for item in payload["concerns"] if item["concern_id"] == "source-profile-validity")
    item["status"] = DeliveryStatus.DELIBERATELY_EXCLUDED
    item["exclusion_rationale"] = "Mutation fixture for the policy rule."
    assessment = ScientificCompletenessAssessmentModel.model_validate(payload)

    failures = _validate_required_exclusions(load_scientific_completeness_taxonomy(), assessment)

    assert {failure.rule_id for failure in failures} == {"scientific-completeness-required-exclusion"}
