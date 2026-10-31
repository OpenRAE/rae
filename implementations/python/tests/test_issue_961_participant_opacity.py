"""SEM-231/ASR-535 closed opacity profiles and bounded falsification."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError
from raes_conformance.conformance import _fixture_case_diagnostics
from raes_contracts.behavioral_claims import BehavioralClaimBindingModel
from raes_contracts.behavioral_relation_profiles import (
    ActiveOpacityStrategyModel,
    BehavioralRelationProfileModel,
    load_behavioral_relation_profile_from_path,
    load_behavioral_relation_profile_revision,
)
from raes_contracts.behavioral_relations import (
    load_behavioral_relation_catalog_revision,
    validate_behavioral_claim_binding,
)
from raes_contracts.errors import InvalidInputError, OperationalError
from raes_contracts.participant_opacity import (
    NORMALIZED_INPUT_PROVENANCE_NONCLAIM,
    OpacityPossiblePointModel,
    ParticipantOpacityAnalysisEvidenceModel,
    ParticipantOpacityAnalysisInputModel,
    ParticipantOpacityDeclaredCountsModel,
    ParticipantOpacityOutcome,
)
from raes_contracts.source_identity import SourceArtifactIdentityModel
from raes_processor.participant_opacity import (
    ParticipantOpacityEvidenceError,
    ParticipantOpacityInputError,
    ParticipantOpacityOperationalError,
    analyze_participant_opacity_file,
    analyze_participant_opacity_input,
    replay_participant_opacity_evidence,
)
from raes_processor.participant_opacity import _service as opacity_service
from raes_schemas import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
PROFILE_ID = "participant-opacity-baseline-v1"
PROFILE_REVISION = "sem-231/rev2"
PROFILE_PATH = REPO_ROOT / "contracts/profiles/behavioral-relation" / f"{PROFILE_ID}.json"


def _claim(**overrides: object) -> BehavioralClaimBindingModel:
    payload: dict[str, object] = {
        "taxonomy_id": "raes-behavioral-relations",
        "taxonomy_revision": "rev8",
        "relation_id": "participant-predicate-opacity",
        "subject": "The exact declared finite possible-point carrier.",
        "left_carrier_ref": "possible-point-carrier:participant-opacity-fixture-v1",
        "observation_projection_ref": "participant-opacity-observation:complete-v1",
        "observation_projection_revision": "rev1",
        "relation_parameter_profile_ref": PROFILE_ID,
        "relation_parameter_profile_revision": "sem-231/rev2",
        "quantifier_scope": "finite-cases",
        "evidence_scope": "finite",
        "assurance_axis": "bounded-test",
        "evidence_boundary": "Only the exact declared finite bounds and model.",
        "assurance_status": "tested",
        "evidence_refs": ["participant-opacity-evidence:fixture-v1"],
        "limitations": ["No result outside the declared finite bounds."],
        "explicit_non_claims": [
            "No model check, proof, runtime enforcement, or backend realization.",
            NORMALIZED_INPUT_PROVENANCE_NONCLAIM,
        ],
    }
    payload.update(overrides)
    return BehavioralClaimBindingModel.model_validate(payload)


def _profile_payload() -> dict[str, object]:
    return load_behavioral_relation_profile_revision(PROFILE_ID, PROFILE_REVISION).model_dump(mode="json")


def test_published_profile_closes_every_sem_231_coordinate() -> None:
    profile = load_behavioral_relation_profile_revision(PROFILE_ID, PROFILE_REVISION)

    assert profile.schema_version == "behavioral-relation-profile/v1"
    assert profile.profile_id == PROFILE_ID
    assert profile.profile_revision == "sem-231/rev2"
    assert profile.taxonomy_id == "raes-behavioral-relations"
    assert profile.taxonomy_revision == "rev8"
    assert profile.relation_id == "participant-predicate-opacity"
    assert profile.left_carrier_ref == _claim().left_carrier_ref
    assert profile.parameters.kind == "participant-predicate-opacity/v1"
    assert profile.parameters.observer.kind == "individual"
    assert profile.parameters.secret.truth_polarity == "one-sided-true"
    assert profile.parameters.strategy.kind == "passive"
    assert profile.parameters.nondeterminism == "possibilistic-support"
    assert profile.parameters.time.progress == "progress-insensitive"
    assert profile.parameters.time.absence_observable is False
    assert profile.parameters.probability == "outside-baseline"
    assert profile.limitations
    assert profile.explicit_non_claims


def test_claim_resolution_joins_catalog_profile_carrier_and_projection() -> None:
    catalog = load_behavioral_relation_catalog_revision("rev8")
    profile = load_behavioral_relation_profile_revision(PROFILE_ID, PROFILE_REVISION)

    assert validate_behavioral_claim_binding(_claim(), catalog, profile) == _claim()

    mismatches = (
        _claim(taxonomy_revision="rev6"),
        _claim(left_carrier_ref="possible-point-carrier:other"),
        _claim(observation_projection_ref="participant-opacity-observation:payload-only"),
        _claim(relation_parameter_profile_revision="sem-231/rev3"),
    )
    for binding in mismatches:
        with pytest.raises(ValueError, match="profile|catalog|carrier|projection"):
            validate_behavioral_claim_binding(binding, catalog, profile)


def test_profile_rejects_unknown_fields_and_incomplete_active_or_coalition_shapes() -> None:
    payload = _profile_payload()
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        BehavioralRelationProfileModel.model_validate(payload)

    active = _profile_payload()
    active["parameters"]["strategy"] = {
        "kind": "active",
        "strategy_refs": [],
    }
    with pytest.raises(ValidationError, match="strategy"):
        BehavioralRelationProfileModel.model_validate(active)

    coalition = _profile_payload()
    coalition["parameters"]["observer"] = {
        "kind": "coalition",
        "member_refs": ["participant:a", "participant:b"],
        "audience_ref": "audience:coalition",
        "fusion_rule_ref": None,
        "fusion_rule_revision": None,
    }
    with pytest.raises(ValidationError, match="fusion"):
        BehavioralRelationProfileModel.model_validate(coalition)


def test_observable_absence_requires_a_declared_opportunity_basis() -> None:
    payload = _profile_payload()
    payload["parameters"]["time"]["absence_observable"] = True

    with pytest.raises(ValidationError, match="opportunity"):
        BehavioralRelationProfileModel.model_validate(payload)


def test_profile_loader_rejects_request_identity_mismatch_and_ambiguous_json(
    tmp_path: Path,
) -> None:
    payload = PROFILE_PATH.read_text(encoding="utf-8")
    other = tmp_path / "other.json"
    other.write_text(payload, encoding="utf-8")
    with pytest.raises(InvalidInputError, match="requested"):
        load_behavioral_relation_profile_from_path("other-profile-v1", other)

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        payload.replace(
            '"schema_version": "behavioral-relation-profile/v1",',
            ('"schema_version": "behavioral-relation-profile/v1","schema_version": "behavioral-relation-profile/v1",'),
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(OperationalError, match="JSON|duplicate") as duplicate_error:
        load_behavioral_relation_profile_from_path(PROFILE_ID, duplicate)
    assert duplicate_error.value.__suppress_context__ is True


def test_profile_local_cross_references_are_canonical_and_complete() -> None:
    payload = _profile_payload()
    payload["parameters"]["scheduler_refs"] = ["scheduler:b", "scheduler:a"]
    with pytest.raises(ValidationError, match="sorted|canonical"):
        BehavioralRelationProfileModel.model_validate(payload)

    duplicate = deepcopy(_profile_payload())
    duplicate["parameters"]["environment_refs"] = [
        "environment:finite-fixture",
        "environment:finite-fixture",
    ]
    with pytest.raises(ValidationError, match="unique"):
        BehavioralRelationProfileModel.model_validate(duplicate)


def _point(
    ordinal: int,
    *,
    secret: bool,
    observation: str,
    initial: str = "initial:shared",
    memory: str = "memory:shared",
    release: str = "release:baseline",
    strategy: str = "strategy:passive",
    order: str = "order:finite-fixture",
    coalition_fusion: str | None = None,
) -> OpacityPossiblePointModel:
    return OpacityPossiblePointModel(
        ordinal=ordinal,
        point_ref=f"possible-point:fixture-{ordinal}",
        run_ref=f"run:fixture-{ordinal}",
        cut_ref="state-cut:fixture-exact-cut",
        strategy_ref=strategy,
        scheduler_ref="scheduler:finite-fixture",
        environment_ref="environment:finite-fixture",
        order_ref=order,
        reachable=True,
        secret_holds=secret,
        initial_information_key=initial,
        observation_key=observation,
        memory_key=memory,
        release_state_key=release,
        coalition_fusion_key=coalition_fusion,
    )


def _request(
    points: tuple[OpacityPossiblePointModel, ...],
    *,
    profile: BehavioralRelationProfileModel | None = None,
    complete_enumeration: bool = True,
) -> tuple[ParticipantOpacityAnalysisInputModel, BehavioralRelationProfileModel]:
    profile = profile or load_behavioral_relation_profile_revision(PROFILE_ID, PROFILE_REVISION)
    strategy_refs = {point.strategy_ref for point in points}
    run_refs = {point.run_ref for point in points}
    cut_refs = {point.cut_ref for point in points}
    scheduler_environment_pairs = {(point.scheduler_ref, point.environment_ref) for point in points}
    order_refs = {point.order_ref for point in points}
    request = ParticipantOpacityAnalysisInputModel(
        schema_version="participant-opacity-analysis-input/v1",
        analysis_profile="raes-participant-opacity-bounded-test/v1",
        source=SourceArtifactIdentityModel(
            source_id="participant-opacity-fixture:finite-model-v1",
            byte_digest="sha256:" + "a" * 64,
        ),
        profile_id=profile.profile_id,
        profile_revision=profile.profile_revision,
        profile_digest=profile.canonical_digest,
        normalized_model_ref="participant-opacity-model:finite-fixture-v1",
        materializer_id="raes-participant-opacity-fixture-materializer",
        materializer_version="1.0.0",
        materializer_digest="sha256:" + "b" * 64,
        complete_enumeration=complete_enumeration,
        declared_counts=ParticipantOpacityDeclaredCountsModel(
            points=len(points),
            runs=len(run_refs),
            cuts=len(cut_refs),
            strategies=len(strategy_refs),
            scheduler_environment_pairs=len(scheduler_environment_pairs),
            order_variants=len(order_refs),
        ),
        claim=_claim(),
        points=points,
    )
    return request, profile


def test_finite_checker_reports_only_a_bounded_positive_result() -> None:
    request, profile = _request(
        (
            _point(0, secret=True, observation="observation:shared"),
            _point(1, secret=False, observation="observation:shared"),
        )
    )

    evidence = analyze_participant_opacity_input(request, profile=profile)

    assert evidence.outcome is ParticipantOpacityOutcome.NO_COUNTEREXAMPLE
    assert evidence.checked_points == 2
    assert evidence.checked_secret_points == 1
    assert evidence.counterexample is None
    assert evidence.claim.assurance_axis == "bounded-test"
    assert evidence.claim.assurance_status == "tested"
    assert evidence.claim.evidence_scope == "finite"
    assert evidence.claim.quantifier_scope == "finite-cases"
    assert "declared finite bounds" in evidence.claim.evidence_boundary
    assert evidence.normalized_model_digest.startswith("sha256:")
    assert evidence.profile_digest == profile.canonical_digest
    assert evidence.checker_configuration.tool_version == "1.0.0"


def test_one_equal_history_pair_does_not_cover_another_secret_point() -> None:
    request, profile = _request(
        (
            _point(0, secret=True, observation="observation:paired"),
            _point(1, secret=False, observation="observation:paired"),
            _point(2, secret=True, observation="observation:secret-only"),
        )
    )

    evidence = analyze_participant_opacity_input(request, profile=profile)

    assert evidence.outcome is ParticipantOpacityOutcome.COUNTEREXAMPLE
    assert evidence.counterexample is not None
    assert evidence.counterexample.actual_point_ordinal == 2
    assert evidence.counterexample.safe_ref == "participant-opacity-counterexample:000002"


def test_counterexample_scan_completes_all_secret_obligations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[int, int] = {}
    original = opacity_service._information_cell_key

    def tracking_cell_key(
        point: OpacityPossiblePointModel,
    ) -> tuple[str, str, str, str, str | None, str, str]:
        calls[point.ordinal] = calls.get(point.ordinal, 0) + 1
        return original(point)

    monkeypatch.setattr(
        opacity_service,
        "_information_cell_key",
        tracking_cell_key,
    )
    request, profile = _request(
        (
            _point(0, secret=True, observation="observation:first-secret"),
            _point(1, secret=True, observation="observation:second-secret"),
            _point(2, secret=False, observation="observation:public"),
        )
    )

    evidence = analyze_participant_opacity_input(request, profile=profile)

    assert evidence.outcome is ParticipantOpacityOutcome.COUNTEREXAMPLE
    assert evidence.counterexample is not None
    assert evidence.counterexample.actual_point_ordinal == 0
    assert evidence.checked_secret_points == 2
    assert calls[0] == 2
    assert calls[1] == 2


@pytest.mark.parametrize(
    ("name", "points"),
    [
        (
            "supervisor decision and delivery leak",
            (
                _point(0, secret=True, observation="decision:deny-delivered"),
                _point(1, secret=False, observation="decision:approve-delivered"),
            ),
        ),
        (
            "declassification remains in retained memory",
            (
                _point(
                    0,
                    secret=True,
                    observation="payload:concealed",
                    memory="memory:released-secret-retained",
                    release="release:concealed-after-release",
                ),
                _point(
                    1,
                    secret=False,
                    observation="payload:concealed",
                    memory="memory:never-released",
                    release="release:concealed-after-release",
                ),
            ),
        ),
    ],
)
def test_observable_control_and_retained_knowledge_falsify_opacity(
    name: str,
    points: tuple[OpacityPossiblePointModel, ...],
) -> None:
    request, profile = _request(points)
    evidence = analyze_participant_opacity_input(request, profile=profile)

    assert evidence.outcome is ParticipantOpacityOutcome.COUNTEREXAMPLE, name


def test_active_probe_requires_a_witness_under_the_same_strategy() -> None:
    payload = _profile_payload()
    payload["parameters"]["strategy"] = {
        "kind": "active",
        "strategy_refs": ["strategy:passive", "strategy:probe"],
    }
    profile = BehavioralRelationProfileModel.model_validate(payload)
    assert isinstance(profile.parameters.strategy, ActiveOpacityStrategyModel)
    request, _ = _request(
        (
            _point(
                0,
                secret=True,
                observation="observation:shared",
                strategy="strategy:passive",
            ),
            _point(
                1,
                secret=False,
                observation="observation:shared",
                strategy="strategy:passive",
            ),
            _point(
                2,
                secret=True,
                observation="probe:secret-response",
                strategy="strategy:probe",
            ),
            _point(
                3,
                secret=False,
                observation="probe:nonsecret-response",
                strategy="strategy:probe",
            ),
        ),
        profile=profile,
    )

    evidence = analyze_participant_opacity_input(request, profile=profile)

    assert evidence.outcome is ParticipantOpacityOutcome.COUNTEREXAMPLE
    assert evidence.counterexample is not None
    assert evidence.counterexample.actual_point_ordinal == 2


def test_fused_coalition_observation_is_not_inferred_from_individual_opacity() -> None:
    payload = _profile_payload()
    payload["parameters"]["observer"] = {
        "kind": "coalition",
        "member_refs": ["participant:a", "participant:b"],
        "audience_ref": "audience:coalition",
        "fusion_rule_ref": "coalition-fusion:ordered-pair-v1",
        "fusion_rule_revision": "rev1",
    }
    profile = BehavioralRelationProfileModel.model_validate(payload)
    request, _ = _request(
        (
            _point(
                0,
                secret=True,
                observation="individual-projections:opaque",
                coalition_fusion="coalition:a0-b1",
            ),
            _point(
                1,
                secret=False,
                observation="individual-projections:opaque",
                coalition_fusion="coalition:a0-b0",
            ),
        ),
        profile=profile,
    )

    evidence = analyze_participant_opacity_input(request, profile=profile)

    assert evidence.outcome is ParticipantOpacityOutcome.COUNTEREXAMPLE


def test_declared_order_context_is_part_of_the_information_cell() -> None:
    payload = _profile_payload()
    payload["parameters"]["order"]["order_refs"] = [
        "order:alternate-fixture",
        "order:finite-fixture",
    ]
    profile = BehavioralRelationProfileModel.model_validate(payload)
    request, _ = _request(
        (
            _point(
                0,
                secret=True,
                observation="observation:shared",
                order="order:finite-fixture",
            ),
            _point(
                1,
                secret=False,
                observation="observation:shared",
                order="order:alternate-fixture",
            ),
        ),
        profile=profile,
    )

    evidence = analyze_participant_opacity_input(request, profile=profile)

    assert evidence.outcome is ParticipantOpacityOutcome.COUNTEREXAMPLE


def test_admission_requires_every_scheduler_environment_pair() -> None:
    payload = _profile_payload()
    payload["parameters"]["scheduler_refs"] = [
        "scheduler:finite-fixture",
        "scheduler:second-fixture",
    ]
    payload["parameters"]["environment_refs"] = [
        "environment:finite-fixture",
        "environment:second-fixture",
    ]
    profile = BehavioralRelationProfileModel.model_validate(payload)
    request, _ = _request(
        (
            _point(0, secret=True, observation="observation:shared"),
            _point(1, secret=False, observation="observation:shared").model_copy(
                update={
                    "scheduler_ref": "scheduler:second-fixture",
                    "environment_ref": "environment:second-fixture",
                }
            ),
        ),
        profile=profile,
    )

    with pytest.raises(
        ParticipantOpacityOperationalError,
        match="scheduler/environment pair domain",
    ):
        analyze_participant_opacity_input(request, profile=profile)


def test_vacuous_or_incomplete_domains_never_produce_a_positive_result() -> None:
    vacuous, profile = _request(
        (
            _point(0, secret=False, observation="observation:a"),
            _point(1, secret=False, observation="observation:b"),
        )
    )
    evidence = analyze_participant_opacity_input(vacuous, profile=profile)
    assert evidence.outcome is ParticipantOpacityOutcome.VACUOUS
    assert evidence.checked_points == 2
    assert evidence.checked_secret_points == 0
    assert {item.code for item in evidence.diagnostics} == {"participant-opacity.vacuous-secret-domain"}

    incomplete, _ = _request(
        (
            _point(0, secret=True, observation="observation:shared"),
            _point(1, secret=False, observation="observation:shared"),
        ),
        complete_enumeration=False,
    )
    unsupported = analyze_participant_opacity_input(incomplete, profile=profile)
    assert unsupported.outcome is ParticipantOpacityOutcome.UNSUPPORTED
    assert {item.code for item in unsupported.diagnostics} == {"participant-opacity.incomplete-enumeration"}


def test_count_mismatch_is_rejected_before_evaluation() -> None:
    request, _ = _request(
        (
            _point(0, secret=True, observation="observation:shared"),
            _point(1, secret=False, observation="observation:shared"),
        )
    )
    payload = request.model_dump(mode="json")
    payload["declared_counts"]["points"] = 3

    with pytest.raises(ValidationError, match="count"):
        ParticipantOpacityAnalysisInputModel.model_validate(payload)


def test_evidence_is_permutation_independent_sanitized_and_replayable() -> None:
    points = (
        _point(0, secret=True, observation="observation:secret-only"),
        _point(1, secret=False, observation="observation:public"),
    )
    request, profile = _request(points)
    permuted, _ = _request(tuple(reversed(points)))

    evidence = analyze_participant_opacity_input(request, profile=profile)
    permuted_evidence = analyze_participant_opacity_input(
        permuted,
        profile=profile,
    )

    assert evidence == permuted_evidence
    serialized = evidence.model_dump_json()
    assert "possible-point:fixture" not in serialized
    assert "observation:secret-only" not in serialized
    assert "memory:" not in serialized
    assert "participant-opacity-fixture:finite-model-v1" not in serialized
    assert "raes-participant-opacity-fixture-materializer" not in serialized
    assert evidence.provenance_scope == "normalized-input-only"
    assert replay_participant_opacity_evidence(request, profile, evidence) == evidence

    drifted = request.model_copy(
        update={
            "materializer_digest": "sha256:" + "c" * 64,
        }
    )
    with pytest.raises(ParticipantOpacityEvidenceError, match="reproduce"):
        replay_participant_opacity_evidence(drifted, profile, evidence)


def test_evidence_contract_rejects_contradictory_outcome_states() -> None:
    request, profile = _request(
        (
            _point(0, secret=True, observation="observation:shared"),
            _point(1, secret=False, observation="observation:shared"),
        )
    )
    evidence = analyze_participant_opacity_input(request, profile=profile)
    base = evidence.model_dump(mode="json")

    for update in (
        {"checked_points": 0, "checked_secret_points": 0},
        {"checked_points": 1, "checked_secret_points": 2},
        {
            "diagnostics": [
                {
                    "code": "participant-opacity.invalid-positive",
                    "domain": "participant-opacity",
                    "address": "/outcome",
                    "message": "A decided outcome cannot carry an error.",
                    "severity": "error",
                }
            ]
        },
    ):
        contradictory = deepcopy(base)
        contradictory.update(update)
        with pytest.raises(ValidationError, match="checked|diagnostic|decided"):
            ParticipantOpacityAnalysisEvidenceModel.model_validate(contradictory)


def test_file_analyzer_rejects_duplicate_or_open_json_without_echoing_input(
    tmp_path: Path,
) -> None:
    request, _ = _request(
        (
            _point(0, secret=True, observation="observation:shared"),
            _point(1, secret=False, observation="observation:shared"),
        )
    )
    valid = tmp_path / "valid.json"
    valid.write_text(request.model_dump_json(), encoding="utf-8")
    assert analyze_participant_opacity_file(valid).outcome is ParticipantOpacityOutcome.NO_COUNTEREXAMPLE

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        request.model_dump_json().replace(
            '"schema_version":',
            '"schema_version":"participant-opacity-analysis-input/v1","schema_version":',
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        ParticipantOpacityInputError,
        match="bounded closed-world admission",
    ) as duplicate_error:
        analyze_participant_opacity_file(duplicate)
    assert "possible-point:fixture" not in str(duplicate_error.value)
    assert duplicate_error.value.__suppress_context__ is True

    open_payload = request.model_dump(mode="json")
    open_payload["unexpected"] = "secret-bearing-value"
    open_input = tmp_path / "open.json"
    open_input.write_text(json.dumps(open_payload), encoding="utf-8")
    with pytest.raises(
        ParticipantOpacityInputError,
        match="bounded closed-world admission",
    ) as open_error:
        analyze_participant_opacity_file(open_input)
    assert "secret-bearing-value" not in str(open_error.value)
    assert open_error.value.__suppress_context__ is True


def test_opacity_contracts_are_published_with_semantic_invariants() -> None:
    bundle = schema_bundle()

    assert {
        "behavioral-relation-profile-v1",
        "participant-opacity-analysis-input-v1",
        "participant-opacity-analysis-evidence-v1",
    } <= set(bundle)
    assert {item["id"] for item in bundle["behavioral-relation-profile-v1"]["x-raes-invariants"]} == {
        "behavioral-relation-profile-local-join",
        "behavioral-relation-profile-claim-resolution",
    }
    assert {item["id"] for item in bundle["participant-opacity-analysis-input-v1"]["x-raes-invariants"]} == {
        "participant-opacity-finite-carrier-counts"
    }
    assert {item["id"] for item in bundle["participant-opacity-analysis-evidence-v1"]["x-raes-invariants"]} == {
        "participant-opacity-evidence-joins"
    }


@pytest.mark.parametrize(
    ("contract_id", "fixture", "valid"),
    [
        (
            "behavioral-relation-profile-v1",
            "valid/participant-opacity-baseline.json",
            True,
        ),
        (
            "behavioral-relation-profile-v1",
            "invalid/observable-absence-without-opportunity.json",
            False,
        ),
        (
            "participant-opacity-analysis-input-v1",
            "valid/opaque-pair.json",
            True,
        ),
        (
            "participant-opacity-analysis-input-v1",
            "invalid/count-mismatch.json",
            False,
        ),
        (
            "participant-opacity-analysis-evidence-v1",
            "valid/bounded-counterexample.json",
            True,
        ),
        (
            "participant-opacity-analysis-evidence-v1",
            "invalid/universal-bounded-claim.json",
            False,
        ),
    ],
)
def test_published_profile_input_and_evidence_fixtures(
    contract_id: str,
    fixture: str,
    valid: bool,
) -> None:
    fixture_family = "profiles" if contract_id == "behavioral-relation-profile-v1" else "formal-analysis"
    root = REPO_ROOT / "contracts/fixtures" / fixture_family / contract_id / fixture
    diagnostics = _fixture_case_diagnostics(
        contract_id,
        json.loads(root.read_text(encoding="utf-8")),
    )

    assert (not diagnostics) is valid
