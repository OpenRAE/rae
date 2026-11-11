"""SemanticValidator _RelationshipsProxyMixin (split from _relationships.py).

Part of the SemanticValidator mixin composition; see __init__.py.
"""


class _RelationshipsProxyMixin:
    def _verify_relationship_proxy_upstreams(self) -> None:
        """Validate typed ``proxy_upstream`` blocks on relationship edges.

        ``route_ref`` must resolve to an application route (by ``route_id``) on
        the relationship's ``source`` proxy; ``upstream_node_ref`` /
        ``upstream_service_ref`` (when concrete) must resolve. AGREEMENT GUARD:
        when the referenced route ALSO carries an ``upstream_target``, the shared
        facts (target node, target service, and the TLS-termination boolean) MUST
        agree between ``route.upstream_target`` and the ``RelationshipProxyUpstream``
        so the same fact recorded at two scopes is never silently duplicated and
        contradictory (SCN-010 §5.7).
        """
        for name, rel in self._s.relationships.items():
            upstream = rel.proxy_upstream
            if upstream is None:
                continue
            label = f"Relationship '{name}'"
            with self._owner(("relationships", name)):
                target_node_name = self._check_proxy_upstream_node_ref(
                    upstream.upstream_node_ref,
                    label,
                    context="proxy_upstream",
                    field_name="upstream_node_ref",
                )
                self._check_proxy_upstream_service_ref(
                    upstream.upstream_service_ref,
                    upstream_node_ref=target_node_name or "",
                    relationship_target=rel.target,
                    label=label,
                    context="proxy_upstream",
                    field_name="upstream_service_ref",
                )
                route = self._check_proxy_upstream_route_ref(upstream.route_ref, rel.source, label)
                if route is not None:
                    self._check_proxy_upstream_agreement(upstream, route, label, relationship_target=rel.target)

    def _check_proxy_upstream_node_ref(
        self,
        node_ref: str,
        label: str,
        *,
        context: str,
        field_name: str,
    ) -> str | None:
        if not node_ref or self._is_unresolved_var(node_ref):
            return None
        if node_ref not in self._s.nodes:
            self._err(f"{label} {context} {field_name} '{node_ref}' does not resolve to a defined node")
            return None
        return node_ref

    def _check_proxy_upstream_service_ref(
        self,
        service_ref: str,
        *,
        upstream_node_ref: str,
        relationship_target: str,
        label: str,
        context: str,
        field_name: str,
    ) -> None:
        if not service_ref or self._is_unresolved_var(service_ref):
            return
        resolved = self._resolve_upstream_service_ref(
            service_ref,
            upstream_node_ref=upstream_node_ref,
            relationship_target=relationship_target,
        )
        if resolved is None:
            self._err(
                f"{label} {context} {field_name} '{service_ref}' cannot be resolved without a concrete upstream node"
            )
            return
        node_name, service_name = resolved
        node = self._proxy_upstream_node(
            node_name,
            service_ref,
            upstream_node_ref=upstream_node_ref,
            relationship_target=relationship_target,
            label=label,
            context=context,
            field_name=field_name,
        )
        if node is None:
            return
        if service_name not in self._node_service_names(node):
            self._err(
                f"{label} {context} {field_name} '{service_ref}' does not resolve to a service on node '{node_name}'"
            )

    def _proxy_upstream_node(
        self,
        node_name: str,
        service_ref: str,
        *,
        upstream_node_ref: str,
        relationship_target: str,
        label: str,
        context: str,
        field_name: str,
    ) -> object | None:
        expected_node_name = upstream_node_ref or self._node_name_from_relationship_target(relationship_target)
        if expected_node_name and node_name != expected_node_name:
            self._err(
                f"{label} {context} {field_name} '{service_ref}' must reference a service "
                f"on upstream node '{expected_node_name}'"
            )
            return None
        node = self._s.nodes.get(node_name)
        if node is None:
            self._err(f"{label} {context} upstream service node '{node_name}' does not resolve to a defined node")
            return None
        return node

    def _resolve_upstream_service_ref(
        self,
        service_ref: str,
        *,
        upstream_node_ref: str,
        relationship_target: str,
    ) -> tuple[str, str] | None:
        split = self._split_node_service_ref(service_ref)
        if split is not None:
            return split
        node_name = ""
        if upstream_node_ref and not self._is_unresolved_var(upstream_node_ref):
            node_name = upstream_node_ref
        else:
            target_node_name = self._node_name_from_relationship_target(relationship_target)
            if target_node_name is not None:
                node_name = target_node_name
        if not node_name:
            return None
        return node_name, service_ref

    def _node_name_from_relationship_target(self, target: object) -> str | None:
        if not isinstance(target, str) or self._is_unresolved_var(target):
            return None
        if target in self._s.nodes:
            return target
        return self._node_name_from_qualified_target(target)

    def _node_name_from_qualified_target(self, target: str) -> str | None:
        service_split = self._split_node_service_ref(target)
        if service_split is not None:
            node_name = service_split[0]
            return node_name if node_name in self._s.nodes else None
        runtime_reference = self._runtime_reference(target)
        if runtime_reference is not None:
            return runtime_reference.node_name
        return None

    def _check_proxy_upstream_route_ref(self, route_ref: str, source: str, label: str) -> object | None:
        if not route_ref or self._is_unresolved_var(route_ref):
            return None
        routes = self._source_application_routes(source)
        if routes is None:
            # The source does not resolve to a runtime application surface; the
            # generic relationship endpoint check already reports an unresolved
            # source, so the route_ref check is deferred rather than duplicated.
            return None
        route = routes.get(route_ref)
        if route is None:
            self._err(
                f"{label} proxy_upstream route_ref '{route_ref}' does not resolve to an "
                f"application route on source '{source}'"
            )
        return route

    def _source_application_routes(self, source: str) -> dict[str, object] | None:
        """Collect ``route_id``->route for every application surface on ``source``.

        ``source`` may be a qualified ``nodes.<node>.runtime.applications.<id>``
        ref or a bare node name; either way the proxy route lives on that node's
        application surface(s).
        """
        application = self._resolve_application_ref(source)
        if application is not None:
            return {route.route_id: route for route in application.routes}
        node = self._s.nodes.get(source)
        runtime = getattr(node, "runtime", None) if node is not None else None
        if runtime is None:
            return None
        routes: dict[str, object] = {}
        for application in getattr(runtime, "applications", []):
            for route in application.routes:
                routes[route.route_id] = route
        return routes

    def _check_proxy_upstream_agreement(
        self,
        upstream: object,
        route: object,
        label: str,
        *,
        relationship_target: str,
    ) -> None:
        target = getattr(route, "upstream_target", None)
        if target is None:
            return
        self._assert_shared_field_agreement(
            label,
            field_label="upstream node",
            relationship_value=getattr(upstream, "upstream_node_ref", ""),
            route_value=getattr(target, "target_node_ref", ""),
        )
        self._assert_shared_field_agreement(
            label,
            field_label="upstream service",
            relationship_value=getattr(upstream, "upstream_service_ref", ""),
            route_value=getattr(target, "target_service", ""),
            upstream_node_ref=getattr(upstream, "upstream_node_ref", "") or getattr(target, "target_node_ref", ""),
            relationship_target=relationship_target,
        )
        self._assert_shared_bool_agreement(
            label,
            field_label="TLS-termination",
            relationship_value=getattr(upstream, "client_tls_terminated", None),
            route_value=getattr(target, "tls_terminated_here", None),
        )

    def _assert_shared_field_agreement(
        self,
        label: str,
        *,
        field_label: str,
        relationship_value: str,
        route_value: str,
        upstream_node_ref: str = "",
        relationship_target: str = "",
    ) -> None:
        if not relationship_value or self._is_unresolved_var(relationship_value):
            return
        if not route_value or self._is_unresolved_var(route_value):
            return
        if self._shared_field_values_agree(
            field_label=field_label,
            relationship_value=relationship_value,
            route_value=route_value,
            upstream_node_ref=upstream_node_ref,
            relationship_target=relationship_target,
        ):
            return
        else:
            self._err(
                f"{label} proxy_upstream {field_label} '{relationship_value}' disagrees with the "
                f"route's upstream_target value '{route_value}'"
            )

    def _shared_field_values_agree(
        self,
        *,
        field_label: str,
        relationship_value: str,
        route_value: str,
        upstream_node_ref: str,
        relationship_target: str,
    ) -> bool:
        if field_label != "upstream service":
            return relationship_value == route_value
        relationship_ref = self._resolve_upstream_service_ref(
            relationship_value,
            upstream_node_ref=upstream_node_ref,
            relationship_target=relationship_target,
        )
        route_ref = self._resolve_upstream_service_ref(
            route_value,
            upstream_node_ref=upstream_node_ref,
            relationship_target=relationship_target,
        )
        if relationship_ref is None or route_ref is None:
            return relationship_value == route_value
        return relationship_ref == route_ref

    def _assert_shared_bool_agreement(
        self, label: str, *, field_label: str, relationship_value: object, route_value: object
    ) -> None:
        if not isinstance(relationship_value, bool) or not isinstance(route_value, bool):
            return
        if relationship_value != route_value:
            self._err(
                f"{label} proxy_upstream {field_label} '{relationship_value}' disagrees with the "
                f"route's upstream_target value '{route_value}'"
            )
