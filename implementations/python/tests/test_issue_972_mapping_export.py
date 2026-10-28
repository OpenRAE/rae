"""Mapping artifacts retain exact source and observed-case identities."""

import json

import pytest
from crossing_model_fixtures import ROOT
from crossing_runtime_cases import collect_cases
from implementations.formal.participant_crossing import runtime_mapping_export as export


@pytest.fixture(scope="module")
def reports():
    return collect_cases()


def test_bundle_is_deterministic_and_keeps_claims_separate(reports):
    bundle = export.build_bundle(ROOT, reports)
    assert bundle == export.build_bundle(ROOT, reports)
    manifest = json.loads(bundle["manifest.json"])
    assert manifest["profile"] == "participant-crossing-dpbb-finite-v1@rev2"
    assert manifest["equivalence_result"] == manifest["runtime_realization"] == "not-established"
    assert manifest["historical_source_drift"]
    assert manifest["case_counts"]["match"] >= 4
    assert manifest["case_counts"]["incompatible"] > 0
    assert reports["ingress/backend-failure"]["classification"] == "incompatible"
    assert reports["ingress/backend-failure"]["operation_outcomes"] == ["failed"]
    assert reports["ingress/backend-failure"]["runtime_safety_issues"] == []
    assert "participant_crossing_egress.py" in str(manifest["source_digests"])
    assert "participant_control_effects.py" in str(manifest["source_digests"])
    assert "participant_decision_surface_control_v2.py" in str(manifest["source_digests"])


def test_published_cases_match_fresh_public_execution(reports):
    export.check(ROOT, reports)


def test_symlinked_source_directory_is_rejected(tmp_path, monkeypatch):
    directory = tmp_path / "implementations/python/packages"
    directory.mkdir(parents=True)
    (directory / "unbound").symlink_to(
        ROOT / "implementations/python/packages/raes_contracts", target_is_directory=True
    )
    monkeypatch.setattr(export, "read_bytes", lambda *args, **kwargs: b"synthetic")
    with pytest.raises(ValueError, match="unsafe mapping source directory"):
        export.source_pins(tmp_path)


@pytest.mark.parametrize("fault", ["source", "artifact", "profile", "case"])
def test_drift_is_rejected_without_overwriting_artifacts(tmp_path, reports, fault):
    from unittest.mock import patch

    expected = export.build_bundle(ROOT, reports)
    for name, data in expected.items():
        path = tmp_path / export.OUTPUT_PATH / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    if fault == "case":
        changed = dict(reports)
        changed["ingress/plain/p0"] = dict(changed["ingress/plain/p0"], classification="match")
        candidate = export.build_bundle(ROOT, changed)
    else:
        candidate = dict(expected)
        if fault == "artifact":
            (tmp_path / export.OUTPUT_PATH / "cases.json").write_bytes(b"{}\n")
        else:
            manifest = json.loads(candidate["manifest.json"])
            manifest["source_digests" if fault == "source" else "profile"] = "changed"
            candidate["manifest.json"] = json.dumps(manifest).encode()
    before = {name: (tmp_path / export.OUTPUT_PATH / name).read_bytes() for name in expected}
    with patch.object(export, "build_bundle", return_value=candidate), pytest.raises(ValueError, match="drift"):
        export.check(tmp_path, reports)
    assert {name: (tmp_path / export.OUTPUT_PATH / name).read_bytes() for name in expected} == before
