"""Reproducible negative evidence for the complete rev2 crossing carrier."""

import argparse
import re
from collections import deque
from dataclasses import asdict
from pathlib import Path

from raes_contracts.canonical import canonical_json_bytes, canonical_json_digest
from raes_contracts.json_ingress import parse_bounded_json_object

from tools.mcrl2_tool import MODES, compare, selection

from . import export
from .aut import parse_aut, render_aut
from .counterexample_mutations import CASE_IDS, build_mutations
from .counterexample_witnesses import check_divergence, check_formula
from .export import digest, publish_bundle
from .ingress import read_bytes, safe_path

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = "specs/formal/participant-semantics/counterexamples"
MAPPING_ROOT = "specs/formal/participant-semantics/runtime-mapping/rev1"
CALIBRATION_IDS = ("finite-stutter", "weak-choice", "internal-divergence")
SOURCE_PATHS = (
    *export.SOURCE_PATHS,
    *(
        "implementations/formal/participant_crossing/" + name
        for name in (
            "counterexample_mutations.py",
            "counterexample_witnesses.py",
            "counterexample_corpus.py",
        )
    ),
    *(
        "tools/" + name
        for name in (
            "mcrl2_tool.py",
            "bounded_tool_process.py",
            "debian_tree_decoder.py",
            "tool_versions.py",
            "tooling_policy_gate.py",
            "tooling_installed_tree.py",
            "verified_tree_archive.py",
            "verified_tree_installation.py",
            "verified_tree_manifest.py",
            "verified_tree_validation.py",
            "verified_tool_installation.py",
            "maintained_client_acquisition.py",
        )
    ),
    "implementations/tooling/artifacts.lock.json",
    "implementations/tooling/profiles/development-profiles.json",
    "implementations/tooling/schemas/artifact-lock.schema.json",
    "implementations/tooling/selector-bindings.json",
    "implementations/tooling/admission-policy.json",
    "implementations/tooling/python/uv.lock",
)


_EXECUTING_PINS = {path: digest(read_bytes(ROOT, path)) for path in SOURCE_PATHS}


def _source_pins(root: Path) -> dict[str, str]:
    pins = {path: digest(read_bytes(root, path)) for path in SOURCE_PATHS}
    if pins != _EXECUTING_PINS:
        raise ValueError("corpus executing source drift")
    return pins


def encoded(document: dict) -> bytes:
    return canonical_json_bytes(document) + b"\n"


def decoded(payload: bytes) -> dict:
    return parse_bounded_json_object(payload, max_bytes=2 * 1024 * 1024, max_depth=32)


def calibrations() -> tuple[dict, ...]:
    def model(initial, count, edges):
        payload = (
            f"des ({initial}, {len(edges)}, {count})\n" + "".join(f'({a},"{b}",{c})\n' for a, b, c in edges)
        ).encode("ascii")
        parse_aut(payload)
        return payload

    a, b = "crossing.request", "crossing.delivery"
    choice = [(0, a, 3), (0, "internal", 1), (1, b, 3), (1, "internal", 2), (2, a, 3)]
    return (
        {
            "id": "finite-stutter",
            "left": model(0, 2, [(0, a, 1)]),
            "right": model(0, 3, [(0, "internal", 1), (1, a, 2)]),
            "expected": [False, True, True, True],
        },
        {
            "id": "weak-choice",
            "left": model(0, 4, choice),
            "right": model(1, 4, choice),
            "expected": [False, True, False, False],
        },
        {
            "id": "internal-divergence",
            "left": model(0, 1, []),
            "right": model(0, 1, [(0, "internal", 0)]),
            "expected": [False, True, True, False],
        },
    )


def inventory() -> set[str]:
    return (
        {
            "manifest.json",
            "cases.json",
            "results.json",
            "abstract.aut",
            "concrete.aut",
            "abstract.json",
            "concrete.json",
            "hidden-divergence.witness.json",
        }
        | {f"{case}.{extension}" for case in CASE_IDS for extension in ("aut", "json")}
        | {f"{case}.mcf" for case in CASE_IDS if case != "hidden-divergence"}
        | {f"{case}.{side}.aut" for case in CALIBRATION_IDS for side in ("left", "right")}
    )


