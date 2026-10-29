"""Cloud ownership and selection references must retain their exact meaning."""

import pytest
from cloud_resource_fixtures import (
    APP,
    AUTHORITY,
    PRINCIPAL,
    SCOPE_A,
    SCOPE_B,
    VERSION,
    authority,
    cloud_scenario,
    secret,
)
from raes._declarations import build_declaration_index
from raes._errors import SDLValidationError
from raes.scenario import Scenario
from raes.validator import SemanticValidator


def validate(raw):
    SemanticValidator(Scenario.model_validate(raw)).validate()


def test_cloud_children_have_canonical_targetable_addresses():
    index = build_declaration_index(Scenario.model_validate(cloud_scenario()))
    for address in (
        SCOPE_A,
        SCOPE_B,
        VERSION,
        f"{AUTHORITY}.identity_uses.worker-use",
        f"{AUTHORITY}.access_observations.denied",
        f"{AUTHORITY}.policies.reader",
    ):
        declaration = index.declaration_for(address)
        assert declaration is not None, address
        assert declaration.targetable


@pytest.mark.parametrize("field", ["resource_scope_ref"])
def test_subject_scope_rejects_an_identity_instead_of_a_scope(field):
    raw = cloud_scenario()
    authority(raw)["subjects"][0][field] = PRINCIPAL
    with pytest.raises(SDLValidationError, match="scope"):
        validate(raw)


def test_scope_ancestry_cannot_cross_provider_identity():
    raw = cloud_scenario()
    scopes = authority(raw)["resource_scopes"]
    scopes[0]["parent_ref"] = SCOPE_B
    scopes[1]["provider"] = "aws"
    with pytest.raises(SDLValidationError, match="provider"):
        validate(raw)


def test_scope_cycles_are_rejected():
    raw = cloud_scenario()
    scopes = authority(raw)["resource_scopes"]
    scopes[0]["parent_ref"], scopes[1]["parent_ref"] = SCOPE_B, SCOPE_A
    with pytest.raises(SDLValidationError, match="cycle"):
        validate(raw)


@pytest.mark.parametrize(
    "field,bad_ref", [("principal_ref", SCOPE_A), ("workload_ref", PRINCIPAL), ("source_principal_ref", SCOPE_B)]
)
def test_identity_use_checks_reference_kinds(field, bad_ref):
    raw = cloud_scenario()
    authority(raw)["identity_uses"][0][field] = bad_ref
    with pytest.raises(SDLValidationError, match="reference"):
        validate(raw)


@pytest.mark.parametrize("field,bad_ref", [("principal_refs", SCOPE_A), ("resource_refs", "nodes.missing")])
def test_policy_bindings_do_not_resolve_by_a_nearby_name(field, bad_ref):
    raw = cloud_scenario()
    authority(raw)["policies"][0]["resource_access"]["bindings"][0][field] = [bad_ref]
    with pytest.raises(SDLValidationError, match="reference"):
        validate(raw)


def test_inherited_policy_preserves_its_source_without_copying_bindings():
    raw = cloud_scenario()
    scope = authority(raw)["resource_scopes"][1]
    scope["parent_ref"] = SCOPE_A
    policy = authority(raw)["policies"][0]
    policy["resource_access"]["attachment_ref"] = SCOPE_A
    authority(raw)["policies"].append(
        {
            "policy_id": "inherited-reader",
            "policy_kind": "access",
            "resource_access": {"attachment_ref": SCOPE_B, "inherited_from_ref": f"{AUTHORITY}.policies.reader"},
        }
    )
    validate(raw)
    inherited = Scenario.model_validate(raw).nodes["iam"].runtime.identity_authorities[0].policies[1]
    assert inherited.resource_access.bindings == []


def test_inherited_policy_cycles_are_rejected():
    raw = cloud_scenario()
    authority(raw)["policies"][0]["resource_access"] = {
        "attachment_ref": SCOPE_A,
        "inherited_from_ref": f"{AUTHORITY}.policies.reader",
    }
    with pytest.raises(SDLValidationError, match="cycle"):
        validate(raw)


def test_version_inherits_project_policy_through_its_owning_secret():
    raw = cloud_scenario()
    authority(raw)["policies"].append(
        {
            "policy_id": "version-view",
            "policy_kind": "access",
            "resource_access": {"attachment_ref": VERSION, "inherited_from_ref": f"{AUTHORITY}.policies.reader"},
        }
    )
    validate(raw)


def test_shared_project_does_not_make_one_secrets_policy_an_ancestor():
    raw = cloud_scenario()
    authority(raw)["policies"][0]["resource_access"]["attachment_ref"] = f"{APP}.secrets.database"
    raw["nodes"]["secrets"]["runtime"]["platform_applications"][0]["secrets"].append(
        {"secret_id": "other", "resource_scope_ref": SCOPE_B}
    )
    authority(raw)["policies"].append(
        {
            "policy_id": "wrong-inheritance",
            "policy_kind": "access",
            "resource_access": {
                "attachment_ref": f"{APP}.secrets.other",
                "inherited_from_ref": f"{AUTHORITY}.policies.reader",
            },
        }
    )
    with pytest.raises(SDLValidationError, match="ancestry"):
        validate(raw)


def test_selection_cannot_name_another_secrets_version():
    raw = cloud_scenario()
    other = {"secret_id": "other", "resource_scope_ref": SCOPE_B, "versions": [{"version_id": "v1"}]}
    raw["nodes"]["secrets"]["runtime"]["platform_applications"][0]["secrets"].append(other)
    secret(raw)["consumers"][0]["version_ref"] = f"{APP}.secrets.other.versions.v1"
    with pytest.raises(SDLValidationError, match="version"):
        validate(raw)


def test_partial_ownership_does_not_require_a_complete_cloud_inventory():
    raw = cloud_scenario()
    secret(raw).pop("versions")
    secret(raw).pop("consumers")
    authority(raw).pop("access_observations")
    validate(raw)


def test_repeated_native_names_are_separate_declared_identities():
    raw = cloud_scenario()
    authority(raw)["subjects"].append(
        {"subject_id": "worker-b", "kind": "service_account", "name": "worker", "resource_scope_ref": SCOPE_B}
    )
    validate(raw)
    assert len(Scenario.model_validate(raw).nodes["iam"].runtime.identity_authorities[0].subjects) == 2
