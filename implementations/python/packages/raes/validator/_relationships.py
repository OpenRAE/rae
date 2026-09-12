"""SemanticValidator _RelationshipsMixin (split from validator.py).

Part of the SemanticValidator mixin composition; see __init__.py.
"""

from ..runtime_security_monitoring import RuntimeSecurityMonitoringListenerRole


class _RelationshipsMixin:
    def _verify_relationship_database_access(self) -> None:
        """Validate typed ``database_access`` blocks on relationship edges.

        When a relationship carries ``database_access``, its ``source`` must
        resolve to a runtime application and its ``target`` must resolve to a
        database service (or logical database); the access ``role_ref`` must
        name a role in that service (ADR-029 §4).
        """
        for name, rel in self._s.relationships.items():
            access = rel.database_access
            if access is None:
                continue
            label = f"Relationship '{name}'"
            self._check_database_access_source(rel.source, label)
            dbsvc = self._check_database_access_target(rel.target, label)
            if dbsvc is not None:
                self._check_database_access_role(access.role_ref, dbsvc, label)

    def _check_database_access_source(self, source: str, label: str) -> None:
        if self._is_unresolved_var(source) or self._resolve_application_ref(source) is not None:
            return
        self._err(f"{label} has database_access but source '{source}' does not resolve to a runtime application")

    def _check_database_access_target(self, target: str, label: str) -> object | None:
        dbsvc = self._resolve_database_service_ref(target)
        if dbsvc is not None or self._is_unresolved_var(target):
            return dbsvc
        self._err(
            f"{label} has database_access but target '{target}' does not resolve to a database service or database"
        )
        return None

    def _check_database_access_role(self, role_ref: str, dbsvc: object, label: str) -> None:
        if not role_ref or self._is_unresolved_var(role_ref):
            return
        if role_ref not in {role.role_id for role in dbsvc.roles}:
            self._err(
                f"{label} database_access role_ref '{role_ref}' "
                f"is not a role in database service '{dbsvc.database_service_id}'"
            )

    # ------------------------------------------------------------------ #
    # Typed relationship subtypes (SCN-010 §5.7)
    # ------------------------------------------------------------------ #

    def _verify_relationship_forwarding_edges(self) -> None:
        """Validate typed ``forwarding_edge`` blocks on relationship edges.

        ``forwarder_ref`` must resolve to a ``RuntimeForwardingAgent`` (by
        ``forwarding_agent_id``) on some node. AGREEMENT GUARD: when that agent
        carries ``ship_targets``, the edge's ``target_listener_role`` and
        ``protocol`` — where both sides are concrete — must be consistent with
        at least one ship_target, so the inter-node trust edge and the
        agent-side shipping state cannot disagree (SCN-010 §5.7).
        """
        for name, rel in self._s.relationships.items():
            edge = rel.forwarding_edge
            if edge is None:
                continue
            label = f"Relationship '{name}'"
            ref = edge.forwarder_ref
            if not ref or self._is_unresolved_var(ref):
                continue
            agents = self._resolve_forwarding_agent_refs(ref)
            if not agents:
                self._err(
                    f"{label} forwarding_edge forwarder_ref '{ref}' does not resolve to a forwarding agent "
                    "on any node or in scenario forwarding_agents"
                )
                continue
            if len(agents) > 1:
                self._err(
                    f"{label} forwarding_edge forwarder_ref '{ref}' resolves to multiple forwarding agents; "
                    "forwarding_agent_id values must be unique across scenario forwarding_agents and node runtimes"
                )
                continue
            self._check_forwarding_edge_agreement(edge, agents[0], label)

    def _resolve_forwarding_agent_refs(self, ref: str) -> list[object]:
        """Resolve a ``forwarding_agent_id`` across node and scenario registries."""
        matches: list[object] = [agent for agent in self._s.forwarding_agents if agent.forwarding_agent_id == ref]
        for node in self._s.nodes.values():
            runtime = getattr(node, "runtime", None)
            if runtime is None:
                continue
            for agent in getattr(runtime, "forwarding_agents", []):
                if agent.forwarding_agent_id == ref:
                    matches.append(agent)
        return matches

    def _check_forwarding_edge_agreement(self, edge: object, agent: object, label: str) -> None:
        ship_targets = list(getattr(agent, "ship_targets", []))
        if not ship_targets:
            return
        agent_id = agent.forwarding_agent_id
        self._check_forwarding_edge_protocol_agreement(edge, ship_targets, agent_id, label)
        self._check_forwarding_edge_role_agreement(edge, ship_targets, agent_id, label)

    def _check_forwarding_edge_protocol_agreement(
        self, edge: object, ship_targets: list[object], agent_id: str, label: str
    ) -> None:
        # Private protocol identities are as binding as core enum members.
        # Only unresolved variables defer agreement to instantiation.
        edge_protocol = getattr(edge, "protocol", "")
        if not edge_protocol or self._is_unresolved_var(edge_protocol):
            return
        target_protocols = [
            getattr(target.protocol, "value", target.protocol)
            for target in ship_targets
            if not self._is_unresolved_var(target.protocol)
        ]
        if not target_protocols:
            return
        if edge_protocol not in target_protocols:
            self._err(
                f"{label} forwarding_edge protocol does not match any ship_target protocol "
                f"on forwarding agent '{agent_id}'"
            )

    def _check_forwarding_edge_role_agreement(
        self, edge: object, ship_targets: list[object], agent_id: str, label: str
    ) -> None:
        # An ``agent_event_ingestion`` listener role requires a ship_target with
        # an ingestion endpoint; an ``agent_enrollment`` role requires one with
        # an enrollment endpoint. Other roles impose no ship_target shape.
        role = getattr(edge, "target_listener_role", None)
        if not isinstance(role, RuntimeSecurityMonitoringListenerRole):
            return
        if role is RuntimeSecurityMonitoringListenerRole.AGENT_EVENT_INGESTION:
            if not any(t.has_ingestion_endpoint() for t in ship_targets):
                self._err(
                    f"{label} forwarding_edge target_listener_role 'agent_event_ingestion' has no agreeing "
                    f"ship_target carrying an ingestion endpoint on forwarding agent '{agent_id}'"
                )
        elif role is RuntimeSecurityMonitoringListenerRole.AGENT_ENROLLMENT:
            if not any(t.has_enrollment_endpoint() for t in ship_targets):
                self._err(
                    f"{label} forwarding_edge target_listener_role 'agent_enrollment' has no agreeing "
                    f"ship_target carrying an enrollment endpoint on forwarding agent '{agent_id}'"
                )

    def _verify_relationship_service_integrations(self) -> None:
        """Validate typed ``service_integration`` blocks on relationship edges.

        ``consumer_ref``/``engine_ref`` (when concrete) must resolve to platform
        applications by ``platform_application_id``; a concrete
        ``auth_principal_ref`` must resolve to the engine application's
        referenced ``app_authorization`` store when ``authorization_ref`` is set
        (the integration authenticates into the engine's internal RBAC store).
        """
        for name, rel in self._s.relationships.items():
            integration = rel.service_integration
            if integration is None:
                continue
            label = f"Relationship '{name}'"
            self._check_service_integration_endpoint(integration.consumer_ref, "consumer_ref", label)
            engine = self._check_service_integration_endpoint(integration.engine_ref, "engine_ref", label)
            self._check_service_integration_auth_principal(integration.auth_principal_ref, engine, label)

    def _check_service_integration_endpoint(self, ref: str, field_name: str, label: str) -> object | None:
        if not ref or self._is_unresolved_var(ref):
            return None
        resolved = self._resolve_platform_application_ref(ref)
        if resolved is None:
            self._err(
                f"{label} service_integration {field_name} '{ref}' does not resolve to a "
                f"platform application on any node"
            )
            return None
        return resolved[1]

    def _resolve_platform_application_ref(self, ref: str) -> tuple[str, object] | None:
        """Resolve a ``platform_application_id`` to (node_name, application)."""
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None:
                continue
            for application in getattr(runtime, "platform_applications", []):
                if application.platform_application_id == ref:
                    return node_name, application
        return None

    def _check_service_integration_auth_principal(self, ref: str, engine: object | None, label: str) -> None:
        if not ref or self._is_unresolved_var(ref) or engine is None:
            return
        node_name = self._node_name_of_platform_application(engine)
        if node_name is None:
            return
        authorizations = self._engine_authorizations(node_name, engine)
        if authorizations is None:
            # The runtime platform application validator reports the bad
            # authorization_ref; avoid emitting a misleading principal-scope
            # error from this relationship pass as well.
            return
        principal_ids = {
            principal.principal_id for authorization in authorizations for principal in authorization.principals
        }
        if ref not in principal_ids:
            self._err(
                f"{label} service_integration auth_principal_ref '{ref}' does not resolve to "
                f"{self._auth_principal_scope(engine)} on the engine application's node '{node_name}'"
            )

    def _engine_authorizations(self, node_name: str, engine: object) -> list[object] | None:
        """App authorizations on the engine's node, filtered by ``authorization_ref``.

        Returns None when a concrete ``authorization_ref`` matches no authorization
        (the platform-application validator reports that; this pass suppresses it).
        """
        node = self._s.nodes.get(node_name)
        runtime = getattr(node, "runtime", None) if node is not None else None
        authorizations = list(getattr(runtime, "app_authorizations", []))
        authorization_ref = getattr(engine, "authorization_ref", "")
        if not authorization_ref or self._is_unresolved_var(authorization_ref):
            return authorizations
        filtered = [a for a in authorizations if getattr(a, "app_authorization_id", "") == authorization_ref]
        return filtered or None

    def _auth_principal_scope(self, engine: object) -> str:
        authorization_ref = getattr(engine, "authorization_ref", "")
        if authorization_ref and not self._is_unresolved_var(authorization_ref):
            return f"authorization '{authorization_ref}'"
        return "an app_authorization principal"

    def _node_name_of_platform_application(self, application: object) -> str | None:
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None:
                continue
            if application in getattr(runtime, "platform_applications", []):
                return node_name
        return None
