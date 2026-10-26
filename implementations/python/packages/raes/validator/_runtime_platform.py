"""SemanticValidator _RuntimePlatformMixin (split from validator.py).

Part of the SemanticValidator mixin composition; see __init__.py.
"""

from collections import defaultdict

from .._reference_targetability import ReferencePurpose


class _RuntimePlatformMixin:
    def _verify_runtime_security_monitoring_managers(self) -> None:
        """Validate observed SIEM/security-monitoring manager inventories.

        Manager and listener service refs are node-local transport ownership
        claims. File refs are checked only when a filesystem inventory exists,
        matching the DNS and mail runtime surfaces' evidence-bound posture.
        Agent/group and setting/component refs are manager-local stable ids.
        """
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None or not runtime.security_monitoring_managers:
                continue
            service_names = self._node_service_names(node)
            observed_paths = self._node_observed_paths(node)
            for manager in runtime.security_monitoring_managers:
                self._verify_security_monitoring_manager(
                    node_name=node_name,
                    manager=manager,
                    service_names=service_names,
                    observed_paths=observed_paths,
                )

    def _verify_security_monitoring_manager(
        self,
        *,
        node_name: str,
        manager: object,
        service_names: set[str],
        observed_paths: set[str],
    ) -> None:
        owner_label = (
            f"Node '{node_name}' runtime security-monitoring manager '{manager.security_monitoring_manager_id}'"
        )
        self._verify_owned_service_ref(
            node_name,
            getattr(manager, "service", ""),
            service_names,
            owner_label=owner_label,
        )
        self._verify_dns_file_refs(
            owner_label,
            getattr(manager, "configuration_file_refs", []),
            field_name="configuration_file_refs",
            observed_paths=observed_paths,
        )
        self._verify_dns_file_refs(
            owner_label,
            getattr(manager, "log_file_refs", []),
            field_name="log_file_refs",
            observed_paths=observed_paths,
        )
        self._verify_dns_file_refs(
            owner_label,
            getattr(manager, "evidence_refs", []),
            field_name="evidence_refs",
            observed_paths=observed_paths,
        )
        self._verify_security_monitoring_children(
            node_name=node_name,
            manager=manager,
            owner_label=owner_label,
            service_names=service_names,
            observed_paths=observed_paths,
        )

    def _verify_security_monitoring_children(
        self,
        *,
        node_name: str,
        manager: object,
        owner_label: str,
        service_names: set[str],
        observed_paths: set[str],
    ) -> None:
        ids = self._security_monitoring_local_ids(manager)
        for listener in manager.listeners:
            self._verify_owned_service_ref(
                node_name,
                getattr(listener, "service", ""),
                service_names,
                owner_label=f"{owner_label} listener '{listener.listener_id}'",
            )
        self._verify_sm_agent_groups(manager, owner_label, ids, observed_paths)
        self._verify_sm_agents(manager, owner_label, ids)
        for content_set in manager.content_sets:
            self._verify_dns_file_refs(
                f"{owner_label} content_set '{content_set.content_id}'",
                getattr(content_set, "file_refs", []),
                field_name="file_refs",
                observed_paths=observed_paths,
            )
        for definition in manager.detection_definitions:
            self._verify_sm_definition(definition, owner_label, ids, observed_paths)
        self._verify_sm_settings(manager, owner_label, ids, observed_paths)

    @staticmethod
    def _security_monitoring_local_ids(manager: object) -> dict[str, set[str]]:
        return {
            "component": {component.component_id for component in manager.components},
            "agent": {agent.agent_id for agent in manager.agents},
            "group": {group.group_id for group in manager.agent_groups},
            "content_set": {content_set.content_id for content_set in manager.content_sets},
            "definition": {definition.definition_id for definition in manager.detection_definitions},
        }

    def _verify_sm_agent_groups(
        self, manager: object, owner_label: str, ids: dict[str, set[str]], observed_paths: set[str]
    ) -> None:
        for group in manager.agent_groups:
            group_label = f"{owner_label} agent_group '{group.group_id}'"
            self._verify_dns_file_refs(
                group_label,
                getattr(group, "configuration_file_refs", []),
                field_name="configuration_file_refs",
                observed_paths=observed_paths,
            )
            for member_ref in group.member_refs:
                self._verify_security_monitoring_local_ref(
                    member_ref,
                    ids["agent"],
                    owner_label=group_label,
                    field_name="member_ref",
                    target_label="agent",
                )

    def _verify_sm_agents(self, manager: object, owner_label: str, ids: dict[str, set[str]]) -> None:
        for agent in manager.agents:
            agent_label = f"{owner_label} agent '{agent.agent_id}'"
            for group_ref in agent.group_refs:
                self._verify_security_monitoring_local_ref(
                    group_ref,
                    ids["group"],
                    owner_label=agent_label,
                    field_name="group_ref",
                    target_label="agent group",
                )

    def _verify_sm_definition(
        self, definition: object, owner_label: str, ids: dict[str, set[str]], observed_paths: set[str]
    ) -> None:
        definition_label = f"{owner_label} detection_definition '{definition.definition_id}'"
        self._verify_security_monitoring_local_ref(
            getattr(definition, "content_set_ref", ""),
            ids["content_set"],
            owner_label=definition_label,
            field_name="content_set_ref",
            target_label="content set",
        )
        self._verify_dns_file_refs(
            definition_label,
            [definition.source_file_ref] if definition.source_file_ref else [],
            field_name="source_file_ref",
            observed_paths=observed_paths,
        )
        self._verify_dns_file_refs(
            definition_label,
            getattr(definition, "evidence_refs", []),
            field_name="evidence_refs",
            observed_paths=observed_paths,
        )
        for field_name, refs in (
            ("if_sid_ref", getattr(definition, "if_sid_refs", [])),
            ("if_matched_sid_ref", getattr(definition, "if_matched_sid_refs", [])),
            ("parent_definition_ref", getattr(definition, "parent_definition_refs", [])),
        ):
            for ref in refs:
                self._verify_security_monitoring_local_ref(
                    ref,
                    ids["definition"],
                    owner_label=definition_label,
                    field_name=field_name,
                    target_label="detection definition",
                )
        source_artifact_ref = getattr(definition, "source_artifact_ref", "")
        if source_artifact_ref and not self._is_unresolved_var(source_artifact_ref):
            self._validate_named_ref(
                source_artifact_ref,
                owner_label=definition_label,
                ref_label="source_artifact_ref",
            )
        for target_ref in getattr(definition, "target_refs", []):
            if self._is_unresolved_var(target_ref):
                continue
            self._validate_named_ref(
                target_ref,
                owner_label=definition_label,
                ref_label="target_ref",
                purpose=ReferencePurpose.TARGETABLE,
            )

    def _verify_sm_settings(
        self, manager: object, owner_label: str, ids: dict[str, set[str]], observed_paths: set[str]
    ) -> None:
        for setting in manager.settings:
            setting_label = f"{owner_label} setting '{setting.setting_id}'"
            self._verify_security_monitoring_local_ref(
                getattr(setting, "component_ref", ""),
                ids["component"],
                owner_label=setting_label,
                field_name="component_ref",
                target_label="component",
            )
            self._verify_dns_file_refs(
                setting_label,
                [setting.source_path] if setting.source_path else [],
                field_name="source_path",
                observed_paths=observed_paths,
            )

    def _verify_security_monitoring_local_ref(
        self,
        ref: str,
        local_refs: set[str],
        *,
        owner_label: str,
        field_name: str,
        target_label: str,
    ) -> None:
        if not ref or self._is_unresolved_var(ref):
            return
        if ref not in local_refs:
            self._err(
                f"{owner_label} {field_name} '{ref}' does not resolve to a "
                f"{target_label} in the security-monitoring manager"
            )

    def _verify_runtime_datastore_services(self) -> None:
        """Validate observed datastore services against the scenario.

        Each service's owning transport service must resolve to a service on
        the same node (mirroring ``runtime.applications`` and
        ``runtime.database_services``); a non-empty, non-variable
        ``authorization_ref`` must resolve to an ``app_authorization`` declared
        on the same node's runtime (the delegated internal RBAC store).
        """
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None or not runtime.datastore_services:
                continue
            service_names = self._node_service_names(node)
            authorization_ids = self._node_app_authorization_ids(runtime)
            for datastore in runtime.datastore_services:
                owner_label = f"Node '{node_name}' runtime datastore service '{datastore.datastore_service_id}'"
                self._verify_owned_service_ref(
                    node_name,
                    getattr(datastore, "service", ""),
                    service_names,
                    owner_label=owner_label,
                )
                self._verify_runtime_authorization_ref(
                    getattr(datastore, "authorization_ref", ""),
                    authorization_ids,
                    owner_label=owner_label,
                )

    def _verify_runtime_platform_applications(self) -> None:
        """Validate observed platform-application inventories against the scenario.

        Each application's owning transport service must resolve to a service on
        the same node; a non-empty, non-variable ``authorization_ref`` must
        resolve to a same-node ``app_authorization``; content-object
        ``references`` must resolve to sibling ``content_object_id`` values and
        ``marking_refs`` to sibling ``marking_id`` values within the same
        application (intra-application referential integrity).
        """
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None or not runtime.platform_applications:
                continue
            service_names = self._node_service_names(node)
            authorization_ids = self._node_app_authorization_ids(runtime)
            for application in runtime.platform_applications:
                self._verify_platform_application(
                    node_name=node_name,
                    application=application,
                    service_names=service_names,
                    authorization_ids=authorization_ids,
                )

    def _verify_platform_application(
        self,
        *,
        node_name: str,
        application: object,
        service_names: set[str],
        authorization_ids: set[str],
    ) -> None:
        owner_label = f"Node '{node_name}' runtime platform application '{application.platform_application_id}'"
        self._verify_owned_service_ref(
            node_name,
            getattr(application, "service", ""),
            service_names,
            owner_label=owner_label,
        )
        self._verify_runtime_authorization_ref(
            getattr(application, "authorization_ref", ""),
            authorization_ids,
            owner_label=owner_label,
        )
        content_object_ids = {obj.content_object_id for obj in application.content_objects}
        marking_ids = {marking.marking_id for marking in application.markings}
        for content_object in application.content_objects:
            self._verify_platform_content_object(content_object, owner_label, content_object_ids, marking_ids)

    def _verify_platform_content_object(
        self, content_object: object, owner_label: str, content_object_ids: set[str], marking_ids: set[str]
    ) -> None:
        object_label = f"{owner_label} content_object '{content_object.content_object_id}'"
        for reference in content_object.references:
            if self._is_unresolved_var(reference):
                continue
            if reference not in content_object_ids:
                self._err(
                    f"{object_label} reference '{reference}' does not resolve to a "
                    f"content_object in the platform application"
                )
        for marking_ref in content_object.marking_refs:
            if self._is_unresolved_var(marking_ref):
                continue
            if marking_ref not in marking_ids:
                self._err(
                    f"{object_label} marking_ref '{marking_ref}' does not resolve to a "
                    f"marking in the platform application"
                )

    @staticmethod
    def _node_app_authorization_ids(runtime: object) -> set[str]:
        """Collect ``app_authorization_id`` values declared on a node's runtime."""
        return {
            authorization.app_authorization_id
            for authorization in getattr(runtime, "app_authorizations", [])
            if authorization.app_authorization_id
        }

    def _verify_runtime_authorization_ref(
        self,
        authorization_ref: str,
        authorization_ids: set[str],
        *,
        owner_label: str,
    ) -> None:
        """Resolve a delegated ``authorization_ref`` to a same-node app_authorization."""
        if not authorization_ref or self._is_unresolved_var(authorization_ref):
            return
        if authorization_ref not in authorization_ids:
            self._err(
                f"{owner_label} authorization_ref '{authorization_ref}' does not resolve to an "
                f"app_authorization on the same node"
            )

    def _verify_runtime_forwarding_agents(self) -> None:
        """Validate observed forwarding / intel-sync agent inventories.

        A ship target's ``target_node_ref``, when present and concrete, must
        resolve to a defined node; a present, concrete ``target_service_ref``
        must resolve to a service on that referenced node (or, when no node ref
        is given, to a service on the owning node). The agent-internal
        ``require_profile_for_agent_kind`` guard (model-local) has already
        enforced the per-``agent_kind`` profile shape.
        """
        self._verify_forwarding_agent_id_uniqueness()
        for agent in self._s.forwarding_agents:
            owner_label = f"Scenario forwarding agent '{agent.forwarding_agent_id}'"
            for target in agent.ship_targets:
                self._verify_scenario_forwarding_ship_target(
                    target=target,
                    owner_label=f"{owner_label} ship_target '{target.target_id}'",
                )
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None or not runtime.forwarding_agents:
                continue
            local_service_names = self._node_service_names(node)
            for agent in runtime.forwarding_agents:
                owner_label = f"Node '{node_name}' runtime forwarding agent '{agent.forwarding_agent_id}'"
                for target in agent.ship_targets:
                    self._verify_forwarding_ship_target(
                        node_name=node_name,
                        local_service_names=local_service_names,
                        target=target,
                        owner_label=f"{owner_label} ship_target '{target.target_id}'",
                    )

    def _verify_forwarding_agent_id_uniqueness(self) -> None:
        locations: dict[str, list[str]] = defaultdict(list)
        for agent in self._s.forwarding_agents:
            if agent.forwarding_agent_id:
                locations[agent.forwarding_agent_id].append("scenario forwarding_agents")
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None:
                continue
            for agent in getattr(runtime, "forwarding_agents", []):
                if agent.forwarding_agent_id:
                    locations[agent.forwarding_agent_id].append(f"node '{node_name}' runtime.forwarding_agents")

        for agent_id, agent_locations in locations.items():
            if len(agent_locations) > 1:
                self._err(f"Duplicate forwarding_agent_id '{agent_id}' across {', '.join(agent_locations)}")

    def _verify_scenario_forwarding_ship_target(self, *, target: object, owner_label: str) -> None:
        node_ref = getattr(target, "target_node_ref", "")
        service_ref = getattr(target, "target_service_ref", "")
        resolved_node = None
        if node_ref and not self._is_unresolved_var(node_ref):
            resolved_node = self._s.nodes.get(node_ref)
            if resolved_node is None:
                self._err(f"{owner_label} target_node_ref '{node_ref}' does not resolve to a defined node")
                return

        if not service_ref or self._is_unresolved_var(service_ref):
            return
        if not node_ref:
            self._err(
                f"{owner_label} target_service_ref '{service_ref}' requires target_node_ref because "
                "scenario-level forwarding agents have no owning node"
            )
            return
        if not self._is_unresolved_var(node_ref) and resolved_node is not None:
            if service_ref not in self._node_service_names(resolved_node):
                self._err(
                    f"{owner_label} target_service_ref '{service_ref}' does not resolve to a service "
                    f"on node '{node_ref}'"
                )

    def _verify_forwarding_ship_target(
        self,
        *,
        node_name: str,
        local_service_names: set[str],
        target: object,
        owner_label: str,
    ) -> None:
        node_ref = getattr(target, "target_node_ref", "")
        service_ref = getattr(target, "target_service_ref", "")
        resolved_node_name = node_name
        resolved_node = self._s.nodes.get(node_name)
        if node_ref and not self._is_unresolved_var(node_ref):
            resolved_node = self._s.nodes.get(node_ref)
            if resolved_node is None:
                self._err(f"{owner_label} target_node_ref '{node_ref}' does not resolve to a defined node")
                return
            resolved_node_name = node_ref
        if service_ref and not self._is_unresolved_var(service_ref):
            if resolved_node is None:
                return
            target_service_names = (
                local_service_names if resolved_node_name == node_name else self._node_service_names(resolved_node)
            )
            if service_ref not in target_service_names:
                self._err(
                    f"{owner_label} target_service_ref '{service_ref}' does not resolve to a service "
                    f"on node '{resolved_node_name}'"
                )
