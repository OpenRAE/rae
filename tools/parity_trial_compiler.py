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
    ExperimentRunModel,
    ExperimentScenarioSelectionDescriptorModel,
    ExperimentSpecModel,
    ExperimentTaskModel,
    MixedParticipantCompositionProfileModel,
    TrialCleanupReceiptModel,
    seal_mixed_composition_profile,
)
from raes_contracts.contracts.admitted_trial_plan import canonical_entry_order  # noqa: E402
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
from raes_contracts.contracts.trial_replacement import TrialReplacementOriginModel  # noqa: E402
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel  # noqa: E402
from raes_processor.trial_compiler import TrialCompilationRequest, compile_admitted_trial_plan  # noqa: E402
from raes_processor.trial_compiler.compiler import _compile  # noqa: E402
from raes_processor.trial_compiler.models import (  # noqa: E402
    TrialCompilationLimitsModel,
    TrialExecutionAuthorityModel,
)
from raes_processor.trial_compiler.replacement import TrialReplacementResult, compile_replacement_trial  # noqa: E402
from raes_processor.trial_compiler.replacement_inputs import ReplacementCompilationContext  # noqa: E402
from raes_processor.trial_realization import (  # noqa: E402
    TrialRealizationInputs,
    instantiate_admitted_trial_entry,
    realize_admitted_trial_entry,
)

TESTDATA = ROOT / "implementations/go/processor/trial/testdata"


def _digest(model: object) -> str:
    return canonical_json_digest(model.model_dump(mode="json"))


def _manifest(key: list[str], payload: dict[str, object]) -> BackendManifestV2Model | ProcessorManifestV2Model:
    model = ProcessorManifestV2Model if key[0] == "processor" else BackendManifestV2Model
    return model.model_validate(payload)


def build_request(
    payload: dict[str, object], limits: dict[str, object] | None = None
) -> tuple[TrialCompilationRequest, dict[str, object]]:
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
) -> dict[str, object]:
    instance = instantiate_admitted_trial_entry(plan=plan, plan_entry_id=entry_id, family=request.family)
    result = {"entry_id": entry_id, "snapshot_digest": canonical_instantiated_sdl_digest(instance).value}
    if provenance:
        result["provenance"] = instance.instantiation_provenance.trial.model_dump(mode="json")
    return result


def _realization(plan: AdmittedTrialPlanModel, entry_id: str, request: TrialCompilationRequest) -> dict[str, object]:
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


def _entry_at(plan: AdmittedTrialPlanModel, coordinate: dict[str, object]) -> str:
    """Return the entry at the retained instantiation coordinate; identities follow the refreshed inputs."""
    matches = [key for key, entry in plan.entries.items() if entry.coordinate.model_dump(mode="json") == coordinate]
    if len(matches) != 1:
        raise ValueError("the retained instantiation coordinate does not name one compiled entry")
    return matches[0]


def compilation_case(case: dict[str, object]) -> dict[str, object]:
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


def compiler_reference(reference: dict[str, object]) -> dict[str, object]:
    return {**reference, "cases": [compilation_case(case) for case in reference["cases"]]}


def _diagnostics(case: dict[str, object]) -> list[dict[str, object]]:
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


def refusal_reference(reference: dict[str, object]) -> dict[str, object]:
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


def _pairs(rows: list[dict[str, object]], kind: type) -> dict[tuple[str, str], object]:
    adapter = TypeAdapter(kind)
    return {tuple(row["key"]): adapter.validate_python({"profile_id": row["key"][0], **row["value"]}) for row in rows}


def _mixed_context(reference: dict[str, object]) -> MixedCompositionResolutionContext:
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


def _reseal_profile(profile: dict[str, object]) -> dict[str, object]:
    fields = {key: value for key, value in profile.items() if key != "profile_digest"}
    return seal_mixed_composition_profile(**fields).model_dump(mode="json")


