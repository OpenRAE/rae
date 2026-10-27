"""Exact references for resource-scoped identity policy and secret state."""

from graphlib import CycleError, TopologicalSorter

from .._declarations import Declaration, DeclarationIndex, build_declaration_index
from .._reference_targetability import DECLARATION_CATEGORIES, DeclarationCategory
from .._runtime_service_families import iter_runtime_family_references
from ..runtime_application import RuntimeApplicationSurface
from ..runtime_directory_identity import RuntimeIdentityAuthority, RuntimeIdentityPolicy, RuntimeIdentitySubject
from ..runtime_identity_resources import (
    RuntimeIdentityAccessObservation,
    RuntimeIdentityPermissionBinding,
    RuntimeIdentityResourceAccess,
    RuntimeIdentityResourceScope,
    RuntimeIdentityUse,
)
from ..runtime_platform_application import RuntimePlatformApplication
from ..runtime_secret_service import RuntimeSecretConsumer, RuntimeSecretVersion, RuntimeServiceSecret

_Scopes = dict[str, RuntimeIdentityResourceScope]


class _CloudResourcesMixin:
    def _cloud_index(self) -> DeclarationIndex:
        if self._declaration_index is None:
            self._declaration_index = build_declaration_index(self._s, raise_on_collision=False)
        return self._declaration_index

    def _cloud_model(self, ref: str, types: type | tuple[type, ...], label: str) -> object | None:
        if self._is_unresolved_var(ref):
            return None
        reference = self._runtime_reference(ref)
        if reference is None or not isinstance(reference.item, types):
            self._err(f"cloud-reference: {label} requires an exact reference of the declared kind")
            return None
        return reference.item

    def _cloud_workload(self, declaration: Declaration) -> bool:
        if declaration.kind == "service":
            return True
        if declaration.kind == "node":
            return self._is_compute_node(declaration.model_tokens[1])
        runtime_ref = self._runtime_reference(declaration.address)
        return runtime_ref is not None and isinstance(
            runtime_ref.item, (RuntimeApplicationSurface, RuntimePlatformApplication)
        )

    def _cloud_resource(self, ref: str, label: str, *, workload: bool = False) -> Declaration | None:
        if self._is_unresolved_var(ref):
            return None
        declaration = self._cloud_index().declaration_for(ref)
        valid = declaration is not None and DECLARATION_CATEGORIES.get(declaration.kind) is DeclarationCategory.RESOURCE
        if valid and workload:
            valid = self._cloud_workload(declaration)
        if not valid:
            self._err(f"cloud-reference: {label} requires an exact resource reference")
            return None
        return declaration

    def _verify_cloud_resources(self) -> None:
        self._cloud_index()
        references = tuple(iter_runtime_family_references(self._s))
        scopes = {ref.address: ref.item for ref in references if isinstance(ref.item, RuntimeIdentityResourceScope)}
        policies = {ref.address: ref.item for ref in references if isinstance(ref.item, RuntimeIdentityPolicy)}
        self._verify_cloud_scopes(scopes)
        self._verify_cloud_policy_graph(policies)
        for reference in references:
            self._verify_cloud_item(reference.item, scopes)

    def _verify_cloud_scopes(self, scopes: _Scopes) -> None:
        for scope in scopes.values():
            self._verify_cloud_scope_parent(scope)
        self._cloud_acyclic(
            {key: (value.parent_ref,) if value.parent_ref in scopes else () for key, value in scopes.items()}, "scope"
        )

    def _verify_cloud_scope_parent(self, scope: RuntimeIdentityResourceScope) -> None:
        if not scope.parent_ref:
            return
        parent = self._cloud_model(scope.parent_ref, RuntimeIdentityResourceScope, "scope parent")
        if (
            parent is not None
            and parent.provider != scope.provider
            and not any(self._is_unresolved_var(value) for value in (parent.provider, scope.provider))
        ):
            self._err("cloud-provider: parent scope must retain the same provider identity")

    def _verify_cloud_policy_graph(self, policies: dict[str, RuntimeIdentityPolicy]) -> None:
        self._cloud_acyclic(
            {
                key: (value.resource_access.inherited_from_ref,)
                if value.resource_access and value.resource_access.inherited_from_ref in policies
                else ()
                for key, value in policies.items()
            },
            "policy",
        )

    def _verify_cloud_item(self, item: object, scopes: _Scopes) -> None:
        if isinstance(item, RuntimeIdentityAuthority):
            self._verify_cloud_authority(item)
        elif isinstance(item, RuntimeIdentitySubject) and item.resource_scope_ref:
            self._cloud_model(item.resource_scope_ref, RuntimeIdentityResourceScope, "subject scope")
        elif isinstance(item, RuntimePlatformApplication):
            self._verify_cloud_application(item)
        elif isinstance(item, RuntimeServiceSecret):
            self._verify_cloud_secret(item)
        elif isinstance(item, RuntimeIdentityPolicy) and item.resource_access:
            self._verify_cloud_policy(item.resource_access, scopes)

    def _verify_cloud_authority(self, authority: RuntimeIdentityAuthority) -> None:
        for use in authority.identity_uses:
            self._verify_cloud_use(use)
        for observation in authority.access_observations:
            self._verify_cloud_observation(observation)

    def _verify_cloud_use(self, use: RuntimeIdentityUse) -> None:
        self._cloud_resource(use.workload_ref, "workload reference", workload=True)
        self._cloud_model(use.principal_ref, RuntimeIdentitySubject, "principal reference")
        if use.source_principal_ref:
            self._cloud_model(use.source_principal_ref, RuntimeIdentitySubject, "source principal reference")

    def _verify_cloud_observation(self, observation: RuntimeIdentityAccessObservation) -> None:
        self._cloud_model(observation.principal_ref, RuntimeIdentitySubject, "observed principal reference")
        self._cloud_resource(observation.resource_ref, "observed resource reference")
        for context_ref in observation.context_refs:
            self._cloud_resource(context_ref, "observation context reference")

    def _verify_cloud_policy(self, access: RuntimeIdentityResourceAccess, scopes: _Scopes) -> None:
        self._cloud_resource(access.attachment_ref, "policy attachment reference")
        self._verify_cloud_policy_source(access, scopes)
        for binding in access.bindings:
            self._verify_cloud_binding(binding)

    def _verify_cloud_policy_source(self, access: RuntimeIdentityResourceAccess, scopes: _Scopes) -> None:
        if not access.inherited_from_ref:
            return
        source = self._cloud_model(access.inherited_from_ref, RuntimeIdentityPolicy, "inherited policy reference")
        if source is None:
            return
        if source.resource_access is None:
            self._err("cloud-policy: an inherited policy source requires resource access meaning")
        else:
            self._verify_cloud_inheritance(source.resource_access.attachment_ref, access.attachment_ref, scopes)

    def _verify_cloud_binding(self, binding: RuntimeIdentityPermissionBinding) -> None:
        for principal_ref in binding.principal_refs:
            self._cloud_model(principal_ref, RuntimeIdentitySubject, "policy principal reference")
        for resource_ref in binding.resource_refs:
            self._cloud_resource(resource_ref, "policy target reference")
        if binding.role_ref:
            role = self._cloud_model(binding.role_ref, RuntimeIdentitySubject, "policy role reference")
            if role is not None and role.kind != "role" and not self._is_unresolved_var(role.kind):
                self._err("cloud-policy: role reference must name a role subject")

    def _verify_cloud_inheritance(self, source_ref: str, target_ref: str, scopes: _Scopes) -> None:
        if any(self._is_unresolved_var(ref) for ref in (source_ref, target_ref)):
            return
        if source_ref in scopes:
            self._verify_cloud_scope_inheritance(source_ref, target_ref, scopes)
        elif not self._cloud_secret_parent(source_ref, target_ref):
            self._err("cloud-policy: inherited source must be a declared resource ancestry link")

    def _cloud_secret_parent(self, source_ref: str, target_ref: str) -> bool:
        source = self._runtime_reference(source_ref)
        target = self._runtime_reference(target_ref)
        return (
            source is not None
            and isinstance(source.item, RuntimeServiceSecret)
            and target is not None
            and isinstance(target.item, RuntimeSecretVersion)
            and any(target.item is version for version in source.item.versions)
        )

    def _verify_cloud_scope_inheritance(self, source_ref: str, target_ref: str, scopes: _Scopes) -> None:
        source_scope = self._cloud_owning_scope(source_ref, scopes)
        target_scope = self._cloud_owning_scope(target_ref, scopes)
        if self._is_unresolved_var(target_scope):
            return
        if source_scope is None or target_scope is None:
            self._err("cloud-policy: inheritance requires declared source and target scopes")
            return
        if source_ref == target_ref:
            self._err("cloud-policy: inherited source must be above its attachment in resource ancestry")
            return
        if not self._cloud_scope_reaches(target_scope, source_scope, scopes):
            self._err("cloud-policy: inherited source must belong to declared target ancestry")

    def _cloud_scope_reaches(self, current: str, source_scope: str, scopes: _Scopes) -> bool:
        seen = set()
        while current not in seen:
            if current == source_scope:
                return True
            seen.add(current)
            scope = scopes.get(current)
            if scope is None or not scope.parent_ref:
                break
            if self._is_unresolved_var(scope.parent_ref):
                return True
            current = scope.parent_ref
        return False

    def _cloud_owning_scope(self, ref: str, scopes: _Scopes) -> str | None:
        if ref in scopes:
            return ref
        runtime_ref = self._runtime_reference(ref)
        if (
            runtime_ref is not None
            and isinstance(runtime_ref.item, RuntimeSecretVersion)
            and isinstance(runtime_ref.owning_item, RuntimePlatformApplication)
        ):
            for secret in runtime_ref.owning_item.secrets:
                if any(runtime_ref.item is version for version in secret.versions):
                    return secret.resource_scope_ref or None
        return getattr(runtime_ref.item, "resource_scope_ref", None) if runtime_ref is not None else None

    def _verify_cloud_application(self, application: RuntimePlatformApplication) -> None:
        if application.resource_scope_ref:
            self._cloud_model(application.resource_scope_ref, RuntimeIdentityResourceScope, "application scope")
        for limit in application.cloud_limits:
            if limit.resource_scope_ref:
                self._cloud_model(limit.resource_scope_ref, RuntimeIdentityResourceScope, "service limit scope")

    def _verify_cloud_secret(self, secret: RuntimeServiceSecret) -> None:
        if secret.resource_scope_ref:
            self._cloud_model(secret.resource_scope_ref, RuntimeIdentityResourceScope, "secret scope")
        for field in ("encryption_key_ref", "reset_owner_ref", "deletion_owner_ref"):
            reference = getattr(secret, field)
            if reference:
                self._cloud_resource(reference, field)
        for version in secret.versions:
            self._verify_cloud_content_reference(version.payload_content_ref)
        for consumer in secret.consumers:
            self._verify_cloud_consumer(secret, consumer)

    def _verify_cloud_content_reference(self, reference: str) -> None:
        if not reference or self._is_unresolved_var(reference):
            return
        target = self._cloud_index().declaration_for(reference)
        if target is None or target.kind != "content":
            self._err("cloud-reference: payload content reference must name exact content")

    def _verify_cloud_consumer(self, secret: RuntimeServiceSecret, consumer: RuntimeSecretConsumer) -> None:
        self._cloud_resource(consumer.consumer_ref, "secret consumer reference", workload=True)
        for ref in (consumer.version_ref, consumer.resolved_version_ref):
            if ref:
                self._verify_cloud_selected_version(secret, ref)

    def _verify_cloud_selected_version(self, secret: RuntimeServiceSecret, ref: str) -> None:
        version = self._cloud_model(ref, RuntimeSecretVersion, "selected version reference")
        if version is not None and not any(version is candidate for candidate in secret.versions):
            self._err("cloud-version: selected version belongs to another secret")

    def _cloud_acyclic(self, graph: dict[str, tuple[str, ...]], label: str) -> None:
        try:
            TopologicalSorter(graph).prepare()
        except CycleError:
            self._err(f"cloud-cycle: {label} references must not form a cycle")
