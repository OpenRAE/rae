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
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from pydantic import TypeAdapter  # noqa: E402
from raes import (  # noqa: E402
    admit_scenario_family,
    parse_sdl,
    select_scenario_family,  # noqa: E402
)
from raes._errors import SDLError  # noqa: E402
from raes.canonical import canonical_instantiated_sdl_digest, canonical_sdl_digest  # noqa: E402
from raes.participant_control_context import SDLControlContextConfigurationValidator  # noqa: E402
from raes.selected_scenario import ExpandedScenarioBindingTargetResolver  # noqa: E402
from raes_contracts.canonical import canonical_json_digest  # noqa: E402
from raes_contracts.contracts import (  # noqa: E402
    AdmittedApparatusBindingModel,
    AdmittedMixedCompositionBindingModel,
    AdmittedTrialPlanInputRefsModel,
    AdmittedTrialPlanModel,
    ExperimentCaptureSpecModel,
    ExperimentReferenceModel,
    ExperimentScenarioSelectionDescriptorModel,
    ExperimentSpecModel,
    ExperimentTaskModel,
    MixedParticipantCompositionProfileModel,
    seal_mixed_composition_profile,
)
from raes_contracts.contracts.manifests import ProcessorManifestV2Model  # noqa: E402
from raes_contracts.contracts.mixed_composition_resolution import (  # noqa: E402
    MixedCompositionResolutionContext,
    MixedCompositionTrustedAllocation,
    MixedCompositionTrustedComponent,
    MixedCompositionTrustedEdge,
    MixedCompositionTrustedTransition,
)
from raes_contracts.contracts.participant_manifests import (  # noqa: E402
    BackendManifestV2Model,
    ParticipantImplementationManifestModel,
)
from raes_contracts.contracts.time_model import TimeModelDeclarationModel  # noqa: E402
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel  # noqa: E402
from raes_processor.trial_compiler import TrialCompilationRequest, compile_admitted_trial_plan  # noqa: E402
from raes_processor.trial_compiler.models import (  # noqa: E402
    TrialCompilationLimitsModel,
    TrialExecutionAuthorityModel,
)
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


def build_request(
    payload: dict[str, Any], limits: dict[str, Any] | None = None
) -> tuple[TrialCompilationRequest, dict[str, Any]]:
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
        # Typed participant references configure the reference SDL control-context owner.
        participant_configuration_validators=(
            {("participant-config", "1"): SDLControlContextConfigurationValidator(family)} if participants else {}
        ),
    )
    if limits is not None:
        request = replace(request, limits=TrialCompilationLimitsModel.model_validate(limits))
    return request, stored


def _instantiation(
    plan: AdmittedTrialPlanModel, entry_id: str, request: TrialCompilationRequest, *, provenance: bool
) -> dict[str, Any]:
    instance = instantiate_admitted_trial_entry(plan=plan, plan_entry_id=entry_id, family=request.family)
    result = {"entry_id": entry_id, "snapshot_digest": canonical_instantiated_sdl_digest(instance).value}
    if provenance:
        result["provenance"] = instance.instantiation_provenance.trial.model_dump(mode="json")
    return result


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
    retained = case["instantiation"]
    coordinate = (
        retained["provenance"]["coordinate"]
        if "provenance" in retained
        else case["plan"]["entries"][retained["entry_id"]]["coordinate"]
    )
    entry_id = _entry_at(plan, coordinate)
    recorded = {**case, "request": stored, "plan": plan.model_dump(mode="json")}
    if "diagnostics" in case:
        recorded["diagnostics"] = []
    recorded["instantiation"] = _instantiation(plan, entry_id, request, provenance="provenance" in retained)
    if "realization" in case:
        recorded["realization"] = _realization(plan, entry_id, request)
    return recorded


def compiler_reference(reference: dict[str, Any]) -> dict[str, Any]:
    return {**reference, "cases": [compilation_case(case) for case in reference["cases"]]}


def _diagnostics(case: dict[str, Any]) -> list[dict[str, Any]]:
    request, stored = build_request(case["request"], case.get("limits"))
    case["request"] = stored
    result = compile_admitted_trial_plan(request)
    if result.plan is not None:
        raise ValueError(f"{case['name']} now compiles")
    return [
        {
            "code": item.code,
            "domain": item.domain,
            "address": item.address,
            "message": item.message,
            "severity": str(getattr(item.severity, "value", item.severity)),
        }
        for item in result.diagnostics
    ]


