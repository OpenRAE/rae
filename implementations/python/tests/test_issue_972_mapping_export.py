"""Mapping artifacts retain exact source and observed-case identities."""

import json
import re

import pytest
from crossing_model_fixtures import ROOT
from crossing_runtime_cases import collect_cases
from implementations.formal.participant_crossing import runtime_mapping_export as export
from raes_contracts.errors import EvidenceIntegrityError, InvalidInputError


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
    assert "contracts/schema-publication/tombstones" in manifest["source_exclusions"]
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


def test_source_inventory_binds_mapping_test_drivers_only():
    pins = export.source_pins(ROOT)
    tests = {path.removeprefix("implementations/python/tests/") for path in pins if "/python/tests/" in path}
    assert {
        "crossing_runtime_cases.py",
        "crossing_runtime_observer.py",
        "participant_crossing_fixtures.py",
        "test_issue_972_runtime_mapping.py",
        "test_issue_972_mapping_export.py",
        "test_issue_972_mapping_ownership.py",
    } <= tests
    assert "test_issue_976_crossing_publication.py" not in tests
    assert "test_behavioral_relations.py" not in tests


def test_manifest_stays_within_the_repository_file_size_limit(reports):
    # check-added-large-files refuses files above 500 KiB.
    assert len(export.build_bundle(ROOT, reports)["manifest.json"]) <= 500 * 1024


def test_historical_schema_tombstones_are_not_live_mapping_sources():
    pins = export.source_pins(ROOT)
    assert not any(path.startswith("contracts/schema-publication/tombstones/") for path in pins)
    assert export.export.PROFILE_PATH in pins
    assert "contracts/schema-publication-manifest.json" in pins


def test_symlinked_source_directory_is_rejected(tmp_path, monkeypatch):
    directory = tmp_path / "implementations/python/packages"
    directory.mkdir(parents=True)
    (directory / "unbound").symlink_to(
        ROOT / "implementations/python/packages/raes_contracts", target_is_directory=True
    )
    monkeypatch.setattr(export, "read_bytes", lambda *args, **kwargs: b"synthetic")
    with pytest.raises(InvalidInputError, match="unsafe mapping source directory"):
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
    with (
        patch.object(export, "build_bundle", return_value=candidate),
        pytest.raises(EvidenceIntegrityError, match="drift"),
    ):
        export.check(tmp_path, reports)
    assert {name: (tmp_path / export.OUTPUT_PATH / name).read_bytes() for name in expected} == before


def test_release_version_bump_keeps_mapping_capture_identity():
    from tools.research_evidence import RELEASE_MANAGED_VERSION_SOURCE

    current = (ROOT / RELEASE_MANAGED_VERSION_SOURCE).read_bytes()
    released = re.sub(rb'(__version__ = ")[^"]+(")', rb"\g<1>999.0.0\g<2>", current, count=1)
    assert released != current
    reads = []

    def read_bytes(root, relative, max_bytes):
        reads.append(relative)
        if relative == RELEASE_MANAGED_VERSION_SOURCE:
            return released
        return (ROOT / relative).read_bytes()

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(export, "read_bytes", read_bytes)
        pins = export.source_pins(ROOT)
    assert RELEASE_MANAGED_VERSION_SOURCE in reads
    assert pins == export.source_pins(ROOT)
