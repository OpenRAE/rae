"""SemanticValidator _RuntimeIdentityDataMixin (split from validator.py).

Part of the SemanticValidator mixin composition; see __init__.py.
"""

from ..runtime_database import DatabaseObjectType
from ._support import _NODES_PREFIX


class _RuntimeIdentityDataMixin:
    def _verify_runtime_identity_authorities(self) -> None:
        """Validate observed identity authorities against the scenario.

        Authority endpoint ``service`` refs resolve like other node-scoped
        runtime service ownership claims. Relationship and policy refs are
        local to the authority inventory so membership and trust facts cannot
        silently point at missing users, groups, policies, or the authority
        record itself.
        """
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None or not runtime.identity_authorities:
                continue
            service_names = self._node_service_names(node)
            for authority in runtime.identity_authorities:
                self._verify_identity_authority_services(node_name, authority, service_names)
                local_refs = self._identity_authority_local_refs(authority)
                self._verify_identity_authority_relationships(node_name, authority, local_refs)
                self._verify_identity_authority_policies(node_name, authority, local_refs)

    def _verify_identity_authority_services(
        self,
        node_name: str,
        authority: object,
        service_names: set[str],
    ) -> None:
        for service in authority.services:
            self._verify_owned_service_ref(
                node_name,
                getattr(service, "service", ""),
                service_names,
                owner_label=(
                    f"Node '{node_name}' runtime identity authority '{authority.identity_authority_id}' "
                    f"service '{service.service_id}'"
                ),
            )

    @staticmethod
    def _identity_authority_local_refs(authority: object) -> set[str]:
        refs = {authority.identity_authority_id}
        refs.update(service.service_id for service in authority.services)
        refs.update(subject.subject_id for subject in authority.subjects)
        refs.update(policy.policy_id for policy in authority.policies)
        refs.update(relationship.relationship_id for relationship in authority.relationships)
        refs.update(scope.scope_id for scope in authority.resource_scopes)
        refs.update(use.use_id for use in authority.identity_uses)
        refs.update(observation.observation_id for observation in authority.access_observations)
        return refs

    def _verify_identity_authority_relationships(
        self,
        node_name: str,
        authority: object,
        local_refs: set[str],
    ) -> None:
        label = f"Node '{node_name}' runtime identity authority '{authority.identity_authority_id}'"
        for relationship in authority.relationships:
            rel_label = f"{label} relationship '{relationship.relationship_id}'"
            self._verify_identity_ref(
                getattr(relationship, "source_ref", ""),
                local_refs,
                label=rel_label,
                field_name="source_ref",
            )
            if relationship.target_ref:
                self._verify_identity_ref(
                    relationship.target_ref,
                    local_refs,
                    label=rel_label,
                    field_name="target_ref",
                )

    def _verify_identity_authority_policies(
        self,
        node_name: str,
        authority: object,
        local_refs: set[str],
    ) -> None:
        label = f"Node '{node_name}' runtime identity authority '{authority.identity_authority_id}'"
        for policy in authority.policies:
            policy_label = f"{label} policy '{policy.policy_id}'"
            for ref in policy.applies_to_refs:
                self._verify_identity_ref(
                    ref,
                    local_refs,
                    label=policy_label,
                    field_name="applies_to_ref",
                )

    def _verify_identity_ref(
        self,
        ref: str,
        local_refs: set[str],
        *,
        label: str,
        field_name: str,
    ) -> None:
        if self._is_unresolved_var(ref):
            return
        if ref not in local_refs:
            self._err(f"{label} {field_name} '{ref}' does not resolve inside identity authority")

    # File-service surface (ADR-037).

    _FILE_SERVICE_SUBJECT_LITERALS: frozenset[str] = frozenset({"anonymous", "guest"})

    def _verify_runtime_file_services(self) -> None:
        """Validate observed runtime file services against the scenario.

        Each service's owning transport service must resolve to a service on
        the same node (mirroring ``runtime.applications``). Rule/observation
        ``subject_ref`` resolves against service-local principal ids plus the
        reserved literals ``anonymous`` and ``guest``. ``resource_ref``
        resolves against service-local share ids; a ``share_id:path`` form is
        allowed for narrowed resources. Optional ``local_user_ref`` and
        ``directory_subject_ref`` on a principal are checked against
        ``runtime.local_identity.users`` and the qualified identity-authority
        ref shape, respectively, when present.
        """
        identity_subject_refs = self._identity_authority_subject_refs()
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None or not runtime.file_services:
                continue
            service_names = self._node_service_names(node)
            local_user_names = self._node_local_user_names(node)
            for service in runtime.file_services:
                owner_label = f"Node '{node_name}' runtime file service '{service.file_service_id}'"
                self._verify_owned_service_ref(
                    node_name,
                    getattr(service, "service", ""),
                    service_names,
                    owner_label=owner_label,
                )
                self._verify_file_service_principals(
                    owner_label,
                    service,
                    local_user_names,
                    identity_subject_refs,
                )
                share_ids = {share.share_id for share in service.shares}
                subject_refs = {
                    principal.principal_id for principal in service.principals
                } | self._FILE_SERVICE_SUBJECT_LITERALS
                for rule in service.access_rules:
                    self._verify_file_service_ref(
                        rule.subject_ref,
                        subject_refs,
                        label=f"{owner_label} rule '{rule.rule_id}'",
                        field_name="subject_ref",
                    )
                    self._verify_file_service_resource_ref(
                        rule.resource_ref,
                        share_ids,
                        label=f"{owner_label} rule '{rule.rule_id}'",
                    )
                for observation in service.access_observations:
                    self._verify_file_service_ref(
                        observation.subject_ref,
                        subject_refs,
                        label=f"{owner_label} observation '{observation.observation_id}'",
                        field_name="subject_ref",
                    )
                    self._verify_file_service_resource_ref(
                        observation.resource_ref,
                        share_ids,
                        label=f"{owner_label} observation '{observation.observation_id}'",
                    )

    @staticmethod
    def _node_local_user_names(node: object) -> set[str]:
        runtime = getattr(node, "runtime", None)
        local_identity = getattr(runtime, "local_identity", None) if runtime is not None else None
        if local_identity is None:
            return set()
        return {user.username for user in getattr(local_identity, "users", []) if user.username}

    def _identity_authority_subject_refs(self) -> set[str]:
        """Qualified subject refs across all node-scoped identity authorities.

        Shape: ``nodes.<node>.runtime.identity_authorities.<authority>.subjects.<subject>``.
        Used by file-service ``directory_subject_ref`` resolution so a
        principal cannot smuggle a dangling pointer at a missing authority or
        subject past semantic validation.
        """
        refs: set[str] = set()
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None:
                continue
            for authority in runtime.identity_authorities:
                base = f"{_NODES_PREFIX}{node_name}.runtime.identity_authorities.{authority.identity_authority_id}"
                for subject in authority.subjects:
                    refs.add(f"{base}.subjects.{subject.subject_id}")
        return refs

    def _verify_file_service_principals(
        self,
        owner_label: str,
        service: object,
        local_user_names: set[str],
        identity_subject_refs: set[str],
    ) -> None:
        for principal in service.principals:
            local_user_ref = getattr(principal, "local_user_ref", "")
            if local_user_ref and not self._is_unresolved_var(local_user_ref):
                if local_user_names and local_user_ref not in local_user_names:
                    self._err(
                        f"{owner_label} principal '{principal.principal_id}' local_user_ref "
                        f"'{local_user_ref}' does not resolve to a runtime.local_identity user"
                    )
            directory_ref = getattr(principal, "directory_subject_ref", "")
            if not directory_ref or self._is_unresolved_var(directory_ref):
                continue
            if not directory_ref.startswith(_NODES_PREFIX):
                self._err(
                    f"{owner_label} principal '{principal.principal_id}' "
                    f"directory_subject_ref '{directory_ref}' must be a qualified "
                    f"'nodes.<node>.runtime.identity_authorities.<id>.subjects.<id>' reference"
                )
                continue
            if directory_ref not in identity_subject_refs:
                self._err(
                    f"{owner_label} principal '{principal.principal_id}' "
                    f"directory_subject_ref '{directory_ref}' does not resolve to a known "
                    "identity-authority subject"
                )

    def _verify_file_service_ref(
        self,
        ref: str,
        local_refs: set[str],
        *,
        label: str,
        field_name: str,
    ) -> None:
        if not ref or self._is_unresolved_var(ref):
            return
        if ref not in local_refs:
            self._err(f"{label} {field_name} '{ref}' does not resolve inside file service")

    def _verify_file_service_resource_ref(
        self,
        ref: str,
        share_ids: set[str],
        *,
        label: str,
    ) -> None:
        if not ref or self._is_unresolved_var(ref):
            return
        share_segment = ref.split(":", 1)[0]
        if share_segment not in share_ids:
            self._err(f"{label} resource_ref '{ref}' does not resolve to a share in the file service")

    def _verify_runtime_database_services(self) -> None:
        """Validate observed database services against the scenario.

        Each service's owning transport service must resolve to a service on
        the same node (mirroring ``runtime.applications``); grant grantee/object
        refs must resolve to roles and logical objects within the same service
        (ADR-029 §6).
        """
        for name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None or not runtime.database_services:
                continue
            service_names = self._node_service_names(node)
            for dbsvc in runtime.database_services:
                self._verify_owned_service_ref(
                    name,
                    getattr(dbsvc, "service", ""),
                    service_names,
                    owner_label=f"Node '{name}' runtime database service '{dbsvc.database_service_id}'",
                )
                self._verify_database_grants(name, dbsvc)

    def _verify_database_grants(self, node_name: str, dbsvc: object) -> None:
        role_ids = {role.role_id for role in dbsvc.roles}
        objects_by_type: dict[str, set[str]] = {
            "database": {db.database_id for db in dbsvc.databases},
            "schema": {schema.schema_id for db in dbsvc.databases for schema in db.schemas},
            "table": {table.table_id for db in dbsvc.databases for schema in db.schemas for table in schema.tables},
        }
        label = f"Node '{node_name}' runtime database service '{dbsvc.database_service_id}'"
        for grant in dbsvc.grants:
            if not self._is_unresolved_var(grant.grantee_role_ref) and grant.grantee_role_ref not in role_ids:
                self._err(f"{label} grant grantee_role_ref '{grant.grantee_role_ref}' is not a role in the service")
            object_type = grant.object_type
            type_value = object_type.value if isinstance(object_type, DatabaseObjectType) else object_type
            if self._is_unresolved_var(grant.object_ref) or self._is_unresolved_var(type_value):
                continue
            if grant.object_ref not in objects_by_type.get(type_value, set()):
                self._err(f"{label} grant object_ref '{grant.object_ref}' is not a {type_value} in the service")

    def _verify_runtime_dns_services(self) -> None:
        """Validate observed DNS services against the scenario.

        Each DNS service's owning transport service must resolve to a service
        on the same node. Optional configuration, log, and zone-file refs are
        checked against ``runtime.filesystem_inventory`` when the node has an
        observed file inventory, keeping evidence paths tied to node-scoped
        runtime facts without embedding raw zone-file content.
        """
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None or not runtime.dns_services:
                continue
            service_names = self._node_service_names(node)
            observed_paths = self._node_observed_paths(node)
            for dns_service in runtime.dns_services:
                owner_label = f"Node '{node_name}' runtime DNS service '{dns_service.dns_service_id}'"
                self._verify_owned_service_ref(
                    node_name,
                    getattr(dns_service, "service", ""),
                    service_names,
                    owner_label=owner_label,
                )
                self._verify_dns_file_refs(
                    owner_label,
                    getattr(dns_service, "configuration_file_refs", []),
                    field_name="configuration_file_refs",
                    observed_paths=observed_paths,
                )
                self._verify_dns_file_refs(
                    owner_label,
                    getattr(dns_service, "log_file_refs", []),
                    field_name="log_file_refs",
                    observed_paths=observed_paths,
                )
                for zone in dns_service.zones:
                    self._verify_dns_file_refs(
                        f"{owner_label} zone '{zone.zone_id}'",
                        getattr(zone, "zone_file_refs", []),
                        field_name="zone_file_refs",
                        observed_paths=observed_paths,
                    )

    def _verify_dns_file_refs(
        self,
        owner_label: str,
        refs: list[str],
        *,
        field_name: str,
        observed_paths: set[str],
    ) -> None:
        if not observed_paths:
            return
        for ref in refs:
            if self._is_unresolved_var(ref):
                continue
            if ref not in observed_paths:
                self._err(f"{owner_label} {field_name} ref '{ref}' does not resolve to an observed file on the node")
