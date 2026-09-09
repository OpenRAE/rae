"""Behavioral regressions for current replay and historical evidence retention."""

from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def test_old_output_digest_pairs_do_not_substitute_for_replay():
    from tools.formal_semantic_validation._replay import _replay_observation_matches

    old = {
        "actual_outcome": "accepted",
        "diagnostic_kind": None,
        "result_digest": "ba0ecbfcb3090ffd6b660cb51324fafcd47ca8dedbbb985e98b6e7f64f8cc25b",
    }
    changed = {**old, "result_digest": "5332666a0299d2c303d7a7da4b56dfd309cebf021af187b063ef597cf81bf40a"}
    assert not _replay_observation_matches("semantic-resolved-objective", old, changed)


def test_historical_integrated_release_does_not_execute_current_code(monkeypatch):
    from tools.formal_semantic_validation import _production, _releases, _retest
    from tools.formal_semantic_validation._loading import load_release_bundles

    release = next(r for r in load_release_bundles(ROOT) if r.manifest["revision"] == "3.0.0")

    def forbidden(*args, **kwargs):
        raise AssertionError("historical observations are not current-code evidence")

    monkeypatch.setattr(_retest, "replay_case", forbidden)
    monkeypatch.setattr(_production, "_run_production_evidence_cli", forbidden)
    assert _releases.validate_release_bundle(ROOT, release) == []


def test_latest_current_release_is_versioned_and_strict(monkeypatch):
    from tools.formal_semantic_validation import _retest
    from tools.formal_semantic_validation._loading import load_retest_bundle
    from tools.formal_semantic_validation._releases import validate_retest_bundle

    release, protocol, corpus, snapshot, analysis = load_retest_bundle(ROOT)
    assert release.manifest["revision"] == "4.0.0"
    original = _retest.replay_case

    def changed_result(root, case):
        result = original(root, case)
        if case["case_id"] == "schema-valid-control":
            result["result_digest"] = "f" * 64
        return result

    monkeypatch.setattr(_retest, "replay_case", changed_result)
    failures = validate_retest_bundle(ROOT, release, protocol, corpus, snapshot, analysis)
    assert "formal-validation-replay-drift" in {f.rule_id for f in failures}


def test_current_release_requires_truthful_implementation_provenance():
    from tools.formal_semantic_validation._loading import load_retest_bundle
    from tools.formal_semantic_validation._releases import validate_retest_bundle

    release, protocol, corpus, snapshot, analysis = load_retest_bundle(ROOT)
    snapshot = deepcopy(snapshot)
    assert "source_state" in snapshot
    snapshot["source_state"]["implementation_digest"] = "0" * 64
    failures = validate_retest_bundle(ROOT, release, protocol, corpus, snapshot, analysis)
    assert "research-evidence-source-state" in {f.rule_id for f in failures}


def test_current_production_evidence_replay_failure_is_not_hidden(monkeypatch):
    from raes_processor import satisfiability
    from tools.formal_semantic_validation._loading import load_retest_bundle
    from tools.formal_semantic_validation._releases import validate_retest_bundle

    def fail(*args, **kwargs):
        raise ValueError("seeded production replay failure")

    monkeypatch.setattr(satisfiability, "replay_satisfiability_evidence", fail)
    release, protocol, corpus, snapshot, analysis = load_retest_bundle(ROOT)
    failures = validate_retest_bundle(ROOT, release, protocol, corpus, snapshot, analysis)
    assert "formal-validation-production-replay" in {f.rule_id for f in failures}


def test_specification_current_capture_does_not_accept_old_artifact_digest():
    from tools.check_specification_coverage import load_bundle, validate_bundle

    manifest, protocol, snapshot, analysis = load_bundle(ROOT)
    assert manifest["revision"] == "2.0.0"
    snapshot = deepcopy(snapshot)
    artifact = next(a for a in snapshot["artifacts"] if a["artifact_id"] == "port-range-sdl")
    artifact["sha256"] = "a27c7a64e0c5c618fadaccafdf1a4e71600170a8b77b983190822b5141f00dec"
    failures = validate_bundle(ROOT, protocol, snapshot, analysis)
    assert "specification-coverage-artifact-digest" in {f.rule_id for f in failures}


def test_historical_specification_evidence_is_integrity_checked_without_execution(monkeypatch):
    from tools import check_specification_coverage as coverage
    from tools.specification_coverage import _artifacts

    manifest, protocol, snapshot, analysis = coverage.load_bundles(ROOT)[0]

    def forbidden(*args, **kwargs):
        raise AssertionError("must not execute an archived artifact on current code")

    monkeypatch.setattr(_artifacts, "_execute_artifact", forbidden)
    assert coverage.validate_historical_bundle(ROOT, protocol, snapshot, analysis) == []