def _replace_digests(value: object, replacements: dict[str, str]) -> object:
    text = json.dumps(value)
    for old, new in replacements.items():
        if old != new:
            text = text.replace(json.dumps(old), json.dumps(new))
    return json.loads(text)


def _refresh_mixed(case: dict[str, object]) -> dict[str, object]:
    """Carry the refreshed scenario snapshots into the profiles, contexts and assignments that cite them."""
    snapshots = _pure_snapshots(case)
    replacements = {
        ref["ref_digest"]: snapshots[ref_id]
        for context in case["contexts"].values()
        for ref_id, ref in context["scenario_snapshots"].items()
        if ref_id in snapshots
    }
    case = _replace_digests(case, replacements)
    for _ in range(8):
        changed = {old: new for old, new in _reseal_profiles(case).items() if old != new}
        if not changed:
            return case
        case = _replace_digests(case, changed)
    raise ValueError("mixed profile digests do not reach a fixed point")


def _pure_snapshots(case: dict[str, object]) -> dict[str, str]:
    """Return the scenario snapshot digest of each entry that the request compiles without mixed profiles."""
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
        snapshot = canonical_instantiated_sdl_digest(selected).value
        snapshots[f"snapshot:compiler-family:{entry.coordinate.replicate_id}"] = snapshot
    return snapshots


def _reseal_profiles(case: dict[str, object]) -> dict[str, str]:
    """Reseal each nested and top-level profile in place; return each old digest with its new digest."""
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
    return profile_digests


def _mixed_request(case: dict[str, object]) -> tuple[TrialCompilationRequest, dict[str, object]]:
    request, stored = build_request(case["request"])
    return replace(
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
    ), stored


def mixed_case(case: dict[str, object]) -> dict[str, object]:
    case = _refresh_mixed(copy.deepcopy(case))
    request, stored = _mixed_request(case)
    result = compile_admitted_trial_plan(request)
    if result.plan is None:
        raise ValueError(f"{case['name']} no longer compiles: {[item.code for item in result.diagnostics]}")
    return {**case, "request": stored, "plan": result.plan.model_dump(mode="json")}


def _compiled(
    inputs: dict[str, object], name: str
) -> tuple[TrialCompilationRequest, dict[str, object], AdmittedTrialPlanModel]:
    request, stored = build_request(inputs)
    result = compile_admitted_trial_plan(request)
    if result.plan is None:
        raise ValueError(f"{name} no longer compiles: {[item.code for item in result.diagnostics]}")
    return request, stored, result.plan


def manifest_defaults(reference: dict[str, object]) -> dict[str, object]:
    _, stored, plan = _compiled(reference["request"], "manifest-defaults")
    return {**reference, "request": stored, "plan": plan.model_dump(mode="json")}


def typed_replay(reference: dict[str, object]) -> dict[str, object]:
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


def mixed_reference(reference: dict[str, object]) -> dict[str, object]:
    return {**reference, "cases": [mixed_case(case) for case in reference["cases"]]}


def mixed_replacement_case(case: dict[str, object]) -> dict[str, object]:
    """Compile the first original slot's successor against its own freshly compiled root plan."""
    case = _refresh_mixed(copy.deepcopy(case))
    request, stored = _mixed_request(case)
    root = compile_admitted_trial_plan(request).plan
    if root is None:
        raise ValueError(f"{case['name']} root no longer compiles")
    root_entry = canonical_entry_order(root)[0]
    origin = {
        **case["origin"],
        "root_plan_id": root.plan_id,
        "root_plan_digest": root.plan_digest,
        "root_entry_id": root_entry,
        "parent_plan_id": root.plan_id,
        "parent_plan_digest": root.plan_digest,
        "parent_entry_id": root_entry,
        "parent_run_id": root.entries[root_entry].run_id,
    }
    context = ReplacementCompilationContext(
        origin=TrialReplacementOriginModel.model_validate(origin), coordinate_index=0
    )
    child = _compile(request, None, context)
    return {**case, "request": stored, "plan": child.model_dump(mode="json"), "origin": origin}


