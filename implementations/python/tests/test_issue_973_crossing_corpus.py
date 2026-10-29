"""Corpus admission and deterministic evidence construction."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def constructed(monkeypatch):
    """Replay recorded tool outputs in unit tests; hosted replay uses the real tool."""
    from implementations.formal.participant_crossing import counterexample_corpus as corpus
    from tools.mcrl2_tool import Comparison

    retained, _ = corpus.load_retained(ROOT)
    records = corpus.decoded(retained["results.json"])

    def replay(root, left, right, mode, *, formula=False):
        if left == right:
            return Comparison(True, None)
        for name, record in records["cases"].items():
            if right == retained[name + ".aut"]:
                if left == retained["concrete.aut"]:
                    return Comparison(record["isolated_concrete_dpbranching_bisim"], None)
                assert left == retained["abstract.aut"]
                return Comparison(record["observed"][mode], retained.get(name + ".mcf") if formula else None)
        for row in corpus.calibrations():
            if (left, right) == (row["left"], row["right"]):
                return Comparison(records["calibrations"][row["id"]]["observed"][mode], None)
        pytest.fail("unexpected model pair")

    monkeypatch.setattr(corpus, "compare", replay)
    return corpus.build_bundle(ROOT)


def test_construction_preserves_measured_artifacts(constructed) -> None:
    from implementations.formal.participant_crossing import counterexample_corpus as corpus

    retained, _ = corpus.load_retained(ROOT)
    assert all(constructed[name] == retained[name] for name in retained if name != "manifest.json")
    corpus.admit_bundle(ROOT, constructed, corpus.digest(constructed["manifest.json"]))


@pytest.mark.parametrize(
    "field,value", [("schema", "unknown/v1"), ("non_claims", []), ("untrusted_policy", {"allow": True})]
)
def test_metadata_is_closed_even_with_a_new_pin(constructed, field, value) -> None:
    from implementations.formal.participant_crossing import counterexample_corpus as corpus

    manifest = corpus.decoded(constructed["manifest.json"])
    manifest[field] = value
    constructed["manifest.json"] = corpus.encoded(manifest)
    with pytest.raises(ValueError, match="metadata"):
        corpus.admit_bundle(ROOT, constructed, corpus.digest(constructed["manifest.json"]))


def test_executing_source_drift_stops_before_checker(monkeypatch) -> None:
    from implementations.formal.participant_crossing import counterexample_corpus as corpus

    original = corpus.read_bytes
    path = "implementations/formal/participant_crossing/counterexample_mutations.py"
    monkeypatch.setattr(
        corpus,
        "read_bytes",
        lambda root, name, **kwargs: b"changed" if name == path else original(root, name, **kwargs),
    )
    monkeypatch.setattr(corpus, "compare", lambda *args, **kwargs: pytest.fail("checker ran with stale source"))
    with pytest.raises(ValueError, match="executing source"):
        corpus.build_bundle(ROOT)


def test_calibration_pairs_keep_distinct_relation_expectations() -> None:
    from implementations.formal.participant_crossing.aut import parse_aut
    from implementations.formal.participant_crossing.counterexample_corpus import calibrations

    pairs = calibrations()
    assert {row["id"]: row["expected"] for row in pairs} == {
        "finite-stutter": [False, True, True, True],
        "weak-choice": [False, True, False, False],
        "internal-divergence": [False, True, True, False],
    }
    for pair in pairs:
        parse_aut(pair["left"])
        parse_aut(pair["right"])


def test_corpus_inventory_refuses_paths_and_missing_cases() -> None:
    from implementations.formal.participant_crossing.counterexample_corpus import validate_inventory

    for bundle in ({"../escape": b"x"}, {}, {"manifest.json": b"{}"}):
        with pytest.raises(ValueError, match="invalid corpus inventory"):
            validate_inventory(bundle)


def test_failure_does_not_publish_completed_corpus(monkeypatch: pytest.MonkeyPatch) -> None:
    from implementations.formal.participant_crossing import counterexample_corpus as corpus

    monkeypatch.setattr(
        corpus, "compare", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("bounded-tool-failed"))
    )
    monkeypatch.setattr(corpus, "publish_bundle", lambda *args, **kwargs: pytest.fail("partial corpus published"))
    with pytest.raises(RuntimeError, match="bounded-tool-failed"):
        corpus.publish(ROOT)


@pytest.mark.parametrize(
    "fault",
    [
        "manifest",
        "joint-replacement",
        "missing-case",
        "unsafe-name",
        "stale-review",
        "authenticity",
        "policy-substitution",
    ],
)
def test_pinned_admission_rejects_tampering(fault: str) -> None:
    from implementations.formal.participant_crossing.counterexample_corpus import (
        admit_bundle,
        decoded,
        encoded,
        load_retained,
    )
    from implementations.formal.participant_crossing.export import digest

    bundle, pin = load_retained(ROOT)
    admit_bundle(ROOT, bundle, pin)
    if fault == "authenticity":
        with pytest.raises(ValueError, match="unsigned"):
            admit_bundle(ROOT, bundle, pin, require_authenticity=True)
        return
    if fault == "unsafe-name":
        bundle["../escaped"] = b"unsafe"
    elif fault == "missing-case":
        del bundle["hidden-denial.aut"]
    else:
        manifest = decoded(bundle["manifest.json"])
        if fault == "joint-replacement":
            bundle["hidden-denial.aut"] = bundle["concrete.aut"]
            manifest["artifact_digests"]["hidden-denial.aut"] = digest(bundle["hidden-denial.aut"])
        elif fault == "stale-review":
            manifest["review_subject_digest"] = "sha256:" + "0" * 64
        elif fault == "policy-substitution":
            manifest["authenticity"] = "authenticated"
        else:
            manifest["tool"]["version"] = "substituted"
        bundle["manifest.json"] = encoded(manifest)
    with pytest.raises(ValueError):
        admit_bundle(ROOT, bundle, pin)


def test_retained_witnesses_and_source_pins_are_checked() -> None:
    from implementations.formal.participant_crossing.counterexample_corpus import admit_bundle, load_retained

    bundle, pin = load_retained(ROOT)
    admit_bundle(ROOT, bundle, pin)
