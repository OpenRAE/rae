"""SCE-003 adaptive-difficulty policy and provenance contracts."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator
from paths import REPO_ROOT
from pydantic import ValidationError
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    ADAPTIVE_THRESHOLD_PROFILE_DIGEST,
    DifficultyActionModel,
    DifficultyAffectedReferenceModel,
    DifficultyDecisionRecordModel,
    DifficultyDecisionRequestModel,
    DifficultyDimensionModel,
    DifficultyInterventionRecordModel,
    DifficultyObservationInputModel,
    DifficultyObservationSourceModel,
    DifficultyPolicyBoundsModel,
    DifficultyPolicyModel,
    DifficultyPolicyRegistryModel,
    DifficultyRunProvenanceModel,
    DifficultySourceDefinitionReferenceModel,
    DifficultyStateCutModel,
    DifficultyThresholdRuleModel,
    DifficultyVariantModel,
    ExperimentReferenceModel,
    ExperimentRunModel,
    ExperimentSpecModel,
    ExperimentStudyModel,
    difficulty_decision_history_head,
    difficulty_policy_digest,
    resolve_difficulty_policy,
    schema_bundle,
    validate_experiment_difficulty_against_spec,
    validate_experiment_study_structure_against_tasks_and_runs,
)

_DIGEST_A = "sha256:" + "1" * 64
_DIGEST_B = "sha256:" + "2" * 64
_ADAPTIVE_FIXTURES = REPO_ROOT / "contracts" / "fixtures" / "experiment-core" / "adaptive-difficulty"


def _profile_ref(profile_id: str = "adaptive-threshold-v1") -> ExperimentReferenceModel:
    return ExperimentReferenceModel(
        ref_kind="profile",
        ref_id=profile_id,
        ref_version="1.0.0",
        ref_digest=ADAPTIVE_THRESHOLD_PROFILE_DIGEST,
    )


def _source_ref() -> DifficultySourceDefinitionReferenceModel:
    return DifficultySourceDefinitionReferenceModel(
        ref_kind="metric-definition",
        ref_id="objective-progress",
        ref_version="1.0.0",
        ref_digest=_DIGEST_B,
    )


def _adaptive_policy(*, condition: str = "adaptive") -> DifficultyPolicyModel:
    rule_id = "stalled" if condition == "scaffolded" else "objectives-met-quickly"
    action_id = "show-hint" if condition == "scaffolded" else "harder-follow-up"
    payload = {
        "policy_id": f"{condition}-standard",
        "policy_version": "1.0.0",
        "condition": condition,
        "baseline_variant_id": "standard",
        "evaluator_ref": _profile_ref().model_dump(mode="json"),
        "observation_sources": {
            "progress": DifficultyObservationSourceModel(
                source_id="progress",
                source_kind="derived-measure",
                source_ref=_source_ref(),
                visibility="participant-visible",
                maximum_age=1,
            ).model_dump(mode="json")
        },
        "threshold_rules": {
            rule_id: DifficultyThresholdRuleModel(
                rule_id=rule_id,
                observation_source_id="progress",
                operator="lte" if condition == "scaffolded" else "gte",
                threshold=0.25 if condition == "scaffolded" else 0.75,
                action_id=action_id,
                priority=1,
            ).model_dump(mode="json")
        },
        "actions": {
            action_id: DifficultyActionModel(
                action_id=action_id,
                action_kind="scaffold" if condition == "scaffolded" else "follow-up-trial",
                carrier_ref=("participant-context.restore-hints" if condition == "scaffolded" else None),
                target_variant_id="standard" if condition == "scaffolded" else "hard",
                affected_refs=(
                    [
                        DifficultyAffectedReferenceModel(
                            ref_kind="scaffold",
                            ref_id="workflow.restore.scaffold",
                        )
                    ]
                    if condition == "scaffolded"
                    else [
                        DifficultyAffectedReferenceModel(
                            ref_kind="scenario-variant",
                            ref_id="scenario-family.challenge-level",
                        )
                    ]
                ),
            ).model_dump(mode="json")
        },
        "bounds": DifficultyPolicyBoundsModel(
            maximum_interventions=2,
            minimum_decision_interval=1,
            cooldown=1,
            terminal_disposition="no-change",
        ).model_dump(mode="json"),
        "guardrails": ["Use only declared evidence and action carriers."],
        "validity_effect": "Adaptive treatment must be analyzed as a distinct condition.",
    }
    payload["policy_digest"] = difficulty_policy_digest(payload)
    return DifficultyPolicyModel.model_validate(payload)


def _fixed_policy() -> DifficultyPolicyModel:
    payload = {
        "policy_id": "fixed-standard",
        "policy_version": "1.0.0",
        "condition": "fixed",
        "baseline_variant_id": "standard",
        "bounds": DifficultyPolicyBoundsModel(
            maximum_interventions=0,
            minimum_decision_interval=0,
            cooldown=0,
            terminal_disposition="fixed",
        ).model_dump(mode="json"),
        "guardrails": ["The admitted baseline remains unchanged."],
        "validity_effect": "Fixed benchmark baseline.",
    }
    payload["policy_digest"] = difficulty_policy_digest(payload)
    return DifficultyPolicyModel.model_validate(payload)


def _registry() -> DifficultyPolicyRegistryModel:
    return DifficultyPolicyRegistryModel(
        dimensions={
            "challenge": DifficultyDimensionModel(
                dimension_id="challenge",
                ordered_variant_ids=["standard", "hard"],
                ordering_rationale="Policy-local challenge ordering for this experiment.",
            )
        },
        variants={
            "standard": DifficultyVariantModel(
                variant_id="standard",
                selection_policy_refs=["select-standard"],
                scaffold_refs=["participant-context.restore-hints"],
            ),
            "hard": DifficultyVariantModel(
                variant_id="hard",
                selection_policy_refs=["select-hard"],
            ),
        },
        policies={
            "fixed-standard": _fixed_policy(),
            "adaptive-standard": _adaptive_policy(),
            "scaffolded-standard": _adaptive_policy(condition="scaffolded"),
        },
        default_policy_id="fixed-standard",
    )


def _request(
    *,
    value: float = 0.75,
    cut: int = 4,
    expected_history_head: str | None = None,
    idempotency_key: str = "decision-1",
    run_id: str = "run-1",
    requested_at: str = "2026-07-30T10:00:00Z",
) -> DifficultyDecisionRequestModel:
    policy = _adaptive_policy()
    state_cut = DifficultyStateCutModel(
        order_domain="logical-step",
        coordinate=cut,
        episode_id="episode-1",
    )
    return DifficultyDecisionRequestModel(
        policy_id="adaptive-standard",
        policy_version="1.0.0",
        policy_digest=policy.policy_digest,
        run_id=run_id,
        state_cut=state_cut,
        observation_inputs=[
            DifficultyObservationInputModel(
                source_id="progress",
                source_ref=_source_ref(),
                run_id=run_id,
                evidence_ref=ExperimentReferenceModel(
                    ref_kind="derived-measure",
                    ref_id=f"progress-at-{cut}",
                    ref_version="1.0.0",
                    ref_digest=_DIGEST_A,
                ),
                observed_cut=state_cut,
                value=value,
            )
        ],
        intervention_count=0,
        expected_history_head=expected_history_head,
        idempotency_key=idempotency_key,
        requested_at=requested_at,
    )


def _fixture(contract_id: str) -> dict:
    path = REPO_ROOT / "contracts" / "fixtures" / "experiment-core" / contract_id / "valid" / "reference.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _adaptive_fixture(name: str) -> dict:
    return json.loads((_ADAPTIVE_FIXTURES / name).read_text(encoding="utf-8"))


def _registry_payload() -> dict:
    return _registry().model_dump(mode="json")


def _add_selection_policies(run_plan: dict) -> None:
    run_plan["selection_policies"] = {
        "select-standard": {
            "kind": "fixed",
            "policy_id": "select-standard",
            "purpose": "fixed-configuration",
            "point_ref": "challenge-level",
            "outcome": {"kind": "literal", "value": "standard"},
            "output_bound": 1,
        },
        "select-hard": {
            "kind": "fixed",
            "policy_id": "select-hard",
            "purpose": "fixed-configuration",
            "point_ref": "challenge-level",
            "outcome": {"kind": "literal", "value": "hard"},
            "output_bound": 1,
        },
    }


def _adaptive_spec_payload() -> dict:
    payload = _fixture("experiment-authoring-input-v1")
    _add_selection_policies(payload["run_plan"])
    payload["run_plan"]["difficulty_policy_registry"] = _registry_payload()
    assignments = payload["run_plan"]["allocation"]["condition_assignments"]
    assignments["cond-aggressive"]["difficulty_condition"] = "fixed"
    assignments["cond-aggressive"]["difficulty_policy_id"] = "fixed-standard"
    assignments["cond-stealthy"]["difficulty_condition"] = "adaptive"
    assignments["cond-stealthy"]["difficulty_policy_id"] = "adaptive-standard"
    return payload


def _adaptive_run_payload() -> dict:
    payload = _fixture("experiment-run-v1")
    run_id = payload["run_id"]
    decision = resolve_difficulty_policy(
        _adaptive_policy(),
        _request(run_id=run_id, requested_at="2026-05-26T00:20:00Z"),
        prior_decisions=[],
    ).decision
    assert decision is not None
    payload["difficulty_provenance"] = DifficultyRunProvenanceModel(
        design_ref=ExperimentReferenceModel(
            ref_kind="authoring-input",
            ref_id="spec-techvault-red-tactic-sweep-v1",
            ref_version="1.0.0",
            ref_digest=_DIGEST_A,
        ),
        policy=_adaptive_policy(),
        baseline_variant_id="standard",
        decisions=[decision],
        interventions=[],
        comparison_disposition="adaptation-is-treatment",
        validity_disclosure="The adaptive policy is a distinct treatment.",
    ).model_dump(mode="json")
    return payload


def test_policy_registry_defaults_to_fixed_and_uses_declared_variants() -> None:
    registry = _registry()

    assert registry.policies[registry.default_policy_id].condition == "fixed"
    assert registry.policies["adaptive-standard"].actions["harder-follow-up"].target_variant_id == "hard"

    payload = registry.model_dump(mode="json")
    payload["default_policy_id"] = "adaptive-standard"
    with pytest.raises(ValidationError, match="default difficulty policy must be fixed"):
        DifficultyPolicyRegistryModel.model_validate(payload)

    payload = registry.model_dump(mode="json")
    payload["policies"]["adaptive-standard"]["actions"]["harder-follow-up"]["target_variant_id"] = "undeclared"
    payload["policies"]["adaptive-standard"]["policy_digest"] = difficulty_policy_digest(
        payload["policies"]["adaptive-standard"]
    )
    with pytest.raises(ValidationError, match="declared difficulty variant"):
        DifficultyPolicyRegistryModel.model_validate(payload)

    payload = registry.model_dump(mode="json")
    payload["policies"]["scaffolded-standard"]["actions"]["show-hint"]["carrier_ref"] = "undeclared-carrier"
    payload["policies"]["scaffolded-standard"]["policy_digest"] = difficulty_policy_digest(
        payload["policies"]["scaffolded-standard"]
    )
    with pytest.raises(ValidationError, match="declared difficulty carrier"):
        DifficultyPolicyRegistryModel.model_validate(payload)

    payload = registry.model_dump(mode="json")
    payload["variants"]["standard"]["scaffold_refs"] = []
    payload["variants"]["hard"]["scaffold_refs"] = ["participant-context.restore-hints"]
    with pytest.raises(ValidationError, match="baseline difficulty variant"):
        DifficultyPolicyRegistryModel.model_validate(payload)


@pytest.mark.parametrize(
    "carrier_ref",
    ["https://controller.example/action", "workflow action"],
)
def test_policy_registry_rejects_executable_or_ambiguous_carrier_references(
    carrier_ref: str,
) -> None:
    payload = _registry_payload()
    payload["variants"]["standard"]["scaffold_refs"] = [carrier_ref]

    with pytest.raises(ValidationError, match="stable non-executable references"):
        DifficultyPolicyRegistryModel.model_validate(payload)


def test_fixed_policy_rejects_hidden_intervention_authority() -> None:
    payload = _fixed_policy().model_dump(mode="json")
    payload["evaluator_ref"] = _profile_ref().model_dump(mode="json")
    payload["actions"] = {
        "hidden": DifficultyActionModel(
            action_id="hidden",
            action_kind="workflow-action",
            carrier_ref="workflow.hidden",
            target_variant_id="standard",
            affected_refs=[
                DifficultyAffectedReferenceModel(
                    ref_kind="workflow-action",
                    ref_id="workflow.hidden",
                )
            ],
        ).model_dump(mode="json")
    }

    with pytest.raises(ValidationError, match="fixed difficulty policies"):
        DifficultyPolicyModel.model_validate(payload)


def test_policy_digest_binds_the_complete_immutable_declaration() -> None:
    payload = _adaptive_policy().model_dump(mode="json")
    payload["guardrails"] = ["A substituted policy body."]

    with pytest.raises(ValidationError, match="policy_digest must match"):
        DifficultyPolicyModel.model_validate(payload)


def test_policy_authority_uses_portable_governed_identifiers() -> None:
    payload = _adaptive_policy().model_dump(mode="json")
    payload["policy_id"] = "https://controller.example/policy"
    payload["policy_digest"] = difficulty_policy_digest(payload)
    with pytest.raises(ValidationError, match="portable SDL identifier"):
        DifficultyPolicyModel.model_validate(payload)

    payload = _adaptive_policy().model_dump(mode="json")
    payload["evaluator_ref"]["ref_id"] = "latest"
    payload["policy_digest"] = difficulty_policy_digest(payload)
    with pytest.raises(ValidationError, match="stable governed profile id"):
        DifficultyPolicyModel.model_validate(payload)

    for missing_identity_field in ("ref_version", "ref_digest"):
        payload = _adaptive_policy().model_dump(mode="json")
        payload["observation_sources"]["progress"]["source_ref"][missing_identity_field] = None
        with pytest.raises(ValidationError, match="source definition references must be versioned and digest-bound"):
            DifficultyPolicyModel.model_validate(payload)

    payload = _adaptive_policy().model_dump(mode="json")
    payload["observation_sources"]["progress"]["source_ref"]["ref_path"] = "mutable/measure.json"
    with pytest.raises(ValidationError, match="source definition references must not depend on mutable paths"):
        DifficultyPolicyModel.model_validate(payload)


def test_published_schema_requires_exact_source_definition_identity() -> None:
    validator = Draft202012Validator(schema_bundle()["experiment-authoring-input-v1"])
    payload = _adaptive_spec_payload()
    assert validator.is_valid(payload)

    for invalid_field, invalid_value in (
        ("ref_version", None),
        ("ref_digest", None),
        ("ref_path", "mutable/measure.json"),
    ):
        invalid = deepcopy(payload)
        source_ref = invalid["run_plan"]["difficulty_policy_registry"]["policies"]["adaptive-standard"][
            "observation_sources"
        ]["progress"]["source_ref"]
        source_ref[invalid_field] = invalid_value
        assert not validator.is_valid(invalid)


def test_difficulty_actions_enforce_closed_carriers_and_follow_up_authority() -> None:
    scaffold_ref = DifficultyAffectedReferenceModel(
        ref_kind="scaffold",
        ref_id="workflow.restore.scaffold",
    )
    with pytest.raises(ValidationError, match="affected_refs must be unique"):
        DifficultyActionModel(
            action_id="duplicate-scaffold",
            action_kind="scaffold",
            carrier_ref="participant-context.restore-hints",
            affected_refs=[scaffold_ref, scaffold_ref],
        )

    mismatched_ref = DifficultyAffectedReferenceModel(
        ref_kind="workflow-action",
        ref_id="workflow.restore.scaffold",
    )
    with pytest.raises(ValidationError, match="must match the closed action carrier kind"):
        DifficultyActionModel(
            action_id="mismatched-carrier",
            action_kind="scaffold",
            carrier_ref="participant-context.restore-hints",
            affected_refs=[mismatched_ref],
        )

    follow_up_ref = DifficultyAffectedReferenceModel(
        ref_kind="scenario-variant",
        ref_id="scenario-family.challenge-level",
    )
    with pytest.raises(
        ValidationError,
        match="require target_variant_id and forbid carrier_ref",
    ):
        DifficultyActionModel(
            action_id="effect-capable-follow-up",
            action_kind="follow-up-trial",
            carrier_ref="workflow.launch-follow-up",
            target_variant_id="hard",
            affected_refs=[follow_up_ref],
        )

    with pytest.raises(ValidationError, match="require a declared carrier_ref"):
        DifficultyActionModel(
            action_id="carrierless-scaffold",
            action_kind="scaffold",
            affected_refs=[scaffold_ref],
        )


def test_policy_rejects_coercive_ordered_thresholds_and_nonfinite_observations() -> None:
    with pytest.raises(ValidationError, match="ordered difficulty thresholds must be finite numbers"):
        DifficultyThresholdRuleModel(
            rule_id="invalid",
            observation_source_id="progress",
            operator="gte",
            threshold="0.75",
            action_id="harder-follow-up",
            priority=1,
        )

    with pytest.raises(ValidationError, match="ordered difficulty thresholds must be finite numbers"):
        DifficultyThresholdRuleModel(
            rule_id="invalid-boolean",
            observation_source_id="progress",
            operator="gte",
            threshold=True,
            action_id="harder-follow-up",
            priority=1,
        )

    boolean_observation = resolve_difficulty_policy(
        _adaptive_policy(),
        _request(value=True),
        prior_decisions=[],
    )
    assert boolean_observation.decision is not None
    assert boolean_observation.decision.disposition == "no-change"
    assert boolean_observation.decision.trigger_rule_id is None

    payload = _request().model_dump(mode="json")
    payload["observation_inputs"][0]["value"] = float("inf")
    with pytest.raises(ValidationError, match="observation values must be finite"):
        DifficultyDecisionRequestModel.model_validate(payload)

    payload = _request().model_dump(mode="json")
    payload["observation_inputs"][0]["evidence_ref"]["ref_version"] = None
    payload["observation_inputs"][0]["evidence_ref"]["ref_digest"] = None
    with pytest.raises(ValidationError, match="versioned or digest-bound"):
        DifficultyDecisionRequestModel.model_validate(payload)


def test_positive_boundary_unsupported_and_policy_violation_fixtures() -> None:
    policy = DifficultyPolicyModel.model_validate(_adaptive_fixture("policy.json"))
    positive = DifficultyDecisionRequestModel.model_validate(_adaptive_fixture("positive.json"))
    selected = resolve_difficulty_policy(policy, positive, prior_decisions=[])
    assert selected.decision is not None
    assert selected.decision.disposition == "selected"

    boundary = DifficultyDecisionRequestModel.model_validate(_adaptive_fixture("boundary.json"))
    terminal = resolve_difficulty_policy(policy, boundary, prior_decisions=[])
    assert terminal.decision is not None
    assert terminal.decision.disposition == "terminal"

    unsupported_policy = DifficultyPolicyModel.model_validate(_adaptive_fixture("unsupported.json"))
    unsupported_request = positive.model_copy(
        update={
            "policy_id": unsupported_policy.policy_id,
            "policy_version": unsupported_policy.policy_version,
            "policy_digest": unsupported_policy.policy_digest,
            "idempotency_key": "unsupported-1",
        }
    )
    unsupported = resolve_difficulty_policy(
        unsupported_policy,
        unsupported_request,
        prior_decisions=[],
    )
    assert unsupported.decision is not None
    assert unsupported.decision.disposition == "unsupported"

    substituted_source = unsupported_request.model_copy(deep=True)
    substituted_source.observation_inputs[0].__dict__["source_ref"] = DifficultySourceDefinitionReferenceModel(
        ref_kind="metric-definition",
        ref_id="different-progress-measure",
        ref_version="1.0.0",
        ref_digest=_DIGEST_B,
    )
    rejected = resolve_difficulty_policy(
        unsupported_policy,
        substituted_source,
        prior_decisions=[],
    )
    assert rejected.decision is None
    assert rejected.diagnostics[0].code == "difficulty.observation-source-mismatch"

    policy_violation = _adaptive_fixture("policy-violation.json")
    with pytest.raises(ValidationError, match="threshold rules must reference declared actions"):
        DifficultyPolicyModel.model_validate(policy_violation)


def test_exact_threshold_selects_one_declared_action_without_performing_it() -> None:
    result = resolve_difficulty_policy(_adaptive_policy(), _request(), prior_decisions=[])

    assert result.diagnostics == []
    assert result.decision is not None
    assert result.decision.disposition == "selected"
    assert result.decision.trigger_rule_id == "objectives-met-quickly"
    assert result.decision.selected_action_id == "harder-follow-up"
    assert result.decision.affected_refs[0].ref_id == "scenario-family.challenge-level"
    assert result.decision.observation_refs[0].source_id == "progress"
    assert result.decision.observation_refs[0].observed_cut.coordinate == 4
    assert result.decision.observation_refs[0].evidence_ref.ref_id == "progress-at-4"


def test_fixed_policy_resolves_without_observations_or_intervention_authority() -> None:
    fixed = _fixed_policy()
    request = _request().model_copy(
        update={
            "policy_id": fixed.policy_id,
            "policy_digest": fixed.policy_digest,
            "observation_inputs": [],
        }
    )

    result = resolve_difficulty_policy(fixed, request, prior_decisions=[])

    assert result.decision is not None
    assert result.decision.disposition == "fixed"
    assert result.decision.selected_action_id is None

    hidden_input_request = _request().model_copy(
        update={
            "policy_id": fixed.policy_id,
            "policy_digest": fixed.policy_digest,
        }
    )
    rejected = resolve_difficulty_policy(fixed, hidden_input_request, prior_decisions=[])
    assert rejected.decision is None
    assert rejected.diagnostics[0].code == "difficulty.fixed-authority-invalid"


def test_no_trigger_and_intervention_boundaries_are_explicit() -> None:
    no_trigger = resolve_difficulty_policy(_adaptive_policy(), _request(value=0.749), prior_decisions=[])
    assert no_trigger.decision is not None
    assert no_trigger.decision.disposition == "no-change"
    assert no_trigger.decision.selected_action_id is None

    capped_request = _request().model_copy(update={"intervention_count": 2})
    capped = resolve_difficulty_policy(_adaptive_policy(), capped_request, prior_decisions=[])
    assert capped.decision is not None
    assert capped.decision.disposition == "terminal"
    assert capped.decision.selected_action_id is None


def test_scaffolded_policy_selects_declared_guidance_when_progress_stalls() -> None:
    policy = _adaptive_policy(condition="scaffolded")
    request = _request(value=0.25).model_copy(
        update={
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "policy_digest": policy.policy_digest,
        }
    )

    result = resolve_difficulty_policy(policy, request, prior_decisions=[])

    assert result.decision is not None
    assert result.decision.selected_action_id == "show-hint"
    assert result.decision.affected_refs[0].ref_kind == "scaffold"
    assert '"value"' not in result.decision.model_dump_json()


def test_resolver_replays_identical_requests_and_rejects_conflicting_replay() -> None:
    policy = _adaptive_policy()
    first = resolve_difficulty_policy(policy, _request(), prior_decisions=[])
    assert first.decision is not None

    replay = resolve_difficulty_policy(policy, _request(), prior_decisions=[first.decision])
    assert replay.decision == first.decision

    conflicting = resolve_difficulty_policy(
        policy,
        _request(value=0.9),
        prior_decisions=[first.decision],
    )
    assert conflicting.decision is None
    assert [diagnostic.code for diagnostic in conflicting.diagnostics] == ["difficulty.idempotency-conflict"]


def test_resolver_rejects_stale_history_and_unsupported_profile_without_fallback() -> None:
    policy = _adaptive_policy()
    first = resolve_difficulty_policy(policy, _request(), prior_decisions=[])
    assert first.decision is not None

    stale = resolve_difficulty_policy(
        policy,
        _request(cut=6, expected_history_head="sha256:" + "f" * 64, idempotency_key="decision-2"),
        prior_decisions=[first.decision],
    )
    assert stale.decision is None
    assert stale.diagnostics[0].code == "difficulty.history-conflict"

    unsupported_payload = policy.model_dump(mode="json")
    unsupported_payload["evaluator_ref"] = _profile_ref("unsupported-profile-v1").model_dump(mode="json")
    unsupported_payload["policy_digest"] = difficulty_policy_digest(unsupported_payload)
    unsupported_policy = DifficultyPolicyModel.model_validate(unsupported_payload)
    unsupported_request = _request().model_copy(update={"policy_digest": unsupported_policy.policy_digest})
    unsupported = resolve_difficulty_policy(
        unsupported_policy,
        unsupported_request,
        prior_decisions=[],
    )
    assert unsupported.decision is not None
    assert unsupported.decision.disposition == "unsupported"
    assert unsupported.decision.selected_action_id is None

    substituted_digest_payload = policy.model_dump(mode="json")
    substituted_digest_payload["evaluator_ref"]["ref_digest"] = _DIGEST_B
    substituted_digest_payload["policy_digest"] = difficulty_policy_digest(substituted_digest_payload)
    substituted_digest_policy = DifficultyPolicyModel.model_validate(substituted_digest_payload)
    substituted_digest_request = _request().model_copy(
        update={"policy_digest": substituted_digest_policy.policy_digest}
    )
    substituted_digest = resolve_difficulty_policy(
        substituted_digest_policy,
        substituted_digest_request,
        prior_decisions=[],
    )
    assert substituted_digest.decision is not None
    assert substituted_digest.decision.disposition == "unsupported"


def test_resolver_rejects_a_discontinuous_or_foreign_prior_history() -> None:
    policy = _adaptive_policy()
    first = resolve_difficulty_policy(policy, _request(), prior_decisions=[]).decision
    assert first is not None
    second_request = _request(
        cut=6,
        expected_history_head=first.history_head,
        idempotency_key="decision-2",
    )
    second = resolve_difficulty_policy(policy, second_request, prior_decisions=[first]).decision
    assert second is not None

    request = _request(
        cut=8,
        expected_history_head=second.history_head,
        idempotency_key="decision-3",
    )
    discontinuous = resolve_difficulty_policy(policy, request, prior_decisions=[second])
    assert discontinuous.decision is None
    assert discontinuous.diagnostics[0].code == "difficulty.history-conflict"

    foreign = first.model_copy(update={"run_id": "other-run"})
    result = resolve_difficulty_policy(
        policy,
        request.model_copy(update={"expected_history_head": foreign.history_head}),
        prior_decisions=[foreign],
    )
    assert result.decision is None
    assert result.diagnostics[0].code == "difficulty.history-conflict"


def test_resolver_rejects_cross_run_future_and_stale_observation_inputs() -> None:
    policy = _adaptive_policy()
    cross_run = _request().model_copy(deep=True)
    cross_run.observation_inputs[0].__dict__["run_id"] = "other-run"
    result = resolve_difficulty_policy(policy, cross_run, prior_decisions=[])
    assert result.decision is None
    assert result.diagnostics[0].code == "difficulty.observation-cut-invalid"

    future = _request().model_copy(deep=True)
    future.observation_inputs[0].__dict__["observed_cut"] = DifficultyStateCutModel(
        order_domain="logical-step",
        coordinate=5,
        episode_id="episode-1",
    )
    result = resolve_difficulty_policy(policy, future, prior_decisions=[])
    assert result.decision is None
    assert result.diagnostics[0].code == "difficulty.observation-cut-invalid"

    stale = _request(cut=6).model_copy(deep=True)
    stale.observation_inputs[0].__dict__["observed_cut"] = DifficultyStateCutModel(
        order_domain="logical-step",
        coordinate=4,
        episode_id="episode-1",
    )
    result = resolve_difficulty_policy(policy, stale, prior_decisions=[])
    assert result.decision is None
    assert result.diagnostics[0].code == "difficulty.observation-cut-invalid"

    substituted_source = _request().model_copy(deep=True)
    substituted_source.observation_inputs[0].__dict__["source_ref"] = DifficultySourceDefinitionReferenceModel(
        ref_kind="metric-definition",
        ref_id="different-progress-measure",
        ref_version="1.0.0",
        ref_digest=_DIGEST_B,
    )
    result = resolve_difficulty_policy(policy, substituted_source, prior_decisions=[])
    assert result.decision is None
    assert result.diagnostics[0].code == "difficulty.observation-source-mismatch"


def test_cooldown_denies_early_repeat_and_allows_the_exact_boundary() -> None:
    policy_payload = _adaptive_policy().model_dump(mode="json")
    policy_payload["bounds"]["cooldown"] = 2
    policy_payload["policy_digest"] = difficulty_policy_digest(policy_payload)
    policy = DifficultyPolicyModel.model_validate(policy_payload)
    first_request = _request().model_copy(update={"policy_digest": policy.policy_digest})
    first = resolve_difficulty_policy(policy, first_request, prior_decisions=[]).decision
    assert first is not None

    early_request = _request(
        cut=5,
        idempotency_key="decision-2",
        expected_history_head=first.history_head,
    ).model_copy(update={"policy_digest": policy.policy_digest})
    early = resolve_difficulty_policy(policy, early_request, prior_decisions=[first])
    assert early.decision is not None
    assert early.decision.disposition == "denied"

    boundary_request = _request(
        cut=6,
        idempotency_key="decision-3",
        expected_history_head=first.history_head,
    ).model_copy(update={"policy_digest": policy.policy_digest})
    boundary = resolve_difficulty_policy(policy, boundary_request, prior_decisions=[first])
    assert boundary.decision is not None
    assert boundary.decision.disposition == "selected"


def test_adaptive_run_provenance_is_append_only_and_fixed_runs_have_no_interventions() -> None:
    decision = resolve_difficulty_policy(_adaptive_policy(), _request(), prior_decisions=[]).decision
    assert decision is not None
    provenance = DifficultyRunProvenanceModel(
        design_ref=ExperimentReferenceModel(
            ref_kind="authoring-input",
            ref_id="adaptive-study",
            ref_version="1.0.0",
            ref_digest=_DIGEST_A,
        ),
        policy=_adaptive_policy(),
        baseline_variant_id="standard",
        decisions=[decision],
        interventions=[],
        comparison_disposition="adaptation-is-treatment",
        validity_disclosure="The selected policy changes treatment relative to fixed runs.",
    )

    assert provenance.decisions[0].run_id == "run-1"

    mislabeled = provenance.model_dump(mode="json")
    mislabeled["comparison_disposition"] = "scaffold-exposure-is-treatment"
    with pytest.raises(ValidationError, match="adaptive policy treatment"):
        DifficultyRunProvenanceModel.model_validate(mislabeled)

    fixed_payload = provenance.model_dump(mode="json")
    fixed_payload["policy"] = _fixed_policy().model_dump(mode="json")
    with pytest.raises(ValidationError, match="fixed difficulty provenance"):
        DifficultyRunProvenanceModel.model_validate(fixed_payload)

    reordered = deepcopy(provenance.model_dump(mode="json"))
    reordered["decisions"].append(deepcopy(reordered["decisions"][0]))
    reordered["decisions"][1]["decision_id"] = "decision-duplicate-cut"
    reordered["decisions"][1]["history_head"] = difficulty_decision_history_head(reordered["decisions"][1])
    with pytest.raises(ValidationError, match="strictly increasing state cuts"):
        DifficultyRunProvenanceModel.model_validate(reordered)

    substituted = deepcopy(provenance.model_dump(mode="json"))
    substituted["decisions"][0]["affected_refs"][0]["ref_id"] = "substituted-target"
    with pytest.raises(ValidationError, match="history_head must match"):
        DifficultyRunProvenanceModel.model_validate(substituted)

    substituted["decisions"][0]["history_head"] = difficulty_decision_history_head(substituted["decisions"][0])
    with pytest.raises(ValidationError, match="declared policy action"):
        DifficultyRunProvenanceModel.model_validate(substituted)

    substituted_source = deepcopy(provenance.model_dump(mode="json"))
    substituted_source["decisions"][0]["observation_refs"][0]["source_ref"]["ref_id"] = "different-progress-measure"
    substituted_source["decisions"][0]["history_head"] = difficulty_decision_history_head(
        substituted_source["decisions"][0]
    )
    with pytest.raises(ValidationError, match="exact policy source definitions"):
        DifficultyRunProvenanceModel.model_validate(substituted_source)

    undeclared_action = deepcopy(provenance.model_dump(mode="json"))
    undeclared_action["decisions"][0]["selected_action_id"] = "undeclared-action"
    undeclared_action["decisions"][0]["history_head"] = difficulty_decision_history_head(
        undeclared_action["decisions"][0]
    )
    with pytest.raises(ValidationError, match="declared policy rule and action"):
        DifficultyRunProvenanceModel.model_validate(undeclared_action)

    incoherent = decision.model_dump(mode="json")
    incoherent["disposition"] = "no-change"
    incoherent["history_head"] = difficulty_decision_history_head(incoherent)
    with pytest.raises(ValidationError, match="selected actions require selected disposition"):
        DifficultyDecisionRecordModel.model_validate(incoherent)


def test_follow_up_intervention_requires_a_distinct_run_identity() -> None:
    policy = _adaptive_policy()
    decision = resolve_difficulty_policy(policy, _request(), prior_decisions=[]).decision
    assert decision is not None
    intervention = DifficultyInterventionRecordModel(
        intervention_id="follow-up-1",
        decision_id=decision.decision_id,
        run_id=decision.run_id,
        action_id="harder-follow-up",
        occurred_at="2026-07-30T10:00:01Z",
        disposition="realized",
        affected_refs=policy.actions["harder-follow-up"].affected_refs,
        follow_up_run_ref=ExperimentReferenceModel(ref_kind="run", ref_id=decision.run_id),
    )
    payload = {
        "design_ref": {
            "ref_kind": "authoring-input",
            "ref_id": "adaptive-study",
            "ref_version": "1.0.0",
            "ref_digest": _DIGEST_A,
        },
        "policy": policy.model_dump(mode="json"),
        "baseline_variant_id": "standard",
        "decisions": [decision.model_dump(mode="json")],
        "interventions": [intervention.model_dump(mode="json")],
        "comparison_disposition": "adaptation-is-treatment",
        "validity_disclosure": "The follow-up is a distinct adaptive treatment.",
    }
    with pytest.raises(ValidationError, match="follow-up run identity must differ"):
        DifficultyRunProvenanceModel.model_validate(payload)

    payload["interventions"][0]["follow_up_run_ref"]["ref_id"] = "run-2"
    provenance = DifficultyRunProvenanceModel.model_validate(payload)
    assert provenance.interventions[0].follow_up_run_ref.ref_id == "run-2"


def test_experiment_authoring_requires_declared_condition_policy_and_selection_joins() -> None:
    spec = ExperimentSpecModel.model_validate(_adaptive_spec_payload())
    assignment = spec.run_plan.allocation.condition_assignments["cond-stealthy"]
    assert assignment.difficulty_condition == "adaptive"
    assert assignment.difficulty_policy_id == "adaptive-standard"

    missing_policy = _adaptive_spec_payload()
    del missing_policy["run_plan"]["allocation"]["condition_assignments"]["cond-stealthy"]["difficulty_policy_id"]
    with pytest.raises(ValidationError, match="adaptive and scaffolded conditions require difficulty_policy_id"):
        ExperimentSpecModel.model_validate(missing_policy)

    undeclared_selection = _adaptive_spec_payload()
    del undeclared_selection["run_plan"]["selection_policies"]["select-hard"]
    with pytest.raises(ValidationError, match="difficulty variants must reference declared selection policies"):
        ExperimentSpecModel.model_validate(undeclared_selection)


def test_run_rejects_cross_run_or_retroactive_difficulty_decisions() -> None:
    payload = _adaptive_run_payload()
    run = ExperimentRunModel.model_validate(payload)
    assert run.difficulty_provenance.policy.condition == "adaptive"

    cross_run = deepcopy(payload)
    cross_run["difficulty_provenance"]["decisions"][0]["run_id"] = "other-run"
    cross_run["difficulty_provenance"]["decisions"][0]["observation_refs"][0]["run_id"] = "other-run"
    cross_run["difficulty_provenance"]["decisions"][0]["history_head"] = difficulty_decision_history_head(
        cross_run["difficulty_provenance"]["decisions"][0]
    )
    with pytest.raises(ValidationError, match="difficulty decisions must match the archival run_id"):
        ExperimentRunModel.model_validate(cross_run)

    retroactive = deepcopy(payload)
    retroactive["difficulty_provenance"]["decisions"][0]["decided_at"] = "2026-05-25T23:59:59Z"
    retroactive["difficulty_provenance"]["decisions"][0]["history_head"] = difficulty_decision_history_head(
        retroactive["difficulty_provenance"]["decisions"][0]
    )
    with pytest.raises(ValidationError, match="difficulty decision timing must be within the run"):
        ExperimentRunModel.model_validate(retroactive)


def test_run_admission_requires_the_exact_authored_difficulty_policy_snapshot() -> None:
    spec = ExperimentSpecModel.model_validate(_adaptive_spec_payload())
    run_payload = _adaptive_run_payload()
    run_payload["difficulty_provenance"]["design_ref"]["ref_digest"] = canonical_json_digest(
        spec.model_dump(mode="json")
    )
    run = ExperimentRunModel.model_validate(run_payload)

    validate_experiment_difficulty_against_spec(spec, run, "cond-stealthy")

    with pytest.raises(ValueError, match="difficulty condition"):
        validate_experiment_difficulty_against_spec(spec, run, "cond-aggressive")

    substituted_spec_payload = _adaptive_spec_payload()
    substituted_policy = substituted_spec_payload["run_plan"]["difficulty_policy_registry"]["policies"][
        "adaptive-standard"
    ]
    substituted_policy["guardrails"] = ["A different admitted policy body."]
    substituted_policy["policy_digest"] = difficulty_policy_digest(substituted_policy)
    substituted_spec = ExperimentSpecModel.model_validate(substituted_spec_payload)
    substituted_run_payload = _adaptive_run_payload()
    substituted_run_payload["difficulty_provenance"]["design_ref"]["ref_digest"] = canonical_json_digest(
        substituted_spec.model_dump(mode="json")
    )
    substituted_run = ExperimentRunModel.model_validate(substituted_run_payload)

    with pytest.raises(ValueError, match="exact admitted policy snapshot"):
        validate_experiment_difficulty_against_spec(
            substituted_spec,
            substituted_run,
            "cond-stealthy",
        )


def test_run_admission_rejects_a_substituted_authoring_design_digest() -> None:
    spec = ExperimentSpecModel.model_validate(_adaptive_spec_payload())
    run = ExperimentRunModel.model_validate(_adaptive_run_payload())

    with pytest.raises(ValueError, match="authoring design reference"):
        validate_experiment_difficulty_against_spec(spec, run, "cond-stealthy")


def test_study_allocation_distinguishes_fixed_and_adaptive_treatments() -> None:
    run_payload = _adaptive_run_payload()
    run = ExperimentRunModel.model_validate(run_payload)
    study_payload = _fixture("experiment-study-v1")
    study_payload["membership"]["run-001"]["grouping"] = "baseline"
    assignment = study_payload["run_allocation"]["condition_assignments"]["baseline"]
    assignment["difficulty_condition"] = "adaptive"
    assignment["difficulty_policy_id"] = "adaptive-standard"
    study_payload["validity_notes"].append(
        {
            "category": "internal",
            "note": "Adaptive treatment paths are analyzed separately from fixed baselines.",
        }
    )
    study = ExperimentStudyModel.model_validate(study_payload)

    task_payload = _fixture("experiment-task-v1")
    from raes_contracts.contracts import ExperimentTaskModel

    task = ExperimentTaskModel.model_validate(task_payload)
    validate_experiment_study_structure_against_tasks_and_runs(study, [task], [run])

    fixed_study = study.model_copy(deep=True)
    fixed_study.run_allocation.condition_assignments["baseline"].__dict__["difficulty_condition"] = "fixed"
    fixed_study.run_allocation.condition_assignments["baseline"].__dict__["difficulty_policy_id"] = None
    with pytest.raises(ValueError, match="must satisfy their condition assignments"):
        validate_experiment_study_structure_against_tasks_and_runs(fixed_study, [task], [run])


def test_nonfixed_collection_requires_analysis_and_validity_treatment() -> None:
    payload = _fixture("experiment-study-v1")
    payload["study_kind"] = "collection"
    assignment = payload["run_allocation"]["condition_assignments"]["baseline"]
    assignment["difficulty_condition"] = "adaptive"
    assignment["difficulty_policy_id"] = "adaptive-standard"
    payload["analysis_plan"] = None
    payload["validity_notes"] = []

    with pytest.raises(ValidationError, match="adaptive and scaffolded studies require"):
        ExperimentStudyModel.model_validate(payload)
