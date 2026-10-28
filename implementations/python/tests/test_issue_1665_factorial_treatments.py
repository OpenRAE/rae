"""Typed factorial contract publication, source joins, and compatibility."""

import json
from copy import deepcopy

import pytest
from pydantic import ValidationError
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    AdmittedSelectionRecordModel,
    AdmittedTrialPlanModel,
    ExperimentRunModel,
    ExperimentSpecModel,
)
from raes_contracts.contracts.experiment_conditions import _run_satisfies_condition_assignment
from test_exp_719_factorial_allocation import _payload


def _typed_payload() -> dict:
    payload = _payload()
    design = payload["factorial_design"]
    bindings = design.pop("level_bindings")
    design["profile"] = "factorial-treatments-v1"
    design["level_effects"] = {
        "agent": {level: {"bindings": values} for level, values in bindings["agent"].items()},
        "path": {
            level: {
                "selections": [
                    {
                        "target": {
                            "plane": "scenario",
                            "scenario_family_id": "compiler-family",
                            "variation_point_id": "worker-presence",
                            "target_id": "nodes.worker.presence",
                        },
                        "scenario_family_digest": "sha256:" + "a" * 64,
                        "owner": bindings["path"][level][0]["owner"],
                        "outcome": {"kind": "member", "member_id": member},
                    }
                ]
            }
            for level, member in (("a", "absent"), ("b", "with-jobs"))
        },
    }
    return payload


def test_mixed_treatments_materialize_typed_source_criteria_and_roundtrip() -> None:
    spec = ExperimentSpecModel.model_validate(_typed_payload())
    allocation = spec.run_plan.allocation
    assert len(allocation.compared_conditions) == 4
    assert spec.binding_semantics == "explicit-required"
    for assignment in allocation.condition_assignments.values():
        selection = assignment.required_selections[0]
        assert selection.source_factor_id == "path"
        assert selection.source_factor_level_id == assignment.factor_levels["path"]
        assert selection.source_condition_id == assignment.condition_id
        assert selection.target.scenario_family_id == "compiler-family"
        assert selection.outcome.kind == "member"
        assert len(assignment.required_bindings) == 1
        assert (
            selection.selection_id
            == "selection-"
            + canonical_json_digest([assignment.condition_id, "path", selection.target.canonical_key()]).split(":")[1]
        )
    assert ExperimentSpecModel.model_validate_json(spec.model_dump_json()) == spec


def test_selection_only_design_needs_no_dummy_binding_and_accepts_fixed_configuration() -> None:
    payload = _typed_payload()
    payload["factors"].pop("agent")
    design = payload["factorial_design"]
    design["factor_ids"].remove("agent")
    design["level_effects"].pop("agent")
    payload["run_plan"]["selection_policies"] = {
        "invariant-mode": {
            "kind": "fixed",
            "policy_id": "invariant-mode",
            "purpose": "fixed-configuration",
            "point_ref": "payload-mode",
            "outcome": {"kind": "literal", "value": "safe"},
            "output_bound": 1,
        }
    }
    spec = ExperimentSpecModel.model_validate(payload)
    assert spec.binding_semantics == "explicit-required"
    assert spec.binding_descriptors is None
    assert all(not a.required_bindings for a in spec.run_plan.allocation.condition_assignments.values())
    assert ExperimentSpecModel.model_validate_json(spec.model_dump_json()) == spec


def test_scalar_identity_projection_remains_unchanged() -> None:
    legacy = ExperimentSpecModel.model_validate(_payload())
    typed = ExperimentSpecModel.model_validate(_typed_payload())
    assert typed.run_plan.allocation.compared_conditions == legacy.run_plan.allocation.compared_conditions
    assert {b.binding_id for b in typed.binding_descriptors.descriptors}.issubset(
        {b.binding_id for b in legacy.binding_descriptors.descriptors}
    )
    scalar = deepcopy(_payload())
    assert ExperimentSpecModel.model_validate_json(legacy.model_dump_json()) == legacy
    assert "level_effects" not in legacy.model_dump(mode="json")["factorial_design"]
    assert scalar["factorial_design"]["profile"] == "factorial-bindings-v1"


