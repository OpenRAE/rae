"""Versioned handoffs reconstruct published children and reject ambiguous bytes."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from assigned_trial_inputs import ORIGINAL_INPUTS, REPLACEMENT_INPUTS, write_inputs
from installed_assigned_trial_consumer import load_inputs
from paths import REPO_ROOT
from raes_contracts.assigned_trial import TrialAssignmentModel, TrialOutcomeModel, trial_attempt_id
from raes_contracts.errors import InvalidInputError
from raes_processor.trial_realization import realize_admitted_trial_entry


@pytest.fixture(scope="module")
def inputs_dir(tmp_path_factory):
    directory = tmp_path_factory.mktemp("assigned-trial")
    write_inputs(directory)
    return directory


@pytest.fixture(scope="module")
def assignment(inputs_dir):
    inputs, _ = load_inputs(inputs_dir / ORIGINAL_INPUTS)
    first = next(iter(inputs.plan.entries))
    realized = realize_admitted_trial_entry(inputs=inputs, plan_entry_id=first, target_name="trial")
    start = datetime(2026, 11, 3, tzinfo=UTC)
    return TrialAssignmentModel(
        plan=inputs.plan,
        plan_entry_id=first,
        execution_attempt_id=trial_attempt_id(inputs.plan.plan_id, first, 1),
        attempt=1,
        started_at=start.isoformat(),
        deadline=(
            start + timedelta(seconds=inputs.plan.entries[first].execution_controls.attempt_timeout_seconds)
        ).isoformat(),
        target_scope="target:trial",
        owner_id="worker-a",
        instantiated_sdl_digest=realized.snapshot_digest,
        processor_plan_refs=realized.processor_plan_refs,
    )


def test_original_portable_sources_reconstruct_the_exact_assignment(assignment):
    restored = TrialAssignmentModel.from_json(assignment.model_dump_json())
    assert restored == assignment
    assert restored.content_digest == assignment.content_digest


def test_installed_replacement_fixture_reconstructs_original_compiler_authority(inputs_dir):
    from installed_assigned_trial_consumer import replacement_request
    from raes_processor.trial_compiler import compile_admitted_trial_plan

    path = inputs_dir / REPLACEMENT_INPUTS
    inputs, _ = load_inputs(path)
    result = compile_admitted_trial_plan(replacement_request(inputs, json.loads(path.read_text())))
    assert result.plan is not None, result.diagnostics
    assert result.plan.model_dump(mode="json") == inputs.plan.model_dump(mode="json")
    assert len(inputs.plan.entries) == 1
    assert inputs.plan.replacement_policy.max_replacements == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "assigned-trial/v2"),
        ("owner_generation", True),
        ("owner_generation", 2),
        ("attempt", "1"),
        ("execution_attempt_id", "worker-created-attempt"),
        ("credential", "unapproved-value"),
        ("effective_parallelism", 17),
        ("lease_evidence_refs", ["lease:unexpected-serial"]),
        ("isolation_proof_ref", "foreign-proof"),
    ],
)
def test_assignment_rejects_unsupported_or_untyped_fields_before_binding(assignment, field, value):
    payload = assignment.model_dump(mode="json")
    payload[field] = value
    encoded = json.dumps(payload)
    with pytest.raises(InvalidInputError) as refusal:
        TrialAssignmentModel.from_json(encoded)
    assert "unapproved-value" not in str(refusal.value)


def test_assignment_json_refuses_duplicate_members(assignment):
    source = assignment.model_dump_json()
    duplicated = '{"owner_id":"other-owner",' + source[1:]
    with pytest.raises(InvalidInputError):
        TrialAssignmentModel.from_json(duplicated)


def test_incomplete_outcome_requires_no_fabricated_receipt(assignment):
    outcome = TrialOutcomeModel(assignment_digest=assignment.content_digest, progress="indeterminate")
    assert not TrialOutcomeModel.from_json(outcome.model_dump_json()).facts
    completed = {**outcome.model_dump(mode="json"), "progress": "completed"}
    with pytest.raises(ValueError):
        TrialOutcomeModel.model_validate(completed)


@pytest.mark.parametrize("omit_facts", [False, True])
def test_published_schema_rejects_invented_completion_without_python_validation(omit_facts):
    from jsonschema import Draft202012Validator

    schema = json.loads((REPO_ROOT / "contracts/schemas/control-plane/trial-outcome-v1.json").read_text())
    path = REPO_ROOT / "contracts/fixtures/control-plane/trial-outcome-v1/invalid/invented-completion.json"
    payload = json.loads(path.read_text())
    if omit_facts:
        payload.pop("facts")
    assert list(Draft202012Validator(schema).iter_errors(payload))


@pytest.mark.parametrize("change", ["coerced-cessation", "running-terminal-fact"])
def test_execution_facts_cannot_coerce_cessation_or_invent_a_terminal_cut(assignment, change):
    from raes_contracts.contracts import RuntimeSnapshotEnvelopeModel

    observation = {"kind": "execution", "state": "succeeded", "ceased": True, "evidence": []}
    if change == "coerced-cessation":
        observation["ceased"] = "true"
    else:
        observation.update(state="running", ceased=False)
    payload = {
        "schema_version": "trial-outcome/v1",
        "assignment_digest": assignment.content_digest,
        "progress": "indeterminate",
        "facts": [
            {
                "observation": observation,
                "observed_at": assignment.started_at,
                "execution_snapshot": RuntimeSnapshotEnvelopeModel().model_dump(mode="json"),
            }
        ],
    }
    encoded = json.dumps(payload)
    with pytest.raises(InvalidInputError):
        TrialOutcomeModel.from_json(encoded)


def test_new_carriers_are_in_the_published_schema_bundle():
    from raes_schemas import schema_bundle

    bundle = schema_bundle()
    for name in ("assigned-trial-v1", "assigned-trial-control-v1", "trial-outcome-v1"):
        expected = json.loads((REPO_ROOT / "contracts/schemas/control-plane" / (name + ".json")).read_text())
        assert bundle[name] == expected


def test_portable_conformance_does_not_claim_native_execution_truth(assignment):
    from raes_conformance.conformance.validators import contract_validation_strength, validate_contract_payload

    for name in ("assigned-trial-v1", "assigned-trial-control-v1", "trial-outcome-v1"):
        assert contract_validation_strength(name) == "structural"
    assert not validate_contract_payload("assigned-trial-v1", assignment.model_dump(mode="json"))
    changed = assignment.model_dump(mode="json")
    changed["execution_attempt_id"] = "another-attempt"
    assert validate_contract_payload("assigned-trial-v1", changed)
