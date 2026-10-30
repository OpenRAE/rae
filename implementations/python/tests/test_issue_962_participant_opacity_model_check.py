"""SEM-231/ASR-535 finite-state participant-opacity model checking."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError
from raes_conformance.conformance import _fixture_case_diagnostics
from raes_contracts.behavioral_relation_profiles import (
    BehavioralRelationProfileModel,
    load_behavioral_relation_profile_revision,
)
from raes_contracts.behavioral_relations import (
    BehavioralRelationCatalogModel,
    load_behavioral_relation_catalog_revision,
)
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.base import BehavioralClaimBindingModel
from raes_contracts.contracts.bundle import schema_bundle
from raes_contracts.participant_opacity import (
    MODEL_CHECK_PROVENANCE_NONCLAIM,
    NORMALIZED_INPUT_PROVENANCE_NONCLAIM,
    OpacityPossiblePointModel,
    ParticipantOpacityAnalysisInputModel,
    ParticipantOpacityDeclaredCountsModel,
    ParticipantOpacityModelAssumptionsModel,
    ParticipantOpacityModelCheckDeclaredCountsModel,
    ParticipantOpacityModelCheckEvidenceModel,
    ParticipantOpacityModelCheckInputModel,
    ParticipantOpacityModelCheckOutcome,
    ParticipantOpacityModelStateModel,
    ParticipantOpacityModelTransitionModel,
)
from raes_contracts.satisfiability import SourceArtifactIdentityModel
from raes_processor.participant_opacity import (
    ParticipantOpacityEvidenceError,
    ParticipantOpacityInputError,
    ParticipantOpacityOperationalError,
    analyze_participant_opacity_input,
    model_check_participant_opacity_file,
    model_check_participant_opacity_input,
    replay_participant_opacity_model_check_evidence,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROFILE_ID = "participant-opacity-baseline-v1"
PROFILE_REVISION = "sem-231/rev2"


def _historical_profile() -> BehavioralRelationProfileModel:
    return load_behavioral_relation_profile_revision(PROFILE_ID, PROFILE_REVISION)


def _historical_catalog() -> BehavioralRelationCatalogModel:
    return load_behavioral_relation_catalog_revision("rev8")


def _claim(
    profile: BehavioralRelationProfileModel,
    catalog: BehavioralRelationCatalogModel,
    *,
    quantifier_scope: str = "all-traces",
) -> BehavioralClaimBindingModel:
    return BehavioralClaimBindingModel(
        taxonomy_id=catalog.taxonomy_id,
        taxonomy_revision=catalog.taxonomy_revision,
        relation_id="participant-predicate-opacity",
        subject="The exact complete finite participant-opacity transition model.",
        left_carrier_ref=profile.left_carrier_ref,
        observation_projection_ref=profile.observation_projection_ref,
        observation_projection_revision=profile.observation_projection_revision,
        relation_parameter_profile_ref=profile.profile_id,
        relation_parameter_profile_revision=profile.profile_revision,
        quantifier_scope=quantifier_scope,
        evidence_scope="model-check",
        assurance_axis="model-check",
        evidence_boundary="All reachable points in the exact digest-bound finite transition model.",
        assurance_status="model-checked",
        evidence_refs=["participant-opacity-model-check-evidence:fixture-v1"],
        limitations=["Only the exact finite model and profile are covered."],
        explicit_non_claims=[
            MODEL_CHECK_PROVENANCE_NONCLAIM,
            "No unbounded proof, runtime enforcement, supervisor synthesis, or backend realization.",
            "No timed, probabilistic, quantitative, or partial-order result.",
        ],
    )


def _state(
    ordinal: int,
    *,
    secret: bool,
    observation: str,
    evaluation_point: bool = True,
    initial: str = "initial:shared",
    memory: str = "memory:shared",
    release: str = "release:baseline",
    strategy: str = "strategy:passive",
    order: str = "order:finite-fixture",
    coalition_fusion: str | None = None,
) -> ParticipantOpacityModelStateModel:
    return ParticipantOpacityModelStateModel(
        ordinal=ordinal,
        state_ref=f"model-state:fixture-{ordinal}",
        run_ref=f"run:fixture-{ordinal}",
        cut_ref="state-cut:fixture-exact-cut",
        strategy_ref=strategy,
        scheduler_ref="scheduler:finite-fixture",
        environment_ref="environment:finite-fixture",
        order_ref=order,
        evaluation_point=evaluation_point,
        secret_holds=secret,
        initial_information_key=initial,
        observation_key=observation,
        memory_key=memory,
        release_state_key=release,
        coalition_fusion_key=coalition_fusion,
    )


def _transition(
    ordinal: int,
    source: int,
    target: int,
    *,
    action: str = "action:advance",
    observation: str = "observation-event:advance",
) -> ParticipantOpacityModelTransitionModel:
    return ParticipantOpacityModelTransitionModel(
        ordinal=ordinal,
        transition_ref=f"model-transition:fixture-{ordinal}",
        source_state_ordinal=source,
        target_state_ordinal=target,
        action_ref=action,
        observation_event_key=observation,
    )


def _assumptions(
    profile: BehavioralRelationProfileModel,
    *,
    strategy_refs: tuple[str, ...] = ("strategy:passive",),
) -> ParticipantOpacityModelAssumptionsModel:
    parameters = profile.parameters
    return ParticipantOpacityModelAssumptionsModel(
        strategy_kind=parameters.strategy.kind,
        strategy_refs=strategy_refs,
        scheduler_refs=parameters.scheduler_refs,
        environment_refs=parameters.environment_refs,
        order_treatment=parameters.order.treatment,
        order_refs=parameters.order.order_refs,
        cut_ref=parameters.horizon.cut_ref,
        nondeterminism=parameters.nondeterminism,
        time_model=parameters.time.model,
        progress=parameters.time.progress,
        probability=parameters.probability,
    )


def _request(
    states: tuple[ParticipantOpacityModelStateModel, ...],
    *,
    initial_state_ordinals: tuple[int, ...],
    transitions: tuple[ParticipantOpacityModelTransitionModel, ...] = (),
    profile: BehavioralRelationProfileModel | None = None,
    catalog: BehavioralRelationCatalogModel | None = None,
    strategy_refs: tuple[str, ...] = ("strategy:passive",),
    complete_model: bool = True,
    quantifier_scope: str = "all-traces",
) -> tuple[
    ParticipantOpacityModelCheckInputModel,
    BehavioralRelationProfileModel,
    BehavioralRelationCatalogModel,
]:
    profile = profile or _historical_profile()
    catalog = catalog or _historical_catalog()
    counts = ParticipantOpacityModelCheckDeclaredCountsModel(
        states=len(states),
        transitions=len(transitions),
        initial_states=len(initial_state_ordinals),
        evaluation_points=sum(state.evaluation_point for state in states),
        runs=len({state.run_ref for state in states}),
        cuts=len({state.cut_ref for state in states}),
        strategies=len({state.strategy_ref for state in states}),
        scheduler_environment_pairs=len({(state.scheduler_ref, state.environment_ref) for state in states}),
        order_variants=len({state.order_ref for state in states}),
    )
    request = ParticipantOpacityModelCheckInputModel(
        schema_version="participant-opacity-model-check-input/v1",
        analysis_profile="raes-participant-opacity-model-check/v1",
        source=SourceArtifactIdentityModel(
            source_id="participant-opacity-model:fixture-source-v1",
            byte_digest="sha256:" + "a" * 64,
        ),
        catalog_digest=canonical_json_digest(catalog.model_dump(mode="json")),
        profile_id=profile.profile_id,
        profile_revision=profile.profile_revision,
        profile_digest=profile.canonical_digest,
        model_ref="participant-opacity-transition-model:fixture-v1",
        model_revision="rev1",
        materializer_id="raes-participant-opacity-model-fixture",
        materializer_version="1.0.0",
        materializer_digest="sha256:" + "b" * 64,
        complete_model=complete_model,
        assumptions=_assumptions(profile, strategy_refs=strategy_refs),
        declared_counts=counts,
        initial_state_ordinals=initial_state_ordinals,
        states=states,
        transitions=transitions,
        claim=_claim(profile, catalog, quantifier_scope=quantifier_scope),
    )
    return request, profile, catalog


def _bounded_pair_request(
    profile: BehavioralRelationProfileModel,
    catalog: BehavioralRelationCatalogModel,
) -> ParticipantOpacityAnalysisInputModel:
    points = (
        OpacityPossiblePointModel(
            ordinal=0,
            point_ref="possible-point:pair-0",
            run_ref="run:pair-0",
            cut_ref="state-cut:fixture-exact-cut",
            strategy_ref="strategy:passive",
            scheduler_ref="scheduler:finite-fixture",
            environment_ref="environment:finite-fixture",
            order_ref="order:finite-fixture",
            reachable=True,
            secret_holds=True,
            initial_information_key="initial:shared",
            observation_key="observation:shared",
            memory_key="memory:shared",
            release_state_key="release:baseline",
        ),
        OpacityPossiblePointModel(
            ordinal=1,
            point_ref="possible-point:pair-1",
            run_ref="run:pair-1",
            cut_ref="state-cut:fixture-exact-cut",
            strategy_ref="strategy:passive",
            scheduler_ref="scheduler:finite-fixture",
            environment_ref="environment:finite-fixture",
            order_ref="order:finite-fixture",
            reachable=True,
            secret_holds=False,
            initial_information_key="initial:shared",
            observation_key="observation:shared",
            memory_key="memory:shared",
            release_state_key="release:baseline",
        ),
    )
    claim = _claim(profile, catalog).model_copy(
        update={
            "subject": "One finite pair probe.",
            "quantifier_scope": "finite-cases",
            "evidence_scope": "finite",
            "assurance_axis": "bounded-test",
            "assurance_status": "tested",
            "evidence_boundary": "Only the supplied finite pair.",
            "explicit_non_claims": [
                NORMALIZED_INPUT_PROVENANCE_NONCLAIM,
                "No model check, proof, runtime enforcement, or backend realization.",
            ],
        }
    )
    return ParticipantOpacityAnalysisInputModel(
        schema_version="participant-opacity-analysis-input/v1",
        analysis_profile="raes-participant-opacity-bounded-test/v1",
        source=SourceArtifactIdentityModel(
            source_id="participant-opacity-fixture:pair-v1",
            byte_digest="sha256:" + "c" * 64,
        ),
        profile_id=profile.profile_id,
        profile_revision=profile.profile_revision,
        profile_digest=profile.canonical_digest,
        normalized_model_ref="participant-opacity-model:pair-v1",
        materializer_id="raes-participant-opacity-fixture-materializer",
        materializer_version="1.0.0",
        materializer_digest="sha256:" + "d" * 64,
        complete_enumeration=True,
        declared_counts=ParticipantOpacityDeclaredCountsModel(
            points=2,
            runs=2,
            cuts=1,
            strategies=1,
            scheduler_environment_pairs=1,
            order_variants=1,
        ),
        claim=claim,
        points=points,
    )


def _bounded_request_for_model_states(
    states: tuple[ParticipantOpacityModelStateModel, ...],
    profile: BehavioralRelationProfileModel,
    catalog: BehavioralRelationCatalogModel,
) -> ParticipantOpacityAnalysisInputModel:
    payload = _bounded_pair_request(profile, catalog).model_dump(mode="json")
    payload["points"] = [
        {
            "ordinal": state.ordinal,
            "point_ref": f"possible-point:agreement-{state.ordinal}",
            "run_ref": state.run_ref,
            "cut_ref": state.cut_ref,
            "strategy_ref": state.strategy_ref,
            "scheduler_ref": state.scheduler_ref,
            "environment_ref": state.environment_ref,
            "order_ref": state.order_ref,
            "reachable": True,
            "secret_holds": state.secret_holds,
            "initial_information_key": state.initial_information_key,
            "observation_key": state.observation_key,
            "memory_key": state.memory_key,
            "release_state_key": state.release_state_key,
            "coalition_fusion_key": state.coalition_fusion_key,
        }
        for state in states
    ]
    payload["declared_counts"] = {
        "points": len(states),
        "runs": len({state.run_ref for state in states}),
        "cuts": len({state.cut_ref for state in states}),
        "strategies": len({state.strategy_ref for state in states}),
        "scheduler_environment_pairs": len({(state.scheduler_ref, state.environment_ref) for state in states}),
        "order_variants": len({state.order_ref for state in states}),
    }
    payload["normalized_model_ref"] = "participant-opacity-model:agreement-v1"
    return ParticipantOpacityAnalysisInputModel.model_validate(payload)


def test_transition_model_contract_rejects_asserted_reachability_and_bad_counts() -> None:
    request, _, _ = _request(
        (
            _state(0, secret=True, observation="observation:shared"),
            _state(1, secret=False, observation="observation:shared"),
        ),
        initial_state_ordinals=(0, 1),
    )
    payload = request.model_dump(mode="json")
    payload["states"][0]["reachable"] = True
    with pytest.raises(ValidationError, match="Extra inputs|extra"):
        ParticipantOpacityModelCheckInputModel.model_validate(payload)

    bad_count = deepcopy(request.model_dump(mode="json"))
    bad_count["declared_counts"]["states"] = 3
    with pytest.raises(ValidationError, match="count"):
        ParticipantOpacityModelCheckInputModel.model_validate(bad_count)

    bad_domain = deepcopy(request.model_dump(mode="json"))
    bad_domain["assumptions"]["strategy_refs"] = [
        "strategy:passive",
        "strategy:undeclared",
    ]
    with pytest.raises(ValidationError, match="strategy domain"):
        ParticipantOpacityModelCheckInputModel.model_validate(bad_domain)


def test_complete_passive_model_check_binds_exact_model_tool_and_coverage() -> None:
    request, profile, catalog = _request(
        (
            _state(0, secret=True, observation="observation:shared"),
            _state(1, secret=False, observation="observation:shared"),
        ),
        initial_state_ordinals=(0, 1),
    )

    evidence = model_check_participant_opacity_input(
        request,
        profile=profile,
        catalog=catalog,
    )

    assert evidence.outcome is ParticipantOpacityModelCheckOutcome.HOLDS
    assert evidence.claim.assurance_axis == "model-check"
    assert evidence.claim.assurance_status == "model-checked"
    assert evidence.claim.evidence_scope == "model-check"
    assert evidence.claim.quantifier_scope == "all-traces"
    assert evidence.model_digest == request.canonical_digest
    assert evidence.catalog_digest == request.catalog_digest
    assert evidence.profile_digest == profile.canonical_digest
    assert evidence.checker_configuration.package_version
    assert evidence.coverage.declared == request.declared_counts
    assert evidence.coverage.explored_states == 2
    assert evidence.coverage.explored_transitions == 0
    assert evidence.coverage.reachable_evaluation_points == 2
    assert evidence.coverage.reachable_secret_points == 1
    assert evidence.coverage.complete_fixed_point is True
    assert evidence.counterexample is None

    bad_coverage = deepcopy(evidence.model_dump(mode="json"))
    bad_coverage["coverage"]["explored_scheduler_environment_pairs"] = 0
    with pytest.raises(ValidationError, match="scheduler/environment coverage"):
        ParticipantOpacityModelCheckEvidenceModel.model_validate(bad_coverage)


def test_pair_probe_can_pass_while_reachable_secret_only_cell_fails_model_check() -> None:
    states = (
        _state(0, secret=True, observation="observation:shared"),
        _state(1, secret=False, observation="observation:shared"),
        _state(2, secret=True, observation="observation:secret-only"),
    )
    request, profile, catalog = _request(
        states,
        initial_state_ordinals=(0, 1),
        transitions=(_transition(0, 0, 2),),
    )

    bounded = analyze_participant_opacity_input(
        _bounded_pair_request(profile, catalog),
        profile=profile,
    )
    evidence = model_check_participant_opacity_input(
        request,
        profile=profile,
        catalog=catalog,
    )

    assert bounded.outcome.value == "no-counterexample-within-declared-finite-bounds"
    assert evidence.outcome is ParticipantOpacityModelCheckOutcome.COUNTEREXAMPLE
    assert evidence.coverage.explored_states == 3
    assert evidence.coverage.explored_transitions == 1
    assert evidence.coverage.reachable_secret_points == 2
    assert evidence.counterexample is not None
    assert evidence.counterexample.actual_state_ordinal == 2
    assert evidence.counterexample.actual_path_transition_ordinals == (0,)


@pytest.mark.parametrize(
    ("states", "expected_model_outcome"),
    [
        (
            (
                _state(0, secret=True, observation="observation:shared"),
                _state(1, secret=False, observation="observation:shared"),
            ),
            ParticipantOpacityModelCheckOutcome.HOLDS,
        ),
        (
            (
                _state(0, secret=True, observation="observation:secret-only"),
                _state(1, secret=False, observation="observation:public"),
            ),
            ParticipantOpacityModelCheckOutcome.COUNTEREXAMPLE,
        ),
    ],
)
def test_bounded_and_model_check_lanes_agree_on_identical_reachable_carriers(
    states: tuple[ParticipantOpacityModelStateModel, ...],
    expected_model_outcome: ParticipantOpacityModelCheckOutcome,
) -> None:
    request, profile, catalog = _request(
        states,
        initial_state_ordinals=tuple(state.ordinal for state in states),
    )
    bounded = analyze_participant_opacity_input(
        _bounded_request_for_model_states(states, profile, catalog),
        profile=profile,
    )
    model_checked = model_check_participant_opacity_input(
        request,
        profile=profile,
        catalog=catalog,
    )

    assert model_checked.outcome is expected_model_outcome
    assert (bounded.outcome.value == "no-counterexample-within-declared-finite-bounds") is (
        expected_model_outcome is ParticipantOpacityModelCheckOutcome.HOLDS
    )
    assert (bounded.counterexample is None) is (model_checked.counterexample is None)
    if bounded.counterexample is not None and model_checked.counterexample is not None:
        assert bounded.counterexample.actual_point_ordinal == model_checked.counterexample.actual_state_ordinal


def test_model_check_evidence_replay_rejects_model_drift() -> None:
    request, profile, catalog = _request(
        (
            _state(0, secret=True, observation="observation:shared"),
            _state(1, secret=False, observation="observation:shared"),
        ),
        initial_state_ordinals=(0, 1),
    )
    evidence = model_check_participant_opacity_input(
        request,
        profile=profile,
        catalog=catalog,
    )

    assert (
        replay_participant_opacity_model_check_evidence(
            request,
            profile,
            catalog,
            evidence,
        )
        == evidence
    )
    drifted = request.model_copy(update={"materializer_digest": "sha256:" + "e" * 64})
    with pytest.raises(ParticipantOpacityEvidenceError, match="reproduce"):
        replay_participant_opacity_model_check_evidence(
            drifted,
            profile,
            catalog,
            evidence,
        )


def test_active_model_checks_every_strategy_and_keeps_witnesses_same_strategy() -> None:
    profile_payload = _historical_profile().model_dump(mode="json")
    profile_payload["parameters"]["strategy"] = {
        "kind": "active",
        "strategy_refs": ["strategy:passive", "strategy:probe"],
    }
    profile = BehavioralRelationProfileModel.model_validate(profile_payload)
    request, _, catalog = _request(
        (
            _state(
                0,
                secret=True,
                observation="observation:shared",
                strategy="strategy:passive",
            ),
            _state(
                1,
                secret=False,
                observation="observation:shared",
                strategy="strategy:passive",
            ),
            _state(
                2,
                secret=True,
                observation="probe:secret-response",
                strategy="strategy:probe",
            ),
            _state(
                3,
                secret=False,
                observation="probe:nonsecret-response",
                strategy="strategy:probe",
            ),
        ),
        initial_state_ordinals=(0, 1, 2, 3),
        profile=profile,
        strategy_refs=("strategy:passive", "strategy:probe"),
        quantifier_scope="all-strategies",
    )

    evidence = model_check_participant_opacity_input(
        request,
        profile=profile,
        catalog=catalog,
    )

    assert evidence.outcome is ParticipantOpacityModelCheckOutcome.COUNTEREXAMPLE
    assert evidence.claim.quantifier_scope == "all-strategies"
    assert tuple(item.strategy_ref for item in evidence.coverage.strategy_coverage) == (
        "strategy:passive",
        "strategy:probe",
    )
    assert evidence.counterexample is not None
    assert evidence.counterexample.strategy_ref == "strategy:probe"
    assert evidence.counterexample.actual_state_ordinal == 2


@pytest.mark.parametrize(
    ("name", "secret_state", "public_state"),
    [
        (
            "supervisor decision and timing",
            _state(0, secret=True, observation="decision:deny-at-step-2"),
            _state(1, secret=False, observation="decision:approve-at-step-1"),
        ),
        (
            "retained cross-episode memory",
            _state(0, secret=True, observation="observation:shared", memory="memory:secret-retained"),
            _state(1, secret=False, observation="observation:shared", memory="memory:public"),
        ),
        (
            "policy release change",
            _state(0, secret=True, observation="observation:shared", release="release:after-policy-change"),
            _state(1, secret=False, observation="observation:shared", release="release:baseline"),
        ),
    ],
)
def test_observable_control_memory_and_policy_changes_split_model_cells(
    name: str,
    secret_state: ParticipantOpacityModelStateModel,
    public_state: ParticipantOpacityModelStateModel,
) -> None:
    request, profile, catalog = _request(
        (secret_state, public_state),
        initial_state_ordinals=(0, 1),
    )

    evidence = model_check_participant_opacity_input(
        request,
        profile=profile,
        catalog=catalog,
    )

    assert evidence.outcome is ParticipantOpacityModelCheckOutcome.COUNTEREXAMPLE, name


def test_coalition_model_uses_fused_observation_instead_of_individual_projection() -> None:
    profile_payload = _historical_profile().model_dump(mode="json")
    profile_payload["parameters"]["observer"] = {
        "kind": "coalition",
        "member_refs": ["participant:a", "participant:b"],
        "audience_ref": "audience:coalition",
        "fusion_rule_ref": "coalition-fusion:ordered-pair-v1",
        "fusion_rule_revision": "rev1",
    }
    profile = BehavioralRelationProfileModel.model_validate(profile_payload)
    request, _, catalog = _request(
        (
            _state(
                0,
                secret=True,
                observation="individual:opaque",
                coalition_fusion="coalition:a0-b1",
            ),
            _state(
                1,
                secret=False,
                observation="individual:opaque",
                coalition_fusion="coalition:a0-b0",
            ),
        ),
        initial_state_ordinals=(0, 1),
        profile=profile,
    )

    evidence = model_check_participant_opacity_input(
        request,
        profile=profile,
        catalog=catalog,
    )

    assert evidence.outcome is ParticipantOpacityModelCheckOutcome.COUNTEREXAMPLE


def test_non_total_order_and_probability_promotions_fail_closed() -> None:
    profile_payload = _historical_profile().model_dump(mode="json")
    profile_payload["parameters"]["order"]["treatment"] = "partial-order"
    profile = BehavioralRelationProfileModel.model_validate(profile_payload)
    request, _, catalog = _request(
        (
            _state(0, secret=True, observation="observation:shared"),
            _state(1, secret=False, observation="observation:shared"),
        ),
        initial_state_ordinals=(0, 1),
        profile=profile,
    )

    evidence = model_check_participant_opacity_input(
        request,
        profile=profile,
        catalog=catalog,
    )

    assert evidence.outcome is ParticipantOpacityModelCheckOutcome.UNSUPPORTED
    assert {item.code for item in evidence.diagnostics} == {
        "participant-opacity-model-check.unsupported-order-treatment"
    }

    payload = request.model_dump(mode="json")
    payload["assumptions"]["probability"] = "probabilistic-support"
    with pytest.raises(ValidationError, match="outside-baseline|literal"):
        ParticipantOpacityModelCheckInputModel.model_validate(payload)


def test_incomplete_and_vacuous_models_never_produce_positive_evidence() -> None:
    incomplete, profile, catalog = _request(
        (
            _state(0, secret=True, observation="observation:shared"),
            _state(1, secret=False, observation="observation:shared"),
        ),
        initial_state_ordinals=(0, 1),
        complete_model=False,
    )
    unsupported = model_check_participant_opacity_input(
        incomplete,
        profile=profile,
        catalog=catalog,
    )
    assert unsupported.outcome is ParticipantOpacityModelCheckOutcome.UNSUPPORTED
    assert unsupported.coverage.complete_fixed_point is False
    assert {item.code for item in unsupported.diagnostics} == {"participant-opacity-model-check.incomplete-model"}

    vacuous, _, _ = _request(
        (
            _state(0, secret=False, observation="observation:a"),
            _state(1, secret=False, observation="observation:b"),
        ),
        initial_state_ordinals=(0, 1),
        profile=profile,
        catalog=catalog,
    )
    vacuous_evidence = model_check_participant_opacity_input(
        vacuous,
        profile=profile,
        catalog=catalog,
    )
    assert vacuous_evidence.outcome is ParticipantOpacityModelCheckOutcome.VACUOUS
    assert vacuous_evidence.coverage.complete_fixed_point is True
    assert vacuous_evidence.coverage.reachable_secret_points == 0


def test_model_check_enforces_profile_bounds() -> None:
    profile_payload = _historical_profile().model_dump(mode="json")
    profile_payload["parameters"]["bounds"]["max_runs"] = 1
    profile = BehavioralRelationProfileModel.model_validate(profile_payload)
    request, _, catalog = _request(
        (
            _state(0, secret=True, observation="observation:shared"),
            _state(1, secret=False, observation="observation:shared"),
        ),
        initial_state_ordinals=(0, 1),
        profile=profile,
    )

    with pytest.raises(ParticipantOpacityOperationalError, match="profile bound"):
        model_check_participant_opacity_input(
            request,
            profile=profile,
            catalog=catalog,
        )


def test_profile_digest_mutation_is_rejected_by_both_assurance_lanes() -> None:
    request, profile, catalog = _request(
        (
            _state(0, secret=True, observation="observation:shared"),
            _state(1, secret=False, observation="observation:shared"),
        ),
        initial_state_ordinals=(0, 1),
    )
    bad_digest = "sha256:" + "f" * 64
    drifted_model = request.model_copy(update={"profile_digest": bad_digest})
    drifted_bounded = _bounded_pair_request(profile, catalog).model_copy(update={"profile_digest": bad_digest})

    with pytest.raises(ParticipantOpacityOperationalError, match="profile identity"):
        model_check_participant_opacity_input(
            drifted_model,
            profile=profile,
            catalog=catalog,
        )
    with pytest.raises(ParticipantOpacityOperationalError, match="profile identity"):
        analyze_participant_opacity_input(drifted_bounded, profile=profile)


def test_model_check_file_ingress_rejects_duplicate_and_open_json_without_leaks(
    tmp_path: Path,
) -> None:
    request, _, _ = _request(
        (
            _state(0, secret=True, observation="observation:shared"),
            _state(1, secret=False, observation="observation:shared"),
        ),
        initial_state_ordinals=(0, 1),
    )
    encoded = request.model_dump_json()
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"schema_version":"participant-opacity-model-check-input/v1",' + encoded.removeprefix("{"),
        encoding="utf-8",
    )
    with pytest.raises(
        ParticipantOpacityInputError,
        match="bounded closed-world admission",
    ) as duplicate_error:
        model_check_participant_opacity_file(duplicate)
    assert "model-state:fixture-0" not in str(duplicate_error.value)
    assert duplicate_error.value.__suppress_context__ is True

    open_payload = request.model_dump(mode="json")
    open_payload["unexpected"] = "secret-bearing-value"
    open_input = tmp_path / "open.json"
    open_input.write_text(json.dumps(open_payload), encoding="utf-8")
    with pytest.raises(
        ParticipantOpacityInputError,
        match="bounded closed-world admission",
    ) as open_error:
        model_check_participant_opacity_file(open_input)
    assert "secret-bearing-value" not in str(open_error.value)
    assert open_error.value.__suppress_context__ is True


def test_model_check_contracts_are_published_with_semantic_invariants() -> None:
    bundle = schema_bundle()

    assert {
        "participant-opacity-model-check-input-v1",
        "participant-opacity-model-check-evidence-v1",
    } <= set(bundle)
    assert {item["id"] for item in bundle["participant-opacity-model-check-input-v1"]["x-raes-invariants"]} == {
        "participant-opacity-model-check-graph-joins"
    }
    assert {item["id"] for item in bundle["participant-opacity-model-check-evidence-v1"]["x-raes-invariants"]} == {
        "participant-opacity-model-check-evidence-joins"
    }


def test_historical_catalog_and_profile_preserve_the_model_check_assurance_axis() -> None:
    catalog = _historical_catalog()
    profile = _historical_profile()
    assurance = catalog.relations["participant-predicate-opacity"].assurance

    assert catalog.taxonomy_revision == "rev8"
    assert profile.profile_revision == "sem-231/rev2"
    assert profile.taxonomy_revision == "rev8"
    assert assurance.model_check_status == "model-checked"
    assert assurance.proof_status == "deliberately-unproved"
    assert assurance.runtime_enforcement_status == "not-enforced"
    assert assurance.backend_declaration_status == "not-declared"
    assert assurance.backend_realization_status == "not-realized"
    assert assurance.backend_conformance_status == "not-tested"


@pytest.mark.parametrize(
    ("contract_id", "fixture", "valid"),
    [
        (
            "participant-opacity-model-check-input-v1",
            "valid/opaque-transition-model.json",
            True,
        ),
        (
            "participant-opacity-model-check-input-v1",
            "invalid/count-mismatch.json",
            False,
        ),
        (
            "participant-opacity-model-check-evidence-v1",
            "valid/opaque-transition-model.json",
            True,
        ),
        (
            "participant-opacity-model-check-evidence-v1",
            "invalid/incomplete-positive-result.json",
            False,
        ),
    ],
)
def test_published_model_check_input_and_evidence_fixtures(
    contract_id: str,
    fixture: str,
    valid: bool,
) -> None:
    path = REPO_ROOT / "contracts/fixtures/formal-analysis" / contract_id / fixture
    diagnostics = _fixture_case_diagnostics(
        contract_id,
        json.loads(path.read_text(encoding="utf-8")),
    )

    assert (not diagnostics) is valid