def refusal_reference(reference: dict[str, Any]) -> dict[str, Any]:
    """Re-record refused compilations in the shape each reference keeps."""
    cases = []
    for item in reference["cases"]:
        case = copy.deepcopy(item)
        diagnostics = _diagnostics(case)
        if "code" in case:
            case["code"] = diagnostics[0]["code"]
        if "codes" in case:
            case["codes"] = [diagnostic["code"] for diagnostic in diagnostics]
        if "diagnostic" in case:
            case["diagnostic"] = diagnostics[0]
        if "diagnostics" in case:
            case["diagnostics"] = diagnostics
        cases.append(case)
    return {**reference, "cases": cases}


def _accept_feature(*_args: object) -> None:
    """The retained mixed cases are positive; the native fixture installs the same accepting owner."""


def _pairs(rows: list[dict[str, Any]], kind: type) -> dict[tuple[str, str], Any]:
    adapter = TypeAdapter(kind)
    return {tuple(row["key"]): adapter.validate_python({"profile_id": row["key"][0], **row["value"]}) for row in rows}


def _mixed_context(reference: dict[str, Any]) -> MixedCompositionResolutionContext:
    return MixedCompositionResolutionContext(
        scenario_snapshots={
            key: ExperimentReferenceModel.model_validate(value)
            for key, value in reference["scenario_snapshots"].items()
        },
        compiled_targets=dict(reference["compiled_targets"]),
        components=_pairs(reference["components"], MixedCompositionTrustedComponent),
        allocations=_pairs(reference["allocations"], MixedCompositionTrustedAllocation),
        edges=_pairs(reference["edges"], MixedCompositionTrustedEdge),
        transitions=_pairs(reference["transitions"], MixedCompositionTrustedTransition),
        feature_support_resolver=_accept_feature,
        feature_downgrade_authorizations=frozenset(),
        time_models={
            key: TimeModelDeclarationModel.model_validate(value) for key, value in reference["time_models"].items()
        },
        time_model_digests=dict(reference["time_model_digests"]),
        evidence_satisfaction={
            tuple(row["key"]): frozenset(row["value"]) for row in reference["evidence_satisfaction"]
        },
        nested_profiles={
            key: MixedParticipantCompositionProfileModel.model_validate(value)
            for key, value in reference["nested_profiles"].items()
        },
        allocation_effects={tuple(row["key"]): frozenset(row["value"]) for row in reference["allocation_effects"]},
        resource_refs={key: frozenset(value) for key, value in reference["resource_refs"].items()},
        component_projection_membership={
            tuple(row["key"]): bool(row["value"]) for row in reference["projection_membership"]
        },
    )


def _reseal_profile(profile: dict[str, Any]) -> dict[str, Any]:
    fields = {key: value for key, value in profile.items() if key != "profile_digest"}
    return seal_mixed_composition_profile(**fields).model_dump(mode="json")


def _replace_digests(value: Any, replacements: dict[str, str]) -> Any:
    text = json.dumps(value)
    for old, new in replacements.items():
        if old != new:
            text = text.replace(json.dumps(old), json.dumps(new))
    return json.loads(text)


def _refresh_mixed(case: dict[str, Any]) -> dict[str, Any]:
    """Carry the refreshed scenario snapshots into the profiles, contexts and assignments that cite them."""
    pure_inputs = copy.deepcopy(case["request"])
    pure_inputs["input_refs"].pop("mixed_composition_profile_refs", None)
    pure_request, _ = build_request(pure_inputs)
    pure = compile_admitted_trial_plan(pure_request)
    if pure.plan is None:
        raise ValueError(f"{case['name']} base request no longer compiles")
    snapshots = {}
    for entry in pure.plan.entries.values():
        outcomes = {selection.variation_point_id: selection.outcome for selection in entry.selections}
        selected = select_scenario_family(pure_request.family, outcomes)
        snapshots[f"snapshot:compiler-family:{entry.coordinate.replicate_id}"] = canonical_instantiated_sdl_digest(
            selected
        ).value
    replacements = {}
    for context in case["contexts"].values():
        for ref_id, ref in context["scenario_snapshots"].items():
            if ref_id in snapshots:
                replacements[ref["ref_digest"]] = snapshots[ref_id]
    case = _replace_digests(case, replacements)
    for _ in range(8):
        profile_digests = {}
        for context in case["contexts"].values():
            for key, nested in context["nested_profiles"].items():
                resealed = _reseal_profile(nested)
                profile_digests[nested["profile_digest"]] = resealed["profile_digest"]
                context["nested_profiles"][key] = resealed
        for key, profile in case["profiles"].items():
            resealed = _reseal_profile(profile)
            profile_digests[profile["profile_digest"]] = resealed["profile_digest"]
            case["profiles"][key] = resealed
        changed = {old: new for old, new in profile_digests.items() if old != new}
        if not changed:
            return case
        case = _replace_digests(case, changed)
    raise ValueError("mixed profile digests do not reach a fixed point")


