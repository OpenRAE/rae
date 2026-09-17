"""Behavioral regressions for current replay and historical evidence retention."""

import re
from copy import deepcopy
from pathlib import Path

import pytest
from evidence_test_fixtures import copy_bundle

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("case_name", ["finite-domain-satisfiable", "typed-exploit-path-valid"])
@pytest.mark.parametrize("mutation", ["missing", "unknown", "nested", "snapshot"])
def test_historical_evidence_rejects_malformed_shapes_even_with_rebound_digest(case_name, mutation):
    import json

    from raes_contracts.canonical import canonical_json_digest
    from tools.formal_semantic_validation._production import _historical_production_replay

    payload = json.loads((ROOT / f"docs/research/formal-semantic-validation/evidence/{case_name}-v3.json").read_text())
    if mutation == "missing":
        del payload["authored_digest"]
    elif mutation == "unknown":
        payload["invented_claim"] = True
    elif mutation == "nested":
        payload["source"]["source_id"] = {"invalid": "identity"}
    elif case_name.startswith("finite"):
        payload["witness"]["snapshot"]["scenario"]["nodes"]["target"]["invented_constraint"] = True
    else:
        payload["normalized_graph"]["state_facts"][0]["invented_constraint"] = True
    observation = {"evidence_digest": canonical_json_digest(payload)}
    mode = "satisfiability" if case_name.startswith("finite") else "exploit-path"
    with pytest.raises(ValueError, match="archival shape"):
        _historical_production_replay(payload, observation, mode)


@pytest.mark.parametrize("version", [1, 2])
def test_historical_shape_contract_cannot_be_replaced_with_an_open_schema(tmp_path, version):
    import json
    import shutil

    from tools.formal_semantic_validation._archival_shape import validate_archival_evidence_shape

    relative = Path("docs/research/formal-semantic-validation/archive-contracts")
    shutil.copytree(ROOT / relative, tmp_path / relative)
    (tmp_path / relative / f"satisfiability-evidence-shape-v{version}.json").write_text("{}\n")
    payload = json.loads(
        (
            ROOT / f"docs/research/formal-semantic-validation/evidence/finite-domain-satisfiable-v{version + 2}.json"
        ).read_text()
    )
    with pytest.raises(ValueError, match="archival shape digest mismatch"):
        validate_archival_evidence_shape(tmp_path, payload, "satisfiability")


@pytest.mark.parametrize("version", [1, 2])
def test_historical_shape_manifest_cannot_authorize_a_replacement_schema(tmp_path, version):
    import hashlib
    import json
    import shutil

    from tools.formal_semantic_validation._archival_shape import validate_archival_evidence_shape

    relative = Path("docs/research/formal-semantic-validation/archive-contracts")
    shutil.copytree(ROOT / relative, tmp_path / relative)
    schema_path = tmp_path / relative / f"satisfiability-evidence-shape-v{version}.json"
    schema_path.write_text("{}\n")
    manifest_path = tmp_path / relative / f"manifest-v{version}.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["contracts"][0]["sha256"] = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="archival manifest"):
        validate_archival_evidence_shape(tmp_path, {}, "satisfiability")


@pytest.mark.parametrize(
    ("family", "field"),
    [
        ("finite-domain-satisfiable", field)
        for field in ("normalized_model_digest", "solver_configuration_digest", "witness.snapshot_digest")
    ]
    + [
        ("typed-exploit-path-valid", field)
        for field in (
            "snapshot_digest",
            "normalized_graph_digest",
            "query_digest",
            "search_configuration_digest",
            "witness.final_state_digest",
            "witness.steps.0.state_before_digest",
            "witness.steps.0.state_after_digest",
        )
    ],
)
def test_historical_computed_joins_reject_rebound_evidence(family, field):
    import json

    from raes_contracts.canonical import canonical_json_digest
    from tools.formal_semantic_validation._production import _historical_production_replay

    payload = json.loads((ROOT / f"docs/research/formal-semantic-validation/evidence/{family}-v3.json").read_text())
    parent = payload
    parts = field.split(".")
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
    parent[parts[-1]] = "sha256:" + "0" * 64
    observation = {"evidence_digest": canonical_json_digest(payload)}
    expected_join = {
        "snapshot_digest": "snapshot join",
        "witness.steps.0.state_before_digest": "state before join",
        "witness.steps.0.state_after_digest": "state after join",
    }.get(field, field.split(".")[-1].removesuffix("_digest") + " digest join")
    mode = "satisfiability" if family.startswith("finite") else "exploit-path"
    with pytest.raises(ValueError, match=expected_join):
        _historical_production_replay(payload, observation, mode)


