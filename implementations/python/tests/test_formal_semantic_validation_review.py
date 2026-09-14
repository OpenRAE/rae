"""Evidence failures identify the exact integrity boundary that rejected them."""

import subprocess

import pytest
from evidence_test_fixtures import copy_bundle
from test_formal_semantic_validation import REPO_ROOT, _bundle
from tools.check_formal_semantic_validation import (
    load_release_bundles,
    load_retest_bundle,
    validate_bundle,
    validate_release_bundle,
    validate_retest_bundle,
)
from tools.formal_semantic_validation import _production, _retest, _snapshot


def test_frozen_baseline_archive_requires_exact_captured_bytes(tmp_path):
    import hashlib

    from tools.formal_semantic_validation._baseline import _baseline_document

    captured = b'{"execution_id":"frozen-observation"}\n'
    digest = hashlib.sha256(captured).hexdigest()
    current = tmp_path / "snapshot.json"
    current.write_text('{"execution_id":"later-observation"}\n')
    archive = tmp_path / "docs/research/formal-semantic-validation/historical-artifacts" / (digest + ".json")
    archive.parent.mkdir(parents=True)
    archive.write_bytes(captured)
    assert _baseline_document(tmp_path, "snapshot.json", digest) is None
    assert _baseline_document(tmp_path, "../snapshot.json", digest) is None
    archive.write_text('{"execution_id":"forged-observation"}\n')
    assert _baseline_document(tmp_path, "snapshot.json", digest) is None


def identities(failures):
    return {(f.rule_id, f.message, f.path) for f in failures}


@pytest.mark.integration
@pytest.mark.parametrize(
    ("field", "value", "rule", "message"),
    [
        ("raes_revision", "dev", "formal-validation-revision-pin", "retest snapshot must pin a full RAES commit"),
        (
            "versions",
            {},
            "formal-validation-version-disclosure",
            "retest snapshot must record the bounded output-affecting versions",
        ),
    ],
)
def test_retest_requires_immutable_revision_and_version_disclosure(field, value, rule, message):
    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, REPO_ROOT)
    snapshot[field] = value
    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)
    assert (rule, message, release.manifest["snapshot_path"]) in identities(failures)


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize(
    ("field", "value"), [("actual_outcome", "accepted"), ("diagnostic_kind", "invented"), ("result_digest", "0" * 64)]
)
def test_unsupported_observations_cannot_fabricate_results(version, field, value):
    observation = {
        "case_id": "unsupported",
        "actual_outcome": "unsupported",
        "diagnostic_kind": None,
        "result_digest": None,
    }
    failures = []

    def validate():
        if version == 1:
            _snapshot._validate_snapshot_replay(
                REPO_ROOT, {"replay_mode": "unsupported"}, observation, failures, "snapshot.json", replay_cases=True
            )
        else:
            _retest._validate_retained_retest_observation(
                REPO_ROOT, {"replay_mode": "unsupported"}, observation, failures, "snapshot.json"
            )

    validate()
    assert failures == []
    observation[field] = value
    validate()
    message = (
        "unsupported observation 'unsupported' must not synthesize diagnostics or results"
        if version == 1
        else "historical unsupported case 'unsupported' must remain unsupported"
    )
    assert identities(failures) == {("formal-validation-unsupported-observation", message, "snapshot.json")}


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("error", [OSError, ValueError])
def test_retained_replay_exceptions_are_failures(monkeypatch, version, error):
    module = _snapshot if version == 1 else _retest

    def fail(*_args):
        raise error("seeded failure")

    monkeypatch.setattr(module, "replay_case", fail)
    case, observation = {"case_id": "control", "replay_mode": "parse"}, {"case_id": "control"}
    failures = []
    if version == 1:
        _snapshot._validate_snapshot_replay(REPO_ROOT, case, observation, failures, "snapshot.json", replay_cases=True)
        message = "could not replay 'control': seeded failure"
    else:
        _retest._validate_retained_retest_observation(REPO_ROOT, case, observation, failures, "snapshot.json")
        message = f"retained case 'control' could not replay ({error.__name__})"
    assert identities(failures) == {("formal-validation-replay-error", message, "snapshot.json")}


