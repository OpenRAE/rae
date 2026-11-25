"""Record analysis fixtures from six targeted incumbent Python test modules.

Run from the repository root with implementations/python/.venv/bin/python.
No existing expected document is read to construct new expected output.
"""

import base64
import copy
import functools
import gzip
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "implementations/python/tests"))
RECORDS = []
TARGETS = {
    "analyze_participant_opacity_input": ("participant-opacity", "document"),
    "model_check_participant_opacity_input": (
        "participant-opacity-model-check",
        "document",
    ),
    "synthesize_sdl_candidate": ("candidate-synthesis", "document"),
    "compare_authoring_paths": ("authoring-adapter-comparison", "authoring"),
    "analyze_scenario_file": ("satisfiability", "source"),
    "analyze_exploit_path_file": ("exploit-path", "file"),
}


def portable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def capture(function, label):
    kind, shape = TARGETS[function.__name__]

    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        row = {"source_test": label, "kind": kind}
        try:
            if shape == "source":
                row["source_text"] = args[0].read_bytes().decode("utf-8")
                row["source_id"] = args[0].name
            elif shape == "file":
                row["input_bytes"] = base64.b64encode(args[0].read_bytes()).decode("ascii")
                row["source_id"] = args[0].name
            else:
                row["input"] = portable(args[0])
            if shape == "authoring":

                def output(value):
                    ds = []
                    for d in value.diagnostics:
                        if hasattr(d, "model_dump"):
                            ds.append({"carrier": "contract", "value": portable(d)})
                        elif hasattr(d, "stage"):
                            ds.append(
                                {
                                    "carrier": "source",
                                    "value": {
                                        "code": d.code,
                                        "severity": d.severity,
                                        "stage": d.stage,
                                        "pointer": d.pointer,
                                        "message": d.message,
                                    },
                                }
                            )
                        else:
                            raise TypeError("untyped diagnostic fixture")
                    report = portable(value.transformation_report)
                    return {
                        "input_source": value.input_source,
                        "output_source": value.output_source,
                        "diagnostics": ds,
                        "transformation_report": report,
                    }

                row["left"] = output(args[1])
                row["right"] = output(args[2])
                row["left_path"] = kwargs.get("left_path", "left")
                row["right_path"] = kwargs.get("right_path", "right")
            else:
                if "profile" in kwargs:
                    row["profile"] = portable(kwargs["profile"])
                if "catalog" in kwargs:
                    row["catalog"] = portable(kwargs["catalog"])
            json.dumps(row)
        except TypeError, ValueError:
            return function(*args, **kwargs)
        try:
            result = function(*args, **kwargs)
        except Exception as error:  # noqa: BLE001 - Record the incumbent refusal class as fixture evidence.
            row["error_type"] = type(error).__name__
            RECORDS.append(row)
            raise
        if kind == "candidate-synthesis":
            row["expected"] = portable(result.record)
            row["candidate_source"] = result.candidate_content
        elif shape == "authoring":
            row["expected"] = portable(result.report)
            row["semantic_result"] = portable(result.semantic_result)
        else:
            row["expected"] = portable(result)
        RECORDS.append(row)
        return result

    return wrapped


class Recorder:
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self, item):
        changed = {}
        for name, function in list(vars(item.module).items()):
            if callable(function) and getattr(function, "__name__", "") in TARGETS:
                changed[name] = function
                setattr(item.module, name, capture(function, item.nodeid))
        yield
        for name, function in changed.items():
            setattr(item.module, name, function)


