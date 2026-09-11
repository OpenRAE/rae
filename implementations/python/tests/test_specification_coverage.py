"""Integrity tests for the standardized specification-coverage evidence gate."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from tools.check_specification_coverage import (
    EXPECTED_CLASSIFICATIONS,
    EXPECTED_STRATA,
    load_bundle,
    load_bundles,
    recompute_analysis,
    validate_bundle,
    validate_historical_bundle,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _rule_ids(failures: list[object]) -> set[str]:
    return {failure.rule_id for failure in failures}


def _bundle() -> tuple[dict, dict, dict, dict]:
    manifest, protocol, snapshot, analysis = load_bundle(REPO_ROOT)
    return (
        deepcopy(manifest),
        deepcopy(protocol),
        deepcopy(snapshot),
        deepcopy(analysis),
    )


def test_current_bundle_is_clean() -> None:
    _manifest, protocol, snapshot, analysis = _bundle()
    assert validate_bundle(REPO_ROOT, protocol, snapshot, analysis) == []


def test_current_bundle_records_reproducible_and_honest_results() -> None:
    _, protocol, snapshot, analysis = _bundle()
    assert {item["stratum_id"] for item in protocol["coverage_strata"]} == EXPECTED_STRATA
    assert set(protocol["classification_rules"]) == EXPECTED_CLASSIFICATIONS
    assert snapshot["execution_status"] == "complete"
    assert analysis == recompute_analysis(protocol, snapshot, analysis)
    assert analysis["evidence_status"] in {"partial", "demonstrated", "refuted"}


def test_immutable_bundle_index_preserves_concurrent_captures() -> None:
    bundles = load_bundles(REPO_ROOT)
    assert {manifest["revision"] for manifest, *_rest in bundles} >= {"1.0.0", "1.1.0"}
    manifest, *_rest = load_bundle(REPO_ROOT)
    assert manifest["revision"] == "4.0.0"


def test_gate_rejects_missing_strata_and_composite_concepts() -> None:
    _, protocol, snapshot, analysis = _bundle()
    protocol["coverage_strata"] = protocol["coverage_strata"][:-1]
    protocol["concepts"][0]["atomic"] = False

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "specification-coverage-strata",
        "specification-coverage-concept-atomicity",
    }.issubset(_rule_ids(failures))


def test_gate_rejects_broken_joins_and_non_rectangular_stage_results() -> None:
    _, protocol, snapshot, analysis = _bundle()
    snapshot["concept_results"][0]["concept_id"] = "unknown-concept"
    snapshot["concept_results"][1]["stage_results"] = []

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "specification-coverage-concept-results",
        "specification-coverage-stage-coverage",
    }.issubset(_rule_ids(failures))


def test_gate_rejects_false_typed_coverage_and_backend_leakage() -> None:
    _, protocol, snapshot, analysis = _bundle()
    direct = next(
        result for result in snapshot["concept_results"] if result["classification"] == "directly-expressible"
    )
    direct["typed_pointer"] = None
    direct["backend_vocabulary_occurrences"] = [
        {
            "term": "docker",
            "artifact_path": direct["stage_results"][0]["artifact_path"],
            "pointer": "/description",
            "reason": "hidden dependency",
            "allowed": False,
        }
    ]

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "specification-coverage-typed-evidence",
        "specification-coverage-backend-leakage",
    }.issubset(_rule_ids(failures))


def test_gate_rejects_unsafe_paths_and_secret_bearing_locators() -> None:
    _, protocol, snapshot, analysis = _bundle()
    protocol["sources"][0]["locator"] = "https://example.invalid/paper?token=secret"
    snapshot["artifacts"][0]["path"] = "../outside.json"

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "specification-coverage-source-locator",
        "specification-coverage-artifact-path",
    }.issubset(_rule_ids(failures))


def test_gate_rejects_digest_drift_and_stale_analysis() -> None:
    _, protocol, snapshot, analysis = _bundle()
    snapshot["artifacts"][0]["sha256"] = "0" * 64
    analysis["classification_counts"]["missing"] += 1
    analysis["evidence_status"] = "demonstrated"

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "specification-coverage-artifact-digest",
        "specification-coverage-analysis-stale",
    }.issubset(_rule_ids(failures))


def test_gate_rejects_a_snapshot_bound_to_the_wrong_protocol_digest() -> None:
    _, protocol, snapshot, analysis = _bundle()
    snapshot["protocol_sha256"] = "0" * 64

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "specification-coverage-snapshot-join" in _rule_ids(failures)


def test_gate_rejects_missing_concepts_promoted_to_demonstrated() -> None:
    _, protocol, snapshot, analysis = _bundle()
    assert any(result["classification"] == "missing" for result in snapshot["concept_results"])
    analysis["evidence_status"] = "demonstrated"

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "specification-coverage-analysis-stale" in _rule_ids(failures)


def test_gate_rejects_post_execution_reclassification_of_load_bearing_concept() -> None:
    _, protocol, snapshot, analysis = _bundle()
    result = next(item for item in snapshot["concept_results"] if item["concept_id"] == "range-topology")
    result["classification"] = "deliberately-backend-specific"
    result["typed_pointer"] = None
    for stage in result["stage_results"]:
        stage["outcome"] = "not_applicable"
        stage["pointer"] = None
        stage["validation_strength"] = "not-applicable"

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "specification-coverage-classification-boundary",
        "specification-coverage-load-bearing-stages",
    }.issubset(_rule_ids(failures))


def test_gate_rejects_invalid_implementation_identity_and_analysis_join() -> None:
    _, protocol, snapshot, analysis = _bundle()
    surfaces = snapshot.get("implementation_surfaces")
    assert isinstance(surfaces, list) and surfaces
    surfaces[0]["content_sha256"] = "not-a-digest"

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "specification-coverage-implementation-identity",
        "specification-coverage-analysis-stale",
    }.issubset(_rule_ids(failures))


def test_historical_implementation_digest_does_not_bind_the_live_checkout() -> None:
    _, protocol, snapshot, analysis = deepcopy(load_bundles(REPO_ROOT)[0])
    surfaces = snapshot.get("implementation_surfaces")
    assert isinstance(surfaces, list) and surfaces
    surfaces[0]["content_sha256"] = "f" * 64

    failures = validate_historical_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "specification-coverage-implementation-identity" not in _rule_ids(failures)


def test_current_implementation_surface_digest_binds_live_checkout() -> None:
    _, protocol, snapshot, analysis = _bundle()
    snapshot["implementation_surfaces"][0]["content_sha256"] = "f" * 64
    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)
    assert "specification-coverage-implementation-identity" in _rule_ids(failures)
