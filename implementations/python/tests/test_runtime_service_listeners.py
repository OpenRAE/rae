"""Generic runtime service listener SDL surface tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from raes import parse_sdl
from raes._errors import SDLValidationError
from raes._module_symbols import symbol_index
from raes.nodes import (
    Node,
    RuntimeConfiguration,
    RuntimeListenerAddressFamily,
    RuntimeListenerProtocol,
    RuntimeListenerProvenance,
    RuntimeListenerScope,
    RuntimeServiceListener,
)
from raes.scenario import ModuleDescriptor, Scenario
from raes.validator import SemanticValidator


def _validate(scenario: Scenario) -> list[str]:
    validator = SemanticValidator(scenario)
    try:
        validator.validate()
        return []
    except SDLValidationError as exc:
        return exc.errors


def _listener(**overrides) -> dict:
    listener = {
        "service_listener_id": "nginx-http-ipv4",
        "service": "http",
        "address": "0.0.0.0",  # noqa: S104 - wildcard bind is the behavior under test.
        "port": 80,
        "protocol": "tcp",
        "address_family": "ipv4",
        "scope": "wildcard",
        "process_ref": "nginx",
        "process_name": "nginx",
        "published_port_refs": [
            {
                "container_port": 80,
                "protocol": "tcp",
                "host_ip": "0.0.0.0",  # noqa: S104 - wildcard host bind is test data.
                "host_port": 8080,
            }
        ],
        "readiness": {"probe": "GET /", "criteria": "HTTP 200", "evidence_refs": ["curl /"]},
        "provenance": "osquery",
        "evidence_refs": ["osquery:listening_ports"],
    }
    listener.update(overrides)
    return listener


def _node(listener: dict | None = None) -> dict:
    return {
        "type": "compute",
        "resources": {"ram": "1 gib", "cpu": 1},
        "services": [
            {"port": 80, "protocol": "tcp", "name": "http"},
            {"port": 443, "protocol": "tcp", "name": "https"},
        ],
        "runtime": {
            "processes": [{"name": "nginx", "pid": 42}],
            "network": {
                "published_ports": [
                    {
                        "container_port": 80,
                        "protocol": "tcp",
                        "host_ip": "0.0.0.0",  # noqa: S104 - wildcard host bind is test data.
                        "host_port": 8080,
                    }
                ]
            },
            "service_listeners": [listener or _listener()],
        },
    }


def test_runtime_service_listeners_are_node_scoped_not_top_level() -> None:
    assert "service_listeners" not in Scenario.model_fields
    assert "service_listeners" in RuntimeConfiguration.model_fields


def test_vm_runtime_service_listener_surface() -> None:
    node = Node(type="compute", runtime={"service_listeners": [_listener()]})

    listener = node.runtime.service_listeners[0]
    assert listener.service_listener_id == "nginx-http-ipv4"
    assert listener.protocol == RuntimeListenerProtocol.TCP
    assert listener.address_family == RuntimeListenerAddressFamily.IPV4
    assert listener.scope == RuntimeListenerScope.WILDCARD
    assert listener.provenance == RuntimeListenerProvenance.OSQUERY
    assert listener.readiness.criteria == "HTTP 200"


def test_parser_accepts_canonical_runtime_service_listeners() -> None:
    scenario = parse_sdl(
        """
        name: listener-parser
        nodes:
          misp:
            type: compute
            resources: {ram: 1 gib, cpu: 1}
            services:
              - {port: 80, protocol: tcp, name: http}
            runtime:
              processes:
                - {name: nginx, pid: 42}
              service_listeners:
                - service_listener_id: nginx-http-ipv4
                  service: http
                  address: 0.0.0.0
                  port: 80
                  protocol: TCP
                  address_family: ipv4
                  scope: wildcard
                  process_ref: nginx
                  readiness:
                    probe: GET /
                    criteria: HTTP 200
                  provenance: osquery
        """
    )

    listener = scenario.nodes["misp"].runtime.service_listeners[0]
    assert listener.service_listener_id == "nginx-http-ipv4"
    assert listener.protocol == RuntimeListenerProtocol.TCP
    assert listener.readiness.probe == "GET /"


def test_runtime_service_listener_rejects_contradictory_scope() -> None:
    with pytest.raises(ValidationError, match="scope 'network_facing' contradicts loopback address"):
        RuntimeServiceListener(
            service_listener_id="supervisord",
            address="127.0.0.1",
            port=9001,
            protocol="tcp",
            address_family="ipv4",
            scope="network_facing",
        )


def test_runtime_service_listener_rejects_loopback_scope_for_non_loopback_address() -> None:
    with pytest.raises(ValidationError, match="scope 'loopback_only' contradicts non-loopback address"):
        RuntimeServiceListener(
            service_listener_id="node-local-api",
            address="192.168.1.1",
            port=8080,
            protocol="tcp",
            address_family="ipv4",
            scope="loopback_only",
        )


def test_runtime_service_listener_rejects_non_wildcard_scope_for_wildcard_address() -> None:
    with pytest.raises(ValidationError, match="scope 'loopback_only' contradicts wildcard address"):
        RuntimeServiceListener(
            service_listener_id="wildcard-api",
            address="0.0.0.0",  # noqa: S104 - wildcard bind is the behavior under test.
            port=8080,
            protocol="tcp",
            address_family="ipv4",
            scope="loopback_only",
        )


def test_runtime_service_listener_rejects_address_family_mismatch() -> None:
    with pytest.raises(ValidationError, match="address_family 'ipv4' contradicts address '::'"):
        RuntimeServiceListener(
            service_listener_id="ipv6-api",
            address="::",
            port=8080,
            protocol="tcp",
            address_family="ipv4",
            scope="wildcard",
        )


def test_runtime_service_listener_rejects_network_local_socket_scope() -> None:
    with pytest.raises(ValidationError, match="scope 'local_socket' requires Unix socket listener"):
        RuntimeServiceListener(
            service_listener_id="supervisord",
            address="127.0.0.1",
            port=9001,
            protocol="tcp",
            address_family="ipv4",
            scope="local_socket",
        )


def test_partial_unix_listener_permits_missing_path_but_rejects_network_fields() -> None:
    partial = RuntimeServiceListener(service_listener_id="unix", protocol="unix", address_family="unix")
    assert partial.model_dump(mode="json", exclude_unset=True) == {
        "service_listener_id": "unix",
        "protocol": "unix",
        "address_family": "unix",
    }

    with pytest.raises(ValidationError, match="Unix listeners must not set port"):
        RuntimeServiceListener(
            service_listener_id="unix",
            protocol="unix",
            address_family="unix",
            socket_path="/run/app.sock",
            port=1,
        )

    with pytest.raises(ValidationError, match="Unix listeners must not set bind_interface"):
        RuntimeServiceListener(service_listener_id="unix", protocol="unix", bind_interface="lo")


def test_listener_rejects_mixed_supplied_unix_and_network_shapes() -> None:
    with pytest.raises(ValidationError, match="must not combine Unix socket and network endpoint fields"):
        RuntimeServiceListener(
            service_listener_id="ambiguous",
            protocol="unknown",
            socket_path="/run/app.sock",
            port=80,
        )


def test_runtime_service_listener_semantics_resolve_refs() -> None:
    scenario = Scenario(name="listeners", nodes={"misp": _node()})

    assert _validate(scenario) == []


def test_runtime_service_listener_service_mismatch_fails_closed() -> None:
    scenario = Scenario(name="listeners", nodes={"misp": _node(_listener(port=81, published_port_refs=[]))})

    assert _validate(scenario) == [
        "Node 'misp' runtime service listener 'nginx-http-ipv4' port/protocol must match service 'http'"
    ]


def test_runtime_service_listener_process_ref_must_resolve_when_set() -> None:
    scenario = Scenario(name="listeners", nodes={"misp": _node(_listener(process_ref="apache2"))})

    assert _validate(scenario) == [
        "Node 'misp' runtime service listener 'nginx-http-ipv4' process_ref 'apache2' "
        "does not resolve to a runtime process name or pid"
    ]


def test_runtime_service_listener_published_port_ref_must_resolve() -> None:
    bad_ref = {"container_port": 80, "protocol": "tcp", "host_ip": "127.0.0.1", "host_port": 8080}
    scenario = Scenario(
        name="listeners",
        nodes={"misp": _node(_listener(published_port_refs=[bad_ref]))},
    )

    assert _validate(scenario) == [
        "Node 'misp' runtime service listener 'nginx-http-ipv4' published_port_refs entry "
        "does not resolve to runtime.network.published_ports"
    ]


def test_runtime_service_listener_published_port_match_defers_unresolved_listener_values() -> None:
    scenario = Scenario(
        name="listeners",
        variables={
            "http_port": {"type": "integer", "default": 80},
            "transport": {"type": "string", "default": "tcp"},
        },
        nodes={"misp": _node(_listener(port="${http_port}", protocol="${transport}"))},
    )

    assert _validate(scenario) == []


def test_runtime_service_listeners_encode_misp_listener_facts() -> None:
    scenario = parse_sdl(
        """
        name: misp-listeners
        nodes:
          misp:
            type: compute
            resources: {ram: 2 gib, cpu: 2}
            services:
              - {port: 80, protocol: tcp, name: http}
              - {port: 443, protocol: tcp, name: https}
            runtime:
              processes:
                - {name: nginx, pid: 11}
                - {name: supervisord, pid: 1}
              network:
                published_ports:
                  - {container_port: 80, protocol: tcp, host_ip: 0.0.0.0, host_port: 80}
                  - {container_port: 443, protocol: tcp, host_ip: 0.0.0.0, host_port: 443}
              service_listeners:
                - service_listener_id: nginx-http-ipv4
                  service: http
                  address: 0.0.0.0
                  port: 80
                  protocol: tcp
                  address_family: ipv4
                  scope: wildcard
                  process_ref: nginx
                  process_name: nginx
                  published_port_refs:
                    - {container_port: 80, protocol: tcp, host_ip: 0.0.0.0, host_port: 80}
                - service_listener_id: nginx-http-ipv6
                  service: http
                  address: "::"
                  port: 80
                  protocol: tcp
                  address_family: ipv6
                  scope: wildcard
                  process_ref: nginx
                - service_listener_id: nginx-https-ipv4
                  service: https
                  address: 0.0.0.0
                  port: 443
                  protocol: tcp
                  address_family: ipv4
                  scope: wildcard
                  process_ref: nginx
                - service_listener_id: nginx-https-ipv6
                  service: https
                  address: "::"
                  port: 443
                  protocol: tcp
                  address_family: ipv6
                  scope: wildcard
                  process_ref: nginx
                - service_listener_id: supervisord-loopback
                  address: 127.0.0.1
                  port: 9001
                  protocol: tcp
                  address_family: ipv4
                  scope: loopback-only
                  process_ref: supervisord
                - service_listener_id: local-runtime-loopback
                  address: 127.0.0.1
                  port: 50000
                  protocol: tcp
                  address_family: ipv4
                  scope: loopback-only
                  process_name: runtime-local
                - service_listener_id: docker-dns
                  address: 127.0.0.11
                  port: 53
                  protocol: udp
                  address_family: ipv4
                  scope: loopback-only
                  process_name: docker-embedded-dns
        """
    )

    assert _validate(scenario) == []
    listeners = scenario.nodes["misp"].runtime.service_listeners
    assert [listener.service_listener_id for listener in listeners] == [
        "nginx-http-ipv4",
        "nginx-http-ipv6",
        "nginx-https-ipv4",
        "nginx-https-ipv6",
        "supervisord-loopback",
        "local-runtime-loopback",
        "docker-dns",
    ]


def test_runtime_service_listener_refs_survive_module_namespacing() -> None:
    scenario = Scenario(name="module", nodes={"misp": _node()})
    index = symbol_index(
        scenario,
        namespace="shared",
        descriptor=ModuleDescriptor(id="acme/shared", version="1.0.0", exports={"nodes": ["misp"]}),
    )

    assert index["named"]["nodes.misp.runtime.service_listeners.nginx-http-ipv4"] == (
        "nodes.shared.misp.runtime.service_listeners.nginx-http-ipv4"
    )