@pytest.mark.parametrize("version", [2, 3, 4])
@pytest.mark.parametrize("mutation", ["source", "authored", "effects", "index", "goal", "non-retained"])
def test_historical_integrity_checks_reject_shape_valid_substitutions(version, mutation):
    import json

    from raes_contracts.canonical import canonical_json_digest
    from tools.formal_semantic_validation._production import _historical_production_replay

    satisfiability = mutation in {"source", "authored"}
    family = "finite-domain-satisfiable" if satisfiability else "typed-exploit-path-valid"
    payload = json.loads(
        (ROOT / f"docs/research/formal-semantic-validation/evidence/{family}-v{version}.json").read_text()
    )
    if mutation == "source":
        payload["source"]["byte_digest"] = "sha256:" + "0" * 64
    elif mutation == "authored":
        payload["authored_digest"]["value"] = "sha256:" + "0" * 64
    elif mutation == "effects":
        payload["witness"]["steps"][0]["applied_effects"] = ["data-access"]
    elif mutation == "index":
        payload["witness"]["steps"][0]["step_index"] = 3
    elif mutation == "goal":
        payload["witness"]["goal_facts"] = ["web-shell"]
    else:
        payload["source"]["source_id"] = "unrecorded-source.json"
    observation = {"evidence_digest": canonical_json_digest(payload)}
    expected = {
        "source": "source join",
        "authored": "authored join",
        "effects": "effects join",
        "index": "step index",
        "goal": "goal facts join",
        "non-retained": "not in the retained production evidence corpus",
    }
    with pytest.raises(ValueError, match=expected[mutation]):
        _historical_production_replay(payload, observation, "satisfiability" if satisfiability else "exploit-path")


def test_current_compile_replay_hashes_complete_capture_dimension():
    import dataclasses

    from raes import instantiate_scenario, parse_sdl_file
    from raes_processor.compiler import compile_runtime_model
    from tools.formal_semantic_validation._loading import load_retest_bundle
    from tools.formal_semantic_validation._replay import _compiled_case_digest, _migration_policy_for_case
    from tools.formal_semantic_validation._shape import _digest

    _, _, corpus, _, _ = copy_bundle(load_retest_bundle, ROOT)
    case = next(c for c in corpus["cases"] if c["case_id"] == "compile-repeatability-control")
    path = ROOT / case["fixture_path"]
    scenario = parse_sdl_file(path, migration_policy=_migration_policy_for_case(ROOT, case, path))
    compiled = dataclasses.asdict(compile_runtime_model(instantiate_scenario(scenario, parameters={})))
    assert "capture_demands" in compiled
    assert _compiled_case_digest(ROOT, case, path) == _digest(compiled)


def test_old_output_digest_pairs_do_not_substitute_for_replay():
    from tools.formal_semantic_validation._replay import _replay_observation_matches

    old = {
        "actual_outcome": "accepted",
        "diagnostic_kind": None,
        "result_digest": "ba0ecbfcb3090ffd6b660cb51324fafcd47ca8dedbbb985e98b6e7f64f8cc25b",
    }
    changed = {**old, "result_digest": "5332666a0299d2c303d7a7da4b56dfd309cebf021af187b063ef597cf81bf40a"}
    assert not _replay_observation_matches(old, changed)


@pytest.mark.parametrize(
    "revision",
    ["3.0.0", "15.0.0", "16.0.0", "17.0.0", "18.0.0", "19.0.0", "20.0.0", "21.0.0", "22.0.0", "23.0.0", "24.0.0", "25.0.0"],
)
def test_historical_integrated_release_does_not_execute_current_code(monkeypatch, revision):
    from raes_contracts.exploit_path import ExploitPathAnalysisEvidenceModel
    from raes_contracts.satisfiability import ScenarioSatisfiabilityEvidenceModel
    from tools.formal_semantic_validation import _production, _releases, _retest
    from tools.formal_semantic_validation._loading import load_release_bundles

    release = next(r for r in copy_bundle(load_release_bundles, ROOT) if r.manifest["revision"] == revision)

    def forbidden(*args, **kwargs):
        raise AssertionError("historical observations are not current-code evidence")

    monkeypatch.setattr(_retest, "replay_case", forbidden)
    monkeypatch.setattr(_production, "_run_production_evidence_cli", forbidden)
    monkeypatch.setattr(ExploitPathAnalysisEvidenceModel, "model_validate", forbidden)
    monkeypatch.setattr(ScenarioSatisfiabilityEvidenceModel, "model_validate", forbidden)
    assert _releases.validate_release_bundle(ROOT, release) == []


