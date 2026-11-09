"""Corpus construction from the current sources; the hosted model check runs the real checker (issue #1929)."""

from pathlib import Path

import pytest
from raes_contracts.errors import EvidenceIntegrityError, OperationalError

ROOT = Path(__file__).resolve().parents[3]


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
    with pytest.raises(EvidenceIntegrityError, match="executing source"):
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
        with pytest.raises(EvidenceIntegrityError, match="invalid corpus inventory"):
            validate_inventory(bundle)


def test_tool_failure_stops_the_corpus_build(monkeypatch: pytest.MonkeyPatch) -> None:
    from implementations.formal.participant_crossing import counterexample_corpus as corpus

    monkeypatch.setattr(
        corpus, "compare", lambda *args, **kwargs: (_ for _ in ()).throw(OperationalError("bounded-tool-failed"))
    )
    with pytest.raises(OperationalError, match="bounded-tool-failed"):
        corpus.build_bundle(ROOT)


def test_unsigned_corpus_cannot_satisfy_an_authenticity_policy() -> None:
    from implementations.formal.participant_crossing.counterexample_corpus import admit_bundle, inventory

    bundle = dict.fromkeys(inventory(), b"{}\n")
    with pytest.raises(EvidenceIntegrityError, match="unsigned"):
        admit_bundle(ROOT, bundle, require_authenticity=True)