def _criterion():
    spec = ExperimentSpecModel.model_validate(_typed_payload())
    return next(iter(spec.run_plan.allocation.condition_assignments.values())).required_selections[0]


def test_admitted_record_retains_treatment_and_rejects_an_outcome_substitution() -> None:
    criterion = _criterion()
    payload = {
        "variation_point_id": criterion.target.variation_point_id,
        "origin_policy_id": "factorial-treatments-v1",
        "origin_policy_kind": "stratified",
        "outcome": criterion.outcome.model_dump(mode="json"),
        "treatment": criterion.model_dump(mode="json"),
    }
    record = AdmittedSelectionRecordModel.model_validate(payload)
    assert AdmittedSelectionRecordModel.model_validate_json(record.model_dump_json()) == record
    payload["outcome"] = {"kind": "member", "member_id": "substituted"}
    with pytest.raises(ValidationError, match="treatment"):
        AdmittedSelectionRecordModel.model_validate(payload)


def test_archival_criteria_require_exact_selection_source_and_content() -> None:
    from test_sce_002_trial_realization import _RUN_FIXTURE

    spec = ExperimentSpecModel.model_validate(_typed_payload())
    assignment = next(iter(spec.run_plan.allocation.condition_assignments.values()))
    criterion = assignment.required_selections[0]
    # Isolate the structural criterion from participant realization obligations.
    assignment = type(assignment).model_validate({**assignment.model_dump(mode="json"), "required_bindings": []})
    payload = json.loads(_RUN_FIXTURE.read_text())
    payload["realized_selections"] = [criterion.model_dump(mode="json")]
    run = ExperimentRunModel.model_validate(payload)
    assert _run_satisfies_condition_assignment(run, assignment) == []
    payload["realized_selections"][0]["source_factor_level_id"] = "wrong-level"
    tampered = ExperimentRunModel.model_validate(payload)
    assert _run_satisfies_condition_assignment(tampered, assignment) == [f"selection:{criterion.selection_id}"]
    payload["realized_selections"] = []
    missing = ExperimentRunModel.model_validate(payload)
    assert _run_satisfies_condition_assignment(missing, assignment) == [f"selection:{criterion.selection_id}"]


def _treatment_plan_fields():
    from raes_contracts.contracts import seal_admitted_trial_entry
    from raes_contracts.contracts.experiment_treatments import ExperimentFactorLevelSelectionModel
    from test_sce_002_admitted_trial_plan import _plan

    plan = _plan()
    entry = next(iter(plan.entries.values()))
    original = entry.selections[0]
    family_ref = plan.input_refs.scenario_family_ref
    template = ExperimentFactorLevelSelectionModel.model_validate(
        {
            "target": {
                **_criterion().target.model_dump(),
                "scenario_family_id": family_ref.ref_id,
                "variation_point_id": original.variation_point_id,
            },
            "scenario_family_digest": family_ref.ref_digest,
            "owner": _criterion().owner,
            "outcome": original.outcome,
        }
    )
    record = AdmittedSelectionRecordModel.model_validate(
        {**original.model_dump(), "treatment": template.descriptor("weather", "clear", entry.coordinate.condition_id)}
    )
    entry = seal_admitted_trial_entry(
        **{**_unsealed_fields(entry, "entry_digest"), "selections": [record], "bindings": []}
    )
    return {
        **_unsealed_fields(plan, "plan_digest"),
        "entries": {entry.plan_entry_id: entry},
        "profiles": plan.profiles.model_copy(update={"treatment_profile": "factorial-treatments-v1"}),
    }


def _unsealed_fields(model, digest_field):
    return {key: getattr(model, key) for key in type(model).model_fields if key != digest_field}