@pytest.mark.parametrize("value", ["0" * 64, "../outside"])
def test_historical_specification_archive_pin_tampering_fails(value):
    from tools import check_specification_coverage as coverage

    manifest, protocol, snapshot, analysis = coverage.load_bundles(ROOT)[0]
    snapshot = deepcopy(snapshot)
    snapshot["artifacts"][0]["sha256"] = value
    failures = coverage.validate_historical_bundle(ROOT, protocol, snapshot, analysis)
    assert "specification-coverage-artifact-digest" in {f.rule_id for f in failures}


@pytest.mark.parametrize("records", [[], [("one", {"revision": "4.0.0"}), ("two", {"revision": "4.0.0"})]])
def test_current_release_selection_rejects_empty_or_ambiguous_sets(records):
    from tools.research_evidence import current_release_path

    with pytest.raises(ValueError):
        current_release_path(records)


def test_current_release_selection_keeps_one_whole_release():
    from tools.research_evidence import current_release_path

    assert current_release_path([("new", {"revision": "4.0.0"}), ("old", {"revision": "3.0.0"})]) == "new"


@pytest.mark.parametrize("family", ["formal", "coverage"])
def test_future_evidence_versions_fail_closed(monkeypatch, family):
    from tools import check_specification_coverage
    from tools.formal_semantic_validation import _loading

    module = _loading if family == "formal" else check_specification_coverage
    monkeypatch.setattr(module, "load_index_records", lambda *args, **kwargs: [("future.json", {"revision": "99.0.0"})])
    loader = _loading.load_release_bundles if family == "formal" else check_specification_coverage.load_bundles
    with pytest.raises(ValueError, match="supported|current"):
        loader(ROOT)


def test_current_formal_release_cannot_request_historical_validation():
    from tools.formal_semantic_validation._loading import load_retest_bundle
    from tools.formal_semantic_validation._releases import validate_retest_bundle

    release, protocol, corpus, snapshot, analysis = load_retest_bundle(ROOT)
    failures = validate_retest_bundle(ROOT, release, protocol, corpus, snapshot, analysis, replay_current=False)
    assert {f.rule_id for f in failures} == {"formal-validation-current-replay-required"}


@pytest.mark.parametrize(
    "state",
    [
        None,
        {},
        {"profile": "future"},
        {
            "profile": "python-reference-source/v1",
            "base_revision": "0" * 40,
            "checkout_state": [],
            "implementation_digest": "0" * 64,
        },
    ],
)
def test_source_state_malformed_values_fail_closed(state):
    from tools.research_evidence import source_state_failures

    assert source_state_failures(ROOT, state, "capture.json", current=True)


def test_historical_supplement_never_runs_current_analyzer(monkeypatch):
    from raes_processor import satisfiability
    from tools.formal_semantic_validation._loading import load_release_bundles
    from tools.formal_semantic_validation._releases import validate_release_bundle

    def forbidden(*args, **kwargs):
        raise AssertionError("historical supplement must not claim current execution")

    monkeypatch.setattr(satisfiability, "analyze_scenario_file", forbidden)
    release = next(r for r in load_release_bundles(ROOT) if r.manifest["revision"] == "2.0.0")
    assert validate_release_bundle(ROOT, release) == []


def test_current_cli_result_drift_is_rejected(monkeypatch):
    from tools.formal_semantic_validation import _production
    from tools.formal_semantic_validation._loading import load_retest_bundle
    from tools.formal_semantic_validation._releases import validate_retest_bundle

    original = _production._run_production_evidence_cli

    def changed_cli(*args, **kwargs):
        payload = original(*args, **kwargs)
        payload["source"]["byte_digest"] = "sha256:" + "0" * 64
        return payload

    monkeypatch.setattr(_production, "_run_production_evidence_cli", changed_cli)
    release, protocol, corpus, snapshot, analysis = load_retest_bundle(ROOT)
    failures = validate_retest_bundle(ROOT, release, protocol, corpus, snapshot, analysis)
    assert "formal-validation-production-evidence-join" in {f.rule_id for f in failures}


def test_current_cli_must_emit_the_complete_pinned_payload(monkeypatch):
    from tools.formal_semantic_validation import _production
    from tools.formal_semantic_validation._loading import load_retest_bundle
    from tools.formal_semantic_validation._releases import validate_retest_bundle

    original = _production._run_production_evidence_cli

    def omit_default(*args, **kwargs):
        payload = original(*args, **kwargs)
        if payload["profile"] == "scenario-satisfiability-evidence/v1":
            assert payload["imports"] == []
            del payload["imports"]
        return payload

    monkeypatch.setattr(_production, "_run_production_evidence_cli", omit_default)
    release, protocol, corpus, snapshot, analysis = load_retest_bundle(ROOT)
    failures = validate_retest_bundle(ROOT, release, protocol, corpus, snapshot, analysis)
    assert "formal-validation-production-evidence-join" in {f.rule_id for f in failures}


