"""New source captures retain earlier progressive evidence without replaying it."""

from copy import deepcopy
from pathlib import Path

import pytest
from tools.check_formal_semantic_validation import load_release_bundles, validate_release_bundle
from tools.formal_semantic_validation import _production, _replay, _retest
from tools.formal_semantic_validation._archival_shape import validate_archival_evidence_shape


def test_prior_progressive_capture_uses_only_frozen_integrity_checks(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    release = next(item for item in load_release_bundles(root) if item.manifest["revision"] == "16.0.0")

    def no_replay(*args, **kwargs):
        pytest.fail("historical validation must not invoke current semantic replay")

    monkeypatch.setattr(_replay, "replay_case", no_replay)
    monkeypatch.setattr(_retest, "replay_case", no_replay)
    monkeypatch.setattr(_production, "_run_production_evidence_cli", no_replay)
    assert validate_release_bundle(root, release) == []


@pytest.mark.parametrize("mode", ["satisfiability", "exploit-path"])
def test_progressive_archival_shapes_reject_changed_recorded_payloads(mode):
    import json

    root = Path(__file__).resolve().parents[3]
    name = "finite-domain-satisfiable-v4.json" if mode == "satisfiability" else "typed-exploit-path-valid-v4.json"
    payload = json.loads((root / "docs/research/formal-semantic-validation/evidence" / name).read_text())
    validate_archival_evidence_shape(root, payload, mode)
    changed = deepcopy(payload)
    changed["source"]["byte_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        validate_archival_evidence_shape(root, changed, mode)
