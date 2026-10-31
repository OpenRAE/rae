"""New source captures retain earlier progressive evidence without replaying it."""

from copy import deepcopy
from pathlib import Path

import pytest
from raes_contracts.errors import EvidenceIntegrityError
from tools.check_formal_semantic_validation import load_release_bundles, validate_release_bundle
from tools.formal_semantic_validation import _production, _releases, _replay, _retest
from tools.formal_semantic_validation._archival_invariants import validate_archival_evidence_invariants
from tools.formal_semantic_validation._archival_shape import validate_archival_evidence_shape
from tools.formal_semantic_validation._release_revisions import source_bound_revision

ROOT = Path(__file__).resolve().parents[3]
SOURCE_BOUND_RELEASES = [
    item.manifest["revision"] for item in load_release_bundles(ROOT) if source_bound_revision(item.manifest["revision"])
]


@pytest.mark.parametrize("revision", SOURCE_BOUND_RELEASES)
@pytest.mark.parametrize("tampered", [False, True])
def test_each_source_bound_release_checks_its_explicit_baseline(revision, tampered):
    root = Path(__file__).resolve().parents[3]
    release = next(item for item in load_release_bundles(root) if item.manifest["revision"] == revision)
    snapshot = deepcopy(release.snapshot)
    if tampered:
        snapshot["baseline"]["release_revision"] = revision
    failures = []
    _releases._current_retest_source_failures(
        root,
        snapshot,
        failures,
        release.manifest["snapshot_path"],
        release_revision=revision,
    )
    assert [failure.rule_id for failure in failures] == (["formal-validation-baseline-selection"] if tampered else [])


@pytest.mark.parametrize("revision", ["16.0.0", "17.0.0", "18.0.0"])
def test_prior_progressive_capture_uses_only_frozen_integrity_checks(monkeypatch, revision):
    root = Path(__file__).resolve().parents[3]
    release = next(item for item in load_release_bundles(root) if item.manifest["revision"] == revision)

    def no_replay(*args, **kwargs):
        pytest.fail("historical validation must not invoke current semantic replay")

    monkeypatch.setattr(_replay, "replay_case", no_replay)
    monkeypatch.setattr(_retest, "replay_case", no_replay)
    monkeypatch.setattr(_production, "_run_production_evidence_cli", no_replay)
    assert validate_release_bundle(root, release) == []


@pytest.mark.parametrize("mode", ["satisfiability", "exploit-path"])
def test_progressive_archival_admission_rejects_changed_recorded_payloads(mode):
    import json

    root = Path(__file__).resolve().parents[3]
    name = "finite-domain-satisfiable-v4.json" if mode == "satisfiability" else "typed-exploit-path-valid-v4.json"
    payload = json.loads((root / "docs/research/formal-semantic-validation/evidence" / name).read_text())
    validate_archival_evidence_shape(root, payload, mode)
    validate_archival_evidence_invariants(payload, mode)
    changed = deepcopy(payload)
    changed["source"]["byte_digest"] = "sha256:" + "0" * 64
    validate_archival_evidence_shape(root, changed, mode)
    with pytest.raises(EvidenceIntegrityError, match="historical evidence invariant failed"):
        validate_archival_evidence_invariants(changed, mode)
