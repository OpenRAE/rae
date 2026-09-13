"""Installed inventory semantics execute through the real pre-apply profile host.

This test backend models contract enforcement, not a live datastore or daemon.
It installs an explicit semantic contract, distinct from resource-label support.
"""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.domain_profiles import (
    DomainProfileBindingBasis,
    DomainProfileBindingOwnerModel,
    DomainProfileOperation,
    DomainProfileSchemaModel,
    DomainProfileSemanticContractModel,
    draft_domain_profile_definition,
    seal_domain_profile_definition,
)
from raes_contracts.realization_observation import RealizationObservationDisclosure
from raes_contracts.realization_preparation import RealizationPreparation
from raes_contracts.realization_profiles import PlanProfileAuthority, ProfileBindingConstraint, profile_context_digest
from raes_contracts.realization_structure import (
    RealizationClosure,
    normalize_realization_literal,
    realization_constraint_binding,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.planner.realization_preparation import preparation_authority
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from test_issue_1200_mixed_runtime_constraints import _fixture, _returned
from test_issue_1202_domain_profiles import _admitted, _binding, _context, _support

CASES = {
    "persistence": (
        "datastore_services",
        {"datastore_service_id": "cache", "data_model": "key_value"},
        {"persistence": {"persistence_id": "durable", "aof": True}},
    ),
    "replication": (
        "datastore_services",
        {"datastore_service_id": "columns", "data_model": "wide_column"},
        {
            "partitions": [
                {
                    "partition_id": "ks",
                    "kind": "keyspace",
                    "replication_strategy": "simple_strategy",
                    "replication_factor": 2,
                }
            ]
        },
    ),
    "destination": (
        "forwarding_agents",
        {"forwarding_agent_id": "logs", "agent_kind": "log_forwarder"},
        {"ship_targets": [{"target_id": "sink", "ingestion_port": 1514, "protocol": "syslog"}]},
    ),
    "privileged-interface": (
        "orchestration_authorities",
        {"orchestration_authority_id": "authority", "privilege_class": "host_root_equivalent"},
        {"control_interface_ref": "control", "engine": "podman"},
    ),
    "grant-coverage": (
        "app_authorizations",
        {"app_authorization_id": "rbac", "resource_vocabulary": "app_resource"},
        {"permission_grants": [{"grant_id": "deny", "resource_kind": "app_resource", "effect": "deny"}]},
    ),
}


def _inventory_profile(operation):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:example:inventory-schema",
        "type": "object",
        "properties": {"operation": {"enum": list(CASES)}},
        "required": ["operation"],
        "additionalProperties": False,
    }
    definition = seal_domain_profile_definition(
        draft_domain_profile_definition(
            namespace="org.example.inventory",
            authority="urn:example:inventory",
            profile_id="completeness",
            revision="1",
            schema=DomainProfileSchemaModel(
                schema_id="urn:example:inventory-schema", revision="1", schema_document=schema
            ),
            semantic_contract=DomainProfileSemanticContractModel(
                authority="urn:example:inventory",
                contract_id="selected-inventory-completeness",
                revision="1",
                digest=canonical_json_digest({"contract": "test-inventory-completeness-v1", "operations": list(CASES)}),
            ),
            allowed_contexts=("runtime-inventory",),
        )
    )
    binding = _binding(definition, value={"operation": operation}).model_copy(
        update={
            "owner": DomainProfileBindingOwnerModel(
                owning_contract_id="plan-realization-profiles-v1",
                canonical_address="#/resources/provision.node.host",
                concept_family="resource-realization",
                lifecycle_phase="planning",
                context="runtime-inventory",
                use="constraint",
            )
        }
    )
    document = normalize_realization_literal(
        binding.value,
        semantic_profile=definition.coordinate.definition_digest,
        default_closure=RealizationClosure(posture="closed", universe="profile-value", profile="test/v1"),
    ).document
    authority = PlanProfileAuthority(
        definitions=(_admitted(definition),),
        bindings=(binding,),
        constraints=(
            ProfileBindingConstraint(
                binding_path=(binding.binding_id,),
                document=document,
                source_binding=realization_constraint_binding(document, binding.value),
            ),
        ),
    )
    context = _context(definition, support_declarations=(_support(definition, *DomainProfileOperation),))
    return authority, context


