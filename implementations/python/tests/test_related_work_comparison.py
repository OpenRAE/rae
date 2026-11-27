"""Reproducible related-work comparison integrity tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from tools.check_related_work_comparison import (
    EXPECTED_AXIS_IDS,
    load_bundle,
    render_publication,
    validate_bundle,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _rule_ids(failures: list[object]) -> set[str]:
    return {failure.rule_id for failure in failures}


def _bundle() -> tuple[dict, dict, dict]:
    protocol, snapshot, analysis = load_bundle(REPO_ROOT)
    return deepcopy(protocol), deepcopy(snapshot), deepcopy(analysis)


def test_current_bundle_is_clean() -> None:
    assert validate_bundle(REPO_ROOT, *_bundle()) == []


def test_protocol_uses_all_required_axes_and_independent_systems() -> None:
    protocol, _, _ = _bundle()

    assert {axis["axis_id"] for axis in protocol["axes"]} == EXPECTED_AXIS_IDS
    assert {system["system_id"] for system in protocol["systems"]} == {
        "a" + "ces",
        "cacao-v2",
        "crack",
        "cyber-dem",
        "cyber-fom",
        "cyborg",
        "ocr-sdl",
        "vsdl",
    }


def test_gate_rejects_a_missing_system_axis_cell() -> None:
    protocol, snapshot, analysis = _bundle()
    snapshot["observations"].pop()

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "related-work-observations-rectangular" in _rule_ids(failures)


def test_gate_rejects_missing_or_non_primary_cell_evidence() -> None:
    protocol, snapshot, analysis = _bundle()
    snapshot["observations"][0]["evidence_refs"] = []

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "related-work-observation-evidence" in _rule_ids(failures)


def test_gate_requires_a_reproducible_rationale_and_explicit_limit_for_every_cell() -> None:
    protocol, snapshot, analysis = _bundle()
    snapshot["observations"][0]["rationale"] = ""
    snapshot["observations"][0]["limitations"] = []

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "related-work-observation-rationale",
        "related-work-observation-limitations",
    }.issubset(_rule_ids(failures))


def test_gate_rejects_mutable_or_unpinned_sources() -> None:
    protocol, snapshot, analysis = _bundle()
    source = next(item for item in snapshot["sources"] if item["kind"] == "git")
    source["revision"] = "main"

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "related-work-source-pin" in _rule_ids(failures)


def test_gate_rejects_composite_system_identities() -> None:
    protocol, snapshot, analysis = _bundle()
    protocol["systems"][0]["name"] = "Cyber DEM/FOM"

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "related-work-composite-system" in _rule_ids(failures)


def test_gate_rejects_secret_bearing_locators_and_unsafe_paths() -> None:
    protocol, snapshot, analysis = _bundle()
    snapshot["sources"][0]["locator"] = "https://example.test/source?access_token=secret"
    snapshot["sources"][0]["artifact_path"] = "../outside.json"

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "related-work-source-locator-secret",
        "related-work-source-path",
    }.issubset(_rule_ids(failures))


def test_gate_requires_rectangular_authoring_task_and_negative_case_coverage() -> None:
    protocol, snapshot, analysis = _bundle()
    snapshot["task_observations"] = [
        item
        for item in snapshot["task_observations"]
        if not (item["system_id"] == "a" + "ces" and item["case_id"] == "negative-dangling-reference")
    ]

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "related-work-task-observations-rectangular" in _rule_ids(failures)


def test_gate_requires_reproducible_task_rationales_and_limits() -> None:
    protocol, snapshot, analysis = _bundle()
    snapshot["task_observations"][0]["rationale"] = ""
    snapshot["task_observations"][0]["limitations"] = []

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "related-work-task-observation-rationale",
        "related-work-task-observation-limitations",
    }.issubset(_rule_ids(failures))


def test_gate_recomputes_weight_profiles_and_exposes_ranking_reversals() -> None:
    protocol, snapshot, analysis = _bundle()
    analysis["sensitivity"]["ranking_reversal_observed"] = False

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "related-work-sensitivity-drift" in _rule_ids(failures)


def test_gate_rejects_stale_publication_output(tmp_path: Path) -> None:
    protocol, snapshot, analysis = _bundle()
    publication = tmp_path / "docs/explain/sdl/related-work-comparison.md"
    publication.parent.mkdir(parents=True)
    publication.write_text("# Stale publication\n", encoding="utf-8")

    failures = validate_bundle(tmp_path, protocol, snapshot, analysis, validate_paths=False)

    assert "related-work-publication-drift" in _rule_ids(failures)
    assert "No overall winner" in render_publication(protocol, snapshot, analysis)


def test_gate_rejects_an_unsupported_highest_quality_claim() -> None:
    protocol, snapshot, analysis = _bundle()
    claim = next(item for item in analysis["claims"] if item["kind"] == "scope-qualified-breadth")
    claim["statement"] = "RAES has the highest quality."

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "related-work-claim-overreach" in _rule_ids(failures)


def test_gate_requires_falsification_first_evidence_records_for_public_claims() -> None:
    protocol, snapshot, analysis = _bundle()
    claim = analysis["claims"][0]
    claim["evidence_status"] = "untested"
    claim["threats_to_validity"] = []
    claim["falsification"]["evidence_artifact_refs"] = []

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "related-work-claim-evidence-gate" in _rule_ids(failures)


def test_gate_recomputes_public_claim_derivations_from_frozen_observations() -> None:
    protocol, snapshot, analysis = _bundle()
    claim = next(item for item in analysis["claims"] if item["kind"] == "scope-qualified-breadth")
    claim["derivation"]["max_score"] = 0

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "related-work-claim-derivation" in _rule_ids(failures)


def test_publication_exposes_each_claims_evidence_status() -> None:
    protocol, snapshot, analysis = _bundle()

    publication = render_publication(protocol, snapshot, analysis)

    for claim in analysis["claims"]:
        assert f"Evidence status: `{claim['evidence_status']}`." in publication


def test_gate_rejects_historical_delivery_scores_without_executable_evidence() -> None:
    protocol, snapshot, analysis = _bundle()
    non_executable_source = next(
        source for source in snapshot["sources"] if source["source_id"] == "a" + "ces-scientific-assessment"
    )
    assert non_executable_source["evidence_class"] == "normative"
    observation = next(
        item
        for item in snapshot["observations"]
        if item["system_id"] == "a" + "ces" and item["axis_id"] == "implementation-maturity"
    )
    observation["evidence_refs"] = [
        {
            "source_id": non_executable_source["source_id"],
            "locator": "implemented, partial, missing, external, and excluded rows",
        }
    ]

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "related-work-raes-executable-evidence" in _rule_ids(failures)


def test_an_invalid_bundle_artifact_is_a_bundle_failure(tmp_path: Path) -> None:
    from tools.check_related_work_comparison import PROTOCOL_PATH, evaluate

    artifact = tmp_path / PROTOCOL_PATH
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"axes": [], "axes": []}', encoding="utf-8")

    assert _rule_ids(evaluate(tmp_path)) == {"related-work-bundle-invalid"}


def test_a_defect_while_loading_the_bundle_is_not_reported_as_an_invalid_bundle(monkeypatch) -> None:
    import tools.check_related_work_comparison as gate

    def defective(*_args, **_kwargs):
        raise ValueError("loader defect")

    monkeypatch.setattr(gate, "load_bounded_json_object", defective)
    with pytest.raises(ValueError, match="loader defect"):
        gate.evaluate(REPO_ROOT)
