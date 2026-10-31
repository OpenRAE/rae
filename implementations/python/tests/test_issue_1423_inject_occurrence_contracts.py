"""ADR-112 inject trigger requests and claimed occurrences: structure, claims and retries."""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes.parser import parse_sdl, parse_sdl_file
from raes_contracts import contracts
from raes_processor.compiler import compile_runtime_model

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "contracts/fixtures/control-plane"
MODELS = {
    "inject-trigger-request-v1": contracts.InjectTriggerRequestModel,
    "inject-occurrence-v1": contracts.InjectOccurrenceModel,
}
CORPUS = [
    (contract_id, category, path.stem)
    for contract_id in MODELS
    for category in ("valid", "invalid", "context-invalid")
    for path in sorted((FIXTURES / contract_id / category).glob("*.json"))
]
OWNERSHIP = "its node and the requested inject"
# Each context-invalid fixture breaks one rule, so it must be refused for that rule's reason.
CONTEXT_REASONS = {
    "ambiguous-instance": "binding/instance pair twice",
    "event-as-inject": "compiled orchestration inject address",
    "foreign-binding": OWNERSHIP,
    "namespaced-binding": OWNERSHIP,
    "provisioning-kind": "admitted as orchestration operations",
    "rebased-order": "without rebasing",
    "shared-identity": "must stay distinct",
}
# Importing the environment below under namespace ``mod`` compiles a second binding ending in ``.release``.
MODULE_HEADER = "module: {id: acme/release, version: 1.0.0, exports: {nodes: [host], injects: [release]}}\n"
IMPORT_HEADER = "imports: [{source: 'local:module.yaml', namespace: mod}]\n"
ENVIRONMENT_SDL = """name: external-trigger-environment
nodes:
  host:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    roles:
      operator: ops
    injects:
      release: operator
injects:
  release:
    description: Release the staged maintenance notice.
events:
  gate:
    injects: [release]
"""


def fixture(contract_id: str, category: str, name: str) -> dict:
    return json.loads((FIXTURES / contract_id / category / f"{name}.json").read_text())


def schema(contract_id: str) -> dict:
    return json.loads((ROOT / f"contracts/schemas/control-plane/{contract_id}.json").read_text())


def occurrence(name: str = "participant-free-environment") -> contracts.InjectOccurrenceModel:
    return contracts.InjectOccurrenceModel.model_validate(fixture("inject-occurrence-v1", "valid", name))


def fresh(
    base: contracts.InjectOccurrenceModel, *, actor: str | None = None, **claims
) -> contracts.InjectOccurrenceModel:
    """Return another claim on the same authored intent with the given claim identities.

    As in the fixtures, position N follows head ``order-head-<N-1>`` unless ``head`` names another.
    """
    payload = base.model_dump(mode="json")
    position = claims.get("position", base.order.position)
    head = claims.get("head", f"order-head-{position - 1}")
    payload["request"]["request_key"] = claims.get("key", base.request.request_key)
    payload["request"]["occurrence_id"] = claims.get("occurrence", base.request.occurrence_id)
    payload["request"]["expected_head"] = head
    payload["operation_id"] = claims.get("operation", base.operation_id)
    payload["order"].update(position=position, predecessor=head)
    payload["admission"]["actor_id"] = actor or base.admission.actor_id
    return contracts.InjectOccurrenceModel.model_validate(payload)


def changed(payload: dict, path: tuple[str, ...], value: object) -> dict:
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return payload


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


def test_published_schemas_are_the_reference_bundle_with_semantic_bindings():
    bundle = contracts.schema_bundle()
    for contract_id in MODELS:
        published = schema(contract_id)
        assert published == bundle[contract_id]
        assert published["x-raes-semantic-profile"]["required"] is True
    validators = {item["validator"] for item in bundle["inject-occurrence-v1"]["x-raes-invariants"]}
    assert "raes_contracts.contracts.validate_inject_occurrence_claims" in validators


def _property_names(node: object) -> set[str]:
    if isinstance(node, dict):
        names = set(node.get("properties", {}))
        return names.union(*(_property_names(value) for value in node.values()))
    if isinstance(node, list):
        return set().union(*(_property_names(value) for value in node))
    return set()


