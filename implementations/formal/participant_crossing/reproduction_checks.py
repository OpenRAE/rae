"""Fixed independent comparisons inside the complete offline worker boundary."""

import os
import re
import shutil
import tempfile
from pathlib import Path

from raes_contracts.errors import EvidenceIntegrityError, OperationalError

from tools.bounded_tool_process import run_bounded
from tools.mcrl2_tool import (
    FORMULA_MODES,
    MODES,
    Comparison,
    parse_decision,
    require_mcrl2,
)

from . import counterexample_corpus as corpus
from . import export
from . import machine_check as machine
from . import machine_check_evidence as evidence
from .aut import parse_aut, render_aut
from .counterexample_mutations import build_mutations
from .counterexample_witnesses import check_divergence, check_formula
from .ingress import read_bytes

VERIFICATION = {
    "native_argv_template": [
        "/opt/mcrl2/usr/bin/ltscompare",
        "--equivalence=<relation-mode>",
        "--tau=internal",
        "--in1=aut",
        "--in2=aut",
        "/checks/<comparison>/left.aut",
        "/checks/<comparison>/right.aut",
    ],
    "hiding": ["internal"],
    "boundary": "single-rootless-worker-with-read-only-source-tool-and-inputs",
    "max_comparisons": 47,
}


def input_pairs(root: Path) -> dict[str, tuple[bytes, bytes]]:
    model = export.build_bundle(root)
    abstract, concrete = model["abstract.aut"], model["concrete.aut"]
    pairs = {"baseline": (abstract, concrete), "unchanged": (concrete, concrete)}
    for mutation in build_mutations():
        payload = render_aut(mutation.graph)
        pairs[mutation.case_id] = (abstract, payload)
        pairs[mutation.case_id + "-concrete"] = (concrete, payload)
    for calibration in corpus.calibrations():
        pairs[calibration["id"]] = (calibration["left"], calibration["right"])
    return pairs


def prepare_inputs(root: Path, destination: Path) -> None:
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name, (left, right) in input_pairs(root).items():
        directory = destination / name
        directory.mkdir(mode=0o700)
        for filename, payload in (("left.aut", left), ("right.aut", right)):
            (directory / filename).write_bytes(payload)


def compare(
    root: Path, name: str, left: bytes, right: bytes, mode: str, *, formula=False
) -> Comparison:
    """Run the admitted checker; the enclosing worker supplies namespace isolation."""
    if root != Path("/reproduction") or not os.statvfs(root).f_flag & os.ST_RDONLY:
        raise OperationalError("reproduction worker boundary is required")
    if (
        mode not in MODES
        or formula
        and mode not in FORMULA_MODES
        or re.fullmatch(r"[a-z0-9-]{1,64}", name) is None
    ):
        raise ValueError("invalid reproduction comparison")
    for filename, payload in (("left.aut", left), ("right.aut", right)):
        parse_aut(payload, max_states=512, max_bytes=65536)
        if (
            read_bytes(Path("/checks"), name + "/" + filename, max_bytes=65536)
            != payload
        ):
            raise EvidenceIntegrityError("prepared reproduction input drift")
    if not require_mcrl2(root).samefile(Path("/opt/mcrl2")):
        raise EvidenceIntegrityError("reproduction native tool mount mismatch")
    output = Path("/output") / (name + "-" + mode + ("-formula" if formula else ""))
    output.mkdir(mode=0o700)
    try:
        argv = [
            "/opt/mcrl2/usr/bin/ltscompare",
            f"--equivalence={mode}",
            "--tau=internal",
            "--in1=aut",
            "--in2=aut",
        ]
        if formula:
            argv.extend(
                (
                    "--counter-example",
                    "--counter-example-file=" + str(output / "witness.mcf"),
                )
            )
        argv.extend((f"/checks/{name}/left.aut", f"/checks/{name}/right.aut"))
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            run_bounded(argv, stdout=stdout, stderr=stderr)
            stdout.seek(0)
            decision = parse_decision(stdout.read(65537))
        expected = {"witness.mcf"} if formula and not decision else set()
        if {path.name for path in output.iterdir()} != expected:
            raise EvidenceIntegrityError("unexpected reproduction native output")
        witness = (
            read_bytes(output, "witness.mcf", max_bytes=65536) if expected else None
        )
        return Comparison(decision, witness)
    finally:
        shutil.rmtree(output)


