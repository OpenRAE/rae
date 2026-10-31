"""Finite decisions require complete inputs, fresh controls and closed evidence."""

from pathlib import Path

import pytest
from raes_contracts.errors import EvidenceIntegrityError, OperationalError
from test_issue_973_crossing_corpus import constructed as constructed

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def result(monkeypatch, constructed):
    from implementations.formal.participant_crossing import machine_check as machine
    from tools.mcrl2_tool import Comparison

    monkeypatch.setattr(machine, "compare", lambda *args, **kwargs: Comparison(True, None))
    return machine.build_bundle(ROOT)


def test_positive_claim_is_bound_to_complete_inputs_and_model_check_axis(result):
    from implementations.formal.participant_crossing import machine_check as machine
    from implementations.formal.participant_crossing.counterexample_corpus import decoded

    record = decoded(result["result.json"])
    assert record["equivalent"] is True
    assert record["claim"]["assurance_axis"] == "model-check"
    assert record["claim"]["evidence_scope"] == "model-check"
    assert record["claim"]["assurance_status"] == "model-checked"
    assert record["claim"]["quantifier_scope"] == "all-admitted-inputs"
    assert record["claim"]["relation_parameter_profile_revision"] == "rev2"
    machine.admit_bundle(ROOT, result, machine.digest(result["manifest.json"]))


@pytest.mark.parametrize("field,value", [("equivalent", "true"), ("equivalent", 1), ("claim", {}), ("extra", True)])
def test_result_tampering_cannot_be_accepted_with_a_replaced_manifest(result, field, value):
    from implementations.formal.participant_crossing import machine_check as machine
    from implementations.formal.participant_crossing.counterexample_corpus import decoded, encoded

    record = decoded(result["result.json"])
    record[field] = value
    result["result.json"] = encoded(record)
    manifest = decoded(result["manifest.json"])
    manifest["artifact_digests"]["result.json"] = machine.digest(result["result.json"])
    result["manifest.json"] = encoded(manifest)
    with pytest.raises(EvidenceIntegrityError):
        machine.admit_bundle(ROOT, result, machine.digest(result["manifest.json"]))


def test_checker_failure_never_publishes(monkeypatch, constructed):
    from implementations.formal.participant_crossing import machine_check as machine

    def unavailable(*args, **kwargs):
        raise OperationalError("bounded-tool-failed")

    monkeypatch.setattr(machine, "compare", unavailable)
    monkeypatch.setattr(machine, "publish_bundle", lambda *args, **kwargs: pytest.fail("partial evidence published"))
    with pytest.raises(OperationalError):
        machine.publish(ROOT)


def test_always_positive_checker_fails_required_negative_controls(monkeypatch):
    from implementations.formal.participant_crossing import counterexample_corpus as corpus
    from implementations.formal.participant_crossing import machine_check as machine
    from tools.mcrl2_tool import Comparison

    monkeypatch.setattr(corpus, "compare", lambda *args, **kwargs: Comparison(True, None))
    monkeypatch.setattr(machine, "publish_bundle", lambda *args, **kwargs: pytest.fail("invalid evidence published"))
    with pytest.raises(EvidenceIntegrityError):
        machine.publish(ROOT)


def test_negative_baseline_without_supported_witness_cannot_publish(monkeypatch, constructed):
    from implementations.formal.participant_crossing import machine_check as machine
    from tools.mcrl2_tool import Comparison

    monkeypatch.setattr(machine, "compare", lambda *args, **kwargs: Comparison(False, None))
    monkeypatch.setattr(machine, "publish_bundle", lambda *args, **kwargs: pytest.fail("unsupported result published"))
    with pytest.raises(EvidenceIntegrityError, match="counterexample"):
        machine.publish(ROOT)


@pytest.mark.parametrize("fault", ["counts", "tool", "proof", "inventory", "input", "pin", "authenticity"])
def test_admission_refuses_faults(result, fault):
    from implementations.formal.participant_crossing import machine_check as machine
    from implementations.formal.participant_crossing.counterexample_corpus import decoded, encoded

    pin = machine.digest(result["manifest.json"])
    if fault == "authenticity":
        with pytest.raises(EvidenceIntegrityError, match="unsigned"):
            machine.admit_bundle(ROOT, result, pin, require_authenticity=True)
        return
    if fault == "inventory":
        result["../unsafe"] = b"x"
    elif fault == "input":
        result["abstract.aut"] = b"des (0, 0, 1)\n"
    elif fault == "pin":
        pin = "sha256:" + "0" * 64
    elif fault == "tool":
        doc = decoded(result["manifest.json"])
        doc["tool"]["version"] = "latest"
        result["manifest.json"] = encoded(doc)
        pin = machine.digest(result["manifest.json"])
    else:
        doc = decoded(result["result.json"])
        if fault == "proof":
            doc["claim"]["assurance_axis"] = "proof"
            doc["claim"]["assurance_status"] = "proved"
            doc["claim"]["evidence_scope"] = "proof"
        else:
            doc["models"]["abstract"]["states"] = True
        result["result.json"] = encoded(doc)
    with pytest.raises(EvidenceIntegrityError):
        machine.admit_bundle(ROOT, result, pin)


def test_source_drift_before_or_during_comparison_cannot_publish(monkeypatch, constructed):
    from implementations.formal.participant_crossing import machine_check as machine
    from tools.mcrl2_tool import Comparison

    original = machine.evidence.source_pins

    def changed(*args, **kwargs):
        monkeypatch.setattr(machine.evidence, "source_pins", lambda root: {})
        return Comparison(True, None)

    monkeypatch.setattr(machine, "compare", changed)
    monkeypatch.setattr(machine, "publish_bundle", lambda *args, **kwargs: pytest.fail("stale result published"))
    with pytest.raises(EvidenceIntegrityError, match="source drift"):
        machine.publish(ROOT)
    assert original(ROOT)


def test_complete_carrier_and_independent_authority_are_required(monkeypatch):
    from dataclasses import replace

    from raes_contracts.errors import InvalidInputError

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