def validate_inventory(bundle: dict[str, bytes]) -> None:
    if (
        set(bundle) != inventory()
        or any(not isinstance(value, bytes) or len(value) > 2 * 1024 * 1024 for value in bundle.values())
        or sum(map(len, bundle.values())) > 8 * 1024 * 1024
    ):
        raise ValueError("invalid corpus inventory")


def _baseline(root: Path):
    current = export.build_bundle(root)
    retained = decoded(read_bytes(root, export.OUTPUT_PATH + "/manifest.json"))
    result = {}
    for name in ("abstract.aut", "concrete.aut", "abstract.json", "concrete.json"):
        payload = read_bytes(root, export.OUTPUT_PATH + "/" + name)
        if digest(payload) != retained["artifact_digests"][name] or payload != current[name]:
            raise ValueError("retained baseline drift")
        result[name] = payload
    return result, decoded(current["manifest.json"]), retained


def divergence_witness(payload: bytes) -> dict:
    initial, _, edges = parse_aut(payload)
    targets = {source for source, label, target in edges if label == "internal" and source == target}
    queue = deque([(initial, [])])
    seen = {initial}
    while queue:
        state, prefix = queue.popleft()
        if state in targets:
            return {"prefix": prefix, "cycle": [[state, "internal", state]]}
        for edge in edges:
            if edge[0] == state and edge[2] not in seen:
                seen.add(edge[2])
                queue.append((edge[2], [*prefix, list(edge)]))
    raise ValueError("no reachable internal self-cycle")


def _measure(root, left, right, expected):
    observed = [compare(root, left, right, mode).equivalent for mode in MODES]
    if observed != expected:
        raise ValueError("unexpected comparison decisions")
    return dict(zip(MODES, observed, strict=True))


def build_bundle(root: Path) -> dict[str, bytes]:
    _source_pins(root)
    bundle, current, retained = _baseline(root)
    controls = _measure(root, bundle["concrete.aut"], bundle["concrete.aut"], [True] * 4)
    cases, results, calibration_records = {}, {}, {}
    for mutation in build_mutations():
        case = mutation.case_id
        payload = render_aut(mutation.graph)
        bundle[case + ".aut"] = payload
        bundle[case + ".json"] = encoded(
            {
                "initial": mutation.graph.initial,
                "states": [asdict(state) for state in mutation.graph.states],
                "semantic_edges": [list(edge) for edge in mutation.graph.edges],
            }
        )
        expected = [False, True, True, False] if case == "hidden-divergence" else [False] * 4
        cases[case] = {
            **mutation.document(),
            "expected": dict(zip(MODES, expected, strict=True)),
            "baseline_digest": digest(bundle["concrete.aut"]),
            "mutant_digest": digest(payload),
        }
        observed = _measure(root, bundle["abstract.aut"], payload, expected)
        isolated = compare(root, bundle["concrete.aut"], payload, "dpbranching-bisim").equivalent
        if isolated:
            raise ValueError("mutation preserves the selected relation")
        if case == "hidden-divergence":
            witness = divergence_witness(payload)
            check_divergence(bundle["abstract.aut"], payload, witness)
            bundle[case + ".witness.json"] = encoded(witness)
            witness_kind = "independently-checked-reachable-divergence"
        else:
            diagnostic = compare(root, bundle["abstract.aut"], payload, "branching-bisim", formula=True)
            if diagnostic.equivalent or diagnostic.formula is None:
                raise ValueError("missing diagnostic formula")
            bundle[case + ".mcf"] = check_formula(bundle["abstract.aut"], payload, diagnostic.formula)
            witness_kind = "checked-auxiliary-branching-bisim-formula"
        results[case] = {
            "status": "decision",
            "ordered_inputs": ["abstract.aut", case + ".aut"],
            "observed": observed,
            "isolated_concrete_dpbranching_bisim": isolated,
            "witness_kind": witness_kind,
        }
    for calibration in calibrations():
        name = calibration["id"]
        for side in ("left", "right"):
            bundle[f"{name}.{side}.aut"] = calibration[side]
        calibration_records[name] = {
            "scope": "relation-calibration-only",
            "expected": dict(zip(MODES, calibration["expected"], strict=True)),
            "observed": _measure(root, calibration["left"], calibration["right"], calibration["expected"]),
        }
    bundle["cases.json"] = encoded(cases)
    bundle["results.json"] = encoded(
        {"cases": results, "unchanged_concrete_control": controls, "calibrations": calibration_records}
    )
    manifest = _manifest(root, bundle, cases, current, retained)
    bundle["manifest.json"] = encoded(manifest)
    validate_inventory(bundle)
    return bundle


