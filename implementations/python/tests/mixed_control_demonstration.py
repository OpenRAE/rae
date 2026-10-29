"""Runnable RAE test demonstration; this is not an installed product command."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from mixed_control_demonstration_harness import DemonstrationHarness
from participant_control_v2_fixtures import Resolver
from raes_conformance.conformance import (
    MIXED_BACKEND_CASES,
    backend_conformance_report_payload,
    run_mixed_backend_conformance,
    run_modular_control_conformance,
)
from raes_contracts.canonical import canonical_json_digest
from test_issue_1069_participant_control_effects import _target
from test_issue_1071_effect_conformance import handoff_case
from test_issue_1071_modular_conformance import Harness, case_for

ROOT = Path(__file__).resolve().parents[3]
UNSUPPORTED = frozenset({"combination-reusable-control-with-mixed-runtime", "combination-distributed-portable-mixed"})
NONCLAIMS = (
    "Test harness evidence for RAE only; no downstream backend qualification.",
    "No universal backend equivalence, physical timing or simulation-to-operational transfer.",
    "Separate control and mixed executions do not establish joint configuration support.",
    "A fresh process recollection is not reproduction by an independent organization.",
)


def source_identity():
    """Bind code and portable fixtures, excluding output and private host state."""

    files = {}
    for root in ("implementations/python/packages", "implementations/python/tests", "contracts", "specs"):
        for path in sorted((ROOT / root).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".json", ".yaml", ".yml"}:
                files[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ("implementations/python/pyproject.toml", "implementations/python/uv.lock"):
        files[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    return {"digest": canonical_json_digest(files), "file_count": len(files)}


def collect(directory: Path):
    """Execute the fixed test selection in a new, caller-selected directory."""

    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    source = source_identity()
    environment = {
        "python": platform.python_version(),
        "implementation": sys.implementation.name,
        "raes": version("raes"),
    }
    with TemporaryDirectory(prefix="stores-", dir=directory) as stores:
        harness = DemonstrationHarness(Path(stores), canonical_json_digest(environment))
        mixed = run_mixed_backend_conformance(harness)
        effect = run_modular_control_conformance(
            _target(), harness=Harness(handoff_case()), obligations=(), effect_kinds=("handoff",)
        )
        denial_owner = Resolver()
        denial_owner.decision = "deny"
        denial = run_modular_control_conformance(
            _target(),
            harness=Harness(case_for("strict-denial", owner=denial_owner, disposition="deny", calls=0)),
            obligations=("strict-denial",),
        )
        evidence = {
            "collection_id": uuid4().hex,
            "source": source,
            "environment": environment,
            "reports": {
                name: backend_conformance_report_payload(report)
                for name, report in (("mixed", mixed), ("effect", effect), ("denial", denial))
            },
            "observations": harness.observations(),
            "nonclaims": list(NONCLAIMS),
        }
    if source != source_identity():
        raise ValueError("source changed during collection")
    verify(evidence)
    with (directory / "evidence.json").open("x", encoding="utf-8") as output:
        json.dump(evidence, output, indent=2, sort_keys=True)
        output.write("\n")
    return evidence


def verify(evidence):
    """Apply the demonstration's fixed test expectations to existing reports."""

    reports = evidence["reports"]
    if set(reports) != {"mixed", "effect", "denial"}:
        raise ValueError("incomplete demonstration report set")
    if any(report["native_conformance"] for report in reports.values()):
        raise ValueError("test evidence cannot claim native conformance")
    cases = reports["mixed"]["cases"]
    expected = {case.case_id for case in MIXED_BACKEND_CASES}
    if len(cases) != len(expected) or {case["name"] for case in cases} != expected:
        raise ValueError("incomplete or duplicate capability matrix")
    for case in cases:
        outcome = "unsupported" if case["name"] in UNSUPPORTED else "passed"
        if case["outcome"] != outcome or case["passed"] != (outcome == "passed"):
            raise ValueError("unexpected capability outcome: " + case["name"])
    if reports["mixed"]["passed"] or set(reports["mixed"]["unsupported_capability_gaps"]) != UNSUPPORTED:
        raise ValueError("unsupported combinations must remain visible")
    for name in ("effect", "denial"):
        report = reports[name]
        if (
            len(report["cases"]) != 1
            or not report["passed"]
            or not report["cases"][0]["passed"]
            or report["cases"][0]["outcome"] != "passed"
        ):
            raise ValueError("failed modular case: " + name)
    denial = reports["denial"]["cases"][0]["modular_control"]
    effect = reports["effect"]["cases"][0]["modular_control"]
    if denial["actual_calls"] or effect["owner_outcomes"] != {"effect-1": "applied"}:
        raise ValueError("denial or governed effect disagrees with readback")
    _verify_observations(evidence["observations"])
    _verify_evidence_links(cases, evidence["observations"])