@pytest.mark.parametrize("case_id", ["finite-domain-satisfiable-v2", "typed-exploit-path-valid-v2"])
@pytest.mark.parametrize("error", [OSError, ValueError, RuntimeError, subprocess.SubprocessError])
def test_production_replay_exceptions_are_failures(monkeypatch, case_id, error):
    release, _protocol, corpus, snapshot, _analysis = copy_bundle(load_retest_bundle, REPO_ROOT)
    case = next(item for item in corpus["cases"] if item["case_id"] == case_id)
    observation = next(item for item in snapshot["observations"] if item["case_id"] == case_id)
    command = next(item for item in snapshot["commands"] if item["command_id"] == case_id)
    context = _production._ProductionObservationContext(
        REPO_ROOT, {item["path"]: item for item in release.manifest["artifacts"]}
    )

    def fail(*_args, **_kwargs):
        raise error("seeded failure")

    monkeypatch.setattr(_production, "_replay_production_evidence", fail)
    failures = []
    _production._validate_production_evidence_observation(
        context, case, observation, command, failures, "snapshot.json"
    )
    assert identities(failures) == {
        (
            "formal-validation-production-replay",
            f"case {case_id!r} production replay failed ({error.__name__})",
            "snapshot.json",
        )
    }


@pytest.mark.integration
def test_retest_rejects_an_extra_atomically_selected_artifact():
    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, REPO_ROOT)
    release.manifest["artifacts"].append(
        {"artifact_id": "extra", "kind": "production-evidence", "path": "extra.json", "sha256": "0" * 64}
    )
    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)
    assert (
        "formal-validation-production-evidence-join",
        "the atomic release must select exactly every production input and evidence artifact",
        release.manifest_path,
    ) in identities(failures)


@pytest.mark.integration
def test_retest_rejects_missing_production_command_selection():
    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, REPO_ROOT)
    snapshot["commands"] = [
        item for item in snapshot["commands"] if item["command_id"] != "typed-exploit-path-valid-v2"
    ]
    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)
    assert (
        "formal-validation-production-command",
        "every production evidence case needs one fixed command",
        release.manifest["snapshot_path"],
    ) in identities(failures)


@pytest.mark.parametrize(
    ("artifact", "keys", "value", "rule"),
    [
        ("corpus", ("cases", 0, "case_id"), "", "formal-validation-case-ids"),
        ("snapshot", ("observations",), {}, "formal-validation-observations"),
        ("snapshot", ("participant_observations",), {}, "formal-validation-participant-observations"),
        ("analysis", ("claim_results",), {}, "formal-validation-analysis-results"),
        ("analysis", ("claim_results", 0, "claim_class_id"), "unknown", "formal-validation-analysis-result-join"),
    ],
)
def test_historical_gate_rejects_remaining_integrity_mutations(artifact, keys, value, rule):
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    target = {"corpus": corpus, "snapshot": snapshot, "analysis": analysis}[artifact]
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis, replay_cases=False)
    assert rule in {f.rule_id for f in failures}


@pytest.mark.parametrize(
    ("keys", "value", "rule"),
    [
        (("unexpected",), True, "formal-validation-release-shape"),
        (("revision",), "dev", "formal-validation-release-revision"),
        (("artifacts",), {}, "formal-validation-release-artifacts"),
        (("artifacts", 0, "unexpected"), True, "formal-validation-release-artifact-shape"),
    ],
)
def test_release_gate_rejects_remaining_integrity_mutations(keys, value, rule):
    release = next(
        item for item in copy_bundle(load_release_bundles, REPO_ROOT) if item.manifest["revision"] == "3.0.0"
    )
    target = release.manifest
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    assert rule in {f.rule_id for f in validate_release_bundle(REPO_ROOT, release)}


