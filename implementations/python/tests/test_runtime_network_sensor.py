"""Runtime network-sensor SDL surface tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from raes import parse_sdl
from raes._errors import SDLValidationError
from raes._module_symbols import symbol_index
from raes.nodes import (
    Node,
    RuntimeConfiguration,
    RuntimeNetworkSensor,
    RuntimeNetworkSensorCaptureMode,
    RuntimeNetworkSensorImplementation,
    RuntimeNetworkSensorKind,
    RuntimeNetworkSensorMonitoringPosture,
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


def _suricata_sensor(**overrides) -> dict:
    sensor = {
        "network_sensor_id": "suricata",
        "implementation": "suricata",
        "sensor_kind": "ids",
        "monitoring_posture": "passive",
        "capture_mode": "pcap",
        "capture_interfaces": ["any"],
        "monitored_network_refs": ["dmz-net", "internal-net", "security-net"],
        "process_ref": "suricata",
        "version": "7.0.15",
        "configuration_file_refs": ["/etc/suricata/suricata.yaml"],
        "log_file_refs": ["/var/log/suricata/fast.log"],
        "evidence_refs": ["/var/log/suricata/eve.json"],
    }
    sensor.update(overrides)
    return sensor


def _sensor_node(sensor: dict | None = None) -> dict:
    return {
        "type": "compute",
        "resources": {"ram": "2 gib", "cpu": 2},
        "runtime": {
            "processes": [{"name": "suricata", "pid": 1, "command": ["suricata", "--pcap"]}],
            "filesystem_inventory": [
                {"path": "/etc/suricata/suricata.yaml", "entry_type": "file"},
                {"path": "/var/log/suricata/fast.log", "entry_type": "file"},
                {"path": "/var/log/suricata/eve.json", "entry_type": "file"},
            ],
            "network": {
                "endpoints": [
                    {"network": "dmz-net", "ip_address": "172.20.1.50"},
                    {"network": "internal-net", "ip_address": "172.20.2.50"},
                    {"network": "security-net", "ip_address": "172.20.0.50"},
                ]
            },
            "network_sensors": [sensor or _suricata_sensor()],
        },
    }


def _network_nodes() -> dict:
    return {
        "dmz-net": {"type": "switch"},
        "internal-net": {"type": "switch"},
        "security-net": {"type": "switch"},
    }


def _infrastructure() -> dict:
    return {
        "dmz-net": {"count": 1},
        "internal-net": {"count": 1},
        "security-net": {"count": 1},
        "suricata": {"count": 1, "links": ["dmz-net", "internal-net", "security-net"]},
    }


def test_network_sensor_surface_is_node_scoped_not_top_level() -> None:
    assert "network_sensors" not in Scenario.model_fields
    assert "network_sensors" in RuntimeConfiguration.model_fields


def test_vm_runtime_network_sensor_inventory() -> None:
    node = Node(type="compute", runtime={"network_sensors": [_suricata_sensor()]})

    sensor = node.runtime.network_sensors[0]
    assert sensor.network_sensor_id == "suricata"
    assert sensor.implementation == RuntimeNetworkSensorImplementation.SURICATA
    assert sensor.sensor_kind == RuntimeNetworkSensorKind.IDS
    assert sensor.monitoring_posture == RuntimeNetworkSensorMonitoringPosture.PASSIVE
    assert sensor.capture_mode == RuntimeNetworkSensorCaptureMode.PCAP
    assert sensor.capture_interfaces == ["any"]
    assert sensor.monitored_network_refs == ["dmz-net", "internal-net", "security-net"]


def test_parser_accepts_canonical_runtime_network_sensors() -> None:
    scenario = parse_sdl(
        """
        name: network-sensor-parser
        nodes:
          dmz-net: {type: switch}
          suricata:
            type: compute
            resources: {ram: 2 gib, cpu: 2}
            runtime:
              network:
                endpoints:
                  - {network: dmz-net, ip_address: 172.20.1.50}
              network_sensors:
                - network_sensor_id: suricata
                  implementation: SURICATA
                  sensor_kind: ids
                  monitoring_posture: passive
                  capture_mode: pcap
                  capture_interfaces: any
                  monitored_network_refs: [dmz-net]
        infrastructure:
          dmz-net: 1
          suricata: {count: 1, links: [dmz-net]}
        """
    )

    sensor = scenario.nodes["suricata"].runtime.network_sensors[0]
    assert sensor.network_sensor_id == "suricata"
    assert sensor.sensor_kind == RuntimeNetworkSensorKind.IDS
    assert sensor.monitoring_posture == RuntimeNetworkSensorMonitoringPosture.PASSIVE
    assert sensor.capture_mode == RuntimeNetworkSensorCaptureMode.PCAP
    assert sensor.capture_interfaces == ["any"]
    assert sensor.monitored_network_refs == ["dmz-net"]


def test_network_sensor_rejects_duplicate_monitored_network_refs() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime network sensor monitored_network_refs"):
        RuntimeNetworkSensor(network_sensor_id="suricata", monitored_network_refs=["dmz-net", "dmz-net"])


class TestRuntimeNetworkSensorSemanticValidation:
    def test_suricata_sensor_monitoring_attached_networks_is_valid(self) -> None:
        scenario = Scenario(
            name="network-sensor",
            nodes={**_network_nodes(), "suricata": _sensor_node()},
            infrastructure=_infrastructure(),
        )

        assert _validate(scenario) == []

    def test_monitored_network_ref_must_resolve_to_infrastructure(self) -> None:
        sensor = _suricata_sensor(monitored_network_refs=["ghost-net"])
        scenario = Scenario(
            name="network-sensor",
            nodes={**_network_nodes(), "suricata": _sensor_node(sensor)},
            infrastructure=_infrastructure(),
        )

        errors = _validate(scenario)
        assert any("monitored_network_ref 'ghost-net' references undefined network" in error for error in errors)

    def test_monitored_network_ref_must_reference_switch_backed_infrastructure(self) -> None:
        sensor = _suricata_sensor(monitored_network_refs=["webapp"])
        scenario = Scenario(
            name="network-sensor",
            nodes={
                **_network_nodes(),
                "webapp": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}},
                "suricata": _sensor_node(sensor),
            },
            infrastructure={**_infrastructure(), "webapp": {"count": 1}},
        )

        errors = _validate(scenario)
        assert any("monitored_network_ref 'webapp' must reference a switch/network entry" in error for error in errors)

    def test_monitored_network_ref_must_match_runtime_endpoint_when_endpoints_are_recorded(self) -> None:
        sensor = _suricata_sensor(monitored_network_refs=["dmz-net", "internal-net"])
        node = _sensor_node(sensor)
        node["runtime"]["network"]["endpoints"] = [{"network": "dmz-net", "ip_address": "172.20.1.50"}]
        scenario = Scenario(
            name="network-sensor",
            nodes={**_network_nodes(), "suricata": node},
            infrastructure=_infrastructure(),
        )

        errors = _validate(scenario)
        assert any("monitored_network_ref 'internal-net' is not attached" in error for error in errors)

    def test_file_refs_resolve_to_runtime_filesystem_inventory_when_present(self) -> None:
        sensor = _suricata_sensor(configuration_file_refs=["/etc/suricata/missing.yaml"])
        scenario = Scenario(
            name="network-sensor",
            nodes={**_network_nodes(), "suricata": _sensor_node(sensor)},
            infrastructure=_infrastructure(),
        )

        errors = _validate(scenario)
        assert any("configuration_file_refs ref '/etc/suricata/missing.yaml'" in error for error in errors)

    def test_relationship_target_to_network_sensor_is_valid(self) -> None:
        scenario = Scenario(
            name="network-sensor",
            nodes={
                **_network_nodes(),
                "suricata": _sensor_node(),
                "client": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}},
            },
            infrastructure={**_infrastructure(), "client": {"count": 1, "links": ["dmz-net"]}},
            relationships={
                "sensor-monitors-client-network": {
                    "type": "depends_on",
                    "source": "nodes.client",
                    "target": "nodes.suricata.runtime.network_sensors.suricata",
                }
            },
        )

        assert _validate(scenario) == []


def test_module_symbol_index_rewrites_runtime_network_sensor_refs() -> None:
    scenario = Scenario(
        name="shared",
        module=ModuleDescriptor(id="acme/shared", version="1.0.0", exports={"nodes": ["suricata"]}),
        nodes={**_network_nodes(), "suricata": _sensor_node()},
        infrastructure=_infrastructure(),
    )

    named = symbol_index(
        scenario,
        namespace="shared",
        descriptor=scenario.module,
    )["named"]

    assert named["nodes.suricata.runtime.network_sensors.suricata"] == (
        "nodes.shared.suricata.runtime.network_sensors.suricata"
    )
