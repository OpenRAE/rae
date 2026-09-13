"""Independent arithmetic oracles and small evidence-validator fixtures."""

from hashlib import sha256

import pytest
from evidence_test_fixtures import copy_bundle
from tools.specification_coverage import _artifacts, _protocol
from tools.specification_coverage._analysis import recompute_analysis


def test_cached_evidence_is_loaded_once_and_copied_per_test(tmp_path):
    calls = []

    def load(root):
        calls.append(root)
        return {"observations": [{"outcome": "accepted"}]}

    first = copy_bundle(load, tmp_path)
    first["observations"][0]["outcome"] = "mutated"
    assert copy_bundle(load, tmp_path) == {"observations": [{"outcome": "accepted"}]}
    assert calls == [tmp_path]


def analysis_inputs(rows):
    concepts, results = [], []
    for index, (classification, load_bearing, outcome) in enumerate(rows):
        concept_id = f"concept-{index}"
        concepts.append(
            {"concept_id": concept_id, "load_bearing": load_bearing, "expected_classification": classification}
        )
        results.append(
            {
                "concept_id": concept_id,
                "classification": classification,
                "stage_results": [{"outcome": outcome}],
                "backend_vocabulary_occurrences": [],
            }
        )
    return {
        "concepts": concepts,
        "requests": [{"request_id": "request", "concept_ids": [item["concept_id"] for item in concepts]}],
    }, {"execution_status": "complete", "concept_results": results}


def test_analysis_arithmetic_has_an_independent_mixed_classification_oracle():
    protocol, snapshot = analysis_inputs(
        [
            ("directly-expressible", True, "passed"),
            ("profile-or-manifest-constraint", True, "passed"),
            ("profile-or-manifest-constraint", True, "failed"),
            ("missing", True, "unsupported"),
            ("deliberately-backend-specific", False, "not_applicable"),
            ("directly-expressible", False, "passed"),
        ]
    )
    actual = recompute_analysis(protocol, snapshot, {})
    assert actual["classification_counts"] == {
        "directly-expressible": 2,
        "profile-or-manifest-constraint": 2,
        "deliberately-backend-specific": 1,
        "missing": 1,
    }
    assert actual["load_bearing_results"] == {"total": 4, "passed": 2, "failed": 1, "missing": 1}
    assert actual["request_results"] == [
        {"request_id": "request", "status": "refuted", "concept_count": 6, "missing_count": 1, "failed_stage_count": 1}
    ]
    assert actual["evidence_status"] == "refuted"


@pytest.mark.parametrize(
    ("classification", "outcome", "expected"),
    [
        ("directly-expressible", "passed", "demonstrated"),
        ("directly-expressible", "failed", "partial"),
        ("missing", "unsupported", "partial"),
    ],
)
def test_noncritical_evidence_status_is_derived_independently(classification, outcome, expected):
    protocol, snapshot = analysis_inputs([(classification, False, outcome)])
    result = recompute_analysis(protocol, snapshot, {"evidence_status": "invented"})
    assert result["evidence_status"] == expected
    assert result["request_results"][0]["status"] == expected
    assert result["load_bearing_results"] == {"total": 0, "passed": 0, "failed": 0, "missing": 0}


@pytest.mark.parametrize(
    ("field", "value", "rule", "message"),
    [
        ("stratum_id", "unknown", "specification-coverage-sources", "source has unknown stratum"),
        ("artifact_path", "../outside", "specification-coverage-source-path", "source path is unsafe or missing"),
        ("content_sha256", "0" * 64, "specification-coverage-source-digest", "source digest is stale"),
    ],
)
def test_synthetic_source_integrity(tmp_path, field, value, rule, message):
    (tmp_path / "source.txt").write_bytes(b"source")
    source = {
        "source_id": "source",
        "stratum_id": "study",
        "locator": "https://example.invalid/study",
        "artifact_path": "source.txt",
        "content_sha256": sha256(b"source").hexdigest(),
    }
    failures = []
    _protocol._source_entry_failures(tmp_path, source, {"study"}, failures, "protocol.json")
    assert failures == []
    source[field] = value
    _protocol._source_entry_failures(tmp_path, source, {"study"}, failures, "protocol.json")
    assert [(f.rule_id, f.message) for f in failures] == [(rule, message)]


def test_synthetic_request_rejects_a_source_from_another_stratum():
    request = {"source_refs": ["source"], "stratum_id": "study"}
    sources = [{"source_id": "source", "stratum_id": "study"}]
    failures = []
    _protocol._request_entry_failures(request, sources, {"source"}, {"study", "survey"}, failures, "protocol.json")
    assert failures == []
    sources[0]["stratum_id"] = "survey"
    _protocol._request_entry_failures(request, sources, {"source"}, {"study", "survey"}, failures, "protocol.json")
    assert [(f.rule_id, f.message) for f in failures] == [
        ("specification-coverage-requests", "request/source stratum mismatch")
    ]


@pytest.mark.parametrize("error", [OSError, ValueError, TypeError])
def test_artifact_execution_errors_become_explicit_failures(tmp_path, monkeypatch, error):
    def fail(*_args):
        raise error("seeded replay failure")

    monkeypatch.setattr(_artifacts, "_execute_artifact", fail)
    failures, executed = [], {}
    _artifacts._record_artifact_execution(
        tmp_path, {"artifact_id": "artifact", "kind": "sdl"}, "input.yaml", tmp_path / "input.yaml", executed, failures
    )
    assert executed == {}
    assert [(f.rule_id, f.message, f.path) for f in failures] == [
        (
            "specification-coverage-artifact-execution",
            "artifact 'artifact' failed its production boundary: seeded replay failure",
            "input.yaml",
        )
    ]