def mixed_replacement_reference(reference: dict[str, object]) -> dict[str, object]:
    return {**reference, "cases": [mixed_replacement_case(case) for case in reference["cases"]]}


RUN_FIXTURE = ROOT / "contracts/fixtures/experiment-core/experiment-run-v1/valid/reference.json"


def _realized_refs(request: TrialCompilationRequest, plan: AdmittedTrialPlanModel, entry_id: str) -> list[object]:
    return _realization(plan, entry_id, request)["processor_plan_refs"]


def _archive(
    request: TrialCompilationRequest,
    plan: AdmittedTrialPlanModel,
    *,
    cleanup_status: str = "succeeded",
) -> tuple[ExperimentRunModel, TrialCleanupReceiptModel]:
    """Archive the first entry as one failed trial, as the reference replacement scenario does."""
    entry = next(iter(plan.entries.values()))
    snapshot = instantiate_admitted_trial_entry(plan=plan, plan_entry_id=entry.plan_entry_id, family=request.family)
    snapshot_digest = canonical_instantiated_sdl_digest(snapshot).value
    cleanup = plan.cleanup_plans[entry.execution_controls.cleanup_plan_ref]
    receipt = TrialCleanupReceiptModel(
        receipt_id=f"cleanup:{entry.run_id}",
        cleanup_plan_ref=cleanup.plan_id,
        plan_entry_id=entry.plan_entry_id,
        run_id=entry.run_id,
        execution_attempt_id=f"attempt:{entry.run_id}",
        trial_outcome="failed",
        cleanup_status=cleanup_status,
        obligation_results={
            key: {
                "obligation_id": key,
                "status": "succeeded" if cleanup_status == "succeeded" else "failed",
                "evidence_refs": ["evidence:cleanup"],
            }
            for key in cleanup.cleanup_obligations
        },
        clean_state_claim=(
            {
                "disposition": "verified-clean",
                "boundary_refs": list(cleanup.resource_boundaries),
                "evidence_refs": ["evidence:clean"],
            }
            if cleanup_status == "succeeded"
            else None
        ),
    )
    payload = json.loads(RUN_FIXTURE.read_text(encoding="utf-8"))
    payload.update(
        run_id=entry.run_id,
        run_status="failed",
        outcome_status="failed",
        scenario_snapshot_ref={
            "ref_kind": "scenario-snapshot",
            "ref_id": request.family.name,
            "ref_version": "raes-sdl-instantiated-snapshot/v2",
            "ref_digest": snapshot_digest,
        },
        trial_provenance={
            "plan_id": plan.plan_id,
            "plan_digest": plan.plan_digest,
            "plan_entry_id": entry.plan_entry_id,
            "entry_digest": entry.entry_digest,
            "admitted_run_id": entry.run_id,
            "coordinate": entry.coordinate.model_dump(),
            "instantiated_scenario_digest": snapshot_digest,
            "processor_plan_refs": _realized_refs(request, plan, entry.plan_entry_id),
            "execution_attempts": [
                {"execution_attempt_id": receipt.execution_attempt_id, "cleanup_receipt_ref": receipt.receipt_id}
            ],
            "terminal_attempt_id": receipt.execution_attempt_id,
        },
        stochastic_controls=[control.model_dump() for control in plan.stochastic_controls.values()],
        stochastic_draws=[draw.model_dump() for draw in entry.stochastic_draws],
    )
    if plan.replacement_origin is not None:
        payload["run_version"] = "1"
    if not payload["stochastic_controls"]:
        payload["stochastic_controls"] = [{"control_id": "deterministic", "role": "other"}]
    payload["participant_implementation_provenance"]["run_id"] = entry.run_id
    return ExperimentRunModel.model_validate(payload), receipt