def _verify_observations(observations):
    expected = {case.case_id for case in MIXED_BACKEND_CASES if case.subject.value != "control"}
    if {item["case"] for item in observations["compositions"]} != expected:
        raise ValueError("incomplete composition observations")
    zero_effect = {
        "edge-time-mapped-incomparable",
        "edge-time-segment-incomparable",
        "edge-refused-before-claim",
        "edge-refused-after-time-grant",
    }
    for item in observations["compositions"]:
        readback = item["provider_readback"]
        if item["case"] in zero_effect and (readback["starts"] or any(readback["component_actions"].values())):
            raise ValueError("prohibited effect occurred: " + item["case"])
    executed = [item for item in observations["compositions"] if item["case"] == "edge-executes"]
    if len(executed) != 1 or set(executed[0]["composition_state"]["active_component_ids"]) != {"sim", "emu"}:
        raise ValueError("simultaneous mixed execution was not observed")
    item = executed[0]
    if item["provider_readback"]["translated_actions"] != ["native:contain-host"]:
        raise ValueError("action translation was not executed")
    time = item["binding"]["subject"]["time"]
    mapping = item["time_models"][time["time_model_ref"]]["mappings"][time["mapping_ref"]]
    if mapping["scale"] != {"numerator": 2, "denominator": 1}:
        raise ValueError("non-identity clock mapping was not selected")


def _verify_evidence_links(cases, observations):
    for case in cases:
        binding = case["mixed_binding"]
        if binding is None:
            continue
        retained = set()
        for item in observations["compositions"]:
            if item["case"] == case["name"]:
                retained.update(
                    canonical_json_digest(stage) for operation in item["operations"] for stage in operation["stages"]
                )
        for item in observations["controls"]:
            if item["case"] == case["name"]:
                retained.update(canonical_json_digest(event) for event in item["history"])
        if any(record["digest"] not in retained for record in binding["evidence"]):
            raise ValueError("report evidence is absent from retained facts: " + case["name"])


def _comparison_facts(evidence):
    reports = {}
    for name, report in evidence["reports"].items():
        reports[name] = [
            {
                key: case[key]
                for key in (
                    "name",
                    "outcome",
                    "configuration_digest",
                    "expected_operations",
                    "accounted_operations",
                )
            }
            for case in report["cases"]
        ]
        for signature, case in zip(reports[name], report["cases"], strict=True):
            modular = case["modular_control"]
            if modular is None:
                signature["probe_digest"] = case["probe_digest"]
                signature["binding"] = {
                    key: value for key, value in (case["mixed_binding"] or {}).items() if key != "evidence"
                }
            else:
                # Modular probe digests include the actual execution's cut,
                # ledger and invocation. Keep those in the raw report; compare
                # fixed inputs and measured outcomes across fresh executions.
                signature["modular"] = {
                    key: modular[key]
                    for key in (
                        "obligation",
                        "selected_obligations",
                        "claimed_effect_kinds",
                        "excluded_effect_kinds",
                        "expected_calls",
                        "actual_calls",
                        "owner_outcomes",
                        "refusal_causes",
                        "exact_replays",
                    )
                }
                signature["modular"]["inputs"] = {
                    key: modular["artifact_digests"][key]
                    for key in (
                        "selection",
                        "apparatus",
                        "profiles",
                        "mechanisms",
                        "implementation",
                        "configuration",
                        "authority",
                        "memory",
                    )
                }
    compositions = []
    for item in evidence["observations"]["compositions"]:
        operations = [
            {
                "kind": operation["kind"],
                "state": operation["state"],
                "stages": [
                    {key: stage["stage"].get(key) for key in ("stage", "producer", "status", "comparison")}
                    for stage in operation["stages"]
                ],
            }
            for operation in item["operations"]
        ]
        compositions.append(
            {
                "case": item["case"],
                "provider_readback": item["provider_readback"],
                "operations": sorted(operations, key=canonical_json_digest),
                "phases": [
                    {key: event.get(key) for key in ("event_kind", "disposition", "phase_id", "phase_revision")}
                    for event in item["composition_history"]
                ],
                "time_readback": item["time_readback"],
            }
        )
    controls = [
        {
            "case": item["case"],
            "history": [
                {
                    key: event.get("occurrence", {}).get(key)
                    for key in ("disposition", "resulting_state_revision", "prior_state_ref", "resulting_state_ref")
                }
                for event in item["history"]
            ],
        }
        for item in evidence["observations"]["controls"]
    ]
    return {"reports": reports, "compositions": compositions, "controls": controls}


def compare(first, second):
    """Compare fresh executions without normalizing away observed failures."""

    verify(first)
    verify(second)
    if first["collection_id"] == second["collection_id"]:
        raise ValueError("reproduction reused the first collection")
    if _operation_ids(first) & _operation_ids(second):
        raise ValueError("reproduction reused prior execution records")
    for key in ("source", "environment"):
        if first[key] != second[key]:
            raise ValueError("reproduction drift: " + key)
    if _comparison_facts(first) != _comparison_facts(second):
        raise ValueError("reproduction drift: configuration or observed behavior")
    return {
        "agrees": True,
        "first_collection": first["collection_id"],
        "second_collection": second["collection_id"],
        "first_digest": canonical_json_digest(first),
        "second_digest": canonical_json_digest(second),
        "comparison_digest": canonical_json_digest(_comparison_facts(first)),
        "nonclaims": list(NONCLAIMS),
    }


def _operation_ids(evidence):
    return {
        operation["operation_id"]
        for group in evidence["observations"].values()
        for item in group
        for operation in item["operations"]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collection = commands.add_parser("collect")
    collection.add_argument("directory", type=Path, help="new local collection directory")
    comparison = commands.add_parser("compare")
    comparison.add_argument("first", type=Path)
    comparison.add_argument("second", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "collect":
        evidence = collect(arguments.directory)
        result = {"collection_id": evidence["collection_id"], "evidence_digest": canonical_json_digest(evidence)}
    else:
        result = compare(json.loads(arguments.first.read_text()), json.loads(arguments.second.read_text()))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