@pytest.mark.parametrize("tamper", [None, "family", "digest", "condition", "profile"])
def test_resealed_plan_checks_treatment_family_coordinate_and_profile(tamper) -> None:
    from raes_contracts.contracts import seal_admitted_trial_entry, seal_admitted_trial_plan
    from raes_contracts.contracts.experiment_treatments import ExperimentFactorLevelSelectionModel

    fields = _treatment_plan_fields()
    entry = next(iter(fields["entries"].values()))
    if tamper == "profile":
        fields["profiles"] = fields["profiles"].model_copy(update={"treatment_profile": None})
    elif tamper:
        descriptor = entry.selections[0].treatment
        template = descriptor.model_dump(
            exclude={"selection_id", "source_factor_id", "source_factor_level_id", "source_condition_id"}
        )
        condition = descriptor.source_condition_id
        if tamper == "family":
            template["target"]["scenario_family_id"] = "other-family"
        elif tamper == "digest":
            template["scenario_family_digest"] = "sha256:" + "f" * 64
        else:
            condition = "other-condition"
        changed = ExperimentFactorLevelSelectionModel.model_validate(template).descriptor("weather", "clear", condition)
        record = AdmittedSelectionRecordModel.model_validate({**entry.selections[0].model_dump(), "treatment": changed})
        fields["entries"][entry.plan_entry_id] = seal_admitted_trial_entry(
            **{**_unsealed_fields(entry, "entry_digest"), "selections": [record]}
        )
    if tamper:
        with pytest.raises(ValidationError, match="treatment"):
            seal_admitted_trial_plan(**fields)
    else:
        plan = seal_admitted_trial_plan(**fields)
        assert (
            AdmittedTrialPlanModel.model_validate_json(plan.model_dump_json()).model_dump_json()
            == plan.model_dump_json()
        )


def test_current_compiler_refuses_unimplemented_treatment_profile_explicitly() -> None:
    from raes_processor.trial_compiler import compile_admitted_trial_plan
    from test_sce_002_trial_compiler import _request

    request = _request().with_experiment(ExperimentSpecModel.model_validate(_typed_payload()))
    result = compile_admitted_trial_plan(request)
    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.factorial-profile-unsupported"


def test_current_compiler_refuses_manual_typed_criteria_without_a_profile() -> None:
    from raes_contracts.contracts.experiment_treatments import ExperimentFactorLevelSelectionModel
    from raes_processor.trial_compiler import compile_admitted_trial_plan
    from test_sce_002_trial_compiler import _request, _stratified_spec

    request = _request()
    payload = _stratified_spec().model_dump(mode="json")
    template = _typed_payload()["factorial_design"]["level_effects"]["path"]["a"]["selections"][0]
    template["target"].update(variation_point_id="payload-path", target_id="variables.payload_path")
    template["scenario_family_digest"] = request.input_refs.scenario_family_ref.ref_digest
    for condition, assignment in payload["run_plan"]["allocation"]["condition_assignments"].items():
        level = assignment["factor_levels"]["red-tactic"]
        template["outcome"] = {"kind": "literal", "value": "/opt/b" if level == "aggressive" else "/opt/a"}
        selection = ExperimentFactorLevelSelectionModel.model_validate(template).descriptor(
            "red-tactic", level, condition
        )
        assignment["required_selections"] = [selection.model_dump(mode="json")]
    spec = ExperimentSpecModel.model_validate(payload)
    assert spec.factorial_design is None
    result = compile_admitted_trial_plan(request.with_experiment(spec))
    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.factorial-profile-unsupported"
    assert result.diagnostics[0].address == "/run_plan/allocation/condition_assignments"


