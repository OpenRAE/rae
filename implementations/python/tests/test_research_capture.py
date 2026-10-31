"""Branch captures coexist without allocating the same numbered release."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from raes_contracts.errors import ConflictError, InvalidInputError
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
    with pytest.raises(InvalidInputError):
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
    with pytest.raises(InvalidInputError, match="no current"):
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
    with pytest.raises(InvalidInputError, match="ambiguous"):
        current_release_path(indexed, tmp_path)


@pytest.mark.parametrize("branch", ["feature", "main", ""])
def test_feature_branches_cannot_allocate_publication_numbers(tmp_path, monkeypatch, branch):
    from tools import research_capture

    monkeypatch.setattr(research_capture.subprocess, "check_output", lambda *args, **kwargs: branch)
    with pytest.raises(ConflictError, match="only on the dev"):
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


def test_inventory_selection_is_scoped_and_still_replays_only_current(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from tools.formal_semantic_validation import _releases

    releases = [SimpleNamespace(manifest_path=name, manifest={}) for name in ("old", "current")]
    selections = []
    replayed = []

    def select(records, root):
        selections.append(root)
        return "current"

    def validate(root, release):
        replayed.append((release.manifest_path, _releases._is_current(root, release)))
        return []

    monkeypatch.setattr(_releases, "current_release_path", select)
    monkeypatch.setattr(_releases, "validate_release_bundle", validate)
    assert _releases.validate_release_bundles(tmp_path, releases) == []
    assert selections == [tmp_path]
    assert replayed == [("old", False), ("current", True)]
    assert _releases._SELECTED_RELEASE.get() is None
    assert _releases.validate_release_bundles(tmp_path, releases) == []
    assert selections == [tmp_path, tmp_path]

    def fail(*args):
        raise ValueError("seeded validation failure")

    monkeypatch.setattr(_releases, "validate_release_bundle", fail)
    with pytest.raises(ValueError, match="seeded validation failure"):
        _releases.validate_release_bundles(tmp_path, releases)
    assert _releases._SELECTED_RELEASE.get() is None


def test_unloadable_evidence_record_message_omits_the_inner_failure_text(tmp_path):
    sentinel = "RECORD-KEY-SENTINEL"
    bundles = tmp_path / "docs/research/family/bundles"
    bundles.mkdir(parents=True)
    (tmp_path / "docs/research/family/index.json").write_text(
        json.dumps({"schema_version": "family/v1", "bundles_directory": "docs/research/family/bundles"})
    )
    (bundles / "record.json").write_text(f'{{"{sentinel}": 1, "{sentinel}": 2}}\n')

    with pytest.raises(InvalidInputError) as raised:
        load_index_records(
            tmp_path,
            index_path="docs/research/family/index.json",
            schema_version="family/v1",
            directory_key="bundles_directory",
            max_bytes=4096,
        )

    assert str(raised.value) == "cannot load evidence record 'docs/research/family/bundles/record.json'"
    assert sentinel not in str(raised.value)
    assert isinstance(raised.value.__cause__, InvalidInputError)


@pytest.mark.parametrize("captured_at", ["not-a-timestamp", "2026-13-40T00:00:00+00:00"])
def test_malformed_capture_date_is_invalid_input(tmp_path, monkeypatch, captured_at):
    from tools import research_evidence

    monkeypatch.setattr(research_evidence, "implementation_digest", lambda _: "live")
    snapshot = {
        "source_state": {"profile": research_evidence.SOURCE_PROFILE, "implementation_digest": "live"},
        "captured_at": captured_at,
    }
    (tmp_path / "current.json").write_text(json.dumps(snapshot))

    with pytest.raises(InvalidInputError, match="offset-aware timestamp"):
        current_release_path(
            [("current", {"revision": "capture-" + "a" * 64, "snapshot_path": "current.json"})], tmp_path
        )


def test_release_managed_version_source_must_be_utf8_text(tmp_path):
    from tools import research_evidence

    version_source = tmp_path / "_version.py"
    version_source.write_bytes(b"\xff\xfe__version__")

    with pytest.raises(InvalidInputError, match="UTF-8 text"):
        research_evidence._source_bytes(version_source, research_evidence.RELEASE_MANAGED_VERSION_SOURCE)


def test_publication_refusal_is_a_message_and_status_one(monkeypatch, capsys):
    from tools import research_capture

    monkeypatch.setattr(research_capture.subprocess, "check_output", lambda *args, **kwargs: "feature")
    monkeypatch.setattr("sys.argv", ["research_capture.py", "publish", FAMILY])

    with pytest.raises(SystemExit) as raised:
        research_capture.main()

    assert raised.value.code == 1
    assert "only on the dev integration branch" in capsys.readouterr().err


def test_capture_defects_are_not_reported_as_refusals(monkeypatch):
    from tools import research_capture

    def defect(*_args, **_kwargs):
        raise RuntimeError("seeded defect")

    monkeypatch.setattr(research_capture, "publish_capture", defect)
    monkeypatch.setattr("sys.argv", ["research_capture.py", "publish", FAMILY])

    with pytest.raises(RuntimeError, match="seeded defect"):
        research_capture.main()
