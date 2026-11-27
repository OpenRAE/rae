"""Finite decisions require complete inputs and fresh controls; the hosted check runs the real checker."""

from pathlib import Path

import pytest
from raes_contracts.errors import EvidenceIntegrityError, InvalidInputError

ROOT = Path(__file__).resolve().parents[3]


def test_always_positive_checker_fails_required_negative_controls(monkeypatch):
    from implementations.formal.participant_crossing import counterexample_corpus as corpus
    from implementations.formal.participant_crossing import machine_check as machine
    from tools.mcrl2_tool import Comparison

    monkeypatch.setattr(corpus, "compare", lambda *args, **kwargs: Comparison(True, None))
    with pytest.raises(EvidenceIntegrityError):
        machine.build_bundle(ROOT)


def test_complete_carrier_and_independent_authority_are_required(monkeypatch):
    from dataclasses import replace

    from implementations.formal.participant_crossing import abstract, concrete
    from implementations.formal.participant_crossing import machine_check as machine

    graph = abstract.build()
    monkeypatch.setattr(abstract, "build", lambda: replace(graph, edges=graph.edges[:-1]))
    monkeypatch.setattr(machine, "compare", lambda *args, **kwargs: pytest.fail("incomplete inputs reached checker"))
    with pytest.raises(InvalidInputError, match="closure"):
        machine.build_bundle(ROOT)
    monkeypatch.undo()
    monkeypatch.setattr(concrete, "successors", abstract.successors)
    with pytest.raises(InvalidInputError, match="independent"):
        machine.build_bundle(ROOT)


@pytest.mark.parametrize(
    "dependency",
    [
        "tools/check_tooling_artifact_policy.py",
        "tools/tooling_artifact_selection.py",
        "tools/tooling_artifact_policy_common.py",
        "implementations/tooling/schemas/profiles.schema.json",
        "implementations/tooling/schemas/admission-policy.schema.json",
    ],
)
def test_tooling_validation_dependency_drift_invalidates_both_producers(monkeypatch, dependency):
    from implementations.formal.participant_crossing import counterexample_corpus as corpus
    from implementations.formal.participant_crossing import machine_check as machine

    original = corpus.read_bytes

    def changed(root, name, **kwargs):
        return b"changed authority" if name == dependency else original(root, name, **kwargs)

    monkeypatch.setattr(corpus, "read_bytes", changed)
    monkeypatch.setattr(machine.evidence, "read_bytes", changed)
    monkeypatch.setattr(corpus, "compare", lambda *args, **kwargs: pytest.fail("drift reached native checker"))
    with pytest.raises(EvidenceIntegrityError, match="source drift"):
        machine.check_sources(ROOT)
    with pytest.raises(EvidenceIntegrityError, match="executing source drift"):
        corpus.build_bundle(ROOT)