def test_plan_aware_archive_rejects_missing_or_relabelled_treatment() -> None:
    from raes_contracts.contracts.trial_analysis import _validate_run_binding_provenance
    from test_sce_002_trial_realization import _RUN_FIXTURE

    entry = next(iter(_treatment_plan_fields()["entries"].values()))
    criterion = entry.selections[0].treatment
    payload = json.loads(_RUN_FIXTURE.read_text())
    payload["realized_selections"] = [criterion.model_dump(mode="json")]
    _validate_run_binding_provenance(entry, ExperimentRunModel.model_validate(payload))
    for actual in ([], [{**criterion.model_dump(mode="json"), "source_factor_level_id": "other"}]):
        payload["realized_selections"] = actual
        run = ExperimentRunModel.model_validate(payload)
        with pytest.raises(ValueError, match="selection"):
            _validate_run_binding_provenance(entry, run)


def test_selection_template_rejects_nonfinite_literals_at_the_contract_boundary() -> None:
    from raes_contracts.contracts.experiment_treatments import ExperimentFactorLevelSelectionModel

    template = _typed_payload()["factorial_design"]["level_effects"]["path"]["a"]["selections"][0]
    template["outcome"] = {"kind": "literal", "value": float("nan")}
    with pytest.raises(ValidationError, match="finite"):
        ExperimentFactorLevelSelectionModel.model_validate(template)


@pytest.mark.parametrize(
    "change",
    ["empty", "duplicate", "scalar-overlap", "fixed-overlap", "dynamic", "fixed-claims", "unknown-level", "work"],
)
def test_invalid_treatment_designs_fail_atomically(change) -> None:
    payload = _typed_payload()
    design = payload["factorial_design"]
    effects = design["level_effects"]["path"]["a"]
    if change == "empty":
        effects["selections"] = []
    elif change == "duplicate":
        effects["selections"] *= 2
    elif change == "scalar-overlap":
        effects["bindings"] = [_payload()["factorial_design"]["level_bindings"]["path"]["a"][0]]
        effects["bindings"][0]["target"]["variation_point_id"] = "worker-presence"
    elif change in {"fixed-overlap", "dynamic", "fixed-claims"}:
        policy = {
            "kind": "fixed",
            "policy_id": "fixed",
            "purpose": "fixed-configuration",
            "point_ref": "worker-presence",
            "outcome": {"kind": "member", "member_id": "absent"},
            "output_bound": 1,
        }
        if change == "dynamic":
            policy.update(kind="enumerate", purpose="nuisance-variation")
            policy.pop("outcome")
        elif change == "fixed-claims":
            policy["binding_descriptor_refs"] = ["unrelated-binding"]
        payload["run_plan"]["selection_policies"] = {"fixed": policy}
    elif change == "unknown-level":
        design["level_effects"]["path"]["unknown"] = effects
    else:
        design["target_runs_per_condition"] = 2000
    with pytest.raises(ValidationError):
        ExperimentSpecModel.model_validate(payload)


def test_expanded_byte_budget_is_checked_before_building_conditions(monkeypatch) -> None:
    import raes_contracts.contracts.experiment_factorial_treatments as materialization

    payload = _typed_payload()
    for effects in payload["factorial_design"]["level_effects"]["agent"].values():
        effects["bindings"][0].update(value_type="string", value={"kind": "literal", "value": "x" * 3_000_000})

    def forbidden_expansion(*args, **kwargs):
        pytest.fail("byte bound must reject the design before condition construction")

    monkeypatch.setattr(materialization, "_condition_bindings", forbidden_expansion)
    with pytest.raises(ValidationError, match="byte bound"):
        ExperimentSpecModel.model_validate(payload)


def test_author_names_mixed_scalar_effects_and_secret_references_are_preserved() -> None:
    payload = _typed_payload()
    design = payload["factorial_design"]
    for old, new in (("agent", "runner-v9"), ("path", "deployment-shape")):
        payload["factors"][new] = payload["factors"].pop(old)
        design["factor_ids"][design["factor_ids"].index(old)] = new
        design["level_effects"][new] = design["level_effects"].pop(old)
    for level, effects in design["level_effects"]["deployment-shape"].items():
        effects["bindings"] = _payload()["factorial_design"]["level_bindings"]["path"][level]
    secret = design["level_effects"]["runner-v9"]["warm"]["bindings"][0]
    secret["value"] = {"kind": "secret-reference", "reference_id": "operator-token"}
    spec = ExperimentSpecModel.model_validate(payload)
    assert all(
        set(a.factor_levels) == {"runner-v9", "deployment-shape"}
        for a in spec.run_plan.allocation.condition_assignments.values()
    )
    assert '"reference_id":"operator-token"' in spec.model_dump_json()
    secret["value"]["resolved_value"] = "sensitive-canary"
    from raes_contracts.experiment_spec import ExperimentSpecValidationError, parse_experiment_spec

    serialized = json.dumps(payload)
    with pytest.raises(ExperimentSpecValidationError) as caught:
        parse_experiment_spec(serialized)
    assert "sensitive-canary" not in str(caught.value)


