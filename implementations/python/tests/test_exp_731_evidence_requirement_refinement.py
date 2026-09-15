"""EXP-731 scoped evidence-requirement refinement and extension."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from raes import canonical_sdl_digest
from raes.parser import parse_sdl
from raes.scenario import ExpandedScenario
from raes.validator import SemanticValidator
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    ExperimentCaptureSpecModel,
    ExperimentEvidenceRequirementRelationModel,
    ExperimentReferenceModel,
    ExperimentRunModel,
    ExperimentSpecModel,
    ExperimentStudyModel,
    ExperimentTaskModel,
    validate_evidence_requirement_relations,
)
from raes_contracts.semantic_comparison import (
    ImpactClosureStatus,
    SemanticComparisonProfileModel,
    SemanticComparisonRequestModel,
    canonical_semantic_comparison_profile_digest,
)
from raes_processor.capture_admission import (
    compile_scoped_evidence_requirement_demands,
)
from raes_processor.semantic_comparison import analyze_semantic_comparison
from raes_processor.semantic_comparison_adapters import build_impact_scope, coordinate_for_artifact
from raes_processor.trial_compiler import compile_admitted_trial_plan

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "contracts" / "fixtures" / "experiment-core"


def _fixture(contract_id: str) -> dict:
    path = FIXTURE_ROOT / contract_id / "valid" / "reference.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _scenario():
    return parse_sdl(
        """
        name: exp731-scenario
        version: 1.0.0
        evidence_requirements:
          event-log:
            description: Capture selected event fields while leaving other realization choices open.
            source_class: external
            scope: run
            window: run
            channel: log
            artifact_role: event-log
            media_types:
              - application/json
            sensitivity: plain
            redaction: none
            integrity: checksum
            retention: run_lifetime
            loss_disclosure: best_effort
            output_contract: event-stream-v1
            field_selectors:
              - /events
        """
    )


def _scenario_ref(scenario) -> dict:
    return {
        "ref_kind": "scenario-snapshot",
        "ref_id": scenario.name,
        "ref_version": scenario.version,
        "ref_digest": canonical_sdl_digest(scenario).value,
    }


def _authority_ref(scope: str, payload: dict) -> dict:
    if scope == "task":
        return {"ref_kind": "task", "ref_id": payload["task_id"], "ref_version": payload["task_version"]}
    if scope == "run-plan":
        return {
            "ref_kind": "authoring-input",
            "ref_id": payload["spec_id"],
            "ref_version": payload["spec_version"],
        }
    if scope == "run":
        return {"ref_kind": "run", "ref_id": payload["run_id"], "ref_version": payload["run_version"]}
    return {"ref_kind": "study", "ref_id": payload["study_id"], "ref_version": payload["study_version"]}


def _relation(
    scenario,
    authority_ref: dict,
    *,
    relation_kind: str = "refine",
    dimensions: list[str] | None = None,
) -> dict:
    scope = "run" if authority_ref["ref_kind"] in {"authoring-input", "run"} else authority_ref["ref_kind"]
    return {
        "relation_id": f"{scope}-event-log-detail",
        "relation_version": "1.0.0",
        "relation_kind": relation_kind,
        "scope": scope,
        "authority_ref": authority_ref,
        "base_scenario_ref": _scenario_ref(scenario),
        "base_requirement_address": "evidence_requirements.event-log",
        "capture_spec_ref": {
            "ref_kind": "capture-spec",
            "ref_id": "capture-event-log-detail",
            "ref_version": "1.0.0",
        },
        "capture_requirement_ref": "event-log-detail",
        "refinement_dimensions": dimensions or [],
        "rationale": "Require a bounded additional event field without changing the authored requirement.",
    }


def _capture_spec(
    authority_ref: dict,
    *,
    artifact_roles: list[str] | None = None,
    integrity: list[str] | None = None,
) -> ExperimentCaptureSpecModel:
    return ExperimentCaptureSpecModel.model_validate(
        {
            "schema_version": "experiment-capture-spec/v1",
            "capture_spec_id": "capture-event-log-detail",
            "spec_version": "1.0.0",
            "title": "Scoped event-log detail",
            "description": "An independently admitted scoped evidence obligation.",
            "scope_refs": [authority_ref],
            "capture_windows": [
                {
                    "window_id": "run-window",
                    "window_kind": "run",
                    "starts_at": "2026-09-14T10:00:00Z",
                    "ends_at": "2026-09-14T10:05:00Z",
                }
            ],
            "capture_requirements": {
                "event-log-detail": {
                    "requirement_id": "event-log-detail",
                    "title": "Additional event-log detail",
                    "capture_kind": "log",
                    "capture_scope": "run",
                    "channel_ref": {
                        "ref_kind": "measurement-channel",
                        "ref_id": "event-log-channel",
                        "ref_version": "1.0.0",
                    },
                    "window_refs": ["run-window"],
                    "expected_media_types": ["application/json"],
                    "required_artifact_roles": artifact_roles or ["event-log"],
                    "output_contract": "event-stream-v1",
                    "field_selectors": ["/events", "/events/0"],
                    "sensitivity": "internal",
                    "integrity_requirements": integrity or ["checksum", "sha256-digest"],
                    "loss_disclosure_required": True,
                }
            },
        }
    )


def test_relation_is_reused_by_task_run_plan_run_and_study_carriers() -> None:
    scenario = _scenario()

    task_payload = _fixture("experiment-task-v1")
    task_payload["scenario_ref"] = _scenario_ref(scenario)
    task_payload["evidence_requirement_relations"] = [
        _relation(scenario, _authority_ref("task", task_payload), dimensions=["field-selectors"])
    ]
    assert ExperimentTaskModel.model_validate(task_payload).evidence_requirement_relations[0].scope == "task"

    spec_payload = _fixture("experiment-authoring-input-v1")
    spec_payload["intended_scenario_ref"] = _scenario_ref(scenario)
    spec_payload["run_plan"]["evidence_requirement_relations"] = [
        _relation(scenario, _authority_ref("run-plan", spec_payload), dimensions=["field-selectors"])
    ]
    assert ExperimentSpecModel.model_validate(spec_payload).run_plan.evidence_requirement_relations[0].scope == "run"

    run_payload = _fixture("experiment-run-v1")
    run_payload["scenario_snapshot_ref"] = _scenario_ref(scenario)
    run_payload["evidence_requirement_relations"] = [
        _relation(scenario, _authority_ref("run", run_payload), dimensions=["field-selectors"])
    ]
    assert ExperimentRunModel.model_validate(run_payload).evidence_requirement_relations[0].scope == "run"

    study_payload = _fixture("experiment-study-v1")
    study_payload["evidence_requirement_relations"] = [
        _relation(scenario, _authority_ref("study", study_payload), dimensions=["field-selectors"])
    ]
    assert ExperimentStudyModel.model_validate(study_payload).evidence_requirement_relations[0].scope == "study"


def test_refinement_resolves_exact_lineage_and_preserves_the_authored_scenario() -> None:
    scenario = _scenario()
    before = scenario.model_dump(mode="json")
    task_payload = _fixture("experiment-task-v1")
    authority_ref = _authority_ref("task", task_payload)
    relation = ExperimentEvidenceRequirementRelationModel.model_validate(
        _relation(
            scenario,
            authority_ref,
            dimensions=["field-selectors", "integrity-requirements", "loss-disclosure"],
        )
    )
    capture_spec = _capture_spec(authority_ref)

    validated = validate_evidence_requirement_relations(
        (relation,), scenario=scenario, capture_specs={capture_spec.capture_spec_id: capture_spec}
    )

    assert validated == (relation,)
    assert scenario.model_dump(mode="json") == before


def test_refinement_fails_closed_when_a_declared_dimension_is_not_monotone() -> None:
    scenario = _scenario()
    task_payload = _fixture("experiment-task-v1")
    authority_ref = _authority_ref("task", task_payload)
    relation = ExperimentEvidenceRequirementRelationModel.model_validate(
        _relation(scenario, authority_ref, dimensions=["integrity-requirements"])
    )
    capture_spec = _capture_spec(authority_ref, integrity=["timestamped"])

    with pytest.raises(ValueError, match="integrity-requirements.*preserve"):
        validate_evidence_requirement_relations(
            (relation,), scenario=scenario, capture_specs={capture_spec.capture_spec_id: capture_spec}
        )


def test_artifact_role_refinement_rejects_an_added_alternative() -> None:
    scenario = _scenario()
    task_payload = _fixture("experiment-task-v1")
    authority_ref = _authority_ref("task", task_payload)
    relation = ExperimentEvidenceRequirementRelationModel.model_validate(
        _relation(scenario, authority_ref, dimensions=["artifact-roles"])
    )
    capture_spec = _capture_spec(authority_ref, artifact_roles=["event-log", "unrelated-role"])

    with pytest.raises(ValueError, match="artifact-roles.*must not add accepted values"):
        validate_evidence_requirement_relations(
            (relation,), scenario=scenario, capture_specs={capture_spec.capture_spec_id: capture_spec}
        )


def test_refinement_rejects_changed_scenario_identity_and_wrong_authority() -> None:
    scenario = _scenario()
    task_payload = _fixture("experiment-task-v1")
    authority_ref = _authority_ref("task", task_payload)
    relation_payload = _relation(scenario, authority_ref, dimensions=["field-selectors"])
    relation_payload["base_scenario_ref"]["ref_digest"] = "sha256:" + "0" * 64
    relation = ExperimentEvidenceRequirementRelationModel.model_validate(relation_payload)

    with pytest.raises(ValueError, match="base_scenario_ref must match"):
        validate_evidence_requirement_relations(
            (relation,), scenario=scenario, capture_specs={"capture-event-log-detail": _capture_spec(authority_ref)}
        )

    wrong_task = copy.deepcopy(task_payload)
    wrong_task["scenario_ref"] = _scenario_ref(scenario)
    wrong_task["evidence_requirement_relations"] = [
        _relation(
            scenario,
            {"ref_kind": "task", "ref_id": "another-task", "ref_version": "1.0.0"},
            dimensions=["field-selectors"],
        )
    ]
    with pytest.raises(ValueError, match="authority_ref must match the task carrier"):
        ExperimentTaskModel.model_validate(wrong_task)


def test_extension_compiles_base_and_scoped_demands_conjunctively_without_filling_open_detail() -> None:
    scenario = _scenario()
    task_payload = _fixture("experiment-task-v1")
    authority_ref = _authority_ref("task", task_payload)
    relation = ExperimentEvidenceRequirementRelationModel.model_validate(
        _relation(scenario, authority_ref, relation_kind="extend")
    )
    capture_spec = _capture_spec(authority_ref)

    demands = compile_scoped_evidence_requirement_demands(
        scenario,
        (capture_spec,),
        (relation,),
    )

    assert [demand.address for demand in demands] == [
        "evidence_requirements.event-log",
        "capture_specs.capture-event-log-detail.capture_requirements.event-log-detail",
    ]
    assert demands[0].source_classes == ("external",)
    assert demands[0].source_refs == ()
    assert demands[1].source_classes == ()
    assert demands[1].source_refs == ()


def _compare(before: object, after: object):
    profile_path = REPO_ROOT / "contracts" / "profiles" / "semantic-comparison" / "reference-v2.json"
    profile = SemanticComparisonProfileModel.model_validate_json(profile_path.read_text(encoding="utf-8"))
    before_coordinate = coordinate_for_artifact(before)
    after_coordinate = coordinate_for_artifact(after)
    scope = build_impact_scope(
        (before,),
        (after,),
        traversal_roots=(after_coordinate.canonical_identity,),
        closure_status=ImpactClosureStatus.COMPLETE,
    )
    request = SemanticComparisonRequestModel(
        comparison_profile=profile.profile_id,
        comparison_profile_digest=canonical_semantic_comparison_profile_digest(profile),
        analyzer_profile=profile.analyzer_profile,
        before=before_coordinate,
        after=after_coordinate,
        impact_scope=scope,
    )
    return analyze_semantic_comparison(profile, request, before, after)


@pytest.mark.parametrize(
    ("contract_id", "model", "scope"),
    [
        ("experiment-task-v1", ExperimentTaskModel, "task"),
        ("experiment-run-v1", ExperimentRunModel, "run"),
        ("experiment-study-v1", ExperimentStudyModel, "study"),
    ],
)
def test_semantic_comparison_detects_relation_changes(contract_id: str, model: type, scope: str) -> None:
    scenario = _scenario()
    payload = _fixture(contract_id)
    if scope == "task":
        payload["scenario_ref"] = _scenario_ref(scenario)
    elif scope == "run":
        payload["scenario_snapshot_ref"] = _scenario_ref(scenario)
    before = model.model_validate(payload)
    payload["evidence_requirement_relations"] = [
        _relation(scenario, _authority_ref(scope, payload), relation_kind="extend")
    ]
    after = model.model_validate(payload)

    owner_identity = coordinate_for_artifact(after).canonical_identity
    change = next(change for change in _compare(before, after).changes if change.identity == owner_identity)

    assert change.structural_relation.value == "changed"
    assert change.semantic_relation.value == "changed"


def _family_with_authored_requirement(family: ExpandedScenario) -> ExpandedScenario:
    payload = family.model_dump(
        mode="python",
        by_alias=True,
        exclude_unset=True,
        exclude={"expansion_provenance"},
    )
    payload["evidence_requirements"] = {
        "event-log": _scenario()
        .evidence_requirements["event-log"]
        .model_dump(
            mode="python",
            by_alias=True,
            exclude_unset=True,
        )
    }
    updated = ExpandedScenario.model_validate(payload)
    SemanticValidator(updated).validate()
    updated._set_semantic_validated(True)
    return updated


def _request_with_invalid_relation(carrier: str):
    from test_sce_002_trial_compiler import _request

    base_request = _request(run_count=2)
    request = base_request.with_family(_family_with_authored_requirement(base_request.family))
    family = request.family
    task_payload = request.task.model_dump(mode="json")
    task_payload["scenario_ref"] = _scenario_ref(family)
    experiment_payload = request.experiment.model_dump(mode="json")
    if carrier == "task":
        authority_ref = _authority_ref("task", task_payload)
        task_payload["evidence_requirement_relations"] = [
            _relation(family, authority_ref, dimensions=["integrity-requirements"])
        ]
    else:
        authority_ref = _authority_ref("run-plan", experiment_payload)
        experiment_payload["run_plan"]["evidence_requirement_relations"] = [
            _relation(family, authority_ref, dimensions=["integrity-requirements"])
        ]
    capture_spec = _capture_spec(authority_ref, integrity=["timestamped"])
    experiment_payload["capture_spec_refs"].append(
        {
            "ref_kind": "capture-spec",
            "ref_id": capture_spec.capture_spec_id,
            "ref_version": capture_spec.spec_version,
        }
    )
    task = ExperimentTaskModel.model_validate(task_payload)
    experiment = ExperimentSpecModel.model_validate(experiment_payload)
    input_refs = request.input_refs.model_copy(
        update={
            "authoring_input_ref": request.input_refs.authoring_input_ref.model_copy(
                update={"ref_digest": canonical_json_digest(experiment.model_dump(mode="json"))}
            ),
            "task_digest": canonical_json_digest(task.model_dump(mode="json")),
            "capture_spec_refs": [
                *request.input_refs.capture_spec_refs,
                ExperimentReferenceModel(
                    ref_kind="capture-spec",
                    ref_id=capture_spec.capture_spec_id,
                    ref_version=capture_spec.spec_version,
                    ref_digest=canonical_json_digest(capture_spec.model_dump(mode="json")),
                ),
            ],
        }
    )
    return replace(
        request,
        experiment=experiment,
        task=task,
        input_refs=input_refs,
        capture_specs={**request.capture_specs, capture_spec.capture_spec_id: capture_spec},
    )


@pytest.mark.parametrize("carrier", ["task", "run-plan"])
def test_trial_compiler_rejects_invalid_authoritative_relations(carrier: str) -> None:
    result = compile_admitted_trial_plan(_request_with_invalid_relation(carrier))

    assert result.plan is None
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["trial-compiler.entry-invalid"]