class _InventoryBackend:
    def __init__(self, context, selection, *, allow_privileged=False, tamper=False, corroborate=True):
        self.domain_profile_context = context
        self.selection = selection
        self.allow_privileged = allow_privileged
        self.tamper = tamper
        self.corroborate = corroborate
        self.prepares = self.validations = self.applies = 0

    def prepare(self, plan, snapshot):
        self.prepares += 1
        operations = deepcopy(plan.operations)
        bindings = tuple(
            binding.model_copy(
                update={
                    "provenance": binding.provenance.model_copy(
                        update={"basis": DomainProfileBindingBasis.BACKEND_SELECTED}
                    )
                }
            )
            for binding in plan.profile_authority.bindings
        )
        operations = tuple(replace(op, profile_bindings=bindings) for op in operations)
        operations[0].payload["spec"]["node"]["runtime"].update(deepcopy(self.selection))
        return RealizationPreparation.for_request(plan, snapshot, operations=operations)

    def validate_profiles(self, plan):
        self.validations += 1
        operation = plan.operations[0].profile_bindings[0].value["operation"]
        family = CASES[operation][0]
        runtime = plan.operations[0].payload["spec"]["node"]["runtime"]
        record = runtime[family][0]
        if operation == "persistence":
            valid = record.get("persistence", {}).get("aof") is True
        elif operation == "replication":
            valid = any(p.get("replication_factor") == 2 for p in record.get("partitions", []))
        elif operation == "destination":
            valid = any(t.get("ingestion_port") == 1514 for t in record.get("ship_targets", []))
        elif operation == "grant-coverage":
            valid = any(
                g.get("resource_kind") == record["resource_vocabulary"] for g in record.get("permission_grants", [])
            )
        else:
            interfaces = {row["control_interface_id"]: row for row in runtime.get("local_control_interfaces", [])}
            interface = interfaces.get(record.get("control_interface_ref"), {})
            valid = (
                self.allow_privileged and record.get("engine") == "podman" and interface.get("access") == "read_write"
            )
        return (
            []
            if valid
            else [Diagnostic("inventory.incomplete", "provisioning", "profiles", "Selected operation is not admitted.")]
        )

    def validate(self, plan):
        return []

    def apply(self, plan, snapshot):
        self.applies += 1
        runtime = deepcopy(plan.operations[0].payload["spec"]["node"]["runtime"])
        if self.tamper:
            runtime["datastore_services"][0]["data_model"] = "wide_column"
        returned = _returned(plan, runtime)
        entries = {
            address: replace(entry, profile_bindings=plan.operations[0].profile_bindings)
            for address, entry in returned.entries.items()
        }
        # Synthetic observation at this test backend's delivery boundary, not
        # evidence that a real datastore or daemon was provisioned.
        observations = (
            tuple(
                RealizationObservationDisclosure(
                    address=row.address,
                    field_path=row.field_path,
                    domain=row.domain,
                    requirement_kind=row.requirement_kind,
                    verification_scope=row.verification_scope,
                    observation_strength=row.required_observation_strength,
                )
                for row in plan.realization_authority
                if row.requirement_kind
                in {
                    "runtime-datastore-services",
                    "runtime-orchestration-authorities",
                    "runtime-app-authorizations",
                    "forwarding-agents",
                    "runtime-local-control-interfaces",
                }
            )
            if self.corroborate
            else ()
        )
        return ApplyResult(
            True,
            replace(
                returned, entries=entries, metadata=deepcopy(snapshot.metadata), realization_observations=observations
            ),
            changed_addresses=list(entries),
        )