@pytest.mark.integration
@pytest.mark.parametrize(
    ("artifact", "field", "value", "rule"),
    [
        ("release", "revision", "99.0.0", "formal-validation-retest-release"),
        ("protocol", "revision", "1.0.0", "formal-validation-retest-revision"),
    ],
)
def test_retest_rejects_unsupported_release_or_protocol(artifact, field, value, rule):
    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, REPO_ROOT)
    target = release.manifest if artifact == "release" else protocol
    target[field] = value
    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)
    assert rule in {f.rule_id for f in failures}


@pytest.mark.integration
def test_retest_cannot_rewrite_a_historical_case():
    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, REPO_ROOT)
    corpus["cases"][0]["expected_outcome"] = "invented"
    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)
    assert "formal-validation-historical-retention" in {f.rule_id for f in failures}


def test_unsupported_case_cannot_acquire_a_fabricated_outcome():
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    case = next(item for item in corpus["cases"] if item["replay_mode"] == "unsupported")
    case["expected_outcome"] = "accepted"
    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis, replay_cases=False)
    assert "formal-validation-unsupported-case" in {f.rule_id for f in failures}


def _archived_baseline(evidence_root):
    """Select the frozen archive explicitly, independent of later baseline repairs."""
    import json

    archive = evidence_root / "historical-artifacts"
    pin = json.loads((archive / "pins-v1.json").read_text())["releases"][0]
    manifest = json.loads((archive / (pin["release_sha256"] + ".json")).read_text())
    snapshot = json.loads((archive / (pin["snapshot_sha256"] + ".json")).read_text())
    return {
        "release_path": pin["release_path"],
        "release_sha256": pin["release_sha256"],
        "release_revision": manifest["revision"],
        "execution_id": snapshot["execution_id"],
    }


def test_archive_cannot_substitute_snapshot_pins_for_an_indexed_release(tmp_path):
    import hashlib
    import json
    from shutil import copytree

    from tools.formal_semantic_validation._baseline import _selected_baseline_manifest
    from tools.formal_semantic_validation._types import MANIFEST_PATH

    root = REPO_ROOT / "docs/research/formal-semantic-validation"
    copytree(root, tmp_path / root.relative_to(REPO_ROOT))
    baseline = _archived_baseline(tmp_path / root.relative_to(REPO_ROOT))
    assert _selected_baseline_manifest(tmp_path, baseline, [], MANIFEST_PATH) is not None
    archive = tmp_path / "docs/research/formal-semantic-validation/historical-artifacts"
    original = json.loads((archive / (baseline["release_sha256"] + ".json")).read_text())
    original["snapshot_sha256"] = "a" * 64
    forged = (json.dumps(original, sort_keys=True) + "\n").encode()
    digest = hashlib.sha256(forged).hexdigest()
    (archive / (digest + ".json")).write_bytes(forged)
    baseline["release_sha256"] = digest
    failures = []
    assert _selected_baseline_manifest(tmp_path, baseline, failures, MANIFEST_PATH) is None
    assert {failure.rule_id for failure in failures} == {"formal-validation-baseline-selection"}


def test_historical_archive_pin_record_cannot_be_rewritten(tmp_path):
    import json
    from shutil import copytree

    from tools.formal_semantic_validation._baseline import _selected_baseline_manifest
    from tools.formal_semantic_validation._types import MANIFEST_PATH

    root = REPO_ROOT / "docs/research/formal-semantic-validation"
    copied = tmp_path / root.relative_to(REPO_ROOT)
    copytree(root, copied)
    baseline = _archived_baseline(copied)
    assert _selected_baseline_manifest(tmp_path, baseline, [], MANIFEST_PATH) is not None
    pins_path = copied / "historical-artifacts/pins-v1.json"
    pins = json.loads(pins_path.read_text())
    pins["source_revision"] = "a" * 40
    pins_path.write_text(json.dumps(pins))
    assert _selected_baseline_manifest(tmp_path, baseline, [], MANIFEST_PATH) is None