def _manifest(root, bundle, cases, current, retained):
    selected = selection()
    sources = _source_pins(root)
    mapping = {name: read_bytes(root, MAPPING_ROOT + "/" + name) for name in ("manifest.json", "cases.json")}
    if decoded(mapping["manifest.json"])["artifact_digests"]["cases.json"] != digest(mapping["cases.json"]):
        raise ValueError("historical mapping drift")
    return {
        "schema": "participant-crossing-counterexamples/v1",
        "profile": "participant-crossing-dpbb-finite-v1@rev2",
        "profile_digest": current["profile_digest"],
        "projection": current["projection"],
        "catalog_revision": current["catalog_revision"],
        "catalog_digest": current["catalog_digest"],
        "baseline_manifest_digest": digest(read_bytes(root, export.OUTPUT_PATH + "/manifest.json")),
        "historical_baseline_source_drift": sorted(
            path for path, pin in retained["source_digests"].items() if digest(read_bytes(root, path)) != pin
        ),
        "mapping": {
            "path": MAPPING_ROOT,
            "scope": "historical-observations",
            "digests": {name: digest(value) for name, value in mapping.items()},
            "case_counts": decoded(mapping["manifest.json"])["case_counts"],
        },
        "source_digests": sources,
        "source_identity": canonical_json_digest(sources),
        "tool": {
            "artifact_id": selected.artifact_id,
            "version": selected.version,
            "raw": asdict(selected.raw_manifest[0]),
            "installed_tree": asdict(selected.installed_tree),
            "executable": asdict(selected.installed_manifest[0]),
            "modes": list(MODES),
            "hiding": ["internal"],
            "cpu_seconds": 30,
            "wall_seconds": 45,
            "address_space_bytes": 2147483648,
            "file_bytes": 1048576,
        },
        "artifact_digests": {name: digest(value) for name, value in bundle.items() if name != "manifest.json"},
        "review_subject_digest": canonical_json_digest(cases),
        "review_authority": "external-review-record-bound-to-subject",
        "authenticity": "unsigned",
        "trust_role": "evidence_artifact",
        "equivalence_result": "not-established",
        "non_claims": [
            "positive-equivalence",
            "mathematical-proof",
            "independent-reproduction",
            "runtime-realization",
            "backend-conformance",
            "noninterference",
            "opacity",
        ],
        "error_behavior": "unsupported-labels-rejected",
        "completion_behavior": "terminal-can-retry-or-advance-cut",
        "deadlock_behavior": "no-outgoing-transition",
    }


def output_path(bundle: dict[str, bytes]) -> str:
    return OUTPUT_ROOT + "/capture-" + digest(bundle["manifest.json"]).split(":", 1)[1]


def _admit_mutations(bundle, baseline):
    cases = {}
    expected_results = {}
    for mutation in build_mutations():
        case = mutation.case_id
        payload = render_aut(mutation.graph)
        if bundle[case + ".aut"] != payload or bundle[case + ".json"] != encoded(
            {
                "initial": mutation.graph.initial,
                "states": [asdict(state) for state in mutation.graph.states],
                "semantic_edges": [list(edge) for edge in mutation.graph.edges],
            }
        ):
            raise ValueError("corpus mutation drift")
        expected = [False, True, True, False] if case == "hidden-divergence" else [False] * 4
        modes = dict(zip(MODES, expected, strict=True))
        cases[case] = {
            **mutation.document(),
            "expected": modes,
            "baseline_digest": digest(baseline["concrete.aut"]),
            "mutant_digest": digest(payload),
        }
        if case == "hidden-divergence":
            check_divergence(baseline["abstract.aut"], payload, decoded(bundle[case + ".witness.json"]))
            kind = "independently-checked-reachable-divergence"
        else:
            witness = bundle[case + ".mcf"]
            if check_formula(baseline["abstract.aut"], payload, witness) != witness:
                raise ValueError("noncanonical formula")
            kind = "checked-auxiliary-branching-bisim-formula"
        expected_results[case] = {
            "status": "decision",
            "ordered_inputs": ["abstract.aut", case + ".aut"],
            "observed": modes,
            "isolated_concrete_dpbranching_bisim": False,
            "witness_kind": kind,
        }
    return cases, expected_results


