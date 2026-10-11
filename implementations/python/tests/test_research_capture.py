"""Branch captures coexist without allocating the same numbered release."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from tools.evidence_bundle_index import load_index_records
from tools.research_capture import FAMILIES, publish_capture, record_capture
from tools.research_evidence import capture_identity, current_release_path, is_capture, validate_inventory

ROOT = Path(__file__).resolve().parents[3]
FAMILY = "specification-coverage"
FOLDER = Path("docs/research") / FAMILY
TEMPLATE = (FOLDER / "bundles/raes-standardized-specification-coverage-issue-1366-sync-v75.json").as_posix()


@pytest.fixture
def capture_repo(tmp_path):
    shutil.copytree(ROOT / FOLDER, tmp_path / FOLDER)
    return tmp_path


def records(root):
    return load_index_records(
        root,
        index_path=(FOLDER / "bundle-manifest.json").as_posix(),
        schema_version=FAMILIES[FAMILY],
        directory_key="bundles_directory",
        max_bytes=2 * 1024 * 1024,
    )


def test_two_branches_record_distinct_captures_without_shared_edits(capture_repo):
    baseline = {p.relative_to(capture_repo): p.read_bytes() for p in capture_repo.rglob("*") if p.is_file()}
    original = json.loads((capture_repo / TEMPLATE).read_text())
    paths = []
    for branch in ("left", "right"):
        snapshot = json.loads((capture_repo / original["snapshot_path"]).read_text())
        analysis = json.loads((capture_repo / original["analysis_path"]).read_text())
        snapshot["snapshot_id"] = branch
        analysis["snapshot_id"] = branch
        (capture_repo / f"{branch}-snapshot.json").write_text(json.dumps(snapshot))
        (capture_repo / f"{branch}-analysis.json").write_text(json.dumps(analysis))
        paths.append(
            record_capture(
                capture_repo,
                FAMILY,
                TEMPLATE,
                snapshot_path=f"{branch}-snapshot.json",
                analysis_path=f"{branch}-analysis.json",
            )
        )
    assert paths[0] != paths[1]
    indexed = records(capture_repo)
    validate_inventory(capture_repo, FAMILY, indexed)
    assert all(path in dict(indexed) for path in paths)
    assert all((capture_repo / path).read_bytes() == content for path, content in baseline.items())


def test_record_is_idempotent_and_preserves_observations(capture_repo):
    path = record_capture(capture_repo, FAMILY, TEMPLATE)
    assert record_capture(capture_repo, FAMILY, TEMPLATE) == path
    manifest = json.loads((capture_repo / path).read_text())
    original = json.loads((capture_repo / TEMPLATE).read_text())
    assert is_capture(manifest["revision"])
    for label in ("snapshot", "analysis"):
        assert (capture_repo / manifest[f"{label}_path"]).read_bytes() == (
            capture_repo / original[f"{label}_path"]
        ).read_bytes()


@pytest.mark.parametrize("mutation", ["missing-history", "missing-capture", "changed-pin", "renamed-identity"])
def test_inventory_rejects_dropped_or_rebound_captures(capture_repo, mutation):
    indexed = records(capture_repo)
    if mutation == "missing-history":
        indexed = [row for row in indexed if row[0] != TEMPLATE]
    elif mutation == "missing-capture":
        indexed = [row for row in indexed if not is_capture(row[1]["revision"])]
    elif mutation == "changed-pin":
        manifest = dict(indexed)[TEMPLATE]
        manifest["snapshot_sha256"] = "0" * 64
    else:
        path, manifest = next(row for row in indexed if is_capture(row[1]["revision"]))
        manifest["revision"] = "capture-" + "0" * 64
    with pytest.raises(ValueError):
        validate_inventory(capture_repo, FAMILY, indexed)


def test_latest_number_does_not_select_stale_source(tmp_path, monkeypatch):
    from tools import research_evidence

    monkeypatch.setattr(research_evidence, "implementation_digest", lambda _: "live")
    indexed = []
    for name, revision, source, date in [
        ("old", "999.0.0", "stale", "2026-01-02T00:00:00+00:00"),
        ("current", "capture-" + "a" * 64, "live", "2026-01-01T00:00:00+00:00"),
    ]:
        snapshot = {
            "source_state": {"profile": research_evidence.SOURCE_PROFILE, "implementation_digest": source},
            "captured_at": date,
        }
        (tmp_path / f"{name}.json").write_text(json.dumps(snapshot))
        indexed.append((name, {"revision": revision, "snapshot_path": f"{name}.json"}))
    assert current_release_path(indexed, tmp_path) == "current"
    with pytest.raises(ValueError, match="no current"):
        current_release_path(indexed[:1], tmp_path)


def test_equal_dates_with_different_pins_are_ambiguous(tmp_path, monkeypatch):
    from tools import research_evidence

    monkeypatch.setattr(research_evidence, "implementation_digest", lambda _: "live")
    indexed = []
    for suffix in ("a", "b"):
        snapshot = {
            "source_state": {"profile": research_evidence.SOURCE_PROFILE, "implementation_digest": "live"},
            "captured_at": "2026-01-01T00:00:00+00:00",
        }
        (tmp_path / f"{suffix}.json").write_text(json.dumps(snapshot))
        indexed.append(
            (
                suffix,
                {
                    "revision": "capture-" + suffix * 64,
                    "snapshot_path": f"{suffix}.json",
                    "snapshot_sha256": suffix * 64,
                    "analysis_sha256": suffix * 64,
                },
            )
        )
    with pytest.raises(ValueError, match="ambiguous"):
        current_release_path(indexed, tmp_path)


@pytest.mark.parametrize("branch", ["feature", "main", ""])
def test_feature_branches_cannot_allocate_publication_numbers(tmp_path, monkeypatch, branch):
    from tools import research_capture

    monkeypatch.setattr(research_capture.subprocess, "check_output", lambda *args, **kwargs: branch)
    with pytest.raises(ValueError, match="only on the dev"):
        publish_capture(tmp_path, FAMILY)
    assert list(tmp_path.iterdir()) == []


def test_integration_assigns_next_number_without_mutating_capture(capture_repo, monkeypatch):
    from tools import research_capture

    selected = record_capture(capture_repo, FAMILY, TEMPLATE)
    before = (capture_repo / selected).read_bytes()
    monkeypatch.setattr(
        research_capture.subprocess, "check_output", lambda args, **kwargs: "dev\n" if "branch" in args else ""
    )
    monkeypatch.setattr(research_capture, "current_release_path", lambda *_: selected)
    published = publish_capture(capture_repo, FAMILY)
    assert publish_capture(capture_repo, FAMILY) == published
    receipt = json.loads((capture_repo / published).read_text())
    assert receipt == {
        "revision": "76.0.0",
        "capture_path": selected,
        "capture_sha256": hashlib.sha256(before).hexdigest(),
    }
    assert (capture_repo / selected).read_bytes() == before
    assert capture_identity(json.loads(before)) == json.loads(before)["revision"]


def test_fresh_analysis_snapshot_reference_is_independent_of_output_hash(capture_repo):
    original = json.loads((capture_repo / TEMPLATE).read_text())
    snapshot = (capture_repo / original["snapshot_path"]).read_bytes()
    analysis = json.loads((capture_repo / original["analysis_path"]).read_text())
    analysis["claim"]["evidence_artifacts"] = ["prepared-snapshot.json"]
    (capture_repo / "prepared-snapshot.json").write_bytes(snapshot)
    (capture_repo / "prepared-analysis.json").write_text(json.dumps(analysis))
    path = record_capture(
        capture_repo, FAMILY, TEMPLATE, snapshot_path="prepared-snapshot.json", analysis_path="prepared-analysis.json"
    )
    manifest = json.loads((capture_repo / path).read_text())
    recorded = json.loads((capture_repo / manifest["analysis_path"]).read_text())
    assert recorded["claim"]["evidence_artifacts"] == ["@snapshot"]
    assert manifest["revision"] == capture_identity(manifest)


def test_snapshot_reference_resolves_only_to_the_selected_pinned_document():
    from tools.formal_semantic_validation._analysis import _claim_record_failures

    folder = ROOT / "docs/research/formal-semantic-validation"
    analysis = json.loads((folder / "analysis-v76.json").read_text())
    analysis["claim"]["evidence_artifacts"] = ["@snapshot"]
    failures = []
    _claim_record_failures(
        ROOT,
        analysis,
        failures,
        "analysis",
        snapshot_path="docs/research/formal-semantic-validation/execution-snapshot-v76.json",
    )
    assert failures == []
    _claim_record_failures(ROOT, analysis, failures, "analysis")
    assert {failure.rule_id for failure in failures} == {"formal-validation-claim-artifact"}


def test_formal_release_rejects_a_rebound_capture_identity(monkeypatch):
    from copy import deepcopy

    from tools.formal_semantic_validation import _releases
    from tools.formal_semantic_validation._loading import load_retest_bundle

    release = deepcopy(load_retest_bundle(ROOT)[0])
    release.manifest["revision"] = "capture-" + "a" * 64
    monkeypatch.setattr(_releases, "_is_current", lambda *_: False)
    monkeypatch.setattr(_releases, "validate_retest_bundle", lambda *args, **kwargs: [])
    failures = _releases.validate_release_bundle(ROOT, release)
    assert any(failure.rule_id == "formal-validation-release-digest" for failure in failures)


def test_ci_participant_replay_uses_the_source_selected_capture(monkeypatch):
    from tools import check_formal_semantic_validation as gate
    from tools.formal_semantic_validation._loading import load_release_bundles, load_retest_bundle

    releases = load_release_bundles(ROOT)
    selected = load_retest_bundle(ROOT)[0]
    calls = []
    monkeypatch.setattr(gate, "_participant_test_refs", lambda protocol: ["selected-protocol"])
    failures = gate._participant_replay_failures(
        ROOT, releases, lambda root, refs: (calls.append(refs) or False, "bounded failure")
    )
    assert calls == [["selected-protocol"]]
    assert failures[0].path == selected.manifest["snapshot_path"]


def test_collided_formal_baseline_resolves_the_exact_preserved_capture():
    from tools.formal_semantic_validation._baseline import _resolved_baseline_snapshot

    snapshot = json.loads((ROOT / "docs/research/formal-semantic-validation/execution-snapshot-v76.json").read_text())
    failures = []
    baseline = _resolved_baseline_snapshot(ROOT, snapshot, failures, "retained-formal-76")
    assert failures == []
    assert baseline["execution_id"] == snapshot["baseline"]["execution_id"]
    canonical = json.loads((ROOT / "docs/research/formal-semantic-validation/execution-snapshot-v75.json").read_text())
    assert baseline["execution_id"] != canonical["execution_id"]