def mixed_case(case: dict[str, Any]) -> dict[str, Any]:
    case = _refresh_mixed(copy.deepcopy(case))
    request, stored = build_request(case["request"])
    request = replace(
        request,
        realization_assignments={
            key: AdmittedMixedCompositionBindingModel.model_validate(value)
            for key, value in case["assignments"].items()
        },
        mixed_profiles={
            key: MixedParticipantCompositionProfileModel.model_validate(value)
            for key, value in case["profiles"].items()
        },
        mixed_profile_contexts={key: _mixed_context(value) for key, value in case["contexts"].items()},
        mixed_realization_envelopes={
            key: BackendRealizationEnvelopeModel.model_validate(value) for key, value in case["envelopes"].items()
        },
    )
    result = compile_admitted_trial_plan(request)
    if result.plan is None:
        raise ValueError(f"{case['name']} no longer compiles: {[item.code for item in result.diagnostics]}")
    return {**case, "request": stored, "plan": result.plan.model_dump(mode="json")}


def _compiled(
    inputs: dict[str, Any], name: str
) -> tuple[TrialCompilationRequest, dict[str, Any], AdmittedTrialPlanModel]:
    request, stored = build_request(inputs)
    result = compile_admitted_trial_plan(request)
    if result.plan is None:
        raise ValueError(f"{name} no longer compiles: {[item.code for item in result.diagnostics]}")
    return request, stored, result.plan


def manifest_defaults(reference: dict[str, Any]) -> dict[str, Any]:
    _, stored, plan = _compiled(reference["request"], "manifest-defaults")
    return {**reference, "request": stored, "plan": plan.model_dump(mode="json")}


def typed_replay(reference: dict[str, Any]) -> dict[str, Any]:
    request, stored, plan = _compiled(reference["request"], "typed-replay")
    entry_id = _entry_at(plan, reference["plan"]["entries"][reference["entry_id"]]["coordinate"])
    instance = _instantiation(plan, entry_id, request, provenance=False)
    return {
        **reference,
        "request": stored,
        "plan": plan.model_dump(mode="json"),
        "entry_id": entry_id,
        "snapshot_digest": instance["snapshot_digest"],
    }


def mixed_reference(reference: dict[str, Any]) -> dict[str, Any]:
    return {**reference, "cases": [mixed_case(case) for case in reference["cases"]]}


def _treatment_valid(family: Any, treatment: dict[str, Any]) -> bool:
    try:
        ExpandedScenarioBindingTargetResolver(family).validate_selection(
            ExperimentScenarioSelectionDescriptorModel.model_validate(treatment)
        )
    except SDLError, ValueError, TypeError:
        return False
    return True


def typed_reference(reference: dict[str, Any]) -> dict[str, Any]:
    """Re-record typed compilations and the treatment verdicts against the first case's family."""
    before = reference["cases"][0]["request"]["input_refs"]["scenario_family_ref"]["ref_digest"]
    cases = [compilation_case(case) for case in reference["cases"]]
    request, _ = build_request(cases[0]["request"])
    after = canonical_sdl_digest(request.family).value
    treatments = []
    for item in reference["treatments"]:
        treatment = copy.deepcopy(item["treatment"])
        if treatment.get("scenario_family_digest") == before:
            treatment["scenario_family_digest"] = after
        treatments.append({**item, "treatment": treatment, "valid": _treatment_valid(request.family, treatment)})
    return {**reference, "cases": cases, "treatments": treatments}


RECORDS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "compiler-reference.json.gz": compiler_reference,
    "typed-reference.json.gz": typed_reference,
    "typed-public-reference.json.gz": compiler_reference,
    "typed-refusals.json": refusal_reference,
    "compiler-refusal-reference.json": refusal_reference,
    "apparatus-refusals.json": refusal_reference,
    "capture-refusals.json": refusal_reference,
    "compiler-limit-reference.json": refusal_reference,
    "mixed-reference.json.gz": mixed_reference,
    "manifest-defaults-reference.json": manifest_defaults,
    "typed-replay-reference.json": typed_replay,
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
