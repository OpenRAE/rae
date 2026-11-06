"""Complete finite DPBB decision, built from the current sources and admitted on each run."""

import argparse
import signal
from contextlib import contextmanager
from pathlib import Path

from raes_contracts.errors import EvidenceIntegrityError, OperationalError, RaesError
from raes_contracts.operational_logging import run_application

from tools.mcrl2_tool import compare

from . import counterexample_corpus as corpus
from . import machine_check_evidence as evidence
from .counterexample_witnesses import check_formula
from .export import digest

ROOT = Path(__file__).resolve().parents[3]
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
        # Re-run the fixed reviewed mutation/calibration inventory, never candidate case lists.
        model, replayed = evidence.inputs(root)
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
                "corpus-manifest.json": replayed["manifest.json"],
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
        bundle["manifest.json"] = corpus.encoded(evidence.manifest(root, bundle, model, replayed))
        admit_bundle(root, bundle, model, replayed)
        return bundle


def admit_bundle(
    root: Path,
    bundle: dict[str, bytes],
    model: dict[str, bytes],
    replayed: dict[str, bytes],
    *,
    require_authenticity=False,
) -> None:
    """Admit a machine-check bundle against the model and corpus built from the current sources."""
    validate_inventory(bundle)
    if require_authenticity:
        raise EvidenceIntegrityError("unsigned result cannot satisfy authenticity policy")
    check_sources(root)
    expected_inputs = {name: model[name] for name in ("abstract.aut", "concrete.aut", "abstract.json", "concrete.json")}
    expected_inputs.update(
        {
            "model-manifest.json": model["manifest.json"],
            "corpus-manifest.json": replayed["manifest.json"],
            "mutation-results.json": replayed["results.json"],
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
    if bundle["manifest.json"] != corpus.encoded(evidence.manifest(root, bundle, model, replayed)):
        raise EvidenceIntegrityError("invalid machine-check metadata")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check",))
    parser.parse_args()
    try:
        # Build the model, the corpus and the decision from the current sources, then admit them.
        build_bundle(ROOT)
    except OSError, RaesError:
        print("crossing machine check: evidence admission failed")
        return 1
    print("crossing machine check: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
