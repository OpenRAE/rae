"""Canonical authority survives normalization and portable plan carriage."""

from dataclasses import replace

import pytest
from raes_contracts.bounded_domains import EnumDomain
from raes_contracts.realization_structure import (
    RealizationClosure,
    RealizationDomainValue,
    RealizationRelationStatus,
    evaluate_realization_constraint,
    normalize_realization_literal,
)


def test_normalization_lowers_domains_and_default_presence_without_losing_exact_sibling():
    result = normalize_realization_literal(
        {"name": "db", "engine": "other", "port": None},
        semantic_profile="test/recursive-carriage/v1",
        default_closure=RealizationClosure(posture="closed", universe="database", profile="test/v1"),
        origins={"/port": "default"},
        optional_fields=frozenset({"/port"}),
        leaf_constraints={
            "/engine": RealizationDomainValue(kind="domain", domain=EnumDomain(values=["sqlite", "postgresql"]))
        },
    )
    assert result.status is RealizationRelationStatus.CONFORMANT
    document = result.document
    assert document.root.fields["port"].origin.value == "default"
    assert document.root.fields["port"].value is None
    for actual, accepted in [
        ({"name": "db", "engine": "sqlite"}, True),
        ({"name": "db", "engine": "postgresql", "port": None}, True),
        ({"name": "other", "engine": "sqlite"}, False),
        ({"name": "db", "engine": "unknown"}, False),
        ({"name": "db", "engine": "sqlite", "port": 0}, False),
    ]:
        assert (
            evaluate_realization_constraint(document, actual).status is RealizationRelationStatus.CONFORMANT
        ) is accepted


@pytest.mark.parametrize("pointer", ["/missing", "/engine/child"])
def test_normalization_rejects_unresolved_leaf_authority(pointer):
    result = normalize_realization_literal(
        {"engine": "other"},
        semantic_profile="test/recursive-carriage/v1",
        leaf_constraints={pointer: RealizationDomainValue(kind="domain", domain=EnumDomain(values=["sqlite"]))},
    )
    assert result.status is RealizationRelationStatus.INVALID
    assert result.document is None


def test_normalization_bounds_leaf_metadata_before_materializing_it():
    from collections.abc import Mapping

    class OversizedMetadata(Mapping):
        def __len__(self):
            return 4097

        def __iter__(self):
            raise AssertionError("oversized metadata must not be copied or traversed")

        def __getitem__(self, key):
            raise AssertionError("oversized metadata must not be indexed")

    result = normalize_realization_literal(
        "value",
        semantic_profile="test/metadata/v1",
        leaf_constraints=OversizedMetadata(),
    )
    assert result.status is RealizationRelationStatus.LIMIT_EXCEEDED
    assert result.document is None


def test_normalization_revalidates_mutated_leaf_models():
    from raes_contracts.realization_structure import RealizationLiteral

    invalid = RealizationLiteral(kind="literal", value="safe").model_copy(update={"value": {"not": "a scalar"}})
    result = normalize_realization_literal(
        "safe",
        semantic_profile="test/metadata/v1",
        leaf_constraints={"": invalid},
    )
    assert result.status is RealizationRelationStatus.INVALID
    assert result.document is None


def test_recursive_authority_roundtrip_and_digest_preserve_explicit_null():
    from raes_contracts.contracts import ProvisioningPlanModel
    from raes_contracts.plan_projection import provisioning_plan_model, runtime_plan_digest
    from raes_runtime.control_plane_api_models import _provisioning_plan
    from test_issue_1200_mixed_runtime_constraints import _fixture

    _, plan, _ = _fixture({"packages": [{"manager": "apt", "name": "nmap", "version": "7.95"}]})
    document = normalize_realization_literal(None, semantic_profile="test/null/v1").document
    authority = replace(plan.realization_authority[0], structure=None, constraint_document=document)
    candidate = replace(plan, realization_authority=(authority, *plan.realization_authority[1:]))
    wire = provisioning_plan_model(candidate).model_dump(mode="json", exclude_none=True)
    assert wire["realization_authority"][0]["constraint_document"]["root"]["value"] is None
    restored = _provisioning_plan(ProvisioningPlanModel.model_validate(wire))
    assert restored.realization_authority[0].constraint_document == document
    assert runtime_plan_digest(restored) == runtime_plan_digest(candidate)


def test_compiler_and_portable_plan_share_the_recursive_database_authority():
    from test_issue_1200_mixed_runtime_constraints import _fixture

    model, plan, _ = _fixture({"database_services": [{"database_service_id": "db", "engine": "other"}]})
    requirement = next(r for r in model.realization_requirements if r.requirement_kind == "runtime-database-services")
    authority = next(r for r in plan.realization_authority if r.requirement_kind == requirement.requirement_kind)
    assert requirement.constraint_document is not None
    assert authority.constraint_document == requirement.constraint_document
    assert authority.structure is None
    member = authority.constraint_document.root.members[0].constraint
    assert member.fields["database_service_id"].value == "db"
    assert "sqlite" in member.fields["engine"].domain.values
    assert "unknown" not in member.fields["engine"].domain.values
    assert member.fields["version"].origin.value == "default"