def legacy_cases(directory):
    from raes_contracts.canonical import canonical_json_digest
    from raes_processor.exploit_path import analyze_exploit_path_file
    from test_exploit_path_analysis import _analysis_input

    root = Path(directory)
    rows = []
    for name in [
        "legacy-vm-raw",
        "legacy-vm-historical",
        "empty-classifications",
        "forged-original",
        "forged-graph",
        "constraint-collision",
        "nonempty-classifications",
    ]:
        value = _analysis_input().model_dump(mode="json")
        snapshot = value["snapshot"]
        scenario = snapshot["scenario"]
        node = scenario["nodes"]["target"]
        if name != "empty-classifications":
            node["type"] = "vm"
        node.pop("architecture", None)
        scenario["vulnerabilities"] = {}
        if name == "nonempty-classifications":
            scenario["vulnerabilities"] = {"retired": "assertion"}
        if name == "constraint-collision":
            scenario["instantiation_provenance"]["realization_constraints"] = [
                {
                    "namespace": [],
                    "field_pointer": "/nodes/target",
                    "concern": "compute-substrate",
                    "posture": "exact",
                    "domain": {"kind": "exact", "value": "virtual-machine"},
                    "provenance": "legacy-node-type-vm",
                }
            ]
        projected = copy.deepcopy(snapshot)
        if name == "legacy-vm-historical":
            for n in projected["scenario"]["nodes"].values():
                n.setdefault("architecture", None)
        identity = canonical_json_digest(projected)
        if name == "forged-original":
            identity = "sha256:" + "a" * 64
        value["snapshot_digest"] = identity
        value["normalized_graph"]["snapshot_digest"] = identity
        if name == "forged-graph":
            value["normalized_graph"]["snapshot_digest"] = "sha256:" + "b" * 64
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        file = root / "input.json"
        file.write_bytes(raw)
        row = {
            "kind": "exploit-path",
            "source_test": "test_issue_1076_compute_realization/" + name,
            "source_id": "input.json",
            "input": value,
        }
        try:
            row["expected"] = analyze_exploit_path_file(file).model_dump(mode="json")
        except Exception as error:  # noqa: BLE001 - Record the incumbent refusal class as fixture evidence.
            row["error_type"] = type(error).__name__
        rows.append(row)
    return rows


FILES = [
    "test_issue_961_participant_opacity.py",
    "test_issue_962_participant_opacity_model_check.py",
    "test_candidate_synthesis.py",
    "test_authoring_adapters.py",
    "test_scenario_satisfiability.py",
    "test_exploit_path_analysis.py",
]
EXCLUDED = (
    "test_semantic_uncertainty_remains_incomparable",
    "test_observation_defect_is_not_reported_as_invalid_output",
    "test_unknown_during_initial_decision_fails_without_evidence",
    "test_unknown_during_core_reduction_fails_loudly_with_budget_context",
    "test_unknown_during_witness_selection_fails_loudly_with_budget_context",
)


def main():
    result = pytest.main(
        [
            "-q",
            "--override-ini=addopts=",
            "--confcutdir=implementations/python/tests",
            *[str(ROOT / "implementations/python/tests" / name) for name in FILES],
        ],
        plugins=[Recorder()],
    )
    if result:
        return result
    rows = [row for row in RECORDS if not any(name in row["source_test"] for name in EXCLUDED)]
    with tempfile.TemporaryDirectory() as directory:
        rows.extend(legacy_cases(directory))
    output = ROOT / "implementations/go/processor/analysis/testdata"
    parts = []
    for kind in sorted({row["kind"] for row in rows}):
        cases = [row for row in rows if row["kind"] == kind]
        data = gzip.compress(
            json.dumps({"cases": cases}, sort_keys=True, separators=(",", ":")).encode() + b"\n",
            mtime=0,
        )
        path = output / (kind + ".json.gz")
        path.write_bytes(data)
        parts.append(
            {
                "path": path.name,
                "sha256": hashlib.sha256(data).hexdigest(),
                "cases": len(cases),
            }
        )
    uncertainty = [
        {
            "source_test": row["source_test"],
            "semantic_result": row["semantic_result"],
            "expected_relation": row["expected"]["semantic_relation"],
        }
        for row in RECORDS
        if "test_semantic_uncertainty_remains_incomparable" in row["source_test"]
    ]
    uncertainty_data = (json.dumps({"cases": uncertainty}, indent=2) + "\n").encode()
    (output / "semantic-uncertainty.json").write_bytes(uncertainty_data)
    parts.append(
        {
            "path": "semantic-uncertainty.json",
            "sha256": hashlib.sha256(uncertainty_data).hexdigest(),
            "cases": len(uncertainty),
        }
    )
    sources = [ROOT / "implementations/python/tests" / name for name in FILES]
    trees = {}
    for package in ["raes_processor", "raes_contracts", "raes_conformance", "raes"]:
        base = ROOT / "implementations/python/packages" / package
        entries = {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(base.rglob("*.py"))
        }
        encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
        trees[str(base.relative_to(ROOT))] = {
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "files": len(entries),
        }
    manifest = {
        "format_version": 1,
        "command": "implementations/python/.venv/bin/python implementations/go/processor/analysis/testdata/reference_driver.py",
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources
        },
        "parts": parts,
        "source_trees": trees,
        "tree_hash_format": "SHA-256 of UTF-8 compact sorted JSON mapping repository-relative .py paths to SHA-256 file hex digests.",
        "excluded_injected_cases": list(EXCLUDED),
        "exclusion_reason": "These cases replace Python internals through monkeypatch. Native owner and solver fault tests cover the fault boundary; ordinary unpatched calls are not an oracle for the injected behavior.",
    }
    (output / "reference-provenance.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
