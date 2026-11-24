#!/usr/bin/env python3
"""Re-record the trial-compiler references against the reference compiler.

Each reference keeps its authored request inputs. The recorder refreshes the
digests that the request derives from those inputs, compiles the request with
the reference compiler, and records the plan, its first-entry instantiation,
and, where the reference has one, the entry realization.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from raes import admit_scenario_family, parse_sdl  # noqa: E402
from raes.canonical import canonical_instantiated_sdl_digest, canonical_sdl_digest  # noqa: E402
from raes_contracts.canonical import canonical_json_digest  # noqa: E402
from raes_contracts.contracts import (  # noqa: E402
    AdmittedApparatusBindingModel,
    AdmittedTrialPlanInputRefsModel,
    AdmittedTrialPlanModel,
    ExperimentCaptureSpecModel,
    ExperimentSpecModel,
    ExperimentTaskModel,
)
from raes_contracts.contracts.manifests import ProcessorManifestV2Model  # noqa: E402
from raes_contracts.contracts.participant_manifests import (  # noqa: E402
    BackendManifestV2Model,
    ParticipantImplementationManifestModel,
)
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel  # noqa: E402
from raes_processor.trial_compiler import TrialCompilationRequest, compile_admitted_trial_plan  # noqa: E402
from raes_processor.trial_compiler.models import TrialExecutionAuthorityModel  # noqa: E402
from raes_processor.trial_realization import (  # noqa: E402
    TrialRealizationInputs,
    instantiate_admitted_trial_entry,
    realize_admitted_trial_entry,
)

TESTDATA = ROOT / "implementations/go/processor/trial/testdata"


def _digest(model: Any) -> str:
    return canonical_json_digest(model.model_dump(mode="json"))


def _manifest(key: list[str], payload: dict[str, Any]) -> BackendManifestV2Model | ProcessorManifestV2Model:
    model = ProcessorManifestV2Model if key[0] == "processor" else BackendManifestV2Model
    return model.model_validate(payload)


def build_request(payload: dict[str, Any]) -> tuple[TrialCompilationRequest, dict[str, Any]]:
    """Return the reference request and the request inputs with refreshed derived digests."""
    stored = copy.deepcopy(payload)
    family = admit_scenario_family(parse_sdl(json.dumps(stored["family"])))
    experiment = ExperimentSpecModel.model_validate(stored["experiment"])
    task = ExperimentTaskModel.model_validate(stored["task"])
    capture_specs = {
        key: ExperimentCaptureSpecModel.model_validate(value) for key, value in stored.get("capture_specs", {}).items()
    }
    manifests = {
        tuple(item["key"]): _manifest(item["key"], item["manifest"]) for item in stored.get("apparatus_manifests", [])
    }
    participants = {
        tuple(item["key"]): ParticipantImplementationManifestModel.model_validate(item["manifest"])
        for item in stored.get("participant_manifests", [])
    }
    refs = stored["input_refs"]
    refs["authoring_input_ref"]["ref_digest"] = _digest(experiment)
    refs["task_digest"] = _digest(task)
    refs["scenario_family_ref"]["ref_digest"] = canonical_sdl_digest(family).value
    for ref in refs.get("capture_spec_refs", []):
        if ref["ref_id"] in capture_specs:
            ref["ref_digest"] = _digest(capture_specs[ref["ref_id"]])
    for ref in stored["apparatus"].get("manifest_refs", []):
        for key, manifest in manifests.items():
            if key[1] == ref["ref_id"] and key[3] == ref["ref_version"]:
                ref["ref_digest"] = _digest(manifest)
    request = TrialCompilationRequest(
        family=family,
        experiment=experiment,
        task=task,
        input_refs=AdmittedTrialPlanInputRefsModel.model_validate(refs),
        apparatus=AdmittedApparatusBindingModel.model_validate(stored["apparatus"]),
        realization_envelope=BackendRealizationEnvelopeModel.model_validate(stored["realization_envelope"]),
        execution_authority=TrialExecutionAuthorityModel.model_validate(stored["execution_authority"]),
        apparatus_manifests=manifests,
        capture_specs=capture_specs,
        participant_manifests=participants,
    )
    return request, stored


def _instantiation(plan: AdmittedTrialPlanModel, entry_id: str, request: TrialCompilationRequest) -> dict[str, Any]:
    instance = instantiate_admitted_trial_entry(plan=plan, plan_entry_id=entry_id, family=request.family)
    provenance = instance.instantiation_provenance.trial
    return {
        "entry_id": entry_id,
        "snapshot_digest": canonical_instantiated_sdl_digest(instance).value,
        "provenance": provenance.model_dump(mode="json"),
    }


def _realization(plan: AdmittedTrialPlanModel, entry_id: str, request: TrialCompilationRequest) -> dict[str, Any]:
    backend = next(key for key in request.apparatus_manifests if key[0] == "backend")
    realized = realize_admitted_trial_entry(
        inputs=TrialRealizationInputs(
            plan=plan,
            family=request.family,
            experiment=request.experiment,
            task=request.task,
            capture_specs=request.capture_specs,
            apparatus_manifests=request.apparatus_manifests,
            realization_envelope=request.realization_envelope,
            backend_key=backend,
            participant_manifests=request.participant_manifests,
        ),
        plan_entry_id=entry_id,
    )
    return {
        "snapshot_digest": realized.snapshot_digest,
        "provisioning": realized.provisioning_plan.model_dump(mode="json"),
        "orchestration": realized.orchestration_plan.model_dump(mode="json"),
        "evaluation": realized.evaluation_plan.model_dump(mode="json"),
        "processor_plan_refs": [ref.model_dump(mode="json") for ref in realized.processor_plan_refs],
    }


def _entry_at(plan: AdmittedTrialPlanModel, coordinate: dict[str, Any]) -> str:
    """Return the entry at the retained instantiation coordinate; identities follow the refreshed inputs."""
    matches = [key for key, entry in plan.entries.items() if entry.coordinate.model_dump(mode="json") == coordinate]
    if len(matches) != 1:
        raise ValueError("the retained instantiation coordinate does not name one compiled entry")
    return matches[0]


def compilation_case(case: dict[str, Any]) -> dict[str, Any]:
    request, stored = build_request(case["request"])
    result = compile_admitted_trial_plan(request)
    if result.plan is None:
        raise ValueError(f"{case['name']} no longer compiles: {[item.code for item in result.diagnostics]}")
    plan = result.plan
    entry_id = _entry_at(plan, case["instantiation"]["provenance"]["coordinate"])
    recorded = {**case, "request": stored, "plan": plan.model_dump(mode="json"), "diagnostics": []}
    recorded["instantiation"] = _instantiation(plan, entry_id, request)
    if "realization" in case:
        recorded["realization"] = _realization(plan, entry_id, request)
    return recorded


def compiler_reference(reference: dict[str, Any]) -> dict[str, Any]:
    return {**reference, "cases": [compilation_case(case) for case in reference["cases"]]}


RECORDS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "compiler-reference.json.gz": compiler_reference,
}


def _load(path: Path) -> Any:
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def _store(path: Path, value: Any) -> None:
    text = json.dumps(value, indent=2) + "\n"
    if path.suffix == ".gz":
        path.write_bytes(gzip.compress(text.encode(), compresslevel=9, mtime=0))
    else:
        path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    failed = False
    for name, record in RECORDS.items():
        path = TESTDATA / name
        before = _load(path)
        after = record(copy.deepcopy(before))
        if args.check:
            if after != before:
                print(f"{name} differs from the reference compiler", file=sys.stderr)
                failed = True
        elif after != before:
            _store(path, after)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
