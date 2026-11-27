"""Runtime security-monitoring manager SDL surface tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from raes import parse_sdl
from raes._errors import SDLValidationError
from raes._module_symbols import symbol_index
from raes.nodes import (
    Node,
    RuntimeConfiguration,
    RuntimeSecurityMonitoringAgentStatus,
    RuntimeSecurityMonitoringComponentKind,
    RuntimeSecurityMonitoringComponentStatus,
    RuntimeSecurityMonitoringContentFormat,
    RuntimeSecurityMonitoringContentKind,
    RuntimeSecurityMonitoringDetectionDefinition,
    RuntimeSecurityMonitoringDetectionDefinitionKind,
    RuntimeSecurityMonitoringDetectionEngine,
    RuntimeSecurityMonitoringFieldPredicateOperator,
    RuntimeSecurityMonitoringImplementation,
    RuntimeSecurityMonitoringListenerRole,
    RuntimeSecurityMonitoringManager,
    RuntimeSecurityMonitoringSetting,
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


def _security_manager(**overrides) -> dict:
    manager = {
        "security_monitoring_manager_id": "techvault-wazuh",
        "service": "wazuh-api",
        "implementation": "wazuh",
        "manager_kind": "siem",
        "version": "v4.12.0",
        "revision": "rc1",
        "configuration_file_refs": ["/var/ossec/etc/ossec.conf"],
        "log_file_refs": ["/var/ossec/logs/ossec.log"],
        "listeners": [
            {
                "listener_id": "agent-events",
                "service": "wazuh-agent-events",
                "role": "agent_event_ingestion",
                "auth_required": True,
                "tls_enabled": True,
            },
            {
                "listener_id": "agent-enrollment",
                "service": "wazuh-enrollment",
                "role": "agent_enrollment",
                "auth_required": True,
                "tls_enabled": True,
            },
            {
                "listener_id": "manager-api",
                "service": "wazuh-api",
                "role": "api",
                "auth_required": True,
                "tls_enabled": True,
            },
        ],
        "components": [
            {"component_id": "analysisd", "kind": "analysis_engine", "name": "wazuh-analysisd", "status": "running"},
            {"component_id": "remoted", "kind": "agent_ingestion", "name": "wazuh-remoted", "status": "running"},
            {"component_id": "authd", "kind": "agent_enrollment", "name": "wazuh-authd", "status": "running"},
            {"component_id": "modulesd", "kind": "module_supervisor", "name": "wazuh-modulesd", "status": "running"},
            {"component_id": "clusterd", "kind": "cluster", "name": "wazuh-clusterd", "status": "stopped"},
            {"component_id": "api", "kind": "api", "name": "wazuh-apid", "status": "running"},
        ],
        "agents": [
            {"agent_id": "001", "name": "aptl-dns-agent", "status": "available", "group_refs": ["default"]},
            {"agent_id": "002", "name": "aptl-webapp-agent", "status": "available", "group_refs": ["default"]},
            {"agent_id": "003", "name": "dc.techvault.local", "status": "available", "group_refs": ["default"]},
        ],
        "agent_groups": [
            {
                "group_id": "default",
                "name": "default",
                "member_refs": ["001", "002", "003"],
                "configuration_file_refs": ["/var/ossec/etc/shared/default/agent.conf"],
            }
        ],
        "content_sets": [
            {
                "content_id": "wazuh-ruleset",
                "kind": "rule_corpus",
                "format": "wazuh_rule_xml",
                "file_count": 173,
                "file_refs": ["/var/ossec/ruleset/rules"],
                "loaded": True,
            },
            {
                "content_id": "wazuh-decoders",
                "kind": "decoder_corpus",
                "format": "wazuh_decoder_xml",
                "file_count": 123,
                "file_refs": ["/var/ossec/ruleset/decoders"],
                "loaded": True,
            },
        ],
        "detection_definitions": [
            {
                "definition_id": "rule-300000",
                "engine": "wazuh",
                "definition_kind": "rule",
                "native_id": "300000",
                "content_set_ref": "wazuh-ruleset",
                "source_file_ref": "/var/ossec/etc/rules/ad_rules.xml",
                "source_start_line": 4,
                "source_end_line": 9,
                "digest_algorithm": "sha256",
                "canonical_digest": "2222222222222222222222222222222222222222222222222222222222222222",
                "enabled": True,
                "loaded": True,
                "parser_accepted": True,
                "level": 3,
                "description": "Windows event parent rule",
                "groups": ["windows"],
            },
            {
                "definition_id": "rule-301010",
                "engine": "wazuh",
                "definition_kind": "correlation_rule",
                "native_id": "301010",
                "name": "Kerberoasting SPN query",
                "content_set_ref": "wazuh-ruleset",
                "source_file_ref": "/var/ossec/etc/rules/ad_rules.xml",
                "source_start_line": 12,
                "source_end_line": 35,
                "digest_algorithm": "sha256",
                "canonical_digest": "1111111111111111111111111111111111111111111111111111111111111111",
                "enabled": True,
                "loaded": True,
                "parser_accepted": True,
                "level": 10,
                "severity": "high",
                "description": "Kerberoasting-style service ticket request pattern",
                "match_strings": ["Kerberos Service Ticket Operations"],
                "regex_patterns": ["(?i)service ticket"],
                "field_predicates": [
                    {
                        "field": "win.system.eventID",
                        "operator": "equals",
                        "value": "4769",
                    }
                ],
                "decoded_as": ["json"],
                "decoder_names": ["windows_eventchannel"],
                "decoder_fields": ["win.system.eventID", "win.eventdata.serviceName"],
                "if_sid_refs": ["rule-300000"],
                "parent_definition_refs": ["rule-300000"],
                "frequency": 5,
                "timeframe_seconds": 60,
                "same_source_constraints": ["same_srcip"],
                "groups": ["windows", "kerberos"],
                "mitre_attack_ids": ["T1558.003"],
                "compliance_tags": ["pci_dss_10.6"],
                "target_refs": ["nodes.siem.services.wazuh-agent-events"],
                "evidence_refs": ["/var/ossec/logs/ossec.log"],
            },
            {
                "definition_id": "decoder-windows-eventchannel",
                "engine": "wazuh",
                "definition_kind": "decoder",
                "native_id": "windows_eventchannel",
                "content_set_ref": "wazuh-decoders",
                "source_file_ref": "/var/ossec/etc/decoders/windows_decoders.xml",
                "source_start_line": 2,
                "source_end_line": 14,
                "digest_algorithm": "sha256",
                "canonical_digest": "3333333333333333333333333333333333333333333333333333333333333333",
                "loaded": True,
                "parser_accepted": True,
                "decoder_names": ["windows_eventchannel"],
                "decoder_fields": ["win.system.eventID", "win.system.providerName"],
            },
        ],
        "settings": [
            {
                "setting_id": "json-output",
                "name": "jsonout_output",
                "value": "yes",
                "provenance": "configuration_file",
                "source_path": "/var/ossec/etc/ossec.conf",
            },
            {
                "setting_id": "vulnerability-detection",
                "name": "vulnerability_detection.enabled",
                "value": "yes",
                "provenance": "configuration_file",
                "source_path": "/var/ossec/etc/ossec.conf",
            },
        ],
    }
    manager.update(overrides)
    return manager


def _manager_node(manager: dict | None = None) -> dict:
    return {
        "type": "compute",
        "resources": {"ram": "2 gib", "cpu": 2},
        "services": [
            {"port": 1514, "protocol": "tcp", "name": "wazuh-agent-events"},
            {"port": 1515, "protocol": "tcp", "name": "wazuh-enrollment"},
            {"port": 514, "protocol": "udp", "name": "wazuh-syslog"},
            {"port": 55000, "protocol": "tcp", "name": "wazuh-api"},
        ],
        "runtime": {
            "filesystem_inventory": [
                {"path": "/var/ossec/etc/ossec.conf", "entry_type": "file"},
                {"path": "/var/ossec/logs/ossec.log", "entry_type": "file"},
                {"path": "/var/ossec/etc/shared/default/agent.conf", "entry_type": "file"},
                {"path": "/var/ossec/ruleset/rules", "entry_type": "directory"},
                {"path": "/var/ossec/ruleset/decoders", "entry_type": "directory"},
                {"path": "/var/ossec/etc/rules/ad_rules.xml", "entry_type": "file"},
                {"path": "/var/ossec/etc/decoders/windows_decoders.xml", "entry_type": "file"},
            ],
            "security_monitoring_managers": [manager or _security_manager()],
        },
    }


def test_security_monitoring_surface_is_node_scoped_not_top_level() -> None:
    assert "security_monitoring_managers" not in Scenario.model_fields
    assert "security_monitoring_managers" in RuntimeConfiguration.model_fields


def test_vm_runtime_security_monitoring_manager_inventory() -> None:
    node = Node(type="compute", runtime={"security_monitoring_managers": [_security_manager()]})

    manager = node.runtime.security_monitoring_managers[0]
    assert manager.security_monitoring_manager_id == "techvault-wazuh"
    assert manager.implementation == RuntimeSecurityMonitoringImplementation.WAZUH
    assert manager.listeners[0].role == RuntimeSecurityMonitoringListenerRole.AGENT_EVENT_INGESTION
    assert manager.listeners[0].auth_required is True
    assert manager.components[0].kind == RuntimeSecurityMonitoringComponentKind.ANALYSIS_ENGINE
    assert manager.components[0].status == RuntimeSecurityMonitoringComponentStatus.RUNNING
    assert manager.agents[0].status == RuntimeSecurityMonitoringAgentStatus.AVAILABLE
    assert manager.content_sets[0].kind == RuntimeSecurityMonitoringContentKind.RULE_CORPUS
    assert manager.content_sets[1].format == RuntimeSecurityMonitoringContentFormat.WAZUH_DECODER_XML
    assert manager.detection_definitions[1].engine == RuntimeSecurityMonitoringDetectionEngine.WAZUH
    assert (
        manager.detection_definitions[1].definition_kind
        == RuntimeSecurityMonitoringDetectionDefinitionKind.CORRELATION_RULE
    )
    assert manager.detection_definitions[1].field_predicates[0].operator == (
        RuntimeSecurityMonitoringFieldPredicateOperator.EQUALS
    )


def test_detection_definition_model_preserves_wazuh_semantics() -> None:
    definition = RuntimeSecurityMonitoringDetectionDefinition(
        definition_id="rule-301011",
        engine="WAZUH",
        definition_kind="list-backed-rule",
        native_id="301011",
        content_set_ref="wazuh-ruleset",
        source_file_ref="/var/ossec/etc/rules/ad_rules.xml",
        source_start_line="36",
        source_end_line="52",
        digest_algorithm="sha256",
        canonical_digest="4444444444444444444444444444444444444444444444444444444444444444",
        enabled="yes",
        loaded="true",
        parser_accepted="1",
        level="7",
        field_predicates=[{"field": "win.eventdata.serviceName", "operator": "matches", "value": ".*"}],
        same_source_constraints="same_srcuser",
        mitre_attack_ids="T1558.003",
    )

    assert definition.engine == RuntimeSecurityMonitoringDetectionEngine.WAZUH
    assert definition.definition_kind == RuntimeSecurityMonitoringDetectionDefinitionKind.LIST_BACKED_RULE
    assert definition.loaded is True
    assert definition.parser_accepted is True
    assert definition.level == 7
    assert definition.field_predicates[0].operator == RuntimeSecurityMonitoringFieldPredicateOperator.MATCHES
    assert definition.same_source_constraints == ["same_srcuser"]
    assert definition.mitre_attack_ids == ["T1558.003"]


def test_parser_accepts_canonical_runtime_security_monitoring_managers() -> None:
    scenario = parse_sdl(
        """
        name: security-monitoring-parser
        nodes:
          siem:
            type: compute
            resources: {ram: 2 gib, cpu: 2}
            services:
              - {port: 55000, name: wazuh-api}
            runtime:
              security_monitoring_managers:
                - security_monitoring_manager_id: techvault-wazuh
                  service: wazuh-api
                  implementation: WAZUH
                  manager_kind: siem
                  listeners:
                    - listener_id: manager-api
                      service: wazuh-api
                      role: api
                      auth_required: true
                  content_sets:
                    - content_id: wazuh-ruleset
                      kind: rule-corpus
                      format: wazuh-rule-xml
                      file_count: 173
                  detection_definitions:
                    - definition_id: rule-301010
                      engine: WAZUH
                      definition_kind: correlation-rule
                      native_id: "301010"
                      content_set_ref: wazuh-ruleset
                      source_file_ref: /var/ossec/etc/rules/ad_rules.xml
                      source_start_line: 12
                      source_end_line: 35
                      digest_algorithm: sha256
                      canonical_digest: "1111111111111111111111111111111111111111111111111111111111111111"
                      loaded: true
                      parser_accepted: true
                      level: 10
                      field_predicates:
                        - field: win.system.eventID
                          operator: equals
                          value: "4769"
                      mitre_attack_ids: [T1558.003]
        """
    )

    manager = scenario.nodes["siem"].runtime.security_monitoring_managers[0]
    assert manager.security_monitoring_manager_id == "techvault-wazuh"
    assert manager.listeners[0].role == RuntimeSecurityMonitoringListenerRole.API
    assert manager.content_sets[0].format == RuntimeSecurityMonitoringContentFormat.WAZUH_RULE_XML
    assert manager.detection_definitions[0].definition_id == "rule-301010"
    assert manager.detection_definitions[0].definition_kind == (
        RuntimeSecurityMonitoringDetectionDefinitionKind.CORRELATION_RULE
    )
    assert manager.detection_definitions[0].field_predicates[0].operator == (
        RuntimeSecurityMonitoringFieldPredicateOperator.EQUALS
    )


def test_security_monitoring_manager_rejects_duplicate_stable_ids() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime security-monitoring stable id 'manager-api'"):
        RuntimeSecurityMonitoringManager(
            **_security_manager(
                components=[
                    {"component_id": "manager-api", "kind": "api", "name": "wazuh-apid"},
                ]
            )
        )


def test_security_monitoring_manager_rejects_duplicate_detection_definition_ids() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime security-monitoring stable id 'rule-301010'"):
        RuntimeSecurityMonitoringManager(
            **_security_manager(
                detection_definitions=[
                    {"definition_id": "rule-301010", "engine": "wazuh", "definition_kind": "rule"},
                    {"definition_id": "rule-301010", "engine": "wazuh", "definition_kind": "rule"},
                ]
            )
        )


def test_detection_definition_digest_requires_algorithm_pair() -> None:
    with pytest.raises(ValidationError, match="canonical_digest requires digest_algorithm"):
        RuntimeSecurityMonitoringDetectionDefinition(
            definition_id="rule-301010",
            engine="wazuh",
            definition_kind="rule",
            canonical_digest="1111111111111111111111111111111111111111111111111111111111111111",
        )


@pytest.mark.parametrize("setting_name", ["api_token", "api_key", "shared_key"])
def test_security_monitoring_setting_accepts_secret_named_scenario_value(setting_name: str) -> None:
    setting = RuntimeSecurityMonitoringSetting(
        setting_id="api-token",
        name=setting_name,
        value="plaintext-token",
        value_classification="plain",
    )

    assert setting.value == "plaintext-token"


class TestRuntimeSecurityMonitoringSemanticValidation:
    def test_manager_with_same_node_service_refs_is_valid(self) -> None:
        assert _validate(Scenario(name="security-monitoring", nodes={"siem": _manager_node()})) == []

    def test_listener_service_ref_must_reference_same_node_service(self) -> None:
        manager = _security_manager(
            listeners=[
                {
                    "listener_id": "manager-api",
                    "service": "nodes.other.services.wazuh-api",
                    "role": "api",
                }
            ]
        )
        scenario = Scenario(
            name="security-monitoring",
            nodes={
                "siem": _manager_node(manager),
                "other": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "services": [{"port": 55000, "name": "wazuh-api"}],
                },
            },
        )

        errors = _validate(scenario)
        assert any("listener 'manager-api'" in error and "same node" in error for error in errors)

    def test_file_refs_resolve_to_runtime_filesystem_inventory_when_present(self) -> None:
        manager = _security_manager(configuration_file_refs=["/var/ossec/etc/missing.conf"])
        errors = _validate(Scenario(name="security-monitoring", nodes={"siem": _manager_node(manager)}))
        assert any("configuration_file_refs ref '/var/ossec/etc/missing.conf'" in error for error in errors)

    def test_detection_definition_content_set_ref_must_resolve_to_content_set(self) -> None:
        manager = _security_manager(
            detection_definitions=[
                {
                    "definition_id": "rule-301010",
                    "engine": "wazuh",
                    "definition_kind": "rule",
                    "content_set_ref": "ghost-corpus",
                }
            ]
        )
        errors = _validate(Scenario(name="security-monitoring", nodes={"siem": _manager_node(manager)}))
        assert any("content_set_ref 'ghost-corpus'" in error for error in errors)

    def test_detection_definition_source_file_ref_resolves_to_runtime_filesystem_inventory(self) -> None:
        manager = _security_manager(
            detection_definitions=[
                {
                    "definition_id": "rule-301010",
                    "engine": "wazuh",
                    "definition_kind": "rule",
                    "source_file_ref": "/var/ossec/etc/rules/missing.xml",
                }
            ]
        )
        errors = _validate(Scenario(name="security-monitoring", nodes={"siem": _manager_node(manager)}))
        assert any("source_file_ref ref '/var/ossec/etc/rules/missing.xml'" in error for error in errors)

    def test_detection_definition_correlation_refs_must_resolve_to_definitions(self) -> None:
        manager = _security_manager(
            detection_definitions=[
                {
                    "definition_id": "rule-301010",
                    "engine": "wazuh",
                    "definition_kind": "correlation_rule",
                    "if_sid_refs": ["ghost-rule"],
                    "parent_definition_refs": ["ghost-parent"],
                }
            ]
        )
        errors = _validate(Scenario(name="security-monitoring", nodes={"siem": _manager_node(manager)}))
        assert any("if_sid_ref 'ghost-rule'" in error for error in errors)
        assert any("parent_definition_ref 'ghost-parent'" in error for error in errors)

    def test_detection_definition_target_refs_must_resolve_to_targetable_elements(self) -> None:
        manager = _security_manager(
            detection_definitions=[
                {
                    "definition_id": "rule-301010",
                    "engine": "wazuh",
                    "definition_kind": "rule",
                    "target_refs": ["ghost-service"],
                }
            ]
        )
        errors = _validate(Scenario(name="security-monitoring", nodes={"siem": _manager_node(manager)}))
        assert any("target_ref 'ghost-service'" in error for error in errors)

    def test_agent_group_member_refs_must_resolve_to_agents(self) -> None:
        manager = _security_manager(
            agent_groups=[{"group_id": "default", "name": "default", "member_refs": ["ghost-agent"]}]
        )
        errors = _validate(Scenario(name="security-monitoring", nodes={"siem": _manager_node(manager)}))
        assert any("member_ref 'ghost-agent'" in error for error in errors)

    def test_agent_group_refs_must_resolve_to_groups(self) -> None:
        manager = _security_manager(
            agents=[{"agent_id": "001", "name": "aptl-dns-agent", "group_refs": ["ghost-group"]}],
            agent_groups=[{"group_id": "default", "name": "default"}],
        )
        errors = _validate(Scenario(name="security-monitoring", nodes={"siem": _manager_node(manager)}))
        assert any("group_ref 'ghost-group'" in error for error in errors)

    def test_relationship_target_to_manager_and_child_records_is_valid(self) -> None:
        scenario = Scenario(
            name="security-monitoring",
            nodes={
                "siem": _manager_node(),
                "client": {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}},
            },
            relationships={
                "client-to-siem": {
                    "type": "connects_to",
                    "source": "nodes.client",
                    "target": "nodes.siem.runtime.security_monitoring_managers.techvault-wazuh",
                },
                "manager-loads-rules": {
                    "type": "depends_on",
                    "source": "nodes.siem.runtime.security_monitoring_managers.techvault-wazuh",
                    "target": (
                        "nodes.siem.runtime.security_monitoring_managers.techvault-wazuh.content_sets.wazuh-ruleset"
                    ),
                },
                "manager-loads-definition": {
                    "type": "depends_on",
                    "source": (
                        "nodes.siem.runtime.security_monitoring_managers.techvault-wazuh.content_sets.wazuh-ruleset"
                    ),
                    "target": (
                        "nodes.siem.runtime.security_monitoring_managers."
                        "techvault-wazuh.detection_definitions.rule-301010"
                    ),
                },
                "agent-inventory": {
                    "type": "depends_on",
                    "source": ("nodes.siem.runtime.security_monitoring_managers.techvault-wazuh.agent_groups.default"),
                    "target": "nodes.siem.runtime.security_monitoring_managers.techvault-wazuh.agents.001",
                },
            },
        )

        assert _validate(scenario) == []


def test_module_symbol_index_rewrites_runtime_security_monitoring_refs() -> None:
    scenario = Scenario(
        name="shared",
        module=ModuleDescriptor(id="acme/shared", version="1.0.0", exports={"nodes": ["siem"]}),
        nodes={"siem": _manager_node()},
    )

    named = symbol_index(
        scenario,
        namespace="shared",
        descriptor=scenario.module,
    )["named"]

    assert named["nodes.siem.runtime.security_monitoring_managers.techvault-wazuh"] == (
        "nodes.shared.siem.runtime.security_monitoring_managers.techvault-wazuh"
    )
    assert named["nodes.siem.runtime.security_monitoring_managers.techvault-wazuh.listeners.manager-api"] == (
        "nodes.shared.siem.runtime.security_monitoring_managers.techvault-wazuh.listeners.manager-api"
    )
    assert named["nodes.siem.runtime.security_monitoring_managers.techvault-wazuh.agents.001"] == (
        "nodes.shared.siem.runtime.security_monitoring_managers.techvault-wazuh.agents.001"
    )
    assert named["nodes.siem.runtime.security_monitoring_managers.techvault-wazuh.content_sets.wazuh-ruleset"] == (
        "nodes.shared.siem.runtime.security_monitoring_managers.techvault-wazuh.content_sets.wazuh-ruleset"
    )
    assert named[
        "nodes.siem.runtime.security_monitoring_managers.techvault-wazuh.detection_definitions.rule-301010"
    ] == ("nodes.shared.siem.runtime.security_monitoring_managers.techvault-wazuh.detection_definitions.rule-301010")
