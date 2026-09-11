"""SemanticValidator _RuntimeServicesMixin (split from validator.py).

Part of the SemanticValidator mixin composition; see __init__.py.
"""

from ..runtime_ssh_server import SshMatchCriterionKind
from ._support import _NODES_PREFIX


class _RuntimeServicesMixin:
    def _verify_runtime_application(self) -> None:
        """Validate observed runtime application surfaces against the scenario.

        Each surface's owning service must resolve to a service on the same
        node; template/static refs should resolve to the
        node's observed file inventory when one is recorded (ADR-026).
        """
        for name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None or not runtime.applications:
                continue
            service_names = self._node_service_names(node)
            observed_paths = self._node_observed_paths(node)
            for application in runtime.applications:
                self._verify_application_service(name, application, service_names)
                for route in application.routes:
                    self._verify_route_refs(name, application, route, observed_paths)
                    self._verify_route_upstream_target(name, application, route)

    @staticmethod
    def _node_service_names(node: object) -> set[str]:
        return {service.name for service in getattr(node, "services", []) if service.name}

    @staticmethod
    def _node_services_by_name(node: object) -> dict[str, object]:
        return {service.name: service for service in getattr(node, "services", []) if service.name}

    @staticmethod
    def _node_observed_paths(node: object) -> set[str]:
        """Collect file paths the node observably exposes for template/static refs."""
        paths: set[str] = set()
        runtime = getattr(node, "runtime", None)
        if runtime is not None:
            paths.update(entry.path for entry in runtime.filesystem_inventory if entry.path)
        source = getattr(node, "source", None)
        build = getattr(source, "build", None) if source is not None else None
        if build is not None:
            paths.update(item.destination_path for item in build.copied_sources if item.destination_path)
            paths.update(item.destination_path for item in build.source_inputs if item.destination_path)
        return paths

    def _verify_application_service(self, node_name: str, application: object, service_names: set[str]) -> None:
        self._verify_owned_service_ref(
            node_name,
            getattr(application, "service", ""),
            service_names,
            owner_label=f"Node '{node_name}' runtime application '{application.application_id}'",
        )

    def _verify_owned_service_ref(
        self,
        node_name: str,
        ref: str,
        service_names: set[str],
        *,
        owner_label: str,
    ) -> None:
        """Validate a runtime surface's owning transport-service reference.

        The ref is a bare ``Node.services[].name`` or the qualified
        ``nodes.<node>.services.<name>`` form, and must resolve to a service on
        the same node. Shared by runtime applications, database services, and
        identity authority services.
        """
        if not ref or self._is_unresolved_var(ref):
            return
        service_name = ref
        if ref.startswith(_NODES_PREFIX):
            split = self._split_node_service_ref(ref)
            if split is None:
                self._err(
                    f"{owner_label} service ref '{ref}' must be a bare service name or 'nodes.<node>.services.<name>'"
                )
                return
            ref_node_name, service_name = split
            if ref_node_name != node_name:
                self._err(f"{owner_label} service ref '{ref}' must reference a service on the same node")
                return
        if service_name not in service_names:
            self._err(f"{owner_label} references undefined service '{service_name}'")

    def _resolve_owned_service_ref(
        self,
        node_name: str,
        ref: str,
        services_by_name: dict[str, object],
        *,
        owner_label: str,
    ) -> object | None:
        if not ref or self._is_unresolved_var(ref):
            return None
        service_name = self._owned_service_name(node_name, ref, owner_label=owner_label)
        if service_name is None:
            return None
        service = services_by_name.get(service_name)
        if service is None:
            self._err(f"{owner_label} references undefined service '{service_name}'")
        return service

    def _owned_service_name(self, node_name: str, ref: str, *, owner_label: str) -> str | None:
        """Resolve a bare or ``nodes.<node>.services.<name>`` ref to a same-node service name."""
        if not ref.startswith(_NODES_PREFIX):
            return ref
        split = self._split_node_service_ref(ref)
        if split is not None and split[0] == node_name:
            return split[1]
        if split is None:
            self._err(
                f"{owner_label} service ref '{ref}' must be a bare service name or 'nodes.<node>.services.<name>'"
            )
        else:
            self._err(f"{owner_label} service ref '{ref}' must reference a service on the same node")
        return None

    def _verify_route_upstream_target(self, node_name: str, application: object, route: object) -> None:
        target = getattr(route, "upstream_target", None)
        if target is None:
            return
        label = (
            f"Node '{node_name}' runtime application '{application.application_id}' "
            f"route '{route.route_id}' upstream_target"
        )
        target_node_name = self._check_proxy_upstream_node_ref(
            getattr(target, "target_node_ref", ""),
            label,
            context="upstream_target",
            field_name="target_node_ref",
        )
        self._check_proxy_upstream_service_ref(
            getattr(target, "target_service", ""),
            upstream_node_ref=target_node_name or "",
            relationship_target="",
            label=label,
            context="upstream_target",
            field_name="target_service",
        )

    def _verify_runtime_service_listeners(self) -> None:
        """Validate observed service listeners against same-node runtime facts."""
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None or not runtime.service_listeners:
                continue
            services_by_name = self._node_services_by_name(node)
            process_refs = self._node_runtime_process_refs(node)
            published_ports = self._node_published_port_keys(node)
            for listener in runtime.service_listeners:
                label = f"Node '{node_name}' runtime service listener '{listener.service_listener_id}'"
                service = self._resolve_owned_service_ref(
                    node_name,
                    getattr(listener, "service", ""),
                    services_by_name,
                    owner_label=label,
                )
                if service is not None:
                    self._verify_listener_service_binding(label, listener, service)
                self._verify_listener_process_ref(label, listener, process_refs)
                self._verify_listener_published_port_refs(label, listener, published_ports)

    def _verify_listener_service_binding(self, label: str, listener: object, service: object) -> None:
        listener_port = getattr(listener, "port", None)
        listener_protocol = self._enum_or_raw(getattr(listener, "protocol", ""))
        service_port = getattr(service, "port", None)
        service_protocol = getattr(service, "protocol", "")
        if any(self._is_unresolved_var(v) for v in (listener_port, listener_protocol, service_port, service_protocol)):
            return
        if listener_port is None:
            return
        if listener_port != service_port or str(listener_protocol).lower() != str(service_protocol).lower():
            self._err(f"{label} port/protocol must match service '{service.name}'")

    @staticmethod
    def _enum_or_raw(value: object) -> object:
        return value.value if hasattr(value, "value") else value

    def _verify_listener_process_ref(self, label: str, listener: object, process_refs: set[str]) -> None:
        ref = getattr(listener, "process_ref", "")
        if not ref or self._is_unresolved_var(ref):
            return
        if ref not in process_refs:
            self._err(f"{label} process_ref '{ref}' does not resolve to a runtime process name or pid")

    def _verify_listener_published_port_refs(
        self,
        label: str,
        listener: object,
        published_ports: set[tuple[str, int | str | None, int | str, str]],
    ) -> None:
        listener_port = getattr(listener, "port", None)
        listener_protocol = self._enum_or_raw(getattr(listener, "protocol", ""))
        for ref in getattr(listener, "published_port_refs", []):
            values = (ref.host_ip, ref.host_port, ref.container_port, ref.protocol)
            if any(self._is_unresolved_var(v) for v in values):
                continue
            if any(self._is_unresolved_var(v) for v in (listener_port, listener_protocol)):
                continue
            if listener_port is not None and (
                ref.container_port != listener_port or ref.protocol != str(listener_protocol).lower()
            ):
                self._err(f"{label} published_port_refs entry must match listener port/protocol")
                continue
            if values not in published_ports:
                self._err(f"{label} published_port_refs entry does not resolve to runtime.network.published_ports")

    def _node_runtime_process_refs(self, node: object) -> set[str]:
        runtime = getattr(node, "runtime", None)
        if runtime is None:
            return set()
        refs: set[str] = set()
        processes = [getattr(runtime, "process", None), *getattr(runtime, "processes", [])]
        for process in processes:
            if process is None:
                continue
            name = getattr(process, "name", "")
            pid = getattr(process, "pid", None)
            if name and not self._is_unresolved_var(name):
                refs.add(str(name))
            if pid is not None and not self._is_unresolved_var(pid):
                refs.add(str(pid))
        return refs

    @staticmethod
    def _node_published_port_keys(node: object) -> set[tuple[str, int | str | None, int | str, str]]:
        runtime = getattr(node, "runtime", None)
        network = getattr(runtime, "network", None) if runtime is not None else None
        if network is None:
            return set()
        return {
            (binding.host_ip, binding.host_port, binding.container_port, binding.protocol)
            for binding in network.published_ports
        }

    def _verify_route_refs(
        self,
        node_name: str,
        application: object,
        route: object,
        observed_paths: set[str],
    ) -> None:
        app_id = application.application_id
        route_id = route.route_id
        if not observed_paths:
            return
        for field_name in ("templates", "static_assets"):
            for ref in getattr(route, field_name):
                if self._is_unresolved_var(ref):
                    continue
                if ref not in observed_paths:
                    self._err(
                        f"Node '{node_name}' runtime application '{app_id}' route '{route_id}' "
                        f"{field_name} ref '{ref}' does not resolve to an observed file on the node"
                    )

    def _verify_runtime_service_manager_units(self) -> None:
        """Validate observed service-manager unit inventories (ADR-035).

        Each ``ServiceManagerUnit.service`` ref, when set and not a variable,
        must resolve to a service on the same node (bare name OR
        ``nodes.<this-node>.services.<name>``). When a ``unit_file_path`` is set
        and ``runtime.filesystem_inventory`` is non-empty, the path SHOULD
        appear in that inventory; otherwise we emit a soft semantic error so
        downstream consumers can tell unit-file evidence and filesystem
        inventory apart.
        """
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None or not runtime.service_manager_units:
                continue
            service_names = self._node_service_names(node)
            observed_paths = self._node_observed_paths(node)
            for unit in runtime.service_manager_units:
                owner_label = f"Node '{node_name}' runtime service_manager_unit '{unit.unit_id}'"
                self._verify_owned_service_ref(
                    node_name,
                    getattr(unit, "service", ""),
                    service_names,
                    owner_label=owner_label,
                )
                unit_file_path = getattr(unit, "unit_file_path", "")
                if (
                    unit_file_path
                    and observed_paths
                    and not self._is_unresolved_var(unit_file_path)
                    and unit_file_path not in observed_paths
                ):
                    self._err(
                        f"{owner_label} unit_file_path '{unit_file_path}' does not resolve to an "
                        f"observed file on the node"
                    )

    def _verify_runtime_ssh_servers(self) -> None:
        """Validate observed SSH server configurations against the scenario.

        Each ``RuntimeSshServer.service`` must resolve to a service on the
        same node (bare name OR ``nodes.<this-node>.services.<name>``).
        Each ``Match`` rule's ``LOCAL_USER`` criterion whose pattern is a
        concrete (non-wildcard, non-variable) literal MAY be cross-checked
        against ``runtime.local_identity.users`` when that inventory is
        present and non-empty (ADR-031 § "Semantic validation gate").
        """
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None or not runtime.ssh_servers:
                continue
            service_names = self._node_service_names(node)
            local_usernames = self._node_local_usernames(node)
            for server in runtime.ssh_servers:
                self._verify_ssh_server_service(node_name, server, service_names)
                for rule in server.match_rules:
                    self._verify_ssh_match_rule(node_name, server, rule, local_usernames)

    @staticmethod
    def _node_local_usernames(node: object) -> set[str]:
        runtime = getattr(node, "runtime", None)
        if runtime is None:
            return set()
        identity = getattr(runtime, "local_identity", None)
        if identity is None:
            return set()
        return {user.username for user in identity.users if user.username}

    def _verify_ssh_server_service(
        self,
        node_name: str,
        server: object,
        service_names: set[str],
    ) -> None:
        ref = getattr(server, "service", "")
        if not ref or self._is_unresolved_var(ref):
            return
        server_id = server.ssh_server_id
        service_name = ref
        if ref.startswith("nodes."):
            split = self._split_node_service_ref(ref)
            if split is None:
                self._err(
                    f"Node '{node_name}' runtime ssh_server '{server_id}' service ref '{ref}' "
                    f"must be a bare service name or 'nodes.<node>.services.<name>'"
                )
                return
            service_node_name, service_name = split
            if service_node_name != node_name:
                self._err(
                    f"Node '{node_name}' runtime ssh_server '{server_id}' service ref '{ref}' "
                    f"must reference a service on the same node"
                )
                return
        if service_name not in service_names:
            self._err(
                f"Node '{node_name}' runtime ssh_server '{server_id}' references undefined service '{service_name}'"
            )

    def _verify_ssh_match_rule(
        self,
        node_name: str,
        server: object,
        rule: object,
        local_usernames: set[str],
    ) -> None:
        if not local_usernames:
            return
        for criterion in rule.criteria:
            if criterion.kind != SshMatchCriterionKind.LOCAL_USER:
                continue
            pattern = criterion.pattern
            if self._is_unresolved_var(pattern):
                continue
            if any(ch in pattern for ch in "*?!,"):
                # Wildcard or comma-separated list — not a single concrete identity.
                continue
            if pattern not in local_usernames:
                self._err(
                    f"Node '{node_name}' runtime ssh_server '{server.ssh_server_id}' "
                    f"match rule '{rule.match_id}' references local user '{pattern}' "
                    f"not present in runtime.local_identity.users"
                )

    def _verify_runtime_app_authorizations(self) -> None:
        """Validate observed application-internal RBAC stores.

        Permission-grant and role-mapping ``role_ref`` values are
        authorization-local role references: each must resolve to a role
        declared within the same ``app_authorization`` store (RBAC96 /
        ANSI INCITS 359 role-permission and user-role assignment integrity).
        """
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None or not runtime.app_authorizations:
                continue
            for authorization in runtime.app_authorizations:
                self._verify_app_authorization_role_refs(node_name, authorization)

    def _verify_app_authorization_role_refs(self, node_name: str, authorization: object) -> None:
        role_ids = {role.role_id for role in authorization.roles}
        label = f"Node '{node_name}' runtime app_authorization '{authorization.app_authorization_id}'"
        for grant in authorization.permission_grants:
            self._verify_app_authorization_role_ref(
                f"{label} permission_grant '{grant.grant_id}'",
                getattr(grant, "role_ref", ""),
                role_ids,
            )
        for mapping in authorization.role_mappings:
            self._verify_app_authorization_role_ref(
                f"{label} role_mapping '{mapping.mapping_id}'",
                getattr(mapping, "role_ref", ""),
                role_ids,
            )

    def _verify_app_authorization_role_ref(self, owner_label: str, role_ref: str, role_ids: set[str]) -> None:
        if not role_ref or self._is_unresolved_var(role_ref):
            return
        if role_ref not in role_ids:
            self._err(f"{owner_label} role_ref '{role_ref}' is not a role in the authorization")

    def _verify_runtime_capability_overrides(self) -> None:
        """Cross-check ``linux_capabilities.process_overrides`` selectors.

        Per ADR-030, scoped capability records identify a subject via
        ``RuntimeProcessIdentity`` selectors and the capability list ships
        through the same closed-world Pydantic gates as the container-wide
        lists. The only check that cannot live on the model itself is the
        scenario-level cross-reference: when an override's
        ``subject.name`` is a literal value and the enclosing node declares
        ``runtime.processes``, the name SHOULD match one of those observed
        processes. A miss is reported as an error so inventories that
        forget to add the new process surface fail fast rather than ship a
        scoped-policy claim that points at nothing.
        """
        for node_name, node in self._s.nodes.items():
            overrides = self._capability_overrides_for(node)
            if not overrides:
                continue
            observed = self._observed_process_names(node)
            if not observed:
                # No declared process inventory to cross-check against — the
                # override stands on its own selectors.
                continue
            self._check_override_subject_names(node_name, overrides, observed)

    @staticmethod
    def _capability_overrides_for(node: object) -> list[object]:
        runtime = getattr(node, "runtime", None)
        if runtime is None:
            return []
        capability_policy = getattr(runtime, "linux_capabilities", None)
        if capability_policy is None:
            return []
        return list(getattr(capability_policy, "process_overrides", None) or [])

    def _observed_process_names(self, node: object) -> set[str]:
        runtime = getattr(node, "runtime", None)
        if runtime is None:
            return set()
        return {
            process.name
            for process in (runtime.processes or [])
            if process.name and not self._is_unresolved_var(process.name)
        }

    def _check_override_subject_names(
        self,
        node_name: str,
        overrides: list[object],
        observed: set[str],
    ) -> None:
        for override in overrides:
            subject_name = override.subject.name
            if not subject_name or self._is_unresolved_var(subject_name):
                continue
            if subject_name not in observed:
                self._err(
                    f"Node '{node_name}' runtime capability override subject "
                    f"'{subject_name}' does not match any process declared in "
                    "'runtime.processes'"
                )