def _replacement_wire(result: TrialReplacementResult) -> dict[str, object]:
    return {
        "plan": None if result.plan is None else result.plan.model_dump(mode="json"),
        "superseded_run": None if result.superseded_run is None else result.superseded_run.model_dump(mode="json"),
        "parent_run": None if result.parent_run is None else result.parent_run.model_dump(mode="json"),
        "cleanup_receipts": [item.model_dump(mode="json") for item in result.cleanup_receipts],
        "diagnostics": [
            {
                "code": item.code,
                "domain": item.domain,
                "address": item.address,
                "message": item.message,
                "severity": str(getattr(item.severity, "value", item.severity)),
            }
            for item in result.diagnostics
        ],
    }


def replacement_reference(reference: dict[str, object]) -> dict[str, object]:
    """Re-run the reference replacement scenario that each retained case names."""
    request, stored, root = _compiled(reference["request"], "replacement-root")
    root_entry = next(iter(root.entries))

    def allocate(
        run: ExperimentRunModel, receipt: TrialCleanupReceiptModel, history: tuple[TrialReplacementResult, ...] = ()
    ) -> object:
        return compile_replacement_trial(
            request,
            original_plan=root,
            root_entry_id=root_entry,
            previous_allocations=history,
            failed_run=run,
            cleanup_receipts=[receipt],
        )

    run0, receipt0 = _archive(request, root)
    first = allocate(run0, receipt0)
    run1, receipt1 = _archive(request, first.plan)
    second = allocate(run1, receipt1, (first,))
    run2, receipt2 = _archive(request, second.plan)
    changed = ExperimentRunModel.model_validate({**run0.model_dump(mode="json"), "run_version": "changed"})
    scenarios: dict[str, tuple[ExperimentRunModel, TrialCleanupReceiptModel, tuple[TrialReplacementResult, ...]]] = {
        "fresh": (run0, receipt0, ()),
        "second": (run1, receipt1, (first,)),
        "duplicate": (run0, receipt0, (first, second)),
        "exhausted": (run2, receipt2, (first, second)),
        "missing-prefix": (run1, receipt1, ()),
        "conflict": (changed, receipt0, (first,)),
    }
    for status in ("failed", "partial", "unverified"):
        run, receipt = _archive(request, root, cleanup_status=status)
        scenarios[f"cleanup-{status}"] = (run, receipt, ())
    for name, claim in (
        ("not-reusable-9", None),
        (
            "not-reusable-10",
            {"disposition": "fresh-range-required", "boundary_refs": ["range"], "evidence_refs": ["new-name"]},
        ),
    ):
        receipt = TrialCleanupReceiptModel.model_validate({**receipt0.model_dump(), "clean_state_claim": claim})
        scenarios[name] = (run0, receipt, ())
    cases = []
    for case in reference["cases"]:
        run, receipt, history = scenarios[case["name"]]
        cases.append(
            {
                "name": case["name"],
                "parent_run": run.model_dump(mode="json"),
                "cleanup_receipts": [receipt.model_dump(mode="json")],
                "history": [_replacement_wire(item) for item in history],
                "expected": _replacement_wire(allocate(run, receipt, history)),
            }
        )
    return {
        **reference,
        "request": stored,
        "root": root.model_dump(mode="json"),
        "root_entry_id": root_entry,
        "cases": cases,
    }


def _treatment_valid(family: object, treatment: dict[str, object]) -> bool:
    try:
        ExpandedScenarioBindingTargetResolver(family).validate_selection(
            ExperimentScenarioSelectionDescriptorModel.model_validate(treatment)
        )
    except SDLError, ValueError, TypeError:
        return False
    return True


def typed_reference(reference: dict[str, object]) -> dict[str, object]:
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


RECORDS: dict[str, Callable[[dict[str, object]], dict[str, object]]] = {
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
    "replacement-reference.json.gz": replacement_reference,
    "mixed-replacement-reference.json.gz": mixed_replacement_reference,
}


def _load(path: Path) -> object:
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def _store(path: Path, value: object) -> None:
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
