"""ADR-112 inject invocation, per-binding readback, participant correlation and backend declaration."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_backend_protocols.operation_supervision import require_inject_occurrence_provider
from raes_backend_stubs.manifest import REFERENCE_BACKEND_SUPPORTED_CONTRACT_VERSIONS as STUB_CONTRACTS
from raes_backend_stubs.manifest import create_stub_manifest
from raes_contracts import contracts
from raes_contracts.manifest_authority import BACKEND_SUPPORTED_CONTRACT_IDS
from raes_contracts.versions import BACKEND_OPERATION_CONTRACT_IDS, INJECT_OCCURRENCE_BACKEND_CONTRACT_IDS
from raes_reference_backend.manifest import REFERENCE_BACKEND_SUPPORTED_CONTRACT_VERSIONS as REFERENCE_CONTRACTS

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "contracts/fixtures/control-plane"
MODELS = {
    "inject-occurrence-outcome-v1": contracts.InjectOccurrenceOutcomeModel,
    "inject-occurrence-correlation-v1": contracts.InjectOccurrenceCorrelationModel,
}
CORPUS = [
    (contract_id, category, path.stem)
    for contract_id in MODELS
    for category in ("valid", "invalid", "context-invalid")
    for path in sorted((FIXTURES / contract_id / category).glob("*.json"))
]
# Each context-invalid fixture breaks one rule, so it must be refused for that rule's reason.
CONTEXT_REASONS = {
    "acceptance-as-settlement": "settles",
    "applied-without-readback": "readback basis",
    "successful-no-op": "no successful no-op",
    "unproven-refusal": "settles",
    "foreign-outcome": "same occurrence",
    "request-as-occurrence": "joins an inject occurrence",
}
# Each valid outcome answers one claimed occurrence through one backend invocation.
JOINS = {
    "participant-free-environment": ("participant-free-environment", "inject-release"),
    "refused": ("participant-free-environment", "inject-release"),
    "known-partial": ("scheduled-fan-out", "inject-handover"),
    "indeterminate": ("scheduled-fan-out", "inject-handover"),
    "unceased-effect": ("participant-free-environment", "inject-release"),
}
DECLARED = (*BACKEND_OPERATION_CONTRACT_IDS, *INJECT_OCCURRENCE_BACKEND_CONTRACT_IDS)
EVIDENCE = {"contract_id": "runtime-snapshot-v1", "artifact_id": "evidence-1", "digest": "sha256:" + "1" * 64}
HANDOVER = "orchestration.inject-binding.workstation.handover"
WORKSTATION = "provision.node.workstation"
FORGED = "sha256:" + "0" * 64
PROVEN_ABSENT = {"effect": "absent", "cessation_established": True, "evidence_refs": [EVIDENCE]}
WILLING = {"kind": "admission", "disposition": "willing", "capability_digest": "sha256:" + "e" * 64, "reason": None}
ADMISSION_REFUSAL = {**WILLING, "disposition": "refused", "reason": "context-refused"}
RECONCILIATION = {
    "kind": "reconciliation",
    "control_id": "control-1",
    "control_digest": "sha256:" + "c" * 64,
    "effects": PROVEN_ABSENT,
}
PARTIAL_IN_VAULT = {
    "effect": "partial",
    "cessation_established": True,
    "evidence_refs": [EVIDENCE],
    "residual_scope": ["orchestration.inject-binding.vault.wipe"],
    "residual_state": EVIDENCE,
}


def fixture(contract_id: str, category: str, name: str) -> dict:
    return json.loads((FIXTURES / contract_id / category / f"{name}.json").read_text())


def schema(contract_id: str) -> dict:
    return json.loads((ROOT / f"contracts/schemas/control-plane/{contract_id}.json").read_text())


def occurrence(name: str) -> contracts.InjectOccurrenceModel:
    return contracts.InjectOccurrenceModel.model_validate(fixture("inject-occurrence-v1", "valid", name))


def invocation(name: str) -> contracts.BackendOperationRequestModel:
    return contracts.BackendOperationRequestModel.model_validate(fixture("backend-operation-request-v1", "valid", name))


def outcome(name: str, payload: dict | None = None) -> contracts.InjectOccurrenceOutcomeModel:
    return contracts.InjectOccurrenceOutcomeModel.model_validate(
        payload or fixture("inject-occurrence-outcome-v1", "valid", name)
    )


def applied_release() -> tuple[
    contracts.InjectOccurrenceModel, contracts.BackendOperationRequestModel, contracts.InjectOccurrenceOutcomeModel
]:
    """The participant-free occurrence, its release invocation and the applied readback that answers it."""

    return (
        occurrence("participant-free-environment"),
        invocation("inject-release"),
        outcome("participant-free-environment"),
    )


def changed(payload: dict, path: tuple[str | int, ...], value: object) -> dict:
    payload = copy.deepcopy(payload)
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return payload


def binding_outcome(effect: str, ceased: bool) -> contracts.InjectBindingOutcomeModel:
    known = effect != "unknown"
    residual = {"residual_scope": [HANDOVER], "residual_state": EVIDENCE} if effect == "partial" else {}
    return contracts.InjectBindingOutcomeModel.model_validate(
        {
            "binding": {
                "binding": HANDOVER,
                "node": WORKSTATION,
                "instance": "workstation-1",
                "revision": "realization-r3",
            },
            "effects": {
                "effect": effect,
                "cessation_established": ceased,
                "evidence_refs": [EVIDENCE] if known else [],
                **residual,
            },
            "readback": EVIDENCE if effect in {"complete", "partial"} else None,
        }
    )


def _provider() -> SimpleNamespace:
    """Installed call shapes only; the declaration check invokes nothing."""

    calls = ("check_operation", "start_operation", "observe_operation", "cancel_operation", "reconcile_operation")
    return SimpleNamespace(operation_capabilities=lambda: None, **dict.fromkeys(calls, lambda request: request))


@pytest.mark.parametrize(("contract_id", "category", "name"), CORPUS)
def test_fixture_corpus_separates_structure_from_contextual_claims(contract_id, category, name):
    payload = fixture(contract_id, category, name)
    model = MODELS[contract_id]

    assert Draft202012Validator(schema(contract_id)).is_valid(payload) is (category != "invalid")
    if category == "valid":
        assert model.model_validate(payload).model_dump(mode="json") == payload
    else:
        reason = CONTEXT_REASONS[name] if category == "context-invalid" else None
        with pytest.raises(ValidationError, match=reason):
            model.model_validate(payload)


@pytest.mark.parametrize(
    ("contract_id", "validator"),
    [
        ("inject-occurrence-outcome-v1", "validate_inject_occurrence_outcome"),
        ("inject-occurrence-correlation-v1", "validate_inject_occurrence_correlation"),
    ],
)
def test_published_schemas_are_the_reference_bundle_with_semantic_bindings(contract_id, validator):
    published = schema(contract_id)
    invariants = published["x-raes-invariants"]

    assert published == contracts.schema_bundle()[contract_id]
    assert published["x-raes-semantic-profile"]["required"] is True
    assert f"raes_contracts.contracts.{validator}" in {item["validator"] for item in invariants}
    # Each invariant reads the instance of the schema that publishes it.
    assert all(contract_id in {item["contract_id"] for item in invariant["inputs"]} for invariant in invariants)


@pytest.mark.parametrize("name", sorted(JOINS))
def test_every_valid_outcome_answers_its_exact_invocation(name):
    occurrence_name, invocation_name = JOINS[name]

    contracts.validate_inject_occurrence_outcome(
        occurrence(occurrence_name), invocation(invocation_name), outcome(name)
    )


@pytest.mark.parametrize(
    ("occurrence_name", "invocation_name", "path", "value", "message"),
    [
        pytest.param(
            "participant-free-environment",
            "inject-release",
            ("command", "digest"),
            "sha256:" + "0" * 64,
            "exact claimed",
            id="changed-occurrence-commitment",
        ),
        pytest.param(
            "participant-free-environment",
            "inject-release",
            ("command", "artifact_id"),
            "release-occurrence-2",
            "exact claimed",
            id="another-occurrence",
        ),
        pytest.param(
            "participant-free-environment",
            "inject-release",
            ("binding", "operation_id"),
            "operation-release-2",
            "admission context",
            id="another-operation",
        ),
        pytest.param(
            "participant-free-environment",
            "inject-release",
            ("binding", "context", "actor_id"),
            "researcher-2",
            "admission context",
            id="another-actor",
        ),
        pytest.param(
            "participant-free-environment",
            "inject-release",
            ("requirement_refs",),
            [],
            "evidence requirement",
            id="dropped-evidence-requirement",
        ),
        pytest.param(
            "participant-free-environment",
            "inject-release",
            ("binding", "attempt_id"),
            "release-occurrence-1",
            "distinct from the claims",
            id="attempt-reuses-occurrence",
        ),
        pytest.param(
            "participant-free-environment",
            "inject-release",
            ("binding", "attempt_id"),
            "operation-release-1",
            "distinct from the claims",
            id="attempt-reuses-operation",
        ),
        pytest.param(
            "participant-free-environment",
            "inject-release",
            ("binding", "invocation_id"),
            "researcher-release-key-1",
            "distinct from the claims",
            id="invocation-reuses-request-key",
        ),
        pytest.param(
            "scheduled-fan-out",
            "inject-handover",
            ("binding", "attempt_id"),
            "day-one/shift-change/1",
            "distinct from the claims",
            id="attempt-reuses-slot",
        ),
        pytest.param(
            "scheduled-fan-out",
            "inject-handover",
            ("binding", "effect_scope", "addresses"),
            ["orchestration.inject-binding.workstation.other"],
            "cover every selected inject binding",
            id="narrowed-scope-misses-a-binding",
        ),
    ],
)
def test_invocation_commands_the_exact_claimed_occurrence(occurrence_name, invocation_name, path, value, message):
    payload = changed(fixture("backend-operation-request-v1", "valid", invocation_name), path, value)
    request = contracts.BackendOperationRequestModel.model_validate(payload)
    claim = occurrence(occurrence_name)

    with pytest.raises(ValueError, match=message):
        contracts.require_inject_occurrence_invocation(claim, request)


@pytest.mark.parametrize(
    "join", [contracts.validate_inject_occurrence_outcome, contracts.inject_occurrence_correlation]
)
def test_readback_for_another_invocation_cannot_settle_or_correlate(join):
    claim, handover, release_readback = (
        occurrence("scheduled-fan-out"),
        invocation("inject-handover"),
        outcome("participant-free-environment"),
    )

    with pytest.raises(ValueError, match="binding mismatch"):
        join(claim, handover, release_readback)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        pytest.param(("bindings",), slice(None, None, -1), "request order", id="reordered-bindings"),
        pytest.param(("bindings",), slice(1, None), "request order", id="missing-binding"),
        pytest.param(("response", "request_digest"), FORGED, "commitment", id="stale-request"),
        pytest.param(("occurrence", "digest"), FORGED, "names another occurrence", id="another-occurrence"),
        pytest.param(
            ("bindings", 0, "effects"),
            PARTIAL_IN_VAULT,
            "exceed the admitted resource scope",
            id="residual-out-of-scope",
        ),
    ],
)
def test_readback_must_answer_the_invocation_for_every_selected_binding(path, value, message):
    payload = fixture("inject-occurrence-outcome-v1", "valid", "indeterminate")
    replacement = payload["bindings"][value] if isinstance(value, slice) else value

    claim, handover = occurrence("scheduled-fan-out"), invocation("inject-handover")
    readback = outcome("indeterminate", changed(payload, path, replacement))

    with pytest.raises(ValueError, match=message):
        contracts.validate_inject_occurrence_outcome(claim, handover, readback)


def test_binding_residual_effects_inside_the_admitted_scope_are_accepted():
    in_scope = {**PARTIAL_IN_VAULT, "residual_scope": [HANDOVER]}
    payload = changed(
        fixture("inject-occurrence-outcome-v1", "valid", "indeterminate"), ("bindings", 0, "effects"), in_scope
    )

    contracts.validate_inject_occurrence_outcome(
        occurrence("scheduled-fan-out"), invocation("inject-handover"), outcome("indeterminate", payload)
    )


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        ([("complete", True), ("complete", True)], "effect-applied"),
        ([("absent", True), ("absent", True)], "effect-absent"),
        ([("complete", True), ("absent", True)], "known-partial"),
        ([("partial", True)], "known-partial"),
        ([("complete", True), ("unknown", False)], "indeterminate"),
        ([("complete", False)], "indeterminate"),
        ([("absent", False)], "indeterminate"),
    ],
)
def test_fan_out_effect_aggregates_every_binding_fact(facts, expected):
    bindings = tuple(binding_outcome(effect, ceased) for effect, ceased in facts)

    assert contracts.inject_occurrence_effect(bindings) == expected


def test_an_empty_fan_out_has_no_effect_to_aggregate():
    with pytest.raises(ValueError, match="at least one reported binding"):
        contracts.inject_occurrence_effect(())


@pytest.mark.parametrize(
    ("base", "path", "value", "message"),
    [
        pytest.param(
            "refused", ("response", "message"), {"kind": "progress", "phase": "executing"}, "settles", id="progress"
        ),
        pytest.param("refused", ("response", "message"), WILLING, "settles", id="willing-admission"),
        # An admission refusal precedes dispatch, so EI-03 withdraws the occurrence instead of settling it.
        pytest.param("refused", ("response", "message"), ADMISSION_REFUSAL, "settles", id="admission-refusal"),
        # EI-04 appends reconciliation as linked evidence; even proven absence there settles nothing.
        pytest.param("refused", ("response", "message"), RECONCILIATION, "settles", id="reconciliation"),
        pytest.param("indeterminate", ("response", "message", "effects"), PROVEN_ABSENT, "disagree", id="disagreeing"),
        pytest.param("indeterminate", ("effect",), "known-partial", "aggregate", id="unaggregated-effect"),
        pytest.param(
            "refused", ("occurrence", "contract_id"), "inject-trigger-request-v1", "claimed inject", id="request-claim"
        ),
        pytest.param(
            "indeterminate", ("bindings", 1, "binding", "instance"), "workstation-1", "instance once", id="duplicate"
        ),
        pytest.param(
            "indeterminate",
            ("bindings", 1, "effects"),
            {**PARTIAL_IN_VAULT, "residual_scope": [HANDOVER]},
            "readback basis",
            id="partial-without-readback",
        ),
    ],
)
def test_outcome_model_refuses_unsettled_or_inconsistent_readback(base, path, value, message):
    payload = changed(fixture("inject-occurrence-outcome-v1", "valid", base), path, value)

    with pytest.raises(ValidationError, match=message):
        contracts.InjectOccurrenceOutcomeModel.model_validate(payload)


def test_correlation_joins_the_successful_applied_world_effect_and_its_result():
    claim, release, applied = applied_release()
    received = fixture("inject-occurrence-correlation-v1", "valid", "participant-free-environment")
    correlation = contracts.inject_occurrence_correlation(claim, release, applied)

    assert correlation.model_dump(mode="json") == received
    assert correlation.outcome.digest == contracts.inject_occurrence_outcome_digest(applied)
    assert correlation.result == applied.response.message.result
    contracts.validate_inject_occurrence_correlation(
        claim, release, applied, contracts.InjectOccurrenceCorrelationModel.model_validate(received)
    )


@pytest.mark.parametrize("field", ["occurrence", "outcome", "result"])
def test_a_received_correlation_must_equal_the_recomputed_join(field):
    received = fixture("inject-occurrence-correlation-v1", "valid", "participant-free-environment")
    forged = contracts.InjectOccurrenceCorrelationModel.model_validate(changed(received, (field, "digest"), FORGED))
    claim, release, applied = applied_release()

    with pytest.raises(ValueError, match="recomputed"):
        contracts.validate_inject_occurrence_correlation(claim, release, applied, forged)


def _failed_but_applied() -> contracts.InjectOccurrenceOutcomeModel:
    payload = fixture("inject-occurrence-outcome-v1", "valid", "participant-free-environment")
    message = payload["response"]["message"]
    message.update(proposed_state="failed", satisfaction="unsatisfied", release_gates_satisfied=False)
    return outcome("participant-free-environment", payload)


@pytest.mark.parametrize(
    ("occurrence_name", "invocation_name", "readback"),
    [
        pytest.param("participant-free-environment", "inject-release", lambda: outcome("refused"), id="refused"),
        pytest.param("participant-free-environment", "inject-release", _failed_but_applied, id="failed-applied"),
        pytest.param("scheduled-fan-out", "inject-handover", lambda: outcome("known-partial"), id="known-partial"),
        pytest.param("scheduled-fan-out", "inject-handover", lambda: outcome("indeterminate"), id="indeterminate"),
        pytest.param(
            "participant-free-environment", "inject-release", lambda: outcome("unceased-effect"), id="unceased"
        ),
    ],
)
def test_no_participant_join_without_a_successful_applied_world_effect(occurrence_name, invocation_name, readback):
    claim, request, settled = occurrence(occurrence_name), invocation(invocation_name), readback()

    with pytest.raises(ValueError, match="only a successful applied world effect"):
        contracts.inject_occurrence_correlation(claim, request, settled)


def _property_names(node: object) -> set[str]:
    if isinstance(node, dict):
        return set(node.get("properties", {})).union(*(_property_names(value) for value in node.values()))
    if isinstance(node, list):
        return set().union(*(_property_names(value) for value in node))
    return set()


@pytest.mark.parametrize("contract_id", sorted(MODELS))
def test_readback_and_correlation_carry_no_participant_identity(contract_id):
    names = _property_names(schema(contract_id))

    assert not [name for name in names if any(word in name for word in ("participant", "episode"))]


def test_backend_declaration_is_explicit_and_existing_backends_do_not_advertise_it():
    stub = create_stub_manifest()

    assert set(INJECT_OCCURRENCE_BACKEND_CONTRACT_IDS) <= set(BACKEND_SUPPORTED_CONTRACT_IDS)
    assert stub.orchestrator.supports_inject_bindings
    for declared in (stub.supported_contract_versions, STUB_CONTRACTS, REFERENCE_CONTRACTS):
        assert set(INJECT_OCCURRENCE_BACKEND_CONTRACT_IDS).isdisjoint(declared)
    provider = _provider()
    with pytest.raises(ValueError, match="inject occurrence contracts are not declared"):
        require_inject_occurrence_provider(provider, stub.supported_contract_versions)


@pytest.mark.parametrize(
    ("provider", "declared", "message"),
    [
        pytest.param(_provider(), BACKEND_OPERATION_CONTRACT_IDS, "inject occurrence", id="no-inject-opt-in"),
        pytest.param(
            _provider(), INJECT_OCCURRENCE_BACKEND_CONTRACT_IDS, "backend operation", id="no-operation-family"
        ),
        pytest.param(object(), DECLARED, "not installed", id="no-installed-protocol"),
        pytest.param(_provider(), (*DECLARED, "inject-trigger-request-v1"), "supported_contract", id="runtime-carrier"),
    ],
)
def test_inject_provider_check_requires_both_declarations_and_the_operation_protocol(provider, declared, message):
    with pytest.raises(ValueError, match=message):
        require_inject_occurrence_provider(provider, declared)


def test_declared_operation_provider_passes_the_inject_shape_check():
    provider = _provider()

    assert require_inject_occurrence_provider(provider, DECLARED) is provider
