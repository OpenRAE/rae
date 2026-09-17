"""Private resource measures retain typed quantity and ledger enforcement."""

import pytest
from pydantic import ValidationError
from raes.participant_resource_budgets import ParticipantResourceBudgetDimension
from raes_contracts.contracts.participant_resource_budgets import ParticipantResourceQuantityModel
from test_issue_1208_profile_selections import _account_profile


def test_private_measure_identity_survives_source_and_quantity_contracts():
    binding, _ = _account_profile()
    kind = binding.coordinate
    dimension = ParticipantResourceBudgetDimension.model_validate(
        {
            "owner_ref": "worker",
            "pool_ref": "packet-pool",
            "resource_kind": kind.model_dump(mode="json"),
            "unit": "packets",
            "accounting_mode": "cumulative_counter",
            "meter_profile_ref": "urn:example:packet-meter:1",
            "limit": 12,
            "reservation": 2,
            "reset": "run",
        }
    )
    assert dimension.resource_kind == kind
    quantity = ParticipantResourceQuantityModel(
        resource_kind=kind,
        unit="packets",
        accounting_mode="cumulative_counter",
        meter_profile_ref="urn:example:packet-meter:1",
        amount=2,
    )
    assert ParticipantResourceQuantityModel.model_validate(quantity.model_dump(mode="json")) == quantity


def test_private_measure_pool_requires_independent_profile_semantics():
    from raes_backend_protocols.participant_resource_budgets import participant_resource_budget_capability_payload
    from raes_contracts.contracts.participant_resource_budgets import ParticipantResourceBudgetCapabilitiesModel
    from test_issue_899_participant_resource_budgets import _capabilities

    binding, _ = _account_profile()
    payload = participant_resource_budget_capability_payload(_capabilities()).model_dump(mode="json")
    pool = dict(payload["configured_pools"][0])
    pool.update(
        pool_ref="private-pool",
        resource_kind=binding.coordinate.model_dump(mode="json"),
        unit="packets",
        accounting_mode="cumulative_counter",
        meter_profile_ref="urn:example:packet-meter:1",
    )
    payload["configured_pools"].append(pool)
    payload["supported_resource_kinds"].append(binding.coordinate.model_dump(mode="json"))
    with pytest.raises(ValidationError, match="profile"):
        ParticipantResourceBudgetCapabilitiesModel.model_validate(payload)


def _resource_profile():
    from raes_contracts.domain_profiles import (
        DomainProfileDefinitionDraftModel,
        DomainProfileOperation,
        DomainProfileSchemaModel,
        seal_domain_profile_definition,
    )
    from raes_contracts.resource_measure_profiles import RESOURCE_MEASURE_SEMANTICS
    from test_issue_1202_domain_profiles import _context, _support

    binding, _ = _account_profile()
    identity = binding.coordinate.model_dump(exclude={"definition_digest"})
    identity["profile_id"] = "packet-counter"
    values = {
        "unit": "packets",
        "accounting_mode": "cumulative_counter",
        "meter_profile_ref": "urn:example:packet-meter:1",
        "reset": "run",
    }
    definition = seal_domain_profile_definition(
        DomainProfileDefinitionDraftModel(
            identity=identity,
            semantic_contract=RESOURCE_MEASURE_SEMANTICS,
            allowed_contexts=("participant-resource-measure",),
            profile_schema=DomainProfileSchemaModel(
                schema_id="urn:example:packet-measure",
                revision="1",
                schema_document={
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "$id": "urn:example:packet-measure",
                    "type": "object",
                    "properties": {key: {"const": value} for key, value in values.items()},
                    "required": list(values),
                    "additionalProperties": False,
                },
            ),
        )
    )
    return definition.coordinate, _context(
        definition, support_declarations=(_support(definition, *DomainProfileOperation),)
    )


def test_private_measure_compiles_and_uses_existing_reservation_and_settlement_ledger():
    from dataclasses import replace

    import yaml
    from raes import parse_sdl
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_processor.compiler import compile_runtime_model
    from raes_runtime.participant_resource_accounting import commit_participant_resource_reservation
    from raes_runtime.participant_resource_budgets import (
        initialize_participant_resource_budgets,
        reserve_participant_resources,
    )
    from test_issue_899_participant_resource_budgets import _budget_policy_yaml, _capabilities, _measured_vector

    kind, context = _resource_profile()
    source = yaml.safe_load(_budget_policy_yaml())
    budget = source["behavior_specifications"]["participant-behavior"]["autonomous_execution"]["resource_budget"]
    budget["dimensions"]["packets"] = {
        "owner_ref": "green",
        "pool_ref": "packet-pool",
        "resource_kind": kind.model_dump(mode="json"),
        "unit": "packets",
        "accounting_mode": "cumulative_counter",
        "meter_profile_ref": "urn:example:packet-meter:1",
        "limit": 12,
        "reservation": 2,
        "reset": "run",
    }
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(source)))
    policy = next(spec.autonomous_execution for spec in model.behavior_specifications.values())
    assert next(item for item in policy.resource_demands if item.budget_id == "packets").resource_kind == kind
    base = _capabilities()
    pool = replace(
        base.configured_pools[0],
        pool_ref="packet-pool",
        resource_kind=kind,
        unit="packets",
        accounting_mode="cumulative_counter",
        meter_profile_ref="urn:example:packet-meter:1",
        capacity=12,
    )
    capabilities = replace(
        base,
        supported_resource_kinds=base.supported_resource_kinds | {kind},
        configured_pools=(*base.configured_pools, pool),
        domain_profile_context=context,
    )
    initialized = initialize_participant_resource_budgets(
        RuntimeSnapshot(), (policy,), capabilities, execution_generation=3
    )
    assert initialized.success, initialized.diagnostics
    reserved = reserve_participant_resources(
        initialized.snapshot, policy, operation_id="packet-action", execution_generation=3
    )
    assert reserved.success, reserved.diagnostics
    committed = commit_participant_resource_reservation(
        reserved.snapshot,
        operation_id="packet-action",
        execution_generation=3,
        measured_quantities=_measured_vector(reserved.snapshot, "packet-action", packets=2),
        evidence_refs=("evidence.packet-counter",),
    )
    assert committed.success, committed.diagnostics
    state = next(
        item
        for item in committed.snapshot.participant_resource_budget_states.values()
        if item["budget_id"] == "packets"
    )
    assert state["resource_kind"] == kind.model_dump(mode="json")
    assert state["cumulative_use"] == 2
    wrong_reset = replace(
        policy,
        resource_demands=tuple(
            replace(item, reset="time_segment") if item.budget_id == "packets" else item
            for item in policy.resource_demands
        ),
    )
    rejected = initialize_participant_resource_budgets(
        RuntimeSnapshot(), (wrong_reset,), capabilities, execution_generation=3
    )
    assert not rejected.success
    assert not rejected.snapshot.participant_resource_budget_states