def test_contract_member_reuses_sdl_node_presence_with_coupled_inventory() -> None:
    from raes import select_scenario_family
    from raes.canonical import canonical_sdl_digest
    from test_issue_1625_structural_variation import _family

    family = _family()
    payload = _typed_payload()
    for level, effects in payload["factorial_design"]["level_effects"]["path"].items():
        template = effects["selections"][0]
        template["target"].update(
            scenario_family_id=family.name, variation_point_id="host-state", target_id="nodes.host.presence"
        )
        template["scenario_family_digest"] = canonical_sdl_digest(family).value
        template["outcome"]["member_id"] = "absent" if level == "a" else "baseline"
    spec = ExperimentSpecModel.model_validate(payload)
    selected = {}
    for assignment in spec.run_plan.allocation.condition_assignments.values():
        criterion = assignment.required_selections[0]
        selected[criterion.outcome.member_id] = select_scenario_family(
            family, {criterion.target.variation_point_id: criterion.outcome}
        )
    assert selected["absent"].nodes == {}
    assert [job.scheduled_job_id for job in selected["baseline"].nodes["host"].runtime.scheduled_jobs] == ["baseline"]


def test_typed_profile_is_admitted_by_the_published_authoring_schema() -> None:
    from jsonschema import Draft202012Validator
    from paths import REPO_ROOT

    schema = json.loads(
        (REPO_ROOT / "contracts/schemas/experiment-core/experiment-authoring-input-v1.json").read_text()
    )
    Draft202012Validator(schema).validate(_typed_payload())


@pytest.mark.parametrize(
    "contract_id",
    ["experiment-authoring-input-v1", "experiment-study-v1", "experiment-run-v1", "admitted-trial-plan-v1"],
)
def test_published_typed_fixture_corpus_separates_shape_and_context(contract_id) -> None:
    from jsonschema import Draft202012Validator
    from paths import REPO_ROOT
    from raes_contracts.contracts import ExperimentStudyModel

    models = {
        "experiment-authoring-input-v1": ExperimentSpecModel,
        "experiment-study-v1": ExperimentStudyModel,
        "experiment-run-v1": ExperimentRunModel,
        "admitted-trial-plan-v1": AdmittedTrialPlanModel,
    }
    group = "plans" if contract_id == "admitted-trial-plan-v1" else "experiment-core"
    schema = json.loads((REPO_ROOT / "contracts/schemas" / group / f"{contract_id}.json").read_text())
    validator = Draft202012Validator(schema)
    root = REPO_ROOT / "contracts/fixtures" / group / contract_id
    for category in ("valid", "invalid", "context-invalid"):
        paths = [
            path
            for path in (root / category).glob("*.json")
            if "typed-" in path.name or path.stem == "unknown-treatment-profile"
        ]
        assert paths, (contract_id, category)
        for path in paths:
            payload = json.loads(path.read_text())
            assert validator.is_valid(payload) == (category != "invalid"), path
            if category == "valid":
                model = models[contract_id].model_validate(payload)
                rebuilt = models[contract_id].model_validate_json(model.model_dump_json())
                assert rebuilt.model_dump(mode="json") == model.model_dump(mode="json")
            else:
                with pytest.raises(ValidationError):
                    models[contract_id].model_validate(payload)
