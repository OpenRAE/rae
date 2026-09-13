"""Runtime application-internal authorization (RBAC) SDL surface tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from raes.runtime_app_authorization import (
    RuntimeAppAuthorization,
    RuntimeAppAuthorizationCredentialClassification,
    RuntimeAppAuthorizationGrant,
    RuntimeAppAuthorizationGrantEffect,
    RuntimeAppAuthorizationPrincipal,
    RuntimeAppAuthorizationPrincipalKind,
    RuntimeAppAuthorizationResourceVocabulary,
    RuntimeAppAuthorizationRole,
    RuntimeAppAuthorizationRoleMapping,
    RuntimeAppAuthorizationTenant,
)


def _opensearch_authorization(**overrides) -> dict:
    authorization = {
        "app_authorization_id": "wazuh-indexer-rbac",
        "resource_vocabulary": "index_pattern",
        "auth_enabled": True,
        "name": "opensearch-security",
        "principals": [
            {
                "principal_id": "admin",
                "kind": "user",
                "name": "admin",
                "reserved": True,
                "credential_classification": "redacted",
                "backend_roles": ["admin"],
            },
            {
                "principal_id": "filebeat-key",
                "kind": "api_key",
                "name": "filebeat-api-key",
                "credential_classification": "operator_secret",
            },
        ],
        "roles": [
            {"role_id": "all-access", "name": "all_access"},
            {"role_id": "readall", "name": "readall"},
        ],
        "permission_grants": [
            {
                "grant_id": "all-access-grant",
                "role_ref": "all-access",
                "resource_kind": "index_pattern",
                "actions": ["indices:data/read/*", "indices:data/write/*"],
                "resource_patterns": ["wazuh-alerts-*"],
                "effect": "allow",
            },
            {
                "grant_id": "readall-grant",
                "role_ref": "readall",
                "resource_kind": "index_pattern",
                "actions": ["indices:data/read/*"],
                "resource_patterns": ["*"],
            },
        ],
        "role_mappings": [
            {
                "mapping_id": "all-access-mapping",
                "role_ref": "all-access",
                "backend_roles": ["admin"],
                "users": ["admin"],
            }
        ],
        "tenants": [
            {"tenant_id": "global-tenant", "name": "global_tenant"},
        ],
    }
    authorization.update(overrides)
    return authorization


def test_full_app_authorization_inventory_is_valid() -> None:
    authorization = RuntimeAppAuthorization(**_opensearch_authorization())

    assert authorization.app_authorization_id == "wazuh-indexer-rbac"
    assert authorization.resource_vocabulary == RuntimeAppAuthorizationResourceVocabulary.INDEX_PATTERN
    assert authorization.auth_enabled is True
    assert authorization.principals[0].kind == RuntimeAppAuthorizationPrincipalKind.USER
    assert (
        authorization.principals[1].credential_classification
        == RuntimeAppAuthorizationCredentialClassification.OPERATOR_SECRET
    )
    assert authorization.roles[0].role_id == "all-access"
    assert authorization.permission_grants[0].resource_kind == RuntimeAppAuthorizationResourceVocabulary.INDEX_PATTERN
    assert authorization.permission_grants[0].effect == RuntimeAppAuthorizationGrantEffect.ALLOW
    assert authorization.role_mappings[0].backend_roles == ["admin"]
    assert authorization.tenants[0].tenant_id == "global-tenant"


# --------------------------------------------------------------------------- #
# Stable-id rejection (empty / variable placeholder)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("bad_id", ["", "   ", "${authz_id}"])
def test_app_authorization_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="app_authorization_id"):
        RuntimeAppAuthorization(**_opensearch_authorization(app_authorization_id=bad_id))


@pytest.mark.parametrize("bad_id", ["", "${principal}"])
def test_principal_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="principal_id"):
        RuntimeAppAuthorizationPrincipal(principal_id=bad_id)


@pytest.mark.parametrize("bad_id", ["", "${role}"])
def test_role_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="role_id"):
        RuntimeAppAuthorizationRole(role_id=bad_id)


@pytest.mark.parametrize("bad_id", ["", "${grant}"])
def test_grant_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="grant_id"):
        RuntimeAppAuthorizationGrant(grant_id=bad_id)


@pytest.mark.parametrize("bad_id", ["", "${mapping}"])
def test_mapping_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="mapping_id"):
        RuntimeAppAuthorizationRoleMapping(mapping_id=bad_id)


@pytest.mark.parametrize("bad_id", ["", "${tenant}"])
def test_tenant_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="tenant_id"):
        RuntimeAppAuthorizationTenant(tenant_id=bad_id)


# --------------------------------------------------------------------------- #
# Enum normalization
# --------------------------------------------------------------------------- #


def test_enum_normalization_is_case_and_separator_insensitive() -> None:
    principal = RuntimeAppAuthorizationPrincipal(
        principal_id="svc",
        kind="SERVICE-ACCOUNT",
        credential_classification="OPERATOR-SECRET",
    )
    assert principal.kind == RuntimeAppAuthorizationPrincipalKind.SERVICE_ACCOUNT
    assert principal.credential_classification == RuntimeAppAuthorizationCredentialClassification.OPERATOR_SECRET

    grant = RuntimeAppAuthorizationGrant(grant_id="g", resource_kind="REDIS-ACL", effect="DENY")
    assert grant.resource_kind == RuntimeAppAuthorizationResourceVocabulary.REDIS_ACL
    assert grant.effect == RuntimeAppAuthorizationGrantEffect.DENY


def test_variable_placeholder_enums_pass_through() -> None:
    grant = RuntimeAppAuthorizationGrant(grant_id="g", resource_kind="${kind}")
    assert grant.resource_kind == "${kind}"


def test_unknown_enum_member_is_rejected() -> None:
    with pytest.raises(ValidationError, match="kind must be one of"):
        RuntimeAppAuthorizationPrincipal(principal_id="p", kind="bogus-kind")


def test_open_taxonomy_carries_unknown_and_other() -> None:
    members = {m.value for m in RuntimeAppAuthorizationResourceVocabulary}
    assert {"unknown", "other"} <= members
    members = {m.value for m in RuntimeAppAuthorizationPrincipalKind}
    assert {"unknown", "other"} <= members


def test_closed_vocabularies_carry_no_sentinels() -> None:
    effect = {m.value for m in RuntimeAppAuthorizationGrantEffect}
    assert effect == {"allow", "deny"}
    classification = {m.value for m in RuntimeAppAuthorizationCredentialClassification}
    assert classification == {"none", "redacted", "operator_secret"}
    assert "unknown" not in classification and "other" not in classification


# --------------------------------------------------------------------------- #
# Duplicate-id rejection
# --------------------------------------------------------------------------- #


def test_rejects_duplicate_local_stable_ids_across_child_kinds() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime app authorization stable id 'shared-id'"):
        RuntimeAppAuthorization(
            app_authorization_id="authz",
            roles=[{"role_id": "shared-id"}],
            tenants=[{"tenant_id": "shared-id"}],
        )


def test_rejects_duplicate_grant_ids() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime app authorization stable id 'dup-grant'"):
        RuntimeAppAuthorization(
            app_authorization_id="authz",
            permission_grants=[
                {"grant_id": "dup-grant", "resource_kind": "app_resource"},
                {"grant_id": "dup-grant", "resource_kind": "app_resource"},
            ],
        )


def test_rejects_duplicate_backend_role_values_on_principal() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime app authorization backend_roles entry on 'p'"):
        RuntimeAppAuthorizationPrincipal(principal_id="p", backend_roles=["admin", "admin"])


def test_rejects_duplicate_action_values_on_grant() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime app authorization actions entry on 'g'"):
        RuntimeAppAuthorizationGrant(grant_id="g", actions=["read", "read"])


# --------------------------------------------------------------------------- #
# require_grants_for_resource_vocabulary guard (positive + negative)
# --------------------------------------------------------------------------- #


def test_declared_vocabulary_with_matching_grant_is_valid() -> None:
    authorization = RuntimeAppAuthorization(
        app_authorization_id="redis-acl",
        resource_vocabulary="redis_acl",
        permission_grants=[{"grant_id": "g1", "resource_kind": "redis_acl", "actions": ["~*", "+@all"]}],
    )
    assert authorization.resource_vocabulary == RuntimeAppAuthorizationResourceVocabulary.REDIS_ACL


def test_declared_vocabulary_without_matching_grant_is_rejected() -> None:
    with pytest.raises(
        ValidationError,
        match="declares a resource_vocabulary but no permission_grant has a matching resource_kind",
    ):
        RuntimeAppAuthorization(
            app_authorization_id="cassandra-rbac",
            resource_vocabulary="cql_resource",
            permission_grants=[{"grant_id": "g1", "resource_kind": "app_resource"}],
        )


def test_declared_vocabulary_with_no_grants_at_all_is_rejected() -> None:
    with pytest.raises(ValidationError, match="but no permission_grant has a matching resource_kind"):
        RuntimeAppAuthorization(
            app_authorization_id="empty-rbac",
            resource_vocabulary="index_pattern",
        )


def test_unknown_vocabulary_is_exempt_from_grant_requirement() -> None:
    authorization = RuntimeAppAuthorization(app_authorization_id="bare", resource_vocabulary="unknown")
    assert authorization.resource_vocabulary == RuntimeAppAuthorizationResourceVocabulary.UNKNOWN


def test_default_vocabulary_is_unknown_and_exempt() -> None:
    authorization = RuntimeAppAuthorization(app_authorization_id="bare")
    assert authorization.resource_vocabulary == RuntimeAppAuthorizationResourceVocabulary.UNKNOWN


def test_variable_placeholder_vocabulary_is_exempt() -> None:
    authorization = RuntimeAppAuthorization(
        app_authorization_id="templated",
        resource_vocabulary="${vocab}",
    )
    assert authorization.resource_vocabulary == "${vocab}"


# --------------------------------------------------------------------------- #
# Credential redaction (no raw secret material; secret-named principal guard)
# --------------------------------------------------------------------------- #


def test_principal_has_no_raw_secret_field() -> None:
    fields = set(RuntimeAppAuthorizationPrincipal.model_fields)
    assert "credential_classification" in fields
    assert not (fields & {"password", "secret", "api_key", "hash", "value", "credential"})


def test_principal_carries_classification_only() -> None:
    principal = RuntimeAppAuthorizationPrincipal(
        principal_id="api-consumer",
        kind="api_key",
        credential_classification="redacted",
    )
    assert principal.credential_classification == RuntimeAppAuthorizationCredentialClassification.REDACTED


def test_secret_named_principal_may_use_none_classification() -> None:
    principal = RuntimeAppAuthorizationPrincipal(
        principal_id="root-api-key",
        name="root-api-key",
        credential_classification="none",
    )

    assert principal.credential_classification == RuntimeAppAuthorizationCredentialClassification.NONE


def test_secret_named_principal_with_redacted_classification_is_valid() -> None:
    principal = RuntimeAppAuthorizationPrincipal(
        principal_id="api-key-1",
        name="ingest-api-key",
        credential_classification="operator_secret",
    )
    assert principal.credential_classification == RuntimeAppAuthorizationCredentialClassification.OPERATOR_SECRET


def test_non_secret_named_principal_may_omit_classification() -> None:
    principal = RuntimeAppAuthorizationPrincipal(principal_id="plain-user", name="analyst")
    assert principal.credential_classification == RuntimeAppAuthorizationCredentialClassification.NONE


# --------------------------------------------------------------------------- #
# Optional-bool + list coercion behaviour
# --------------------------------------------------------------------------- #


def test_optional_bool_string_coercion() -> None:
    principal = RuntimeAppAuthorizationPrincipal(principal_id="p", reserved="true", hidden="false")
    assert principal.reserved is True
    assert principal.hidden is False

    authorization = RuntimeAppAuthorization(app_authorization_id="a", auth_enabled="no")
    assert authorization.auth_enabled is False


def test_scalar_list_fields_coerce_to_single_element_lists() -> None:
    grant = RuntimeAppAuthorizationGrant(grant_id="g", actions="read", resource_patterns="wazuh-*")
    assert grant.actions == ["read"]
    assert grant.resource_patterns == ["wazuh-*"]


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        RuntimeAppAuthorizationRole(role_id="r", bogus="x")
