"""Rewrite declared cloud references without inspecting native provider data."""

from typing import Any

from ._references import _maybe_rename


def rewrite_cloud_runtime(runtime: dict[str, Any], symbols: dict[str, Any]) -> None:
    named = symbols["named"]
    for authority in runtime.get("identity_authorities", []):
        _rewrite_authority(authority, named)
    for application in runtime.get("platform_applications", []):
        _rewrite_application(application, named)


def _rewrite_authority(authority: dict[str, Any], named: dict[str, str]) -> None:
    for scope in authority.get("resource_scopes", []):
        _refs(scope, named, "parent_ref")
    for subject in authority.get("subjects", []):
        _refs(subject, named, "resource_scope_ref")
    for use in authority.get("identity_uses", []):
        _refs(use, named, "workload_ref", "principal_ref", "source_principal_ref")
    for policy in authority.get("policies", []):
        _rewrite_policy(policy, named)
    for observation in authority.get("access_observations", []):
        _refs(observation, named, "principal_ref", "resource_ref")
        _ref_list(observation, named, "context_refs")


def _rewrite_policy(policy: dict[str, Any], named: dict[str, str]) -> None:
    access = policy.get("resource_access")
    if access is None:
        return
    _refs(access, named, "attachment_ref", "inherited_from_ref")
    for binding in access.get("bindings", []):
        _refs(binding, named, "role_ref")
        _ref_list(binding, named, "principal_refs", "resource_refs")


def _rewrite_application(application: dict[str, Any], named: dict[str, str]) -> None:
    _refs(application, named, "resource_scope_ref")
    for limit in application.get("cloud_limits", []):
        _refs(limit, named, "resource_scope_ref")
    for secret in application.get("secrets", []):
        _rewrite_secret(secret, named)


def _rewrite_secret(secret: dict[str, Any], named: dict[str, str]) -> None:
    _refs(secret, named, "resource_scope_ref", "encryption_key_ref", "reset_owner_ref", "deletion_owner_ref")
    for version in secret.get("versions", []):
        _refs(version, named, "payload_content_ref")
    for consumer in secret.get("consumers", []):
        _refs(consumer, named, "consumer_ref", "version_ref", "resolved_version_ref")


def _refs(record: dict[str, Any], named: dict[str, str], *fields: str) -> None:
    for field in fields:
        if record.get(field):
            record[field] = _maybe_rename(record[field], named)


def _ref_list(record: dict[str, Any], named: dict[str, str], *fields: str) -> None:
    for field in fields:
        if field in record:
            record[field] = [_maybe_rename(value, named) for value in record[field]]