def test_participant_free_environment_trigger_names_only_compiled_orchestration_identities():
    model = compile_runtime_model(parse_sdl(ENVIRONMENT_SDL))
    claim = occurrence()
    request = claim.request

    assert not model.diagnostics
    assert not model.agent_specs
    assert not model.participant_behaviors
    assert not model.participant_inject_deliveries
    assert request.inject in model.injects
    assert {(item.binding, item.node) for item in request.bindings} <= {
        (address, binding.node_address) for address, binding in model.inject_bindings.items()
    }
    assert request.inject in model.events[request.placement.event].inject_addresses
    names = _property_names(schema("inject-occurrence-v1"))
    assert not [name for name in names if any(word in name for word in ("participant", "episode", "control"))]


def _with_header(header: str) -> str:
    name, body = ENVIRONMENT_SDL.split("\n", 1)
    return f"{name}\n{header}{body}"


def _selects(inject: str, binding) -> bool:
    payload = fixture("inject-trigger-request-v1", "valid", "participant-free-environment")
    payload["inject"] = inject
    payload["bindings"] = [
        {"binding": binding.address, "node": binding.node_address, "instance": "host-1", "revision": "realization-r1"}
    ]
    try:
        contracts.InjectTriggerRequestModel.model_validate(payload)
    except ValidationError as error:
        assert OWNERSHIP in str(error)
        return False
    return True


def test_module_namespaces_cannot_borrow_another_injects_binding(tmp_path):
    (tmp_path / "module.yaml").write_text(_with_header(MODULE_HEADER))
    (tmp_path / "root.yaml").write_text(_with_header(IMPORT_HEADER))
    model = compile_runtime_model(parse_sdl_file(tmp_path / "root.yaml"))
    bindings = model.inject_bindings.values()

    assert not model.diagnostics
    assert sorted(model.inject_bindings) == [
        "orchestration.inject-binding.host.release",
        "orchestration.inject-binding.mod.host.mod.release",
    ]
    selected = {(inject, item.address) for inject, item in product(model.injects, bindings) if _selects(inject, item)}
    assert selected == {(item.spec["inject_address"], item.address) for item in bindings}


def test_exact_retry_returns_the_original_claim_without_a_new_admission():
    claim = occurrence()
    retry = contracts.InjectTriggerRequestModel.model_validate(claim.request.model_dump(mode="json"))

    assert contracts.require_inject_trigger_retry(claim, retry, actor_id="researcher-1") is claim


@pytest.mark.parametrize(
    ("actor_id", "path", "value"),
    [
        pytest.param("researcher-2", ("expected_head",), "order-head-9", id="another-actor"),
        pytest.param("researcher-1", ("request_key",), "researcher-release-key-2", id="another-key"),
        pytest.param("researcher-1", ("occurrence_id",), "release-occurrence-2", id="another-occurrence"),
        pytest.param("researcher-1", ("expected_head",), "order-head-10", id="changed-cut"),
        pytest.param("researcher-1", ("bindings", 0, "instance"), "host-2", id="changed-target"),
        pytest.param(
            "researcher-1",
            ("input_ref",),
            {"contract_id": "release-input-v1", "artifact_id": "input-1", "digest": "sha256:" + "9" * 64},
            id="changed-input",
        ),
    ],
)
def test_changed_actor_key_or_content_conflicts_with_the_original_claim(actor_id, path, value):
    claim = occurrence()
    retry = contracts.InjectTriggerRequestModel.model_validate(
        changed(claim.request.model_dump(mode="json"), path, value)
    )

    with pytest.raises(ValueError, match="conflicts with the original claim"):
        contracts.require_inject_trigger_retry(claim, retry, actor_id=actor_id)


def test_fresh_key_and_occurrence_may_repeat_the_same_authored_inject():
    first = occurrence()
    repeat = fresh(
        first, key="researcher-release-key-2", occurrence="release-occurrence-2", operation="op-2", position=11
    )

    contracts.validate_inject_occurrence_claims([first, repeat])
    assert contracts.inject_retry_key(repeat) != contracts.inject_retry_key(first)


