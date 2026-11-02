"""SCE-002 admitted experiment trial-plan contract (issue #788).

Covers the immutable, schedule-independent handoff between experiment
design/admission and orchestration: identity distinctness, resolved-only
selections/bindings/draws, plan-local reference joins, the acyclic
entry/plan digest integrity chain, and schema publication.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_contracts.contracts.admitted_trial_plan import (
    AdmittedApparatusBindingModel,
    AdmittedBindingModel,
    AdmittedExecutionControlModel,
    AdmittedInstantiationProvenanceModel,
    AdmittedSelectionRecordModel,
    AdmittedTrialEntryModel,
    AdmittedTrialPlanAdmissionModel,
    AdmittedTrialPlanInputRefsModel,
    AdmittedTrialPlanModel,
    AdmittedTrialPlanProfilesModel,
    ExperimentScenarioFamilyReferenceModel,
    seal_admitted_trial_entry,
    seal_admitted_trial_plan,
)
from raes_contracts.contracts.admitted_trial_plan_ingress import (
    MAX_ADMITTED_TRIAL_PLAN_BYTES,
    AdmittedTrialPlanIngressError,
    parse_admitted_trial_plan_json,
)
from raes_contracts.contracts.experiment_apparatus import ExperimentStochasticControlModel
from raes_contracts.contracts.experiment_bindings import (
    BindingOwnerModel,
    ExperimentBindingDescriptorModel,
    LiteralBindingValueModel,
    ScenarioBindingTargetModel,
)
from raes_contracts.contracts.experiment_manifest_references import (
    ExperimentBackendReferenceModel,
    ExperimentManifestReferenceModel,
)
from raes_contracts.contracts.experiment_references import (
    ExperimentReferenceModel,
    ExperimentTaskReferenceModel,
)
from raes_contracts.contracts.random_stream import (
    PublicRandomOutcomeModel,
    PublicSeedModel,
    RandomStreamControlBindingModel,
    RandomStreamDrawRecordModel,
    RandomStreamProfileReferenceModel,
    StreamAddressModel,
    TrialCoordinateModel,
)
from raes_contracts.contracts.realization_plans import RealizationEnvelopeIdentityModel
from raes_contracts.contracts.trial_cleanup import (
    CleanStateRequirementModel,
    CleanupObligationModel,
    CleanupResourceBoundaryModel,
    ExecutionRetryPolicyModel,
    IsolationDimensionEvidenceModel,
    SchedulerIsolationProofModel,
    TrialCleanupPlanModel,
)
from raes_schemas import schema_bundle

_REQUIRED_ISOLATION_DIMENSIONS = (
    "range-instance",
    "host-capacity",
    "ports",
    "storage",
    "control-plane-locks",
    "secret-scope",
    "cleanup",
)

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "contracts" / "fixtures"
CONTRACT_ID = "admitted-trial-plan-v1"


def _digest(byte: str) -> str:
    return "sha256:" + byte * 32


def _profiles(**overrides: object) -> AdmittedTrialPlanProfilesModel:
    fields: dict[str, object] = {
        "coordinate_profile": "trial-coordinate-v1",
        "entry_identity_profile": "trial-entry-identity-v1",
        "run_identity_profile": "archival-run-identity-v1",
        "canonicalization_profile": "jcs-sha256-v1",
        "integrity_profile": "acyclic-digest-chain-v1",
        "compiler_profile": "trial-compiler-v1",
        "selection_policy_profile": "experiment-selection-v1",
        "random_stream_profile": "blake3-xof-v1",
        "execution_control_profile": "attempt-control-v1",
        "cleanup_profile": "trial-cleanup-v1",
        "isolation_profile": "scheduler-isolation-v1",
    }
    fields.update(overrides)
    return AdmittedTrialPlanProfilesModel(**fields)


def _parallel_proof(entry_ids: list[str]) -> SchedulerIsolationProofModel:
    return SchedulerIsolationProofModel(
        schema_version="scheduler-isolation-proof/v1",
        proof_id="proof-parallel",
        plan_entry_ids=entry_ids,
        requested_parallelism=2,
        dimensions=[
            IsolationDimensionEvidenceModel(
                dimension=dimension, independent=True, evidence_refs=[f"evidence:{dimension}"]
            )
            for dimension in _REQUIRED_ISOLATION_DIMENSIONS
        ],
    )


def _input_refs(**overrides: object) -> AdmittedTrialPlanInputRefsModel:
    fields: dict[str, object] = {
        "authoring_input_ref": ExperimentReferenceModel(
            ref_kind="authoring-input", ref_id="exp-a", ref_version="1", ref_digest=_digest("ab")
        ),
        "task_ref": ExperimentTaskReferenceModel(ref_kind="task", ref_id="task-a", ref_version="1"),
        "task_digest": _digest("bc"),
        "scenario_family_ref": ExperimentScenarioFamilyReferenceModel(
            ref_kind="scenario-family",
            ref_id="family-a",
            ref_version="expanded-scenario-family/v1",
            ref_digest=_digest("cd"),
        ),
        "binding_descriptor_set_ref": ExperimentReferenceModel(
            ref_kind="other", ref_id="bindings-a", ref_version="1", ref_digest=_digest("ef")
        ),
    }
    fields.update(overrides)
    return AdmittedTrialPlanInputRefsModel(**fields)


def _control(
    control_id: str = "control-a", *, executable: bool = True, profile_ref_id: str = "blake3-xof-v1"
) -> ExperimentStochasticControlModel:
    binding = None
    if executable:
        binding = RandomStreamControlBindingModel(
            profile_ref=RandomStreamProfileReferenceModel(
                ref_kind="profile", ref_id=profile_ref_id, ref_version="random-stream-profile/v1"
            ),
            namespace="study-namespace",
            root_entropy=PublicSeedModel(kind="public-seed", encoding="hex-fixed-width", value="ab" * 32),
        )
    return ExperimentStochasticControlModel(control_id=control_id, role="randomization", executable_binding=binding)


def _cleanup_plan(plan_id: str, entry_id: str, run_id: str, resource: str = "a") -> TrialCleanupPlanModel:
    boundary_id = f"range-{resource}"
    return TrialCleanupPlanModel(
        schema_version="trial-cleanup-plan/v1",
        plan_id=plan_id,
        plan_entry_id=entry_id,
        run_id=run_id,
        clean_state=CleanStateRequirementModel(
            mode="fresh", boundary_refs=[boundary_id], verification_probe_refs=["probe:fresh"]
        ),
        resource_boundaries={
            boundary_id: CleanupResourceBoundaryModel(
                boundary_id=boundary_id,
                resource_kind="range-instance",
                owner_ref=f"apparatus:{boundary_id}",
                resource_refs=[f"node.vm-{resource}"],
            )
        },
        cleanup_obligations={
            "destroy-range": CleanupObligationModel(
                obligation_id="destroy-range",
                boundary_refs=[boundary_id],
                action_kind="destroy",
                triggers=["success", "failure", "cancellation", "timeout", "abort"],
                requirement="required",
                idempotency="idempotent",
                verification_probe_refs=["probe:absent"],
                timeout_seconds=120,
            )
        },
        retry_policy=ExecutionRetryPolicyModel(max_attempts=1, after_effect_policy="disallow"),
    )


def _manifest_ref(**overrides: object) -> ExperimentManifestReferenceModel:
    fields: dict[str, object] = {
        "ref_kind": "manifest",
        "ref_id": "backend-a",
        "ref_version": "backend-manifest/v2",
        "ref_digest": _digest("33"),
        "subject_ref": ExperimentBackendReferenceModel(ref_kind="backend", ref_id="backend-a", ref_version="1"),
    }
    fields.update(overrides)
    return ExperimentManifestReferenceModel(**fields)


def _apparatus(**overrides: object) -> AdmittedApparatusBindingModel:
    fields: dict[str, object] = {
        "manifest_refs": [_manifest_ref()],
        "realization_envelope": RealizationEnvelopeIdentityModel(
            envelope_id="env-a", digest=_digest("11"), configuration_digest=_digest("22")
        ),
        "capability_refs": ["cap:isolation"],
    }
    fields.update(overrides)
    return AdmittedApparatusBindingModel(**fields)


def _binding(condition_id: str = "baseline", family_id: str = "family-a") -> AdmittedBindingModel:
    return AdmittedBindingModel(
        descriptor=ExperimentBindingDescriptorModel(
            binding_id="bind-a",
            source_factor_id="factor-a",
            source_factor_level_id="level-a",
            source_condition_id=condition_id,
            target=ScenarioBindingTargetModel(
                plane="scenario", scenario_family_id=family_id, variation_point_id="point-b", target_id="target-a"
            ),
            value_type="string",
            value=LiteralBindingValueModel(kind="literal", value="v"),
            owner=BindingOwnerModel(
                contract_id="sdl-authoring-input-v1",
                contract_version="1",
                validator_id="scenario-binder",
                validator_version="1",
            ),
        ),
        origin="selection",
    )


def _draw(
    control_id: str = "control-a", condition_id: str = "baseline", namespace: str = "study-namespace"
) -> RandomStreamDrawRecordModel:
    return RandomStreamDrawRecordModel(
        control_id=control_id,
        address=StreamAddressModel(
            namespace=namespace,
            trial_coordinate=TrialCoordinateModel(condition_id=condition_id),
            selection_policy_id="policy-a",
            variation_point_id="point-a",
            draw_purpose="condition-assignment",
            local_coordinate=0,
        ),
        transform_id="bounded-integer",
        transform_version="1",
        local_coordinate=0,
        outcome=PublicRandomOutcomeModel(kind="public-value", value="3"),
    )


def _entry(
    *,
    entry_id: str = "entry-a",
    run_id: str = "run-a",
    condition_id: str = "baseline",
    cleanup_ref: str = "cleanup-a",
    control_id: str = "control-a",
    provenance_plan_id: str = "plan-a",
    provenance_family_id: str = "family-a",
    draw_condition_id: str | None = None,
    apparatus: AdmittedApparatusBindingModel | None = None,
) -> AdmittedTrialEntryModel:
    return seal_admitted_trial_entry(
        plan_entry_id=entry_id,
        coordinate=TrialCoordinateModel(condition_id=condition_id),
        run_id=run_id,
        selections=[
            AdmittedSelectionRecordModel(
                variation_point_id="point-a",
                origin_policy_id="policy-a",
                origin_policy_kind="fixed",
                outcome={"kind": "member", "member_id": "variant-a"},
            )
        ],
        bindings=[_binding(condition_id)],
        stochastic_draws=[_draw(control_id, draw_condition_id or condition_id)],
        apparatus=apparatus or _apparatus(),
        execution_controls=AdmittedExecutionControlModel(
            attempt_timeout_seconds=600,
            on_timeout="cleanup-and-fail",
            on_cancellation="cleanup-and-fail",
            cleanup_plan_ref=cleanup_ref,
        ),
        instantiation_provenance=AdmittedInstantiationProvenanceModel(
            plan_id=provenance_plan_id, plan_entry_id=entry_id, run_id=run_id, scenario_family_id=provenance_family_id
        ),
    )


def _execution_controls(cleanup_ref: str = "cleanup-a") -> AdmittedExecutionControlModel:
    return AdmittedExecutionControlModel(
        attempt_timeout_seconds=600,
        on_timeout="cleanup-and-fail",
        on_cancellation="cleanup-and-fail",
        cleanup_plan_ref=cleanup_ref,
    )


def _seal_entry(**overrides: object) -> AdmittedTrialEntryModel:
    fields: dict[str, object] = {
        "plan_entry_id": "entry-a",
        "coordinate": TrialCoordinateModel(condition_id="baseline"),
        "run_id": "run-a",
        "selections": [
            AdmittedSelectionRecordModel(
                variation_point_id="point-a",
                origin_policy_id="policy-a",
                origin_policy_kind="fixed",
                outcome={"kind": "member", "member_id": "variant-a"},
            )
        ],
        "bindings": [_binding()],
        "stochastic_draws": [_draw()],
        "apparatus": _apparatus(),
        "execution_controls": _execution_controls(),
        "instantiation_provenance": AdmittedInstantiationProvenanceModel(
            plan_id="plan-a", plan_entry_id="entry-a", run_id="run-a", scenario_family_id="family-a"
        ),
    }
    fields.update(overrides)
    return seal_admitted_trial_entry(**fields)


def _plan(**overrides: object) -> AdmittedTrialPlanModel:
    entries = overrides.pop("entries", {"entry-a": _entry()})
    cleanup_plans = overrides.pop("cleanup_plans", {"cleanup-a": _cleanup_plan("cleanup-a", "entry-a", "run-a")})
    fields: dict[str, object] = {
        "plan_id": "plan-a",
        "profiles": _profiles(),
        "input_refs": _input_refs(),
        "stochastic_controls": {"control-a": _control()},
        "cleanup_plans": cleanup_plans,
        "entries": entries,
        "admission": AdmittedTrialPlanAdmissionModel(admitted_at_stage="admitted-sealed", entry_count=len(entries)),
    }
    fields.update(overrides)
    return seal_admitted_trial_plan(**fields)


# --- positive path -----------------------------------------------------------


def test_sealed_plan_round_trips_and_binds_its_content() -> None:
    plan = _plan()

    round_tripped = AdmittedTrialPlanModel.model_validate(plan.model_dump(mode="json"))

    assert round_tripped.plan_digest == plan.plan_digest
    assert round_tripped.entries["entry-a"].entry_digest.startswith("sha256:")


def test_serialized_key_order_does_not_change_plan_identity() -> None:
    plan = _plan()
    payload = plan.model_dump(mode="json")
    reordered = json.loads(json.dumps(payload, sort_keys=True))

    assert AdmittedTrialPlanModel.model_validate(reordered).plan_digest == plan.plan_digest


# --- identity distinctness ---------------------------------------------------


def test_entry_run_id_must_differ_from_plan_id() -> None:
    entry = _entry(entry_id="entry-a", run_id="plan-a", provenance_plan_id="plan-a")
    cleanup = {"cleanup-a": _cleanup_plan("cleanup-a", "entry-a", "plan-a")}
    with pytest.raises(ValidationError, match="plan_id must be distinct from every entry run_id"):
        _plan(entries={"entry-a": entry}, cleanup_plans=cleanup)


def test_entry_run_id_must_differ_from_plan_entry_id() -> None:
    with pytest.raises(ValidationError, match="run_id must be distinct from plan_entry_id"):
        _entry(entry_id="shared", run_id="shared")


def test_entries_must_have_unique_run_ids() -> None:
    entries = {
        "entry-a": _entry(entry_id="entry-a", run_id="run-shared"),
        "entry-b": _entry(entry_id="entry-b", run_id="run-shared", condition_id="treatment"),
    }
    entries["entry-b"] = _entry(
        entry_id="entry-b", run_id="run-shared", condition_id="treatment", cleanup_ref="cleanup-b"
    )
    cleanup = {
        "cleanup-a": _cleanup_plan("cleanup-a", "entry-a", "run-shared"),
        "cleanup-b": _cleanup_plan("cleanup-b", "entry-b", "run-shared"),
    }
    with pytest.raises(ValidationError, match="entry run_id must not contain duplicates"):
        _plan(entries=entries, cleanup_plans=cleanup)


def test_entries_must_have_unique_logical_coordinates() -> None:
    entries = {
        "entry-a": _entry(entry_id="entry-a", run_id="run-a", condition_id="baseline"),
        "entry-b": _entry(entry_id="entry-b", run_id="run-b", condition_id="baseline", cleanup_ref="cleanup-b"),
    }
    cleanup = {
        "cleanup-a": _cleanup_plan("cleanup-a", "entry-a", "run-a"),
        "cleanup-b": _cleanup_plan("cleanup-b", "entry-b", "run-b"),
    }
    with pytest.raises(ValidationError, match="unique logical coordinates"):
        _plan(entries=entries, cleanup_plans=cleanup)


# --- resolved-only and joins -------------------------------------------------


def test_stochastic_draw_must_resolve_to_a_control_with_executable_binding() -> None:
    controls = {"control-a": _control(executable=False)}
    with pytest.raises(ValidationError, match="executable binding"):
        _plan(stochastic_controls=controls)


def test_stochastic_draw_control_must_be_declared() -> None:
    controls = {"other-control": _control("other-control")}
    with pytest.raises(ValidationError, match="does not resolve to a plan control"):
        _plan(stochastic_controls=controls)


def test_cleanup_reference_must_bind_same_entry_and_run() -> None:
    cleanup = {"cleanup-a": _cleanup_plan("cleanup-a", "entry-a", "run-other")}
    with pytest.raises(ValidationError, match="same plan_entry_id and run_id"):
        _plan(cleanup_plans=cleanup)


def test_cleanup_plans_must_not_be_orphaned() -> None:
    cleanup = {
        "cleanup-a": _cleanup_plan("cleanup-a", "entry-a", "run-a"),
        "cleanup-orphan": _cleanup_plan("cleanup-orphan", "entry-a", "run-a"),
    }
    with pytest.raises(ValidationError, match="cleanup plans must be referenced"):
        _plan(cleanup_plans=cleanup)


def test_isolation_proof_entries_must_resolve() -> None:
    proof = SchedulerIsolationProofModel(
        schema_version="scheduler-isolation-proof/v1",
        proof_id="proof-a",
        plan_entry_ids=["entry-a", "ghost-entry"],
    )
    with pytest.raises(ValidationError, match="isolation proof references unknown plan entries"):
        _plan(isolation_proof=proof)


def test_admission_entry_count_must_match_entries() -> None:
    admission = AdmittedTrialPlanAdmissionModel(admitted_at_stage="admitted-sealed", entry_count=5)
    with pytest.raises(ValidationError, match="entry_count must equal the number of admitted entries"):
        _plan(admission=admission)


# --- integrity / tamper-evidence ---------------------------------------------


def test_tampered_entry_content_fails_closed() -> None:
    payload = _plan().model_dump(mode="json")
    payload["entries"]["entry-a"]["selections"][0]["outcome"]["member_id"] = "variant-tampered"
    with pytest.raises(ValidationError):
        AdmittedTrialPlanModel.model_validate(payload)


def test_tampered_plan_content_fails_closed() -> None:
    payload = _plan().model_dump(mode="json")
    payload["admission"]["limitations"].append("tampered-after-sealing")
    with pytest.raises(ValidationError, match="plan_digest does not match"):
        AdmittedTrialPlanModel.model_validate(payload)


def test_forbids_unknown_metadata_fields() -> None:
    payload = _plan().model_dump(mode="json")
    payload["environment"] = {"TOKEN": "secret"}
    with pytest.raises(ValidationError):
        AdmittedTrialPlanModel.model_validate(payload)


# --- admission-boundary invariants (codex review findings) -------------------


def test_unsupported_declared_profile_fails_closed() -> None:
    # C1-F1 / C2-F3: an unsupported profile is rejected by the closed literal, so
    # the published JSON Schema (not just the Python validator) fails closed.
    with pytest.raises(ValidationError, match="jcs-sha256-v1"):
        _profiles(canonicalization_profile="sha3-512-v9")


def test_apparatus_manifest_refs_must_be_digest_pinned() -> None:
    # F2/F4: an admitted apparatus selection must pin a concrete manifest digest,
    # not an id/version-only reference an attacker could swap under.
    plain_ref = ExperimentManifestReferenceModel(ref_kind="manifest", ref_id="backend-a", ref_version="1")
    with pytest.raises(ValidationError, match="manifest references must be digest-pinned"):
        _apparatus(manifest_refs=[plain_ref])


def test_stochastic_draw_coordinate_must_match_entry() -> None:
    # F3: a draw addressed to a different logical coordinate than its entry
    # corrupts deterministic draw provenance and must fail closed.
    entry = _entry(draw_condition_id="treatment")
    with pytest.raises(ValidationError, match="trial_coordinate must equal the enclosing entry coordinate"):
        _plan(entries={"entry-a": entry})


def test_parallel_isolation_rejects_shared_resources() -> None:
    # F5: bounded parallelism must not authorize entries that own the same
    # resource, even with an otherwise complete isolation proof.
    entries = {
        "entry-a": _entry(entry_id="entry-a", run_id="run-a", condition_id="baseline", cleanup_ref="cleanup-a"),
        "entry-b": _entry(entry_id="entry-b", run_id="run-b", condition_id="treatment", cleanup_ref="cleanup-b"),
    }
    shared_resource_cleanup = {
        "cleanup-a": _cleanup_plan("cleanup-a", "entry-a", "run-a", resource="a"),
        "cleanup-b": _cleanup_plan("cleanup-b", "entry-b", "run-b", resource="a"),
    }
    proof = _parallel_proof(["entry-a", "entry-b"])
    with pytest.raises(ValidationError, match="parallel entries that share resources"):
        _plan(entries=entries, cleanup_plans=shared_resource_cleanup, isolation_proof=proof)


def test_parallel_isolation_accepts_disjoint_resources() -> None:
    entries = {
        "entry-a": _entry(entry_id="entry-a", run_id="run-a", condition_id="baseline", cleanup_ref="cleanup-a"),
        "entry-b": _entry(entry_id="entry-b", run_id="run-b", condition_id="treatment", cleanup_ref="cleanup-b"),
    }
    disjoint_cleanup = {
        "cleanup-a": _cleanup_plan("cleanup-a", "entry-a", "run-a", resource="a"),
        "cleanup-b": _cleanup_plan("cleanup-b", "entry-b", "run-b", resource="b"),
    }
    plan = _plan(
        entries=entries,
        cleanup_plans=disjoint_cleanup,
        isolation_proof=_parallel_proof(["entry-a", "entry-b"]),
    )
    assert plan.isolation_proof is not None
    assert plan.isolation_proof.requested_parallelism == 2


def test_random_stream_profile_must_match_control_binding() -> None:
    # C2-F1: the plan-declared random-stream profile must not contradict the
    # executable control's profile_ref.
    controls = {"control-a": _control(profile_ref_id="some-other-profile-v1")}
    with pytest.raises(ValidationError, match="must equal the plan random_stream_profile"):
        _plan(stochastic_controls=controls)


def test_binding_condition_must_match_entry_coordinate() -> None:
    # C2-F1: a binding descriptor's source condition must not contradict the
    # entry's logical coordinate.
    entry = seal_admitted_trial_entry(
        plan_entry_id="entry-a",
        coordinate=TrialCoordinateModel(condition_id="baseline"),
        run_id="run-a",
        bindings=[_binding(condition_id="treatment")],
        apparatus=_apparatus(),
        execution_controls=AdmittedExecutionControlModel(
            attempt_timeout_seconds=600,
            on_timeout="cleanup-and-fail",
            on_cancellation="cleanup-and-fail",
            cleanup_plan_ref="cleanup-a",
        ),
        instantiation_provenance=AdmittedInstantiationProvenanceModel(
            plan_id="plan-a", plan_entry_id="entry-a", run_id="run-a", scenario_family_id="family-a"
        ),
    )
    with pytest.raises(ValidationError, match="source_condition_id must equal the entry coordinate"):
        _plan(entries={"entry-a": entry})


def test_scenario_binding_family_must_match_pinned_family() -> None:
    # C2-F1: a scenario-plane binding must target the pinned scenario family.
    entry = seal_admitted_trial_entry(
        plan_entry_id="entry-a",
        coordinate=TrialCoordinateModel(condition_id="baseline"),
        run_id="run-a",
        bindings=[_binding(condition_id="baseline", family_id="other-family")],
        apparatus=_apparatus(),
        execution_controls=AdmittedExecutionControlModel(
            attempt_timeout_seconds=600,
            on_timeout="cleanup-and-fail",
            on_cancellation="cleanup-and-fail",
            cleanup_plan_ref="cleanup-a",
        ),
        instantiation_provenance=AdmittedInstantiationProvenanceModel(
            plan_id="plan-a", plan_entry_id="entry-a", run_id="run-a", scenario_family_id="family-a"
        ),
    )
    with pytest.raises(ValidationError, match="must equal the pinned scenario family"):
        _plan(entries={"entry-a": entry})


def test_admission_stage_is_a_closed_successful_state() -> None:
    # C2-F2: a caller cannot seal a plan marked partial/failed.
    with pytest.raises(ValidationError, match="admitted-sealed"):
        AdmittedTrialPlanAdmissionModel(admitted_at_stage="partial", entry_count=1)


# --- validator failure-branch coverage (test-quality review cycle 1) ---------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"stochastic_controls": {"wrong": _control("control-a")}}, "stochastic_controls map key must equal"),
        (
            {"cleanup_plans": {"wrong": _cleanup_plan("cleanup-a", "entry-a", "run-a")}},
            "cleanup_plans map key must equal",
        ),
        ({"entries": {"wrong": _entry(entry_id="entry-a")}}, "entries map key must equal"),
    ],
)
def test_plan_map_keys_must_equal_embedded_ids(kwargs: dict, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        _plan(**kwargs)


def test_cross_entry_run_id_plan_entry_id_collision() -> None:
    entries = {
        "entry-a": _entry(entry_id="entry-a", run_id="run-a"),
        "entry-b": _entry(entry_id="entry-b", run_id="entry-a", condition_id="treatment", cleanup_ref="cleanup-b"),
    }
    cleanup = {
        "cleanup-a": _cleanup_plan("cleanup-a", "entry-a", "run-a", resource="a"),
        "cleanup-b": _cleanup_plan("cleanup-b", "entry-b", "entry-a", resource="b"),
    }
    with pytest.raises(ValidationError, match="run_id must be distinct from every plan_entry_id"):
        _plan(entries=entries, cleanup_plans=cleanup)


def test_provenance_plan_id_must_equal_plan_id() -> None:
    entries = {"entry-a": _entry(provenance_plan_id="other-plan")}
    with pytest.raises(ValidationError, match="instantiation_provenance plan_id must equal the admitted plan_id"):
        _plan(entries=entries)


def test_provenance_family_id_must_equal_pinned_family() -> None:
    entries = {"entry-a": _entry(provenance_family_id="other-family")}
    with pytest.raises(ValidationError, match="scenario_family_id must equal the pinned family ref"):
        _plan(entries=entries)


def test_dangling_cleanup_plan_ref_is_rejected() -> None:
    entries = {"entry-a": _entry(cleanup_ref="ghost-cleanup")}
    with pytest.raises(ValidationError, match="does not resolve to a plan cleanup block"):
        _plan(entries=entries)


def test_stochastic_draw_namespace_must_match_control_binding() -> None:
    entry = _seal_entry(stochastic_draws=[_draw(namespace="other-namespace")])
    with pytest.raises(ValidationError, match="namespace must match its control binding namespace"):
        _plan(entries={"entry-a": entry})


def test_duplicate_selection_variation_point_is_rejected() -> None:
    selection = AdmittedSelectionRecordModel(
        variation_point_id="point-a",
        origin_policy_id="policy-a",
        origin_policy_kind="fixed",
        outcome={"kind": "member", "member_id": "variant-a"},
    )
    with pytest.raises(ValidationError, match="selection variation_point_id must not contain duplicates"):
        _seal_entry(selections=[selection, selection])


def test_rejection_exhausted_draw_is_rejected() -> None:
    exhausted = RandomStreamDrawRecordModel(
        control_id="control-a",
        address=StreamAddressModel(
            namespace="study-namespace",
            trial_coordinate=TrialCoordinateModel(condition_id="baseline"),
            selection_policy_id="policy-a",
            variation_point_id="point-a",
            draw_purpose="condition-assignment",
            local_coordinate=0,
        ),
        transform_id="bounded-integer",
        transform_version="1",
        local_coordinate=0,
        outcome=None,
        rejection_exhausted=True,
    )
    with pytest.raises(ValidationError, match="must record a resolved outcome, not exhaustion"):
        _seal_entry(stochastic_draws=[exhausted])


def test_entry_level_provenance_mismatch_is_rejected() -> None:
    provenance = AdmittedInstantiationProvenanceModel(
        plan_id="plan-a", plan_entry_id="mismatch", run_id="run-a", scenario_family_id="family-a"
    )
    with pytest.raises(ValidationError, match="instantiation_provenance must match the entry plan_entry_id and run_id"):
        _seal_entry(instantiation_provenance=provenance)


@pytest.mark.parametrize(
    ("override", "match"),
    [
        (
            {"authoring_input_ref": ExperimentReferenceModel(ref_kind="other", ref_id="x", ref_digest=_digest("ab"))},
            "authoring_input_ref must have ref_kind",
        ),
        (
            {"authoring_input_ref": ExperimentReferenceModel(ref_kind="authoring-input", ref_id="x")},
            "authoring_input_ref must pin a ref_digest",
        ),
        (
            {
                "binding_descriptor_set_ref": ExperimentReferenceModel(
                    ref_kind="study", ref_id="x", ref_digest=_digest("ef")
                )
            },
            "binding_descriptor_set_ref must have ref_kind",
        ),
        (
            {"binding_descriptor_set_ref": ExperimentReferenceModel(ref_kind="other", ref_id="x")},
            "binding_descriptor_set_ref must pin a ref_digest",
        ),
        (
            {
                "scenario_family_ref": {
                    "ref_kind": "scenario-family",
                    "ref_id": "family-a",
                    "ref_version": "expanded-scenario-family/v1",
                }
            },
            "ref_digest",
        ),
        ({"study_ref": ExperimentReferenceModel(ref_kind="other", ref_id="s")}, "study_ref must have ref_kind"),
        (
            {"associated_artifact_set_ref": ExperimentReferenceModel(ref_kind="other", ref_id="a")},
            "associated_artifact_set_ref must pin a ref_digest",
        ),
    ],
)
def test_input_refs_validation_branches(override: dict, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        _input_refs(**override)


def test_apparatus_capability_refs_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="apparatus capability_refs must be unique"):
        _apparatus(capability_refs=["cap:x", "cap:x"])


# --- publication -------------------------------------------------------------


def test_schema_bundle_publishes_admitted_trial_plan_contract() -> None:
    bundle = schema_bundle()

    assert CONTRACT_ID in bundle
    assert bundle[CONTRACT_ID]["additionalProperties"] is False
    assert any(
        invariant["validator"].endswith("AdmittedTrialPlanModel._validate_plan")
        for invariant in bundle[CONTRACT_ID]["x-raes-invariants"]
    )


def test_admitted_plan_ingress_reconstructs_and_revalidates_complete_plan() -> None:
    fixture = FIXTURES_ROOT / "plans" / CONTRACT_ID / "valid" / "minimal.json"

    admitted = parse_admitted_trial_plan_json(fixture.read_bytes())

    assert admitted.plan_id == "plan-a"
    assert tuple(admitted.entries) == ("entry-a",)


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b'{"plan_id":"first","plan_id":"second"}', "duplicate-member"),
        (b"[]", "invalid-root"),
        (b'{"value":NaN}', "non-finite-number"),
        (b"", "empty-input"),
    ],
)
def test_admitted_plan_ingress_rejects_ambiguous_or_non_contract_json(raw: bytes, code: str) -> None:
    with pytest.raises(AdmittedTrialPlanIngressError) as error:
        parse_admitted_trial_plan_json(raw)

    assert error.value.code == code


def test_admitted_plan_ingress_rejects_oversized_input_before_parsing() -> None:
    raw = b"{" + b" " * MAX_ADMITTED_TRIAL_PLAN_BYTES + b"}"

    with pytest.raises(AdmittedTrialPlanIngressError) as error:
        parse_admitted_trial_plan_json(raw)

    assert error.value.code == "input-too-large"


def test_admitted_trial_plan_fixture_corpora_validate() -> None:
    validator = Draft202012Validator(schema_bundle()[CONTRACT_ID])
    fixture_dir = FIXTURES_ROOT / "plans" / CONTRACT_ID
    valid = sorted((fixture_dir / "valid").glob("*.json"))
    invalid = sorted((fixture_dir / "invalid").glob("*.json"))

    assert valid, "missing valid fixtures"
    assert invalid, "missing invalid fixtures"
    for path in valid:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert not list(validator.iter_errors(payload)), path.name
        AdmittedTrialPlanModel.model_validate(payload)
    for path in invalid:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert list(validator.iter_errors(payload)), path.name
