"""Fresh measurements retain the exact finite claim and require separate review."""

from pathlib import Path

import pytest
from raes_contracts.errors import EvidenceIntegrityError, OperationalError
from test_issue_973_crossing_corpus import constructed as constructed
from test_issue_974_machine_check import result as result

ROOT = Path(__file__).resolve().parents[3]


def prepare(monkeypatch, result):
    from implementations.formal.participant_crossing import reproduction

    pin = reproduction.digest(result["manifest.json"])
    monkeypatch.setattr(reproduction.machine, "load_retained", lambda root: (dict(result), pin))
    return reproduction, pin


def test_measure_requires_fresh_bytes_and_retains_the_exact_claim(monkeypatch, result):
    reproduction, pin = prepare(monkeypatch, result)
    calls = []

    def fresh(root):
        calls.append(root)
        return dict(result)

    monkeypatch.setattr(reproduction.sandbox, "replay", fresh)
    payload = reproduction.measure(ROOT, pin)
    record = reproduction.decoded(payload)
    assert calls == [ROOT]
    assert record["expected_manifest_digest"] == record["actual_manifest_digest"] == pin
    assert record["claim_digest"] == reproduction.canonical_json_digest(
        reproduction.decoded(result["result.json"])["claim"]
    )
    assert record["result"] == reproduction.decoded(result["result.json"])
    assert record["review_acceptance"] == "required"
    assert record["producer_run_ref"] == "https://github.com/OpenRAE/rae/issues/974"
    assert record["reproducer_run_ref"].endswith("/975#issuecomment-6539701555")
    assert record["reproducer_role"] == "implementation-agent"
    assert "runtime-realization" in record["result"]["non_claims"]
    reproduction.admit_measurement(ROOT, payload, pin)


@pytest.mark.parametrize("name", ["abstract.aut", "result.json", "mutation-results.json", "manifest.json"])
def test_no_result_or_mutation_difference_can_publish(monkeypatch, result, name):
    reproduction, pin = prepare(monkeypatch, result)
    actual = dict(result)
    actual[name] += b" "
    monkeypatch.setattr(reproduction.sandbox, "replay", lambda root: actual)
    with pytest.raises(EvidenceIntegrityError, match="reproduction differs"):
        reproduction.measure(ROOT, pin)


def test_candidate_cannot_select_its_own_expected_pin(monkeypatch, result):
    reproduction, pin = prepare(monkeypatch, result)
    monkeypatch.setattr(reproduction.sandbox, "replay", lambda root: pytest.fail("wrong subject reached execution"))
    with pytest.raises(EvidenceIntegrityError, match="selected subject"):
        reproduction.measure(ROOT, "sha256:" + "0" * 64)


def test_worker_failure_never_becomes_a_measurement(monkeypatch, result):
    reproduction, pin = prepare(monkeypatch, result)

    def failed(root):
        raise OperationalError("bounded-tool-failed")

    monkeypatch.setattr(reproduction.sandbox, "replay", failed)
    with pytest.raises(OperationalError):
        reproduction.measure(ROOT, pin)


def test_qualified_publication_binds_measured_bytes_to_separate_host_provenance(monkeypatch, result):
    reproduction, pin = prepare(monkeypatch, result)
    monkeypatch.setattr(reproduction.sandbox, "replay", lambda root: dict(result))
    from implementations.formal.participant_crossing import machine_check_publication as publication

    monkeypatch.setattr(publication, "execution_record", lambda root, subject: {"manifest_digest": subject})
    published = []
    monkeypatch.setattr(reproduction, "publish_bundle", lambda root, bundle, path: published.append(bundle))
    reproduction.publish_qualified(ROOT, pin)
    assert len(published) == 1
    bundle = published[0]
    assert set(bundle) == {"measurement.json", "execution.json"}
    execution = reproduction.decoded(bundle["execution.json"])
    assert execution["measurement_digest"] == reproduction.digest(bundle["measurement.json"])
    assert execution["execution"]["manifest_digest"] == pin
    assert execution["review_acceptance"] == "required"


@pytest.mark.parametrize("fault", ["approval", "counts", "tau", "mutations", "nonclaims", "extra"])
def test_measurement_admission_refuses_promotion_and_drift(monkeypatch, result, fault):
    reproduction, pin = prepare(monkeypatch, result)
    monkeypatch.setattr(reproduction.sandbox, "replay", lambda root: dict(result))
    record = reproduction.decoded(reproduction.measure(ROOT, pin))
    if fault == "approval":
        record["review_acceptance"] = "approved"
    elif fault == "counts":
        record["result"]["models"]["abstract"]["states"] = True
    elif fault == "tau":
        record["verification"]["tau"] = ["internal", "crossing.denied"]
    elif fault == "mutations":
        record["mutations"] = {}
    elif fault == "nonclaims":
        record["result"]["non_claims"] = []
    else:
        record["reviewer"] = "self-approved"
    payload = reproduction.encoded(record)
    with pytest.raises(EvidenceIntegrityError):
        reproduction.admit_measurement(ROOT, payload, pin)