@pytest.mark.integration
def test_latest_current_release_is_versioned_and_strict(monkeypatch):
    from tools.formal_semantic_validation import _retest
    from tools.formal_semantic_validation._loading import load_retest_bundle
    from tools.formal_semantic_validation._releases import validate_retest_bundle

    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, ROOT)
    assert release.manifest["revision"] == "26.0.0"
    original = _retest.replay_case

    def changed_result(root, case):
        result = original(root, case)
        if case["case_id"] == "schema-valid-control":
            result["result_digest"] = "f" * 64
        return result

    monkeypatch.setattr(_retest, "replay_case", changed_result)
    failures = validate_retest_bundle(ROOT, release, protocol, corpus, snapshot, analysis)
    assert "formal-validation-replay-drift" in {f.rule_id for f in failures}


@pytest.mark.integration
def test_current_release_requires_truthful_implementation_provenance():
    from tools.formal_semantic_validation._loading import load_retest_bundle
    from tools.formal_semantic_validation._releases import validate_retest_bundle

    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, ROOT)
    snapshot = deepcopy(snapshot)
    assert "source_state" in snapshot
    snapshot["source_state"]["implementation_digest"] = "0" * 64
    failures = validate_retest_bundle(ROOT, release, protocol, corpus, snapshot, analysis)
    assert "research-evidence-source-state" in {f.rule_id for f in failures}


@pytest.mark.integration
def test_current_production_evidence_replay_failure_is_not_hidden(monkeypatch):
    from raes_processor import satisfiability
    from tools.formal_semantic_validation._loading import load_retest_bundle
    from tools.formal_semantic_validation._releases import validate_retest_bundle

    def fail(*args, **kwargs):
        raise ValueError("seeded production replay failure")

    monkeypatch.setattr(satisfiability, "replay_satisfiability_evidence", fail)
    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, ROOT)
    failures = validate_retest_bundle(ROOT, release, protocol, corpus, snapshot, analysis)
    assert "formal-validation-production-replay" in {f.rule_id for f in failures}


@pytest.mark.parametrize(
    ("artifact_id", "old_digest"),
    [
        ("port-range-sdl", "a27c7a64e0c5c618fadaccafdf1a4e71600170a8b77b983190822b5141f00dec"),
        ("known-limitations", "129cf17810aad4c51988bc872e28fe43ae95019a80053c42d800ff7e2b9cc93e"),
    ],
)
def test_specification_current_capture_does_not_accept_old_artifact_digest(artifact_id, old_digest):
    from tools.check_specification_coverage import load_bundle, validate_bundle

    manifest, protocol, snapshot, analysis = copy_bundle(load_bundle, ROOT)
    assert manifest["revision"] == "25.0.0"
    snapshot = deepcopy(snapshot)
    artifact = next(a for a in snapshot["artifacts"] if a["artifact_id"] == artifact_id)
    artifact["sha256"] = old_digest
    failures = validate_bundle(ROOT, manifest, protocol, snapshot, analysis)
    assert "specification-coverage-artifact-digest" in {f.rule_id for f in failures}


def test_historical_specification_evidence_is_integrity_checked_without_execution(monkeypatch):
    from tools import check_specification_coverage as coverage
    from tools.specification_coverage import _artifacts

    manifest, protocol, snapshot, analysis = copy_bundle(coverage.load_bundles, ROOT)[0]

    def forbidden(*args, **kwargs):
        raise AssertionError("must not execute an archived artifact on current code")

    monkeypatch.setattr(_artifacts, "_execute_artifact", forbidden)
    assert coverage.validate_historical_bundle(ROOT, manifest, protocol, snapshot, analysis) == []