def test_archive_content_tampering_fails_even_when_manifest_pin_is_unchanged(monkeypatch):
    from tools import check_specification_coverage as coverage
    from tools.specification_coverage import _artifacts

    original = _artifacts.load_bounded_json_object

    def changed_archive(*args, **kwargs):
        payload = original(*args, **kwargs)
        if "content_base64" in payload:
            payload["content_base64"] = "dGFtcGVyZWQ="
        return payload

    monkeypatch.setattr(_artifacts, "load_bounded_json_object", changed_archive)
    _, protocol, snapshot, analysis = coverage.load_bundles(ROOT)[0]
    failures = coverage.validate_historical_bundle(ROOT, protocol, snapshot, analysis)
    assert "specification-coverage-artifact-digest" in {f.rule_id for f in failures}


@pytest.mark.parametrize("family", ["formal", "coverage"])
@pytest.mark.parametrize("removed", ["current", "history"])
def test_no_capture_can_be_silently_dropped(monkeypatch, family, removed):
    from tools import check_specification_coverage
    from tools.formal_semantic_validation import _loading

    module = _loading if family == "formal" else check_specification_coverage
    revisions = (
        ["1.0.0", "1.1.0", "1.2.0", "2.0.0", "3.0.0", "4.0.0"] if family == "formal" else ["1.0.0", "1.1.0", "2.0.0"]
    )
    revisions.pop(-1 if removed == "current" else 0)
    monkeypatch.setattr(
        module,
        "load_index_records",
        lambda *args, **kwargs: [(revision, {"revision": revision}) for revision in revisions],
    )
    loader = _loading.load_release_bundles if family == "formal" else check_specification_coverage.load_bundles
    with pytest.raises(ValueError, match="supported|current"):
        loader(ROOT)


@pytest.mark.parametrize("change", ["missing", "old_digest", "unknown_field", "baseline_pin"])
def test_current_coverage_requires_exact_baseline_deviations(change):
    from tools.check_specification_coverage import load_bundle, validate_bundle

    _, protocol, snapshot, analysis = load_bundle(ROOT)
    if change == "missing":
        snapshot["deviations"].pop()
    elif change == "old_digest":
        snapshot["deviations"][0]["baseline_sha256"] = "0" * 64
    elif change == "unknown_field":
        snapshot["deviations"][0]["trust_me"] = True
    else:
        snapshot["baseline"]["release_sha256"] = "0" * 64
    assert "specification-coverage-baseline-drift" in {
        f.rule_id for f in validate_bundle(ROOT, protocol, snapshot, analysis)
    }


def test_current_coverage_preserves_untested_slots_without_claiming_capability_absence():
    from tools.check_specification_coverage import load_bundle

    _, protocol, snapshot, analysis = load_bundle(ROOT)
    missing = [item for item in snapshot["concept_results"] if item["classification"] == "missing"]
    assert len(snapshot["concept_results"]) == len(protocol["concepts"]) == 16
    assert len(missing) == 3
    assert all(stage["outcome"] == "not_run" for item in missing for stage in item["stage_results"])
    assert analysis["evidence_status"] == "partial"


def test_historical_archive_does_not_require_a_live_source_file(tmp_path):
    import shutil

    from tools.check_specification_coverage import load_bundles
    from tools.specification_coverage._artifacts import _validate_artifacts

    _, _, snapshot, _ = load_bundles(ROOT)[0]
    archive = Path("docs/research/specification-coverage/historical-artifacts")
    shutil.copytree(ROOT / archive, tmp_path / archive)
    assert all(not (tmp_path / item["path"]).exists() for item in snapshot["artifacts"])
    failures = []
    artifacts, executed = _validate_artifacts(tmp_path, snapshot, failures, replay_current=False)
    assert failures == []
    assert len(artifacts) == len(executed) == 6
    failures = []
    _validate_artifacts(tmp_path, snapshot, failures)
    assert {f.rule_id for f in failures} == {"specification-coverage-artifact-path"}


def test_classification_retirement_has_a_recorded_adr_001_amendment():
    import hashlib

    import yaml
    from tools.check_adr_immutability import amendment_refs, canonical_content

    path = ROOT / "docs/decisions/adrs/adr-001-scenario-description-language.md"
    content = path.read_text()
    index = yaml.safe_load((ROOT / "docs/decisions/adrs/adr-index.yaml").read_text())
    entry = next(item for item in index["adrs"] if item["id"] == "ADR-001")
    assert "#989" in amendment_refs(content)
    assert "#989" in {item["ref"] for item in entry["amendments"]}
    assert entry["pin"] == hashlib.sha256(canonical_content(content).encode()).hexdigest()
