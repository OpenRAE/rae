"""Semantic validation for node-scoped runtime service listeners."""

from __future__ import annotations


class _RuntimeListenersMixin:
    def _verify_runtime_service_listeners(self) -> None:
        """Validate service-listener descriptions against same-node runtime facts."""
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None or not runtime.service_listeners:
                continue
            services_by_name = self._node_services_by_name(node)
            process_refs = self._node_runtime_process_refs(node)
            published_ports = self._node_published_port_keys(node)
            for listener_index, listener in enumerate(runtime.service_listeners):
                label = f"Node '{node_name}' runtime service listener '{listener.service_listener_id}'"
                field_prefix = f"nodes.{node_name}.runtime.service_listeners[{listener_index}]"
                self._verify_listener_transport_shape(label, field_prefix, listener)
                service = self._resolve_owned_service_ref(
                    node_name,
                    getattr(listener, "service", ""),
                    services_by_name,
                    owner_label=label,
                )
                if service is not None:
                    self._verify_listener_service_binding(label, field_prefix, listener, service)
                self._verify_listener_process_ref(label, listener, process_refs)
                self._verify_listener_published_port_refs(label, field_prefix, listener, published_ports)

    def _verify_listener_transport_shape(self, label: str, field_prefix: str, listener: object) -> None:
        """Resolve legacy TCP-default ambiguity with scenario provenance."""
        if not self._listener_field_supplied(listener, field_prefix, "protocol"):
            return
        protocol = self._known_listener_protocol(getattr(listener, "protocol", ""))
        if protocol != "tcp":
            return
        socket_path = getattr(listener, "socket_path", "")
        family = self._enum_or_raw(getattr(listener, "address_family", ""))
        scope = self._enum_or_raw(getattr(listener, "scope", ""))
        if socket_path or family == "unix" or scope == "local_socket":
            self._err(f"{label} supplied TCP protocol contradicts Unix listener facts")

    def _verify_listener_service_binding(
        self,
        label: str,
        field_prefix: str,
        listener: object,
        service: object,
    ) -> None:
        listener_port = getattr(listener, "port", None)
        listener_protocol = self._known_listener_protocol(getattr(listener, "protocol", ""))
        service_port = getattr(service, "port", None)
        service_protocol = getattr(service, "protocol", "")
        if any(self._is_unresolved_var(value) for value in (service_port, service_protocol)):
            return
        port_mismatch = (
            self._listener_field_supplied(listener, field_prefix, "port")
            and listener_port is not None
            and not self._is_unresolved_var(listener_port)
            and listener_port != service_port
        )
        protocol_mismatch = (
            self._listener_field_supplied(listener, field_prefix, "protocol")
            and listener_protocol is not None
            and listener_protocol != str(service_protocol).lower()
        )
        if port_mismatch or protocol_mismatch:
            self._err(f"{label} port/protocol must match service '{service.name}'")

    @staticmethod
    def _enum_or_raw(value: object) -> object:
        return value.value if hasattr(value, "value") else value

    def _known_listener_protocol(self, value: object) -> str | None:
        raw = self._enum_or_raw(value)
        if not raw or self._is_unresolved_var(raw):
            return None
        normalized = str(raw).lower()
        if normalized in {"unknown", "other"}:
            return None
        return normalized

    def _listener_field_supplied(self, listener: object, field_prefix: str, field_name: str) -> bool:
        if hasattr(self._s, "instantiation_provenance"):
            return f"{field_prefix}.{field_name}" in self._s.explicitness
        return field_name in getattr(listener, "model_fields_set", set())

    def _verify_listener_process_ref(self, label: str, listener: object, process_refs: set[str]) -> None:
        ref = getattr(listener, "process_ref", "")
        if not ref or self._is_unresolved_var(ref):
            return
        if ref not in process_refs:
            self._err(f"{label} process_ref '{ref}' does not resolve to a runtime process name or pid")

    def _verify_listener_published_port_refs(
        self,
        label: str,
        field_prefix: str,
        listener: object,
        published_ports: set[tuple[str, int | str | None, int | str, str]],
    ) -> None:
        listener_port = getattr(listener, "port", None)
        listener_protocol = self._known_listener_protocol(getattr(listener, "protocol", ""))
        port_supplied = self._listener_field_supplied(listener, field_prefix, "port")
        protocol_supplied = self._listener_field_supplied(listener, field_prefix, "protocol")
        for ref in getattr(listener, "published_port_refs", []):
            values = (ref.host_ip, ref.host_port, ref.container_port, ref.protocol)
            if any(self._is_unresolved_var(value) for value in values):
                continue
            if self._listener_published_port_mismatch(
                ref_container_port=ref.container_port,
                ref_protocol=ref.protocol,
                listener_port=listener_port,
                listener_protocol=listener_protocol,
                port_supplied=port_supplied,
                protocol_supplied=protocol_supplied,
            ):
                self._err(f"{label} published_port_refs entry must match listener port/protocol")
                continue
            if values not in published_ports:
                self._err(f"{label} published_port_refs entry does not resolve to runtime.network.published_ports")

    def _listener_published_port_mismatch(
        self,
        *,
        ref_container_port: object,
        ref_protocol: str,
        listener_port: object,
        listener_protocol: str | None,
        port_supplied: bool,
        protocol_supplied: bool,
    ) -> bool:
        port_mismatch = (
            port_supplied
            and listener_port is not None
            and not self._is_unresolved_var(listener_port)
            and ref_container_port != listener_port
        )
        protocol_mismatch = protocol_supplied and listener_protocol is not None and ref_protocol != listener_protocol
        return port_mismatch or protocol_mismatch

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