@pytest.mark.parametrize("value", ["0" * 64, "../outside"])
def test_historical_specification_archive_pin_tampering_fails(value):
    from tools import check_specification_coverage as coverage

    manifest, protocol, snapshot, analysis = copy_bundle(coverage.load_bundles, ROOT)[0]
    snapshot = deepcopy(snapshot)
    snapshot["artifacts"][0]["sha256"] = value
    failures = coverage.validate_historical_bundle(ROOT, manifest, protocol, snapshot, analysis)
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

    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, ROOT)
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
    release = next(r for r in copy_bundle(load_release_bundles, ROOT) if r.manifest["revision"] == "2.0.0")
    assert validate_release_bundle(ROOT, release) == []


@pytest.mark.integration
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
    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, ROOT)
    failures = validate_retest_bundle(ROOT, release, protocol, corpus, snapshot, analysis)
    assert "formal-validation-production-evidence-join" in {f.rule_id for f in failures}


@pytest.mark.integration
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
    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, ROOT)
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
    manifest, protocol, snapshot, analysis = copy_bundle(coverage.load_bundles, ROOT)[0]
    failures = coverage.validate_historical_bundle(ROOT, manifest, protocol, snapshot, analysis)
    assert "specification-coverage-artifact-digest" in {f.rule_id for f in failures}