@pytest.mark.parametrize("missing", ["constraint_document", "constraint_binding"])
def test_constraint_and_source_binding_cannot_be_carried_independently(missing):
    from pydantic import ValidationError
    from raes_contracts.contracts import ProvisioningPlanModel
    from raes_contracts.plan_projection import provisioning_plan_model
    from test_issue_1200_mixed_runtime_constraints import _fixture

    _, plan, _ = _fixture({"packages": [{"manager": "apt", "name": "nmap", "version": "7.95"}]})
    with pytest.raises(ValueError):
        replace(plan.realization_authority[0], **{missing: None})
    wire = provisioning_plan_model(plan).model_dump(mode="json")
    del wire["realization_authority"][0][missing]
    with pytest.raises(ValidationError):
        ProvisioningPlanModel.model_validate(wire)


@pytest.mark.parametrize("accepted", [True, False])
def test_runtime_uses_recursive_exact_leaf_even_with_open_summary(accepted):
    from raes_contracts.planning import RealizationAuthorityMode
    from raes_contracts.realization_structure import realization_constraint_binding
    from raes_processor.semantics.realization_concerns import project_realization_concern
    from test_issue_1200_mixed_runtime_constraints import _apply, _fixture

    _, plan, manifest = _fixture({"packages": [{"manager": "apt", "name": "nmap", "version": "7.95"}]})
    authority = next(a for a in plan.realization_authority if a.requirement_kind == "runtime-packages")
    document = normalize_realization_literal(
        [{"manager": "apt", "name": "nmap", "version": "7.95"}],
        semantic_profile="raes/runtime-packages/v1",
        default_closure=RealizationClosure(
            posture="open", universe="runtime-packages", profile="raes/runtime-packages/v1"
        ),
    ).document
    projected = project_realization_concern(
        "runtime-packages", plan.operations[0].payload["spec"]["node"]["runtime"]["packages"], recursive=True
    )
    candidate = replace(
        authority,
        mode=RealizationAuthorityMode.OPEN,
        structure=None,
        constraint_document=document,
        constraint_binding=realization_constraint_binding(document, projected),
    )
    plan = replace(
        plan, realization_authority=tuple(candidate if a is authority else a for a in plan.realization_authority)
    )
    result = _apply(
        plan, manifest, {"packages": [{"manager": "apt", "name": "nmap", "version": "7.95" if accepted else "7.94"}]}
    )
    assert result.success is accepted


def test_recursive_projection_preserves_occurrence_order():
    from pydantic import TypeAdapter
    from raes_processor.semantics.realization_typed_runtime_projection import project_typed_runtime_concern

    value = [{"name": "second"}, {"name": "first"}]
    result = project_typed_runtime_concern(
        value, adapter=TypeAdapter(list[dict[str, str]]), concern_kind="test/sequence", preserve_sequence_order=True
    )
    assert result == value


def test_accepted_snapshot_sanitization_preserves_recursive_sequence_order():
    from raes_processor.semantics.realization_concerns import project_realization_concern
    from test_issue_1200_mixed_runtime_constraints import _apply, _fixture

    runtime = {
        "database_services": [
            {
                "database_service_id": "db",
                "engine": "sqlite",
                "databases": [{"database_id": "z", "name": "z-last"}, {"database_id": "a", "name": "a-first"}],
            }
        ]
    }
    _, portable, manifest = _fixture(runtime)
    result = _apply(portable, manifest, runtime)
    assert result.success, result.diagnostics
    accepted = result.snapshot.entries["provision.node.host"].payload["spec"]["node"]["runtime"]["database_services"]
    authority = next(
        item for item in portable.realization_authority if item.requirement_kind == "runtime-database-services"
    )
    projection = project_realization_concern("runtime-database-services", accepted, observed=True, recursive=True)
    assert evaluate_realization_constraint(authority.constraint_document, projection).conformant
    assert [database["name"] for database in accepted[0]["databases"]] == ["z-last", "a-first"]


def test_final_safe_projection_cannot_introduce_a_constraint_violation(monkeypatch):
    from raes_runtime import backend_apply_results
    from test_issue_1200_mixed_runtime_constraints import _apply, _fixture

    sanitize = backend_apply_results._sanitize_backend_realization

    def changed_projection(result, **kwargs):
        sanitized = sanitize(result, **kwargs)
        payload = sanitized.snapshot.entries["provision.node.host"].payload
        payload["spec"]["node"]["runtime"]["packages"][0]["version"] = "7.94"
        return sanitized

    runtime = {"packages": [{"manager": "apt", "name": "nmap", "version": "7.95"}]}
    _, portable, manifest = _fixture(runtime)
    monkeypatch.setattr(backend_apply_results, "_sanitize_backend_realization", changed_projection)
    result = _apply(portable, manifest, runtime)
    assert not result.success
    assert result.snapshot.entries == {}
    assert result.changed_addresses == []
    assert result.diagnostics[0].code == "runtime.backend-contract-invalid"
