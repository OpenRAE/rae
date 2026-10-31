"""Retained qualified measurements, execution provenance and acceptance stay joined."""

from pathlib import Path

import pytest
from implementations.formal.participant_crossing import machine_check, reproduction, reproduction_record
from raes_contracts.errors import EvidenceIntegrityError

ROOT = Path(__file__).resolve().parents[3]


def test_retained_qualified_reproduction_has_exact_artifacts_and_agent_acceptance():
    record = reproduction_record.admit_record(ROOT)
    _, subject = machine_check.load_retained(ROOT)
    measurement, execution, review = record["measurement"], record["execution"], record["review"]
    assert measurement["expected_manifest_digest"] == measurement["actual_manifest_digest"] == subject
    assert execution["execution"]["manifest_digest"] == subject
    assert execution["execution"]["host_profile"] == "model-check-ubuntu-26.04-x86_64"
    assert execution["execution"]["python_profile"] == "public-linux-x86_64-cp314-all-extras"
    assert review["decision"] == "accepted-bounded-reproduction"
    assert review["reviewer_role"] == "implementation-agent"
    assert review["reviewer_ref"] != review["producer_ref"]
    assert review["acceptance_record_ref"].startswith("https://github.com/OpenRAE/rae/issues/976#issuecomment-")


@pytest.mark.parametrize("fault", ["payload", "subject", "sources"])
def test_retained_admission_refuses_replacement_subject_and_source_maps(fault):
    bundle, _ = reproduction_record.load_record(ROOT)
    _, subject = machine_check.load_retained(ROOT)
    if fault == "payload":
        bundle["measurement.json"] += b" "
    elif fault == "subject":
        subject = "sha256:" + "0" * 64
    else:
        record = reproduction.decoded(bundle["measurement.json"])
        record["reproducer_sources"] = {"unrelated.py": "sha256:" + "0" * 64}
        bundle["measurement.json"] = reproduction.encoded(record)
    with pytest.raises(EvidenceIntegrityError):
        reproduction_record.admit_capture(ROOT, bundle, subject)