@pytest.mark.parametrize("family", ["formal", "coverage"])
@pytest.mark.parametrize("removed", ["current", "history"])
def test_no_capture_can_be_silently_dropped(monkeypatch, family, removed):
    from tools import check_specification_coverage
    from tools.formal_semantic_validation import _loading

    module = _loading if family == "formal" else check_specification_coverage
    revisions = (
        [
            "1.0.0",
            "1.1.0",
            "1.2.0",
            "2.0.0",
            "3.0.0",
            "4.0.0",
            "5.0.0",
            "6.0.0",
            "7.0.0",
            "8.0.0",
            "9.0.0",
            "10.0.0",
            "11.0.0",
            "12.0.0",
            "13.0.0",
            "14.0.0",
            "15.0.0",
            "16.0.0",
            "17.0.0",
            "18.0.0",
            "19.0.0",
            "20.0.0",
            "21.0.0",
            "22.0.0",
            "23.0.0",
            "24.0.0",
            "25.0.0",
            "26.0.0",
        ]
        if family == "formal"
        else [
            "1.0.0",
            "1.1.0",
            "2.0.0",
            "3.0.0",
            "4.0.0",
            "5.0.0",
            "6.0.0",
            "7.0.0",
            "8.0.0",
            "9.0.0",
            "10.0.0",
            "11.0.0",
            "12.0.0",
            "13.0.0",
            "14.0.0",
            "15.0.0",
            "16.0.0",
            "17.0.0",
            "18.0.0",
            "19.0.0",
            "20.0.0",
            "21.0.0",
            "22.0.0",
            "23.0.0",
            "24.0.0",
            "25.0.0",
        ]
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

    manifest, protocol, snapshot, analysis = copy_bundle(load_bundle, ROOT)
    if change == "missing":
        snapshot["deviations"].pop()
    elif change == "old_digest":
        snapshot["deviations"][0]["baseline_sha256"] = "0" * 64
    elif change == "unknown_field":
        snapshot["deviations"][0]["trust_me"] = True
    else:
        snapshot["baseline"]["release_sha256"] = "0" * 64
    assert "specification-coverage-baseline-drift" in {
        f.rule_id for f in validate_bundle(ROOT, manifest, protocol, snapshot, analysis)
    }


def test_current_coverage_preserves_untested_slots_without_claiming_capability_absence():
    from tools.check_specification_coverage import load_bundle

    _, protocol, snapshot, analysis = copy_bundle(load_bundle, ROOT)
    missing = [item for item in snapshot["concept_results"] if item["classification"] == "missing"]
    assert len(snapshot["concept_results"]) == len(protocol["concepts"]) == 16
    assert len(missing) == 3
    assert all(stage["outcome"] == "not_run" for item in missing for stage in item["stage_results"])
    assert analysis["evidence_status"] == "partial"


def test_historical_archive_does_not_require_a_live_source_file(tmp_path):
    import shutil

    from tools.check_specification_coverage import load_bundles
    from tools.specification_coverage._artifacts import _validate_artifacts

    manifest, _, snapshot, _ = copy_bundle(load_bundles, ROOT)[0]
    archive = Path("docs/research/specification-coverage/historical-artifacts")
    shutil.copytree(ROOT / archive, tmp_path / archive)
    assert all(not (tmp_path / item["path"]).exists() for item in snapshot["artifacts"])
    failures = []
    artifacts, executed = _validate_artifacts(
        tmp_path,
        snapshot,
        failures,
        manifest["snapshot_path"],
        replay_current=False,
    )
    assert failures == []
    assert len(artifacts) == len(executed) == 6
    failures = []
    _validate_artifacts(tmp_path, snapshot, failures, manifest["snapshot_path"])
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


def _release_managed_source_tree(tmp_path: Path, version_source: str) -> Path:
    from tools.research_evidence import RELEASE_MANAGED_VERSION_SOURCE

    python = tmp_path / "implementations/python"
    (python / "packages/raes").mkdir(parents=True)
    (python / "pyproject.toml").write_text('[project]\nname = "raes"\n', encoding="utf-8")
    (python / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (python / "packages/raes/__init__.py").write_text("from raes._version import __version__\n", encoding="utf-8")
    (tmp_path / RELEASE_MANAGED_VERSION_SOURCE).write_text(version_source, encoding="utf-8")
    return tmp_path


def _released_version_source(version: str) -> str:
    from tools.research_evidence import RELEASE_MANAGED_VERSION_SOURCE

    current = (ROOT / RELEASE_MANAGED_VERSION_SOURCE).read_text(encoding="utf-8")
    released, count = re.subn(r'(__version__ = ")[^"]+(")', rf"\g<1>{version}\g<2>", current)
    assert count == 1
    return released


def _source_digests(root: Path) -> tuple[str, str]:
    from tools.research_evidence import implementation_digest, surface_digest

    return implementation_digest(root), surface_digest(root, "implementations/python/packages/raes")


def test_release_version_bump_does_not_change_source_identity(tmp_path):
    before = _source_digests(_release_managed_source_tree(tmp_path / "before", _released_version_source("3.5.0")))
    after = _source_digests(_release_managed_source_tree(tmp_path / "after", _released_version_source("4.0.0")))

    assert before == after


def test_release_managed_source_still_binds_everything_but_the_version_literal(tmp_path):
    released = _released_version_source("4.0.0")
    baseline = _source_digests(_release_managed_source_tree(tmp_path / "baseline", released))
    changed = _source_digests(_release_managed_source_tree(tmp_path / "changed", released + "RELEASE_HOOK = True\n"))

    assert baseline[0] != changed[0]
    assert baseline[1] != changed[1]


@pytest.mark.parametrize(
    "version_source",
    [
        '__version__ = "4.0.0"\n',
        '__version__ = "4.0.0"  # x-release-please-version\nOTHER = "1.0.0"  # x-release-please-version\n',
        '__version__ = __import__("os").getenv("V")  # x-release-please-version\n',
    ],
)
def test_malformed_release_managed_source_fails_closed(tmp_path, version_source):
    from tools.research_evidence import implementation_digest, source_state_failures, surface_digest

    root = _release_managed_source_tree(tmp_path, version_source)
    with pytest.raises(ValueError, match="release-managed version source"):
        implementation_digest(root)
    with pytest.raises(ValueError, match="release-managed version source"):
        surface_digest(root, "implementations/python/packages/raes")
    state = {
        "profile": "python-reference-source/v2",
        "base_revision": "0" * 40,
        "checkout_state": "clean",
        "implementation_digest": "0" * 64,
    }
    assert source_state_failures(root, state, "capture.json", current=True)


def test_release_managed_version_source_is_the_file_release_please_rewrites():
    import json

    from tools.research_evidence import RELEASE_MANAGED_VERSION_SOURCE

    config = json.loads((ROOT / "release-please-config.json").read_text(encoding="utf-8"))
    extra_files = config["packages"]["."]["extra-files"]
    assert extra_files == [{"type": "generic", "path": RELEASE_MANAGED_VERSION_SOURCE}]


def test_current_capture_requires_the_release_stable_source_profile():
    from tools.formal_semantic_validation._loading import load_retest_bundle
    from tools.research_evidence import SOURCE_PROFILE, source_state_failures

    _, _, _, snapshot, _ = load_retest_bundle(ROOT)
    state = deepcopy(snapshot["source_state"])
    assert state["profile"] == SOURCE_PROFILE == "python-reference-source/v2"
    assert source_state_failures(ROOT, state, "capture.json", current=True) == []

    state["profile"] = "python-reference-source/v1"
    assert source_state_failures(ROOT, state, "capture.json", current=True)
    assert source_state_failures(ROOT, state, "capture.json", current=False) == []
