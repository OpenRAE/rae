"""Pinned complete finite DPBB decision, admission, and immutable publication."""

import argparse
import re
import signal
from contextlib import contextmanager
from pathlib import Path

from raes_contracts.errors import EvidenceIntegrityError, OperationalError, RaesError
from raes_contracts.operational_logging import run_application

from tools.mcrl2_tool import compare

from . import counterexample_corpus as corpus
from . import machine_check_evidence as evidence
from .counterexample_witnesses import check_formula
from .export import digest, publish_bundle
from .ingress import read_bytes, safe_path

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = evidence.OUTPUT_ROOT
EXECUTING_PINS = evidence.source_pins(ROOT)
INVENTORY = frozenset(
    {
        "abstract.aut",
        "concrete.aut",
        "abstract.json",
        "concrete.json",
        "model-manifest.json",
        "corpus-manifest.json",
        "mutation-results.json",
        "result.json",
        "manifest.json",
    }
)


def check_sources(root: Path) -> None:
    if evidence.source_pins(root) != EXECUTING_PINS:
        raise EvidenceIntegrityError("machine-check executing source drift")


def validate_inventory(bundle: dict[str, bytes]) -> None:
    if (
        set(bundle) not in (INVENTORY, INVENTORY | {"baseline.mcf"})
        or any(type(value) is not bytes or len(value) > 2 * 1024 * 1024 for value in bundle.values())
        or sum(map(len, bundle.values())) > 8 * 1024 * 1024
    ):
        raise EvidenceIntegrityError("invalid machine-check inventory")


@contextmanager
def producer_budget():
    """Bound the complete run; child-runner cleanup still reaps native processes."""

    def expired(_number, _frame):
        raise OperationalError("machine-check producer deadline exceeded")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(2160)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def build_bundle(root: Path) -> dict[str, bytes]:
    with producer_budget():
        check_sources(root)
        model, retained, pin = evidence.inputs(root)
        # Re-run the fixed reviewed mutation/calibration inventory, never candidate case lists.
        replayed = corpus.build_bundle(root)
        corpus.admit_bundle(root, replayed, pin)
        decision = compare(root, model["abstract.aut"], model["concrete.aut"], "dpbranching-bisim")
        if type(decision.equivalent) is not bool or decision.formula is not None:
            raise EvidenceIntegrityError("invalid machine-check decision")
        bundle = {
            name: model[name]
            for name in (
                "abstract.aut",
                "concrete.aut",
                "abstract.json",
                "concrete.json",
            )
        }
        bundle.update(
            {
                "model-manifest.json": model["manifest.json"],
                "corpus-manifest.json": retained["manifest.json"],
                "mutation-results.json": replayed["results.json"],
            }
        )
        witness_digest = None
        if not decision.equivalent:
            auxiliary = compare(
                root,
                model["abstract.aut"],
                model["concrete.aut"],
                "branching-bisim",
                formula=True,
            )
            if auxiliary.equivalent is not False or auxiliary.formula is None:
                raise EvidenceIntegrityError("unsupported baseline counterexample")
            bundle["baseline.mcf"] = check_formula(model["abstract.aut"], model["concrete.aut"], auxiliary.formula)
            witness_digest = digest(bundle["baseline.mcf"])
        bundle["result.json"] = corpus.encoded(evidence.result(root, decision.equivalent, model, witness_digest))
        check_sources(root)
        bundle["manifest.json"] = corpus.encoded(evidence.manifest(root, bundle, model, retained, pin))
        admit_bundle(root, bundle, digest(bundle["manifest.json"]))
        return bundle