@pytest.mark.parametrize(
    ("label", "actor", "claims"),
    [
        ("retry key", None, {"occurrence": "release-occurrence-2", "operation": "op-2", "position": 11}),
        ("occurrence", "researcher-2", {"key": "researcher-release-key-2", "operation": "op-2", "position": 11}),
        ("operation", None, {"key": "researcher-release-key-2", "occurrence": "release-occurrence-2", "position": 11}),
        (
            "order position",
            None,
            {"key": "key-2", "occurrence": "release-occurrence-2", "operation": "op-2", "head": "order-head-forked"},
        ),
        (
            "order predecessor",
            None,
            {
                "key": "key-2",
                "occurrence": "release-occurrence-2",
                "operation": "op-2",
                "position": 11,
                "head": "order-head-9",
            },
        ),
    ],
)
def test_claim_set_rejects_a_reused_claim_identity(label, actor, claims):
    first = occurrence()
    claim_set = [first, fresh(first, actor=actor, **claims)]

    with pytest.raises(ValueError, match=f"{label} is already claimed"):
        contracts.validate_inject_occurrence_claims(claim_set)


def test_a_consumed_schedule_slot_cannot_be_claimed_under_fresh_names():
    first = occurrence("scheduled-fan-out")
    claim_set = [
        first,
        fresh(first, key="slot-key-2", occurrence="handover-occurrence-2", operation="op-2", position=21),
    ]

    with pytest.raises(ValueError, match="schedule slot is already claimed"):
        contracts.validate_inject_occurrence_claims(claim_set)


def test_claim_sets_stay_within_one_bounded_target_run_store():
    other_run = occurrence("scheduled-fan-out")
    claim_set = [occurrence(), other_run]
    oversized = [occurrence()] * 1025

    with pytest.raises(ValueError, match="one target/run store"):
        contracts.validate_inject_occurrence_claims(claim_set)
    with pytest.raises(ValueError, match="exceeds its bound"):
        contracts.validate_inject_occurrence_claims(oversized)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("plan", "contract_id"), "provisioning-plan-v1", "orchestration plan"),
        (("bindings", 0, "binding"), "orchestration.inject-binding.release", OWNERSHIP),
        (("bindings", 0, "node"), "orchestration.event.gate", "provision node address"),
        (("placement",), {"kind": "event", "event": "orchestration.script.day-one"}, "event address"),
        (
            ("placement",),
            {
                "kind": "schedule",
                "event": "orchestration.script.day-one",
                "script": "orchestration.script.s",
                "slot": "1",
            },
            "event address",
        ),
        (
            ("placement",),
            {"kind": "schedule", "event": "orchestration.event.gate", "script": "orchestration.story.s", "slot": "1"},
            "script address",
        ),
        (
            ("placement",),
            {
                "kind": "schedule",
                "event": "orchestration.event.gate",
                "script": "orchestration.script.s",
                "story": "orchestration.event.gate",
                "slot": "1",
            },
            "story address",
        ),
    ],
)
def test_request_requires_the_compiled_plan_and_narrative_address_families(path, value, message):
    payload = changed(fixture("inject-trigger-request-v1", "valid", "participant-free-environment"), path, value)

    with pytest.raises(ValidationError, match=message):
        contracts.InjectTriggerRequestModel.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("admission", "target_scope"), "target:other", "requested target and run"),
        (("admission", "run_scope"), "run:other", "requested target and run"),
        (("order", "scope"), "run:other", "without rebasing"),
        (("operation_id",), "day-one/shift-change/1", "must stay distinct"),
    ],
)
def test_occurrence_binds_admission_order_and_distinct_identities(path, value, message):
    payload = changed(fixture("inject-occurrence-v1", "valid", "scheduled-fan-out"), path, value)

    with pytest.raises(ValidationError, match=message):
        contracts.InjectOccurrenceModel.model_validate(payload)


def test_commitments_are_canonical_and_cover_the_selected_targets():
    claim = occurrence("scheduled-fan-out")
    narrowed = contracts.InjectTriggerRequestModel.model_validate(
        {**claim.request.model_dump(mode="json"), "bindings": [claim.request.bindings[0].model_dump(mode="json")]}
    )

    assert contracts.inject_trigger_request_digest(claim.request).startswith("sha256:")
    assert contracts.inject_trigger_request_digest(narrowed) != contracts.inject_trigger_request_digest(claim.request)
    assert contracts.inject_occurrence_digest(claim) == contracts.inject_occurrence_digest(
        occurrence("scheduled-fan-out")
    )