def observed(comparison, root, name, left, right, expected) -> dict[str, bool]:
    values = [comparison(root, name, left, right, mode).equivalent for mode in MODES]
    if any(type(value) is not bool for value in values) or values != expected:
        raise EvidenceIntegrityError("unexpected reproduction decisions")
    return dict(zip(MODES, values, strict=True))


def replay_corpus(root, model, retained, comparison) -> bytes:
    abstract, concrete = model["abstract.aut"], model["concrete.aut"]
    control = observed(comparison, root, "unchanged", concrete, concrete, [True] * 4)
    cases, calibrations = {}, {}
    for mutation in build_mutations():
        name, payload = mutation.case_id, render_aut(mutation.graph)
        expected = (
            [False, True, True, False] if name == "hidden-divergence" else [False] * 4
        )
        measured = observed(comparison, root, name, abstract, payload, expected)
        isolated = comparison(
            root, name + "-concrete", concrete, payload, "dpbranching-bisim"
        ).equivalent
        if isolated is not False:
            raise EvidenceIntegrityError("reproduction mutation preserves the relation")
        if name == "hidden-divergence":
            witness = corpus.divergence_witness(payload)
            check_divergence(abstract, payload, witness)
            if corpus.encoded(witness) != retained[name + ".witness.json"]:
                raise EvidenceIntegrityError("reproduction divergence witness drift")
            kind = "independently-checked-reachable-divergence"
        else:
            diagnostic = comparison(
                root, name, abstract, payload, "branching-bisim", formula=True
            )
            if diagnostic.equivalent is not False or diagnostic.formula is None:
                raise EvidenceIntegrityError("missing reproduction diagnostic")
            if (
                check_formula(abstract, payload, diagnostic.formula)
                != retained[name + ".mcf"]
            ):
                raise EvidenceIntegrityError("reproduction formula drift")
            kind = "checked-auxiliary-branching-bisim-formula"
        cases[name] = {
            "status": "decision",
            "ordered_inputs": ["abstract.aut", name + ".aut"],
            "observed": measured,
            "isolated_concrete_dpbranching_bisim": isolated,
            "witness_kind": kind,
        }
    for calibration in corpus.calibrations():
        name = calibration["id"]
        calibrations[name] = {
            "scope": "relation-calibration-only",
            "expected": dict(zip(MODES, calibration["expected"], strict=True)),
            "observed": observed(
                comparison,
                root,
                name,
                calibration["left"],
                calibration["right"],
                calibration["expected"],
            ),
        }
    return corpus.encoded(
        {
            "cases": cases,
            "unchanged_concrete_control": control,
            "calibrations": calibrations,
        }
    )


def rebuild_bundle(root: Path, *, comparison=None) -> dict[str, bytes]:
    comparison = comparison or compare
    with machine.producer_budget():
        machine.check_sources(root)
        model, retained, pin = evidence.inputs(root)
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
                "mutation-results.json": replay_corpus(
                    root, model, retained, comparison
                ),
            }
        )
        decision = comparison(
            root,
            "baseline",
            model["abstract.aut"],
            model["concrete.aut"],
            "dpbranching-bisim",
        )
        if type(decision.equivalent) is not bool or decision.formula is not None:
            raise EvidenceIntegrityError("invalid reproduction baseline decision")
        witness_digest = None
        if not decision.equivalent:
            auxiliary = comparison(
                root,
                "baseline",
                model["abstract.aut"],
                model["concrete.aut"],
                "branching-bisim",
                formula=True,
            )
            if auxiliary.equivalent is not False or auxiliary.formula is None:
                raise EvidenceIntegrityError(
                    "unsupported reproduction baseline counterexample"
                )
            bundle["baseline.mcf"] = check_formula(
                model["abstract.aut"], model["concrete.aut"], auxiliary.formula
            )
            witness_digest = export.digest(bundle["baseline.mcf"])
        bundle["result.json"] = corpus.encoded(
            evidence.result(root, decision.equivalent, model, witness_digest)
        )
        machine.check_sources(root)
        bundle["manifest.json"] = corpus.encoded(
            evidence.manifest(root, bundle, model, retained, pin)
        )
        machine.admit_bundle(root, bundle, export.digest(bundle["manifest.json"]))
        return bundle
