"""Runtime network detection-engine SDL surface tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from raes import parse_sdl
from raes._errors import SDLValidationError
from raes._module_symbols import symbol_index
from raes.nodes import (
    Node,
    RuntimeConfiguration,
    RuntimeNetworkDetectionAppProtocol,
    RuntimeNetworkDetectionControlChannelKind,
    RuntimeNetworkDetectionEngine,
    RuntimeNetworkDetectionEngineImplementation,
    RuntimeNetworkDetectionEngineKind,
    RuntimeNetworkDetectionOutputFormat,
    RuntimeNetworkDetectionRuleFormat,
    RuntimeNetworkDetectionRuleSourceKind,
)
from raes.scenario import ModuleDescriptor, Scenario
from raes.validator import SemanticValidator


def _validate(scenario: Scenario) -> list[str]:
    validator = SemanticValidator(scenario)
    try:
        validator.validate()
    except SDLValidationError as exc:
        return exc.errors
    else:
        return []


def _suricata_sensor() -> dict:
    return {
        "network_sensor_id": "suricata-sensor",
        "implementation": "suricata",
        "sensor_kind": "ids",
        "monitoring_posture": "passive",
        "capture_mode": "pcap",
        "capture_interfaces": ["any"],
        "monitored_network_refs": ["dmz-net", "internal-net"],
    }


def _suricata_engine(**overrides) -> dict:
    engine = {
        "network_detection_engine_id": "suricata-engine",
        "implementation": "suricata",
        "engine_kind": "ids",
        "version": "7.0.15",
        "process_ref": "suricata",
        "sensor_ref": "suricata-sensor",
        "app_layer_protocols": ["http", "tls", "dns", "ssh", "smtp", "ftp", "smb"],
        "configuration_file_refs": ["/etc/suricata/suricata.yaml"],
        "log_file_refs": ["/var/log/suricata/fast.log"],
        "evidence_refs": ["/var/log/suricata/eve.json"],
        "rule_sources": [
            {
                "source_id": "suricata-update",
                "kind": "managed",
                "format": "suricata_rule",
                "name": "suricata.rules",
                "rule_count": 65814,
                "file_refs": ["/var/lib/suricata/rules/suricata.rules"],
                "loaded": True,
            },
            {
                "source_id": "local-rules",
                "kind": "local",
                "format": "suricata_rule",
                "name": "local.rules",
                "rule_count": 46,
                "file_refs": ["/etc/suricata/rules/local.rules"],
                "loaded": True,
            },
            {
                "source_id": "misp-iocs",
                "kind": "ioc",
                "format": "suricata_rule",
                "name": "misp/misp-iocs.rules",
                "rule_count": 6,
                "file_refs": ["/etc/suricata/rules/misp/misp-iocs.rules"],
                "generated_by": "nodes.suricata.runtime.forwarding_agents.misp-suricata-sync",
                "loaded": True,
            },
        ],
        "network_sets": [
            {
                "set_id": "home-net",
                "kind": "home_net",
                "name": "HOME_NET",
                "network_refs": ["dmz-net", "internal-net"],
            },
            {
                "set_id": "dns-servers",
                "kind": "service_group",
                "name": "DNS_SERVERS",
                "selector_values": ["10.0.0.53"],
            },
        ],
        "output_streams": [
            {
                "stream_id": "eve-json",
                "format": "eve_json",
                "path": "/var/log/suricata/eve.json",
                "event_types": ["alert", "http", "dns", "tls", "ssh", "flow", "netflow", "stats"],
                "enabled": True,
            },
            {
                "stream_id": "fast-log",
                "format": "fast_log",
                "path": "/var/log/suricata/fast.log",
                "event_types": ["alert"],
                "enabled": True,
            },
        ],
        "control_channels": [
            {
                "channel_id": "command-socket",
                "kind": "unix_socket",
                "path": "/var/run/suricata-command.socket",
                "capabilities": ["rule_reload"],
            }
        ],
    }
    engine.update(overrides)
    return engine


def _detection_node(engine: dict | None = None) -> dict:
    return {
        "type": "compute",
        "resources": {"ram": "2 gib", "cpu": 2},
        "runtime": {
            "processes": [{"name": "suricata", "pid": 1, "command": ["suricata", "--pcap"]}],
            "filesystem_inventory": [
                {"path": "/etc/suricata/suricata.yaml", "entry_type": "file"},
                {"path": "/var/log/suricata/fast.log", "entry_type": "file"},
                {"path": "/var/log/suricata/eve.json", "entry_type": "file"},
                {"path": "/var/lib/suricata/rules/suricata.rules", "entry_type": "file"},
                {"path": "/etc/suricata/rules/local.rules", "entry_type": "file"},
                {"path": "/etc/suricata/rules/misp/misp-iocs.rules", "entry_type": "file"},
                {"path": "/var/run/suricata-command.socket", "entry_type": "socket"},
            ],
            "network_sensors": [_suricata_sensor()],
            "network_detection_engines": [engine or _suricata_engine()],
            "forwarding_agents": [{"forwarding_agent_id": "misp-suricata-sync", "agent_kind": "content_sync"}],
        },
    }


def _network_nodes() -> dict:
    return {
        "dmz-net": {"type": "switch"},
        "internal-net": {"type": "switch"},
    }


def _infrastructure() -> dict:
    return {
        "dmz-net": {"count": 1},
        "internal-net": {"count": 1},
        "suricata": {"count": 1, "links": ["dmz-net", "internal-net"]},
    }


def test_network_detection_surface_is_node_scoped_not_top_level() -> None:
    assert "network_detection_engines" not in Scenario.model_fields
    assert "network_detection_engines" in RuntimeConfiguration.model_fields


def test_vm_runtime_network_detection_engine_inventory() -> None:
    node = Node(type="compute", runtime={"network_detection_engines": [_suricata_engine()]})

    engine = node.runtime.network_detection_engines[0]
    assert engine.network_detection_engine_id == "suricata-engine"
    assert engine.implementation == RuntimeNetworkDetectionEngineImplementation.SURICATA
    assert engine.engine_kind == RuntimeNetworkDetectionEngineKind.IDS
    assert engine.app_layer_protocols[0] == RuntimeNetworkDetectionAppProtocol.HTTP
    assert engine.rule_sources[0].kind == RuntimeNetworkDetectionRuleSourceKind.MANAGED
    assert engine.rule_sources[0].format == RuntimeNetworkDetectionRuleFormat.SURICATA_RULE
    assert engine.output_streams[0].format == RuntimeNetworkDetectionOutputFormat.EVE_JSON
    assert engine.control_channels[0].kind == RuntimeNetworkDetectionControlChannelKind.UNIX_SOCKET


def test_parser_accepts_canonical_runtime_network_detection_engines() -> None:
    scenario = parse_sdl(
        """
        name: detection-engine-parser
        nodes:
          dmz-net: {type: switch}
          suricata:
            type: compute
            resources: {ram: 2 gib, cpu: 2}
            runtime:
              network_sensors:
                - network_sensor_id: suricata-sensor
                  implementation: SURICATA
                  sensor_kind: ids
                  monitoring_posture: passive
                  capture_mode: pcap
                  monitored_network_refs: [dmz-net]
              network_detection_engines:
                - network_detection_engine_id: suricata-engine
                  implementation: SURICATA
                  engine_kind: ids
                  sensor_ref: suricata-sensor
                  app_layer_protocols: [http, tls, dns]
                  rule_sources:
                    - source_id: local-rules
                      kind: local
                      format: suricata-rule
                      rule_count: "46"
                  network_sets:
                    - set_id: home-net
                      kind: home-net
                      name: HOME_NET
                      network_refs: [dmz-net]
                  output_streams:
                    - stream_id: eve-json
                      format: eve-json
                      event_types: [alert, dns]
                      enabled: true
                  control_channels:
                    - channel_id: command-socket
                      kind: unix-socket
                      path: /var/run/suricata-command.socket
                      capabilities: rule-reload
        infrastructure:
          dmz-net: 1
          suricata: {count: 1, links: [dmz-net]}
        """
    )

    engine = scenario.nodes["suricata"].runtime.network_detection_engines[0]
    assert engine.network_detection_engine_id == "suricata-engine"
    assert engine.rule_sources[0].rule_count == 46
    assert engine.control_channels[0].capabilities == ["rule_reload"]


def test_network_detection_engine_rejects_duplicate_stable_ids() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime network detection stable id 'eve-json'"):
        RuntimeNetworkDetectionEngine(
            **_suricata_engine(
                output_streams=[
                    {"stream_id": "eve-json", "format": "eve_json"},
                    {"stream_id": "eve-json", "format": "fast_log"},
                ]
            )
        )


class TestRuntimeNetworkDetectionSemanticValidation:
    def test_suricata_detection_engine_inventory_is_valid(self) -> None:
        scenario = Scenario(
            name="network-detection",
            nodes={**_network_nodes(), "suricata": _detection_node()},
            infrastructure=_infrastructure(),
        )

        assert _validate(scenario) == []

    def test_sensor_ref_must_resolve_to_same_node_network_sensor(self) -> None:
        engine = _suricata_engine(sensor_ref="missing-sensor")
        errors = _validate(
            Scenario(
                name="network-detection",
                nodes={**_network_nodes(), "suricata": _detection_node(engine)},
                infrastructure=_infrastructure(),
            )
        )

        assert any("sensor_ref 'missing-sensor'" in error for error in errors)

    def test_rule_source_file_refs_resolve_to_runtime_filesystem_inventory_when_present(self) -> None:
        engine = _suricata_engine(
            rule_sources=[{"source_id": "local-rules", "kind": "local", "file_refs": ["/missing.rules"]}]
        )
        errors = _validate(
            Scenario(
                name="network-detection",
                nodes={**_network_nodes(), "suricata": _detection_node(engine)},
                infrastructure=_infrastructure(),
            )
        )

        assert any(
            "rule_source 'local-rules'" in error and "file_refs ref '/missing.rules'" in error for error in errors
        )

    def test_network_set_refs_must_reference_switch_backed_infrastructure(self) -> None:
        engine = _suricata_engine(network_sets=[{"set_id": "home-net", "network_refs": ["suricata"]}])
        errors = _validate(
            Scenario(
                name="network-detection",
                nodes={**_network_nodes(), "suricata": _detection_node(engine)},
                infrastructure=_infrastructure(),
            )
        )

        assert any("network_ref 'suricata' must reference a switch/network entry" in error for error in errors)

    def test_relationship_target_to_engine_and_child_records_is_valid(self) -> None:
        scenario = Scenario(
            name="network-detection",
            nodes={**_network_nodes(), "suricata": _detection_node()},
            infrastructure=_infrastructure(),
            relationships={
                "client-detected-by-suricata": {
                    "type": "depends_on",
                    "source": "nodes.suricata.runtime.network_detection_engines.suricata-engine",
                    "target": "nodes.suricata.runtime.network_detection_engines.suricata-engine.rule_sources.local-rules",
                },
                "suricata-emits-eve": {
                    "type": "depends_on",
                    "source": "nodes.suricata.runtime.network_detection_engines.suricata-engine",
                    "target": "nodes.suricata.runtime.network_detection_engines.suricata-engine.output_streams.eve-json",
                },
            },
        )

        assert _validate(scenario) == []


def test_module_symbol_index_rewrites_runtime_network_detection_refs() -> None:
    scenario = Scenario(
        name="shared",
        module=ModuleDescriptor(id="acme/shared", version="1.0.0", exports={"nodes": ["suricata"]}),
        nodes={**_network_nodes(), "suricata": _detection_node()},
        infrastructure=_infrastructure(),
    )

    named = symbol_index(
        scenario,
        namespace="shared",
        descriptor=scenario.module,
    )["named"]

    assert named["nodes.suricata.runtime.network_detection_engines.suricata-engine"] == (
        "nodes.shared.suricata.runtime.network_detection_engines.suricata-engine"
    )
    assert named["nodes.suricata.runtime.network_detection_engines.suricata-engine.rule_sources.local-rules"] == (
        "nodes.shared.suricata.runtime.network_detection_engines.suricata-engine.rule_sources.local-rules"
    )
    assert named["nodes.suricata.runtime.network_detection_engines.suricata-engine.output_streams.eve-json"] == (
        "nodes.shared.suricata.runtime.network_detection_engines.suricata-engine.output_streams.eve-json"
    )