def admit_bundle(
    root: Path,
    bundle: dict[str, bytes],
    expected_manifest_digest: str,
    *,
    require_authenticity=False,
) -> None:
    validate_inventory(bundle)
    if digest(bundle["manifest.json"]) != expected_manifest_digest:
        raise EvidenceIntegrityError("machine-check differs from independent pin")
    if require_authenticity:
        raise EvidenceIntegrityError("unsigned result cannot satisfy authenticity policy")
    check_sources(root)
    model, retained, pin = evidence.inputs(root)
    expected_inputs = {name: model[name] for name in ("abstract.aut", "concrete.aut", "abstract.json", "concrete.json")}
    expected_inputs.update(
        {
            "model-manifest.json": model["manifest.json"],
            "corpus-manifest.json": retained["manifest.json"],
            "mutation-results.json": retained["results.json"],
        }
    )
    if any(bundle[name] != content for name, content in expected_inputs.items()):
        raise EvidenceIntegrityError("machine-check input or mutation drift")
    decision = corpus.decoded(bundle["result.json"]).get("equivalent")
    witness = bundle.get("baseline.mcf")
    if witness is not None:
        if decision is not False or check_formula(model["abstract.aut"], model["concrete.aut"], witness) != witness:
            raise EvidenceIntegrityError("invalid baseline counterexample")
    expected_result = evidence.result(root, decision, model, digest(witness) if witness is not None else None)
    if bundle["result.json"] != corpus.encoded(expected_result):
        raise EvidenceIntegrityError("invalid machine-check result or claim")
    if bundle["manifest.json"] != corpus.encoded(evidence.manifest(root, bundle, model, retained, pin)):
        raise EvidenceIntegrityError("invalid machine-check metadata")


def output_path(bundle: dict[str, bytes]) -> str:
    return OUTPUT_ROOT + "/capture-" + digest(bundle["manifest.json"]).split(":", 1)[1]


def load_retained(root: Path) -> tuple[dict[str, bytes], str]:
    pin = corpus.decoded(read_bytes(root, OUTPUT_ROOT + "/pin.json", max_bytes=4096))
    if (
        set(pin) != {"schema", "manifest_digest"}
        or pin["schema"] != "participant-crossing-machine-check-pin/v1"
        or not isinstance(pin["manifest_digest"], str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", pin["manifest_digest"]) is None
    ):
        raise EvidenceIntegrityError("invalid machine-check pin")
    expected = pin["manifest_digest"]
    path = OUTPUT_ROOT + "/capture-" + expected.split(":", 1)[1]
    names = {item.name for item in safe_path(root, path).iterdir()}
    if names not in (INVENTORY, INVENTORY | {"baseline.mcf"}):
        raise EvidenceIntegrityError("invalid machine-check inventory")
    return {name: read_bytes(root, path + "/" + name) for name in names}, expected


def admit_retained_bundle(bundle: dict[str, bytes], expected_manifest_digest: str) -> None:
    """Check a pinned archive without treating its source as current execution."""
    validate_inventory(bundle)
    if digest(bundle["manifest.json"]) != expected_manifest_digest:
        raise EvidenceIntegrityError("retained machine-check manifest drift")
    manifest = corpus.decoded(bundle["manifest.json"])
    artifacts = {name: digest(payload) for name, payload in bundle.items() if name != "manifest.json"}
    if manifest.get("artifact_digests") != artifacts:
        raise EvidenceIntegrityError("retained machine-check artifact drift")


def publish(root: Path) -> str:
    bundle = build_bundle(root)
    path = output_path(bundle)
    publish_bundle(root, bundle, path)
    return path


def verify(root: Path) -> None:
    """Run current finite decisions and negative controls without publishing a capture."""
    bundle = build_bundle(root)
    if corpus.decoded(bundle["result.json"]).get("equivalent") is not True:
        raise EvidenceIntegrityError("current finite model does not satisfy the selected relation")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("record", "check", "replay", "verify"))
    args = parser.parse_args()
    try:
        if args.action == "verify":
            verify(ROOT)
            print("Current finite model and negative controls passed.")
            return 0
        if args.action == "record":
            path = publish(ROOT)
        else:
            bundle, pin = load_retained(ROOT)
            admit_bundle(ROOT, bundle, pin)
            path = output_path(bundle)
            if args.action == "replay" and build_bundle(ROOT) != bundle:
                raise EvidenceIntegrityError("machine-check replay drift")
    except OSError, RaesError:
        print("crossing machine check: evidence admission failed")
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