def _exercise(
    operation,
    *,
    completed=True,
    trusted=True,
    supported=True,
    allow_privileged=True,
    tamper=False,
    authored_override=None,
    interface_access="read_write",
    corroborate=True,
):
    family, record, completion = CASES[operation]
    authored = {family: [{**record, **(authored_override or {})}]}
    if operation == "privileged-interface":
        authored["local_control_interfaces"] = [
            {
                "control_interface_id": "control",
                "kind": "unix_socket",
                "path": "/run/podman/podman.sock",
                "access": interface_access,
            }
        ]
    _, plan, manifest = _fixture(authored, scope=f"/nodes/host/runtime/{family}")
    authority, context = _inventory_profile(operation)
    selected = {family: [{**record, **(completion if completed else {})}]}
    if operation == "privileged-interface" and completed:
        selected["local_control_interfaces"] = [
            {
                "control_interface_id": "control",
                "kind": "unix_socket",
                "path": "/run/podman/podman.sock",
                "access": interface_access,
            }
        ]
    if not trusted:
        context = context.model_copy(update={"namespace_admissions": ()})
    if not supported:
        context = context.model_copy(update={"support_declarations": ()})
    manifest = replace(
        manifest,
        supported_contract_versions=manifest.supported_contract_versions
        | {"plan-realization-profiles-v1", "backend-realization-preparation-v1"},
        domain_profile_context_digest=profile_context_digest(context),
    )
    plan = replace(plan, profile_authority=authority, preparation=preparation_authority(manifest))
    backend = _InventoryBackend(
        context, selected, allow_privileged=allow_privileged, tamper=tamper, corroborate=corroborate
    )
    previous = RuntimeSnapshot(metadata={"trusted": "predecessor"})
    result = _call_backend_apply(
        backend.apply,
        plan,
        previous,
        snapshot=previous,
        address="runtime.test.inventory",
        realization=_RealizationApplyContext(plan=plan, manifest=manifest),
    )
    return backend, previous, result


@pytest.mark.parametrize("operation", CASES)
@pytest.mark.parametrize("completed", [False, True])
def test_selected_completeness_is_checked_after_backend_choice_before_apply(operation, completed):
    backend, previous, result = _exercise(operation, completed=completed)
    assert backend.validations == 1, result.diagnostics
    assert backend.applies == int(completed), result.diagnostics
    assert result.success is completed, result.diagnostics
    if not completed:
        assert result.snapshot == previous


@pytest.mark.parametrize("condition", [{"trusted": False}, {"supported": False}])
def test_description_and_profile_shape_do_not_supply_trust_or_execution_support(condition):
    backend, previous, result = _exercise("persistence", **condition)
    assert (backend.prepares, backend.applies) == (0, 0)
    assert not result.success
    assert result.snapshot == previous


@pytest.mark.parametrize(
    "condition", [{"allow_privileged": False}, {"interface_access": "unknown"}, {"interface_access": "read_only"}]
)
def test_privileged_description_and_socket_do_not_grant_selected_execution(condition):
    backend, previous, result = _exercise("privileged-interface", **condition)
    assert backend.applies == 0
    assert not result.success
    assert result.snapshot == previous


def test_profile_prerequisite_cannot_override_exact_nonpersistent_choice():
    backend, previous, result = _exercise(
        "persistence", authored_override={"persistence": {"persistence_id": "durable", "aof": False}}
    )
    assert backend.applies == 0
    assert not result.success
    assert result.snapshot == previous


def test_selected_delivery_must_match_the_admitted_completion():
    backend, previous, result = _exercise("persistence", tamper=True)
    assert backend.applies == 1, result.diagnostics
    assert not result.success
    assert result.snapshot == previous


def test_profile_admission_and_echoed_inventory_are_not_delivery_corroboration():
    backend, previous, result = _exercise("persistence", corroborate=False)
    assert backend.applies == 1, result.diagnostics
    assert not result.success
    assert result.snapshot == previous
