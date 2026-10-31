"""Retained qualified measurements, execution provenance and acceptance stay joined."""

import re
from pathlib import Path

from implementations.formal.participant_crossing import reproduction
from implementations.formal.participant_crossing.ingress import read_bytes

ROOT = Path(__file__).resolve().parents[3]
PREFIX = "specs/formal/participant-semantics/reproduction"


def test_retained_qualified_reproduction_has_exact_artifacts_and_agent_acceptance():
    pin = reproduction.decoded(read_bytes(ROOT, PREFIX + "/pin.json"))
    assert set(pin) == {"schema", "manifest_digest"}
    assert pin["schema"] == "participant-crossing-reproduction-pin/v1"
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", pin["manifest_digest"])
    directory = PREFIX + "/capture-" + pin["manifest_digest"].split(":", 1)[1]
    manifest_bytes = read_bytes(ROOT, directory + "/manifest.json")
    assert reproduction.digest(manifest_bytes) == pin["manifest_digest"]
    manifest = reproduction.decoded(manifest_bytes)
    assert set(manifest) == {"schema", "target_manifest_digest", "artifact_digests", "authenticity"}
    assert manifest["schema"] == "participant-crossing-reproduction-capture/v1"
    assert manifest["authenticity"] == "unsigned"
    assert set(manifest["artifact_digests"]) == {"measurement.json", "execution.json", "review.json"}
    assert {p.name for p in (ROOT / directory).iterdir()} == {"manifest.json", *manifest["artifact_digests"]}
    bundle = {name: read_bytes(ROOT, directory + "/" + name) for name in manifest["artifact_digests"]}
    assert {name: reproduction.digest(payload) for name, payload in bundle.items()} == manifest["artifact_digests"]
    reproduction.admit_measurement(ROOT, bundle["measurement.json"], manifest["target_manifest_digest"])
    measurement = reproduction.decoded(bundle["measurement.json"])
    execution = reproduction.decoded(bundle["execution.json"])
    review = reproduction.decoded(bundle["review.json"])
    assert set(execution) == {"schema", "measurement_digest", "execution", "review_acceptance"}
    assert execution["schema"] == "participant-crossing-reproduction-execution/v1"
    assert execution["measurement_digest"] == reproduction.digest(bundle["measurement.json"])
    context = execution["execution"]
    assert context["manifest_digest"] == manifest["target_manifest_digest"]
    assert context["host_profile"] == "model-check-ubuntu-26.04-x86_64"
    assert context["python_profile"] == "public-linux-x86_64-cp314-all-extras"
    assert measurement["review_acceptance"] == execution["review_acceptance"] == "required"
    assert review["decision"] == "accepted-bounded-reproduction"
    assert review["measurement_digest"] == execution["measurement_digest"]
    assert review["execution_digest"] == reproduction.digest(bundle["execution.json"])
    assert review["claim_digest"] == measurement["claim_digest"]
    assert review["mutation_review_subject_digest"] == measurement["mutation_review_subject_digest"]
    assert review["reviewer_role"] == measurement["reproducer_role"] == "implementation-agent"
    assert review["reviewer_ref"] == measurement["reproducer_run_ref"]
    assert review["source_revision"] == context["source_revision"]
    assert review["qualified_run"]["feature_sha"] in review["qualified_run"]["source_parents"]
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", review["qualified_run"]["artifact_digest"])
    assert review["acceptance_record_ref"].startswith("https://github.com/OpenRAE/rae/issues/975#issuecomment-")
