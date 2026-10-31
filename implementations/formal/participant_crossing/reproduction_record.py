"""Admit and retain one measured, executed and separately reviewed reproduction capture."""

import argparse
import re
from pathlib import Path

from raes_contracts.errors import EvidenceIntegrityError, RaesError
from raes_contracts.operational_logging import run_application

from . import machine_check as machine
from . import machine_check_publication as publication
from . import reproduction
from . import reproduction_attestation as attestation
from .counterexample_corpus import decoded, encoded
from .export import digest, publish_bundle
from .ingress import read_bytes, safe_path

OUTPUT_ROOT = reproduction.OUTPUT_ROOT
REVIEWED = ("measurement.json", "execution.json", "review.json")
INVENTORY = frozenset({"manifest.json", *REVIEWED})
REVIEWER_ROLES = frozenset({"implementation-agent"})
REVIEW_NONCLAIMS = [
    "runtime-realization",
    "backend-conformance",
    "noninterference",
    "opacity",
    "unbounded-proof",
    "wider-profile",
]
EXECUTION_NONCLAIMS = ["immutable-host", "independent-reproduction"]
EXECUTION_KEYS = frozenset(
    {
        "schema",
        "manifest_digest",
        "source_revision",
        "host_profile",
        "observed_base",
        "observed_repository",
        "native_packages",
        "kernel",
        "python_profile",
        "observed_python",
        "python_lock_digest",
        "tool_lock_digest",
        "sandbox",
        "non_claims",
    }
)
REVIEW_KEYS = frozenset(
    {
        "schema",
        "decision",
        "authenticity",
        "scope",
        "nonclaims",
        "measurement_digest",
        "execution_digest",
        "claim_digest",
        "mutation_review_subject_digest",
        "producer_ref",
        "reviewer_ref",
        "reviewer_role",
        "acceptance_record_ref",
        "source_revision",
        "qualified_run",
    }
)
RUN_KEYS = frozenset({"artifact_digest", "artifact_id", "artifact_name", "feature_sha", "source_parents", "url"})
_ISSUE = r"https://github\.com/OpenRAE/rae/issues/[1-9][0-9]{0,6}"
_ISSUE_REF = re.compile(_ISSUE + r"(?:#issuecomment-[1-9][0-9]{0,19})?")
_COMMENT_REF = re.compile(_ISSUE + r"#issuecomment-[1-9][0-9]{0,19}")
_RUN_URL = re.compile(r"https://github\.com/OpenRAE/rae/actions/runs/[1-9][0-9]{0,19}")
_REVISION = re.compile(r"[0-9a-f]{40}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def _matches(pattern: re.Pattern, value: object) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def capture_bundle(files: dict[str, bytes]) -> dict[str, bytes]:
    """Add the content-addressed manifest to the three reviewed records."""
    if set(files) != set(REVIEWED):
        raise EvidenceIntegrityError("invalid reproduction capture inventory")
    manifest = {
        "schema": "participant-crossing-reproduction-capture/v1",
        "target_manifest_digest": decoded(files["measurement.json"]).get("expected_manifest_digest"),
        "artifact_digests": {name: digest(files[name]) for name in sorted(files)},
        "authenticity": "unsigned",
    }
    return {**files, "manifest.json": encoded(manifest)}


def _admit_execution(payload: bytes, measurement: bytes, subject: str) -> dict:
    document = decoded(payload)
    context = document.get("execution")
    if (
        set(document) != {"schema", "measurement_digest", "execution", "review_acceptance"}
        or document["schema"] != "participant-crossing-reproduction-execution/v1"
        or document["measurement_digest"] != digest(measurement)
        or document["review_acceptance"] != "required"
        or not isinstance(context, dict)
        or set(context) != EXECUTION_KEYS
        or context["schema"] != "participant-crossing-machine-check-execution/v1"
        or context["manifest_digest"] != subject
        or not _matches(_REVISION, context["source_revision"])
        or context["host_profile"] != publication.HOST_PROFILE
        or context["python_profile"] != publication.PYTHON_PROFILE
        or context["sandbox"] != "required-successful-native-replay"
        or context["non_claims"] != EXECUTION_NONCLAIMS
    ):
        raise EvidenceIntegrityError("invalid reproduction execution record")
    return document


def _admit_run(run: object, source_revision: str) -> None:
    parents = run.get("source_parents") if isinstance(run, dict) else None
    if (
        not isinstance(run, dict)
        or set(run) != RUN_KEYS
        or not _matches(_DIGEST, run["artifact_digest"])
        or type(run["artifact_id"]) is not int
        or run["artifact_id"] < 1
        or run["artifact_name"] != "participant-crossing-machine-check-" + source_revision
        or not isinstance(parents, list)
        or not 1 <= len(parents) <= 2
        or len(set(parents)) != len(parents)
        or not all(_matches(_REVISION, parent) for parent in parents)
        or run["feature_sha"] not in parents
        or not _matches(_RUN_URL, run["url"])
    ):
        raise EvidenceIntegrityError("invalid qualified reproduction run")


def _admit_review(payload: bytes, files: dict[str, bytes], execution: dict) -> dict:
    review = decoded(payload)
    measurement = decoded(files["measurement.json"])
    result = measurement["result"]
    source_revision = execution["execution"]["source_revision"]
    if (
        set(review) != REVIEW_KEYS
        or review["schema"] != "participant-crossing-reproduction-review/v1"
        or review["decision"] != "accepted-bounded-reproduction"
        or review["authenticity"] != "unsigned"
        or review["scope"] != f"Complete reachable finite carrier of {result['profile']}; {result['relation']} only."
        or review["nonclaims"] != REVIEW_NONCLAIMS
        or review["measurement_digest"] != digest(files["measurement.json"])
        or review["execution_digest"] != digest(files["execution.json"])
        or review["claim_digest"] != measurement["claim_digest"]
        or review["mutation_review_subject_digest"] != measurement["mutation_review_subject_digest"]
        or review["source_revision"] != source_revision
        or not isinstance(review["reviewer_role"], str)
        or review["reviewer_role"] not in REVIEWER_ROLES
        or not _matches(_ISSUE_REF, review["producer_ref"])
        or not _matches(_COMMENT_REF, review["reviewer_ref"])
        or not _matches(_COMMENT_REF, review["acceptance_record_ref"])
        or review["producer_ref"] in {review["reviewer_ref"], review["acceptance_record_ref"]}
    ):
        raise EvidenceIntegrityError("invalid reproduction review record")
    _admit_run(review["qualified_run"], source_revision)
    return review


def admit_capture(root: Path, bundle: dict[str, bytes], expected_manifest_digest: str) -> dict:
    """Admit one capture for the separately selected machine-check subject."""
    if set(bundle) != INVENTORY or any(type(value) is not bytes for value in bundle.values()):
        raise EvidenceIntegrityError("invalid reproduction capture inventory")
    files = {name: bundle[name] for name in REVIEWED}
    if bundle["manifest.json"] != capture_bundle(files)["manifest.json"]:
        raise EvidenceIntegrityError("invalid reproduction capture manifest")
    reproduction.admit_measurement(root, files["measurement.json"], expected_manifest_digest)
    execution = _admit_execution(files["execution.json"], files["measurement.json"], expected_manifest_digest)
    review = _admit_review(files["review.json"], files, execution)
    return {
        "manifest_digest": digest(bundle["manifest.json"]),
        "artifact_digests": {name: digest(value) for name, value in files.items()},
        "measurement": decoded(files["measurement.json"]),
        "execution": execution,
        "review": review,
    }


def load_record(root: Path) -> tuple[dict[str, bytes], str]:
    pin = decoded(read_bytes(root, OUTPUT_ROOT + "/pin.json", max_bytes=4096))
    if (
        set(pin) != {"schema", "manifest_digest"}
        or pin["schema"] != "participant-crossing-reproduction-pin/v1"
        or not _matches(_DIGEST, pin["manifest_digest"])
    ):
        raise EvidenceIntegrityError("invalid reproduction pin")
    path = OUTPUT_ROOT + "/capture-" + pin["manifest_digest"].split(":", 1)[1]
    if {item.name for item in safe_path(root, path).iterdir()} != INVENTORY:
        raise EvidenceIntegrityError("invalid reproduction capture inventory")
    bundle = {name: read_bytes(root, path + "/" + name) for name in INVENTORY}
    if digest(bundle["manifest.json"]) != pin["manifest_digest"]:
        raise EvidenceIntegrityError("reproduction capture differs from its pin")
    return bundle, pin["manifest_digest"]


def admit_record(root: Path) -> dict:
    """Admit the pinned capture against the currently pinned machine-check subject."""
    bundle, _ = load_record(root)
    _, subject = machine.load_retained(root)
    return admit_capture(root, bundle, subject)


def retain(
    root: Path, staging: str, expected_manifest_digest: str, *, fetch: attestation.Fetch = attestation.github_fetch
) -> str:
    """Write a new capture only after admission and server-record binding both pass."""
    files = {name: read_bytes(root, staging + "/" + name, max_bytes=4 * 1024 * 1024) for name in REVIEWED}
    bundle = capture_bundle(files)
    record = admit_capture(root, bundle, expected_manifest_digest)
    attestation.verify_review_records(
        record["review"], files["measurement.json"], files["execution.json"], expected_manifest_digest, fetch
    )
    path = OUTPUT_ROOT + "/capture-" + digest(bundle["manifest.json"]).split(":", 1)[1]
    publish_bundle(root, bundle, path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-manifest", required=True)
    parser.add_argument("--staging", required=True, help="repository-relative directory with the reviewed records")
    args = parser.parse_args()
    try:
        path = retain(reproduction.ROOT, args.staging, args.expected_manifest)
    except OSError, RaesError:
        print("crossing reproduction: capture refused")
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
