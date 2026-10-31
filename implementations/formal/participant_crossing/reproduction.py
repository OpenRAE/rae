"""Measure a fresh finite replay without asserting independent reviewer acceptance."""

import argparse
import re
from pathlib import Path

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.errors import EvidenceIntegrityError, RaesError
from raes_contracts.operational_logging import run_application

from . import machine_check as machine
from . import machine_check_publication as publication
from . import reproduction_checks as checks
from . import reproduction_sandbox as sandbox
from .counterexample_corpus import decoded, encoded
from .export import digest, publish_bundle
from .ingress import read_bytes

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = "specs/formal/participant-semantics/reproduction"
SOURCE_PATHS = (
    *sandbox.EXTRA_SOURCE_PATHS,
    *tuple(
        "implementations/formal/participant_crossing/" + name for name in ("reproduction.py", "reproduction_sandbox.py")
    ),
)


def source_pins(root: Path) -> dict[str, str]:
    return {
        name: digest(read_bytes(root, name)) for name in sorted({*SOURCE_PATHS, *sandbox.package_source_paths(root)})
    }


def selected_bundle(root: Path, expected_manifest_digest: str) -> dict[str, bytes]:
    bundle, pin = machine.load_retained(root)
    if pin != expected_manifest_digest:
        raise EvidenceIntegrityError("reproduction selected subject mismatch")
    machine.admit_bundle(root, bundle, expected_manifest_digest)
    return bundle


def measurement_record(root: Path, bundle: dict[str, bytes]) -> dict:
    return _measurement_record(bundle, source_pins(root))


def _measurement_record(bundle: dict[str, bytes], reproducer_sources: dict[str, str]) -> dict:
    manifest = decoded(bundle["manifest.json"])
    result = decoded(bundle["result.json"])
    return {
        "schema": "participant-crossing-reproduction-measurement/v1",
        "producer_run_ref": "https://github.com/OpenRAE/rae/issues/974",
        "reproducer_run_ref": "https://github.com/OpenRAE/rae/issues/975#issuecomment-6539701555",
        "reproducer_role": "implementation-agent",
        "expected_manifest_digest": digest(bundle["manifest.json"]),
        "actual_manifest_digest": digest(bundle["manifest.json"]),
        "claim_digest": canonical_json_digest(result["claim"]),
        "artifact_digests": {name: digest(value) for name, value in sorted(bundle.items())},
        "producer_source_identity": manifest["source_identity"],
        "reproducer_sources": reproducer_sources,
        "corpus_manifest_digest": manifest["corpus_manifest_digest"],
        "mutation_review_subject_digest": manifest["mutation_review_subject_digest"],
        "tool": manifest["tool"],
        "verification": manifest["verification"],
        "replay_verification": checks.VERIFICATION,
        "result": result,
        "mutations": decoded(bundle["mutation-results.json"]),
        "execution_boundary": "fresh-offline-single-worker-sandbox/v2",
        "review_acceptance": "required",
    }


def admit_measurement(root: Path, payload: bytes, expected_manifest_digest: str) -> None:
    """Check measurement integrity; this does not execute or authenticate a review."""
    expected = selected_bundle(root, expected_manifest_digest)
    if payload != encoded(measurement_record(root, expected)):
        raise EvidenceIntegrityError("invalid reproduction measurement")


def admit_retained_measurement(root: Path, payload: bytes, expected_manifest_digest: str) -> None:
    """Check pinned archival integrity without claiming current-source replay."""
    pin = decoded(read_bytes(root, OUTPUT_ROOT + "/pin.json"))
    capture_digest = pin.get("manifest_digest")
    if (
        set(pin) != {"schema", "manifest_digest"}
        or pin["schema"] != "participant-crossing-reproduction-pin/v1"
        or not isinstance(capture_digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", capture_digest) is None
    ):
        raise EvidenceIntegrityError("invalid retained reproduction pin")
    capture = read_bytes(
        root,
        OUTPUT_ROOT + "/capture-" + capture_digest.split(":", 1)[1] + "/manifest.json",
    )
    if digest(capture) != capture_digest:
        raise EvidenceIntegrityError("retained reproduction capture drift")
    manifest = decoded(capture)
    if (
        set(manifest) != {"schema", "target_manifest_digest", "artifact_digests", "authenticity"}
        or manifest["schema"] != "participant-crossing-reproduction-capture/v1"
        or manifest["target_manifest_digest"] != expected_manifest_digest
        or not isinstance(manifest["artifact_digests"], dict)
        or manifest["artifact_digests"].get("measurement.json") != digest(payload)
    ):
        raise EvidenceIntegrityError("retained reproduction measurement drift")
    record = decoded(payload)
    retained_sources = record.get("reproducer_sources")
    if (
        not isinstance(retained_sources, dict)
        or not 1 <= len(retained_sources) <= 10000
        or not set(SOURCE_PATHS).issubset(retained_sources)
        or any(
            not isinstance(name, str)
            or not isinstance(value, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
            for name, value in retained_sources.items()
        )
    ):
        raise EvidenceIntegrityError("invalid retained reproducer source pins")
    subject, subject_pin = machine.load_retained(root)
    if subject_pin != expected_manifest_digest:
        raise EvidenceIntegrityError("retained reproduction subject mismatch")
    machine.admit_retained_bundle(subject, expected_manifest_digest)
    expected = _measurement_record(subject, retained_sources)
    if payload != encoded(expected):
        raise EvidenceIntegrityError("invalid retained reproduction measurement")


def measure(root: Path, expected_manifest_digest: str) -> bytes:
    expected = selected_bundle(root, expected_manifest_digest)
    sources = source_pins(root)
    actual = sandbox.replay(root)
    machine.validate_inventory(actual)
    if actual != expected:
        raise EvidenceIntegrityError("reproduction differs from selected subject")
    machine.check_sources(root)
    if source_pins(root) != sources:
        raise EvidenceIntegrityError("reproducer source drift")
    payload = encoded(measurement_record(root, actual))
    admit_measurement(root, payload, expected_manifest_digest)
    return payload


def publish_qualified(root: Path, expected_manifest_digest: str) -> str:
    payload = measure(root, expected_manifest_digest)
    execution = {
        "schema": "participant-crossing-reproduction-execution/v1",
        "measurement_digest": digest(payload),
        "execution": publication.execution_record(root, expected_manifest_digest),
        "review_acceptance": "required",
    }
    path = ".cache/raes-sdl/crossing-reproduction-publication"
    publish_bundle(root, {"measurement.json": payload, "execution.json": encoded(execution)}, path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-manifest", required=True)
    parser.add_argument("--qualified", action="store_true")
    args = parser.parse_args()
    try:
        if args.qualified:
            path = publish_qualified(ROOT, args.expected_manifest)
        else:
            payload = measure(ROOT, args.expected_manifest)
            path = OUTPUT_ROOT + "/capture-" + digest(payload).split(":", 1)[1]
            publish_bundle(ROOT, {"measurement.json": payload}, path)
    except OSError, RaesError:
        print("crossing reproduction: measurement refused")
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
