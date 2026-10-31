"""Retained crossing records bind subject sources; apparatus changes keep them admissible."""

from pathlib import Path

import pytest
from raes_contracts.errors import EvidenceIntegrityError

ROOT = Path(__file__).resolve().parents[3]

APPARATUS_PATHS = (
    "noxfile.py",
    "implementations/python/uv.lock",
    "implementations/python/packages/raes_contracts/scientific_completeness.py",
    "implementations/python/packages/raes_contracts/behavioral_relations.py",
    "implementations/python/packages/raes_runtime/participant_crossing_policy.py",
    "tools/tooling_policy_gate.py",
    "tools/mcrl2_tool.py",
)
SUBJECT_PATHS = (
    "implementations/formal/participant_crossing/counterexample_mutations.py",
    "implementations/formal/participant_crossing/machine_check_evidence.py",
    "specs/formal/participant-semantics/participant-crossing-machine-check.md",
)


def checkout_with_changed(monkeypatch, path: str) -> None:
    """Simulate a checkout whose bytes at ``path`` differ from the producer checkout."""
    from implementations.formal.participant_crossing import counterexample_corpus as corpus
    from implementations.formal.participant_crossing import export, machine_check
    from implementations.formal.participant_crossing import machine_check_evidence as evidence

    original = export.read_bytes

    def changed(root, name, **kwargs):
        content = original(root, name, **kwargs)
        return content + b"\n# changed checkout\n" if name == path else content

    for module in (export, corpus, evidence, machine_check):
        monkeypatch.setattr(module, "read_bytes", changed)
    monkeypatch.setattr(
        export,
        "_EXECUTING_SOURCE_DIGESTS",
        {name: export.digest(changed(ROOT, name)) for name in export._EXECUTING_SOURCE_DIGESTS},
    )
    monkeypatch.setattr(
        corpus, "_EXECUTING_PINS", {name: export.digest(changed(ROOT, name)) for name in corpus.SOURCE_PATHS}
    )
    monkeypatch.setattr(machine_check, "EXECUTING_PINS", evidence.source_pins(ROOT))


def test_subject_sources_are_a_narrow_owned_inventory():
    from implementations.formal.participant_crossing import counterexample_corpus as corpus
    from implementations.formal.participant_crossing import export
    from implementations.formal.participant_crossing import machine_check_evidence as evidence

    assert set(export.SUBJECT_SOURCE_PATHS) < set(corpus.SUBJECT_SOURCE_PATHS) < set(evidence.SUBJECT_SOURCE_PATHS)
    assert set(evidence.SUBJECT_SOURCE_PATHS) < set(evidence.SOURCE_PATHS)
    for path in evidence.SUBJECT_SOURCE_PATHS:
        assert path.startswith(("implementations/formal/participant_crossing/", "specs/formal/", "contracts/profiles/"))
    assert not set(APPARATUS_PATHS) & set(evidence.SUBJECT_SOURCE_PATHS)
    assert set(SUBJECT_PATHS) <= set(evidence.SUBJECT_SOURCE_PATHS)


def test_retained_manifests_bind_subject_sources_only():
    from implementations.formal.participant_crossing import counterexample_corpus as corpus
    from implementations.formal.participant_crossing import export, machine_check
    from implementations.formal.participant_crossing import machine_check_evidence as evidence

    retained_corpus, _ = corpus.load_retained(ROOT)
    retained_check, _ = machine_check.load_retained(ROOT)
    corpus_manifest = corpus.decoded(retained_corpus["manifest.json"])
    check_manifest = corpus.decoded(retained_check["manifest.json"])
    model_manifest = corpus.decoded(retained_check["model-manifest.json"])
    assert set(model_manifest["source_digests"]) == set(export.SUBJECT_SOURCE_PATHS)
    assert set(corpus_manifest["source_digests"]) == set(corpus.SUBJECT_SOURCE_PATHS)
    assert set(check_manifest["source_digests"]) == set(evidence.SUBJECT_SOURCE_PATHS)
    assert "historical_baseline_source_drift" not in corpus_manifest
    assert "historical_baseline_source_drift" not in check_manifest


@pytest.mark.parametrize("path", APPARATUS_PATHS)
def test_apparatus_change_keeps_retained_records_admissible(monkeypatch, path):
    from implementations.formal.participant_crossing import counterexample_corpus as corpus
    from implementations.formal.participant_crossing import machine_check

    checkout_with_changed(monkeypatch, path)
    corpus.admit_bundle(ROOT, *corpus.load_retained(ROOT))
    machine_check.admit_bundle(ROOT, *machine_check.load_retained(ROOT))


@pytest.mark.parametrize("path", SUBJECT_PATHS)
def test_subject_change_refuses_the_retained_machine_check(monkeypatch, path):
    from implementations.formal.participant_crossing import machine_check

    checkout_with_changed(monkeypatch, path)
    with pytest.raises(EvidenceIntegrityError):
        machine_check.admit_bundle(ROOT, *machine_check.load_retained(ROOT))


def test_apparatus_drift_during_a_run_still_stops_the_producer(monkeypatch):
    from implementations.formal.participant_crossing import counterexample_corpus as corpus
    from implementations.formal.participant_crossing import machine_check

    original = corpus.read_bytes

    def changed(root, name, **kwargs):
        content = original(root, name, **kwargs)
        return b"changed" if name == "tools/tooling_policy_gate.py" else content

    monkeypatch.setattr(corpus, "read_bytes", changed)
    monkeypatch.setattr(machine_check.evidence, "read_bytes", changed)
    with pytest.raises(EvidenceIntegrityError, match="source drift"):
        machine_check.check_sources(ROOT)