def _admit_calibrations(bundle):
    expected_calibrations = {}
    for row in calibrations():
        name = row["id"]
        for side in ("left", "right"):
            if bundle[f"{name}.{side}.aut"] != row[side]:
                raise ValueError("calibration drift")
        modes = dict(zip(MODES, row["expected"], strict=True))
        expected_calibrations[name] = {"scope": "relation-calibration-only", "expected": modes, "observed": modes}
    return expected_calibrations


def admit_bundle(
    root: Path, bundle: dict[str, bytes], expected_manifest_digest: str, *, require_authenticity: bool = False
) -> None:
    """Admit against an independently selected pin; never adopt candidate policy."""

    validate_inventory(bundle)
    if digest(bundle["manifest.json"]) != expected_manifest_digest:
        raise ValueError("corpus differs from retained manifest pin")
    if require_authenticity:
        raise ValueError("unsigned corpus cannot satisfy authenticity policy")
    baseline, current, retained = _baseline(root)
    if any(bundle[name] != value for name, value in baseline.items()):
        raise ValueError("corpus baseline drift")
    cases, results = _admit_mutations(bundle, baseline)
    if bundle["cases.json"] != encoded(cases):
        raise ValueError("corpus review subject drift")
    expected = {
        "cases": results,
        "unchanged_concrete_control": dict.fromkeys(MODES, True),
        "calibrations": _admit_calibrations(bundle),
    }
    if bundle["results.json"] != encoded(expected):
        raise ValueError("invalid corpus decisions")
    # Reconstruct all metadata from independently selected authorities. This also
    # closes unknown fields, claim promotion, source/tool drift and digest joins.
    if bundle["manifest.json"] != encoded(_manifest(root, bundle, cases, current, retained)):
        raise ValueError("invalid corpus metadata")


def load_retained(root: Path) -> tuple[dict[str, bytes], str]:
    """Read the repository's reviewed pin separately from the candidate bundle."""

    pin = decoded(read_bytes(root, OUTPUT_ROOT + "/pin.json", max_bytes=4096))
    if (
        set(pin) != {"schema", "capture", "manifest_digest", "review_subject_digest"}
        or pin["schema"] != "participant-crossing-counterexample-pin/v1"
    ):
        raise ValueError("invalid corpus pin")
    expected = pin["manifest_digest"]
    if not isinstance(expected, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", expected) is None:
        raise ValueError("invalid corpus pin")
    path = OUTPUT_ROOT + "/capture-" + expected.split(":", 1)[1]
    if pin["capture"] != path or {item.name for item in safe_path(root, path).iterdir()} != inventory():
        raise ValueError("invalid corpus inventory")
    bundle = {name: read_bytes(root, path + "/" + name) for name in inventory()}
    if decoded(bundle["manifest.json"])["review_subject_digest"] != pin["review_subject_digest"]:
        raise ValueError("corpus review pin drift")
    return bundle, expected


def publish(root: Path) -> str:
    bundle = build_bundle(root)
    admit_bundle(root, bundle, digest(bundle["manifest.json"]))
    path = output_path(bundle)
    publish_bundle(root, bundle, path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("record", "check", "replay"))
    args = parser.parse_args()
    try:
        if args.action == "record":
            path = publish(ROOT)
        else:
            bundle, pin = load_retained(ROOT)
            admit_bundle(ROOT, bundle, pin)
            path = output_path(bundle)
            if args.action == "replay":
                export._check_expected(ROOT, build_bundle(ROOT), path)
    except OSError, ValueError, RuntimeError:
        print("crossing corpus: evidence admission failed")
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
