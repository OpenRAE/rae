"""Cloud reference expectations for the existing identity and application owners."""

from tools.sdl_catalog_parity._paths import _SEMANTIC

_CLOUD_IDENTITY = "nodes.*.runtime.identity_authorities[]"
_CLOUD_APPLICATION = "nodes.*.runtime.platform_applications[]"
_CLOUD_RESOURCE_VALIDATOR = (
    "[cloud resource validator](../../implementations/python/packages/raes/validator/_cloud_resources.py)"
)

_SCOPE_TARGET = "runtime:resource_scopes"
_SUBJECT_TARGET = "runtime:subjects"
_RESOURCE_TARGET = "derived:cloud-resource"

CLOUD_RESOURCE_EXPECTATIONS: dict[str, tuple[str, str, str, str]] = {
    path: (
        target,
        _SEMANTIC,
        "fatal dangling, wrong kind, or conflicting ancestry",
        _CLOUD_RESOURCE_VALIDATOR,
    )
    for path, target in (
        (
            f"{_CLOUD_IDENTITY}.resource_scopes[].parent_ref",
            _SCOPE_TARGET,
        ),
        (
            f"{_CLOUD_IDENTITY}.subjects[].resource_scope_ref",
            _SCOPE_TARGET,
        ),
        (
            f"{_CLOUD_IDENTITY}.identity_uses[].workload_ref",
            "derived:cloud-workload",
        ),
        (f"{_CLOUD_IDENTITY}.identity_uses[].principal_ref", _SUBJECT_TARGET),
        (
            f"{_CLOUD_IDENTITY}.identity_uses[].source_principal_ref",
            _SUBJECT_TARGET,
        ),
        (
            f"{_CLOUD_IDENTITY}.policies[].resource_access.attachment_ref",
            _RESOURCE_TARGET,
        ),
        (
            f"{_CLOUD_IDENTITY}.policies[].resource_access.inherited_from_ref",
            "runtime:policies",
        ),
        (
            f"{_CLOUD_IDENTITY}.policies[].resource_access.bindings[].principal_refs[]",
            _SUBJECT_TARGET,
        ),
        (
            f"{_CLOUD_IDENTITY}.policies[].resource_access.bindings[].resource_refs[]",
            _RESOURCE_TARGET,
        ),
        (
            f"{_CLOUD_IDENTITY}.policies[].resource_access.bindings[].role_ref",
            _SUBJECT_TARGET,
        ),
        (
            f"{_CLOUD_IDENTITY}.access_observations[].principal_ref",
            _SUBJECT_TARGET,
        ),
        (
            f"{_CLOUD_IDENTITY}.access_observations[].resource_ref",
            _RESOURCE_TARGET,
        ),
        (
            f"{_CLOUD_IDENTITY}.access_observations[].context_refs[]",
            _RESOURCE_TARGET,
        ),
        (f"{_CLOUD_APPLICATION}.resource_scope_ref", _SCOPE_TARGET),
        (
            f"{_CLOUD_APPLICATION}.cloud_limits[].resource_scope_ref",
            _SCOPE_TARGET,
        ),
        (
            f"{_CLOUD_APPLICATION}.secrets[].resource_scope_ref",
            _SCOPE_TARGET,
        ),
        (
            f"{_CLOUD_APPLICATION}.secrets[].encryption_key_ref",
            _RESOURCE_TARGET,
        ),
        (
            f"{_CLOUD_APPLICATION}.secrets[].reset_owner_ref",
            _RESOURCE_TARGET,
        ),
        (
            f"{_CLOUD_APPLICATION}.secrets[].deletion_owner_ref",
            _RESOURCE_TARGET,
        ),
        (
            f"{_CLOUD_APPLICATION}.secrets[].versions[].payload_content_ref",
            "content",
        ),
        (
            f"{_CLOUD_APPLICATION}.secrets[].consumers[].consumer_ref",
            "derived:cloud-workload",
        ),
        (
            f"{_CLOUD_APPLICATION}.secrets[].consumers[].version_ref",
            "runtime:versions",
        ),
        (
            f"{_CLOUD_APPLICATION}.secrets[].consumers[].resolved_version_ref",
            "runtime:versions",
        ),
    )
}
