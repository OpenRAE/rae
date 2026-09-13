"""Partial typed inventories retain identity, exact children and source presence."""

from copy import deepcopy

import pytest
from raes.runtime_inventory import runtime_inventory_collection_identity
from raes_contracts.realization_structure import evaluate_realization_constraint
from raes_processor.semantics.realization_concerns import project_realization_concern
from test_issue_1200_mixed_runtime_constraints import _fixture


@pytest.mark.parametrize(
    "family,identity,child,child_id",
    [
        ("app_authorizations", "app_authorization_id", "roles", "role_id"),
        ("datastore_services", "datastore_service_id", "partitions", "partition_id"),
        ("orchestration_authorities", "orchestration_authority_id", "spawn_templates", "template_id"),
    ],
)
def test_reordered_typed_inventory_preserves_exact_children(family, identity, child, child_id):
    records = [
        {
            identity: "first",
            child: [{child_id: "one", "name" if child != "spawn_templates" else "purpose": "exact"}, {child_id: "two"}],
        },
        {identity: "second"},
    ]
    model, _, _ = _fixture({family: records}, scope="/nodes/host/runtime")
    kind = "runtime-" + family.replace("_", "-")
    requirement = next(row for row in model.realization_requirements if row.requirement_kind == kind)
    selected = deepcopy(records)
    selected[0][child].reverse()
    selected.reverse()
    projected = project_realization_concern(kind, selected, recursive=True)
    assert evaluate_realization_constraint(requirement.constraint_document, projected).conformant
    selected[1][child][1]["name" if child != "spawn_templates" else "purpose"] = "violated"
    projected = project_realization_concern(kind, selected, recursive=True)
    assert not evaluate_realization_constraint(requirement.constraint_document, projected).conformant


@pytest.mark.parametrize("empty,accepted", [(False, True), (True, False)])
def test_omitted_and_explicitly_closed_empty_grants_remain_distinct(empty, accepted):
    record = {"app_authorization_id": "rbac", "resource_vocabulary": "app_resource"}
    if empty:
        record["permission_grants"] = []
    model, _, _ = _fixture(
        {"app_authorizations": [record]},
        scope="/nodes/host/runtime",
        closed_scopes=("/nodes/host/runtime/app_authorizations/0/permission_grants",) if empty else (),
    )
    requirement = next(
        row for row in model.realization_requirements if row.requirement_kind == "runtime-app-authorizations"
    )
    selected = [
        {**record, "permission_grants": [{"grant_id": "selected", "resource_kind": "app_resource", "effect": "deny"}]}
    ]
    projected = project_realization_concern("runtime-app-authorizations", selected, recursive=True)
    assert evaluate_realization_constraint(requirement.constraint_document, projected).conformant is accepted


@pytest.mark.parametrize(
    "pointer,expected",
    [
        ("", ("datastore_service_id",)),
        ("/0/nodes", ("node_id",)),
        ("/0/nodes/1/plugins", ("plugin_id",)),
        ("/0/nodes/1/endpoints", ("endpoint_id",)),
        ("/0/aliases", ()),
        ("/0/persistence/rdb_save_points", ()),
        ("nodes", ()),
        ("/00/nodes", ()),
        ("/x/nodes", ()),
        ("/١/nodes", ()),
        ("/-1/nodes", ()),
        ("/+1/nodes", ()),
        ("//nodes", ()),
        ("/10/nodes/20/plugins", ("plugin_id",)),
        ("/0/nodes/1/missing", ()),
        ("/0/nodes/1/plugins/0/nodes", ()),
        ("/0", ()),
        ("/0/no~1des", ()),
        ("/0/nodes/0/plugins/0", ()),
    ],
)
def test_public_identity_lookup_only_admits_registered_collection_paths(pointer, expected):
    assert runtime_inventory_collection_identity("datastore-services", pointer) == expected
    assert runtime_inventory_collection_identity("not-a-family", pointer) == ()


def test_omitted_relational_protocol_survives_instantiation_and_portable_compilation():
    model, portable, _ = _fixture(
        {"database_services": [{"database_service_id": "db", "engine": "postgresql"}]},
        scope="/nodes/host/runtime/database_services",
    )
    requirement = next(
        row for row in model.realization_requirements if row.requirement_kind == "runtime-database-services"
    )
    selected = [{"database_service_id": "db", "engine": "postgresql", "protocol": "postgresql"}]
    projected = project_realization_concern("runtime-database-services", selected, recursive=True)
    assert evaluate_realization_constraint(requirement.constraint_document, projected).conformant
    assert portable.operations[0].payload["spec"]["node"]["runtime"]["database_services"][0]["protocol"] == "unknown"
